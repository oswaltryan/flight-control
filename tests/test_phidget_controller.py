# Directory: tests/
# Filename: test_phidget_controller.py

#############################################################
##
## This test file is designed to systematically cover every function
## in controllers/phidget_board.py.
##
## Run this test with the following command:
## pytest tests/test_phidget_controller.py --cov=controllers.phidget_board --cov-report term-missing
##
#############################################################

import itertools
import unittest
import time
from unittest.mock import patch, MagicMock, call, ANY
from typing import cast
# We must import the module we are testing
from controllers.phidget_board import PhidgetController, PhidgetException, ErrorCode
from Phidget22.Devices.DigitalOutput import DigitalOutput


# --- [Mock classes and Test Config remain the same] ---
class MockPhidgetChannel:
    def __init__(self):
        self._attached = False; self._state = False; self._serial_number = -1
        self.setIsRemote = MagicMock()
        self.setDeviceSerialNumber = MagicMock(side_effect=self._set_serial)
        self.getDeviceSerialNumber = MagicMock(side_effect=self._get_serial)
        self.setChannel = MagicMock()
        self.setIsHubPortDevice = MagicMock()
        self.setHubPort = MagicMock()
        self.getIsRemote = MagicMock(return_value=False)
        self.getIsHubPortDevice = MagicMock(return_value=False)
        self.getDeviceName = MagicMock(return_value="Mock Phidget")
        self.getChannel = MagicMock(return_value=0)
        self.getHubPort = MagicMock(return_value=0)
    def _set_serial(self, num): self._serial_number = num
    def _get_serial(self): return self._serial_number
    def openWaitForAttachment(self, timeout): self._attached = True
    def getAttached(self): return self._attached
    def close(self): self._attached = False

class MockDigitalOutput(MockPhidgetChannel):
    def setState(self, state):
        if not self._attached: raise PhidgetException(ErrorCode.EPHIDGET_NOTATTACHED)
        self._state = bool(state)
    def getState(self): return self._state

class MockDigitalInput(MockPhidgetChannel):
    def getState(self):
        if not self._attached: raise PhidgetException(ErrorCode.EPHIDGET_NOTATTACHED)
        return self._state
    def set_mock_state(self, state): self._state = bool(state)

TEST_SCRIPT_MAP_CONFIG = {
    "outputs": { "out1": {"phidget_id": "main", "physical_channel": 0}, "out2": {"phidget_id": "main", "physical_channel": 1}, "out_fail": {"phidget_id": "fail_phidget", "physical_channel": 0}, "out_bad_config": {"physical_channel": 99}, "hub_out": {"phidget_id": "hub_device", "physical_channel": 0}, },
    "inputs": { "in1": {"phidget_id": "main", "physical_channel": 0} }
}
TEST_DEVICE_CONFIGS = { "main": {"serial_number": 12345}, "fail_phidget": {"serial_number": 67890}, "remote_phidget": {"serial_number": 54321, "is_remote": True}, "hub_device": { "serial_number": 99999, "is_hub_port_device": True, "hub_port": 3, "parent_serial_number": 88888 } }

# --- Test Suite ---
@patch('controllers.phidget_board.DigitalInput', new=MockDigitalInput)
@patch('controllers.phidget_board.DigitalOutput', new=MockDigitalOutput)
@patch('controllers.phidget_board.PhidgetException', new=PhidgetException)
@patch('controllers.phidget_board.ErrorCode', new=ErrorCode)
class TestPhidgetController(unittest.TestCase):

    def setUp(self):
        self.mock_logger = MagicMock()

    # --- [Tests from previous steps remain here] ---
    def test_initialization_with_hub_port_device(self):
        with PhidgetController(script_map_config=TEST_SCRIPT_MAP_CONFIG, device_configs=TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger) as controller:
            hub_channel_mock = controller.channels['hub_out']
            hub_channel_mock.setIsHubPortDevice.assert_called_once_with(True)
            hub_channel_mock.setHubPort.assert_called_once_with(3)
            self.mock_logger.debug.assert_any_call("Parent S/N 88888 for hub_device.")

    def test_initialization_with_hub_port_any(self):
        specific_hub_config = {"any_hub_device": {"is_hub_port_device": True}}
        specific_script_map = {"outputs": {"any_hub_out": {"phidget_id": "any_hub_device", "physical_channel": 0}}}
        with PhidgetController(script_map_config=specific_script_map, device_configs=specific_hub_config, logger_instance=self.mock_logger) as controller:
            hub_channel_mock = controller.channels['any_hub_out']
            hub_channel_mock.setHubPort.assert_called_once_with(-1)
            self.mock_logger.debug.assert_any_call("Hub port for any_hub_device is any.")

    def test_initialization_happy_path(self):
        with PhidgetController(script_map_config=TEST_SCRIPT_MAP_CONFIG, device_configs=TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger) as controller:
            self.assertIn('out1', controller.channels)
            self.assertNotIn('out_bad_config', controller.channels)
            self.mock_logger.warning.assert_any_call("Skip 'out_bad_config': missing phidget_id/physical_channel.")

    def test_initialization_phidget_open_failure(self):
        def side_effect_open(instance_self, timeout):
            if instance_self.getDeviceSerialNumber() == 67890: raise PhidgetException(ErrorCode.EPHIDGET_TIMEOUT)
            instance_self._attached = True
        with patch.object(MockDigitalOutput, 'openWaitForAttachment', side_effect=side_effect_open, autospec=True):
            controller = PhidgetController(script_map_config=TEST_SCRIPT_MAP_CONFIG, device_configs=TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger)
            self.assertIsNone(controller.channels['out_fail'])
            self.assertTrue(any("Error opening output 'out_fail'" in str(c) for c in self.mock_logger.error.call_args_list))
            controller.close_all()

    def test_initialization_missing_device_config(self):
        bad_map = {"outputs": {"bad": {"phidget_id": "non_existent", "physical_channel": 0}}}
        controller = PhidgetController(script_map_config=bad_map, device_configs=TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger)
        self.assertIsNone(controller.channels['bad'])
        self.assertTrue(any("Unexpected error opening output 'bad'" in str(c) for c in self.mock_logger.error.call_args_list))
        controller.close_all()

    def test_get_channel_object_unhappy_paths(self):
        with PhidgetController(script_map_config=TEST_SCRIPT_MAP_CONFIG, device_configs=TEST_DEVICE_CONFIGS) as controller:
            with self.assertRaisesRegex(NameError, "Channel 'non_existent' not defined."): controller._get_channel_object('non_existent')
            controller.channels['out_fail'] = None
            with self.assertRaisesRegex(RuntimeError, "Channel 'out_fail' is None \\(failed init\\)."): controller._get_channel_object('out_fail')
            ch = controller.channels['out1']; ch._attached = False 
            with self.assertRaises(PhidgetException): controller._get_channel_object('out1')
            ch._attached = True
            with self.assertRaisesRegex(TypeError, "Channel 'out1' not MockDigitalInput"): controller._get_channel_object('out1', MockDigitalInput)
    
    @patch('time.sleep')
    def test_set_output_on_off_hold(self, mock_sleep):
        with PhidgetController(script_map_config=TEST_SCRIPT_MAP_CONFIG, device_configs=TEST_DEVICE_CONFIGS) as controller:
            out1_ch = controller.channels['out1']
            controller.on('out1'); self.assertTrue(out1_ch.getState())
            controller.off('out1'); self.assertFalse(out1_ch.getState())
            with patch.object(out1_ch, 'setState', wraps=out1_ch.setState) as spy:
                controller.hold('out1', 150)
                spy.assert_has_calls([call(True), call(False)])
                self.assertFalse(out1_ch.getState())
    
    # --- NEW TEST CASE FOR set_output EXCEPTION ---
    def test_set_output_phidget_exception(self):
        """Tests that a PhidgetException during setState is logged and re-raised."""
        with PhidgetController(
            script_map_config=TEST_SCRIPT_MAP_CONFIG,
            device_configs=TEST_DEVICE_CONFIGS,
            logger_instance=self.mock_logger
        ) as controller:
            out1_ch = controller.channels['out1']
            
            # Create a mock PhidgetException
            test_exception = PhidgetException(ErrorCode.EPHIDGET_UNEXPECTED)
            test_exception.description = "A controllers error occurred"

            # Patch the setState method on the specific mock instance to raise the exception
            with patch.object(out1_ch, 'setState', side_effect=test_exception):
                
                # Verify the exception is raised from set_output
                with self.assertRaises(PhidgetException) as cm:
                    controller.set_output('out1', True)
                
                # Check that the raised exception is the one we created
                self.assertIs(cm.exception, test_exception)

            # Verify the error was logged with the correct message
            self.mock_logger.error.assert_called_once_with(
                f"Error setting output 'out1': {test_exception.description}",
                exc_info=False
            )

    @patch('time.sleep')
    def test_hold_off_raises_exception(self, mock_sleep):
        """Covers the error path when 'off' fails during hold()."""
        with PhidgetController(script_map_config=TEST_SCRIPT_MAP_CONFIG, device_configs=TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger) as controller:
            # Patch `off` to raise an exception
            with patch.object(controller, 'off', side_effect=Exception("fail")):
                # The 'on' state will still be triggered successfully
                controller.hold('out1', 100)

                self.mock_logger.error.assert_any_call(
                    "Error turning off 'out1' during hold: fail",
                    exc_info=True
                )

    @patch('time.sleep')
    def test_pulse_simultaneous_off_raises_exception(self, mock_sleep):
        """Covers error handling in _pulse_simultaneous when off() fails."""
        with PhidgetController(script_map_config=TEST_SCRIPT_MAP_CONFIG, device_configs=TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger) as controller:
            with patch.object(controller, 'on') as mock_on, \
                patch.object(controller, 'off', side_effect=[None, Exception("simul_off_fail")]):

                controller.press(["out1", "out2"], duration_ms=100)

                mock_on.assert_has_calls([call('out1'), call('out2')])
                self.mock_logger.error.assert_any_call(
                    "Error turning off 'out2' during simultaneous pulse: simul_off_fail",
                    exc_info=True
                )

    def test_sequence_invalid_pins_type(self):
        with PhidgetController(TEST_SCRIPT_MAP_CONFIG, TEST_DEVICE_CONFIGS) as controller:
            with self.assertRaisesRegex(ValueError, "Pins argument must be a list"):
                controller.sequence(cast(list, "not-a-list"), press_ms=100, pause_ms=50)

    def test_sequence_invalid_press_ms(self):
        with PhidgetController(TEST_SCRIPT_MAP_CONFIG, TEST_DEVICE_CONFIGS) as controller:
            with self.assertRaisesRegex(ValueError, "press_ms must be a non-negative number"):
                controller.sequence(['out1'], press_ms=-1, pause_ms=50)

    def test_sequence_invalid_pause_ms(self):
        with PhidgetController(TEST_SCRIPT_MAP_CONFIG, TEST_DEVICE_CONFIGS) as controller:
            with self.assertRaisesRegex(ValueError, "pause_ms must be a non-negative number"):
                controller.sequence(['out1'], press_ms=100, pause_ms=-5)

    def test_sequence_invalid_item_type(self):
        with PhidgetController(TEST_SCRIPT_MAP_CONFIG, TEST_DEVICE_CONFIGS) as controller:
            with self.assertRaisesRegex(TypeError, "Sequence item must be a string or a list of strings"):
                controller.sequence(['out1', 123], press_ms=100, pause_ms=50)

    @patch('time.sleep', return_value=None)
    @patch('time.time', side_effect=[
        100.0, 100.01, 100.02, 100.03, 100.04, 100.05, 100.06, 100.07, 100.08, 100.09
    ])
    def test_wait_for_input_detached_and_phidget_exception(self, mock_time, mock_sleep):
        with PhidgetController(TEST_SCRIPT_MAP_CONFIG, TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger) as controller:
            in1 = controller.channels['in1']
            in1._attached = True
            in1.getDeviceSerialNumber = MagicMock(return_value=99999)

            # Force getState to raise EPHIDGET_NOTATTACHED repeatedly
            with patch.object(in1, 'getState', side_effect=PhidgetException(ErrorCode.EPHIDGET_NOTATTACHED)):
                result = controller.wait_for_input('in1', True, 0.05)

            self.assertFalse(result)
            self.mock_logger.warning.assert_any_call(
                "Input 'in1' detached. Retrying. (S/N 99999)"
            )

    @patch('time.sleep', return_value=None)
    @patch('time.time', side_effect=[100.0 + i * 0.01 for i in range(20)])  # gives 20 time values
    def test_wait_for_input_unexpected_phidget_exception(self, mock_time, mock_sleep):
        with PhidgetController(TEST_SCRIPT_MAP_CONFIG, TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger) as controller:
            in1 = controller.channels['in1']
            in1._attached = True
            in1.getDeviceSerialNumber = MagicMock(return_value=12345)

            err = PhidgetException(ErrorCode.EPHIDGET_UNKNOWNVAL)
            err.description = "Something weird"

            with patch.object(in1, 'getState', side_effect=err):
                result = controller.wait_for_input('in1', True, 0.05)

            self.assertFalse(result)
            self.mock_logger.error.assert_any_call(
                "PhidgetExc waiting for 'in1': Something weird",
                exc_info=False
            )

    @patch('time.sleep', return_value=None)
    @patch('time.time', side_effect=[100.0 + i * 0.01 for i in range(20)])  # plenty of ticks
    def test_wait_for_input_detached_sets_last_state(self, mock_time, mock_sleep):
        with PhidgetController(
            script_map_config=TEST_SCRIPT_MAP_CONFIG,
            device_configs=TEST_DEVICE_CONFIGS,
            logger_instance=self.mock_logger
        ) as controller:
            in1 = controller.channels['in1']
            in1._attached = True
    
            # Always return False so the wait condition is never met
            in1.getState = MagicMock(return_value=False)
            # Simulate that the device is detached at the moment the final state is checked
            in1.getAttached = MagicMock(return_value=False)
    
            result = controller.wait_for_input('in1', True, timeout_s=0.1)
            self.assertFalse(result)
    
            # FIX: Assert against the correct log level (warning) and the exact message format.
            self.mock_logger.warning.assert_any_call(
                "Timeout waiting for 'in1' to be HIGH. Last state: NOT ATTACHED."
            )

    def test_close_all_logs_error_on_phidget_exception(self):
        mock_ch = MagicMock(spec=DigitalOutput)
        mock_ch.getAttached.return_value = True
        mock_ch.getState.return_value = True

        # Cause .close() to raise PhidgetException with description
        exc = PhidgetException(ErrorCode.EPHIDGET_TIMEOUT)
        exc.description = "Timeout error"
        mock_ch.close.side_effect = exc

        key = ("devkey", "DigitalOutput", 0)
        with PhidgetController(TEST_SCRIPT_MAP_CONFIG, TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger) as controller:
            controller._opened_physical_channels[key] = mock_ch
            controller.channels["out1"] = mock_ch  # Needed to resolve `Scripts:` mapping

            controller.close_all()

            self.mock_logger.error.assert_any_call(
                "Error closing DevKey 'devkey', Type 'DigitalOutput', PhysCh 0 (Scripts: ['out1']): Timeout error",
                exc_info=False
            )

    def test_wait_for_input_channel_lookup_failure(self):
        with PhidgetController(TEST_SCRIPT_MAP_CONFIG, TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger) as controller:
            controller.channels['in1'] = None  # simulate init failure
            with self.assertRaises(RuntimeError):
                controller.wait_for_input('in1', True, 0.1)

            self.mock_logger.error.assert_any_call(
                "Cannot wait for 'in1': Channel 'in1' is None (failed init).",
                exc_info=True
            )

    @patch('time.sleep')
    def test_press_and_pulse_simultaneous(self, mock_sleep):
        with PhidgetController(script_map_config=TEST_SCRIPT_MAP_CONFIG, device_configs=TEST_DEVICE_CONFIGS) as controller:
            with patch.object(controller, 'hold') as mock_hold, patch.object(controller, '_pulse_simultaneous') as mock_pulse:
                controller.press("out1", 50)
                mock_hold.assert_called_once_with("out1", duration_ms=50)

                controller.press(["out1", "out2"], 300)
                mock_pulse.assert_called_once_with(["out1", "out2"], duration_ms=300)

            # Use cast to avoid type checker error
            bad_input = cast(str, 123)
            with self.assertRaisesRegex(TypeError, "must be a string or a list"):
                controller.press(bad_input)
    
    @patch('time.sleep')
    def test_sequence(self, mock_sleep):
        with PhidgetController(script_map_config=TEST_SCRIPT_MAP_CONFIG, device_configs=TEST_DEVICE_CONFIGS) as controller:
            controller.sequence(['out1', ['out1', 'out2']], 50, 20)
            mock_sleep.assert_has_calls([call(0.05), call(0.02), call(0.05)])

    def test_read_input(self):
        with PhidgetController(script_map_config=TEST_SCRIPT_MAP_CONFIG, device_configs=TEST_DEVICE_CONFIGS) as controller:
            in1_ch = controller.channels['in1']
            in1_ch.set_mock_state(False); self.assertFalse(controller.read_input('in1'))
            in1_ch.set_mock_state(True); self.assertTrue(controller.read_input('in1'))
            with patch.object(in1_ch, 'getState', side_effect=PhidgetException(ErrorCode.EPHIDGET_UNKNOWNVAL)):
                with self.assertRaises(PhidgetException): controller.read_input('in1')

    @patch('time.sleep', return_value=None)
    @patch('time.time')
    def test_wait_for_input(self, mock_time, mock_sleep):
        # Configure mock_time to provide a continuous sequence of time values.
        # This prevents StopIteration errors as logging calls time.time() internally
        # and the polling loop in wait_for_input also calls it.
        mock_time.side_effect = itertools.count(start=100.0, step=0.01)

        # Scenario 1: Input never reaches expected state, times out
        with PhidgetController(TEST_SCRIPT_MAP_CONFIG, TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger) as controller:
            in1_ch = controller.channels['in1']
            in1_ch.set_mock_state(False) # Input state always remains False

            # Reset logger calls for this specific assertion to avoid interference from __init__ logs
            self.mock_logger.reset_mock() 

            # Use a shorter timeout and poll interval for faster testing
            result = controller.wait_for_input('in1', True, timeout_s=0.1, poll_s=0.01) 
            self.assertFalse(result)
            self.mock_logger.warning.assert_called_with(
                "Timeout waiting for 'in1' to be HIGH. Last state: LOW."
            )

        # Scenario 2: Input reaches expected state
        # Reset mock_time for the new scenario to ensure a fresh sequence
        mock_time.side_effect = itertools.count(start=200.0, step=0.01)
        
        with PhidgetController(TEST_SCRIPT_MAP_CONFIG, TEST_DEVICE_CONFIGS, logger_instance=self.mock_logger) as controller:
            in1_ch = controller.channels['in1']
            # Configure getState to return False twice, then True to simulate the change
            with patch.object(in1_ch, 'getState', side_effect=[False, False, True]):
                # Reset logger calls for this specific assertion
                self.mock_logger.reset_mock() 
                result = controller.wait_for_input('in1', True, timeout_s=0.1, poll_s=0.01)
                self.assertTrue(result)
                self.mock_logger.info.assert_called_with("Input 'in1' reached state HIGH.")
            
    def test_close_all_and_context_manager(self):
        controller = PhidgetController(TEST_SCRIPT_MAP_CONFIG, TEST_DEVICE_CONFIGS)
        out1_ch = controller.channels['out1']
        with patch.object(out1_ch, 'close') as spy_close:
            controller.on('out1'); controller.close_all()
            self.assertFalse(out1_ch.getState())
            spy_close.assert_called_once()
            self.assertEqual(len(controller.channels), 0)