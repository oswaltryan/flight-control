# Directory: flight-control
# Filename: basic_tutorial_2.py
#!/usr/bin/env python3

import time
import logging
import traceback
import sys

# Phidget imports
from hardware.phidget_io_controller import PhidgetController
from Phidget22.PhidgetException import PhidgetException

# Logitech LED Checker import
# This LOGITECH_CHECKER_AVAILABLE is at the module/global scope
LOGITECH_CHECKER_MODULE_IMPORTED = False # Default to False
LogitechLedChecker = None # Define to avoid NameError if import fails

try:
    from camera.camera_controller import LogitechLedChecker
    LOGITECH_CHECKER_MODULE_IMPORTED = True
except ImportError:
    # This logging will go to 'root' logger if basicConfig is called after this,
    # or to a pre-configured root logger.
    logging.warning("LogitechLedChecker module not found. Camera LED checks will be skipped.")
    # LOGITECH_CHECKER_MODULE_IMPORTED remains False, LogitechLedChecker remains None

def main():
    # pc and led_checker are local to main
    pc = None
    led_checker = None # Will store the instance if successfully initialized

    CAMERA_ID_TO_USE = 0

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        stream=sys.stdout)
    
    script_logger = logging.getLogger("BasicTutorialApp")

    try:
        script_logger.info("--- Starting Full Automation Tutorial ---")

        # --- Initialize Logitech LED Checker ---
        # Check if the module was successfully imported (using the global flag)
        if LOGITECH_CHECKER_MODULE_IMPORTED:
            try:
                # Attempt to create an instance. led_checker remains local.
                led_checker_instance = LogitechLedChecker(camera_id=CAMERA_ID_TO_USE)
                if not led_checker_instance.is_camera_initialized:
                    script_logger.error(f"Failed to initialize Logitech LED Checker with camera ID {CAMERA_ID_TO_USE}. LED checks will be unreliable.")
                    # led_checker remains None or you could set it to None explicitly
                    led_checker = None
                else:
                    led_checker = led_checker_instance # Assign to the main variable for use
            except Exception as e:
                script_logger.error(f"Exception during LogitechLedChecker instantiation: {e}")
                script_logger.error(traceback.format_exc())
                led_checker = None # Ensure led_checker is None if instantiation fails

        # --- Initialize Phidget Controller ---
        with PhidgetController() as pc:
            script_logger.info("--- Starting Test ---")

            print()
            pc.on("usb3")
            pc.on("connect")

            # --- Example Camera LED Check ---
            # Check if led_checker instance exists and was initialized
            print("here0")
            if led_checker and led_checker.is_camera_initialized:
                print("here1")
                target_led_state = {'led1': 1}
                script_logger.info(f"Awaiting camera LED state: {target_led_state}")
                if led_checker.await_led_state(target_led_state, timeout=3):
                    script_logger.info(f"SUCCESS: Camera LED state {target_led_state} observed.")
                else:
                    script_logger.warning(f"FAILURE: Camera LED state {target_led_state} not observed within timeout.")
            else:
                pc.logger.info("Skipping camera LED check (checker not available or not initialized).")
            
            pc.sequence(["key1", "key1", "key2", "key2", "key3", "key3", "key4", "key4", "unlock"])
            time.sleep(10)
            pc.press("lock")
            time.sleep(1)
            pc.off("connect")
            pc.off("usb3")

            pc.logger.info("--- Phidget Interaction Test Complete ---")

        script_logger.info("Phidget Controller resources released (due to 'with' statement).")

    except PhidgetException as e:
        logger_to_use = pc.logger if pc and hasattr(pc, 'logger') and pc.logger else script_logger
        logger_to_use.error(f"A PhidgetException occurred: {e.description} (Code: {e.code})")
        logger_to_use.error(traceback.format_exc())
    except NameError as e:
        logger_to_use = pc.logger if pc and hasattr(pc, 'logger') and pc.logger else script_logger
        logger_to_use.error(f"A NameError occurred: {e}")
        logger_to_use.error(traceback.format_exc())
    except RuntimeError as e:
        logger_to_use = pc.logger if pc and hasattr(pc, 'logger') and pc.logger else script_logger
        logger_to_use.error(f"A RuntimeError occurred: {e}")
        logger_to_use.error(traceback.format_exc())
    except Exception as e:
        script_logger.error(f"An unexpected error occurred in the main application: {e}")
        script_logger.error(traceback.format_exc())
    finally:
        if led_checker and hasattr(led_checker, 'release_camera') and led_checker.is_camera_initialized:
            script_logger.info("Attempting to release Logitech LED Checker resources in finally block...")
            try:
                led_checker.release_camera() # Call release on the instance
                script_logger.info("Logitech LED Checker resources released.")
            except Exception as cam_release_e:
                script_logger.error(f"Error releasing camera resources: {cam_release_e}")
        
        script_logger.info("--- Full Automation Tutorial Finished ---")

if __name__ == "__main__":
    main()