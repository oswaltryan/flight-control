# Filename: scripts/my_automation_script.py

# IMPORTANT: If running this script directly, Python needs to find the project root
# to import 'automation_toolkit'. This is typically handled by:
# 1. Running from the project root: `python scripts/my_automation_script.py`
# 2. Or, adding path manipulation at the top of *this* script if run from elsewhere.

import sys
import os
import logging # Already configured by automation_toolkit import

# --- Path Setup if running this script directly and not from project root ---
# This ensures that 'automation_toolkit' in the parent directory can be found.
SCRIPT_DIR_MYSCRIPT = os.path.dirname(os.path.abspath(__file__)) # scripts/
PROJECT_ROOT_MYSCRIPT = os.path.dirname(SCRIPT_DIR_MYSCRIPT) # project_root/
if PROJECT_ROOT_MYSCRIPT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_MYSCRIPT)
# --- End Path Setup ---

# Import the global 'at' controller and 'fsm' from automation_toolkit
# The import of automation_toolkit will set up logging and initialize 'at' and 'fsm'.
try:
    from automation_toolkit import get_at_controller, get_fsm, global_at_logger # Use the specific logger if needed
    at = get_at_controller()
    fsm = get_fsm()
except Exception as e: # Catch potential RuntimeError if 'at' or 'fsm' failed init
    # Fallback basic logging if automation_toolkit's logging failed
    logging.basicConfig(level=logging.CRITICAL)
    logging.critical(f"Failed to import or get controllers from automation_toolkit: {e}", exc_info=True)
    sys.exit("Critical error during setup. See logs.")


# Get a logger for this script (it will use the global config from automation_toolkit)
script_logger = logging.getLogger("MyAutomationScript") # Or use global_at_logger

def run_sequence():
    # if fsm.state == 'OFF':
    #     fsm.power_on() # This is the FSM trigger method
    # else:
    #     script_logger.warning(f"Device not in OFF state as expected, current state: {fsm.state}. Skipping power on.")

    # if fsm.state == "STARTUP_SELF_TEST":
    #     fsm.confirm_standby_mode()

    # if fsm.state == 'STANDBY_MODE':
    #     fsm.power_off()
    # elif fsm.state == 'ERROR_POST_FAILED':
    #     fsm.power_off()
    # else:
    #     script_logger.warning(f"Device in unexpected state: {fsm.state}. Sequence may not run correctly.")

    fsm.power_on()
    fsm.confirm_standby_mode()
    fsm.unlock_admin()
    fsm.lock_admin()
    fsm.power_off()

if __name__ == "__main__":
    # The import of automation_toolkit should have already configured logging.
    # 'at' and 'fsm' should be available.
    run_sequence()
    # Resources held by 'at' should be cleaned up by atexit in automation_toolkit.