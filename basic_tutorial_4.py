# Directory: flight-control
# Filename: basic_tutorial_4.py
#!/usr/bin/env python3

import time
import logging
import sys
import traceback
import os

# --- Path Setup ---
# Add the project root directory (parent of 'flight-control') to the Python path
# This allows imports like 'from camera.camera_controller import ...'
# Assumes:
# project_root/
#   flight-control/ (this script is here)
#   camera/
#   hardware/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- Imports ---
try:
    from hardware.phidget_io_controller import PhidgetController
    from camera.camera_controller import LogitechLedChecker 
    # PRIMARY_LED_CONFIGURATIONS is used by LogitechLedChecker internally
    from Phidget22.PhidgetException import PhidgetException
except ImportError as e:
    # This initial ImportError might happen if PROJECT_ROOT logic is insufficient
    # or modules are not found. Log and re-raise to make it obvious.
    initial_log_msg = f"Critical Import Error: {e}. Check PYTHONPATH and project structure. Attempted to add {PROJECT_ROOT} to sys.path."
    print(initial_log_msg, file=sys.stderr) # Print to stderr as logging might not be set up
    logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.critical(initial_log_msg)
    logging.critical(traceback.format_exc())
    raise

# --- Configuration ---
CAMERA_ID = 0
LOG_LEVEL = logging.INFO  # Use logging.DEBUG for more verbose camera/phidget output

# LED Pattern to match.
# Keys 'red', 'green', 'blue' must correspond to keys in PRIMARY_LED_CONFIGURATIONS
# in camera/camera_controller.py.
# Durations are (min_duration_seconds, max_duration_seconds).
STARTUP_PATTERN_CONFIG = [
    # {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  4.0)}, # All OFF
    {'red':1, 'green':0, 'blue':0, 'duration': (0.50,  5.0)}, # Red ON
    {'red':0, 'green':1, 'blue':0, 'duration': (0.50,  3.0)}, # Green ON
    {'red':0, 'green':0, 'blue':1, 'duration': (0.50,  4.0)}, # Blue ON
    {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  5.0)}, # All OFF
    {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  1.5)}, # Green ON
    {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  1.5)}, # All OFF
    {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  1.5)}, # Green ON
    {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  1.5)}, # All OFF
    {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  1.5)}, # Green ON
    {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  1.5)}  # All OFF
]

# Timeout for await_and_confirm_led_pattern's internal await_led_state for the *first* step.
# Should be slightly more than the max duration of the first pattern step.
# First step max duration is 4.0s.
AWAIT_FIRST_STATE_TIMEOUT = 6.0  # seconds

def setup_logging(level=logging.INFO):
    """Configures basic logging for the application."""
    logging.basicConfig(stream=sys.stdout, level=level,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def main():
    setup_logging(LOG_LEVEL)
    script_logger = logging.getLogger("PatternTestScript")
    script_logger.info("--- Starting LED Pattern Test Script ---")

    # Define pc_instance and checker_instance here for broader scope in error logging if needed
    # However, their primary loggers are passed during instantiation.
    pc_instance = None 
    checker_instance = None

    try:
        # Create child loggers for better log organization
        phidget_logger = script_logger.getChild("PhidgetCtrl")
        camera_logger = script_logger.getChild("LedChecker")

        # Initialize PhidgetController using a 'with' statement for resource management
        with PhidgetController(logger_instance=phidget_logger) as pc:
            pc_instance = pc # Store for reference if needed, though 'with' handles closure
            script_logger.info("PhidgetController initialized.")

            # Initialize LogitechLedChecker using a 'with' statement
            with LogitechLedChecker(camera_id=CAMERA_ID, logger_instance=camera_logger) as checker:
                checker_instance = checker
                script_logger.info("LogitechLedChecker initialized.")

                if not checker.is_camera_initialized:
                    script_logger.error(
                        f"Failed to initialize Logitech LED Checker (Camera ID: {CAMERA_ID}). Cannot perform test."
                    )
                    # The 'with' statement for PhidgetController will still call its __exit__
                    return  # Exit main function

                script_logger.info("Turning Phidget 'connect' output ON.")
                pc.on("connect")
                
                # Optional: Short delay if the connected device needs time to react
                # time.sleep(2) 

                script_logger.info(
                    f"Attempting to match LED pattern. Timeout for first state: {AWAIT_FIRST_STATE_TIMEOUT}s."
                )
                
                pattern_matched = checker.await_and_confirm_led_pattern(
                    pattern=STARTUP_PATTERN_CONFIG,
                    timeout=AWAIT_FIRST_STATE_TIMEOUT,
                    clear_buffer=True  # Recommended to clear buffer before a new sequence
                )

                if pattern_matched:
                    script_logger.info("SUCCESS: LED startup pattern matched!")
                else:
                    script_logger.warning("FAILURE: LED startup pattern did NOT match.")

            script_logger.info("LogitechLedChecker resources released (camera closed).")
            checker_instance = None # Mark as closed

        script_logger.info("PhidgetController resources released (all outputs should be off).")
        pc_instance = None # Mark as closed

    except PhidgetException as e:
        # Use the specific phidget_logger if pc_instance was successfully created, else script_logger
        logger_to_use = pc_instance.logger if pc_instance and hasattr(pc_instance, 'logger') and pc_instance.logger else script_logger
        logger_to_use.error(f"A PhidgetException occurred: {e.description} (Code: {e.code})")
        logger_to_use.error(traceback.format_exc())
    except (NameError, RuntimeError, ValueError) as e: # Common config/runtime errors
        # Try to determine if it's a Phidget or Camera related error for more specific logging
        # This is a heuristic; specific error context is best.
        log_msg = str(e).lower()
        if "phidget" in log_msg or "channel" in log_msg:
            logger_to_use = pc_instance.logger if pc_instance and hasattr(pc_instance, 'logger') and pc_instance.logger else script_logger
        elif "camera" in log_msg or "led" in log_msg or "roi" in log_msg or "hsv" in log_msg:
            logger_to_use = checker_instance.logger if checker_instance and hasattr(checker_instance, 'logger') and checker_instance.logger else script_logger
        else:
            logger_to_use = script_logger
        logger_to_use.error(f"A configuration or runtime error occurred: {e}")
        logger_to_use.error(traceback.format_exc())
    except ImportError as e: # Should have been caught by top-level import try-except
        script_logger.critical(f"A late ImportError occurred: {e}")
        script_logger.critical(traceback.format_exc())
    except Exception as e:
        script_logger.error(f"An unexpected error occurred in the main application: {e}")
        script_logger.error(traceback.format_exc())
    finally:
        # The 'with' statements for PhidgetController and LogitechLedChecker handle resource cleanup.
        # PhidgetController.__exit__ calls close_all(), which turns off outputs.
        # LogitechLedChecker.__exit__ calls release_camera().
        # No explicit pc.off("connect") is needed here due to PhidgetController's __exit__.
        script_logger.info("--- LED Pattern Test Script Finished ---")

if __name__ == "__main__":
    main()