# Filename: scripts/my_automation_script.py

import sys
import os
import logging # Already configured by automation_toolkit import
from pprint import pprint

# --- Path Setup if running this script directly and not from project root ---
SCRIPT_DIR_MYSCRIPT = os.path.dirname(os.path.abspath(__file__)) # scripts/
PROJECT_ROOT_MYSCRIPT = os.path.dirname(SCRIPT_DIR_MYSCRIPT) # project_root/
if PROJECT_ROOT_MYSCRIPT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_MYSCRIPT)
# --- End Path Setup ---

try:
    from automation_toolkit import get_at_controller, get_dut, get_fsm, global_at_logger # Use the specific logger if needed
    at = get_at_controller()
    dut = get_dut()
    fsm = get_fsm()
except Exception as e: # Catch potential RuntimeError if 'at' or 'fsm' failed init
    logging.basicConfig(level=logging.CRITICAL)
    logging.critical(f"Failed to import or get controllers from automation_toolkit: {e}", exc_info=True)
    sys.exit("Critical error during setup. See logs.")

# Get a logger for this script (it will use the global config from automation_toolkit)
script_logger = logging.getLogger("MyAutomationScript") # Or use global_at_logger

def run_sequence():
    fsm.power_on()
    fsm.unlock_admin()
    fsm.lock_admin()
    fsm.power_off()

if __name__ == "__main__":
    run_sequence()
