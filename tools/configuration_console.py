# File: tools/tune_camera.py

#!/usr/bin/env python3

import copy
import cv2
import json
import time
import tkinter as tk
from tkinter import font as tkFont
import threading
import sys
import os
import logging
import numpy as np
from typing import Optional, Dict, Any

# --- Path Setup ---
_CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_CURRENT_SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- Basic Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CameraTuner")

# --- Project Imports ---
try:
    from controllers.unified_controller import UnifiedController
    from controllers.finite_state_machine import DeviceUnderTest # Add this import
    from controllers.logitech_webcam import (
        LogitechLedChecker,
        OVERLAY_TEXT_COLOR_MAIN,
        OVERLAY_LED_INDICATOR_OFF_COLOR,
        OVERLAY_LED_INDICATOR_RADIUS,
        _CAMERA_SETTINGS_FILE
    )
except ImportError as e:
    logger.critical(f"Failed to import project modules: {e}. Make sure the script is run from the project root or the path setup is correct.", exc_info=True)
    sys.exit(1)

CAMERA_SETTINGS_SAVE_PATH = _CAMERA_SETTINGS_FILE


# --- Smart, Cross-Platform Backend Selection ---
platform = sys.platform
if platform.startswith('win'):
    CAMERA_BACKEND = cv2.CAP_DSHOW
    print("Platform: Windows. Using optimized DSHOW backend.")
elif platform == 'darwin':
    CAMERA_BACKEND = cv2.CAP_AVFOUNDATION
    print("Platform: macOS. Using optimized AVFOUNDATION backend.")
elif platform.startswith('linux'):
    CAMERA_BACKEND = cv2.CAP_V4L2
    print("Platform: Linux. Using optimized V4L2 backend.")
else:
    CAMERA_BACKEND = None
    print(f"Platform: {platform}. Using default backend (may be slow).")

# --- Other Configuration ---
CAMERA_ID = 0


# --- Main Application Class ---
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Configuration Console")
        
        # --- Instance variables ---
        self.controller: Optional[UnifiedController] = None
        self.checker: Optional[LogitechLedChecker] = None
        self.dut: Optional[DeviceUnderTest] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.imgtk = None
        self._debounce_job = None

        # --- Variables for ROI Tuning ---
        self.tune_led_button: Optional[tk.Button] = None
        self.is_tuning = False
        self.tuning_step = 0
        self.tuning_leds = ["red", "green", "blue"]
        self.tuning_status_var = tk.StringVar(value="")
        self.new_rois: Dict[str, tuple] = {}

        # --- Variable to track Shift key state ---
        self.shift_is_held = False

        # --- Define UI Fonts and Variables ---
        self.label_font = tkFont.Font(family="Helvetica", size=10, weight="bold")
        self.value_font = tkFont.Font(family="Courier", size=11)
        self.target_settings = {"focus": tk.IntVar(value=0), "brightness": tk.IntVar(value=128), "exposure": tk.IntVar(value=7)}
        
        # Variables to track toggle button state (default to OFF)
        self.power_state = tk.BooleanVar(value=False)
        self.usb3_state = tk.BooleanVar(value=False)

        # Dictionary to hold BooleanVar for each keypad key
        self.keypad_states: Dict[str, tk.BooleanVar] = {key: tk.BooleanVar(value=False) for key in [
            'key1', 'key2', 'key3', 'key4', 'key5', 'key6', 'key7', 'key8', 'key9', 'key0', 'lock', 'unlock'
        ]}

        # Variable to hold the scanned barcode text
        self.scanned_barcode_text = tk.StringVar(value="")


        self.keypad_button_widgets: Dict[str, tk.Button] = {} 
        self.power_button: Optional[tk.Checkbutton] = None
        self.usb3_button: Optional[tk.Checkbutton] = None
        self.scan_button: Optional[tk.Button] = None
        self.tune_led_button: Optional[tk.Button] = None
        self.sliders: list = []
        
        # --- UI Layout Setup ---
        main_area_frame = tk.Frame(root)
        main_area_frame.pack(side=tk.TOP, expand=True, fill=tk.BOTH, padx=5, pady=5)

        self.left_panel = tk.Frame(main_area_frame, padx=10, pady=10)
        self.left_panel.pack(side=tk.LEFT, fill=tk.Y)

        self.right_panel = tk.Frame(main_area_frame)
        self.right_panel.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)

        self.video_label = tk.Label(self.right_panel, text="Initializing Hardware...", padx=100, pady=100, bg="black", fg="white")
        self.video_label.pack(side=tk.TOP, expand=True, fill=tk.BOTH)
        
        # --- Populate all controls (initially disabled) ---
        self._create_controls_layout() 

        # --- Initializer logic ---
        # --- Bind keyboard events for Shift key detection ---
        self.root.bind('<KeyPress-Shift_L>', self._on_shift_press)
        self.root.bind('<KeyPress-Shift_R>', self._on_shift_press)
        self.root.bind('<KeyRelease-Shift_L>', self._on_shift_release)
        self.root.bind('<KeyRelease-Shift_R>', self._on_shift_release)
        self.root.bind("<Button-1>", self._on_video_click)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        threading.Thread(target=self.initialize_hardware, daemon=True).start()

    def _on_shift_press(self, event):
        """Event handler for when the Shift key is pressed."""
        self.shift_is_held = True

    def _on_shift_release(self, event):
        """
        Event handler for when the Shift key is released.
        Also turns off all active keys that were toggled on.
        """
        self.shift_is_held = False
        
        if not self.controller:
            logger.warning("Controller not ready, cannot release keys on Shift-up.")
            return
        
        logger.info("Shift key released. Releasing all active keys.")
        keys_were_released = False

        # Iterate through the state dictionary and turn off any active keys
        for key_name, state_var in self.keypad_states.items():
            if state_var.get():  # Check if the key is currently ON
                keys_were_released = True
                logger.debug(f"Releasing key via Shift-up: {key_name}")
                
                # 1. Update the Tkinter state variable
                state_var.set(False)
                
                # 2. Update the button's visual appearance
                self.keypad_button_widgets[key_name].config(relief=tk.RAISED)
                
                # 3. Send the 'off' command to the hardware
                self.controller.off(key_name)
        
        if keys_were_released:
            logger.info("All active keys have been released.")

    def _create_controls_layout(self):
        """Creates and packs all UI control elements (keypad, toggles, sliders)."""
        # Keypad Frame
        keypad_frame = tk.Frame(self.left_panel, relief=tk.GROOVE, borderwidth=2)
        keypad_frame.pack(side=tk.TOP, pady=10, padx=5)

        tk.Label(keypad_frame, text="Manual Keypad", font=self.label_font).grid(row=0, column=0, columnspan=3, pady=(5, 10))

        # --- CORRECTED: Create simple placeholder Buttons without commands ---
        KEYPAD_LAYOUT_INITIAL = [
            ['key1', 'key2', 'key3'], ['key4', 'key5', 'key6'],
            ['key7', 'key8', 'key9'], ['lock', 'key0', 'unlock']
        ]
        button_font = tkFont.Font(family="Helvetica", size=10)
        for row_idx, row_of_keys in enumerate(KEYPAD_LAYOUT_INITIAL):
            for col_idx, key_name in enumerate(row_of_keys):
                # Use tk.Button as a placeholder. It will be replaced by the fully-functional
                # button in _recreate_keypad_and_enable_buttons.
                button = tk.Button(
                    keypad_frame,
                    text=key_name,
                    font=button_font,
                    width=7, height=2,
                    state=tk.DISABLED,
                    relief=tk.RAISED
                )
                button.grid(row=row_idx + 1, column=col_idx, padx=5, pady=5)
                # We don't need to store a reference here as it gets overwritten.

        # Toggle buttons & Barcode scan
        toggle_button_frame = tk.Frame(self.left_panel, relief=tk.GROOVE, borderwidth=1, padx=5, pady=5)
        toggle_button_frame.pack(side=tk.TOP, pady=10, fill=tk.X)
        
        power_usb_frame = tk.Frame(toggle_button_frame)
        power_usb_frame.pack(side=tk.TOP, fill=tk.X, expand=True, pady=5)
        
        self.power_button = tk.Checkbutton(power_usb_frame, text="Power", variable=self.power_state, indicatoron=False, width=12, state=tk.DISABLED, relief=tk.RAISED)
        self.power_button.config(command=lambda btn=self.power_button: self._handle_phidget_toggle("connect", self.power_state, btn))
        self.power_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.usb3_button = tk.Checkbutton(power_usb_frame, text="USB3", variable=self.usb3_state, indicatoron=False, width=12, state=tk.DISABLED, relief=tk.RAISED)
        self.usb3_button.config(command=lambda btn=self.usb3_button: self._handle_phidget_toggle("usb3", self.usb3_state, btn))
        self.usb3_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.scan_button = tk.Button(toggle_button_frame, text="Scan Barcode", command=self._scan_barcode_action, state=tk.DISABLED)
        self.scan_button.pack(pady=(10, 5), fill=tk.X, expand=True)

        scanned_barcode_label = tk.Label(toggle_button_frame, textvariable=self.scanned_barcode_text, font=tkFont.Font(family="Courier", size=8), wraplength=150)
        scanned_barcode_label.pack(pady=(0,5), fill=tk.X)

        # Sliders
        sliders_frame = tk.Frame(self.left_panel, relief=tk.GROOVE, borderwidth=1, padx=5, pady=5)
        sliders_frame.pack(side=tk.TOP, pady=10, fill=tk.X)
        
        self.sliders.append(self._create_slider_control(sliders_frame, "Focus", "focus", 0, 255))
        self.sliders.append(self._create_slider_control(sliders_frame, "Brightness", "brightness", 0, 255))
        self.sliders.append(self._create_slider_control(sliders_frame, "Exposure", "exposure", 2, 13))

        # --- Button Area at the bottom of the left panel ---
        # NOTE: Packing with side=tk.BOTTOM adds widgets from the bottom up.
        # So, the 'Save' button is packed first to appear at the very bottom.
        
        # 'Save Settings' button
        save_button = tk.Button(self.left_panel, text="Save Settings", command=self._save_settings_action)
        save_button.pack(side=tk.BOTTOM, fill=tk.X, pady=5, ipady=5)

        # 'Tune LED Coordinates' button (will appear above the Save button)
        self.tune_led_button = tk.Button(self.left_panel, text="Tune LED Coordinates", command=self._start_tuning_action, state=tk.DISABLED)
        self.tune_led_button.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(10,0), ipady=5)

        # Status label for the tuning process (will appear above the Tune button)
        self.tuning_status_label = tk.Label(self.left_panel, textvariable=self.tuning_status_var, font=self.label_font, fg="blue")
        self.tuning_status_label.pack(side=tk.BOTTOM, pady=5)

    def _on_video_click(self, event):
        """Callback for when the user clicks on the video feed during ROI tuning."""
        # --- FIX: Drastically simplify coordinate handling ---
        # Since the event is bound to the parent panel that the video label fills,
        # event.x and event.y are already the correct coordinates relative to the video feed.
        relative_x = event.x
        relative_y = event.y
        logger.debug(f"Video panel click event at: x={relative_x}, y={relative_y}")
        # --- END FIX ---
        if not self.is_tuning:
            return

        if self.tuning_step >= len(self.tuning_leds):
            return  # Safeguard against extra clicks

        led_key = self.tuning_leds[self.tuning_step]
        logger.info(f"Tuning '{led_key}': Click received at ({event.x}, {event.y}).")

        # Use a fixed size for the new ROI
        roi_width, roi_height = 40, 40
        
        # User clicks the center, so calculate the top-left corner
        new_x = event.x - (roi_width // 2) - 2
        new_y = event.y - (roi_height // 2) - 160
        
        # Update the temporary ROI dictionary. This is the only state that changes here.
        self.new_rois[led_key] = (new_x, new_y, roi_width, roi_height)
        
        # Move to the next step
        self.tuning_step += 1
        
        if self.tuning_step < len(self.tuning_leds):
            # --- FIX: Set text and color for the NEXT step ---
            next_led_key = self.tuning_leds[self.tuning_step]
            self.tuning_status_var.set(f"Click on the {next_led_key.upper()} LED")
            if self.tuning_status_label:
                # The color name (e.g., "green") is a valid Tkinter color.
                self.tuning_status_label.config(fg=next_led_key)
        else:
            # Finished tuning all LEDs
            self._finish_tuning()

    def _start_tuning_action(self):
        """Begins the interactive ROI tuning process."""
        if not self.checker:
            logger.error("Cannot start tuning, camera checker not ready.")
            return
        self.is_tuning = True
        self.tuning_step = 0
        self.new_rois = {
            key: config.get('roi', (0, 0, 10, 10))
            for key, config in self.checker.led_configs.items()
        }
        
        # Disable other controls to avoid conflicts
        if self.power_button:
            self.power_button.config(state=tk.DISABLED)
        if self.usb3_button:
            self.usb3_button.config(state=tk.DISABLED)
        if self.scan_button:
            self.scan_button.config(state=tk.DISABLED)
        for slider in self.sliders:
            slider.config(state=tk.DISABLED)
        
        # Set initial instruction
        first_led = self.tuning_leds[0]
        self.tuning_status_var.set(f"Click on the {first_led.upper()} LED")
        if self.tuning_status_label:
            self.tuning_status_label.config(fg=first_led)
        logger.info(f"Starting ROI tuning. Please click on the {first_led.upper()} LED.")

    def _finish_tuning(self):
        """Finalizes the ROI tuning process, saves settings, and re-enables controls."""
        self.is_tuning = False
        self.tuning_status_var.set("Tuning complete. Saving...")
        if self.tuning_status_label:
            self.tuning_status_label.config(fg="black")
        logger.info("Tuning complete. Applying and saving new ROI coordinates...")

        # Apply the tuned ROIs to the live checker instance
        if self.checker:
            for key, roi in self.new_rois.items():
                if key in self.checker.led_configs:
                    self.checker.led_configs[key]['roi'] = roi
        
        self._save_settings()
        
        # Re-enable controls
        if self.power_button:
            self.power_button.config(state=tk.NORMAL)
        if self.usb3_button:
            self.usb3_button.config(state=tk.NORMAL)
        if self.scan_button:
            self.scan_button.config(state=tk.NORMAL)
        for slider in self.sliders:
            slider.config(state=tk.NORMAL)
            
        # Clear the status message after a short delay
        self.root.after(2000, lambda: self.tuning_status_var.set(""))
            
        # Clear the status message after a short delay
        self.root.after(2000, lambda: self.tuning_status_var.set(""))

    def _on_keypad_press(self, event, key_name: str):
        """Handles the mouse-down event on a keypad button."""
        if not self.controller:
            logger.warning("Controller not ready.")
            return

        button_widget = event.widget
        if self.shift_is_held:
            # --- SHIFT-HELD: Multi-Toggle Logic ---
            # Invert the current state and apply it.
            new_state = not self.keypad_states[key_name].get()
            self.keypad_states[key_name].set(new_state)
            
            if new_state: # Turning ON
                logger.info(f"Keypad multi-toggle: '{key_name}' ON.")
                self.controller.on(key_name)
                button_widget.config(relief=tk.SUNKEN)
            else: # Turning OFF
                logger.info(f"Keypad multi-toggle: '{key_name}' OFF.")
                self.controller.off(key_name)
                button_widget.config(relief=tk.RAISED)
        else:
            # --- NORMAL: Momentary Press Logic ---
            logger.info(f"Keypad momentary press: '{key_name}' ON.")
            # Turn on the Phidget channel and sink the button.
            self.controller.on(key_name)
            button_widget.config(relief=tk.SUNKEN)

    def _on_keypad_release(self, event, key_name: str):
        """Handles the mouse-up event on a keypad button."""
        if not self.controller:
            return
            
        # If shift is held, the state is persistent, so we do nothing on release.
        if self.shift_is_held:
            return

        # --- NORMAL: Momentary Release Logic ---
        logger.info(f"Keypad momentary press: '{key_name}' OFF.")
        # Turn off the Phidget channel and raise the button.
        self.controller.off(key_name)
        event.widget.config(relief=tk.RAISED)

    def _trigger_key_press(self, key_name: str):
        # This method is no longer used for keypad buttons, but keeping it for completeness if needed elsewhere
        pass 

    def _handle_phidget_toggle(self, channel_name: str, state_variable: tk.BooleanVar, button_widget: tk.Checkbutton):
        """
        Handles on/off logic for a phidget channel (e.g., "connect", "usb3") and updates the button's relief.
        """
        if not self.controller:
            logger.warning("Controller not ready, cannot toggle channel.")
            state_variable.set(not state_variable.get()) # Revert checkbox state
            button_widget.config(relief=tk.RAISED) # Ensure it looks "off" if disabled
            return
        
        if state_variable.get():
            logger.info(f"Toggling '{channel_name}' ON.")
            self.controller.on(channel_name)
            button_widget.config(relief=tk.SUNKEN)
        else:
            logger.info(f"Toggling '{channel_name}' OFF.")
            self.controller.off(channel_name)
            button_widget.config(relief=tk.RAISED)

    def _scan_barcode_action(self):
        """Triggers a barcode scan in a background thread to not freeze the UI."""
        if not self.controller:
            logger.warning("Controller not ready, cannot scan barcode.")
            self.scanned_barcode_text.set("Scan Failed: Controller Not Ready")
            self.root.after(3000, lambda: self.scanned_barcode_text.set("")) 
            return
        
        logger.info("Scan barcode button pressed. Starting scan thread...")
        threading.Thread(target=self._perform_barcode_scan, daemon=True).start()

    def _perform_barcode_scan(self):
        """Performs the actual barcode scan and updates the UI variable."""
        if not self.controller:
            self.root.after(0, lambda: self.scanned_barcode_text.set("Scan Failed: Internal Error"))
            self.root.after(3000, lambda: self.scanned_barcode_text.set(""))
            logger.error("Controller is None inside _perform_barcode_scan thread. This should not happen.")
            return

        self.root.after(0, lambda: self.scanned_barcode_text.set("Scanning..."))
        
        scanned_data = self.controller.scan_barcode()
        
        if scanned_data:
            self.root.after(0, lambda: self.scanned_barcode_text.set(scanned_data))
        else:
            self.root.after(0, lambda: self.scanned_barcode_text.set("TIMEOUT / No Data"))

        self.root.after(3000, lambda: self.scanned_barcode_text.set(""))


    def initialize_hardware(self):
        """Initializes hardware in a background thread, then schedules UI finalization."""
        try:
            logger.info("Initializing UnifiedController...")
            self.controller = UnifiedController(
                camera_id=CAMERA_ID,
                logger_instance=logger.getChild("UnifiedCtrl"),
                replay_output_dir=None
            )

            if not self.controller.is_fully_initialized:
                error_msg = "Hardware Initialization Failed. Check logs for details (e.g., Phidget/Camera init)."
                self.video_label.config(text=error_msg)
                logger.critical(error_msg)
                return

            self.dut = DeviceUnderTest(at_controller=self.controller) 
            self.checker = self.controller._camera_checker
            self.cap = self.checker.cap if self.checker else None
            
            self.scanned_barcode_text.set("")
            
            self.root.after(0, self.finish_ui_setup)
            
        except Exception as e:
            error_msg = f"Hardware Init Error:\n{e}"
            self.video_label.config(text=error_msg)
            logger.critical(error_msg, exc_info=True)

    def finish_ui_setup(self):
        """Populates the remaining UI elements now that hardware is initialized."""
        self.populate_sliders_from_camera()
        
        # Re-create the keypad with the correct layout and enable buttons
        self._recreate_keypad_and_enable_buttons()

        # Enable toggle and scan buttons, and set their initial relief
        if self.power_button: 
            self.power_button.config(state=tk.NORMAL)
            self.power_button.config(relief=tk.RAISED if not self.power_state.get() else tk.SUNKEN)
        if self.usb3_button: 
            self.usb3_button.config(state=tk.NORMAL)
            self.usb3_button.config(relief=tk.RAISED if not self.usb3_state.get() else tk.SUNKEN)
        if self.scan_button: self.scan_button.config(state=tk.NORMAL)
        if self.tune_led_button: self.tune_led_button.config(state=tk.NORMAL)

        # Enable sliders
        for slider in self.sliders:
            slider.config(state=tk.NORMAL)

        self._update_frame()

    def _recreate_keypad_and_enable_buttons(self):
        """Destroys existing keypad buttons and recreates them with correct layout and state."""
        keypad_frame = None
        for child in self.left_panel.winfo_children():
            if isinstance(child, tk.Frame) and child.cget('relief') == 'groove':
                is_keypad_frame = any(isinstance(w, (tk.Checkbutton, tk.Button)) for w in child.winfo_children())
                if is_keypad_frame:
                    keypad_frame = child
                    break
        
        if keypad_frame:
            for widget in keypad_frame.winfo_children():
                widget.destroy()
            
            tk.Label(keypad_frame, text="Manual Keypad", font=self.label_font).grid(row=0, column=0, columnspan=3, pady=(5, 10))

            if self.dut and self.dut.secure_key:
                logger.info("Secure_key device detected, using 2-column keypad layout.")
                KEYPAD_LAYOUT = [
                    ['key1', 'key2'], ['key3', 'key4'], ['key5', 'key6'],
                    ['key7', 'key8'], ['key9', 'key0'], ['lock', 'unlock']
                ]
            else:
                logger.info("Standard device detected, using 3-column keypad layout.")
                KEYPAD_LAYOUT = [
                    ['key1', 'key2', 'key3'],
                    ['key4', 'key5', 'key6'],
                    ['key7', 'key8', 'key9'],
                    ['lock', 'key0', 'unlock']
                ]
            
            button_font = tkFont.Font(family="Helvetica", size=10)
            self.keypad_button_widgets.clear() # Clear old references
            for row_idx, row_of_keys in enumerate(KEYPAD_LAYOUT):
                for col_idx, key_name in enumerate(row_of_keys):
                    # Use tk.Button for the keypad
                    button = tk.Button(
                        keypad_frame,
                        text=key_name,
                        font=button_font,
                        width=7, height=2,
                        state=tk.NORMAL,
                        relief=tk.RAISED
                    )
                    # Bind press and release events
                    button.bind('<ButtonPress-1>', lambda event, k=key_name: self._on_keypad_press(event, k))
                    button.bind('<ButtonRelease-1>', lambda event, k=key_name: self._on_keypad_release(event, k))

                    button.grid(row=row_idx + 1, column=col_idx, padx=5, pady=5)
                    self.keypad_button_widgets[key_name] = button # Store reference
            
            # The 'Release All' button has been removed.
        else:
            logger.error("Could not find keypad_frame to re-create buttons.")

    def populate_sliders_from_camera(self):
        """Safely updates the Tkinter variables with current camera properties."""
        if not self.cap or not self.cap.isOpened():
            return
        logger.info("Reading initial camera settings...")
        self.target_settings["focus"].set(self._safe_get_prop(cv2.CAP_PROP_FOCUS, 0))
        self.target_settings["brightness"].set(self._safe_get_prop(cv2.CAP_PROP_BRIGHTNESS, 128))
        self.target_settings["exposure"].set(-self._safe_get_prop(cv2.CAP_PROP_EXPOSURE, -7))

    def _safe_get_prop(self, prop_id, default_value=0):
        """Safely get a camera property, returning a default if it fails or is None."""
        if self.cap and self.cap.isOpened():
            value = self.cap.get(prop_id)
            if value is not None:
                return int(value)
        return default_value

    def _create_slider_control(self, parent, label_text, key, from_val, to_val):
        """Creates a single horizontal slider and its labels, packed vertically."""
        control_frame = tk.Frame(parent, pady=2)
        control_frame.pack(side=tk.TOP, fill=tk.X, expand=True, padx=5)

        tk.Label(control_frame, text=label_text, font=self.label_font).pack()

        slider = tk.Scale( # Store reference
            control_frame,
            from_=from_val,
            to=to_val,
            orient=tk.HORIZONTAL,
            variable=self.target_settings[key],
            showvalue=False,
            command=self._on_slider_move,
            state=tk.DISABLED # Disable initially
        )
        slider.pack(fill=tk.X, expand=True)

        tk.Label(control_frame, textvariable=self.target_settings[key], font=self.value_font).pack()
        return slider # Return the slider widget

    def _on_slider_move(self, value):
        """Debounced callback for when any slider is moved."""
        if self._debounce_job:
            self.root.after_cancel(self._debounce_job)
        self._debounce_job = self.root.after(250, self._apply_all_settings)

    def _apply_all_settings(self):
        if not self.cap or not self.cap.isOpened(): return
        
        logger.info("--- Sending all target settings to camera ---")
        focus_val = self.target_settings["focus"].get()
        brightness_val = self.target_settings["brightness"].get()
        exposure_val_ui = self.target_settings["exposure"].get() # UI value (positive)
        exposure_val_cv = -exposure_val_ui # OpenCV value (negative)

        # IMPORTANT: Ensure auto-focus and auto-exposure are explicitly off before setting manual values.
        # This is a common requirement for many webcams.
        logger.info(f"Attempting to set Autofocus to 0 (Off)...")
        if self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0):
            logger.info(f"  Actual Autofocus after set: {self.cap.get(cv2.CAP_PROP_AUTOFOCUS)}")
        else:
            logger.warning("  Failed to set Autofocus to 0.")

        logger.info(f"Attempting to set Auto Exposure to 0 (Manual)...")
        if self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0):
            logger.info(f"  Actual Auto Exposure after set: {self.cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)}")
        else:
            logger.warning("  Failed to set Auto Exposure to 0.")


        logger.info(f"Attempting to set Focus to: {focus_val}")
        if self.cap.set(cv2.CAP_PROP_FOCUS, focus_val):
            logger.info(f"  Actual Focus after set: {self.cap.get(cv2.CAP_PROP_FOCUS)}")
        else:
            logger.warning(f"  Failed to set Focus to {focus_val}.")

        logger.info(f"Attempting to set Brightness to: {brightness_val}")
        if self.cap.set(cv2.CAP_PROP_BRIGHTNESS, brightness_val):
            logger.info(f"  Actual Brightness after set: {self.cap.get(cv2.CAP_PROP_BRIGHTNESS)}")
        else:
            logger.warning(f"  Failed to set Brightness to {brightness_val}.")
        
        logger.info(f"Attempting to set Exposure (UI: {exposure_val_ui}) to CV value: {exposure_val_cv}")
        if self.cap.set(cv2.CAP_PROP_EXPOSURE, exposure_val_cv):
            logger.info(f"  Actual Exposure after set: {self.cap.get(cv2.CAP_PROP_EXPOSURE)}")
        else:
            logger.warning(f"  Failed to set Exposure to {exposure_val_cv}.")

        logger.info("-------------------------------------------")

    def _draw_led_status_overlays(self, frame: np.ndarray, detected_states: Dict[str, Any]) -> np.ndarray:
        """Draws ROIs and status indicators on the frame."""
        if not self.checker:
            return frame
            
        overlay_frame = frame.copy()
        
        # Determine which set of ROIs to use for drawing
        rois_to_draw = self.new_rois if self.is_tuning else {
            key: config.get('roi') for key, config in self.checker.led_configs.items()
        }

        for led_key, config in self.checker.led_configs.items():
            roi_coords = rois_to_draw.get(led_key)
            if not roi_coords: continue

            x, y, w, h = roi_coords
            roi_color = config.get("display_color_bgr", (128, 128, 128))
            cv2.rectangle(overlay_frame, (x, y), (x + w, y + h), roi_color, 2)
            
            # --- FIX: Draw the text on the 'overlay_frame', not the original 'frame' ---
            # cv2.putText(overlay_frame, config["name"], (x, y - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, roi_color, 2)

            # --- Indicator circle drawing logic ---
            indicator_x = x + (w // 2)
            indicator_y = y - OVERLAY_LED_INDICATOR_RADIUS - 5 # Position it just above the ROI name

            is_on = detected_states.get(led_key, 0) == 1
            indicator_color = OVERLAY_TEXT_COLOR_MAIN if is_on else OVERLAY_LED_INDICATOR_OFF_COLOR
            
            cv2.circle(overlay_frame, (indicator_x, indicator_y), OVERLAY_LED_INDICATOR_RADIUS, indicator_color, -1)
            cv2.circle(overlay_frame, (indicator_x, indicator_y), OVERLAY_LED_INDICATOR_RADIUS, OVERLAY_TEXT_COLOR_MAIN, 1)
            
        return overlay_frame

    def _update_frame(self):
        """Main video loop to update the Tkinter label."""
        if self.checker:
            frame, detected_states = self.checker._get_current_led_state_from_camera()
            
            if frame is not None:
                annotated_frame = self._draw_led_status_overlays(frame, detected_states)
                
                success, buffer = cv2.imencode(".ppm", annotated_frame)
                if success:
                    self.imgtk = tk.PhotoImage(data=buffer.tobytes())
                    self.video_label.configure(image=self.imgtk)

        self.root.after(30, self._update_frame)

    def _save_settings_action(self):
        """
        Action for the 'Save Settings' button. Triggers a save but does not
        close the application. Provides feedback in the log.
        """
        logger.info("User clicked 'Save Settings' button.")
        self._save_settings()

    def _save_settings(self):
        """Saves the current slider values and ROI coordinates to the JSON file."""
        # 1. Get current slider values
        # IMPORTANT: These values are read directly from the Tkinter variables,
        # which should reflect what the user has set.
        current_focus = self.target_settings["focus"].get()
        current_brightness = self.target_settings["brightness"].get()
        current_exposure = self.target_settings["exposure"].get() # This is the positive UI value

        camera_properties = {
            "focus": current_focus,
            "brightness": current_brightness,
            "exposure": current_exposure # Save the positive UI value
        }
        logger.info(f"Saving camera properties: {camera_properties}") # ADDED LOG

        # 2. Get current ROI coordinates from the checker
        roi_settings = {}
        if self.new_rois:
            logger.info(f"Applying {len(self.new_rois)} new ROIs from tuning session.")
            for led_key, roi_tuple in self.new_rois.items():
                roi_settings[led_key] = list(roi_tuple)
        
        if self.checker and self.checker.led_configs:
            for led_key, config_item in self.checker.led_configs.items():
                # If this key wasn't part of the tuning session, use its current value.
                if led_key not in roi_settings and "roi" in config_item:
                    roi_settings[led_key] = list(config_item["roi"])
        else:
            logger.warning("Checker or LED configs not available. Cannot save ROI settings.")   

        # 3. Combine all settings into a single dictionary for JSON output
        all_settings_to_save = {
            "camera_properties": camera_properties,
            "roi_settings": roi_settings
        }

        try:
            os.makedirs(os.path.dirname(CAMERA_SETTINGS_SAVE_PATH), exist_ok=True)
            
            with open(CAMERA_SETTINGS_SAVE_PATH, 'w') as f:
                json.dump(all_settings_to_save, f, indent=4)
            logger.info(f"Settings saved successfully to: {CAMERA_SETTINGS_SAVE_PATH}")
            logger.info("Restart the application for changes to take effect on camera initialization.")
        except Exception as e:
            logger.error(f"Failed to save settings to '{CAMERA_SETTINGS_SAVE_PATH}': {e}", exc_info=True)

    def _on_closing(self):
        """Cleanup method for closing the application."""
        logger.info("Closing application...")
        self._save_settings() # Save the UI state first

        if self.cap and self.cap.isOpened():
            print("\n--- Final Target Values ---")
            # CORRECTED: Read from the UI variables, which are the source for the saved file,
            # ensuring the final printout matches what was saved.
            final_focus = self.target_settings["focus"].get()
            final_brightness = self.target_settings["brightness"].get()
            final_exposure = -self.target_settings["exposure"].get() # Get UI value and convert to CV value

            print(f"Focus:      {final_focus}")
            print(f"Brightness: {final_brightness}")
            print(f"Exposure:   {final_exposure}")
            print("-----------------------------")
            
        # Ensure all keypad Phidgets are turned off
        if self.controller:
            for key_name, state_var in self.keypad_states.items():
                if state_var.get(): # If the key is currently ON
                    logger.info(f"Turning off keypad channel '{key_name}' during shutdown.")
                    try:
                        self.controller.off(key_name)
                    except Exception as e:
                        logger.error(f"Error turning off keypad channel {key_name} during cleanup: {e}", exc_info=True)

            self.controller.close()
            
        self.root.destroy()

if __name__ == "__main__":
    print("""--- Camera Tuning Script (v26 - with Live Detection) ---
The UI window will appear immediately while hardware initializes.
Use the sliders to set target values. Settings are applied automatically.
-----------------------------------------------------------------""")
    root = tk.Tk()
    app = App(root)
    root.mainloop()