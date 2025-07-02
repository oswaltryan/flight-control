# Directory: controllers
# Filename: logitech_webcam.py
#!/usr/bin/env python3

import time
import logging # Standard library logging
import copy
import cv2
import json
import sys # Import sys to check platform
import numpy as np # Import numpy for array operations
import collections # For deque, for instant replay
import datetime # For timestamping replay files
import os # For path manipulation for replay files
from typing import Dict, Optional, List, Tuple, Any # For type hinting
import threading


# Get the logger for this module. Its name will be 'controllers.logitech_webcam'.
# Configuration (handlers, level, format) comes from the global setup.
logger = logging.getLogger(__name__)

DEFAULT_FPS = 15
CAMERA_BUFFER_SIZE_FRAMES = 5
MIN_LOGGABLE_STATE_DURATION = 0.01 # Seconds. States held for less than this won't be logged as "held".
DEFAULT_DURATION_TOLERANCE_SEC = 0.1 # NEW: Default tolerance for duration checks

# --- Instant Replay Configuration ---
GLOBAL_ENABLE_INSTANT_REPLAY_FEATURE = True
DEFAULT_REPLAY_PRE_FAIL_DURATION_SEC = 7.0
DEFAULT_REPLAY_POST_FAIL_DURATION_SEC = 5.0
KEY_PRESS_VISUAL_DELAY_S = 0.1
KEY_PRESS_VISUAL_SUSTAIN_S = 0.15
DEFAULT_REPLAY_FPS_FOR_OUTPUT = DEFAULT_FPS # Use camera's default FPS for replay output
_CAMERA_CONTROLLER_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT_FROM_CAMERA = os.path.dirname(_CAMERA_CONTROLLER_FILE_DIR)

# --- Overlay Drawing Constants ---
OVERLAY_FONT = cv2.FONT_HERSHEY_SIMPLEX
OVERLAY_FONT_SCALE = 0.5
OVERLAY_FONT_THICKNESS = 1
OVERLAY_TEXT_COLOR_MAIN = (255, 255, 255)  # White
OVERLAY_LINE_HEIGHT = 20 # Used as a spacer for positioning indicators
OVERLAY_PADDING = 5
OVERLAY_BG_COLOR = (20, 20, 20) # Dark Grey

# --- Constants for drawing LED status indicators on the replay video ---
OVERLAY_LED_INDICATOR_RADIUS = 7
# Fallback 'ON' color for configs missing a 'display_color_bgr' key.
OVERLAY_LED_INDICATOR_ON_COLOR_FALLBACK = (0, 255, 0) # Bright Green
OVERLAY_LED_INDICATOR_OFF_COLOR = (80, 80, 80) # Dark Grey for OFF

# --- Path to external camera settings file ---
_CONFIG_DIR = os.path.join(_PROJECT_ROOT_FROM_CAMERA, 'utils', 'config')
_CAMERA_SETTINGS_FILE = os.path.join(_CONFIG_DIR, 'camera_hardware_settings.json')

# --- PRIMARY (USER-TUNED) LED CONFIGURATIONS ---
PRIMARY_LED_CONFIGURATIONS = {
    "red":   {
        "name": "Red LED",
        "roi": (187, 165, 40, 40),
        "hsv_lower": (165,150,150),
        "hsv_upper": (15,255,255),
        "min_match_percentage": 0.15,
        "display_color_bgr": (0,0,255)
    },
    "green": {
        "name": "Green LED",
        "roi": (302, 165, 40, 40),
        "hsv_lower": (40, 10, 100),
        "hsv_upper": (85, 255, 255),
        "min_match_percentage": 0.25,
        "display_color_bgr": (0,255,0)
    },
    "blue":  {
        "name": "Blue LED",
        "roi": (417, 165, 40, 40),
        "hsv_lower": (0,    0, 100),
        "hsv_upper": (130, 255, 255),
        "min_match_percentage": 0.75,
        "display_color_bgr": (255,0,0)
    }
}
# --- End of PRIMARY LED Configurations ---


# --- FALLBACK LED CONFIGURATIONS (Generic Placeholders) ---
_FALLBACK_LED_DEFINITIONS = {
    "fallback_red": {
        "name": "Fallback Generic Red LED",
        "roi": (50, 50, 20, 20),
        "hsv_lower": (0, 100, 100), "hsv_upper": (10, 255, 255),
        "min_match_percentage": 0.1,
        "display_color_bgr": (128, 128, 128)
    },
}
# --- End of Fallback LED Configurations ---

# Define a default display order for common LED keys for logging.
DEFAULT_LED_DISPLAY_ORDER = ["red", "green", "blue"]

# --- Camera Hardware Settings (Default Fallback) ---
DEFAULT_CAMERA_HARDWARE_SETTINGS = {
    cv2.CAP_PROP_AUTO_EXPOSURE: 0,
    cv2.CAP_PROP_EXPOSURE: -6, # UI exposure 7 maps to -6, UI exposure 2 maps to -2 etc.
    cv2.CAP_PROP_AUTOFOCUS: 0,
    cv2.CAP_PROP_FOCUS: 30, 
    cv2.CAP_PROP_AUTO_WB: 0,
    cv2.CAP_PROP_WB_TEMPERATURE: 4500,
}
# --- End of Camera Hardware Settings ---

def get_capture_backend():
    if sys.platform.startswith('win'):
        return cv2.CAP_DSHOW
    elif sys.platform.startswith('darwin'): # macOS
        return cv2.CAP_AVFOUNDATION
    return None # Let OpenCV choose default

def _load_all_camera_settings() -> Tuple[Dict[int, Any], Dict[str, Tuple[int, int, int, int]]]:
    """
    Attempts to load camera hardware settings and ROI definitions from a JSON file.
    Falls back to defaults if file not found or invalid.

    Returns:
        A tuple: (camera_properties: Dict[cv2.CAP_PROP, Any], roi_settings: Dict[str, Tuple[int, int, int, int]])
    """
    if not os.path.exists(_CAMERA_SETTINGS_FILE):
        logger.info(f"Camera settings file not found at '{_CAMERA_SETTINGS_FILE}'. Using default settings.")
        return DEFAULT_CAMERA_HARDWARE_SETTINGS.copy(), {}

    loaded_camera_props = {} # This is the target dictionary for camera properties
    loaded_roi_settings = {}

    try:
        with open(_CAMERA_SETTINGS_FILE, 'r') as f:
            loaded_data = json.load(f)
        
        logger.debug(f"Loaded raw data from config file: {loaded_data}") # ADDED DEBUG LOG
        
        # Load camera properties (focus, brightness, exposure)
        for key_str, value in loaded_data.get('camera_properties', {}).items():
            try:
                if key_str == 'exposure': # UI exposure (positive) to cv2 exposure (negative)
                    loaded_camera_props[cv2.CAP_PROP_EXPOSURE] = -value
                elif key_str == 'focus': # Assign to loaded_camera_props
                    loaded_camera_props[cv2.CAP_PROP_FOCUS] = value
                elif key_str == 'brightness': # Assign to loaded_camera_props
                    loaded_camera_props[cv2.CAP_PROP_BRIGHTNESS] = value
                logger.debug(f"Parsed setting from file: '{key_str}'={value} -> CAP_PROP_{key_str.upper()}={loaded_camera_props.get(getattr(cv2, f'CAP_PROP_{key_str.upper()}', None))}") # ADDED DEBUG LOG
            except ValueError:
                logger.warning(f"Skipping invalid setting '{key_str}' from config file: value is not an integer.")
                continue

        # Merge with defaults to ensure all required settings are present,
        # giving preference to loaded settings if they exist.
        merged_camera_properties = DEFAULT_CAMERA_HARDWARE_SETTINGS.copy()
        merged_camera_properties.update(loaded_camera_props)
        logger.debug(f"Merged camera properties for application: {merged_camera_properties}") # ADDED DEBUG LOG


        # Load ROI settings
        for led_name, roi_list in loaded_data.get('roi_settings', {}).items():
            if isinstance(roi_list, list) and len(roi_list) == 4 and all(isinstance(n, int) for n in roi_list):
                loaded_roi_settings[led_name] = tuple(roi_list)
            else:
                logger.warning(f"Skipping invalid ROI setting for '{led_name}' from config file: expected list of 4 ints.")

        logger.info(f"Successfully loaded camera and ROI settings from '{_CAMERA_SETTINGS_FILE}'.")
        return merged_camera_properties, loaded_roi_settings # Return the merged properties

    except json.JSONDecodeError as e:
        logger.error(f"Error decoding camera settings JSON from '{_CAMERA_SETTINGS_FILE}': {e}. Using default settings.", exc_info=True)
        return DEFAULT_CAMERA_HARDWARE_SETTINGS.copy(), {}
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading camera settings from '{_CAMERA_SETTINGS_FILE}': {e}. Using default settings.", exc_info=True)
        return DEFAULT_CAMERA_HARDWARE_SETTINGS.copy(), {}
 
class LogitechLedChecker:
    def __init__(self, camera_id: int, logger_instance=None, led_configs=None,
                 display_order: Optional[List[str]] = None, duration_tolerance_sec: float = DEFAULT_DURATION_TOLERANCE_SEC,
                 replay_post_failure_duration_sec: float = DEFAULT_REPLAY_POST_FAIL_DURATION_SEC,
                 replay_output_dir: Optional[str] = None,
                 enable_instant_replay: Optional[bool] = None,
                 keypad_layout: Optional[Dict[str, Any]] = None):
        self.logger = logger_instance if logger_instance else logger
        self.cap = None
        self.is_camera_initialized = False
        self.camera_id = camera_id
        self.preferred_backend = get_capture_backend()
        self._ordered_keys_for_display_cache = None
        self.explicit_display_order = display_order
        self.duration_tolerance_sec = duration_tolerance_sec

        # --- Attributes for Key Press Overlay ---
        self.keypad_layout = keypad_layout
        self.active_keys_for_replay: set = set()
        self.active_keys_lock = threading.Lock()

        # --- Instant Replay Initialization ---
        if enable_instant_replay is not None:
            self.enable_instant_replay = enable_instant_replay
        else:
            self.enable_instant_replay = GLOBAL_ENABLE_INSTANT_REPLAY_FEATURE
        self.replay_post_failure_duration_sec = replay_post_failure_duration_sec
        self.replay_output_dir = replay_output_dir
        self.is_replay_armed = False

        self.replay_fps = float(DEFAULT_REPLAY_FPS_FOR_OUTPUT)
        self.replay_pre_fail_duration_sec = DEFAULT_REPLAY_PRE_FAIL_DURATION_SEC
        replay_buffer_maxlen = int(self.replay_pre_fail_duration_sec * self.replay_fps)
        self.replay_buffer = collections.deque(maxlen=replay_buffer_maxlen)
        
        self.replay_start_time = 0.0
        self.replay_method_name = ""
        self.replay_extra_context: Optional[Dict[str, str]] = None
        self.replay_failure_reason = ""
        self.replay_frame_width = None
        self.replay_frame_height = None

        if self.enable_instant_replay and self.replay_output_dir:
            try:
                os.makedirs(self.replay_output_dir, exist_ok=True)
            except OSError as e:
                self.logger.error(f"Failed to create replay output directory {self.replay_output_dir}: {e}. Replays will not be saved.", exc_info=True)
                self.replay_output_dir = None 
        elif not self.enable_instant_replay:
            self.logger.info("Instant replay is disabled via configuration.")
            self.replay_output_dir = None
        else:
            self.logger.warning("Replay output directory is not set. Replays will not be saved.")
        
        # --- LED Config Loading ---
        # 1. Start with a deep copy of the base primary configurations
        if led_configs is not None: # If custom led_configs are passed, use them as base
            self.led_configs = copy.deepcopy(led_configs)
        elif PRIMARY_LED_CONFIGURATIONS: # Otherwise, use the module's default primary config
            self.led_configs = copy.deepcopy(PRIMARY_LED_CONFIGURATIONS)
        else: # Fallback if even PRIMARY_LED_CONFIGURATIONS is empty (shouldn't happen in production)
            self.led_configs = copy.deepcopy(_FALLBACK_LED_DEFINITIONS)
            self.logger.error("PRIMARY_LED_CONFIGURATIONS empty/invalid. Using _FALLBACK_LED_DEFINITIONS.")

        # 2. Load settings from external file, including potentially updated ROIs
        # camera_settings_to_apply will be the actual values for cv2.CAP_PROP
        # loaded_roi_coordinates will be { 'red': (x,y,w,h), 'green': (x,y,w,h) }
        self._camera_settings_to_apply, self._loaded_roi_coordinates = _load_all_camera_settings()

        # 3. Overwrite ROIs in self.led_configs with loaded values if present
        for led_name, roi_coords in self._loaded_roi_coordinates.items():
            if led_name in self.led_configs:
                self.led_configs[led_name]["roi"] = roi_coords
                self.logger.debug(f"Overwrote ROI for '{led_name}' with loaded value: {roi_coords}")
            else:
                self.logger.warning(f"ROI for '{led_name}' found in config file but not defined in PRIMARY_LED_CONFIGURATIONS. Skipping.")

        # 4. Final validation of LED configs (ensure all required keys are present and types are correct)
        if not isinstance(self.led_configs, dict) or not self.led_configs:
             raise ValueError("LED configurations are missing or invalid after loading.")

        core_keys = ["name", "roi", "hsv_lower", "hsv_upper", "min_match_percentage"]
        for key, config_item in self.led_configs.items():
            if not isinstance(config_item, dict): raise ValueError(f"LED config item '{key}' not a dict.")
            if any(k not in config_item for k in core_keys):
                raise ValueError(f"LED config '{key}' missing core keys.")
            if not (isinstance(config_item["roi"], tuple) and len(config_item["roi"]) == 4 and
                    all(isinstance(n, int) for n in config_item["roi"])):
                raise ValueError(f"ROI for LED '{key}' must be tuple of 4 ints.")
            
        if self.explicit_display_order:
            for key in self.explicit_display_order:
                if key not in self.led_configs:
                    raise ValueError(f"Key '{key}' in display_order not found in final LED configs.")
            
        self.stopped = False
        # One lock for the replay buffer, which now contains all data.
        self.buffer_lock = threading.Lock()

        if self.camera_id is None: self.logger.error("Camera ID cannot be None."); return 
        self._initialize_camera()

        if self.is_camera_initialized:
            self.thread = threading.Thread(target=self._update_frame_thread, args=())
            self.thread.daemon = True
            self.thread.start()

    def _update_frame_thread(self):
        """
        MODIFIED: This thread now also snapshots the set of active keys
        and includes it in the replay buffer tuple.
        """
        self.logger.info("Starting background frame-reading and processing thread.")
        while not self.stopped:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if not ret:
                    continue

                detected_led_states = {}
                for led_key, config_item in self.led_configs.items():
                    detected_led_states[led_key] = 1 if self._check_roi_for_color(frame, config_item) else 0

                # MODIFIED: Get a snapshot of active keys for this specific frame.
                with self.active_keys_lock:
                    active_keys_snapshot = self.active_keys_for_replay.copy()

                with self.buffer_lock:
                    current_capture_time = time.time()
                    # MODIFIED: The tuple now includes the active keys snapshot.
                    self.replay_buffer.append((current_capture_time, frame.copy(),
                                               detected_led_states.copy(), active_keys_snapshot))
                    if self.replay_frame_width is None or self.replay_frame_height is None:
                        h, w = frame.shape[:2]
                        self.replay_frame_width, self.replay_frame_height = w, h
            else:
                time.sleep(0.1)
        self.logger.info("Frame-reading and processing thread has stopped.")

    def _initialize_camera(self):
        try:
            if self.preferred_backend is not None:
                self.cap = cv2.VideoCapture(self.camera_id, self.preferred_backend)
            else:
                self.cap = cv2.VideoCapture(self.camera_id)

            if not self.cap.isOpened():
                if self.preferred_backend is not None:
                    self.logger.warning(f"Preferred backend ({self.preferred_backend}) failed for camera ID {self.camera_id}. Trying default.")
                    self.cap = cv2.VideoCapture(self.camera_id) 
                if not self.cap.isOpened():
                    backend_name_str = f" with backend {cv2.videoio_registry.getBackendName(self.preferred_backend)}" if self.preferred_backend and hasattr(cv2.videoio_registry, 'getBackendName') else ""
                    raise IOError(f"Cannot open webcam {self.camera_id}{backend_name_str} or with default backend.")
                
            self.logger.info("Applying hard-coded camera hardware settings...")
            prop_names = {
                cv2.CAP_PROP_AUTO_EXPOSURE: "Auto Exposure",
                cv2.CAP_PROP_EXPOSURE: "Exposure",
                cv2.CAP_PROP_AUTOFOCUS: "Autofocus",
                cv2.CAP_PROP_FOCUS: "Focus",
                cv2.CAP_PROP_AUTO_WB: "Auto White Balance",
                cv2.CAP_PROP_WB_TEMPERATURE: "White Balance Temp",
                cv2.CAP_PROP_GAIN: "Gain",
                cv2.CAP_PROP_BRIGHTNESS: "Brightness",
                cv2.CAP_PROP_CONTRAST: "Contrast",
                cv2.CAP_PROP_SATURATION: "Saturation",
            }
            # Iterate through the LOADED settings (which might be defaults or from file)
            for prop, value in self._camera_settings_to_apply.items():
                prop_name = prop_names.get(prop, f"Property_ID_{prop}")
                
                # ADDED: Log the value of relevant properties BEFORE attempting to set
                if prop == cv2.CAP_PROP_EXPOSURE:
                    current_val = self.cap.get(cv2.CAP_PROP_EXPOSURE)
                    self.logger.debug(f"  [Init] Before setting {prop_name}, current value is: {current_val}")
                elif prop == cv2.CAP_PROP_FOCUS:
                    current_val = self.cap.get(cv2.CAP_PROP_FOCUS)
                    self.logger.debug(f"  [Init] Before setting {prop_name}, current value is: {current_val}")
                elif prop == cv2.CAP_PROP_AUTOFOCUS:
                    current_val = self.cap.get(cv2.CAP_PROP_AUTOFOCUS)
                    self.logger.debug(f"  [Init] Before setting {prop_name}, current value is: {current_val}")
                elif prop == cv2.CAP_PROP_AUTO_EXPOSURE:
                    current_val = self.cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)
                    self.logger.debug(f"  [Init] Before setting {prop_name}, current value is: {current_val}")

                self.logger.debug(f"Attempting to set {prop_name} ({prop}) to {value}.")
                if self.cap.set(prop, value):
                    actual_value = self.cap.get(prop)
                    self.logger.info(f"Successfully set {prop_name} to {value} (read back: {actual_value}).")
                    if actual_value != value and prop not in [cv2.CAP_PROP_AUTO_EXPOSURE, cv2.CAP_PROP_AUTOFOCUS, cv2.CAP_PROP_AUTO_WB]:
                         # Warning if the camera didn't take the exact value, common for some props
                        self.logger.warning(f"  Note: {prop_name} read back value ({actual_value}) differs from set value ({value}). Camera likely applied closest supported value.")
                else:
                    self.logger.warning(f"FAILED to set {prop_name} to {value}. The camera/driver may not support this property or it's being overridden.")
                
            if not self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640):
                self.logger.warning("Failed to set camera width to 640.")

            if not self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480):
                self.logger.warning("Failed to set camera height to 480.")

            self.is_camera_initialized = True
            if self.cap.set(cv2.CAP_PROP_FPS, DEFAULT_FPS): pass
            else: self.logger.warning(f"Could not set FPS {DEFAULT_FPS} for camera ID {self.camera_id}.")
            
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            if actual_fps > 0:
                self.replay_fps = float(actual_fps) 
            self.logger.info(f"Camera Controller initialized successfully at {DEFAULT_FPS} FPS.")
        except Exception as e:
            self.logger.error(f"Failed to initialize camera {self.camera_id}: {e}", exc_info=True)
            self.is_camera_initialized = False
            if self.cap: self.cap.release()
            self.cap = None

    def _clear_camera_buffer(self):
        if not self.is_camera_initialized or not self.cap:
            self.logger.warning("Camera not initialized. Cannot clear buffer.")
            return
        try:
            for _ in range(CAMERA_BUFFER_SIZE_FRAMES):
                ret, _ = self.cap.read() 
                if not ret: self.logger.warning(f"Could not read frame while clearing buffer."); break
        except Exception as e:
            self.logger.error(f"Exception while clearing camera buffer: {e}", exc_info=True)

    def _check_roi_for_color(self, frame: np.ndarray, led_config_item: dict) -> bool:
        roi_rect = led_config_item["roi"]
        hsv_lower_orig = np.array(led_config_item["hsv_lower"])
        hsv_upper_orig = np.array(led_config_item["hsv_upper"])
        min_match_percentage = led_config_item["min_match_percentage"]
        x, y, w, h = roi_rect
        if w <= 0 or h <= 0: return False
        frame_h, frame_w = frame.shape[:2]
        x_start, y_start = max(0, x), max(0, y)
        x_end, y_end = min(frame_w, x + w), min(frame_h, y + h)
        actual_w, actual_h = x_end - x_start, y_end - y_start
        if actual_w <= 0 or actual_h <= 0: return False
        led_roi_color = frame[y_start:y_end, x_start:x_end]
        if led_roi_color.size == 0: return False
        hsv_roi = cv2.cvtColor(led_roi_color, cv2.COLOR_BGR2HSV)
        if hsv_lower_orig[0] > hsv_upper_orig[0]:
            lower1 = np.array([hsv_lower_orig[0], hsv_lower_orig[1], hsv_lower_orig[2]])
            upper1 = np.array([179, hsv_upper_orig[1], hsv_upper_orig[2]])
            mask1 = cv2.inRange(hsv_roi, lower1, upper1)
            lower2 = np.array([0, hsv_lower_orig[1], hsv_lower_orig[2]])
            upper2 = np.array([hsv_upper_orig[0], hsv_upper_orig[1], hsv_upper_orig[2]])
            mask2 = cv2.inRange(hsv_roi, lower2, upper2)
            color_mask = cv2.bitwise_or(mask1, mask2)
        else: 
            color_mask = cv2.inRange(hsv_roi, hsv_lower_orig, hsv_upper_orig)
        matching_pixels = cv2.countNonZero(color_mask)
        total_pixels_in_roi = actual_w * actual_h
        if total_pixels_in_roi == 0: return False
        current_match_percentage = matching_pixels / float(total_pixels_in_roi)
        return current_match_percentage >= min_match_percentage

    def _get_current_led_state_from_camera(self) -> Tuple[Optional[np.ndarray], Dict[str, int]]:
        """
        CORRECTED: This method now correctly unpacks the 4-element tuple from the
        replay buffer but still returns only the frame and states to its callers.
        """
        with self.buffer_lock:
            if not self.replay_buffer:
                return None, {}
            
            # CORRECTED: Unpack the 4-element tuple that is now stored in the buffer.
            # We ignore the timestamp and active_keys for the immediate return value.
            _, last_frame, last_states, _ = self.replay_buffer[-1]
            
            # Return a copy to ensure thread safety for consumers of this data.
            return last_frame.copy(), last_states.copy()
        
    def _draw_text_with_background(self, img: np.ndarray, text: str, pos: Tuple[int, int]):
        """
        NEW: This is the missing helper function.
        Draws the given text on the image with an opaque background for better readability.

        Args:
            img: The image (frame) to draw on.
            text: The string of text to draw.
            pos: A tuple (x, y) representing the bottom-left starting position of the text.
        """
        text_size, _ = cv2.getTextSize(text, OVERLAY_FONT, OVERLAY_FONT_SCALE, OVERLAY_FONT_THICKNESS)
        text_w, text_h = text_size
        
        # The 'y' in the position tuple is the baseline of the text.
        x, y = pos

        # Calculate the coordinates for the background rectangle.
        rect_x1 = x - OVERLAY_PADDING
        rect_y1 = y - text_h - OVERLAY_PADDING
        rect_x2 = x + text_w + OVERLAY_PADDING
        rect_y2 = y + OVERLAY_PADDING
        
        # Draw the opaque background rectangle.
        cv2.rectangle(img, (rect_x1, rect_y1), (rect_x2, rect_y2), OVERLAY_BG_COLOR, -1)
        
        # Draw the text on top of the background.
        cv2.putText(img, text, pos, OVERLAY_FONT, OVERLAY_FONT_SCALE, OVERLAY_TEXT_COLOR_MAIN, OVERLAY_FONT_THICKNESS, cv2.LINE_AA)

    def _draw_overlays(self, frame: np.ndarray, timestamp_in_replay: float, led_state_for_frame: Dict[str, int], active_keys_for_frame: set) -> np.ndarray:
        overlay_frame = frame.copy()
        current_y_offset = OVERLAY_PADDING

        # --- FSM State and other text overlays (unchanged) ---
        if self.replay_extra_context:
            fsm_curr = self.replay_extra_context.get('fsm_current_state', 'N/A')
            fsm_dest = self.replay_extra_context.get('fsm_destination_state', 'N/A')
            
            self._draw_text_with_background(overlay_frame, f"Current State: {fsm_curr}", 
                        (OVERLAY_PADDING + 5, current_y_offset + OVERLAY_LINE_HEIGHT))
            current_y_offset += OVERLAY_LINE_HEIGHT

            self._draw_text_with_background(overlay_frame, f"Destination State: {fsm_dest}",
                        (OVERLAY_PADDING + 5, current_y_offset + OVERLAY_LINE_HEIGHT))
            current_y_offset += (OVERLAY_LINE_HEIGHT * 2)

        # --- Keypad Overlay Drawing ---
        if self.keypad_layout:
            key_height, key_width = 30, 45
            key_padding = 5

            X_OFFSET_FROM_LEFT = 10   # Pixels from the left edge
            Y_OFFSET_FROM_BOTTOM = 50 # Pixels from the bottom edge
            
            num_rows = len(self.keypad_layout)
            grid_height = (key_height * num_rows) + (key_padding * (num_rows -1))
            
            start_x = OVERLAY_PADDING + X_OFFSET_FROM_LEFT
            start_y = overlay_frame.shape[0] - grid_height - OVERLAY_PADDING - Y_OFFSET_FROM_BOTTOM

            for row_idx, row_of_keys in enumerate(self.keypad_layout):
                for col_idx, key_name in enumerate(row_of_keys):
                    x1 = start_x + col_idx * (key_width + key_padding)
                    y1 = start_y + row_idx * (key_height + key_padding)
                    x2, y2 = x1 + key_width, y1 + key_height
                    
                    is_pressed = key_name in active_keys_for_frame
                    
                    rect_color = (200, 200, 200)
                    rect_thickness = -1 if is_pressed else 2
                    cv2.rectangle(overlay_frame, (x1, y1), (x2, y2), rect_color, rect_thickness)
                    
                    if is_pressed:
                        cv2.rectangle(overlay_frame, (x1, y1), (x2, y2), OVERLAY_TEXT_COLOR_MAIN, 2)

                    text_color = (0, 0, 0) if is_pressed else OVERLAY_TEXT_COLOR_MAIN
                    cv2.putText(overlay_frame, key_name, (x1 + 5, y1 + 20), OVERLAY_FONT, 0.4, text_color, 1)

        # --- ROI and LED Indicator Drawing (unchanged) ---
        ordered_leds = self._get_ordered_led_keys_for_display()
        for led_key in ordered_leds:
            if led_key not in self.led_configs:
                continue
            config_item = self.led_configs[led_key]
            x, y, w, h = config_item["roi"]
            roi_box_color = config_item.get("display_color_bgr", (128, 128, 128))
            cv2.rectangle(overlay_frame, (x, y), (x + w, y + h), roi_box_color, 1)
            indicator_x_pos = x + (w // 2)
            indicator_y_pos = y - OVERLAY_LINE_HEIGHT
            if indicator_y_pos < OVERLAY_LED_INDICATOR_RADIUS + OVERLAY_PADDING:
                indicator_y_pos = OVERLAY_LED_INDICATOR_RADIUS + OVERLAY_PADDING
            is_on = led_state_for_frame.get(led_key, 0) == 1
            indicator_color = OVERLAY_TEXT_COLOR_MAIN if is_on else OVERLAY_LED_INDICATOR_OFF_COLOR
            cv2.circle(overlay_frame, (indicator_x_pos, indicator_y_pos), OVERLAY_LED_INDICATOR_RADIUS, indicator_color, -1)
            cv2.circle(overlay_frame, (indicator_x_pos, indicator_y_pos), OVERLAY_LED_INDICATOR_RADIUS, OVERLAY_TEXT_COLOR_MAIN, 1)

        return overlay_frame
    
    def set_keypad_layout(self, layout: list[list[str]]):
        self.logger.info(f"Keypad layout for replay overlays has been set.")
        self.keypad_layout = layout

    def _add_key_to_replay(self, key_name: str):
        """NEW: A thread-safe helper called by a Timer to add a key to the active set."""
        with self.active_keys_lock:
            self.active_keys_for_replay.add(key_name)

    def _remove_key_from_replay(self, key_name: str):
        """A thread-safe callback for the Timer to remove a key from the active set."""
        with self.active_keys_lock:
            self.active_keys_for_replay.discard(key_name)

    def log_key_press_for_replay(self, key_name: str, duration_s: float):
        """
        CORRECTED: Now adds a fixed "sustain" time to the visual overlay's
        duration to improve the "feel" of the key release.
        """
        if not self.enable_instant_replay:
            return

        # Timer to ADD the key to the visual set after a small delay.
        # This remains unchanged.
        threading.Timer(
            KEY_PRESS_VISUAL_DELAY_S,
            self._add_key_to_replay,
            [key_name]
        ).start()

        # Timer to REMOVE the key.
        # CORRECTED: We add the new sustain time to the total duration.
        total_visual_duration = KEY_PRESS_VISUAL_DELAY_S + duration_s + KEY_PRESS_VISUAL_SUSTAIN_S
        
        threading.Timer(
            total_visual_duration,
            self._remove_key_from_replay,
            [key_name]
        ).start()

    def start_key_press_for_replay(self, key_name: str):
        """
        NEW: Adds a key to the active set for an indefinite hold (for use with on()).
        This is thread-safe.
        """
        if not self.enable_instant_replay:
            return
        
        with self.active_keys_lock:
            self.active_keys_for_replay.add(key_name)
        self.logger.debug(f"Replay Overlay: Started persistent press for '{key_name}'.")

    def stop_key_press_for_replay(self, key_name: str):
        """
        NEW: Removes a key from the active set to end an indefinite hold (for use with off()).
        This is thread-safe.
        """
        if not self.enable_instant_replay:
            return
            
        with self.active_keys_lock:
            self.active_keys_for_replay.discard(key_name)
        self.logger.debug(f"Replay Overlay: Stopped persistent press for '{key_name}'.")

    def _start_replay_recording(self, method_name: str, extra_context: Optional[Dict[str, str]] = None):
        """
        MODIFIED: This method now ONLY arms the replay system. It does not set
        the start time, as that will be anchored to the moment of failure.
        """
        if not self.enable_instant_replay:
            self.logger.debug(f"Replay not armed for '{method_name}': Instant replay is disabled.")
            return
        if not self.replay_output_dir:
            self.logger.debug(f"Replay not armed for '{method_name}': output directory not available.")
            return
        if self.is_replay_armed:
            self.logger.debug(f"Replay: System already armed for method '{self.replay_method_name}'. Ignoring start for '{method_name}'.")
            return

        self.is_replay_armed = True
        # CORRECTED: The start time is no longer set here.
        self.replay_method_name = method_name
        self.replay_extra_context = extra_context.copy() if extra_context else {}
        self.replay_failure_reason = ""
        self.logger.debug(f"Replay system armed for method '{method_name}'.")

    def _save_replay_video(self, replay_sequence_to_save: list):
        """
        CORRECTED: Now correctly unpacks the 4-element tuple from the buffer
        and calls the updated _draw_overlays function with all 4 arguments.
        """
        if not self.is_replay_armed or not replay_sequence_to_save or not self.replay_output_dir:
            if not replay_sequence_to_save and self.is_replay_armed: self.logger.debug("Replay: No frames in sequence to save.")
            return

        self.logger.debug(f"Replay: Writing a total of {len(replay_sequence_to_save)} frames to video.")

        if self.replay_frame_width is None or self.replay_frame_height is None:
            self.logger.error("Replay: Frame dimensions not set. Cannot save video.")
            return

        timestamp_str = datetime.datetime.now().strftime("%H-%M-%S")
        method_name_safe = self.replay_method_name.replace(" ", "_")
        filename_base = f"replay_{timestamp_str}_{method_name_safe}.mp4"
        filepath = os.path.join(self.replay_output_dir, filename_base)

        fourcc = int.from_bytes(b'mp4v', 'little')
        video_writer = None
        try:
            video_writer = cv2.VideoWriter(filepath, fourcc, self.replay_fps,
                                           (self.replay_frame_width, self.replay_frame_height))
            if not video_writer.isOpened():
                self.logger.error(f"Replay: Failed to open VideoWriter for {filepath}."); return

            # Unpack the 4-element tuple from the replay sequence
            for frame_capture_time, frame_data, led_state, active_keys in replay_sequence_to_save:
                time_in_replay_seconds = frame_capture_time - self.replay_start_time
                # Pass all 4 arguments to the drawing function
                frame_with_overlays = self._draw_overlays(frame_data, time_in_replay_seconds, led_state, active_keys)

                fh_overlay, fw_overlay = frame_with_overlays.shape[:2]
                if fw_overlay == self.replay_frame_width and fh_overlay == self.replay_frame_height:
                    video_writer.write(frame_with_overlays)
                else:
                    self.logger.warning(f"Replay: Overlay frame dimension mismatch. Resizing.")
                    resized_overlay_frame = cv2.resize(frame_with_overlays, (self.replay_frame_width, self.replay_frame_height))
                    video_writer.write(resized_overlay_frame)

            self.logger.info(f"Replay: Successfully wrote frames to {filepath}.")
        except Exception as e:
            self.logger.error(f"Replay: Error during video writing for {filepath}: {e}", exc_info=True)
        finally:
            if video_writer: video_writer.release()

    def _stop_replay_recording(self, success: bool, failure_reason: str = "unspecified_failure"):
        """
        CORRECTED: Now properly snapshots the pre-roll buffer *before* capturing
        post-roll footage to prevent data loss.
        """
        if not self.is_replay_armed: return

        if not success:
            self.replay_failure_reason = failure_reason.replace("_", " ")
            if self.replay_buffer and self.replay_output_dir:
                self.replay_start_time = time.time()
                
                # CORRECTED LOGIC: Snapshot the pre-roll buffer immediately.
                pre_roll_footage = list(self.replay_buffer)
                
                # DEBUG LOG: Log the number of pre-roll frames captured.
                self.logger.debug(f"Replay: Failure '{self.replay_failure_reason}'. "
                                  f"Captured {len(pre_roll_footage)} pre-roll frames. Now recording post-failure.")

                post_roll_footage = []
                post_failure_start_time = time.time()
                while time.time() - post_failure_start_time < self.replay_post_failure_duration_sec:
                    frame, detected_led_states = self._get_current_led_state_from_camera()
                    # The main buffer continues to update, but we don't care about it anymore for this save.
                    if frame is not None:
                        # We append to our temporary post-roll list.
                        post_roll_footage.append((time.time(), frame.copy(), detected_led_states))
                    time.sleep(1.0 / self.replay_fps if self.replay_fps > 0 else 0.01)
                
                # DEBUG LOG: Log the number of post-roll frames captured.
                self.logger.debug(f"Replay: Captured {len(post_roll_footage)} post-roll frames.")
                
                full_replay_sequence = pre_roll_footage + post_roll_footage
                
                self._save_replay_video(full_replay_sequence)
            else:
                self.logger.debug("Failure occurred, but no replay will be saved (buffer empty or output dir not set).")
        
        # Disarm the system. The main circular buffer continues to run.
        self.is_replay_armed = False
        self.replay_method_name = ""
        self.replay_failure_reason = ""
        self.replay_extra_context = None

    def _matches_state(self, current_state: dict, target_state: dict, fail_leds: Optional[List[str]] = None) -> bool:
        if not current_state: return False
        if fail_leds:
            for led_name in fail_leds:
                if current_state.get(led_name, 0) == 1: return False 
        for led, expected_value in target_state.items():
            if current_state.get(led, 0) != expected_value: return False 
        return True 
    
    def _get_ordered_led_keys_for_display(self) -> List[str]:
        if self._ordered_keys_for_display_cache is None:
            if self.explicit_display_order:
                self._ordered_keys_for_display_cache = self.explicit_display_order
            else:
                available_keys = list(self.led_configs.keys())
                ordered_keys = [key for key in DEFAULT_LED_DISPLAY_ORDER if key in available_keys]
                remaining_keys = sorted([key for key in available_keys if key not in ordered_keys])
                ordered_keys.extend(remaining_keys)
                self._ordered_keys_for_display_cache = ordered_keys
        return self._ordered_keys_for_display_cache

    def _format_led_display_string(self, target_state_dict: dict, ordered_keys: Optional[List[str]]=None) -> str:
        if ordered_keys is None: ordered_keys = self._get_ordered_led_keys_for_display()
        parts = []
        for i, key in enumerate(ordered_keys):
            if key in self.led_configs: 
                parts.append(f"({i+1})" if target_state_dict.get(key, 0) == 1 else "( )")
        return " ".join(parts)

    def _handle_state_change_logging(self, current_state_dict: dict, current_time: float,
                                     last_state_info: list, reason: str = "") -> bool:
        # CORRECTED: All replay-related logic has been removed from this function.
        # Its only responsibility is to log state changes to the console/log file.
        # Frame buffering is now handled exclusively and continuously by _get_current_led_state_from_camera.
        prev_state_dict, prev_state_timestamp = last_state_info
        if prev_state_dict is None: 
            last_state_info[0] = current_state_dict
            last_state_info[1] = current_time
            return False 
        
        logged_change = False
        if current_state_dict != prev_state_dict:
            duration = current_time - prev_state_timestamp
            if duration >= MIN_LOGGABLE_STATE_DURATION:
                self.logger.info(f"{self._format_led_display_string(prev_state_dict)} ({duration:.2f}s)")
                logged_change = True
            last_state_info[0] = current_state_dict
            last_state_info[1] = current_time
        return logged_change
        
    def _log_final_state(self, last_state_info: list, end_time: float, reason_suffix: str = ""):
        state_dict, state_timestamp = last_state_info
        if state_dict is not None:
            duration = end_time - state_timestamp
            if duration >= MIN_LOGGABLE_STATE_DURATION:
                self.logger.info(f"{self._format_led_display_string(state_dict)} ({duration:.2f}s{reason_suffix})")

    def _process_pattern_step(self, step_cfg: dict, ordered_keys: List[str], overall_timeout_end_time: float, step_idx: int, total_steps: int) -> Tuple[bool, str]:
        """
        Processes a single step in an LED pattern sequence: finds the state and confirms its duration.

        Args:
            step_cfg: Dictionary defining the target state and duration for this step.
            ordered_keys: Ordered list of LED keys for consistent display string formatting.
            overall_timeout_end_time: The absolute time at which the entire pattern check should timeout.
            step_idx: The 0-based index of the current step.
            total_steps: The total number of steps in the pattern.

        Returns:
            A tuple (success: bool, failure_reason: str).
        """
        target_state_for_step = {k: v for k, v in step_cfg.items() if k != 'duration'}
        min_d_orig, max_d_orig = step_cfg.get('duration', (0, float('inf')))
        min_d_check = min_d_orig
        max_d_check = max_d_orig + self.duration_tolerance_sec if max_d_orig != float('inf') else float('inf')
        target_state_str = self._format_led_display_string(target_state_for_step, ordered_keys)

        self.logger.debug(f"Pattern step {step_idx + 1}/{total_steps}: Awaiting '{target_state_str}' (min {min_d_orig:.2f}s, max {max_d_orig:.2f}s)")

        # --- Phase 1: Find the target state for this step ---
        step_seen_at = None
        step_find_start_time = time.time()
        
        # Determine the maximum time to wait for the step to *appear*.
        step_appearance_timeout = max(1.0, max_d_orig if max_d_orig != float('inf') else 5.0) + 2.0
        
        # For a 0.0 duration first step, allow a brief moment for it to appear/be skipped
        if step_idx == 0 and min_d_orig == 0.0:
            step_appearance_timeout = 0.5 
        
        # Ensure we don't exceed the overall pattern timeout
        current_step_find_timeout_end_time = min(overall_timeout_end_time, time.time() + step_appearance_timeout)

        while time.time() < current_step_find_timeout_end_time:
            _, current_leds = self._get_current_led_state_from_camera()
            if not current_leds:
                time.sleep(0.001)
                continue
            if self._matches_state(current_leds, target_state_for_step):
                step_seen_at = time.time()
                break
            time.sleep(0.001)

        if step_seen_at is None:
            # Special handling for initial 0-duration step not found
            if step_idx == 0 and min_d_orig == 0.0:
                self.logger.info(f"Pattern step {step_idx + 1}/{total_steps}: '{target_state_str}' (0.00s) - Not present but 0 duration. Continuing.")
                return True, "" # Treat as a skip/pass for 0-duration first step not seen
            return False, f"step_{step_idx+1}_not_seen_{target_state_str.replace(' ','_')}"
        
        self.logger.debug(f"Pattern step {step_idx + 1}/{total_steps}: '{target_state_str}' detected. Confirming duration.")

        # --- Phase 2: Confirm the state holds for the required duration ---
        held_time = None
        while time.time() < overall_timeout_end_time:
            current_time = time.time()
            held_time = current_time - step_seen_at
            
            _, current_leds = self._get_current_led_state_from_camera()
            if not current_leds:
                time.sleep(0.001)
                continue
            
            if self._matches_state(current_leds, target_state_for_step):
                # Check for max duration violation first
                if max_d_check != float('inf') and held_time > max_d_check:
                    return False, f"step_{step_idx+1}_exceeded_max_duration_held_{held_time:.2f}s_max_{max_d_orig:.2f}s"
                
                # Check if minimum duration is met
                if held_time >= min_d_check:
                    self.logger.info(f"Pattern step {step_idx + 1}/{total_steps}: '{target_state_str}' held for {held_time:.2f}s.")
                    return True, "" # Success for this step
            else: # State changed early
                if held_time >= min_d_check:
                    self.logger.info(f"Pattern step {step_idx + 1}/{total_steps}: '{target_state_str}' held for {held_time:.2f}s (state changed but min duration met).")
                    return True, "" # Success for this step, as minimum was met
                elif held_time >= (min_d_orig - self.duration_tolerance_sec):
                    self.logger.warning(f"Pattern step {step_idx + 1}/{total_steps}: '{target_state_str}' held for {held_time:.2f}s. Shorter than required {min_d_orig:.2f}s but within tolerance. Passing.")
                    return True, "" # Pass due to tolerance
                else:
                    current_led_str = self._format_led_display_string(current_leds, ordered_keys)
                    return False, f"step_{step_idx+1}_state_{target_state_str.replace(' ','_')}_changed_to_{current_led_str.replace(' ','_')}_early_held_{held_time:.2f}s_min_{min_d_orig:.2f}s"
            
            time.sleep(0.001) # Small sleep to prevent busy-waiting

        # If the loop finishes without success or failure (i.e., hit overall_timeout_end_time), it's a timeout.
        return False, f"timeout_hold_step_{step_idx+1}_held_{held_time:.2f}s"

    def _await_state_appearance(self, target_state: Dict[str, int], timeout_end_time: float, 
                               fail_leds: Optional[List[str]] = None, 
                               last_state_info_for_logging: Optional[List[Any]] = None,
                               description: str = "target state") -> Tuple[bool, Optional[float], str]:
        """
        Waits for a specific LED state to appear within a given timeout, optionally failing on other LEDs.
        Manages internal state logging if last_state_info_for_logging is provided.

        Args:
            target_state: The LED state dictionary to wait for.
            timeout_end_time: The absolute time by which the state must appear.
            fail_leds: List of LED names that, if ON, should cause an immediate failure.
            last_state_info_for_logging: A mutable list [state_dict, timestamp] for logging state changes.
                                         If None, no detailed state change logging occurs.
            description: A human-readable description of the state for logging.

        Returns:
            Tuple: (success: bool, time_state_appeared: Optional[float], failure_reason: str)
        """
        while time.time() < timeout_end_time:
            current_time = time.time()
            
            _, current_leds = self._get_current_led_state_from_camera()
            
            if last_state_info_for_logging is not None:
                self._handle_state_change_logging(current_leds, current_time, last_state_info_for_logging)

            if not current_leds:
                time.sleep(0.001) # Yield CPU if no frame is ready
                continue
            
            if fail_leds:
                for led_name in fail_leds:
                    if current_leds.get(led_name, 0) == 1:
                        actual_state_str = self._format_led_display_string(current_leds)
                        self.logger.warning(f"Failed to await '{description}': Prohibited LED '{led_name}' is ON. Current: {actual_state_str}")
                        return False, None, f"prohibited_led_{led_name}_on"

            if self._matches_state(current_leds, target_state):
                # Only log specific "target observed" message here, not state progression
                self.logger.debug(f"Awaited '{description}': state {self._format_led_display_string(target_state)} observed.")
                return True, current_time, "" # Success
            
            time.sleep(0.001) # Small sleep to prevent busy-waiting if state is not found immediately

        if last_state_info_for_logging is not None:
            self._log_final_state(last_state_info_for_logging, time.time(), reason_suffix=f" at timeout for {description}")
        return False, None, f"timeout_await_{description.replace(' ','_')}"

    # --- Public methods remain unchanged ---
    def confirm_led_solid(self, state: dict, minimum: float = 2, timeout: float = 10,
                          fail_leds: Optional[List[str]] = None, clear_buffer: bool = True, 
                          manage_replay: bool = True, replay_extra_context: Optional[Dict[str, str]] = None) -> bool:
        method_name = "confirm_led_solid"
        if manage_replay: self._start_replay_recording(method_name, extra_context=replay_extra_context)
        
        success_flag = False
        failure_detail = "unknown_solid_failure"
        
        formatted_target_state = self._format_led_display_string(state)
        self.logger.debug(f"Waiting for LED solid {formatted_target_state}, minimum {minimum:.2f}s (tol: {self.duration_tolerance_sec:.2f}s), timeout {timeout:.2f}s")
        
        if not self.is_camera_initialized: 
            self.logger.error(f"Camera not initialized for {method_name}.")
            failure_detail = "camera_not_initialized"
        else:
            last_state_info = [None, 0.0] 
            initial_capture_time = time.time()
            if clear_buffer: self._clear_camera_buffer()
            
            # CORRECTED: The call no longer takes a 'record_for_replay' argument.
            # The continuous buffer is always active.
            _, initial_leds_for_log = self._get_current_led_state_from_camera()
            if not initial_leds_for_log: initial_leds_for_log = {} 
            last_state_info = [initial_leds_for_log, initial_capture_time]

            overall_start_time = time.time()
            continuous_target_match_start_time = None
            try:
                while time.time() - overall_start_time < timeout:
                    current_time = time.time()
                    
                    # This call is correct, as it was already updated.
                    _, current_leds = self._get_current_led_state_from_camera()
                    
                    if not current_leds: 
                        self._handle_state_change_logging({}, current_time, last_state_info)
                        continuous_target_match_start_time = None
                        time.sleep(0.01) # Minimal sleep for empty frames
                        continue
                    
                    self._handle_state_change_logging(current_leds, current_time, last_state_info)

                    if self._matches_state(current_leds, state, fail_leds):
                        if continuous_target_match_start_time is None:
                            continuous_target_match_start_time = last_state_info[1] 
                        target_held_duration = current_time - continuous_target_match_start_time
                        if target_held_duration >= minimum:
                            self.logger.info(f"{self._format_led_display_string(last_state_info[0])} ({target_held_duration:.2f}s) - Solid Confirmed")
                            success_flag = True; break
                    else: 
                        continuous_target_match_start_time = None 
            
            except Exception as e_loop:
                failure_detail = f"exception_in_solid_loop_{type(e_loop).__name__}"
                self.logger.error(f"Exception in {method_name} loop: {e_loop}", exc_info=True)
                success_flag = False

            if not success_flag:
                self._log_final_state(last_state_info, time.time(), reason_suffix=" at timeout")
                if continuous_target_match_start_time is not None:
                    held_duration = time.time() - continuous_target_match_start_time
                    if held_duration >= (minimum - self.duration_tolerance_sec):
                        self.logger.warning(f"Timeout for {method_name}, but final duration {held_duration:.2f}s was within tolerance of required {minimum:.2f}s. Passing.")
                        success_flag = True
                    else:
                        failure_detail = f"timeout_target_active_for_{held_duration:.2f}s_needed_{minimum:.2f}s"
                        self.logger.warning(f"Timeout for {method_name}: Target {formatted_target_state} not solid. Reason: {failure_detail}")
                else:
                    failure_detail = f"timeout_target_not_solid_for_{minimum:.2f}s"
                    self.logger.warning(f"Timeout for {method_name}: Target {formatted_target_state} not solid. Reason: {failure_detail}")

        if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)
        return success_flag
    
    def confirm_led_solid_strict(self, state: dict, minimum: float, clear_buffer: bool = True,
                                 manage_replay: bool = True, replay_extra_context: Optional[Dict[str, str]] = None) -> bool:
        method_name = "confirm_led_solid_strict"
        if manage_replay: self._start_replay_recording(method_name, extra_context=replay_extra_context)
        success_flag, failure_detail = False, "unknown_strict_failure"

        formatted_target_state = self._format_led_display_string(state)
        self.logger.info(f"Waiting strictly solid {formatted_target_state}, min {minimum:.2f}s")

        if not self.is_camera_initialized:
            failure_detail = "camera_not_init_strict"; self.logger.error(f"{method_name}: {failure_detail}")
        else:
            last_state_info = [None, 0.0] 
            if clear_buffer: self._clear_camera_buffer()
            _, initial_leds = self._get_current_led_state_from_camera() # Refactored call
            initial_leds = initial_leds or {}
            last_state_info = [initial_leds, time.time()]
            self.logger.info(f"Initial for strict: {self._format_led_display_string(initial_leds)}")

            if not self._matches_state(initial_leds, state, None):
                failure_detail="initial_state_not_target_strict"; self.logger.warning(f"{method_name} FAILED: {failure_detail}")
            else:
                target_state_began_at = last_state_info[1]; strict_op_start_time = time.time()
                try:
                    while time.time() - target_state_began_at < minimum:
                        current_time = time.time()
                        if current_time - strict_op_start_time > (minimum + 5.0):
                            failure_detail=f"op_timeout_strict_aiming_{minimum:.2f}s"; self.logger.warning(f"{method_name} FAILED: {failure_detail}"); success_flag=False; break
                        _, current_leds = self._get_current_led_state_from_camera() # Refactored call
                        if not current_leds:
                            failure_detail="frame_capture_err_strict"; self.logger.warning(f"{method_name} FAILED: {failure_detail}"); success_flag=False; break
                        logged_a_change = self._handle_state_change_logging(current_leds, current_time, last_state_info)
                        
                        if not self._matches_state(current_leds, state, None):
                            held_for = current_time - target_state_began_at 
                            if not logged_a_change and last_state_info[0] is not None: self.logger.info(f"{self._format_led_display_string(last_state_info[0])} ({current_time - last_state_info[1]:.2f}s, broke strict sequence)")
                            
                            if held_for >= (minimum - self.duration_tolerance_sec):
                                self.logger.warning(f"Strict sequence broke at {held_for:.2f}s, but this is within tolerance of required {minimum:.2f}s. Passing.")
                                success_flag = True
                            else:
                                failure_detail=f"state_broke_strict_held_{held_for:.2f}s_needed_{minimum:.2f}s"; self.logger.warning(f"{method_name} FAILED: {failure_detail}"); success_flag=False
                            break

                        # time.sleep(1 / self.replay_fps if self.replay_fps > 0 else 0.1)
                        time.sleep(0.001)
                    else:
                        self._log_final_state(last_state_info, time.time(), reason_suffix=" on success") 
                        success_flag = True; self.logger.info(f"{method_name}: LED strictly solid confirmed: {formatted_target_state}")
                except Exception as e_strict_loop:
                    failure_detail=f"exception_strict_loop_{type(e_strict_loop).__name__}"; self.logger.error(f"Exception in {method_name} loop: {e_strict_loop}", exc_info=True); success_flag=False
        
        if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)
        return success_flag

    def await_led_state(self, state: dict, timeout: float = 1,
                        fail_leds: Optional[List[str]] = None, clear_buffer: bool = True,
                        manage_replay: bool = True, replay_extra_context: Optional[Dict[str, str]] = None) -> bool:
        method_name = "await_led_state"
        if manage_replay: self._start_replay_recording(method_name, extra_context=replay_extra_context)
        success_flag, failure_detail = False, "unknown_await_failure"

        formatted_target_state = self._format_led_display_string(state)
        self.logger.info(f"Awaiting LED state {formatted_target_state}, timeout {timeout:.2f}s")
        if not self.is_camera_initialized:
            failure_detail = "camera_not_init_await"
            self.logger.error(f"{method_name}: {failure_detail}")
        else:
            if clear_buffer: self._clear_camera_buffer()
            
            # Initialize state logging info for the helper
            _, initial_leds = self._get_current_led_state_from_camera()
            last_state_info_for_logging = [initial_leds or {}, time.time()]

            await_timeout_end_time = time.time() + timeout
            success_flag, _, reason = self._await_state_appearance(
                state,
                await_timeout_end_time,
                fail_leds=fail_leds,
                last_state_info_for_logging=last_state_info_for_logging, # Pass the logging info
                description=f"await {formatted_target_state}"
            )
            failure_detail = reason # If not successful, reason will contain the failure detail

            if success_flag:
                # _await_state_appearance will have already logged the transition;
                # just log the overall success of the await call if needed.
                self.logger.info(f"Target state {formatted_target_state} observed.")
            else:
                self.logger.warning(f"Timeout: {formatted_target_state} not observed. Reason: {failure_detail.replace('_', ' ')}")

        if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)
        return success_flag

    def confirm_led_pattern(self, pattern: list, clear_buffer: bool = True,
                            manage_replay: bool = True, replay_extra_context: Optional[Dict[str, str]] = None) -> bool:
        method_name = "confirm_led_pattern"
        if manage_replay: self._start_replay_recording(method_name, extra_context=replay_extra_context)
        success_flag, failure_detail = False, "unknown_pattern_failure"

        if not pattern:
            failure_detail = "empty_pattern"
            self.logger.warning(f"{method_name}: {failure_detail}")
        elif not self.is_camera_initialized:
            failure_detail = "camera_not_init_pattern"
            self.logger.error(f"{method_name}: {failure_detail}")
        else:
            try:
                if clear_buffer:
                    self._clear_camera_buffer()
                ordered_keys = self._get_ordered_led_keys_for_display()

                # Calculate overall timeout for the entire pattern
                max_dur_sum = sum(p.get('duration', (0, 1))[1] for p in pattern if p.get('duration', [0, 0])[1] != float('inf'))
                inf_steps = sum(1 for p in pattern if p.get('duration', [0, 0])[1] == float('inf'))
                # Add a generous buffer for each step and overall operation
                overall_timeout = max_dur_sum + (inf_steps * 10.0) + (len(pattern) * 5.0) + 15.0
                pattern_start_time = time.time()
                overall_timeout_end_time = pattern_start_time + overall_timeout
                
                self.logger.info(f"Starting pattern confirmation of {len(pattern)} steps. Overall timeout: {overall_timeout:.2f}s")

                for current_step_idx, step_cfg in enumerate(pattern):
                    if time.time() > overall_timeout_end_time:
                        failure_detail = f"overall_timeout_pattern_at_step_{current_step_idx+1}"
                        self.logger.error(f"{method_name} Error: {failure_detail}")
                        success_flag = False
                        break

                    step_success, step_failure_reason = self._process_pattern_step(
                        step_cfg, ordered_keys, overall_timeout_end_time, current_step_idx, len(pattern)
                    )

                    if not step_success:
                        failure_detail = step_failure_reason
                        success_flag = False
                        break # Break from pattern loop on first step failure
                else: # All steps completed successfully
                    success_flag = True
                    self.logger.info(f"{method_name}: LED pattern confirmed successfully.")

            except Exception as e_pattern_loop:
                failure_detail = f"exception_pattern_loop_{type(e_pattern_loop).__name__}"
                self.logger.error(f"Exception in {method_name} loop: {e_pattern_loop}", exc_info=True)
                success_flag = False

        if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)
        return success_flag
    
    def await_and_confirm_led_pattern(self, pattern: list, timeout: float, clear_buffer: bool = True,
                                      manage_replay: bool = True, replay_extra_context: Optional[Dict[str, str]] = None) -> bool:
        method_name = "await_and_confirm_led_pattern"
        if manage_replay: self._start_replay_recording(method_name, extra_context=replay_extra_context)
        success_flag, failure_detail = False, "unknown_await_confirm_failure"

        if not pattern: failure_detail="empty_pattern_await_confirm"; self.logger.warning(f"{method_name}: {failure_detail}")
        elif not self.is_camera_initialized: failure_detail="camera_not_init_await_confirm"; self.logger.error(f"{method_name}: {failure_detail}")
        else:
            self.logger.debug(f"Awaiting first state of pattern (timeout: {timeout:.2f}s), steps: {len(pattern)}.")
            first_state_target = {k:v for k,v in pattern[0].items() if k!='duration'}
            
            if self.await_led_state(first_state_target, timeout=timeout, clear_buffer=clear_buffer, 
                                    manage_replay=False, replay_extra_context=replay_extra_context):
                pattern_confirmed = self.confirm_led_pattern(pattern, clear_buffer=False, 
                                                             manage_replay=False, replay_extra_context=replay_extra_context)
                success_flag = pattern_confirmed
                if not pattern_confirmed:
                    failure_detail = "pattern_confirm_failed_after_await"
                else:
                    failure_detail = "" 
            else:
                formatted_first_state = self._format_led_display_string(first_state_target).replace(' ','_')
                failure_detail = f"first_state_{formatted_first_state}_not_observed_in_await_confirm"
                self.logger.warning(f"{method_name}: Pattern not started: {failure_detail}")
        
        if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)
        return success_flag

    def release_camera(self):
        self.stopped = True
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=1.0) # Wait for thread to exit cleanly
        
        # MODIFIED: Check the renamed flag.
        if self.is_replay_armed:
            self.logger.info("Replay: System was armed when camera released. Discarding potential replay.")
            self.is_replay_armed = False
        
        self.replay_buffer.clear()

        if self.cap and self.cap.isOpened(): self.cap.release(); self.logger.info(f"Camera ID {self.camera_id} released.")
        else: self.logger.debug(f"Camera ID {self.camera_id} was not open or already released.")
        self.cap = None; self.is_camera_initialized = False

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.release_camera()