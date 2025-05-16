# Directory: camera
# Filename: camera_controller.py
#!/usr/bin/env python3

import time
import logging
import cv2
import sys # Import sys to check platform
import numpy as np # Import numpy for array operations

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

DEFAULT_FPS = 30
CAMERA_BUFFER_SIZE_FRAMES = 5

# --- PRIMARY (USER-TUNED) LED CONFIGURATIONS ---
# THIS IS THE SINGLE SOURCE OF TRUTH FOR LED CONFIGURATIONS.
#
# !!! USERS: TUNE THESE VALUES BY EDITING THEM DIRECTLY IN THIS FILE. !!!
# Use flight-control/basic_tutorial_3.py to get visual feedback (like AvgHSV in ROIs)
# to help you decide on the correct hsv_lower, hsv_upper, and min_match_percentage values.
#
# Format for each led_key: {
#   "name": "Descriptive Name",
#   "roi": (x, y, w, h),                 # Region of Interest (top-left x,y, width, height)
#   "hsv_lower": (H_min, S_min, V_min),  # Lower HSV bound (H:0-179, S:0-255, V:0-255)
#   "hsv_upper": (H_max, S_max, V_max),  # Upper HSV bound
#   "min_match_percentage": 0.1,         # Min % of ROI pixels to match (0.0 to 1.0)
#   "display_color_bgr": (B, G, R)       # OPTIONAL: BGR color for drawing ROI in tuning script
# }
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
        "hsv_lower": (40, 100, 100),
        "hsv_upper": (85, 255, 255),
        "min_match_percentage": 0.15,
        "display_color_bgr": (0,255,0) 
    },
    "blue":  {
        "name": "Blue LED",
        "roi": (417, 165, 40, 40),
        "hsv_lower": (95, 100, 100),
        "hsv_upper": (130, 255, 255),
        "min_match_percentage": 0.15,
        "display_color_bgr": (255,0,0) 
    } 
}
# --- End of PRIMARY LED Configurations ---


# --- FALLBACK LED CONFIGURATIONS (Generic Placeholders) ---
_FALLBACK_LED_DEFINITIONS = {
    "fallback_led1": {
        "name": "Fallback Generic LED 1",
        "roi": (50, 50, 20, 20),
        "hsv_lower": (0, 100, 100), "hsv_upper": (10, 255, 255),
        "min_match_percentage": 0.1,
        "display_color_bgr": (128, 128, 128) # Grey
    },
}
# --- End of Fallback LED Configurations ---

# Define a default display order for common LED keys.
# This will be used if no explicit display_order is passed to the constructor.
DEFAULT_LED_DISPLAY_ORDER = ["red", "green", "blue", "yellow", "white", "amber", "orange", "cyan", "magenta"]


def get_capture_backend():
    """Returns a potentially preferred OpenCV capture backend based on the OS."""
    if sys.platform.startswith('win'):
        return cv2.CAP_DSHOW
    elif sys.platform.startswith('darwin'): # macOS
        return cv2.CAP_AVFOUNDATION
    return None


class LogitechLedChecker:
    def __init__(self, camera_id: int, logger_instance=None, led_configs=None, display_order: list = None):
        self.logger = logger_instance if logger_instance else logger
        self.cap = None
        self.is_camera_initialized = False
        self.camera_id = camera_id
        self.preferred_backend = get_capture_backend()
        self._ordered_keys_for_display_cache = None 
        self.explicit_display_order = display_order 

        if led_configs is not None:
            self.led_configs = led_configs
            self.logger.info("Using LED configurations explicitly provided by the caller.")
        elif PRIMARY_LED_CONFIGURATIONS and isinstance(PRIMARY_LED_CONFIGURATIONS, dict) and len(PRIMARY_LED_CONFIGURATIONS) > 0:
            self.led_configs = PRIMARY_LED_CONFIGURATIONS
            self.logger.info("Using PRIMARY_LED_CONFIGURATIONS defined in camera_controller.py.")
        else:
            self.led_configs = _FALLBACK_LED_DEFINITIONS
            self.logger.error(
                "Using _FALLBACK_LED_DEFINITIONS. These are generic placeholders and likely insufficient. "
                "For reliable LED detection, define and tune PRIMARY_LED_CONFIGURATIONS in camera_controller.py."
            )

        if not isinstance(self.led_configs, dict) or not self.led_configs:
             raise ValueError("LED configurations are missing or invalid. "
                              "Ensure PRIMARY_LED_CONFIGURATIONS is set in camera_controller.py or pass valid 'led_configs'.")

        if self.explicit_display_order:
            for key in self.explicit_display_order:
                if key not in self.led_configs:
                    raise ValueError(
                        f"Key '{key}' in provided 'display_order' not found in LED configurations. "
                        f"Available keys: {list(self.led_configs.keys())}"
                    )
            if len(self.explicit_display_order) != len(self.led_configs):
                 self.logger.warning(
                    f"The provided 'display_order' has {len(self.explicit_display_order)} keys, "
                    f"but LED configurations have {len(self.led_configs)} keys. "
                    "Only keys in 'display_order' will be shown in formatted logs; others will be ignored for display."
                 )

        core_keys = ["name", "roi", "hsv_lower", "hsv_upper", "min_match_percentage"]
        for key, config_item in self.led_configs.items():
            if not isinstance(config_item, dict):
                 raise ValueError(f"LED configuration item for '{key}' must be a dictionary.")
            if not all(k in config_item for k in core_keys):
                missing_keys = [k for k in core_keys if k not in config_item]
                raise ValueError(f"LED configuration for '{key}' is missing core keys: {missing_keys}. "
                                 f"Expected all of: {core_keys}.")
            
            if not (isinstance(config_item["roi"], tuple) and len(config_item["roi"]) == 4 and
                    all(isinstance(n, int) for n in config_item["roi"])):
                raise ValueError(f"ROI for LED '{key}' ('{config_item['name']}') must be a tuple of 4 integers (x, y, w, h).")
            if not (isinstance(config_item["hsv_lower"], tuple) and len(config_item["hsv_lower"]) == 3 and
                    all(isinstance(n, int) for n in config_item["hsv_lower"])) or \
               not (isinstance(config_item["hsv_upper"], tuple) and len(config_item["hsv_upper"]) == 3 and
                    all(isinstance(n, int) for n in config_item["hsv_upper"])):
                raise ValueError(f"hsv_lower/hsv_upper for LED '{key}' ('{config_item['name']}') must be a tuple of 3 integers (H, S, V).")
            if not isinstance(config_item["min_match_percentage"], float) or \
               not (0.0 <= config_item["min_match_percentage"] <= 1.0):
                raise ValueError(f"min_match_percentage for LED '{key}' ('{config_item['name']}') must be a float between 0.0 and 1.0.")

            if "display_color_bgr" in config_item:
                color_val = config_item["display_color_bgr"]
                if not (isinstance(color_val, tuple) and len(color_val) == 3 and
                        all(isinstance(n, int) and 0 <= n <= 255 for n in color_val)):
                    self.logger.warning(f"Optional 'display_color_bgr' for LED '{key}' is malformed. ")

        if self.camera_id is None:
            self.logger.error("Camera ID cannot be None. Please provide a valid camera ID.")
            return

        self._initialize_camera()

    # ... _initialize_camera, _clear_camera_buffer, _check_roi_for_color, _get_current_led_state_from_camera, _matches_state ...
    # ... confirm_led_solid, confirm_led_solid_strict, await_led_state ... (These are unchanged)

    def _initialize_camera(self):
        try:
            if self.preferred_backend is not None:
                self.cap = cv2.VideoCapture(self.camera_id, self.preferred_backend)
            else:
                self.cap = cv2.VideoCapture(self.camera_id)

            if not self.cap.isOpened():
                if self.preferred_backend is not None:
                    self.logger.warning(f"Preferred backend failed for camera ID {self.camera_id}. Trying default backend.")
                    self.cap = cv2.VideoCapture(self.camera_id)

                if not self.cap.isOpened():
                    raise IOError(f"Cannot open webcam {self.camera_id} with any tried backend.")

            self.is_camera_initialized = True
            self.logger.info(f"Camera Controller initialized successfully with camera ID: {self.camera_id}.")
        except Exception as e:
            self.logger.error(f"Failed to initialize camera {self.camera_id}: {e}")
            self.is_camera_initialized = False
            if self.cap:
                self.cap.release()
            self.cap = None

    def _clear_camera_buffer(self):
        self.logger.debug(f"Clearing camera buffer (discarding ~{CAMERA_BUFFER_SIZE_FRAMES} frames).")
        if not self.is_camera_initialized or not self.cap:
            self.logger.warning("Camera not initialized. Cannot clear buffer.")
            return
        try:
            for _ in range(CAMERA_BUFFER_SIZE_FRAMES):
                ret, frame = self.cap.read()
                if not ret:
                    self.logger.warning("Could not read frame while clearing buffer (stream ended or error).")
                    break
        except Exception as e:
            self.logger.error(f"Exception while clearing camera buffer: {e}")

    def _check_roi_for_color(self, frame, led_config_item: dict) -> bool:
        roi_rect = led_config_item["roi"]
        hsv_lower_orig = np.array(led_config_item["hsv_lower"])
        hsv_upper_orig = np.array(led_config_item["hsv_upper"])
        min_match_percentage = led_config_item["min_match_percentage"]
        # led_name = led_config_item["name"] # Not used in this version for brevity

        x, y, w, h = roi_rect
        if w <= 0 or h <= 0:
            return False

        frame_h_disp, frame_w_disp = frame.shape[:2]
        x_start, y_start = max(0, x), max(0, y)
        x_end, y_end = min(frame_w_disp, x + w), min(frame_h_disp, y + h)

        actual_w, actual_h = x_end - x_start, y_end - y_start
        if actual_w <= 0 or actual_h <= 0:
            return False

        led_roi_color = frame[y_start:y_end, x_start:x_end]
        if led_roi_color.size == 0:
            return False

        hsv_roi = cv2.cvtColor(led_roi_color, cv2.COLOR_BGR2HSV)
        
        if hsv_lower_orig[0] > hsv_upper_orig[0]: # Hue wraps around
            lower1 = np.array([hsv_lower_orig[0], hsv_lower_orig[1], hsv_lower_orig[2]])
            upper1 = np.array([179, hsv_upper_orig[1], hsv_upper_orig[2]])
            mask1 = cv2.inRange(hsv_roi, lower1, upper1)
            
            lower2 = np.array([0, hsv_lower_orig[1], hsv_lower_orig[2]])
            upper2 = np.array([hsv_upper_orig[0], hsv_upper_orig[1], hsv_upper_orig[2]])
            mask2 = cv2.inRange(hsv_roi, lower2, upper2)
            color_mask = cv2.bitwise_or(mask1, mask2)
        else: # Normal Hue range
            color_mask = cv2.inRange(hsv_roi, hsv_lower_orig, hsv_upper_orig)

        matching_pixels = cv2.countNonZero(color_mask)
        total_pixels_in_roi = actual_w * actual_h
        
        if total_pixels_in_roi == 0:
            return False

        current_match_percentage = matching_pixels / float(total_pixels_in_roi)
        return current_match_percentage >= min_match_percentage


    def _get_current_led_state_from_camera(self) -> dict:
        if not self.is_camera_initialized or not self.cap:
            self.logger.warning("Camera not initialized. Cannot get LED state.")
            return {}

        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                self.logger.warning("Failed to capture frame from camera.")
                return {}
        except Exception as e:
            self.logger.error(f"Exception while capturing frame: {e}")
            return {}

        detected_led_states = {}
        for led_key, config_item in self.led_configs.items():
            is_on = self._check_roi_for_color(frame, config_item)
            detected_led_states[led_key] = 1 if is_on else 0
        return detected_led_states

    def _matches_state(self, current_state: dict, target_state: dict, fail_leds: list = None) -> bool:
        if not current_state: 
            return False
        if fail_leds:
            for led_name in fail_leds:
                if led_name in current_state and current_state[led_name] == 1:
                    return False 
        for led, expected_value in target_state.items():
            if led not in current_state or current_state[led] != expected_value:
                return False 
        return True 

    def confirm_led_solid(self, state: dict, minimum: float = 2, timeout: float = 10,
                          fail_leds: list = None, clear_buffer: bool = True) -> bool:
        self.logger.debug(
            f"Attempting to confirm LED state {state} solid for {minimum}s "
            f"within {timeout}s. Fail_leds: {fail_leds}. Clear buffer: {clear_buffer}."
        )
        if not self.is_camera_initialized:
            self.logger.error("Camera not initialized for confirm_led_solid.")
            return False
        if clear_buffer:
            self._clear_camera_buffer()

        overall_start_time = time.time()
        continuous_match_start_time = None

        while time.time() - overall_start_time < timeout:
            current_leds = self._get_current_led_state_from_camera()
            
            if self._matches_state(current_leds, state, fail_leds):
                if continuous_match_start_time is None:
                    continuous_match_start_time = time.time() 
                
                if time.time() - continuous_match_start_time >= minimum:
                    self.logger.info(f"State {state} confirmed solid for {time.time() - continuous_match_start_time:.2f}s (min: {minimum:.2f}s).")
                    return True
            else:
                if continuous_match_start_time is not None:
                    self.logger.debug(f"State {state} broke after {time.time() - continuous_match_start_time:.2f}s.")
                continuous_match_start_time = None 

            time.sleep(1 / DEFAULT_FPS if DEFAULT_FPS > 0 else 0.1)

        if continuous_match_start_time is not None: 
            self.logger.warning(f"Timeout: State {state} was active for {time.time() - continuous_match_start_time:.2f}s, "
                                f"but did not meet full minimum {minimum:.2f}s within {timeout:.2f}s overall timeout.")
        else: 
            self.logger.warning(f"Timeout: State {state} not confirmed solid for {minimum:.2f}s within {timeout:.2f}s.")
        return False


    def confirm_led_solid_strict(self, state: dict, minimum: float, clear_buffer: bool = True) -> bool:
        self.logger.debug(
            f"Attempting strict confirm of LED state {state} solid for {minimum}s. "
            f"Clear buffer: {clear_buffer}."
        )
        if not self.is_camera_initialized:
            self.logger.error("Camera not initialized for confirm_led_solid_strict.")
            return False
        if clear_buffer:
            self._clear_camera_buffer()

        strict_start_time = time.time()
        while time.time() - strict_start_time < minimum:
            current_leds = self._get_current_led_state_from_camera()
            if not self._matches_state(current_leds, state, fail_leds=None):
                self.logger.warning(
                    f"Strict confirm for {state} FAILED. Current state {current_leds} broke sequence "
                    f"after {time.time() - strict_start_time:.2f}s (required {minimum:.2f}s)."
                )
                return False
            time.sleep(1 / DEFAULT_FPS if DEFAULT_FPS > 0 else 0.1)

        self.logger.info(f"State {state} strictly confirmed solid for {time.time() - strict_start_time:.2f}s (min: {minimum:.2f}s).")
        return True

    def await_led_state(self, state: dict, timeout: float = 1,
                        fail_leds: list = None, clear_buffer: bool = True) -> bool:
        self.logger.debug(
            f"Awaiting LED state {state} within {timeout}s. "
            f"Fail_leds: {fail_leds}. Clear buffer: {clear_buffer}."
        )
        if not self.is_camera_initialized:
            self.logger.error("Camera not initialized for await_led_state.")
            return False
        if clear_buffer:
            self._clear_camera_buffer()

        await_start_time = time.time()
        while time.time() - await_start_time < timeout:
            current_leds = self._get_current_led_state_from_camera()
            if self._matches_state(current_leds, state, fail_leds):
                # Concise log for await_led_state success
                # self.logger.info(f"State {state} observed after {time.time() - await_start_time:.2f}s.")
                self.logger.debug(f"State {state} observed by await_led_state after {time.time() - await_start_time:.2f}s.")
                return True
            time.sleep(1 / DEFAULT_FPS if DEFAULT_FPS > 0 else 0.1)

        self.logger.warning(f"Timeout: State {state} not observed within {timeout:.2f}s.")
        return False

    def _get_ordered_led_keys_for_display(self):
        if self._ordered_keys_for_display_cache is None:
            if self.explicit_display_order:
                self._ordered_keys_for_display_cache = self.explicit_display_order
                configured_keys = set(self.led_configs.keys())
                display_keys_set = set(self.explicit_display_order)
                not_displayed = configured_keys - display_keys_set
                if not_displayed:
                    self.logger.debug(f"LEDs {sorted(list(not_displayed))} are configured but not in 'display_order', so they won't appear in formatted pattern logs.")
            else:
                available_keys = list(self.led_configs.keys())
                ordered_keys = []
                for key in DEFAULT_LED_DISPLAY_ORDER:
                    if key in available_keys:
                        ordered_keys.append(key)
                        available_keys.remove(key) 
                if available_keys:
                    ordered_keys.extend(sorted(available_keys))
                self._ordered_keys_for_display_cache = ordered_keys
            
            self.logger.debug(f"Using display order for logs: {self._ordered_keys_for_display_cache}")
        return self._ordered_keys_for_display_cache


    def _format_led_display_string(self, target_state_dict, ordered_keys):
        parts = []
        for i, key in enumerate(ordered_keys):
            if key in self.led_configs: 
                if target_state_dict.get(key, 0) == 1: 
                    parts.append(f"({i+1})") 
                else: 
                    parts.append("( )")
        return "".join(parts)

    def confirm_led_pattern(self, pattern: list, clear_buffer: bool = True) -> bool:
        # Entry debug log for the whole pattern attempt
        self.logger.debug(f"Attempting to match LED pattern ({len(pattern)} steps) with concise logging...")
        if not pattern:
            self.logger.warning("Empty pattern provided to confirm_led_pattern.")
            return False
        if not self.is_camera_initialized:
            self.logger.error("Camera not initialized for confirm_led_pattern.")
            return False
        if clear_buffer:
            self._clear_camera_buffer()

        ordered_led_keys = self._get_ordered_led_keys_for_display()
        current_pattern_step_index = 0
        
        max_total_duration_sum = sum(p.get('duration', (0,1))[1] for p in pattern if isinstance(p.get('duration'), tuple) and len(p.get('duration')) == 2)
        overall_timeout_duration = max_total_duration_sum + len(pattern) * 1.0 + 10.0 
        pattern_start_time = time.time()

        # Store the state of the *previous* completed step for concise logging
        # This is the state that was just active when a transition occurs.
        previous_step_target_state_for_log = None 

        while current_pattern_step_index < len(pattern):
            if time.time() - pattern_start_time > overall_timeout_duration:
                self.logger.error(f"Overall pattern timeout ({overall_timeout_duration:.2f}s) reached at step {current_pattern_step_index + 1}.")
                return False

            step_config = pattern[current_pattern_step_index]
            target_led_state_for_step = {k: v for k, v in step_config.items() if k != 'duration'}
            min_duration, max_duration = step_config.get('duration', (0, float('inf')))
            
            # For verbose debugging of current step attempt:
            # step_label_debug = f"({current_pattern_step_index + 1:02d}/{len(pattern):02d})"
            # target_state_str_debug = self._format_led_display_string(target_led_state_for_step, ordered_led_keys)
            # self.logger.debug(f"{target_state_str_debug} {step_label_debug} Awaiting (min:{min_duration:.2f}s, max:{max_duration:.2f}s)")
            
            time_awaiting_step_start = time.time()
            initial_state_seen_at = None 

            while True: 
                if time.time() - pattern_start_time > overall_timeout_duration: 
                    # self.logger.error(f"Overall pattern timeout while awaiting step {current_pattern_step_index + 1}.") # Already logged by outer check
                    return False

                current_actual_leds = self._get_current_led_state_from_camera()
                
                if self._matches_state(current_actual_leds, target_led_state_for_step):
                    initial_state_seen_at = time.time()
                    # self.logger.debug(f"Step {current_pattern_step_index + 1} detected. Holding...")
                    break 
                
                if current_pattern_step_index == 0 and min_duration == 0.0 and \
                   not self._matches_state(current_actual_leds, target_led_state_for_step):
                    if time.time() - time_awaiting_step_start > 0.2: 
                        # self.logger.debug(f"Step {current_pattern_step_index + 1} (optional) skipped.")
                        # Log the "skipped" state as if it completed immediately
                        step_label = f"({current_pattern_step_index + 1:02d}/{len(pattern):02d})"
                        target_state_str = self._format_led_display_string(target_led_state_for_step, ordered_led_keys)
                        self.logger.info(f"{target_state_str} {step_label}")
                        previous_step_target_state_for_log = target_led_state_for_step
                        break 

                time.sleep(1 / DEFAULT_FPS if DEFAULT_FPS > 0 else 0.03) 

            if initial_state_seen_at is None: # True if optional first step was skipped
                if current_pattern_step_index == 0 and min_duration == 0.0: 
                    current_pattern_step_index += 1
                    continue 
                else:
                    self.logger.error(f"Step {current_pattern_step_index + 1} was never detected. Pattern failed.")
                    return False

            time_held_current_state = 0.0
            while True: 
                if time.time() - pattern_start_time > overall_timeout_duration: 
                    # self.logger.error(f"Overall pattern timeout while holding step {current_pattern_step_index + 1}.") # Already logged
                    return False

                current_actual_leds = self._get_current_led_state_from_camera()
                time_held_current_state = time.time() - initial_state_seen_at

                if self._matches_state(current_actual_leds, target_led_state_for_step):
                    if time_held_current_state > max_duration:
                        self.logger.warning(
                            f"Pattern FAILED at step {current_pattern_step_index + 1}: "
                            f"{self._format_led_display_string(target_led_state_for_step, ordered_led_keys)} "
                            f"held for {time_held_current_state:.2f}s, exceeding max_duration {max_duration:.2f}s."
                        )
                        return False
                    
                    if current_pattern_step_index == len(pattern) - 1 and time_held_current_state >= min_duration:
                        # Last step confirmed
                        step_label = f"({current_pattern_step_index + 1:02d}/{len(pattern):02d})"
                        target_state_str = self._format_led_display_string(target_led_state_for_step, ordered_led_keys)
                        self.logger.info(f"{target_state_str} {step_label}")
                        # self.logger.debug(f"Last step ({step_label}) confirmed. Held {time_held_current_state:.2f}s.")
                        current_pattern_step_index += 1 
                        break 
                else: 
                    if time_held_current_state >= min_duration:
                        # Step completed successfully by transition
                        step_label = f"({current_pattern_step_index + 1:02d}/{len(pattern):02d})"
                        target_state_str = self._format_led_display_string(target_led_state_for_step, ordered_led_keys)
                        self.logger.info(f"{target_state_str} {step_label}")
                        # self.logger.debug(
                        #     f"Step {step_label} completed. Held {time_held_current_state:.2f}s. "
                        #     f"Transitioned to {self._format_led_display_string(current_actual_leds, ordered_led_keys)}."
                        # )
                        previous_step_target_state_for_log = target_led_state_for_step
                        current_pattern_step_index += 1 
                        break 
                    else: 
                        self.logger.warning(
                            f"Pattern FAILED at step {current_pattern_step_index + 1}: "
                            f"{self._format_led_display_string(target_led_state_for_step, ordered_led_keys)} "
                            f"changed to {self._format_led_display_string(current_actual_leds, ordered_led_keys)} "
                            f"after only {time_held_current_state:.2f}s (min_duration {min_duration:.2f}s required)."
                        )
                        return False
                
                time.sleep(1 / DEFAULT_FPS if DEFAULT_FPS > 0 else 0.03) 
            
        if current_pattern_step_index == len(pattern):
            self.logger.info("Entire LED pattern confirmed successfully.")
            return True
        else:
            self.logger.warning(f"LED pattern ended inconclusively. Processed up to step {current_pattern_step_index} of {len(pattern)}.")
            return False

    def await_and_confirm_led_pattern(self, pattern: list, timeout: float,
                                      clear_buffer: bool = True) -> bool:
        self.logger.debug(
            f"Awaiting first state of pattern (timeout: {timeout}s) then confirming. "
            f"Total pattern steps: {len(pattern)}. Clear buffer: {clear_buffer}."
        )
        if not pattern:
            self.logger.warning("Empty pattern provided to await_and_confirm_led_pattern.")
            return False
        if not self.is_camera_initialized:
            self.logger.error("Camera not initialized for await_and_confirm_led_pattern.")
            return False
            
        first_step_config = pattern[0]
        first_state_to_await = {k: v for k, v in first_step_config.items() if k != 'duration'}
        
        if self.await_led_state(first_state_to_await, timeout=timeout, fail_leds=None, clear_buffer=clear_buffer):
            # self.logger.info("First state of pattern observed by await_led_state. Now confirming full pattern sequence.")
            self.logger.debug("First state observed. Proceeding with full pattern confirmation.")
            return self.confirm_led_pattern(pattern, clear_buffer=False) 
        else:
            self.logger.warning(f"First state ({first_state_to_await}) of pattern not observed within {timeout:.2f}s timeout for await_and_confirm_led_pattern.")
            return False

    def release_camera(self):
        self.logger.info(f"Releasing camera ID: {self.camera_id}.")
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.logger.info(f"Camera ID {self.camera_id} released.")
        self.cap = None
        self.is_camera_initialized = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release_camera()