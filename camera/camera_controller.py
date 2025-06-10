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
from typing import Dict, Optional, List, Tuple, Any # For type hinting


# Get the logger for this module. Its name will be 'camera.camera_controller'.
# Configuration (handlers, level, format) comes from the global setup.
logger = logging.getLogger(__name__)

DEFAULT_FPS = 15
CAMERA_BUFFER_SIZE_FRAMES = 5
MIN_LOGGABLE_STATE_DURATION = 0.01 # Seconds. States held for less than this won't be logged as "held".
DEFAULT_DURATION_TOLERANCE_SEC = 0.1 # NEW: Default tolerance for duration checks

# --- Instant Replay Configuration ---
GLOBAL_ENABLE_INSTANT_REPLAY_FEATURE = True
DEFAULT_REPLAY_POST_FAIL_DURATION_SEC = 5.0
DEFAULT_REPLAY_FPS_FOR_OUTPUT = DEFAULT_FPS # Use camera's default FPS for replay output
_CAMERA_CONTROLLER_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT_FROM_CAMERA = os.path.dirname(_CAMERA_CONTROLLER_FILE_DIR)

# --- Overlay Drawing Constants ---
OVERLAY_FONT = cv2.FONT_HERSHEY_SIMPLEX
OVERLAY_FONT_SCALE = 0.5
OVERLAY_FONT_THICKNESS = 1
OVERLAY_TEXT_COLOR_MAIN = (255, 255, 255)  # White
OVERLAY_LINE_HEIGHT = 18 # Used as a spacer for positioning indicators
OVERLAY_PADDING = 5

# --- Constants for drawing LED status indicators on the replay video ---
OVERLAY_LED_INDICATOR_RADIUS = 7
# Fallback 'ON' color for configs missing a 'display_color_bgr' key.
OVERLAY_LED_INDICATOR_ON_COLOR_FALLBACK = (0, 255, 0) # Bright Green
OVERLAY_LED_INDICATOR_OFF_COLOR = (80, 80, 80) # Dark Grey for OFF


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
        "min_match_percentage": 0.15,
        "display_color_bgr": (0,255,0)
    },
    "blue":  {
        "name": "Blue LED",
        "roi": (417, 165, 40, 40),
        "hsv_lower": (75,    0, 100),
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
        "display_color_bgr": (128, 128, 128)
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
    return None # Let OpenCV choose default


class LogitechLedChecker:
    def __init__(self, camera_id: int, logger_instance=None, led_configs=None,
                 display_order: Optional[List[str]] = None, duration_tolerance_sec: float = DEFAULT_DURATION_TOLERANCE_SEC,
                 replay_post_failure_duration_sec: float = DEFAULT_REPLAY_POST_FAIL_DURATION_SEC,
                 replay_output_dir: Optional[str] = None,
                 enable_instant_replay: Optional[bool] = None):
        self.logger = logger_instance if logger_instance else logger
        self.cap = None
        self.is_camera_initialized = False
        self.camera_id = camera_id
        self.preferred_backend = get_capture_backend()
        self._ordered_keys_for_display_cache = None
        self.explicit_display_order = display_order
        self.duration_tolerance_sec = duration_tolerance_sec

        # --- Instant Replay Initialization ---
        if enable_instant_replay is not None:
            self.enable_instant_replay = enable_instant_replay
        else:
            self.enable_instant_replay = GLOBAL_ENABLE_INSTANT_REPLAY_FEATURE
        self.replay_post_failure_duration_sec = replay_post_failure_duration_sec
        self.replay_output_dir = replay_output_dir
        self.is_recording_replay = False
        self.replay_buffer = collections.deque()
        self.replay_start_time = 0.0
        self.replay_method_name = ""
        self.replay_extra_context: Optional[Dict[str, str]] = None
        self.replay_failure_reason = ""
        self.replay_frame_width = None
        self.replay_frame_height = None
        self.replay_fps = float(DEFAULT_REPLAY_FPS_FOR_OUTPUT) 

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
        if led_configs is not None:
            self.led_configs = led_configs
        elif PRIMARY_LED_CONFIGURATIONS:
            self.led_configs = PRIMARY_LED_CONFIGURATIONS
        else:
            self.led_configs = _FALLBACK_LED_DEFINITIONS
            self.logger.error("PRIMARY_LED_CONFIGURATIONS empty/invalid. Using _FALLBACK_LED_DEFINITIONS.")

        if not isinstance(self.led_configs, dict) or not self.led_configs:
             raise ValueError("LED configurations are missing or invalid.")

        if self.explicit_display_order:
            for key in self.explicit_display_order:
                if key not in self.led_configs:
                    raise ValueError(f"Key '{key}' in display_order not found in LED configs.")

        core_keys = ["name", "roi", "hsv_lower", "hsv_upper", "min_match_percentage"]
        for key, config_item in self.led_configs.items():
            if not isinstance(config_item, dict): raise ValueError(f"LED config item '{key}' not a dict.")
            if any(k not in config_item for k in core_keys):
                raise ValueError(f"LED config '{key}' missing core keys.")
            if not (isinstance(config_item["roi"], tuple) and len(config_item["roi"]) == 4 and
                    all(isinstance(n, int) for n in config_item["roi"])):
                raise ValueError(f"ROI for LED '{key}' must be tuple of 4 ints.")

        if self.camera_id is None: self.logger.error("Camera ID cannot be None."); return 
        self._initialize_camera()

    # ... (No changes to _initialize_camera, _clear_camera_buffer, _check_roi_for_color) ...
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
        Captures ONE frame and checks all configured LEDs against it. This guarantees
        an atomic snapshot of the LED states at a single point in time.

        It no longer accepts an 'input_frame' argument.

        Returns:
            A tuple containing:
            - The frame (np.ndarray) that was analyzed, or None on failure.
            - A dictionary (dict) of the detected LED states.
        """
        if not self.is_camera_initialized or not self.cap:
            return None, {}

        frame_for_processing = None
        detected_led_states = {}
        
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                self.logger.warning("Frame capture failed.")
                return None, {}
            frame_for_processing = frame
        except Exception as e:
            self.logger.error(f"Exception while capturing frame: {e}", exc_info=True)
            return None, {}

        # Now, check all LEDs against the single frame we just captured.
        for led_key, config_item in self.led_configs.items():
            detected_led_states[led_key] = 1 if self._check_roi_for_color(frame_for_processing, config_item) else 0

        # If replay is active, store this atomic result.
        if self.is_recording_replay:
            current_capture_time = time.time()
            self.replay_buffer.append((current_capture_time, frame_for_processing.copy(), detected_led_states.copy()))
            if self.replay_frame_width is None or self.replay_frame_height is None:
                h, w = frame_for_processing.shape[:2]
                self.replay_frame_width, self.replay_frame_height = w, h

        return frame_for_processing, detected_led_states

    def _draw_overlays(self, frame: np.ndarray, timestamp_in_replay: float, led_state_for_frame: Dict[str, int]) -> np.ndarray:
        overlay_frame = frame.copy()
        current_y_offset = OVERLAY_PADDING

        # --- MODIFICATION: Draw FSM context if available ---
        if self.replay_extra_context:
            fsm_curr = self.replay_extra_context.get('fsm_current_state', 'N/A')
            fsm_dest = self.replay_extra_context.get('fsm_destination_state', 'N/A')
            
            # Draw Current State text on the video frame
            cv2.putText(overlay_frame, f"Current State: {fsm_curr}", 
                        (OVERLAY_PADDING, current_y_offset + OVERLAY_LINE_HEIGHT),
                        OVERLAY_FONT, OVERLAY_FONT_SCALE, OVERLAY_TEXT_COLOR_MAIN, OVERLAY_FONT_THICKNESS, cv2.LINE_AA)
            current_y_offset += OVERLAY_LINE_HEIGHT

            # Draw Destination State text on the video frame
            cv2.putText(overlay_frame, f"Destination State: {fsm_dest}",
                        (OVERLAY_PADDING, current_y_offset + OVERLAY_LINE_HEIGHT),
                        OVERLAY_FONT, OVERLAY_FONT_SCALE, OVERLAY_TEXT_COLOR_MAIN, OVERLAY_FONT_THICKNESS, cv2.LINE_AA)
            # Add extra padding to separate this block from other potential overlays
            current_y_offset += (OVERLAY_LINE_HEIGHT * 2)

        # Iterate through all configured LEDs to draw their ROI and status indicator
        ordered_leds = self._get_ordered_led_keys_for_display()
        for led_key in ordered_leds:
            if led_key not in self.led_configs:
                continue

            config_item = self.led_configs[led_key]
            x, y, w, h = config_item["roi"]

            # 1. Draw the ROI box for context
            roi_box_color = config_item.get("display_color_bgr", (128, 128, 128))
            cv2.rectangle(overlay_frame, (x, y), (x + w, y + h), roi_box_color, 1)

            # 2. Calculate the position for the indicator: centered above the ROI
            indicator_x_pos = x + (w // 2)
            # Position it a fixed distance above the ROI's top edge
            indicator_y_pos = y - OVERLAY_LINE_HEIGHT
            
            # Ensure the indicator doesn't draw off-screen at the top
            if indicator_y_pos < OVERLAY_LED_INDICATOR_RADIUS + OVERLAY_PADDING:
                indicator_y_pos = OVERLAY_LED_INDICATOR_RADIUS + OVERLAY_PADDING

            # 3. Determine the color of the indicator
            is_on = led_state_for_frame.get(led_key, 0) == 1
            if is_on:
                # Use the LED's specific color when ON
                indicator_color = config_item.get('display_color_bgr', OVERLAY_LED_INDICATOR_ON_COLOR_FALLBACK)
            else:
                # Use the standard dark grey color when OFF
                indicator_color = OVERLAY_LED_INDICATOR_OFF_COLOR

            # 4. Draw the indicator circle
            # Draw the filled circle for the status
            cv2.circle(overlay_frame, (indicator_x_pos, indicator_y_pos), OVERLAY_LED_INDICATOR_RADIUS, indicator_color, -1)
            # Draw a white border for better visibility against any background
            cv2.circle(overlay_frame, (indicator_x_pos, indicator_y_pos), OVERLAY_LED_INDICATOR_RADIUS, OVERLAY_TEXT_COLOR_MAIN, 1)

        return overlay_frame

    def _start_replay_recording(self, method_name: str, extra_context: Optional[Dict[str, str]] = None):
        if not self.enable_instant_replay:
            self.logger.debug(f"Replay recording not started for method '{method_name}': Instant replay is disabled.")
            return
        if not self.replay_output_dir:
            self.logger.debug(f"Replay recording not started for method '{method_name}': output directory not available.")
            return
        if self.is_recording_replay: 
            self.logger.debug(f"Replay: Recording already active for method '{self.replay_method_name}'. Ignoring start for '{method_name}'.")
            return

        self.is_recording_replay = True
        self.replay_buffer.clear()
        self.replay_start_time = time.time()
        self.replay_method_name = method_name
        self.replay_extra_context = extra_context.copy() if extra_context else {}
        self.replay_failure_reason = ""
        self.replay_frame_width = None; self.replay_frame_height = None

    def _save_replay_video(self):
        if not self.is_recording_replay or not self.replay_buffer or not self.replay_output_dir:
            if not self.replay_buffer and self.is_recording_replay: self.logger.debug("Replay: No frames in buffer to save.")
            return

        if self.replay_frame_width is None or self.replay_frame_height is None:
            self.logger.error("Replay: Frame dimensions not set. Cannot save video.")
            return

        filename_base = f"failure_instant_replay.mp4"
        filepath = os.path.join(self.replay_output_dir, filename_base)

        fourcc = int.from_bytes(b'mp4v', 'little')
        video_writer = None
        try:
            video_writer = cv2.VideoWriter(filepath, fourcc, self.replay_fps, 
                                           (self.replay_frame_width, self.replay_frame_height))
            if not video_writer.isOpened(): 
                self.logger.error(f"Replay: Failed to open VideoWriter for {filepath}."); return

            for frame_capture_time, frame_data, led_state in self.replay_buffer:
                time_in_replay_seconds = frame_capture_time - self.replay_start_time
                frame_with_overlays = self._draw_overlays(frame_data, time_in_replay_seconds, led_state)
                
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
        if not self.is_recording_replay: return

        self.replay_failure_reason = failure_reason.replace("_", " ")

        if not success and self.replay_buffer and self.replay_output_dir:
            self.logger.debug(self.replay_failure_reason)
            post_failure_start_time = time.time(); frames_after_failure = 0
            
            if self.replay_frame_width is None or self.replay_frame_height is None: 
                self.logger.error("Replay: Frame dimensions not set. Cannot save.");
                self.is_recording_replay = False; self.replay_buffer.clear(); return

            while time.time() - post_failure_start_time < self.replay_post_failure_duration_sec:
                frame, led_state_for_frame = self._get_current_led_state_from_camera()
                if frame is not None:
                    # The replay buffer expects the frame and states, which our new method provides.
                    # We just need to add the timestamp.
                    self.replay_buffer.append((time.time(), frame, led_state_for_frame))
                    frames_after_failure += 1
                else:
                    self.logger.warning("Replay: Failed to capture frame during post-failure recording.")
                time.sleep(1.0 / self.replay_fps if self.replay_fps > 0 else 0.01) 

            self._save_replay_video() 
        
        self.replay_buffer.clear()
        self.is_recording_replay = False
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
        prev_state_dict, prev_state_timestamp = last_state_info
        if prev_state_dict is None: 
            last_state_info[0] = current_state_dict; last_state_info[1] = current_time; return False 
        logged_change = False
        if current_state_dict != prev_state_dict:
            duration = current_time - prev_state_timestamp
            if duration >= MIN_LOGGABLE_STATE_DURATION:
                self.logger.info(f"{self._format_led_display_string(prev_state_dict)} ({duration:.2f}s)")
                logged_change = True
            last_state_info[0] = current_state_dict; last_state_info[1] = current_time
        return logged_change
        
    def _log_final_state(self, last_state_info: list, end_time: float, reason_suffix: str = ""):
        state_dict, state_timestamp = last_state_info
        if state_dict is not None:
            duration = end_time - state_timestamp
            if duration >= MIN_LOGGABLE_STATE_DURATION:
                self.logger.info(f"{self._format_led_display_string(state_dict)} ({duration:.2f}s{reason_suffix})")

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
            
            _, initial_leds_for_log = self._get_current_led_state_from_camera()
            if not initial_leds_for_log: initial_leds_for_log = {} 
            last_state_info = [initial_leds_for_log, initial_capture_time]

            overall_start_time = time.time()
            continuous_target_match_start_time = None
            try:
                while time.time() - overall_start_time < timeout:
                    current_time = time.time()
                    _, current_leds = self._get_current_led_state_from_camera() # Refactored call
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
                            self.logger.info(f"{self._format_led_display_string(last_state_info[0])} ({target_held_duration:.2f}s) - Solid Confirmed")
                            success_flag = True; break
                    else: 
                        continuous_target_match_start_time = None 
                    time.sleep(1 / self.replay_fps if self.replay_fps > 0 else 0.1)
                
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

            except Exception as e_loop:
                failure_detail = f"exception_in_solid_loop_{type(e_loop).__name__}"
                self.logger.error(f"Exception in {method_name} loop: {e_loop}", exc_info=True)
                success_flag = False

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

                        time.sleep(1 / self.replay_fps if self.replay_fps > 0 else 0.1)
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
            failure_detail="camera_not_init_await"; self.logger.error(f"{method_name}: {failure_detail}")
        else:
            last_state_info = [None, 0.0]
            if clear_buffer: self._clear_camera_buffer()
            _, initial_leds = self._get_current_led_state_from_camera() # Refactored call
            initial_leds = initial_leds or {}
            last_state_info = [initial_leds, time.time()]
            await_start_time = time.time()
            try:
                while time.time() - await_start_time < timeout:
                    current_time = time.time()
                    _, current_leds = self._get_current_led_state_from_camera() # Refactored call
                    if not current_leds: self._handle_state_change_logging({}, current_time, last_state_info); time.sleep(0.1); continue
                    self._handle_state_change_logging(current_leds, current_time, last_state_info)
                    if self._matches_state(current_leds, state, fail_leds):
                        if last_state_info[0] == current_leds and (current_time - last_state_info[1] >= MIN_LOGGABLE_STATE_DURATION): self.logger.info(f"{self._format_led_display_string(last_state_info[0])} ({current_time - last_state_info[1]:.2f}s when target observed)")
                        elif last_state_info[0] != current_leds: self.logger.info(f"{self._format_led_display_string(current_leds)} (0.00s+ when target observed)")
                        self.logger.info(f"Target state {formatted_target_state} observed."); success_flag=True; break
                    time.sleep(1 / self.replay_fps if self.replay_fps > 0 else 0.1)
                if not success_flag:
                    self._log_final_state(last_state_info, time.time(), reason_suffix=" at timeout")
                    failure_detail=f"timeout_await_{formatted_target_state.replace(' ','_')}"; self.logger.warning(f"Timeout: {formatted_target_state} not observed.")
            except Exception as e_await_loop:
                failure_detail=f"exception_await_loop_{type(e_await_loop).__name__}"; self.logger.error(f"Exception in {method_name} loop: {e_await_loop}", exc_info=True); success_flag=False

        if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)
        return success_flag

    def confirm_led_pattern(self, pattern: list, clear_buffer: bool = True,
                            manage_replay: bool = True, replay_extra_context: Optional[Dict[str, str]] = None) -> bool:
        method_name = "confirm_led_pattern"
        if manage_replay: self._start_replay_recording(method_name, extra_context=replay_extra_context)
        success_flag, failure_detail = False, "unknown_pattern_failure"

        if not pattern: failure_detail="empty_pattern"; self.logger.warning(f"{method_name}: {failure_detail}")
        elif not self.is_camera_initialized: failure_detail="camera_not_init_pattern"; self.logger.error(f"{method_name}: {failure_detail}")
        else:
            if clear_buffer: self._clear_camera_buffer(); self._get_current_led_state_from_camera() 
            ordered_keys = self._get_ordered_led_keys_for_display(); current_step_idx = 0
            max_dur_sum = sum(p.get('duration',(0,1))[1] for p in pattern if p.get('duration',[0,0])[1]!=float('inf'))
            inf_steps = sum(1 for p in pattern if p.get('duration',[0,0])[1]==float('inf'))
            overall_timeout = max_dur_sum + inf_steps*10.0 + len(pattern)*5.0 + 15.0 
            pattern_start_time = time.time()
            try:
                while current_step_idx < len(pattern):
                    if time.time()-pattern_start_time > overall_timeout: 
                        failure_detail=f"overall_timeout_step_{current_step_idx+1}"; self.logger.error(f"{method_name} Error: {failure_detail}"); success_flag=False; break
                    
                    step_cfg = pattern[current_step_idx]; target_state_for_step = {k:v for k,v in step_cfg.items() if k!='duration'}
                    min_d_orig, max_d_orig = step_cfg.get('duration', (0, float('inf')))
                    min_d_check = min_d_orig
                    max_d_check = max_d_orig + self.duration_tolerance_sec if max_d_orig != float('inf') else float('inf')
                    target_state_str = self._format_led_display_string(target_state_for_step, ordered_keys)
                    
                    step_seen_at = None; step_loop_start_time = time.time()
                    while True: 
                        if time.time()-pattern_start_time > overall_timeout: 
                            failure_detail=f"timeout_find_step_{current_step_idx+1}"; success_flag=False; break
                        _, current_leds = self._get_current_led_state_from_camera() # Refactored call
                        if not current_leds: time.sleep(0.03); continue
                        if self._matches_state(current_leds, target_state_for_step): step_seen_at=time.time(); break
                        if current_step_idx==0 and min_d_orig==0.0 and (time.time()-step_loop_start_time > 0.25): break 
                        step_app_timeout = max(1.0, max_d_orig/2 if max_d_orig!=float('inf') else 5.0) + 2.0
                        if time.time()-step_loop_start_time > step_app_timeout: 
                            failure_detail=f"step_{current_step_idx+1}_not_seen_{target_state_str.replace(' ','_')}"; success_flag=False; break
                        time.sleep(1/self.replay_fps if self.replay_fps > 0 else 0.03)
                    if success_flag is False and failure_detail != "unknown_pattern_failure": break 

                    if step_seen_at is None: 
                        if current_step_idx==0 and min_d_orig==0.0: 
                            self.logger.info(f"{target_state_str} 0.00s ({current_step_idx + 1:02d}/{len(pattern):02d}) - Skipped (0 dur)"); current_step_idx+=1; continue
                        failure_detail=f"step_{current_step_idx+1}_never_detected_logic_{target_state_str.replace(' ','_')}"; success_flag=False; break
                    
                    while True: 
                        if time.time()-pattern_start_time > overall_timeout: 
                            failure_detail=f"timeout_hold_step_{current_step_idx+1}"; success_flag=False; break
                        _, current_leds = self._get_current_led_state_from_camera() # Refactored call
                        if not current_leds: time.sleep(0.03); continue
                        held_time = time.time() - step_seen_at
                        if self._matches_state(current_leds, target_state_for_step): 
                            if max_d_check!=float('inf') and held_time > max_d_check: 
                                failure_detail=f"Failure to detect: {target_state_str}"; success_flag=False; break
                            if current_step_idx==len(pattern)-1 and held_time >= min_d_check: 
                                self.logger.info(f"{target_state_str}  {held_time:.2f}s+ ({current_step_idx + 1:02d}/{len(pattern):02d})")
                                current_step_idx+=1; break 
                        else:
                            if held_time >= min_d_check:
                                self.logger.info(f"{target_state_str}  {held_time:.2f}s ({current_step_idx + 1:02d}/{len(pattern):02d})")
                                current_step_idx += 1
                                break
                            elif held_time >= (min_d_orig - self.duration_tolerance_sec):
                                self.logger.warning(f"{target_state_str} held for {held_time:.2f}s. Shorter than required {min_d_orig:.2f}s but within tolerance. Passing.")
                                current_step_idx += 1
                                break
                            else:
                                current_led_str = self._format_led_display_string(current_leds, ordered_keys)
                                failure_detail=f"step_{current_step_idx+1}_state_{target_state_str.replace(' ','_')}_changed_to_{current_led_str.replace(' ','_')}_early_held_{held_time:.2f}s_min_{min_d_check:.2f}s"; success_flag=False; break
                        time.sleep(1/self.replay_fps if self.replay_fps > 0 else 0.03)
                    if success_flag is False and failure_detail != "unknown_pattern_failure": break 
                
                if current_step_idx == len(pattern) and (failure_detail == "unknown_pattern_failure" or success_flag is True):
                    success_flag = True; self.logger.info(f"{method_name}: LED pattern confirmed")
                elif failure_detail == "unknown_pattern_failure":
                    failure_detail = f"pattern_ended_inconclusively_step_{current_step_idx}"
                    self.logger.warning(f"{method_name}: Pattern ended inconclusively. Processed {current_step_idx}/{len(pattern)} steps. Reason: {failure_detail}")
                    success_flag = False
            except Exception as e_pattern_loop:
                failure_detail=f"exception_pattern_loop_{type(e_pattern_loop).__name__}"; self.logger.error(f"Exception in {method_name} loop: {e_pattern_loop}", exc_info=True); success_flag=False
        
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
                if not pattern_confirmed: failure_detail = "pattern_confirm_failed_after_await"
            else:
                formatted_first_state = self._format_led_display_string(first_state_target).replace(' ','_')
                failure_detail = f"first_state_{formatted_first_state}_not_observed_in_await_confirm"
                self.logger.warning(f"{method_name}: Pattern not started: {failure_detail}")
        
        if manage_replay: self._stop_replay_recording(success=success_flag, failure_reason=failure_detail)
        return success_flag

    def release_camera(self):
        if self.is_recording_replay:
            self.logger.info("Replay: Active recording stopped due to camera release. Discarding buffered frames.")
            self.replay_buffer.clear(); self.is_recording_replay = False 
        if self.cap and self.cap.isOpened(): self.cap.release(); self.logger.info(f"Camera ID {self.camera_id} released.")
        else: self.logger.debug(f"Camera ID {self.camera_id} was not open or already released.")
        self.cap = None; self.is_camera_initialized = False

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.release_camera()