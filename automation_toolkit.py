# Directory: /
# Filename: automation_toolkit.py

# Filename: automation_toolkit.py (in project root)
import logging
import sys
import os
import atexit
import datetime # Make sure datetime is imported

# --- Path Setup & Run Context ---
PROJECT_ROOT_FOR_GLOBAL = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT_FOR_GLOBAL not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_FOR_GLOBAL)

# Format: YYYY-MM-DD_HH-MM-SS
RUN_TIMESTAMP = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
RUN_OUTPUT_DIR = os.path.join(PROJECT_ROOT_FOR_GLOBAL, "logs", RUN_TIMESTAMP)
os.makedirs(RUN_OUTPUT_DIR, exist_ok=True) # Create the directory

# --- IMPORT AND SETUP LOGGING FIRST ---
try:
    from utils.logging_config import setup_logging
    # Pass the specific log file path for this run
    run_log_file = os.path.join(RUN_OUTPUT_DIR, "main.log")
    setup_logging(log_file_path=run_log_file, log_file_mode="w") # "w" to start fresh for each run
except ImportError as e_log_setup:
    # Basic fallback logging if setup_logging fails
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logging.getLogger().critical(f"Failed to import or run setup_logging: {e_log_setup}. Using basic logging.", exc_info=True)
    pass 

global_at_logger = logging.getLogger("GlobalATController")

# --- IMPORT CONTROLLERS AND FSM ---
try:
    from controllers.unified_controller import UnifiedController
    from controllers.flight_control_fsm import DeviceUnderTest, ApricornDeviceFSM
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
        logger_instance=global_at_logger.getChild("UnifiedInstance"),
        enable_instant_replay=True,
        replay_output_dir=RUN_OUTPUT_DIR 
    )
except Exception as e_at_create:
    global_at_logger.critical(f"Failed to create global 'at' (UnifiedController) instance: {e_at_create}", exc_info=True)

def get_at_controller():
    if at is None:
        raise RuntimeError("Global 'at' controller was not successfully initialized.")
    return at

# --- Instantiate the Global DUT ---
dut = None
try:
    dut = DeviceUnderTest()
    global_at_logger.info(f"Global DUT initialized.")
except Exception as e_dut_create:
    global_at_logger.critical(f"Failed to create global 'dut' instance: {e_dut_create}", exc_info=True)


def get_dut():
    if dut is None:
        raise RuntimeError("Global 'dut' was not successfully initialized.")
    return dut

# --- Instantiate the Global FSM ---
# The FSM needs the 'at' controller.
# It's crucial 'at' is initialized before the FSM if the FSM's __init__ uses 'at'.
fsm = None
if at: # Only initialize FSM if 'at' was successful
    try:
        fsm = ApricornDeviceFSM(at_controller=at)
        global_at_logger.info(f"Global FSM initialized. Initial state: {fsm.state}")
    except Exception as e_fsm_create:
        global_at_logger.critical(f"Failed to create global 'fsm' instance: {e_fsm_create}", exc_info=True)
        # fsm remains None
else:
    global_at_logger.error("'at' controller is None. Cannot initialize global FSM.")


def get_fsm():
    if fsm is None:
        raise RuntimeError("Global 'fsm' was not successfully initialized or 'at' controller failed.")
    return fsm


# --- Optional: Resource cleanup ---
def _cleanup_global_at():
    if at and hasattr(at, 'close'):
        try:
            at.close()
            global_at_logger.info("Global 'at' resources closed successfully.")
        except Exception as e_at_close:
            global_at_logger.error(f"Error during global 'at' cleanup: {e_at_close}", exc_info=True)
    elif at:
        global_at_logger.warning("Global 'at' instance exists but has no 'close' method.")
    else:
        pass # No 'at' instance to cleanup, already logged or handled

if 'pytest' not in sys.modules:
    if at is not None: # Check if 'at' was successfully created before registering cleanup
        atexit.register(_cleanup_global_at)
    else:
        global_at_logger.warning("Global 'at' instance is None; atexit cleanup for 'at' not registered.")
else:
    global_at_logger.debug("Pytest is running. Skipping atexit registration for 'at' controller.")

global_at_logger.info("")
global_at_logger.info("____"*10)
global_at_logger.info("")

# To test this file directly (optional, mainly for checking imports and initializations)
if __name__ == "__main__":
    global_at_logger.info("Testing automation_toolkit.py directly...")
    if at:
        global_at_logger.info(f"Global 'at' instance available. Camera ready: {at.is_camera_ready}")
        global_at_logger.info(f"  'at' instance effective LED duration tolerance: {at.effective_led_duration_tolerance:.3f}s")
    else:
        global_at_logger.error("Global 'at' instance is None.")
    if fsm:
        global_at_logger.info(f"Global 'fsm' instance available. Current state: {fsm.state}")
        # Example: Trigger an FSM event if it makes sense for testing
        # if fsm.state == 'OFF':
        #     global_at_logger.info("Attempting to trigger 'power_on_requested' on FSM...")
        #     fsm.power_on_requested() # Ensure this method exists or use a valid trigger
        #     global_at_logger.info(f"FSM state after power_on_requested: {fsm.state}")
    else:
        global_at_logger.error("Global 'fsm' instance is None.")
    global_at_logger.info("Exiting automation_toolkit.py direct test.")