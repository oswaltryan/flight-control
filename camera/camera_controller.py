# Directory: camera
# Filename: camera_controller.py
#!/usr/bin/env python3

import time
import logging # Standard library logging
import cv2
import sys # Import sys to check platform
import numpy as np # Import numpy for array operations

# Get the logger for this module. Its name will be 'camera.camera_controller'.
# Configuration (handlers, level, format) comes from the global setup.
logger = logging.getLogger(__name__)

DEFAULT_FPS = 30
CAMERA_BUFFER_SIZE_FRAMES = 5
MIN_LOGGABLE_STATE_DURATION = 0.01 # Seconds. States held for less than this won't be logged as "held".

# --- PRIMARY (USER-TUNED) LED CONFIGURATIONS ---
PRIMARY_LED_CONFIGURATIONS = {
    "red":   {
        "name": "Red LED",
        "roi": (187, 165, 40, 40),
        "hsv_lower": (165,150,150), # Hue lower bound for red (wraps around)
        "hsv_upper": (15,255,255),   # Hue upper bound for red
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
        "hsv_lower": (0, 100, 100), "hsv_upper": (10, 255, 255), # Example: generic red
        "min_match_percentage": 0.1,
        "display_color_bgr": (128, 128, 128) # Grey
    },
}
# --- End of Fallback LED Configurations ---

# Define a default display order for common LED keys for logging.
DEFAULT_LED_DISPLAY_ORDER = ["red", "green", "blue"]


def get_capture_backend():
    if sys.platform.startswith('win'):
        return cv2.CAP_DSHOW
    elif sys.platform.startswith('darwin'): # macOS
        return cv2.CAP_AVFOUNDATION
    # Add other platform-specific backends if needed (e.g., cv2.CAP_V4L2 for Linux)
    return None # Let OpenCV choose default


class LogitechLedChecker:
    def __init__(self, camera_id: int, logger_instance=None, led_configs=None, display_order: list = None):
        self.logger = logger_instance if logger_instance else logger
        self.cap = None
        self.is_camera_initialized = False # Set to True upon successful _initialize_camera
        self.camera_id = camera_id
        self.preferred_backend = get_capture_backend()
        self._ordered_keys_for_display_cache = None
        self.explicit_display_order = display_order

        # Determine LED configurations
        if led_configs is not None:
            self.led_configs = led_configs
            self.logger.debug("Using LED configurations explicitly provided by the caller.")
        elif PRIMARY_LED_CONFIGURATIONS and isinstance(PRIMARY_LED_CONFIGURATIONS, dict) and len(PRIMARY_LED_CONFIGURATIONS) > 0:
            self.led_configs = PRIMARY_LED_CONFIGURATIONS
        else:
            self.led_configs = _FALLBACK_LED_DEFINITIONS
            self.logger.error(
                "PRIMARY_LED_CONFIGURATIONS is empty or invalid. Using _FALLBACK_LED_DEFINITIONS. "
                "These are generic placeholders and likely insufficient for reliable LED detection. "
                "Please define and tune PRIMARY_LED_CONFIGURATIONS in camera_controller.py."
            )

        # Validate LED configurations structure
        if not isinstance(self.led_configs, dict) or not self.led_configs:
             self.logger.critical("LED configurations are missing or invalid. Cannot initialize LogitechLedChecker.")
             raise ValueError("LED configurations are missing or invalid. "
                              "Ensure PRIMARY_LED_CONFIGURATIONS is set or valid 'led_configs' are passed.")

        # Validate display_order if provided
        if self.explicit_display_order:
            for key in self.explicit_display_order:
                if key not in self.led_configs:
                    raise ValueError(
                        f"Key '{key}' in provided 'display_order' not found in LED configurations. "
                        f"Available keys: {list(self.led_configs.keys())}"
                    )
            if len(self.explicit_display_order) != len(self.led_configs):
                 self.logger.debug(
                    f"The provided 'display_order' has {len(self.explicit_display_order)} keys, "
                    f"but LED configurations have {len(self.led_configs)} keys. "
                    "Formatted logs will only show keys in 'display_order'."
                 )

        core_keys = ["name", "roi", "hsv_lower", "hsv_upper", "min_match_percentage"]
        for key, config_item in self.led_configs.items():
            if not isinstance(config_item, dict):
                 raise ValueError(f"LED configuration item for '{key}' must be a dictionary.")
            missing_keys = [k for k in core_keys if k not in config_item]
            if missing_keys:
                raise ValueError(f"LED configuration for '{key}' is missing core keys: {missing_keys}. "
                                 f"Expected all of: {core_keys}.")
            
            if not (isinstance(config_item["roi"], tuple) and len(config_item["roi"]) == 4 and
                    all(isinstance(n, int) for n in config_item["roi"])):
                raise ValueError(f"ROI for LED '{key}' ('{config_item['name']}') must be a tuple of 4 integers (x, y, w, h).")

        if self.camera_id is None:
            self.logger.error("Camera ID cannot be None. Please provide a valid camera ID.")
            return 

        self._initialize_camera()

    def _initialize_camera(self):
        try:
            if self.preferred_backend is not None:
                self.cap = cv2.VideoCapture(self.camera_id, self.preferred_backend)
            else:
                self.cap = cv2.VideoCapture(self.camera_id)

            if not self.cap.isOpened():
                if self.preferred_backend is not None:
                    self.logger.warning(f"Preferred backend ({self.preferred_backend}) failed for camera ID {self.camera_id}. Trying default backend.")
                    self.cap = cv2.VideoCapture(self.camera_id) 

                if not self.cap.isOpened():
                    backend_name_str = f" with backend {cv2.videoio_registry.getBackendName(self.preferred_backend)}" if self.preferred_backend and hasattr(cv2.videoio_registry, 'getBackendName') else ""
                    raise IOError(f"Cannot open webcam {self.camera_id}{backend_name_str} or with default backend.")

            self.is_camera_initialized = True
            self.logger.info(f"Camera Controller initialized successfully with camera ID: {self.camera_id}.")
        except Exception as e:
            self.logger.error(f"Failed to initialize camera {self.camera_id}: {e}", exc_info=True)
            self.is_camera_initialized = False
            if self.cap:
                self.cap.release()
            self.cap = None

    def _clear_camera_buffer(self):
        if not self.is_camera_initialized or not self.cap:
            self.logger.warning("Camera not initialized. Cannot clear buffer.")
            return
        try:
            for i in range(CAMERA_BUFFER_SIZE_FRAMES):
                ret, _ = self.cap.read() 
                if not ret:
                    self.logger.warning(f"Could not read frame {i+1}/{CAMERA_BUFFER_SIZE_FRAMES} while clearing buffer (stream ended or error).")
                    break
        except Exception as e:
            self.logger.error(f"Exception while clearing camera buffer: {e}", exc_info=True)

    def _check_roi_for_color(self, frame, led_config_item: dict) -> bool:
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

    def _get_current_led_state_from_camera(self) -> dict:
        if not self.is_camera_initialized or not self.cap: return {}
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None: return {}
        except Exception as e:
            self.logger.error(f"Exception while capturing frame: {e}", exc_info=True)
            return {}
        detected_led_states = {}
        for led_key, config_item in self.led_configs.items():
            detected_led_states[led_key] = 1 if self._check_roi_for_color(frame, config_item) else 0
        return detected_led_states

    def _matches_state(self, current_state: dict, target_state: dict, fail_leds: list = None) -> bool:
        if not current_state: return False
        if fail_leds:
            for led_name in fail_leds:
                if current_state.get(led_name, 0) == 1: return False 
        for led, expected_value in target_state.items():
            if current_state.get(led, 0) != expected_value: return False 
        return True 
        
    def _get_ordered_led_keys_for_display(self):
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

    def _format_led_display_string(self, target_state_dict, ordered_keys=None):
        if ordered_keys is None: ordered_keys = self._get_ordered_led_keys_for_display()
        parts = []
        for i, key in enumerate(ordered_keys):
            if key in self.led_configs: 
                parts.append(f"({i+1})" if target_state_dict.get(key, 0) == 1 else "( )")
        return " ".join(parts)

    def _handle_state_change_logging(self, current_state_dict: dict, current_time: float,
                                     last_state_info: list, reason: str = ""):
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
                self.logger.info(f"{self._format_led_display_string(state_dict)} ({duration:.0f}s{reason_suffix})")


    def confirm_led_solid(self, state: dict, minimum: float = 2, timeout: float = 10,
                          fail_leds: list = None, clear_buffer: bool = True) -> bool:
        formatted_target_state = self._format_led_display_string(state)
        # MODIFIED: "Waiting for..." message level is DEBUG (as per provided file)
        self.logger.debug(f"Waiting for LED solid {formatted_target_state}, minimum {minimum:.0f}s, timeout {timeout:.0f}s")
        if not self.is_camera_initialized: self.logger.error("Camera not initialized for confirm_led_solid."); return False
        
        last_state_info = [None, 0.0] 
        initial_capture_time = time.time()
        initial_leds_for_log = {} 

        if clear_buffer: 
            self._clear_camera_buffer()
            initial_leds_for_log = self._get_current_led_state_from_camera()
            if not initial_leds_for_log: initial_leds_for_log = {} 
            # MODIFIED: Removed immediate bare log of initial state
            # self.logger.info(f"{self._format_led_display_string(initial_leds_for_log)}") 
            last_state_info[0] = initial_leds_for_log
            last_state_info[1] = initial_capture_time 
        else: 
            initial_leds_for_log = self._get_current_led_state_from_camera()
            if not initial_leds_for_log: initial_leds_for_log = {}
            # MODIFIED: Removed immediate bare log of initial state
            # self.logger.info(f"{self._format_led_display_string(initial_leds_for_log)}")
            last_state_info[0] = initial_leds_for_log 
            last_state_info[1] = initial_capture_time

        overall_start_time = time.time()
        continuous_target_match_start_time = None

        try:
            while time.time() - overall_start_time < timeout:
                current_time = time.time()
                current_leds = self._get_current_led_state_from_camera()

                if not current_leds: 
                    self._handle_state_change_logging({}, current_time, last_state_info) 
                    continuous_target_match_start_time = None
                    time.sleep(0.1); continue
                
                self._handle_state_change_logging(current_leds, current_time, last_state_info)

                if self._matches_state(current_leds, state, fail_leds):
                    if continuous_target_match_start_time is None:
                        continuous_target_match_start_time = last_state_info[1] 
                    
                    target_held_duration = current_time - continuous_target_match_start_time
                    
                    if target_held_duration >= minimum:
                        # MODIFIED: Log confirmed state with :.2f duration
                        self.logger.info(f"{self._format_led_display_string(last_state_info[0])} ({target_held_duration:.2f}s)")
                        # MODIFIED: Summary log uses target_held_duration with :.0f
                        self.logger.info(f"LED solid confirmed: {formatted_target_state} for {target_held_duration:.0f}s")
                        return True
                else: 
                    continuous_target_match_start_time = None 
                
                time.sleep(1 / DEFAULT_FPS if DEFAULT_FPS > 0 else 0.1)
            
            self._log_final_state(last_state_info, time.time(), reason_suffix=" at timeout")
            log_method = self.logger.warning
            if continuous_target_match_start_time is not None:
                held_duration = time.time() - continuous_target_match_start_time
                log_method(f"Timeout: Target {formatted_target_state} was active for {held_duration:.0f}s, "
                           f"but did not meet full minimum {minimum:.0f}s within {timeout:.0f}s overall timeout.")
            else:
                log_method(f"Timeout: Target {formatted_target_state} not confirmed solid for {minimum:.0f}s within {timeout:.0f}s.")
            return False
        finally:
            pass


    def confirm_led_solid_strict(self, state: dict, minimum: float, clear_buffer: bool = True) -> bool:
        formatted_target_state = self._format_led_display_string(state)
        self.logger.info(f"Waiting for LED strictly solid {formatted_target_state}, duration {minimum:.0f}s")
        if not self.is_camera_initialized: self.logger.error("Camera not initialized for confirm_led_solid_strict."); return False
        
        last_state_info = [None, 0.0] 
        if clear_buffer: 
            self._clear_camera_buffer()
        else:
            prime_time_for_pre_state = time.time()
            prime_state_for_pre_state = self._get_current_led_state_from_camera()
            if prime_state_for_pre_state: 
                last_state_info[0] = prime_state_for_pre_state
                last_state_info[1] = prime_time_for_pre_state
        
        strict_overall_start_time = time.time() 
        initial_check_time = time.time()
        initial_leds = self._get_current_led_state_from_camera()
        if not initial_leds: initial_leds = {} 

        self.logger.info(f"{self._format_led_display_string(initial_leds)}")
        self._handle_state_change_logging(initial_leds, initial_check_time, last_state_info)

        if not self._matches_state(initial_leds, state, fail_leds=None):
            self.logger.warning(f"Strict confirm for {formatted_target_state} FAILED. Initial state is not target.")
            return False
        
        target_state_began_at = last_state_info[1] 

        try:
            while time.time() - target_state_began_at < minimum :
                current_time = time.time()

                if current_time - strict_overall_start_time > (minimum + 5.0): 
                    self._log_final_state(last_state_info, current_time, reason_suffix=" at strict op timeout")
                    self.logger.warning(f"Strict confirm for {formatted_target_state} FAILED due to operation timeout.")
                    return False

                current_leds = self._get_current_led_state_from_camera()

                if not current_leds: 
                    self._handle_state_change_logging({}, current_time, last_state_info) 
                    self.logger.warning(f"Strict confirm for {formatted_target_state} FAILED. Frame capture error at {current_time - strict_overall_start_time:.0f}s.")
                    return False
                
                logged_a_change = self._handle_state_change_logging(current_leds, current_time, last_state_info)

                if not self._matches_state(current_leds, state, fail_leds=None):
                    if not logged_a_change and last_state_info[0] is not None: 
                        self.logger.info(f"{self._format_led_display_string(last_state_info[0])} ({current_time - last_state_info[1]:.2f}s, broke strict sequence)")
                    
                    self.logger.warning(
                        f"Strict confirm for {formatted_target_state} FAILED. State broke sequence. "
                        f"Target was held for {last_state_info[1] - target_state_began_at:.0f}s.")
                    return False
                
                time.sleep(1 / DEFAULT_FPS if DEFAULT_FPS > 0 else 0.1)
            
            self._log_final_state(last_state_info, time.time(), reason_suffix=" on success") 
            self.logger.info(f"LED strictly solid confirmed: {formatted_target_state} for at least {minimum:.0f}s")
            return True
        finally:
            pass


    def await_led_state(self, state: dict, timeout: float = 1,
                        fail_leds: list = None, clear_buffer: bool = True) -> bool:
        formatted_target_state = self._format_led_display_string(state)
        self.logger.info(f"Awaiting LED state {formatted_target_state}, timeout {timeout:.0f}s")
        if not self.is_camera_initialized: self.logger.error("Camera not initialized for await_led_state."); return False
        
        last_state_info = [None, 0.0]
        initial_capture_time = time.time()
        initial_leds_for_log = {}

        if clear_buffer: 
            self._clear_camera_buffer()
            initial_leds_for_log = self._get_current_led_state_from_camera()
            if not initial_leds_for_log: initial_leds_for_log = {}
            self.logger.info(f"{self._format_led_display_string(initial_leds_for_log)}")
            self.logger.info(f"LED state confirmed: {self._format_led_display_string(initial_leds_for_log)}") # This line seems redundant/misplaced
            last_state_info[0] = initial_leds_for_log
            last_state_info[1] = initial_capture_time
        else:
            initial_leds_for_log = self._get_current_led_state_from_camera()
            if not initial_leds_for_log: initial_leds_for_log = {}
            self.logger.info(f"{self._format_led_display_string(initial_leds_for_log)}")
            self.logger.info(f"LED state confirmed: {self._format_led_display_string(initial_leds_for_log)}") # This line also seems redundant/misplaced
            last_state_info[0] = initial_leds_for_log
            last_state_info[1] = initial_capture_time

        await_start_time = time.time()
        try:
            while time.time() - await_start_time < timeout:
                current_time = time.time()
                current_leds = self._get_current_led_state_from_camera()

                if not current_leds:
                    self._handle_state_change_logging({}, current_time, last_state_info)
                    time.sleep(0.1); continue
                
                self._handle_state_change_logging(current_leds, current_time, last_state_info)

                if self._matches_state(current_leds, state, fail_leds):
                    # NOTE: The success path logging from the original file was:
                    # if last_state_info[0] == state:
                    #     self._log_final_state(last_state_info, current_time, reason_suffix=" when target observed")
                    # This is missing in the provided file. I am not re-adding it as per the scoped request.
                    return True
                
                time.sleep(1 / DEFAULT_FPS if DEFAULT_FPS > 0 else 0.1)

            self._log_final_state(last_state_info, time.time(), reason_suffix=" at timeout")
            self.logger.warning(f"Timeout: {formatted_target_state} not observed within {timeout:.0f}s."); 
            return False
        finally:
            pass


    def confirm_led_pattern(self, pattern: list, clear_buffer: bool = True) -> bool:
        self.logger.debug("Attempting to match LED pattern...") 
        if not pattern: self.logger.warning("Empty pattern provided."); return False
        if not self.is_camera_initialized: self.logger.error("Camera not initialized for confirm_led_pattern."); return False
        
        if clear_buffer: 
            self._clear_camera_buffer()

        ordered_keys = self._get_ordered_led_keys_for_display()
        current_step_idx = 0
        max_dur_sum = sum(p.get('duration', (0,1))[1] for p in pattern if p.get('duration',[0,0])[1] != float('inf'))
        inf_steps = sum(1 for p in pattern if p.get('duration',[0,0])[1] == float('inf'))
        overall_timeout = max_dur_sum + inf_steps * 5.0 + len(pattern) * 3.0 + 10.0 
        pattern_start_time = time.time()

        while current_step_idx < len(pattern):
            if time.time() - pattern_start_time > overall_timeout:
                self.logger.error(f"Overall pattern timeout ({overall_timeout:.2f}s) at step {current_step_idx + 1}."); return False

            step_cfg = pattern[current_step_idx]
            target_state_for_step = {k: v for k, v in step_cfg.items() if k != 'duration'}
            min_d, max_d = step_cfg.get('duration', (0, float('inf')))
            target_state_str_for_step = self._format_led_display_string(target_state_for_step, ordered_keys)
                        
            step_seen_at = None 
            step_loop_start_time = time.time() 

            while True: 
                loop_check_time = time.time()
                if loop_check_time - pattern_start_time > overall_timeout: 
                    self.logger.error(f"Timeout waiting for step {current_step_idx+1} ({target_state_str_for_step}) to appear."); return False
                
                current_leds = self._get_current_led_state_from_camera()
                if not current_leds: time.sleep(0.03); continue 
                
                if self._matches_state(current_leds, target_state_for_step):
                    step_seen_at = loop_check_time 
                    break 

                if current_step_idx == 0 and min_d == 0.0 and (loop_check_time - step_loop_start_time > 0.25): 
                    break 
                
                step_appearance_timeout_val = max(1.0, max_d / 2 if max_d != float('inf') else 5.0) 
                if loop_check_time - step_loop_start_time > step_appearance_timeout_val :
                    self.logger.warning(f"Pattern FAILED: Step {current_step_idx+1} ({target_state_str_for_step}) not seen within {step_appearance_timeout_val:.2f}s of trying for it."); return False
                time.sleep(1 / DEFAULT_FPS if DEFAULT_FPS > 0 else 0.03)

            if step_seen_at is None: 
                if current_step_idx == 0 and min_d == 0.0:
                    self.logger.info(f"{target_state_str_for_step}  0.00s ({current_step_idx + 1:02d}/{len(pattern):02d}) - Skipped")
                    current_step_idx += 1; continue
                else: 
                    self.logger.error(f"Pattern FAILED: Step {current_step_idx + 1} ({target_state_str_for_step}) internal logic error, never detected."); return False

            while True: 
                loop_check_time = time.time()
                if loop_check_time - pattern_start_time > overall_timeout:
                    self.logger.error(f"Timeout while holding pattern step {current_step_idx+1} ({target_state_str_for_step})"); return False
                
                current_leds = self._get_current_led_state_from_camera()
                if not current_leds: time.sleep(0.03); continue

                held_time = loop_check_time - step_seen_at 
                
                if self._matches_state(current_leds, target_state_for_step): 
                    if held_time > max_d:
                        self.logger.warning(f"Pattern FAILED: Step {current_step_idx+1} ({target_state_str_for_step}) held for {held_time:.2f}s > max {max_d:.2f}s."); return False
                    
                    is_last_step_of_pattern = (current_step_idx == len(pattern) - 1)
                    if is_last_step_of_pattern and held_time >= min_d: 
                        self.logger.info(f"{target_state_str_for_step}  {held_time:.2f}s+ ({current_step_idx + 1:02d}/{len(pattern):02d})")
                        current_step_idx += 1; break 
                else: 
                    if held_time >= min_d: 
                        self.logger.info(f"{target_state_str_for_step}  {held_time:.2f}s ({current_step_idx + 1:02d}/{len(pattern):02d})")
                        current_step_idx += 1; break 
                    else: 
                        self.logger.warning(f"Pattern FAILED: Step {current_step_idx+1} ({target_state_str_for_step}) changed to {self._format_led_display_string(current_leds, ordered_keys)} "
                                           f"after {held_time:.2f}s (min {min_d:.2f}s required)."); return False
                time.sleep(1 / DEFAULT_FPS if DEFAULT_FPS > 0 else 0.03)
        
        if current_step_idx == len(pattern): self.logger.info("LED pattern confirmed"); return True
        self.logger.warning(f"Pattern ended inconclusively. Processed {current_step_idx}/{len(pattern)} steps."); return False


    def await_and_confirm_led_pattern(self, pattern: list, timeout: float, clear_buffer: bool = True) -> bool:
        if not pattern: self.logger.warning("Empty pattern for await_and_confirm."); return False # Moved this check up
        if not self.is_camera_initialized: self.logger.error("Camera not init for await_and_confirm."); return False
            
        # Moved the debug log after the initial checks
        self.logger.debug(f"Awaiting first state of pattern (timeout: {timeout:.0f}s), steps: {len(pattern)}.")
        first_state_target = {k: v for k, v in pattern[0].items() if k != 'duration'}
        
        if self.await_led_state(first_state_target, timeout=timeout, clear_buffer=clear_buffer):
            return self.confirm_led_pattern(pattern, clear_buffer=False) 
        
        self.logger.warning(f"Pattern not started: First state {self._format_led_display_string(first_state_target)} not observed in {timeout:.0f}s."); return False

    def release_camera(self):
        if self.cap and self.cap.isOpened(): self.cap.release(); self.logger.info(f"Camera ID {self.camera_id} released.")
        else: self.logger.debug(f"Camera ID {self.camera_id} was not open or already released.")
        self.cap = None; self.is_camera_initialized = False

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.release_camera()