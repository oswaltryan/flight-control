# Directory: controllers
# Filename: flight_control_fsm.py

import logging
import time # For simulating delays if needed
from typing import List, Dict, Tuple, Any, Optional # For type hinting
import os
from pprint import pprint

from camera.led_dictionaries import LEDs
from transitions import Machine, EventData # Import EventData for type hinting
from usb_tool import find_apricorn_device


from .unified_controller import UnifiedController

# --- FSM Class Definition ---
class SimplifiedDeviceFSM:

    STATES: List[str] = ['OFF', 'STARTUP_SELF_TEST', 'STANDBY_MODE', 'UNLOCKED_ADMIN']

    logger: logging.Logger
    at: 'UnifiedController' # Use the actual class name if imported
    machine: Machine
    state: str

    def __init__(self, at_controller: 'UnifiedController'):
        self.logger = logging.getLogger("DeviceFSM.Simplified")
        self.at = at_controller

        self.machine = Machine(
            model=self,
            states=SimplifiedDeviceFSM.STATES,
            initial='OFF',
            send_event=True, # Allows passing EventData to callbacks
            after_state_change='_log_state_change_details'
        )
        self.state = self.machine.initial

        # Define transition triggers (methods will be dynamically created by transitions)
        self.confirm_standby_mode: callable
        self.power_on: callable
        self.power_off: callable
        self.post_successful_standby_detected: callable
        self.post_failed: callable
        self.critical_error_detected: callable
        self.unlock_admin: callable
        self.lock_admin: callable

        # --- Transitions ---
        self.machine.add_transition(trigger='power_on', source='OFF', dest='STARTUP_SELF_TEST')                         # Power on, confirm Startup Self-Test
        self.machine.add_transition(trigger='confirm_standby_mode', source='STARTUP_SELF_TEST', dest='STANDBY_MODE')    # Confirm Standby Mode
        self.machine.add_transition(trigger='power_off', source='STANDBY_MODE', dest='OFF')                             # Power off, confirm DUT LEDs off
        self.machine.add_transition(trigger='unlock_admin', source='STANDBY_MODE', dest='UNLOCKED_ADMIN')               # Unlock DUT using Admin PIN
        self.machine.add_transition(trigger='lock_admin', source='UNLOCKED_ADMIN', dest='STANDBY_MODE')                 # Lock DUT from Admin enum


    def _log_state_change_details(self, event_data: EventData) -> None:
        source_state: str = event_data.transition.source
        event_name: str = event_data.event.name
        current_state: str = self.state # self.state is updated by the Machine
        self.logger.debug(f"State changed: {source_state} -> {current_state} (Event: {event_name})")
        if event_data.kwargs: # Log any extra data passed with the event trigger
            self.logger.debug(f"  Event details: {event_data.kwargs}")

    # --- on_enter_STATENAME Callbacks (State-specific logic) ---
    def on_enter_OFF(self, event_data: EventData) -> None:
        self.at.off("usb3")
        self.at.off("connect")

        power_off_ok: bool = self.at.confirm_led_solid(
            LEDs['ALL_OFF'], 
            minimum=3.0, 
            timeout=5.0,
            clear_buffer=True # Expecting a stable state now
        )

        if not power_off_ok:
            self.logger.error("Failed DUT off LED confirmation...")
            self.post_failed(details="POST_ANIMATION_MISMATCH") # Pass details
            return

        self.logger.info("Device is now OFF.")
        # Additional OFF state actions if any (e.g., ensure all power is cut if not handled by at.power_off)

    def on_enter_STARTUP_SELF_TEST(self, event_data: EventData) -> None:
        self.logger.info("Powering DUT on...")
        self.at.on("usb3")
        self.at.on("connect")

        # 1. Confirm the POST animation (using low-level AT method)
        post_animation_observed_ok: bool = self.at.confirm_led_pattern(LEDs['STARTUP'], clear_buffer=True)

        if not post_animation_observed_ok:
            self.logger.error("Failed Startup Self-Test LED confirmation...")
            self.post_failed(details="POST_ANIMATION_MISMATCH") # Pass details
            return

    def on_enter_STANDBY_MODE(self, event_data: EventData) -> None:

       self.logger.info(f"Confirming Standby Mode...")
       
       # Or, using the lower-level primitive directly as before:
       standby_confirmed_ok: bool = self.at.confirm_led_solid(
            LEDs['STANDBY_MODE'], 
            minimum=3.0, 
            timeout=5.0,
            clear_buffer=True # Expecting a stable state now
        )

       if not standby_confirmed_ok:
            self.logger.error(f"Failed to confirm stable STANDBY_MODE LEDs. Device state uncertain. Triggering critical error.")
            self.critical_error_detected(details="STANDBY_LED_CONFIRMATION_FAILED") # Pass details
            return
       self.logger.info("Stable STANDBY_MODE LEDs confirmed.")
        
    def on_enter_UNLOCKED_ADMIN(self, event_data: EventData) -> None:
        self.logger.info("Unlocking DUT with Admin PIN...")

        self.at.sequence(["key1", "key1", "key2", "key2", "key3", "key3", "key4", "key4", "unlock"])
        # 1. Confirm the POST animation (using low-level AT method)
        unlock_admin_ok: bool = self.at.await_and_confirm_led_pattern(LEDs['ENUM'], timeout = 15, clear_buffer=True)

        if not unlock_admin_ok:
            self.logger.error("Failed DUT unlock LED confirmation...")
            self.post_failed(details="POST_ANIMATION_MISMATCH") # Pass details
            return
        
        self.at.confirm_enum()

    def on_exit_UNLOCKED_ADMIN(self, event_data: EventData) -> None:
        self.logger.info(f"Locking DUT from Unlocked Admin...")
        self.at.press("lock")

# --- Main Execution Logic (Example for direct testing of this FSM module) ---
if __name__ == '__main__':
    print("WARNING: Running flight_control_fsm.py directly. Setting up paths for test.")
    import sys
    SCRIPT_DIR_FSM = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT_FSM = os.path.dirname(SCRIPT_DIR_FSM)
    if PROJECT_ROOT_FSM not in sys.path:
        sys.path.insert(0, PROJECT_ROOT_FSM)

    main_log: logging.Logger
    try:
        from utils.logging_config import setup_logging
        setup_logging() # Configure with project defaults
    except ImportError:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logging.warning("Could not import custom logging_config for FSM direct test. Using basicConfig.")
    main_log = logging.getLogger("__main__FSM_Test")

    at_controller_test: Optional['UnifiedController'] = None
    try:
        # This assumes automation_toolkit.py can successfully create 'at'
        from automation_toolkit import get_at_controller
        at_controller_test = get_at_controller()
        if at_controller_test is None:
            raise RuntimeError("Failed to get 'at' controller for FSM direct test.")
        main_log.info("Successfully obtained 'at' controller for FSM direct test.")
    except Exception as e_test_at:
        main_log.critical(f"Could not get/initialize 'at' controller for FSM direct test: {e_test_at}. Aborting.", exc_info=True)
        sys.exit(1)

    main_log.info("Initializing SimplifiedDeviceFSM for direct test...")
    device_fsm_test = SimplifiedDeviceFSM(at_controller=at_controller_test)
    main_log.info(f"FSM (direct test) initial state: {device_fsm_test.state}")

    main_log.info("\n>>> FSM Direct Test: Simulating power on request...")
    # Physical device should be connected and ready to show POST -> Standby sequence
    if hasattr(device_fsm_test, 'power_on_requested'): 
        device_fsm_test.power_on_requested() 
    else:
        main_log.error("FSM instance does not have 'power_on_requested' trigger.")
        
    main_log.info(f"FSM (direct test) state after power_on_requested & internal processing: {device_fsm_test.state}")

    if device_fsm_test.state == 'STANDBY_MODE':
        main_log.info("\n>>> FSM Direct Test: Device is in Standby. Simulating power off request...")
        time.sleep(1) 
        if hasattr(device_fsm_test, 'power_off_requested'):
            device_fsm_test.power_off_requested()
        main_log.info(f"FSM (direct test) state after power_off from Standby: {device_fsm_test.state}")
    elif device_fsm_test.state == 'ERROR_POST_FAILED':
        main_log.info("\n>>> FSM Direct Test: Device is in Error. Simulating power off request...")
        time.sleep(1)
        if hasattr(device_fsm_test, 'power_off_requested'):
            # The 'power_off_requested' trigger will call self.at.power_off()
            device_fsm_test.power_off_requested(details="Shutdown from error by test") # Example of passing details
        main_log.info(f"FSM (direct test) state after power_off from Error: {device_fsm_test.state}")
    else:
        main_log.warning(f"\n>>> FSM Direct Test: Device ended in unexpected state '{device_fsm_test.state}'. Not simulating power off.")

    main_log.info("\nSimplified FSM direct test complete.")
    if at_controller_test and hasattr(at_controller_test, 'close'):
        main_log.info("Closing 'at_controller_test' resources from FSM direct test.")
        at_controller_test.close()