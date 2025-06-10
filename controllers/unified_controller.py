# Directory: controllers
# Filename: unified_controller.py
#!/usr/bin/env python3

import logging
import sys
import os
import time 
from typing import Optional, List, Dict, Any, Union
from pprint import pprint

# --- Path Setup ---
CONTROLLERS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CONTROLLERS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

module_logger = logging.getLogger(__name__)

try:
    from hardware.phidget_io_controller import PhidgetController, DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG
    from camera.camera_controller import (
        LogitechLedChecker, 
        DEFAULT_DURATION_TOLERANCE_SEC as CAMERA_DEFAULT_TOLERANCE,
        DEFAULT_REPLAY_POST_FAIL_DURATION_SEC as CAMERA_DEFAULT_REPLAY_DURATION, 
    )
    from Phidget22.PhidgetException import PhidgetException
    from camera.led_dictionaries import LEDs
    from usb_tool import find_apricorn_device
    # from transitions import EventData # For FSM event data typing if needed
except ImportError as e_import:
    module_logger.critical(f"Critical Import Error in unified_controller.py: {e_import}. Check paths and dependencies.", exc_info=True)
    raise


class UnifiedController:
    _phidget_controller: Optional[PhidgetController]
    _camera_checker: Optional[LogitechLedChecker]
    logger: logging.Logger
    phidget_config_to_use: Dict[str, Any]
    effective_led_duration_tolerance: float

    def __init__(self,
                 script_map_config: Optional[Dict[str, Any]] = None,
                 camera_id: int = 0,
                 led_configs: Optional[Dict[str, Any]] = None,
                 display_order: Optional[List[str]] = None,
                 logger_instance: Optional[logging.Logger] = None,
                 led_duration_tolerance_sec: Optional[float] = None,
                 replay_post_failure_duration_sec: Optional[float] = None,
                 replay_output_dir: Optional[str] = None,
                 enable_instant_replay: Optional[bool] = None):
        self.logger = logger_instance if logger_instance else module_logger
        effective_replay_output_dir = replay_output_dir
        self.phidget_config_to_use = script_map_config if script_map_config is not None else DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG
        phidget_ctrl_logger = self.logger.getChild("Phidget")
        camera_ctrl_logger = self.logger.getChild("Camera")

        self._phidget_controller = None
        try:
            self._phidget_controller = PhidgetController(
                script_map_config=self.phidget_config_to_use, logger_instance=phidget_ctrl_logger)
        except Exception as e_phidget_init:
            self.logger.error(f"Failed to initialize PhidgetController: {e_phidget_init}", exc_info=True)

        self._camera_checker = None
        self.effective_led_duration_tolerance = led_duration_tolerance_sec if led_duration_tolerance_sec is not None else CAMERA_DEFAULT_TOLERANCE
        effective_replay_duration = replay_post_failure_duration_sec if replay_post_failure_duration_sec is not None else CAMERA_DEFAULT_REPLAY_DURATION
        effective_replay_output_dir = replay_output_dir

        try:
            self._camera_checker = LogitechLedChecker(
                camera_id=camera_id, led_configs=led_configs, display_order=display_order,
                logger_instance=camera_ctrl_logger, duration_tolerance_sec=self.effective_led_duration_tolerance,
                replay_post_failure_duration_sec=effective_replay_duration, replay_output_dir=effective_replay_output_dir, enable_instant_replay=enable_instant_replay)
            if not self._camera_checker.is_camera_initialized:
                self.logger.error(f"LogitechLedChecker FAILED to initialize camera {camera_id}.")
        except Exception as e_camera_init:
            self.logger.error(f"Failed to initialize LogitechLedChecker for camera {camera_id}: {e_camera_init}", exc_info=True)

    # --- PhidgetController Method Delegation ---
    def on(self, channel_name: str):
        if not self._phidget_controller: self.logger.error("Phidget not init for 'on'."); return
        self._phidget_controller.on(channel_name)
    def off(self, channel_name: str):
        if not self._phidget_controller: self.logger.error("Phidget not init for 'off'."); return
        self._phidget_controller.off(channel_name)
    def hold(self, channel_name: str, duration_ms: float = 200):
        if not self._phidget_controller: self.logger.error("Phidget not init for 'hold'."); return
        self._phidget_controller.hold(channel_name, duration_ms)
    def press(self, channel_or_channels: Union[str, List[str]], duration_ms: float = 100):
        if not self._phidget_controller: self.logger.error("Phidget not init for 'press'."); return
        self._phidget_controller.press(channel_or_channels, duration_ms=duration_ms)
    def sequence(self, pin_sequence: List[Any], press_duration_ms: float = 100, pause_duration_ms: float = 100):
        if not self._phidget_controller: self.logger.error("Phidget not init for 'sequence'."); return
        self._phidget_controller.sequence(pin_sequence, press_ms=press_duration_ms, pause_ms=pause_duration_ms)
    def read_input(self, channel_name: str) -> Optional[bool]:
        if not self._phidget_controller: self.logger.error("Phidget not init for 'read_input'."); return None
        return self._phidget_controller.read_input(channel_name)
    def wait_for_input(self, channel_name: str, expected_state: bool, timeout_s: float = 5, poll_interval_s: float = 0.05) -> bool:
        if not self._phidget_controller: self.logger.error("Phidget not init for 'wait_for_input'."); return False
        return self._phidget_controller.wait_for_input(channel_name, expected_state, timeout_s, poll_interval_s)

    # --- LogitechLedChecker Method Delegation ---
    @property
    def is_camera_ready(self) -> bool:
        return self._camera_checker is not None and self._camera_checker.is_camera_initialized

    def confirm_led_solid(self, state: dict, minimum: float = 2, timeout: float = 10,
                                 fail_leds: Optional[List[str]] = None, clear_buffer: bool = True, 
                                 manage_replay: bool = True, replay_extra_context: Optional[Dict[str, Any]] = None) -> bool:
        checker = self._camera_checker
        if checker is None or not checker.is_camera_initialized:
            self.logger.error("Camera not ready for confirm_led_solid.")
            return False
        return checker.confirm_led_solid(state, minimum, timeout, fail_leds, clear_buffer, 
                                         manage_replay=manage_replay, replay_extra_context=replay_extra_context)

    def confirm_led_solid_strict(self, state: dict, minimum: float, clear_buffer: bool = True, 
                                 manage_replay: bool = True, replay_extra_context: Optional[Dict[str, Any]] = None) -> bool:
        checker = self._camera_checker
        if checker is None or not checker.is_camera_initialized:
            self.logger.error("Camera not ready for confirm_led_solid_strict.")
            return False
        return checker.confirm_led_solid_strict(state, minimum, clear_buffer, 
                                                manage_replay=manage_replay, replay_extra_context=replay_extra_context)

    def await_led_state(self, state: dict, timeout: float = 1,
                               fail_leds: Optional[List[str]] = None, clear_buffer: bool = True, 
                               manage_replay: bool = True, replay_extra_context: Optional[Dict[str, Any]] = None) -> bool:
        checker = self._camera_checker
        if checker is None or not checker.is_camera_initialized:
            self.logger.error("Camera not ready for await_led_state.")
            return False
        return checker.await_led_state(state, timeout, fail_leds, clear_buffer, 
                                       manage_replay=manage_replay, replay_extra_context=replay_extra_context)

    def confirm_led_pattern(self, pattern: list, clear_buffer: bool = True, 
                            manage_replay: bool = True, replay_extra_context: Optional[Dict[str, Any]] = None) -> bool:
        checker = self._camera_checker
        if checker is None or not checker.is_camera_initialized:
            self.logger.error("Camera not ready for confirm_led_pattern.")
            return False
        return checker.confirm_led_pattern(pattern, clear_buffer, 
                                           manage_replay=manage_replay, replay_extra_context=replay_extra_context)

    def await_and_confirm_led_pattern(self, pattern: list, timeout: float,
                                             clear_buffer: bool = True, manage_replay: bool = True, replay_extra_context: Optional[Dict[str, Any]] = None) -> bool:
        checker = self._camera_checker
        if checker is None or not checker.is_camera_initialized:
            self.logger.error("Camera not ready for await_and_confirm_led_pattern.")
            return False
        return checker.await_and_confirm_led_pattern(pattern, timeout, clear_buffer, 
                                                     manage_replay=manage_replay, replay_extra_context=replay_extra_context)

    # --- Resource Management ---
    def close(self):
        if self._camera_checker and hasattr(self._camera_checker, 'release_camera'):
            try: self._camera_checker.release_camera()
            except Exception as e: self.logger.error(f"Error releasing camera: {e}", exc_info=True)
        if self._phidget_controller and hasattr(self._phidget_controller, 'close_all'):
            try: self._phidget_controller.close_all()
            except Exception as e: self.logger.error(f"Error closing phidget: {e}", exc_info=True)
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.close()

    def confirm_enum(self, stable_min: float = 5, timeout: float = 15) -> bool:
        self.logger.info(f"Confirming Drive enumeration (stable: {stable_min}s, overall_timeout: {timeout}s)...")
        overall_start_time = time.time()
        DUT_ping_1 = find_apricorn_device()
        if not DUT_ping_1: self.logger.warning("No device found on initial enum check."); return False
        
        # Assuming one device or interested in the first one. This might need adjustment for multi-device scenarios.
        first_device_serial = DUT_ping_1[0].iSerial 
        self.logger.info(f"Initial device found with iSerial: {first_device_serial}. Verifying stability...")
        
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

        for device_after_wait in DUT_ping_2:
            if device_after_wait.iSerial == first_device_serial: 
                self.logger.info(f"Drive with iSerial {first_device_serial} confirmed stable for at least {stable_min}s:")
                self.logger.info(f"  VID:PID  [Firm] @USB iSerial      iProduct")
                self.logger.info(f"  {device_after_wait.idVendor}:{device_after_wait.idProduct} [{device_after_wait.bcdDevice}] @{device_after_wait.bcdUSB} {device_after_wait.iSerial} {device_after_wait.iProduct}")
                return True
        
        self.logger.warning(f"Device with iSerial {first_device_serial} did not remain stable or was not found after stability wait.")
        return False

    # --- FSM Event Handling Callbacks (High-Level) ---
    def handle_post_failure(self, event_data: Any) -> None: 
        details = event_data.kwargs.get('details', "No details provided") if event_data and hasattr(event_data, 'kwargs') else "No details provided"
        self.logger.error(f"UnifiedController: Handling POST failure. Details from FSM: {details}")

    def handle_critical_error(self, event_data: Any) -> None:
        details = event_data.kwargs.get('details', "No details provided") if event_data and hasattr(event_data, 'kwargs') else "No details provided"
        self.logger.critical(f"UnifiedController: Handling CRITICAL error. Details from FSM: {details}")

# --- For direct testing ---
if __name__ == '__main__':
    try:
        from utils.logging_config import setup_logging
        setup_logging(default_log_level=logging.DEBUG) 
    except ImportError:
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logging.getLogger().critical("Could not import 'utils.logging_config.setup_logging' for direct test. Using basicConfig.")

    direct_test_logger = logging.getLogger("UnifiedControllerDirectTest")
    direct_test_logger.info("UnifiedController direct test logging configured and starting...")
    uc_instance_for_test = None
    try:
        test_replay_dir = os.path.join(PROJECT_ROOT, "logs", "test_replays_uc_direct")
        os.makedirs(test_replay_dir, exist_ok=True)

        uc_instance_for_test = UnifiedController(
            logger_instance=direct_test_logger.getChild("TestUCInstance"),
            camera_id=0, 
            led_duration_tolerance_sec=0.08, 
            replay_post_failure_duration_sec=2.0, # Shorter for quick testing
            replay_output_dir=test_replay_dir 
        )
        direct_test_logger.info(f"Test UnifiedController instance created. Camera Ready: {uc_instance_for_test.is_camera_ready}")
        if uc_instance_for_test._camera_checker:
            direct_test_logger.info(f"  Replay dir: {uc_instance_for_test._camera_checker.replay_output_dir}")

        if uc_instance_for_test.is_camera_ready:
            direct_test_logger.info("--- Testing Camera Replay with Context ---")
            fail_state = {"red": 1, "green": 1, "blue": 1} # A state likely to fail
            
            # Simulate context that an FSM might provide
            test_context = {
                "replay_script_name": os.path.basename(__file__),
                "replay_fsm_test_case": "DirectUCTest_Failure",
                "replay_some_other_info": "Value123"
            }
            direct_test_logger.info(f"Attempting confirm_led_solid for {fail_state} (expecting failure and replay with context).")
            # input("Prepare for FAILING confirm_led_solid test with context. Press Enter...")
            
            uc_instance_for_test.confirm_led_solid(
                fail_state, minimum=0.1, timeout=0.5, replay_extra_context=test_context
            )
            direct_test_logger.info(f"  Check for replay video in: {test_replay_dir}")
        else:
            direct_test_logger.warning("Camera component not ready, skipping camera replay test.")
            
    except Exception as e_test_main:
        direct_test_logger.error(f"Error during UnifiedController direct test: {e_test_main}", exc_info=True)
    finally:
        if uc_instance_for_test:
            direct_test_logger.info("Closing UnifiedController instance from direct test...")
            uc_instance_for_test.close()
        direct_test_logger.info("UnifiedController direct test finished.")