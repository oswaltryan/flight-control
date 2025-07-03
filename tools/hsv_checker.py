# File: tools/hsv_checker.py

import os
import sys
import logging
import cv2
import numpy as np
from typing import Optional

# --- Path Setup ---
_CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_CURRENT_SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- Basic Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("HSV_Checker")

# --- Import Project Modules & Constants ---
try:
    from controllers.unified_controller import UnifiedController
    from controllers.logitech_webcam import (
        LogitechLedChecker,
        OVERLAY_TEXT_COLOR_MAIN,
        OVERLAY_LED_INDICATOR_OFF_COLOR,
        OVERLAY_LED_INDICATOR_RADIUS,
        OVERLAY_LINE_HEIGHT,
        OVERLAY_PADDING,
        _CAMERA_SETTINGS_FILE # NEW: Import the path to the settings file
    )
except ImportError as e_import:
    logger.critical(f"Import Error: {e_import}. Ensure paths are correct.", exc_info=True)
    sys.exit(1)

# --- Global state for mouse info ---
mouse_info = {'x': -1, 'y': -1, 'bgr': (0,0,0), 'hsv': (0,0,0)}

def on_mouse_event(event, x, y, flags, param):
    """Mouse callback to update the global mouse position."""
    if event == cv2.EVENT_MOUSEMOVE:
        mouse_info['x'], mouse_info['y'] = x, y

def main():
    """Main function to run the HSV checker."""
    unified_at_controller: Optional[UnifiedController] = None
    
    logger.info("Initializing UnifiedController to power on device...")
    try:
        # NEW: Log which settings file will be used
        logger.info(f"UnifiedController will attempt to apply camera settings from: {_CAMERA_SETTINGS_FILE}")

        unified_at_controller = UnifiedController(
            camera_id=0,
            logger_instance=logger.getChild("UnifiedCtrl"),
            replay_output_dir=None # Disable replays for this tool
        )

        if not unified_at_controller.is_camera_ready:
            logger.error("Camera not initialized. Exiting.")
            return

        checker_instance = unified_at_controller._camera_checker
        if not checker_instance or not checker_instance.cap:
            logger.error("Internal camera or video capture object is not available. Exiting.")
            return

        logger.info("Turning on device to illuminate LEDs...")
        unified_at_controller.on("connect")

        window_name = "HSV Checker (Live Feed) - Press 'q' to quit"
        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, on_mouse_event)

        logger.info("\n--- Instructions ---")
        logger.info("1. Move mouse over the lit LEDs in the window to see HSV/BGR values.")
        logger.info("2. The circle indicator above each ROI shows the real-time ON/OFF detection status.")
        logger.info("3. Press 'q' to close the window.")
        logger.info("--------------------\n")

        while True:
            # Atomically get the latest frame and the detected LED states from that frame
            frame, detected_led_states = checker_instance._get_current_led_state_from_camera()
            
            if frame is None:
                logger.warning("Failed to grab frame. Retrying...")
                continue

            # Convert the whole frame to HSV for the mouse-over display
            hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            # Update pixel color info if the mouse is on the screen
            if mouse_info['x'] >= 0 and mouse_info['y'] >= 0:
                mouse_info['bgr'] = frame[mouse_info['y'], mouse_info['x']]
                mouse_info['hsv'] = hsv_frame[mouse_info['y'], mouse_info['x']]

            # Draw the defined ROIs and their status indicators
            for led_key, config in checker_instance.led_configs.items():
                x, y, w, h = config["roi"]
                roi_color = config.get("display_color_bgr", (128, 128, 128))
                cv2.rectangle(frame, (x, y), (x + w, y + h), roi_color, 2)
                cv2.putText(frame, config["name"], (x, y - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, roi_color, 2)

                # --- NEW: Add the replay-style indicator circle ---
                indicator_x = x + (w // 2)
                indicator_y = y - OVERLAY_LED_INDICATOR_RADIUS - 5 # Position it just above the ROI name

                # Determine the indicator color based on the detected state
                is_on = detected_led_states.get(led_key, 0) == 1
                indicator_color = OVERLAY_TEXT_COLOR_MAIN if is_on else OVERLAY_LED_INDICATOR_OFF_COLOR
                
                # Draw the filled indicator circle and its outline
                cv2.circle(frame, (indicator_x, indicator_y), OVERLAY_LED_INDICATOR_RADIUS, indicator_color, -1)
                cv2.circle(frame, (indicator_x, indicator_y), OVERLAY_LED_INDICATOR_RADIUS, OVERLAY_TEXT_COLOR_MAIN, 1)
                # --- END NEW ---

            # Prepare BGR/HSV text to display on screen
            bgr_str = f"BGR: {str(tuple(mouse_info['bgr'])):<15}"
            hsv_str = f"HSV: {str(tuple(mouse_info['hsv'])):<15}"

            # Draw a black background rectangle for the text
            cv2.rectangle(frame, (5, 5), (300, 60), (0,0,0), -1)
            # Draw the text on the rectangle
            cv2.putText(frame, bgr_str, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(frame, hsv_str, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

            cv2.imshow(window_name, frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        if unified_at_controller:
            logger.info("Cleaning up: Turning off device and closing resources.")
            unified_at_controller.close()
        cv2.destroyAllWindows()
        logger.info("Script finished.")

if __name__ == "__main__":
    main()