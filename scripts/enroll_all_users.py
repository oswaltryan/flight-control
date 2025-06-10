# Filename: scripts/enroll_all_users.py

import sys
import os
import logging
from pprint import pprint
import time

# --- Path Setup ---
SCRIPT_DIR_ENROLL = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_ENROLL = os.path.dirname(SCRIPT_DIR_ENROLL)
if PROJECT_ROOT_ENROLL not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_ENROLL)
# --- End Path Setup ---

# This try/except block is for when the script is run directly
try:
    from automation_toolkit import get_at_controller, get_dut, get_fsm
except Exception as e:
    logging.basicConfig(level=logging.CRITICAL)
    logging.critical(f"Failed to import or get controllers from automation_toolkit: {e}", exc_info=True)
    sys.exit("Critical error during setup. See logs.")

script_logger = logging.getLogger("EnrollAndTestUsersScript")

# MODIFICATION: The function now accepts fsm and dut as arguments.
# This allows us to pass in MOCKS during testing.
def run_sequence(fsm, dut):
    """
    Executes a full device setup and test sequence.
    This function contains the core logic and is now testable.
    """
    script_logger.info("--- Starting Full Enrollment & Test Sequence ---")
    
    # 1. Power on
    script_logger.info(f"Initial FSM state: {fsm.state}")
    assert fsm.state == 'OFF', "FSM must start in OFF state for a clean run."
    fsm.power_on()
    script_logger.info(f"FSM state after power on: {fsm.state}")
    assert fsm.state == 'OOB_MODE', "Device must be in OOB_MODE to enroll a new admin."

    # 2. Enroll Admin
    script_logger.info("--- Enrolling Admin PIN ---")
    admin_pin = ['key1', 'key1', 'key2', 'key2', 'key3', 'key3', 'key4', 'key4', 'unlock']
    enroll_admin_ok = fsm.enroll_admin(new_pin=admin_pin)
    assert enroll_admin_ok, "Admin enrollment failed."
    assert fsm.state == 'ADMIN_MODE', "FSM did not transition to ADMIN_MODE."
    script_logger.info("Admin enrollment successful.")
    
    # 3. Enroll Users
    max_users_to_enroll = 1 if dut.fips in [2, 3] else 4
    script_logger.info(f"Enrolling {max_users_to_enroll} user(s).")
    user_pins = [
        ['key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key2', 'unlock'],
        ['key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key3', 'unlock'],
        ['key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key4', 'unlock'],
        ['key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key1', 'key5', 'unlock'],
    ]
    for i in range(max_users_to_enroll):
        user_id = i + 1
        script_logger.info(f"--- Enrolling User {user_id} ---")
        enrolled_id = fsm.enroll_user_pin(new_pin=user_pins[i])
        assert enrolled_id is not None, f"Failed to enroll User {user_id}."
        script_logger.info(f"Successfully enrolled User {user_id} into slot: {enrolled_id}")

    # 4. Power cycle to lock
    script_logger.info("--- Preparing for Unlock/Lock Tests by Power-Cycling ---")
    fsm.power_off()
    assert fsm.state == 'OFF'
    script_logger.info("Device is OFF. Powering back on to reach STANDBY.")
    time.sleep(1)
    fsm.power_on()
    assert fsm.state == 'STANDBY_MODE', f"Device did not reach STANDBY_MODE. State: {fsm.state}"
    script_logger.info(f"Device is ready in {fsm.state}.")
    
    # 5. Unlock/Lock loop
    for user_id in range(1, max_users_to_enroll + 1):
        script_logger.info(f"--- Testing Unlock/Lock for User {user_id} ---")
        unlock_ok = fsm.unlock_user(user_id=user_id)
        assert unlock_ok, f"Unlock for User {user_id} failed."
        assert fsm.state == 'UNLOCKED_USER'
        fsm.lock_user()
        assert fsm.state == 'STANDBY_MODE'
        script_logger.info(f"--- User {user_id} test complete. ---")

    # 6. Reset device
    script_logger.info("--- Performing User Reset ---")
    fsm.unlock_admin()
    assert fsm.state == 'UNLOCKED_ADMIN'
    fsm.lock_admin()
    assert fsm.state == 'ADMIN_MODE'
    reset_ok = fsm.user_reset()
    assert reset_ok, "User reset failed."
    assert fsm.state == 'OOB_MODE'
    script_logger.info("Device successfully reset.")

# MODIFICATION: This block is now ONLY for running the script directly.
# It gets the REAL fsm and dut and passes them to the function.
if __name__ == "__main__":
    fsm_real = get_fsm()
    dut_real = get_dut()
    run_sequence(fsm_real, dut_real)