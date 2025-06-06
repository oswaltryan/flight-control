# Directory: controllers
# Filename: flight_control_fsm.py

import logging
import time # For simulating delays if needed
from typing import List, Dict, Tuple, Any, Optional, Callable # For type hinting
import os
from pprint import pprint
import json
from camera.led_dictionaries import LEDs
from transitions import Machine, EventData # Import EventData for type hinting
from usb_tool import find_apricorn_device


from .unified_controller import UnifiedController

# --- Load External JSON Configuration ---
# Get a logger for this module-level operation
_fsm_module_logger = logging.getLogger(__name__)

# Initialize the variable that will hold the data.
# Using ALL_CAPS is a convention for module-level constants.
DEVICE_PROPERTIES: Dict[str, Any] = {}

# --- Path Construction (moved outside the try block) ---
# This logic is deterministic and guarantees _json_path is always assigned.
_current_file_path = os.path.abspath(__file__)
_controllers_dir = os.path.dirname(_current_file_path)
_project_root = os.path.dirname(_controllers_dir)
_json_path = os.path.join(_project_root, 'utils', 'device_properties.json')


# --- File I/O and Parsing (operations that can fail are kept in the try block) ---
try:
    _fsm_module_logger.debug(f"Attempting to load module config from: {_json_path}")
    with open(_json_path, 'r') as f:
        DEVICE_PROPERTIES = json.load(f)
    _fsm_module_logger.info("Successfully loaded module-level DEVICE_PROPERTIES from JSON.")
except FileNotFoundError:
    _fsm_module_logger.critical(f"Configuration file not found at '{_json_path}'. Cannot continue.")
    raise
except json.JSONDecodeError:
    _fsm_module_logger.critical(f"Could not parse '{_json_path}'. Check for syntax errors.")
    raise
except Exception as e:
    _fsm_module_logger.critical(f"An unexpected error occurred while loading '{_json_path}': {e}", exc_info=True)
    raise

class DeviceUnderTest:
    device_name = "ask3-3639"

    name = device_name
    battery = False
    batteryVBUS = False
    VBUS = True
    bridgeFW = DEVICE_PROPERTIES[device_name]['bridgeFW']
    mcuFW = []
    mcuFWHumanReadable = ""
    fips = DEVICE_PROPERTIES[device_name]['fips']
    secureKey = DEVICE_PROPERTIES[device_name]['secureKey']
    usb3 = False
    diskPath = ""
    mounted = False
    serialNumber = ""
    devKeypadSerialNumber = ""

    CMFR = False
    modelID1 = DEVICE_PROPERTIES[device_name]['model_id_digit_1']
    modelID2 = DEVICE_PROPERTIES[device_name]['model_id_digit_2']
    hardwareID1 = DEVICE_PROPERTIES[device_name]['hardware_major']
    hardwareID2 = DEVICE_PROPERTIES[device_name]['hardware_minor']
    scbPartNumber = DEVICE_PROPERTIES[device_name]['singleCodeBasePartNumber']
    singleCodeBase = DEVICE_PROPERTIES[device_name]['singleCodeBase']
    
    basicDisk = True
    removableMedia = False
    
    bruteForceCounter = 20
    
    ledFlicker = False
    lockOverride = False

    manufacturerResetEnum = False

    maxPINCounter = 16
    minPINCounter = int(DEVICE_PROPERTIES[device_name]['minpin'])
    defaultMinPINCounter = int(DEVICE_PROPERTIES[device_name]['minpin'])

    provisionLock = False
    provisionLockBricked = False
    provisionLockRecoverCounter = 5

    readOnlyEnabled = False

    unattendedAutoLockCounter = 0

    userForcedEnrollmentUsed = False

    adminPIN = {}
    oldAdminPIN = {}
    adminEnum = False

    recoveryPIN = {1: {}, 2: {}, 3: {}, 4: {}}
    oldRecoveryPIN = {1: {}, 2: {}, 3: {}, 4: {}}
    usedRecovery = {1: False, 2: False, 3: False, 4: False}
    
    selfDestructEnabled = False
    selfDestructPIN = {}
    oldSelfDestructPIN = {}
    selfDestructEnum = False
    selfDestructUsed = False

    userCount = DEVICE_PROPERTIES[device_name]['userCount']
    userPIN = {1: None, 2: None, 3: None, 4: None}
    oldUserPIN = {1: None, 2: None, 3: None, 4: None}
    enumUser = {1: False, 2: False, 3: False, 4: False}

# --- FSM Class Definition ---
class SimplifiedDeviceFSM:

    STATES: List[str] = ['OFF', 'STARTUP_SELF_TEST', 'STANDBY_MODE', 'UNLOCKED_ADMIN']

    logger: logging.Logger
    at: 'UnifiedController' # Use the actual class name if imported
    machine: Machine
    state: str
    source_state: str

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

        self.source_state = 'OFF'

        # Define transition triggers (methods will be dynamically created by transitions)
        self.standby_mode: Callable
        self.power_on: Callable
        self.power_off: Callable
        self.post_successful_standby_detected: Callable
        self.post_failed: Callable
        self.critical_error_detected: Callable
        self.unlock_admin: Callable
        self.lock_admin: Callable

        # --- Transitions ---
        self.machine.add_transition(trigger='power_on', source='OFF', dest='STARTUP_SELF_TEST')                         # Power on, confirm Startup Self-Test
        self.machine.add_transition(trigger='standby_mode', source='STARTUP_SELF_TEST', dest='STANDBY_MODE')            # Confirm Standby Mode
        self.machine.add_transition(trigger='power_off', source='STANDBY_MODE', dest='OFF')                             # Power off, confirm DUT LEDs off
        self.machine.add_transition(trigger='unlock_admin', source='STANDBY_MODE', dest='UNLOCKED_ADMIN')               # Unlock DUT using Admin PIN
        self.machine.add_transition(trigger='lock_admin', source='UNLOCKED_ADMIN', dest='STANDBY_MODE')                 # Lock DUT from Admin enum


    def _log_state_change_details(self, event_data: EventData) -> None:
        assert event_data.transition is not None, "after_state_change callback must have a transition"
        self.source_state = event_data.transition.source
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
