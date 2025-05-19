# Filename: global_controller.py (place in project_root, or a common 'utils' or 'core' directory)
import logging
import sys
import os

# --- Path Setup for global_controller.py to find 'controllers' ---
# This assumes global_controller.py is in project_root.
# If it's elsewhere (e.g. project_root/core/global_controller.py), adjust as needed.
PROJECT_ROOT_FOR_GLOBAL = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT_FOR_GLOBAL not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_FOR_GLOBAL)

try:
    from controllers.unified_controller import UnifiedController
except ImportError as e:
    print(f"Critical Import Error in global_controller.py: {e}. Cannot find UnifiedController.", file=sys.stderr)
    print("Ensure 'controllers/unified_controller.py' exists and paths are correct.", file=sys.stderr)
    raise

# --- Global Configuration for the 'at' instance ---
# You can centralize default configurations here.
# Scripts can override these if the UnifiedController allows reconfiguration,
# or you can make these truly fixed for the global instance.

DEFAULT_CAMERA_ID = 0
DEFAULT_LED_DISPLAY_ORDER = ["red", "green", "blue"] # Or load from a config file

# Setup a base logger for the global 'at' instance.
# Individual scripts can still have their own script-specific loggers.
global_at_logger = logging.getLogger("GlobalATController")
if not global_at_logger.hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    global_at_logger.addHandler(handler)
    global_at_logger.setLevel(logging.INFO) # Default level for the global controller

# --- Instantiate the Global Controller ---
try:
    # This instance 'at' will be created once when global_controller.py is first imported.
    at = UnifiedController(
        camera_id=DEFAULT_CAMERA_ID,
        display_order=DEFAULT_LED_DISPLAY_ORDER,
        logger_instance=global_at_logger.getChild("UnifiedInstance") # Give it a child logger
        # Add other default parameters for UnifiedController here if needed:
        # script_map_config=None, # To use default Phidget map
        # led_configs=None,       # To use default LED configs
    )
    global_at_logger.info("Global 'at' (UnifiedController) instance created and initialized.")

except Exception as e:
    global_at_logger.critical(f"Failed to create global 'at' (UnifiedController) instance: {e}")
    import traceback
    global_at_logger.critical(traceback.format_exc())
    # Depending on how critical this is, you might re-raise or set 'at' to None
    at = None # Or raise SystemExit("Failed to initialize global controller.")

def get_at_controller():
    """
    Returns the globally initialized UnifiedController instance.
    This function can also be used to perform any late initialization if needed,
    though the current setup initializes 'at' on import.
    """
    if at is None:
        # This condition would be met if the initial instantiation failed.
        # You might try to re-initialize or raise an error.
        raise RuntimeError("Global 'at' controller was not successfully initialized.")
    return at

# --- Optional: Resource cleanup for the global instance ---
# This is a bit trickier for a truly global instance that isn't managed by a 'with' block.
# `atexit` can be used, but it has limitations (e.g., signal handling).
# For scripts, it's often better if the main script using 'at' calls at.close() explicitly
# in a finally block, or if 'at' itself is designed to be robust to being left open
# (which PhidgetController and LogitechLedChecker generally are by releasing on __del__ or __exit__).

import atexit
def _cleanup_global_at():
    if at is not None and hasattr(at, 'close'):
        global_at_logger.info("Attempting to close global 'at' controller instance on script exit...")
        try:
            at.close()
            global_at_logger.info("Global 'at' controller instance closed via atexit.")
        except Exception as e:
            global_at_logger.error(f"Error closing global 'at' controller via atexit: {e}")

if at is not None: # Only register cleanup if 'at' was successfully created
    atexit.register(_cleanup_global_at)

# You could also provide a manual cleanup function:
# def cleanup_automation_toolkit():
#     _cleanup_global_at()

# To test this file directly (optional):
if __name__ == "__main__":
    print("Testing global_controller.py...")
    if at:
        print(f"Global 'at' instance created. Camera ready: {at.is_camera_ready}")
        # Example: at.on("usb3")
        # time.sleep(0.1)
        # at.off("usb3")
        # print("Test Phidget command executed via global 'at'.")
        # No at.close() here for direct test, atexit should handle it or it's left open.
    else:
        print("Global 'at' instance is None (failed to initialize).")
    print("Exiting global_controller.py test.")