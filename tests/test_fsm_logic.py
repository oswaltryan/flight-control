# tests/test_fsm_happy_path.py

import pytest
from unittest.mock import MagicMock, call, ANY
from camera.led_dictionaries import LEDs
from controllers.flight_control_fsm import SimplifiedDeviceFSM, DeviceUnderTest

@pytest.fixture
def mock_at():
    """Provides a fresh mock of the hardware controller for each test."""
    at = MagicMock()
    # Default all hardware checks to succeed for happy path testing
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
    dut.bruteForceCurrent = 10
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
    """Test that the FSM initializes to the OFF state."""
    assert fsm.state == 'OFF'

def test_power_on_to_oob_mode(fsm, mock_at):
    """Test the full auto-transition sequence from OFF to OOB_MODE."""
    fsm.power_on()
    assert fsm.state == 'OOB_MODE'
    mock_at.confirm_led_pattern.assert_called_with(LEDs['STARTUP'], clear_buffer=True, replay_extra_context=ANY)
    mock_at.await_and_confirm_led_pattern.assert_called_with(LEDs['ACCEPT_PATTERN'], timeout=ANY, replay_extra_context=ANY)
    mock_at.confirm_led_solid.assert_called_with(LEDs['GREEN_BLUE_STATE'], minimum=ANY, timeout=ANY, replay_extra_context=ANY)

def test_reboot_to_standby_when_enrolled(fsm, dut_instance):
    """Test that a device with a PIN boots into STANDBY_MODE."""
    dut_instance.adminPIN = ['key1', 'key2', 'key3', 'key4', 'key5', 'key6', 'key7']
    fsm.power_on()
    assert fsm.state == 'STANDBY_MODE'

def test_admin_unlock_path(fsm, mock_at, dut_instance):
    """Test the admin unlock transition and enumeration check."""
    dut_instance.adminPIN = ['key1', 'key2', 'key3']
    fsm.state = 'STANDBY_MODE'
    fsm.unlock_admin()
    assert fsm.state == 'UNLOCKED_ADMIN'
    mock_at.sequence.assert_called_with(dut_instance.adminPIN)
    mock_at.await_and_confirm_led_pattern.assert_called_with(LEDs['ENUM'], timeout=ANY, replay_extra_context=ANY)
    mock_at.confirm_enum.assert_called_once()

def test_user_enrollment_and_unlock_path(fsm, mock_at, dut_instance):
    """Test enrolling a user and then successfully unlocking with that user's PIN."""
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

def test_user_enrollment_fails_on_hw_check(fsm, mock_at, dut_instance):
    """Test that user enrollment fails gracefully on a hardware check."""
    # GIVEN
    fsm.state = 'ADMIN_MODE'
    mock_at.await_and_confirm_led_pattern.return_value = False # Simulate HW failure
    # Let's also mock the press method to see if it was called
    mock_at.press = MagicMock()

    # WHEN
    fsm.enroll_user(new_pin=['key1','key2','key3'])
    
    # THEN
    # The most important thing is that the PIN was NOT saved.
    assert dut_instance.userPIN[1] is None
    
    # The state should remain ADMIN_MODE, which it does.
    assert fsm.state == 'ADMIN_MODE'
    
    # We can also assert that the initial key press to start enrollment happened.
    mock_at.press.assert_called_with(['unlock', 'key1'])
    
    # We can assert that the sequence() method for entering the PIN was NEVER called,
    # because the function aborted before that.
    mock_at.sequence.assert_not_called()

def test_user_reset_path(fsm, mock_at, dut_instance):
    """Test that a user reset clears PINs and returns to OOB_MODE."""
    fsm.state = 'ADMIN_MODE'
    dut_instance.adminPIN = ['key1', 'key2', 'key3']
    dut_instance.userPIN[1] = ['key4', 'key5', 'key6']
    reset_ok = fsm.user_reset()
    assert reset_ok is True
    assert fsm.state == 'OOB_MODE'
    assert dut_instance.adminPIN == []
    assert dut_instance.userPIN[1] is None
    mock_at.sequence.assert_called_with([['lock', 'unlock', 'key2']])
    mock_at.confirm_led_solid.assert_any_call(LEDs['KEY_GENERATION'], minimum=ANY, timeout=ANY, replay_extra_context=ANY)
    
def test_last_try_login_from_brute_force(fsm, mock_at):
    """Test the 'last try' escape hatch from BRUTE_FORCE mode."""
    fsm.state = 'BRUTE_FORCE'
    fsm.last_try_login()
    assert fsm.state == 'STANDBY_MODE'
    mock_at.press.assert_called_with(['key5', 'unlock'], duration_ms=ANY)
    mock_at.await_and_confirm_led_pattern.assert_called_with(LEDs["RED_GREEN"], timeout=ANY)
    mock_at.sequence.assert_called_with(['key5', 'key2', 'key7', 'key8', 'key8', 'key7', 'key9', 'unlock'])