# tests/test_fsm_logic.py

import pytest
from unittest.mock import MagicMock

# MODIFICATION: Import directly from the source, NOT from automation_toolkit
from controllers.flight_control_fsm import SimplifiedDeviceFSM, DeviceUnderTest

# We use a mock to replace the real UnifiedController ('at')
# so we don't need any hardware to run these tests.
mock_at = MagicMock()

@pytest.fixture
def fsm():
    """
    This is a pytest "fixture". It creates a fresh FSM instance
    for every single test function, ensuring tests are isolated.
    """
    mock_at.reset_mock()
    return SimplifiedDeviceFSM(at_controller=mock_at)

# --- Test Cases ---

def test_initial_state(fsm):
    """
    GIVEN a new FSM
    WHEN it is initialized
    THEN its state should be 'OFF'.
    """
    assert fsm.state == 'OFF'

def test_full_enrollment_flow(fsm, monkeypatch):
    """
    Tests the high-level state transitions from OOB to ADMIN_MODE.
    This simulates the first part of your script.
    """
    # --- GIVEN ---
    # MODIFICATION: Directly set the state for the test setup
    fsm.state = 'OOB_MODE'
    
    # We tell our mock 'at' controller to pretend its LED checks succeed
    mock_at.await_and_confirm_led_pattern.return_value = True
    mock_at.await_led_state.return_value = True

    # --- WHEN ---
    # We trigger the admin enrollment
    admin_pin = ['key1']*7
    result = fsm.enroll_admin(new_pin=admin_pin)

    # --- THEN ---
    # Assert that the FSM is now in the correct state
    assert fsm.state == 'ADMIN_MODE'
    assert result is True # Check the return value of the callback
    # We can even assert that the correct hardware commands were SENT
    mock_at.press.assert_called_with(['unlock', 'key9'])


def test_lock_admin_from_invalid_state(fsm):
    """
    !!! THIS IS THE TEST THAT CAUGHT THE BUG !!!
    GIVEN an FSM in the ADMIN_MODE state
    WHEN we try to trigger 'lock_admin'
    THEN it should raise a MachineError because it's an invalid transition.
    """
    # MODIFICATION: Directly set the state for the test setup
    fsm.state = 'ADMIN_MODE'
    
    # Use pytest.raises to assert that a specific error IS thrown
    with pytest.raises(Exception, match="Can't trigger event lock_admin from state ADMIN_MODE!"):
        fsm.lock_admin()

def test_lock_admin_from_valid_state(fsm):
    """
    Tests the CORRECT path for locking the admin session.
    """
    # --- GIVEN ---
    # MODIFICATION: Directly set the state for the test setup
    fsm.state = 'UNLOCKED_ADMIN'

    # --- WHEN ---
    # We trigger the event
    fsm.lock_admin()

    # --- THEN ---
    # Assert the FSM transitioned correctly
    assert fsm.state == 'STANDBY_MODE'
    # Assert the lock button was pressed on the (mock) hardware
    mock_at.press.assert_called_with("lock")