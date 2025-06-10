# Filename: scripts/enroll_all_users.py

import sys
import os
import logging
from pprint import pprint

# --- Path Setup if running this script directly and not from project root ---
SCRIPT_DIR_ENROLL = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_ENROLL = os.path.dirname(SCRIPT_DIR_ENROLL)
if PROJECT_ROOT_ENROLL not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_ENROLL)
# --- End Path Setup ---

try:
    from automation_toolkit import get_at_controller, get_dut, get_fsm
    at = get_at_controller()
    dut = get_dut()
    fsm = get_fsm()
except Exception as e:
    logging.basicConfig(level=logging.CRITICAL)
    logging.critical(f"Failed to import or get controllers from automation_toolkit: {e}", exc_info=True)
    sys.exit("Critical error during setup. See logs.")

# Get a logger for this script
script_logger = logging.getLogger("EnrollAllUsersScript")

def run_sequence():
    """
    Executes a full enrollment sequence: Admin PIN followed by four User PINs.
    Assumes the device is starting in a fresh, out-of-box state.
    """
    script_logger.info("--- Starting Full Enrollment Sequence ---")
    
    # 1. Power on the device. It should start in OFF and transition to OOB_MODE.
    script_logger.info(f"Initial FSM state: {fsm.state}")
    assert fsm.state == 'OFF', "FSM must start in OFF state for a clean run."
    
    fsm.power_on()
    script_logger.info(f"FSM state after power on: {fsm.state}")
    assert fsm.state == 'OOB_MODE', "Device must be in OOB_MODE to enroll a new admin."

    # 2. Enroll the Admin PIN.
    script_logger.info("--- Enrolling Admin PIN ---")
    # Note: The 'unlock' key is automatically appended by the FSM logic.
    admin_pin = ['key1', 'key1', 'key2', 'key2', 'key3', 'key3', 'key4', 'key4', 'unlock']
    enroll_admin_ok = fsm.enroll_admin(new_pin=admin_pin)
    
    assert enroll_admin_ok, "Admin enrollment failed to return True."
    assert fsm.state == 'ADMIN_MODE', "FSM did not transition to ADMIN_MODE after admin enrollment."
    script_logger.info("Admin enrollment successful. FSM is now in ADMIN_MODE.")
    
    # 3. From ADMIN_MODE, enroll all four User PINs sequentially.
    # The `enroll_user_pin` function will find the next available slot.
    
    # Enroll User 1
    script_logger.info("--- Enrolling User 1 ---")
    user_1_pin = ['key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key2', 'unlock']
    user_1_id = fsm.enroll_user(new_pin=user_1_pin)
    assert user_1_id is not None, "Failed to enroll User 1."
    script_logger.info(f"Successfully enrolled User 1 into logical slot: {user_1_id}")

    # Enroll User 2
    script_logger.info("--- Enrolling User 2 ---")
    user_2_pin = ['key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key3', 'unlock']
    user_2_id = fsm.enroll_user(new_pin=user_2_pin)
    assert user_2_id is not None, "Failed to enroll User 2."
    script_logger.info(f"Successfully enrolled User 2 into logical slot: {user_2_id}")

    # Enroll User 3
    script_logger.info("--- Enrolling User 3 ---")
    user_3_pin = ['key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key4', 'unlock']
    user_3_id = fsm.enroll_user(new_pin=user_3_pin)
    assert user_3_id is not None, "Failed to enroll User 3."
    script_logger.info(f"Successfully enrolled User 3 into logical slot: {user_3_id}")

    # Enroll User 4
    script_logger.info("--- Enrolling User 4 ---")
    user_4_pin = ['key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key5', 'unlock']
    user_4_id = fsm.enroll_user(new_pin=user_4_pin)
    assert user_4_id is not None, "Failed to enroll User 4."
    script_logger.info(f"Successfully enrolled User 4 into logical slot: {user_4_id}")

    # 4. Final verification.
    script_logger.info("--- All Enrollments Complete ---")
    script_logger.info(f"Final FSM state: {fsm.state}")
    script_logger.info("Final state of the DUT's tracked User PINs:")
    pprint(dut.userPIN)

    fsm.user_reset()

if __name__ == "__main__":
    run_sequence()