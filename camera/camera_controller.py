# Directory: camera
# Filename: camera_controller.py
#!/usr/bin/env python3

import time
import logging # Standard library logging
import cv2
import sys # Import sys to check platform
import numpy as np # Import numpy for array operations
import collections # For deque, for instant replay
import datetime # For timestamping replay files
import os # For path manipulation for replay files

# Get the logger for this module. Its name will be 'camera.camera_controller'.
# Configuration (handlers, level, format) comes from the global setup.
logger = logging.getLogger(__name__)

DEFAULT_FPS = 30
CAMERA_BUFFER_SIZE_FRAMES = 5
MIN_LOGGABLE_STATE_DURATION = 0.01 # Seconds. States held for less than this won't be logged as "held".
DEFAULT_DURATION_TOLERANCE_SEC = 0.5 # NEW: Default tolerance for duration checks

# --- Instant Replay Configuration ---
DEFAULT_REPLAY_POST_FAIL_DURATION_SEC = 5.0
DEFAULT_REPLAY_FPS_FOR_OUTPUT = DEFAULT_FPS # Use camera's default FPS for replay output
_CAMERA_CONTROLLER_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT_FROM_CAMERA = os.path.dirname(_CAMERA_CONTROLLER_FILE_DIR)
DEFAULT_REPLAY_OUTPUT_DIR = os.path.join(_PROJECT_ROOT_FROM_CAMERA, "logs", "replays")


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
    def __init__(self, camera_id: int, logger_instance=None, led_configs=None,
                 display_order: list = None, duration_tolerance_sec: float = DEFAULT_DURATION_TOLERANCE_SEC,
                 replay_post_failure_duration_sec: float = DEFAULT_REPLAY_POST_FAIL_DURATION_SEC,
                 replay_output_dir: str = DEFAULT_REPLAY_OUTPUT_DIR):
        self.logger = logger_instance if logger_instance else logger
        self.cap = None
        self.is_camera_initialized = False
        self.camera_id = camera_id
        self.preferred_backend = get_capture_backend()
        self._ordered_keys_for_display_cache = None
        self.explicit_display_order = display_order
        self.duration_tolerance_sec = duration_tolerance_sec

        # --- Instant Replay Initialization ---
        self.replay_post_failure_duration_sec = replay_post_failure_duration_sec
        self.replay_output_dir = replay_output_dir
        self.is_recording_replay = False
        self.replay_buffer = collections.deque()
        self.replay_start_time = 0.0
        self.replay_context_name = ""
        self.replay_failure_reason = ""
        self.replay_frame_width = None
        self.replay_frame_height = None
        self.replay_fps = float(DEFAULT_REPLAY_FPS_FOR_OUTPUT) # Ensure it's float

        if self.replay_output_dir:
            try:
                os.makedirs(self.replay_output_dir, exist_ok=True)
                self.logger.info(f"Instant replay output directory: {self.replay_output_dir}")
            except OSError as e:
                self.logger.error(f"Failed to create replay output directory {self.replay_output_dir}: {e}. Replays will not be saved.", exc_info=True)
                self.replay_output_dir = None # Disable replay saving if dir creation fails
        else:
            self.logger.warning("Replay output directory is not set. Replays will not be saved.")
        # --- End Instant Replay Initialization ---


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

        if not isinstance(self.led_configs, dict) or not self.led_configs:
             self.logger.critical("LED configurations are missing or invalid. Cannot initialize LogitechLedChecker.")
             raise ValueError("LED configurations are missing or invalid. "
                              "Ensure PRIMARY_LED_CONFIGURATIONS is set or valid 'led_configs' are passed.")

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
        self.logger.info(f"LogitechLedChecker initialized with duration tolerance: {self.duration_tolerance_sec:.3f}s")

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
            # Attempt to set FPS - this is often a request, camera might not obey
            if self.cap.set(cv2.CAP_PROP_FPS, DEFAULT_FPS):
                self.logger.info(f"Requested FPS {DEFAULT_FPS} for camera ID {self.camera_id}.")
            else:
                self.logger.warning(f"Could not set FPS {DEFAULT_FPS} for camera ID {self.camera_id}.")
            
            # Read current FPS from camera if possible
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            if actual_fps > 0:
                self.replay_fps = float(actual_fps) # Use actual camera FPS for replay if available
                self.logger.info(f"Camera ID {self.camera_id} actual FPS: {actual_fps:.2f}. Using this for replay timing.")
            else:
                self.logger.warning(f"Could not get actual FPS from camera ID {self.camera_id}. Using default {self.replay_fps:.2f} for replay.")

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
        # This method remains largely the same, operates on a given frame
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
        
        frame_for_processing = None
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                if self.is_recording_replay:
                    self.logger.warning("Replay: Frame capture failed during active recording.")
                return {}
            frame_for_processing = frame # Keep a reference to the captured frame

            # --- Instant Replay Frame Buffering ---
            if self.is_recording_replay and frame_for_processing is not None:
                current_capture_time = time.time()
                # Make a copy for the buffer to avoid issues if frame is modified later (though it shouldn't be here)
                self.replay_buffer.append((current_capture_time, frame_for_processing.copy())) 
                if self.replay_frame_width is None or self.replay_frame_height is None:
                    h, w = frame_for_processing.shape[:2]
                    self.replay_frame_width = w
                    self.replay_frame_height = h
                    self.logger.debug(f"Replay: Frame dimensions set to {w}x{h} at {self.replay_fps:.2f} FPS.")
            # --- End Instant Replay Frame Buffering ---

        except Exception as e:
            self.logger.error(f"Exception while capturing frame: {e}", exc_info=True)
            return {}
        
        detected_led_states = {}
        if frame_for_processing is not None:
            for led_key, config_item in self.led_configs.items():
                detected_led_states[led_key] = 1 if self._check_roi_for_color(frame_for_processing, config_item) else 0
        return detected_led_states

    def _start_replay_recording(self, context_name: str):
        if not self.replay_output_dir:
            self.logger.debug(f"Replay recording not started for '{context_name}': output directory not available or configured.")
            return
        if self.is_recording_replay: # Avoid nested recordings by the same instance.
            self.logger.debug(f"Replay: Recording already active for context '{self.replay_context_name}'. Ignoring start for '{context_name}'.")
            return

        self.logger.debug(f"Replay: Starting recording for context '{context_name}'.")
        self.is_recording_replay = True
        self.replay_buffer.clear()
        self.replay_start_time = time.time()
        self.replay_context_name = context_name
        self.replay_failure_reason = "" 
        self.replay_frame_width = None # Reset, will be set by the first frame
        self.replay_frame_height = None

    def _save_replay_video(self):
        if not self.is_recording_replay or not self.replay_buffer or not self.replay_output_dir:
            if not self.replay_buffer and self.is_recording_replay : self.logger.debug("Replay: No frames in buffer to save.")
            # Ensure recording flag is reset if we bail early for other reasons
            # self.is_recording_replay = False # Moved to _stop_replay_recording
            return

        if self.replay_frame_width is None or self.replay_frame_height is None:
            self.logger.error("Replay: Frame dimensions not set. Cannot save video.")
            # self.is_recording_replay = False
            # self.replay_buffer.clear()
            return

        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3] # Milliseconds
        # Sanitize context and reason for filename
        sane_context = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in self.replay_context_name)
        sane_reason = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in self.replay_failure_reason)
        filename_base = f"replay_{sane_context}_{sane_reason}_{timestamp_str}.mp4"
        filepath = os.path.join(self.replay_output_dir, filename_base)

        self.logger.info(f"Replay: Saving video to {filepath} ({len(self.replay_buffer)} base frames + post-failure frames).")

        fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
        
        video_writer = None
        try:
            video_writer = cv2.VideoWriter(filepath, fourcc, self.replay_fps,
                                           (self.replay_frame_width, self.replay_frame_height))
            if not video_writer.isOpened():
                self.logger.error(f"Replay: Failed to open VideoWriter for {filepath}.")
                return

            for _, frame_data in self.replay_buffer:
                # Ensure frame matches dimensions before writing
                fh, fw = frame_data.shape[:2]
                if fw == self.replay_frame_width and fh == self.replay_frame_height:
                    video_writer.write(frame_data)
                else:
                    # If dimensions mismatch, try to resize (though this indicates an issue)
                    self.logger.warning(f"Replay: Frame dim mismatch ({fw}x{fh} vs {self.replay_frame_width}x{self.replay_frame_height}). Resizing frame for {filepath}.")
                    resized_frame = cv2.resize(frame_data, (self.replay_frame_width, self.replay_frame_height))
                    video_writer.write(resized_frame)
            
            self.logger.info(f"Replay: Successfully wrote frames to {filepath}.")

        except Exception as e:
            self.logger.error(f"Replay: Error during video writing for {filepath}: {e}", exc_info=True)
        finally:
            if video_writer:
                video_writer.release()
            # Buffer clearing and flag reset is handled by _stop_replay_recording

    def _stop_replay_recording(self, success: bool, failure_reason: str = "unspecified_failure"):
        if not self.is_recording_replay:
            return

        self.replay_failure_reason = failure_reason.replace(" ", "_").replace(":", "").lower()

        if not success and self.replay_buffer and self.replay_output_dir:
            self.logger.debug(f"Replay: Failure detected (Reason: {self.replay_failure_reason}). Recording post-failure duration of {self.replay_post_failure_duration_sec}s.")
            
            post_failure_start_time = time.time()
            frames_after_failure = 0
            
            if self.replay_frame_width is None or self.replay_frame_height is None:
                self.logger.error("Replay: Frame dimensions not set prior to post-failure recording. Cannot continue.")
                self.is_recording_replay = False 
                self.replay_buffer.clear()
                return

            while time.time() - post_failure_start_time < self.replay_post_failure_duration_sec:
                if not self.cap or not self.cap.isOpened():
                    self.logger.warning("Replay: Camera not available for post-failure recording.")
                    break
                
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    current_h, current_w = frame.shape[:2]
                    if current_w == self.replay_frame_width and current_h == self.replay_frame_height:
                        self.replay_buffer.append((time.time(), frame.copy()))
                        frames_after_failure += 1
                    else:
                        self.logger.warning(f"Replay: Frame size changed during post-failure recording. Expected {self.replay_frame_width}x{self.replay_frame_height}, got {current_w}x{current_h}. Frame skipped.")
                else:
                    self.logger.warning("Replay: Failed to capture frame during post-failure recording.")
                
                time.sleep(1.0 / self.replay_fps if self.replay_fps > 0 else 0.01)

            self.logger.debug(f"Replay: Captured {frames_after_failure} additional frames post-failure.")
            self._save_replay_video() 
        
        elif success:
             self.logger.debug(f"Replay: Success for context '{self.replay_context_name}'. Clearing buffer without saving video.")
        
        # Always clean up
        self.replay_buffer.clear()
        self.is_recording_replay = False
        self.replay_context_name = ""
        self.replay_failure_reason = ""
        # Keep replay_frame_width/height as they might be useful if another recording starts soon with same camera settings.
        # Or reset them: self.replay_frame_width = None; self.replay_frame_height = None;

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
                self.logger.info(f"{self._format_led_display_string(state_dict)} ({duration:.2f}s{reason_suffix})")

    def confirm_led_solid(self, state: dict, minimum: float = 2, timeout: float = 10,
                          fail_leds: list = None, clear_buffer: bool = True, manage_replay: bool = True) -> bool:
        context_name = "confirm_led_solid"
        if manage_replay: self._start_replay_recording(context_name)
        
        success_flag = False
        failure_detail = "unknown_failure"
        
        formatted_target_state = self._format_led_display_string(state)
        self.logger.debug(f"Waiting for LED solid {formatted_target_state}, minimum {minimum:.2f}s (tol: {self.duration_tolerance_sec:.2f}s), timeout {timeout:.2f}s")
        if not self.is_camera_initialized: 
            self.logger.error("Camera not initialized for confirm_led_solid.")
            failure_detail = "camera_not_initialized"
            if manage_replay: self._stop_replay_recording(success=False, failure_reason=failure_detail)
            return False
        
        last_state_info = [None, 0.0] 
        initial_capture_time = time.time()
        initial_leds_for_log = {} 

        if clear_buffer: 
            self._clear_camera_buffer()
        # Always get an initial state for logging and continuity, even if not clearing hardware buffer
        initial_leds_for_log = self._get_current_led_state_from_camera()
        if not initial_leds_for_log: initial_leds_for_log = {} 
        last_state_info[0] = initial_leds_for_log
        last_state_info[1] = initial_capture_time 

        overall_start_time = time.time()
        continuous_target_match_start_time = None
        effective_minimum = max(0, minimum - self.duration_tolerance_sec)

        try:
            while time.time() - overall_start_time < timeout:
                current_time = time.time()
                current_leds = self._get_current_led_state_from_camera() # This now buffers for replay

                if not current_leds: 
                    self._handle_state_change_logging({}, current_time, last_state_info) 
                    continuous_target_match_start_time = None
                    time.sleep(0.1); continue
                
                self._handle_state_change_logging(current_leds, current_time, last_state_info)

                if self._matches_state(current_leds, state, fail_leds):
                    if continuous_target_match_start_time is None:
                        continuous_target_match_start_time = last_state_info[1] 
                    
                    target_held_duration = current_time - continuous_target_match_start_time
                    
                    if target_held_duration >= effective_minimum:
                        self.logger.info(f"{self._format_led_display_string(last_state_info[0])} ({target_held_duration:.2f}s)")
                        self.logger.info(f"LED solid confirmed: {formatted_target_state} for {target_held_duration:.2f}s (required ~{effective_minimum:.2f}s)")
                        success_flag = True
                        return True # Goes to finally
                else: 
                    continuous_target_match_start_time = None 
                
                time.sleep(1 / self.replay_fps if self.replay_fps > 0 else 0.1) # Use replay_fps for sleep consistency
            
            # Timeout occurred
            self._log_final_state(last_state_info, time.time(), reason_suffix=" at timeout")
            log_method = self.logger.warning
            if continuous_target_match_start_time is not None:
                held_duration = time.time() - continuous_target_match_start_time
                failure_detail = f"timeout_target_active_for_{held_duration:.2f}s_needed_{effective_minimum:.2f}s"
                log_method(f"Timeout: Target {formatted_target_state} was active for {held_duration:.2f}s, "
                           f"but did not meet full minimum {effective_minimum:.2f}s (original min: {minimum:.2f}s) within {timeout:.2f}s overall timeout.")
            else:
                failure_detail = f"timeout_target_not_solid_for_{effective_minimum:.2f}s"
                log_method(f"Timeout: Target {formatted_target_state} not confirmed solid for {effective_minimum:.2f}s (original min: {minimum:.2f}s) within {timeout:.2f}s.")
            success_flag = False
            return False # Goes to finally
        finally:
            if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)


    def confirm_led_solid_strict(self, state: dict, minimum: float, clear_buffer: bool = True, manage_replay: bool = True) -> bool:
        context_name = "confirm_led_solid_strict"
        if manage_replay: self._start_replay_recording(context_name)
        
        success_flag = False
        failure_detail = "unknown_failure"

        formatted_target_state = self._format_led_display_string(state)
        effective_minimum = max(0.0, minimum - self.duration_tolerance_sec)
        self.logger.info(f"Waiting for LED strictly solid {formatted_target_state}, effective duration {effective_minimum:.2f}s (original min: {minimum:.2f}s, tol: {self.duration_tolerance_sec:.2f}s)")
        
        if not self.is_camera_initialized:
            self.logger.error("Camera not initialized for confirm_led_solid_strict.")
            failure_detail = "camera_not_initialized"
            if manage_replay: self._stop_replay_recording(success=False, failure_reason=failure_detail)
            return False # Early exit, finally will still run if it were structured differently
        
        last_state_info = [None, 0.0] 
        if clear_buffer: 
            self._clear_camera_buffer()
        
        # Always get an initial state
        prime_time_for_pre_state = time.time()
        prime_state_for_pre_state = self._get_current_led_state_from_camera()
        if prime_state_for_pre_state: 
            last_state_info[0] = prime_state_for_pre_state
            last_state_info[1] = prime_time_for_pre_state
        
        strict_overall_start_time = time.time() 
        # initial_check_time = time.time() # Redundant if prime_time_for_pre_state is used for last_state_info[1]
        initial_leds = last_state_info[0] if last_state_info[0] is not None else {}

        self.logger.info(f"{self._format_led_display_string(initial_leds)}")
        # _handle_state_change_logging is implicitly called by _get_current_led_state_from_camera setting up last_state_info

        if not self._matches_state(initial_leds, state, fail_leds=None): # fail_leds=None for strict state match
            failure_detail = "initial_state_not_target"
            self.logger.warning(f"Strict confirm for {formatted_target_state} FAILED. Initial state is not target.")
            success_flag = False
            # No direct return here; let success_flag be false and fall through to finally
        else: # Initial state matches
            target_state_began_at = last_state_info[1] 
            try: # This try block is for the main logic after initial state matches
                while time.time() - target_state_began_at < effective_minimum :
                    current_time = time.time()

                    if current_time - strict_overall_start_time > (effective_minimum + 5.0): # Operation timeout
                        self._log_final_state(last_state_info, current_time, reason_suffix=" at strict op timeout")
                        failure_detail = f"operation_timeout_aiming_for_{effective_minimum:.2f}s"
                        self.logger.warning(f"Strict confirm for {formatted_target_state} FAILED due to operation timeout (aiming for {effective_minimum:.2f}s).")
                        success_flag = False
                        # This return False will be caught by the outer finally
                        if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)
                        return False 

                    current_leds = self._get_current_led_state_from_camera()

                    if not current_leds: 
                        self._handle_state_change_logging({}, current_time, last_state_info) 
                        failure_detail = "frame_capture_error"
                        self.logger.warning(f"Strict confirm for {formatted_target_state} FAILED. Frame capture error at {current_time - strict_overall_start_time:.2f}s.")
                        success_flag = False
                        if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)
                        return False 
                    
                    logged_a_change = self._handle_state_change_logging(current_leds, current_time, last_state_info)

                    if not self._matches_state(current_leds, state, fail_leds=None):
                        if not logged_a_change and last_state_info[0] is not None: 
                            self.logger.info(f"{self._format_led_display_string(last_state_info[0])} ({current_time - last_state_info[1]:.2f}s, broke strict sequence)")
                        
                        actual_held_duration_before_break = current_time - target_state_began_at # More accurate held time before break
                        # If logged_a_change is true, last_state_info[1] would be the time of the break.
                        # If logged_a_change is false, it means it broke from the target state, so current_time is the break time.
                        # The duration calculation here needs to be careful about what last_state_info[1] represents.
                        # Let's use current_time - target_state_began_at for how long it was "good"
                        
                        failure_detail = f"state_broke_sequence_held_{actual_held_duration_before_break:.2f}s_needed_{effective_minimum:.2f}s"
                        self.logger.warning(
                            f"Strict confirm for {formatted_target_state} FAILED. State broke sequence. "
                            f"Target was held for {actual_held_duration_before_break:.2f}s. Needed to hold for {effective_minimum:.2f}s without break.")
                        success_flag = False
                        if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)
                        return False 
                    
                    time.sleep(1 / self.replay_fps if self.replay_fps > 0 else 0.1)
                
                # If loop completes, minimum duration met
                self._log_final_state(last_state_info, time.time(), reason_suffix=" on success") 
                self.logger.info(f"LED strictly solid confirmed: {formatted_target_state} for at least {effective_minimum:.2f}s (original min: {minimum:.2f}s, tol: {self.duration_tolerance_sec:.2f}s)")
                success_flag = True
                # No return here, success_flag is set, fall through to finally
            except Exception as e_strict: # Catch unexpected errors within the try
                failure_detail = f"exception_in_loop_{type(e_strict).__name__}"
                self.logger.error(f"Exception in strict confirm loop: {e_strict}", exc_info=True)
                success_flag = False
                # No direct return here, fall through to finally

        # This is the final decision point before replay is stopped.
        if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)
        return success_flag


    def await_led_state(self, state: dict, timeout: float = 1,
                        fail_leds: list = None, clear_buffer: bool = True, manage_replay: bool = True) -> bool:
        context_name = "await_led_state"
        if manage_replay: self._start_replay_recording(context_name)

        success_flag = False
        failure_detail = "unknown_failure"

        formatted_target_state = self._format_led_display_string(state)
        self.logger.info(f"Awaiting LED state {formatted_target_state}, timeout {timeout:.2f}s")
        if not self.is_camera_initialized:
            self.logger.error("Camera not initialized for await_led_state.")
            failure_detail = "camera_not_initialized"
            if manage_replay: self._stop_replay_recording(success=False, failure_reason=failure_detail)
            return False
        
        last_state_info = [None, 0.0]
        # initial_capture_time = time.time() # Used if not clearing buffer or as base time

        if clear_buffer: 
            self._clear_camera_buffer()
        
        # Always get an initial state for logging
        initial_leds_for_log = self._get_current_led_state_from_camera()
        if not initial_leds_for_log: initial_leds_for_log = {}
        self.logger.info(f"{self._format_led_display_string(initial_leds_for_log)}")
        last_state_info[0] = initial_leds_for_log
        last_state_info[1] = time.time() # Use current time after getting initial state

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
                    if last_state_info[0] == current_leds and (current_time - last_state_info[1] >= MIN_LOGGABLE_STATE_DURATION): 
                         self.logger.info(f"{self._format_led_display_string(last_state_info[0])} ({current_time - last_state_info[1]:.2f}s when target observed)")
                    elif last_state_info[0] != current_leds: 
                         self.logger.info(f"{self._format_led_display_string(current_leds)} (0.00s+ when target observed)")

                    self.logger.info(f"Target state {formatted_target_state} observed.")
                    success_flag = True
                    return True # Goes to finally
                
                time.sleep(1 / self.replay_fps if self.replay_fps > 0 else 0.1)

            # Timeout occurred
            self._log_final_state(last_state_info, time.time(), reason_suffix=" at timeout")
            failure_detail = f"timeout_target_{formatted_target_state.replace(' ','_')}_not_observed"
            self.logger.warning(f"Timeout: {formatted_target_state} not observed within {timeout:.2f}s.")
            success_flag = False
            return False # Goes to finally
        finally:
            if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)


    def confirm_led_pattern(self, pattern: list, clear_buffer: bool = True, manage_replay: bool = True) -> bool:
        context_name = "confirm_led_pattern"
        if manage_replay: self._start_replay_recording(context_name)

        success_flag = False
        failure_detail = "unknown_failure_or_empty_pattern" 

        self.logger.debug(f"Attempting to match LED pattern (tol: {self.duration_tolerance_sec:.2f}s)...")
        if not pattern: 
            self.logger.warning("Empty pattern provided.")
            failure_detail = "empty_pattern"
            if manage_replay: self._stop_replay_recording(success=False, failure_reason=failure_detail)
            return False
        if not self.is_camera_initialized:
            self.logger.error("Camera not initialized for confirm_led_pattern.")
            failure_detail = "camera_not_initialized"
            if manage_replay: self._stop_replay_recording(success=False, failure_reason=failure_detail)
            return False
        
        if clear_buffer: 
            self._clear_camera_buffer()
            # Get an initial state reading after clearing buffer for logging context if needed
            self._get_current_led_state_from_camera() # This will also buffer a frame if replay is on


        ordered_keys = self._get_ordered_led_keys_for_display()
        current_step_idx = 0
        # Calculate a generous overall timeout for the entire pattern
        max_dur_sum = sum(p.get('duration', (0,1))[1] for p in pattern if p.get('duration',[0,0])[1] != float('inf'))
        inf_steps = sum(1 for p in pattern if p.get('duration',[0,0])[1] == float('inf'))
        # Add buffer for transitions, processing, and potential inf_steps
        overall_timeout = max_dur_sum + inf_steps * 10.0 + len(pattern) * 5.0 + 15.0 
        pattern_start_time = time.time()

        try:
            while current_step_idx < len(pattern):
                if time.time() - pattern_start_time > overall_timeout:
                    failure_detail = f"overall_pattern_timeout_at_step_{current_step_idx + 1}"
                    self.logger.error(f"Overall pattern timeout ({overall_timeout:.2f}s) at step {current_step_idx + 1}. Failure detail: {failure_detail}")
                    success_flag = False; return False # Goes to finally

                step_cfg = pattern[current_step_idx]
                target_state_for_step = {k: v for k, v in step_cfg.items() if k != 'duration'}
                min_d_orig, max_d_orig = step_cfg.get('duration', (0, float('inf')))
                
                min_d_check = max(0.0, min_d_orig - self.duration_tolerance_sec)
                max_d_check = max_d_orig + self.duration_tolerance_sec
                if max_d_orig == float('inf'): # Ensure inf remains inf
                    max_d_check = float('inf')

                target_state_str_for_step = self._format_led_display_string(target_state_for_step, ordered_keys)
                            
                step_seen_at = None 
                step_loop_start_time = time.time() 

                # Loop to see the target state for the current step
                while True: 
                    loop_check_time = time.time()
                    if loop_check_time - pattern_start_time > overall_timeout: 
                        failure_detail = f"timeout_waiting_for_step_{current_step_idx + 1}_to_appear"
                        self.logger.error(f"Timeout waiting for step {current_step_idx+1} ({target_state_str_for_step}) to appear. Failure detail: {failure_detail}")
                        success_flag = False; return False 

                    current_leds = self._get_current_led_state_from_camera()
                    if not current_leds: time.sleep(0.03); continue 
                    
                    if self._matches_state(current_leds, target_state_for_step):
                        step_seen_at = loop_check_time 
                        break # Seen the target state, now check duration

                    # Special handling for first step if its min duration is 0 (can be skipped if not immediately present)
                    if current_step_idx == 0 and min_d_orig == 0.0 and (loop_check_time - step_loop_start_time > 0.25): 
                        # If first step is 0-duration and not seen quickly, assume it's "skipped"
                        break # Will proceed to step_seen_at is None check
                    
                    # Timeout for *this specific step* to appear. More aggressive than overall_timeout.
                    # Based on max_d_orig or a fixed value for inf duration steps
                    step_appearance_timeout_val = max(1.0, max_d_orig / 2 if max_d_orig != float('inf') else 5.0) + 2.0 # Add buffer
                    if loop_check_time - step_loop_start_time > step_appearance_timeout_val :
                        failure_detail = f"step_{current_step_idx + 1}_state_{target_state_str_for_step.replace(' ','_')}_not_seen_within_{step_appearance_timeout_val:.2f}s"
                        self.logger.warning(f"Pattern FAILED: Step {current_step_idx+1} ({target_state_str_for_step}) not seen within {step_appearance_timeout_val:.2f}s of trying for it. Failure detail: {failure_detail}")
                        success_flag = False; return False
                    time.sleep(1 / self.replay_fps if self.replay_fps > 0 else 0.03)

                if step_seen_at is None: # Only true if first step, min_d_orig == 0, and it wasn't seen quickly
                    if current_step_idx == 0 and min_d_orig == 0.0: 
                        self.logger.info(f"{target_state_str_for_step}  0.00s ({current_step_idx + 1:02d}/{len(pattern):02d}) - Skipped (original min_d was 0)")
                        current_step_idx += 1; continue # Successfully "matched" a zero-duration step by skipping
                    else: # Should not happen if logic above is correct
                        failure_detail = f"step_{current_step_idx + 1}_state_{target_state_str_for_step.replace(' ','_')}_never_detected_internal_logic"
                        self.logger.error(f"Pattern FAILED: Step {current_step_idx + 1} ({target_state_str_for_step}) internal logic error, never detected. Failure detail: {failure_detail}");
                        success_flag = False; return False

                # Loop to hold the target state for the required duration
                while True: 
                    loop_check_time = time.time()
                    if loop_check_time - pattern_start_time > overall_timeout:
                        failure_detail = f"timeout_holding_step_{current_step_idx + 1}_state_{target_state_str_for_step.replace(' ','_')}"
                        self.logger.error(f"Timeout while holding pattern step {current_step_idx+1} ({target_state_str_for_step}). Failure detail: {failure_detail}");
                        success_flag = False; return False
                    
                    current_leds = self._get_current_led_state_from_camera()
                    if not current_leds: time.sleep(0.03); continue

                    held_time = loop_check_time - step_seen_at 
                    
                    if self._matches_state(current_leds, target_state_for_step): # Still in target state
                        if max_d_check != float('inf') and held_time > max_d_check:
                            failure_detail = f"step_{current_step_idx + 1}_state_{target_state_str_for_step.replace(' ','_')}_held_too_long_{held_time:.2f}s_max_{max_d_check:.2f}s"
                            self.logger.warning(f"Pattern FAILED: Step {current_step_idx+1} ({target_state_str_for_step}) held for {held_time:.2f}s > max_check {max_d_check:.2f}s (orig_max: {max_d_orig:.2f}s). Failure detail: {failure_detail}");
                            success_flag = False; return False
                        
                        is_last_step_of_pattern = (current_step_idx == len(pattern) - 1)
                        if is_last_step_of_pattern and held_time >= min_d_check: 
                            self.logger.info(f"{target_state_str_for_step}  {held_time:.2f}s+ ({current_step_idx + 1:02d}/{len(pattern):02d})")
                            current_step_idx += 1; break # Matched last step
                        # If not last step, just continue holding and checking time, or wait for state change
                    else: # State changed from target
                        if held_time >= min_d_check: 
                            self.logger.info(f"{target_state_str_for_step}  {held_time:.2f}s ({current_step_idx + 1:02d}/{len(pattern):02d})")
                            current_step_idx += 1; break # Matched current step, state changed appropriately for next step
                        else: # State changed too early
                            current_led_str = self._format_led_display_string(current_leds, ordered_keys)
                            failure_detail = f"step_{current_step_idx + 1}_state_{target_state_str_for_step.replace(' ','_')}_changed_to_{current_led_str.replace(' ','_')}_early_held_{held_time:.2f}s_min_{min_d_check:.2f}s"
                            self.logger.warning(f"Pattern FAILED: Step {current_step_idx+1} ({target_state_str_for_step}) changed to {current_led_str} "
                                               f"after {held_time:.2f}s (min_check {min_d_check:.2f}s required, orig_min: {min_d_orig:.2f}s). Failure detail: {failure_detail}");
                            success_flag = False; return False
                    time.sleep(1 / self.replay_fps if self.replay_fps > 0 else 0.03)
            
            if current_step_idx == len(pattern):
                self.logger.info("LED pattern confirmed")
                success_flag = True
                return True # Goes to finally
            
            # Fallback if loop finishes unexpectedly
            failure_detail = f"ended_inconclusively_processed_{current_step_idx}_of_{len(pattern)}"
            self.logger.warning(f"Pattern ended inconclusively. Processed {current_step_idx}/{len(pattern)} steps. Failure detail: {failure_detail}")
            success_flag = False
            return False # Goes to finally
        finally:
            if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)


    def await_and_confirm_led_pattern(self, pattern: list, timeout: float, clear_buffer: bool = True, manage_replay: bool = True) -> bool:
        context_name = "await_and_confirm_led_pattern"
        if manage_replay: self._start_replay_recording(context_name)

        success_flag = False
        failure_detail = "unknown_failure_or_empty_pattern"

        if not pattern: 
            self.logger.warning("Empty pattern for await_and_confirm.")
            failure_detail = "empty_pattern"
            if manage_replay: self._stop_replay_recording(success=False, failure_reason=failure_detail)
            return False
        if not self.is_camera_initialized:
            self.logger.error("Camera not init for await_and_confirm.")
            failure_detail = "camera_not_initialized"
            if manage_replay: self._stop_replay_recording(success=False, failure_reason=failure_detail)
            return False
            
        self.logger.debug(f"Awaiting first state of pattern (timeout: {timeout:.2f}s), steps: {len(pattern)}.")
        first_state_target = {k: v for k, v in pattern[0].items() if k != 'duration'}
        
        try:
            # Call await_led_state with manage_replay=False as this is an inner call
            # Replay for await_led_state is managed by this parent function's replay session
            if self.await_led_state(first_state_target, timeout=timeout, clear_buffer=clear_buffer, manage_replay=False):
                # If first state seen, now try to confirm the whole pattern starting from there
                # Call confirm_led_pattern with manage_replay=False
                pattern_confirmed = self.confirm_led_pattern(pattern, clear_buffer=False, manage_replay=False)
                success_flag = pattern_confirmed # Set based on the pattern confirmation
                if not pattern_confirmed:
                    # confirm_led_pattern itself will log specific reasons. This is the higher-level failure.
                    failure_detail = "pattern_confirmation_failed_after_await" 
                # If pattern_confirmed is true, success_flag is true, failure_detail might not be used by _stop_replay if success
                return pattern_confirmed # Goes to finally
            else: # await_led_state failed to find the first state
                formatted_first_state = self._format_led_display_string(first_state_target).replace(' ','_')
                failure_detail = f"first_state_{formatted_first_state}_not_observed_in_{timeout:.2f}s"
                self.logger.warning(f"Pattern not started: First state {self._format_led_display_string(first_state_target)} not observed in {timeout:.2f}s. Failure detail: {failure_detail}")
                success_flag = False
                return False # Goes to finally
        finally:
            if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)

    def release_camera(self):
        if self.is_recording_replay:
            self.logger.info("Replay: Active recording stopped due to camera release. Discarding buffered frames.")
            self.replay_buffer.clear() # Clear buffer
            self.is_recording_replay = False # Ensure flag is reset

        if self.cap and self.cap.isOpened(): self.cap.release(); self.logger.info(f"Camera ID {self.camera_id} released.")
        else: self.logger.debug(f"Camera ID {self.camera_id} was not open or already released.")
        self.cap = None; self.is_camera_initialized = False

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.release_camera()