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
        self.source_state = self.machine.initial

        # Define transition triggers (methods will be dynamically created by transitions)
        self.standby_mode: callable
        self.power_on: callable
        self.power_off: callable
        self.post_successful_standby_detected: callable
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
        current_state: str = self.state # self.state is updated by the Machine
        self.logger.info(f"State changed: {self.source_state} -> {current_state} (Event: {event_name})")
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

    def on_exit_STARTUP_SELF_TEST(self, event_data: EventData) -> None:
        self.confirm_standby_mode()
        
    def on_exit_STANDBY_MODE(self, event_data: EventData) -> None:
        if self.source_state == "STARTUP_SELF_TEST":
            self.enter_admin_pin()

    def on_exit_UNLOCKED_ADMIN(self, event_data: EventData) -> None:
        self.logger.info(f"Locking DUT from Unlocked Admin...")
        self.at.press("lock")
        self.confirm_standby_mode()

    ####################################################################################

    def confirm_standby_mode(self):
        self.logger.info(f"Confirming Standby Mode...")
        
        standby_confirmed: bool = self.at.confirm_led_solid(
            LEDs['STANDBY_MODE'],
            minimum=3.0,
            timeout=5.0,
            clear_buffer=True
        )
        if not standby_confirmed:
            self.logger.error(f"Failed to confirm stable STANDBY_MODE LEDs. Device state uncertain. Triggering critical error.")
            self.critical_error_detected(details="STANDBY_LED_CONFIRMATION_FAILED") # Pass details
            return
        self.logger.info("Stable STANDBY_MODE LEDs confirmed.")
        return standby_confirmed
    
    def enter_admin_pin(self):
        self.logger.info("Unlocking DUT with Admin PIN...")

        self.at.sequence(["key1", "key1", "key2", "key2", "key3", "key3", "key4", "key4", "unlock"])
        unlock_admin_ok: bool = self.at.await_and_confirm_led_pattern(LEDs['ENUM'], timeout = 15, clear_buffer=True)

        if not unlock_admin_ok:
            self.logger.error("Failed DUT unlock LED confirmation...")
            self.post_failed(details="POST_ANIMATION_MISMATCH") # Pass details
            return
        
        self.at.confirm_enum()
