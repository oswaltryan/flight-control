# Directory: tests/
# Filename: test_logging.py

#############################################################
##
## This test file is designed to systematically cover every function
## in controllers/test_logging.py.
##
## Run this test with the following command:
## pytest tests/test_logging.py --cov=controllers.logging_config --cov-report term-missing
##
#############################################################

import pytest
import logging
import os
import sys
from unittest.mock import patch, MagicMock

# Import the function to be tested
from controllers.logging import setup_logging

class TestLoggingConfig:
    """Tests for the setup_logging function in controllers/logging.py"""

    def test_setup_logging_file_handler_exception_with_console(self):
        """
        Covers line 79:
        Tests that an error is logged to the console logger if creating the
        file handler fails.
        """
        # GIVEN: We patch getLogger to control the logger instance
        # AND patch FileHandler to raise an exception.
        with patch('controllers.logging.logging.getLogger') as mock_get_logger, \
             patch('controllers.logging.logging.FileHandler', side_effect=OSError("Permission Denied")):
            
            # The logger that the function will use
            mock_logger_instance = MagicMock()
            mock_get_logger.return_value = mock_logger_instance

            # WHEN: setup_logging is called with a file path.
            setup_logging(log_file_path="/unwritable/path/test.log")

            # THEN: The logger's error method should have been called.
            mock_logger_instance.error.assert_called_once()
            call_args, call_kwargs = mock_logger_instance.error.call_args
            assert "Error setting up file logging" in call_args[0]
            assert "Permission Denied" in call_args[0]
            assert call_kwargs.get('exc_info') is True

    def test_setup_logging_file_handler_exception_no_console(self, capsys):
        """
        Covers line 83:
        Tests that an error is printed to stderr if creating the file handler
        fails AND console logging is disabled.
        """
        # GIVEN: FileHandler will fail, and console logging is off.
        with patch('controllers.logging.logging.FileHandler', side_effect=OSError("Permission Denied")):
            # WHEN: setup_logging is called.
            setup_logging(log_to_console=False, log_file_path="/unwritable/path/test.log")
            
            # THEN: The error message should be printed to stderr.
            captured = capsys.readouterr()
            assert "Error setting up file logging" in captured.err
            assert "Permission Denied" in captured.err

    def test_setup_logging_invalid_level_with_console(self):
        """
        Covers lines 94, 96:
        Tests that a warning is logged if a logger level override is invalid.
        """
        # GIVEN: An invalid log level override and a mocked logger.
        invalid_overrides = {'some_logger': 'NOT_A_LEVEL'}
        with patch('controllers.logging.logging.getLogger') as mock_get_logger:
            mock_logger_instance = MagicMock()
            mock_get_logger.return_value = mock_logger_instance
            
            # WHEN: setup_logging is called with the invalid override.
            setup_logging(log_level_overrides=invalid_overrides)
        
            # THEN: A warning message should have been logged.
            mock_logger_instance.warning.assert_called_once()
            call_args, _ = mock_logger_instance.warning.call_args
            assert "Could not set log level for 'some_logger'" in call_args[0]
            assert "NOT_A_LEVEL" in call_args[0]

    def test_setup_logging_invalid_level_no_console(self, capsys):
        """
        Covers lines 97-101:
        Tests that a warning is printed to stderr for an invalid logger level
        when console logging is disabled.
        """
        # GIVEN: An invalid override and console logging is off.
        invalid_overrides = {'another_logger': None} # None is also invalid
        
        # WHEN: setup_logging is called.
        setup_logging(log_level_overrides=invalid_overrides, log_to_console=False)
        
        # THEN: The warning should be printed to stderr.
        captured = capsys.readouterr()
        assert "Could not set log level for 'another_logger'" in captured.err

    def test_setup_logging_creates_directory(self):
        """
        Covers lines 69-70:
        Tests that os.makedirs is called if the log directory does not exist.
        """
        # GIVEN: We will patch os.path.exists to return False, and os.makedirs.
        with patch('controllers.logging.os.path.exists') as mock_exists, \
             patch('controllers.logging.os.makedirs') as mock_makedirs:
            
            mock_exists.return_value = False
            log_file = os.path.join("non_existent_dir", "test.log")
            
            # WHEN: setup_logging is called with a path in a non-existent directory.
            setup_logging(log_file_path=log_file)

            # THEN: os.path.exists should have been checked.
            mock_exists.assert_called_once_with("non_existent_dir")
            
            # AND: os.makedirs should have been called to create it.
            mock_makedirs.assert_called_once_with("non_existent_dir")

    def test_setup_logging_file_logging_success(self):
        """
        Covers lines 72-73:
        Tests the successful creation and addition of a file handler.
        """
        # GIVEN: We patch the necessary file system and logging components
        with patch('controllers.logging.os.path.exists') as mock_exists, \
             patch('controllers.logging.os.makedirs') as mock_makedirs, \
             patch('controllers.logging.logging.FileHandler') as mock_file_handler_constructor, \
             patch('controllers.logging.logging.getLogger') as mock_get_logger:

            mock_exists.return_value = True  # Simulate directory already exists
            mock_file_handler_instance = MagicMock()
            mock_file_handler_constructor.return_value = mock_file_handler_instance
            mock_root_logger = MagicMock()
            mock_get_logger.return_value = mock_root_logger

            log_file = "logs/test.log"

            # WHEN: setup_logging is called with file logging enabled
            setup_logging(log_file_path=log_file)

            # THEN: The file handler should be configured and added
            mock_file_handler_constructor.assert_called_once_with(log_file, mode='a', encoding='utf-8')
            
            # Check that setFormatter was called on the created handler instance
            mock_file_handler_instance.setFormatter.assert_called_once()
            
            # Check that addHandler was called on the root logger with the handler instance
            # Use assert_any_call because the console handler might also be added.
            mock_root_logger.addHandler.assert_any_call(mock_file_handler_instance)
            
            # And makedirs should not have been called since exists() returned True
            mock_makedirs.assert_not_called()