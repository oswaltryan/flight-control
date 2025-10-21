# Segmentation Fault Investigation – scripts/stress_loop_test.py

## 1. Crash Summary
- Observed `zsh: segmentation fault  python scripts/stress_loop_test.py` without hardware connected.
- Reviewed `crashguard.log`; fault occurs in `controllers/logitech_webcam.py` within `_update_frame_thread` and `_clear_camera_buffer`.

## 2. Initial Code Inspection
- Inspected `controllers/logitech_webcam.py` around `_update_frame_thread` and `_clear_camera_buffer`; segfault occurs while calling `cv2.VideoCapture.read()` on background thread.
- Noted `confirm_led_solid()` clears the buffer by synchronously reading `CAMERA_BUFFER_SIZE_FRAMES` frames before starting LED polling.

## 3. Hypothesis
- Concurrent calls to `cv2.VideoCapture.read()` from `_update_frame_thread` and `_clear_camera_buffer()` likely race; OpenCV's capture object is not thread-safe, explaining occasional segfaults without hardware.
- Plan to rework `_clear_camera_buffer()` to flush `replay_buffer` via synchronization instead of direct capture reads.

## 4. Fix Implementation
- Added `self._frame_thread_active` flag and `buffer_clear_wait_timeout_sec` to track capture thread activity.
- Wrapped `_update_frame_thread()` loop in `try/finally` to manage the activity flag reliably.
- Replaced `_clear_camera_buffer()` with logic that clears `replay_buffer` under lock and optionally waits for a fresh frame instead of calling `cap.read()` directly.
- Updated `release_camera()` to reset the activity flag and adjusted unit test to assert the new buffer-clearing behaviour.

## 5. Verification
- Ran `pytest tests/test_logitech_webcam_controller.py::TestLogitechLedCheckerMethods::test_clear_camera_buffer -q`; test passes after update.
