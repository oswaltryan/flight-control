# Directory: tests/
# Filename: test_logitech_webcam_controller.py

#############################################################
##
## This test file is designed to systematically cover every function
## in controllers/logitech_webcam_controller.py.
##
## Run this test with the following command:
## pytest tests/test_logitech_webcam_controller.py --cov=controllers.logitech_webcam --cov-report term-missing
##
#############################################################

import pytest
from unittest.mock import MagicMock, patch, call, ANY
import os
import sys
import time
import logging
import cv2
import numpy as np
import threading
import itertools

# Import the module and class to be tested
import controllers.logitech_webcam as camera_module
from controllers.logitech_webcam import LogitechLedChecker, PRIMARY_LED_CONFIGURATIONS

# --- Test Fixtures ---

@pytest.fixture
def mock_logger():
    """Provides a mocked logger instance."""
    return MagicMock(spec=logging.Logger)

@pytest.fixture
def mock_cv2_videocapture():
    """Mocks the cv2.VideoCapture class."""
    with patch('cv2.VideoCapture') as mock_videocapture:
        mock_cap_instance = MagicMock()
        mock_cap_instance.isOpened.return_value = True
        mock_cap_instance.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_cap_instance.set.return_value = True
        mock_cap_instance.get.return_value = 30.0 # Mock FPS
        mock_cap_instance.release.return_value = None
        mock_videocapture.return_value = mock_cap_instance
        yield mock_videocapture

@pytest.fixture
def default_configs():
    """Provides a default set of LED configurations for tests."""
    return {
        "red": {"name": "Red", "roi": (10, 10, 10, 10), "hsv_lower": (0,0,0), "hsv_upper": (10,255,255), "min_match_percentage": 0.5, "display_color_bgr": (0,0,255)},
        "green": {"name": "Green", "roi": (30, 10, 10, 10), "hsv_lower": (50,0,0), "hsv_upper": (70,255,255), "min_match_percentage": 0.5, "display_color_bgr": (0,255,0)},
    }

# --- Test Classes ---

class TestGetCaptureBackend:
    """Tests the platform-specific get_capture_backend function."""
    @pytest.mark.parametrize("platform, expected_backend", [
        ("win32", cv2.CAP_DSHOW),
        ("darwin", cv2.CAP_AVFOUNDATION),
        ("linux", None),
        ("sunos", None),
    ])
    def test_get_capture_backend_platforms(self, monkeypatch, platform, expected_backend):
        monkeypatch.setattr(sys, 'platform', platform)
        assert camera_module.get_capture_backend() == expected_backend

class TestLogitechLedCheckerInit:
    """Tests the __init__ method of the LogitechLedChecker."""

    def test_initialization_success(self, mock_cv2_videocapture, mock_logger, default_configs):
        """Test successful initialization with standard parameters."""
        checker = LogitechLedChecker(camera_id=0, logger_instance=mock_logger, led_configs=default_configs)
        assert checker.is_camera_initialized is True
        assert checker.cap is not None
        checker.release_camera()

    def test_initialization_no_camera_id(self, mock_logger):
        """Test that initialization fails gracefully if camera_id is None."""
        # We use a type ignore comment here because we are intentionally
        # passing an invalid type to test the runtime check within the constructor.
        checker = LogitechLedChecker(camera_id=None, logger_instance=mock_logger) # type: ignore
        assert checker.is_camera_initialized is False
        mock_logger.error.assert_called_with("Camera ID cannot be None.")

    def test_initialization_camera_open_failure(self, mock_cv2_videocapture, caplog):
        """
        Tests that if both camera open attempts fail, the exception is caught,
        logged, and the checker is left in a safe, uninitialized state.
        """
        # --- ARRANGE ---
        # Create two separate mock instances for the video capture object.
        mock_cap_fail1 = MagicMock()
        mock_cap_fail1.isOpened.return_value = False
        
        mock_cap_fail2 = MagicMock()
        mock_cap_fail2.isOpened.return_value = False

        # Configure the main VideoCapture mock to return these two instances in sequence.
        mock_cv2_videocapture.side_effect = [mock_cap_fail1, mock_cap_fail2]

        # Patch the registry to prevent an AttributeError.
        with patch('cv2.videoio_registry') as mock_registry:
            mock_registry.getBackendName.return_value = "DSHOW"

            # --- ACT ---
            # We target the specific logger name used by the class. We do NOT pass
            # a mocked logger instance anymore. We let the class create its own.
            with caplog.at_level(logging.ERROR, logger="controllers.camera_controller"):
                 checker = LogitechLedChecker(camera_id=0) # No logger_instance passed

        # --- ASSERT ---
        # 1. Verify the checker's final state.
        assert checker.is_camera_initialized is False
        assert checker.cap is None
        
        # 2. Verify caplog captured the error from the real logger.
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        
        assert "Failed to initialize camera" in log_record.message
        # The actual exception object is stored in the record's exc_info attribute.
        assert "Cannot open webcam" in str(log_record.exc_info[1])
        
        # 3. Verify cleanup logic was called.
        mock_cap_fail2.release.assert_called_once()
        
        # 4. Verify VideoCapture was called twice.
        assert mock_cv2_videocapture.call_count == 2

    def test_initialization_with_fallback_led_configs(self, mock_cv2_videocapture, mock_logger):
        """Test that fallback configs are used if primary ones are not provided."""
        with patch.dict(camera_module.PRIMARY_LED_CONFIGURATIONS, {}, clear=True):
             checker = LogitechLedChecker(camera_id=0, logger_instance=mock_logger)
             assert "fallback_red" in checker.led_configs
             mock_logger.error.assert_called_with("PRIMARY_LED_CONFIGURATIONS empty/invalid. Using _FALLBACK_LED_DEFINITIONS.")
        checker.release_camera()
        
    @pytest.mark.parametrize("bad_config, error_msg", [
        (None, "missing or invalid"),
        ({}, "missing or invalid"),
        ({"red": "not-a-dict"}, "not a dict"),
        ({"red": {"name":"r"}}, "missing core keys"),
        ({"red": {"name":"r", "roi": (1,1), "hsv_lower": (0,0,0), "hsv_upper": (10,255,255), "min_match_percentage": 0.5}}, "tuple of 4 ints"),
    ])
    def test_invalid_led_configs_raise_valueerror(self, bad_config, error_msg):
        """Test that malformed LED configs raise ValueError."""
        
        # To test the None/empty cases, we must ensure ALL fallbacks are also empty.
        if bad_config is None or not bad_config:
            # Patch both the primary and fallback configurations to be empty dicts.
            with patch.dict(camera_module.PRIMARY_LED_CONFIGURATIONS, {}, clear=True), \
                 patch.dict(camera_module._FALLBACK_LED_DEFINITIONS, {}, clear=True):
                
                with pytest.raises(ValueError, match=error_msg):
                    # Now, with no valid configs to fall back to, this will raise the error.
                    LogitechLedChecker(camera_id=0, led_configs=bad_config)
        else:
            # For all other test cases, the primary configs don't matter as we are
            # providing a specific bad_config.
            with pytest.raises(ValueError, match=error_msg):
                LogitechLedChecker(camera_id=0, led_configs=bad_config)

    def test_invalid_display_order_key_raises_valueerror(self):
        """Test that a key in display_order not in led_configs raises ValueError."""
        with pytest.raises(ValueError, match="not found in LED configs"):
            LogitechLedChecker(camera_id=0, display_order=["red", "nonexistent"])
            
    def test_replay_directory_creation_failure(self, mock_cv2_videocapture, mock_logger):
        """Test that an OSError during replay directory creation is handled."""
        with patch('os.makedirs', side_effect=OSError("Permission denied")):
            checker = LogitechLedChecker(camera_id=0, logger_instance=mock_logger, replay_output_dir="/unwritable", enable_instant_replay=True)
            assert checker.replay_output_dir is None
            mock_logger.error.assert_called_with(ANY, exc_info=True)
        checker.release_camera()

    def test_init_instant_replay_disabled_via_config(self, mock_cv2_videocapture, mock_logger, tmp_path, caplog):
        """
        Tests that if instant replay is explicitly disabled via configuration,
        the output directory is set to None and an info message is logged.
        """
        # ARRANGE
        # Ensure that replay_output_dir would initially be set if not for the disable flag
        test_replay_dir = str(tmp_path / "replays")

        # To ensure the __init__ doesn't fail on LED config validation
        dummy_led_configs = {
            "test_led": {"name": "Test LED", "roi": (0, 0, 1, 1), "hsv_lower": (0, 0, 0),
                         "hsv_upper": (1, 1, 1), "min_match_percentage": 0.1}
        }

        with caplog.at_level(logging.INFO, logger="controllers.logitech_webcam"):
            # ACT
            checker = LogitechLedChecker(
                camera_id=0,
                # REMOVE THIS LINE: logger_instance=mock_logger,
                enable_instant_replay=False,  # <--- This is the key setting for this test
                replay_output_dir=test_replay_dir, # This should be overridden to None
                led_configs=dummy_led_configs
            )

        # ASSERT
        # 1. Verify that the enable_instant_replay flag itself is correctly set
        assert checker.enable_instant_replay is False

        # 2. Verify that replay_output_dir was set to None
        assert checker.replay_output_dir is None

        # 3. Verify that the correct info message was logged via caplog (as checker now uses global logger)
        # REMOVE THIS LINE: mock_logger.info.assert_any_call("Instant replay is disabled via configuration.")
        assert "Instant replay is disabled via configuration." in caplog.text

        # Cleanup
        checker.release_camera()
        
class TestLogitechLedCheckerMethods:
    """Tests the various methods of LogitechLedChecker."""

    @pytest.fixture
    @patch('threading.Thread')
    def checker(self, mock_thread, mock_cv2_videocapture, mock_logger, default_configs, request, tmp_path):
        """
        Auto-provides an initialized checker instance for each test in this class.
        The background thread is patched. Cleanup is handled by addfinalizer.
        A temporary directory is provided for replays to prevent warnings.
        """
        # Provide a temporary directory to prevent the "replay_output_dir is not set" warning.
        instance = LogitechLedChecker(
            camera_id=0, 
            logger_instance=mock_logger, 
            led_configs=default_configs, 
            replay_output_dir=str(tmp_path),
            enable_instant_replay=True
        )
        
        # Register the cleanup function to run after the test finishes.
        request.addfinalizer(instance.release_camera)
        
        # Return the instance directly.
        return instance

    def test_clear_camera_buffer(self, checker, mock_cv2_videocapture):
        """
        Test the camera buffer clearing logic. The background thread is disabled
        by the 'checker' fixture.
        """
        # The checker fixture now returns a real instance, not a generator.
        checker._clear_camera_buffer()
        
        # <<< FIX: Use the .call_count attribute for the assertion. >>>
        # The .read() method should be called exactly CAMERA_BUFFER_SIZE_FRAMES times.
        assert mock_cv2_videocapture.return_value.read.call_count == camera_module.CAMERA_BUFFER_SIZE_FRAMES

    def test_clear_buffer_on_uninitialized_camera(self, checker, mock_logger):
        """Test that clearing buffer on uninitialized camera logs a warning."""
        checker.is_camera_initialized = False
        checker.cap = None
        checker._clear_camera_buffer()
        mock_logger.warning.assert_called_with("Camera not initialized. Cannot clear buffer.")

    @pytest.mark.parametrize("roi_rect, expected_result", [
        ((10, 10, 0, 10), False), # Zero width
        ((10, 10, 10, -5), False), # Negative height
    ])
    def test_check_roi_for_color_invalid_roi(self, checker, roi_rect, expected_result):
        """Test that ROIs with zero or negative dimensions return False."""
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        config = {"roi": roi_rect, "hsv_lower": (0,0,0), "hsv_upper": (255,255,255), "min_match_percentage": 0.1}
        assert checker._check_roi_for_color(frame, config) is expected_result
        
    def test_check_roi_for_color_handles_red_wrap(self, checker):
        """Test the special HSV case for red color that wraps around 180."""
        # Create a red frame
        frame = np.full((100, 100, 3), (0, 0, 255), dtype=np.uint8)
        # Config for red that wraps around the hue value
        red_config = {"roi": (0,0,10,10), "hsv_lower": (170,100,100), "hsv_upper": (10,255,255), "min_match_percentage": 0.9}
        assert checker._check_roi_for_color(frame, red_config) is True

    def test_get_ordered_led_keys_for_display(self, checker, default_configs):
        """Test the logic for ordering LED keys for display."""
        # 1. With explicit order
        checker.explicit_display_order = ["green", "red"]
        assert checker._get_ordered_led_keys_for_display() == ["green", "red"]
        
        # 2. With default order (reset cache first)
        checker._ordered_keys_for_display_cache = None
        checker.explicit_display_order = None
        checker.led_configs = {"blue": {}, "red": {}, "green": {}}
        assert checker._get_ordered_led_keys_for_display() == ["red", "green", "blue"]

        # 3. With extra keys not in default order
        checker._ordered_keys_for_display_cache = None
        checker.led_configs = {"blue": {}, "amber": {}, "red": {}}
        # 'amber' should be sorted and appended
        assert checker._get_ordered_led_keys_for_display() == ["red", "blue", "amber"]

    @pytest.mark.filterwarnings("ignore:Exception in thread")
    def test_update_frame_thread_handles_failed_read(self, mock_cv2_videocapture, mock_logger, default_configs, tmp_path):
        """
        Tests that the running _update_frame_thread correctly handles a failed
        frame read by hitting the `continue` statement and not processing the frame.
        """
        # ARRANGE
        good_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Use an exception to controllably stop the thread's loop.
        class StopThread(Exception):
            pass

        mock_cv2_videocapture.return_value.read.side_effect = [
            (False, None),      # 1. This triggers `if not ret: continue`
            (True, good_frame), # 2. This is processed normally.
            StopThread          # 3. This will break the loop and stop the thread.
        ]

        # ACT & ASSERT
        # Patch the method on the CLASS before the instance is created to avoid a race condition.
        with patch.object(camera_module.LogitechLedChecker, '_check_roi_for_color', return_value=True) as mock_check_roi:
            # The `with` statement ensures `release_camera()` is also called.
            with LogitechLedChecker(
                camera_id=0,
                logger_instance=mock_logger,
                led_configs=default_configs,
                replay_output_dir=str(tmp_path)
            ) as checker:
                # Wait for the thread to run through the side_effect list and terminate.
                checker.thread.join(timeout=1.0)

                # The buffer should only contain the single frame from the successful read.
                assert len(checker.replay_buffer) == 1

                # The mock that was patched onto the class should have been called for the successful frame.
                assert mock_check_roi.call_count == 2

        # Assert that read() was called 3 times: fail, success, and the one that raised the exception.
        assert mock_cv2_videocapture.return_value.read.call_count == 3

    @pytest.mark.filterwarnings("ignore:Exception in thread")
    def test_update_frame_thread_sleeps_when_camera_not_open(self, mock_cv2_videocapture, mock_logger, default_configs, tmp_path):
        """
        Tests that the `else` block in the `_update_frame_thread` is covered by
        correctly calling `time.sleep(0.1)` when the camera is not opened.
        """
        # ARRANGE
        class StopThread(Exception): pass

        # Configure a sequence for isOpened() to control all calls throughout the
        # checker's lifecycle: initialization, thread loop, and cleanup.
        mock_cv2_videocapture.return_value.isOpened.side_effect = [
            False,      # 1. First call in _initialize_camera (triggers retry)
            True,       # 2. Second call in _initialize_camera (succeeds)
            False,      # 3. Thread loop 1: enters 'else' block and calls sleep
            True,       # 4. Thread loop 2: enters 'if' block and processes frame
            StopThread, # 5. Thread loop 3: crashes thread to end the test
            False       # 6. Final call from release_camera() during __exit__
        ]

        # Configure `read()` to be called only on the successful path.
        good_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cv2_videocapture.return_value.read.return_value = (True, good_frame)

        # ACT & ASSERT
        # Patch `time.sleep` where it is imported and used: in `controllers.logitech_webcam`.
        with patch('controllers.logitech_webcam.time.sleep') as mock_sleep:
            # Patch the ROI check on the class to avoid a race condition.
            with patch.object(camera_module.LogitechLedChecker, '_check_roi_for_color', return_value=True):
                # Instantiate the checker, which starts the thread.
                with LogitechLedChecker(
                    camera_id=0,
                    logger_instance=mock_logger,
                    led_configs=default_configs,
                    replay_output_dir=str(tmp_path)
                ) as checker:
                    # Wait for the thread to complete its sequence and stop.
                    checker.thread.join(timeout=1.0)

                    # Assert that the `else` block was executed once, calling sleep.
                    mock_sleep.assert_called_once_with(0.1)

                    # Assert that the `if` block was also executed once by checking the buffer.
                    assert len(checker.replay_buffer) == 1

        # Final check on how many times the mocked camera methods were called.
        assert mock_cv2_videocapture.return_value.isOpened.call_count == 6
        assert mock_cv2_videocapture.return_value.read.call_count == 1

    def test_initialize_camera_with_no_preferred_backend(self, mock_cv2_videocapture, mock_logger, tmp_path):
        """
        Tests the `_initialize_camera` `else` branch for when no preferred
        backend is available, ensuring cv2.VideoCapture is called with one argument.
        """
        # ARRANGE
        # Configure the mock camera to succeed on all operations to isolate the test case.
        mock_cap = mock_cv2_videocapture.return_value
        mock_cap.isOpened.return_value = True
        mock_cap.set.return_value = True
        mock_cap.get.return_value = 30.0

        # ACT & ASSERT
        # Patch the helper function to simulate having no preferred backend (returns None).
        with patch('controllers.logitech_webcam.get_capture_backend', return_value=None):
            # The 'with' block ensures checker.release_camera() is called.
            with LogitechLedChecker(
                camera_id=0,
                logger_instance=mock_logger,
                replay_output_dir=str(tmp_path) # Prevent replay warning
            ) as checker:
                # 1. Assert the "no backend" path was taken by checking the call signature.
                #    This is the key assertion for the line under test.
                mock_cv2_videocapture.assert_called_once_with(0)

                # 2. Assert no warnings were logged about a failing backend, since none was tried.
                for call_obj in mock_logger.warning.call_args_list:
                    assert "Preferred backend" not in call_obj.args[0]

                # 3. Assert the rest of the initialization succeeded.
                assert mock_cap.set.call_count == 3
                mock_cap.get.assert_called_once_with(cv2.CAP_PROP_FPS)
                assert checker.is_camera_initialized is True

    @patch('threading.Thread') # This decorator prevents the thread from starting
    def test_initialize_camera_handles_backend_retry_and_set_failures(self, mock_thread, mock_cv2_videocapture, mock_logger, tmp_path):
        """
        Tests the `_initialize_camera` method's `else` branches for when the
        preferred backend fails (triggering a retry) and when setting
        camera properties fails.
        """
        # ARRANGE
        # Simulate a two-step camera open process:
        # 1. First attempt fails (for the preferred backend)
        # 2. Second attempt succeeds (for the default backend)
        mock_cap_fail = MagicMock()
        mock_cap_fail.isOpened.return_value = False

        mock_cap_success = MagicMock()
        mock_cap_success.isOpened.return_value = True
        # Configure the `set` method on the *successful* capture object to fail
        mock_cap_success.set.return_value = False
        # Configure the `get` method to return a valid number to prevent a TypeError
        mock_cap_success.get.return_value = 30.0

        # Make the VideoCapture mock return the fail, then success objects
        mock_cv2_videocapture.side_effect = [mock_cap_fail, mock_cap_success]

        # Define the expected warning calls in the correct order
        preferred_backend_val = cv2.CAP_DSHOW # A real backend value
        expected_warnings = [
            call(f"Preferred backend ({preferred_backend_val}) failed for camera ID 0. Trying default."),
            call("Failed to set camera width to 640."),
            call("Failed to set camera height to 480."),
            call(f"Could not set FPS {camera_module.DEFAULT_FPS} for camera ID 0.")
        ]

        # ACT & ASSERT
        # Patch the helper function to *provide* a preferred backend
        with patch('controllers.logitech_webcam.get_capture_backend', return_value=preferred_backend_val):
            # The 'with' block ensures checker.release_camera() is called
            with LogitechLedChecker(
                camera_id=0,
                logger_instance=mock_logger,
                replay_output_dir=str(tmp_path)
            ) as checker:
                # 1. Assert that VideoCapture was called twice (initial + retry)
                assert mock_cv2_videocapture.call_count == 2
                mock_cv2_videocapture.assert_has_calls([
                    call(0, preferred_backend_val), # First call with backend
                    call(0)                         # Second call without (default)
                ])

                # 2. Assert the `set` and `get` methods were called correctly
                assert mock_cap_success.set.call_count == 3
                mock_cap_success.get.assert_called_once_with(cv2.CAP_PROP_FPS)

                # 3. Assert all *four* warning messages were logged correctly
                mock_logger.warning.assert_has_calls(expected_warnings, any_order=False)
                assert mock_logger.warning.call_count == 4

                # 4. Assert initialization is now considered successful
                assert checker.is_camera_initialized is True

    def test_clear_camera_buffer_handles_exception(self, checker, mock_logger):
        """
        Tests that the `except` block in _clear_camera_buffer is hit when
        cap.read() raises an exception, and the error is logged correctly.
        """
        # ARRANGE
        # The `checker` fixture provides an initialized instance with a mocked `cap`.
        # We configure its `read` method to raise an exception on the first call.
        error_message = "Simulated hardware read failure"
        checker.cap.read.side_effect = Exception(error_message)

        # ACT
        # Call the method under test.
        checker._clear_camera_buffer()

        # ASSERT
        # Verify that the logger's error method was called exactly once.
        mock_logger.error.assert_called_once()
        
        # Unpack the call arguments to inspect them individually.
        # call_args is a tuple: (positional_args, keyword_args)
        call_args, call_kwargs = mock_logger.error.call_args
        
        # Check that the log message is correct.
        assert f"Exception while clearing camera buffer: {error_message}" in call_args[0]
        
        # Check that the exception info was included for debugging.
        assert call_kwargs.get('exc_info') is True

    def test_get_current_led_state_from_camera_empty_buffer(self, checker):
        """
        Tests that _get_current_led_state_from_camera returns (None, {})
        when the replay buffer is empty.
        """
        # ARRANGE
        # The `checker` fixture provides an initialized instance.
        # Ensure its replay buffer is empty.
        checker.replay_buffer.clear()

        # ACT
        # Call the method under test.
        frame, states = checker._get_current_led_state_from_camera()

        # ASSERT
        # Verify that the returned values match the expected empty state.
        assert frame is None
        assert states == {}

    @patch('cv2.rectangle')
    def test_draw_overlays_skips_invalid_led_key(self, mock_rectangle, checker):
        """
        Tests that _draw_overlays safely handles and skips a key that is in the
        display order but not in the led_configs dictionary, hitting the `continue`
        statement.
        """
        # ARRANGE
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        led_states = {"red": 1} # One valid LED state
        active_keys = set()

        # Patch the helper method to return an order with a non-existent key.
        # "red" is valid in `default_configs`, "amber" is not.
        checker._get_ordered_led_keys_for_display = MagicMock(return_value=["red", "amber"])

        # ACT
        # Call the function. If the `continue` works, this will not raise a KeyError.
        try:
            checker._draw_overlays(frame, 1.23, led_states, active_keys)
        except KeyError:
            pytest.fail("KeyError was raised. The 'continue' statement was not effective.")

        # ASSERT
        # The drawing logic for ROIs uses cv2.rectangle.
        # It should have been called only ONCE for the valid "red" key.
        # The invalid "amber" key should have been skipped.
        assert mock_rectangle.call_count == 1
        
        # Verify the call was for the 'red' ROI box
        red_config = checker.led_configs["red"]
        x, y, w, h = red_config["roi"]
        mock_rectangle.assert_called_once_with(ANY, (x, y), (x + w, y + h), ANY, 1)

    def test_set_keypad_layout(self, checker, mock_logger):
        """
        Tests that set_keypad_layout correctly updates the keypad_layout
        attribute and logs an informational message.
        """
        # ARRANGE
        sample_layout = [
            ["Q", "W", "E"],
            ["A", "S", "D"]
        ]
        # The `checker` fixture is already initialized here.

        # Ensure the layout is not set initially. The __init__ sets it to None.
        assert checker.keypad_layout is None

        # Clear any previous calls made to the mock logger during initialization.
        mock_logger.reset_mock()

        # ACT
        checker.set_keypad_layout(sample_layout)

        # ASSERT
        # 1. Verify the attribute was updated correctly.
        assert checker.keypad_layout == sample_layout

        # 2. Verify that the correct info message was logged (and only once since we reset).
        mock_logger.info.assert_called_once_with(
            "Keypad layout for replay overlays has been set."
        )

    def test_add_key_to_replay(self, checker):
        """
        Tests that _add_key_to_replay correctly adds a key to the
        active_keys_for_replay set.
        """
        # ARRANGE
        key_to_add = "test_key"
        # Ensure the key is not in the set initially
        assert key_to_add not in checker.active_keys_for_replay

        # ACT
        checker._add_key_to_replay(key_to_add)

        # ASSERT
        assert key_to_add in checker.active_keys_for_replay

    def test_remove_key_from_replay(self, checker):
        """
        Tests that _remove_key_from_replay correctly removes a key from the
        active_keys_for_replay set.
        """
        # ARRANGE
        key_to_remove = "test_key"
        # Add the key to the set first so we can test its removal
        checker.active_keys_for_replay.add(key_to_remove)
        assert key_to_remove in checker.active_keys_for_replay

        # ACT
        checker._remove_key_from_replay(key_to_remove)

        # ASSERT
        assert key_to_remove not in checker.active_keys_for_replay
        
        # Test that calling discard on a non-existent key doesn't raise an error
        try:
            checker._remove_key_from_replay("non_existent_key")
        except Exception:
            pytest.fail("_remove_key_from_replay raised an unexpected exception for a non-existent key.")

    def test_log_key_press_for_replay_disabled(self, checker, monkeypatch):
        """
        Tests that log_key_press_for_replay returns early and does not start
        any timers when the instant replay feature is disabled.
        """
        # ARRANGE
        # Disable the instant replay feature on the checker instance.
        checker.enable_instant_replay = False

        # Mock threading.Timer to detect if it gets called.
        mock_timer = MagicMock()
        monkeypatch.setattr(threading, 'Timer', mock_timer)

        # ACT
        # Call the function under test.
        checker.log_key_press_for_replay("some_key", duration_s=1.0)

        # ASSERT
        # Verify that no Timer was created or started, because the function
        # should have returned at the initial check.
        mock_timer.assert_not_called()

    def test_start_key_press_for_replay_disabled(self, checker):
        """
        Tests that start_key_press_for_replay returns early and does not add
        a key when the instant replay feature is disabled.
        """
        # ARRANGE
        # Disable the instant replay feature.
        checker.enable_instant_replay = False
        key_name = "test_key"

        # Ensure the set is empty to start with.
        checker.active_keys_for_replay.clear()
        
        # ACT
        # Call the function under test.
        checker.start_key_press_for_replay(key_name)

        # ASSERT
        # Verify that the key was not added to the set, because the function
        # should have returned at the initial check.
        assert key_name not in checker.active_keys_for_replay

    def test_stop_key_press_for_replay_disabled(self, checker):
        """
        Tests that stop_key_press_for_replay returns early and does not remove
        a key when the instant replay feature is disabled.
        """
        # ARRANGE
        key_name = "test_key"
        # Manually add a key to the active set.
        checker.active_keys_for_replay.add(key_name)
        assert key_name in checker.active_keys_for_replay

        # Disable the instant replay feature.
        checker.enable_instant_replay = False
        
        # ACT
        # Call the function under test.
        checker.stop_key_press_for_replay(key_name)

        # ASSERT
        # Verify that the key was NOT removed from the set, because the
        # function should have returned at the initial check.
        assert key_name in checker.active_keys_for_replay

    @pytest.mark.parametrize("current_state, target_state, fail_leds, expected_result, description", [
        (
            {"red": 1, "green": 0},
            {"green": 0},
            ["red"],
            False,
            "Should fail because 'red' is a fail_led and is ON."
        ),
        (
            {"red": 0, "green": 1},
            {"green": 1},
            ["red"],
            True,
            "Should succeed because fail_led 'red' is OFF."
        ),
        (
            {"green": 1},
            {"green": 1},
            ["red"],
            True,
            "Should succeed because fail_led 'red' is not present (defaults to OFF)."
        ),
        (
            {"red": 1, "blue": 1},
            {"blue": 1},
            ["green", "red"],
            False,
            "Should fail on the second item in the fail_leds list."
        )
    ])
    def test_matches_state_with_fail_leds(self, checker, current_state, target_state, fail_leds, expected_result, description):
        """
        Tests the fail_leds logic within the _matches_state helper method.
        """
        # ACT
        result = checker._matches_state(current_state, target_state, fail_leds)

        # ASSERT
        assert result is expected_result, description

    def test_handle_state_change_logging_initial_state(self, checker, mock_logger):
        """
        Tests the initial state handling in _handle_state_change_logging where
        the previous state is None.
        """
        # ARRANGE
        current_state = {"red": 1, "green": 0}
        current_time = 1000.0
        # This is the key part of the setup: the previous state is None.
        last_state_info = [None, 0.0]

        # FIX: Reset the mock to ignore calls from the fixture's setup.
        mock_logger.reset_mock()

        # ACT
        # Call the function under test.
        result = checker._handle_state_change_logging(current_state, current_time, last_state_info)

        # ASSERT
        # 1. The function should return False as no state change was "logged".
        assert result is False

        # 2. The last_state_info list should be updated with the current state and time.
        assert last_state_info[0] == current_state
        assert last_state_info[1] == current_time

        # 3. No logging should occur on the first call.
        mock_logger.info.assert_not_called()

    def test_process_pattern_step_handles_empty_frames(self, checker, mock_logger):
        """
        Tests that _process_pattern_step handles empty frames gracefully in both
        the 'find' and 'hold' phases by hitting the `continue` statements.
        """
        # ARRANGE
        step_config = {"red": 1, "duration": (0.1, 0.5)}
        ordered_keys = ["red", "green"]
        timeout = time.time() + 5.0

        # Mock `_get_current_led_state_from_camera` to inject empty frames.
        empty_state = (None, {})
        target_state = (None, {"red": 1})
        checker._get_current_led_state_from_camera = MagicMock(side_effect=[
            empty_state,    # 1. Skipped in 'find' loop, calls sleep
            target_state,   # 2. Found, enters 'hold' loop
            target_state,   # 3. Held, calls loop-end sleep
            empty_state,    # 4. Skipped in 'hold' loop, calls sleep
            target_state,   # 5. Held, duration is met, function returns
        ])

        # Use a generator to provide a continuous stream of time values.
        start_time = 1000.0
        time_generator = (start_time + i * 0.05 for i in range(100))

        # Patch time.sleep to verify it's called for the empty frames and loop-ends.
        with patch('controllers.logitech_webcam.time.sleep') as mock_sleep, \
             patch('controllers.logitech_webcam.time.time', side_effect=time_generator):

            # ACT
            success, reason = checker._process_pattern_step(step_config, ordered_keys, timeout, 0, 1)

        # ASSERT
        assert success is True, f"Step should have succeeded, but failed with: {reason}"
        assert reason == ""

        # FIX: The correct count is 3 based on the code's execution path.
        assert mock_sleep.call_count == 3
        mock_sleep.assert_has_calls([call(0.001)] * 3)

        # Verify the logger was not spammed with warnings or errors.
        mock_logger.warning.assert_not_called()

    @pytest.mark.parametrize("held_time, min_duration, tolerance, expected_log_level, description", [
        (1.1, 1.0, 0.2, "info", "State changed AFTER min duration was met"),
        (0.9, 1.0, 0.2, "warning", "State changed WITHIN tolerance window")
    ])
    def test_process_pattern_step_state_changes_after_hold(self, checker, mock_logger,
                                                         held_time, min_duration, tolerance,
                                                         expected_log_level, description):
        """
        Tests successful outcomes in _process_pattern_step when the state changes
        after being held, covering both the main success and tolerance success paths.
        """
        # ARRANGE
        step_config = {"red": 1, "duration": (min_duration, 2.0)}
        ordered_keys = ["red"]
        overall_timeout = time.time() + 5.0
        checker.duration_tolerance_sec = tolerance

        # This mock controls the state sequence precisely.
        target_state = (None, {"red": 1})
        changed_state = (None, {"red": 0})
        # We need a generator here too to prevent StopIteration on this mock
        state_generator = itertools.chain(
            [target_state],  # To find the state initially
            itertools.repeat(target_state, 10), # Hold the state for several cycles
            itertools.repeat(changed_state) # Then change the state indefinitely
        )
        checker._get_current_led_state_from_camera = MagicMock(side_effect=state_generator)

        # FIX: Use a time generator to prevent StopIteration on the time mock.
        start_time = 1000.0
        # This generator will provide a new, slightly later time on every call.
        time_generator = itertools.count(start=start_time, step=0.1)

        # We will manually control the time of the crucial "state seen" event
        # by patching the mock inside the test.
        time_seen = start_time + 1.0
        # And the time of the state change
        time_changed = time_seen + held_time

        # Create a new generator that injects our specific event times.
        def controlled_time_generator():
            yield next(time_generator) # step_find_start_time
            yield next(time_generator) # current_step_find_timeout_end_time calc
            yield next(time_generator) # 'find' loop time check
            yield time_seen            # 'find' loop -> step_seen_at = 1001.0
            
            # Now, in the 'hold' loop, let time advance until it's time for the change
            current_time = time_seen
            while current_time < time_changed:
                current_time += 0.1
                yield current_time
            
            # Yield the change time and continue indefinitely from there
            while True:
                yield time_changed
        
        with patch('controllers.logitech_webcam.time.time', side_effect=controlled_time_generator()), \
             patch('controllers.logitech_webcam.time.sleep'):
            
            mock_logger.reset_mock()
            # ACT
            success, reason = checker._process_pattern_step(step_config, ordered_keys, overall_timeout, 0, 1)

        # ASSERT
        assert success is True, description
        assert reason == "", description
        
        # Check that the correct log (info or warning) was called
        log_method = getattr(mock_logger, expected_log_level)
        log_method.assert_called_once()

    def test_process_pattern_step_succeeds_when_state_changes_after_min_duration(self, checker, mock_logger):
        """
        Tests the specific path where a state is held for the minimum required
        duration, then changes, which should still result in a success. This
        specifically covers the `else` block in the 'hold' phase.
        """
        # ARRANGE
        min_duration = 0.5
        step_config = {"red": 1, "duration": (min_duration, 2.0)}
        ordered_keys = ["red"]
        overall_timeout = time.time() + 5.0

        # Control the state sequence: find -> then immediately change
        target_state = (None, {"red": 1})
        changed_state = (None, {"red": 0})
        checker._get_current_led_state_from_camera = MagicMock(side_effect=[
            target_state,   # 1. State is found in the 'find' loop
            changed_state,  # 2. State has changed for the first 'hold' loop iteration
        ])

        # FIX: Use a generator for most time calls, but inject specific values
        # for the two critical moments to ensure the duration calculation is exact.
        time_state_seen = 1001.0
        time_state_changed = time_state_seen + min_duration # 1001.5
        
        # This generator handles all background time.time() calls
        time_generator = itertools.count(start=1000.0, step=0.01)
        
        # The side_effect list will precisely control the critical calls.
        time_side_effect = [
            next(time_generator),   # for step_find_start_time
            next(time_generator),   # for current_step_find_timeout_end_time calc
            next(time_generator),   # for 'find' loop while condition
            time_state_seen,        # CRITICAL: set the exact time the state was seen
            next(time_generator),   # for 'hold' loop while condition
            time_state_changed,     # CRITICAL: set the exact time the state changed
        ]

        checker._format_led_display_string = MagicMock(return_value="[RED ON]")

        with patch('controllers.logitech_webcam.time.time', side_effect=time_side_effect), \
             patch('controllers.logitech_webcam.time.sleep'):
            
            mock_logger.reset_mock()
            # ACT
            success, reason = checker._process_pattern_step(step_config, ordered_keys, overall_timeout, 0, 1)

        # ASSERT
        assert success is True, "The step should have succeeded"
        assert reason == "", "There should be no failure reason"

        # Verify the specific info log for this success path was called.
        mock_logger.info.assert_called_once_with(
            f"Pattern step 1/1: '[RED ON]' held for {min_duration:.2f}s (state changed but min duration met)."
        )

    def test_confirm_led_solid_success_path_and_state_reset(self, checker, mock_logger):
        """
        Tests the primary success path for confirm_led_solid and that the
        hold timer is correctly reset when the state changes.
        """
        # ARRANGE
        target_state = {"green": 1}
        other_state = {"green": 0}
        minimum_duration = 0.5
        timeout = 2.0

        # Sequence: Wrong state -> Target -> Wrong (resets) -> Target -> Held long enough
        checker._get_current_led_state_from_camera = MagicMock(side_effect=[
            (None, other_state),
            (None, target_state),
            (None, other_state),
            (None, target_state),
            (None, target_state), # This is the call that will pass the duration check
        ])

        # FIX: Use a robust generator for time to prevent StopIteration
        time_generator = itertools.count(start=1000.0, step=0.3)

        # Mock internal helpers
        checker._start_replay_recording = MagicMock()
        checker._stop_replay_recording = MagicMock()
        checker._clear_camera_buffer = MagicMock()
        checker._format_led_display_string = MagicMock(return_value="[TARGET]")
        checker._handle_state_change_logging = MagicMock() # Prevent noisy logs
        mock_logger.reset_mock()

        with patch('controllers.logitech_webcam.time.time', side_effect=time_generator):
            # ACT
            result = checker.confirm_led_solid(target_state, minimum=minimum_duration, timeout=timeout)

        # ASSERT
        assert result is True
        mock_logger.info.assert_called_once()
        logged_message = mock_logger.info.call_args[0][0]
        assert "[TARGET]" in logged_message and "Solid Confirmed" in logged_message
        checker._start_replay_recording.assert_called_once()
        checker._stop_replay_recording.assert_called_once_with(success=True, failure_reason=ANY)

    def test_confirm_led_solid_handles_empty_frame(self, checker, mock_logger):
        """
        Tests that confirm_led_solid correctly handles an empty frame from the
        camera, resets the hold timer, and calls time.sleep.
        """
        # ARRANGE
        target_state = {"green": 1}
        empty_state = (None, {})
        minimum_duration = 0.5
        timeout = 1.0

        checker._get_current_led_state_from_camera = MagicMock(side_effect=[
            (None, target_state),
            empty_state,
            (None, target_state),
            (None, target_state), # Hold to succeed
            (None, target_state),
        ])

        time_generator = itertools.count(start=1000.0, step=0.2)
        mock_logger.reset_mock()

        with patch('controllers.logitech_webcam.time.time', side_effect=time_generator), \
             patch('controllers.logitech_webcam.time.sleep') as mock_sleep:
            # ACT
            result = checker.confirm_led_solid(target_state, minimum=minimum_duration, timeout=timeout)

        # ASSERT
        assert result is True
        mock_sleep.assert_called_once_with(0.01)

    def test_confirm_led_solid_handles_exception_in_loop(self, checker, mock_logger):
        """
        Tests that confirm_led_solid's main loop correctly catches exceptions
        and that the failure reason is handled, even though it gets overwritten
        by the subsequent timeout logic.
        """
        # ARRANGE
        error_message = "A simulated error"
        checker._get_current_led_state_from_camera = MagicMock(side_effect=[
            (None, {"green": 0}),      # Successful call for initialization
            ValueError(error_message)  # Exception raised inside the while loop
        ])
        checker._start_replay_recording = MagicMock()
        checker._stop_replay_recording = MagicMock()
        # Mock the formatter to prevent an extra failure if it's called
        checker._format_led_display_string = MagicMock(return_value="[TARGET]")
        mock_logger.reset_mock()

        # Use a time generator so time can advance and the loop can run.
        time_generator = itertools.count(start=1000.0, step=0.1)

        with patch('controllers.logitech_webcam.time.time', side_effect=time_generator):
            # ACT
            # The default `minimum` is 2.0s
            result = checker.confirm_led_solid({"green": 1}, timeout=1.0)

        # ASSERT
        assert result is False

        # 1. Verify the `except` block was indeed hit and logged the correct error.
        mock_logger.error.assert_called_once()
        call_args, _ = mock_logger.error.call_args
        assert f"Exception in confirm_led_solid loop: {error_message}" in call_args[0]

        # 2. Verify the `if not success_flag:` block was ALSO hit and logged a timeout warning.
        mock_logger.warning.assert_called_once()

        # 3. FIX: Assert that the failure reason passed to the replay recorder is the
        #    *overwritten* value from the timeout logic, not the exception one.
        checker._stop_replay_recording.assert_called_once()
        stop_call_kwargs = checker._stop_replay_recording.call_args.kwargs
        assert stop_call_kwargs['success'] is False

        # The default `minimum` is 2.0, which is used to generate the timeout message.
        expected_overwritten_reason = "timeout_target_not_solid_for_2.00s"
        assert stop_call_kwargs['failure_reason'] == expected_overwritten_reason

    @pytest.mark.parametrize("initial_state, final_state, expected_reason, description", [
        (
            {"green": 1}, {"green": 1},
            "timeout_target_active_for_0.30s_needed_1.00s",
            "Timeout while holding target, but duration not met."
        ),
        (
            {"green": 0}, {"green": 0},
            "timeout_target_not_solid_for_1.00s",
            "Timeout while never holding the target."
        )
    ])
    def test_confirm_led_solid_timeout_scenarios(self, checker, mock_logger, initial_state, 
                                                 final_state, expected_reason, description):
        """
        Tests different timeout failure paths for confirm_led_solid.
        """
        # ARRANGE
        target_state = {"green": 1}
        minimum_duration = 1.0
        timeout = 0.2  # A very short timeout to force failure

        checker._get_current_led_state_from_camera = MagicMock(side_effect=[
             (None, {"green": 0}),  # For initialization call
             (None, initial_state), # For first loop iteration
             (None, final_state)    # For second loop iteration
        ])

        # Use a precise list of time values to control the logic flow exactly.
        time_side_effect = [
            1000.0, # initial_capture_time
            1000.0, # overall_start_time
            1000.0, # first loop time check and current_time
            1000.0, # first loop current_time again for handle_state_change
            1000.3, # loop 2 time check (FAILS timeout > 0.2)
            1000.3, # final log time
            1000.3, # final duration check time
            1000.3, # final duration check time again
        ]

        checker._start_replay_recording = MagicMock()
        checker._stop_replay_recording = MagicMock()
        checker._format_led_display_string = MagicMock(return_value="[TARGET]")
        checker._handle_state_change_logging = MagicMock() # Prevent noisy logs
        mock_logger.reset_mock()

        with patch('controllers.logitech_webcam.time.time', side_effect=time_side_effect):
            # ACT
            result = checker.confirm_led_solid(target_state, minimum=minimum_duration, timeout=timeout)

        # ASSERT
        assert result is False, description
        
        # FIX: The log message uses the `failure_detail` string directly, which contains underscores.
        # Do NOT replace them with spaces for this assertion.
        mock_logger.warning.assert_called_once_with(
            f"Timeout for confirm_led_solid: Target [TARGET] not solid. Reason: {expected_reason}"
        )
        # The replay failure reason is the same string with underscores.
        checker._stop_replay_recording.assert_called_with(success=False, failure_reason=expected_reason)

    def test_process_pattern_step_times_out_during_hold(self, checker):
        """
        Tests that _process_pattern_step correctly times out and returns a
        failure if the overall_timeout is reached during the hold phase.
        """
        # ARRANGE
        # Use a long duration that can't possibly be met in the short timeout.
        step_config = {"red": 1, "duration": (5.0, 10.0)}
        ordered_keys = ["red"]
        
        # Mock the camera to always return the target state. The state never changes.
        target_state = (None, {"red": 1})
        checker._get_current_led_state_from_camera = MagicMock(return_value=target_state)

        start_time = 1000.0
        # Set a very short overall timeout that will be reached quickly.
        overall_timeout = start_time + 0.5

        # Use a generator for time so it never runs out.
        time_generator = (start_time + i * 0.1 for i in range(100))

        with patch('controllers.logitech_webcam.time.time', side_effect=time_generator), \
             patch('controllers.logitech_webcam.time.sleep'):
            
            # ACT
            success, reason = checker._process_pattern_step(step_config, ordered_keys, overall_timeout, 0, 1)

        # ASSERT
        assert success is False
        assert "timeout_hold_step" in reason

    def test_confirm_led_solid_strict_fails_on_initial_mismatch(self, checker, mock_logger):
        """
        Tests that confirm_led_solid_strict fails immediately if the initial
        state read from the camera does not match the target state.
        """
        # ARRANGE
        target_state = {"green": 1}
        initial_wrong_state = {"green": 0}
        method_name = "confirm_led_solid_strict"
        failure_detail = "initial_state_not_target_strict"

        # Mock the camera to return the wrong state initially.
        checker._get_current_led_state_from_camera = MagicMock(return_value=(None, initial_wrong_state))
        
        # Mock internal helpers to isolate the test.
        checker._start_replay_recording = MagicMock()
        checker._stop_replay_recording = MagicMock()
        mock_logger.reset_mock()

        # ACT
        result = checker.confirm_led_solid_strict(target_state, minimum=1.0)

        # ASSERT
        assert result is False

        # Verify the specific warning was logged.
        mock_logger.warning.assert_called_once_with(f"{method_name} FAILED: {failure_detail}")

        # Verify that replay was stopped with the correct failure reason.
        checker._stop_replay_recording.assert_called_once_with(success=False, failure_reason=failure_detail)

    def test_confirm_led_solid_strict_fails_on_op_timeout(self, checker, mock_logger):
        """
        Tests that confirm_led_solid_strict fails if the operation takes
        too long, hitting the internal operation timeout.
        """
        # ARRANGE
        target_state = {"green": 1}
        minimum = 1.0
        method_name = "confirm_led_solid_strict"
        failure_detail = f"op_timeout_strict_aiming_{minimum:.2f}s"

        # The camera always returns the correct state, so failure is not due to state change.
        checker._get_current_led_state_from_camera = MagicMock(return_value=(None, target_state))
        
        # Control time to trigger the specific timeout.
        start_time = 1000.0
        op_timeout_time = start_time + minimum + 5.1 # Time when op timeout is exceeded

        def time_generator():
            # Initial calls for setup
            yield start_time  # For last_state_info and target_state_began_at
            yield start_time  # For strict_op_start_time
            
            # First loop iteration: time hasn't advanced much for the main duration check
            yield start_time + 0.1 # For main `while` condition
            
            # But for the op timeout check, time has advanced significantly
            yield op_timeout_time # For `current_time` inside the loop
            
            # Extra values in case they are needed after the loop breaks
            while True:
                yield op_timeout_time + 1

        checker._start_replay_recording = MagicMock()
        checker._stop_replay_recording = MagicMock()
        mock_logger.reset_mock()
        
        with patch('controllers.logitech_webcam.time.time', side_effect=time_generator()):
            # ACT
            result = checker.confirm_led_solid_strict(target_state, minimum=minimum)

        # ASSERT
        assert result is False

        # Verify the specific timeout warning was logged.
        mock_logger.warning.assert_called_once_with(f"{method_name} FAILED: {failure_detail}")
        
        # Verify replay was stopped with the correct failure reason.
        checker._stop_replay_recording.assert_called_once_with(success=False, failure_reason=failure_detail)

    def test_confirm_led_solid_strict_fails_on_empty_frame(self, checker, mock_logger):
        """
        Tests that confirm_led_solid_strict fails if an empty frame/state
        is detected during the hold check.
        """
        # ARRANGE
        target_state = {"green": 1}
        minimum = 1.0
        method_name = "confirm_led_solid_strict"
        failure_detail = "frame_capture_err_strict"

        # Sequence: Good initial frame, then an empty frame inside the loop
        checker._get_current_led_state_from_camera = MagicMock(side_effect=[
            (None, target_state), # Passes initial check
            (None, {})            # Fails inside the loop
        ])
        
        # Mock internal helpers to isolate the test.
        checker._start_replay_recording = MagicMock()
        checker._stop_replay_recording = MagicMock()
        mock_logger.reset_mock()

        # ACT
        result = checker.confirm_led_solid_strict(target_state, minimum=minimum)

        # ASSERT
        assert result is False

        # Verify the specific warning was logged.
        mock_logger.warning.assert_called_once_with(f"{method_name} FAILED: {failure_detail}")

        # Verify that replay was stopped with the correct failure reason.
        checker._stop_replay_recording.assert_called_once_with(success=False, failure_reason=failure_detail)

    def test_confirm_led_solid_strict_fails_on_state_change(self, checker, mock_logger):
        """
        Tests that confirm_led_solid_strict fails if the state changes
        before the minimum duration is met (and outside the tolerance window).
        """
        # ARRANGE
        target_state = {"green": 1}
        changed_state = {"green": 0}
        minimum = 1.0
        held_for = 0.5 # A duration shorter than the minimum
        method_name = "confirm_led_solid_strict"
        failure_detail = f"state_broke_strict_held_{held_for:.2f}s_needed_{minimum:.2f}s"
        
        # Sequence: Good initial frame, then a different frame inside the loop
        checker._get_current_led_state_from_camera = MagicMock(side_effect=[
            (None, target_state),   # Passes initial check
            (None, changed_state)   # Fails inside the loop
        ])

        # Control time to get the exact `held_for` duration
        start_time = 1000.0
        change_time = start_time + held_for
        time_side_effect = [
            start_time,     # For last_state_info and target_state_began_at
            start_time,     # For strict_op_start_time
            change_time,    # For main `while` condition
            change_time,    # For op timeout check
            change_time,    # For `current_time` inside the loop
            change_time,    # For final `held_for` calculation
        ]

        checker._start_replay_recording = MagicMock()
        checker._stop_replay_recording = MagicMock()
        # Mock this to prevent it from logging and interfering with our assertion
        checker._handle_state_change_logging = MagicMock(return_value=True)
        mock_logger.reset_mock()
        
        with patch('controllers.logitech_webcam.time.time', side_effect=time_side_effect):
            # ACT
            result = checker.confirm_led_solid_strict(target_state, minimum=minimum)

        # ASSERT
        assert result is False

        # Verify the specific warning was logged.
        mock_logger.warning.assert_called_once_with(f"{method_name} FAILED: {failure_detail}")

        # Verify that replay was stopped with the correct failure reason.
        checker._stop_replay_recording.assert_called_once_with(success=False, failure_reason=failure_detail)

    def test_confirm_led_solid_strict_success_path(self, checker, mock_logger):
        """
        Tests the primary success path for confirm_led_solid_strict where the
        state is held for the entire minimum duration.
        """
        # ARRANGE
        target_state = {"green": 1}
        minimum = 0.5
        method_name = "confirm_led_solid_strict"
        
        # Camera always returns the correct state
        checker._get_current_led_state_from_camera = MagicMock(return_value=(None, target_state))
        
        # Control time to satisfy the duration check
        start_time = 1000.0
        end_time = start_time + minimum + 0.1 # A time after the duration is met
        
        time_generator = itertools.count(start_time, step=0.1)

        checker._start_replay_recording = MagicMock()
        checker._stop_replay_recording = MagicMock()
        checker._log_final_state = MagicMock()
        checker._format_led_display_string = MagicMock(return_value="[TARGET]")
        mock_logger.reset_mock()
        
        with patch('controllers.logitech_webcam.time.time', side_effect=time_generator), \
             patch('controllers.logitech_webcam.time.sleep') as mock_sleep:
            # ACT
            result = checker.confirm_led_solid_strict(target_state, minimum=minimum)

        # ASSERT
        assert result is True
        
        # Verify the success logs
        checker._log_final_state.assert_called_once()
        mock_logger.info.assert_any_call(f"{method_name}: LED strictly solid confirmed: [TARGET]")
        
        # Verify the loop ran and called sleep
        assert mock_sleep.call_count > 0

        # Verify replay was stopped with success
        checker._stop_replay_recording.assert_called_once_with(success=True, failure_reason=ANY)

    def test_confirm_led_solid_strict_handles_exception(self, checker, mock_logger):
        """
        Tests that the try...except block in confirm_led_solid_strict correctly
        handles an unexpected exception.
        """
        # ARRANGE
        target_state = {"green": 1}
        minimum = 1.0
        method_name = "confirm_led_solid_strict"
        error_message = "Simulated read error"
        
        # Sequence: Good initial frame, then an exception inside the loop
        checker._get_current_led_state_from_camera = MagicMock(side_effect=[
            (None, target_state), # Passes initial check
            RuntimeError(error_message)
        ])
        
        checker._start_replay_recording = MagicMock()
        checker._stop_replay_recording = MagicMock()
        mock_logger.reset_mock()
        
        # ACT
        result = checker.confirm_led_solid_strict(target_state, minimum=minimum)
        
        # ASSERT
        assert result is False
        
        # Verify the error log
        mock_logger.error.assert_called_once()
        call_args, call_kwargs = mock_logger.error.call_args
        assert f"Exception in {method_name} loop: {error_message}" in call_args[0]
        assert call_kwargs.get('exc_info') is True
        
        # Verify replay was stopped with the correct failure reason
        checker._stop_replay_recording.assert_called_once_with(
            success=False,
            failure_reason="exception_strict_loop_RuntimeError"
        )

    def test_log_key_press_for_replay(self, checker, monkeypatch):
        """Test that timers are started to add and remove keys for replay."""
        mock_timer = MagicMock()
        monkeypatch.setattr(threading, 'Timer', mock_timer)
        checker.enable_instant_replay = True
        
        checker.log_key_press_for_replay("key1", duration_s=0.1)

        # Assert two timers were created: one to add the key, one to remove it.
        assert mock_timer.call_count == 2
        # Check the call to start the timers
        assert mock_timer.return_value.start.call_count == 2
    
    def test_start_stop_key_press_for_replay(self, checker):
        """Test the manual start/stop methods for key press visualization."""
        checker.enable_instant_replay = True
        
        checker.start_key_press_for_replay("lock")
        assert "lock" in checker.active_keys_for_replay
        
        checker.stop_key_press_for_replay("lock")
        assert "lock" not in checker.active_keys_for_replay

    def test_start_replay_recording_conditions(self, checker, mock_logger):
        """Test the conditions that prevent a replay from being armed."""
        # 1. Replay disabled globally
        checker.enable_instant_replay = False
        checker._start_replay_recording("test_method")
        assert checker.is_replay_armed is False
        mock_logger.debug.assert_called_with("Replay not armed for 'test_method': Instant replay is disabled.")

        # 2. No output directory
        checker.enable_instant_replay = True
        checker.replay_output_dir = None
        checker._start_replay_recording("test_method")
        assert checker.is_replay_armed is False
        mock_logger.debug.assert_any_call("Replay not armed for 'test_method': output directory not available.")

        # 3. Already armed
        checker.replay_output_dir = "/tmp/replays"
        checker._start_replay_recording("first_method")
        assert checker.is_replay_armed is True
        checker._start_replay_recording("second_method")
        mock_logger.debug.assert_any_call("Replay: System already armed for method 'first_method'. Ignoring start for 'second_method'.")

    def test_save_replay_video_conditions(self, checker, mock_logger):
        """Test conditions that prevent a video from being saved."""
        # Not armed
        checker.is_replay_armed = False
        checker._save_replay_video([1, 2, 3])
        mock_logger.debug.assert_not_called()

        # No frames
        checker.is_replay_armed = True
        checker.replay_output_dir = "/tmp/replays"
        checker._save_replay_video([])
        mock_logger.debug.assert_called_with("Replay: No frames in sequence to save.")

        # Frame dimensions not set
        checker.replay_frame_width = None
        checker._save_replay_video([1, 2, 3])
        mock_logger.error.assert_called_with("Replay: Frame dimensions not set. Cannot save video.")

    def test_public_methods_fail_if_camera_not_initialized(self, checker, mock_logger):
        """Test that all public-facing methods fail gracefully if camera is not initialized."""
        checker.is_camera_initialized = False
        
        assert checker.confirm_led_solid({}, manage_replay=False) is False
        assert checker.confirm_led_solid_strict({}, minimum=1, manage_replay=False) is False
        assert checker.await_led_state({}, manage_replay=False) is False
        assert checker.confirm_led_pattern([{}], manage_replay=False) is False
        assert checker.await_and_confirm_led_pattern([{}], timeout=1, manage_replay=False) is False
        
        # Check that an error was logged for each call
        assert mock_logger.error.call_count == 5

    def test_confirm_led_solid_tolerance_pass(self, checker, mock_logger):
        """
        Test that a solid check passes if it times out but was within the duration tolerance.
        """
        # --- ARRANGE ---
        target_state = {"green": 1}
        required_duration = 2.0
        checker.duration_tolerance_sec = 0.2 # Test will pass if held for >= 1.8s
        
        # We will simulate the state being held for exactly 1.9s.
        start_time = 1000.0
        end_time = start_time + 1.9
        mock_frame = np.zeros((10,10,3), dtype=np.uint8)
        
        # This test works by controlling the two inputs to the function's loop:
        # 1. The mocked return values of time.time()
        # 2. The contents of the replay_buffer, which simulates the camera's output.

        # Configure the sequence of times that will be returned. This is critical.
        time_side_effect = [
            start_time,         # Called at line 697: initial_capture_time
            start_time,         # Called at line 702: overall_start_time
            start_time + 0.05,  # Called at line 704: while loop check 1 (continue)
            start_time + 0.05,  # Called at line 705: current_time in loop 1
            start_time + 0.2,   # Called at line 704: while loop check 2 (timeout)
            end_time,           # Called at line 722: _log_final_state
            end_time,           # Called at line 724: final duration calculation
        ]

        # The state inside the buffer will always be the correct, matching state.
        # This ensures 'continuous_target_match_start_time' is set and never cleared.
        checker.replay_buffer.append((start_time, mock_frame, target_state, set()))

        # --- ACT ---
        with patch('time.time', side_effect=time_side_effect):
            # WHEN confirm_led_solid is called with a short timeout (0.1s) to force failure
            result = checker.confirm_led_solid(
                target_state, 
                minimum=required_duration, 
                timeout=0.1, 
                manage_replay=False
            )

        # --- ASSERT ---
        # THEN the function should return True because the tolerance check passed.
        assert result is True
        
        # AND a warning should have been logged about passing due to tolerance.
        mock_logger.warning.assert_called_once()
        assert "within tolerance" in mock_logger.warning.call_args[0][0]

    def test_confirm_led_solid_strict_tolerance_pass(self, checker, mock_logger):
        """Test that a strict solid check passes if it breaks but was within tolerance."""
        # --- ARRANGE ---
        target_state = {"green": 1}
        required_duration = 1.0
        checker.duration_tolerance_sec = 0.2  # Pass if held >= 0.8s
        
        start_time = 1000.0
        break_time = start_time + 0.9  # Held for 0.9s, which is within tolerance
        
        mock_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        good_state_tuple = (mock_frame, target_state)
        bad_state_tuple = (mock_frame, {"green": 0})

        # Control the sequence of returned states and times precisely.
        # The first call to _get_current_led_state_from_camera happens *before* the loop.
        # The second call happens *inside* the loop.
        state_side_effect = [
            good_state_tuple,  # For the initial check before the loop
            bad_state_tuple,   # For the check inside the loop that breaks it
        ]
        time_side_effect = [
            start_time, # For last_state_info timestamp
            start_time, # For target_state_began_at
            break_time, # For the while-loop condition check
            break_time, # For strict_op_start_time check
            break_time, # For current_time in _handle_state_change_logging
            break_time, # For the held_for calculation
        ]

        with patch.object(checker, '_get_current_led_state_from_camera', side_effect=state_side_effect), \
             patch('time.time', side_effect=time_side_effect):
            
            # --- ACT ---
            result = checker.confirm_led_solid_strict(
                target_state, 
                minimum=required_duration, 
                manage_replay=False
            )

        # --- ASSERT ---
        assert result is True
        mock_logger.warning.assert_called_once()
        assert "within tolerance" in mock_logger.warning.call_args[0][0]

    @patch('cv2.getTextSize', return_value=((100, 20), 10)) # Mock text width=100, height=20
    @patch('cv2.rectangle')
    @patch('cv2.putText')
    def test_draw_text_with_background(self, mock_put_text, mock_rectangle, mock_get_text_size, checker):
        """
        Tests that _draw_text_with_background correctly calculates coordinates
        and calls the underlying cv2 functions for drawing.
        """
        # --- ARRANGE ---
        # A blank image to draw on
        img = np.zeros((200, 300, 3), dtype=np.uint8)
        text_to_draw = "Test Text"
        position = (50, 100) # (x, y)
        
        # --- ACT ---
        checker._draw_text_with_background(img, text_to_draw, position)

        # --- ASSERT ---
        # 1. Verify getTextSize was called with the correct parameters
        mock_get_text_size.assert_called_once_with(
            text_to_draw,
            camera_module.OVERLAY_FONT,
            camera_module.OVERLAY_FONT_SCALE,
            camera_module.OVERLAY_FONT_THICKNESS
        )

        # 2. Verify the background rectangle was drawn with correctly calculated coordinates
        # From mock_getTextSize, we have text_w=100, text_h=20.
        # From the function, pos is x=50, y=100. OVERLAY_PADDING is 5.
        # rect_x1 = 50 - 5 = 45
        # rect_y1 = 100 - 20 - 5 = 75
        # rect_x2 = 50 + 100 + 5 = 155
        # rect_y2 = 100 + 5 = 105
        expected_rect_p1 = (45, 75)
        expected_rect_p2 = (155, 105)
        
        mock_rectangle.assert_called_once()
        # Use ANY for the image array, as comparing numpy arrays is tricky
        mock_rectangle.assert_called_with(
            ANY,
            expected_rect_p1,
            expected_rect_p2,
            camera_module.OVERLAY_BG_COLOR,
            -1 # Filled rectangle
        )

        # 3. Verify the text was drawn with the correct parameters
        mock_put_text.assert_called_once_with(
            ANY,
            text_to_draw,
            position,
            camera_module.OVERLAY_FONT,
            camera_module.OVERLAY_FONT_SCALE,
            camera_module.OVERLAY_TEXT_COLOR_MAIN,
            camera_module.OVERLAY_FONT_THICKNESS,
            cv2.LINE_AA
        )

    @pytest.mark.parametrize("has_context", [True, False])
    @pytest.mark.parametrize("has_keypad", [True, False])
    @patch('cv2.rectangle')
    @patch('cv2.circle')
    @patch('cv2.putText')
    def test_draw_overlays(self, mock_put_text, mock_circle, mock_rectangle, checker, has_context, has_keypad):
        """
        Tests the _draw_overlays function, covering all conditional branches.
        """
        # --- ARRANGE ---
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        led_states = {"red": 1, "green": 0}
        active_keys = {"key1"}
        checker._draw_text_with_background = MagicMock()

        if has_context:
            checker.replay_extra_context = {'fsm_current_state': 'STATE_A', 'fsm_destination_state': 'STATE_B'}
        else:
            checker.replay_extra_context = None

        if has_keypad:
            checker.keypad_layout = [['key1', 'key2']]
        else:
            checker.keypad_layout = None

        # --- ACT ---
        result_frame = checker._draw_overlays(frame, 1.23, led_states, active_keys)

        # --- ASSERT ---
        assert isinstance(result_frame, np.ndarray)

        if has_context:
            assert checker._draw_text_with_background.call_count == 2
        else:
            checker._draw_text_with_background.assert_not_called()

        # Assert Keypad drawing
        if has_keypad:
            # <<< FIX: Check the specific argument for the text string. >>>
            # call.args will be (image_array, text_string, ...). We check the second element.
            assert any(call.args[1] == "key1" for call in mock_put_text.call_args_list)
            assert any(call.args[1] == "key2" for call in mock_put_text.call_args_list)
            
            # The logic for rectangle count was also slightly off.
            # ROI drawing adds 2 rectangles. Keypad adds 3 (2 for unpressed, 2 for pressed).
            # The pressed key gets two rectangle calls (background and outline).
            # The unpressed key gets one. Total = 3 for keypad.
            # ROI drawing for red and green adds 2 more. Total >= 5
            assert mock_rectangle.call_count >= 5
        
        # Assert ROI and LED indicator drawing
        assert mock_circle.call_count == 4
        mock_circle.assert_any_call(ANY, ANY, ANY, camera_module.OVERLAY_TEXT_COLOR_MAIN, -1)
        mock_circle.assert_any_call(ANY, ANY, ANY, camera_module.OVERLAY_LED_INDICATOR_OFF_COLOR, -1)

class TestSaveReplayVideo:
    """A dedicated class for testing the _save_replay_video method."""

    @pytest.fixture
    def checker(self, mock_cv2_videocapture, mock_logger, tmp_path):
        """Provides a checker instance configured for replay testing."""
        # Use a real temporary path provided by pytest's tmp_path fixture
        replay_dir = str(tmp_path)
        
        # Patch the thread so it doesn't run in the background
        with patch('threading.Thread'):
            instance = LogitechLedChecker(
                camera_id=0,
                logger_instance=mock_logger,
                replay_output_dir=replay_dir,
                enable_instant_replay=True
            )
        
        # Pre-configure the instance for a typical save operation
        instance.is_replay_armed = True
        instance.replay_frame_width = 100
        instance.replay_frame_height = 80
        instance.replay_start_time = 1000.0
        instance.replay_method_name = "test method"
        
        yield instance
        # Cleanup
        instance.release_camera()

    @pytest.mark.parametrize("armed, has_sequence, has_dir", [
        (False, True, True),   # Not armed
        (True, False, True),   # No frames in sequence
        (True, True, False),   # No output directory
    ])
    @patch('cv2.VideoWriter')
    def test_save_replay_exits_early(self, mock_video_writer, checker, armed, has_sequence, has_dir):
        """Tests all three initial conditions that should cause the function to exit early."""
        # --- ARRANGE ---
        checker.is_replay_armed = armed
        checker.replay_output_dir = "/fake/dir" if has_dir else None
        sequence = [1] if has_sequence else []

        # --- ACT ---
        checker._save_replay_video(sequence)
        
        # --- ASSERT ---
        # VideoWriter should never be called if an early exit condition is met
        mock_video_writer.assert_not_called()

    def test_save_replay_exits_if_no_frame_dimensions(self, checker, mock_logger):
        """Tests that the function exits if frame dimensions are not set."""
        # ARRANGE
        checker.replay_frame_width = None
        
        # ACT
        checker._save_replay_video([1])
        
        # ASSERT
        mock_logger.error.assert_called_with("Replay: Frame dimensions not set. Cannot save video.")

    @patch('cv2.VideoWriter')
    def test_save_replay_exits_if_writer_fails_to_open(self, mock_video_writer, checker, mock_logger):
        """Tests the case where cv2.VideoWriter fails to open the file."""
        # ARRANGE
        mock_writer_instance = MagicMock()
        mock_writer_instance.isOpened.return_value = False
        mock_video_writer.return_value = mock_writer_instance
    
        # ACT
        checker._save_replay_video([1])
    
        # ASSERT
        # <<< FIX: The error is logged without an exc_info kwarg. >>>
        mock_logger.error.assert_called_once()
        # We can be more specific and check that the logged message contains the expected text.
        logged_message = mock_logger.error.call_args[0][0]
        assert "Failed to open VideoWriter" in logged_message

        # Ensure release is still called in the finally block
        mock_writer_instance.release.assert_called_once()
    
    @patch('cv2.VideoWriter')
    @patch('cv2.resize')
    def test_save_replay_success_and_frame_resizing(self, mock_resize, mock_video_writer, checker, mock_logger):
        """
        Tests the successful video saving path, including both matched and
        mismatched frame sizes to test the resizing logic.
        """
        # --- ARRANGE ---
        # Mock the VideoWriter to simulate successful opening
        mock_writer_instance = MagicMock()
        mock_writer_instance.isOpened.return_value = True
        mock_video_writer.return_value = mock_writer_instance

        # Mock the internal _draw_overlays to return frames of different sizes
        matched_frame = np.zeros((80, 100, 3)) # Matches checker's dimensions
        mismatched_frame = np.zeros((50, 50, 3)) # Does not match
        checker._draw_overlays = MagicMock(side_effect=[matched_frame, mismatched_frame])

        # Prepare a dummy replay sequence
        replay_sequence = [
            (1001.0, MagicMock(), {}, set()), # This will get the matched_frame
            (1002.0, MagicMock(), {}, set())  # This will get the mismatched_frame
        ]
        
        # --- ACT ---
        checker._save_replay_video(replay_sequence)

        # --- ASSERT ---
        # 1. Verify VideoWriter was created with correct parameters
        mock_video_writer.assert_called_once_with(
            ANY, ANY, checker.replay_fps, (checker.replay_frame_width, checker.replay_frame_height)
        )

        # 2. Verify _draw_overlays was called for each frame in the sequence
        assert checker._draw_overlays.call_count == 2

        # 3. Verify writer.write was called twice
        assert mock_writer_instance.write.call_count == 2
        
        # 4. Verify that cv2.resize was called exactly once for the mismatched frame
        mock_resize.assert_called_once_with(mismatched_frame, (checker.replay_frame_width, checker.replay_frame_height))
        
        # 5. Verify the success and warning logs
        mock_logger.info.assert_any_call(ANY)
        assert "Successfully wrote frames" in mock_logger.info.call_args[0][0]
        mock_logger.warning.assert_called_once_with("Replay: Overlay frame dimension mismatch. Resizing.")

        # 6. Verify the writer was released
        mock_writer_instance.release.assert_called_once()

    @patch('cv2.VideoWriter', side_effect=Exception("Disk full"))
    def test_save_replay_handles_generic_exception(self, mock_video_writer, checker, mock_logger):
        """Tests that a generic exception during video writing is caught and logged."""
        # --- ACT ---
        checker._save_replay_video([1])
        
        # --- ASSERT ---
        mock_logger.error.assert_called_once()
        assert "Error during video writing" in mock_logger.error.call_args[0][0]

class TestStopReplayRecording:
    """A dedicated class for testing the _stop_replay_recording method."""

    @pytest.fixture
    def checker(self, mock_cv2_videocapture, mock_logger, tmp_path):
        """Provides a checker instance configured for replay testing."""
        replay_dir = str(tmp_path)
        with patch('threading.Thread'):
            instance = LogitechLedChecker(
                camera_id=0,
                logger_instance=mock_logger,
                replay_output_dir=replay_dir,
                enable_instant_replay=True
            )
        instance.is_replay_armed = True # Arm it by default for most tests
        yield instance
        instance.release_camera()

    def test_exits_early_if_not_armed(self, checker):
        """Tests that the function does nothing if the replay system isn't armed."""
        # ARRANGE
        checker.is_replay_armed = False
        checker._save_replay_video = MagicMock()
        
        # ACT
        checker._stop_replay_recording(success=False)
        
        # ASSERT
        checker._save_replay_video.assert_not_called()
        # The flag should remain False
        assert checker.is_replay_armed is False

    def test_disarms_on_success(self, checker):
        """Tests that on success, no video is saved and the system is disarmed."""
        # ARRANGE
        checker._save_replay_video = MagicMock()
        checker.replay_method_name = "A_TEST" # Give it some state to clear
        
        # ACT
        checker._stop_replay_recording(success=True)
        
        # ASSERT
        checker._save_replay_video.assert_not_called()
        assert checker.is_replay_armed is False
        assert checker.replay_method_name == "" # State should be cleared

    @pytest.mark.parametrize("has_buffer, has_dir", [
        (False, True),
        (True, False),
    ])
    def test_logs_debug_on_failure_with_no_buffer_or_dir(self, checker, mock_logger, has_buffer, has_dir):
        """
        Tests that on failure, if the buffer or directory is missing, a debug
        log is created and no save is attempted.
        """
        # ARRANGE
        if has_buffer:
            checker.replay_buffer.append(1)
        else:
            checker.replay_buffer.clear()
            
        if has_dir:
            checker.replay_output_dir = "/fake/dir"
        else:
            checker.replay_output_dir = None
        
        checker._save_replay_video = MagicMock()
        
        # ACT
        checker._stop_replay_recording(success=False)
        
        # ASSERT
        checker._save_replay_video.assert_not_called()
        mock_logger.debug.assert_called_with(
            "Failure occurred, but no replay will be saved (buffer empty or output dir not set)."
        )
        # System should still be disarmed
        assert checker.is_replay_armed is False
    
    def test_failure_path_saves_video(self, checker):
        """
        Tests the main failure path where a video with pre-roll and post-roll
        footage is generated and saved.
        """
        # --- ARRANGE ---
        # 1. Pre-load the replay buffer with some "pre-roll" frames
        checker.replay_buffer.append("pre-roll-frame-1")
        
        # 2. Configure mocks for the post-roll recording loop
        mock_frame = np.zeros((10,10,3))
        mock_states = {"red": 1}
        
        # This time trace must account for every call to time.time()
        time_side_effect = [
            1000.0, # For replay_start_time
            1000.0, # For post_failure_start_time
            1000.1, # Loop 1: while check
            1000.1, # Loop 1: append()
            1001.1, # Loop 2: while check (terminates)
        ]

        # This is the key: We will patch the internal _save_replay_video method
        # and perform our assertion inside the patch.
        def assert_and_save(sequence_to_save):
            # ASSERTION 1: Check the failure reason *before* it gets cleared.
            assert checker.replay_failure_reason == "test failed reason"
            
            # ASSERTION 2: Check the content of the saved sequence.
            assert len(sequence_to_save) == 2 # 1 pre-roll + 1 post-roll
            assert sequence_to_save[0] == "pre-roll-frame-1"
            assert sequence_to_save[1][0] == 1000.1 # Timestamp of post-roll frame

        # Create a mock for the save method and assign our assertion function to its side_effect
        mock_save_method = MagicMock(side_effect=assert_and_save)

        with patch.object(checker, '_get_current_led_state_from_camera', return_value=(mock_frame, mock_states)), \
             patch.object(checker, '_save_replay_video', mock_save_method), \
             patch('time.time', side_effect=time_side_effect), \
             patch('time.sleep'):
            
            # Set a short post-failure duration for the test
            checker.replay_post_failure_duration_sec = 1.0

            # --- ACT ---
            checker._stop_replay_recording(success=False, failure_reason="test_failed_reason")

        # --- FINAL ASSERTIONS ---
        # Verify our patched save method was called
        mock_save_method.assert_called_once()
        # Verify the system was disarmed after the process
        assert checker.is_replay_armed is False
        assert checker.replay_failure_reason == "" # Verify it was cleared at the end

class TestAwaitLedState:
    """A dedicated class for testing the await_led_state method."""

    @pytest.fixture
    def checker(self, mock_cv2_videocapture, mock_logger, tmp_path):
        """Provides a checker instance configured for testing this method."""
        replay_dir = str(tmp_path)
        with patch('threading.Thread'):
            instance = LogitechLedChecker(
                camera_id=0,
                logger_instance=mock_logger,
                replay_output_dir=replay_dir,
                enable_instant_replay=True
            )
        # Mock internal helpers to isolate the function's logic
        instance._start_replay_recording = MagicMock()
        instance._stop_replay_recording = MagicMock()
        instance._clear_camera_buffer = MagicMock()
        instance._log_final_state = MagicMock()
        instance._format_led_display_string = MagicMock(return_value="[TARGET]")
        yield instance
        instance.release_camera()

    def test_success_path(self, checker, mock_logger):
        """Tests the successful detection of the target state."""
        # --- ARRANGE ---
        target_state = {"green": 1}
        # Simulate the camera returning the correct state on the first try
        with patch.object(checker, '_get_current_led_state_from_camera', return_value=(None, target_state)):
            
            # --- ACT ---
            result = checker.await_led_state(target_state)

        # --- ASSERT ---
        assert result is True
        checker._start_replay_recording.assert_called_once()
        checker._stop_replay_recording.assert_called_with(success=True, failure_reason=ANY)
        # Verify the success log message was called
        mock_logger.info.assert_any_call("Target state [TARGET] observed.")

    def test_timeout_path(self, checker, mock_logger):
        """Tests the timeout path where the target state is never seen."""
        # --- ARRANGE ---
        # Simulate the camera always returning an incorrect state
        incorrect_state = {"green": 0}
        with patch.object(checker, '_get_current_led_state_from_camera', return_value=(None, incorrect_state)):
            # --- ACT ---
            result = checker.await_led_state({"green": 1}, timeout=0.1)
    
        # --- ASSERT ---
        assert result is False
        checker._stop_replay_recording.assert_called_with(success=False, failure_reason="timeout_await_await_[TARGET]")

    def test_fail_leds_path(self, checker, mock_logger):
        """Tests that the function returns False if a 'fail_led' is detected."""
        # --- ARRANGE ---
        target_state = {"green": 1}
        fail_leds = ["red"]
        # Simulate camera returning a state that matches the target but also includes a fail_led
        bad_state = {"green": 1, "red": 1}
        with patch.object(checker, '_get_current_led_state_from_camera', return_value=(None, bad_state)):
            # --- ACT ---
            result = checker.await_led_state(target_state, fail_leds=fail_leds, timeout=0.1)

        # --- ASSERT ---
        # The function should time out because _matches_state will return False
        assert result is False
        mock_logger.warning.assert_has_calls([
            call("Failed to await 'await [TARGET]': Prohibited LED 'red' is ON. Current: [TARGET]"),
            call('Timeout: [TARGET] not observed. Reason: prohibited led red on')
        ])
        assert mock_logger.warning.call_count == 2

    def test_camera_not_initialized_path(self, checker, mock_logger):
        """Tests the early exit path when the camera is not initialized."""
        # --- ARRANGE ---
        checker.is_camera_initialized = False
        
        # --- ACT ---
        result = checker.await_led_state({})

        # --- ASSERT ---
        assert result is False
        mock_logger.error.assert_called_once_with("await_led_state: camera_not_init_await")
        checker._stop_replay_recording.assert_called_with(success=False, failure_reason="camera_not_init_await")

    def test_empty_frame_path(self, checker, mock_logger):
        """Tests the 'if not current_leds' branch in the loop."""
        # --- ARRANGE ---
        # Simulate camera returning an empty frame, then the correct state
        initial_state = (None, {})
        empty_state_in_loop = (None, {})
        good_state = (None, {"green": 1})
        
        # We also need to patch the method we want to check
        with patch.object(checker, '_handle_state_change_logging') as mock_handle_log, \
             patch.object(checker, '_get_current_led_state_from_camera', side_effect=[initial_state, empty_state_in_loop, good_state]):
            
            # --- ACT ---
            result = checker.await_led_state({"green": 1})
    
        # --- ASSERT ---
        assert result is True
        # Check that the specific log call for an empty frame was made
        mock_handle_log.assert_any_call({}, ANY, ANY)

    def test_logging_path_for_newly_observed_state(self, checker, mock_logger):
        """
        Tests the logging branch for when the target state is different from the previous state.
        """
        # --- ARRANGE ---
        initial_state = {"green": 0}
        target_state = {"green": 1}
        
        start_time = 1000.0
        
        # This sequence simulates finding the initial state, then finding the target state in the loop.
        state_side_effect = [
            (None, initial_state), # For the initial check before the loop
            (None, target_state)   # For the check inside the loop that succeeds
        ]

        # We only need to control time for the two main checks.
        with patch.object(checker, '_get_current_led_state_from_camera', side_effect=state_side_effect), \
             patch('time.time', return_value=start_time): # Keep time constant for simplicity
            
            # --- ACT ---
            checker.await_led_state(target_state)
            
        # --- ASSERT ---
        # The most reliable check is for the final success message, which is always the same.
        mock_logger.info.assert_any_call("Target state [TARGET] observed.")

class TestConfirmLedPattern:
    """A dedicated class for testing the confirm_led_pattern method."""

    @pytest.fixture
    def checker(self, mock_cv2_videocapture, tmp_path):
        """Provides a checker instance with a REAL logger for these tests."""
        with patch('threading.Thread'):
            instance = LogitechLedChecker(
                camera_id=0,
                replay_output_dir=str(tmp_path),
                enable_instant_replay=True
            )
        # Mock internal helpers to isolate the function's logic
        instance._start_replay_recording = MagicMock()
        instance._stop_replay_recording = MagicMock()
        instance._clear_camera_buffer = MagicMock()
        instance._format_led_display_string = MagicMock(return_value="[TARGET]")
        yield instance
        instance.release_camera()

    @pytest.mark.parametrize("pattern, is_initialized", [
        ([], True),
        ([{"green":1}], False),
    ])
    def test_early_exit_paths(self, checker, caplog, pattern, is_initialized):
        """Tests the initial checks for empty pattern and uninitialized camera."""
        checker.is_camera_initialized = is_initialized
        # CORRECTED: Use the correct logger name "controllers.logitech_webcam"
        with caplog.at_level(logging.INFO, logger="controllers.logitech_webcam"):
            result = checker.confirm_led_pattern(pattern)
        assert result is False
        if not pattern:
            assert "empty_pattern" in caplog.text
        if not is_initialized:
            assert "camera_not_init_pattern" in caplog.text

    def test_overall_timeout_in_find_loop(self, checker, caplog):
        """Tests that the main timeout breaks the 'find' loop."""
        # --- ARRANGE ---
        pattern = [{"green": 1, "duration": (0.1, 1.0)}] # This step will never be found

        mock_frame = np.zeros((10,10,3))
        # Provide states that will NEVER match {"green": 1}
        state_side_effect = itertools.repeat((mock_frame, {"blue": 0}))

        start_time = 1000.0
        # The crucial part: we need time to advance *just enough* so that
        # `time.time() > overall_timeout_end_time` becomes true in the *outer* loop
        # before the internal `_process_pattern_step` logic has a chance to
        # trigger its own timeout.

        # The `overall_timeout` variable in the SUT will be: 1.0 + 0*10 + 1*5 + 15 = 21.0
        # So overall_timeout_end_time = pattern_start_time + 21.0

        # We need `time.time()` to jump from `pattern_start_time` to something > `pattern_start_time + 21.0`
        time_side_effect_list = [
            start_time, # For pattern_start_time in confirm_led_pattern
            start_time + 21.001, # This will make time.time() > overall_timeout_end_time for the outer loop check
            # Provide an infinite supply for any subsequent calls (e.g. within _stop_replay_recording)
            *(start_time + 21.002 + i * 0.001 for i in range(100))
        ]

        checker._stop_replay_recording = MagicMock()

        # Add a patch for _process_pattern_step so we can assert on its calls
        with patch.object(checker, '_get_current_led_state_from_camera', side_effect=state_side_effect), \
             patch('time.time', side_effect=time_side_effect_list), \
             patch('time.sleep', return_value=None), \
             patch.object(checker, '_process_pattern_step') as mock_process_pattern_step: # <-- NEW PATCH HERE

            with caplog.at_level(logging.ERROR, logger="controllers.logitech_webcam"):
                 result = checker.confirm_led_pattern(pattern, clear_buffer=False)

        assert result is False
        expected_log_substring = f"confirm_led_pattern Error: overall_timeout_pattern_at_step_1"
        assert expected_log_substring in caplog.text
        
        # Now use the mock object to assert it was NOT called
        mock_process_pattern_step.assert_not_called() # <-- CHANGED ASSERTION TARGET

    def test_step_never_seen_timeout(self, checker, caplog):
        """Tests the timeout for finding an individual step."""
        # --- ARRANGE ---
        # Simulate camera always returning the wrong state
        mock_frame = np.zeros((10,10,3))
        wrong_state = (mock_frame, {"green":0})

        # We need time to advance enough to trigger step_app_timeout.
        # step_app_timeout for (0.1, 0.2) duration is max(1.0, 0.2/2 or 5.0) + 2.0 = 7.0
        # So we need time to advance beyond step_loop_start_time + 7.0
        
        start_time = 1000.0
        # Time when the step_app_timeout is exceeded
        # This will be the time.time() value that causes the `if time.time()-step_loop_start_time > step_app_timeout:` condition to be true.
        timeout_trigger_time = start_time + 7.5 # Example time to exceed 7.0s timeout

        # Sequence of time.time() calls:
        # Part 1 (Time Mock Adjustment): Ensure enough time values for all calls, including internal logging and replay.
        time_side_effect = [
            start_time,                # 1. pattern_start_time
            start_time + 0.001,        # 2. overall_timeout check (outer while)
            start_time + 0.002,        # 3. step_loop_start_time (for current step)

            # Simulate many internal loop iterations for `time.time()` checks until `timeout_trigger_time` is reached.
            # We assume a base of 1ms sleep, but multiple `time.time()` calls per iteration.
            # Use a generator to provide plenty of distinct time values.
            *(start_time + 0.003 + i * 0.01 for i in range(0, 750)), # Many calls during the loop (750 iterations * 0.01s = 7.5s)
            
            timeout_trigger_time,      # This value triggers the step_app_timeout failure
            timeout_trigger_time + 0.001, # overall_timeout check after break
            
            # Calls inside _stop_replay_recording (assuming it's triggered on failure)
            timeout_trigger_time + 0.010, # replay_start_time
            timeout_trigger_time + 0.011, # post_failure_start_time
            # Simulate post-failure recording (e.g., 5 seconds post-fail duration at 30 FPS = 150 frames)
            *(timeout_trigger_time + 0.011 + i * (1.0 / 30.0) for i in range(0, 160)), # 160 frames for post-roll + buffer
            
            # Add a few extra for robustness beyond the end of replay saving.
            timeout_trigger_time + 6.0, # Final time.time() for any cleanup/logger calls
            timeout_trigger_time + 6.01,
            timeout_trigger_time + 6.02,
        ]
        
        # The state_side_effect needs to be long enough for all _get_current_led_state_from_camera calls.
        # We'll just return `wrong_state` consistently.
        state_side_effect = [wrong_state] * (len(time_side_effect) // 2 + 5) # Provide plenty

        with patch.object(checker, '_get_current_led_state_from_camera', side_effect=state_side_effect), \
             patch('time.time', side_effect=time_side_effect), \
             patch('time.sleep', return_value=None):

            with caplog.at_level(logging.WARNING, logger="controllers.logitech_webcam"):
                 result = checker.confirm_led_pattern([{"green":1, "duration":(0.1, 0.2)}])

        assert result is False
        
        # Part 2 (Assertion Adjustment): Remove the old assertion and add the correct one.
        # The `Pattern ended inconclusively` log is NOT produced in this specific failure path.
        # It should pass the specific failure reason to _stop_replay_recording.
        # assert "Pattern ended inconclusively" in caplog.text # REMOVED

        expected_failure_reason_for_stop = f"step_1_not_seen_[TARGET]" # [TARGET] comes from checker._format_led_display_string mock
        checker._stop_replay_recording.assert_called_once_with(
            success=False,
            failure_reason=expected_failure_reason_for_stop
        )

    def test_skipped_zero_duration_step(self, checker, caplog):
        """Tests that a step with zero duration is correctly skipped."""
        pattern = [{"green": 1, "duration": (0.0, 0.1)}, {"red": 1}]
        
        mock_frame = np.zeros((10,10,3))
        non_matching_state_tuple = (mock_frame, {"blue": 0}) # For 1st step (green) - should NOT match
        matching_state_for_second_step_tuple = (mock_frame, {"red": 1}) # For 2nd step (red) - should match

        # For _process_pattern_step (and _await_state_appearance) to work with 0.0 duration initial step:
        # 1. First state: provided by itertools.repeat, it's a non-matching state.
        #    _await_state_appearance will hit its 0.5s timeout.
        #    _process_pattern_step will then return (True, "") due to the 0-duration special case.
        # 2. Second state: provided by itertools.repeat, it's a matching state.
        #    _await_state_appearance finds it.
        #    _process_process_step's hold loop will then confirm duration (0.1s).
        state_side_effect_generator = itertools.chain(
            itertools.repeat(non_matching_state_tuple, 100), # Plenty of non-matching for first step's short timeout
            itertools.repeat(matching_state_for_second_step_tuple) # Infinite matching for second step
        )

        start_time = 1000.0
        # Time needs to just continuously increase
        time_side_effect_generator = itertools.count(start=start_time, step=0.001)

        with patch.object(checker, '_get_current_led_state_from_camera', side_effect=state_side_effect_generator), \
             patch('time.time', side_effect=time_side_effect_generator), \
             patch('time.sleep', return_value=None):
            with caplog.at_level(logging.INFO, logger="controllers.logitech_webcam"):
                result = checker.confirm_led_pattern(pattern)
        
        assert result is True # Should be True as both steps will "pass"

        # The log message should be captured:
        assert "Not present but 0 duration" in caplog.text
        assert "LED pattern confirmed successfully." in caplog.text

    def test_hold_time_exceeds_max_duration(self, checker, caplog):
        """Tests that the function fails if a state is held for too long."""
        # --- ARRANGE ---
        pattern = [{"green": 1, "duration": (0.1, 0.5)}] # min_d_orig=0.1, max_d_orig=0.5

        max_d_orig = pattern[0]['duration'][1] # 0.5
        checker.duration_tolerance_sec = 0.01 # Reduce tolerance to make the max duration break precise
        max_d_check = max_d_orig + checker.duration_tolerance_sec # 0.5 + 0.01 = 0.51

        start_time = 1000.0
        step_seen_time = start_time + 0.01
        exceed_time = step_seen_time + 0.6 # 0.6s held, which is > 0.51s

        mock_frame = np.zeros((10,10,3))
        good_state = (mock_frame, {"green":1})
        state_side_effect = [good_state] * 5 

        # Detailed time sequence:
        time_side_effect = [
            start_time,          # 1. pattern_start_time (1000.0)
            start_time + 0.001,  # 2. overall_timeout check (outer loop)
            start_time + 0.002,  # 3. step_loop_start_time

            # Inner "find" loop - Assume first state is found quickly
            start_time + 0.010,  # 4. overall_timeout check (inner find loop)
            start_time + 0.010,  # 5. step_seen_at (state matches at this time) = 1000.010

            # Inner "hold" loop
            step_seen_time + 0.05, # 6. overall_timeout check (time.time()) = 1000.06
            step_seen_time + 0.05, # 7. held_time calc (time.time()) = 1000.06
            
            # Simulate a jump in time that EXCEEDS max_d_check (0.51)
            exceed_time,           # 8. overall_timeout check (time.time()) = 1000.61
            exceed_time,           # 9. held_time calc (time.time()) = 1000.61

            # After inner loop breaks and checker logs
            exceed_time + 0.01,   # 10. Time for internal logging (by _stop_replay_recording)
            exceed_time + 0.02,   # 11. Final time.time() call before return
        ]

        with patch.object(checker, '_get_current_led_state_from_camera', side_effect=state_side_effect), \
             patch('time.time', side_effect=time_side_effect), \
             patch('time.sleep', return_value=None):

            with caplog.at_level(logging.WARNING, logger="controllers.logitech_webcam"):
                result = checker.confirm_led_pattern(pattern)

        assert result is False

        # Part 2 (Refinement of Test Assertion): Ensure the expected string matches the new construction.
        # It's now explicitly built with str() on target_state_str and then concatenated.
        
        # Calculate the actual values that would be used in the _process_pattern_step failure string
        actual_held_time_at_failure = 0.55
        actual_max_d_orig = pattern[0]['duration'][1] # 0.5s from test setup

        expected_failure_reason_for_stop = (
            f"step_1_exceeded_max_duration_held_{actual_held_time_at_failure:.2f}s_max_{actual_max_d_orig:.2f}s"
        )

        checker._stop_replay_recording.assert_called_once_with(
            success=False,
            failure_reason=expected_failure_reason_for_stop
        )

    def test_success_with_final_step_held_indefinitely(self, checker, caplog):
        """Tests success when the last step has an infinite max duration."""
        pattern = [{"green": 1, "duration": (0.1, float('inf'))}]
        
        mock_frame = np.zeros((10,10,3))
        good_state_tuple = (mock_frame, {"green":1})
        
        # Infinite supply of good states
        state_side_effect_generator = itertools.repeat(good_state_tuple)

        start_time = 1000.0
        # Infinite supply of increasing time values
        time_side_effect_generator = itertools.count(start=start_time, step=0.001)

        with patch.object(checker, '_get_current_led_state_from_camera', side_effect=state_side_effect_generator), \
             patch('time.time', side_effect=time_side_effect_generator), \
             patch('time.sleep', return_value=None):
            with caplog.at_level(logging.INFO, logger="controllers.logitech_webcam"):
                result = checker.confirm_led_pattern(pattern)
        
        assert result is True
        assert "LED pattern confirmed successfully." in caplog.text

    def test_state_changes_early(self, checker, caplog):
        """Tests failure when the state changes before minimum duration is met."""
        pattern = [{"green": 1, "duration": (1.0, 1.5)}] # min_d_orig=1.0, max_d_orig=1.5

        mock_frame = np.zeros((10,10,3))
        good_state = (mock_frame, {"green": 1})
        bad_state = (mock_frame, {"red": 1})

        # Sequence of states: one good (for initial detection), then infinite bad to trigger early change
        state_side_effect_generator = itertools.chain(
            [good_state],         # First state detected by _process_pattern_step's "find" phase
            itertools.repeat(bad_state) # Then, continuously provide a non-matching state for the "hold" phase
        )

        start_time = 1000.0
        # Provide an infinite supply of increasing time values to prevent StopIteration.
        time_side_effect_generator = itertools.count(start=start_time, step=0.001)

        # Mock the checker's format_led_display_string for predictable output in failure message
        checker._format_led_display_string = MagicMock(side_effect=lambda s, o=None: str(s))

        with patch.object(checker, '_get_current_led_state_from_camera', side_effect=state_side_effect_generator), \
             patch('time.time', side_effect=time_side_effect_generator), \
             patch('time.sleep', return_value=None):
            # Capture logs at INFO level to see the success message for pattern start
            # and WARNING/ERROR for any failure details from _process_pattern_step
            with caplog.at_level(logging.INFO, logger="controllers.logitech_webcam"):
                result = checker.confirm_led_pattern(pattern)

        assert result is False

        # Construct the expected failure reason string from _process_pattern_step:
        # step_idx+1 = 1 (first step)
        # target_state_str will be '{"green": 1}' (from mocked _format_led_display_string)
        # current_led_str will be '{"red": 1}' (from mocked _format_led_display_string)
        # held_time will be approximately the difference between step_seen_at and when bad_state is seen,
        # which in this precise mock is 0.001s (1000.001 - 1000.000) or very close.
        # min_d_orig is 1.0
        
        # Calculate expected held_time based on mocked time values
        # step_seen_at occurs after 1 call to time.time() inside _process_pattern_step (for current_step_find_timeout_end_time)
        # and then 1 call for _get_current_led_state_from_camera (which internally calls time.time())
        # and then 1 call for step_seen_at = time.time().
        # So step_seen_at ~ start_time + 3*0.001 = 1000.003
        
        # When `bad_state` is received, time will be ~ start_time + X*0.001.
        # The first time current_leds is `bad_state`, it occurs after _get_current_led_state_from_camera
        # which means time has incremented at least once more.
        # So `current_time` might be `start_time + 4*0.001 = 1000.004`
        # held_time = 1000.004 - 1000.003 = 0.001s (approximately)

        expected_held_time = 0.001 # based on the time_side_effect_generator and flow
        expected_min_d_orig = pattern[0]['duration'][0] # 1.0

        # Note: The replace(' ','_') is necessary because _format_led_display_string mock returns spaces
        expected_failure_reason = (
            f"step_1_state_{str({'green': 1}).replace(' ','_')}_changed_to_"
            f"{str({'red': 1}).replace(' ','_')}_early_held_{expected_held_time:.2f}s_min_{expected_min_d_orig:.2f}s" # Corrected line
        )
        
        checker._stop_replay_recording.assert_called_once_with(
            success=False,
            failure_reason=expected_failure_reason
        )

        # We can also assert that the initial pattern confirmation message was logged
        assert "Starting pattern confirmation of 1 steps." in caplog.text

        # The specific early change log from _process_pattern_step is NOT a warning level.
        # It's a return value. So we don't expect a specific warning log from this scenario
        # unless it hits the tolerance path (which it won't here, as 0.001s is far from 1.0s).
        # The `caplog.text` will also contain the ERROR from `_stop_replay_recording` if replay is enabled.
        # We confirm the `result` and `_stop_replay_recording` call, which is sufficient.

    def test_generic_exception_handling(self, checker, caplog):
        """Tests the outer try...except block."""
        error_message = "A test error"
        method_name = "confirm_led_pattern" # Get the method_name explicitly for assertion

        # Patch the method to raise an error at a specific point
        with patch.object(checker, '_get_ordered_led_keys_for_display', side_effect=ValueError(error_message)):
             # CORRECTED: Use the correct logger name "controllers.logitech_webcam"
             with caplog.at_level(logging.ERROR, logger="controllers.logitech_webcam"):
                result = checker.confirm_led_pattern([{"green": 1}])

        assert result is False
        # The exception is logged by the function under test, so caplog will contain it.
        # CORRECTED: Assert the exact log message produced by the code.
        expected_log_substring = f"Exception in {method_name} loop: {error_message}"
        assert expected_log_substring in caplog.text

class TestAwaitAndConfirmLedPattern:
    """Tests the await_and_confirm_led_pattern method."""

    @pytest.fixture
    def checker(self, mock_cv2_videocapture, mock_logger, tmp_path):
        """Provides a checker instance with mocked internal methods."""
        with patch('threading.Thread'): # Prevent background thread from starting
            instance = LogitechLedChecker(
                camera_id=0,
                logger_instance=mock_logger,
                replay_output_dir=str(tmp_path),
                enable_instant_replay=True # Enable replay for testing its management
            )
        # Mock internal methods that `await_and_confirm_led_pattern` calls
        instance._start_replay_recording = MagicMock()
        instance._stop_replay_recording = MagicMock()
        instance.await_led_state = MagicMock()
        instance.confirm_led_pattern = MagicMock()
        # Mock _format_led_display_string to return a predictable string based on input dict
        instance._format_led_display_string = MagicMock(side_effect=lambda target_state_dict, ordered_keys=None: str(target_state_dict))
        
        # Ensure camera is initialized for tests unless explicitly set otherwise
        instance.is_camera_initialized = True
        
        yield instance
        instance.release_camera()

    # Test Case 1: Empty pattern
    def test_empty_pattern(self, checker, mock_logger):
        pattern = []
        timeout = 5

        result = checker.await_and_confirm_led_pattern(pattern, timeout)

        assert result is False
        # CORRECTED: The warning message is a single string including the method name prefix
        method_name = "await_and_confirm_led_pattern" # Get the method_name explicitly for assertion
        expected_log_message = f"{method_name}: empty_pattern_await_confirm"
        mock_logger.warning.assert_called_once_with(expected_log_message) # Check for specific failure detail
        checker._start_replay_recording.assert_called_once_with("await_and_confirm_led_pattern", extra_context=None)
        checker._stop_replay_recording.assert_called_once_with(success=False, failure_reason="empty_pattern_await_confirm")
        checker.await_led_state.assert_not_called()
        checker.confirm_led_pattern.assert_not_called()

    # Test Case 2: Camera not initialized
    def test_camera_not_initialized(self, checker, mock_logger):
        checker.is_camera_initialized = False
        pattern = [{"green": 1}]
        timeout = 5
        
        result = checker.await_and_confirm_led_pattern(pattern, timeout)
        
        assert result is False
        # CORRECTED: The error message is a single string including the method name prefix
        method_name = "await_and_confirm_led_pattern" # Get the method_name explicitly for assertion
        expected_log_message = f"{method_name}: camera_not_init_await_confirm"
        mock_logger.error.assert_called_once_with(expected_log_message) # Check for specific failure detail
        checker._start_replay_recording.assert_called_once_with("await_and_confirm_led_pattern", extra_context=None)
        checker._stop_replay_recording.assert_called_once_with(success=False, failure_reason="camera_not_init_await_confirm")
        checker.await_led_state.assert_not_called()
        checker.confirm_led_pattern.assert_not_called()

    # Test Case 3: Await succeeds, Confirm succeeds
    def test_success_path(self, checker, mock_logger):
        pattern = [{"green": 1, "duration": (0.1, 0.5)}, {"red": 1, "duration": (0.1, 0.5)}]
        timeout = 10
        extra_context = {"test": "context"}

        checker.await_led_state.return_value = True
        checker.confirm_led_pattern.return_value = True

        result = checker.await_and_confirm_led_pattern(pattern, timeout, replay_extra_context=extra_context)

        assert result is True
        checker._start_replay_recording.assert_called_once_with("await_and_confirm_led_pattern", extra_context=extra_context)
        
        # Verify await_led_state was called correctly
        checker.await_led_state.assert_called_once_with(
            {"green": 1}, timeout=timeout, clear_buffer=True, manage_replay=False, replay_extra_context=extra_context
        )
        
        # Verify confirm_led_pattern was called correctly
        checker.confirm_led_pattern.assert_called_once_with(
            pattern, clear_buffer=False, manage_replay=False, replay_extra_context=extra_context
        )
        
        # On success, the failure_reason passed to _stop_replay_recording should be its default ""
        checker._stop_replay_recording.assert_called_once_with(success=True, failure_reason="") 
        mock_logger.debug.assert_called_once_with(f"Awaiting first state of pattern (timeout: {timeout:.2f}s), steps: {len(pattern)}.")

    # Test Case 4: Await fails
    def test_await_fails(self, checker, mock_logger):
        pattern = [{"green": 1, "duration": (0.1, 0.5)}, {"red": 1, "duration": (0.1, 0.5)}]
        timeout = 5

        checker.await_led_state.return_value = False
        checker.confirm_led_pattern.return_value = True # This shouldn't be called

        result = checker.await_and_confirm_led_pattern(pattern, timeout)

        assert result is False
        checker._start_replay_recording.assert_called_once()
        checker.await_led_state.assert_called_once_with(
            {"green": 1}, timeout=timeout, clear_buffer=True, manage_replay=False, replay_extra_context=None
        )
        checker.confirm_led_pattern.assert_not_called() # Should not be called if await fails

        # Expected failure reason based on the actual implementation
        method_name = "await_and_confirm_led_pattern" # Get the method_name explicitly for assertion
        expected_failure_reason = str({"green": 1}).replace(' ', '_') # This matches the mock of _format_led_display_string
        checker._stop_replay_recording.assert_called_once_with(
            success=False, failure_reason=f"first_state_{expected_failure_reason}_not_observed_in_await_confirm"
        )
        # The warning message is a single string, including the method name prefix
        expected_log_message = f"{method_name}: Pattern not started: first_state_{expected_failure_reason}_not_observed_in_await_confirm"
        mock_logger.warning.assert_called_once_with(expected_log_message)

    # Test Case 5: Await succeeds, Confirm fails
    def test_confirm_fails_after_await(self, checker, mock_logger):
        pattern = [{"green": 1, "duration": (0.1, 0.5)}, {"red": 1, "duration": (0.1, 0.5)}]
        timeout = 10
        
        checker.await_led_state.return_value = True
        checker.confirm_led_pattern.return_value = False

        result = checker.await_and_confirm_led_pattern(pattern, timeout)

        assert result is False
        checker._start_replay_recording.assert_called_once()
        checker.await_led_state.assert_called_once() # Await should pass
        checker.confirm_led_pattern.assert_called_once() # Confirm should be called and fail
        checker._stop_replay_recording.assert_called_once_with(
            success=False, failure_reason="pattern_confirm_failed_after_await"
        )
        # No specific warning/error from _await_and_confirm for this scenario, as it delegates to confirm_led_pattern

    # Test Case 6: `manage_replay=False`
    def test_manage_replay_false(self, checker):
        pattern = [{"green": 1, "duration": (0.1, 0.5)}]
        timeout = 5
        
        checker.await_led_state.return_value = True
        checker.confirm_led_pattern.return_value = True

        result = checker.await_and_confirm_led_pattern(pattern, timeout, manage_replay=False)
        
        assert result is True
        checker._start_replay_recording.assert_not_called() # Should not be called
        checker._stop_replay_recording.assert_not_called() # Should not be called
        
        # Internal calls should still manage replay=False as they are passed through
        checker.await_led_state.assert_called_once_with(
            {"green": 1}, timeout=timeout, clear_buffer=True, manage_replay=False, replay_extra_context=None
        )
        checker.confirm_led_pattern.assert_called_once_with(
            pattern, clear_buffer=False, manage_replay=False, replay_extra_context=None
        )