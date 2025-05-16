# Directory: scripts
# Filename: basic_tutorial_5.py
#!/usr/bin/env python3

import time
import logging
import sys
import os
from pprint import pprint
import traceback
from usb_tool import find_apricorn_device

# --- Path Setup ---
# This script (basic_tutorial_5.py) is in project_root/scripts/
# We need to add project_root to sys.path so it can find the 'controllers' package,
# and 'controllers.unified_controller' can then find 'camera' and 'hardware'.
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR) # This should be project_root

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    # Now import from the 'controllers' package
    from controllers.unified_controller import UnifiedController
    # PhidgetException is re-exported by unified_controller, but can also be imported directly
    from Phidget22.PhidgetException import PhidgetException
except ImportError as e:
    initial_log_msg = (f"Critical Import Error in basic_tutorial_5.py: {e}. "
                       f"Check PYTHONPATH and project structure. Attempted to add '{PROJECT_ROOT}' to sys.path. "
                       "Ensure 'controllers/unified_controller.py' exists and is importable.")
    print(initial_log_msg, file=sys.stderr)
    logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.critical(initial_log_msg)
    logging.critical(traceback.format_exc())
    raise

# --- Configuration ---
CAMERA_ID_TO_USE = 0
LOG_LEVEL = logging.INFO

STARTUP_PATTERN = [
    # {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  4.0)},
    {'red':1, 'green':0, 'blue':0, 'duration': (0.50,  5.0)},
    {'red':0, 'green':1, 'blue':0, 'duration': (0.50,  3.0)},
    {'red':0, 'green':0, 'blue':1, 'duration': (0.50,  4.0)},
    {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  5.0)},
    {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  1.5)},
    {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  1.5)},
    {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  1.5)},
    {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  1.5)},
    {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  1.5)},
    {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  1.5)}
]
AWAIT_FIRST_PATTERN_STATE_TIMEOUT = 6.0
LED_DISPLAY_ORDER = ["red", "green", "blue"]


def setup_logging(level=logging.INFO):
    logging.basicConfig(stream=sys.stdout, level=level,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def main():
    setup_logging(LOG_LEVEL)
    script_logger = logging.getLogger("UnifiedTutorialScript") # Main logger for this script
    script_logger.info("--- Starting Tutorial with UnifiedController (from scripts dir) ---")

    try:
        # Pass the script_logger's child to UnifiedController
        # UnifiedController will then create its own children for Phidget & Camera
        unified_ctrl_logger = script_logger.getChild("UnifiedCtrl")
        
        with UnifiedController(camera_id=CAMERA_ID_TO_USE,
                               display_order=LED_DISPLAY_ORDER,
                               logger_instance=unified_ctrl_logger) as at:

            script_logger.info("UnifiedController initialized and active.")

            if not at.is_camera_ready:
                script_logger.error("Camera component of UnifiedController is not ready. Aborting pattern test.")
                return

            script_logger.info("Turning Phidget 'connect' output ON.")
            at.on("usb3")
            at.on("connect") 

            script_logger.info(
                f"Attempting to match LED startup pattern. Timeout for first state: {AWAIT_FIRST_PATTERN_STATE_TIMEOUT}s."
            )
            
            if at.await_and_confirm_led_pattern(pattern=STARTUP_PATTERN, timeout=AWAIT_FIRST_PATTERN_STATE_TIMEOUT, clear_buffer=True):
                if at.confirm_led_solid({'red':1, 'green':0, 'blue':0}, minimum=3, timeout=5):
                    at.sequence(["key1", "key1", "key2", "key2", "key3", "key3", "key4", "key4", "unlock"])
                    time.sleep(3)
                    if at.confirm_led_solid({'green':1}, minimum=5, timeout=15):
                        device = find_apricorn_device()
                        pprint(device[1])
                        at.press("lock")
                        if at.confirm_led_solid({'red':1}, minimum=3, timeout=10):
                            at.off("connect")
                            at.confirm_led_solid({'red':0, 'green':0, 'blue':0}, minimum=3, timeout=5)
            
        script_logger.info("UnifiedController resources released.")

    except PhidgetException as e:
        script_logger.error(f"A PhidgetException occurred: {e.description} (Code: {e.code})")
        script_logger.error(traceback.format_exc())
    except (NameError, RuntimeError, ValueError) as e: 
        script_logger.error(f"A configuration or runtime error occurred: {e}")
        script_logger.error(traceback.format_exc())
    except Exception as e:
        script_logger.error(f"An unexpected error occurred: {e}")
        script_logger.error(traceback.format_exc())
    finally:
        script_logger.info("--- UnifiedController Tutorial (from scripts dir) Finished ---")

if __name__ == "__main__":
    main()