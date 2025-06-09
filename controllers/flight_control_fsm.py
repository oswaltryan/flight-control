# Directory: controllers
# Filename: flight_control_fsm.py

import logging
import time # For simulating delays if needed
from typing import List, Dict, Tuple, Any, Optional, Callable # For type hinting
import os
from pprint import pprint
import json
from camera.led_dictionaries import LEDs

### For running scripts
# from transitions import Machine, EventData
###

### For generating a diagram
from transitions.extensions import GraphMachine as Machine
from transitions import EventData
###

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
    device_name = "padlock3-3637"

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

    # MODIFICATION: Changed to an empty list to represent a new, un-enrolled device.
    # The FSM will correctly start in OOB_MODE.
    adminPIN = []
    oldAdminPIN = []

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

DUT = DeviceUnderTest()

## --- FSM Class Definition ---
class SimplifiedDeviceFSM:

    STATES: List[str] = ['OFF', 'STARTUP_SELF_TEST', 'OOB_MODE', 'STANDBY_MODE', 'UNLOCKED_ADMIN', 'POST_FAILED', 'ADMIN_MODE']

    logger: logging.Logger
    at: 'UnifiedController'
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
            send_event=True,
            after_state_change='_log_state_change_details',
            # MODIFICATION: Changed to True to let transitions find on_enter_STATE methods by convention.
            auto_transitions=False,
            use_pygraphviz=False
        )

        self.source_state = 'OFF'

        self.power_on: Callable
        self.post_test_complete: Callable
        self.power_off: Callable
        self.unlock_admin: Callable
        self.lock_admin: Callable
        self.post_failed: Callable
        self.enroll_admin: Callable

        # --- REFACTORED TRANSITIONS ---
        # The 'before' callback performs the action. If it returns True, the transition to STARTUP_SELF_TEST occurs.
        self.machine.add_transition(trigger='power_on', source='OFF', dest='STARTUP_SELF_TEST', before='do_power_on_and_test')
        self.machine.add_transition(trigger='post_failed', source='STARTUP_SELF_TEST', dest='POST_FAILED')
        self.machine.add_transition(trigger='power_off', source=['STANDBY_MODE', 'OOB_MODE', 'POST_FAILED', 'ADMIN_MODE'], dest='OFF')

        # The 'on_enter' for the new state now triggers the *next* logical step.
        self.machine.add_transition(trigger='post_test_complete', source='STARTUP_SELF_TEST', dest='OOB_MODE', conditions=[lambda _: not DUT.adminPIN])
        self.machine.add_transition(trigger='post_test_complete', source='STARTUP_SELF_TEST', dest='STANDBY_MODE', conditions=[lambda _: bool(DUT.adminPIN)])

        # MODIFICATION: The 'enroll_admin' transition now uses a dedicated 'before' callback to perform the enrollment actions.
        # The 'on_enter_ADMIN_MODE' method will be called automatically after the transition succeeds.
        self.machine.add_transition(trigger='enroll_admin', source='OOB_MODE', dest='ADMIN_MODE', before='admin_enrollment')

        self.machine.add_transition(trigger='unlock_admin', source='STANDBY_MODE', dest='UNLOCKED_ADMIN', before='enter_admin_pin')
        self.machine.add_transition(trigger='lock_admin', source='UNLOCKED_ADMIN', dest='STANDBY_MODE', before='press_lock_button')


    def _log_state_change_details(self, event_data: EventData) -> None:
        if event_data.transition is None:
            self.logger.info(f"FSM initialized to state: {self.state}")
            return
        self.source_state = event_data.transition.source
        self.logger.info(f"State changed: {self.source_state} -> {self.state} (Event: {event_data.event.name})")

    def do_power_on_and_test(self, event_data: EventData) -> bool:
        """
        This is a 'before' callback. It performs the power-on and POST.
        It must return True for the transition to proceed, or False to cancel it.
        """
        self.logger.info("Powering DUT on and performing self-test...")
        self.at.on("usb3")
        self.at.on("connect")
        time.sleep(0.5)

        post_animation_observed_ok: bool = self.at.confirm_led_pattern(LEDs['STARTUP'], clear_buffer=True)

        if not post_animation_observed_ok:
            self.logger.error("Failed Startup Self-Test LED confirmation. Aborting transition.")
            self.post_failed(details="POST_ANIMATION_MISMATCH")
            return False # This stops the FSM from entering the STARTUP_SELF_TEST state
        
        self.logger.info("Startup Self-Test successful. Proceeding to STARTUP_SELF_TEST state.")
        return True # Allows the transition to complete
    
    def on_enter_ADMIN_MODE(self, event_data: EventData) -> None:
        """
        Called automatically upon entering the ADMIN_MODE state.
        Confirms the device shows the correct stable LED state.
        """
        self.logger.info(f"Entered ADMIN_MODE. Confirming stable state (solid Blue)...")
        if self.at.confirm_led_solid(LEDs['ADMIN_MODE'], minimum=3.0, timeout=5.0):
            self.logger.info(f"Stable ADMIN_MODE confirmed.")
        else:
            self.logger.error(f"Failed to confirm stable ADMIN_MODE LEDs.")

    def on_enter_STARTUP_SELF_TEST(self, event_data: EventData) -> None:
        """
        Now this callback is very simple. Its only job is to trigger the next logical step.
        The FSM is now officially in this state.
        """
        self.logger.info("Entered STARTUP_SELF_TEST state. Evaluating next transition...")
        self.post_test_complete()

    def on_enter_OFF(self, event_data: EventData) -> None:
        self.at.off("usb3")
        self.at.off("connect")
        if self.at.confirm_led_solid(LEDs['ALL_OFF'], minimum=1.0, timeout=3.0):
            self.logger.info("Device is confirmed OFF.")
        else:
            self.logger.error("Failed to confirm device LEDs are OFF.")
    
    def on_enter_OOB_MODE(self, event_data: EventData) -> None:
        self.logger.info(f"Confirming OOB Mode (solid Green/Blue)...")
        if self.at.confirm_led_solid(LEDs['GREEN_BLUE_STATE'], minimum=3.0, timeout=5.0):
            self.logger.info("Stable OOB_MODE confirmed.")
        else:
            self.logger.error("Failed to confirm OOB_MODE LEDs.")

    def on_enter_STANDBY_MODE(self, event_data: EventData) -> None:
        self.logger.info(f"Confirming Standby Mode (solid Red)...")
        if self.at.confirm_led_solid(LEDs['STANDBY_MODE'], minimum=3.0, timeout=5.0):
            self.logger.info("Stable STANDBY_MODE confirmed.")
        else:
            self.logger.error("Failed to confirm STANDBY_MODE LEDs.")

    def on_enter_UNLOCKED_ADMIN(self, event_data: EventData) -> None:
        self.logger.info("Confirming device enumeration post-unlock...")
        if not self.at.confirm_enum():
             self.logger.error("Device did not enumerate after admin unlock.")
             self.post_failed(details="ADMIN_UNLOCK_ENUM_FAILED")
        else:
             self.logger.info("Admin unlock successful, device enumerated.")

    def admin_enrollment(self, new_pin, event_data: EventData) -> bool:
        """
        Performs the full admin enrollment procedure. This is a 'before'
        callback, returning True allows the state transition to proceed.
        Call it via: fsm.enroll_admin(pin=['key1', 'key2', ...])
        """

        self.logger.info(f"Entering Admin PIN Enrollment...")
        self.at.sequence(['unlock', 'key9'])
        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0):
            self.logger.error("Did not observe GREEN_BLUE pattern. Enrollment aborted.")
            return False

        self.logger.info(f"Entering new Admin PIN (first time)...")
        self.at.sequence(new_pin)

        self.logger.info("Verifying PIN confirmation...")
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0):
            self.logger.error("Did not observe ACCEPT_PATTERN pattern after first PIN entry.")
            return False

        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0):
            self.logger.error("Did not observe GREEN_BLUE pattern after first PIN entry. Enrollment aborted.")
            return False

        self.logger.info("Re-entering Admin PIN for confirmation...")
        self.at.sequence(new_pin)
        
        self.logger.info("Awaiting 'ACCEPT_PATTERN' to confirm successful enrollment...")
        if not self.at.await_led_state(LEDs['ACCEPT_STATE'], timeout=5.0):
            self.logger.error("Did not observe ACCEPT_PATTERN after PIN confirmation. Enrollment likely failed.")
            return False
            
        self.logger.info("Admin enrollment sequence completed successfully. Updating DUT model.")
        
        # The standard admin PIN sequence in DUT includes the 'unlock' action. We add it here
        # so the DUT model is consistent with how it's used for unlocking later.
        DUT.adminPIN = new_pin + ['unlock']
        self.logger.info("Updated DUT with new admin PIN. Allowing FSM transition to ADMIN_MODE.")
        
        return True

    def enter_admin_pin(self, event_data: EventData) -> bool:
        self.logger.info("Unlocking DUT with Admin PIN...")
        self.at.sequence(DUT.adminPIN)
        unlock_admin_ok: bool = self.at.await_and_confirm_led_pattern(LEDs['ENUM'], timeout=15)
        if not unlock_admin_ok:
            self.logger.error("Failed admin unlock LED pattern. Aborting transition.")
            self.post_failed(details="ADMIN_UNLOCK_PATTERN_MISMATCH")
            return False # Cancel the transition
        return True

    def press_lock_button(self, event_data: EventData) -> None:
        self.logger.info(f"Locking DUT from Unlocked Admin...")
        self.at.press("lock")
