# Filename: automation_toolkit.py (in project root)
import logging
import sys
import os
import atexit

# --- Path Setup for automation_toolkit.py to find 'controllers' AND 'utils' ---
# This assumes automation_toolkit.py is in project_root.
PROJECT_ROOT_FOR_GLOBAL = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT_FOR_GLOBAL not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_FOR_GLOBAL) # Ensures root is in path

# --- IMPORT AND SETUP LOGGING FIRST ---
try:
    from utils.logging_config import setup_logging # utils is found because root is in path
    setup_logging()
except ImportError as e_log_setup:
    # ... (fallback logging) ...
    pass # Placeholder

global_at_logger = logging.getLogger("GlobalATController")

# --- IMPORT CONTROLLERS AND FSM ---
try:
    from controllers.unified_controller import UnifiedController # controllers is found
    from controllers.flight_control_fsm import SimplifiedDeviceFSM # Import your FSM
except ImportError as e_uc_import:
    global_at_logger.critical(f"Import Error for UnifiedController or FSM: {e_uc_import}. Ensure paths are correct.", exc_info=True)
    raise

# --- Global Configuration for the 'at' instance ---
DEFAULT_CAMERA_ID = 0
DEFAULT_LED_DISPLAY_ORDER = ["red", "green", "blue"]

# --- Instantiate the Global Controller ('at') ---
at = None
try:
    at = UnifiedController(
        camera_id=DEFAULT_CAMERA_ID,
        display_order=DEFAULT_LED_DISPLAY_ORDER,
        logger_instance=global_at_logger.getChild("UnifiedInstance")
    )
except Exception as e_at_create:
    global_at_logger.critical(f"Failed to create global 'at' (UnifiedController) instance: {e_at_create}", exc_info=True)

def get_at_controller():
    if at is None:
        raise RuntimeError("Global 'at' controller was not successfully initialized.")
    return at

# --- Instantiate the Global FSM ---
# The FSM needs the 'at' controller.
# It's crucial 'at' is initialized before the FSM if the FSM's __init__ uses 'at'.
fsm = None
if at: # Only initialize FSM if 'at' was successful
    try:
        fsm = SimplifiedDeviceFSM(at_controller=at)
        global_at_logger.info(f"Global FSM initialized. Initial state: {fsm.state}")
    except Exception as e_fsm_create:
        global_at_logger.critical(f"Failed to create global 'fsm' instance: {e_fsm_create}", exc_info=True)
else:
    global_at_logger.error("'at' controller is None. Cannot initialize global FSM.")


def get_fsm():
    if fsm is None:
        raise RuntimeError("Global 'fsm' was not successfully initialized or 'at' controller failed.")
    return fsm

# --- Optional: Resource cleanup ---
def _cleanup_global_at():
    # ... (your existing cleanup for 'at') ...
    pass # Placeholder

if at is not None:
    atexit.register(_cleanup_global_at)
else:
    global_at_logger.warning("Global 'at' instance is None; atexit cleanup for 'at' not registered.")

global_at_logger.info("")
global_at_logger.info("____"*10)
global_at_logger.info("")

# To test this file directly (optional, mainly for checking imports and initializations)
if __name__ == "__main__":
    global_at_logger.info("Testing automation_toolkit.py directly...")
    if at:
        global_at_logger.info(f"Global 'at' instance available. Camera ready: {at.is_camera_ready}")
    else:
        global_at_logger.error("Global 'at' instance is None.")
    if fsm:
        global_at_logger.info(f"Global 'fsm' instance available. Current state: {fsm.state}")
        # Example: Trigger an FSM event if it makes sense for testing
        # if fsm.state == 'OFF':
        #     global_at_logger.info("Attempting to trigger 'power_on_requested' on FSM...")
        #     fsm.power_on_requested()
        #     global_at_logger.info(f"FSM state after power_on_requested: {fsm.state}")
    else:
        global_at_logger.error("Global 'fsm' instance is None.")
    global_at_logger.info("Exiting automation_toolkit.py direct test.")