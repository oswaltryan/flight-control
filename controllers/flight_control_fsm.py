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

# --- FSM Machine Type Selection ---
# This allows us to use a lightweight machine for runtime and tests,
# and a heavyweight machine for generating diagrams, without affecting the main code.
DIAGRAM_MODE = os.environ.get('FSM_DIAGRAM_MODE', 'false').lower() == 'true'

if DIAGRAM_MODE:
    from transitions.extensions import GraphMachine as Machine
    # This print statement is a helpful confirmation when generating diagrams
    print("FSM running in DIAGRAM_MODE with GraphMachine.")
else:
    from transitions import Machine
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
    battery_vbus = False
    vbus = True
    bridge_fw = DEVICE_PROPERTIES[device_name]['bridgeFW']
    mcu_fw = []
    mcu_fw_human_readable = ""
    fips = DEVICE_PROPERTIES[device_name]['fips']
    secure_key = DEVICE_PROPERTIES[device_name]['secureKey']
    usb3 = False
    disk_path = ""
    mounted = False
    serial_number = ""
    dev_keypad_serial_number = ""

    CMFR = False
    model_id_1 = DEVICE_PROPERTIES[device_name]['model_id_digit_1']
    model_id_2 = DEVICE_PROPERTIES[device_name]['model_id_digit_2']
    hardware_id_1 = DEVICE_PROPERTIES[device_name]['hardware_major']
    hardware_id_2 = DEVICE_PROPERTIES[device_name]['hardware_minor']
    scb_part_number = DEVICE_PROPERTIES[device_name]['singleCodeBasePartNumber']
    single_code_base = DEVICE_PROPERTIES[device_name]['singleCodeBase']
    
    basic_disk = True
    removable_media = False
    
    brute_force_counter = 20
    brute_force_counter_current = 20
    
    led_flicker = False
    lock_override = False

    manufacturer_reset_enum = False

    maximum_pin_counter = 16
    minimum_pin_counter = int(DEVICE_PROPERTIES[device_name]['minpin'])
    default_minimum_pin_counter = int(DEVICE_PROPERTIES[device_name]['minpin'])

    provision_lock = False
    provision_lock_bricked = False
    provision_lock_recovery_counter = 5

    read_only_enabled = False

    unattended_auto_lock_counter = 0

    user_forced_enrollment = False
    user_forced_enrollment_used = False

    admin_pin = []
    old_admin_pin = []

    recovery_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, 5)}
    old_recovery_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, 5)}
    recovery_pin_used: Dict[int, bool] = {i: False for i in range(1, 5)}
    
    self_destruct_enabled = False
    self_destruct_pin = []
    old_self_destruct_pin = []
    self_destruct_enum = False
    self_destruct_used = False

    user_count = DEVICE_PROPERTIES[device_name]['userCount']
    _max_users = 1 if fips in [2, 3] else 4
    user_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, _max_users + 1)}
    old_user_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, _max_users + 1)}
    user_pin_enum: Dict[int, bool] = {i: False for i in range(1, _max_users + 1)}

DUT = DeviceUnderTest()

class CallableCondition:
    """
    A wrapper that makes a callable condition have a readable __name__
    for diagram generation, allowing inline lambda definitions to be labeled.
    """
    def __init__(self, func: Callable[..., bool], name: str):
        self.func = func
        self.__name__ = name  # <-- THE CRITICAL CHANGE

    def __call__(self, *args, **kwargs) -> bool:
        # This makes the object behave like a function for the FSM
        return self.func(*args, **kwargs)

    def __repr__(self) -> str:
        # A helpful representation for debugging
        return f"<CallableCondition: {self.__name__}>"

## --- FSM Class Definition ---
class ApricornDeviceFSM:

    STATES: List[str] = ['OFF', 'POWER_ON_SELF_TEST', 'ERROR_MODE', 'BRUTE_FORCE', 'BRICKED', 'OOB_MODE', 'STANDBY_MODE', 'USER_FORCED_ENROLLMENT',
                         'UNLOCKED_ADMIN', 'UNLOCKED_USER',
                         'ADMIN_MODE', 'PIN_ENROLLMENT', 'COUNTER_ENROLLMENT',
                         'DIAGNOSTIC_MODE'
    ]

    logger: logging.Logger
    at: 'UnifiedController'
    machine: Machine
    state: str
    source_state: str = 'OFF'

    def __init__(self, at_controller: 'UnifiedController'):
        self.logger = logging.getLogger("DeviceFSM.Simplified")
        self.at = at_controller

        # Define all transitions in a single list of dictionaries, including lambdas.
        transitions = [
            # --- Power On/Off Transitions ---
            {'trigger': 'power_on', 'source': 'OFF', 'dest': 'POWER_ON_SELF_TEST', 'before': '_power_toggle'},
            {'trigger': 'post_fail', 'source': 'POWER_ON_SELF_TEST', 'dest': 'ERROR_MODE'},
            {'trigger': 'power_off', 'source': '*', 'dest': 'OFF', 'before': '_power_toggle'},

            # --- 'Idle' Mode Transitions (from POST) ---
            {'trigger': 'post_pass', 'source': 'POWER_ON_SELF_TEST', 'dest': 'OOB_MODE', 'conditions': [CallableCondition(lambda _: not DUT.admin_pin, "DUT.admiPIN not enrolled")]},
            {'trigger': 'post_pass', 'source': 'POWER_ON_SELF_TEST', 'dest': 'USER_FORCED_ENROLLMENT', 'conditions': [CallableCondition(lambda _: bool(DUT.user_forced_enrollment), "DUT.user_forced_enrollment == True")]},
            {'trigger': 'post_pass', 'source': 'POWER_ON_SELF_TEST', 'dest': 'BRUTE_FORCE', 'conditions': [CallableCondition(lambda _: DUT.brute_force_counter == 0, "DUT.brute_force_counter == 0")]},
            {'trigger': 'post_pass', 'source': 'POWER_ON_SELF_TEST', 'dest': 'STANDBY_MODE', 'conditions': [CallableCondition(lambda _: bool(DUT.admin_pin), "DUT.admin_pin enrolled")]},

            # --- OOB Mode Transitions ---
            {'trigger': 'enter_diagnostic_mode', 'source': 'OOB_MODE', 'dest': 'DIAGNOSTIC_MODE'},
            {'trigger': 'exit_diagnostic_mode', 'source': 'DIAGNOSTIC_MODE', 'dest': 'OOB_MODE', 'conditions': [CallableCondition(lambda _: not DUT.admin_pin, "DUT.admin_pin not enrolled")]},
            {'trigger': 'enroll_admin', 'source': 'OOB_MODE', 'dest': 'ADMIN_MODE', 'before': '_admin_enrollment'},
            {'trigger': 'user_reset', 'source': 'OOB_MODE', 'dest': 'OOB_MODE', 'conditions': [CallableCondition(lambda _: not DUT.provision_lock, "DUT.provision_lock == False")]},

            # --- Standby Mode Transitions ---
            {'trigger': 'admin_mode_login', 'source': 'STANDBY_MODE', 'dest': 'ADMIN_MODE', 'before': '_enter_admin_mode_login'},
            {'trigger': 'lock_admin', 'source': 'ADMIN_MODE', 'dest': 'STANDBY_MODE', 'before': '_press_lock_button'},
            {'trigger': 'unlock_admin', 'source': 'STANDBY_MODE', 'dest': 'UNLOCKED_ADMIN', 'before': '_enter_admin_pin'},
            {'trigger': 'lock_admin', 'source': 'UNLOCKED_ADMIN', 'dest': 'STANDBY_MODE', 'before': '_press_lock_button'},
            {'trigger': 'enter_diagnostic_mode', 'source': 'STANDBY_MODE', 'dest': 'DIAGNOSTIC_MODE'},
            {'trigger': 'self_destruct', 'source': 'STANDBY_MODE', 'dest': 'UNLOCKED_ADMIN', 'before': '_enter_self_destruct_pin'},
            {'trigger': 'exit_diagnostic_mode', 'source': 'DIAGNOSTIC_MODE', 'dest': 'STANDBY_MODE', 'conditions': [CallableCondition(lambda _: bool(DUT.admin_pin), "DUT.admin_pin enrolled")]},
            {'trigger': 'user_reset', 'source': 'STANDBY_MODE', 'dest': 'OOB_MODE', 'conditions': [CallableCondition(lambda _: not DUT.provision_lock, "DUT.provision_lock == False")]},
            {'trigger': 'unlock_user', 'source': 'STANDBY_MODE', 'dest': 'UNLOCKED_USER', 'before': '_enter_user_pin'},
            {'trigger': 'lock_user', 'source': 'UNLOCKED_USER', 'dest': 'STANDBY_MODE', 'before': '_press_lock_button'},
            {'trigger': 'fail_unlock', 'source': 'STANDBY_MODE', 'dest': 'STANDBY_MODE', 'before': '_enter_invalid_pin', 'conditions': [CallableCondition(lambda _: DUT.brute_force_counter_current > 1 and not (DUT.brute_force_counter_current == (DUT.brute_force_counter/2)+1), "Brute Force not triggered")]},
            {'trigger': 'fail_unlock', 'source': 'STANDBY_MODE', 'dest': 'BRUTE_FORCE', 'before': '_enter_invalid_pin', 'conditions': [CallableCondition(lambda _: (DUT.brute_force_counter_current == (DUT.brute_force_counter/2)+1) or DUT.brute_force_counter_current == 1, "Brute Force triggered")]},

            # --- User-Forced Enrollment Mode Transitions ---
            {'trigger': 'admin_mode_login', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'ADMIN_MODE', 'before': '_enter_admin_mode_login'},
            {'trigger': 'lock_admin', 'source': 'ADMIN_MODE', 'dest': 'USER_FORCED_ENROLLMENT', 'before': '_press_lock_button'},
            {'trigger': 'unlock_admin', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'UNLOCKED_ADMIN', 'before': '_enter_admin_pin'},
            {'trigger': 'lock_admin', 'source': 'UNLOCKED_ADMIN', 'dest': 'USER_FORCED_ENROLLMENT', 'before': '_press_lock_button'},
            {'trigger': 'enroll_user', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'STANDBY_MODE', 'before': '_user_enrollment'},
            {'trigger': 'enter_diagnostic_mode', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'DIAGNOSTIC_MODE'},
            {'trigger': 'exit_diagnostic_mode', 'source': 'DIAGNOSTIC_MODE', 'dest': 'USER_FORCED_ENROLLMENT', 'conditions': [CallableCondition(lambda _: bool(DUT.user_forced_enrollment), "DUT.user_forced_enrollment == True")]},
            {'trigger': 'self_destruct', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'UNLOCKED_ADMIN', 'before': '_enter_self_destruct_pin'},
            {'trigger': 'user_reset', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'OOB_MODE', 'conditions': [CallableCondition(lambda _: not DUT.provision_lock, "DUT.provision_lock == False")]},
            {'trigger': 'unlock_user', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'UNLOCKED_USER', 'before': '_enter_user_pin', 'conditions': [CallableCondition(lambda _: any(pin is not None for pin in DUT.user_pin.values()), "DUT.user_pin(s) enrolled")]},
            {'trigger': 'lock_user', 'source': 'UNLOCKED_USER', 'dest': 'USER_FORCED_ENROLLMENT', 'before': '_press_lock_button'},
            {'trigger': 'fail_unlock', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'STANDBY_MODE', 'before': '_enter_invalid_pin', 'conditions': [CallableCondition(lambda _: DUT.brute_force_counter_current > 1 and not (DUT.brute_force_counter_current == (DUT.brute_force_counter/2)+1), "Brute Force not triggered")]},
            {'trigger': 'fail_unlock', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'BRUTE_FORCE', 'before': '_enter_invalid_pin', 'conditions': [CallableCondition(lambda _: DUT.brute_force_counter_current == DUT.brute_force_counter/2 or DUT.brute_force_counter_current == 1, "Brute Force triggered")]},

            # --- Brute Force Mode Transitions ---
            {'trigger': 'last_try_login', 'source': 'BRUTE_FORCE', 'dest': 'STANDBY_MODE', 'before': '_enter_last_try_pin', 'conditions': [CallableCondition(lambda _: DUT.brute_force_counter_current == DUT.brute_force_counter/2, "Brute Force halfway point")]},
            {'trigger': 'user_reset', 'source': 'BRUTE_FORCE', 'dest': 'OOB_MODE', 'conditions': [CallableCondition(lambda _: not DUT.provision_lock, "DUT.provision_lock == False")]},
            {'trigger': 'admin_recovery_failed', 'source': 'BRUTE_FORCE', 'dest': 'BRICKED'},

            # --- Admin Mode Enrollment Transitions ---
            {'trigger': 'user_reset', 'source': 'ADMIN_MODE', 'dest': 'OOB_MODE', 'before': '_do_user_reset'},
            # Counter Enrollments
            {'trigger': 'enroll_brute_force_counter', 'source': 'ADMIN_MODE', 'dest': 'COUNTER_ENROLLMENT', 'before': '_brute_force_counter_enrollment'},
            {'trigger': 'enroll_unattended_auto_lock_counter', 'source': 'ADMIN_MODE', 'dest': 'COUNTER_ENROLLMENT', 'before': '_unattended_auto_lock_enrollment'},
            {'trigger': 'enroll_min_pin_counter', 'source': 'ADMIN_MODE', 'dest': 'COUNTER_ENROLLMENT', 'before': '_min_pin_enrollment'},
            {'trigger': 'enroll_counter', 'source': 'COUNTER_ENROLLMENT', 'dest': 'ADMIN_MODE', 'before': '_counter_enrollment'},
            {'trigger': 'timeout_enroll_counter', 'source': 'COUNTER_ENROLLMENT', 'dest': 'ADMIN_MODE', 'before': '_timeout_counter_enrollment'},
            {'trigger': 'exit_enroll_counter', 'source': 'COUNTER_ENROLLMENT', 'dest': 'ADMIN_MODE', 'before': '_press_lock_button'},
            # PIN Enrollments
            {'trigger': 'enroll_admin', 'source': 'ADMIN_MODE', 'dest': 'PIN_ENROLLMENT', 'before': '_admin_enrollment'},
            {'trigger': 'enroll_user', 'source': 'ADMIN_MODE', 'dest': 'PIN_ENROLLMENT', 'before': '_user_enrollment', 'conditions': [CallableCondition(lambda _: any(pin_value is None for pin_value in DUT.user_pin.values()), "Empty user slot available")]},
            {'trigger': 'enroll_recovery', 'source': 'ADMIN_MODE', 'dest': 'PIN_ENROLLMENT', 'before': '_recovery_pin_enrollment'},
            {'trigger': 'enroll_self_destruct', 'source': 'ADMIN_MODE', 'dest': 'PIN_ENROLLMENT', 'before': '_self_destruct_pin_enrollment'},
            {'trigger': 'enroll_pin', 'source': 'PIN_ENROLLMENT', 'dest': 'ADMIN_MODE', 'before': '_pin_enrollment'},
            {'trigger': 'timeout_enroll_pin', 'source': 'PIN_ENROLLMENT', 'dest': 'ADMIN_MODE', 'before': '_timeout_pin_enrollment'},
            {'trigger': 'exit_enroll_pin', 'source': 'PIN_ENROLLMENT', 'dest': 'ADMIN_MODE', 'before': '_press_lock_button'},

            # --- Admin Mode Toggle Transitions (Self-Loops) ---
            {'trigger': 'toggle_basic_disk', 'source': 'ADMIN_MODE', 'dest': 'ADMIN_MODE', 'before': '_basic_disk_toggle'},
            {'trigger': 'toggle_removable_media', 'source': 'ADMIN_MODE', 'dest': 'ADMIN_MODE', 'before': '_removable_media_toggle'},
            {'trigger': 'enable_led_Flicker', 'source': 'ADMIN_MODE', 'dest': 'ADMIN_MODE', 'before': '_led_flicker_enable'},
            {'trigger': 'disable_led_Flicker', 'source': 'ADMIN_MODE', 'dest': 'ADMIN_MODE', 'before': '_led_flicker_disable'},
            {'trigger': 'delete_pins', 'source': 'ADMIN_MODE', 'dest': 'ADMIN_MODE', 'before': '_delete_pins_toggle'},
            {'trigger': 'toggle_lock_override', 'source': 'ADMIN_MODE', 'dest': 'ADMIN_MODE', 'before': '_lock_override_toggle'},
            {'trigger': 'enable_provision_lock', 'source': 'ADMIN_MODE', 'dest': 'ADMIN_MODE', 'before': '_provision_lock_toggle'},
            {'trigger': 'toggle_read_only', 'source': 'ADMIN_MODE', 'dest': 'ADMIN_MODE', 'before': '_read_only_toggle'},
            {'trigger': 'toggle_read_write', 'source': 'ADMIN_MODE', 'dest': 'ADMIN_MODE', 'before': '_read_write_toggle'},
            {'trigger': 'enable_self_destruct', 'source': 'ADMIN_MODE', 'dest': 'ADMIN_MODE', 'before': '_self_destruct_toggle'},
            {'trigger': 'toggle_user_forced_enrollment', 'source': 'ADMIN_MODE', 'dest': 'ADMIN_MODE', 'before': '_user_forced_enrollment_toggle'},
        ]

        machine_kwargs = {
            'model': self,
            'states': ApricornDeviceFSM.STATES,
            'transitions': transitions,
            'initial': 'OFF',
            'send_event': True,
            'after_state_change': '_log_state_change_details',
            'auto_transitions': True,
        }

        # Conditionally add the diagramming engine parameter
        if DIAGRAM_MODE:
            machine_kwargs['graph_engine'] = 'pygraphviz'

        # Initialize the machine by unpacking the keyword arguments dictionary
        self.machine = Machine(**machine_kwargs)
        self.transition_config = transitions

        # --- TRANSITIONS (Type Hinting for autocomplete and static analysis) ---
        self.admin_mode_login: Callable
        self.admin_recovery_failed: Callable
        self.delete_pins: Callable
        self.disable_led_Flicker: Callable
        self.enable_led_Flicker: Callable
        self.enable_provision_lock: Callable
        self.enable_self_destruct: Callable
        self.enroll_admin: Callable
        self.enroll_brute_force_counter: Callable
        self.enroll_counter: Callable
        self.enroll_min_pin_counter: Callable
        self.enroll_pin: Callable
        self.enroll_recovery: Callable
        self.enroll_self_destruct: Callable
        self.enroll_unattended_auto_lock_counter: Callable
        self.enroll_user: Callable
        self.enter_diagnostic_mode: Callable
        self.exit_diagnostic_mode: Callable
        self.exit_enroll_counter: Callable
        self.exit_enroll_pin: Callable
        self.fail_unlock: Callable
        self.last_try_login: Callable
        self.lock_admin: Callable
        self.lock_user: Callable
        self.post_fail: Callable
        self.post_pass: Callable
        self.power_off: Callable
        self.power_on: Callable
        self.self_destruct: Callable
        self.timeout_enroll_counter: Callable
        self.timeout_enroll_pin: Callable
        self.toggle_basic_disk: Callable
        self.toggle_lock_override: Callable
        self.toggle_read_only: Callable
        self.toggle_read_write: Callable
        self.toggle_removable_media: Callable
        self.toggle_user_forced_enrollment: Callable
        self.unlock_admin: Callable
        self.unlock_user: Callable
        self.user_reset: Callable

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
        else:
            self.logger.info("Device is in BRUTE_FORCE Mode...")

    def on_enter_COUNTER_ENROLLMENT(self, event_data: EventData) -> None:
        """
        Called upon entering COUNTER_ENROLLMENT. It logs which specific
        counter enrollment process was triggered.
        """
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        
        if not self.at.confirm_led_pattern(LEDs['RED_COUNTER'], replay_extra_context=context):
            self.logger.error("Failed to confirm RED_COUNTER LED pattern.")
        else:
            self.logger.info("Awaiting counter enrollment...")

    def on_enter_PIN_ENROLLMENT(self, event_data: EventData) -> None:
        """
        Called upon entering PIN_ENROLLMENT. It logs which specific
        PIN enrollment process was triggered.
        """
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        trigger_name = event_data.event.name
        self.logger.info(f"Entered PIN_ENROLLMENT state via '{trigger_name}' trigger.")
        # Example of trigger-specific logic:
        if trigger_name == 'enroll_self_destruct':
            if not self.at.await_and_confirm_led_pattern(LEDs['RED_BLUE'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe RED_BLUE pattern.")
            else:
                self.logger.info("Awaiting PIN enrollment...")
        else:
            if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe GREEN_BLUE pattern for recovery enrollment.")
            else:
                self.logger.info("Awaiting PIN enrollment...")

###########################################################################################################
# Before/After Functions

##########
## Power

    def _power_toggle(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        trigger_name = event_data.event.name

        if trigger_name == 'power_on':
            self.logger.info("Powering DUT on and performing self-test...")
            self.at.on("usb3")
            self.at.on("connect")
            time.sleep(0.5)
            if DUT.vbus:
                if not self.at.confirm_led_pattern(LEDs['STARTUP'], clear_buffer=True, replay_extra_context=context):
                    raise TransitionCallbackError("Failed Startup Self-Test LED confirmation.")
                self.logger.info("Startup Self-Test successful. Proceeding to POWER_ON_SELF_TEST state.")
        elif trigger_name == 'power_off':
            self.logger.info("Powering off DUT...")
            self.at.off("usb3")
            self.at.off("connect")

##########
## Unlocks

    def _enter_admin_pin(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        self.logger.info("Unlocking DUT with Admin PIN...")
        self.at.sequence(DUT.admin_pin)
        if DUT.read_only_enabled and DUT.lock_override:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM_LOCK_OVERRIDE_READ_ONLY'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError("Failed Admin unlock LED pattern.")
        elif DUT.read_only_enabled:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM_READ_ONLY'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError("Failed Admin unlock LED pattern.")
        elif DUT.lock_override:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM_LOCK_OVERRIDE'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError("Failed Admin unlock LED pattern.")
        else:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError("Failed Admin unlock LED pattern.")
        
    def _enter_self_destruct_pin(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        self.logger.info("Unlocking DUT with Self-Destruct PIN...")
        self.at.sequence(DUT.admin_pin)
        if DUT.read_only_enabled and DUT.lock_override:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM_LOCK_OVERRIDE_READ_ONLY'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError("Failed Self-Destruct unlock LED pattern.")
        elif DUT.read_only_enabled:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM_READ_ONLY'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError("Failed Self-Destruct unlock LED pattern.")
        elif DUT.lock_override:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM_LOCK_OVERRIDE'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError("Failed Self-Destruct unlock LED pattern.")
        else:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError("Failed Self-Destruct unlock LED pattern.")
        
    def _enter_user_pin(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        user_id = event_data.kwargs.get('user_id')
        if not user_id:
            raise TransitionCallbackError("Unlock user requires a 'user_id' to be passed.")
        if user_id not in DUT.user_pin:
            raise TransitionCallbackError(f"Unlock failed: User ID {user_id} is not a valid slot for this device. Available slots: {list(DUT.user_pin.keys())}")
        
        pin_to_enter = DUT.user_pin.get(user_id)
        if not pin_to_enter:
            raise TransitionCallbackError(f"Unlock failed: No PIN is tracked for logical user {user_id}.")

        self.logger.info(f"Attempting to unlock device with PIN from logical user slot {user_id}...")
        self.at.sequence(pin_to_enter)
        if DUT.read_only_enabled and DUT.lock_override:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM_LOCK_OVERRIDE_READ_ONLY'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError(f"Failed User {user_id} unlock LED pattern.")
        elif DUT.read_only_enabled:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM_READ_ONLY'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError(f"Failed User {user_id} unlock LED pattern.")
        elif DUT.lock_override:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM_LOCK_OVERRIDE'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError(f"Failed User {user_id} unlock LED pattern.")
        else:
            if not self.at.await_and_confirm_led_pattern(LEDs['ENUM'], timeout=15, replay_extra_context=context):
                raise TransitionCallbackError(f"Failed User {user_id} unlock LED pattern.")
    
##########
## Logins

    def _enter_admin_mode_login(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        self.at.press(['key0', 'unlock'], duration_ms=6000)
        if not self.at.confirm_led_pattern(LEDs['RED_LOGIN'], clear_buffer=True, replay_extra_context=context):
                raise TransitionCallbackError("Failed Admin Mode Login LED confirmation.")
        self.at.sequence(DUT.admin_pin)

    def _enter_last_try_pin(self, event_data: EventData) -> None:
        self.logger.info(f"Entering Last Try Login...")
        self.at.press(['key5', 'unlock'], duration_ms=6000)
        if not self.at.await_and_confirm_led_pattern(LEDs["RED_GREEN"], timeout=10):
            raise TransitionCallbackError("Failed 'LASTTRY' Login confirmation.")
        self.at.sequence(['key5', 'key2', 'key7', 'key8', 'key8', 'key7', 'key9', 'unlock']) 

##########
## Resets

    def _do_user_reset(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        self.logger.info("Initiating User Reset...")
        if self.state == "ADMIN_MODE":
            self.at.sequence([["lock", "unlock", "key2"]])
        reset_pattern_ok = self.at.confirm_led_solid(LEDs["KEY_GENERATION"], minimum=12, timeout=15, replay_extra_context=context)
        if not reset_pattern_ok:
            raise TransitionCallbackError("Failed to observe user reset confirmation pattern.")
        
        self.logger.info("User reset confirmation pattern observed. Resetting DUT model state...")
        DUT.admin_pin = []
        DUT.user_pin = {1: None, 2: None, 3: None, 4: None}
        self.logger.info("DUT model state has been reset.")
    
##########
## Miscellaneous
        
    def _press_lock_button(self, event_data: EventData) -> None:
        self.logger.info(f"Locking DUT from Unlocked Admin...")
        self.at.press("lock")

    def _enter_invalid_pin(self, event_data: EventData) -> bool:
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
            
        if DUT.brute_force_counter_current > 0:
            DUT.brute_force_counter_current -= 1
        
        self.logger.info("Device correctly showed REJECT pattern.")
        return True
    
##########
## Admin mode Counter Enrollments

    def _brute_force_counter_enrollment(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Entering Brute Force Counter Enrollment...")
        self.at.press(['unlock', 'key5'], duration_ms=6000)

    def _min_pin_enrollment(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        self.logger.info(f"Entering Minimum PIN Length Counter Enrollment...")
        self.at.press(['unlock', 'key4'], duration_ms=6000)

    def _unattended_auto_lock_enrollment(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Entering Unattended Auto-Lock Enrollment...")
        self.at.press(['unlock', 'key6'], duration_ms=6000)

    def _counter_enrollment(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        trigger_name = event_data.event.name
        new_counter = event_data.kwargs.get('new_counter')

        if trigger_name == 'enroll_brute_force_counter':
            if not new_counter or not isinstance(new_counter, str):
                raise TransitionCallbackError("Brute Force Counter Enrollment requires a 'new_counter' str.")
            if len(new_counter) != 2:
                raise TransitionCallbackError("Brute Force Counter Enrollment requires two-digits")
            
            BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACK = []
            for iteration in range(int(new_counter)):
                BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACK.append({'red':0, 'green':0, 'blue':0, 'duration': (0.00,  3.0)})
                BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACK.append({'red':0, 'green':1, 'blue':0, 'duration': (0.01,  1.0)})

            self.at.press(new_counter[0])
            self.at.press(new_counter[1])
            if int(new_counter) < 2 or int(new_counter) > 10:
                if not self.at.await_and_confirm_led_pattern(LEDs['REJECT_PATTERN'], timeout=5.0, replay_extra_context=context):
                    raise TransitionCallbackError("Did not observe REJECT_PATTERN for invalid Brute Force Counter Enrollment value.")
            else:
                if not self.at.await_and_confirm_led_pattern(BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACK, timeout=5.0, replay_extra_context=context):
                    raise TransitionCallbackError("Did not observe BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACKt pattern.")
                
        elif trigger_name == 'enroll_min_pin_counter':
            if not new_counter or not isinstance(new_counter, str):
                raise TransitionCallbackError("Minimum PIN Length Enrollment requires a 'new_counter' str.")
            if len(new_counter) != 2:
                raise TransitionCallbackError("Minimum PIN Length Enrollment requires two-digits")
            
            self.at.press(new_counter[0])
            self.at.press(new_counter[1])

            if int(new_counter) < DUT.default_minimum_pin_counter or int(new_counter) > DUT.maximum_pin_counter:
                if not self.at.await_and_confirm_led_pattern(LEDs['REJECT_PATTERN'], timeout=5.0, replay_extra_context=context):
                    raise TransitionCallbackError("Did not observe REJECT_PATTERN for invalid Brute Force Counter Enrollment value.")
            else:
                if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                    raise TransitionCallbackError("Did not observe ACCEPT_PATTERN after Minimum PIN Length Counter Enrollment.")
                
        elif trigger_name == 'enroll_unattended_auto_lock_counter':
            new_counter = event_data.kwargs.get('new_counter')
            if not new_counter or not isinstance(new_counter, int):
                raise TransitionCallbackError("Unattended Auto-Lock Enrollment requires a 'new_counter' integer.")            
            if len(str(new_counter)) != 1:
                raise TransitionCallbackError("Unattended Auto-Lock Enrollment requires a single digit (0-3).")
            
            self.at.press(f"key{new_counter}")

            # Validate the input range. The condition is the inverse of the valid range (-1 < new_counter < 4).
            if new_counter < 0 or new_counter > 3:
                if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                    raise TransitionCallbackError("Did not observe REJECT_PATTERN for invalid Unattended Auto-Lock value.")
            else:
                if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                    raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for setting Auto-Lock to 0.")
                else:
                    DUT.unattended_auto_lock_counter = new_counter
                    self.logger.info(f"Unattended Auto-Lock new_counter set to: {new_counter}")

    def _timeout_counter_enrollment(self, event_data: EventData) -> None:
        pin_entered = event_data.kwargs.get('pin_entered')
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        if not pin_entered:
            time.sleep(30)
        else:
            time.sleep(30)
            if not self.at.await_and_confirm_led_pattern(LEDs['REJECT_PATTERN'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe REJECT_PATTERN for counter enrollment timeout...")

#################
## Admin mode PIN Enrollments

    def _admin_enrollment(self, event_data: EventData) -> None:       
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Entering Admin PIN Enrollment...")
        self.at.press(['unlock', 'key9'])

    def _recovery_pin_enrollment(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.at.press(['unlock', 'key7'])
        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe GREEN_BLUE pattern for recovery enrollment.")

    def _user_enrollment(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        self.at.press(['unlock', 'key1'])
        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe GREEN_BLUE pattern for user enrollment.")

    def _self_destruct_pin_enrollment(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        if not DUT.self_destruct_enabled:
            self.logger.info(f"Attempting Self-Destruct PIN Enrollment without Self-Destruct enabled...")
            self.at.press(['key4', 'key7'])
            if not self.at.await_and_confirm_led_pattern(LEDs['REJECT_PATTERN'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe REJECT_PATTERN for Self-Destruct toggle with Provision Lock enabled.")
        else:
            self.logger.info(f"Entering Self-Destruct PIN Enrollment...")
            self.at.press(['key3', 'unlock'])

    def _pin_enrollment(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        trigger_name = event_data.event.name
        new_pin = event_data.kwargs.get('new_pin')
        if not new_pin or not isinstance(new_pin, list):
            raise TransitionCallbackError("PIN enrollment requires a 'new_pin' list.")
        
        if trigger_name == 'enroll_admin':
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
            else:
                DUT.admin_pin = new_pin
                self.logger.info("Admin enrollment sequence completed successfully. Updated DUT model.")

        elif trigger_name == 'enroll_recovery':
            next_available_slot = next((i for i in DUT.recovery_pin.keys() if DUT.recovery_pin.get(i) is None), None)
            if next_available_slot is None:
                self.logger.warning(f"No available recovery slots. This path assumes a REJECT pattern will be shown by the device.")
                if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                    raise TransitionCallbackError("Did not observe REJECT_PATTERN on Recovery PIN Enrollment attempt when slots are full.")
                raise TransitionCallbackError(f"Enrollment failed as expected: All {len(DUT.recovery_pin)} recovery slots are full.")

            # If the code reaches here, a slot is available.
            self.logger.info(f"Attempting to enroll new recovery PIN into logical slot #{next_available_slot}...")
            self.logger.info(f"Entering new Recovery PIN (first time)...")
            self.at.sequence(new_pin)
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe ACCEPT_PATTERN after first recovery PIN entry.")
            if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe GREEN_BLUE pattern after first recovery PIN entry.")

            self.logger.info("Re-entering Recovery PIN for confirmation...")
            self.at.sequence(new_pin)
            if not self.at.confirm_led_solid(LEDs["ACCEPT_STATE"], minimum=1, timeout=3, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe final ACCEPT_PATTERN for recovery PIN confirmation.")

            DUT.recovery_pin[next_available_slot] = new_pin
            self.logger.info(f"Successfully enrolled recovery PIN for logical slot {next_available_slot}.")

        elif trigger_name == 'enroll_user':
            next_available_slot = next((i for i in DUT.user_pin.keys() if DUT.user_pin.get(i) is None), None)
            self.logger.info(f"Attempting to enroll new user into logical slot #{next_available_slot}...")
            if next_available_slot is None:
                if not self.at.await_and_confirm_led_pattern(LEDs['REJECT_PATTERN'], timeout=5.0, replay_extra_context=context):
                    raise TransitionCallbackError("Did not observe REJECT_PATTERN on User PIN Enrollment entry.")
                raise TransitionCallbackError(f"Enrollment failed as expected: All {len(DUT.user_pin)} user slots are full.")
            
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
            
            DUT.user_pin[next_available_slot] = new_pin
            self.logger.info(f"Successfully enrolled PIN for logical user {next_available_slot}.")

        elif trigger_name == 'enroll_self_destruct':
            self.logger.info(f"Entering new Self-Destruct PIN (first time)...")
            self.at.sequence(new_pin)
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe ACCEPT_PATTERN after first PIN entry.")
            if not self.at.await_and_confirm_led_pattern(LEDs['RED_BLUE'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe RED_BLUE pattern after first PIN entry.")

            self.logger.info("Re-entering Self-Destruct PIN for confirmation...")
            self.at.sequence(new_pin)
            if not self.at.await_led_state(LEDs['ACCEPT_STATE'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe ACCEPT_PATTERN after PIN confirmation.")
                
            DUT.self_destruct_pin = new_pin
            self.logger.info("Self-Destruct enrollment sequence completed successfully. Updated DUT model.")

##################
## Admin mode Toggles

    def _basic_disk_toggle(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Toggling Basic Disk mode...")
        self.at.press(['key2', 'key3'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for Basic Disk toggle.")
        else:
            DUT.basic_disk = True
            self.logger.info(f"Basic Disk mode: {DUT.basic_disk}")

    def _removable_media_toggle(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Toggling Removable Media mode...")
        self.at.press(['key3', 'key7'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for Removable Media toggle.")
        else:
            DUT.basic_disk = True
            self.logger.info(f"Removable Media mode: {DUT.removable_media}")

    def _led_flicker_enable(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Enabling LED Flicker mode...")
        self.at.press(['key0', 'key3'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for LED Flicker toggle.")
        else:
            DUT.led_flicker = True
            self.logger.info(f"LED Flicker mode: {DUT.led_flicker}")

    def _led_flicker_disable(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Disabling LED Flicker Mode...")
        self.at.press(['key0', 'key3'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for LED Flicker toggle.")
        else:
            DUT.led_flicker = False
            self.logger.info(f"LED Flicker mode: {DUT.led_flicker}")

    def _lock_override_toggle(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Toggling Lock Override mode...")
        self.at.press(['key0', 'key3'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for Lock Override toggle.")
        else:
            DUT.led_flicker = False
            self.logger.info(f"LED Override mode: {DUT.lock_override}")

    def _provision_lock_toggle(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        if DUT.self_destruct_enabled:
            self.logger.info(f"Toggling Provision Lock with Self-Destruct enabled...")
            self.at.press(['key2', 'key5'])
            if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe REJECT_PATTERN for Provision Lock toggle with Self-Destruct enabled.")
        else:
            self.logger.info(f"Toggling Provision Lock...")
            self.at.press(['key2', 'key5'])
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for Provision Lock toggle.")
            else:
                DUT.provision_lock = not DUT.provision_lock
                self.logger.info(f"Provision Lock mode: {DUT.provision_lock}")

    def _read_only_toggle(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Toggling Read-Only mode...")
        self.at.press(['key6', 'key7'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for Read-Only toggle.")
        else:
            DUT.read_only_enabled = True
            self.logger.info(f"Read-Only mode: {DUT.read_only_enabled}")

    def _read_write_toggle(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Toggling to Read-Write mode...")
        self.at.press(['key7', 'key9'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for Read-Write toggle.")
        else:
            DUT.read_only_enabled = False
            self.logger.info(f"Read-Write mode: {DUT.read_only_enabled}")

    def _self_destruct_toggle(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        if DUT.provision_lock:
            self.logger.info(f"Toggling Self-Destruct PIN with Provision Lock enabled...")
            self.at.press(['key4', 'key7'])
            if not self.at.await_and_confirm_led_pattern(LEDs['REJECT_PATTERN'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe REJECT_PATTERN for Self-Destruct toggle with Provision Lock enabled.")
        else:
            self.logger.info(f"Toggling Self-Destruct PIN...")
            self.at.press(['key4', 'key7'])
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for Self-Destruct toggle.")
            else:
                DUT.self_destruct_enabled = True

    def _user_forced_enrollment_toggle(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        if not DUT.user_forced_enrollment:
            self.logger.info(f"Toggling User-Forced Enrollment...")
            self.at.press(['key0', 'key1'])
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for User-Forced Enrollment toggle.")
            else:
                DUT.user_forced_enrollment = True
                self.logger.info(f"User-Forced Enrollment toggled. New state: {DUT.user_forced_enrollment}")
        else:
            self.logger.info(f"Toggling User-Forced Enrollment with User-Forced Enrollment enabled...")
            self.at.press(['key0', 'key1'])
            if not self.at.await_and_confirm_led_pattern(LEDs['REJECT_PATTERN'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe REJECT_PATTERN for User-Forced Enrollment toggle.")
            else:
                self.logger.info(f"User-Forced Enrollment cannot be disabled using this toggle...")

    def _delete_pins_toggle(self, event_data: EventData) -> None:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        if not DUT.user_forced_enrollment:
            self.logger.info(f"Toggling Delete PINs...")
            self.at.press(['key7', 'key8'], duration_ms=6000)
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                raise TransitionCallbackError("Did not observe ACCEPT_PATTERN for Delete PINs toggle.")
            else:
                if not self.at.await_and_confirm_led_pattern(LEDs['RED_BLUE'], timeout=5.0, replay_extra_context=context):
                    raise TransitionCallbackError("Did not observe RED_BLUE for Delete PINs initiation.")
                else:
                    self.at.press(['key7', 'key8'], duration_ms=6000)
                    if not self.at.confirm_led_solid(LEDs["ACCEPT_STATE"], minimum=1, timeout=3, replay_extra_context=context):
                        raise TransitionCallbackError("Did not observe final ACCEPT_PATTERN for recovery PIN confirmation.")
                    else:
                        self.logger.info(f"Delete PINs toggled. PINs deleted...")

