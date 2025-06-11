# Directory: tests/
# Filename: test_fsm_logic.py

import pytest
from unittest.mock import MagicMock, call, ANY
from camera.led_dictionaries import LEDs
from controllers.flight_control_fsm import SimplifiedDeviceFSM, DeviceUnderTest, TransitionCallbackError
from transitions.core import MachineError

@pytest.fixture
def mock_at():
    """Provides a fresh mock of the hardware controller for each test."""
    at = MagicMock()
    at.confirm_led_pattern.return_value = True
    at.await_and_confirm_led_pattern.return_value = True
    at.await_led_state.return_value = True
    at.confirm_led_solid.return_value = True
    at.confirm_enum.return_value = True
    return at

@pytest.fixture
def dut_instance():
    """Provides a fresh, clean instance of the DUT for each test."""
    dut = DeviceUnderTest()
    dut.adminPIN = []
    dut.userPIN = {1: None, 2: None, 3: None, 4: None}
    dut.bruteForceCounter = 20
    dut.bruteForceCurrent = 20
    dut.provisionLock = False
    dut.userForcedEnrollment = False
    dut.selfDestructPIN = []
    return dut

@pytest.fixture
def fsm(mock_at, dut_instance, monkeypatch):
    """
    Creates a fresh FSM instance for each test, ensuring the test uses
    its own isolated DUT instance.
    """
    monkeypatch.setattr('controllers.flight_control_fsm.DUT', dut_instance)
    return SimplifiedDeviceFSM(at_controller=mock_at)

# --- Happy Path Tests ---

def test_initial_state(fsm):
    assert fsm.state == 'OFF'

def test_power_on_to_oob_mode(fsm, mock_at):
    fsm.power_on()
    assert fsm.state == 'OOB_MODE'
    mock_at.confirm_led_pattern.assert_called_with(LEDs['STARTUP'], clear_buffer=True, replay_extra_context=ANY)
    mock_at.await_and_confirm_led_pattern.assert_called_with(LEDs['ACCEPT_PATTERN'], timeout=ANY, replay_extra_context=ANY)
    mock_at.confirm_led_solid.assert_called_with(LEDs['GREEN_BLUE_STATE'], minimum=ANY, timeout=ANY, replay_extra_context=ANY)

def test_reboot_to_standby_when_enrolled(fsm, dut_instance):
    dut_instance.adminPIN = ['key1', 'key2', 'key3', 'key4', 'key5', 'key6', 'key7']
    fsm.power_on()
    assert fsm.state == 'STANDBY_MODE'

def test_admin_unlock_path(fsm, mock_at, dut_instance):
    dut_instance.adminPIN = ['key1', 'key2', 'key3']
    fsm.state = 'STANDBY_MODE'
    fsm.unlock_admin()
    assert fsm.state == 'UNLOCKED_ADMIN'
    mock_at.sequence.assert_called_with(dut_instance.adminPIN)
    mock_at.await_and_confirm_led_pattern.assert_called_with(LEDs['ENUM'], timeout=ANY, replay_extra_context=ANY)
    mock_at.confirm_enum.assert_called_once()

def test_user_enrollment_and_unlock_path(fsm, mock_at, dut_instance):
    fsm.state = 'ADMIN_MODE'
    user_pin = ['key7', 'key7', 'key7', 'key7', 'key7', 'key7', 'key7']
    result_id = fsm.enroll_user(new_pin=user_pin)
    assert fsm.state == 'ADMIN_MODE'
    assert result_id == 1
    assert dut_instance.userPIN[1] is not None
    fsm.lock_admin()
    assert fsm.state == 'STANDBY_MODE'
    fsm.unlock_user(user_id=1)
    assert fsm.state == 'UNLOCKED_USER'
    mock_at.sequence.assert_called_with(dut_instance.userPIN[1])
    mock_at.confirm_enum.assert_called_once()

def test_user_reset_path(fsm, mock_at, dut_instance):
    fsm.state = 'ADMIN_MODE'
    dut_instance.adminPIN = ['key1', 'key2', 'key3']
    dut_instance.userPIN[1] = ['key4', 'key5', 'key6']
    fsm.user_reset()
    assert fsm.state == 'OOB_MODE'
    assert dut_instance.adminPIN == []
    assert dut_instance.userPIN[1] is None
    mock_at.sequence.assert_called_with([['lock', 'unlock', 'key2']])
    mock_at.confirm_led_solid.assert_any_call(LEDs['KEY_GENERATION'], minimum=ANY, timeout=ANY, replay_extra_context=ANY)
    
def test_last_try_login_from_brute_force(fsm, mock_at, dut_instance):
    fsm.state = 'BRUTE_FORCE'
    dut_instance.bruteForceCurrent = dut_instance.bruteForceCounter / 2
    fsm.last_try_login()
    assert fsm.state == 'STANDBY_MODE'
    mock_at.press.assert_called_with(['key5', 'unlock'], duration_ms=ANY)
    mock_at.await_and_confirm_led_pattern.assert_called_with(LEDs["RED_GREEN"], timeout=ANY)
    mock_at.sequence.assert_called_with(['key5', 'key2', 'key7', 'key8', 'key8', 'key7', 'key9', 'unlock'])

def test_admin_mode_login(fsm, mock_at, dut_instance):
    fsm.state = 'STANDBY_MODE'
    dut_instance.adminPIN = ['key1', 'key2', 'key3']
    fsm.admin_mode_login()
    assert fsm.state == 'ADMIN_MODE'
    mock_at.press.assert_called_with(['key0', 'unlock'], duration_ms=6000)
    mock_at.confirm_led_pattern.assert_called_with(LEDs['RED_LOGIN'], clear_buffer=True, replay_extra_context=ANY)
    mock_at.sequence.assert_called_with(dut_instance.adminPIN)

def test_user_forced_enrollment_path(fsm, dut_instance):
    dut_instance.userForcedEnrollment = True
    dut_instance.adminPIN = ['key1', 'key2', 'key3']
    fsm.power_on()
    assert fsm.state == 'USER_FORCED_ENROLLMENT'

def test_self_destruct_path(fsm, mock_at, dut_instance):
    fsm.state = 'USER_FORCED_ENROLLMENT'
    dut_instance.selfDestructPIN = ['key9', 'key8', 'key7']
    fsm.self_destruct()
    assert fsm.state == 'UNLOCKED_ADMIN'
    mock_at.sequence.assert_called_with(dut_instance.selfDestructPIN)
    
# --- Sad Path and Edge Case Tests ---

def test_power_on_failure_path(fsm, mock_at):
    mock_at.confirm_led_pattern.return_value = False
    with pytest.raises(TransitionCallbackError):
        fsm.power_on()
    assert fsm.state == 'OFF' # State should not have changed

def test_admin_unlock_fails_on_hw_check(fsm, mock_at, dut_instance):
    fsm.state = 'STANDBY_MODE'
    dut_instance.adminPIN = ['key1', 'key2', 'key3']
    mock_at.await_and_confirm_led_pattern.return_value = False
    with pytest.raises(TransitionCallbackError):
        fsm.unlock_admin()
    assert fsm.state == 'STANDBY_MODE' # State should not have changed

def test_user_enrollment_fails_on_hw_check(fsm, mock_at, dut_instance):
    fsm.state = 'ADMIN_MODE'
    mock_at.await_and_confirm_led_pattern.return_value = False
    mock_at.press = MagicMock()
    with pytest.raises(TransitionCallbackError):
        fsm.enroll_user(new_pin=['key1','key2','key3'])
    assert dut_instance.userPIN[1] is None
    assert fsm.state == 'ADMIN_MODE'
    mock_at.press.assert_called_with(['unlock', 'key1'])
    mock_at.sequence.assert_not_called()

def test_lock_from_admin_mode(fsm, mock_at):
    """Test locking the device from ADMIN_MODE returns it to STANDBY_MODE."""
    # GIVEN
    fsm.state = 'ADMIN_MODE'

    # WHEN
    fsm.lock_admin()

    # THEN
    assert fsm.state == 'STANDBY_MODE'
    mock_at.press.assert_called_with("lock")
    # Verify the on_enter_STANDBY_MODE callback was triggered
    mock_at.confirm_led_solid.assert_called_with(LEDs['STANDBY_MODE'], minimum=ANY, timeout=ANY, replay_extra_context=ANY)

def test_post_pass_to_standby(fsm, mock_at, dut_instance):
    """Test that post_pass goes to STANDBY_MODE if an admin PIN is set."""
    # GIVEN
    fsm.state = 'POWER_ON_SELF_TEST'
    dut_instance.adminPIN = ['key1', 'key2', 'key3', 'key4', 'key5', 'key6', 'key7']

    # WHEN
    fsm.post_pass()

    # THEN
    assert fsm.state == 'STANDBY_MODE'
    # Verify the on_enter_STANDBY_MODE callback was triggered by the transition
    mock_at.confirm_led_solid.assert_called_with(LEDs['STANDBY_MODE'], minimum=ANY, timeout=ANY, replay_extra_context=ANY)

def test_admin_enrollment_success(fsm, mock_at, dut_instance):
    """
    Tests the full, successful admin enrollment procedure from OOB_MODE,
    covering the `admin_enrollment` callback thoroughly.
    """
    # GIVEN
    fsm.state = 'OOB_MODE'
    # FIX: Correctly formatted PIN
    new_admin_pin = ['key1','key2','key3','key4','key5','key6','key7']
    
    # All hardware checks should pass for a successful enrollment
    mock_at.await_and_confirm_led_pattern.side_effect = [
        True, # For GREEN_BLUE pattern
        True, # For ACCEPT_PATTERN after first entry
        True  # For GREEN_BLUE pattern after first entry
    ]
    mock_at.await_led_state.return_value = True # For final ACCEPT_STATE

    # WHEN
    # The enroll_admin function does not add 'unlock' itself, so we don't add it here
    fsm.enroll_admin(new_pin=new_admin_pin)

    # THEN
    # 1. The FSM should be in ADMIN_MODE
    assert fsm.state == 'ADMIN_MODE'
    
    # 2. The DUT model should be updated
    assert dut_instance.adminPIN == new_admin_pin
    
    # 3. All hardware calls should have been made in order
    mock_at.press.assert_called_once_with(['unlock', 'key9'])
    mock_at.sequence.assert_has_calls([
        call(new_admin_pin), # First entry
        call(new_admin_pin)  # Confirmation entry
    ])
    mock_at.await_and_confirm_led_pattern.assert_called()
    mock_at.await_led_state.assert_called_once_with(LEDs['ACCEPT_STATE'], timeout=ANY, replay_extra_context=ANY)

def test_enroll_admin_from_oob(fsm, mock_at, dut_instance):
    """
    Test the successful enrollment of an admin from the OOB_MODE state.
    This covers the `enroll_admin` trigger and its callback.
    """
    # GIVEN
    fsm.state = 'OOB_MODE'
    # FIX: Correctly formatted PIN
    new_pin = ['key1', 'key2', 'key3', 'key4', 'key5', 'key6', 'key7']
    # All hardware checks must pass for a successful enrollment
    mock_at.await_and_confirm_led_pattern.return_value = True
    mock_at.await_led_state.return_value = True

    # WHEN
    fsm.enroll_admin(new_pin=new_pin)

    # THEN
    assert fsm.state == 'ADMIN_MODE'
    assert dut_instance.adminPIN == new_pin
    # Check that the sequence of hardware operations is correct
    mock_at.press.assert_called_once_with(['unlock', 'key9'])
    assert mock_at.sequence.call_count == 2
    mock_at.sequence.assert_called_with(new_pin)

def test_full_enrollment_flow(fsm, mock_at, dut_instance):
    """
    Test a complete flow: power on -> enroll admin -> enroll user -> lock -> standby.
    This covers multiple transitions and callbacks.
    """
    # 1. Power on to OOB
    fsm.power_on()
    assert fsm.state == 'OOB_MODE'

    # 2. Enroll Admin
    # FIX: Correctly formatted PIN
    admin_pin = ['key1','key2','key3','key4','key5','key6','key7']
    # Set mocks for successful admin enrollment
    mock_at.await_and_confirm_led_pattern.return_value = True
    mock_at.await_led_state.return_value = True
    fsm.enroll_admin(new_pin=admin_pin)
    assert fsm.state == 'ADMIN_MODE'
    assert dut_instance.adminPIN == admin_pin

    # 3. Enroll User from Admin Mode
    # FIX: Correctly formatted PIN, without 'unlock' as the function adds it
    user_pin = ['key8','key8','key8','key8','key8','key8','key8']
    # Set mocks for successful user enrollment
    fsm.enroll_user(new_pin=user_pin)
    assert fsm.state == 'ADMIN_MODE' # Stays in admin mode
    # The user_enrollment function adds 'unlock' to the stored PIN
    assert dut_instance.userPIN[1] == user_pin + ['unlock']
    
    # 4. Lock from Admin Mode
    fsm.lock_admin()
    assert fsm.state == 'STANDBY_MODE'

def test_brute_force_decrement(fsm, mock_at, dut_instance):
    fsm.state = 'STANDBY_MODE'
    initial_attempts = dut_instance.bruteForceCurrent = 10
    fsm.fail_unlock()
    assert fsm.state == 'STANDBY_MODE'
    assert dut_instance.bruteForceCurrent == initial_attempts - 1

def test_lock_admin_from_unlocked_state(fsm, mock_at):
    """
    Tests locking the device from the UNLOCKED_ADMIN state. This covers a
    different source state for the 'lock_admin' trigger.
    """
    # GIVEN
    fsm.state = 'UNLOCKED_ADMIN'

    # WHEN
    fsm.lock_admin()

    # THEN
    assert fsm.state == 'STANDBY_MODE'
    mock_at.press.assert_called_with("lock")
    # Verify the on_enter_STANDBY_MODE callback was triggered
    mock_at.confirm_led_solid.assert_called_with(LEDs['STANDBY_MODE'], minimum=ANY, timeout=ANY, replay_extra_context=ANY)

def test_post_fail_transition(fsm):
    """
    Tests the simple transition from POWER_ON_SELF_TEST to ERROR_MODE.
    """
    # GIVEN
    fsm.state = 'POWER_ON_SELF_TEST'

    # WHEN
    fsm.post_fail()

    # THEN
    assert fsm.state == 'ERROR_MODE'

def test_lock_admin_from_invalid_state(fsm, mock_at):
    """
    Tests that calling lock_admin from an invalid state (like OOB_MODE)
    raises a MachineError and does not change the state.
    """
    # GIVEN
    fsm.state = 'OOB_MODE'

    # WHEN / THEN
    # The 'transitions' library correctly raises an error on an invalid trigger.
    # We assert that this specific error is raised.
    with pytest.raises(MachineError, match="Can't trigger event lock_admin from state OOB_MODE!"):
        fsm.lock_admin()

    # Finally, assert that the state did not change and no hardware was touched.
    assert fsm.state == 'OOB_MODE'
    mock_at.press.assert_not_called()

# def test_user_reset_path_success(fsm, mock_at, dut_instance):
#     """
#     Tests that a successful user reset clears PINs and returns to OOB_MODE.
#     This is the happy path.
#     """
#     # GIVEN
#     fsm.state = 'ADMIN_MODE'
#     dut_instance.adminPIN = ['key1', 'key2', 'key3']
#     dut_instance.userPIN[1] = ['key4', 'key5', 'key6']
#     # Ensure the hardware check for the reset pattern passes
#     mock_at.confirm_led_solid.return_value = True

#     # WHEN
#     fsm.user_reset()

#     # THEN
#     assert fsm.state == 'OOB_MODE'
#     assert dut_instance.adminPIN == []
#     assert dut_instance.userPIN[1] is None
#     mock_at.sequence.assert_called_with([['lock', 'unlock', 'key2']])
#     mock_at.confirm_led_solid.assert_called_with(LEDs["KEY_GENERATION"], minimum=ANY, timeout=ANY, replay_extra_context=ANY)

def test_user_reset_path_fails_on_hw_check(fsm, mock_at, dut_instance):
    """
    Tests that a user reset fails if the hardware confirmation pattern is not seen.
    This covers the failure branch within the do_user_reset callback.
    """
    # GIVEN
    fsm.state = 'ADMIN_MODE'
    dut_instance.adminPIN = ['key1', 'key2', 'key3']
    # Ensure the hardware check for the reset pattern FAILS
    mock_at.confirm_led_solid.return_value = False

    # WHEN / THEN
    with pytest.raises(TransitionCallbackError, match="Failed to observe user reset confirmation pattern"):
        fsm.user_reset()

    # Assert that state has not changed and PINs were not cleared
    assert fsm.state == 'ADMIN_MODE'
    assert dut_instance.adminPIN == ['key1', 'key2', 'key3']

# def test_user_enrollment_success_from_admin_mode(fsm, mock_at, dut_instance):
#     """
#     Tests the full, successful user enrollment procedure from ADMIN_MODE.
#     This covers all success branches of the `user_enrollment` callback (lines 507-550).
#     """
#     # GIVEN
#     fsm.state = 'ADMIN_MODE'
#     user_pin = ['key1', 'key2', 'key3', 'key4', 'key5', 'key6', 'key7']
    
#     # Ensure all hardware checks for a successful enrollment pass
#     mock_at.await_and_confirm_led_pattern.return_value = True
#     mock_at.confirm_led_solid.return_value = True

#     # WHEN
#     result_id = fsm.enroll_user(new_pin=user_pin)

#     # THEN
#     # 1. The FSM should remain in ADMIN_MODE
#     assert fsm.state == 'ADMIN_MODE'
    
#     # 2. A valid user ID should be returned
#     assert result_id == 1
    
#     # 3. The DUT model should be updated with the new PIN and the 'unlock' key
#     assert dut_instance.userPIN[1] == user_pin + ['unlock']
    
#     # 4. Verify the correct sequence of hardware interactions
#     mock_at.press.assert_called_once_with(['unlock', 'key1'])
#     # The PIN should be entered twice (initial and confirmation)
#     assert mock_at.sequence.call_count == 2
#     mock_at.sequence.assert_called_with(user_pin)
#     # The final solid green check should be called
#     mock_at.confirm_led_solid.assert_called_once_with(LEDs["ACCEPT_STATE"], minimum=ANY, timeout=ANY, replay_extra_context=ANY)


def test_enter_admin_mode_fails_on_hw_check(fsm, mock_at, dut_instance):
    """
    Tests that entering admin mode fails if the hardware check for the
    RED_LOGIN pattern fails. This covers the failure branch in `enter_admin_mode` (lines 483-486).
    """
    # GIVEN
    fsm.state = 'STANDBY_MODE'
    dut_instance.adminPIN = ['key1', 'key2', 'key3']
    # Make the specific hardware check for RED_LOGIN fail
    mock_at.confirm_led_pattern.return_value = False

    # WHEN / THEN
    with pytest.raises(TransitionCallbackError, match="Failed Admin Mode Login LED confirmation."):
        fsm.admin_mode_login()
    
    # Assert state has not changed and no PIN was sent
    assert fsm.state == 'STANDBY_MODE'
    mock_at.press.assert_called_once_with(['key0', 'unlock'], duration_ms=6000)
    mock_at.confirm_led_pattern.assert_called_once_with(LEDs['RED_LOGIN'], clear_buffer=True, replay_extra_context=ANY)
    mock_at.sequence.assert_not_called()

# def test_brute_force_entry(fsm, mock_at, dut_instance):
#     # GIVEN
#     fsm.state = 'STANDBY_MODE'
#     dut_instance.bruteForceCurrent = 1
#     mock_at.await_and_confirm_led_pattern.return_value = True

#     # WHEN
#     fsm.fail_unlock()

#     # THEN
#     assert dut_instance.bruteForceCurrent == 0
#     assert fsm.state == 'BRUTE_FORCE'
#     # Verify that the correct LED pattern was checked for
#     mock_at.await_and_confirm_led_pattern.assert_called_with(LEDs['REJECT'], timeout=ANY)

# def test_bricking_on_brute_force_entry(fsm, mock_at, dut_instance):
#     fsm.state = 'STANDBY_MODE'
#     dut_instance.bruteForceCurrent = 1
#     dut_instance.provisionLock = True
#     fsm.fail_unlock()
#     assert dut_instance.bruteForceCurrent == 0
#     assert fsm.state == 'BRICKED'