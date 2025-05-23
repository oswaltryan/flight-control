# Directory: controllers
# Filename: unified_controller.py
#!/usr/bin/env python3

import logging
import sys
import os
import time # Added for the __main__ test block
# import traceback # Not strictly needed if using exc_info=True with logging
from pprint import pprint

# --- Path Setup ---
CONTROLLERS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CONTROLLERS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Get a logger for this module. Name will be 'controllers.unified_controller'.
# Assumed to be configured by a central setup_logging() call.
module_logger = logging.getLogger(__name__)

try:
    from hardware.phidget_io_controller import PhidgetController, DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG
    # MODIFIED: Import DEFAULT_DURATION_TOLERANCE_SEC to use as a default if not provided by caller
    from camera.camera_controller import LogitechLedChecker, DEFAULT_DURATION_TOLERANCE_SEC as CAMERA_DEFAULT_TOLERANCE
    from Phidget22.PhidgetException import PhidgetException
    from camera.led_dictionaries import LEDs
    from usb_tool import find_apricorn_device
    # If EventData is needed for type hinting:
    # from transitions import EventData # Or from typing import Any if you don't want direct dependency
except ImportError as e_import:
    module_logger.critical(f"Critical Import Error in unified_controller.py: {e_import}. Check paths and dependencies.", exc_info=True)
    raise


class UnifiedController:
    def __init__(self,
                 script_map_config=None,
                 camera_id: int = 0,
                 led_configs=None,
                 display_order: list = None,
                 logger_instance=None,
                 led_duration_tolerance_sec: float = None): # MODIFIED: Added led_duration_tolerance_sec
        """
        Initializes a unified controller for Phidgets and Logitech LED checking.
        Logging is assumed to be pre-configured globally.
        """
        self.logger = logger_instance if logger_instance else module_logger

        self.phidget_config_to_use = script_map_config if script_map_config is not None else DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG

        phidget_ctrl_logger = self.logger.getChild("Phidget")
        camera_ctrl_logger = self.logger.getChild("Camera")

        self._phidget_controller = None
        try:
            self._phidget_controller = PhidgetController(
                script_map_config=self.phidget_config_to_use,
                logger_instance=phidget_ctrl_logger
            )
        except Exception as e_phidget_init:
            self.logger.error(f"Failed to initialize PhidgetController component: {e_phidget_init}", exc_info=True)

        self._camera_checker = None
        # MODIFIED: Determine tolerance to pass to LogitechLedChecker
        self.effective_led_duration_tolerance = led_duration_tolerance_sec if led_duration_tolerance_sec is not None else CAMERA_DEFAULT_TOLERANCE
        
        try:
            self._camera_checker = LogitechLedChecker(
                camera_id=camera_id,
                led_configs=led_configs,
                display_order=display_order,
                logger_instance=camera_ctrl_logger,
                duration_tolerance_sec=self.effective_led_duration_tolerance # MODIFIED: Pass tolerance
            )
            if not self._camera_checker.is_camera_initialized:
                self.logger.error(f"LogitechLedChecker component FAILED to initialize camera ID {camera_id}. Camera functions will not work.")
        except Exception as e_camera_init:
            self.logger.error(f"Failed to initialize LogitechLedChecker component for camera ID {camera_id}: {e_camera_init}", exc_info=True)


    ### LOWER LEVEL COMMANDS ###
    # --- PhidgetController Method Delegation ---
    def on(self, channel_name):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'on'.")
            return
        self._phidget_controller.on(channel_name)

    def off(self, channel_name):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'off'.")
            return
        self._phidget_controller.off(channel_name)

    def hold(self, channel_name, duration_ms=200):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'hold'.")
            return
        self._phidget_controller.hold(channel_name, duration_ms)

    def press(self, channel_name, duration_ms=200):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'press'.")
            return
        self._phidget_controller.press(channel_name, duration_ms=duration_ms)

    def sequence(self, pin_sequence: list, press_duration_ms: float = 100, pause_duration_ms: float = 100):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'sequence'.")
            return
        self._phidget_controller.sequence(pin_sequence, press_duration_ms, pause_duration_ms)

    def read_input(self, channel_name):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'read_input'.")
            return None
        return self._phidget_controller.read_input(channel_name)

    def wait_for_input(self, channel_name, expected_state, timeout_s=5, poll_interval_s=0.05):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'wait_for_input'.")
            return False
        return self._phidget_controller.wait_for_input(channel_name, expected_state, timeout_s, poll_interval_s)

    # --- LogitechLedChecker Method Delegation (Low-Level Primitives) ---
    @property
    def is_camera_ready(self) -> bool:
        return self._camera_checker is not None and self._camera_checker.is_camera_initialized

    def confirm_led_solid(self, state: dict, minimum: float = 2, timeout: float = 10,
                                 fail_leds: list = None, clear_buffer: bool = True) -> bool:
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for confirm_led_solid.")
            return False
        return self._camera_checker.confirm_led_solid(state, minimum, timeout, fail_leds, clear_buffer)

    def confirm_led_solid_strict(self, state: dict, minimum: float, clear_buffer: bool = True) -> bool:
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for confirm_led_solid_strict.")
            return False
        return self._camera_checker.confirm_led_solid_strict(state, minimum, clear_buffer)

    def await_led_state(self, state: dict, timeout: float = 1,
                               fail_leds: list = None, clear_buffer: bool = True) -> bool:
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for await_led_state.")
            return False
        return self._camera_checker.await_led_state(state, timeout, fail_leds, clear_buffer)

    def confirm_led_pattern(self, pattern: list, clear_buffer: bool = True) -> bool:
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for confirm_led_pattern.")
            return False
        return self._camera_checker.confirm_led_pattern(pattern, clear_buffer)

    def await_and_confirm_led_pattern(self, pattern: list, timeout: float,
                                             clear_buffer: bool = True) -> bool:
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for await_and_confirm_led_pattern.")
            return False
        return self._camera_checker.await_and_confirm_led_pattern(pattern, timeout, clear_buffer)

    # --- Resource Management ---
    def close(self):
        if self._camera_checker and hasattr(self._camera_checker, 'release_camera'):
            try:
                self._camera_checker.release_camera()
            except Exception as e_cam_close:
                self.logger.error(f"Error releasing camera component: {e_cam_close}", exc_info=True)
        
        if self._phidget_controller and hasattr(self._phidget_controller, 'close_all'):
            try:
                self._phidget_controller.close_all()
            except Exception as e_phid_close:
                self.logger.error(f"Error closing phidget component: {e_phid_close}", exc_info=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def confirm_enum(self, stable_min=5, timeout=15):
        self.logger.info(f"Attempting to confirm Drive enumeration (USB)...")
        self.logger.info(f"Waiting for stable, available drive (stable_min: {stable_min}, timeout: {timeout})...")
        DUT_ping_1 = find_apricorn_device()
        if len(DUT_ping_1) != 0:
            self.logger.info("Device enumerated at 0.0s, verifying stability...")
        for device in DUT_ping_1:
            if device.idProduct == '0310':
                ping_1_iSerial = device.iSerial
        time.sleep(stable_min)
        DUT_ping_2 = find_apricorn_device()
        for device in DUT_ping_2:
            if device.iSerial == ping_1_iSerial:
                self.logger.info(f"Drive stable for {float(stable_min)}s:")
                self.logger.info(f" VID:PID  [Firm] @USB iSerial      iProduct")
                self.logger.info(f"{device.idVendor}:{device.idProduct} [{device.bcdDevice}] @{device.bcdUSB} {device.iSerial} {device.iProduct}")

    # --- FSM Event Handling Callbacks (High-Level) ---
    def handle_post_failure(self, event_data) -> None: # event_data is passed by transitions
        """Handles actions to take when POST fails."""
        details = "No details provided"
        if event_data and hasattr(event_data, 'kwargs') and event_data.kwargs:
            details = event_data.kwargs.get('details', details)
        self.logger.error(f"UnifiedController: Handling POST failure. Details: {details}")
        # Add any specific actions UnifiedController should take on POST failure
        # e.g., self.off("all_power_relays_if_any")
        # e.g., self.log_to_external_monitoring_system("POST_FAIL", details)

    def handle_critical_error(self, event_data) -> None: # event_data is passed by transitions
        """Handles actions to take on a critical error."""
        details = "No details provided"
        if event_data and hasattr(event_data, 'kwargs') and event_data.kwargs:
            details = event_data.kwargs.get('details', details)
        self.logger.critical(f"UnifiedController: Handling CRITICAL error. Details: {details}")
        # Add any specific actions UnifiedController should take on critical error
        # e.g., attempt a safe shutdown, log extensively.

# --- For direct testing of unified_controller.py if needed ---
if __name__ == '__main__':
    print("Running a direct test of UnifiedController (from controllers/unified_controller.py)...")
    try:
        from utils.logging_config import setup_logging
        setup_logging(default_log_level=logging.DEBUG)
    except ImportError:
        print("CRITICAL: Could not import 'utils.logging_config.setup_logging' for direct test. Using basicConfig.")
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    direct_test_logger = logging.getLogger("UnifiedControllerDirectTest")
    direct_test_logger.info("UnifiedController direct test logging configured and starting...")

    uc_instance_for_test = None
    try:
        uc_instance_for_test = UnifiedController(
            logger_instance=direct_test_logger.getChild("TestUCInstance"),
            camera_id=0,
            led_duration_tolerance_sec=0.08 # Example: Test with a specific tolerance
        )
        direct_test_logger.info(f"UnifiedController instance for test created. Camera Ready: {uc_instance_for_test.is_camera_ready}")
        direct_test_logger.info(f"Effective LED duration tolerance for this instance: {uc_instance_for_test.effective_led_duration_tolerance:.3f}s")
        
        if uc_instance_for_test._phidget_controller:
            direct_test_logger.info("Testing Phidget: Turning 'usb3' ON then OFF.") # Simplified test message
            uc_instance_for_test.on("usb3") # Test new high-level method
            time.sleep(1)
            uc_instance_for_test.off("usb3") # Test new high-level method
            direct_test_logger.info("Phidget 'usb3' power cycle test complete.")
        else:
            direct_test_logger.warning("Phidget component of UnifiedController not initialized. Skipping Phidget tests.")

        # Mock EventData for testing handler methods
        class MockEventData:
            def __init__(self, kwargs=None):
                self.kwargs = kwargs if kwargs else {}
                self.transition = type('MockTransition', (), {'source': 'test_source', 'dest': 'test_dest'})()
                self.event = type('MockEvent', (), {'name': 'test_event'})()
                self.model = uc_instance_for_test # or a mock model

        direct_test_logger.info("Testing handle_post_failure...")
        uc_instance_for_test.handle_post_failure(MockEventData(kwargs={'details': 'Test POST failure details'}))
        
        direct_test_logger.info("Testing handle_critical_error...")
        uc_instance_for_test.handle_critical_error(MockEventData(kwargs={'details': 'Test CRITICAL error details'}))


        if uc_instance_for_test.is_camera_ready:
            direct_test_logger.info("--- Testing Camera Functions (with tolerance) ---")
            # Example: Test confirm_led_solid with a short minimum that might only pass due to tolerance
            test_state = {"red": 1, "green": 0, "blue": 0} # Example: Red LED only
            test_min_duration = 0.1 # A very short duration
            direct_test_logger.info(f"Attempting confirm_led_solid for {test_state} with min_duration {test_min_duration}s. "
                                    f"Effective min with tolerance: {max(0, test_min_duration - uc_instance_for_test.effective_led_duration_tolerance):.3f}s")
            # input(f"Ensure only RED LED is on and press Enter to test confirm_led_solid for {test_min_duration}s...")
            # success = uc_instance_for_test.confirm_led_solid(test_state, minimum=test_min_duration, timeout=2)
            # direct_test_logger.info(f"confirm_led_solid result: {'SUCCESS' if success else 'FAILURE'}")

            # Removed startup_self_test from here as it's a very specific sequence
            # and this direct test is more for unit-testing the controller itself.
        else:
            direct_test_logger.warning("Camera component not ready, skipping camera function tests.")

        direct_test_logger.info("UnifiedController direct test sequence complete.")

    except PhidgetException as e_phidget_test:
        direct_test_logger.error(f"A PhidgetException occurred during test: {e_phidget_test.description} (Code: {e_phidget_test.code})", exc_info=True)
    except Exception as e_test_main:
        direct_test_logger.error(f"An unexpected error occurred during test: {e_test_main}", exc_info=True)
    finally:
        if uc_instance_for_test:
            direct_test_logger.info("Closing UnifiedController instance from direct test...")
            uc_instance_for_test.close()
        direct_test_logger.info("UnifiedController direct test finished.")