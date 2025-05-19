# Filename: automation_toolkit.py (place in project_root, or a common 'utils' or 'core' directory)
import logging
import sys
import os
import atexit # Moved import up

# --- Path Setup for automation_toolkit.py to find 'controllers' AND 'utils' ---
# This assumes automation_toolkit.py is in project_root.
PROJECT_ROOT_FOR_GLOBAL = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT_FOR_GLOBAL not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_FOR_GLOBAL)

# --- IMPORT AND SETUP LOGGING FIRST ---
try:
    from utils.logging_config import setup_logging
    # Call setup_logging() here, before anything else that might log.
    # This establishes the global logging configuration for the entire application.
    setup_logging()
except ImportError as e_log_setup:
    # Fallback basic logging if the main setup fails
    _fallback_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(stream=sys.stderr, level=logging.CRITICAL, format=_fallback_format)
    logging.critical(f"CRITICAL: Logging setup FAILED. Cannot import 'utils.logging_config'. Error: {e_log_setup}. Using basic fallback logging to stderr.", exc_info=True)
    # Depending on policy, you might re-raise e_log_setup or sys.exit() here.
# --- END OF LOGGING SETUP ---

# Now get the logger for this module. It will use the global configuration.
# Name ("GlobalATController") matches an entry in LOG_LEVEL_CONFIG for specific level setting.
global_at_logger = logging.getLogger("GlobalATController")

try:
    from controllers.unified_controller import UnifiedController
except ImportError as e_uc_import:
    global_at_logger.critical(f"Import Error for UnifiedController: {e_uc_import}. Ensure 'controllers/unified_controller.py' exists and paths are correct.", exc_info=True)
    raise # Re-raise after logging

# --- Global Configuration for the 'at' instance ---
DEFAULT_CAMERA_ID = 0
DEFAULT_LED_DISPLAY_ORDER = ["red", "green", "blue"]

# --- Instantiate the Global Controller ---
at = None # Initialize to None
try:
    # This instance 'at' will be created once when automation_toolkit.py is first imported.
    at = UnifiedController(
        camera_id=DEFAULT_CAMERA_ID,
        display_order=DEFAULT_LED_DISPLAY_ORDER,
        # Pass a child logger for UnifiedController's internal messages.
        # This logger ("GlobalATController.UnifiedInstance") can also be configured in LOG_LEVEL_CONFIG.
        logger_instance=global_at_logger.getChild("UnifiedInstance")
    )

except Exception as e_at_create:
    global_at_logger.critical(f"Failed to create global 'at' (UnifiedController) instance: {e_at_create}", exc_info=True)
    # 'at' remains None

def get_at_controller():
    """
    Returns the globally initialized UnifiedController instance.
    """
    if at is None:
        # This condition would be met if the initial instantiation failed.
        raise RuntimeError("Global 'at' controller was not successfully initialized or is None.")
    return at

# --- Optional: Resource cleanup for the global instance ---
def _cleanup_global_at():
    if at is not None and hasattr(at, 'close'):
        try:
            at.close()
            # 'at.close()' itself should log success/failure of its components.
            # global_at_logger.info("Global 'at' controller instance close method called via atexit.")
        except Exception as e_at_close:
            global_at_logger.error(f"Error during at.close() via atexit: {e_at_close}", exc_info=True)

if at is not None: # Only register cleanup if 'at' was successfully created
    atexit.register(_cleanup_global_at)
else:
    global_at_logger.warning("Global 'at' instance is None; atexit cleanup for 'at' not registered.")


# To test this file directly (optional):
if __name__ == "__main__":
    # The setup_logging() at the top of the file has already run.
    # The logger 'global_at_logger' is already configured.
    global_at_logger.info("Testing automation_toolkit.py directly...")
    if at:
        global_at_logger.info(f"Global 'at' instance available. Camera ready: {at.is_camera_ready}")
        # Example of using the global 'at' instance:
        # try:
        #     if at.is_camera_ready:
        #         global_at_logger.info("Attempting a quick camera LED check (manual observation needed)...")
        #         at.await_led_state({"red": 1}, timeout=2.0) # Example call
        # except Exception as e_test:
        #     global_at_logger.error(f"Error during direct test of 'at': {e_test}", exc_info=True)
    else:
        global_at_logger.error("Global 'at' instance is None (failed to initialize). Cannot perform direct tests on 'at'.")
    global_at_logger.info("Exiting automation_toolkit.py direct test.")