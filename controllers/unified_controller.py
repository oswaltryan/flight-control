# Directory: controllers
# Filename: unified_controller.py
#!/usr/bin/env python3

import logging
import sys
import os
import time # Added for the __main__ test block
import traceback # Added for the __main__ test block


# --- Path Setup ---
# This script (unified_controller.py) is in project_root/controllers/
# We need to add project_root to sys.path so it can find 'camera' and 'hardware'
CONTROLLERS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CONTROLLERS_DIR) # This should be project_root

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from hardware.phidget_io_controller import PhidgetController, DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG
    from camera.camera_controller import LogitechLedChecker
    from Phidget22.PhidgetException import PhidgetException # For re-exporting if desired, or for __main__
except ImportError as e:
    print(f"Critical Import Error in unified_controller.py: {e}", file=sys.stderr)
    print(f"Attempted to add '{PROJECT_ROOT}' to sys.path. Check structure and PYTHONPATH.", file=sys.stderr)
    raise

# Module-level logger for the unified controller itself
module_logger = logging.getLogger(__name__)
module_logger.addHandler(logging.NullHandler()) # Prevent "No handler found" warnings


class UnifiedController:
    def __init__(self,
                 # PhidgetController params
                 script_map_config=None, # Uses DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG from phidget_io_controller if None
                 # LogitechLedChecker params
                 camera_id: int = 0,
                 led_configs=None, # Uses PRIMARY_LED_CONFIGURATIONS from camera_controller if None
                 display_order: list = None, # For camera log formatting
                 # UnifiedController params
                 logger_instance=None):
        """
        Initializes a unified controller for Phidgets and Logitech LED checking.

        :param script_map_config: Phidget channel mapping. Defaults to DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG.
        :param camera_id: ID of the camera for LED checking.
        :param led_configs: Custom LED configurations for the camera. Defaults to PRIMARY_LED_CONFIGURATIONS.
        :param display_order: List of LED keys defining the order for (1)(2)(3) log display.
        :param logger_instance: An external logging.Logger instance for the UnifiedController.
        """
        self.logger = logger_instance if logger_instance else module_logger
        if not self.logger.hasHandlers() and logger_instance is None:
             # Basic config if no logger passed and module_logger is unconfigured
            logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            self.logger.info("UnifiedController using basicConfig for its logger as no instance was provided and module logger was unconfigured.")


        self.phidget_config_to_use = script_map_config if script_map_config is not None else DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG

        # Create child loggers for encapsulated controllers
        phidget_ctrl_logger = self.logger.getChild("Phidget")
        camera_ctrl_logger = self.logger.getChild("Camera")

        # Initialize PhidgetController
        self._phidget_controller = PhidgetController(
            script_map_config=self.phidget_config_to_use,
            logger_instance=phidget_ctrl_logger
        )
        self.logger.info("PhidgetController component initialized.")

        # Initialize LogitechLedChecker
        self._camera_checker = LogitechLedChecker(
            camera_id=camera_id,
            led_configs=led_configs, # Will default to PRIMARY_LED_CONFIGURATIONS if None
            display_order=display_order,
            logger_instance=camera_ctrl_logger
        )
        if not self._camera_checker.is_camera_initialized:
            self.logger.error(f"LogitechLedChecker component FAILED to initialize camera ID {camera_id}. Camera functions will not work.")
        else:
            self.logger.info("LogitechLedChecker component initialized.")

    # --- PhidgetController Method Delegation (Direct Names) ---
    def on(self, channel_name):
        """Turns a Phidget digital output ON."""
        self._phidget_controller.on(channel_name)

    def off(self, channel_name):
        """Turns a Phidget digital output OFF."""
        self._phidget_controller.off(channel_name)

    def hold(self, channel_name, duration_ms=200):
        """Holds a Phidget digital output ON for a duration, then OFF."""
        self._phidget_controller.hold(channel_name, duration_ms)

    def press(self, channel_name):
        """Presses a Phidget digital output (ON for 200ms, then OFF)."""
        self._phidget_controller.press(channel_name)

    def sequence(self, pin_sequence: list, press_duration_ms: float = 100, pause_duration_ms: float = 100):
        """Executes a sequence of Phidget digital output presses."""
        self._phidget_controller.sequence(pin_sequence, press_duration_ms, pause_duration_ms)

    def read_input(self, channel_name):
        """Reads the state of a Phidget digital input."""
        return self._phidget_controller.read_input(channel_name)

    def wait_for_input(self, channel_name, expected_state, timeout_s=5, poll_interval_s=0.05):
        """Waits for a Phidget digital input to reach an expected state."""
        return self._phidget_controller.wait_for_input(channel_name, expected_state, timeout_s, poll_interval_s)

    # --- LogitechLedChecker Method Delegation (Original Names from LogitechLedChecker) ---
    @property
    def is_camera_ready(self) -> bool:
        """Checks if the camera component is initialized and ready."""
        return self._camera_checker is not None and self._camera_checker.is_camera_initialized

    def confirm_led_solid(self, state: dict, minimum: float = 2, timeout: float = 10,
                                 fail_leds: list = None, clear_buffer: bool = True) -> bool:
        """Confirms if the specified LED state is solidly ON/OFF for a minimum duration."""
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for confirm_led_solid.")
            return False
        return self._camera_checker.confirm_led_solid(state, minimum, timeout, fail_leds, clear_buffer)

    def confirm_led_solid_strict(self, state: dict, minimum: float, clear_buffer: bool = True) -> bool:
        """Strictly confirms an LED state remains solid for the entire minimum duration."""
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for confirm_led_solid_strict.")
            return False
        return self._camera_checker.confirm_led_solid_strict(state, minimum, clear_buffer)

    def await_led_state(self, state: dict, timeout: float = 1,
                               fail_leds: list = None, clear_buffer: bool = True) -> bool:
        """Waits for a specific LED state to be observed within a timeout."""
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for await_led_state.")
            return False
        return self._camera_checker.await_led_state(state, timeout, fail_leds, clear_buffer)

    def confirm_led_pattern(self, pattern: list, clear_buffer: bool = True) -> bool:
        """Confirms if a sequence of LED states (pattern) occurs as specified."""
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for confirm_led_pattern.")
            return False
        return self._camera_checker.confirm_led_pattern(pattern, clear_buffer)

    def await_and_confirm_led_pattern(self, pattern: list, timeout: float,
                                             clear_buffer: bool = True) -> bool:
        """Awaits the first state of an LED pattern and then confirms the entire pattern."""
        if not self.is_camera_ready:
            self.logger.error("Camera not ready for await_and_confirm_led_pattern.")
            return False
        return self._camera_checker.await_and_confirm_led_pattern(pattern, timeout, clear_buffer)

    # --- Resource Management ---
    def close(self):
        """Closes all underlying resources (Phidgets and Camera)."""
        self.logger.info("Closing UnifiedController resources...")
        if hasattr(self._camera_checker, 'release_camera') and self.is_camera_ready:
            try:
                self._camera_checker.release_camera() # release_camera also sets is_camera_initialized to False
                self.logger.info("Camera component released.")
            except Exception as e:
                self.logger.error(f"Error releasing camera component: {e}")
        
        if hasattr(self._phidget_controller, 'close_all'):
            try:
                self._phidget_controller.close_all()
                self.logger.info("Phidget component closed.")
            except Exception as e:
                self.logger.error(f"Error closing phidget component: {e}")
        self.logger.info("UnifiedController resources closed.")

    def __enter__(self):
        # Initialization is done in __init__
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# --- For direct testing of unified_controller.py if needed ---
if __name__ == '__main__':
    print("Running a basic direct test of UnifiedController (from controllers/unified_controller.py)...")
    # Basic logging config for the test
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, # Use DEBUG to see all logs
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    main_test_logger = logging.getLogger("UnifiedControllerDirectTest")

    test_display_order = ["red", "green", "blue"] 
    test_pattern_for_camera = [
        {'red':1, 'green':0, 'blue':0, 'duration': (0.5, 2.0)}, # Red ON
        {'red':0, 'green':0, 'blue':0, 'duration': (0.1, 2.0)}, # All OFF
    ]
    test_solid_state_red_on = {'red':1, 'green':0, 'blue':0}
    phidget_channel_to_test = "connect" # Ensure this is in DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG

    try:
        with UnifiedController(logger_instance=main_test_logger, 
                               camera_id=0, 
                               display_order=test_display_order
                               ) as uc:
            
            main_test_logger.info(f"UnifiedController active for direct test. Camera Ready: {uc.is_camera_ready}")
            
            main_test_logger.info(f"Testing Phidget: Turning '{phidget_channel_to_test}' ON for 1 second.")
            uc.on(phidget_channel_to_test) # Using direct name 'on'
            time.sleep(1)
            uc.off(phidget_channel_to_test) # Using direct name 'off'
            main_test_logger.info(f"Phidget '{phidget_channel_to_test}' OFF.")

            if uc.is_camera_ready:
                 main_test_logger.info("--- Testing Camera Functions ---")
                 main_test_logger.info(f"You will need to manually make the RED LED turn ON for the next test ('confirm_led_solid').")
                 main_test_logger.info("Test 1: Confirming RED LED is solid ON for 2 seconds (within 5s timeout)...")
                 
                 solid_success = uc.confirm_led_solid(test_solid_state_red_on, minimum=2.0, timeout=5.0)
                 if solid_success:
                     main_test_logger.info(f"SUCCESS: RED ON state confirmed solid.")
                 else:
                     main_test_logger.warning(f"FAILURE: RED ON state not confirmed solid.")

                 main_test_logger.info("-" * 30)
                 main_test_logger.info(f"You will need to manually make the LEDs follow the pattern: RED ON, then ALL OFF for the next test.")
                 main_test_logger.info("Test 2: Awaiting and confirming camera pattern...")
                 
                 pattern_success = uc.await_and_confirm_led_pattern(test_pattern_for_camera, timeout=3.0) 
                 if pattern_success:
                     main_test_logger.info("SUCCESS: Camera pattern confirmed.")
                 else:
                     main_test_logger.warning("FAILURE: Camera pattern NOT confirmed.")
            else:
                main_test_logger.warning("Camera component not ready, skipping camera function tests.")

            main_test_logger.info("UnifiedController direct test sequence complete.")

    except PhidgetException as e: 
        main_test_logger.error(f"A PhidgetException occurred during test: {e.description} (Code: {e.code})")
        main_test_logger.error(traceback.format_exc())
    except Exception as e: 
        main_test_logger.error(f"An unexpected error occurred during test: {e}")
        main_test_logger.error(traceback.format_exc())
    finally:
        main_test_logger.info("UnifiedController direct test finished.")