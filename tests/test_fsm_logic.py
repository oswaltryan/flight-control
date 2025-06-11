# Directory: tests/
# Filename: test_fsm_logic.py

import pytest
from unittest.mock import MagicMock, call, ANY
from camera.led_dictionaries import LEDs
from controllers.flight_control_fsm import SimplifiedDeviceFSM, DeviceUnderTest, TransitionCallbackError

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

def test_brute_force_decrement(fsm, mock_at, dut_instance):
    fsm.state = 'STANDBY_MODE'
    initial_attempts = dut_instance.bruteForceCurrent = 10
    fsm.fail_unlock()
    assert fsm.state == 'STANDBY_MODE'
    assert dut_instance.bruteForceCurrent == initial_attempts - 1

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