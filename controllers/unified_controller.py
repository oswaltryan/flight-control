# Directory: controllers
# Filename: unified_controller.py
#!/usr/bin/env python3

import logging
import sys
import os
import time # Added for the __main__ test block
from typing import Optional, List, Dict, Any # For Optional type hint and others
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
    from camera.camera_controller import (
        LogitechLedChecker, 
        DEFAULT_DURATION_TOLERANCE_SEC as CAMERA_DEFAULT_TOLERANCE,
        # Import replay defaults to use if not overridden by UnifiedController caller
        DEFAULT_REPLAY_POST_FAIL_DURATION_SEC as CAMERA_DEFAULT_REPLAY_DURATION, 
        DEFAULT_REPLAY_OUTPUT_DIR as CAMERA_DEFAULT_REPLAY_DIR
    )
    # from camera import camera_controller # No longer needed for direct constant access
    from Phidget22.PhidgetException import PhidgetException
    from camera.led_dictionaries import LEDs
    from usb_tool import find_apricorn_device
    # If EventData is needed for type hinting for FSM handlers:
    # from transitions import EventData 
except ImportError as e_import:
    module_logger.critical(f"Critical Import Error in unified_controller.py: {e_import}. Check paths and dependencies.", exc_info=True)
    raise


class UnifiedController:
    def __init__(self,
                 script_map_config: Optional[Dict[str, Any]] = None,
                 camera_id: int = 0,
                 led_configs: Optional[Dict[str, Any]] = None,
                 display_order: Optional[List[str]] = None,
                 logger_instance: Optional[logging.Logger] = None,
                 led_duration_tolerance_sec: Optional[float] = None,
                 replay_post_failure_duration_sec: Optional[float] = None,
                 replay_output_dir: Optional[str] = None):
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
        self.effective_led_duration_tolerance = led_duration_tolerance_sec if led_duration_tolerance_sec is not None else CAMERA_DEFAULT_TOLERANCE
        
        # Determine replay parameters, using defaults from camera_controller if not provided by this constructor
        effective_replay_duration = replay_post_failure_duration_sec \
            if replay_post_failure_duration_sec is not None \
            else CAMERA_DEFAULT_REPLAY_DURATION # Use imported default
        
        effective_replay_output_dir = replay_output_dir \
            if replay_output_dir is not None \
            else CAMERA_DEFAULT_REPLAY_DIR # Use imported default

        try:
            self._camera_checker = LogitechLedChecker(
                camera_id=camera_id,
                led_configs=led_configs,
                display_order=display_order,
                logger_instance=camera_ctrl_logger,
                duration_tolerance_sec=self.effective_led_duration_tolerance,
                replay_post_failure_duration_sec=effective_replay_duration,
                replay_output_dir=effective_replay_output_dir
            )
            if not self._camera_checker.is_camera_initialized:
                self.logger.error(f"LogitechLedChecker component FAILED to initialize camera ID {camera_id}. Camera functions will not work.")
        except Exception as e_camera_init:
            self.logger.error(f"Failed to initialize LogitechLedChecker component for camera ID {camera_id}: {e_camera_init}", exc_info=True)


    ### LOWER LEVEL COMMANDS ###
    # --- PhidgetController Method Delegation ---
    def on(self, channel_name: str):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'on'.")
            return
        self._phidget_controller.on(channel_name)

    def off(self, channel_name: str):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'off'.")
            return
        self._phidget_controller.off(channel_name)

    def hold(self, channel_name: str, duration_ms: int = 200):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'hold'.")
            return
        self._phidget_controller.hold(channel_name, duration_ms)

    def press(self, channel_name: str, duration_ms: int = 200):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'press'.")
            return
        self._phidget_controller.press(channel_name, duration_ms=duration_ms)

    def sequence(self, pin_sequence: List[str], press_duration_ms: float = 100, pause_duration_ms: float = 100):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'sequence'.")
            return
        self._phidget_controller.sequence(pin_sequence, press_duration_ms, pause_duration_ms)

    def read_input(self, channel_name: str) -> Optional[bool]:
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'read_input'.")
            return None
        return self._phidget_controller.read_input(channel_name)

    def wait_for_input(self, channel_name: str, expected_state: bool, timeout_s: float = 5, poll_interval_s: float = 0.05) -> bool:
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'wait_for_input'.")
            return False
        return self._phidget_controller.wait_for_input(channel_name, expected_state, timeout_s, poll_interval_s)

    # --- LogitechLedChecker Method Delegation (Low-Level Primitives) ---
    @property
    def is_camera_ready(self) -> bool:
        return self._camera_checker is not None and self._camera_checker.is_camera_initialized

    def confirm_led_solid(self, state: dict, minimum: float = 2, timeout: float = 10,
                                 fail_leds: Optional[list] = None, clear_buffer: bool = True, manage_replay: bool = True) -> bool:
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for confirm_led_solid.")
            return False
        return self._camera_checker.confirm_led_solid(state, minimum, timeout, fail_leds, clear_buffer, manage_replay=manage_replay)

    def confirm_led_solid_strict(self, state: dict, minimum: float, clear_buffer: bool = True, manage_replay: bool = True) -> bool:
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for confirm_led_solid_strict.")
            return False
        return self._camera_checker.confirm_led_solid_strict(state, minimum, clear_buffer, manage_replay=manage_replay)

    def await_led_state(self, state: dict, timeout: float = 1,
                               fail_leds: Optional[list] = None, clear_buffer: bool = True, manage_replay: bool = True) -> bool:
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for await_led_state.")
            return False
        return self._camera_checker.await_led_state(state, timeout, fail_leds, clear_buffer, manage_replay=manage_replay)

    def confirm_led_pattern(self, pattern: list, clear_buffer: bool = True, manage_replay: bool = True) -> bool:
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for confirm_led_pattern.")
            return False
        return self._camera_checker.confirm_led_pattern(pattern, clear_buffer, manage_replay=manage_replay)

    def await_and_confirm_led_pattern(self, pattern: list, timeout: float,
                                             clear_buffer: bool = True, manage_replay: bool = True) -> bool:
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for await_and_confirm_led_pattern.")
            return False
        return self._camera_checker.await_and_confirm_led_pattern(pattern, timeout, clear_buffer, manage_replay=manage_replay)

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

    def confirm_enum(self, stable_min: float = 5, timeout: float = 15) -> bool: # Added timeout, used for overall duration
        self.logger.info(f"Attempting to confirm Drive enumeration (USB)...")
        self.logger.info(f"Waiting for stable, available drive (stable_min: {stable_min}s, overall_timeout: {timeout}s)...")
        
        overall_start_time = time.time()
        
        # Initial find
        DUT_ping_1 = find_apricorn_device()
        
        if not DUT_ping_1:
            self.logger.warning("No device found on initial enumeration check.")
            return False

        # Assuming one device or interested in the first one.
        # For multiple devices, a more robust selection (e.g., by expected serial pattern) would be needed.
        first_device_serial = DUT_ping_1[0].iSerial 
        self.logger.info(f"Initial device found with iSerial: {first_device_serial}. Verifying stability...")

        # Wait for the stability period, but respect overall timeout
        stability_wait_start = time.time()
        while time.time() - stability_wait_start < stable_min:
            if time.time() - overall_start_time > timeout:
                self.logger.warning(f"Overall timeout ({timeout}s) reached while waiting for stability for device {first_device_serial}.")
                return False
            time.sleep(0.2) # Poll less aggressively during stability wait

        DUT_ping_2 = find_apricorn_device()
        if not DUT_ping_2:
            self.logger.warning(f"Device with iSerial {first_device_serial} disappeared after {time.time() - stability_wait_start:.2f}s stability wait.")
            return False

        found_stable_device = False
        for device_after_wait in DUT_ping_2:
            if device_after_wait.iSerial == first_device_serial: 
                self.logger.info(f"Drive with iSerial {first_device_serial} confirmed stable for at least {stable_min}s:")
                self.logger.info(f"  VID:PID  [Firm] @USB iSerial      iProduct")
                self.logger.info(f"  {device_after_wait.idVendor}:{device_after_wait.idProduct} [{device_after_wait.bcdDevice}] @{device_after_wait.bcdUSB} {device_after_wait.iSerial} {device_after_wait.iProduct}")
                found_stable_device = True
                break 
        
        if not found_stable_device:
            self.logger.warning(f"Device with iSerial {first_device_serial} did not remain stable or was not found after stability wait.")
        
        return found_stable_device


    # --- FSM Event Handling Callbacks (High-Level) ---
    # These methods are placeholders if UnifiedController needs to react to FSM events.
    # The actual FSM event_data would be passed if these were registered as FSM callbacks.
    def handle_post_failure(self, event_data: Any) -> None: 
        """Handles actions to take when POST fails. Expected to be called by FSM."""
        details = "No details provided"
        if event_data and hasattr(event_data, 'kwargs') and event_data.kwargs:
            details = event_data.kwargs.get('details', details)
        self.logger.error(f"UnifiedController: Handling POST failure. Details from FSM: {details}")
        # Example: self.off("some_critical_relay_if_post_fails")

    def handle_critical_error(self, event_data: Any) -> None:
        """Handles actions to take on a critical error. Expected to be called by FSM."""
        details = "No details provided"
        if event_data and hasattr(event_data, 'kwargs') and event_data.kwargs:
            details = event_data.kwargs.get('details', details)
        self.logger.critical(f"UnifiedController: Handling CRITICAL error. Details from FSM: {details}")
        # Example: self.off("all_power_outputs")

# --- For direct testing of unified_controller.py if needed ---
if __name__ == '__main__':
    print("Running a direct test of UnifiedController (from controllers/unified_controller.py)...")
    try:
        # Assuming utils.logging_config is in a directory accessible via PROJECT_ROOT in sys.path
        from utils.logging_config import setup_logging
        setup_logging(default_log_level=logging.DEBUG) # Set to DEBUG for detailed test output
    except ImportError:
        print("CRITICAL: Could not import 'utils.logging_config.setup_logging' for direct test. Using basicConfig.")
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    direct_test_logger = logging.getLogger("UnifiedControllerDirectTest")
    direct_test_logger.info("UnifiedController direct test logging configured and starting...")

    uc_instance_for_test = None
    try:
        # Ensure PROJECT_ROOT is correctly defined if replay_output_dir needs it
        # For this test, using a relative path or an absolute one based on known structure.
        test_replay_dir = os.path.join(PROJECT_ROOT, "logs", "test_replays_unified")

        uc_instance_for_test = UnifiedController(
            logger_instance=direct_test_logger.getChild("TestUCInstance"),
            camera_id=0, # Ensure this camera ID is available and working
            led_duration_tolerance_sec=0.08, 
            replay_post_failure_duration_sec=3.0, # Shorter for testing
            replay_output_dir=test_replay_dir 
        )
        direct_test_logger.info(f"UnifiedController instance for test created. Camera Ready: {uc_instance_for_test.is_camera_ready}")
        direct_test_logger.info(f"Effective LED duration tolerance for this instance: {uc_instance_for_test.effective_led_duration_tolerance:.3f}s")
        if uc_instance_for_test._camera_checker: # Check if camera_checker was initialized
            direct_test_logger.info(f"  Replay post-failure duration: {uc_instance_for_test._camera_checker.replay_post_failure_duration_sec:.1f}s")
            direct_test_logger.info(f"  Replay output directory: {uc_instance_for_test._camera_checker.replay_output_dir}")
            os.makedirs(uc_instance_for_test._camera_checker.replay_output_dir, exist_ok=True) # Ensure dir exists for test
        
        if uc_instance_for_test._phidget_controller:
            direct_test_logger.info("Testing Phidget: Turning 'usb3' ON then OFF.") 
            uc_instance_for_test.on("usb3") 
            time.sleep(0.5) # Shorter sleep for faster test
            uc_instance_for_test.off("usb3") 
            direct_test_logger.info("Phidget 'usb3' power cycle test complete.")
        else:
            direct_test_logger.warning("Phidget component of UnifiedController not initialized. Skipping Phidget tests.")

        # Mock EventData for testing FSM handler methods
        class MockEventData: # Simplified MockEventData for this test
            def __init__(self, kwargs=None):
                self.kwargs = kwargs if kwargs else {}
        
        direct_test_logger.info("Testing handle_post_failure (mock call)...")
        uc_instance_for_test.handle_post_failure(MockEventData(kwargs={'details': 'Test POST failure from __main__'}))
        
        direct_test_logger.info("Testing handle_critical_error (mock call)...")
        uc_instance_for_test.handle_critical_error(MockEventData(kwargs={'details': 'Test CRITICAL error from __main__'}))


        if uc_instance_for_test.is_camera_ready:
            direct_test_logger.info("--- Testing Camera Functions (with tolerance and replay) ---")
            # Example: Test confirm_led_solid to trigger a failure and replay
            test_state_fail = {"red": 1, "green": 1, "blue": 1} # All ON state
            test_min_duration_fail = 0.5 
            
            direct_test_logger.info(f"Attempting confirm_led_solid for {test_state_fail} (expecting failure and replay).")
            direct_test_logger.info(f"  Ensure LEDs are NOT {test_state_fail} to cause failure.")
            # input("Press Enter to run FAILING confirm_led_solid test...") # Uncomment for manual sync

            success_fail_test = uc_instance_for_test.confirm_led_solid(
                test_state_fail, 
                minimum=test_min_duration_fail, 
                timeout=1.0 # Short timeout to ensure it fails if not immediately met
            )
            direct_test_logger.info(f"confirm_led_solid (failure case) result: {'SUCCESS' if success_fail_test else 'FAILURE'}")
            if not success_fail_test and uc_instance_for_test._camera_checker:
                direct_test_logger.info(f"  Check for replay video in: {uc_instance_for_test._camera_checker.replay_output_dir}")

            # Example: Test confirm_led_solid for success (no replay saved)
            test_state_success = {"red": 0, "green": 0, "blue": 0} # All OFF state
            test_min_duration_success = 0.5

            direct_test_logger.info(f"Attempting confirm_led_solid for {test_state_success} (expecting success).")
            direct_test_logger.info(f"  Ensure LEDs ARE {test_state_success} to cause success.")
            # input("Press Enter to run SUCCESSFUL confirm_led_solid test...") # Uncomment for manual sync
            
            # You might need to manually ensure the LED state is "ALL_OFF" for this to pass.
            # For automated testing, this would be harder without controlling the LEDs.
            # success_pass_test = uc_instance_for_test.confirm_led_solid(
            #     test_state_success, 
            #     minimum=test_min_duration_success, 
            #     timeout=2.0
            # )
            # direct_test_logger.info(f"confirm_led_solid (success case) result: {'SUCCESS' if success_pass_test else 'FAILURE'}")

        else:
            direct_test_logger.warning("Camera component not ready, skipping camera function tests.")

        direct_test_logger.info("UnifiedController direct test sequence complete.")

    except PhidgetException as e_phidget_test:
        direct_test_logger.error(f"A PhidgetException occurred during test: {e_phidget_test.description} (Code: {e_phidget_test.code})", exc_info=True)
    except Exception as e_test_main:
        direct_test_logger.error(f"An unexpected error occurred during the UnifiedController direct test: {e_test_main}", exc_info=True)
    finally:
        if uc_instance_for_test:
            direct_test_logger.info("Closing UnifiedController instance from direct test...")
            uc_instance_for_test.close()
        direct_test_logger.info("UnifiedController direct test finished.")