# Directory: scripts
# Filename: basic_tutorial_6.py
#!/usr/bin/env python3

import time
import logging
import sys
import os
from pprint import pprint
import traceback

# --- Path Setup ---
# This script is in project_root/scripts/
# We need to add project_root to sys.path to find 'global_controller.py' (if it's in project_root)
# and allow global_controller.py to find 'controllers', 'camera', 'hardware'.
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR) # This should be project_root

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    # Import the globally initialized 'at' instance
    from automation_toolkit import at # Assumes global_controller.py is in PROJECT_ROOT
    from Phidget22.PhidgetException import PhidgetException
    from usb_tool import find_apricorn_device 
except ImportError as e:
    initial_log_msg = (f"Critical Import Error in basic_tutorial_6.py: {e}. "
                       f"Check PYTHONPATH and project structure. Attempted to add '{PROJECT_ROOT}' to sys.path. "
                       "Ensure 'global_controller.py' exists and is importable, and that it can find UnifiedController and usb_tool.")
    print(initial_log_msg, file=sys.stderr)
    # Minimal logging if full setup fails
    logging.basicConfig(level=logging.CRITICAL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.critical(initial_log_msg)
    logging.critical(traceback.format_exc())
    raise SystemExit("Failed to import core automation toolkit or dependencies.")


# --- Script-Specific Configuration ---
# Most configuration for 'at' should be in global_controller.py
# These are mainly for this script's logic.
LOG_LEVEL_SCRIPT = logging.INFO # Logging level for this script's specific logger

# LED Pattern for this script's logic
# Keys ('red', 'green', 'blue') must match what 'at' instance expects (from its led_configs/display_order)
SCRIPT_STARTUP_PATTERN = [
    {'red':1, 'green':0, 'blue':0, 'duration': (0.50,  5.0)}, # Starts with Red ON
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
AWAIT_FIRST_STATE_TIMEOUT_SCRIPT = 6.0 # Timeout for awaiting the first step of SCRIPT_STARTUP_PATTERN

# --- Logging Setup for this Script ---
# The 'at' instance has its own logger configured in global_controller.py.
# This sets up a logger specifically for messages from this script.
script_logger = logging.getLogger("Tutorial6Script")
if not script_logger.hasHandlers(): # Configure only if not already configured (e.g. by a root config)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - SCRIPT - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    script_logger.addHandler(handler)
    script_logger.setLevel(LOG_LEVEL_SCRIPT)


def run_automation_sequence():
    """Main automation logic using the global 'at' controller."""
    script_logger.info("--- Starting Simplified Automation Sequence ---")

    if at is None:
        script_logger.critical("Global 'at' controller is not available (failed initialization). Exiting.")
        return False # Indicate failure

    if not at.is_camera_ready:
        script_logger.error("Camera component of 'at' is not ready. Cannot perform full sequence.")
        # Potentially run Phidget-only actions or exit
        # at.on("usb3") # Example
        # time.sleep(1)
        # at.off("usb3")
        return False # Indicate failure

    at.on("usb3")
    at.on("connect") 

    pattern_matched = at.await_and_confirm_led_pattern(
        pattern=SCRIPT_STARTUP_PATTERN, 
        timeout=AWAIT_FIRST_STATE_TIMEOUT_SCRIPT, 
        clear_buffer=True
    )

    if not pattern_matched:
        script_logger.warning("Startup pattern FAILED to match.")
        # Decide if to continue or stop; here we stop for this example
        return False # Indicate failure
    
    if not at.confirm_led_solid({'red':1, 'green':0, 'blue':0}, minimum=3, timeout=5):
        script_logger.warning("RED solid state NOT confirmed after pattern.")
        return False # Indicate failure
    at.sequence(["key1", "key1", "key2", "key2", "key3", "key3", "key4", "key4", "unlock"])
    time.sleep(3) # Pause after key sequence

    if not at.confirm_led_solid({'green':1}, minimum=5, timeout=15): # Expecting Green to be ON now
        script_logger.warning("GREEN solid state NOT confirmed.")
        return False # Indicate failure
    
    device_info_tuple = find_apricorn_device()
    script_logger.info("Apricorn device info:")
    pprint(device_info_tuple[0])

    at.press("lock")

    if not at.confirm_led_solid({'red':1}, minimum=3, timeout=10): # Expecting Red to be ON after lock
        script_logger.warning("RED solid state (after lock) NOT confirmed.")
        return False # Indicate failure

    at.off("connect")
    
    # Assuming all LEDs should be off after disconnect
    if not at.confirm_led_solid({'red':0, 'green':0, 'blue':0}, minimum=3, timeout=5):
        script_logger.warning("All LEDs OFF state NOT confirmed after disconnect.")
        # This might not be a critical failure for the overall sequence, depends on requirements
    
    # at.off("usb3") # Consider if usb3 should also be turned off here or by atexit
    return True # Indicate overall success of the sequence


def main():
    try:
        success = run_automation_sequence()
            
    except PhidgetException as e:
        script_logger.error(f"A PhidgetException occurred during automation: {e.description} (Code: {e.code})")
        script_logger.error(traceback.format_exc())
    except (NameError, RuntimeError, ValueError) as e: 
        script_logger.error(f"A configuration or runtime error occurred: {e}")
        script_logger.error(traceback.format_exc())
    except Exception as e:
        script_logger.error(f"An unexpected error occurred during automation: {e}")
        script_logger.error(traceback.format_exc())
    finally:
        script_logger.info("--- Simplified Automation Script Finished ---")
        # Note: Cleanup of the 'at' instance is handled by 'atexit' in global_controller.py
        # or could be done explicitly here if 'atexit' is not desired/sufficient.
        # e.g., if at: at.close()

if __name__ == "__main__":
    main()