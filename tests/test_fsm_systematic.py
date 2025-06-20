# Directory: tests/
# Filename: test_fsm_systematic.py

#############################################################
##
## This test file is designed to systematically cover every function
## in controllers/flight_control_fsm.py.
##
## Run this test with the following command:
## pytest tests/test_fsm_systematic.py --cov=controllers.flight_control_fsm --cov-report term-missing
##
#############################################################

import pytest
from unittest.mock import MagicMock, call, ANY, patch
import json
import io
import importlib
import time

# --- Module and Class Imports ---
from controllers import flight_control_fsm
from controllers.flight_control_fsm import (
    ApricornDeviceFSM, DeviceUnderTest, TransitionCallbackError, CallableCondition
)
from camera.led_dictionaries import LEDs
from transitions import Machine as StandardMachine

# Handle optional import for diagramming
try:
    from transitions.extensions import GraphMachine
    DIAGRAM_TOOLS_INSTALLED = True
except ImportError:
    GraphMachine = None
    DIAGRAM_TOOLS_INSTALLED = False

# --- Top-Level Test Fixtures ---

@pytest.fixture(autouse=True)
def ensure_device_properties(monkeypatch):
    """
    Auto-running fixture to ensure DEVICE_PROPERTIES is always loaded
    correctly, preventing side-effects from module reload tests.
    """
    json_path = flight_control_fsm._json_path
    with open(json_path, 'r') as f:
        real_properties = json.load(f)
    monkeypatch.setattr(flight_control_fsm, 'DEVICE_PROPERTIES', real_properties)

@pytest.fixture
def mock_at():
    """Provides a fresh mock of the hardware controller for each test."""
    at = MagicMock()
    # Default all mock hardware calls to succeed
    at.confirm_led_pattern.return_value = True
    at.await_and_confirm_led_pattern.return_value = True
    at.await_led_state.return_value = True
    at.confirm_led_solid.return_value = True
    at.confirm_led_solid_strict.return_value = True
    at.confirm_drive_enum.return_value = True
    at.confirm_device_enum.return_value = True
    at.scanned_serial_number = "TEST_SERIAL_123"
    return at

@pytest.fixture
def dut_instance(mock_at):
    """Provides a fresh, clean instance of the DUT for each test."""
    with patch('controllers.flight_control_fsm.UnifiedController', return_value=mock_at):
        dut = DeviceUnderTest(at_controller=mock_at)
    return dut

@pytest.fixture
def fsm(mock_at, dut_instance):
    """Creates a fresh FSM instance using the mocked DUT and AT controller."""
    fsm_instance = ApricornDeviceFSM(at_controller=mock_at)
    fsm_instance.dut = dut_instance
    return fsm_instance

# Helper to get the reloaded exception class
def get_reloaded_exception():
    return flight_control_fsm.TransitionCallbackError

# =============================================================================
# === 0. Tests for Module Setup and Helper Classes
# =============================================================================
class TestModuleAndHelpers:
    """Tests for module-level setup and helper classes like CallableCondition."""

    def test_callable_condition_repr(self):
        """Test the __repr__ method for correct string formatting."""
        condition = CallableCondition(func=lambda: True, name="my_test_condition")
        assert repr(condition) == "<CallableCondition: my_test_condition>"

    @pytest.mark.parametrize("diagram_mode_env, expected_class_name", [
        # Case 1: Diagram mode is ON
        pytest.param(
            'true',
            'GraphMachine',
            marks=pytest.mark.skipif(not DIAGRAM_TOOLS_INSTALLED, reason="Diagramming libraries not installed.")
        ),
        # Case 2: Diagram mode is OFF
        ('false', 'Machine'),
        # Case 3: Environment variable is not set
        (None, 'Machine'),
    ])
    def test_conditional_machine_import(self, monkeypatch, diagram_mode_env, expected_class_name):
        """
        GIVEN a specific FSM_DIAGRAM_MODE environment variable setting
        WHEN the flight_control_fsm module is reloaded
        THEN the correct Machine class is imported and used.
        """
        # GIVEN: Set or delete the environment variable
        if diagram_mode_env is None:
            monkeypatch.delenv("FSM_DIAGRAM_MODE", raising=False)
        else:
            monkeypatch.setenv("FSM_DIAGRAM_MODE", diagram_mode_env)

        # WHEN: Reload the module to trigger the conditional import
        importlib.reload(flight_control_fsm)

        # THEN: Inspect the reloaded module to see which class was aliased to 'Machine'
        # We check the class name as a string to avoid object identity issues.
        assert flight_control_fsm.Machine.__name__ == expected_class_name

class TestModuleLoading:
    """Tests for failures during module loading."""

    @patch('builtins.open', new_callable=MagicMock)
    def test_load_config_file_not_found(self, mock_open, monkeypatch):
        """Test module load failure when JSON file is not found."""
        mock_open.side_effect = FileNotFoundError
        with pytest.raises(FileNotFoundError):
            importlib.reload(flight_control_fsm)

    @patch('builtins.open', new_callable=MagicMock)
    def test_load_config_json_decode_error(self, mock_open, monkeypatch):
        """Test module load failure on JSON syntax error."""
        # Simulate reading a file with invalid JSON
        mock_file = MagicMock()
        mock_file.read.return_value = "{'invalid': 'json',}" # Invalid JSON
        mock_open.return_value.__enter__.return_value = mock_file
        
        with pytest.raises(json.JSONDecodeError):
            importlib.reload(flight_control_fsm)
            
    @patch('builtins.open', new_callable=MagicMock)
    def test_load_config_unexpected_error(self, mock_open, monkeypatch):
        """Test module load failure on an unexpected exception."""
        mock_open.side_effect = Exception("A random error occurred")
        with pytest.raises(Exception, match="A random error occurred"):
            importlib.reload(flight_control_fsm)

# =============================================================================
# === 1. Tests for DeviceUnderTest Class
# =============================================================================
class TestDeviceUnderTest:
    """Unit tests for the DeviceUnderTest state model class."""

    def test_init(self, dut_instance, mock_at):
        """Test that __init__ correctly assigns properties from the loaded JSON."""
        assert dut_instance.at == mock_at
        assert dut_instance.name == "padlock3-3637"
        assert dut_instance.bridge_fw == "0510"
        assert dut_instance.fips == 0
        assert dut_instance.scanned_serial_number == "TEST_SERIAL_123"
        assert dut_instance.brute_force_counter_current == 20

    def test_delete_pins(self, dut_instance):
        """Test the _delete_pins method."""
        dut_instance.user_pin[1] = ['1']
        dut_instance.recovery_pin[2] = ['2']
        dut_instance.self_destruct_pin = ['3']
        dut_instance.user_forced_enrollment = True
        
        dut_instance._delete_pins()
        
        assert dut_instance.user_pin[1] is None
        assert dut_instance.recovery_pin[2] is None
        assert dut_instance.self_destruct_pin == []
        assert dut_instance.user_forced_enrollment is False
        assert dut_instance.old_user_pin[1] == ['1']

    def test_reset(self, dut_instance):
        """Test the _reset method."""
        dut_instance.admin_pin = ['1']
        dut_instance.brute_force_counter_current = 5
        
        dut_instance._reset()

        assert dut_instance.admin_pin == []
        assert dut_instance.brute_force_counter_current == 20

    def test_self_destruct(self, dut_instance):
        """Test the _self_destruct method."""
        dut_instance.admin_pin = ['1']
        dut_instance.user_pin[1] = ['2']
        dut_instance.self_destruct_pin = ['9']
        
        dut_instance._self_destruct()

        assert dut_instance.admin_pin == ['9']
        assert dut_instance.user_pin[1] is None
        assert dut_instance.self_destruct_used is True

# =============================================================================
# === 2. Tests for CallableCondition Helper Class
# =============================================================================
class TestCallableCondition:
    """Unit tests for the CallableCondition helper class."""

    def test_call(self):
        """Test that the __call__ method executes the wrapped function."""
        # Test that it returns True when the wrapped function returns True
        cond_true = CallableCondition(func=lambda: True, name="is_true")
        assert cond_true() is True
        
        # Test that it returns False when the wrapped function returns False
        cond_false = CallableCondition(func=lambda: False, name="is_false")
        assert cond_false() is False

    def test_repr(self):
        """Test the __repr__ method for correct string formatting."""
        condition = CallableCondition(func=lambda: True, name="my_test_condition")
        assert repr(condition) == "<CallableCondition: my_test_condition>"

# =============================================================================
# === 3. Tests for ApricornDeviceFSM Class
# =============================================================================
class TestApricornDeviceFSM:
    """High-level tests for the FSM class itself."""
    
    def test_init(self, fsm, mock_at, dut_instance):
        """Test that the FSM initializes correctly."""
        assert fsm.at == mock_at
        assert fsm.dut == dut_instance
        assert fsm.state == 'OFF'
        # The check for the machine type is handled better in TestModuleAndHelpers
        assert hasattr(fsm, 'machine')

    def test_log_state_change_details(self, fsm, caplog):
        """Test that _log_state_change_details logs correctly."""
        # GIVEN the FSM is in a specific state before the transition
        fsm.state = 'OFF'
    
        # WHEN a transition occurs
        event = MagicMock()
        event.transition.source = 'OFF'
        # Configure the 'name' attribute on the nested mock to be a string
        event.event.name = 'power_on' 
        
        # Manually update the FSM's state to simulate the transition
        fsm.state = 'POWER_ON_SELF_TEST'

        fsm._log_state_change_details(event)

        # THEN the source state should be updated and a log created
        assert fsm.source_state == 'OFF'
        assert "State changed: OFF -> POWER_ON_SELF_TEST (Event: power_on)" in caplog.text

        # THEN the source state should be updated and a log created
        assert fsm.source_state == 'OFF'
        assert "State changed: OFF -> POWER_ON_SELF_TEST (Event: power_on)" in caplog.text

    def test_log_state_change_details_on_initialization(self, fsm, caplog):
        """
        Test that _log_state_change_details logs the initial state correctly
        when the FSM is first created. This covers the 'if event_data.transition is None' block.
        """
        # GIVEN: The FSM is in its initial state 'OFF'
        assert fsm.state == 'OFF'

        # WHEN: The callback is triggered with event_data.transition as None,
        # which simulates FSM initialization.
        event = MagicMock()
        event.transition = None
        
        fsm._log_state_change_details(event)

        # THEN: The initialization log message should be present.
        assert f"FSM initialized to state: {fsm.state}" in caplog.text

        # AND: The source state should not have been updated (it remains the default).
        assert fsm.source_state == 'OFF'

    # --- on_enter_* Callbacks ---

    def test_on_enter_POWER_ON_SELF_TEST_failure_path(self, fsm, mock_at):
        """Explicitly tests the post_fail call in on_enter_POWER_ON_SELF_TEST."""
        # GIVEN
        mock_at.await_and_confirm_led_pattern.return_value = False
        fsm.post_fail = MagicMock()

        # WHEN
        fsm.on_enter_POWER_ON_SELF_TEST(MagicMock())

        # THEN
        fsm.post_fail.assert_called_once() # Covers line 408

    def test_enter_invalid_pin_failure_and_zero_counter(self, fsm, mock_at, dut_instance):
        """Tests failure to see REJECT pattern and the path where counter is already zero."""
        ExpectedException = get_reloaded_exception()
        
        # Test hardware failure (covers line 738)
        mock_at.await_and_confirm_led_pattern.return_value = False
        result = fsm._enter_invalid_pin(MagicMock(kwargs={}))
        assert result is False
        mock_at.await_and_confirm_led_pattern.assert_called_once_with(LEDs['REJECT'], timeout=ANY)

        # Test when counter is already 0 (covers line 743)
        mock_at.await_and_confirm_led_pattern.return_value = True
        dut_instance.brute_force_counter_current = 0
        fsm._enter_invalid_pin(MagicMock(kwargs={}))
        assert dut_instance.brute_force_counter_current == 0 # Unchanged
    
    @pytest.mark.parametrize("hw_success, log_msg", [(True, "Stable ADMIN_MODE confirmed"), (False, "Failed to confirm stable ADMIN_MODE LEDs")])
    def test_on_enter_ADMIN_MODE(self, fsm, mock_at, caplog, hw_success, log_msg):
        mock_at.confirm_led_solid.return_value = hw_success
        fsm.on_enter_ADMIN_MODE(MagicMock())
        assert log_msg in caplog.text

    @pytest.mark.parametrize("hw_success, expected_call", [(True, "post_pass"), (False, "post_fail")])
    def test_on_enter_POWER_ON_SELF_TEST(self, fsm, mock_at, hw_success, expected_call):
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        setattr(fsm, expected_call, MagicMock()) # Mock the method that should be called
        fsm.on_enter_POWER_ON_SELF_TEST(MagicMock())
        getattr(fsm, expected_call).assert_called_once()

    @pytest.mark.parametrize("hw_success", [True, False])
    def test_on_enter_OFF(self, fsm, mock_at, hw_success):
        mock_at.confirm_led_solid.return_value = hw_success
        fsm.on_enter_OFF(MagicMock())
        mock_at.off.assert_has_calls([call("usb3"), call("connect")])
        mock_at.confirm_led_solid.assert_called_once()
        
    @pytest.mark.parametrize("hw_success", [True, False])
    def test_on_enter_FACTORY_MODE(self, fsm, mock_at, hw_success):
        mock_at.confirm_led_solid.return_value = hw_success
        fsm.on_enter_FACTORY_MODE(MagicMock())
        mock_at.confirm_led_solid.assert_called_with(LEDs['ALL_ON'], minimum=ANY, timeout=ANY, replay_extra_context=ANY)

    @pytest.mark.parametrize("led_success, enum_success", [
    (True, True),   # Happy path
    (True, False),  # Enum fails
    (False, True),  # LED check fails
    ])
    def test_on_enter_OOB_MODE(self, fsm, mock_at, caplog, led_success, enum_success):
        mock_at.confirm_led_solid.return_value = led_success
        mock_at.confirm_device_enum.return_value = enum_success
        fsm.post_fail = MagicMock()

        fsm.on_enter_OOB_MODE(MagicMock())

        if not led_success:
            assert "Failed to confirm OOB_MODE LEDs" in caplog.text
        
        if led_success and not enum_success:
            assert "Device did not enumerate in OOB_MODE" in caplog.text
            fsm.post_fail.assert_called_once_with(details="OOB_MODE_ENUM_FAILED")
        else:
            assert not fsm.post_fail.called

    @pytest.mark.parametrize("hw_success", [True, False])
    def test_on_enter_USER_FORCED_ENROLLMENT(self, fsm, mock_at, hw_success):
        mock_at.confirm_led_solid.return_value = hw_success
        fsm.on_enter_USER_FORCED_ENROLLMENT(MagicMock())
        mock_at.confirm_led_solid.assert_called_with(LEDs['GREEN_BLUE_STATE'], minimum=ANY, timeout=ANY, replay_extra_context=ANY)

    @pytest.mark.parametrize("hw_success", [True, False])
    def test_on_enter_STANDBY_MODE(self, fsm, mock_at, hw_success):
        mock_at.confirm_led_solid.return_value = hw_success
        fsm.on_enter_STANDBY_MODE(MagicMock())
        mock_at.confirm_led_solid.assert_called_with(LEDs['STANDBY_MODE'], minimum=ANY, timeout=ANY, replay_extra_context=ANY)
    
    @pytest.mark.parametrize("enum_success", [True, False])
    def test_on_enter_UNLOCKED_ADMIN(self, fsm, mock_at, enum_success):
        mock_at.confirm_drive_enum.return_value = enum_success
        fsm.post_fail = MagicMock()
        fsm.on_enter_UNLOCKED_ADMIN(MagicMock())
        
        if not enum_success:
            fsm.post_fail.assert_called_once_with(details="ADMIN_UNLOCK_ENUM_FAILED")
        else:
            assert not fsm.post_fail.called
        
    @pytest.mark.parametrize("enum_success", [True, False])
    def test_on_enter_UNLOCKED_USER(self, fsm, mock_at, enum_success):
        mock_at.confirm_drive_enum.return_value = enum_success
        fsm.post_fail = MagicMock()
        fsm.on_enter_UNLOCKED_USER(MagicMock())

        if not enum_success:
            fsm.post_fail.assert_called_once_with(details="USER_UNLOCK_ENUM_FAILED")
        else:
            assert not fsm.post_fail.called

    @pytest.mark.parametrize("hw_success", [True, False])
    def test_on_enter_BRUTE_FORCE(self, fsm, mock_at, hw_success):
        mock_at.confirm_led_pattern.return_value = hw_success
        fsm.on_enter_BRUTE_FORCE(MagicMock())
        mock_at.confirm_led_pattern.assert_called_with(LEDs['BRUTE_FORCED'], replay_extra_context=ANY)

    @pytest.mark.parametrize("hw_success", [True, False])
    def test_on_enter_COUNTER_ENROLLMENT(self, fsm, mock_at, hw_success):
        mock_at.confirm_led_pattern.return_value = hw_success
        fsm.on_enter_COUNTER_ENROLLMENT(MagicMock())
        mock_at.confirm_led_pattern.assert_called_with(LEDs['RED_COUNTER'], replay_extra_context=ANY)

    @pytest.mark.parametrize("trigger, pattern_key", [("enroll_self_destruct", "RED_BLUE"), ("enroll_user", "GREEN_BLUE")])
    def test_on_enter_PIN_ENROLLMENT(self, fsm, mock_at, trigger, pattern_key):
        # GIVEN
        event = MagicMock()
        event.event.name = trigger  # Set the name attribute to the string from the parameter

        # WHEN
        fsm.on_enter_PIN_ENROLLMENT(event)

        # THEN
        mock_at.await_and_confirm_led_pattern.assert_called_with(
            LEDs[pattern_key], 
            timeout=ANY, 
            replay_extra_context=ANY
        )

    # --- 'before' Callbacks ---

    @pytest.mark.parametrize("usb2_arg, vbus_state, hw_success", [
    (False, True, True),   # Standard success case
    (True, True, True),    # USB2 success case
    (False, False, True),  # VBUS is off, skip LED check
    (False, True, False),  # Hardware fails LED check
    ])
    def test_do_power_on_scenarios(self, fsm, mock_at, dut_instance, usb2_arg, vbus_state, hw_success):
        """Tests various scenarios in the _do_power_on method."""
        # GIVEN
        dut_instance.vbus = vbus_state
        mock_at.confirm_led_pattern.return_value = hw_success
        event = MagicMock(transition=MagicMock(), kwargs={'usb2': usb2_arg})
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        if not hw_success:
            with pytest.raises(ExpectedException, match="Failed Startup Self-Test LED confirmation"):
                fsm._do_power_on(event)
            mock_at.confirm_led_pattern.assert_called_once()
            return

        fsm._do_power_on(event)
        
        # Assertions
        if usb2_arg:
            mock_at.on.assert_has_calls([call("usb3"), call("connect")])
        else:
            mock_at.on.assert_called_once_with("connect")

        if vbus_state:
            mock_at.confirm_led_pattern.assert_called_once()
        else:
            mock_at.confirm_led_pattern.assert_not_called()

    def test_do_power_on_invalid_arg(self, fsm):
        """Tests that _do_power_on raises an error for an invalid 'usb2' argument type."""
        # GIVEN an invalid argument for usb2
        event = MagicMock(transition=MagicMock(), kwargs={'usb2': 'not-a-bool'})
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        with pytest.raises(ExpectedException, match="usb2 argument, if provided, must be a boolean"):
            fsm._do_power_on(event)
        
    def test_do_power_off(self, fsm, mock_at):
        fsm._do_power_off(MagicMock())
        mock_at.off.assert_has_calls([call("usb3"), call("connect")])

    @pytest.mark.parametrize("unlock_method_name, pin_attr", [
    ("_enter_admin_pin", "admin_pin"),
    ("_enter_self_destruct_pin", "self_destruct_pin"),
    ("_enter_user_pin", "user_pin"),
    ])
    @pytest.mark.parametrize("read_only", [True, False])
    @pytest.mark.parametrize("lock_override", [True, False])
    @pytest.mark.parametrize("hw_success", [True, False])
    def test_all_unlock_scenarios(self, fsm, mock_at, dut_instance, unlock_method_name, pin_attr, read_only, lock_override, hw_success):
        """A comprehensive test for all PIN unlock methods and hardware configurations."""
        # GIVEN
        dut_instance.read_only_enabled = read_only
        dut_instance.lock_override = lock_override
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        unlock_method = getattr(fsm, unlock_method_name)

        # Set up the PIN and event kwargs
        pin = ['1','2','3','4','5','6','7']
        event_kwargs = {}
        if pin_attr == "user_pin":
            dut_instance.user_pin[1] = pin
            event_kwargs['user_id'] = 1
        else:
            setattr(dut_instance, pin_attr, pin)
        
        event = MagicMock(transition=MagicMock(), kwargs=event_kwargs)
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        if not hw_success:
            with pytest.raises(ExpectedException, match="Failed .* unlock LED pattern"):
                unlock_method(event)
        else:
            unlock_method(event)

        # Assertions
        # Determine the expected LED pattern based on the DUT state
        if read_only and lock_override:
            expected_led_pattern = LEDs['ENUM_LOCK_OVERRIDE_READ_ONLY']
        elif read_only:
            expected_led_pattern = LEDs['ENUM_READ_ONLY']
        elif lock_override:
            expected_led_pattern = LEDs['ENUM_LOCK_OVERRIDE']
        else:
            expected_led_pattern = LEDs['ENUM']

        mock_at.await_and_confirm_led_pattern.assert_called_once_with(expected_led_pattern, timeout=ANY, replay_extra_context=ANY)

    # Add this new test to the TestApricornDeviceFSM class.
    @pytest.mark.parametrize("kwargs, error_msg", [
        ({}, "Unlock user requires a 'user_id' to be passed"),
        ({'user_id': 99}, "is not a valid slot"),
        ({'user_id': 1}, "No PIN is tracked for logical user 1"),
    ])
    def test_enter_user_pin_arg_failures(self, fsm, dut_instance, kwargs, error_msg):
        """Tests the argument validation paths in _enter_user_pin."""
        # GIVEN
        event = MagicMock(transition=MagicMock(), kwargs=kwargs)
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        with pytest.raises(ExpectedException, match=error_msg):
            fsm._enter_user_pin(event)

    def test_enter_admin_mode_login(self, fsm, mock_at, dut_instance):
        dut_instance.admin_pin = ['1']
        fsm._enter_admin_mode_login(MagicMock(transition=MagicMock()))
        mock_at.press.assert_called_once()
        mock_at.confirm_led_pattern.assert_called_once()
        mock_at.sequence.assert_called_once_with(['1'])

    def test_enter_last_try_pin(self, fsm, mock_at):
        fsm._enter_last_try_pin(MagicMock())
        mock_at.press.assert_called_once()
        mock_at.await_and_confirm_led_pattern.assert_called_once()
        mock_at.sequence.assert_called_once()

    def test_do_user_reset_from_admin_mode(self, fsm, mock_at, dut_instance):
        """Test successful user reset when initiated from ADMIN_MODE."""
        # GIVEN
        fsm.state = 'ADMIN_MODE'
        dut_instance.admin_pin = ['1']
        
        # WHEN
        fsm._do_user_reset(MagicMock(transition=MagicMock()))
        
        # THEN
        assert dut_instance.admin_pin == []
        mock_at.sequence.assert_called_once_with([["lock", "unlock", "key2"]], pause_duration_ms=ANY)
        mock_at.confirm_led_solid.assert_called_once()
        mock_at.on.assert_not_called() # Should use sequence, not .on()

    @pytest.mark.parametrize("hw_success", [True, False])
    def test_do_user_reset_from_standby_mode(self, fsm, mock_at, dut_instance, hw_success):
        """
        Test user reset when initiated from a non-ADMIN_MODE state (e.g., STANDBY).
        This covers the 'else' block of the function.
        """
        # GIVEN: The FSM is in a state other than ADMIN_MODE
        fsm.state = 'STANDBY_MODE'
        dut_instance.admin_pin = ['1']
        
        # GIVEN: The hardware check for the initiation pattern will either succeed or fail
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        
        # WHEN / THEN
        if hw_success:
            # If the initiation pattern is seen, the rest of the function should execute
            fsm._do_user_reset(MagicMock(transition=MagicMock()))
            
            # Assert the `else` block's logic was followed
            mock_at.on.assert_called_once_with("lock", "unlock", "key2")
            mock_at.await_and_confirm_led_pattern.assert_called_once_with(
                LEDs["RED_BLUE"], timeout=15, replay_extra_context=ANY
            )
            mock_at.off.assert_called_once_with("lock", "unlock", "key2")
            mock_at.confirm_led_solid.assert_called_once()
            assert dut_instance.admin_pin == [] # PINs should be cleared
        else:
            # If the initiation pattern is NOT seen, it should raise an error immediately
            ExpectedException = get_reloaded_exception()
            with pytest.raises(ExpectedException, match="Failed to observe user reset initiation pattern"):
                fsm._do_user_reset(MagicMock(transition=MagicMock()))

            # Assert the function aborted before clearing data
            assert dut_instance.admin_pin == ['1']
            mock_at.on.assert_called_once_with("lock", "unlock", "key2")
            mock_at.off.assert_not_called() # Should not be called if it aborts early

    def test_do_user_reset_failure(self, fsm, mock_at, dut_instance):
        # This test remains valid for testing a failure in the final confirmation step
        fsm.state = 'ADMIN_MODE'
        dut_instance.admin_pin = ['1']
        mock_at.confirm_led_solid.return_value = False # Simulate final HW failure
        event = MagicMock(transition=MagicMock())
        ExpectedException = get_reloaded_exception()
        with pytest.raises(ExpectedException, match="Failed to observe user reset confirmation pattern"):
            fsm._do_user_reset(event)
        assert dut_instance.admin_pin == ['1']
        
    def test_do_manufacturer_reset(self, fsm, mock_at, dut_instance):
        # GIVEN
        fsm.state = 'FACTORY_MODE'
        dut_instance.secure_key = False
        
        # WHEN
        with patch('time.sleep'): # Avoid long sleeps
            fsm._do_manufacturer_reset(MagicMock(transition=MagicMock()))

        # THEN
        # 1. Assert the initial sequence and long press happen once.
        assert mock_at.sequence.call_count == 1
        
        assert mock_at.press.call_count == 2
        # And we can verify what those calls were.
        mock_at.press.assert_has_calls([
            call("lock", duration_ms=6000), # The first long press
            call("unlock")                 # The final key press in the sequence
        ])

        # 2. Assert the keypad test loop calls 'on' and 'off' the correct number of times.
        # portable list has 12 keys. The first is special, the last uses 'press'.
        # The loop runs for 10 'OTHER_KEYS'.
        assert mock_at.on.call_count == 11 # The first key + 10 other keys
        assert mock_at.off.call_count == 1 # Only for the first key

        # 3. Assert the LED checks happen as expected.
        assert mock_at.confirm_led_pattern.call_count == 1
        assert mock_at.confirm_led_solid.call_count == 1
        assert mock_at.await_led_state.call_count == 10 # Once for each of the OTHER_KEYS
        assert mock_at.confirm_led_solid_strict.call_count == 1

    def test_press_lock_button(self, fsm, mock_at):
        fsm._press_lock_button(MagicMock())
        mock_at.press.assert_called_with("lock")

    def test_enter_invalid_pin(self, fsm, mock_at, dut_instance):
        initial_count = dut_instance.brute_force_counter_current
        result = fsm._enter_invalid_pin(MagicMock(kwargs={}))
        assert dut_instance.brute_force_counter_current == initial_count - 1
        assert result is True
        mock_at.await_and_confirm_led_pattern.assert_called_with(LEDs['REJECT'], timeout=ANY)

    @pytest.mark.parametrize("pin_entered, hw_success", [
    (True, True),   # Partial entry, correct REJECT observed
    (True, False),  # Partial entry, REJECT not observed (failure)
    (False, True),  # No entry, no REJECT expected
    ])
    def test_timeout_pin_enrollment(self, monkeypatch, fsm, mock_at, pin_entered, hw_success):
        """Tests all paths of the newly added _timeout_pin_enrollment method."""
        # GIVEN
        mock_sleep = MagicMock()
        monkeypatch.setattr(time, 'sleep', mock_sleep)
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        event = MagicMock(transition=MagicMock(), kwargs={'pin_entered': pin_entered})
        ExpectedException = get_reloaded_exception()
        
        # WHEN / THEN
        if pin_entered and not hw_success:
            with pytest.raises(ExpectedException, match="Did not observe REJECT"):
                fsm._timeout_pin_enrollment(event)
        else:
            fsm._timeout_pin_enrollment(event)

        # Assertions
        mock_sleep.assert_called_with(30)
        if pin_entered:
            mock_at.await_and_confirm_led_pattern.assert_called_with(LEDs['REJECT'], timeout=ANY, replay_extra_context=ANY)
        else:
            mock_at.await_and_confirm_led_pattern.assert_not_called()

    def test_brute_force_counter_enrollment(self, fsm, mock_at):
        fsm._brute_force_counter_enrollment(MagicMock(transition=MagicMock()))
        mock_at.press.assert_called_with(['unlock', 'key5'], duration_ms=6000)

    def test_min_pin_enrollment(self, fsm, mock_at):
        fsm._min_pin_enrollment(MagicMock(transition=MagicMock()))
        mock_at.press.assert_called_with(['unlock', 'key4'], duration_ms=6000)

    def test_unattended_auto_lock_enrollment(self, fsm, mock_at):
        fsm._unattended_auto_lock_enrollment(MagicMock(transition=MagicMock()))
        mock_at.press.assert_called_with(['unlock', 'key6'], duration_ms=6000)

    @pytest.mark.parametrize("trigger, kwargs, error_msg", [
    # Brute Force Counter Failures
    ("enroll_brute_force_counter", {'new_counter': None}, "requires a 'new_counter' str"),
    ("enroll_brute_force_counter", {'new_counter': '1'}, "requires two-digits"),
    ("enroll_brute_force_counter", {'new_counter': 12}, "requires a 'new_counter' str"),
    # Min PIN Length Failures
    ("enroll_min_pin_counter", {'new_counter': None}, "requires a 'new_counter' str"),
    ("enroll_min_pin_counter", {'new_counter': '7'}, "requires two-digits"),
    ("enroll_min_pin_counter", {'new_counter': 10}, "requires a 'new_counter' str"),
    # Unattended Auto-Lock Failures
    ("enroll_unattended_auto_lock_counter", {'new_counter': None}, "requires a 'new_counter' integer"),
    ("enroll_unattended_auto_lock_counter", {'new_counter': '1'}, "requires a 'new_counter' integer"),
    ("enroll_unattended_auto_lock_counter", {'new_counter': 10}, "requires a single digit"),
    ])
    def test_counter_enrollment_invalid_args(self, fsm, trigger, kwargs, error_msg):
        """Tests all argument validation failure paths in _counter_enrollment."""
        # GIVEN
        event = MagicMock(transition=MagicMock(), kwargs=kwargs)
        event.event.name = trigger
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        with pytest.raises(ExpectedException, match=error_msg):
            fsm._counter_enrollment(event)
    
    @pytest.mark.parametrize("trigger_name, counter_value, expected_press_arg", [
        # Case 1: Unattended Auto-Lock
        ('enroll_unattended_auto_lock_counter', 1, 'key1'),
        # Case 2: Brute Force (requires a 2-digit string)
        ('enroll_brute_force_counter', '08', ['8', '0']), # Note: press is called twice
        # Case 3: Min PIN Length (requires a 2-digit string)
        ('enroll_min_pin_counter', '12', ['2', '1']),
    ])
    def test_counter_enrollment_success_paths(self, fsm, mock_at, dut_instance, trigger_name, counter_value, expected_press_arg):
        # GIVEN
        dut_instance.unattended_auto_lock_counter = 0 # Initial state
        
        event = MagicMock(transition=MagicMock(), kwargs={'new_counter': counter_value})
        event.event.name = trigger_name # Set the name attribute to a simple string

        # WHEN
        fsm._counter_enrollment(event)

        # THEN
        if isinstance(expected_press_arg, list):
            # For 2-digit counters, press is called twice
            mock_at.press.assert_has_calls([
                call(expected_press_arg[1]),
                call(expected_press_arg[0])
            ])
        else:
            # For single-digit counters
            mock_at.press.assert_called_with(expected_press_arg)

        # Also check that the DUT state was updated for the auto-lock case
        if trigger_name == 'enroll_unattended_auto_lock_counter':
            assert dut_instance.unattended_auto_lock_counter == counter_value

    @pytest.mark.parametrize("trigger_name, counter_value, dut_min_pin, dut_max_pin", [
    # Unattended Auto-Lock out of range
    ('enroll_unattended_auto_lock_counter', 9, 7, 16),
    # Brute force out of range (low)
    ('enroll_brute_force_counter', '01', 7, 16),
    # Brute force out of range (high)
    ('enroll_brute_force_counter', '11', 7, 16),
    # Min PIN out of range (low)
    ('enroll_min_pin_counter', '06', 7, 16),
    # Min PIN out of range (high)
    ('enroll_min_pin_counter', '17', 7, 16),
    ])
    def test_counter_enrollment_invalid_value_rejection(self, fsm, mock_at, dut_instance, trigger_name, counter_value, dut_min_pin, dut_max_pin):
        """Tests the logic for when the device itself should reject an out-of-range value."""
        # GIVEN
        dut_instance.default_minimum_pin_counter = dut_min_pin
        dut_instance.maximum_pin_counter = dut_max_pin
        
        # The new_counter kwarg must match the type expected by the function
        if trigger_name == 'enroll_unattended_auto_lock_counter':
            kwargs = {'new_counter': counter_value}
            expected_press = f"key{counter_value}"
        else:
            kwargs = {'new_counter': str(counter_value)}
            expected_press = [str(counter_value)[0], str(counter_value)[1]]

        event = MagicMock(transition=MagicMock(), kwargs=kwargs)
        event.event.name = trigger_name
        
        # WHEN
        fsm._counter_enrollment(event)

        # THEN it should have checked for the REJECT pattern
        mock_at.await_and_confirm_led_pattern.assert_called_with(
            LEDs['REJECT'], timeout=ANY, replay_extra_context=ANY
        )
        
    @pytest.mark.parametrize("pin_entered", [True, False])
    def test_timeout_counter_enrollment(self, monkeypatch, fsm, mock_at, pin_entered):
        mock_sleep = MagicMock()
        monkeypatch.setattr(time, 'sleep', mock_sleep)
        event = MagicMock(transition=MagicMock(), kwargs={'pin_entered': pin_entered})
        
        fsm._timeout_counter_enrollment(event)
        
        mock_sleep.assert_called_with(30)
        if pin_entered:
            mock_at.await_and_confirm_led_pattern.assert_called_with(LEDs['REJECT'], timeout=ANY, replay_extra_context=ANY)
        else:
            # This covers line 1019
            mock_at.await_and_confirm_led_pattern.assert_not_called()
        
    def test_admin_enrollment(self, fsm, mock_at, dut_instance):
        fsm._admin_enrollment(MagicMock())
        mock_at.press.assert_called_with(['unlock', 'key9'])
        assert dut_instance.pending_enrollment_type == 'admin'

    @pytest.mark.parametrize("hw_success", [True, False])
    def test_recovery_pin_enrollment(self, fsm, mock_at, dut_instance, hw_success):
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        ExpectedException = get_reloaded_exception()

        if not hw_success:
            with pytest.raises(ExpectedException, match="Did not observe GREEN_BLUE pattern"):
                fsm._recovery_pin_enrollment(MagicMock(transition=MagicMock()))
        else:
            fsm._recovery_pin_enrollment(MagicMock(transition=MagicMock()))
            assert dut_instance.pending_enrollment_type == 'recovery'
        
        mock_at.press.assert_called_with(['unlock', 'key7'])
        
    def test_user_enrollment(self, fsm, mock_at, dut_instance):
        fsm._user_enrollment(MagicMock(transition=MagicMock()))
        mock_at.press.assert_called_with(['unlock', 'key1'])
        assert dut_instance.pending_enrollment_type == 'user'
        
    @pytest.mark.parametrize("sd_enabled, hw_success", [
    (True, True),   # Happy path: SD enabled, HW works
    (True, False),  # Failure: SD enabled, but subsequent HW check fails (tested elsewhere)
    (False, True),  # Rejected: SD disabled, device correctly rejects
    (False, False)  # Failure: SD disabled, device should reject but pattern isn't seen
    ])
    def test_self_destruct_pin_enrollment(self, fsm, mock_at, dut_instance, sd_enabled, hw_success):
        # GIVEN
        dut_instance.self_destruct_enabled = sd_enabled
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        event = MagicMock(transition=MagicMock())
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        if sd_enabled:
            fsm._self_destruct_pin_enrollment(event)
            assert dut_instance.pending_enrollment_type == 'self_destruct'
        else: # Self-destruct is not enabled, so we expect a REJECT
            if not hw_success:
                with pytest.raises(ExpectedException, match="Did not observe REJECT"):
                    fsm._self_destruct_pin_enrollment(event)
            else:
                fsm._self_destruct_pin_enrollment(event)
                # Should not change pending type because it was rejected
                assert dut_instance.pending_enrollment_type is None 
                mock_at.await_and_confirm_led_pattern.assert_called_once_with(LEDs['REJECT'], timeout=ANY, replay_extra_context=ANY)
        
        # The key press happens regardless
        mock_at.press.assert_called_with(['key3', 'unlock'])

    def test_pin_enrollment_fails_with_invalid_pin_arg(self, fsm):
        """
        GIVEN an invalid 'new_pin' argument (e.g., None or not a list)
        WHEN _pin_enrollment is called
        THEN it should raise a TransitionCallbackError immediately.
        """
        ExpectedException = get_reloaded_exception()

        # Test with new_pin=None
        with pytest.raises(ExpectedException, match="PIN enrollment requires a 'new_pin' list"):
            # The event mock needs the 'event.name' attribute, even if it's not used here,
            # because the function tries to access it.
            event = MagicMock(kwargs={'new_pin': None}, event=MagicMock())
            fsm._pin_enrollment(event)

        # Test with new_pin being a string instead of a list
        with pytest.raises(ExpectedException, match="PIN enrollment requires a 'new_pin' list"):
            event = MagicMock(kwargs={'new_pin': "1234567"}, event=MagicMock())
            fsm._pin_enrollment(event)

    # --- Admin Enrollment Tests ---

    def test_pin_enrollment_admin_success(self, fsm, mock_at, dut_instance):
        """Test the successful enrollment of an Admin PIN."""
        # GIVEN
        dut_instance.pending_enrollment_type = 'admin'
        new_pin = ['1', '2', '3', '4', '5', '6', '7']
        event = MagicMock(transition=MagicMock(), kwargs={'new_pin': new_pin})
        
        # WHEN
        fsm._pin_enrollment(event)
        
        # THEN
        assert dut_instance.admin_pin == new_pin
        assert mock_at.sequence.call_count == 2
        assert mock_at.await_and_confirm_led_pattern.call_count == 2
        mock_at.await_led_state.assert_called_once()
        assert dut_instance.pending_enrollment_type is None

    def test_pin_enrollment_admin_failure_on_hw_check(self, fsm, mock_at, dut_instance):
        """Test Admin PIN enrollment failure during a hardware check."""
        # GIVEN
        dut_instance.pending_enrollment_type = 'admin'
        new_pin = ['1', '2', '3', '4', '5', '6', '7']
        event = MagicMock(transition=MagicMock(), kwargs={'new_pin': new_pin}, event=MagicMock())
        mock_at.await_and_confirm_led_pattern.side_effect = [True, False] 
        
        ExpectedException = get_reloaded_exception()

        # WHEN/THEN
        with pytest.raises(ExpectedException, match="Did not observe GREEN_BLUE pattern"):
            fsm._pin_enrollment(event)

        assert dut_instance.admin_pin == []
        mock_at.sequence.assert_called_once_with(new_pin)

    # --- User Enrollment Tests ---
    
    def test_pin_enrollment_user_success(self, fsm, mock_at, dut_instance):
        """Test the successful enrollment of a User PIN."""
        # GIVEN
        dut_instance.pending_enrollment_type = 'user'
        new_pin = ['2', '3', '4', '5', '6', '7', '8']
        event = MagicMock(transition=MagicMock(), kwargs={'new_pin': new_pin})
        
        # WHEN
        fsm._pin_enrollment(event)

        # THEN
        assert dut_instance.user_pin[1] == new_pin
        assert mock_at.sequence.call_count == 2
        mock_at.confirm_led_solid.assert_called_once()
        assert dut_instance.pending_enrollment_type is None

    def test_pin_enrollment_user_fails_when_slots_full(self, fsm, mock_at, dut_instance):
        """Test User PIN enrollment failure when all user slots are full."""
        # GIVEN
        dut_instance.pending_enrollment_type = 'user'
        for i in dut_instance.user_pin.keys():
            dut_instance.user_pin[i] = [str(i)] # Fill all slots
        event = MagicMock(transition=MagicMock(), kwargs={'new_pin': ['9']}, event=MagicMock())

        ExpectedException = get_reloaded_exception()

        # WHEN/THEN
        with pytest.raises(ExpectedException, match="All 4 user slots are full"):
            fsm._pin_enrollment(event)
        
        mock_at.sequence.assert_not_called()

    # --- Recovery Enrollment Tests ---

    def test_pin_enrollment_recovery_success(self, fsm, mock_at, dut_instance):
        """Test the successful enrollment of a Recovery PIN."""
        # GIVEN
        dut_instance.pending_enrollment_type = 'recovery'
        new_pin = ['3', '4', '5', '6', '7', '8', '9']
        event = MagicMock(transition=MagicMock(), kwargs={'new_pin': new_pin})

        # WHEN
        fsm._pin_enrollment(event)

        # THEN
        assert dut_instance.recovery_pin[1] == new_pin
        assert mock_at.sequence.call_count == 2
        mock_at.confirm_led_solid.assert_called_once()
        assert dut_instance.pending_enrollment_type is None

    def test_pin_enrollment_recovery_fails_when_slots_full(self, fsm, mock_at, dut_instance):
        """Test Recovery PIN enrollment failure when all recovery slots are full."""
        # GIVEN
        dut_instance.pending_enrollment_type = 'recovery'
        for i in dut_instance.recovery_pin.keys():
            dut_instance.recovery_pin[i] = [str(i)] # Fill all slots
        event = MagicMock(transition=MagicMock(), kwargs={'new_pin': ['9']}, event=MagicMock())

        ExpectedException = get_reloaded_exception()

        # WHEN/THEN
        with pytest.raises(ExpectedException, match="All 4 recovery slots are full"):
            fsm._pin_enrollment(event)
        
        mock_at.sequence.assert_not_called()

    # --- Self-Destruct Enrollment Tests ---
    
    def test_pin_enrollment_self_destruct_success(self, fsm, mock_at, dut_instance):
        """Test the successful enrollment of a Self-Destruct PIN."""
        # GIVEN
        dut_instance.pending_enrollment_type = 'self_destruct'
        new_pin = ['9', '8', '7', '6', '5', '4', '3']
        event = MagicMock(transition=MagicMock(), kwargs={'new_pin': new_pin})
        
        # WHEN
        fsm._pin_enrollment(event)

        # THEN
        assert dut_instance.self_destruct_pin == new_pin
        mock_at.await_and_confirm_led_pattern.assert_any_call(LEDs['RED_BLUE'], timeout=ANY, replay_extra_context=ANY)
        assert mock_at.sequence.call_count == 2
        assert dut_instance.pending_enrollment_type is None

    def test_pin_enrollment_self_destruct_failure_on_hw_check(self, fsm, mock_at, dut_instance):
        """Test Self-Destruct PIN enrollment failure during a hardware check."""
        # GIVEN
        dut_instance.pending_enrollment_type = 'self_destruct'
        new_pin = ['9', '8', '7', '6', '5', '4', '3']
        event = MagicMock(transition=MagicMock(), kwargs={'new_pin': new_pin}, event=MagicMock())
        mock_at.await_and_confirm_led_pattern.side_effect = [True, False]
        
        ExpectedException = get_reloaded_exception()

        # WHEN/THEN
        with pytest.raises(ExpectedException, match="Did not observe RED_BLUE pattern"):
            fsm._pin_enrollment(event)

        assert dut_instance.self_destruct_pin == []
        mock_at.sequence.assert_called_once_with(new_pin) # Only first entry

    @pytest.mark.parametrize("toggle_method, expected_press, dut_attr, expected_val", [
        ("_basic_disk_toggle", ['key2', 'key3'], "basic_disk", True),
        ("_removable_media_toggle", ['key3', 'key7'], "removable_media", True),
        ("_led_flicker_enable", ['key0', 'key3'], "led_flicker", True),
        ("_led_flicker_disable", ['key0', 'key3'], "led_flicker", False),
        ("_lock_override_toggle", ['key0', 'key3'], "lock_override", True),
        ("_read_only_toggle", ['key6', 'key7'], "read_only_enabled", True),
        ("_read_write_toggle", ['key7', 'key9'], "read_only_enabled", False),
    ])
    def test_simple_toggles(self, fsm, mock_at, dut_instance, toggle_method, expected_press, dut_attr, expected_val):
        # This single test covers 7 simple toggle functions
        if toggle_method == "_removable_media_toggle":
            dut_instance.removable_media = False
        elif toggle_method == "_lock_override_toggle":
            dut_instance.lock_override = False
            
        getattr(fsm, toggle_method)(MagicMock(transition=MagicMock()))
        
        mock_at.press.assert_called_with(expected_press)
        mock_at.await_and_confirm_led_pattern.assert_called_with(LEDs['ACCEPT_PATTERN'], timeout=ANY, replay_extra_context=ANY)
        assert getattr(dut_instance, dut_attr) == expected_val

    @pytest.mark.parametrize("sd_enabled, initial_pl_state, expected_pl_state, expected_pattern_key", [
        # Case 1: Success. Self-destruct is OFF, so Provision Lock can be enabled.
        (False, False, True, 'ACCEPT_PATTERN'),
        # Case 2: Failure. Self-destruct is ON, so Provision Lock toggle is rejected.
        (True, False, False, 'REJECT'),
    ])
    def test_provision_lock_toggle(self, fsm, mock_at, dut_instance, sd_enabled, initial_pl_state, expected_pl_state, expected_pattern_key):
        """
        GIVEN a specific device state (self-destruct enabled or not)
        WHEN _provision_lock_toggle is called
        THEN the correct hardware commands are sent and the DUT state is updated accordingly.
        """
        # GIVEN: The DUT is configured for the specific test case.
        dut_instance.self_destruct_enabled = sd_enabled
        dut_instance.provision_lock = initial_pl_state
        
        # WHEN: The callback is executed.
        fsm._provision_lock_toggle(MagicMock(transition=MagicMock()))

        # THEN: Assert that the correct key combination was always pressed.
        mock_at.press.assert_called_once_with(['key2', 'key5'])

        # THEN: Assert that the correct LED pattern was checked.
        expected_pattern = LEDs[expected_pattern_key]
        mock_at.await_and_confirm_led_pattern.assert_called_once_with(
            expected_pattern, 
            timeout=ANY, 
            replay_extra_context=ANY
        )

        # THEN: Assert that the provision_lock state is correct after the operation.
        assert dut_instance.provision_lock == expected_pl_state

    def test_self_destruct_toggle(self, fsm, mock_at, dut_instance):
        dut_instance.provision_lock = False
        getattr(fsm, "_self_destruct_toggle")(MagicMock(transition=MagicMock()))
        mock_at.press.assert_called_with(['key4', 'key7'])
        assert dut_instance.self_destruct_enabled is True

    @pytest.mark.parametrize("initial_ufe_state, expected_ufe_state, expected_pattern_key", [
        # Case 1: Success. UFE is OFF, so the toggle enables it.
        (False, True, 'ACCEPT_PATTERN'),
        # Case 2: Failure/Reject. UFE is already ON, so the toggle is rejected.
        (True, True, 'REJECT'),
    ])
    def test_user_forced_enrollment_toggle(self, fsm, mock_at, dut_instance, initial_ufe_state, expected_ufe_state, expected_pattern_key):
        """
        GIVEN a specific User-Forced Enrollment (UFE) state
        WHEN _user_forced_enrollment_toggle is called
        THEN the correct hardware commands are sent and the DUT state is updated accordingly.
        """
        # GIVEN: The DUT is configured for the specific test case.
        dut_instance.user_forced_enrollment = initial_ufe_state
        
        # WHEN: The callback is executed.
        fsm._user_forced_enrollment_toggle(MagicMock(transition=MagicMock()))

        # THEN: Assert that the correct key combination was always pressed.
        mock_at.press.assert_called_once_with(['key0', 'key1'])

        # THEN: Assert that the correct LED pattern was checked.
        expected_pattern = LEDs[expected_pattern_key]
        mock_at.await_and_confirm_led_pattern.assert_called_once_with(
            expected_pattern, 
            timeout=ANY, 
            replay_extra_context=ANY
        )

        # THEN: Assert that the UFE state is correct after the operation.
        assert dut_instance.user_forced_enrollment == expected_ufe_state
        
    @pytest.mark.parametrize("ufe_enabled, hw_step_to_fail", [
    (False, 0), # Happy path, all HW checks succeed
    (True, 0),  # UFE is enabled, so the function should do nothing
    (False, 1), # Fails on first ACCEPT_PATTERN
    (False, 2), # Fails on RED_BLUE pattern
    (False, 3), # Fails on final ACCEPT_STATE
    ])
    def test_delete_pins_toggle(self, fsm, mock_at, dut_instance, ufe_enabled, hw_step_to_fail):
        """Tests all success, no-op, and failure paths of _delete_pins_toggle."""
        # GIVEN
        dut_instance.user_forced_enrollment = ufe_enabled
        dut_instance.user_pin[1] = ['1'] # Give it a pin to delete

        # Set up hardware mock side effects
        mock_at.await_and_confirm_led_pattern.side_effect = [
            hw_step_to_fail != 1, # First ACCEPT
            hw_step_to_fail != 2, # RED_BLUE
        ]
        mock_at.confirm_led_solid.return_value = (hw_step_to_fail != 3)

        event = MagicMock(transition=MagicMock())
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        if ufe_enabled:
            fsm._delete_pins_toggle(event)
            mock_at.press.assert_not_called()
            assert dut_instance.user_pin[1] is not None # Pin should not be deleted
            return

        if hw_step_to_fail > 0:
            with pytest.raises(ExpectedException):
                fsm._delete_pins_toggle(event)
            assert dut_instance.user_pin[1] is not None # Pin should not be deleted
        else: # Happy path
            fsm._delete_pins_toggle(event)
            assert dut_instance.user_pin[1] is None # Pin should be deleted
            assert mock_at.press.call_count == 2

    def test_on_enter_PIN_ENROLLMENT_self_destruct_failure(self, fsm, mock_at):
        """Covers the hardware failure path for self_destruct in on_enter_PIN_ENROLLMENT."""
        # GIVEN
        event = MagicMock()
        event.event.name = 'enroll_self_destruct'
        mock_at.await_and_confirm_led_pattern.return_value = False
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        with pytest.raises(ExpectedException, match="Did not observe RED_BLUE pattern"):
            fsm.on_enter_PIN_ENROLLMENT(event) # Covers lines 1072-1073

    # Add this new test to the TestApricornDeviceFSM class
    @pytest.mark.parametrize("enrollment_type, step_to_fail", [
        ('admin', 1), ('admin', 2), ('admin', 3), # Fail first accept, second accept, final state
        ('recovery', 1), ('recovery', 2), ('recovery', 3),
        ('user', 1), ('user', 2), ('user', 3),
        ('self_destruct', 1), ('self_destruct', 2), ('self_destruct', 3),
    ])
    def test_pin_enrollment_all_hw_failure_paths(self, fsm, mock_at, dut_instance, enrollment_type, step_to_fail):
        """Covers all intermediate hardware failure paths in the _pin_enrollment method."""
        # GIVEN
        dut_instance.pending_enrollment_type = enrollment_type
        new_pin = ['1', '2', '3', '4', '5', '6', '7']
        event = MagicMock(transition=MagicMock(), kwargs={'new_pin': new_pin}, event=MagicMock())
        ExpectedException = get_reloaded_exception()

        # Configure mock side-effects to fail at the specified step
        side_effects_1 = [step_to_fail != 1, step_to_fail != 2]
        side_effects_2 = [step_to_fail != 3]
        
        mock_at.await_and_confirm_led_pattern.side_effect = side_effects_1
        mock_at.await_led_state.side_effect = side_effects_2 # For admin/sd
        mock_at.confirm_led_solid.side_effect = side_effects_2 # For user/recovery

        # WHEN / THEN
        with pytest.raises(ExpectedException):
            fsm._pin_enrollment(event)

    # Add this new test to the TestApricornDeviceFSM class
    def test_do_manufacturer_reset_keypad_test_failures(self, fsm, mock_at, dut_instance):
        """Covers specific failure points within the manufacturer reset keypad test."""
        ExpectedException = get_reloaded_exception()
        
        # Test failure on the very first key (line 916)
        mock_at.confirm_led_pattern.return_value = False
        with pytest.raises(ExpectedException, match="Failed 'key1' confirmation"):
            with patch('time.sleep'):
                fsm._do_manufacturer_reset(MagicMock(transition=MagicMock()))

        # Test failure on one of the 'other' keys (line 933)
        mock_at.confirm_led_pattern.return_value = True # First key passes now
        mock_at.await_led_state.return_value = False # But the next one fails
        with pytest.raises(ExpectedException, match="Failed 'key2' confirmation"):
            with patch('time.sleep'):
                fsm._do_manufacturer_reset(MagicMock(transition=MagicMock()))

    # Add this new test to the TestApricornDeviceFSM class
    @pytest.mark.parametrize("toggle_method_name", [
        "_basic_disk_toggle", "_removable_media_toggle", "_led_flicker_enable",
        "_lock_override_toggle", "_read_only_toggle", "_read_write_toggle",
        "_self_destruct_toggle",
    ])
    def test_simple_toggles_failure_path(self, fsm, mock_at, dut_instance, toggle_method_name):
        """Covers the generic hardware failure path for all simple toggle methods."""
        # GIVEN
        mock_at.await_and_confirm_led_pattern.return_value = False
        toggle_method = getattr(fsm, toggle_method_name)
        ExpectedException = get_reloaded_exception()

        # Special setup for methods with preconditions
        if toggle_method_name == "_self_destruct_toggle":
            dut_instance.provision_lock = False

        # WHEN / THEN
        with pytest.raises(ExpectedException):
            toggle_method(MagicMock(transition=MagicMock()))

    # --- Other Methods ---

    def test_speed_test(self, fsm, mock_at):
        """Test the speed_test method."""
        target_disk = "/dev/sd_test"
        fsm.speed_test(target=target_disk, event_data=MagicMock(transition=MagicMock()))
        mock_at.run_fio_tests.assert_called_once_with(disk_path=target_disk)