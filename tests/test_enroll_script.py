# tests/test_enroll_script.py

import pytest
from unittest.mock import MagicMock, call

# Import the function we want to test
from scripts.enroll_all_users import run_sequence

@pytest.fixture
def mock_dut():
    """ Mocks the DUT object. This runs first. """
    dut = MagicMock()
    # Simulate a 4-user device for this test
    dut.fips = 0
    # Start with an empty admin PIN, like a real new device
    dut.adminPIN = []
    return dut

@pytest.fixture
def mock_fsm(mock_dut): # MODIFICATION: The FSM fixture now depends on the DUT fixture
    """ Mocks the FSM object. """
    fsm = MagicMock()
    fsm.state = 'OFF'
    
    def set_state(new_state):
        fsm.state = new_state
    
    # --- MODIFICATION: Make the side effect functions smarter ---
    
    def power_on_effect():
        # This now behaves like the REAL FSM's conditional transition
        if not mock_dut.adminPIN:
            set_state('OOB_MODE')
        else:
            set_state('STANDBY_MODE')
    
    def enroll_admin_effect(new_pin):
        # Simulate the real callback's behavior: update the DUT model
        mock_dut.adminPIN = new_pin
        set_state('ADMIN_MODE')
        return True

    def unlock_user_effect(user_id):
        set_state('UNLOCKED_USER')
        return True

    def user_reset_effect():
        # Simulate the real callback's behavior: clear the PINs
        mock_dut.adminPIN = []
        set_state('OOB_MODE')
        return True

    fsm.power_on.side_effect = power_on_effect
    fsm.enroll_admin.side_effect = enroll_admin_effect
    fsm.unlock_user.side_effect = unlock_user_effect
    fsm.user_reset.side_effect = user_reset_effect

    fsm.power_off.side_effect = lambda: set_state('OFF')
    fsm.lock_user.side_effect = lambda: set_state('STANDBY_MODE')
    fsm.unlock_admin.side_effect = lambda: set_state('UNLOCKED_ADMIN')
    fsm.lock_admin.side_effect = lambda: set_state('ADMIN_MODE')
    
    return fsm

def test_enroll_script_logic(mock_fsm, mock_dut):
    """
    GIVEN a mocked FSM and DUT
    WHEN the run_sequence function from the script is called
    THEN it should call the FSM methods in the correct sequence.
    """
    # --- WHEN ---
    run_sequence(fsm=mock_fsm, dut=mock_dut)

    # --- THEN ---
    mock_fsm.power_on.assert_has_calls([call(), call()])
    assert mock_fsm.power_on.call_count == 2
    
    mock_fsm.enroll_admin.assert_called_once()
    assert mock_fsm.enroll_user.call_count == 4
    mock_fsm.power_off.assert_called_once()
    assert mock_fsm.unlock_user.call_count == 4
    assert mock_fsm.lock_user.call_count == 4
    mock_fsm.unlock_admin.assert_called_once()
    mock_fsm.lock_admin.assert_called_once()
    mock_fsm.user_reset.assert_called_once()