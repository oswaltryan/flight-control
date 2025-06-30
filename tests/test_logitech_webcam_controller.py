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
        checker._stop_replay_recording.assert_called_with(success=False, failure_reason="timeout_await_[TARGET]")
        mock_logger.warning.assert_called_once_with("Timeout: [TARGET] not observed.")
        checker._log_final_state.assert_called_once() # Ensure final state is logged on timeout

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
        mock_logger.warning.assert_called_once_with("Timeout: [TARGET] not observed.")

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
        pattern = [{"green": 1, "duration": (0.1, 1.0)}]

        max_dur_sum = sum(p.get('duration',(0,1))[1] for p in pattern if p.get('duration',[0,0])[1]!=float('inf'))
        inf_steps = sum(1 for p in pattern if p.get('duration',[0,0])[1]==float('inf'))
        overall_timeout = max_dur_sum + inf_steps*10.0 + len(pattern)*5.0 + 15.0 # This calculates to 1.0 + 0 + 5.0 + 15.0 = 21.0

        mock_frame = np.zeros((10,10,3))
        
        # CORRECTED: Use itertools.repeat for an infinite supply of non-matching states.
        # This prevents StopIteration from _get_current_led_state_from_camera.
        state_side_effect = itertools.repeat((mock_frame, {"blue": 0}))

        # CORRECTED: Use itertools.count for time.time() to ensure an infinite supply of time values.
        # This prevents StopIteration from time.time() itself.
        start_time_val = 1000.0
        time_side_effect = itertools.count(start=start_time_val, step=0.001)

        checker._stop_replay_recording = MagicMock()


        with patch.object(checker, '_get_current_led_state_from_camera', side_effect=state_side_effect), \
             patch('time.time', side_effect=time_side_effect), \
             patch('time.sleep', return_value=None):

            with caplog.at_level(logging.ERROR, logger="controllers.logitech_webcam"):
                 result = checker.confirm_led_pattern(pattern, clear_buffer=False)

        assert result is False
        # The assertion for the log message content remains correct, as the production code
        # is expected to log this specific message when the overall timeout occurs.
        expected_log_substring = f"confirm_led_pattern Error: overall_timeout_pattern_at_step_1"
        assert expected_log_substring in caplog.text

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
        non_matching_state = (mock_frame, {"blue": 0}) # For 1st step (green) - should NOT match
        matching_state_for_second_step = (mock_frame, {"red": 1}) # For 2nd step (red) - should match

        start_time = 1000.0
        
        # CORRECTED: Expanded time_side_effect to cover all anticipated calls, including logging.
        # This list needs to be long enough and values carefully chosen to simulate progression.
        time_side_effect = [
            start_time,          # 1. pattern_start_time
            start_time + 0.001,  # 2. overall_timeout check (outer while)
            start_time + 0.002,  # 3. step_loop_start_time (for green)

            # Inner "find" loop for green (0.0 duration)
            start_time + 0.003,  # 4. overall_timeout check (inner find)
            start_time + 0.004,  # 5. _get_current_led_state_from_camera (internal time.time)
            # state_side_effect[0] is non_matching_state. `_matches_state` is false.
            start_time + 0.300,  # 6. time.time() for `(time.time()-step_loop_start_time > 0.25)` -> 1000.300 - 1000.002 = 0.298 > 0.25. Breaks.

            start_time + 0.301,  # 7. Logger for "Skipped (0 dur)" (internal time.time)

            # Outer loop continues to second step (red)
            start_time + 0.302,  # 8. overall_timeout check (outer while)
            start_time + 0.303,  # 9. step_loop_start_time (for red)

            # Inner "find" loop for red
            start_time + 0.304,  # 10. overall_timeout check (inner find)
            start_time + 0.305,  # 11. _get_current_led_state_from_camera (internal time.time)
            # state_side_effect[1] is matching_state_for_second_step. `_matches_state` is true.
            start_time + 0.306,  # 12. step_seen_at (time.time())

            # Inner "hold" loop for red
            start_time + 0.307,  # 13. overall_timeout check (inner hold)
            start_time + 0.308,  # 14. _get_current_led_state_from_camera (internal time.time)
            start_time + 0.406,  # 15. held_time calc (time.time()). Held for 1000.406 - 1000.306 = 0.100s. Meets min_d_check (0.1).

            start_time + 0.407,  # 16. Logger for step completion (internal time.time)

            # Outer loop finishes
            start_time + 0.408,  # 17. Logger for "LED pattern confirmed" (internal time.time)
            # Add a few extra for robustness, though 17 should be minimum.
            start_time + 0.409,
            start_time + 0.410,
        ]

        state_side_effect = [
            non_matching_state, # For the first step (green)
            matching_state_for_second_step, # For the second step (red)
            matching_state_for_second_step, # More matching states if the hold loop runs more than once
            matching_state_for_second_step,
            matching_state_for_second_step,
            matching_state_for_second_step,
            matching_state_for_second_step,
            matching_state_for_second_step,
            matching_state_for_second_step,
            matching_state_for_second_step,
        ]

        with patch.object(checker, '_get_current_led_state_from_camera', side_effect=state_side_effect), \
             patch('time.time', side_effect=time_side_effect), \
             patch('time.sleep', return_value=None):
            with caplog.at_level(logging.INFO, logger="controllers.logitech_webcam"):
                result = checker.confirm_led_pattern(pattern)
        
        assert "Skipped (0 dur)" in caplog.text
        # Assert overall success, as this path should lead to success
        assert result is True # Assert the function's return value

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
        expected_failure_reason_for_stop = "Failure to detect: " + str("[TARGET]") + \
                                         " exceeded max duration " + f"{max_d_check:.2f}s"
        checker._stop_replay_recording.assert_called_once_with(
            success=False,
            failure_reason=expected_failure_reason_for_stop
        )

    def test_success_with_final_step_held_indefinitely(self, checker, caplog):
        """Tests success when the last step has an infinite max duration."""
        pattern = [{"green": 1, "duration": (0.1, float('inf'))}]
        
        mock_frame = np.zeros((10,10,3))
        good_state = (mock_frame, {"green":1})

        # Sequence of time.time() calls:
        # It needs enough iterations to pass the min_d_orig (0.1)
        start_time = 1000.0
        
        # CORRECTED: Expanded time_side_effect to ensure enough values for all time.time() calls,
        # including internal logging calls.
        time_side_effect = [
            start_time,          # 1. pattern_start_time
            start_time + 0.001,  # 2. overall_timeout check (outer loop)
            start_time + 0.002,  # 3. step_loop_start_time

            # Inner "find" loop
            start_time + 0.010,  # 4. overall_timeout check (inner find loop)
            start_time + 0.010,  # 5. step_seen_at (state matches at this time)

            # Inner "hold" loop (needs to be held for at least 0.1s from step_seen_at)
            start_time + 0.100,  # 6. overall_timeout check (inner hold loop)
            start_time + 0.110,  # 7. held_time calc (1000.110 - 1000.010 = 0.100, meets min_d_orig)
            
            # Logger calls made after `held_time >= min_d_check` and `current_step_idx += 1`
            start_time + 0.111,  # 8. internal logger.info for step completion
            
            # After loop finishes and `success_flag` is set, final success message is logged
            start_time + 0.112,  # 9. internal logger.info for overall pattern success
        ]

        with patch.object(checker, '_get_current_led_state_from_camera', return_value=(None, {"green":1})), \
             patch('time.time', side_effect=time_side_effect), \
             patch('time.sleep', return_value=None):
            # CORRECTED: Use the correct logger name "controllers.logitech_webcam"
            with caplog.at_level(logging.INFO, logger="controllers.logitech_webcam"):
                result = checker.confirm_led_pattern(pattern)
        
        assert result is True
        assert "LED pattern confirmed" in caplog.text

    def test_state_changes_early(self, checker, caplog):
        """Tests failure when the state changes before minimum duration is met."""
        pattern = [{"green": 1, "duration": (1.0, 1.5)}]
        
        mock_frame = np.zeros((10,10,3))
        good_state = (mock_frame, {"green": 1})
        bad_state = (mock_frame, {"red": 1})

        # Sequence of states from _get_current_led_state_from_camera:
        # 1. Finds the good state
        # 2. Immediately changes to bad state in the next check.
        state_side_effect = [good_state, bad_state]
        
        start_time = 1000.0
        step_seen_time = start_time + 0.01 # Time when step is seen
        break_time = step_seen_time + 0.05 # Time when state changes (too early)

        # Time sequence:
        time_side_effect = [
            start_time,      # pattern_start_time
            start_time,      # step_loop_start_time
            step_seen_time,  # step_seen_at
            
            break_time,      # 1st call in "hold" loop (overall_timeout check)
            break_time,      # 1st call in "hold" loop (held_time calc)
            
            break_time + 0.01, # Final overall_timeout check after loop breaks
        ]

        with patch.object(checker, '_get_current_led_state_from_camera', side_effect=state_side_effect), \
             patch('time.time', side_effect=time_side_effect), \
             patch('time.sleep', return_value=None):
            # CORRECTED: Use the correct logger name "controllers.logitech_webcam"
            with caplog.at_level(logging.WARNING, logger="controllers.logitech_webcam"):
                result = checker.confirm_led_pattern(pattern)

        assert result is False
        assert "Pattern ended inconclusively" in caplog.text
        assert "changed_to" in caplog.text

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