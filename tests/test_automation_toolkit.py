# Directory: tests/
# Filename: test_automation_toolkit.py

#############################################################
##
## This test file is designed to systematically cover every function
## in controllers/automation_toolkit.py.
##
## Run this test with the following command:
## pytest tests/test_automation_toolkit.py --cov=automation_toolkit --cov-report term-missing
##
#############################################################

import pytest
from unittest.mock import patch, MagicMock
from contextlib import redirect_stdout
import importlib
import io
import logging

# We will be reloading this module, so we need a way to reference it.
import automation_toolkit as at_toolkit
import runpy
import sys


class TestAutomationToolkit:
    """
    Tests the initialization logic and getter functions of the automation_toolkit.
    """

    def test_getters_raise_error_when_uninitialized(self):
        """
        Tests that all getter functions raise a RuntimeError if their
        corresponding global object is None.
        """
        # GIVEN: The global objects are None
        at_toolkit.at = None
        at_toolkit.dut = None
        at_toolkit.session = None
        at_toolkit.fsm = None
        at_toolkit.pin_gen = None

        # THEN: Each getter should raise a RuntimeError
        with pytest.raises(RuntimeError):
            at_toolkit.get_at_controller()
        with pytest.raises(RuntimeError):
            at_toolkit.get_dut()
        with pytest.raises(RuntimeError):
            at_toolkit.get_session()
        with pytest.raises(RuntimeError):
            at_toolkit.get_fsm()
        with pytest.raises(RuntimeError):
            at_toolkit.get_pin_generator()

    @patch('controllers.unified_controller.UnifiedController')
    @patch('controllers.finite_state_machine.TestSession')
    @patch('controllers.finite_state_machine.ApricornDeviceFSM')
    @patch('utils.pin_generator.PINGenerator')
    @patch('automation_toolkit.os.makedirs')
    @patch('automation_toolkit.setup_logging')
    def test_successful_initialization(self, mock_setup_logging, mock_makedirs,
                                     mock_pingenerator, mock_fsm, mock_session,
                                     mock_unified_controller):
        """
        Tests the full, successful initialization path where all components
        are created without error.
        """
        # GIVEN: We get handles to the mock instances that will be created.
        mock_at_instance = mock_unified_controller.return_value
        # The 'dut' instance is an attribute of the 'at' instance mock.
        mock_dut_instance = mock_at_instance.dut

        importlib.reload(at_toolkit)

        # THEN: All global objects should have been created (are not None)
        assert at_toolkit.at is not None
        assert at_toolkit.dut is not None
        assert at_toolkit.session is not None
        assert at_toolkit.fsm is not None
        assert at_toolkit.pin_gen is not None
        
        # AND: The getter functions should return the created objects
        assert at_toolkit.get_at_controller() is not None
        assert at_toolkit.get_fsm() is not None
        
        # <<< FIX: Add assertions for the remaining getter return paths >>>
        assert at_toolkit.get_dut() is not None
        assert at_toolkit.get_session() is not None
        assert at_toolkit.get_pin_generator() is not None

        # AND: The constructors should have been called with the correct dependencies
        mock_session.assert_called_once_with(
            at_controller=mock_at_instance,
            dut_instance=mock_dut_instance
        )
        mock_fsm.assert_called_once_with(
            at_controller=mock_at_instance,
            session_instance=mock_session.return_value,
            dut_instance=mock_dut_instance
        )
        mock_pingenerator.assert_called_once_with(dut_model=mock_dut_instance)

    @patch('controllers.unified_controller.UnifiedController', side_effect=Exception("Hardware Failure"))
    @patch('automation_toolkit.os.makedirs')
    @patch('automation_toolkit.setup_logging')
    def test_initialization_fails_on_controller_error(self, mock_setup_logging, mock_makedirs, mock_unified_controller):
        """
        Tests that if the UnifiedController fails to initialize, all dependent
        objects are correctly NOT created.
        """
        # GIVEN: The UnifiedController class itself (at its source) is mocked to raise an exception.
        
        # WHEN: The automation_toolkit module is reloaded
        importlib.reload(at_toolkit)

        # THEN: The primary controller should be None because the constructor failed
        assert at_toolkit.at is None

        # AND: All dependent objects should also be None
        assert at_toolkit.dut is None
        assert at_toolkit.session is None
        assert at_toolkit.fsm is None
        assert at_toolkit.pin_gen is None

        # AND: The getter for 'at' should raise the expected error
        with pytest.raises(RuntimeError):
            at_toolkit.get_at_controller()

    def test_sys_path_is_added_if_missing(self):
        """
        Covers lines 13-14:
        Tests that the project root is added to sys.path if it's not already there.
        """
        # GIVEN: The project root path from the toolkit itself.
        project_root = at_toolkit.PROJECT_ROOT_FOR_GLOBAL
        original_sys_path = list(sys.path) # Keep a copy for restoration

        try:
            # AND: We temporarily remove the path from the ACTUAL sys.path list
            if project_root in sys.path:
                sys.path.remove(project_root)
            
            # Verify the precondition: the path is now missing.
            assert project_root not in sys.path
            
            # WHEN: We call the setup function directly
            at_toolkit._setup_sys_path()
            
            # THEN: The project root should now be the very first item in sys.path
            assert sys.path[0] == project_root
            
        finally:
            # FINALLY: Restore the original sys.path to not affect other tests.
            sys.path[:] = original_sys_path

    def test_sys_path_is_not_added_if_present(self):
        """
        Covers the case where the project root is already in sys.path.
        """
        # GIVEN: The project root is already in sys.path (and not at the start)
        project_root = at_toolkit.PROJECT_ROOT_FOR_GLOBAL
        original_sys_path = list(sys.path)
        
        # Ensure the path is present, but not at index 0
        if project_root in sys.path:
            sys.path.remove(project_root)
        sys.path.append(project_root)
        
        # Keep a copy of the path in this specific state
        path_before_call = list(sys.path)

        try:
            # WHEN: We call the setup function
            at_toolkit._setup_sys_path()
            
            # THEN: The sys.path should be completely unchanged, because the
            # 'if' condition in the function was false.
            assert sys.path == path_before_call
            
        finally:
            # FINALLY: Restore the original sys.path
            sys.path[:] = original_sys_path

    @patch('controllers.unified_controller.UnifiedController')
    @patch('automation_toolkit.os.makedirs')
    @patch('automation_toolkit.setup_logging') # Patch the successful setup_logging call
    def test_import_error_for_logging_setup(self, mock_setup_logging, mock_makedirs, mock_controller, monkeypatch):
        """
        Covers lines 27-31:
        Tests fallback logging if `controllers.logging` fails to import.
        """
        # GIVEN: We hide the 'controllers.logging' module so the import fails
        monkeypatch.setitem(sys.modules, 'controllers.logging', None)
    
        # WHEN: The toolkit is reloaded
        # THEN: It should not raise an error, but use basicConfig
        with patch('automation_toolkit.logging.basicConfig') as mock_basic_config:
            importlib.reload(at_toolkit)
            mock_basic_config.assert_called_once()

    @patch('controllers.unified_controller.UnifiedController')
    @patch('automation_toolkit.os.makedirs')
    @patch('automation_toolkit.setup_logging')
    def test_creation_failure_of_dut(self, mock_logging, mock_mkdirs, mock_controller):
        # Configure the 'dut' attribute on the mock 'at' instance to be a property
        # that raises an exception when accessed. This correctly tests the try/except block.
        from unittest.mock import PropertyMock
        type(mock_controller.return_value).dut = PropertyMock(side_effect=Exception("DUT Fail on access"))

        importlib.reload(at_toolkit)
        assert at_toolkit.at is not None
        assert at_toolkit.dut is None
        assert at_toolkit.session is None
        assert at_toolkit.fsm is None
        assert at_toolkit.pin_gen is None

    @patch('controllers.unified_controller.UnifiedController')
    @patch('controllers.finite_state_machine.DeviceUnderTest')
    @patch('controllers.finite_state_machine.TestSession', side_effect=Exception("Session Fail"))
    @patch('automation_toolkit.os.makedirs')
    @patch('automation_toolkit.setup_logging')
    def test_creation_failure_of_session(self, mock_logging, mock_mkdirs, mock_session, mock_dut, mock_controller):
        importlib.reload(at_toolkit)
        assert at_toolkit.at is not None
        assert at_toolkit.dut is not None
        assert at_toolkit.session is None
        assert at_toolkit.fsm is None

    @patch('controllers.unified_controller.UnifiedController')
    @patch('controllers.finite_state_machine.DeviceUnderTest')
    @patch('controllers.finite_state_machine.TestSession')
    @patch('controllers.finite_state_machine.ApricornDeviceFSM', side_effect=Exception("FSM Fail"))
    @patch('automation_toolkit.os.makedirs')
    @patch('automation_toolkit.setup_logging')
    def test_creation_failure_of_fsm(self, mock_logging, mock_mkdirs, mock_fsm, mock_session, mock_dut, mock_controller):
        importlib.reload(at_toolkit)
        assert at_toolkit.at is not None
        assert at_toolkit.dut is not None
        assert at_toolkit.session is not None
        assert at_toolkit.fsm is None

    @patch('controllers.unified_controller.UnifiedController')
    @patch('controllers.finite_state_machine.DeviceUnderTest')
    @patch('utils.pin_generator.PINGenerator', side_effect=Exception("PinGen Fail"))
    @patch('automation_toolkit.os.makedirs')
    @patch('automation_toolkit.setup_logging')
    def test_creation_failure_of_pin_gen(self, mock_logging, mock_mkdirs, mock_pingenerator, mock_dut, mock_controller):
        importlib.reload(at_toolkit)
        assert at_toolkit.at is not None
        assert at_toolkit.dut is not None
        assert at_toolkit.pin_gen is None

    @patch('automation_toolkit.atexit.register')
    @patch('controllers.unified_controller.UnifiedController')
    def test_cleanup_registration(self, mock_controller, mock_register, monkeypatch):
        monkeypatch.delitem(sys.modules, 'pytest', raising=False)
        importlib.reload(at_toolkit)
        mock_register.assert_called_once_with(at_toolkit._cleanup_global_at)

    @patch('automation_toolkit.atexit.register')
    def test_cleanup_registration_skipped_if_pytest_running(self, mock_register, monkeypatch):
        monkeypatch.setitem(sys.modules, 'pytest', MagicMock())
        with patch('controllers.unified_controller.UnifiedController'):
            importlib.reload(at_toolkit)
            mock_register.assert_not_called()

    def test_cleanup_global_at_function(self, caplog):
        """
        Covers lines 147-150:
        Tests the logic of the _cleanup_global_at function itself for all branches.
        """
        # --- Scenario 1: 'at' exists and has a 'close' method that works ---
        mock_at_closable = MagicMock()
        mock_at_closable.close = MagicMock()
        at_toolkit.at = mock_at_closable
        
        at_toolkit._cleanup_global_at()
        mock_at_closable.close.assert_called_once()

        # --- Scenario 2: 'at' exists but has no 'close' method ---
        mock_at_not_closable = object() # A plain object has no 'close' method
        at_toolkit.at = mock_at_not_closable
        # This should run without raising an error
        at_toolkit._cleanup_global_at()
        
        # --- Scenario 3: 'at' is None ---
        at_toolkit.at = None
        # This should run without raising an error
        at_toolkit._cleanup_global_at()

        # --- Scenario 4: 'at.close()' raises an exception ---
        mock_at_fails_to_close = MagicMock()
        # Configure the mock's close method to raise an error when called
        mock_at_fails_to_close.close.side_effect = IOError("Failed to close hardware")
        at_toolkit.at = mock_at_fails_to_close
        
        # WHEN the cleanup function is called while capturing logs
        with caplog.at_level(logging.ERROR, logger="GlobalATController"):
            at_toolkit._cleanup_global_at()

        # THEN the error should have been caught and logged
        assert "Error during global 'at' cleanup" in caplog.text
        assert "Failed to close hardware" in caplog.text
        
    @patch('automation_toolkit.atexit.register')
    @patch('controllers.unified_controller.UnifiedController', side_effect=Exception("AT Fail"))
    def test_cleanup_registration_skipped_on_at_failure(self, mock_controller, mock_register, monkeypatch):
        """
        Covers the 'else' block for atexit registration.
        Tests that cleanup is NOT registered and a warning is logged if the
        'at' controller fails to initialize.
        """
        # GIVEN: We are not running under pytest for this module's logic
        monkeypatch.delitem(sys.modules, 'pytest', raising=False)
        
        # AND: We create a string buffer to capture stdout
        f = io.StringIO()

        # WHEN: The toolkit module is reloaded, and we redirect all stdout to our buffer
        with redirect_stdout(f):
            importlib.reload(at_toolkit)

        # THEN: atexit.register should NOT have been called.
        mock_register.assert_not_called()
        
        # AND: The specific warning message should exist in the captured output string.
        output = f.getvalue()
        expected_warning = "Global 'at' instance is None; atexit cleanup for 'at' not registered."
        assert expected_warning in output