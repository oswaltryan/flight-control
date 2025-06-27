# Directory: tools
# Filename: calibrate_rois.py

"""
A lightweight, standalone script to calibrate and verify the LED Regions of Interest (ROIs).

This tool powers on the device to trigger its Power-On Self-Test (POST) sequence.
It then individually checks if the 'red', 'green', and 'blue' LEDs are detected
correctly as they light up during the startup pattern.

This is useful for:
- Initial setup of a test station.
- Verifying camera position and focus.
- Confirming that the HSV color values in camera_controller.py are accurate.
"""

import logging
import sys
import os
import time
from typing import Dict

# --- Path Setup ---
# This allows the script to be run from anywhere and still find the project modules.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- Minimal Imports from the Project ---
try:
    from hardware.phidget_controller import PhidgetController
    from camera.camera_controller import LogitechLedChecker
except ImportError as e:
    print(f"ERROR: Could not import necessary modules. Make sure you are running this from a project with the correct structure.", file=sys.stderr)
    print(f"Import Error: {e}", file=sys.stderr)
    sys.exit(1)


# --- Basic Logging Configuration ---
# We don't need the full logging_config.py for this simple tool.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("ROICalibration")


def run_calibration(camera: LogitechLedChecker, phidget: PhidgetController) -> bool:
    """
    Executes the calibration logic.

    Args:
        camera: An initialized LogitechLedChecker instance.
        phidget: An initialized PhidgetController instance.

    Returns:
        True if all colors were detected successfully, False otherwise.
    """
    # <<< FIX IS HERE >>>
    # The attribute on LogitechLedChecker is 'is_camera_initialized', not 'is_camera_ready'.
    if not camera.is_camera_initialized:
        logger.error("Camera is not initialized. Cannot run calibration.")
        return False

    results: Dict[str, bool] = {
        "red": False,
        "green": False,
        "blue": False,
    }
    
    # Define the simple, single-color states we expect to see during POST.
    # These are derived from the 'STARTUP' pattern in led_dictionaries.py
    RED_SOLID = {'red': 1, 'green': 0, 'blue': 0}
    GREEN_SOLID = {'red': 0, 'green': 1, 'blue': 0}
    BLUE_SOLID = {'red': 0, 'green': 0, 'blue': 1}

    try:
        logger.info("--- Starting ROI Calibration ---")
        logger.info("This script will now power on the device to trigger its POST sequence.")
        input("Please ensure the device is connected and ready. Press Enter to continue...")

        # 1. Trigger the POST by turning on the 'connect' relay.
        phidget.on("connect")
        logger.info("Device power on triggered. Awaiting POST sequence...")
        # A small delay to allow the device to start its boot process.
        time.sleep(1)

        # 2. Check for each color in sequence.
        # The 'STARTUP' pattern is: R, G, B, then a flicker. We just need to catch the first three solid states.
        # We give each check a generous timeout.

        logger.info("\n[1/3] Awaiting SOLID RED...")
        if camera.await_led_state(RED_SOLID, timeout=5, clear_buffer=False):
            logger.info("SUCCESS: RED LED detected correctly.")
            results["red"] = True
        else:
            logger.error("FAILURE: RED LED was not detected.")

        logger.info("\n[2/3] Awaiting SOLID GREEN...")
        if camera.await_led_state(GREEN_SOLID, timeout=5, clear_buffer=False):
            logger.info("SUCCESS: GREEN LED detected correctly.")
            results["green"] = True
        else:
            logger.error("FAILURE: GREEN LED was not detected.")

        logger.info("\n[3/3] Awaiting SOLID BLUE...")
        if camera.await_led_state(BLUE_SOLID, timeout=5, clear_buffer=False):
            logger.info("SUCCESS: BLUE LED detected correctly.")
            results["blue"] = True
        else:
            logger.error("FAILURE: BLUE LED was not detected.")

    except Exception as e:
        logger.error(f"An unexpected error occurred during calibration: {e}", exc_info=True)
        return False
    finally:
        # 3. Clean up by powering down the device.
        logger.info("Powering down the device.")
        phidget.off("connect")

    # 4. Report the final results.
    logger.info("\n" + "---" * 15)
    logger.info("--- ROI CALIBRATION SUMMARY ---")
    all_ok = True
    for color, status in results.items():
        if status:
            logger.info(f"  [PASS] {color.upper():<5} ROI is correctly configured.")
        else:
            logger.error(f"  [FAIL] {color.upper():<5} ROI failed. Check camera position or HSV values in camera_controller.py.")
            all_ok = False
    logger.info("---" * 15 + "\n")

    if not all_ok:
        logger.warning("One or more ROIs failed. Please adjust your setup and re-run.")

    return all_ok


def main():
    """ Main entry point of the script. """
    camera = None
    phidget = None
    try:
        # Directly instantiate the controllers we need.
        logger.info("Initializing Phidget and Camera controllers...")
        phidget = PhidgetController(logger_instance=logger.getChild("Phidget"))
        camera = LogitechLedChecker(camera_id=0, logger_instance=logger.getChild("Camera"))

        run_calibration(camera, phidget)

    except Exception as e:
        logger.critical(f"A critical error occurred during initialization: {e}", exc_info=True)
    finally:
        # Ensure all hardware resources are released.
        logger.info("Closing hardware resources.")
        if camera:
            camera.release_camera()
        if phidget:
            phidget.close_all()
        logger.info("Script finished.")


if __name__ == "__main__":
    main()