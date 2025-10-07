# Directory: controllers
# Filename: finite_state_machine.py
#!/usr/bin/env python3

import logging
import time # For simulating delays if needed
from typing import List, Dict, Tuple, Any, Optional, Callable, Union # For type hinting
import os
from pprint import pprint
import json
from utils.led_states import LEDs
import subprocess
import statistics
import sys

### For running scripts
# from transitions import Machine, EventData
###

# --- FSM Machine Type Selection ---
# This allows us to use a lightweight machine for runtime and tests,
# and a heavyweight machine for generating diagrams, without affecting the main code.
DIAGRAM_MODE = os.environ.get('FSM_DIAGRAM_MODE', 'false').lower() == 'true'

if DIAGRAM_MODE:
    from transitions.extensions import GraphMachine as Machine
    print("FSM running in DIAGRAM_MODE with GraphMachine.")
else:
    from transitions import Machine
from transitions import EventData


from usb_tool import find_apricorn_device
from .unified_controller import UnifiedController

# --- Custom Exception for Transition Failures ---
class TransitionCallbackError(Exception):
    """Custom exception to be raised from 'before' callbacks on failure."""
    pass

def release_valve(func):
    """Mark a transition callback so its return value can gate the transition."""
    setattr(func, '_release_valve', True)
    return func

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
_json_path = os.path.join(_project_root, 'utils', 'config', 'device_properties.json')
_hardware_config = os.path.join(_project_root, 'utils', 'config', 'hardware_configuration_settings.json')

_CACHED_SCANNED_SERIAL: Optional[str] = None


# --- File I/O and Parsing (operations that can fail are kept in the try block) ---
try:
    _fsm_module_logger.debug(f"Attempting to load module config from: {_json_path}")
    with open(_json_path, 'r') as f:
        DEVICE_PROPERTIES = json.load(f)
    _fsm_module_logger.debug("Successfully loaded module-level DEVICE_PROPERTIES from JSON.")

    _fsm_module_logger.debug(f"Attempting to load module config from: {_hardware_config}")
    with open(_hardware_config, 'r') as f:
        HARDWARE_CONFIG = json.load(f)
    _fsm_module_logger.debug("Successfully loaded module-level HARDWARE_CONFIG from JSON.")
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
    """
    A stateful model representing the Device Under Test (self.dut).

    This class acts as a data container, tracking the known and assumed state
    of the physical hardware device. It holds properties like enrolled PINs,
    feature settings (e.g., read-only, self-destruct), security counters,
    and hardware identifiers. The FSM and its callbacks read from and write
    to an instance of this class to mirror the device's real-world state.
    """
    def __init__(self, 
                 at_controller: 'UnifiedController', 
                 target_device_profile: Optional[str] = None, 
                 scanned_serial_number: Optional[str] = None,
                 power: bool = False):
        """
        Initializes the DeviceUnderTest state model.

        Args:
            at_controller: An instance of the UnifiedController to allow
                           this model to interact with hardware if needed.
            target_device_profile (Optional[str]): The device profile key from device_properties.json.
                                                   If not provided, a fallback is used.
            scanned_serial_number (Optional[str]): An optional serial number to use.
                                                   If not provided, a one-time barcode
                                                   scan will be attempted and cached.
        """
        global _CACHED_SCANNED_SERIAL
        self.at = at_controller

        if not target_device_profile:
            self.device_name = HARDWARE_CONFIG['device_properties']['name']
            power = HARDWARE_CONFIG['device_properties']['name']
        else:
            self.device_name = target_device_profile

        self.name: str = self.device_name
        self.battery: bool = power
        self.bridge_fw: str = DEVICE_PROPERTIES[self.device_name]['bridge_fw']
        self.pid: str = DEVICE_PROPERTIES[self.device_name]['id_product']
        self.mcu_fw_human_readable = DEVICE_PROPERTIES[self.device_name]['mcu_fw']
        self.mcu_fw: list[int] = self.mcu_fw_human_readable.split(".")
        self.fips: int = DEVICE_PROPERTIES[self.device_name]['fips']
        self.secure_key: bool = DEVICE_PROPERTIES[self.device_name]['secure_key']
        self.usb3: bool = False
        self.disk_path: str = ""
        self.mounted: bool = False
        self.serial_number: str = ""
        self.dev_keypad_serial_number: str = ""
        # Logic for one-time barcode scan
        if scanned_serial_number is not None:
            self.scanned_serial_number = scanned_serial_number
            _CACHED_SCANNED_SERIAL = scanned_serial_number
        elif _CACHED_SCANNED_SERIAL is not None:
            self.scanned_serial_number = _CACHED_SCANNED_SERIAL
        else:
            _CACHED_SCANNED_SERIAL = self.at.scan_barcode()
            self.scanned_serial_number = _CACHED_SCANNED_SERIAL

        self.model_id_1: int = DEVICE_PROPERTIES[self.device_name]['model_id_digit_1']
        self.model_id_2: int = DEVICE_PROPERTIES[self.device_name]['model_id_digit_2']
        self.hardware_id_1: int = DEVICE_PROPERTIES[self.device_name]['hardware_major']
        self.hardware_id_2: int = DEVICE_PROPERTIES[self.device_name]['hardware_minor']
        self.scb_part_number: str = DEVICE_PROPERTIES[self.device_name]['scb_part_number']
        self.single_code_base: bool = self.scb_part_number is None
        self.completed_cmfr: bool = True # ASSUMPTION IS MOST DEVICES WILL NOT BE IN FACTORY_MODE

        self.basic_disk: bool = True
        self.removable_media: bool = False

        self.brute_force_counter: int = 20
        self.brute_force_counter_current: int = 20

        self.led_flicker: bool = False
        self.lock_override: bool = False

        self.manufacturer_reset_enum: bool = False

        self.maximum_pin_counter: int = 16
        self.minimum_pin_counter = int(DEVICE_PROPERTIES[self.device_name]['minimum_pin_length'])
        self.default_minimum_pin_counter = int(DEVICE_PROPERTIES[self.device_name]['minimum_pin_length'])

        self.provision_lock: bool = False
        self.provision_lock_bricked: bool = False
        self.provision_lock_recovery_counter: int = 5

        self.read_only_enabled: bool = False

        self.unattended_auto_lock_counter: int = 0
        self.needs_block_orientation: bool = False

        self.user_forced_enrollment: bool = False
        self.user_forced_enrollment_used: bool = False

        self.pending_enrollment_type: Optional[str] = None

        self.admin_pin: list[str] = []
        self.old_admin_pin: list[str] = []

        self.recovery_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, 5)}
        self.old_recovery_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, 5)}
        self.recovery_pin_used: Dict[int, bool] = {i: False for i in range(1, 5)}

        self.self_destruct_enabled: bool = False
        self.self_destruct_pin: list[str] = []
        self.old_self_destruct_pin: list[str] = []
        self.self_destruct_enum: bool = False
        self.self_destruct_used: bool = False

        self.user_count = DEVICE_PROPERTIES[self.device_name]['user_count']
        self._max_users = 1 if self.fips in [2, 3] else 4
        self.user_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, self._max_users + 1)}
        self.old_user_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, self._max_users + 1)}
        self.user_pin_enum: Dict[int, bool] = {i: False for i in range(1, self._max_users + 1)}


    def _delete_pins(self):
        """ This function sets the current self.dut recovery_pin, self_destruct and user_pin parameters to the 'old' parameters.
            Then clears the current self.dut recovery_pin, self_destruct_pin, user_forced_enrollment and user_pin parameters
            Args:
                None:
        """
        self.old_recovery_pin = self.recovery_pin
        self.recovery_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, 5)}
        self.recovery_pin_used: Dict[int, bool] = {i: False for i in range(1, 5)}

        self.old_self_destruct_pin = self.self_destruct_pin
        self.self_destruct_pin = []
        self.self_destruct_enabled = False
        self.self_destruct_enum = False
        self.self_destruct_used = False

        self.old_user_pin = self.user_pin
        self.user_count = DEVICE_PROPERTIES[self.device_name]['user_count']
        self._max_users = 1 if self.fips in [2, 3] else 4
        self.user_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, self._max_users + 1)}
        self.user_pin_enum: Dict[int, bool] = {i: False for i in range(1, self._max_users + 1)}

        self.user_forced_enrollment = False
        self.user_forced_enrollment_used = False

    def _reset(self):
        """ Resets all attributes of the self.dut model to their default initial state.
            Args:
                None:
        """
        # Re-call init, passing along the controller it already has
        self.__init__(
            self.at, 
            target_device_profile=self.device_name, 
            power=self.battery
        )

    def _self_destruct(self):
        """ This function sets the current self.dut admin_pin, recovery_pin, self_destruct_pin, and user_pin parameters to the 'old' parameters.
            Then clears the current self.dut admin_pin, recovery_pin, self_destruct_pin, user_forced_enrollment and user_pin parameters
            Args:
                None:
        """
        self.old_admin_pin = self.admin_pin
        self.admin_pin = self.self_destruct_pin

        self.old_recovery_pin = self.recovery_pin
        self.recovery_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, 5)}
        self.recovery_pin_used: Dict[int, bool] = {i: False for i in range(1, 5)}

        self.user_count = DEVICE_PROPERTIES[self.device_name]['user_count']
        self._max_users = 1 if self.fips in [2, 3] else 4
        self.user_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, self._max_users + 1)}
        self.old_user_pin: Dict[int, Optional[List[str]]] = {i: None for i in range(1, self._max_users + 1)}
        self.user_pin_enum: Dict[int, bool] = {i: False for i in range(1, self._max_users + 1)}

        self.old_self_destruct_pin = self.self_destruct_pin
        self.self_destruct_pin = []
        self.self_destruct_enabled = False
        self.self_destruct_used = True

        self.brute_force_counter = 20
        self.brute_force_counter_current = 20

        self.unattended_auto_lock_counter = 0

class TestSession:
    """
    Tracks and stores information about a single script execution session.

    This class acts as a data container for metadata related to a test run,
    including timing, failure/warning counts, enumeration statistics, and
    test results. It is distinct from the DeviceUnderTest, which models the
    hardware state.
    """    
    __test__ = False
    def __init__(self, at_controller: 'UnifiedController', dut_instance: 'DeviceUnderTest'):
        """
        Initializes the session tracker.

        Args:
            script_num (int): An identifier for the script being run.
            script_title (str): A human-readable title for the script.
        """

        self.logger = logging.getLogger("DeviceFSM.Simplified")
        self.at = at_controller
        self.dut = dut_instance # Use the provided DUT, don't create a new one.

        # Script Identification
        self.script_num: int = 0
        self.script_title: str = "N/A"

        # Test Block Management
        self.current_test_block: int = -1
        # Map of block_id -> block_name (in insertion order)
        self.test_blocks: Dict[int, str] = {}
        self.block_failure_count: dict = {}
        self.block_warning_count: dict = {}

        # Timing
        self.script_start_time: float = time.time()
        self.block_start_time: float = 0.0
        self.block_end_time: float = 0.0
        
        self.block_enumeration_totals: dict = {}
        self.script_enumeration_totals: dict = {}

        # Failure and Warning Details
        self.failure_block: dict = {}
        self.warning_block: dict = {}
        self.warning_description_block: dict = {}

        # Other Metrics
        self.key_press_totals: dict = {}
        self.speed_test_results: list = []
        self.usb3_fail_count: int = 0

    def start_new_block(self, block_name: str, current_test_block: int):
        """Resets counters and timers for the start of a new test block."""
        self.block_start_time = time.time()
        self.current_test_block = current_test_block
        self.dut.needs_block_orientation = True
        # Track mapping from block id to human-readable name
        self.test_blocks[self.current_test_block] = block_name

        self.block_enumeration_totals.update({self.current_test_block: {}})
        self.block_enumeration_totals[self.current_test_block].update({"mfr": 0})
        self.block_enumeration_totals[self.current_test_block].update({"oob": 0})
        self.block_enumeration_totals[self.current_test_block].update({"pin": 0})
        self.block_enumeration_totals[self.current_test_block].update({"spi": 0})
        
        self.block_failure_count[self.current_test_block] = 0
        self.block_warning_count[self.current_test_block] = 0
        self.failure_block[self.current_test_block] = []
        self.warning_block[self.current_test_block] = []
        self.warning_description_block[self.current_test_block] = []

        if self.dut.secure_key:
            self.at.on("hold")

        self.logger.info(f"__________"*10)
        self.logger.info("")

    def end_block(self):
        """Finalizes metrics for the completed test block."""
        self.block_end_time = time.time()
        self.dut.needs_block_orientation = False

    def log_key_press(self, key_name: str):
        """Increments the counter for a specific key press."""
        if key_name not in self.key_press_totals:
            self.key_press_totals[key_name] = 0
        self.key_press_totals[key_name] += 1

    def log_enumeration(self, enum_type: str):
            """
            Increments the counter for a specific type of enumeration.
            Assumes enum_type has already been validated by the caller.
            """
            self.block_enumeration_totals[self.current_test_block][enum_type] += 1

    def log_failure(self, failure_message: str):
        """Logs a failure for a specific test block."""
        self.block_failure_count[self.current_test_block] += 1
        self.failure_block[self.current_test_block].append(failure_message)
        self.logger.error(failure_message)
        
    def log_warning(self, block_name: str, warning_summary: str, warning_details: str = ""):
        """Logs a warning for a specific test block."""
        self.block_warning_count[self.current_test_block] += 1
        self.warning_block[self.current_test_block].append(warning_summary)
        self.warning_description_block[self.current_test_block].append(warning_details)
        
    def add_speed_test_result(self, result: Any):
        """Adds a speed test result to the session."""
        self.speed_test_results.append(result)

    def generate_summary_report(self):
        """
        Generates and logs a comprehensive summary of the test session.
        This is a refactor of the original finishScript() function, preserving its output format.
        
        Args:
            (No arguments needed, uses self.dut and self.logger)
        """

        logger = self.logger
        dut = self.dut

        self.logger.info(f"__________"*10)
        self.logger.info("")
        self.logger.info(f"{self.script_title} Script Details:")
        self.logger.info("____"*10)

        # --- Keypress Totals ---
        logger.info("Keypress Totals:")
        if self.key_press_totals:
            # Note: The 'unlockKey' concept from the old script is simplified to 'unlock'
            unlock_key_name = 'unlock'
            key_layout = {
                'secure': [
                    ['key1', 'key2'], ['key3', 'key4'], ['key5', 'key6'],
                    ['key7', 'key8'], ['key9', 'key0'], ['lock', unlock_key_name]
                ],
                'standard': [
                    ['key1', 'key2', 'key3'], ['key4', 'key5', 'key6'],
                    ['key7', 'key8', 'key9'], ['lock', 'key0', unlock_key_name]
                ]
            }
            layout_to_use = key_layout['secure'] if dut.secure_key else key_layout['standard']
            max_key_len = 6

            for row in layout_to_use:
                # Build each column individually with the new formatting.
                cols = [f"{key:>{max_key_len}}: {self.key_press_totals.get(key, 0):<3}" for key in row]
                
                # Join the aligned columns with a consistent separator.
                row_str = "    ".join(cols)
                logger.info(row_str)
        else:
            logger.info("  No key presses were tracked.")
        self.logger.info("____"*10)

        # --- Enumeration Totals ---
        logger.info("Enumerations Totals:")
        logger.info("{:>15}   {:^5}   {:^5}   {:^5}".format("Reset", "OOB", "PIN", "SPI"))
        
        total_resets = 0
        total_oob = 0
        total_pin = 0
        total_spi = 0

        for block_id, _block_name in self.test_blocks.items():
            resets = self.block_enumeration_totals[block_id]['mfr']
            oob = self.block_enumeration_totals[block_id]['oob']
            pin = self.block_enumeration_totals[block_id]['pin']
            spi = self.block_enumeration_totals[block_id]['spi']
            total_resets += resets
            total_oob += oob
            total_pin += pin
            total_spi += spi
            logger.info("Block {:<2}: {:^5} | {:^5} | {:^5} | {:^5} |".format(block_id, resets, oob, pin, spi))
        
        logger.info("Total   : {:^5} | {:^5} | {:^5} | {:^5} |".format(total_resets, total_oob, total_pin, total_spi))
        self.logger.info("____"*10)

        # --- Block Results (Failures/Warnings) ---
        logger.info("Block Result:")
        logger.info("")
        total_failures = sum(len(v) for v in self.failure_block.values())
        total_warnings = sum(len(v) for v in self.warning_block.values())

        block_headers = {
            block_id: f"Block {block_id} ({block_name}):"
            for block_id, block_name in self.test_blocks.items()
        }
        header_width = max((len(text) for text in block_headers.values()), default=0)
        status_padding = 2  # Align status labels with a consistent gap

        for block_id, block_name in self.test_blocks.items():
            failures = self.failure_block.get(block_id, [])
            warnings = self.warning_block.get(block_id, [])
            header = block_headers[block_id]

            if not failures and not warnings:
                padded_header = f"{header:<{header_width + status_padding}}"
                logger.info(f"{padded_header}Passed")
            else:
                logger.info(header)
                if warnings:
                    logger.info(f"         Warning(s):")
                    for w_summary in warnings:
                        logger.info(f"                     - {w_summary}")
                if failures:
                    logger.error(f"         Failure(s):")
                    for f_summary in failures:
                        logger.error(f"                     - {f_summary}")
        
                logger.info("")
        if total_warnings > 0: logger.info(f"Total Number of Warnings: {total_warnings}")
        if total_failures > 0: logger.info(f"Total Number of Failures: {total_failures}")
        logger.info("")

        # --- Speed Test Results ---
        if self.speed_test_results:
            logger.info("Speed Test Block Results:")
            for result in self.speed_test_results:
                 logger.info(f"  Block {result.get('block', 'N/A')}: Read: {result.get('read', 'N/A')} MB/s, Write: {result.get('write', 'N/A')} MB/s")
            
            all_reads = [r['read'] for r in self.speed_test_results if 'read' in r]
            all_writes = [r['write'] for r in self.speed_test_results if 'write' in r]
            
            logger.info("Speedtest Totals:")
            if all_reads:
                logger.info("  Read:")
                logger.info(f"    Min: {min(all_reads):.1f} MB/s, Max: {max(all_reads):.1f} MB/s, Avg: {statistics.mean(all_reads):.1f} MB/s")
            if all_writes:
                logger.info("  Write:")
                logger.info(f"    Min: {min(all_writes):.1f} MB/s, Max: {max(all_writes):.1f} MB/s, Avg: {statistics.mean(all_writes):.1f} MB/s")
            self.logger.info("____"*10)

        if self.usb3_fail_count > 0:
            logger.info(f"{self.usb3_fail_count} USB3 Failures detected during the session.")

        logger.info(f"{self.script_title} script complete.")
        logger.info("")

    def get_failure_summary_string(self) -> str:
        """
        Aggregates all failure descriptions into a single comma-separated string.
        
        Returns:
            A single string containing all failure messages, or an empty string if none.
        """
        msg_list = []
        for i, (block_id, block_name) in enumerate(self.test_blocks.items(), 1):
            failures = self.failure_block.get(block_id)
            if not failures:
                continue
            
            failure_details = "; ".join(failures)
            msg_list.append(f"Block {i} ({block_name}): [{failure_details}]")
            
        return ", ".join(msg_list)

    def end_session_and_report(self) -> Optional[str]:
        """
        Finalizes the test session, generates the summary report, and performs cleanup.
        This is the main public method to be called at the end of a test script.

        Returns:
            A string containing an aggregated summary of all failures, or None if no failures.
        """
        
        # Step 1: Generate and log the detailed report using the session object.
        self.generate_summary_report()

        # Step 2: Perform final hardware cleanup.
        self.logger.info("Powering down device at end of session.")
        self.at.off("usb3")
        self.at.off("connect")
        
        # Step 3: Aggregate failure messages for external tools.
        failure_string = self.get_failure_summary_string()
        if failure_string:
            return failure_string
        return None

class CallableCondition:
    """
    A wrapper that makes a callable condition have a readable __name__
    for diagram generation, allowing inline lambda definitions to be labeled.
    """
    def __init__(self, func: Callable[..., bool], name: str):
        """
        Initializes the CallableCondition.

        Args:
            func: The callable (e.g., a lambda) to be executed as the condition.
            name: A human-readable name for the condition, used in diagrams.
        """
        self.func = func
        self.__name__ = name  # <-- THE CRITICAL CHANGE

    def __call__(self, *args, **kwargs) -> bool:
        """
        Makes the object behave like a function for the FSM.

        When the FSM evaluates this condition, this method is called, which
        in turn executes the wrapped function and returns its boolean value.

        Returns:
            The boolean result of the wrapped function.
        """
        return bool(self.func(*args, **kwargs))

    def __repr__(self) -> str:
        """
        Provides a helpful string representation for debugging.
        """
        # A helpful representation for debugging
        return f"<CallableCondition: {self.__name__}>"

## --- FSM Class Definition ---
class ApricornDeviceFSM:
    """
    A Finite State Machine (FSM) to model and control an Apricorn secure device.

    This class defines the operational states of the device and the transitions
    between them. It uses a `UnifiedController` instance (`at`) to interact
    with the physical hardware (key presses, LED state verification) and a
    `DeviceUnderTest` instance (`self.dut`) to maintain a model of the device's
    current configuration and state.

    Attributes:
        STATES: A list of all possible states the machine can be in.
        logger: A dedicated logger for FSM activities.
        at: The `UnifiedController` instance for hardware interaction.
        machine: The `transitions` library's `Machine` object that powers the FSM.
        state: The current state of the FSM.
        source_state: The state from which the last transition originated.
    """

    STATES: List[str] = ['OFF', 'POWER_ON_SELF_TEST', 'ERROR_MODE', 'BRUTE_FORCE', 'BRICKED', 'OOB_MODE', 'STANDBY_MODE', 'USER_FORCED_ENROLLMENT', 'FACTORY_MODE',
                         'UNLOCKED_ADMIN', 'UNLOCKED_USER', 'UNLOCKED_RESET',
                         'ADMIN_MODE', 'PIN_ENROLLMENT', 'COUNTER_ENROLLMENT',
                         'DIAGNOSTIC_MODE',
    ]

    logger: logging.Logger
    at: 'UnifiedController'
    dut: 'DeviceUnderTest'
    session: 'TestSession'
    machine: Machine
    state: str
    source_state: str = 'OFF'

    def __init__(self, at_controller: 'UnifiedController', session_instance: 'TestSession', dut_instance: 'DeviceUnderTest'):
        """
        Initializes the ApricornDeviceFSM.
        ...
        """
        self.logger = logging.getLogger("DeviceFSM.Simplified")
        self.at = at_controller
        self.dut = dut_instance
        self.session = session_instance

        # Define all transitions in a single list of dictionaries, including lambdas.
        transitions = [
            # --- Power On/Off Transitions ---
            {'trigger': 'power_on', 'source': 'OFF', 'dest': 'POWER_ON_SELF_TEST', 'before': '_do_power_on', 'conditions': [CallableCondition(lambda _: not bool(self.dut.battery), "dut.battery == False")]},
            {'trigger': 'power_off', 'source': '*', 'dest': 'OFF', 'before': '_do_power_off'},
            # {'trigger': 'collect_error_number', 'source': '*', 'dest': 'ERROR_MODE'},

            # --- 'Idle' Mode Transitions (battery-powered) ---
            {'trigger': 'power_on', 'source': 'OFF', 'dest': 'FACTORY_MODE',  'before': '_do_power_on', 'conditions': [CallableCondition(lambda _: not bool(self.dut.completed_cmfr), "dut.completed_cmfr == False")]},
            {'trigger': 'power_on', 'source': 'OFF', 'dest': 'BRUTE_FORCE',  'before': '_do_power_on', 'conditions': [CallableCondition(lambda _: self.dut.brute_force_counter_current == 0, "dut.brute_force_counter_current == 0")]},
            {'trigger': 'power_on', 'source': 'OFF', 'dest': 'USER_FORCED_ENROLLMENT',  'before': '_do_power_on', 'conditions': [CallableCondition(lambda _: bool(self.dut.user_forced_enrollment), "dut.user_forced_enrollment == True")]},
            {'trigger': 'power_on', 'source': 'OFF', 'dest': 'OOB_MODE',  'before': '_do_power_on', 'conditions': [CallableCondition(lambda _: not bool(self.dut.admin_pin), "dut.admiPIN not enrolled")]},
            {'trigger': 'power_on', 'source': 'OFF', 'dest': 'STANDBY_MODE',  'before': '_do_power_on', 'conditions': [CallableCondition(lambda _: bool(self.dut.admin_pin), "dut.admin_pin enrolled")]},
            {'trigger': 'user_reset', 'source': 'OFF', 'dest': 'OOB_MODE', 'before': '_do_user_reset', 'conditions': [CallableCondition(lambda _: not bool(self.dut.provision_lock) and bool (self.dut.battery), "dut.provision_lock == False AND dut.battery == True")]},
            {'trigger': 'manufacturer_reset', 'source': 'OFF', 'dest': 'OOB_MODE', 'before': '_do_manufacturer_reset', 'conditions': [CallableCondition(lambda _: not bool(self.dut.provision_lock) and bool (self.dut.battery), "dut.provision_lock == False AND dut.battery == True")]},

            # --- 'Idle' Mode Transitions (from POST) ---
            {'trigger': 'post_pass', 'source': 'POWER_ON_SELF_TEST', 'dest': 'FACTORY_MODE', 'conditions': [CallableCondition(lambda _: not bool(self.dut.completed_cmfr), "dut.completed_cmfr == False")]},
            {'trigger': 'post_pass', 'source': 'POWER_ON_SELF_TEST', 'dest': 'BRUTE_FORCE', 'conditions': [CallableCondition(lambda _: self.dut.brute_force_counter_current == 0, "dut.brute_force_counter_current == 0")]},
            {'trigger': 'post_pass', 'source': 'POWER_ON_SELF_TEST', 'dest': 'USER_FORCED_ENROLLMENT', 'conditions': [CallableCondition(lambda _: bool(self.dut.user_forced_enrollment), "dut.user_forced_enrollment == True")]},
            {'trigger': 'post_pass', 'source': 'POWER_ON_SELF_TEST', 'dest': 'OOB_MODE', 'conditions': [CallableCondition(lambda _: not bool(self.dut.admin_pin), "dut.admiPIN not enrolled")]},
            {'trigger': 'post_pass', 'source': 'POWER_ON_SELF_TEST', 'dest': 'STANDBY_MODE', 'conditions': [CallableCondition(lambda _: bool(self.dut.admin_pin), "dut.admin_pin enrolled")]},

            # --- RESET Transitions ---
            {'trigger': 'manufacturer_reset', 'source': ['FACTORY_MODE', 'OOB_MODE', 'STANDBY_MODE', 'BRUTE_FORCE', 'USER_FORCED_ENROLLMENT'], 'dest': 'UNLOCKED_RESET', 'before': '_do_manufacturer_reset'},
            {'trigger': 'lock_reset', 'source': 'UNLOCKED_RESET', 'dest': 'OOB_MODE', 'before': '_press_lock_button'},

            # --- OOB Mode Transitions ---
            {'trigger': 'enter_diagnostic_mode', 'source': 'OOB_MODE', 'dest': 'DIAGNOSTIC_MODE'},
            {'trigger': 'exit_diagnostic_mode', 'source': 'DIAGNOSTIC_MODE', 'dest': 'OOB_MODE', 'conditions': [CallableCondition(lambda _: not bool(self.dut.admin_pin), "dut.admin_pin not enrolled")]},
            {'trigger': 'enroll_admin', 'source': 'OOB_MODE', 'dest': 'PIN_ENROLLMENT', 'before': '_admin_enrollment'},
            {'trigger': 'user_reset', 'source': 'OOB_MODE', 'dest': 'OOB_MODE', 'before': '_do_user_reset', 'conditions': [CallableCondition(lambda _: not bool(self.dut.provision_lock), "dut.provision_lock == False")]},

            # --- Standby Mode Transitions ---
            {'trigger': 'admin_mode_login', 'source': 'STANDBY_MODE', 'dest': 'ADMIN_MODE', 'before': '_enter_admin_mode_login'},
            {'trigger': 'lock_admin', 'source': 'ADMIN_MODE', 'dest': 'STANDBY_MODE', 'before': '_press_lock_button'},
            {'trigger': 'unlock_admin', 'source': 'STANDBY_MODE', 'dest': 'UNLOCKED_ADMIN', 'before': '_enter_admin_pin'},
            {'trigger': 'lock_admin', 'source': 'UNLOCKED_ADMIN', 'dest': 'STANDBY_MODE', 'before': '_press_lock_button'},
            {'trigger': 'enter_diagnostic_mode', 'source': 'STANDBY_MODE', 'dest': 'DIAGNOSTIC_MODE'},
            {'trigger': 'self_destruct', 'source': 'STANDBY_MODE', 'dest': 'UNLOCKED_ADMIN', 'before': '_enter_self_destruct_pin'},
            {'trigger': 'exit_diagnostic_mode', 'source': 'DIAGNOSTIC_MODE', 'dest': 'STANDBY_MODE', 'conditions': [CallableCondition(lambda _: bool(self.dut.admin_pin), "dut.admin_pin enrolled")]},
            {'trigger': 'user_reset', 'source': 'STANDBY_MODE', 'dest': 'OOB_MODE', 'before': '_do_user_reset', 'conditions': [CallableCondition(lambda _: not bool(self.dut.provision_lock), "dut.provision_lock == False")]},
            {'trigger': 'unlock_user', 'source': 'STANDBY_MODE', 'dest': 'UNLOCKED_USER', 'before': '_enter_user_pin'},
            {'trigger': 'lock_user', 'source': 'UNLOCKED_USER', 'dest': 'STANDBY_MODE', 'before': '_press_lock_button'},
            {'trigger': 'fail_unlock', 'source': 'STANDBY_MODE', 'dest': 'STANDBY_MODE', 'before': '_enter_invalid_pin', 'conditions': [CallableCondition(lambda _: self.dut.brute_force_counter_current > 1 and not (self.dut.brute_force_counter_current == (self.dut.brute_force_counter/2)+1), "Brute Force not triggered")]},
            {'trigger': 'fail_unlock', 'source': 'STANDBY_MODE', 'dest': 'BRUTE_FORCE', 'before': '_enter_invalid_pin', 'conditions': [CallableCondition(lambda _: (self.dut.brute_force_counter_current == (self.dut.brute_force_counter/2)+1) or self.dut.brute_force_counter_current == 1, "Brute Force triggered")]},

            # --- User-Forced Enrollment Mode Transitions ---
            {'trigger': 'admin_mode_login', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'ADMIN_MODE', 'before': '_enter_admin_mode_login'},
            {'trigger': 'lock_admin', 'source': 'ADMIN_MODE', 'dest': 'USER_FORCED_ENROLLMENT', 'before': '_press_lock_button'},
            {'trigger': 'unlock_admin', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'UNLOCKED_ADMIN', 'before': '_enter_admin_pin'},
            {'trigger': 'lock_admin', 'source': 'UNLOCKED_ADMIN', 'dest': 'USER_FORCED_ENROLLMENT', 'before': '_press_lock_button'},
            {'trigger': 'enroll_user', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'STANDBY_MODE', 'before': '_user_enrollment'},
            {'trigger': 'enter_diagnostic_mode', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'DIAGNOSTIC_MODE'},
            {'trigger': 'exit_diagnostic_mode', 'source': 'DIAGNOSTIC_MODE', 'dest': 'USER_FORCED_ENROLLMENT', 'conditions': [CallableCondition(lambda _: bool(self.dut.user_forced_enrollment), "dut.user_forced_enrollment == True")]},
            {'trigger': 'self_destruct', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'UNLOCKED_ADMIN', 'before': '_enter_self_destruct_pin'},
            {'trigger': 'user_reset', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'OOB_MODE', 'before': '_do_user_reset', 'conditions': [CallableCondition(lambda _: not bool(self.dut.provision_lock), "dut.provision_lock == False")]},
            {'trigger': 'unlock_user', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'UNLOCKED_USER', 'before': '_enter_user_pin', 'conditions': [CallableCondition(lambda _: any(pin is not None for pin in self.dut.user_pin.values()), "dut.user_pin(s) enrolled")]},
            {'trigger': 'lock_user', 'source': 'UNLOCKED_USER', 'dest': 'USER_FORCED_ENROLLMENT', 'before': '_press_lock_button'},
            {'trigger': 'fail_unlock', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'STANDBY_MODE', 'before': '_enter_invalid_pin', 'conditions': [CallableCondition(lambda _: self.dut.brute_force_counter_current > 1 and not (self.dut.brute_force_counter_current == (self.dut.brute_force_counter/2)+1), "Brute Force not triggered")]},
            {'trigger': 'fail_unlock', 'source': 'USER_FORCED_ENROLLMENT', 'dest': 'BRUTE_FORCE', 'before': '_enter_invalid_pin', 'conditions': [CallableCondition(lambda _: self.dut.brute_force_counter_current == self.dut.brute_force_counter/2 or self.dut.brute_force_counter_current == 1, "Brute Force triggered")]},

            # --- Brute Force Mode Transitions ---
            {'trigger': 'last_try_login', 'source': 'BRUTE_FORCE', 'dest': 'STANDBY_MODE', 'before': '_enter_last_try_pin', 'conditions': [CallableCondition(lambda _: self.dut.brute_force_counter_current == self.dut.brute_force_counter/2, "Brute Force halfway point")]},
            {'trigger': 'user_reset', 'source': 'BRUTE_FORCE', 'dest': 'OOB_MODE', 'before': '_do_user_reset', 'conditions': [CallableCondition(lambda _: not bool(self.dut.provision_lock), "dut.provision_lock == False")]},
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
            {'trigger': 'enroll_user', 'source': 'ADMIN_MODE', 'dest': 'PIN_ENROLLMENT', 'before': '_user_enrollment', 'conditions': [CallableCondition(lambda _: any(pin_value is None for pin_value in self.dut.user_pin.values()), "Empty user slot available")]},
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

        release_valve_transitions: List[Tuple[Dict[str, Any], Callable[[EventData], Any]]] = []
        for transition in transitions:
            before_name = transition.get('before')
            if not before_name:
                continue
            candidate = getattr(self, before_name, None)
            if callable(candidate) and getattr(candidate, '_release_valve', False):
                release_valve_transitions.append((transition, candidate))

        for transition, method in release_valve_transitions:
            transition.pop('before', None)
            transition.setdefault('conditions', [])
            transition['conditions'].append(
                CallableCondition(
                    lambda event_data, bound_method=method: bool(bound_method(event_data)),
                    f"{method.__name__} release valve"
                )
            )

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

        self._block_orientation_log: Dict[int, str] = {}
        self.orienting: bool = False

        # --- Public functions --- #
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
        self.lock_reset: Callable
        self.lock_user: Callable
        self.manufacturer_reset: Callable
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

    def orient_for_block(
        self,
        *,
        usb3: bool = True,
        retry_attempts: int = 1,
        retry_delay_sec: float = 3.0,
    ) -> None:
        """Ensure the device boots into OOB_MODE before block actions begin."""
        self.orienting = True
        self.logger.warning(
            f"=== Block {self.session.current_test_block}: '{self.session.test_blocks[self.session.current_test_block]}' mode orientation ==="
        )

        self.dut.needs_block_orientation = False
        total_attempts = max(0, int(retry_attempts)) + 1

        for attempt in range(1, total_attempts + 1):
            self.logger.info(
                f"Mode orientation attempt {attempt}/{total_attempts} (usb3={usb3})."
            )

            if self.dut.provision_lock:
                if self.manufacturer_reset():
                    self.lock_reset()
                    self.orienting = False
                    self.dut.needs_block_orientation = False
                    self.logger.warning(
                        f"=== Block {self.session.current_test_block}: '{self.session.test_blocks[self.session.current_test_block]}' mode orientation success ==="
                    )
                    return
            else:
                if self.user_reset():
                    self.orienting = False
                    self.dut.needs_block_orientation = False
                    self.logger.warning(
                        f"=== Block {self.session.current_test_block}: '{self.session.test_blocks[self.session.current_test_block]}' mode orientation success ==="
                    )
                    return
            time.sleep(retry_delay_sec)
        self.logger.error("Mode orientation failed")
        self.session.generate_summary_report()
        raise SystemExit()

    def _log_state_change_details(self, event_data: EventData) -> None:
        """
        Logs the details of every state transition.

        This callback is executed automatically by the FSM after any state
        change. It captures the source state, destination state, and the
        triggering event for logging purposes.

        Args:
            event_data: The event data provided by the FSM, containing
                        details about the transition that just occurred.
        """
        if event_data.transition is None:
            self.logger.info(f"FSM initialized to state: {self.state}")
            return
        self.source_state = event_data.transition.source
        self.logger.info(f"State changed: {self.source_state} -> {self.state} (Event: {event_data.event.name})")

    def _sequence(self, pin_sequence: List[Any], **kwargs):
        """Tracks each key press and then executes the sequence."""
        for key in pin_sequence:
            if isinstance(key, list): # For simultaneous presses like ['key1', 'key2']
                for sub_key in key:
                    self.session.log_key_press(sub_key)
            else: # For single presses 'key1'
                self.session.log_key_press(key)
        self.at.sequence(pin_sequence, **kwargs)

    def _press(self, channel_or_channels: Union[str, List[str]], **kwargs):
        """Tracks each key press and then executes the press/hold action."""
        if isinstance(channel_or_channels, list):
            for key in channel_or_channels:
                self.session.log_key_press(key)
        else:
            self.session.log_key_press(channel_or_channels)
        self.at.press(channel_or_channels, **kwargs)

    def _on(self, channel_or_channels: str, **kwargs):
        """Tracks each key press and then executes the on action."""
        if isinstance(channel_or_channels, list):
            for key in channel_or_channels:
                self.session.log_key_press(key)
        else:
            self.session.log_key_press(channel_or_channels)
        self.at.on(channel_or_channels, **kwargs)

    def _increment_enumeration_count(self, enum_type: str):
        """Validates the enumeration type and logs it to the session."""
        # Define the valid enumeration types in one central place.
        valid_enum_types = ['pin', 'oob', 'mfr', 'spi']

        if enum_type in valid_enum_types:
            self.session.log_enumeration(enum_type)
        else:
            # The FSM has a logger and can correctly log a warning.
            self.logger.warning(f"Invalid enumeration type '{enum_type}' passed for tracking.")

###########################################################################################################
# Transition Functions (Automatic on entry to state)
    
    def on_enter_ADMIN_MODE(self, event_data: EventData) -> None:
        """
        Verifies the device state upon entering ADMIN_MODE.

        This 'on_enter' callback is automatically executed when the FSM
        transitions into the ADMIN_MODE state. It confirms that the device
        is displaying the stable solid blue LED pattern, indicating it is
        ready for administrative commands.

        Args:
            event_data: The event data provided by the FSM.
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
        Verifies the Power-On Self-Test (POST) result.

        This 'on_enter' callback is executed upon entering the
        POWER_ON_SELF_TEST state. It checks for the 'ACCEPT_PATTERN' LED
        sequence. On success, it triggers 'post_pass'; on failure, it
        triggers 'post_fail'.

        Args:
            event_data: The event data provided by the FSM.
        """
        self.logger.info("Entered POWER_ON_SELF_TEST state. Confirming POST result...")
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe ACCEPT_PATTERN pattern. POST failed.")
        else:
            self.post_pass()

    def on_enter_OFF(self, event_data: EventData) -> None:
        """
        Confirms the device is powered off.

        This 'on_enter' callback is executed when the FSM enters the OFF state.
        It ensures the physical power relays are off and verifies that all
        device LEDs are extinguished.

        Args:
            event_data: The event data provided by the FSM.
        """
        self.at.off("usb3")
        self.at.off("connect")
        # This callback uses the safe `on_enter` pattern, no change needed.
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        if self.dut.battery:
            duration = 20.0
        else:
            duration = 3.0
        if self.at.confirm_led_solid(LEDs['ALL_OFF'], minimum=1.0, timeout=duration, replay_extra_context=context):
            self.logger.info("Device is confirmed OFF.")
        else:
            self.logger.error("Failed to confirm device LEDs are OFF.")

    def on_enter_FACTORY_MODE(self,event_data: EventData) -> None:
        """
        Verifies the device state upon entering Factory Mode.

        This 'on_enter' callback confirms the device shows the correct
        red/green/blue LED pattern for Factory mode.

        Args:
            event_data: The event data provided by the FSM.
        """
        self.logger.info(f"Confirming Factory Mode (solid Red/Green/Blue)...")
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        if not self.at.confirm_led_solid(LEDs['ALL_ON'], minimum=3.0, timeout=10.0, replay_extra_context=context):
            self.logger.error("Failed to confirm FACTORY_MODE LEDs.")
        else:
            keypad_test = ["key1", "key2", "key3", "key4", "key5", "key6", "key7", "key8", "key9", "lock", "key0", "unlock"]
            for key in keypad_test:
                self._on(key)
                if not self.at.await_led_state(LEDs['ACCEPT_STATE'], timeout=1, clear_buffer=False, replay_extra_context=context):
                    self.at.off(key)
                    self.session.log_failure(f"Failed '{key}' confirmation")

    def on_enter_OOB_MODE(self, event_data: EventData) -> None:
        """
        Verifies the device state upon entering Out-Of-Box (OOB) Mode.

        This 'on_enter' callback confirms the device shows the correct
        green/blue LED pattern for OOB mode and has successfully enumerated
        on the USB bus.

        Args:
            event_data: The event data provided by the FSM.
        """
        self.logger.info(f"Confirming OOB Mode (solid Green/Blue)...")
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        if self.dut.battery:
            pattern = LEDs['GREEN_BLUE_BATTERY_STATE']
        else:
            pattern = LEDs['GREEN_BLUE_STATE']

        if self.at.confirm_led_solid(pattern, minimum=3.0, timeout=10.0, replay_extra_context=context):
            self.logger.info("Stable OOB_MODE confirmed.")
        else:
            self.dut.completed_cmfr = False
            self.session.log_failure("Failed to confirm OOB Mode LED pattern")
            if self.dut.needs_block_orientation:
                self.orient_for_block()

        serial_to_check = self.dut.scanned_serial_number        
        is_stable, device_info = self.at.confirm_device_enum(serial_number=serial_to_check)
        if not is_stable:
            self.session.log_failure(f"Device with serial {serial_to_check} did not enumerate correctly in OOB_MODE.")
        else:
            # Optional: You can now use the returned device_info object if needed.
            # For example, to update the DUT model with the most current info.
            if device_info:
                self._increment_enumeration_count('oob')
                self.dut.serial_number = device_info.iSerial
                # You could update other properties here as well if they can change
                self.logger.info(f"Successfully confirmed enumeration for S/N: {self.dut.serial_number}")

    def on_enter_USER_FORCED_ENROLLMENT(self,event_data: EventData) -> None:
        """
        Verifies the device state upon entering User-Forced Enrollment.

        This 'on_enter' callback confirms the device shows the correct
        green/blue LED pattern for User-Forced Enrollment mode.

        Args:
            event_data: The event data provided by the FSM.
        """
        self.logger.info(f"Confirming User-Forced Enrollment Mode (solid Green/Blue)...")
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        if self.at.confirm_led_solid(LEDs['GREEN_BLUE_STATE'], minimum=3.0, timeout=10.0, replay_extra_context=context):
            self.logger.info("Stable USER_FORCED_ENROLLMENT confirmed.")
        else:
            self.logger.error("Failed to confirm USER_FORCED_ENROLLMENT LEDs.")

    def on_enter_STANDBY_MODE(self, event_data: EventData) -> None:
        """
        Verifies the device state upon entering Standby Mode.

        This 'on_enter' callback confirms the device shows the stable solid
        red LED pattern, indicating it is configured, locked, and awaiting a
        PIN or command.

        Args:
            event_data: The event data provided by the FSM.
        """
        self.logger.info(f"Confirming Standby Mode (solid Red)...")
        # This callback uses the safe `on_enter` pattern, no change needed.
        context = {
            'fsm_current_state': self.source_state,
            'fsm_destination_state': self.state
        }
        if self.at.confirm_led_solid(LEDs['STANDBY_MODE'], minimum=2.5, timeout=15, replay_extra_context=context):
            self.logger.info("Stable STANDBY_MODE confirmed.")
        else:
            self.logger.error("Failed to confirm STANDBY_MODE LEDs.")

    def on_enter_UNLOCKED_ADMIN(self, event_data: EventData) -> None:
        """
        Verifies device enumeration after an admin unlock.

        This 'on_enter' callback is executed after successfully unlocking with
        an Admin PIN. It confirms that the device's storage volume has
        enumerated correctly on the host system.

        Args:
            event_data: The event data provided by the FSM.
        """
        serial_to_check = self.dut.scanned_serial_number
        is_stable, device_info = self.at.confirm_drive_enum(serial_number=serial_to_check)
        if not is_stable:
            self.session.log_failure(f"Device with serial {serial_to_check} did not enumerate correctly in UNLOCKED_ADMIN.")
        else:
            # Optional: You can now use the returned device_info object if needed.
            # For example, to update the DUT model with the most current info.
            if device_info:
                self._increment_enumeration_count('pin')
                self.dut.serial_number = device_info.iSerial
                if sys.platform.startswith('win32'):
                    self.dut.disk_path = device_info.physicalDriveNum
                elif sys.platform.startswith('linux'):
                    self.dut.disk_path = device_info.blockDevice
                # You could update other properties here as well if they can change
                self.logger.info(f"Successfully confirmed enumeration for S/N: {self.dut.serial_number}")

    def on_enter_UNLOCKED_USER(self, event_data: EventData) -> None:
        """
        Verifies device enumeration after a user unlock.

        This 'on_enter' callback is executed after successfully unlocking with
        a User PIN. It confirms that the device's storage volume has
        enumerated correctly on the host system.

        Args:
            event_data: The event data provided by the FSM.
        """
        serial_to_check = self.dut.scanned_serial_number
        is_stable, device_info = self.at.confirm_drive_enum(serial_number=serial_to_check)
        if not is_stable:
            self.session.log_failure(f"Device with serial {serial_to_check} did not enumerate correctly in UNLOCKED_USER.")
        else:
            # Optional: You can now use the returned device_info object if needed.
            # For example, to update the DUT model with the most current info.
            if device_info:
                self._increment_enumeration_count('pin')
                self.dut.serial_number = device_info.iSerial
                if sys.platform == 'win32':
                    self.dut.disk_path = device_info.physicalDriveNum
                elif sys.platform.startswith('linux'):
                    self.dut.disk_path = device_info.blockDevice
                # You could update other properties here as well if they can change
                self.logger.info(f"Successfully confirmed enumeration for S/N: {self.dut.serial_number}")

    def on_enter_UNLOCKED_RESET(self, event_data: EventData) -> None:
        """
        Verifies device enumeration after an reset unlock.

        This 'on_enter' callback is executed after successfully unlocking after
        a manufacturer reset. It confirms that the device's storage volume has
        enumerated correctly on the host system.

        Args:
            event_data: The event data provided by the FSM.
        """
        if not self.at.await_and_confirm_led_pattern(LEDs['ENUM'], timeout=15):
                self.session.log_failure("Failed Manufacturer Reset unlock LED pattern")
        
        serial_to_check = self.dut.scanned_serial_number        
        is_stable, device_info = self.at.confirm_drive_enum(serial_number=serial_to_check)
        if not is_stable:
            self.session.log_failure(f"Device with serial {serial_to_check} did not enumerate correctly in UNLOCKED_RESET.")
        else:
            # Optional: You can now use the returned device_info object if needed.
            # For example, to update the DUT model with the most current info.
            if device_info:
                self._increment_enumeration_count('mfr')
                self.dut.serial_number = device_info.iSerial
                if sys.platform.startswith('win32'):
                    self.dut.disk_path = device_info.physicalDriveNum
                elif sys.platform.startswith('linux'):
                    self.dut.disk_path = device_info.blockDevice
                # You could update other properties here as well if they can change
                self.logger.info(f"Successfully confirmed enumeration for S/N: {self.dut.serial_number}")

    def on_enter_BRUTE_FORCE(self, event_data: EventData) -> None:
        """
        Verifies the device state upon entering Brute Force protection mode.

        This 'on_enter' callback confirms that the device is displaying the
        correct LED pattern for brute force lockout.

        Args:
            event_data: The event data provided by the FSM.
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
        Verifies the device state upon entering Counter Enrollment mode.

        This 'on_enter' callback confirms the device is showing the red
        blinking pattern, indicating it is ready to accept numeric input
        for a counter setting (e.g., min PIN length).

        Args:
            event_data: The event data provided by the FSM.
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
        Verifies the device state upon entering PIN Enrollment mode.

        This 'on_enter' callback confirms the device is showing the correct
        LED pattern for the specific type of PIN being enrolled (e.g.,
        green/blue for User, red/blue for Self-Destruct).

        Args:
            event_data: The event data from the FSM, which includes the
                        trigger name to determine which PIN type is expected.

        Raises:
            TransitionCallbackError: If the expected LED pattern for the
                                     enrollment type is not observed.
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
                self.session.log_failure("Did not observe RED_BLUE pattern")
            else:
                self.logger.info("Awaiting PIN enrollment...")
        else:
            if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe GREEN_BLUE pattern for recovery enrollment")
            else:
                self.logger.info("Awaiting PIN enrollment...")

###########################################################################################################
# Before/After Functions (Automatic before entry to state)

##########
## Power

    @release_valve
    def _do_power_on(self, event_data: EventData) -> bool:
        """Handles the physical power-on sequence for the dut."""
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        # Use .get() with a default value to safely handle kwargs
        usb3 = event_data.kwargs.get('usb3', True)
        if not isinstance(usb3, bool):
            raise TransitionCallbackError("usb3 argument, if provided, must be a boolean")

        self.logger.info("Powering dut on and performing self-test...")
        if usb3:
            self.at.on("usb3")
        
        self.at.on("connect") # This will now be called correctly.
        time.sleep(0.5)
        
        if self.dut.battery:
            pass
        else:
            if not self.at.confirm_led_pattern(LEDs['RED_GREEN_BLUE'], clear_buffer=True, replay_extra_context=context):
                self.session.log_failure("Failed Startup Self-Test LED confirmation")
                return False
            self.logger.info("Startup Self-Test successful. Proceeding to POWER_ON_SELF_TEST state.")
        return True


    def _do_power_off(self, event_data: EventData) -> None:
        """Handles the physical power-off sequence for the dut."""
        self.logger.info("Powering off dut...")
        self.at.off("usb3")
        self.at.off("connect")

##########
## Unlocks

    @release_valve
    def _enter_admin_pin(self, event_data: EventData) -> bool:
        """
        Performs the sequence to unlock the device with the Admin PIN.

        This 'before' callback enters the stored Admin PIN and confirms the
        correct enumeration LED pattern based on the device's current
        configuration (e.g., read-only, lock-override).

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the expected unlock LED pattern is not
                                     observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        self.logger.info("Unlocking self.dut with Admin PIN...")
        self._sequence(self.dut.admin_pin)
        duration = 10
        if self.dut.read_only_enabled and self.dut.lock_override:
            pattern = 'ENUM_LOCK_OVERRIDE_READ_ONLY'
        elif self.dut.read_only_enabled:
            pattern = 'ENUM_READ_ONLY'
        elif self.dut.lock_override:
            pattern = 'ENUM_LOCK_OVERRIDE'
        else:
            pattern = 'ENUM_LEGACY'
            duration = 0
        time.sleep(duration)
        if not self.at.await_and_confirm_led_pattern(LEDs[pattern], timeout=15, replay_extra_context=context):
            self.session.log_failure("Failed Admin unlock LED pattern")
            return False
        return True
    
    @release_valve
    def _enter_self_destruct_pin(self, event_data: EventData) -> bool:
        """
        Performs the sequence to unlock the device with the Self-Destruct PIN.

        This 'before' callback enters the stored Self-Destruct PIN and confirms
        the correct enumeration LED pattern, which will trigger the device
        to wipe its data.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the expected unlock LED pattern is not
                                     observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        self.logger.info("Unlocking self.dut with Self-Destruct PIN...")
        self._sequence(self.dut.self_destruct_pin)
        duration = 10
        if self.dut.read_only_enabled and self.dut.lock_override:
            pattern = 'ENUM_LOCK_OVERRIDE_READ_ONLY'
        elif self.dut.read_only_enabled:
            pattern = 'ENUM_READ_ONLY'
        elif self.dut.lock_override:
            pattern = 'ENUM_LOCK_OVERRIDE'
        else:
            pattern = 'ENUM'
            duration = 0
        time.sleep(duration)
        if not self.at.await_and_confirm_led_pattern(LEDs[pattern], timeout=15, replay_extra_context=context):
            self.session.log_failure("Failed Self-Destruct unlock LED pattern")
            return False
        return True
    
    @release_valve
    def _enter_user_pin(self, event_data: EventData) -> bool:
        """
        Performs the sequence to unlock the device with a User PIN.

        This 'before' callback retrieves the PIN for the specified `user_id`,
        enters it, and confirms the correct enumeration LED pattern.

        Args:
            event_data: Event data from the FSM. Must contain a `user_id` in
                        its kwargs to identify which user PIN to use.

        Raises:
            TransitionCallbackError: If `user_id` is missing, invalid, or has
                                     no enrolled PIN, or if the expected unlock
                                     LED pattern is not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        user_id = event_data.kwargs.get('user_id')
        if not user_id:
            raise TransitionCallbackError("Unlock user requires a 'user_id' to be passed")
        if user_id not in self.dut.user_pin:
            raise TransitionCallbackError(f"Unlock failed: User ID {user_id} is not a valid slot for this device. Available slots: {list(self.dut.user_pin.keys())}")
        
        pin_to_enter = self.dut.user_pin.get(user_id)
        if not pin_to_enter:
            raise TransitionCallbackError(f"Unlock failed: No PIN is tracked for logical user {user_id}")

        self.logger.info(f"Attempting to unlock device with PIN from logical user slot {user_id}...")
        self._sequence(pin_to_enter)
        duration = 10
        if self.dut.read_only_enabled and self.dut.lock_override:
            pattern = 'ENUM_LOCK_OVERRIDE_READ_ONLY'
        elif self.dut.read_only_enabled:
            pattern = 'ENUM_READ_ONLY'
        elif self.dut.lock_override:
            pattern = 'ENUM_LOCK_OVERRIDE'
        else:
            pattern = 'ENUM_LEGACY'
            duration = 0
        time.sleep(duration)
        if not self.at.await_and_confirm_led_pattern(LEDs[pattern], timeout=15, replay_extra_context=context):
            self.session.log_failure(f"Failed User {user_id} unlock LED pattern")
            return False
        return True
    
##########
## Logins

    @release_valve
    def _enter_admin_mode_login(self, event_data: EventData) -> bool:
        """
        Performs the sequence to enter Admin configuration mode.

        This 'before' callback presses the required key combination, confirms
        the LED pattern indicating the device is ready for the admin PIN, and
        then enters the admin PIN.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the admin mode login LED pattern is
                                     not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        self._press(['key0', 'unlock'], duration_ms=6000)
        if not self.at.confirm_led_pattern(LEDs['RED_LOGIN'], clear_buffer=True, replay_extra_context=context):
            self.session.log_failure("Failed Admin Mode Login LED confirmation")
            return False
        self._sequence(self.dut.admin_pin)
        return True

    @release_valve
    def _enter_last_try_pin(self, event_data: EventData) -> bool:
        """
        Performs the special login sequence for the 'last try' from brute force.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the 'last try' login LED pattern is
                                     not observed.
        """
        self.logger.info(f"Entering Last Try Login...")
        self._press(['key5', 'unlock'], duration_ms=6000)
        if not self.at.await_and_confirm_led_pattern(LEDs["RED_GREEN"], timeout=10):
            self.session.log_failure("Failed 'LASTTRY' Login confirmation")
            return False
        self._sequence(['key5', 'key2', 'key7', 'key8', 'key8', 'key7', 'key9', 'unlock'])
        return True

##########
## Resets

    @release_valve
    def _do_user_reset(self, event_data: EventData) -> bool:
        """
        Performs a user reset (factory default) of the device.

        This 'before' callback initiates the reset sequence from Admin Mode,
        confirms the key generation LED pattern, and upon success, resets the
        self.dut model's state by clearing all PINs.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the reset confirmation LED pattern
                                     is not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        self.logger.info("Initiating User Reset...")
        if self.state == "ADMIN_MODE":
            self._sequence([["lock", "unlock", "key2"]], pause_duration_ms=100)
        else:
            self._on("lock")
            self._on("unlock")
            self._on("key2")
            if self.dut.battery:
                pattern = LEDs["USER_RESET_KEY"]
            else:
                pattern = LEDs["RED_BLUE"]
            user_reset_initiate = self.at.await_and_confirm_led_pattern(pattern, timeout=15, replay_extra_context=context)
            if not user_reset_initiate:
                self.at.off("lock", "unlock", "key2")
                self.session.log_failure("Failed to observe user reset initiation pattern")
                return False
        time.sleep(10)
        self.at.off("lock", "unlock", "key2")
        user_reset_pattern = self.at.confirm_led_solid(LEDs["KEY_GENERATION"], minimum=8, timeout=15, replay_extra_context=context)
        if not user_reset_pattern:
            self.session.log_failure("Failed to observe user reset confirmation pattern")
            return False
        
        self.dut._reset()
        self.logger.info("User reset confirmation pattern observed. Resetting self.dut model state...")
        self.dut.admin_pin = []
        self.dut.user_pin = {1: None, 2: None, 3: None, 4: None}
        self.logger.info("dut model state has been reset.")
        if self.orienting:
            self.at.on("connect")
        return True

    @release_valve
    def _do_manufacturer_reset(self, event_data: EventData) -> bool:
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        if self.state == 'FACTORY_MODE':
            self.logger.info("Initiating Configuration Manufacturer Reset...")
            self._sequence([["lock", "key2"], "key3", f"key{self.dut.hardware_id_1}", f"key{self.dut.hardware_id_2}", f"key{self.dut.model_id_1}", f"key{self.dut.model_id_2}"], pause_duration_ms=100)
            self._press("lock", duration_ms=6000)
        else:
            self.logger.info("Initiating Manufacturer Reset...")
            self._sequence([["lock", "key2"], "key3", "key8"], pause_duration_ms=200)
            time.sleep(.2)
            self._press("lock", duration_ms=6000)

        if not self.at.await_and_confirm_led_pattern(LEDs['RED_GREEN_BLUE'], timeout=7, clear_buffer=True, replay_extra_context=context):
            self.session.log_failure("Failed Reset Ready LED confirmation")
            return False
        
        portable = ["key1", "key2", "key3", "key4", "key5", "key6", "key7", "key8", "key9", "lock", "key0", "unlock"]
        secure_key = ["key1", "key2", "key3", "key4", "key5", "key6", "key7", "key8", "key9", "key0", "lock", "unlock"]
        if self.dut.secure_key:
                FIRST_KEY, LAST_KEY = secure_key[0], secure_key[-1]
                OTHER_KEYS = secure_key[1:-1]
        else:
            FIRST_KEY, LAST_KEY = portable[0], portable[-1]
            OTHER_KEYS = portable[1:-1]

        self.logger.info(f"Testing key: {FIRST_KEY}")
        self._on(FIRST_KEY)
        if not self.at.confirm_led_pattern(LEDs['FIRST_KEY_KEYPAD_TEST'], clear_buffer=False, replay_extra_context=context):      ## First key is special because of previous LED pattern, Reset Ready Mode
            self.at.off(FIRST_KEY)
            self.session.log_failure("Failed 'key1' confirmation")
            return False
        self.at.off(FIRST_KEY)
        self.at.confirm_led_solid(LEDs["ALL_OFF"], minimum=.15, timeout=1, clear_buffer=False, replay_extra_context=context)

        for key in OTHER_KEYS:
            self.logger.info(f"Testing key: {key}")
            self._on(key)
            if not self.at.await_led_state(LEDs['ACCEPT_STATE'], timeout=1, clear_buffer=False, replay_extra_context=context):
                self.at.off(key)
                self.session.log_failure(f"Failed '{key}' confirmation")
                return False
            self.at.off(key)
            self.at.confirm_led_solid(LEDs["ALL_OFF"], minimum=.15, timeout=1, clear_buffer=False, replay_extra_context=context)

        self.logger.info(f"Testing key: {LAST_KEY}")
        self._press(LAST_KEY)
        if not self.at.confirm_led_solid(LEDs['KEY_GENERATION'], minimum=2, timeout=5, replay_extra_context=context):
            self.session.log_failure("Failed Encryption Key confirmation")
            return False
        self.at.confirm_led_solid(LEDs['KEY_GENERATION'], minimum=6, timeout=15, replay_extra_context=context)
        self.dut._reset()
        return True


##########
## Miscellaneous
        
    def _press_lock_button(self, event_data: EventData) -> None:
        """
        Simulates pressing the physical lock button on the device.

        Args:
            event_data: The event data provided by the FSM.
        """
        self.logger.info(f"Locking self.dut from Unlocked Admin...")
        self._press("lock")

    def _enter_invalid_pin(self, event_data: EventData) -> bool:
        """
        Enters an invalid PIN and verifies the REJECT response.

        This action is used to decrement the brute force counter. It can use a
        guaranteed-invalid PIN by default, or accept a specific PIN (like a
        now-obsolete 'old' PIN) via the event_data kwargs. It confirms the
        device's reject pattern and decrements the `bruteForceCurrent`
        counter in the self.dut model.

        Args:
            event_data: The event data provided by the FSM. Can optionally
                        contain `pin` in its kwargs, which should
                        be a list of key strings (e.g., self.dut.old_admin_pin).

        Returns:
            True if the REJECT pattern was successfully observed, False otherwise.
        """
        # Define the default, guaranteed-wrong PIN sequence
        default_invalid_pin = ['key9', 'key9', 'key9', 'key9', 'key9', 'key9', 'key9', 'unlock']

        # Get the pin from the event kwargs. If the 'pin' kwarg is not
        # provided, it will automatically use the default_invalid_pin.
        pin_to_enter = event_data.kwargs.get('pin', default_invalid_pin)

        # Log differently based on which PIN is being used for clarity
        if pin_to_enter is default_invalid_pin:
            self.logger.info("Intentionally entering a guaranteed-invalid PIN...")
        else:
            self.logger.info("Intentionally entering a specific known-invalid PIN (e.g., an old PIN)...")

        # Perform the hardware sequence with the selected PIN
        self._sequence(pin_to_enter)

        # Confirm the device rejects the PIN
        if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5):
            self.logger.error("Device did not show REJECT pattern after invalid PIN entry.")
            return False

        # Decrement the brute force counter in the model
        if self.dut.brute_force_counter_current > 0:
            self.dut.brute_force_counter_current -= 1

        self.logger.info("Device correctly showed REJECT pattern.")
        return True
    
    def _timeout_pin_enrollment(self, event_data: EventData) -> None:
        """
        Handles the timeout case for PIN enrollment.

        This callback simulates waiting for the 30-second enrollment window to
        expire. It then checks for a REJECT pattern if a partial PIN was
        entered before the timeout.

        Args:
            event_data: Event data containing an optional boolean `pin_entered` kwarg.

        Raises:
            TransitionCallbackError: If the REJECT pattern is not observed
                                     after a timeout with a partial entry.
        """
        pin_entered = event_data.kwargs.get('pin_entered', False)
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info("Simulating 30-second PIN enrollment timeout...")
        time.sleep(30) # Simulate the timeout

        if pin_entered:
            self.logger.info("Partial PIN was entered before timeout, expecting REJECT pattern.")
            if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe REJECT for PIN enrollment timeout with partial entry")
        else:
            self.logger.info("No PIN was entered before timeout, no REJECT pattern expected.")

##########
## Admin mode Counter Enrollments

    def _brute_force_counter_enrollment(self, event_data: EventData) -> None:
        """
        Initiates the sequence to enroll a new brute force counter value.

        Args:
            event_data: The event data provided by the FSM.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Entering Brute Force Counter Enrollment...")
        self._press(['unlock', 'key5'], duration_ms=6000)

    def _min_pin_enrollment(self, event_data: EventData) -> None:
        """
        Initiates the sequence to enroll a new minimum PIN length.

        Args:
            event_data: The event data provided by the FSM.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        self.logger.info(f"Entering Minimum PIN Length Counter Enrollment...")
        self._press(['unlock', 'key4'], duration_ms=6000)

    def _unattended_auto_lock_enrollment(self, event_data: EventData) -> None:
        """
        Initiates the sequence to enroll a new unattended auto-lock timer value.

        Args:
            event_data: The event data provided by the FSM.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Entering Unattended Auto-Lock Enrollment...")
        self._press(['unlock', 'key6'], duration_ms=6000)

    def _counter_enrollment(self, event_data: EventData) -> None:
        """
        Enters a numeric value for a counter and confirms the result.

        This 'before' callback is triggered after initiating a counter
        enrollment. It enters the `new_counter` value provided in the event's
        kwargs, checks for the appropriate ACCEPT or REJECT pattern, and
        updates the self.dut model on success.

        Args:
            event_data: Event data containing the trigger name and a
                        `new_counter` value in its kwargs.

        Raises:
            TransitionCallbackError: If `new_counter` is missing or invalid,
                                     or if the hardware confirmation fails.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        trigger_name = event_data.event.name
        new_counter = event_data.kwargs.get('new_counter')

        if trigger_name == 'enroll_brute_force_counter':
            if not new_counter or not isinstance(new_counter, str):
                raise TransitionCallbackError("Brute Force Counter Enrollment requires a 'new_counter' str")
            if len(new_counter) != 2:
                raise TransitionCallbackError("Brute Force Counter Enrollment requires two-digits")
            
            BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACK = []
            for iteration in range(int(new_counter)):
                BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACK.append({'red':0, 'green':0, 'blue':0, 'duration': (0.00,  3.0)})
                BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACK.append({'red':0, 'green':1, 'blue':0, 'duration': (0.01,  1.0)})

            self._press(new_counter[0])
            self._press(new_counter[1])
            if int(new_counter) < 2 or int(new_counter) > 10:
                if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                    self.session.log_failure("Did not observe REJECT for invalid Brute Force Counter Enrollment value")
            else:
                if not self.at.await_and_confirm_led_pattern(BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACK, timeout=5.0, replay_extra_context=context):
                    self.session.log_failure("Did not observe BRUTE_FORCE_COUNTER_ENROLLMENT_FEEDBACKt pattern")
                
        elif trigger_name == 'enroll_min_pin_counter':
            if not new_counter or not isinstance(new_counter, str):
                raise TransitionCallbackError("Minimum PIN Length Enrollment requires a 'new_counter' str")
            if len(new_counter) != 2:
                raise TransitionCallbackError("Minimum PIN Length Enrollment requires two-digits")
            
            self._press(new_counter[0])
            self._press(new_counter[1])

            if int(new_counter) < self.dut.default_minimum_pin_counter or int(new_counter) > self.dut.maximum_pin_counter:
                if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                    self.session.log_failure("Did not observe REJECT for invalid Brute Force Counter Enrollment value")
            else:
                if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                    self.session.log_failure("Did not observe ACCEPT_PATTERN after Minimum PIN Length Counter Enrollment")
                
        elif trigger_name == 'enroll_unattended_auto_lock_counter':
            new_counter = event_data.kwargs.get('new_counter')
            if not new_counter or not isinstance(new_counter, int):
                raise TransitionCallbackError("Unattended Auto-Lock Enrollment requires a 'new_counter' integer")            
            if len(str(new_counter)) != 1:
                raise TransitionCallbackError("Unattended Auto-Lock Enrollment requires a single digit (0-3)")
            
            self._press(f"key{new_counter}")

            # Validate the input range. The condition is the inverse of the valid range (-1 < new_counter < 4).
            if new_counter < 0 or new_counter > 3:
                if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                    self.session.log_failure("Did not observe REJECT for invalid Unattended Auto-Lock value")
            else:
                if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                    self.session.log_failure("Did not observe ACCEPT_PATTERN for setting Auto-Lock to 0")
                else:
                    self.dut.unattended_auto_lock_counter = new_counter
                    self.logger.info(f"Unattended Auto-Lock new_counter set to: {new_counter}")

    def _timeout_counter_enrollment(self, event_data: EventData) -> None:
        """
        Handles the timeout case for counter enrollment.

        This callback simulates waiting for the 30-second enrollment window to
        expire. It then checks for a REJECT pattern if a partial PIN was
        entered before the timeout.

        Args:
            event_data: Event data containing a boolean `pin_entered` kwarg.

        Raises:
            TransitionCallbackError: If the REJECT pattern is not observed
                                     after a timeout with a partial entry.
        """
        pin_entered = event_data.kwargs.get('pin_entered')
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        if not pin_entered:
            time.sleep(30)
        else:
            time.sleep(30)
            if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe REJECT for counter enrollment timeout")

#################
## Admin mode PIN Enrollments

    def _admin_enrollment(self, event_data: EventData) -> None:
        """
        Initiates the sequence to enroll or change the Admin PIN.

        Args:
            event_data: The event data provided by the FSM.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Entering Admin PIN Enrollment...")
        self._press(['unlock', 'key9'])
        self.dut.pending_enrollment_type = 'admin'

    def _recovery_pin_enrollment(self, event_data: EventData) -> None:
        """
        Initiates the sequence to enroll a new Recovery PIN.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the initial green/blue LED pattern is
                                     not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self._press(['unlock', 'key7'])
        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            self.session.log_failure("Did not observe GREEN_BLUE pattern for recovery enrollment")
        self.dut.pending_enrollment_type = 'recovery'

    def _user_enrollment(self, event_data: EventData) -> None:
        """
        Initiates the sequence to enroll a new User PIN.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the initial green/blue LED pattern is
                                     not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        self._press(['unlock', 'key1'])
        if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
            self.session.log_failure("Did not observe GREEN_BLUE pattern for user enrollment")
        self.dut.pending_enrollment_type = 'user'

    def _self_destruct_pin_enrollment(self, event_data: EventData) -> None:
        """
        Initiates the sequence to enroll a new Self-Destruct PIN.

        This callback also checks if the self-destruct feature is enabled in
        the self.dut model; if not, it expects and confirms a REJECT pattern.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the self-destruct feature is disabled
                                     and the REJECT pattern is not seen, or if
                                     the feature is enabled and the enrollment
                                     fails.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        if not self.dut.self_destruct_enabled:
            self.logger.info(f"Attempting Self-Destruct PIN Enrollment without Self-Destruct enabled...")
            self._press(['key3', 'unlock'])
            if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe REJECT for Self-Destruct toggle with Provision Lock enabled")
        else:
            self.logger.info(f"Entering Self-Destruct PIN Enrollment...")
            self._press(['key3', 'unlock'])
            self.dut.pending_enrollment_type = 'self_destruct'

    def _pin_enrollment(self, event_data: EventData) -> None:
        """
        Enters a new PIN, confirms it, and verifies the device's response.

        This comprehensive 'before' callback handles the two-step entry process
        for all PIN types (Admin, User, Recovery, Self-Destruct). It enters
        the PIN, waits for the confirmation prompt, re-enters the PIN, and
        verifies the final accept/reject signal. On success, it updates the
        corresponding PIN in the self.dut model.

        Args:
            event_data: Event data containing the trigger name and a `new_pin`
                        list in its kwargs.

        Raises:
            TransitionCallbackError: If `new_pin` is missing/invalid, if any
                                     hardware confirmation step fails, or if
                                     enrollment is attempted when no slots
                                     are available.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        trigger_name = event_data.event.name
        new_pin = event_data.kwargs.get('new_pin')
        if not new_pin or not isinstance(new_pin, list):
            raise TransitionCallbackError("PIN enrollment requires a 'new_pin' list")
        
        enrollment_type = self.dut.pending_enrollment_type
        
        if enrollment_type == 'admin':
            self.logger.info(f"Entering new Admin PIN (first time)...")
            self._sequence(new_pin)
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe ACCEPT_PATTERN after first PIN entry")
            if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe GREEN_BLUE pattern after first PIN entry")

            self.logger.info("Re-entering Admin PIN for confirmation...")
            self._sequence(new_pin)
            if not self.at.await_led_state(LEDs['ACCEPT_STATE'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe ACCEPT_PATTERN after PIN confirmation")
            else:
                self.dut.admin_pin = new_pin
                self.logger.info("Admin enrollment sequence completed successfully. Updated self.dut model.")

        elif enrollment_type == 'recovery':
            next_available_slot = next((i for i in self.dut.recovery_pin.keys() if self.dut.recovery_pin.get(i) is None), None)
            if next_available_slot is None:
                if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                    self.session.log_failure("Did not observe REJECT on Recovery PIN Enrollment attempt when slots are full")
                self.logger.info(f"Enrollment failed as expected: All {len(self.dut.recovery_pin)} recovery slots are full")
                self.dut.pending_enrollment_type = None
                return

            # If the code reaches here, a slot is available.
            self.logger.info(f"Attempting to enroll new recovery PIN into logical slot #{next_available_slot}...")
            self.logger.info(f"Entering new Recovery PIN (first time)...")
            self._sequence(new_pin)
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe ACCEPT_PATTERN after first recovery PIN entry")
            if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe GREEN_BLUE pattern after first recovery PIN entry")

            self.logger.info("Re-entering Recovery PIN for confirmation...")
            self._sequence(new_pin)
            if not self.at.confirm_led_solid(LEDs["ACCEPT_STATE"], minimum=1, timeout=3, replay_extra_context=context):
                self.session.log_failure("Did not observe final ACCEPT_PATTERN for recovery PIN confirmation")

            self.dut.recovery_pin[next_available_slot] = new_pin
            self.logger.info(f"Successfully enrolled recovery PIN for logical slot {next_available_slot}.")

        elif enrollment_type == 'user':
            next_available_slot = next((i for i in self.dut.user_pin.keys() if self.dut.user_pin.get(i) is None), None)
            self.logger.info(f"Attempting to enroll new user into logical slot #{next_available_slot}...")
            if next_available_slot is None:
                if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                    self.session.log_failure("Did not observe REJECT on User PIN Enrollment entry")
                self.session.log_failure(f"Enrollment failed as expected: All {len(self.dut.user_pin)} user slots are full")
                self.dut.pending_enrollment_type = None
                return
            
            self.logger.info(f"Entering new User PIN (first time)...")
            self._sequence(new_pin)
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe ACCEPT_PATTERN after first user PIN entry")
            if not self.at.await_and_confirm_led_pattern(LEDs['GREEN_BLUE'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe GREEN_BLUE pattern after first user PIN entry")

            self.logger.info("Re-entering User PIN for confirmation...")
            self._sequence(new_pin)
            if not self.at.confirm_led_solid(LEDs["ACCEPT_STATE"], minimum=1, timeout=3, replay_extra_context=context):
                self.session.log_failure("Did not observe final ACCEPT_PATTERN for user PIN confirmation")
            
            self.dut.user_pin[next_available_slot] = new_pin
            self.logger.info(f"Successfully enrolled PIN for logical user {next_available_slot}.")

        elif enrollment_type == 'self_destruct':
            self.logger.info(f"Entering new Self-Destruct PIN (first time)...")
            self._sequence(new_pin)
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe ACCEPT_PATTERN after first PIN entry")
            if not self.at.await_and_confirm_led_pattern(LEDs['RED_BLUE'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe RED_BLUE pattern after first PIN entry")

            self.logger.info("Re-entering Self-Destruct PIN for confirmation...")
            self._sequence(new_pin)
            if not self.at.await_led_state(LEDs['ACCEPT_STATE'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe ACCEPT_PATTERN after PIN confirmation")
                
            self.dut.self_destruct_pin = new_pin
            self.logger.info("Self-Destruct enrollment sequence completed successfully. Updated self.dut model.")

        self.dut.pending_enrollment_type = None

    def enroll_admin_pin(self, new_pin_sequence: list):
        self.logger.info(f"--- Starting high-level admin PIN enrollment sequence... ---")
        valid_start_states = ['OOB_MODE', 'ADMIN_MODE']
        if self.state not in valid_start_states:
            raise RuntimeError(f"Cannot enroll admin PIN from state '{self.state}'. Must be in {valid_start_states}.")
        self.enroll_admin()
        self.enroll_pin(new_pin=new_pin_sequence)
        self.logger.info(f"--- High-level admin PIN enrollment sequence complete. ---")

    def enroll_user_pin(self, new_pin_sequence: list):
        """
        High-level convenience method to perform a full user PIN enrollment.

        Args:
            new_pin_sequence (list): The sequence of keys for the new user PIN.
        
        Raises:
            RuntimeError: If not in ADMIN_MODE or if no user slots are available.
        """
        self.logger.info(f"--- Starting high-level user PIN enrollment sequence... ---")
        if self.state != 'ADMIN_MODE':
            raise RuntimeError(f"Cannot enroll user PIN from state '{self.state}'. Must be in ADMIN_MODE.")

        # Check for an available slot before starting the FSM transition.
        if all(pin is not None for pin in self.dut.user_pin.values()):
            raise RuntimeError("No available user slots to enroll a new PIN.")

        self.enroll_user()
        self.enroll_pin(new_pin=new_pin_sequence)
        self.logger.info(f"--- High-level user PIN enrollment sequence complete. ---")

    def enroll_recovery_pin(self, new_pin_sequence: list):
        """
        High-level convenience method to perform a full recovery PIN enrollment.

        Args:
            new_pin_sequence (list): The sequence of keys for the new recovery PIN.
        
        Raises:
            RuntimeError: If not in ADMIN_MODE or if no recovery slots are available.
        """
        self.logger.info(f"--- Starting high-level recovery PIN enrollment sequence... ---")
        if self.state != 'ADMIN_MODE':
            raise RuntimeError(f"Cannot enroll recovery PIN from state '{self.state}'. Must be in ADMIN_MODE.")

        if all(pin is not None for pin in self.dut.recovery_pin.values()):
            raise RuntimeError("No available recovery slots to enroll a new PIN.")
        
        self.enroll_recovery()
        self.enroll_pin(new_pin=new_pin_sequence)
        self.logger.info(f"--- High-level recovery PIN enrollment sequence complete. ---")

    def enroll_self_destruct_pin(self, new_pin_sequence: list):
        """
        High-level convenience method to perform a full self-destruct PIN enrollment.

        Args:
            new_pin_sequence (list): The sequence of keys for the new self-destruct PIN.
        
        Raises:
            RuntimeError: If not in ADMIN_MODE.
        """
        self.logger.info(f"--- Starting high-level self-destruct PIN enrollment sequence... ---")
        if self.state != 'ADMIN_MODE':
            raise RuntimeError(f"Cannot enroll self-destruct PIN from state '{self.state}'. Must be in ADMIN_MODE.")
        
        # Note: The underlying _self_destruct_pin_enrollment FSM callback already
        # checks if the feature is enabled, so we don't need to repeat it here.
        
        self.enroll_self_destruct()
        self.enroll_pin(new_pin=new_pin_sequence)
        self.logger.info(f"--- High-level self-destruct PIN enrollment sequence complete. ---")

##################
## Admin mode Toggles

    def _basic_disk_toggle(self, event_data: EventData) -> None:
        """
        Toggles the device's basic disk mode.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the ACCEPT pattern is not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Toggling Basic Disk mode...")
        self._press(['key2', 'key3'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            self.session.log_failure("Did not observe ACCEPT_PATTERN for Basic Disk toggle")
        else:
            self.dut.basic_disk = True
            self.logger.info(f"Basic Disk mode: {self.dut.basic_disk}")

    def _removable_media_toggle(self, event_data: EventData) -> None:
        """
        Toggles the device's removable media mode.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the ACCEPT pattern is not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Toggling Removable Media mode...")
        self._press(['key3', 'key7'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            self.session.log_failure("Did not observe ACCEPT_PATTERN for Removable Media toggle")
        else:
            self.dut.removable_media = True
            self.logger.info(f"Removable Media mode: {self.dut.removable_media}")

    def _led_flicker_enable(self, event_data: EventData) -> None:
        """
        Enables the device's LED flicker mode.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the ACCEPT pattern is not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Enabling LED Flicker mode...")
        self._press(['key0', 'key3'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            self.session.log_failure("Did not observe ACCEPT_PATTERN for LED Flicker toggle")
        else:
            self.dut.led_flicker = True
            self.logger.info(f"LED Flicker mode: {self.dut.led_flicker}")

    def _led_flicker_disable(self, event_data: EventData) -> None:
        """
        Disables the device's LED flicker mode.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the ACCEPT pattern is not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Disabling LED Flicker Mode...")
        self._press(['key0', 'key3'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            self.session.log_failure("Did not observe ACCEPT_PATTERN for LED Flicker toggle")
        else:
            self.dut.led_flicker = False
            self.logger.info(f"LED Flicker mode: {self.dut.led_flicker}")

    def _lock_override_toggle(self, event_data: EventData) -> None:
        """
        Toggles the device's lock override feature.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the ACCEPT pattern is not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Toggling Lock Override mode...")
        self._press(['key0', 'key3'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            self.session.log_failure("Did not observe ACCEPT_PATTERN for Lock Override toggle")
        else:
            self.dut.lock_override = not self.dut.lock_override
            self.logger.info(f"LED Override mode: {self.dut.lock_override}")

    def _provision_lock_toggle(self, event_data: EventData) -> None:
        """
        Toggles the device's provision lock feature.

        This callback checks if self-destruct is enabled first, as these
        features are mutually exclusive.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the feature toggle fails.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        if self.dut.self_destruct_enabled:
            self.logger.info(f"Toggling Provision Lock with Self-Destruct enabled...")
            self._press(['key2', 'key5'])
            if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe REJECT for Provision Lock toggle with Self-Destruct enabled")
        else:
            self.logger.info(f"Toggling Provision Lock...")
            self._press(['key2', 'key5'])
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe ACCEPT_PATTERN for Provision Lock toggle")
            else:
                self.dut.provision_lock = not self.dut.provision_lock
                self.logger.info(f"Provision Lock mode: {self.dut.provision_lock}")

    def _read_only_toggle(self, event_data: EventData) -> None:
        """
        Toggles the device to read-only mode.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the ACCEPT pattern is not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Toggling Read-Only mode...")
        self._press(['key6', 'key7'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            self.session.log_failure("Did not observe ACCEPT_PATTERN for Read-Only toggle")
        else:
            self.dut.read_only_enabled = True
            self.logger.info(f"Read-Only mode: {self.dut.read_only_enabled}")

    def _read_write_toggle(self, event_data: EventData) -> None:
        """
        Toggles the device to read-write mode.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the ACCEPT pattern is not observed.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        self.logger.info(f"Toggling to Read-Write mode...")
        self._press(['key7', 'key9'])
        if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
            self.session.log_failure("Did not observe ACCEPT_PATTERN for Read-Write toggle")
        else:
            self.dut.read_only_enabled = False
            self.logger.info(f"Read-Write mode: {self.dut.read_only_enabled}")

    def _self_destruct_toggle(self, event_data: EventData) -> None:
        """
        Toggles the device's self-destruct feature.

        This callback checks if provision lock is enabled first, as these
        features are mutually exclusive.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the feature toggle fails.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}

        if self.dut.provision_lock:
            self.logger.info(f"Toggling Self-Destruct PIN with Provision Lock enabled...")
            self._press(['key4', 'key7'])
            if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe REJECT for Self-Destruct toggle with Provision Lock enabled")
        else:
            self.logger.info(f"Toggling Self-Destruct PIN...")
            self._press(['key4', 'key7'])
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe ACCEPT_PATTERN for Self-Destruct toggle")
            else:
                self.dut.self_destruct_enabled = True

    def _user_forced_enrollment_toggle(self, event_data: EventData) -> None:
        """
        Toggles the device's User-Forced Enrollment feature.

        This feature can only be enabled; it cannot be disabled via the same
        toggle. The callback confirms the correct ACCEPT or REJECT pattern.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If the feature toggle fails.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        if not self.dut.user_forced_enrollment:
            self.logger.info(f"Toggling User-Forced Enrollment...")
            self._press(['key0', 'key1'])
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe ACCEPT_PATTERN for User-Forced Enrollment toggle")
            else:
                self.dut.user_forced_enrollment = True
                self.logger.info(f"User-Forced Enrollment toggled. New state: {self.dut.user_forced_enrollment}")
        else:
            self.logger.info(f"Toggling User-Forced Enrollment with User-Forced Enrollment enabled...")
            self._press(['key0', 'key1'])
            if not self.at.await_and_confirm_led_pattern(LEDs['REJECT'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe REJECT for User-Forced Enrollment toggle")
            else:
                self.logger.info(f"User-Forced Enrollment cannot be disabled using this toggle...")

    def _delete_pins_toggle(self, event_data: EventData) -> None:
        """
        Performs the two-step sequence to delete all User and Recovery PINs.

        Args:
            event_data: The event data provided by the FSM.

        Raises:
            TransitionCallbackError: If any hardware confirmation step fails.
        """
        dest_state = event_data.transition.dest if event_data.transition else "UNKNOWN"
        context = {'fsm_current_state': self.state, 'fsm_destination_state': dest_state}
        
        if not self.dut.user_forced_enrollment:
            self.logger.info(f"Toggling Delete PINs...")
            self._press(['key7', 'key8'], duration_ms=6000)
            if not self.at.await_and_confirm_led_pattern(LEDs['ACCEPT_PATTERN'], timeout=5.0, replay_extra_context=context):
                self.session.log_failure("Did not observe ACCEPT_PATTERN for Delete PINs toggle")
            else:
                if not self.at.await_and_confirm_led_pattern(LEDs['RED_BLUE'], timeout=5.0, replay_extra_context=context):
                    self.session.log_failure("Did not observe RED_BLUE for Delete PINs initiation")
                else:
                    self._press(['key7', 'key8'], duration_ms=6000)
                    if not self.at.confirm_led_solid(LEDs["ACCEPT_STATE"], minimum=1, timeout=3, replay_extra_context=context):
                        self.session.log_failure("Did not observe final ACCEPT_PATTERN for recovery PIN confirmation")
                    else:
                        self.dut._delete_pins()
                        self.logger.info(f"Delete PINs toggled. PINs deleted...")

#################
## Verification of Toggled Behavior

    def format_operation(self) -> None:
        """
        Needs docstring
        """
        self.logger.info(f"Performing format operation...")
        disk_to_format = int(self.dut.disk_path)
        
        if not disk_to_format:
            self.logger.error("Cannot run format operation: DUT disk path is not set. Ensure the device is unlocked first.")
            return None

        self.logger.info(f"Initiating format operation on target: {disk_to_format}")
        results = self.at._format_disk(disk_to_format)
        
        if not results:
            if self.dut.read_only_enabled:
                self.logger.info(f"Read-Only prevented drive format")
            else:
                self.logger.info(f"DUT format failed")

#################
## Speed Test

    def speed_test(self) -> Optional[Dict[str, float]]:
        """
        Performs a standardized FIO speed test on the DUT's disk.

        This method retrieves the disk path from the DUT model and triggers
        the Unified Controller to execute the read/write tests. It handles
        potential errors like a missing disk path.

        Returns:
            A dictionary with 'read' and 'write' speeds in MB/s on success,
            or None on failure.
        """
        self.logger.info(f"Performing FIO Speed Test...")
        
        disk_to_test = self.dut.disk_path
        
        if not disk_to_test:
            self.logger.error("Cannot run speed test: DUT disk path is not set. Ensure the device is unlocked first.")
            return None

        self.logger.info(f"Initiating speed test on target: {disk_to_test}")
        results = self.at.run_fio_tests(disk_path=disk_to_test)
        
        if results:
            self.session.add_speed_test_result(results)

        return results
