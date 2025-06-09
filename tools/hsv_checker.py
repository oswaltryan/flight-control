# Directory: /scripts/
# Filename: camera_feed_test.py

import os
import sys
import logging
import time
import cv2
import numpy as np
from typing import Dict, Any, Optional

# --- Path Setup ---
# Correctly identify the project root when the script is in a subdirectory (e.g., 'scripts').
_CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_FOR_DISPLAY = os.path.dirname(_CURRENT_SCRIPT_DIR)

# Ensure the project root is in sys.path so modules like 'utils', 'camera', and 'controllers' can be found.
if PROJECT_ROOT_FOR_DISPLAY not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_FOR_DISPLAY)

# --- IMPORT AND SETUP LOGGING FIRST ---
try:
    from utils.logging_config import setup_logging
    # Configure logging for this specific script
    setup_logging(
        default_log_level=logging.INFO,
        log_level_overrides={
            "CameraFeedDisplay": logging.INFO,
            "CameraFeedDisplay.UnifiedCtrl": logging.INFO, # Logger for UnifiedController instance
            "CameraFeedDisplay.UnifiedCtrl.Phidget": logging.INFO, # Phidget sub-logger
            "CameraFeedDisplay.UnifiedCtrl.Camera": logging.DEBUG, # Camera sub-logger for detailed info
            "camera.camera_controller": logging.INFO, # General camera_controller if not via UnifiedController
            "hardware.phidget_io_controller": logging.INFO, # General phidget_io_controller
            "controllers.unified_controller": logging.INFO, # UnifiedController's own messages
            "Phidget22": logging.WARNING # Suppress verbose Phidget library logs
        }
    )
except ImportError as e_log_setup:
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.getLogger().critical(f"Failed to import or run setup_logging: {e_log_setup}. Using basic logging.", exc_info=True)

# Get a logger for this script
display_logger = logging.getLogger("CameraFeedDisplay")

# --- Import Controllers and Camera Components ---
try:
    # We now import UnifiedController as it orchestrates both camera and Phidgets
    from controllers.unified_controller import UnifiedController
    from camera.camera_controller import (
        PRIMARY_LED_CONFIGURATIONS, # Contains the ROI definitions
        DEFAULT_FPS, # Default FPS for camera if not detected
        # Overlay drawing constants from camera_controller.py
        OVERLAY_FONT, OVERLAY_FONT_SCALE, OVERLAY_FONT_THICKNESS,
        OVERLAY_TEXT_COLOR_MAIN,
        OVERLAY_LINE_HEIGHT, OVERLAY_PADDING
    )
    # We'll need access to the internal LogitechLedChecker instance
    from camera.camera_controller import LogitechLedChecker # Used for type hinting

except ImportError as e_import:
    display_logger.critical(f"Import Error in camera_feed_test.py: {e_import}. Ensure paths are correct and dependencies are installed.", exc_info=True)
    sys.exit(1)

# --- Helper Function for Drawing Overlays ---
def draw_text_with_optional_bg(img: np.ndarray, text: str, origin_xy: tuple, font: int, scale: float, color: tuple, thickness: int) -> None:
    """
    Draws text on the image. Simplistic, without actual background drawing for this utility.
    """
    cv2.putText(img, text, origin_xy, font, scale, color, thickness, lineType=cv2.LINE_AA)

def draw_live_overlays(frame: np.ndarray, checker_instance: LogitechLedChecker, detected_states: Dict[str, int], current_fps: float) -> np.ndarray:
    """
    Draws ROIs, LED states, and FPS on the live camera frame.
    """
    overlay_frame = frame.copy()
    current_y_offset = OVERLAY_PADDING

    # 1. Draw Camera FPS (Top-left)
    fps_text = f"FPS: {current_fps:.2f}"
    draw_text_with_optional_bg(overlay_frame, fps_text, (OVERLAY_PADDING, current_y_offset + OVERLAY_LINE_HEIGHT),
                               OVERLAY_FONT, OVERLAY_FONT_SCALE * 1.1, OVERLAY_TEXT_COLOR_MAIN, OVERLAY_FONT_THICKNESS + 1)
    current_y_offset += OVERLAY_LINE_HEIGHT * 2

    # 2. Prepare and draw Combined LED States (e.g., "LEDs: (R) OFF (G) ON (B) OFF")
    state_line_parts = []
    # _get_ordered_led_keys_for_display() is an internal method of LogitechLedChecker
    ordered_keys = checker_instance._get_ordered_led_keys_for_display()
    
    for led_key in ordered_keys:
        config_item = checker_instance.led_configs.get(led_key)
        if not config_item:
            continue

        x, y, w, h = config_item["roi"]
        roi_box_color = config_item.get("display_color_bgr", (128, 128, 128))
        cv2.rectangle(overlay_frame, (x, y), (x + w, y + h), roi_box_color, 1)

        text_pos_y = y - OVERLAY_PADDING if y - OVERLAY_PADDING > OVERLAY_LINE_HEIGHT else y + h + OVERLAY_LINE_HEIGHT
        text_pos_x = x + OVERLAY_PADDING
        draw_text_with_optional_bg(overlay_frame, config_item["name"], (text_pos_x, text_pos_y),
                                   OVERLAY_FONT, OVERLAY_FONT_SCALE * 0.8, OVERLAY_TEXT_COLOR_MAIN,
                                   OVERLAY_FONT_THICKNESS)
        
        state_val = detected_states.get(led_key, -1)
        display_char = config_item["name"][0] if config_item["name"] else led_key[0].upper()
        state_str = "ON" if state_val == 1 else "OFF" if state_val == 0 else "N/A"
        state_line_parts.append(f"({display_char}) {state_str}")
        
    combined_states_text = "LEDs: " + " ".join(state_line_parts)
    draw_text_with_optional_bg(overlay_frame, combined_states_text, (OVERLAY_PADDING, current_y_offset + OVERLAY_LINE_HEIGHT),
                               OVERLAY_FONT, OVERLAY_FONT_SCALE * 0.9, OVERLAY_TEXT_COLOR_MAIN, OVERLAY_FONT_THICKNESS)

    return overlay_frame

def on_mouse_event(event, x, y, flags, param):
    """Callback function for mouse events to display pixel color info."""
    if event == cv2.EVENT_MOUSEMOVE:
        hsv_frame = param[0]
        bgr_frame = param[1]
        bgr_val = bgr_frame[y, x]
        hsv_val = hsv_frame[y, x]
        output_str = f"Pixel @ ({x}, {y}) -> BGR: {str(bgr_val):<16} | HSV: {str(hsv_val)}"
        print(output_str, end='\r')

# --- Main function to run the camera feed ---
def main():
    camera_id = 0
    unified_at_controller: Optional[UnifiedController] = None
    
    display_logger.info(f"Initializing UnifiedController (including camera ID {camera_id} and Phidgets)...")
    try:
        unified_at_controller = UnifiedController(
            camera_id=camera_id,
            led_configs=PRIMARY_LED_CONFIGURATIONS,
            display_order=["red", "green", "blue"],
            logger_instance=display_logger.getChild("UnifiedCtrl"),
            replay_output_dir=None
        )

        if not unified_at_controller.is_camera_ready:
            display_logger.error("UnifiedController's camera component not initialized. Exiting.")
            return

        checker_instance_from_at = unified_at_controller._camera_checker
        if checker_instance_from_at is None:
            display_logger.error("Internal camera checker instance is None. Exiting.")
            return

        display_logger.info("Camera initialized successfully. Displaying live feed.")
        
        display_logger.info("Turning on device (USB3 and Connect lines)...")
        unified_at_controller.on("usb3")
        unified_at_controller.on("connect")
        display_logger.info("Device power sequence initiated.")
        time.sleep(2) 

        display_logger.info("\n--- CONTROLS ---")
        display_logger.info(" 'p'       : Pause / Resume the live feed")
        display_logger.info(" 'q' / ESC : Quit the application")
        display_logger.info(" Mouse     : When paused, move mouse to see pixel BGR/HSV values in console.")
        display_logger.info("----------------\n")

        checker_instance_from_at._clear_camera_buffer()

        prev_frame_time = time.time()
        fps_display_value = 0.0
        is_paused = False
        window_name = "Live Camera Feed with LED ROIs"
        cv2.namedWindow(window_name)

        # <<< MODIFICATION START: Corrected Control Flow >>>
        # Initialize frame variables to None before the loop.
        frame: Optional[np.ndarray] = None
        annotated_frame: Optional[np.ndarray] = None

        while True:
            # Step 1: Process a new frame IF we are not paused.
            if not is_paused:
                # Capture the new frame and its detected states
                new_frame, detected_led_states = checker_instance_from_at._get_current_led_state_from_camera()
                
                if new_frame is not None:
                    # If capture was successful, update our 'last good frame'
                    frame = new_frame
                    
                    # Update FPS calculation
                    current_frame_time = time.time()
                    fps_display_value = 1.0 / (current_frame_time - prev_frame_time) if (current_frame_time - prev_frame_time) > 0 else 0.0
                    prev_frame_time = current_frame_time
                    
                    # Create the new annotated frame
                    annotated_frame = draw_live_overlays(frame, checker_instance_from_at, detected_led_states, fps_display_value)
                else:
                    display_logger.warning("Failed to grab frame. Retrying...")
                    time.sleep(0.1)

            # Step 2: Display the last valid annotated frame.
            # If paused, this shows the same frame repeatedly. If running, it shows the newest one.
            if annotated_frame is not None:
                cv2.imshow(window_name, annotated_frame)
            
            # Step 3: Check for user input.
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                display_logger.info("Exit key pressed. Terminating camera feed.")
                break
            elif key == ord('p'):
                # By the time this code is reached, 'frame' is guaranteed to exist from Step 1.
                if frame is None:
                    display_logger.warning("Cannot pause, no valid frame has been captured yet.")
                    continue

                is_paused = not is_paused
                if is_paused:
                    display_logger.info("Feed PAUSED. Move mouse over image to inspect pixel values.")
                    hsv_snapshot = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                    cv2.setMouseCallback(window_name, on_mouse_event, [hsv_snapshot, frame])
                else:
                    display_logger.info("Feed RESUMED.")
                    cv2.setMouseCallback(window_name, lambda *args: None)
                    print()
        # <<< MODIFICATION END >>>

    except Exception as e:
        display_logger.critical(f"An unexpected error occurred in the main camera feed loop: {e}", exc_info=True)
    finally:
        if unified_at_controller:
            display_logger.info("Attempting to turn off device before closing UnifiedController...")
            try:
                unified_at_controller.off("usb3")
                unified_at_controller.off("connect")
                display_logger.info("Device power lines set to OFF.")
                time.sleep(0.5)
            except Exception as e_off:
                display_logger.warning(f"Error turning off device: {e_off}", exc_info=True)

            display_logger.info("Closing UnifiedController resources...")
            unified_at_controller.close()
        cv2.destroyAllWindows()
        display_logger.info("Camera feed display application terminated.")

if __name__ == "__main__":
    main()