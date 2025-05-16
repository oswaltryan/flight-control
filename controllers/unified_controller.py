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
    from Phidget22.PhidgetException import PhidgetException
except ImportError as e:
    print(f"Critical Import Error in unified_controller.py: {e}", file=sys.stderr)
    print(f"Attempted to add '{PROJECT_ROOT}' to sys.path. Check structure and PYTHONPATH.", file=sys.stderr)
    raise

module_logger = logging.getLogger(__name__)
module_logger.addHandler(logging.NullHandler())


class UnifiedController:
    def __init__(self,
                 script_map_config=None,
                 camera_id: int = 0,
                 led_configs=None,
                 display_order: list = None,
                 logger_instance=None):

        self.logger = logger_instance if logger_instance else module_logger
        if not self.logger.hasHandlers() and logger_instance is None:
            logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            self.logger.info("UnifiedController using basicConfig for its logger.")

        self.phidget_config_to_use = script_map_config if script_map_config is not None else DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG

        phidget_ctrl_logger = self.logger.getChild("Phidget")
        camera_ctrl_logger = self.logger.getChild("Camera")

        self._phidget_controller = PhidgetController(
            script_map_config=self.phidget_config_to_use,
            logger_instance=phidget_ctrl_logger
        )
        self.logger.info("PhidgetController component initialized.")

        self._camera_checker = LogitechLedChecker(
            camera_id=camera_id,
            led_configs=led_configs,
            display_order=display_order,
            logger_instance=camera_ctrl_logger
        )
        if not self._camera_checker.is_camera_initialized:
            self.logger.error(f"LogitechLedChecker component FAILED to initialize camera ID {camera_id}. Camera functions will not work.")
        else:
            self.logger.info("LogitechLedChecker component initialized.")

    # --- PhidgetController Method Delegation ---
    def on(self, channel_name):
        self._phidget_controller.on(channel_name)

    def off(self, channel_name):
        self._phidget_controller.off(channel_name)

    def hold(self, channel_name, duration_ms=200):
        self._phidget_controller.hold(channel_name, duration_ms)

    def press(self, channel_name):
        self._phidget_controller.press(channel_name)

    def sequence(self, pin_sequence: list, press_duration_ms: float = 100, pause_duration_ms: float = 100):
        self._phidget_controller.sequence(pin_sequence, press_duration_ms, pause_duration_ms)

    def read_input(self, channel_name):
        return self._phidget_controller.read_input(channel_name)

    def wait_for_input(self, channel_name, expected_state, timeout_s=5, poll_interval_s=0.05):
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
        self.logger.info("Closing UnifiedController resources...")
        if hasattr(self._camera_checker, 'release_camera') and self.is_camera_ready: # Check is_camera_ready
            try:
                self._camera_checker.release_camera()
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
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# --- For direct testing of unified_controller.py if needed ---
if __name__ == '__main__':
    print("Running a basic direct test of UnifiedController (from controllers/unified_controller.py)...")
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    main_test_logger = logging.getLogger("UnifiedControllerDirectTest")

    test_display_order = ["red", "green", "blue"]
    test_pattern = [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.5, 2.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.5, 2.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.1, 1.0)},
    ]
    
    try:
        # Ensure the Phidget channel 'connect' (or any other used) is defined in
        # hardware/phidget_io_controller.py : DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG
        # Or, pass a custom script_map_config here.
        with UnifiedController(logger_instance=main_test_logger, 
                               camera_id=0, 
                               display_order=test_display_order) as uc:
            
            main_test_logger.info("UnifiedController active for direct test.")
            
            main_test_logger.info("Testing Phidget: Turning 'connect' ON for 1 second.")
            uc.phidget_on("connect") 
            time.sleep(1)
            uc.phidget_off("connect")
            main_test_logger.info("Phidget 'connect' OFF.")

            if uc.is_camera_ready:
                 main_test_logger.info("Testing Camera: Awaiting and confirming a short pattern...")
                 # Physically trigger the LED pattern for this to pass
                 success = uc.camera_await_and_confirm_led_pattern(test_pattern, timeout=3.0)
                 if success:
                     main_test_logger.info("Test pattern confirmed successfully by camera.")
                 else:
                     main_test_logger.warning("Test pattern NOT confirmed by camera.")
            else:
                main_test_logger.warning("Camera component not ready, skipping camera pattern test.")

            main_test_logger.info("UnifiedController direct test sequence complete.")

    except PhidgetException as e:
        main_test_logger.error(f"A PhidgetException occurred during test: {e.description} (Code: {e.code})")
        main_test_logger.error(traceback.format_exc())
    except Exception as e:
        main_test_logger.error(f"An unexpected error occurred during test: {e}")
        main_test_logger.error(traceback.format_exc())
    finally:
        main_test_logger.info("UnifiedController direct test finished.")