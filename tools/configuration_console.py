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
    from controllers.finite_state_machine import DeviceUnderTest
    from controllers.logitech_webcam import (
        LogitechLedChecker,
        OVERLAY_TEXT_COLOR_MAIN,
        OVERLAY_LED_INDICATOR_OFF_COLOR,
        OVERLAY_LED_INDICATOR_RADIUS,
        _CAMERA_SETTINGS_FILE,
    )
    from utils.config.keypad_layouts import KEYPAD_LAYOUTS
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
VALID_FOCUS_VALUES = list(range(0, 255, 5))

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

        self.keypad_button_widgets: Dict[str, tk.Button] = {} 
        self.keypad_frame: Optional[tk.Frame] = None
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
        self.root.bind("<ButtonPress-1>", self._on_drag_start)
        self.root.bind("<B1-Motion>", self._on_drag_move)
        self.root.bind("<ButtonRelease-1>", self._on_drag_end)
        self.root.bind('<Escape>', self._abort_tuning_on_escape)
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
        GROUP_PADDING = 5

        # --- Group 1: Keypad Frame (Structure Only) ---
        self.keypad_frame = tk.Frame(self.left_panel, relief=tk.GROOVE, borderwidth=2, padx=5, pady=5)
        self.keypad_frame.pack(side=tk.TOP, pady=GROUP_PADDING, padx=0, fill=tk.X)
        tk.Label(self.keypad_frame, text="Phidget I/Os", font=self.label_font).grid(row=0, column=0, columnspan=3, pady=(0, 5))

        # --- Group 2: Sliders Frame ---
        sliders_frame = tk.Frame(self.left_panel, relief=tk.GROOVE, borderwidth=2, padx=5, pady=0)
        sliders_frame.pack(side=tk.TOP, pady=GROUP_PADDING, fill=tk.X)
        tk.Label(sliders_frame, text="Camera Settings", font=self.label_font).pack()
        self.sliders.append(self._create_slider_control(sliders_frame, "Focus", "focus", 0, 255))
        self.sliders.append(self._create_slider_control(sliders_frame, "Brightness", "brightness", 0, 255))
        self.sliders.append(self._create_slider_control(sliders_frame, "Exposure", "exposure", 2, 13))

        # --- Group 3: A single frame for all action buttons at the bottom ---
        action_button_frame = tk.Frame(self.left_panel)
        # This frame is packed at the top level, which will center it by default
        action_button_frame.pack(side=tk.TOP, pady=(GROUP_PADDING, 2))

        # --- [BUG FIX] ---
        # A fixed width is set ONLY for the tune_led_button.
        # No 'sticky' or 'columnconfigure' options are used, so buttons will not stretch.
        TUNE_BUTTON_WIDTH = 17

        # 'Tune LED Coordinates' button
        self.tune_led_button = tk.Button(
            action_button_frame, 
            text="Tune LED Coordinates", 
            command=self._start_tuning_action, 
            state=tk.DISABLED, 
            width=TUNE_BUTTON_WIDTH  # Apply fixed width here
        )
        # Grid is used here just to place the two buttons neatly side-by-side
        self.tune_led_button.grid(row=0, column=1, padx=(2, 0))

        # 'Save Settings' button now has no fixed width and will size to its text
        save_button = tk.Button(
            action_button_frame, 
            text="Save Settings", 
            command=self._save_settings_action
        )
        save_button.grid(row=0, column=0, padx=(0, 2))

    def _get_relative_coords(self, event) -> tuple[Optional[int], Optional[int]]:
        """
        Translates a root window event to coordinates relative to the video label.
        Returns (None, None) if the click is outside the video label.
        """
        # We must call update_idletasks to ensure all geometry calculations are current.
        self.root.update_idletasks()
        
        # Get absolute screen coordinates of the video label's top-left corner and its size.
        label_x_abs = self.video_label.winfo_rootx()
        label_y_abs = self.video_label.winfo_rooty()
        label_width = self.video_label.winfo_width()
        label_height = self.video_label.winfo_height()

        # Get the absolute screen coordinates of the mouse click from the event object.
        click_x_abs = event.x_root
        click_y_abs = event.y_root

        # Check if the click is within the video label's bounds.
        if not (label_x_abs <= click_x_abs < label_x_abs + label_width and
                label_y_abs <= click_y_abs < label_y_abs + label_height):
            return None, None # Click was outside the video feed.

        # If inside, calculate and return the coordinates relative to the video label.
        relative_x = click_x_abs - label_x_abs
        relative_y = click_y_abs - label_y_abs
        return relative_x, relative_y

    def _on_drag_start(self, event):
        """Initiates the ROI placement when the mouse is first clicked."""
        relative_x, relative_y = self._get_relative_coords(event)
        
        # --- FIX: Check for None and tuning status BEFORE calling the update method ---
        if self.is_tuning and relative_x is not None and relative_y is not None:
            logger.debug(f"Drag start detected at relative coords: x={relative_x}, y={relative_y}")
            self._update_roi_position(relative_x, relative_y)

    def _on_drag_move(self, event):
        """Updates the ROI box position as the mouse is dragged."""
        relative_x, relative_y = self._get_relative_coords(event)
        
        # --- FIX: Check for None and tuning status BEFORE calling the update method ---
        if self.is_tuning and relative_x is not None and relative_y is not None:
            self._update_roi_position(relative_x, relative_y)

    def _on_drag_end(self, event):
        """Finalizes the ROI position and advances to the next tuning step."""
        # ... (code to get relative_x, relative_y is unchanged) ...
        relative_x, relative_y = self._get_relative_coords(event)
        if not (self.is_tuning and relative_x is not None and relative_y is not None):
            return

        # ... (safeguard and led_key logic is unchanged) ...
        if self.tuning_step >= len(self.tuning_leds):
            return
        led_key = self.tuning_leds[self.tuning_step]
        final_coords = self.new_rois.get(led_key, "N/A")
        logger.info(f"Tuning for '{led_key}' finalized at ROI: {final_coords}")

        self.tuning_step += 1
        
        if self.tuning_step < len(self.tuning_leds):
            # Update UI for the next LED
            next_led_key = self.tuning_leds[self.tuning_step]
            if self.tune_led_button:
                self.tune_led_button.config(text=f"Click/drag to place {next_led_key.upper()} LED", fg=next_led_key)
        else:
            # --- FIX: Last LED is done, so apply to live config, save, and finish ---
            logger.info("Final LED tuned. Applying new ROIs and saving...")

            # --- [BUG FIX START] ---
            # This is the crucial new block. It updates the live, in-memory
            # configuration that the video renderer uses after tuning is complete.
            if self.checker:
                for led_key, new_roi_coords in self.new_rois.items():
                    if led_key in self.checker.led_configs:
                        self.checker.led_configs[led_key]['roi'] = new_roi_coords
                        logger.debug(f"Updated live ROI for '{led_key}': {new_roi_coords}")
            # --- [BUG FIX END] ---
            
            self._save_settings() # Save the new settings to the JSON file
            if self.tune_led_button:
                self.tune_led_button.config(text="Tuning Complete!", fg="black")
            
            # Revert UI state after a short delay
            self.root.after(2000, self._finish_tuning)

    def _update_roi_position(self, x: int, y: int):
        """Calculates and updates the current ROI based on mouse coordinates."""
        if self.tuning_step >= len(self.tuning_leds):
            return

        led_key = self.tuning_leds[self.tuning_step]

        # --- [BUG FIX] ---
        # Get the current width and height from the ROI we are tuning.
        # This preserves the size that was dynamically set when tuning started.
        # Default to (40, 40) as a safe fallback if the key somehow doesn't exist.
        _prev_x, _prev_y, roi_width, roi_height = self.new_rois.get(led_key, (0, 0, 40, 40))

        # The offset calculation remains the same
        new_x = x - (roi_width // 2) - 2
        new_y = y - (roi_height // 2) - 40
        
        # Update the dictionary with the new position but the PRESERVED size.
        self.new_rois[led_key] = (new_x, new_y, roi_width, roi_height)

    def _start_tuning_action(self):
        """Begins or aborts the interactive ROI tuning process."""
        if self.is_tuning:
            self.is_tuning = False
            if self.tune_led_button:
                self.tune_led_button.config(text="Tune LED Coordinates")
            logger.info("ROI tuning aborted by user.")
            self._finish_tuning()
            return

        if not self.checker:
            logger.error("Cannot start tuning, camera checker not ready.")
            return

        self.is_tuning = True
        self.tuning_step = 0
        
        # Determine the current ROI size from the live checker to use for tuning
        # This makes the tool robust to whichever size was loaded.
        current_roi_w, current_roi_h = 40, 40 # Default fallback
        if 'red' in self.checker.led_configs and 'roi' in self.checker.led_configs['red']:
             _, _, current_roi_w, current_roi_h = self.checker.led_configs['red']['roi']
             logger.info(f"Initializing tuning session with current ROI size: {current_roi_w}x{current_roi_h}")

        # Initialize new_rois with current positions but dynamic size for drawing
        self.new_rois = {
            key: (config['roi'][0], config['roi'][1], current_roi_w, current_roi_h)
            for key, config in self.checker.led_configs.items() if 'roi' in config
        }
        
        # Disable other controls to avoid conflicts
        if self.power_button: self.power_button.config(state=tk.DISABLED)
        if self.usb3_button: self.usb3_button.config(state=tk.DISABLED)
        if self.scan_button: self.scan_button.config(state=tk.DISABLED)
        for slider in self.sliders:
            slider.config(state=tk.DISABLED)
        
        first_led = self.tuning_leds[0]
        if self.tune_led_button:
            self.tune_led_button.config(text=f"Click on the {first_led.upper()} LED", fg=first_led)
        
        logger.info(f"Starting ROI tuning. Please click and drag to place the {first_led.upper()} LED.")

    def _finish_tuning(self):
        """Resets the UI controls after tuning is complete or aborted."""
        self.is_tuning = False
        
        # Reset the button to its original state
        if self.tune_led_button:
            self.tune_led_button.config(text="Tune LED Coordinates", fg="black")

        # Re-enable all other controls
        if self.power_button: self.power_button.config(state=tk.NORMAL)
        if self.usb3_button: self.usb3_button.config(state=tk.NORMAL)
        if self.scan_button: self.scan_button.config(state=tk.NORMAL)
        for slider in self.sliders:
            slider.config(state=tk.NORMAL)

    def _abort_tuning_on_escape(self, event):
        """Event handler to abort the ROI tuning process when 'Esc' is pressed."""
        if self.is_tuning:
            logger.info("ROI tuning aborted by user via Escape key.")
            # Re-use the existing finish method to reset the UI and state
            self._finish_tuning()

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
            # --- FIX: Check if the button exists before configuring it ---
            if self.scan_button:
                self.scan_button.config(text="Scan Failed: Controller Not Ready")
                # Schedule the button text to revert
                self.root.after(3000, lambda: self.scan_button.config(text="Scan Barcode") if self.scan_button else None)
            return
        
        logger.info("Scan barcode button pressed. Starting scan thread...")
        threading.Thread(target=self._perform_barcode_scan, daemon=True).start()

    def _perform_barcode_scan(self):
        """Performs the actual barcode scan and updates the button text."""
        if not self.controller or not self.scan_button:
            logger.error("Controller or scan button not ready for barcode scan.")
            return

        # --- FIX: Check if the button exists before configuring it ---
        # Update button text to show scanning is in progress
        if self.scan_button:
            self.root.after(0, lambda: self.scan_button.config(text="Scanning...") if self.scan_button else None)
        
        scanned_data = self.controller.scan_barcode()
        
        # Determine the result text
        new_text = scanned_data if scanned_data else "TIMEOUT / No Data"
        
        # Schedule UI updates from the main thread
        if self.scan_button:
            self.root.after(0, lambda: self.scan_button.config(text=new_text) if self.scan_button else None)
        
        # Schedule the button text to revert back to its original state after 3 seconds
        if self.scan_button:
            self.root.after(3000, lambda: self.scan_button.config(text="Scan Barcode") if self.scan_button else None)

    def initialize_hardware(self):
        """Initializes hardware in a background thread, then schedules UI finalization."""
        try:
            logger.info("Initializing UnifiedController...")            
            self.controller = UnifiedController(
                camera_id=CAMERA_ID,
                logger_instance=logger.getChild("UnifiedCtrl"),
                replay_output_dir=None,
                skip_initial_scan=True
            )

            if not self.controller.is_fully_initialized:
                error_msg = "Hardware Initialization Failed. Check logs for details (e.g., Phidget/Camera init)."
                self.video_label.config(text=error_msg)
                logger.critical(error_msg)
                return

            # The controller now creates its own DUT. Use that instance instead of creating a new one.
            self.dut = self.controller.dut
            self.checker = self.controller._camera_checker
            self.cap = self.checker.cap if self.checker else None
                        
            self.root.after(0, self.finish_ui_setup)
            
        except Exception as e:
            error_msg = f"Hardware Init Error:\n{e}"
            self.video_label.config(text=error_msg)
            logger.critical(error_msg, exc_info=True)

    def finish_ui_setup(self):
        """Populates the remaining UI elements now that hardware is initialized."""
        self.populate_sliders_from_camera()
        
        # Re-create the keypad with the correct layout and enable buttons
        self._populate_keypad()

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

    def _populate_keypad(self):
        """Determines the correct layout and creates all keypad-related controls ONCE."""
        if not self.keypad_frame:
            logger.error("Cannot populate keypad, frame container not found.")
            return

        # Determine which layout to use based on the initialized DUT.
        if self.dut and self.dut.secure_key:
            logger.info("Secure Key device detected, using 2-column keypad layout.")
            keypad_layout = KEYPAD_LAYOUTS['Secure Key']
            num_columns = 2
        else:
            logger.info("Portable device detected, using 3-column keypad layout.")
            keypad_layout = KEYPAD_LAYOUTS['Portable']
            num_columns = 3
        
        # Configure keypad columns to have equal weight.
        for i in range(num_columns):
            self.keypad_frame.columnconfigure(i, weight=1)

        button_font = tkFont.Font(family="Helvetica", size=10)
        self.keypad_button_widgets.clear() # Clear any old references, just in case

        # Create and place the keypad buttons.
        for row_idx, row_of_keys in enumerate(keypad_layout):
            for col_idx, key_name in enumerate(row_of_keys):
                button = tk.Button(
                    self.keypad_frame,
                    text=key_name,
                    font=button_font,
                    height=1, 
                    state=tk.NORMAL,
                    relief=tk.RAISED
                )
                button.bind('<ButtonPress-1>', lambda event, k=key_name: self._on_keypad_press(event, k))
                button.bind('<ButtonRelease-1>', lambda event, k=key_name: self._on_keypad_release(event, k))
                button.grid(row=row_idx + 1, column=col_idx, padx=5, pady=2, sticky="ew")
                self.keypad_button_widgets[key_name] = button

        # Calculate the next available row after the keypad
        next_row = len(keypad_layout) + 1

        # Add a separator
        separator = tk.Frame(self.keypad_frame, height=2, bd=1, relief=tk.SUNKEN)
        separator.grid(row=next_row, column=0, columnspan=num_columns, sticky="ew", padx=5, pady=10)
        next_row += 1

        # Create a dedicated frame for the Power and USB3 buttons
        power_usb_frame = tk.Frame(self.keypad_frame)
        power_usb_frame.grid(row=next_row, column=0, columnspan=num_columns, sticky="ew")

        # Configure the frame's columns to have equal weight, so they share space.
        power_usb_frame.columnconfigure(0, weight=1)
        power_usb_frame.columnconfigure(1, weight=1)

        # Create and grid the Power and USB3 buttons within this new frame
        self.power_button = tk.Checkbutton(power_usb_frame, text="Power", variable=self.power_state, indicatoron=False, state=tk.NORMAL, relief=tk.RAISED)
        self.power_button.config(command=lambda btn=self.power_button: self._handle_phidget_toggle("connect", self.power_state, btn))
        self.power_button.grid(row=0, column=0, sticky="ew", padx=(5, 2))
        
        self.usb3_button = tk.Checkbutton(power_usb_frame, text="USB3", variable=self.usb3_state, indicatoron=False, state=tk.NORMAL, relief=tk.RAISED)
        self.usb3_button.config(command=lambda btn=self.usb3_button: self._handle_phidget_toggle("usb3", self.usb3_state, btn))
        self.usb3_button.grid(row=0, column=1, sticky="ew", padx=(2, 5))
        next_row += 1
        
        # Create Scan Barcode button
        self.scan_button = tk.Button(self.keypad_frame, text="Scan Barcode", command=self._scan_barcode_action, state=tk.NORMAL)
        self.scan_button.grid(row=next_row, column=0, columnspan=num_columns, sticky="ew", padx=5, pady=(8, 5))

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
        """Creates a single horizontal slider with its value label to the right."""
        control_frame = tk.Frame(parent, pady=2)
        control_frame.pack(side=tk.TOP, fill=tk.X, expand=True, padx=5)

        # Configure the grid columns within the control_frame.
        # Column 0 (the slider) will expand to take up all available space.
        control_frame.columnconfigure(0, weight=1)
        # Column 1 (the value) will have a fixed width.

        # 1. Place the main label ("Focus", etc.) in row 0, spanning both columns.
        tk.Label(control_frame, text=label_text, font=self.label_font).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )

        # 2. Place the Scale widget (the slider) in row 1, column 0.
        slider = tk.Scale(
            control_frame,
            from_=from_val,
            to=to_val,
            orient=tk.HORIZONTAL,
            variable=self.target_settings[key],
            showvalue=False,  # We are showing our own label
            command=lambda value, k=key: self._on_slider_move(k, value),
            state=tk.DISABLED
        )
        # Use sticky="ew" to make the slider expand horizontally to fill its column.
        slider.grid(row=1, column=0, sticky="ew")

        # 3. Place the value label in row 1, column 1, to the right of the slider.
        # Give it a fixed width to prevent the UI from resizing as the number changes.
        value_label = tk.Label(
            control_frame,
            textvariable=self.target_settings[key],
            font=self.value_font,
            width=4  # A fixed width of 4 characters is good for values up to 255.
        )
        value_label.grid(row=1, column=1, padx=(5, 0))

        return slider

    def _apply_single_setting(self, key: str, value: int):
        """Applies a single camera setting to the hardware."""
        if not self.cap or not self.cap.isOpened(): return

        logger.info(f"--- Applying setting for {key}: {value} ---")
        
        if key == "focus":
            logger.info(f"Attempting to set Autofocus to 0 (Off)...")
            self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
            logger.info(f"Attempting to set Focus to: {value}")
            if self.cap.set(cv2.CAP_PROP_FOCUS, value):
                logger.info(f"  Actual Focus after set: {self.cap.get(cv2.CAP_PROP_FOCUS)}")
            else:
                logger.warning(f"  Failed to set Focus to {value}.")
        
        elif key == "brightness":
            logger.info(f"Attempting to set Brightness to: {value}")
            if self.cap.set(cv2.CAP_PROP_BRIGHTNESS, value):
                logger.info(f"  Actual Brightness after set: {self.cap.get(cv2.CAP_PROP_BRIGHTNESS)}")
            else:
                logger.warning(f"  Failed to set Brightness to {value}.")

        elif key == "exposure":
            # UI value is positive, OpenCV value is negative
            exposure_val_cv = -value
            logger.info(f"Attempting to set Auto Exposure to 0 (Manual)...")
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)
            logger.info(f"Attempting to set Exposure (UI: {value}) to CV value: {exposure_val_cv}")
            if self.cap.set(cv2.CAP_PROP_EXPOSURE, exposure_val_cv):
                logger.info(f"  Actual Exposure after set: {self.cap.get(cv2.CAP_PROP_EXPOSURE)}")
            else:
                logger.warning(f"  Failed to set Exposure to {exposure_val_cv}.")
        
        logger.info("-------------------------------------------")

    def _on_slider_move(self, key: str, value: str):
        """Debounced callback for when a specific slider is moved."""
        if self._debounce_job:
            self.root.after_cancel(self._debounce_job)
        
        int_value = int(value)

        if key == "focus":
            # Find the closest valid focus value from our hardcoded list
            closest_value = min(VALID_FOCUS_VALUES, key=lambda x: abs(x - int_value))
            # Snap the UI slider's variable to this valid value. This will update the label.
            if self.target_settings["focus"].get() != closest_value:
                self.target_settings["focus"].set(closest_value)
            
            # Use the snapped value for the debounced hardware call
            int_value = closest_value
            
        self._debounce_job = self.root.after(250, lambda: self._apply_single_setting(key, int_value))

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
        """Saves the current slider values and ROI positions to the JSON file."""
        # Step 1: READ - Load the entire existing config file first.
        # If the file doesn't exist or is invalid, start with an empty dictionary.
        try:
            with open(CAMERA_SETTINGS_SAVE_PATH, 'r') as f:
                all_settings_to_save = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            all_settings_to_save = {}

        # Step 2: Update only the parts this tool is responsible for.
        current_focus = self.target_settings["focus"].get()
        current_brightness = self.target_settings["brightness"].get()
        current_exposure = self.target_settings["exposure"].get()

        camera_properties = {
            "focus": current_focus,
            "brightness": current_brightness,
            "exposure": current_exposure
        }
        all_settings_to_save['camera_properties'] = camera_properties
        logger.info(f"Updating camera properties to: {camera_properties}")
        
        rois_to_save_from = {}
        if self.is_tuning:
            rois_to_save_from = self.new_rois
        elif self.checker:
            rois_to_save_from = {
                key: config.get('roi') for key, config in self.checker.led_configs.items()
            }
        
        roi_settings = {}
        if rois_to_save_from:
            for led_key, roi_tuple in rois_to_save_from.items():
                if roi_tuple:
                    roi_settings[led_key] = {'x': roi_tuple[0], 'y': roi_tuple[1]}
        
        all_settings_to_save['roi_settings'] = roi_settings
        logger.info(f"Updating ROI positions to: {roi_settings}")

        # Step 3: WRITE - Save the entire modified data structure back to the file.
        try:
            os.makedirs(os.path.dirname(CAMERA_SETTINGS_SAVE_PATH), exist_ok=True)
            with open(CAMERA_SETTINGS_SAVE_PATH, 'w') as f:
                json.dump(all_settings_to_save, f, indent=4)
            logger.info(f"Settings saved successfully to: {CAMERA_SETTINGS_SAVE_PATH}")
            if not self.is_tuning:
                logger.info("Restart the application for changes to take full effect.")
        except Exception as e:
            logger.error(f"Failed to save settings to '{CAMERA_SETTINGS_SAVE_PATH}': {e}", exc_info=True)

    def _on_closing(self):
        """Cleanup method for closing the application."""
        logger.info("Closing application...")
        self._save_settings() # Save the UI state first

        # if self.cap and self.cap.isOpened():
        #     print("\n--- Final Target Values ---")
        #     # CORRECTED: Read from the UI variables, which are the source for the saved file,
        #     # ensuring the final printout matches what was saved.
        #     final_focus = self.target_settings["focus"].get()
        #     final_brightness = self.target_settings["brightness"].get()
        #     final_exposure = -self.target_settings["exposure"].get() # Get UI value and convert to CV value

        #     print(f"Focus:      {final_focus}")
        #     print(f"Brightness: {final_brightness}")
        #     print(f"Exposure:   {final_exposure}")
        #     print("-----------------------------")
            
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