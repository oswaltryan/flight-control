# Directory: controllers
# Filename: unified_controller.py
#!/usr/bin/env python3

import logging
import sys
import os
import time # Added for the __main__ test block
# import traceback # Not strictly needed if using exc_info=True with logging

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
    from camera.camera_controller import LogitechLedChecker
    from Phidget22.PhidgetException import PhidgetException
except ImportError as e_import:
    module_logger.critical(f"Critical Import Error in unified_controller.py: {e_import}. Check paths and dependencies.", exc_info=True)
    raise


class UnifiedController:
    def __init__(self,
                 script_map_config=None,
                 camera_id: int = 0,
                 led_configs=None,
                 display_order: list = None,
                 logger_instance=None):
        """
        Initializes a unified controller for Phidgets and Logitech LED checking.
        Logging is assumed to be pre-configured globally.
        """
        self.logger = logger_instance if logger_instance else module_logger
        # No basicConfig or other logging setup here.

        self.phidget_config_to_use = script_map_config if script_map_config is not None else DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG

        # Create child loggers for encapsulated controllers. These inherit from self.logger.
        phidget_ctrl_logger = self.logger.getChild("Phidget")
        camera_ctrl_logger = self.logger.getChild("Camera")

        # Initialize PhidgetController
        self._phidget_controller = None # Initialize to None
        try:
            self._phidget_controller = PhidgetController(
                script_map_config=self.phidget_config_to_use,
                logger_instance=phidget_ctrl_logger
            )
            # PhidgetController's __init__ logs its own success/status.
        except Exception as e_phidget_init:
            self.logger.error(f"Failed to initialize PhidgetController component: {e_phidget_init}", exc_info=True)
            # Allow continuation if possible, or re-raise if critical

        # Initialize LogitechLedChecker
        self._camera_checker = None # Initialize to None
        try:
            self._camera_checker = LogitechLedChecker(
                camera_id=camera_id,
                led_configs=led_configs,
                display_order=display_order,
                logger_instance=camera_ctrl_logger
            )
            if not self._camera_checker.is_camera_initialized: # is_camera_initialized is set by LogitechLedChecker
                self.logger.error(f"LogitechLedChecker component FAILED to initialize camera ID {camera_id}. Camera functions will not work.")
            # LogitechLedChecker's __init__ logs its own success/status.
        except Exception as e_camera_init:
            self.logger.error(f"Failed to initialize LogitechLedChecker component for camera ID {camera_id}: {e_camera_init}", exc_info=True)
            # Allow continuation, _camera_checker remains None or partially init'd

    # --- PhidgetController Method Delegation ---
    def on(self, channel_name):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'on'.")
            return # Or raise an exception
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

    def press(self, channel_name, duration_ms=200): # Added duration_ms from PhidgetController
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
            return None # Or raise
        return self._phidget_controller.read_input(channel_name)

    def wait_for_input(self, channel_name, expected_state, timeout_s=5, poll_interval_s=0.05):
        if not self._phidget_controller:
            self.logger.error("Phidget controller not initialized. Cannot call 'wait_for_input'.")
            return False # Or raise
        return self._phidget_controller.wait_for_input(channel_name, expected_state, timeout_s, poll_interval_s)

    # --- LogitechLedChecker Method Delegation ---
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
        if self._camera_checker and hasattr(self._camera_checker, 'release_camera'): # Check if instance exists
            try:
                self._camera_checker.release_camera()
                # self.logger.info("Camera component released.") # Logged by LogitechLedChecker.release_camera
            except Exception as e_cam_close:
                self.logger.error(f"Error releasing camera component: {e_cam_close}", exc_info=True)
        
        if self._phidget_controller and hasattr(self._phidget_controller, 'close_all'): # Check if instance exists
            try:
                self._phidget_controller.close_all()
                # self.logger.info("Phidget component closed.") # Logged by PhidgetController.close_all
            except Exception as e_phid_close:
                self.logger.error(f"Error closing phidget component: {e_phid_close}", exc_info=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# --- For direct testing of unified_controller.py if needed ---
if __name__ == '__main__':
    # IMPORTANT FOR DIRECT TESTING: Call setup_logging() from this module's test scope.
    print("Running a direct test of UnifiedController (from controllers/unified_controller.py)...")
    try:
        from utils.logging_config import setup_logging
        # For testing, often useful to set a more verbose default level.
        # This will be applied to all loggers unless overridden by LOG_LEVEL_CONFIG.
        setup_logging(default_log_level=logging.DEBUG)
    except ImportError:
        print("CRITICAL: Could not import 'utils.logging_config.setup_logging' for direct test. Using basicConfig.")
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Get a logger specifically for this test block.
    # Its name ("UnifiedControllerDirectTest") can be added to LOG_LEVEL_CONFIG for custom levels.
    direct_test_logger = logging.getLogger("UnifiedControllerDirectTest")
    direct_test_logger.info("UnifiedController direct test logging configured and starting...")

    test_display_order = ["red", "green", "blue"]
    test_pattern_for_camera = [
        {'red':1, 'green':0, 'blue':0, 'duration': (0.5, 2.0)}, # Red ON
        {'red':0, 'green':0, 'blue':0, 'duration': (0.1, 2.0)}, # All OFF
    ]
    test_solid_state_red_on = {'red':1, 'green':0, 'blue':0}
    phidget_channel_to_test = "connect" # Ensure this is in DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG

    uc_instance_for_test = None
    try:
        # Pass a child of the direct_test_logger to the UnifiedController instance
        uc_instance_for_test = UnifiedController(
            logger_instance=direct_test_logger.getChild("TestUCInstance"),
            camera_id=0,
            display_order=test_display_order
        )
        direct_test_logger.info(f"UnifiedController instance for test created. Camera Ready: {uc_instance_for_test.is_camera_ready}")
        
        if uc_instance_for_test._phidget_controller: # Check if Phidget part initialized
            direct_test_logger.info(f"Testing Phidget: Turning '{phidget_channel_to_test}' ON for 1 second.")
            uc_instance_for_test.on(phidget_channel_to_test)
            time.sleep(1)
            uc_instance_for_test.off(phidget_channel_to_test)
            direct_test_logger.info(f"Phidget '{phidget_channel_to_test}' OFF.")
        else:
            direct_test_logger.warning("Phidget component of UnifiedController not initialized. Skipping Phidget tests.")


        if uc_instance_for_test.is_camera_ready:
            direct_test_logger.info("--- Testing Camera Functions ---")
            direct_test_logger.info(f"Manual check: Make RED LED turn ON for 'confirm_led_solid' test.")
            direct_test_logger.info("Test 1: Confirming RED LED is solid ON for 2s (5s timeout)...")
            
            solid_success = uc_instance_for_test.confirm_led_solid(test_solid_state_red_on, minimum=2.0, timeout=5.0)
            if solid_success:
                direct_test_logger.info(f"SUCCESS: RED ON state confirmed solid.")
            else:
                direct_test_logger.warning(f"FAILURE: RED ON state not confirmed solid.")

            direct_test_logger.info("-" * 30)
            direct_test_logger.info(f"Manual check: Make LEDs follow pattern: RED ON, then ALL OFF for 'await_and_confirm_led_pattern' test.")
            direct_test_logger.info("Test 2: Awaiting and confirming camera pattern (3s await timeout)...")
            
            pattern_success = uc_instance_for_test.await_and_confirm_led_pattern(test_pattern_for_camera, timeout=3.0)
            if pattern_success:
                direct_test_logger.info("SUCCESS: Camera pattern confirmed.")
            else:
                direct_test_logger.warning("FAILURE: Camera pattern NOT confirmed.")
        else:
            direct_test_logger.warning("Camera component not ready, skipping camera function tests.")

        direct_test_logger.info("UnifiedController direct test sequence complete.")

    except PhidgetException as e_phidget_test:
        direct_test_logger.error(f"A PhidgetException occurred during test: {e_phidget_test.description} (Code: {e_phidget_test.code})", exc_info=True)
    except Exception as e_test_main:
        direct_test_logger.error(f"An unexpected error occurred during test: {e_test_main}", exc_info=True)
    finally:
        if uc_instance_for_test: # Ensure close is called if instance was created
            direct_test_logger.info("Closing UnifiedController instance from direct test...")
            uc_instance_for_test.close()
        direct_test_logger.info("UnifiedController direct test finished.")