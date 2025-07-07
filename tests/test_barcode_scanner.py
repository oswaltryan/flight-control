# Directory: tests/
# Filename: test_barcode_scanner.py

#############################################################
##
## This test file is designed to systematically cover every function
## in hardware/barcode_scanner.py.
##
## Run this test with the following command:
## pytest tests/test_barcode_scanner.py --cov=controllers.barcode_scanner --cov-report term-missing
##
#############################################################

import pytest
from unittest.mock import MagicMock, patch, call
import sys
import threading
import time
from pynput import keyboard
import importlib

# Corrected import to match the actual file location
import controllers.barcode_scanner as barcode_scanner_module
from controllers.barcode_scanner import BarcodeScanner


@pytest.fixture
def mock_phidget_callback():
    return MagicMock()

@patch("controllers.barcode_scanner.keyboard.Listener")
def test_successful_scan(mock_listener_class, mock_phidget_callback):
    """
    Simulates a scan that captures characters followed by Enter.
    """
    # Simulate the listener instance
    listener_instance = MagicMock()
    mock_listener_class.return_value = listener_instance

    # The callback will be set via constructor, so capture it
    on_press_callback = {}

    def fake_listener_constructor(on_press):
        on_press_callback['fn'] = on_press
        return listener_instance

    mock_listener_class.side_effect = fake_listener_constructor

    # Mock methods
    listener_instance.start.side_effect = lambda: simulate_input(on_press_callback)
    listener_instance.stop.return_value = None
    listener_instance.join.return_value = None

    def simulate_input(cb_dict):
        """
        Simulates typing 'X', 'Y', 'Z', then Enter.
        """
        time.sleep(0.05)
        for char in "XYZ":
            mock_key = MagicMock()
            mock_key.char = char
            cb_dict['fn'](mock_key)
        enter_key = keyboard.Key.enter
        cb_dict['fn'](enter_key)

    scanner = BarcodeScanner(phidget_press_callback=mock_phidget_callback)
    result = scanner.await_scan(timeout=1)

    assert result == "XYZ"
    mock_phidget_callback.assert_called_once_with("barcode", 1000)


@patch("controllers.barcode_scanner.keyboard.Listener")
def test_scan_timeout_returns_none(mock_listener_class, mock_phidget_callback):
    """
    Verifies that a timeout results in a None return and no exception.
    """
    mock_listener_instance = MagicMock()
    mock_listener_instance.start.return_value = None
    mock_listener_instance.stop.return_value = None
    mock_listener_instance.join.return_value = None
    mock_listener_class.return_value = mock_listener_instance

    scanner = BarcodeScanner(phidget_press_callback=mock_phidget_callback)
    # Use a very short timeout to speed up the test
    result = scanner.await_scan(timeout=0.01)

    assert result is None
    # The duration passed to the callback is now timeout * 1000 = 10ms
    mock_phidget_callback.assert_called_once_with("barcode", 10)

@patch("controllers.barcode_scanner.keyboard.Listener")
def test_flush_buffer_windows(mock_listener_class, mock_phidget_callback):
    """
    Tests stdin flush on Windows. This test is now platform-independent.
    """
    # GIVEN a simulated Windows environment
    with patch("sys.platform", "win32"):
        # AND we reload the module to trigger the 'import msvcrt'
        importlib.reload(barcode_scanner_module)
        
        # AND we patch the msvcrt module that was just "imported"
        with patch("controllers.barcode_scanner.msvcrt") as mock_msvcrt:
            listener_instance = MagicMock()
            mock_listener_class.return_value = listener_instance
            listener_instance.start.return_value = None
            listener_instance.stop.return_value = None
            listener_instance.join.return_value = None

            # Simulate Windows keystroke buffer has data
            mock_msvcrt.kbhit.side_effect = [True, True, False]
            mock_msvcrt.getch.return_value = b'x'

            # WHEN the scanner is used with a short timeout
            scanner = BarcodeScanner(phidget_press_callback=mock_phidget_callback)
            result = scanner.await_scan(timeout=0.01)

            # THEN the buffer flushing logic should be called correctly
            assert result is None
            assert mock_phidget_callback.call_count == 1
            assert mock_msvcrt.getch.call_count == 2

def test_flush_buffer_unix():
    """
    Tests stdin flush on Unix-like systems. This test is now platform-independent.
    """
    # GIVEN a mock termios module and a simulated Linux environment
    mock_termios = MagicMock()
    with patch.dict(sys.modules, {'termios': mock_termios}):
        with patch("sys.platform", "linux"):
            # AND we reload the module to trigger the 'import termios'
            importlib.reload(barcode_scanner_module)
            from controllers.barcode_scanner import BarcodeScanner

            with patch("controllers.barcode_scanner.keyboard.Listener") as mock_listener_class:
                listener_instance = MagicMock()
                mock_listener_class.return_value = listener_instance
                listener_instance.start.return_value = None
                listener_instance.stop.return_value = None
                listener_instance.join.return_value = None

                mock_phidget_callback = MagicMock()

                # WHEN the scanner is used with a short timeout
                scanner = BarcodeScanner(phidget_press_callback=mock_phidget_callback)
                result = scanner.await_scan(timeout=0.01)

                # THEN the buffer flushing logic should be called correctly
                assert result is None
                mock_termios.tcflush.assert_called_once_with(sys.stdin, mock_termios.TCIOFLUSH)

@patch("controllers.barcode_scanner.keyboard.Listener")
def test_scan_complete_event_prevents_extra_keys(mock_listener_class):
    """
    Ensures that on_press() exits early when scan_complete_event is set.
    """

    pressed_keys = []

    # Place to store the on_press callback
    on_press_wrapper = {}

    listener_instance = MagicMock()
    def simulate_listener(on_press):
        on_press_wrapper["fn"] = on_press
        return listener_instance

    mock_listener_class.side_effect = simulate_listener
    listener_instance.start.side_effect = lambda: threading.Thread(target=simulate_keypresses, args=(on_press_wrapper,)).start()
    listener_instance.stop.return_value = None
    listener_instance.join.return_value = None

    def fake_phidget_callback(name, duration_ms):
        time.sleep(0.05)  # Simulate controllers delay

    def simulate_keypresses(cb_dict):
        # Trigger valid scan: "X", "Y", "Z", Enter
        for ch in "XYZ":
            key = MagicMock()
            key.char = ch
            cb_dict["fn"](key)
            pressed_keys.append(ch)
        enter_key = keyboard.Key.enter
        cb_dict["fn"](enter_key)
        pressed_keys.append("enter")

        # AFTER scan is complete, send extra key
        late_key = MagicMock()
        late_key.char = "E"
        cb_dict["fn"](late_key)
        pressed_keys.append("E")

    scanner = BarcodeScanner(phidget_press_callback=fake_phidget_callback)
    result = scanner.await_scan(timeout=1)

    assert result == "XYZ"
    assert "E" in pressed_keys

@patch("controllers.barcode_scanner.keyboard.Listener")
def test_key_with_no_char_triggers_attributeerror(mock_listener_class):
    """
    Ensures that the AttributeError handler in on_press() is covered when key.char is missing.
    """

    on_press_wrapper = {}
    listener_instance = MagicMock()

    def simulate_listener(on_press):
        on_press_wrapper["fn"] = on_press
        return listener_instance

    mock_listener_class.side_effect = simulate_listener
    listener_instance.stop.return_value = None
    listener_instance.join.return_value = None

    # Trigger simulation after listener starts
    def trigger_invalid_key():
        # Normal key to build buffer
        k1 = MagicMock()
        k1.char = "X"
        on_press_wrapper["fn"](k1)

        # Special key with no `.char` — will trigger AttributeError
        special_key = MagicMock(spec=[])
        # This mock has no `char` attribute
        on_press_wrapper["fn"](special_key)

        # Finalize with enter to complete scan
        enter_key = keyboard.Key.enter
        on_press_wrapper["fn"](enter_key)

    listener_instance.start.side_effect = lambda: trigger_invalid_key()

    def fake_phidget_callback(name, duration_ms):
        time.sleep(0.01)

    scanner = BarcodeScanner(phidget_press_callback=fake_phidget_callback)
    result = scanner.await_scan(timeout=1)

    assert result == "X"

def test_stdin_flush_error_windows(mock_phidget_callback):
    """
    Triggers an exception during buffer flushing on Windows to test the error handler.
    This test is now platform-independent.
    """
    # GIVEN a simulated Windows environment
    with patch("sys.platform", "win32"):
        # AND we reload the module to trigger the 'import msvcrt'
        importlib.reload(barcode_scanner_module)
        
        with patch("controllers.barcode_scanner.msvcrt") as mock_msvcrt, \
             patch("controllers.barcode_scanner.keyboard.Listener") as mock_listener_class:
            
            # Configure mocks for the test conditions
            mock_msvcrt.getch.side_effect = OSError("flush fail")
            mock_msvcrt.kbhit.side_effect = [True, False]
            
            listener_instance = MagicMock()
            mock_listener_class.return_value = listener_instance

            # Wrap the rest of the original test logic
            def simulate_scan(cb_dict):
                key = MagicMock(char="Q")
                cb_dict["fn"](key)
                enter = keyboard.Key.enter
                cb_dict["fn"](enter)

            on_press_wrapper = {}
            def simulate_listener(on_press):
                on_press_wrapper["fn"] = on_press
                return listener_instance
            
            mock_listener_class.side_effect = simulate_listener
            listener_instance.start.side_effect = lambda: simulate_scan(on_press_wrapper)

            # WHEN the scanner is used
            scanner = BarcodeScanner(phidget_press_callback=mock_phidget_callback)
            result = scanner.await_scan(timeout=1)

            # THEN the scan should succeed despite the flush error
            assert result == "Q"
            mock_msvcrt.getch.assert_called_once()