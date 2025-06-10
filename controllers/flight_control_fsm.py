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

    userForcedEnrollment = False
    userForcedEnrollmentUsed = False

    adminPIN = []
    oldAdminPIN = []

    recoveryPIN: Dict[int, Dict] = {1: {}, 2: {}, 3: {}, 4: {}}
    oldRecoveryPIN: Dict[int, Dict] = {1: {}, 2: {}, 3: {}, 4: {}}
    usedRecovery: Dict[int, bool] = {1: False, 2: False, 3: False, 4: False}
    
    selfDestructEnabled = False
    selfDestructPIN: Dict = {}
    oldSelfDestructPIN: Dict = {}
    selfDestructEnum = False
    selfDestructUsed = False

    userCount = DEVICE_PROPERTIES[device_name]['userCount']
    userPIN: Dict[int, Optional[List[str]]] = {1: None, 2: None, 3: None, 4: None}
    oldUserPIN: Dict[int, Optional[List[str]]] = {1: None, 2: None, 3: None, 4: None}
    enumUser: Dict[int, bool] = {1: False, 2: False, 3: False, 4: False}

DUT = DeviceUnderTest()

## --- FSM Class Definition ---
class SimplifiedDeviceFSM:

    STATES: List[str] = ['OFF', 'POWER_ON_SELF_TEST', 'POST_FAILED', 'BRUTE_FORCE', 'OOB_MODE', 'STANDBY_MODE', 'USER_FORCED_ENROLLMENT',
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
            auto_transitions=False, # MODIFICATION: Changed to True to let transitions find on_enter_STATE methods by convention.
            use_pygraphviz=False
        )

        # --- TRANSITIONS ---
        # power on/off and POST
        self.power_on: Callable
        self.post_fail: Callable
        self.power_off: Callable
        self.machine.add_transition(trigger='power_on', source='OFF', dest='POWER_ON_SELF_TEST', before='do_power_on_and_test')
        self.machine.add_transition(trigger='post_fail', source='POWER_ON_SELF_TEST', dest='POST_FAILED')
        self.machine.add_transition(trigger='power_off', source="*", dest='OFF')

        # Idle State that can be held indefinitely
        self.post_pass: Callable
        self.machine.add_transition(trigger='post_pass', source='POWER_ON_SELF_TEST', dest='OOB_MODE', conditions=[lambda _: not DUT.adminPIN])
        self.machine.add_transition(trigger='post_pass', source='POWER_ON_SELF_TEST', dest='STANDBY_MODE', conditions=[lambda _: bool(DUT.adminPIN)])
        self.machine.add_transition(trigger='post_pass', source='POWER_ON_SELF_TEST', dest='USER_FORCED_ENROLLMENT', conditions=[lambda _: bool(DUT.userForcedEnrollment)])
        self.machine.add_transition(trigger='post_pass', source='POWER_ON_SELF_TEST', dest='BRUTE_FORCE', conditions=[lambda _: DUT.bruteForceCounter == 0])

        self.enter_diagnostic_mode: Callable
        self.machine.add_transition(trigger='enter_diagnostic_mode', source=['OOB_MODE', 'STANDBY_MODE'], dest='DIAGNOSTIC_MODE')
        self.machine.add_transition(trigger='exit_diagnostic_mode', source='DIAGNOSTIC_MODE', dest='OOB_MODE', conditions=[lambda _: not DUT.adminPIN])
        self.machine.add_transition(trigger='exit_diagnostic_mode', source='DIAGNOSTIC_MODE', dest='STANDBY_MODE', conditions=[lambda _: bool(DUT.adminPIN)])
        

        # --- User Reset Transitions ---
        self.user_reset: Callable
        self.machine.add_transition(trigger='user_reset', source=['BRUTE_FORCE', 'OOB_MODE', 'STANDBY_MODE', 'USER_FORCED_ENROLLMENT'], dest='OOB_MODE', conditions=[lambda _: not DUT.provisionLock])
        self.machine.add_transition(trigger='user_reset', source='ADMIN_MODE', dest='OOB_MODE', before='do_user_reset')

        # --- Enrollment Transitions ---
        self.enroll_admin: Callable
        self.enroll_user: Callable
        self.machine.add_transition(trigger='enroll_admin', source=['ADMIN_MODE', 'OOB_MODE'], dest='ADMIN_MODE', before='admin_enrollment')
        self.machine.add_transition(trigger='enroll_user', source='ADMIN_MODE', dest='ADMIN_MODE')
        self.machine.add_transition(trigger='enroll_user', source='USER_FORCED_ENROLLMENT', dest='STANDBY_MODE')


        # self.machine.add_transition(trigger='set_brute_force_counter', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='change_admin_pin', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='enroll_self_destruct_pin', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='set_min_pin_length', source='ADMIN_MODE', dest='ADMIN_MODE')
        # self.machine.add_transition(trigger='enroll_recovery_pin', source='ADMIN_MODE', dest='ADMIN_MODE')

        # # --- Admin Mode Toggle Transitions ---
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

        # --- Admin Enum Transition ---
        self.unlock_admin: Callable
        self.lock_admin: Callable
        self.machine.add_transition(trigger='unlock_admin', source=['STANDBY_MODE', 'USER_FORCED_ENROLLMENT'], dest='UNLOCKED_ADMIN', before='enter_admin_pin')
        self.machine.add_transition(trigger='lock_admin', source='UNLOCKED_ADMIN', dest='STANDBY_MODE', before='press_lock_button')

        # --- User Enum Transition ---
        self.unlock_user: Callable
        self.lock_user: Callable
        self.machine.add_transition(trigger='unlock_user', source=['STANDBY_MODE'], dest='UNLOCKED_USER', before='enter_user_pin')
        self.machine.add_transition(trigger='lock_user', source='UNLOCKED_USER', dest='STANDBY_MODE', before='press_lock_button')


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
        Now this callback is very simple. Its only job is to trigger the next logical step.
        The FSM is now officially in this state.
        """
        self.logger.info("Entered POWER_ON_SELF_TEST state. Evaluating next transition...")
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
        if self.at.confirm_led_solid(LEDs['GREEN_BLUE_STATE'], minimum=3.0, timeout=5.0, replay_extra_context=context):
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


    ###########################################################################################################
    # Before/After Functions
    
    def do_power_on_and_test(self, event_data: EventData) -> bool:
        """
        This is a 'before' callback. It performs the power-on and POST.
        It must return True for the transition to proceed, or False to cancel it.
        """
        self.logger.info("Powering DUT on and performing self-test...")
        self.at.on("usb3")
        self.at.on("connect")
        time.sleep(0.5)

        dest_state = "UNKNOWN"
        if event_data and event_data.transition:
            dest_state = event_data.transition.dest
        context = {
            'fsm_current_state': self.state,
            'fsm_destination_state': dest_state
        }
        
        post_animation_observed_ok: bool = self.at.confirm_led_pattern(
            LEDs['STARTUP'], clear_buffer=True, replay_extra_context=context
        )

        if not post_animation_observed_ok:
            self.logger.error("Failed Startup Self-Test LED confirmation. Aborting transition.")
            self.post_fail(details="POST_ANIMATION_MISMATCH")
            return False # This stops the FSM from entering the POWER_ON_SELF_TEST state
        
        self.logger.info("Startup Self-Test successful. Proceeding to POWER_ON_SELF_TEST state.")
        return True # Allows the transition to complete

    def admin_enrollment(self, event_data: EventData) -> bool:
        """
        Performs the full admin enrollment procedure. This is a 'before'
        callback, which uses the 'new_pin' passed in the trigger call's kwargs.
        """
        new_pin = event_data.kwargs.get('new_pin')
        if not new_pin or not isinstance(new_pin, list):
            self.logger.error("Admin enrollment requires a 'new_pin' list passed as a keyword argument.")
            return False

        dest_state = "UNKNOWN"
        if event_data and event_data.transition:
            dest_state = event_data.transition.dest
        context = {
            'fsm_current_state': self.state,
            'fsm_destination_state': dest_state
        }
        
        self.logger.info(f"Entering Admin PIN Enrollment...")
        self.at.press(['unlock', 'key9'])
        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            self.logger.error("Did not observe GREEN_BLUE pattern. Enrollment aborted.")
            return False

        self.logger.info(f"Entering new Admin PIN (first time)...")
        self.at.sequence(new_pin)

        self.logger.info("Verifying PIN confirmation...")
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            self.logger.error("Did not observe ACCEPT_PATTERN pattern after first PIN entry.")
            return False

        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            self.logger.error("Did not observe GREEN_BLUE pattern after first PIN entry. Enrollment aborted.")
            return False

        self.logger.info("Re-entering Admin PIN for confirmation...")
        self.at.sequence(new_pin)
        
        self.logger.info("Awaiting 'ACCEPT_PATTERN' to confirm successful enrollment...")
        if not self.at.await_led_state(LEDs['ACCEPT_STATE'], timeout=5.0, replay_extra_context=context):
            self.logger.error("Did not observe ACCEPT_PATTERN after PIN confirmation. Enrollment likely failed.")
            return False
            
        self.logger.info("Admin enrollment sequence completed successfully. Updating DUT model.")
        DUT.adminPIN = new_pin
        self.logger.info("Updated DUT with new admin PIN. Allowing FSM transition to ADMIN_MODE.")
        
        return True

    def enter_admin_pin(self, event_data: EventData) -> bool:
        """
        Enters the stored Admin PIN to unlock the device. This is a 'before'
        callback for the 'unlock_admin' transition.

        It sends the PIN sequence stored in the DUT model and waits for the
        'ENUM' LED pattern to confirm a successful unlock.
        """
        self.logger.info("Unlocking DUT with Admin PIN...")
        self.at.sequence(DUT.adminPIN)

        dest_state = "UNKNOWN"
        if event_data and event_data.transition:
            dest_state = event_data.transition.dest
        context = {
            'fsm_current_state': self.state,
            'fsm_destination_state': dest_state
        }

        unlock_admin_ok: bool = self.at.await_and_confirm_led_pattern(LEDs['ENUM'], timeout=15, replay_extra_context=context)
        if not unlock_admin_ok:
            self.logger.error("Failed admin unlock LED pattern. Aborting transition.")
            self.post_fail(details="ADMIN_UNLOCK_PATTERN_MISMATCH")
            return False # Cancel the transition
        return True

    def user_enrollment(self, event_data: EventData) -> Optional[int]:
        """
        Performs the user enrollment procedure. This is a 'before' callback
        triggered from ADMIN_MODE. It finds the next available logical user
        slot based on the device's FIPS level, performs the physical
        enrollment sequence, and updates the DUT model.

        Args:
            event_data: The event data object, which contains the `new_pin`
                        in its kwargs.

        Returns:
            An integer representing the logical user ID (1-based) that was
            successfully enrolled, or None if enrollment failed.
        """
        new_pin = event_data.kwargs.get('new_pin')
        if not new_pin or not isinstance(new_pin, list):
            self.logger.error("User enrollment requires a 'new_pin' list passed as a keyword argument.")
            return None

        max_users = 1 if DUT.fips in [2, 3] else 4
        next_available_slot = None
        for i in range(1, max_users + 1):
            if DUT.userPIN.get(i) is None:
                next_available_slot = i
                break

        if next_available_slot is None:
            self.logger.error(f"Cannot enroll new user. All {max_users} user slots are full.")
            return None
        
        self.logger.info(f"Attempting to enroll new user into logical slot #{next_available_slot}...")
        
        context = {'fsm_current_state': self.state, 'fsm_destination_state': self.state}

        self.at.press(['unlock', 'key1'])
        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            self.logger.error("Did not observe GREEN_BLUE pattern for user enrollment. Aborted.")
            return None

        self.logger.info(f"Entering new User PIN (first time)...")
        self.at.sequence(new_pin)

        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            self.logger.error("Did not observe ACCEPT_PATTERN after first user PIN entry.")
            return None

        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            self.logger.error("Did not observe GREEN_BLUE pattern after first user PIN entry. Aborted.")
            return None

        self.logger.info("Re-entering User PIN for confirmation...")
        self.at.sequence(new_pin)

        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            self.logger.error("Did not observe final ACCEPT_PATTERN for user PIN confirmation. Enrollment failed.")
            return None
        
        DUT.userPIN[next_available_slot] = new_pin + ['unlock']
        self.logger.info(f"Successfully enrolled PIN for logical user {next_available_slot}.")
        return next_available_slot
    
    def enter_user_pin(self, event_data: EventData) -> bool:
        """
        Enters a specified user PIN to unlock the device. This is a 'before'
        callback for the 'unlock_user' transition. It uses a logical `user_id`
        provided by the caller to look up the correct PIN from the DUT model.

        Args:
            event_data: The event data object, containing the `user_id` in kwargs.

        Returns:
            True if the unlock pattern is confirmed, allowing the transition to
            UNLOCKED_USER. False otherwise, canceling the transition.
        """
        user_id = event_data.kwargs.get('user_id')
        if not user_id:
            self.logger.error("Unlock user requires a 'user_id' to be passed.")
            return False

        pin_to_enter = DUT.userPIN.get(user_id)
        if not pin_to_enter:
            self.logger.error(f"Unlock failed: No PIN is tracked for logical user {user_id}.")
            return False

        self.logger.info(f"Attempting to unlock device with PIN from logical user slot {user_id}...")
        self.at.sequence(pin_to_enter)

        dest_state = "UNKNOWN"
        if event_data and event_data.transition:
            dest_state = event_data.transition.dest
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        unlock_user_ok = self.at.await_and_confirm_led_pattern(LEDs['ENUM'], timeout=15, replay_extra_context=context)
        if not unlock_user_ok:
            self.logger.error("Failed user unlock LED pattern. Aborting transition.")
            self.post_fail(details="USER_UNLOCK_PATTERN_MISMATCH")
            return False
        
        return True

    def press_lock_button(self, event_data: EventData) -> None:
        self.logger.info(f"Locking DUT from Unlocked Admin...")
        self.at.press("lock")


    def do_user_reset(self, event_data: EventData) -> bool:
        """
        Performs the physical key sequence to trigger a user factory reset
        from ADMIN_MODE. This is a 'before' callback for the 'user_reset'
        transition.

        It sends the reset key combination, verifies the 'RED_BLUE'
        LED pattern, and clears the PINs from the DUT model to reflect
        the device's new state.

        Args:
            event_data: The event data from the FSM trigger.

        Returns:
            True if the reset confirmation pattern is observed, allowing the
            transition to OOB_MODE. False otherwise, canceling the transition.
        """

        dest_state = "UNKNOWN"
        if event_data and event_data.transition:
            dest_state = event_data.transition.dest
        context = {
            'fsm_current_state': self.state,
            'fsm_destination_state': dest_state
        }

        self.logger.info("Initiating User Reset...")

        self.at.sequence([["lock", "unlock", "key2"]])

        reset_pattern_ok = self.at.confirm_led_solid(
            LEDs["KEY_GENERATION"],
            minimum=12,
            timeout=15,
            replay_extra_context=context
        )

        if not reset_pattern_ok:
            self.logger.error("Failed to observe user reset confirmation (RED_BLUE) pattern. Aborting transition.")
            return False

        self.logger.info("User reset confirmation pattern observed. Resetting DUT model state...")
        # Reset the DUT model to its factory default state
        DUT.adminPIN = []
        DUT.userPIN = {1: None, 2: None, 3: None, 4: None}
        # To-do: Add any other DUT properties that should be reset to default here.

        self.logger.info("DUT model state has been reset. Allowing transition to OOB_MODE.")
        return True