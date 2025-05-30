# Directory: controllers
# Filename: flight_control_fsm.py

import logging
import time # For simulating delays if needed
from typing import List, Dict, Tuple, Any, Optional # For type hinting
import os # For os.path.basename
from pprint import pprint

from camera.led_dictionaries import LEDs
from transitions import Machine, EventData # Import EventData for type hinting
from usb_tool import find_apricorn_device


from .unified_controller import UnifiedController

# --- FSM Class Definition ---
class SimplifiedDeviceFSM:

    # DUT: dict = {
    #     "name": None,
    #     "battery": False,
    #     "batteryVBUS": False,
    #     "VBUS": False,
    #     "bridgeFW": Devices[cfg.PROD.name]['bridgeFW'],
    #     "mcuFW": [],
    #     "mcuFWHumanReadable": "",
    #     "fips": Devices[cfg.PROD.name]['fips'],
    #     "legacyProduct": Devices[cfg.PROD.name]['legacy'],
    #     "factoryKeypadTest": Devices[cfg.PROD.name]['factoryKeypadTest'],
    #     "resetKeypadTest": Devices[cfg.PROD.name]['resetKeypadTest'],
    #     "secureKey": Devices[cfg.PROD.name]['secureKey'],
    #     "usb3": False,
    #     "diskPath": "",
    #     "mounted": False,
    #     "serialNumber": "",
    #     "devKeypadSerialNumber": "",

    #     "CMFR": False,
    #     "modelID1": Devices[cfg.PROD.name]['model_id_digit_1'],
    #     "modelID2": Devices[cfg.PROD.name]['model_id_digit_2'],
    #     "hardwareID1": Devices[cfg.PROD.name]['hardware_major'],
    #     "hardwareID2": Devices[cfg.PROD.name]['hardware_minor'],
    #     "scbPartNumber": Devices[cfg.PROD.name]['singleCodeBasePartNumber'],
    #     "singleCodeBase": Devices[cfg.PROD.name]['singleCodeBase'],
    #     "oobTrace": int(Devices['scriptConfig']["usbmonoob"]),
    #     "port": int(Devices[cfg.PROD.name]["usbmonport"]),
    #     "resetTrace": int(Devices['scriptConfig']["usbmonreset"]),
    #     "unlockTrace": int(Devices['scriptConfig']["usbmonunlock"]),
    #     "SPITrace": int(Devices['scriptConfig']["usbmonSPI"]),
        
    #     "lastFunctionExitMode": "",
    #     "adminMode": False,
    #     "bridgeChipTestMode": False,
    #     "diagnosticMode": False,
    #     "errorMode": False,
    #     "factoryMode": False,
    #     "oobMode": True,
    #     "sleepMode": True,
    #     "standbyMode": False,
    #     "onDemandSelfTest": False,
    #     "startupSelfTest": False,
    #     "basicDisk": True,
    #     "removableMedia": False,
        
    #     "bruteForceCounter": 10,
    #     "bruteForceCounterHalfwayPoint": 5,
    #     "bruteForceCounterFirstHalf": 0,
    #     "bruteForceCounterSecondHalf": 0,
    #     "enrollingBruteForce": False,
    #     "enrollmentBruteForce": False,
    #     "bruteForcedFirstHalf": False,
    #     "bruteForcedSecondHalf": False,
    #     "lastTryLogin": False,
    #     "deletePINs": False,
        
    #     "ledFlicker": False,
        
    #     "lockOverride": False,
    #     "manufacturerResetEnum": False,
    #     "manufacturerResetInitiate": False,
    #     "manufacturerResetKeypadTest": False,
    #     "manufacturerResetReadyMode": False,
    #     "userResetInitiate": False,
    #     "userResetWarning": False,
    #     "resetVBUSInterruptTesting": False,
    #     "generatingEncryptionKey": False,
    #     "selfDestructVBUSInterrupt": False,
    #     "selfDestructVBUSInterruptPIN": {},
    #     "maxPINCounter": 16,
    #     "minPINCounter": int(Devices[cfg.PROD.name]["minpin"]),
    #     "defaultMinPINCounter": int(Devices[cfg.PROD.name]["minpin"]),
    #     "enrollingMinPIN": False,
    #     "enrollmentMinPIN": False,
    #     "provisionLock": False,
    #     "provisionLockBricked": False,
    #     "provisionLockSoftBricked": False,
    #     "provisionLockRecover": False,
    #     "provisionLockRecoverCounter": 5,
    #     "readOnlyEnabled": False,
    #     "readWriteEnabled": True,
    #     "unattendedAutoLockCounter": 0,
    #     "enrollingUnattendedAutoLock": False,
    #     "enrollmentUnattendedAutoLock": False,
    #     "unattendedAutoLockEnum": False,
    #     "unattendedAutoLockTimeout": 0,
    #     "userForcedEnrollment": False,
    #     "userForcedEnrollmentUsed": False,
    #     "adminPIN": {},
    #     "oldAdminPIN": {},
    #     "enrolledAdmin": False,
    #     "enrollingAdmin": False,
    #     "enrollmentAdmin": False,
    #     "adminEnum": False,
    #     "adminLogin": False,
    #     "recoveryPIN": {1: {}, 2: {}, 3: {}, 4: {}},
    #     "oldRecoveryPIN": {1: {}, 2: {}, 3: {}, 4: {}},
    #     "enrolledRecovery": {1: False, 2: False, 3: False, 4: False},
    #     "enrollingRecovery": False,
    #     "enrollmentRecovery": {1: False, 2: False, 3: False, 4: False},
    #     "loginRecovery": {1: False, 2: False, 3: False, 4: False},
    #     "usedRecovery": {1: False, 2: False, 3: False, 4: False},
        
    #     "selfDestructEnabled": False,
    #     "selfDestructPIN": {},
    #     "oldSelfDestructPIN": {},
    #     "enrolledSelfDestruct": False,
    #     "enrollingSelfDestruct": False,
    #     "enrollmentSelfDestruct": False,
    #     "selfDestructEnum": False,
    #     "selfDestructUsed": False,
    #     "userCount": Devices[cfg.PROD.name]['userCount'],
    #     "userPIN": {1: None, 2: None, 3: None, 4: None},
    #     "oldUserPIN": {1: None, 2: None, 3: None, 4: None},
    #     "enrolledUser": {1: False, 2: False, 3: False, 4: False},
    #     "enrollingUser": False,
    #     "enrollmentUser": {1: False, 2: False, 3: False, 4: False},
    #     "enumUser": {1: False, 2: False, 3: False, 4: False},
    #     "changeLoginUser": {1: False, 2: False, 3: False, 4: False},
    #     "psuedoUserPIN": None,
    #     "devFWUnlockDrive": False,
    #     "devResultSPI": 0,
    #     "modeOrientationDisable": False,
    #     "modeOrientationCounter": 0,
    #     "orientationData": {'expectedState': "OFF", 'currentState': None, 'pinNumber': None},
    #     "fileHash": {},
    #     "executeSpeedTest": False,
    #     "windowsEnumTesting": False,
    #     "httpAddress": ""
    # }

    STATES: List[str] = ['OFF', 'STARTUP_SELF_TEST', 'STANDBY_MODE', 'UNLOCKED_ADMIN']

    logger: logging.Logger
    at: 'UnifiedController' # Use the actual class name if imported
    machine: Machine
    state: str # Current state
    source_state: str # State before the current transition

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
        self.state = self.machine.initial # Explicitly set initial state variable
        self.source_state = self.machine.initial # Initialize source_state

        # Define transition triggers (methods will be dynamically created by transitions)
        self.standby_mode: callable
        self.power_on: callable
        self.power_off: callable
        # self.post_successful_standby_detected: callable # This was from my previous incorrect version
        self.post_failed: callable
        self.critical_error_detected: callable
        self.unlock_admin: callable
        self.lock_admin: callable

        # --- Transitions ---
        self.machine.add_transition(trigger='power_on', source='OFF', dest='STARTUP_SELF_TEST')                         # Power on, confirm Startup Self-Test
        self.machine.add_transition(trigger='standby_mode', source='STARTUP_SELF_TEST', dest='STANDBY_MODE')            # Confirm Standby Mode
        self.machine.add_transition(trigger='power_off', source='STANDBY_MODE', dest='OFF')                             # Power off, confirm DUT LEDs off
        self.machine.add_transition(trigger='unlock_admin', source='STANDBY_MODE', dest='UNLOCKED_ADMIN')               # Unlock DUT using Admin PIN
        self.machine.add_transition(trigger='lock_admin', source='UNLOCKED_ADMIN', dest='STANDBY_MODE')                 # Lock DUT from Admin enum


    def _log_state_change_details(self, event_data: EventData) -> None:
        self.source_state: str = event_data.transition.source
        event_name: str = event_data.event.name
        # self.state is updated by the Machine before this callback
        self.logger.info(f"State changed: {self.source_state} -> {self.state} (Event: {event_name})")
        if event_data.kwargs: # Log any extra data passed with the event trigger
            self.logger.debug(f"  Event details: {event_data.kwargs}")

    # --- on_enter_STATENAME Callbacks (State-specific logic) ---
    def on_enter_OFF(self, event_data: EventData) -> None:
        self.at.off("usb3")
        self.at.off("connect")

        replay_ctx = {
            "replay_script_name": os.path.basename(__file__),
            "replay_fsm_function": "on_enter_OFF",
            "replay_fsm_source_state": self.source_state,
            "replay_fsm_current_state": self.state # OFF
        }
        power_off_ok: bool = self.at.confirm_led_solid(
            LEDs['ALL_OFF'], 
            minimum=3.0, 
            timeout=5.0,
            clear_buffer=True, # Expecting a stable state now
            **replay_ctx
        )

        if not power_off_ok:
            self.logger.error("Failed DUT off LED confirmation...")
            # self.post_failed was present here before, which might be confusing
            # if called from a state other than STARTUP_SELF_TEST.
            # If this is a critical failure, consider self.critical_error_detected
            # For now, just logging the error.
            # self.post_failed(details="POWER_OFF_LED_CONFIRM_FAIL_IN_ON_ENTER_OFF")
            return

        self.logger.info("Device is now OFF.")

    def on_enter_STARTUP_SELF_TEST(self, event_data: EventData) -> None:
        self.logger.info("Powering DUT on...")
        self.at.on("usb3")
        self.at.on("connect")

        replay_ctx = {
            "replay_script_name": os.path.basename(__file__),
            "replay_fsm_function": "on_enter_STARTUP_SELF_TEST",
            "replay_fsm_source_state": self.source_state,
            "replay_fsm_current_state": self.state # STARTUP_SELF_TEST
        }
        post_animation_observed_ok: bool = self.at.confirm_led_pattern(
            LEDs['STARTUP'], clear_buffer=True, **replay_ctx
        )

        if not post_animation_observed_ok:
            self.logger.error("Failed Startup Self-Test LED confirmation...")
            self.post_failed(details="POST_ANIMATION_MISMATCH") # Pass details
            return
        # If successful, the FSM expects 'standby_mode' trigger to move to STANDBY_MODE
        # This is handled by on_exit_STARTUP_SELF_TEST calling self.confirm_standby_mode()
        # which then should trigger self.standby_mode() if successful.

    def on_exit_STARTUP_SELF_TEST(self, event_data: EventData) -> None:
        # This is called when STARTUP_SELF_TEST is being exited.
        # If post_animation_observed_ok was true, we should now confirm standby.
        # The 'standby_mode' trigger will be called if confirm_standby_mode is successful.
        if self.confirm_standby_mode(event_data): # Pass event_data if needed by confirm_standby_mode context
            self.standby_mode() # This is the trigger to move to STANDBY_MODE state.
        else:
            # If it didn't settle into standby, it's effectively a POST failure.
            self.logger.error("Did not settle into standby mode after POST animation.")
            self.post_failed(details="NO_STANDBY_AFTER_POST_ANIMATION")


    def on_exit_STANDBY_MODE(self, event_data: EventData) -> None:
        # This is called when exiting STANDBY_MODE.
        # If the reason for exiting is to go to UNLOCKED_ADMIN (i.e., source_state was STANDBY_MODE and dest will be UNLOCKED_ADMIN)
        # then enter_admin_pin should be called.
        # The FSM's 'unlock_admin' trigger handles the transition to UNLOCKED_ADMIN.
        # The actual PIN entry logic is better placed in an 'after_unlock_admin_requested' if we had one,
        # or called directly by whatever triggers 'unlock_admin'.
        # For your current structure, if unlock_admin is triggered, this exit callback might not be the best place for enter_admin_pin.
        # However, to keep minimal changes to your structure:
        # This condition checks if we came from STARTUP_SELF_TEST and are now likely proceeding to unlock.
        # A more robust way is to check event_data.transition.dest if available and matches UNLOCKED_ADMIN.
        
        # Based on your original logic: if self.source_state == "STARTUP_SELF_TEST":
        # This seems like it was intended if STARTUP_SELF_TEST -> STANDBY_MODE, then unlock.
        # Let's assume 'unlock_admin' trigger is called separately.
        # The previous `if self.source_state == "STARTUP_SELF_TEST": self.enter_admin_pin()` here implied
        # that after POST and reaching standby, it would automatically try to unlock.
        # If 'unlock_admin' is the explicit trigger for unlocking, then `enter_admin_pin` should be
        # part of the action associated with that trigger, not this generic on_exit.
        # For now, I will remove it from here to avoid auto-unlocking unless explicitly requested.
        pass


    def on_exit_UNLOCKED_ADMIN(self, event_data: EventData) -> None:
        self.logger.info(f"Locking DUT from Unlocked Admin...")
        self.at.press("lock")
        # After pressing lock, we expect it to go to standby.
        # The 'lock_admin' trigger should lead to STANDBY_MODE.
        # confirm_standby_mode should verify this.
        if self.confirm_standby_mode(event_data): # Pass event_data for context
            # The FSM should already be transitioning to STANDBY_MODE due to 'lock_admin' trigger.
            # No need to call self.standby_mode() here.
            pass
        else:
            self.logger.error("Failed to confirm standby after locking from admin.")
            self.critical_error_detected(details="LOCK_FROM_ADMIN_FAILED_STANDBY_CONFIRM")


    ####################################################################################

    # Renamed parameter to avoid conflict with built-in 'event'
    def confirm_standby_mode(self, fsm_event_data: Optional[EventData] = None): # Added Optional event_data
        self.logger.info(f"Confirming Standby Mode...")
        
        replay_ctx = {
            "replay_script_name": os.path.basename(__file__),
            "replay_fsm_function": "confirm_standby_mode",
            "replay_fsm_source_state": self.source_state, # The state before this check
            "replay_fsm_current_state": self.state    # The state during this check
        }
        if fsm_event_data and hasattr(fsm_event_data, 'event') and fsm_event_data.event:
             replay_ctx["replay_fsm_trigger_event"] = fsm_event_data.event.name


        standby_confirmed: bool = self.at.confirm_led_solid(
            LEDs['STANDBY_MODE'],
            minimum=3.0,
            timeout=5.0,
            clear_buffer=True,
            **replay_ctx
        )
        if not standby_confirmed:
            self.logger.error(f"Failed to confirm stable STANDBY_MODE LEDs. Device state uncertain.")
            # This was self.critical_error_detected before, which is a state transition.
            # If this function is just a checker, it should return bool.
            # Let the caller decide on state transition.
            # self.critical_error_detected(details="STANDBY_LED_CONFIRMATION_FAILED")
            return False # Indicate failure
        self.logger.info("Stable STANDBY_MODE LEDs confirmed.")
        return True # Indicate success
    
    def enter_admin_pin(self, fsm_event_data: Optional[EventData] = None): # Added Optional event_data
        self.logger.info("Unlocking DUT with Admin PIN...")

        self.at.sequence(["key1", "key1", "key2", "key2", "key3", "key3", "key4", "key4", "unlock"])
        
        replay_ctx = {
            "replay_script_name": os.path.basename(__file__),
            "replay_fsm_function": "enter_admin_pin",
            "replay_fsm_source_state": self.source_state, # Likely STANDBY_MODE
            "replay_fsm_current_state": self.state    # State when this action is called
        }
        if fsm_event_data and hasattr(fsm_event_data, 'event') and fsm_event_data.event:
             replay_ctx["replay_fsm_trigger_event"] = fsm_event_data.event.name


        unlock_admin_ok: bool = self.at.await_and_confirm_led_pattern(
            LEDs['ENUM'], timeout = 15, clear_buffer=True, **replay_ctx
        )

        if not unlock_admin_ok:
            self.logger.error("Failed DUT unlock LED confirmation...")
            self.post_failed(details="ADMIN_UNLOCK_ENUM_PATTERN_MISMATCH") # Pass details
            return False # Indicate failure
        
        self.at.confirm_enum() # This method does not currently support replay context.
        return True # Indicate success