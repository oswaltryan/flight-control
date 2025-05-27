#!/usr/bin/env python3

import time
import logging
import sys
import cv2 # OpenCV for displaying frames and drawing ROIs
import numpy as np # For HSV array manipulation
import os

# Make sure the 'camera' module is in the Python path
SCRIPT_DIR_BASIC = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_BASIC = os.path.abspath(os.path.join(SCRIPT_DIR_BASIC, '..')) # Go one level up
if PROJECT_ROOT_BASIC not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_BASIC)

try:
    # Import the checker class AND the single source of truth for LED configurations
    from camera.camera_controller import LogitechLedChecker, PRIMARY_LED_CONFIGURATIONS
except ImportError:
    import os
    from camera.camera_controller import LogitechLedChecker, PRIMARY_LED_CONFIGURATIONS

try:
    from hardware.phidget_io_controller import PhidgetController
except ImportError:
    import os
    from hardware.phidget_io_controller import PhidgetController


# --- Configuration ---
CAMERA_ID = 0  # Adjust if your camera is not ID 0
LOG_LEVEL = logging.DEBUG # Use DEBUG to see HSV match details from LogitechLedChecker
DEFAULT_VISUALIZATION_COLOR = (200, 200, 200) # BGR for ROIs if "display_color_bgr" not in config

def setup_logging(level=logging.INFO):
    """Configures basic logging for the test script."""
    logging.basicConfig(stream=sys.stdout, level=level,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def main():
    setup_logging(LOG_LEVEL)
    script_logger = logging.getLogger("LEDFeedbackScript")
    script_logger.info("--- Starting LED Configuration Feedback Script ---")

    # Check if PRIMARY_LED_CONFIGURATIONS was imported and is valid
    if not PRIMARY_LED_CONFIGURATIONS or not isinstance(PRIMARY_LED_CONFIGURATIONS, dict) or not len(PRIMARY_LED_CONFIGURATIONS):
        script_logger.error("PRIMARY_LED_CONFIGURATIONS not found, is empty, or is invalid in camera_controller.py.")
        script_logger.error("Please define LED configurations in camera/camera_controller.py before running this script.")
        return

    script_logger.info("Press 'q' in the OpenCV window to quit.")

    try:
        # LogitechLedChecker will implicitly use PRIMARY_LED_CONFIGURATIONS
        with PhidgetController() as pc:
            with LogitechLedChecker(camera_id=CAMERA_ID,
                                    logger_instance=script_logger) as checker:

                if not checker.is_camera_initialized:
                    script_logger.error("Failed to initialize camera. Exiting.")
                    return

                effective_led_configs = checker.led_configs # These are PRIMARY_LED_CONFIGURATIONS

                script_logger.info("Camera initialized. Displaying feedback based on PRIMARY_LED_CONFIGURATIONS...")

                pc.on("connect")

                while True:
                    if not checker.cap or not checker.cap.isOpened():
                        script_logger.error("Camera capture is not open. Exiting loop.")
                        break

                    ret, frame = checker.cap.read()
                    if not ret or frame is None:
                        script_logger.warning("Failed to grab frame from camera.")
                        time.sleep(0.1)
                        continue

                    display_frame = frame.copy()
                    official_led_states = checker._get_current_led_state_from_camera()

                    for led_key, config in effective_led_configs.items():
                        # Values from PRIMARY_LED_CONFIGURATIONS in camera_controller.py
                        roi_rect = config["roi"]
                        hsv_lower_cfg = np.array(config["hsv_lower"])
                        hsv_upper_cfg = np.array(config["hsv_upper"])
                        min_match_percentage_cfg = config["min_match_percentage"]
                        
                        # Get display color from config, or use default
                        draw_color = config.get("display_color_bgr", DEFAULT_VISUALIZATION_COLOR)
                        # Ensure draw_color is valid, fallback if not
                        if not (isinstance(draw_color, tuple) and len(draw_color) == 3 and all(isinstance(c, int) for c in draw_color)):
                            draw_color = DEFAULT_VISUALIZATION_COLOR


                        x, y, w, h = roi_rect
                        frame_h_disp, frame_w_disp = display_frame.shape[:2]
                        x_start, y_start = max(0, x), max(0, y)
                        x_end, y_end = min(frame_w_disp, x + w), min(frame_h_disp, y + h)
                        actual_w, actual_h = x_end - x_start, y_end - y_start

                        avg_hsv_text = "AvgHSV: N/A"
                        match_percentage_display = 0.0

                        if actual_w > 0 and actual_h > 0:
                            led_roi_bgr = display_frame[y_start:y_end, x_start:x_end]
                            if led_roi_bgr.size > 0:
                                led_roi_hsv = cv2.cvtColor(led_roi_bgr, cv2.COLOR_BGR2HSV)
                                avg_h, avg_s, avg_v = cv2.mean(led_roi_hsv)[:3]
                                avg_hsv_text = f"AvgHSV:({int(avg_h)},{int(avg_s)},{int(avg_v)})"

                                # Re-calculate match percentage for display
                                if hsv_lower_cfg[0] > hsv_upper_cfg[0]:
                                    mask1 = cv2.inRange(led_roi_hsv, np.array([hsv_lower_cfg[0],hsv_lower_cfg[1],hsv_lower_cfg[2]]), np.array([179,hsv_upper_cfg[1],hsv_upper_cfg[2]]))
                                    mask2 = cv2.inRange(led_roi_hsv, np.array([0,hsv_lower_cfg[1],hsv_lower_cfg[2]]), np.array([hsv_upper_cfg[0],hsv_upper_cfg[1],hsv_upper_cfg[2]]))
                                    color_mask = cv2.bitwise_or(mask1, mask2)
                                else:
                                    color_mask = cv2.inRange(led_roi_hsv, hsv_lower_cfg, hsv_upper_cfg)
                                
                                matching_pixels = cv2.countNonZero(color_mask)
                                total_pixels_in_roi = actual_w * actual_h
                                match_percentage_display = matching_pixels / float(total_pixels_in_roi) if total_pixels_in_roi > 0 else 0.0
                        
                        is_on_status = "ON" if official_led_states.get(led_key, 0) == 1 else "OFF"
                        status_text = f"{config.get('name', led_key).upper()}: {is_on_status}"
                        match_text = f"Match:{match_percentage_display*100:.0f}% (Req:{min_match_percentage_cfg*100:.0f}%)"
                        
                        x_draw, y_draw = max(0,x), max(0,y)
                        cv2.rectangle(display_frame, (x_draw, y_draw), (x_draw + actual_w, y_draw + actual_h), draw_color, 2)
                        cv2.putText(display_frame, status_text, (x_draw, y_draw - 5 if y_draw > 5 else y_draw + actual_h + 15),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, draw_color, 1)
                        # cv2.putText(display_frame, avg_hsv_text, (x_draw, y_draw - 20 if y_draw > 20 else y_draw + actual_h + 30),
                        #             cv2.FONT_HERSHEY_SIMPLEX, 0.4, draw_color, 1)
                        # cv2.putText(display_frame, match_text, (x_draw, y_draw - 5 if y_draw > 5 else y_draw + actual_h + 45),
                        #             cv2.FONT_HERSHEY_SIMPLEX, 0.4, draw_color, 1)

                    cv2.imshow(f"LED Config Feedback (Edit camera_controller.py) - Cam {CAMERA_ID} (q to quit)", display_frame)

                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        script_logger.info("Quit key pressed. Exiting...")
                        break
                    
                    time.sleep(0.05)

    except ImportError as e:
        script_logger.critical(f"Failed to import a required module: {e}")
    except FileNotFoundError:
        script_logger.critical("Could not find camera_controller.py or PhidgetController. Ensure PYTHONPATH is correct.")
    except AttributeError as e:
        script_logger.critical(f"Likely PRIMARY_LED_CONFIGURATIONS is missing or malformed in camera_controller.py: {e}")
    except Exception as e:
        script_logger.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        cv2.destroyAllWindows()
        script_logger.info("--- LED Configuration Feedback Script Finished ---")

if __name__ == "__main__":
    main()