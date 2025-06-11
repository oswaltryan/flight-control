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

# --- Custom Exception for Transition Failures ---
class TransitionCallbackError(Exception):
    """Custom exception to be raised from 'before' callbacks on failure."""
    pass

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
    bruteForceCurrent = 20
    
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

    userForcedEnrollment = False
    userForcedEnrollmentUsed = False

    adminPIN = []
    oldAdminPIN = []

    recoveryPIN: Dict[int, Dict] = {1: {}, 2: {}, 3: {}, 4: {}}
    oldRecoveryPIN: Dict[int, Dict] = {1: {}, 2: {}, 3: {}, 4: {}}
    usedRecovery: Dict[int, bool] = {1: False, 2: False, 3: False, 4: False}
    
    selfDestructEnabled = False
    selfDestructPIN = []
    oldSelfDestructPIN = []
    selfDestructEnum = False
    selfDestructUsed = False

    userCount = DEVICE_PROPERTIES[device_name]['userCount']
    userPIN: Dict[int, Optional[List[str]]] = {1: None, 2: None, 3: None, 4: None}
    oldUserPIN: Dict[int, Optional[List[str]]] = {1: None, 2: None, 3: None, 4: None}
    enumUser: Dict[int, bool] = {1: False, 2: False, 3: False, 4: False}

DUT = DeviceUnderTest()

## --- FSM Class Definition ---
class SimplifiedDeviceFSM:

    STATES: List[str] = ['OFF', 'POWER_ON_SELF_TEST', 'ERROR_MODE', 'BRUTE_FORCE', 'BRICKED', 'OOB_MODE', 'STANDBY_MODE', 'USER_FORCED_ENROLLMENT',
                         'UNLOCKED_ADMIN', 'UNLOCKED_USER',
                         'ADMIN_MODE', 'DIAGNOSTIC_MODE'
    ]

    logger: logging.Logger
    at: 'UnifiedController'
    machine: Machine
    state: str
    source_state: str = 'OFF'

    def __init__(self, at_controller: 'UnifiedController'):
        self.logger = logging.getLogger("DeviceFSM.Simplified")
        self.at = at_controller

        self.machine = Machine(
            model=self,
            states=SimplifiedDeviceFSM.STATES,
            initial='OFF',
            send_event=True,
            after_state_change='_log_state_change_details',
            auto_transitions=True, # MODIFICATION: Changed to True to let transitions find on_enter_STATE methods by convention.
            graph_engine='pygraphviz'
        )

        # --- TRANSITIONS ---
        # --- Power On/Off Transitions ---
        self.power_on: Callable
        self.post_fail: Callable
        self.power_off: Callable
        self.machine.add_transition(trigger='power_on', source='OFF', dest='POWER_ON_SELF_TEST', before='do_power_on')
        self.machine.add_transition(trigger='post_fail', source='POWER_ON_SELF_TEST', dest='ERROR_MODE')
        self.machine.add_transition(trigger='power_off', source="*", dest='OFF')

        # --- 'Idle' Mode Transitions ---
        self.post_pass: Callable
        self.machine.add_transition(trigger='post_pass', source='POWER_ON_SELF_TEST', dest='OOB_MODE', conditions=[lambda _: not DUT.adminPIN])
        self.machine.add_transition(trigger='post_pass', source='POWER_ON_SELF_TEST', dest='USER_FORCED_ENROLLMENT', conditions=[lambda _: bool(DUT.userForcedEnrollment)])
        self.machine.add_transition(trigger='post_pass', source='POWER_ON_SELF_TEST', dest='BRUTE_FORCE', conditions=[lambda _: DUT.bruteForceCounter == 0])
        self.machine.add_transition(trigger='post_pass', source='POWER_ON_SELF_TEST', dest='STANDBY_MODE', conditions=[lambda _: bool(DUT.adminPIN)])

        # --- OOB Mode Transitions ---
        self.enter_diagnostic_mode: Callable
        self.exit_diagnostic_mode: Callable
        self.enroll_admin: Callable
        self.user_reset: Callable
        self.machine.add_transition(trigger='enter_diagnostic_mode', source='OOB_MODE', dest='DIAGNOSTIC_MODE')
        self.machine.add_transition(trigger='exit_diagnostic_mode', source='DIAGNOSTIC_MODE', dest='OOB_MODE', conditions=[lambda _: not DUT.adminPIN])
        self.machine.add_transition(trigger='enroll_admin', source='OOB_MODE', dest='ADMIN_MODE', before='admin_enrollment')
        self.machine.add_transition(trigger='user_reset', source='OOB_MODE', dest='OOB_MODE', conditions=[lambda _: not DUT.provisionLock])

        # --- Standby Mode Transitions ---
        self.fail_unlock: Callable
        self.machine.add_transition(trigger='admin_mode_login', source='STANDBY_MODE', dest='ADMIN_MODE', before='enter_admin_mode')
        self.machine.add_transition(trigger='lock_admin', source='ADMIN_MODE', dest='STANDBY_MODE', before='press_lock_button')
        self.machine.add_transition(trigger='unlock_admin', source='STANDBY_MODE', dest='UNLOCKED_ADMIN', before='enter_admin_pin')
        self.machine.add_transition(trigger='lock_admin', source='UNLOCKED_ADMIN', dest='STANDBY_MODE', before='press_lock_button')
        self.machine.add_transition(trigger='enter_diagnostic_mode', source='STANDBY_MODE', dest='DIAGNOSTIC_MODE')
        self.machine.add_transition(trigger='self_destruct', source='STANDBY_MODE', dest='UNLOCKED_ADMIN', before='enter_self_destruct_pin')
        self.machine.add_transition(trigger='exit_diagnostic_mode', source='DIAGNOSTIC_MODE', dest='STANDBY_MODE', conditions=[lambda _: bool(DUT.adminPIN)])
        self.machine.add_transition(trigger='user_reset', source='STANDBY_MODE', dest='OOB_MODE', conditions=[lambda _: not DUT.provisionLock])
        self.machine.add_transition(trigger='unlock_user', source='STANDBY_MODE', dest='UNLOCKED_USER', before='enter_user_pin')
        self.machine.add_transition(trigger='lock_user', source='UNLOCKED_USER', dest='STANDBY_MODE', before='press_lock_button')
        self.machine.add_transition(trigger='fail_unlock', source='STANDBY_MODE', dest='STANDBY_MODE', before='enter_invalid_pin', conditions=[lambda _: DUT.bruteForceCurrent > 1])
        self.machine.add_transition(trigger='fail_unlock', source='STANDBY_MODE', dest='BRUTE_FORCE', before='enter_invalid_pin', conditions=[lambda _: DUT.bruteForceCurrent == DUT.bruteForceCounter/2 or DUT.bruteForceCurrent == 0])


        # --- User-Forced Enrollment Mode Transitions ---
        self.unlock_admin: Callable
        self.admin_mode_login: Callable
        self.enroll_user: Callable
        self.self_destruct: Callable
        self.machine.add_transition(trigger='admin_mode_login', source='USER_FORCED_ENROLLMENT', dest='ADMIN_MODE', before='enter_admin_mode')
        self.machine.add_transition(trigger='lock_admin', source='ADMIN_MODE', dest='USER_FORCED_ENROLLMENT', before='press_lock_button')
        self.machine.add_transition(trigger='unlock_admin', source='USER_FORCED_ENROLLMENT', dest='UNLOCKED_ADMIN', before='enter_admin_pin')
        self.machine.add_transition(trigger='lock_admin', source='UNLOCKED_ADMIN', dest='USER_FORCED_ENROLLMENT', before='press_lock_button')
        self.machine.add_transition(trigger='enroll_user', source='USER_FORCED_ENROLLMENT', dest='STANDBY_MODE', before='user_enrollment')
        self.machine.add_transition(trigger='enter_diagnostic_mode', source='USER_FORCED_ENROLLMENT', dest='DIAGNOSTIC_MODE')
        self.machine.add_transition(trigger='exit_diagnostic_mode', source='DIAGNOSTIC_MODE', dest='USER_FORCED_ENROLLMENT', conditions=[lambda _: not DUT.adminPIN])
        self.machine.add_transition(trigger='self_destruct', source='USER_FORCED_ENROLLMENT', dest='UNLOCKED_ADMIN', before='enter_self_destruct_pin')
        self.machine.add_transition(trigger='user_reset', source='USER_FORCED_ENROLLMENT', dest='OOB_MODE', conditions=[lambda _: not DUT.provisionLock])
        self.machine.add_transition(trigger='unlock_user', source='USER_FORCED_ENROLLMENT', dest='UNLOCKED_USER', before='enter_user_pin', conditions=[lambda: any(pin is not None for pin in DUT.userPIN.values())])
        self.machine.add_transition(trigger='lock_user', source='UNLOCKED_USER', dest='USER_FORCED_ENROLLMENT', before='press_lock_button')
        self.machine.add_transition(trigger='fail_unlock', source='USER_FORCED_ENROLLMENT', dest='STANDBY_MODE', before='enter_invalid_pin', conditions=[lambda _: DUT.bruteForceCurrent > 1])
        self.machine.add_transition(trigger='fail_unlock', source='USER_FORCED_ENROLLMENT', dest='BRUTE_FORCE', before='enter_invalid_pin', conditions=[lambda _: DUT.bruteForceCurrent == DUT.bruteForceCounter/2 or DUT.bruteForceCurrent == 0])

        # --- Brute Force Mode Transitions ---
        self.admin_recovery_failed: Callable
        self.machine.add_transition(trigger='last_try_login', source='BRUTE_FORCE', dest='STANDBY_MODE', before='enter_last_try_pin', conditions=[lambda _: DUT.bruteForceCurrent == DUT.bruteForceCounter/2])
        self.machine.add_transition(trigger='user_reset', source='BRUTE_FORCE', dest='OOB_MODE', conditions=[lambda _: not DUT.provisionLock])
        self.machine.add_transition(trigger='admin_recovery_failed', source='BRUTE_FORCE', dest='BRICKED')
        
        # --- Admin Mode Transitions ---
        self.user_reset: Callable
        self.machine.add_transition(trigger='user_reset', source='ADMIN_MODE', dest='OOB_MODE', before='do_user_reset')
        self.machine.add_transition(trigger='enroll_user', source='ADMIN_MODE', dest='ADMIN_MODE', before='user_enrollment')


        # self.machine.add_transition(trigger='set_brute_force_counter', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='change_admin_pin', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='enroll_self_destruct_pin', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='set_min_pin_length', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='enroll_recovery_pin', source='ADMIN_MODE', dest='ADMIN_MODE')

        # --- Admin Mode Toggle Transitions ---
        # self.machine.add_transition(trigger='toggle_basic_disk', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='delete_pins', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='toggle_led_flicker', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='toggle_lock_override', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='enable_provision_lock', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='toggle_read_only', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='toggle_read_write', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='toggle_removable_media', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='toggle_self_destruct', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='set_unattended_autolock', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='toggle_user_forced_enrollment', source='ADMIN_MODE', dest='ADMIN_MODE')

        # --- Admin Mode Transition ---
        self.enroll_admin: Callable
        self.lock_admin: Callable
        

        # --- Admin Enum Transition ---
        self.unlock_admin: Callable

        # --- User Enum Transition ---
        self.unlock_user: Callable
        self.lock_user: Callable
        


    def _log_state_change_details(self, event_data: EventData) -> None:
        if event_data.transition is None:
            self.logger.info(f"FSM initialized to state: {self.state}")
            return
        self.source_state = event_data.transition.source
        self.logger.info(f"State changed: {self.source_state} -> {self.state} (Event: {event_data.event.name})")


    ###########################################################################################################
    # Transition Functions (Automatic)
    
    def on_enter_ADMIN_MODE(self, event_data: EventData) -> None:
        """
        Called automatically upon entering the ADMIN_MODE state.
        Confirms the device shows the correct stable LED state.
        """
        self.logger.info(f"Entered ADMIN_MODE. Confirming stable state (solid Blue)...")
        # This callback uses the safe `on_enter` pattern, no change needed.
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        if self.at.confirm_led_solid(LEDs['ADMIN_MODE'], minimum=3.0, timeout=5.0, replay_extra_context=context):
            self.logger.info(f"Stable ADMIN_MODE confirmed.")
        else:
            self.logger.error(f"Failed to confirm stable ADMIN_MODE LEDs.")

    def on_enter_POWER_ON_SELF_TEST(self, event_data: EventData) -> None:
        """
        This function will be the check of whether the POST passed or failed.
        """
        self.logger.info("Entered POWER_ON_SELF_TEST state. Confirming POST result...")
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            self.logger.error("Did not observe ACCEPT_PATTERN pattern. POST failed.")
            self.post_fail()
        else:
            self.post_pass()

    def on_enter_OFF(self, event_data: EventData) -> None:
        self.at.off("usb3")
        self.at.off("connect")
        # This callback uses the safe `on_enter` pattern, no change needed.
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        if self.at.confirm_led_solid(LEDs['ALL_OFF'], minimum=1.0, timeout=3.0, replay_extra_context=context):
            self.logger.info("Device is confirmed OFF.")
        else:
            self.logger.error("Failed to confirm device LEDs are OFF.")
        
    def on_enter_OOB_MODE(self, event_data: EventData) -> None:
        self.logger.info(f"Confirming OOB Mode (solid Green/Blue)...")
        # This callback uses the safe `on_enter` pattern, no change needed.
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        if self.at.confirm_led_solid(LEDs['GREEN_BLUE_STATE'], minimum=3.0, timeout=10.0, replay_extra_context=context):
            self.logger.info("Stable OOB_MODE confirmed.")
        else:
            self.logger.error("Failed to confirm OOB_MODE LEDs.")

    def on_enter_STANDBY_MODE(self, event_data: EventData) -> None:
        self.logger.info(f"Confirming Standby Mode (solid Red)...")
        # This callback uses the safe `on_enter` pattern, no change needed.
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        if self.at.confirm_led_solid(LEDs['STANDBY_MODE'], minimum=3.0, timeout=5.0, replay_extra_context=context):
            self.logger.info("Stable STANDBY_MODE confirmed.")
        else:
            self.logger.error("Failed to confirm STANDBY_MODE LEDs.")

    def on_enter_UNLOCKED_ADMIN(self, event_data: EventData) -> None:
        self.logger.info("Confirming device enumeration post-unlock...")
        if not self.at.confirm_enum():
             self.logger.error("Device did not enumerate after admin unlock.")
             self.post_fail(details="ADMIN_UNLOCK_ENUM_FAILED")
        else:
             self.logger.info("Admin unlock successful, device enumerated.")

    def on_enter_UNLOCKED_USER(self, event_data: EventData) -> None:
        """
        Called automatically upon entering the UNLOCKED_USER state.
        Confirms the device has enumerated correctly.
        """
        self.logger.info("Confirming device enumeration post-user-unlock...")
        if not self.at.confirm_enum():
             self.logger.error("Device did not enumerate after user unlock.")
             self.post_fail(details="USER_UNLOCK_ENUM_FAILED")
        else:
             self.logger.info("User unlock successful, device enumerated.")


    def on_enter_BRUTE_FORCE(self, event_data: EventData) -> None:
        """
        Called automatically upon entering BRUTE_FORCE. It immediately checks
        if the device should be bricked.
        """
        self.logger.info("Entered BRUTE_FORCE mode. Checking conditions...")
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }

        if not self.at.confirm_led_pattern(LEDs['BRUTE_FORCED'], replay_extra_context=context):
            self.logger.error("Failed to confirm BRUTE_FORCE LED pattern.")
        
        # This is the check you wanted to perform on entry.
        if DUT.bruteForceCurrent == 0 and DUT.provisionLock:
            self.logger.warning("Brute force limit reached with provision lock enabled. Admin has 5 attempts to recover DUT...")
            # If the conditions are met, immediately trigger the next transition.
            self.admin_recovery_failed()
        else:
            self.logger.info("Device is in BRUTE_FORCE Mode...")
            # You could add an LED check here for the BRUTE_FORCED pattern if desired.


    ###########################################################################################################
    # Before/After Functions
    
    def do_power_on(self, event_data: EventData) -> None:
        self.logger.info("Powering DUT on and performing self-test...")
        self.at.on("usb3")
        self.at.on("connect")
        time.sleep(0.5)
        # FIX: Safely access destination state
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        if DUT.VBUS:
            if not self.at.confirm_led_pattern(LEDs['STARTUP'], clear_buffer=True, replay_extra_context=context):
                raise TransitionCallbackError("Failed Startup Self-Test LED confirmation.")
            self.logger.info("Startup Self-Test successful. Proceeding to POWER_ON_SELF_TEST state.")

    def admin_enrollment(self, event_data: EventData) -> None:
        new_pin = event_data.kwargs.get('new_pin')
        if not new_pin or not isinstance(new_pin, list):
            raise TransitionCallbackError("Admin enrollment requires a 'new_pin' list.")
        
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Entering Admin PIN Enrollment...")
        self.at.press(['unlock', 'key9'])
        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe GREEN_BLUE pattern.")

        self.logger.info(f"Entering new Admin PIN (first time)...")
        self.at.sequence(new_pin)
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe ACCEPT_PATTERN after first PIN entry.")
        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe GREEN_BLUE pattern after first PIN entry.")

        self.logger.info("Re-entering Admin PIN for confirmation...")
        self.at.sequence(new_pin)
        if not self.at.await_led_state(LEDs['ACCEPT_STATE'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe ACCEPT_PATTERN after PIN confirmation.")
            
        DUT.adminPIN = new_pin
        self.logger.info("Admin enrollment sequence completed successfully. Updated DUT model.")

    def enter_admin_pin(self, event_data: EventData) -> None:
        self.logger.info("Unlocking DUT with Admin PIN...")
        self.at.sequence(DUT.adminPIN)
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        if not self.at.await_and_confirm_led_pattern(LEDs['ENUM'], timeout=15, replay_extra_context=context):
            raise TransitionCallbackError("Failed admin unlock LED pattern.")

    def user_enrollment(self, event_data: EventData) -> int:
        new_pin = event_data.kwargs.get('new_pin')
        if not new_pin or not isinstance(new_pin, list):
            raise TransitionCallbackError("User enrollment requires a 'new_pin' list.")

        max_users = 1 if DUT.fips in [2, 3] else 4
        next_available_slot = next((i for i in range(1, max_users + 1) if DUT.userPIN.get(i) is None), None)

        if next_available_slot is None:
            raise TransitionCallbackError(f"Cannot enroll new user. All {max_users} user slots are full.")
        
        self.logger.info(f"Attempting to enroll new user into logical slot #{next_available_slot}...")
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        self.at.press(['unlock', 'key1'])
        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe GREEN_BLUE pattern for user enrollment.")

        self.logger.info(f"Entering new User PIN (first time)...")
        self.at.sequence(new_pin)
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe ACCEPT_PATTERN after first user PIN entry.")
        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe GREEN_BLUE pattern after first user PIN entry.")

        self.logger.info("Re-entering User PIN for confirmation...")
        self.at.sequence(new_pin)
        if not self.at.confirm_led_solid(LEDs["ACCEPT_STATE"], minimum=1, timeout=3, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe final ACCEPT_PATTERN for user PIN confirmation.")
        
        DUT.userPIN[next_available_slot] = new_pin + ['unlock']
        self.logger.info(f"Successfully enrolled PIN for logical user {next_available_slot}.")
        return next_available_slot
    
    def enter_user_pin(self, event_data: EventData) -> None:
        user_id = event_data.kwargs.get('user_id')
        if not user_id:
            raise TransitionCallbackError("Unlock user requires a 'user_id' to be passed.")
        pin_to_enter = DUT.userPIN.get(user_id)
        if not pin_to_enter:
            raise TransitionCallbackError(f"Unlock failed: No PIN is tracked for logical user {user_id}.")

        self.logger.info(f"Attempting to unlock device with PIN from logical user slot {user_id}...")
        self.at.sequence(pin_to_enter)
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        if not self.at.await_and_confirm_led_pattern(LEDs['ENUM'], timeout=15, replay_extra_context=context):
            raise TransitionCallbackError("Failed user unlock LED pattern.")
        
    def press_lock_button(self, event_data: EventData) -> None:
        self.logger.info(f"Locking DUT from Unlocked Admin...")
        self.at.press("lock")

    def do_user_reset(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        self.logger.info("Initiating User Reset...")
        if self.state == "ADMIN_MODE":
            self.at.sequence([["lock", "unlock", "key2"]])
        reset_pattern_ok = self.at.confirm_led_solid(LEDs["KEY_GENERATION"], minimum=12, timeout=15, replay_extra_context=context)
        if not reset_pattern_ok:
            raise TransitionCallbackError("Failed to observe user reset confirmation pattern.")
        
        self.logger.info("User reset confirmation pattern observed. Resetting DUT model state...")
        DUT.adminPIN = []
        DUT.userPIN = {1: None, 2: None, 3: None, 4: None}
        self.logger.info("DUT model state has been reset.")
    
    def enter_admin_mode(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        self.at.press(['key0', 'unlock'], duration_ms=6000)
        if not self.at.confirm_led_pattern(LEDs['RED_LOGIN'], clear_buffer=True, replay_extra_context=context):
                raise TransitionCallbackError("Failed Admin Mode Login LED confirmation.")
        self.at.sequence(DUT.adminPIN)

    def enter_self_destruct_pin(self, event_data: EventData) -> None:
        self.logger.info("Entering Self Destruct PIN...")
        self.at.sequence(DUT.selfDestructPIN)
        
    def enter_last_try_pin(self, event_data: EventData) -> None:
        self.logger.info(f"Entering Last Try Login...")
        self.at.press(['key5', 'unlock'], duration_ms=6000)
        if not self.at.await_and_confirm_led_pattern(LEDs["RED_GREEN"], timeout=10):
            raise TransitionCallbackError("Failed 'LASTTRY' Login confirmation.")
        self.at.sequence(['key5', 'key2', 'key7', 'key8', 'key8', 'key7', 'key9', 'unlock'])

    def enter_invalid_pin(self, event_data: EventData) -> bool:
        """
        Atomically performs the action of entering a guaranteed-invalid PIN
        and verifies the device's REJECT response. This is a reusable helper
        method and not a direct transition callback.

        Returns:
            True if the REJECT pattern was successfully observed, False otherwise.
        """
        invalid_pin_sequence = ['key9', 'key9', 'key9', 'key9', 'key9', 'key9', 'key9', 'unlock']
        self.logger.info("Intentionally entering an invalid PIN...")
        self.at.sequence(invalid_pin_sequence)
        
        if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5):
            self.logger.error("Device did not show REJECT pattern after invalid PIN entry.")
            return False
            
        if DUT.bruteForceCurrent > 0:
            DUT.bruteForceCurrent -= 1
        
        self.logger.info("Device correctly showed REJECT pattern.")
        return True
        
