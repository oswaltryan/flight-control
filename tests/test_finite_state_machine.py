# Directory: tests/
# Filename: test_fsm_systematic.py

#############################################################
##
## This test file is designed to systematically cover every function
## in controllers/finite_state_machine.py.
##
## Run this test with the following command:
## pytest tests/test_finite_state_machine.py --cov=controllers.finite_state_machine --cov-report term-missing
##
#############################################################

import pytest
from unittest.mock import MagicMock, call, ANY, patch
import json
import io
import importlib
import time
import logging
import statistics
import sys
from unittest.mock import patch

# --- Module and Class Imports ---
from controllers import finite_state_machine
from controllers.finite_state_machine import (
    ApricornDeviceFSM, DeviceUnderTest, TestSession, TransitionCallbackError, CallableCondition
)
from utils.led_states import LEDs
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
    """Auto-running fixture to ensure DEVICE_PROPERTIES is always loaded."""
    json_path = finite_state_machine._json_path
    with open(json_path, 'r') as f:
        real_properties = json.load(f)
    monkeypatch.setattr(finite_state_machine, 'DEVICE_PROPERTIES', real_properties)

@pytest.fixture
def mock_at():
    """Provides a fresh mock of the hardware controller for each test."""
    at = MagicMock()
    at.confirm_led_pattern.return_value = True
    at.await_and_confirm_led_pattern.return_value = True
    at.await_led_state.return_value = True
    at.confirm_led_solid.return_value = True
    at.confirm_led_solid_strict.return_value = True
    mock_device_info = MagicMock()
    mock_device_info.iSerial = "MOCK_SERIAL_123"
    at.confirm_drive_enum.return_value = (True, mock_device_info)
    at.confirm_device_enum.return_value = (True, mock_device_info)
    at.scan_barcode.return_value = "TEST_SERIAL_123"
    return at

@pytest.fixture
def dut_instance(mock_at):
    """Provides a fresh, clean instance of the DUT for each test."""
    with patch('controllers.finite_state_machine.UnifiedController', return_value=mock_at):
        dut = DeviceUnderTest(at_controller=mock_at)
    return dut

@pytest.fixture
def mock_session(mock_at, dut_instance):
    """Provides a fully mocked TestSession for FSM tests."""
    with patch('controllers.finite_state_machine.UnifiedController', return_value=mock_at):
        session = TestSession(at_controller=mock_at, dut_instance=dut_instance)
    session.log_enumeration = MagicMock()
    session.log_key_press = MagicMock()
    session.add_speed_test_result = MagicMock()
    return session

@pytest.fixture
def session_instance(mock_at, dut_instance):
    """Provides a real, clean instance of the TestSession for testing its own methods."""
    with patch('controllers.finite_state_machine.UnifiedController', return_value=mock_at):
        session = TestSession(at_controller=mock_at, dut_instance=dut_instance)
    return session

@pytest.fixture
def fsm(mock_at, dut_instance, mock_session):
    """Creates a fresh FSM instance using mocked dependencies."""
    fsm_instance = ApricornDeviceFSM(
        at_controller=mock_at,
        session_instance=mock_session,
        dut_instance=dut_instance
    )
    return fsm_instance

# Helper to get the reloaded exception class
def get_reloaded_exception():
    return finite_state_machine.TransitionCallbackError

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
        WHEN the finite_state_machine module is reloaded
        THEN the correct Machine class is imported and used.
        """
        # GIVEN: Set or delete the environment variable
        if diagram_mode_env is None:
            monkeypatch.delenv("FSM_DIAGRAM_MODE", raising=False)
        else:
            monkeypatch.setenv("FSM_DIAGRAM_MODE", diagram_mode_env)

        # WHEN: Reload the module to trigger the conditional import
        importlib.reload(finite_state_machine)

        # THEN: Inspect the reloaded module to see which class was aliased to 'Machine'
        # We check the class name as a string to avoid object identity issues.
        assert finite_state_machine.Machine.__name__ == expected_class_name

class TestModuleLoading:
    """Tests for failures during module loading."""

    @patch('builtins.open', new_callable=MagicMock)
    def test_load_config_file_not_found(self, mock_open, monkeypatch):
        """Test module load failure when JSON file is not found."""
        mock_open.side_effect = FileNotFoundError
        with pytest.raises(FileNotFoundError):
            importlib.reload(finite_state_machine)

    @patch('builtins.open', new_callable=MagicMock)
    def test_load_config_json_decode_error(self, mock_open, monkeypatch):
        """Test module load failure on JSON syntax error."""
        # Simulate reading a file with invalid JSON
        mock_file = MagicMock()
        mock_file.read.return_value = "{'invalid': 'json',}" # Invalid JSON
        mock_open.return_value.__enter__.return_value = mock_file
        
        with pytest.raises(json.JSONDecodeError):
            importlib.reload(finite_state_machine)
            
    @patch('builtins.open', new_callable=MagicMock)
    def test_load_config_unexpected_error(self, mock_open, monkeypatch):
        """Test module load failure on an unexpected exception."""
        mock_open.side_effect = Exception("A random error occurred")
        with pytest.raises(Exception, match="A random error occurred"):
            importlib.reload(finite_state_machine)

# =============================================================================
# === 1. Tests for DeviceUnderTest Class
# =============================================================================
class TestDeviceUnderTest:
    """Unit tests for the DeviceUnderTest state model class."""

    def test_init(self, dut_instance, mock_at):
        """Test that __init__ correctly assigns properties from the loaded JSON."""
        assert dut_instance.at == mock_at
        assert dut_instance.name == "ask3-3639"
        assert dut_instance.bridge_fw == "0501"
        assert dut_instance.fips == 3
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

    def test_init(self):
        """
        Tests that the __init__ method correctly assigns the function and name.
        """
        # GIVEN a lambda function that returns a boolean, and a name string
        # <<< FIX: Change the return value to a boolean >>>
        test_func = lambda: True
        test_name = "my_condition_name"

        # WHEN a CallableCondition is instantiated
        condition = CallableCondition(func=test_func, name=test_name)

        # THEN the attributes should be set correctly
        assert condition.func is test_func
        assert condition.__name__ == test_name

    @pytest.mark.parametrize("func_return_value, expected_result", [
        (True, True),
        (False, False),
        ("any_truthy_value", True),
        (None, False),
    ])
    def test_call(self, func_return_value, expected_result):
        """
        Tests that calling the instance executes the wrapped function and
        returns its boolean-equivalent result. It also tests that arguments
        are passed through correctly.
        """
        # GIVEN a mock function to wrap
        mock_func = MagicMock(return_value=func_return_value)
        condition = CallableCondition(func=mock_func, name="test_call")

        # WHEN the instance is called like a function, with arguments
        result = condition("arg1", kwarg2="value2")

        # THEN the wrapped function should have been called with those same arguments
        mock_func.assert_called_once_with("arg1", kwarg2="value2")

        # AND the final result should be the correct boolean equivalent
        assert result is expected_result

    def test_repr(self):
        """
        Tests that the __repr__ method returns the correct, readable string format.
        """
        # GIVEN a condition with a specific name
        condition = CallableCondition(func=lambda: True, name="is_ready_for_testing")

        # WHEN its representation is requested
        repr_string = repr(condition)

        # THEN the string should be in the expected format
        assert repr_string == "<CallableCondition: is_ready_for_testing>"

# =============================================================================
# === 3. Tests for ApricornDeviceFSM Class
# =============================================================================
class TestTestSession:
    """Unit tests for the TestSession data tracking class."""

    def test_start_new_block_first_call(self, session_instance):
        """
        Tests that start_new_block correctly initializes all attributes
        when called with a new block name.
        """
        # GIVEN: A fresh session instance and a known block name and number.
        block_name = "first_test_block"
        block_number = 1
        
        # To test the reset, set a counter to a non-zero value beforehand.
        session_instance.current_block_pin_enum = 99

        # WHEN: The method is called for the first time.
        # We can patch time.time to get a predictable value for assertion.
        with patch('time.time', return_value=12345.0):
            session_instance.start_new_block(block_name=block_name, current_test_block=block_number)

        # THEN: Verify all attributes are set correctly.
        assert session_instance.current_test_block == block_number
        assert session_instance.test_blocks == [block_name]
        assert session_instance.block_start_time == 12345.0
        
        # Verify all counters were reset to 0.
        assert session_instance.current_block_manufacturer_reset_enum == 0
        assert session_instance.current_block_oob_enum == 0
        assert session_instance.current_block_pin_enum == 0
        assert session_instance.current_block_spi_enum == 0

        # Verify the dictionaries were initialized for the new block name.
        assert session_instance.block_failure_count[block_name] == 0
        assert session_instance.warning_block[block_name] == []
        assert session_instance.failure_description_block[block_name] == []

    def test_start_new_block_re_enters_existing_block(self, session_instance):
        """
        Tests that start_new_block correctly resets counters but does NOT
        clear existing failure/warning logs when called for a block that
        has already been seen.
        """
        # GIVEN: The block has been started once and has some data logged.
        block_name = "re-entered_block"
        session_instance.start_new_block(block_name=block_name, current_test_block=1)
        
        # Add some mock data to the logs.
        session_instance.block_failure_count[block_name] = 1
        session_instance.failure_block[block_name].append("A previous failure")
        session_instance.current_block_pin_enum = 50 # Set a counter to a non-zero value.

        # WHEN: The method is called a second time for the same block name.
        with patch('time.time', return_value=67890.0):
            session_instance.start_new_block(block_name=block_name, current_test_block=2)
            
        # THEN: Verify attributes that should change have been updated.
        assert session_instance.current_test_block == 2 # Should update to new number
        assert session_instance.block_start_time == 67890.0 # Should update to new time
        assert session_instance.current_block_pin_enum == 0 # Should be reset

        # THEN: Verify attributes that should NOT change are preserved.
        # The block name should only appear once in the list of all blocks.
        assert session_instance.test_blocks == [block_name]
        # The previously logged failure data should still be there.
        assert session_instance.block_failure_count[block_name] == 1
        assert session_instance.failure_block[block_name] == ["A previous failure"]

    def test_end_block(self, session_instance):
        """Tests that end_block captures the current time."""
        # GIVEN a session
        # WHEN end_block is called
        with patch('time.time', return_value=99999.9):
            session_instance.end_block()
        # THEN the block_end_time attribute should be updated
        assert session_instance.block_end_time == 99999.9

    def test_log_key_press(self, session_instance):
        """
        Tests that log_key_press correctly initializes and increments
        the key press counter.
        """
        # GIVEN an empty key press dictionary
        assert session_instance.key_press_totals == {}

        # WHEN a key is logged for the first time
        session_instance.log_key_press("key1")
        # THEN it should be initialized to 1
        assert session_instance.key_press_totals["key1"] == 1

        # WHEN the same key is logged again
        session_instance.log_key_press("key1")
        # THEN its count should be incremented
        assert session_instance.key_press_totals["key1"] == 2

        # WHEN a different key is logged
        session_instance.log_key_press("lock")
        # THEN it should be added to the dictionary
        assert session_instance.key_press_totals["lock"] == 1

    @pytest.mark.parametrize("enum_type, expected_attr", [
        ("pin", "current_block_pin_enum"),
        ("oob", "current_block_oob_enum"),
        ("manufacturer_reset", "current_block_manufacturer_reset_enum"),
        ("spi", "current_block_spi_enum"),
    ])
    def test_log_enumeration(self, session_instance, enum_type, expected_attr):
        """
        Tests that log_enumeration correctly increments the specified counter.
        """
        # GIVEN the counter is at 0
        assert getattr(session_instance, expected_attr) == 0

        # WHEN the enumeration is logged
        session_instance.log_enumeration(enum_type)
        # THEN the counter should be 1
        assert getattr(session_instance, expected_attr) == 1

        # WHEN it's logged again
        session_instance.log_enumeration(enum_type)
        # THEN the counter should be 2
        assert getattr(session_instance, expected_attr) == 2

    def test_log_failure(self, session_instance):
        """
        Tests that log_failure correctly appends failure details and
        increments the failure count for a given block.
        """
        # GIVEN a block has been started
        block_name = "test_block_with_failures"
        session_instance.start_new_block(block_name=block_name, current_test_block=1)

        # WHEN a failure is logged
        session_instance.log_failure(
            block_name=block_name,
            failure_summary="Test failed",
            failure_details="The widget did not spin"
        )
        
        # THEN the data should be correctly stored
        assert session_instance.block_failure_count[block_name] == 1
        assert session_instance.failure_block[block_name] == ["Test failed"]
        assert session_instance.failure_description_block[block_name] == ["The widget did not spin"]

        # WHEN a second failure is logged for the same block
        session_instance.log_failure(block_name=block_name, failure_summary="Another failure")
        
        # THEN the new data is appended and the count is updated
        assert session_instance.block_failure_count[block_name] == 2
        assert session_instance.failure_block[block_name] == ["Test failed", "Another failure"]
        # Ensure details are appended even if empty
        assert session_instance.failure_description_block[block_name] == ["The widget did not spin", ""]

    def test_log_warning(self, session_instance):
        """
        Tests that log_warning correctly appends warning details and
        increments the warning count for a given block.
        """
        # GIVEN a block has been started
        block_name = "test_block_with_warnings"
        session_instance.start_new_block(block_name=block_name, current_test_block=1)

        # WHEN a warning is logged
        session_instance.log_warning(
            block_name=block_name,
            warning_summary="Test is slow",
            warning_details="The widget spun slowly"
        )
        
        # THEN the data should be correctly stored
        assert session_instance.block_warning_count[block_name] == 1
        assert session_instance.warning_block[block_name] == ["Test is slow"]
        assert session_instance.warning_description_block[block_name] == ["The widget spun slowly"]

    def test_add_speed_test_result(self, session_instance):
        """
        Tests that add_speed_test_result correctly appends results to the list.
        """
        # GIVEN the results list is empty
        assert session_instance.speed_test_results == []

        # WHEN a result is added
        result1 = {'read': 100.0, 'write': 90.0}
        session_instance.add_speed_test_result(result1)
        # THEN the list contains that result
        assert session_instance.speed_test_results == [result1]

        # WHEN another result is added
        result2 = {'read': 110.0, 'write': 95.0}
        session_instance.add_speed_test_result(result2)
        # THEN it is appended to the list
        assert session_instance.speed_test_results == [result1, result2]

    def test_get_failure_summary_string(self, session_instance):
        """
        Tests that the failure summary string is generated correctly,
        including skipping blocks with no failures.
        """
        # --- SCENARIO 1: No failures at all ---
        # GIVEN a session with no failures
        assert session_instance.get_failure_summary_string() == ""
        
        # --- SCENARIO 2: Failures in multiple blocks ---
        # GIVEN a session with failures in multiple blocks
        session_instance.start_new_block("BlockA", 1)
        session_instance.log_failure("BlockA", "First A fail")
        session_instance.log_failure("BlockA", "Second A fail")
        
        session_instance.start_new_block("BlockB", 2)
        session_instance.log_failure("BlockB", "B failure")

        # WHEN the summary string is generated
        summary = session_instance.get_failure_summary_string()
        
        # THEN the string should be correctly formatted
        expected = "Block 1 (BlockA): [First A fail; Second A fail], Block 2 (BlockB): [B failure]"
        assert summary == expected
        
        # --- SCENARIO 3: A mix of failing and non-failing blocks ---
        # GIVEN a third block is run with NO failures
        session_instance.start_new_block("BlockC_passed", 3)
        # Note: We do NOT call log_failure for BlockC_passed
        
        # WHEN the summary string is generated again
        summary_with_pass = session_instance.get_failure_summary_string()
        
        # THEN the string should be IDENTICAL to the previous one,
        # proving that BlockC was correctly skipped by the 'continue'.
        assert summary_with_pass == expected

    def test_generate_summary_report_with_data(self, session_instance, dut_instance):
        """
        Tests that generate_summary_report logs all sections correctly when
        the session has accumulated data, including the 'Passed' case.
        """
        # ... (GIVEN block is unchanged) ...
        # GIVEN: A session with pre-populated data for all report sections.
        session_instance.script_title = "My Test Script"
        dut_instance.secure_key = False
        
        session_instance.key_press_totals = {'key1': 5, 'lock': 2}
        session_instance.test_blocks = ["BlockA", "BlockB", "BlockC"]
        session_instance.block_enumeration_totals = {
            "BlockA": {'pin': 2, 'oob': 1},
            "BlockB": {'manufacturer_reset': 1},
            "BlockC": {'spi': 3}
        }
        session_instance.failure_block = {
            "BlockA": ["First fail"], "BlockB": ["B is broken"], "BlockC": []
        }
        session_instance.warning_block = {
            "BlockA": ["A is slow"], "BlockB": ["A warning"], "BlockC": []
        }
        session_instance.speed_test_results = [
            {'block': 'BlockA', 'read': 100.0, 'write': 80.0},
            {'block': 'BlockB', 'read': 110.0, 'write': 85.0}
        ]
        session_instance.usb3_fail_count = 1
        
        mock_logger = MagicMock()
        session_instance.logger = mock_logger

        # WHEN
        session_instance.generate_summary_report()

        # THEN
        log_output = "\n".join([call.args[0] for call in mock_logger.info.call_args_list])
        warning_output = "\n".join([call.args[0] for call in mock_logger.warning.call_args_list])
        error_output = "\n".join([call.args[0] for call in mock_logger.error.call_args_list])
        
        # --- Assertions for each section ---
        assert "My Test Script Script Details" in log_output
        assert "key1: 5" in log_output
        assert "lock: 2" in log_output
        
        # Block 1 (A): resets=0, oob=1, pin=2, spi=0
        assert "Block 1 :   0   |   1   |   2   |   0   |" in log_output
        # Block 2 (B): resets=1, oob=0, pin=0, spi=0
        assert "Block 2 :   1   |   0   |   0   |   0   |" in log_output
        # Block 3 (C): resets=0, oob=0, pin=0, spi=3
        assert "Block 3 :   0   |   0   |   0   |   3   |" in log_output
        # Totals: resets=1, oob=1, pin=2, spi=3
        assert "Total   :   1   |   1   |   2   |   3   |" in log_output
        
        assert "Block 1 (BlockA):" in log_output
        assert "- First fail" in error_output
        assert "- A is slow" in warning_output
        
        assert "Block 2 (BlockB):" in log_output
        assert "- B is broken" in error_output
        assert "- A warning" in warning_output
        
        assert "Block 3 (BlockC): Passed" in log_output

        assert "Total Number of Failures: 2" in error_output
        assert "Total Number of Warnings: 2" in warning_output
        
        assert "BlockA: Read: 100.0 MB/s, Write: 80.0 MB/s" in log_output
        assert "BlockB: Read: 110.0 MB/s, Write: 85.0 MB/s" in log_output
        assert "Avg: 105.0 MB/s" in log_output
        assert "1 USB3 Failures detected" in warning_output
        assert "My Test Script script complete" in log_output

    def test_generate_summary_report_empty(self, session_instance):
        """
        Tests that generate_summary_report handles a session with no data gracefully.
        """
        # GIVEN: A completely fresh session instance
        mock_logger = MagicMock()
        session_instance.logger = mock_logger
    
        # WHEN: The summary report is generated.
        session_instance.generate_summary_report()
    
        # THEN: The log output should indicate that no data was tracked for key sections.
        log_output = "\n".join([call.args[0] for call in mock_logger.info.call_args_list])
    
        assert "No key presses were tracked" in log_output
        assert "Total   :   0   |   0   |   0   |   0   |" in log_output
        assert "Block Result:" in log_output
        # Verify that sections for failures, warnings, and speed tests are not present
        assert "Failure(s):" not in log_output
        assert "Warning(s):" not in log_output
        assert "Speed Test Block Results:" not in log_output

    @patch.object(TestSession, '_handle_missing_serial_number')
    @patch.object(TestSession, 'generate_summary_report')
    @patch.object(TestSession, 'get_failure_summary_string')
    def test_end_session_and_report_with_failures(
        self,
        mock_get_failure_summary,
        mock_generate_report,
        mock_handle_serial,
        session_instance,
        mock_at
    ):
        """
        Tests that end_session_and_report calls all helpers and returns the
        failure string when failures are present.
        """
        # GIVEN: The get_failure_summary_string method is mocked to return a failure message
        failure_message = "Block 1: [Something failed]"
        mock_get_failure_summary.return_value = failure_message

        # WHEN: The end_session_and_report method is called
        result = session_instance.end_session_and_report()

        # THEN: Verify all helper methods were called exactly once.
        mock_handle_serial.assert_called_once()
        mock_generate_report.assert_called_once()
        mock_get_failure_summary.assert_called_once()
        
        # AND: Verify the hardware cleanup commands were sent.
        mock_at.off.assert_has_calls([call("usb3"), call("connect")], any_order=True)
        
        # AND: The method should return the failure string.
        assert result == failure_message

    @patch.object(TestSession, '_handle_missing_serial_number')
    @patch.object(TestSession, 'generate_summary_report')
    @patch.object(TestSession, 'get_failure_summary_string')
    def test_end_session_and_report_no_failures(
        self,
        mock_get_failure_summary,
        mock_generate_report,
        mock_handle_serial,
        session_instance,
        mock_at
    ):
        """
        Tests that end_session_and_report calls all helpers and returns None
        when no failures are present.
        """
        # GIVEN: The get_failure_summary_string method is mocked to return an empty string
        mock_get_failure_summary.return_value = ""

        # WHEN: The end_session_and_report method is called
        result = session_instance.end_session_and_report()

        # THEN: Verify all helper methods were called exactly once.
        mock_handle_serial.assert_called_once()
        mock_generate_report.assert_called_once()
        mock_get_failure_summary.assert_called_once()

        # AND: Verify the hardware cleanup commands were sent.
        mock_at.off.assert_has_calls([call("usb3"), call("connect")], any_order=True)

        # AND: The method should return None since there were no failures.
        assert result is None

    def test_handle_missing_serial_number_skips_if_already_present(self, session_instance, dut_instance):
        """
        Tests that the method returns immediately if a serial number is already set.
        """
        # GIVEN: The DUT already has a serial number
        dut_instance.serial_number = "EXISTING_SERIAL"
        
        # WHEN the method is called
        # THEN it should not call input() and should return immediately
        with patch('builtins.input') as mock_input:
            session_instance._handle_missing_serial_number()
            mock_input.assert_not_called()
        
        # AND the original serial number should be unchanged
        assert dut_instance.serial_number == "EXISTING_SERIAL"

    def test_handle_missing_serial_number_skips_for_dev_board(self, session_instance, dut_instance):
        """
        Tests that the method returns immediately for development boards.
        """
        # GIVEN: The DUT is a development board and has no serial number
        dut_instance.serial_number = ""
        dut_instance.device_name = "my-development-board-rev1"
        
        # WHEN the method is called
        # THEN it should not call input() and should return immediately
        with patch('builtins.input') as mock_input:
            session_instance._handle_missing_serial_number()
            mock_input.assert_not_called()
            
        # AND the serial number remains empty
        assert dut_instance.serial_number == ""

    def test_handle_missing_serial_number_valid_input_first_try(self, session_instance, dut_instance):
        """
        Tests the happy path where the user enters a valid serial number
        on the first attempt.
        """
        # GIVEN: The DUT has no serial number
        dut_instance.serial_number = ""
        dut_instance.device_name = "production-device"
        valid_serial = "123456789012"
        
        # WHEN the method is called, and we mock the user's input
        with patch('builtins.input', return_value=valid_serial) as mock_input:
            session_instance._handle_missing_serial_number()
            
            # THEN input() should have been called exactly once
            mock_input.assert_called_once()
        
        # AND the DUT's serial number should be updated
        assert dut_instance.serial_number == valid_serial

    def test_handle_missing_serial_number_invalid_then_valid_input(self, session_instance, dut_instance, caplog):
        """
        Tests the loop where the user provides invalid input first,
        then valid input.
        """
        # GIVEN: The DUT has no serial number
        dut_instance.serial_number = ""
        dut_instance.device_name = "production-device"
        valid_serial = "987654321098"
        
        # WHEN we simulate the user typing an invalid value, then a valid one
        with patch('builtins.input', side_effect=["invalid-input", valid_serial]) as mock_input:
            with caplog.at_level(logging.WARNING, logger="DeviceFSM.Simplified"):
                session_instance._handle_missing_serial_number()
                
                # THEN input() should have been called twice
                assert mock_input.call_count == 2
                
        # AND a warning message should have been logged
        assert "Invalid input" in caplog.text
        
        # AND the DUT's serial number should be updated with the final, valid value
        assert dut_instance.serial_number == valid_serial

# =============================================================================
# === 4. Tests for ApricornDeviceFSM Class
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

    @pytest.mark.parametrize("diagram_mode_env, expect_graph_engine", [
    # Case 1: Diagram mode is ON, expect the kwarg
    pytest.param(
        'true', True,
        marks=pytest.mark.skipif(not DIAGRAM_TOOLS_INSTALLED, reason="Diagramming libraries not installed.")
    ),
    # Case 2: Diagram mode is OFF, do not expect the kwarg
    ('false', False),
    ])
    def test_fsm_initialization_with_diagram_mode(self, monkeypatch, mock_at, dut_instance, mock_session, diagram_mode_env, expect_graph_engine):
        """
        GIVEN a specific FSM_DIAGRAM_MODE environment setting
        WHEN the ApricornDeviceFSM is initialized
        THEN the underlying Machine class is instantiated with the correct kwargs.
        This specifically covers the `if DIAGRAM_MODE:` block in the FSM's __init__.
        """
        # GIVEN: The environment is set and the FSM module is reloaded to pick it up.
        monkeypatch.setenv("FSM_DIAGRAM_MODE", diagram_mode_env)
        importlib.reload(finite_state_machine)

        # We patch the Machine class within the FSM's module namespace.
        with patch('controllers.finite_state_machine.Machine') as mock_machine_constructor:
            # WHEN: The FSM is instantiated.
            fsm_instance = finite_state_machine.ApricornDeviceFSM(
                at_controller=mock_at,
                session_instance=mock_session,
                dut_instance=dut_instance
            )

            # THEN: Assert the constructor for the Machine was called.
            mock_machine_constructor.assert_called_once()
            
            # THEN: Inspect the keyword arguments passed to the constructor.
            call_kwargs = mock_machine_constructor.call_args.kwargs
            
            if expect_graph_engine:
                assert 'graph_engine' in call_kwargs
                assert call_kwargs['graph_engine'] == 'pygraphviz'
            else:
                assert 'graph_engine' not in call_kwargs

    def test_log_state_change_details(self, fsm, caplog):
        """Test that _log_state_change_details logs correctly."""
        # GIVEN: The FSM is in its initial state 'OFF'
        assert fsm.state == 'OFF'

        # We need to mock the 'before' and 'on_enter' callbacks for the
        # power_on transition to prevent further automatic transitions.
        fsm._do_power_on = MagicMock()
        fsm.on_enter_POWER_ON_SELF_TEST = MagicMock() # <<< FIX: Mock this method

        # WHEN: A real transition is triggered
        with caplog.at_level(logging.INFO):
             fsm.power_on(usb3=True)

        # THEN: The FSM's internal state should have changed and STOPPED at POWER_ON_SELF_TEST
        assert fsm.state == 'POWER_ON_SELF_TEST'

        # AND: The log message for the FIRST transition should be present.
        # We check the log messages directly for more precise testing.
        assert any(
            "State changed: OFF -> POWER_ON_SELF_TEST (Event: power_on)" in record.message
            for record in caplog.records
        )

    def test_log_state_change_details_on_initialization(self, fsm, caplog):
        """
        Test that _log_state_change_details logs the initial state correctly
        when the FSM is first created. This covers the 'if event_data.transition is None' block.
        """
        # GIVEN: A fully constructed FSM from our fixture
        assert fsm.state == 'OFF'

        # AND: A special event object that simulates the one sent on initialization
        event_data_on_init = MagicMock()
        event_data_on_init.transition = None

        # WHEN: We manually call the callback function, ensuring logs are captured
        # from the FSM's specific logger.
        with caplog.at_level(logging.INFO, logger="DeviceFSM.Simplified"):
            fsm._log_state_change_details(event_data_on_init)

        # THEN: The initialization log message should have been captured.
        assert f"FSM initialized to state: {fsm.state}" in caplog.text

    def test_init_with_explicit_serial_number(self, mock_at):
        """
        Tests that passing a serial number to the constructor correctly sets
        the instance attribute and the module-level cache. This covers the
        'if scanned_serial_number is not None:' branch.
        """
        # GIVEN: The module-level cache is initially None to prove it gets updated
        finite_state_machine._CACHED_SCANNED_SERIAL = None
        explicit_serial = "EXPLICIT_SN_12345"

        # WHEN: A DeviceUnderTest is instantiated with an explicit serial number
        dut = DeviceUnderTest(at_controller=mock_at, scanned_serial_number=explicit_serial)

        # THEN: The instance's attribute should be set to the explicit serial
        assert dut.scanned_serial_number == explicit_serial

        # AND: The module-level cache should also be updated with the explicit serial
        assert finite_state_machine._CACHED_SCANNED_SERIAL == explicit_serial

    @pytest.mark.parametrize("valid_enum_type", [
        "pin",
        "oob",
        "reset",
        "spi"
    ])
    def test_increment_enumeration_count_valid_type(self, fsm, valid_enum_type):
        """
        Tests that a valid enumeration type is correctly logged to the session.
        """
        # GIVEN an FSM with a mocked session
        
        # WHEN the method is called with a valid enumeration type
        fsm._increment_enumeration_count(valid_enum_type)
        
        # THEN the session's log_enumeration method should have been called with that type
        fsm.session.log_enumeration.assert_called_once_with(valid_enum_type)

    def test_increment_enumeration_count_invalid_type(self, fsm, caplog):
        """
        Tests that an invalid enumeration type is not logged to the session
        and that a warning is logged instead.
        """
        # GIVEN an FSM with a mocked session and logger
        invalid_type = "not_a_real_enum"
        fsm.logger = MagicMock() # Use a mock logger to check the warning call

        # WHEN the method is called with an invalid type
        fsm._increment_enumeration_count(invalid_type)

        # THEN the session's log_enumeration method should NOT have been called
        fsm.session.log_enumeration.assert_not_called()
        
        # AND a warning should have been logged to the FSM's logger
        fsm.logger.warning.assert_called_once_with(
            f"Invalid enumeration type '{invalid_type}' passed for tracking."
        )

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

    @pytest.mark.parametrize("scenario", ["hw_failure", "zero_counter", "specific_pin"])
    def test_enter_invalid_pin_all_scenarios(self, fsm, mock_at, dut_instance, caplog, scenario):
        """
        Tests all scenarios for _enter_invalid_pin:
        1. Hardware failure (REJECT pattern not seen).
        2. Brute force counter is already zero.
        3. A specific invalid PIN is provided via kwargs.
        """
        # Set the logger for caplog to listen to for all scenarios in this test
        caplog.set_level(logging.INFO, logger="DeviceFSM.Simplified")

        ExpectedException = get_reloaded_exception()
    
        if scenario == "hw_failure":
            # GIVEN: The hardware check will fail
            mock_at.await_and_confirm_led_pattern.return_value = False
    
            # WHEN: The function is called
            result = fsm._enter_invalid_pin(MagicMock(kwargs={}))
    
            # THEN: It should return False and not decrement the counter
            assert result is False
            assert dut_instance.brute_force_counter_current == 20 # Unchanged from default
            assert "Device did not show REJECT pattern" in caplog.text

        elif scenario == "zero_counter":
            # GIVEN: The brute force counter is already at zero
            dut_instance.brute_force_counter_current = 0
            mock_at.await_and_confirm_led_pattern.return_value = True

            # WHEN: The function is called
            result = fsm._enter_invalid_pin(MagicMock(kwargs={}))

            # THEN: It should succeed but not change the counter
            assert result is True
            assert dut_instance.brute_force_counter_current == 0 # Unchanged

        elif scenario == "specific_pin":
            # GIVEN: A specific PIN is passed in the event kwargs
            initial_count = dut_instance.brute_force_counter_current
            specific_pin = ['old', 'pin', '1', '2', '3']
            event = MagicMock(kwargs={'pin': specific_pin})
            mock_at.await_and_confirm_led_pattern.return_value = True

            # WHEN: The function is called
            result = fsm._enter_invalid_pin(event)

            # THEN: The specific log message should be present and the counter decremented
            # <<< FIX: The assertion will now pass because caplog is listening correctly >>>
            assert "Intentionally entering a specific known-invalid PIN" in caplog.text
            assert result is True
            mock_at.sequence.assert_called_once_with(specific_pin)
            assert dut_instance.brute_force_counter_current == initial_count - 1
    
    @pytest.mark.parametrize("hw_success, log_msg", [(True, "Stable ADMIN_MODE confirmed"), (False, "Failed to confirm stable ADMIN_MODE LEDs")])
    def test_on_enter_ADMIN_MODE(self, fsm, mock_at, caplog, hw_success, log_msg):
        # GIVEN: The hardware mock is set up for the scenario
        mock_at.confirm_led_solid.return_value = hw_success
        
        # WHEN: The on_enter method is called, while caplog is listening to the correct logger
        with caplog.at_level(logging.INFO, logger="DeviceFSM.Simplified"):
            fsm.on_enter_ADMIN_MODE(MagicMock())
            
        # THEN: The expected log message should have been captured
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
        
    @pytest.mark.parametrize("hw_led_solid_success", [True, False])
    @pytest.mark.parametrize("hw_await_state_success", [True, False])
    def test_on_enter_FACTORY_MODE(self, fsm, mock_at, caplog, hw_led_solid_success, hw_await_state_success):
        """
        Tests all success and failure paths in on_enter_FACTORY_MODE, including
        the initial LED check and the keypad test failure.
        """
        # GIVEN
        mock_at.confirm_led_solid.return_value = hw_led_solid_success
        mock_at.await_led_state.return_value = hw_await_state_success
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        if not hw_led_solid_success:
            # Case 1: The initial solid LED check fails.
            fsm.on_enter_FACTORY_MODE(MagicMock())
            assert "Failed to confirm FACTORY_MODE LEDs" in caplog.text
            mock_at.await_led_state.assert_not_called() # Keypad test should be skipped
            # Ensure power_off was NOT called, as it's not in this function's logic
            assert mock_at.off.call_count == 0
            return # End of this test case

        if not hw_await_state_success:
            # Case 2: The keypad test fails on one of the keys.
            # This will cover the final missing lines (570-571).
            with pytest.raises(ExpectedException, match="Failed 'key1' confirmation"):
                fsm.on_enter_FACTORY_MODE(MagicMock())
        else:
            # Case 3: Happy path, everything succeeds.
            fsm.on_enter_FACTORY_MODE(MagicMock())
            assert "Failed to confirm FACTORY_MODE LEDs" not in caplog.text

    @pytest.mark.parametrize("led_success, enum_success", [
        (True, True),   # Happy path
        (True, False),  # Enum fails
        (False, True),  # LED check fails
    ])
    def test_on_enter_OOB_MODE(self, fsm, mock_at, caplog, dut_instance, led_success, enum_success):
        # GIVEN
        mock_at.confirm_led_solid.return_value = led_success
        
        # Create a mock device object to be part of the tuple
        mock_device_info = MagicMock()
        mock_device_info.iSerial = "MOCK_SERIAL_123"
        # Set the return value to be a tuple, where the first element is the
        # success status from the test's parameterization.
        mock_at.confirm_device_enum.return_value = (enum_success, mock_device_info)
        
        fsm.post_fail = MagicMock()
        # We must reset the DUT's property to its default before the test
        dut_instance.completed_cmfr = True
    
        # WHEN
        fsm.on_enter_OOB_MODE(MagicMock())

        # THEN
        if not led_success:
            assert dut_instance.completed_cmfr is False
            mock_at.off.assert_any_call("connect")
            assert not fsm.post_fail.called
        elif not enum_success:
            fsm.post_fail.assert_called_once_with(details="OOB_MODE_ENUM_FAILED")
            assert dut_instance.completed_cmfr is True
        else: # Happy Path
            assert not fsm.post_fail.called
            assert dut_instance.completed_cmfr is True

    def test_on_enter_OOB_MODE_fails_if_no_serial(self, fsm, dut_instance, caplog):
        """
        Tests that on_enter_OOB_MODE fails correctly if no serial number
        was scanned at startup.
        """
        # GIVEN: The DUT's scanned_serial_number is None
        dut_instance.scanned_serial_number = None
        
        # AND the initial LED check will succeed, allowing the method to proceed
        fsm.at.confirm_led_solid.return_value = True
        
        # AND we have a mock for the post_fail trigger
        fsm.post_fail = MagicMock()
        
        # WHEN the on_enter method is called
        with caplog.at_level(logging.ERROR, logger="DeviceFSM.Simplified"):
            fsm.on_enter_OOB_MODE(MagicMock())

        # THEN: The post_fail method should have been called with the correct details
        fsm.post_fail.assert_called_once_with(details="OOB_ENUM_FAILED_NO_SERIAL")
        
        # AND: The specific error message should have been logged
        assert "Cannot confirm device enumeration: No serial number was scanned at startup." in caplog.text
        
        # AND: The confirm_device_enum method should NOT have been called
        fsm.at.confirm_device_enum.assert_not_called()

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
    def test_on_enter_UNLOCKED_ADMIN(self, fsm, mock_at, dut_instance, enum_success):
        """Tests the on_enter_UNLOCKED_ADMIN callback for both success and failure."""
        # GIVEN: The mock is set up to return the correct tuple format
        mock_device_info = MagicMock()
        mock_at.confirm_drive_enum.return_value = (enum_success, mock_device_info)
        fsm.post_fail = MagicMock()
        dut_instance.scanned_serial_number = "TEST_SERIAL_123" # Ensure a serial number exists

        # WHEN
        fsm.on_enter_UNLOCKED_ADMIN(MagicMock())
        
        # THEN
        if not enum_success:
            fsm.post_fail.assert_called_once_with(details="UNLOCKED_ADMIN_ENUM_FAILED")
        else:
            assert not fsm.post_fail.called
            # Verify the enumeration count was incremented
            fsm.session.log_enumeration.assert_called_with('pin')

    def test_on_enter_UNLOCKED_ADMIN_sets_linux_path(self, fsm, mock_at, dut_instance, monkeypatch):
        """
        Tests that the on_enter_UNLOCKED_ADMIN callback correctly sets the
        disk_path attribute when running on a Linux-like platform.
        """
        # GIVEN: We use monkeypatch to simulate running on Linux
        monkeypatch.setattr(sys, 'platform', 'linux')
        
        # AND: The mock enumeration will succeed and return a mock device object
        # with the expected Linux-specific attribute.
        mock_device_info = MagicMock()
        mock_device_info.blockDevice = "/dev/sdb" # Simulate the Linux attribute
        mock_at.confirm_drive_enum.return_value = (True, mock_device_info)
        
        # AND: The DUT has a valid scanned serial number
        dut_instance.scanned_serial_number = "TEST_SERIAL_123"
        # AND: The initial disk_path is empty
        dut_instance.disk_path = ""

        # WHEN: The on_enter method is called
        fsm.on_enter_UNLOCKED_ADMIN(MagicMock())

        # THEN: The dut.disk_path should have been updated with the value
        # from the mock_device_info.blockDevice attribute.
        assert dut_instance.disk_path == "/dev/sdb"
        
    @pytest.mark.parametrize("enum_success", [True, False])
    def test_on_enter_UNLOCKED_USER(self, fsm, mock_at, dut_instance, enum_success):
        """Tests the on_enter_UNLOCKED_USER callback for both success and failure."""
        # GIVEN: The mock is set up to return the correct tuple format
        mock_device_info = MagicMock()
        mock_at.confirm_drive_enum.return_value = (enum_success, mock_device_info)
        fsm.post_fail = MagicMock()
        dut_instance.scanned_serial_number = "TEST_SERIAL_123"

        # WHEN
        fsm.on_enter_UNLOCKED_USER(MagicMock())
        
        # THEN
        if not enum_success:
            fsm.post_fail.assert_called_once_with(details="UNLOCKED_USER_ENUM_FAILED")
        else:
            assert not fsm.post_fail.called
            fsm.session.log_enumeration.assert_called_with('pin')

    def test_on_enter_UNLOCKED_USER_sets_linux_path(self, fsm, mock_at, dut_instance, monkeypatch):
        """
        Tests that the on_enter_UNLOCKED_USER callback correctly sets the
        disk_path attribute when running on a Linux-like platform.
        """
        # GIVEN: We use monkeypatch to simulate running on Linux
        monkeypatch.setattr(sys, 'platform', 'linux')
        
        # AND: The mock enumeration will succeed and return a mock device object
        # with the expected Linux-specific attribute.
        mock_device_info = MagicMock()
        mock_device_info.blockDevice = "/dev/sdc" # Use a different path to distinguish
        mock_at.confirm_drive_enum.return_value = (True, mock_device_info)
        
        # AND: The DUT has a valid scanned serial number
        dut_instance.scanned_serial_number = "TEST_SERIAL_123"
        # AND: The initial disk_path is empty
        dut_instance.disk_path = ""

        # WHEN: The on_enter method is called
        fsm.on_enter_UNLOCKED_USER(MagicMock())

        # THEN: The dut.disk_path should have been updated with the value
        # from the mock_device_info.blockDevice attribute.
        assert dut_instance.disk_path == "/dev/sdc"

    @pytest.mark.parametrize("enum_success", [True, False])
    @pytest.mark.parametrize("led_success", [True, False])
    def test_on_enter_UNLOCKED_RESET(self, fsm, mock_at, dut_instance, enum_success, led_success):
        """Tests the on_enter_UNLOCKED_RESET callback."""
        # GIVEN
        mock_at.await_and_confirm_led_pattern.return_value = led_success
        mock_device_info = MagicMock()
        mock_at.confirm_drive_enum.return_value = (enum_success, mock_device_info)
        fsm.post_fail = MagicMock()
        dut_instance.scanned_serial_number = "TEST_SERIAL_123"
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        if not led_success:
            # If the initial LED pattern check fails, it should raise an exception
            with pytest.raises(ExpectedException, match="Failed Manufacturer Reset unlock LED pattern"):
                fsm.on_enter_UNLOCKED_RESET(MagicMock())
            # And no further checks should be made
            mock_at.confirm_drive_enum.assert_not_called()
            return

        # If LED check passes, proceed with the rest of the logic
        fsm.on_enter_UNLOCKED_RESET(MagicMock())

        if not enum_success:
            fsm.post_fail.assert_called_once_with(details="UNLOCKED_RESET_ENUM_FAILED")
        else:
            assert not fsm.post_fail.called
            fsm.session.log_enumeration.assert_called_with('reset')

    def test_on_enter_UNLOCKED_RESET_sets_linux_path(self, fsm, mock_at, dut_instance, monkeypatch):
        """
        Tests that the on_enter_UNLOCKED_RESET callback correctly sets the
        disk_path attribute when running on a Linux-like platform.
        """
        # GIVEN: We use monkeypatch to simulate running on Linux
        monkeypatch.setattr(sys, 'platform', 'linux')
        
        # AND: All mock hardware checks will succeed
        mock_at.await_and_confirm_led_pattern.return_value = True
        mock_device_info = MagicMock()
        mock_device_info.blockDevice = "/dev/sdd" # Use a unique path
        mock_at.confirm_drive_enum.return_value = (True, mock_device_info)
        
        # AND: The DUT has a valid scanned serial number and empty disk path
        dut_instance.scanned_serial_number = "TEST_SERIAL_123"
        dut_instance.disk_path = ""

        # WHEN: The on_enter method is called
        fsm.on_enter_UNLOCKED_RESET(MagicMock())

        # THEN: The dut.disk_path should have been updated with the value
        # from the mock_device_info.blockDevice attribute.
        assert dut_instance.disk_path == "/dev/sdd"

    def test_unlocked_enum_fails_if_no_serial(self, fsm):
        """
        Tests that on_enter for all UNLOCKED states correctly fails if no
        serial number was previously scanned.
        """
        # GIVEN: The scanned_serial_number on the DUT is None
        fsm.dut.scanned_serial_number = None
        fsm.post_fail = MagicMock()

        # --- Test for UNLOCKED_ADMIN ---
        # WHEN we call the on_enter method for UNLOCKED_ADMIN
        fsm.on_enter_UNLOCKED_ADMIN(MagicMock())
        # THEN it should fail with the correct details
        fsm.post_fail.assert_called_once_with(details="ADMIN_ENUM_FAILED_NO_SERIAL")

        # --- Test for UNLOCKED_USER ---
        fsm.post_fail.reset_mock() # Reset the mock for the next call
        # WHEN we call the on_enter method for UNLOCKED_USER
        fsm.on_enter_UNLOCKED_USER(MagicMock())
        # THEN it should fail with the correct details
        fsm.post_fail.assert_called_once_with(details="USER_ENUM_FAILED_NO_SERIAL")

        # <<< FIX: Add the test case for UNLOCKED_RESET >>>
        # --- Test for UNLOCKED_RESET ---
        fsm.post_fail.reset_mock() # Reset the mock again
        # GIVEN the initial LED check for RESET will pass
        fsm.at.await_and_confirm_led_pattern.return_value = True

        # WHEN we call the on_enter method for UNLOCKED_RESET
        fsm.on_enter_UNLOCKED_RESET(MagicMock())
        # THEN it should fail with the correct details
        fsm.post_fail.assert_called_once_with(details="RESET_ENUM_FAILED_NO_SERIAL")

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



    # --- 'before' Callbacks ---

    @pytest.mark.parametrize("usb3_arg, vbus_state, hw_success", [
        (True, True, True),    # Standard success case (USB3 on)
        (False, True, True),   # USB2 success case (USB3 off)
        (True, False, True),   # VBUS is off, skip LED check (USB3 on)
        (True, True, False),   # Hardware fails LED check (USB3 on)
    ])
    def test_do_power_on_scenarios(self, fsm, mock_at, dut_instance, usb3_arg, vbus_state, hw_success):
        """Tests various scenarios in the _do_power_on method."""
        # GIVEN
        dut_instance.vbus = vbus_state
        
        # <<< FIX: Mock the correct method that is actually called >>>
        mock_at.confirm_led_pattern.return_value = hw_success
        
        event = MagicMock(transition=MagicMock(), kwargs={'usb3': usb3_arg})
        ExpectedException = get_reloaded_exception()
    
        # WHEN / THEN
        if not hw_success:
            with pytest.raises(ExpectedException, match="Failed Startup Self-Test LED confirmation"):
                fsm._do_power_on(event)
            # It should still check for the pattern even if it fails
            mock_at.confirm_led_pattern.assert_called_once()
            return

        fsm._do_power_on(event)

        # Assertions
        if usb3_arg:
            mock_at.on.assert_has_calls([call("usb3"), call("connect")], any_order=True)
            assert mock_at.on.call_count == 2
        else:
            mock_at.on.assert_called_once_with("connect")

        if vbus_state:
            # <<< FIX: Assert that the correct method was called >>>
            mock_at.confirm_led_pattern.assert_called_once()
        else:
            mock_at.confirm_led_pattern.assert_not_called()

    def test_do_power_on_invalid_arg(self, fsm):
        """Tests that _do_power_on raises an error for an invalid 'usb3' argument type."""
        # GIVEN an invalid argument for usb3
        event = MagicMock(transition=MagicMock(), kwargs={'usb3': 'not-a-bool'})
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        with pytest.raises(ExpectedException, match="usb3 argument, if provided, must be a boolean"):
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

    @pytest.mark.parametrize("hw_success", [True, False])
    def test_enter_admin_mode_login(self, fsm, mock_at, dut_instance, hw_success):
        """
        Tests both the success and failure paths for entering Admin Mode.
        This specifically covers the LED confirmation check.
        """
        # GIVEN: The FSM is ready and the hardware check will either succeed or fail.
        dut_instance.admin_pin = ['1', '2', '3']
        mock_at.confirm_led_pattern.return_value = hw_success
        ExpectedException = get_reloaded_exception()
        
        # WHEN the function is called
        if not hw_success:
            # THEN: If the hardware check fails, an exception should be raised.
            with pytest.raises(ExpectedException, match="Failed Admin Mode Login LED confirmation"):
                fsm._enter_admin_mode_login(MagicMock(transition=MagicMock()))
            
            # AND: The function should have aborted before entering the PIN.
            mock_at.sequence.assert_not_called()
        else:
            # THEN: If the hardware check succeeds, the function completes normally.
            fsm._enter_admin_mode_login(MagicMock(transition=MagicMock()))
            
            # AND: The PIN entry sequence should have been called.
            mock_at.sequence.assert_called_once_with(dut_instance.admin_pin)

        # FINALLY: Verify that the initial key press and the LED check were always attempted.
        mock_at.press.assert_called_once_with(['key0', 'unlock'], duration_ms=6000)
        mock_at.confirm_led_pattern.assert_called_once_with(
            LEDs['RED_LOGIN'], 
            clear_buffer=True, 
            replay_extra_context=ANY
        )

    @pytest.mark.parametrize("hw_success", [True, False])
    def test_enter_last_try_pin(self, fsm, mock_at, hw_success):
        """
        Tests both the success and failure paths for the 'last try' login sequence.
        This specifically covers the LED confirmation check.
        """
        # GIVEN: The hardware check will either succeed or fail.
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        ExpectedException = get_reloaded_exception()
        
        # WHEN the function is called
        if not hw_success:
            # THEN: If the hardware check fails, an exception should be raised.
            with pytest.raises(ExpectedException, match="Failed 'LASTTRY' Login confirmation"):
                fsm._enter_last_try_pin(MagicMock())
            
            # AND: The function should have aborted before entering the final sequence.
            mock_at.sequence.assert_not_called()
        else:
            # THEN: If the hardware check succeeds, the function completes normally.
            fsm._enter_last_try_pin(MagicMock())
            
            # AND: The final key sequence should have been entered.
            mock_at.sequence.assert_called_once_with(
                ['key5', 'key2', 'key7', 'key8', 'key8', 'key7', 'key9', 'unlock']
            )

        # FINALLY: Verify that the initial key press and the LED check were always attempted.
        mock_at.press.assert_called_once_with(['key5', 'unlock'], duration_ms=6000)
        mock_at.await_and_confirm_led_pattern.assert_called_once_with(
            LEDs["RED_GREEN"], 
            timeout=10
        )

    def test_do_user_reset_from_admin_mode(self, fsm, mock_at, dut_instance, monkeypatch):
        """Test successful user reset when initiated from ADMIN_MODE."""
        # GIVEN
        mock_sleep = MagicMock()
        monkeypatch.setattr(time, 'sleep', mock_sleep)
        fsm.state = 'ADMIN_MODE'
        dut_instance.admin_pin = ['1']
        
        # WHEN
        fsm._do_user_reset(MagicMock(transition=MagicMock()))
        
        # THEN
        mock_sleep.assert_called_with(9)
        assert dut_instance.admin_pin == []
        mock_at.sequence.assert_called_once_with([["lock", "unlock", "key2"]], pause_duration_ms=ANY)
        mock_at.confirm_led_solid.assert_called_once()
        mock_at.on.assert_not_called() # Should use sequence, not .on()

    @pytest.mark.parametrize("hw_success", [True, False])
    def test_do_user_reset_from_standby_mode(self, fsm, mock_at, dut_instance, hw_success, monkeypatch):
        """
        Test user reset when initiated from a non-ADMIN_MODE state (e.g., STANDBY).
        This covers the 'else' block of the function.
        """
        # GIVEN: The FSM is in a state other than ADMIN_MODE
        mock_sleep = MagicMock()
        monkeypatch.setattr(time, 'sleep', mock_sleep)
        fsm.state = 'STANDBY_MODE'
        dut_instance.admin_pin = ['1']
        
        # GIVEN: The hardware check for the initiation pattern will either succeed or fail
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        
        # WHEN / THEN
        if hw_success:
            # If the initiation pattern is seen, the rest of the function should execute
            fsm._do_user_reset(MagicMock(transition=MagicMock()))
            
            # Assert the `else` block's logic was followed
            mock_sleep.assert_called_with(9)
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
            mock_sleep.assert_not_called()
            assert dut_instance.admin_pin == ['1']
            mock_at.on.assert_called_once_with("lock", "unlock", "key2")
            mock_at.off.assert_not_called() # Should not be called if it aborts early

    def test_do_user_reset_failure(self, fsm, mock_at, dut_instance, monkeypatch):
        # This test remains valid for testing a failure in the final confirmation step
        mock_sleep = MagicMock()
        monkeypatch.setattr(time, 'sleep', mock_sleep)
        fsm.state = 'ADMIN_MODE'
        dut_instance.admin_pin = ['1']
        mock_at.confirm_led_solid.return_value = False # Simulate final HW failure
        event = MagicMock(transition=MagicMock())
        ExpectedException = get_reloaded_exception()
        with pytest.raises(ExpectedException, match="Failed to observe user reset confirmation pattern"):
            fsm._do_user_reset(event)
        
        mock_sleep.assert_called_with(9)
        assert dut_instance.admin_pin == ['1']
        
    @pytest.mark.parametrize("is_secure_key", [True, False])
    @pytest.mark.parametrize("from_factory_mode", [True, False]) # Test both branches
    def test_do_manufacturer_reset(self, fsm, mock_at, dut_instance, is_secure_key, from_factory_mode):
        """
        Tests the full, successful manufacturer reset process for both
        standard and 'secure_key' devices, and from both FACTORY_MODE and other states.
        """
        # GIVEN: The FSM is in the correct starting state and the DUT is configured.
        fsm.state = 'FACTORY_MODE' if from_factory_mode else 'STANDBY_MODE'
        dut_instance.secure_key = is_secure_key
        # Provide mock hardware IDs for the FACTORY_MODE path
        dut_instance.hardware_id_1 = 1
        dut_instance.hardware_id_2 = 2
        dut_instance.model_id_1 = 3
        dut_instance.model_id_2 = 4

        # WHEN
        with patch('time.sleep'): # Avoid long sleeps
            fsm._do_manufacturer_reset(MagicMock(transition=MagicMock()))

        # THEN
        # 1. Assert the correct initial sequence was called.
        assert mock_at.sequence.call_count == 1
        
        # 2. Assert the correct long press was used.
        if from_factory_mode:
            mock_at.press.assert_any_call("lock", duration_ms=6000)
        else:
            mock_at.press.assert_any_call("unlock", duration_ms=6000)

        # The final key press is always the last key in the list.
        final_key = "unlock"
        mock_at.press.assert_any_call(final_key)
        assert mock_at.press.call_count == 2
        
        # 3. Assert the keypad test loop calls 'on' and 'off' the correct number of times.
        # on() is called for the first key and all 10 'other' keys.
        # off() is now also called for the first key and all 10 'other' keys.
        # <<< FIX: Correct the call count assertions >>>
        assert mock_at.on.call_count == 11 
        assert mock_at.off.call_count == 11
        
        # 4. Assert the LED checks happen as expected.
        assert mock_at.await_and_confirm_led_pattern.call_count == 1
        assert mock_at.confirm_led_pattern.call_count == 1
        # confirm_led_solid is called for the first key and all 10 'other' keys, plus the final key gen
        assert mock_at.confirm_led_solid.call_count == 12
        assert mock_at.await_led_state.call_count == 10

    @pytest.mark.parametrize("from_factory_mode", [True, False]) # <<< NEW
    @pytest.mark.parametrize("step_to_fail, error_msg", [
        (1, "Failed Reset Ready LED confirmation"),
        # The second failure case is no longer valid because the final LED check
        # was removed in your new code. I'll remove it from the test.
        # (2, "Failed Manufacturer Reset unlock LED pattern"),
    ])
    def test_do_manufacturer_reset_led_failures(self, fsm, mock_at, dut_instance, from_factory_mode, step_to_fail, error_msg):
        """
        Tests specific LED failure paths in _do_manufacturer_reset.
        """
        # GIVEN: The FSM is in the correct starting state
        fsm.state = 'FACTORY_MODE' if from_factory_mode else 'STANDBY_MODE'
        
        # GIVEN: The mock is configured to fail the LED check.
        # Since there's only one await_and_confirm_led_pattern call now, no side_effect is needed.
        mock_at.await_and_confirm_led_pattern.return_value = False
        ExpectedException = get_reloaded_exception()

        # WHEN the function is called
        # THEN: It should raise the specific TransitionCallbackError for that step
        with pytest.raises(ExpectedException, match=error_msg):
            with patch('time.sleep'): # Avoid long sleeps
                fsm._do_manufacturer_reset(MagicMock(transition=MagicMock()))

        # FINALLY: Verify what happened before the failure.
        
        # 1. Assert that the correct initial sequence was always called.
        mock_at.sequence.assert_called_once()
        
        # 2. Assert that the correct long press was initiated.
        if from_factory_mode:
            mock_at.press.assert_called_once_with("lock", duration_ms=6000)
        else:
            mock_at.press.assert_called_once_with("unlock", duration_ms=6000)

        # 3. Assert that if the first LED check fails, the keypad test loop never starts.
        mock_at.on.assert_not_called()

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
    
    @pytest.mark.parametrize("trigger_name, counter_value, expected_pattern_key, hw_success", [
        # --- Unattended Auto-Lock ---
        ('enroll_unattended_auto_lock_counter', 1, 'ACCEPT_PATTERN', True),
        ('enroll_unattended_auto_lock_counter', 1, 'ACCEPT_PATTERN', False), # Failure case
        # --- Brute Force ---
        ('enroll_brute_force_counter', '08', 'BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACK', True),
        ('enroll_brute_force_counter', '08', 'BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACK', False), # Failure case
        # --- Min PIN Length ---
        ('enroll_min_pin_counter', '12', 'ACCEPT_PATTERN', True),
        ('enroll_min_pin_counter', '12', 'ACCEPT_PATTERN', False), # Failure case
    ])
    def test_counter_enrollment_success_paths(self, fsm, mock_at, dut_instance, trigger_name, counter_value, expected_pattern_key, hw_success):
        """
        Tests the success paths for all counter enrollments, and also the case
        where the hardware fails to show the correct success/feedback pattern.
        """
        # GIVEN
        dut_instance.unattended_auto_lock_counter = 0 # Initial state
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        ExpectedException = get_reloaded_exception()
        
        # Set up kwargs for the event
        if trigger_name == 'enroll_unattended_auto_lock_counter':
            kwargs = {'new_counter': counter_value}
        else:
            kwargs = {'new_counter': str(counter_value)}
            
        event = MagicMock(transition=MagicMock(), kwargs=kwargs)
        event.event.name = trigger_name

        # WHEN / THEN
        if not hw_success:
            with pytest.raises(ExpectedException, match="Did not observe"):
                fsm._counter_enrollment(event)
        else:
            fsm._counter_enrollment(event)

        # --- Assertions ---
        
        # Construct the expected pattern dynamically for the brute-force case
        if expected_pattern_key == 'BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACK':
            expected_pattern = []
            for _ in range(int(counter_value)):
                expected_pattern.append({'red':0, 'green':0, 'blue':0, 'duration': (0.00,  3.0)})
                expected_pattern.append({'red':0, 'green':1, 'blue':0, 'duration': (0.01,  1.0)})
        else:
            expected_pattern = LEDs[expected_pattern_key]
            
        mock_at.await_and_confirm_led_pattern.assert_called_once_with(
            expected_pattern, 
            timeout=ANY, 
            replay_extra_context=ANY
        )

        # Also check that the DUT state was updated only on the successful auto-lock case
        if trigger_name == 'enroll_unattended_auto_lock_counter' and hw_success:
            assert dut_instance.unattended_auto_lock_counter == counter_value
        else:
            assert dut_instance.unattended_auto_lock_counter == 0 # Should not change

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
    @pytest.mark.parametrize("hw_should_succeed", [True, False]) # NEW PARAMETER
    def test_counter_enrollment_invalid_value_rejection(self, fsm, mock_at, dut_instance, trigger_name, counter_value, dut_min_pin, dut_max_pin, hw_should_succeed):
        """
        Tests the logic for when the device itself should reject an out-of-range value,
        and also tests the case where the hardware fails to show that rejection.
        """
        # GIVEN
        dut_instance.default_minimum_pin_counter = dut_min_pin
        dut_instance.maximum_pin_counter = dut_max_pin
        mock_at.await_and_confirm_led_pattern.return_value = hw_should_succeed
        ExpectedException = get_reloaded_exception()
        
        # The new_counter kwarg must match the type expected by the function
        if trigger_name == 'enroll_unattended_auto_lock_counter':
            kwargs = {'new_counter': counter_value}
        else:
            kwargs = {'new_counter': str(counter_value)}

        event = MagicMock(transition=MagicMock(), kwargs=kwargs)
        event.event.name = trigger_name
        
        # WHEN / THEN
        if not hw_should_succeed:
            # If the hardware fails to show the REJECT pattern, we expect an exception
            with pytest.raises(ExpectedException, match="Did not observe REJECT"):
                fsm._counter_enrollment(event)
        else:
            # If the hardware correctly shows REJECT, the function should complete without error
            fsm._counter_enrollment(event)

        # FINALLY: Assert that the function always checked for the REJECT pattern
        mock_at.await_and_confirm_led_pattern.assert_called_with(
            LEDs['REJECT'], timeout=ANY, replay_extra_context=ANY
        )
        
    @pytest.mark.parametrize("pin_entered", [True, False])
    @pytest.mark.parametrize("hw_success", [True, False])
    def test_timeout_counter_enrollment(self, monkeypatch, fsm, mock_at, pin_entered, hw_success):
        """
        Tests all paths of the _timeout_counter_enrollment method, including:
        - Partial PIN entry vs. no entry.
        - Hardware success vs. failure on showing the REJECT pattern.
        """
        # GIVEN: The hardware check's outcome is controlled by hw_success
        mock_sleep = MagicMock()
        monkeypatch.setattr(time, 'sleep', mock_sleep)
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        event = MagicMock(transition=MagicMock(), kwargs={'pin_entered': pin_entered})
        ExpectedException = get_reloaded_exception()
        
        # WHEN / THEN
        if pin_entered and not hw_success:
            # This is the specific path to test the lines you highlighted.
            # A PIN was entered, but the hardware failed to show REJECT.
            with pytest.raises(ExpectedException, match="Did not observe REJECT for counter enrollment timeout"):
                fsm._timeout_counter_enrollment(event)
        else:
            # For all other cases (no PIN entered, or successful HW check), no exception is raised.
            fsm._timeout_counter_enrollment(event)
        
        # Assertions
        mock_sleep.assert_called_with(30)
        
        if pin_entered:
            # The hardware check should always be attempted if a PIN was entered.
            mock_at.await_and_confirm_led_pattern.assert_called_with(
                LEDs['REJECT'], 
                timeout=ANY, 
                replay_extra_context=ANY
            )
        else:
            # If no PIN was entered, the hardware check should never be attempted.
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
        
    @pytest.mark.parametrize("hw_success", [True, False])
    def test_user_enrollment(self, fsm, mock_at, dut_instance, hw_success):
        """
        Tests both the success and failure paths for initiating a User PIN enrollment.
        This specifically covers the initial GREEN_BLUE LED confirmation.
        """
        # GIVEN: The hardware check will either succeed or fail.
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        ExpectedException = get_reloaded_exception()
        
        # WHEN the function is called
        if not hw_success:
            # THEN: If the hardware check fails, an exception should be raised.
            with pytest.raises(ExpectedException, match="Did not observe GREEN_BLUE pattern for user enrollment"):
                fsm._user_enrollment(MagicMock(transition=MagicMock()))
            
            # AND: The pending enrollment type should not have been set.
            assert dut_instance.pending_enrollment_type is None
        else:
            # THEN: If the hardware check succeeds, the function completes normally.
            fsm._user_enrollment(MagicMock(transition=MagicMock()))
            
            # AND: The pending enrollment type should be set correctly.
            assert dut_instance.pending_enrollment_type == 'user'

        # FINALLY: Verify that the key press and the LED check were always attempted.
        mock_at.press.assert_called_once_with(['unlock', 'key1'])
        mock_at.await_and_confirm_led_pattern.assert_called_once_with(
            LEDs['GREEN_BLUE'], 
            timeout=ANY, 
            replay_extra_context=ANY
        )
        
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

    @pytest.mark.parametrize("enrollment_type, pin_attr, expected_error_msg", [
        ("user", "user_pin", "Enrollment failed as expected: All 1 user slots are full"),
        ("recovery", "recovery_pin", "Enrollment failed as expected: All 4 recovery slots are full"),
    ])
    @pytest.mark.parametrize("hw_observes_reject", [True, False])
    def test_pin_enrollment_fails_when_slots_full(self, fsm, mock_at, dut_instance, enrollment_type, pin_attr, expected_error_msg, hw_observes_reject):
        """
        Tests PIN enrollment failure when all slots are full for both User and Recovery PINs.
        Also tests the case where the hardware fails to show the expected REJECT pattern.
        """
        # GIVEN: All slots for the given PIN type are filled.
        dut_instance.pending_enrollment_type = enrollment_type
        pin_dictionary = getattr(dut_instance, pin_attr)
        for i in pin_dictionary.keys():
            pin_dictionary[i] = [str(i)] # Fill all slots

        # GIVEN: The hardware will either observe the REJECT pattern or not.
        mock_at.await_and_confirm_led_pattern.return_value = hw_observes_reject
        event = MagicMock(transition=MagicMock(), kwargs={'new_pin': ['9']}, event=MagicMock())
        ExpectedException = get_reloaded_exception()

        # WHEN / THEN
        if hw_observes_reject:
            # If the hardware correctly shows REJECT, the function should raise the "slots are full" error.
            with pytest.raises(ExpectedException, match=expected_error_msg):
                fsm._pin_enrollment(event)
        else:
            # If the hardware FAILS to show REJECT, we expect the "Did not observe REJECT" error.
            # THIS IS THE CORRECTED LINE:
            with pytest.raises(ExpectedException, match="Did not observe REJECT on .*"):
                fsm._pin_enrollment(event)

        # FINALLY: Verify that the sequence entry was never attempted, and the REJECT check was.
        mock_at.sequence.assert_not_called()
        mock_at.await_and_confirm_led_pattern.assert_called_once_with(
            LEDs['REJECT'],
            timeout=ANY,
            replay_extra_context=ANY
        )

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

    @pytest.mark.parametrize("start_state", ["OOB_MODE", "ADMIN_MODE"])
    def test_enroll_admin_pin_happy_path(self, fsm, start_state):
        """
        Tests that enroll_admin_pin correctly calls the underlying triggers
        from valid start states.
        """
        # GIVEN: The FSM is in a valid starting state
        fsm.state = start_state
        # AND: The FSM triggers are mocked to prevent further execution
        fsm.enroll_admin = MagicMock()
        fsm.enroll_pin = MagicMock()
        
        # WHEN: The convenience method is called
        pin_seq = ['1', '2', '3', '4', '5', '6', '7']
        fsm.enroll_admin_pin(new_pin_sequence=pin_seq)
        
        # THEN: The correct sequence of FSM triggers should have been called
        fsm.enroll_admin.assert_called_once()
        fsm.enroll_pin.assert_called_once_with(new_pin=pin_seq)

    def test_enroll_admin_pin_invalid_state(self, fsm):
        """
        Tests that enroll_admin_pin raises a RuntimeError if called from an
        invalid state.
        """
        # GIVEN: The FSM is in an invalid state like STANDBY_MODE
        fsm.state = 'STANDBY_MODE'
        
        # WHEN/THEN: The method should raise a RuntimeError
        with pytest.raises(RuntimeError, match="Cannot enroll admin PIN from state 'STANDBY_MODE'"):
            fsm.enroll_admin_pin(new_pin_sequence=[])

    @pytest.mark.parametrize("pin_type", ["user", "recovery", "self_destruct"])
    def test_enroll_other_pins_happy_path(self, fsm, pin_type):
        """
        Tests the happy path for user, recovery, and self-destruct PIN enrollment.
        """
        # GIVEN: The FSM is in ADMIN_MODE
        fsm.state = 'ADMIN_MODE'
        # AND: The underlying FSM triggers are mocked
        fsm.enroll_user = MagicMock()
        fsm.enroll_recovery = MagicMock()
        fsm.enroll_self_destruct = MagicMock()
        fsm.enroll_pin = MagicMock()
        
        # WHEN: The corresponding convenience method is called
        pin_seq = ['1', '2', '3', '4', '5', '6', '7', '8']
        method_to_call = getattr(fsm, f"enroll_{pin_type}_pin")
        method_to_call(new_pin_sequence=pin_seq)
        
        # THEN: The correct trigger should have been called, followed by enroll_pin
        expected_trigger_mock = getattr(fsm, f"enroll_{pin_type}")
        expected_trigger_mock.assert_called_once()
        fsm.enroll_pin.assert_called_once_with(new_pin=pin_seq)

    @pytest.mark.parametrize("pin_type", ["user", "recovery", "self_destruct"])
    def test_enroll_other_pins_invalid_state(self, fsm, pin_type):
        """
        Tests that user, recovery, and self-destruct enrollments fail if not
        in ADMIN_MODE.
        """
        # GIVEN: The FSM is in an invalid state
        fsm.state = 'OOB_MODE'
        
        # WHEN/THEN: The method should raise a RuntimeError
        method_to_call = getattr(fsm, f"enroll_{pin_type}_pin")
        with pytest.raises(RuntimeError, match=f"Cannot enroll .* from state 'OOB_MODE'"):
            method_to_call(new_pin_sequence=[])

    @pytest.mark.parametrize("pin_type, dut_attr", [
        ("user", "user_pin"),
        ("recovery", "recovery_pin"),
    ])
    def test_enroll_pin_fails_if_slots_full(self, fsm, dut_instance, pin_type, dut_attr):
        """
        Tests that user and recovery PIN enrollments fail if all slots are full.
        """
        # GIVEN: The FSM is in ADMIN_MODE
        fsm.state = 'ADMIN_MODE'
        # AND: All slots for the given PIN type are full
        pin_dict = getattr(dut_instance, dut_attr)
        for i in pin_dict:
            pin_dict[i] = ["filled"]
        
        # WHEN/THEN: The convenience method should raise a RuntimeError
        method_to_call = getattr(fsm, f"enroll_{pin_type}_pin")
        with pytest.raises(RuntimeError, match="No available .* slots"):
            method_to_call(new_pin_sequence=[])

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

    @pytest.mark.parametrize("sd_enabled, initial_pl_state", [
        (False, False), # Path to enable provision lock
        (True, False),  # Path where provision lock is blocked by self-destruct
    ])
    @pytest.mark.parametrize("hw_success", [True, False])
    def test_provision_lock_toggle(self, fsm, mock_at, dut_instance, sd_enabled, initial_pl_state, hw_success):
        """
        Tests all logic and hardware failure paths for _provision_lock_toggle.
        - GIVEN self-destruct is enabled or disabled.
        - GIVEN the hardware confirmation succeeds or fails.
        - THEN the correct behavior or exception occurs.
        """
        # GIVEN: The DUT is configured for the specific test case.
        dut_instance.self_destruct_enabled = sd_enabled
        dut_instance.provision_lock = initial_pl_state
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        ExpectedException = get_reloaded_exception()
        
        # Determine the expected pattern and final DUT state
        if sd_enabled:
            expected_pattern_key = 'REJECT'
            expected_pl_state = False
            error_msg = "Did not observe REJECT for Provision Lock toggle with Self-Destruct enabled"
        else:
            expected_pattern_key = 'ACCEPT_PATTERN'
            expected_pl_state = True # It will toggle to True
            error_msg = "Did not observe ACCEPT_PATTERN for Provision Lock toggle"

        # WHEN / THEN
        if not hw_success:
            # If the hardware confirmation fails, we expect a specific exception
            with pytest.raises(ExpectedException, match=error_msg):
                fsm._provision_lock_toggle(MagicMock(transition=MagicMock()))
        else:
            # If the hardware confirmation succeeds, no exception should be raised
            fsm._provision_lock_toggle(MagicMock(transition=MagicMock()))

        # --- FINAL ASSERTIONS ---

        # Assert that the correct key combination was always pressed.
        mock_at.press.assert_called_once_with(['key2', 'key5'])

        # Assert that the correct LED pattern was always checked.
        expected_pattern = LEDs[expected_pattern_key]
        mock_at.await_and_confirm_led_pattern.assert_called_once_with(
            expected_pattern, 
            timeout=ANY, 
            replay_extra_context=ANY
        )

        # Assert that the provision_lock state is correct after the operation.
        # It should only change if SD was off AND the hardware succeeded.
        if not sd_enabled and hw_success:
            assert dut_instance.provision_lock == expected_pl_state
        else:
            assert dut_instance.provision_lock == initial_pl_state # Should be unchanged

    @pytest.mark.parametrize("pl_enabled", [True, False])
    @pytest.mark.parametrize("hw_success", [True, False])
    def test_self_destruct_toggle(self, fsm, mock_at, dut_instance, pl_enabled, hw_success):
        """
        Tests all logic and hardware failure paths for _self_destruct_toggle.
        - GIVEN provision_lock is enabled or disabled.
        - GIVEN the hardware confirmation succeeds or fails.
        - THEN the correct behavior or exception occurs.
        """
        # GIVEN: The DUT and mock are configured for the specific test case.
        dut_instance.provision_lock = pl_enabled
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        ExpectedException = get_reloaded_exception()
        
        # Determine the expected pattern and final DUT state
        if pl_enabled:
            expected_pattern_key = 'REJECT'
            expected_sd_state = False # Should not change
            error_msg = "Did not observe REJECT for Self-Destruct toggle with Provision Lock enabled"
        else:
            expected_pattern_key = 'ACCEPT_PATTERN'
            expected_sd_state = True # It will toggle to True
            error_msg = "Did not observe ACCEPT_PATTERN for Self-Destruct toggle"

        # WHEN / THEN
        if not hw_success:
            # If the hardware confirmation fails, we expect a specific exception
            with pytest.raises(ExpectedException, match=error_msg):
                fsm._self_destruct_toggle(MagicMock(transition=MagicMock()))
        else:
            # If the hardware confirmation succeeds, no exception should be raised
            fsm._self_destruct_toggle(MagicMock(transition=MagicMock()))

        # --- FINAL ASSERTIONS ---

        # Assert that the correct key combination was always pressed.
        mock_at.press.assert_called_once_with(['key4', 'key7'])

        # Assert that the correct LED pattern was always checked.
        expected_pattern = LEDs[expected_pattern_key]
        mock_at.await_and_confirm_led_pattern.assert_called_once_with(
            expected_pattern, 
            timeout=ANY, 
            replay_extra_context=ANY
        )

        # Assert that the self_destruct_enabled state is correct after the operation.
        # It should only change if PL was off AND the hardware succeeded.
        if not pl_enabled and hw_success:
            assert dut_instance.self_destruct_enabled == expected_sd_state
        else:
            assert dut_instance.self_destruct_enabled is False # Should be unchanged

    @pytest.mark.parametrize("initial_ufe_state", [True, False])
    @pytest.mark.parametrize("hw_success", [True, False])
    def test_user_forced_enrollment_toggle(self, fsm, mock_at, dut_instance, initial_ufe_state, hw_success):
        """
        Tests all logic and hardware failure paths for _user_forced_enrollment_toggle.
        - GIVEN UFE is initially enabled or disabled.
        - GIVEN the hardware confirmation succeeds or fails.
        - THEN the correct behavior or exception occurs.
        """
        # GIVEN: The DUT and mock are configured for the specific test case.
        dut_instance.user_forced_enrollment = initial_ufe_state
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        ExpectedException = get_reloaded_exception()

        # Determine the expected pattern and final DUT state
        if initial_ufe_state:
            expected_pattern_key = 'REJECT'
            error_msg = "Did not observe REJECT for User-Forced Enrollment toggle"
        else:
            expected_pattern_key = 'ACCEPT_PATTERN'
            error_msg = "Did not observe ACCEPT_PATTERN for User-Forced Enrollment toggle"
        
        # WHEN / THEN
        if not hw_success:
            # If the hardware confirmation fails, we expect a specific exception
            with pytest.raises(ExpectedException, match=error_msg):
                fsm._user_forced_enrollment_toggle(MagicMock(transition=MagicMock()))
        else:
            # If the hardware confirmation succeeds, no exception should be raised
            fsm._user_forced_enrollment_toggle(MagicMock(transition=MagicMock()))

        # --- FINAL ASSERTIONS ---

        # Assert that the correct key combination was always pressed.
        mock_at.press.assert_called_once_with(['key0', 'key1'])

        # Assert that the correct LED pattern was always checked.
        expected_pattern = LEDs[expected_pattern_key]
        mock_at.await_and_confirm_led_pattern.assert_called_once_with(
            expected_pattern, 
            timeout=ANY, 
            replay_extra_context=ANY
        )

        # Assert that the UFE state is correct after the operation.
        # It should only change if it was initially OFF and the hardware succeeded.
        if not initial_ufe_state and hw_success:
            assert dut_instance.user_forced_enrollment is True
        else:
            # For all other cases, it should remain in its initial state.
            assert dut_instance.user_forced_enrollment == initial_ufe_state
        
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

    @pytest.mark.parametrize("trigger, pattern_key, hw_success, error_msg", [
        # --- Success Paths ---
        ("enroll_self_destruct", "RED_BLUE", True, None),
        ("enroll_user", "GREEN_BLUE", True, None), # Covers any non-SD trigger

        # --- Failure Paths ---
        ("enroll_self_destruct", "RED_BLUE", False, "Did not observe RED_BLUE pattern"),
        ("enroll_user", "GREEN_BLUE", False, "Did not observe GREEN_BLUE pattern for recovery enrollment"),
    ])
    def test_on_enter_PIN_ENROLLMENT_all_paths(self, fsm, mock_at, trigger, pattern_key, hw_success, error_msg):
        """
        Covers all success and failure paths for the on_enter_PIN_ENROLLMENT method,
        based on the trigger name and hardware success.
        """
        # GIVEN: The FSM is set up for a specific trigger and hardware outcome.
        event = MagicMock()
        event.event.name = trigger
        mock_at.await_and_confirm_led_pattern.return_value = hw_success
        ExpectedException = get_reloaded_exception()

        # WHEN the on_enter callback is triggered
        # THEN the behavior matches the expected outcome (success or specific exception).
        if not hw_success:
            with pytest.raises(ExpectedException, match=error_msg):
                fsm.on_enter_PIN_ENROLLMENT(event)
        else:
            # On success, no exception should be raised.
            fsm.on_enter_PIN_ENROLLMENT(event)

        # FINALLY: Verify that the correct hardware check was always attempted.
        mock_at.await_and_confirm_led_pattern.assert_called_with(
            LEDs[pattern_key],
            timeout=ANY,
            replay_extra_context=ANY
        )

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

    @pytest.mark.parametrize("toggle_method_name", [
        "_basic_disk_toggle",
        "_removable_media_toggle",
        "_led_flicker_enable",
        "_led_flicker_disable",  # <<< THIS IS THE ADDED LINE
        "_lock_override_toggle",
        "_read_only_toggle",
        "_read_write_toggle",
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

    def test_speed_test_happy_path(self, fsm, mock_at, dut_instance):
        """
        Tests the successful execution of a speed test.
        GIVEN the DUT has a valid disk path,
        WHEN speed_test is called,
        THEN it should call the controller's test method and return the results.
        """
        # GIVEN: A valid disk path is set on the DUT model
        test_disk_path = "PhysicalDrive1"
        dut_instance.disk_path = test_disk_path

        # AND: The mock controller is set up to return a successful result
        mock_results = {'read': 150.5, 'write': 120.2}
        mock_at.run_fio_tests.return_value = mock_results
        
        # <<< FIX: Mock the logger on the FSM instance itself for this test >>>
        # This prevents any logging calls from interfering.
        fsm.logger = MagicMock()

        # WHEN: The FSM's speed_test method is called
        results = fsm.speed_test()

        # THEN: The controller's method should have been called with the correct path
        mock_at.run_fio_tests.assert_called_once_with(disk_path=test_disk_path)

        # AND: The session's method should have been called with the results
        fsm.session.add_speed_test_result.assert_called_once_with(mock_results)
        
        # AND: The function should return the results from the controller
        assert results == mock_results

    def test_speed_test_unhappy_path_no_disk(self, fsm, mock_at, dut_instance, caplog):
        """
        Tests the failure case where the speed test is called without a disk path.
        GIVEN the DUT's disk path is empty,
        WHEN speed_test is called,
        THEN it should log an error and not call the controller.
        """
        # GIVEN: The disk path on the DUT model is empty
        dut_instance.disk_path = ""
        
        # WHEN: The FSM's speed_test method is called, while capturing logs
        with caplog.at_level(logging.ERROR, logger="DeviceFSM.Simplified"):
            results = fsm.speed_test()

        # THEN: The controller's method should NOT have been called
        mock_at.run_fio_tests.assert_not_called()

        # AND: An error message should have been logged
        assert "Cannot run speed test: DUT disk path is not set" in caplog.text

        # AND: The function should return None
        assert results is None