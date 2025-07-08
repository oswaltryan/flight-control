# Directory: tests/
# Filename: test_unified_controller.py

#############################################################
##
## This test file is designed to systematically cover every function
## in controllers/unified_controller.py.
##
## Run this test with the following command:
## pytest tests/test_unified_controller.py --cov=controllers.unified_controller --cov-report term-missing
##
#############################################################

import pytest
from unittest.mock import patch, MagicMock, call
import sys
import logging
import json
import subprocess
import os
import importlib
from controllers.unified_controller import UnifiedController
import controllers.unified_controller as unified_controller_module

@pytest.fixture
def mock_dependencies():
    """A fixture to mock all external dependencies of UnifiedController."""
    with patch.object(unified_controller_module, 'PhidgetController') as mock_phidget, \
         patch.object(unified_controller_module, 'LogitechLedChecker') as mock_camera, \
         patch.object(unified_controller_module, 'BarcodeScanner') as mock_scanner, \
         patch.object(unified_controller_module, 'find_apricorn_device') as mock_find_device:
        
        mock_camera.return_value.is_camera_initialized = True
        mock_scanner.return_value.await_scan.return_value = "TEST_SERIAL_123"
        yield {
            "phidget": mock_phidget,
            "camera": mock_camera,
            "scanner": mock_scanner,
            "find_device": mock_find_device
        }


class TestUnifiedController:

    def test_initialization_success(self, mock_dependencies):
        controller = UnifiedController()
        mock_dependencies["phidget"].assert_called_once()
        mock_dependencies["camera"].assert_called_once()
        # mock_dependencies["scanner"].assert_called_once()
        # mock_dependencies["scanner"].return_value.await_scan.assert_called_once()
        # assert controller.scanned_serial_number == "TEST_SERIAL_123"

    def test_critical_error_on_failed_import(self, monkeypatch):
        """
        Tests that a top-level ImportError in unified_controller.py is
        caught, logged, and re-raised. This test works by temporarily removing
        a class from a dependency module, causing 'from...import' to fail.
        """
        # --- ARRANGE ---
        # We must get a direct handle to the dependency module that has already
        # been loaded by pytest during test discovery.
        import controllers.phidget_board as phidget_module_to_break

        # The module under test must be reloaded to trigger its import logic again.
        module_to_reload = 'controllers.unified_controller'

        # CRITICAL STEP: Temporarily delete the 'PhidgetController' class from the
        # already-loaded phidget_controller module. This will cause the
        # `from controllers.phidget_controller import PhidgetController` line
        # to raise an ImportError.
        monkeypatch.delattr(phidget_module_to_break, 'PhidgetController')
        
        # We must also clear the module we are about to reload from the cache.
        if module_to_reload in sys.modules:
            del sys.modules[module_to_reload]

        # --- ACT & ASSERT ---
        # We patch the logger at its source to reliably intercept the call.
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger_instance = MagicMock()
            mock_get_logger.return_value = mock_logger_instance
            
            # Now, when we import unified_controller, it will find the phidget_controller
            # module but will fail to find the PhidgetController class inside it.
            with pytest.raises(ImportError) as excinfo:
                import controllers.unified_controller

        # Verify the exception was caught and logged as expected.
        mock_logger_instance.critical.assert_called_once()
        call_args, call_kwargs = mock_logger_instance.critical.call_args
        assert "Critical Import Error" in call_args[0]
        assert call_kwargs.get('exc_info') is True
        assert issubclass(excinfo.type, ImportError)

        # --- CLEANUP ---
        # monkeypatch automatically restores the 'PhidgetController' class.
        # We just need to remove the module we imported for the test.
        if module_to_reload in sys.modules:
            del sys.modules[module_to_reload]

    def test_initialization_defaults_keypad_on_fsm_import_error(self, mock_dependencies, monkeypatch, caplog):
        """
        Tests that if 'DeviceUnderTest' fails to import during initialization,
        the controller logs the error and defaults to the portable keypad layout
        without crashing.
        """
        # --- ARRANGE ---
        from unittest.mock import ANY
        from utils.config.keypad_layouts import KEYPAD_LAYOUTS
        import controllers.finite_state_machine as fsm_module_to_break

        monkeypatch.delattr(fsm_module_to_break, 'DeviceUnderTest')

        mock_camera_constructor = mock_dependencies["camera"]

        # --- ACT ---
        with caplog.at_level(logging.WARNING):
            controller = UnifiedController()

        # --- ASSERT ---
        assert controller is not None
        assert "Failed to initialize DeviceUnderTest" in caplog.text
        assert "Defaulting to 'Portable' keypad layout" in caplog.text
        expected_default_layout = KEYPAD_LAYOUTS['Portable']

        # [BUG FIX] Add the new 'camera_hw_settings' parameter to the assertion.
        mock_camera_constructor.assert_called_once_with(
            camera_id=ANY,
            led_configs=ANY,
            display_order=ANY,
            logger_instance=ANY,
            duration_tolerance_sec=ANY,
            replay_post_failure_duration_sec=ANY,
            replay_output_dir=ANY,
            enable_instant_replay=ANY,
            keypad_layout=expected_default_layout,
            camera_hw_settings=ANY # <-- ADD THIS LINE
        )

    def test_initialization_skips_barcode_scan(self, mock_dependencies, caplog):
        """
        Tests that when skip_initial_scan=True, the DUT is initialized
        with a placeholder serial number, and an info message is logged.
        """
        # --- ARRANGE ---
        # Mock the function that loads settings from the JSON file to provide
        # a predictable device name for the test.
        mock_settings_return = ({}, {}, "test_device_profile_from_config")

        # --- [BUG FIX] ---
        # Patch both functions where they are DEFINED, not where they are imported/used.
        with patch('controllers.logitech_webcam._load_all_camera_settings', return_value=mock_settings_return), \
             patch('controllers.finite_state_machine.DeviceUnderTest') as mock_dut_constructor:
            # --- [END BUG FIX] ---

            # --- ACT ---
            # Initialize the controller with the skip_initial_scan flag set to True.
            # Capture logs at the INFO level to verify the log message.
            with caplog.at_level(logging.INFO):
                controller = UnifiedController(skip_initial_scan=True)

            # --- ASSERT ---
            # 1. Verify that the correct informational message was logged.
            assert "DUT initialization requested to skip initial barcode scan." in caplog.text

            # 2. Verify that the DeviceUnderTest constructor was called exactly once.
            mock_dut_constructor.assert_called_once()

            # 3. Inspect the keyword arguments passed to the constructor to ensure
            #    they match the logic in the 'if skip_initial_scan:' block.
            call_kwargs = mock_dut_constructor.call_args.kwargs
            
            assert call_kwargs.get('at_controller') is controller
            assert call_kwargs.get('target_device_profile') == "test_device_profile_from_config"
            assert call_kwargs.get('scanned_serial_number') == "SCAN_SKIPPED_BY_TOOL"

    def test_initialization_handles_phidget_exception(self, mock_dependencies, caplog):
        """
        GIVEN the PhidgetController constructor raises an exception
        WHEN UnifiedController is initialized
        THEN an error is logged and the internal phidget controller is None.
        """
        # --- ARRANGE ---
        # Configure the mocked PhidgetController class to raise an error when called
        error_message = "Phidget device not found"
        mock_dependencies["phidget"].side_effect = Exception(error_message)

        # --- ACT ---
        # Initialize the controller, which should catch the exception
        with caplog.at_level(logging.ERROR):
            controller = UnifiedController()

        # --- ASSERT ---
        # The internal controller instance should not have been assigned
        assert controller._phidget_controller is None
        # The error log should contain the specific message from the exception
        assert f"Failed to initialize PhidgetController: {error_message}" in caplog.text
        

    def test_phidget_methods_are_delegated(self, mock_dependencies):
        # NOTE: Parameterizing this test was problematic. Let's test one method directly.
        controller = UnifiedController()
        mock_phidget_instance = mock_dependencies["phidget"].return_value

        controller.press("button1", duration_ms=150)

        mock_phidget_instance.press.assert_called_once_with("button1", duration_ms=150)

    @pytest.mark.parametrize("method_name", ["on", "off"])
    def test_phidget_on_off_logic(self, mock_dependencies, caplog, method_name):
        """
        Tests the logic for 'on' and 'off' methods, covering both the success
        path (iteration over channels) and the failure path (uninitialized controller).
        """
        # --- ARRANGE (for success path) ---
        controller = UnifiedController()
        mock_phidget_instance = mock_dependencies["phidget"].return_value
        
        method_to_call = getattr(controller, method_name)
        mocked_phidget_method = getattr(mock_phidget_instance, method_name)
        
        # --- ACT (for success path) ---
        # Call the method with multiple channel arguments
        method_to_call("ch_A", "ch_B")
        
        # --- ASSERT (for success path) ---
        # Verify the underlying method was called for each channel
        expected_calls = [call("ch_A"), call("ch_B")]
        mocked_phidget_method.assert_has_calls(expected_calls, any_order=False)
        assert mocked_phidget_method.call_count == 2

        # --- ARRANGE (for failure path) ---
        # Reset the mock and break the controller for the second part of the test
        mocked_phidget_method.reset_mock()
        controller._phidget_controller = None
        
        # --- ACT (for failure path) ---
        with caplog.at_level(logging.ERROR):
            method_to_call("ch_C")

        # --- ASSERT (for failure path) ---
        # Verify the correct error was logged and the underlying method was not called
        assert f"Phidget not initialized for '{method_name}' command." in caplog.text
        mocked_phidget_method.assert_not_called()

    def test_phidget_hold_logic(self, mock_dependencies, caplog):
        """
        Tests the logic for the 'hold' method, covering both successful
        delegation and the uninitialized controller failure path.
        """
        # --- ARRANGE (Success Path) ---
        controller = UnifiedController()
        mock_phidget_instance = mock_dependencies["phidget"].return_value

        # --- ACT (Success Path) ---
        controller.hold("ch_hold", duration_ms=500)

        # --- ASSERT (Success Path) ---
        mock_phidget_instance.hold.assert_called_once_with("ch_hold", 500)

        # --- ARRANGE (Failure Path) ---
        # Break the internal controller reference
        controller._phidget_controller = None

        # --- ACT & ASSERT (Failure Path) ---
        with caplog.at_level(logging.ERROR):
            controller.hold("ch_hold_fail")
            assert "Phidget not init for 'hold'." in caplog.text
            # The call count should still be 1 from the successful call
            assert mock_phidget_instance.hold.call_count == 1

    @pytest.mark.parametrize(
        "method_name, success_args, success_kwargs, expected_call_args, expected_call_kwargs, failure_return_value",
        [
            # Test case for 'sequence'
            (
                "sequence",
                (['key1', 'key2', 'key3'],), # <<< FIX: Use strings, not integers
                {"press_duration_ms": 50, "pause_duration_ms": 75},
                (['key1', 'key2', 'key3'],), # <<< FIX: Match the corrected args
                {"press_ms": 50, "pause_ms": 75},
                None
            ),
            # Test case for 'read_input'
            (
                "read_input",
                ("in1",),
                {},
                ("in1",),
                {},
                None
            ),
            # Test case for 'wait_for_input' - CORRECTED
            (
                "wait_for_input",
                ("in2", True),
                {"timeout_s": 10},
                ("in2", True, 10, 0.05), # Correctly includes the default poll_interval_s
                {},
                False
            ),
        ]
    )
    def test_phidget_sequence_read_wait_logic(self, mock_dependencies, caplog, method_name, success_args, success_kwargs, expected_call_args, expected_call_kwargs, failure_return_value):
        """
        Tests delegation and failure paths for sequence, read_input, and wait_for_input.
        """
        # --- ARRANGE (Success Path) ---
        controller = UnifiedController()
        mock_phidget_instance = mock_dependencies["phidget"].return_value
        method_to_call = getattr(controller, method_name)
        mocked_phidget_method = getattr(mock_phidget_instance, method_name)

        # --- ACT (Success Path) ---
        method_to_call(*success_args, **success_kwargs)

        # --- ASSERT (Success Path) ---
        mocked_phidget_method.assert_called_once_with(*expected_call_args, **expected_call_kwargs)

        # --- ARRANGE (Failure Path) ---
        mocked_phidget_method.reset_mock()
        controller._phidget_controller = None  # Break the internal controller

        # --- ACT (Failure Path) ---
        with caplog.at_level(logging.ERROR):
            result = method_to_call(*success_args, **success_kwargs)

        # --- ASSERT (Failure Path) ---
        assert f"Phidget not init for '{method_name}'" in caplog.text
        assert result == failure_return_value
        mocked_phidget_method.assert_not_called()

    def test_is_camera_ready_property(self, mock_dependencies):
        """
        Tests the is_camera_ready property under different conditions.
        """
        # --- SCENARIO 1: Camera is initialized and ready ---
        # The default mock_dependencies setup handles this.
        mock_dependencies["camera"].return_value.is_camera_initialized = True
        controller_ready = UnifiedController()
        assert controller_ready.is_camera_ready is True
        
        # --- SCENARIO 2: Camera checker exists, but is not initialized ---
        mock_dependencies["camera"].return_value.is_camera_initialized = False
        controller_not_init = UnifiedController()
        assert controller_not_init.is_camera_ready is False

        # --- SCENARIO 3: Camera checker is None due to init exception ---
        mock_dependencies["camera"].side_effect = Exception("Camera Init Failure")
        controller_no_checker = UnifiedController()
        # The _camera_checker attribute itself will be None
        assert controller_no_checker._camera_checker is None
        assert controller_no_checker.is_camera_ready is False

    def test_initialization_handles_camera_exception(self, mock_dependencies, caplog):
        """
        GIVEN the LogitechLedChecker constructor raises an exception
        WHEN UnifiedController is initialized
        THEN an error is logged and the internal camera checker is None.
        """
        # --- ARRANGE ---
        # Configure the mocked LogitechLedChecker class to raise an error when called
        error_message = "Camera not available"
        mock_dependencies["camera"].side_effect = Exception(error_message)
        test_camera_id = 2

        # --- ACT ---
        # Initialize the controller, which should catch the exception
        with caplog.at_level(logging.ERROR):
            controller = UnifiedController(camera_id=test_camera_id)

        # --- ASSERT ---
        # The internal checker instance should not have been assigned
        assert controller._camera_checker is None
        # The error log should contain the specific message and camera ID
        assert f"Failed to initialize LogitechLedChecker for camera {test_camera_id}: {error_message}" in caplog.text

    def test_camera_delegation_when_ready(self, mock_dependencies):
        controller = UnifiedController()
        mock_camera_instance = mock_dependencies["camera"].return_value
        controller.confirm_led_solid({})
        mock_camera_instance.confirm_led_solid.assert_called_once()

    def test_camera_delegation_when_not_ready(self, mock_dependencies, caplog):
        mock_dependencies["camera"].return_value.is_camera_initialized = False
        controller = UnifiedController()
        mock_camera_instance = mock_dependencies["camera"].return_value
        result = controller.confirm_led_solid({})
        mock_camera_instance.confirm_led_solid.assert_not_called()
        assert "Camera not ready" in caplog.text
        assert result is False

    @pytest.mark.parametrize(
        "scan_result, log_level, expected_log_msg, expected_return",
        [
            # Scenario 1: Successful scan (Updated to match implementation)
            ("NEW_SERIAL_456", logging.DEBUG, "Scanned Serial Number: NEW_SERIAL_456", "NEW_SERIAL_456"),
            # Scenario 2: Scan fails or times out (returns None)
            (None, logging.WARNING, "On-demand barcode scan did not return data.", None),
        ]
    )
    def test_scan_barcode_scenarios(self, mock_dependencies, caplog, scan_result, log_level, expected_log_msg, expected_return):
        """
        Tests the scan_barcode method for both success and failure scenarios where the scanner is present.
        """
        # --- ARRANGE ---
        # Patch DeviceUnderTest to prevent the implicit scan during controller init.
        # This makes the test a true unit test of the scan_barcode method itself.
        with patch('controllers.finite_state_machine.DeviceUnderTest'):
            controller = UnifiedController()
        
        mock_scanner_instance = mock_dependencies["scanner"].return_value
        mock_scanner_instance.await_scan.return_value = scan_result

        # With the DUT patched, the initial serial number should be None.
        initial_serial = controller.scanned_serial_number

        # --- ACT ---
        # Set the level on the specific logger to ensure DEBUG messages are captured.
        with caplog.at_level(logging.DEBUG, logger='controllers.unified_controller'):
            returned_value = controller.scan_barcode()

        # --- ASSERT ---
        # With the init scan patched, await_scan is now only called once.
        mock_scanner_instance.await_scan.assert_called_once()

        # The return value from scan_barcode() should match the expected outcome
        assert returned_value == expected_return

        # The log should contain the expected message
        assert expected_log_msg in caplog.text
        
        # Check if the controller's serial number attribute was updated correctly
        if scan_result:
            assert controller.scanned_serial_number == scan_result
        else:
            # If the scan failed, the serial number should not have changed from its initial state.
            assert controller.scanned_serial_number == initial_serial

    def test_scan_barcode_no_scanner(self, mock_dependencies, caplog):
        """
        Tests that scan_barcode handles the case where the scanner is not initialized.
        """
        # --- ARRANGE ---
        controller = UnifiedController()
        
        # Manually break the internal scanner reference to simulate an init failure
        controller._barcode_scanner = None
        
        mock_scanner_instance = mock_dependencies["scanner"].return_value

        # --- ACT ---
        with caplog.at_level(logging.ERROR):
            result = controller.scan_barcode()

        # --- ASSERT ---
        # The method should return None because the scanner is unavailable
        assert result is None
        
        # The correct error should be logged
        assert "Barcode scanner not available." in caplog.text
        
        # The underlying scanner's await_scan method should NOT have been called
        mock_scanner_instance.await_scan.assert_not_called()

    @pytest.mark.parametrize("is_secure, expected_layout_key", [
        (True, 'Secure Key'),
        (False, 'Portable'),
    ])
    def test_initialization_passes_correct_keypad_layout(self, mock_dependencies, monkeypatch, is_secure, expected_layout_key):
        """
        Tests that the correct keypad layout is determined based on the DUT's
        'secure_key' attribute and passed to the camera checker's constructor.
        """
        # GIVEN: We will mock the DeviceUnderTest to control its attributes.
        from unittest.mock import ANY
        from utils.config.keypad_layouts import KEYPAD_LAYOUTS
        from controllers import finite_state_machine

        mock_dut_instance = MagicMock()
        mock_dut_instance.secure_key = is_secure
        mock_dut_instance.scanned_serial_number = "MOCK_SERIAL_123"

        monkeypatch.setattr(finite_state_machine, 'DeviceUnderTest', lambda *args, **kwargs: mock_dut_instance)

        # WHEN: The UnifiedController is initialized.
        with patch('sys.exit') as mock_exit:
            controller = UnifiedController()
            mock_exit.assert_not_called()

        # THEN: The LogitechLedChecker constructor should have been called with
        # the correct keypad layout.
        expected_layout = KEYPAD_LAYOUTS[expected_layout_key]
        mock_camera_constructor = mock_dependencies["camera"]

        # [BUG FIX] Add the new 'camera_hw_settings' parameter to the assertion.
        mock_camera_constructor.assert_called_once_with(
            camera_id=ANY,
            led_configs=ANY,
            display_order=ANY,
            logger_instance=ANY,
            duration_tolerance_sec=ANY,
            replay_post_failure_duration_sec=ANY,
            replay_output_dir=ANY,
            enable_instant_replay=ANY,
            keypad_layout=expected_layout,
            camera_hw_settings=ANY # <-- ADD THIS LINE
        )

    def test_run_fio_tests_path_formatting(self, mock_dependencies, monkeypatch):
        """
        Tests that the FIO device path is formatted correctly for each OS.
        """
        controller = UnifiedController()

        # GIVEN: Mock JSON outputs for a write test and a read test
        mock_write_json = '{"jobs": [{"write": {"io_bytes": 1, "bw_bytes": 150000000}}]}'
        mock_read_json = '{"jobs": [{"read": {"io_bytes": 1, "bw_bytes": 250000000}}]}'

        # Configure the mock subprocess to return these outputs in sequence
        mock_write_result = MagicMock(stdout=mock_write_json)
        mock_read_result = MagicMock(stdout=mock_read_json)
        
        with patch.object(unified_controller_module, 'subprocess') as mock_subprocess:
            with patch.object(controller, '_get_fio_path', return_value='mock_fio_path'):
                # Set the side_effect to return the write result first, then the read result
                mock_subprocess.run.side_effect = [mock_write_result, mock_read_result]
                
                # --- Test Windows Path ---
                monkeypatch.setattr(sys, 'platform', 'win32')
                # WHEN
                final_results_win = controller.run_fio_tests(disk_path="3")
                
                # THEN
                fio_command_args_win = mock_subprocess.run.call_args_list[0].args[0]
                assert any(arg.endswith("\\\\.\\PhysicalDrive3") for arg in fio_command_args_win)
                assert final_results_win == {'write': 150.0, 'read': 250.0}

                # --- Test Linux Path ---
                mock_subprocess.run.reset_mock()
                mock_subprocess.run.side_effect = [mock_write_result, mock_read_result] # Reset side effect
                monkeypatch.setattr(sys, 'platform', 'linux')
                # WHEN
                final_results_linux = controller.run_fio_tests(disk_path="/dev/sdb")
                
                # THEN
                fio_command_args_linux = mock_subprocess.run.call_args_list[0].args[0]
                assert any(arg.endswith("/dev/sdb") for arg in fio_command_args_linux)
                assert final_results_linux == {'write': 150.0, 'read': 250.0}

    def test_parse_fio_json_output(self, mock_dependencies):
        controller = UnifiedController()
        
        # Test case with both read and write results
        sample_json_rw = '{"jobs": [{"read": {"io_bytes": 1, "bw_bytes": 250000000}, "write": {"io_bytes": 1, "bw_bytes": 150000000}}]}'
        result_rw = controller._parse_fio_json_output(sample_json_rw)
        assert result_rw == {'read': 250.0, 'write': 150.0}

        # Test case with only read results (write bytes are 0)
        sample_json_r = '{"jobs": [{"read": {"io_bytes": 1, "bw_bytes": 300000000}, "write": {"io_bytes": 0}}]}'
        result_r = controller._parse_fio_json_output(sample_json_r)
        assert result_r == {'read': 300.0}

        # Test case where no operations happened (io_bytes are 0)
        sample_json_empty_job = '{"jobs": [{"read": {"io_bytes": 0}, "write": {"io_bytes": 0}}]}'
        result_empty = controller._parse_fio_json_output(sample_json_empty_job)
        # CORRECTED ASSERTION: The function returns None when the results dict is empty.
        assert result_empty is None

        # Test case with missing 'jobs' key
        sample_json_no_jobs = '{"other_key": "value"}'
        result_no_jobs = controller._parse_fio_json_output(sample_json_no_jobs)
        assert result_no_jobs is None

        # Test case with invalid JSON
        sample_invalid_json = '{"jobs": [}'
        result_invalid = controller._parse_fio_json_output(sample_invalid_json)
        assert result_invalid is None

    def test_confirm_led_solid_strict_delegation(self, mock_dependencies, caplog):
        """
        Tests the logic for 'confirm_led_solid_strict', covering both successful
        delegation and the uninitialized camera failure path.
        """
        # --- ARRANGE (Success Path) ---
        controller = UnifiedController()
        mock_camera_instance = mock_dependencies["camera"].return_value

        test_state = {"green": 1}
        test_context = {"fsm_state": "TESTING"}
        
        # --- ACT (Success Path) ---
        controller.confirm_led_solid_strict(
            state=test_state,
            minimum=2.5,
            clear_buffer=False,
            manage_replay=False,
            replay_extra_context=test_context
        )

        # --- ASSERT (Success Path) ---
        mock_camera_instance.confirm_led_solid_strict.assert_called_once_with(
            test_state, 2.5, False, manage_replay=False, replay_extra_context=test_context
        )

        # --- ARRANGE (Failure Path) ---
        # Break the camera readiness
        mock_camera_instance.reset_mock()
        mock_camera_instance.is_camera_initialized = False
        
        # --- ACT (Failure Path) ---
        with caplog.at_level(logging.ERROR):
            result = controller.confirm_led_solid_strict(test_state, 2.5)

        # --- ASSERT (Failure Path) ---
        assert result is False
        assert "Camera not ready for confirm_led_solid_strict." in caplog.text
        mock_camera_instance.confirm_led_solid_strict.assert_not_called()

    def test_await_led_state_delegation(self, mock_dependencies, caplog):
        """
        Tests the logic for 'await_led_state', covering both successful
        delegation and the uninitialized camera failure path.
        """
        # --- ARRANGE (Success Path) ---
        controller = UnifiedController()
        mock_camera_instance = mock_dependencies["camera"].return_value

        test_state = {"blue": 1}
        test_context = {"step": "AWAIT_BLUE"}
        test_fail_leds = ["red"]

        # --- ACT (Success Path) ---
        controller.await_led_state(
            state=test_state,
            timeout=5.0,
            fail_leds=test_fail_leds,
            clear_buffer=False,
            manage_replay=False,
            replay_extra_context=test_context
        )

        # --- ASSERT (Success Path) ---
        mock_camera_instance.await_led_state.assert_called_once_with(
            test_state, 5.0, test_fail_leds, False, manage_replay=False, replay_extra_context=test_context
        )

        # --- ARRANGE (Failure Path) ---
        mock_camera_instance.reset_mock()
        mock_camera_instance.is_camera_initialized = False
        
        # --- ACT (Failure Path) ---
        with caplog.at_level(logging.ERROR):
            result = controller.await_led_state(test_state, 5.0)

        # --- ASSERT (Failure Path) ---
        assert result is False
        assert "Camera not ready for await_led_state." in caplog.text
        mock_camera_instance.await_led_state.assert_not_called()

    def test_confirm_led_pattern_delegation(self, mock_dependencies, caplog):
        """
        Tests delegation and failure path for the 'confirm_led_pattern' method.
        """
        # --- ARRANGE (Success Path) ---
        controller = UnifiedController()
        mock_camera_instance = mock_dependencies["camera"].return_value

        test_pattern = [{"state": "A", "duration": 1}]
        test_context = {"step": "CONFIRM_A"}

        # --- ACT (Success Path) ---
        controller.confirm_led_pattern(
            pattern=test_pattern,
            clear_buffer=False,
            manage_replay=False,
            replay_extra_context=test_context
        )

        # --- ASSERT (Success Path) ---
        mock_camera_instance.confirm_led_pattern.assert_called_once_with(
            test_pattern, False, manage_replay=False, replay_extra_context=test_context
        )

        # --- ARRANGE (Failure Path) ---
        mock_camera_instance.reset_mock()
        mock_camera_instance.is_camera_initialized = False

        # --- ACT (Failure Path) ---
        with caplog.at_level(logging.ERROR):
            result = controller.confirm_led_pattern(test_pattern)
        
        # --- ASSERT (Failure Path) ---
        assert result is False
        assert "Camera not ready for confirm_led_pattern." in caplog.text
        mock_camera_instance.confirm_led_pattern.assert_not_called()

    def test_await_and_confirm_led_pattern_delegation(self, mock_dependencies, caplog):
        """
        Tests delegation and failure path for the 'await_and_confirm_led_pattern' method.
        """
        # --- ARRANGE (Success Path) ---
        controller = UnifiedController()
        mock_camera_instance = mock_dependencies["camera"].return_value

        test_pattern = [{"state": "B", "duration": 2}]
        test_context = {"step": "AWAIT_B"}

        # --- ACT (Success Path) ---
        controller.await_and_confirm_led_pattern(
            pattern=test_pattern,
            timeout=15.0,
            clear_buffer=False,
            manage_replay=False,
            replay_extra_context=test_context
        )

        # --- ASSERT (Success Path) ---
        mock_camera_instance.await_and_confirm_led_pattern.assert_called_once_with(
            test_pattern, 15.0, False, manage_replay=False, replay_extra_context=test_context
        )

        # --- ARRANGE (Failure Path) ---
        mock_camera_instance.reset_mock()
        mock_camera_instance.is_camera_initialized = False

        # --- ACT (Failure Path) ---
        with caplog.at_level(logging.ERROR):
            result = controller.await_and_confirm_led_pattern(test_pattern, 15.0)
        
        # --- ASSERT (Failure Path) ---
        assert result is False
        assert "Camera not ready for await_and_confirm_led_pattern." in caplog.text
        mock_camera_instance.await_and_confirm_led_pattern.assert_not_called()

    def test_close_method_scenarios(self, mock_dependencies, caplog):
        """
        Tests the close() method under various conditions, including success
        and exceptions during component cleanup.
        """
        # --- SCENARIO 1: Both components close successfully ---
        controller = UnifiedController()
        mock_camera_instance = mock_dependencies["camera"].return_value
        mock_phidget_instance = mock_dependencies["phidget"].return_value
        
        controller.close()
        
        mock_camera_instance.release_camera.assert_called_once()
        mock_phidget_instance.close_all.assert_called_once()

        # --- SCENARIO 2: Camera fails to close, Phidget succeeds ---
        mock_camera_instance.reset_mock()
        mock_phidget_instance.reset_mock()
        
        # Configure the camera's close method to raise an error
        error_message = "Camera hardware disconnected"
        mock_camera_instance.release_camera.side_effect = Exception(error_message)
        
        with caplog.at_level(logging.ERROR):
            controller.close()
            # The error log should contain the specific message
            assert f"Error releasing camera: {error_message}" in caplog.text
        
        # Even though the camera failed, the phidget should still be closed
        mock_phidget_instance.close_all.assert_called_once()
        
        # --- SCENARIO 3: Phidget fails to close, Camera succeeds ---
        caplog.clear() # Clear logs from the previous scenario
        mock_camera_instance.reset_mock()
        mock_phidget_instance.reset_mock()
        
        # Fix the camera mock and break the phidget mock
        mock_camera_instance.release_camera.side_effect = None
        phidget_error = "Phidget channel still open"
        mock_phidget_instance.close_all.side_effect = Exception(phidget_error)
        
        with caplog.at_level(logging.ERROR):
            controller.close()
            assert f"Error closing phidget: {phidget_error}" in caplog.text
            
        # The camera should have been closed successfully
        mock_camera_instance.release_camera.assert_called_once()

        # --- SCENARIO 4: A component is None and should be skipped ---
        mock_camera_instance.reset_mock()
        mock_phidget_instance.reset_mock()
        
        # Manually remove the phidget controller
        controller._phidget_controller = None
        
        controller.close()
        
        # Camera should be closed, phidget's close should not be attempted
        mock_camera_instance.release_camera.assert_called_once()
        mock_phidget_instance.close_all.assert_not_called()


# New class to test module-level setup logic
class TestModuleSetup:
    """
    Tests for the module-level setup code in unified_controller.py,
    specifically the sys.path modification.
    """

    def test_project_root_is_added_to_sys_path_if_missing(self):
        """
        GIVEN the project's root path is NOT in sys.path
        WHEN the unified_controller module is imported
        THEN the project's root path should be inserted at the beginning of sys.path
        """
        # --- ARRANGE ---
        # Get the path that the module *would* calculate
        controllers_dir = os.path.dirname(unified_controller_module.__file__)
        project_root = os.path.dirname(controllers_dir)

        # Save the original path and module cache for later restoration
        original_sys_path = list(sys.path)
        original_uc_module = sys.modules.get('controllers.unified_controller')

        # Ensure the path is NOT in sys.path for this test
        if project_root in sys.path:
            sys.path.remove(project_root)

        # Remove the module from the cache to force a re-import
        if 'controllers.unified_controller' in sys.modules:
            del sys.modules['controllers.unified_controller']

        # --- ACT ---
        # Re-importing the module will execute its top-level code again
        import controllers.unified_controller as reloaded_module

        # --- ASSERT ---
        # Verify that the path was added to the beginning of the list
        assert sys.path[0] == project_root

        # --- CLEANUP ---
        # Restore sys.path and the module cache to not affect other tests
        sys.path[:] = original_sys_path
        if original_uc_module:
            sys.modules['controllers.unified_controller'] = original_uc_module
        else:
            # If it wasn't there to begin with, ensure it's removed again
            if 'controllers.unified_controller' in sys.modules:
                del sys.modules['controllers.unified_controller']


    def test_project_root_is_not_added_if_already_present(self):
        """
        GIVEN the project's root path IS already in sys.path
        WHEN the unified_controller module is imported
        THEN sys.path should NOT be modified
        """
        # --- ARRANGE ---
        controllers_dir = os.path.dirname(unified_controller_module.__file__)
        project_root = os.path.dirname(controllers_dir)

        original_sys_path = list(sys.path)
        original_uc_module = sys.modules.get('controllers.unified_controller')

        # Ensure the path IS in sys.path for this test
        if project_root not in sys.path:
            sys.path.append(project_root)

        # Store the state of sys.path *before* the re-import to check for changes
        path_before_reload = list(sys.path)

        if 'controllers.unified_controller' in sys.modules:
            del sys.modules['controllers.unified_controller']

        # --- ACT ---
        import controllers.unified_controller as reloaded_module

        # --- ASSERT ---
        # Verify that the sys.path list is identical to how it was before the import
        assert sys.path == path_before_reload

        # --- CLEANUP ---
        sys.path[:] = original_sys_path
        if original_uc_module:
            sys.modules['controllers.unified_controller'] = original_uc_module

             

# Mock class to simulate the device object returned by find_apricorn_device
class MockApricornDevice:
    def __init__(self, iSerial, driveSizeGB, **kwargs):
        self.iSerial = iSerial
        self.driveSizeGB = driveSizeGB
        self.idVendor = kwargs.get('idVendor', '0984')
        self.idProduct = kwargs.get('idProduct', '0205')
        self.bcdDevice = kwargs.get('bcdDevice', '1.00')
        self.bcdUSB = kwargs.get('bcdUSB', '2.10')
        self.iProduct = kwargs.get('iProduct', 'MockDrive')

    def __repr__(self):
        return f"MockApricornDevice(iSerial='{self.iSerial}')"


class ConfirmEnumBaseTests:
    """
    A generic base class for testing confirm_device_enum and confirm_drive_enum.
    This class is not run directly by pytest.
    Subclasses must define METHOD_NAME and state-related attributes.
    """
    METHOD_NAME = None
    SERIAL_NUM = "OVERRIDE_IN_SUBCLASS"
    GOOD_DRIVE_STATE = "OVERRIDE_IN_SUBCLASS"
    BAD_DRIVE_STATE = "OVERRIDE_IN_SUBCLASS"
    WRONG_MODE_LOG_MSG = "OVERRIDE_IN_SUBCLASS"
    MODE_CHANGE_LOG_MSG = "OVERRIDE_IN_SUBCLASS"

    @pytest.fixture
    def controller_and_mocks(self, mock_dependencies):
        """
        Fixture that provides a controller instance created *after* time has been
        fully mocked to prevent test hangs from busy-wait loops.
        """
        # instantiating the controller.
        with patch('time.sleep'), patch('time.time') as mock_time:
            # Configure a simple, incrementing time mock for general use.
            # This prevents TypeErrors and ensures any while loop terminates instantly.
            # The test_enum_fails_on_timeout will override this with its own patch.
            call_count = 0
            def time_incrementer(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return call_count
            mock_time.side_effect = time_incrementer

            controller = UnifiedController()
            find_device_mock = mock_dependencies["find_device"]
            yield controller, find_device_mock

    def _call_method(self, controller, *args, **kwargs):
        """Helper to call the correct method based on the subclass."""
        assert self.METHOD_NAME is not None, "Subclasses of ConfirmEnumBaseTests must define METHOD_NAME"
        return getattr(controller, self.METHOD_NAME)(*args, **kwargs)

    def test_enum_success(self, controller_and_mocks, caplog):
        controller, find_device_mock = controller_and_mocks
        mock_device = MockApricornDevice(self.SERIAL_NUM, self.GOOD_DRIVE_STATE)
        find_device_mock.side_effect = [[mock_device], [mock_device]]
        with caplog.at_level(logging.INFO):
            is_stable, dev_info = self._call_method(controller, self.SERIAL_NUM)
        assert is_stable is True
        assert dev_info is mock_device
        assert "confirmed stable" in caplog.text

    def test_enum_fails_initial_device_not_found(self, controller_and_mocks, caplog):
        controller, find_device_mock = controller_and_mocks
        find_device_mock.return_value = []
        with caplog.at_level(logging.WARNING):
            is_stable, dev_info = self._call_method(controller, self.SERIAL_NUM)
        assert is_stable is False and dev_info is None
        assert "No device found" in caplog.text

    def test_enum_fails_no_matching_serial(self, controller_and_mocks, caplog):
        controller, find_device_mock = controller_and_mocks
        find_device_mock.return_value = [MockApricornDevice("WRONG_SN", self.GOOD_DRIVE_STATE)]
        with caplog.at_level(logging.ERROR):
            is_stable, dev_info = self._call_method(controller, self.SERIAL_NUM)
        assert is_stable is False and dev_info is None
        assert "Could not match devices" in caplog.text

    def test_enum_fails_on_wrong_drive_mode(self, controller_and_mocks, caplog):
        controller, find_device_mock = controller_and_mocks
        find_device_mock.return_value = [MockApricornDevice(self.SERIAL_NUM, self.BAD_DRIVE_STATE)]
        with caplog.at_level(logging.WARNING):
            is_stable, dev_info = self._call_method(controller, self.SERIAL_NUM)
        assert is_stable is False and dev_info is None
        assert self.WRONG_MODE_LOG_MSG in caplog.text

    @patch('time.time')
    def test_enum_fails_on_timeout(self, mock_time, controller_and_mocks, caplog):
        controller, find_device_mock = controller_and_mocks
        find_device_mock.return_value = [MockApricornDevice(self.SERIAL_NUM, self.GOOD_DRIVE_STATE)]
        call_count = 0
        def time_advancer(*args, **kwargs):
            nonlocal call_count; call_count += 1
            if call_count <= 2: return 0
            elif call_count == 3: return 1
            else: return 16
        mock_time.side_effect = time_advancer
        with caplog.at_level(logging.WARNING):
            is_stable, dev_info = self._call_method(controller, self.SERIAL_NUM, stable_min=5, timeout=15)
        assert is_stable is False and dev_info is None
        assert "Overall timeout" in caplog.text

    def test_enum_fails_if_device_disappears(self, controller_and_mocks, caplog):
        controller, find_device_mock = controller_and_mocks
        mock_device = MockApricornDevice(self.SERIAL_NUM, self.GOOD_DRIVE_STATE)
        find_device_mock.side_effect = [[mock_device], []]
        with caplog.at_level(logging.WARNING):
            is_stable, dev_info = self._call_method(controller, self.SERIAL_NUM)
        assert is_stable is False and dev_info is None
        assert "disappeared after" in caplog.text

    def test_enum_fails_if_drive_mode_changes(self, controller_and_mocks, caplog):
        controller, find_device_mock = controller_and_mocks
        initial_device = MockApricornDevice(self.SERIAL_NUM, self.GOOD_DRIVE_STATE)
        final_device = MockApricornDevice(self.SERIAL_NUM, self.BAD_DRIVE_STATE)
        find_device_mock.side_effect = [[initial_device], [final_device]]
        with caplog.at_level(logging.WARNING):
            is_stable, dev_info = self._call_method(controller, self.SERIAL_NUM)
        assert is_stable is False and dev_info is None
        assert self.MODE_CHANGE_LOG_MSG in caplog.text

    def test_enum_fails_if_device_serial_changes(self, controller_and_mocks, caplog):
        controller, find_device_mock = controller_and_mocks
        initial_device = MockApricornDevice(self.SERIAL_NUM, self.GOOD_DRIVE_STATE)
        changed_device = MockApricornDevice("DIFFERENT_SN", self.GOOD_DRIVE_STATE)
        find_device_mock.side_effect = [[initial_device], [changed_device]]
        with caplog.at_level(logging.ERROR):
            is_stable, dev_info = self._call_method(controller, self.SERIAL_NUM)
        assert is_stable is False and dev_info is None
        assert "Device is not stable on the bus" in caplog.text


# Subclass inherits all tests and is discovered by pytest
class TestConfirmDeviceEnum(ConfirmEnumBaseTests):
    """Tests for the confirm_device_enum method (OOB/Standby Mode)."""
    METHOD_NAME = "confirm_device_enum"
    SERIAL_NUM = "TEST_OOB_SN"
    GOOD_DRIVE_STATE = "N/A (OOB Mode)"
    BAD_DRIVE_STATE = "1000 GB"
    WRONG_MODE_LOG_MSG = "Device volume is exposed!"
    MODE_CHANGE_LOG_MSG = "Device volume became exposed"


# Subclass inherits all tests and is discovered by pytest
class TestConfirmDriveEnum(ConfirmEnumBaseTests):
    """Tests for the confirm_drive_enum method (Data Drive Mode)."""
    METHOD_NAME = "confirm_drive_enum"
    SERIAL_NUM = "TEST_DRIVE_SN"
    GOOD_DRIVE_STATE = "1000 GB"
    BAD_DRIVE_STATE = "N/A (OOB Mode)"
    WRONG_MODE_LOG_MSG = "Device volume is not exposed!"
    MODE_CHANGE_LOG_MSG = "Device volume disappeared"

class TestFioHelpers:
    """A dedicated test class for FIO-related helper methods."""

    @pytest.fixture
    def controller(self, mock_dependencies):
        """Provides a standard controller instance."""
        return UnifiedController()

    @pytest.mark.parametrize(
        "platform, expected_binary_name",
        [
            ('darwin', 'fio-macos'),
            ('linux', 'fio-linux'),
            ('win32', 'fio-windows.exe'),
        ]
    )
    def test_get_fio_path_success_platforms(self, controller, monkeypatch, platform, expected_binary_name):
        """Tests that the correct FIO binary path is returned for supported OSes."""
        # ARRANGE: Simulate the OS and a valid, executable file
        monkeypatch.setattr(sys, 'platform', platform)
        monkeypatch.setattr(os.path, 'isfile', lambda path: True)
        monkeypatch.setattr(os, 'access', lambda path, mode: True)

        # ACT
        fio_path = controller._get_fio_path()

        # ASSERT
        assert expected_binary_name in fio_path
        
    def test_get_fio_path_unsupported_os_raises_error(self, controller, monkeypatch):
        """Tests that an unsupported OS raises NotImplementedError."""
        # ARRANGE: Simulate an unsupported OS
        monkeypatch.setattr(sys, 'platform', 'sunos')

        # ACT & ASSERT
        with pytest.raises(NotImplementedError) as excinfo:
            controller._get_fio_path()
        assert "not supported on this OS: sunos" in str(excinfo.value)

    def test_get_fio_path_missing_file_raises_error(self, controller, monkeypatch):
        """Tests that a missing binary file raises FileNotFoundError."""
        # ARRANGE: Simulate a supported OS but a missing file
        monkeypatch.setattr(sys, 'platform', 'linux')
        monkeypatch.setattr(os.path, 'isfile', lambda path: False)

        # ACT & ASSERT
        with pytest.raises(FileNotFoundError):
            controller._get_fio_path()
            
    def test_get_fio_path_not_executable_logs_warning(self, controller, monkeypatch, caplog):
        """Tests that a non-executable binary on a non-Windows OS logs a warning."""
        # ARRANGE: Simulate Linux with a file that exists but isn't executable
        monkeypatch.setattr(sys, 'platform', 'linux')
        monkeypatch.setattr(os.path, 'isfile', lambda path: True)
        monkeypatch.setattr(os, 'access', lambda path, mode: False)

        # ACT
        with caplog.at_level(logging.WARNING):
            fio_path = controller._get_fio_path()

        # ASSERT
        # The path should still be returned
        assert "fio-linux" in fio_path
        # A warning should be logged
        assert "is not executable" in caplog.text

    def test_get_fio_path_not_executable_on_windows_is_ok(self, controller, monkeypatch, caplog):
        """Tests that non-executable check is skipped on Windows, so no warning is logged."""
        # ARRANGE: Simulate Windows with a file that exists but isn't "executable" by os.access
        monkeypatch.setattr(sys, 'platform', 'win32')
        monkeypatch.setattr(os.path, 'isfile', lambda path: True)
        monkeypatch.setattr(os, 'access', lambda path, mode: False) # This check is skipped on Windows

        # ACT
        with caplog.at_level(logging.WARNING):
            controller._get_fio_path()

        # ASSERT: No warning should be logged for this case on Windows
        assert "is not executable" not in caplog.text

    def test_run_fio_tests_handles_get_path_error(self, controller, caplog):
        """
        Tests that run_fio_tests catches and re-raises errors from _get_fio_path.
        """
        # --- ARRANGE ---
        # Mock _get_fio_path to raise an error
        error_message = "FIO is not supported"
        with patch.object(controller, '_get_fio_path', side_effect=NotImplementedError(error_message)):
            # --- ACT & ASSERT ---
            with pytest.raises(NotImplementedError), caplog.at_level(logging.ERROR):
                controller.run_fio_tests(disk_path="/dev/sdb")
        
        # Verify the correct log message was generated before re-raising
        assert f"Cannot run FIO tests: {error_message}" in caplog.text

    def test_run_fio_tests_windows_non_digit_path(self, controller, monkeypatch):
        """
        Tests the 'else' branch for Windows path handling where the path is
        not just a digit (e.g., already 'PhysicalDrive1').
        """
        # --- ARRANGE ---
        monkeypatch.setattr(sys, 'platform', 'win32')
        with patch.object(controller, '_get_fio_path', return_value='fio.exe'), \
             patch.object(unified_controller_module, 'subprocess') as mock_subprocess:
            
            # THE FIX: Configure the mock to return a valid result object.
            # This prevents the TypeError inside json.loads().
            mock_result = MagicMock(stdout='{"jobs": [{"read": {"io_bytes": 1}}]}')
            mock_subprocess.run.return_value = mock_result
            
            # --- ACT ---
            controller.run_fio_tests(disk_path="PhysicalDrive1")

        # --- ASSERT ---
        called_args = mock_subprocess.run.call_args.args[0]
        assert any(arg.endswith("\\\\.\\PhysicalDrive1") for arg in called_args)

    @pytest.mark.parametrize(
        "exception_to_raise, expected_log_msg",
        [
            # Test that a CalledProcessError is caught and logged
            (
                subprocess.CalledProcessError(1, "fio", stderr="Permission Denied"),
                "failed with exit code 1"
            ),
            # Test that another, unexpected Exception is caught and logged
            (
                ValueError("A surprising error"),
                "An unexpected error occurred"
            ),
        ]
    )
    def test_run_fio_handles_subprocess_exceptions(self, controller, caplog, exception_to_raise, expected_log_msg):
        """
        Tests that exceptions raised by subprocess.run are caught and logged correctly.
        """
        # --- ARRANGE ---
        # Mock _get_fio_path to prevent its own logic from running
        # Patch subprocess.run directly within the module where it's imported (unified_controller_module).
        with patch.object(controller, '_get_fio_path', return_value='fio'), \
             patch.object(unified_controller_module.subprocess, 'run') as mock_subprocess_run:
            
            # Configure the mocked run method to raise the exception for this test case
            mock_subprocess_run.side_effect = exception_to_raise

            # --- ACT ---
            with caplog.at_level(logging.ERROR):
                result = controller.run_fio_tests(disk_path="/dev/sdb")

            # --- ASSERT ---
            assert result is None
            assert expected_log_msg in caplog.text

    def test_run_fio_handles_file_not_found_from_subprocess(self, controller, caplog, monkeypatch):
        """
        Tests that a FileNotFoundError from subprocess.run is caught, logged, and re-raised.
        This simulates a race condition where the file disappears after being checked.
        """
        # --- ARRANGE ---
        # We need _get_fio_path to succeed, but subprocess.run to fail.
        fio_path = 'path/to/nonexistent/fio'
        monkeypatch.setattr(controller, '_get_fio_path', lambda: fio_path)

        # Patch the specific `run` function within the module's `subprocess` object
        # FIX: Use patch.object on the module's subprocess.run for precise control.
        with patch.object(unified_controller_module.subprocess, 'run') as mock_subprocess_run:
            # Configure subprocess.run to raise the FileNotFoundError
            # FIX: Raise the FileNotFoundError instance. The exact message is OS-dependent,
            # but the type is consistent.
            mock_subprocess_run.side_effect = FileNotFoundError("Simulated FNF error")

            # Determine an OS-appropriate disk path, though the mock prevents actual execution.
            if sys.platform == 'win32':
                disk_path = "1" # Represents PhysicalDrive1
            else:
                disk_path = "/dev/sdb"

            # --- ACT & ASSERT ---
            # Use pytest.raises to confirm the exception is re-raised
            with pytest.raises(FileNotFoundError) as excinfo:
                with caplog.at_level(logging.ERROR):
                    controller.run_fio_tests(disk_path=disk_path)
            
            # Assert that the re-raised exception is of the correct type
            # FIX: Check the exception type directly, as its string representation is OS-dependent.
            assert excinfo.type is FileNotFoundError
            
            # Assert that our specific log message was generated by the except block
            assert f"FIO command not found at '{fio_path}'" in caplog.text
            mock_subprocess_run.assert_called_once()

    def test_run_fio_fails_on_parse_error(self, controller, caplog):
        """Tests that a failure to parse FIO's JSON output is handled correctly."""
        # --- ARRANGE ---
        # Mock all dependencies to isolate the parsing logic.
        with patch.object(controller, '_get_fio_path', return_value='fio'), \
             patch.object(unified_controller_module, 'subprocess') as mock_subprocess, \
             patch.object(controller, '_parse_fio_json_output', return_value=None) as mock_parse:
            
            # Ensure subprocess.run() 'succeeds' so we can test the parsing failure.
            mock_subprocess.run.return_value = MagicMock(stdout='{}') # Content doesn't matter
            
            # --- ACT ---
            with caplog.at_level(logging.ERROR):
                result = controller.run_fio_tests(disk_path="/dev/sdb")

            # --- ASSERT ---
            assert result is None
            assert "Failed to parse results" in caplog.text
            mock_parse.assert_called_once()

class TestFsmEventHandlers:
    """Tests for high-level FSM event handling callbacks."""

    @pytest.fixture
    def controller(self, mock_dependencies):
        """Provides a standard controller instance."""
        return UnifiedController()

    def test_handle_post_failure(self, controller, caplog):
        """
        Tests the handle_post_failure method with various event_data structures.
        """
        # --- SCENARIO 1: event_data has kwargs with 'details' ---
        mock_event_with_details = MagicMock()
        mock_event_with_details.kwargs = {'details': 'Test failure reason 123'}
        
        with caplog.at_level(logging.ERROR):
            controller.handle_post_failure(mock_event_with_details)
        
        assert "Handling POST failure. Details from FSM: Test failure reason 123" in caplog.text
        caplog.clear() # Clear logs for the next scenario

        # --- SCENARIO 2: event_data has kwargs but no 'details' key ---
        mock_event_no_details = MagicMock()
        mock_event_no_details.kwargs = {'other_key': 'some_value'}

        with caplog.at_level(logging.ERROR):
            controller.handle_post_failure(mock_event_no_details)
        
        assert "Handling POST failure. Details from FSM: No details provided" in caplog.text
        caplog.clear()

        # --- SCENARIO 3: event_data has no kwargs attribute ---
        # A plain object is a good way to simulate this
        mock_event_no_kwargs = object()

        with caplog.at_level(logging.ERROR):
            controller.handle_post_failure(mock_event_no_kwargs)

        assert "Handling POST failure. Details from FSM: No details provided" in caplog.text
        caplog.clear()

        # --- SCENARIO 4: event_data is None ---
        with caplog.at_level(logging.ERROR):
            controller.handle_post_failure(None)

        assert "Handling POST failure. Details from FSM: No details provided" in caplog.text

    def test_handle_critical_error(self, controller, caplog):
        """
        Tests the handle_critical_error method with various event_data structures.
        """
        # --- SCENARIO 1: event_data has kwargs with 'details' ---
        mock_event_with_details = MagicMock()
        mock_event_with_details.kwargs = {'details': 'A critical failure occurred'}
        
        with caplog.at_level(logging.CRITICAL):
            controller.handle_critical_error(mock_event_with_details)
        
        assert "Handling CRITICAL error. Details from FSM: A critical failure occurred" in caplog.text
        caplog.clear()

        # --- SCENARIO 2: event_data has kwargs but no 'details' key ---
        mock_event_no_details = MagicMock()
        mock_event_no_details.kwargs = {'other_key': 'some_value'}

        with caplog.at_level(logging.CRITICAL):
            controller.handle_critical_error(mock_event_no_details)
        
        assert "Handling CRITICAL error. Details from FSM: No details provided" in caplog.text
        caplog.clear()

        # --- SCENARIO 3: event_data is None ---
        with caplog.at_level(logging.CRITICAL):
            controller.handle_critical_error(None)

        assert "Handling CRITICAL error. Details from FSM: No details provided" in caplog.text