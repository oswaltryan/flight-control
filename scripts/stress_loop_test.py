import sys
import os
import logging
from pprint import pprint
import random
import time

# --- Path Setup ---
SCRIPT_DIR_ENROLL = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_ENROLL = os.path.dirname(SCRIPT_DIR_ENROLL)
if PROJECT_ROOT_ENROLL not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_ENROLL)
# --- End Path Setup ---

# This try/except block is for when the script is run directly
try:
    from automation_toolkit import get_at_controller, get_dut, get_fsm, get_session, get_pin_generator
except Exception as e:
    logging.basicConfig(level=logging.CRITICAL)
    logging.critical(f"Failed to import or get controllers from automation_toolkit: {e}", exc_info=True)
    sys.exit("Critical error during setup. See logs.")

dut = get_dut()
fsm = get_fsm()
session = get_session()
pin_gen = get_pin_generator()
script_logger = logging.getLogger("stress_loop_testing")

session.script_num = 0
session.script_title = "Stress Loop Testing"

class StressTesting:
    def __init__(self):
        self.time_check: float = 0.0
        self.iteration: int = 0
        self.test_list: list = self._get_test_list()
        self.test_duration: float = self._get_test_duration()

        self.power_cycle_config: dict = self._get_power_cycle_config()
        self.speed_test_config: dict = self._get_speed_test_config()
        self.usb_2_config: dict = self._get_usb2_config()

    def _get_list_from_user(self, eligible_tests: list, prompt: str) -> list[int]:
        """A generic helper to get a list of tests from user input."""
        selected_list = []
        while True:
            raw = input(f"{prompt} from {eligible_tests} (space separated; blank = all eligible): ").strip()
            
            if not raw:
                return eligible_tests

            invalid = []
            selected_list.clear()
            for tok in raw.split():
                if tok.isdigit():
                    num = int(tok)
                    if num in eligible_tests and num not in selected_list:
                        selected_list.append(num)
                    else:
                        invalid.append(tok)
                else:
                    invalid.append(tok)
            
            if invalid:
                script_logger.warning(f"Invalid entries: {', '.join(invalid)} — must be in {eligible_tests}. Try again.")
                continue
            else:
                break
        return selected_list

    def _get_test_list(self) -> list[int]:
        """
        Prompts the user to select which test blocks to run.

        Displays a list of available tests and asks for a space-separated
        list of test IDs. It validates the input to ensure only available
        and valid numbers are selected. If the user provides no input, it
        defaults to running all available tests.

        Returns:
            A sorted list of integer test IDs to be executed.
        """
        tests = ["Admin PIN",
                 "Manufacturer Reset",
                 "User Reset",
                 "Power Cycle",
                 "Read-only"]
        options = list(range(len(tests)))

        script_logger.info("Available tests:")
        for name in tests:
            script_logger.info(f"                 {tests.index(name)}) {name}")

        while True:
            script_logger.info("")
            raw = input("Enter a list of tests (space separated). Leave blank to run all: ").strip()

            if not raw:
                selected = options.copy()
            else:
                tokens = raw.split()
                selected = []
                invalid = []
                for token in tokens:
                    if token.isdigit():
                        num = int(token)
                        if num in options and num not in selected:
                            selected.append(num)
                        else:
                            invalid.append(token)
                    else:
                        invalid.append(token)

                if invalid:
                    script_logger.warning(f"Invalid entries: {', '.join(invalid)} — please enter numbers 0-{len(tests)-1} only.")
                    script_logger.info(f"Invalid test IDs entered: {invalid}")
                    continue

            selected.sort()
            self.test_list = selected
            script_logger.info(f"Tests selected for execution: {self.test_list}")
            return self.test_list

    def _get_test_duration(self) -> float:
        """
        Prompts the user to enter the duration for each test block.

        The user is asked to provide a positive number representing the number
        of hours each selected test block should loop for. Input is validated
        to ensure it is a positive numeric value.

        Returns:
            The duration in hours (float) for each test block.
        """
        raw = ""
        while True:
            try:
                script_logger.info("")
                raw = input("Enter how many hours each test should loop (positive number): ").strip()

                value = float(raw)
                if value <= 0:
                    raise ValueError("Duration must be greater than zero.")

                self.test_duration = value
                script_logger.info(f"Duration of block execution: {self.test_duration}")
                return self.test_duration

            except ValueError as e:
                script_logger.warning(f"Invalid input: {e}. Please enter a positive numeric value.")
            except KeyboardInterrupt:
                script_logger.warning("User cancelled block duration input via KeyboardInterrupt.")
                raise

    def _get_power_cycle_config(self) -> dict:
        """
        Asks the user how power cycling should be handled for eligible tests.

        The user can choose 'Yes' to always power cycle, 'No' to never power
        cycle, or 'Random' to randomly decide on each iteration. If 'Yes' or
        'Random' is chosen, the user can specify which of the eligible tests
        this setting applies to. Test 3 (Power Cycle) is always excluded.

        Returns:
            A dictionary containing the 'mode' ('yes', 'no', 'random') and
            a 'list' of test IDs the mode applies to.
        """
        config = {'mode': 'no', 'list': []}
        valid_options = {'y', 'yes', 'n', 'no', 'r', 'random'}
        eligible_tests = [t for t in self.test_list if t != 3] # Power cycle is test 3

        if not eligible_tests:
            script_logger.info("No tests eligible for power cycling (Test 3 is excluded). Skipping.")
            return config

        while True:
            script_logger.info("")
            answer = input("Power-cycle between iterations? (Y/N/Random): ").strip().lower()

            if answer not in valid_options:
                script_logger.warning("Please answer Y, N, or Random.")
                continue
            
            if answer in {'n', 'no'}:
                config['mode'] = 'no'
                break
            
            # User said 'yes' or 'random'
            config['mode'] = 'random' if answer in {'r', 'random'} else 'yes'
            
            if len(eligible_tests) == 1:
                config['list'] = eligible_tests
            else:
                prompt_text = "Enter tests to RANDOMLY power cycle" if config['mode'] == 'random' else "Enter tests to ALWAYS power cycle"
                config['list'] = self._get_list_from_user(eligible_tests, prompt_text)
            
            break

        config['list'].sort()
        script_logger.info(f"Power Cycle Mode: '{config['mode']}'. Applied to tests: {config['list']}")
        return config
    
    def _get_speed_test_config(self) -> dict:
        """
        Asks the user how FIO speed tests should be handled for eligible tests.

        The user can choose 'Yes' to always run a speed test, 'No' to never
        run one, or 'Random' to randomly decide on each iteration. Tests that
        do not result in an unlocked data state (e.g., User Reset, Power Cycle)
        are excluded from eligibility.

        Returns:
            A dictionary containing the 'mode' ('yes', 'no', 'random') and
            a 'list' of test IDs the mode applies to.
        """
        config = {'mode': 'no', 'list': []}
        valid_options = {'y', 'yes', 'n', 'no', 'r', 'random'}
        eligible_tests = [t for t in self.test_list if t not in {2, 3}]

        if not eligible_tests:
            script_logger.info("No tests eligible for speed testing (Tests 2 & 3 are excluded). Skipping.")
            return config

        while True:
            script_logger.info("")
            answer = input("Execute a speed test in any blocks? (Y/N/Random): ").strip().lower()

            if answer not in valid_options:
                script_logger.warning("Please answer Y, N, or Random.")
                continue

            if answer in {'n', 'no'}:
                config['mode'] = 'no'
                break
            
            config['mode'] = 'random' if answer in {'r', 'random'} else 'yes'

            if len(eligible_tests) == 1:
                config['list'] = eligible_tests
            else:
                prompt_text = "Enter tests for RANDOM speed tests" if config['mode'] == 'random' else "Enter tests for ALWAYS speed tests"
                config['list'] = self._get_list_from_user(eligible_tests, prompt_text)
                
            break
        
        config['list'].sort()
        script_logger.info(f"Speed Test Mode: '{config['mode']}'. Applied to tests: {config['list']}")
        return config
    
    def _get_usb2_config(self) -> dict:
        """
        Asks the user how USB protocol selection should be handled.

        The user can choose 'Yes' to force USB2, 'No' to force USB3 (default),
        or 'Random' to randomly decide the protocol for each power-on event.
        The user can specify which of the selected test blocks this setting
        applies to.

        Returns:
            A dictionary containing the 'mode' ('yes', 'no', 'random') and
            a 'list' of test IDs the mode applies to.
        """
        config = {'mode': 'no', 'list': []}
        valid_options = {'y', 'yes', 'n', 'no', 'r', 'random'}
        eligible_tests = self.test_list

        while True:
            script_logger.info("")
            answer = input("Execute any blocks with USB2 testing? (Y/N/Random): ").strip().lower()

            if answer not in valid_options:
                script_logger.warning("Please answer Y, N, or Random.")
                continue

            if answer in {'n', 'no'}:
                config['mode'] = 'no'
                break
            
            config['mode'] = 'random' if answer in {'r', 'random'} else 'yes'

            if len(eligible_tests) == 1:
                config['list'] = eligible_tests
            else:
                prompt_text = "Enter tests for RANDOM USB2 testing" if config['mode'] == 'random' else "Enter tests for ALWAYS USB2 testing"
                config['list'] = self._get_list_from_user(eligible_tests, prompt_text)
            
            break
        
        config['list'].sort()
        script_logger.info(f"USB2 Mode: '{config['mode']}'. Applied to tests: {config['list']}")
        script_logger.info("")
        return config

    def should_run_action(self, test_id: int, config: dict) -> bool:
        """
        Determines if an action should run based on its configuration.
        
        Args:
            test_id: The ID of the current test block.
            config: The configuration dictionary (e.g., self.power_cycle_config).
            
        Returns:
            True if the action should run for this iteration.
        """
        if test_id not in config['list']:
            return False
            
        if config['mode'] == 'yes':
            return True
            
        if config['mode'] == 'random':
            return random.choice([True, False])
            
        return False

    def setUSBProtocol(self, test_id: int) -> bool:
        """
        Determines the USB protocol for the current iteration.
        Returns True for USB3, False for USB2.
        """
        # should_run_action will be True if mode is 'yes' or randomly 'random'
        if self.should_run_action(test_id, self.usb_2_config):
            return False # Use USB2
        return True # Default to USB3

    def timeComparison(self, current_time: float) -> float:
        """Return elapsed time since blockStart in hours, rounded to 2 decimals."""
        return round((current_time - session.block_start_time) / 3600, 2)

    
def block_0():
    """
    Executes a stress test on the Admin PIN functionality.

    Test Flow:
    1. Powers on the device and enrolls a new random Admin PIN.
    2. Enters a loop for the specified duration.
    3. In each iteration, it unlocks the device with the Admin PIN to verify
       data access, and then locks it again.
    4. Optionally runs a speed test while unlocked.
    5. Optionally power-cycles the device between iterations.
    6. After the loop, it performs a user reset to clean the device for the next block.
    """
    test_id = 0
    block_title = 'Admin PIN Unlock'
    if test_id in loop_test.test_list:
        session.start_new_block(block_name=block_title, current_test_block=test_id)
        
        # Determine initial USB protocol based on user/random settings
        is_usb3_initial = loop_test.setUSBProtocol(test_id)
        
        # --- Initial Setup for the Block ---
        script_logger.info(f"Setting up Block {test_id} ({block_title})...")
        fsm.power_on(usb3=is_usb3_initial)
        admin_pin = pin_gen.generate_valid_pin(dut.minimum_pin_counter)
        fsm.enroll_admin_pin(new_pin_sequence=admin_pin['sequence'])
        fsm.lock_admin()
        
        # --- Main Test Loop ---
        loop_test.time_check = loop_test.timeComparison(time.time())
        loop_test.iteration = 0
        while loop_test.time_check < loop_test.test_duration:
            loop_test.iteration += 1
            script_logger.info(f"Beginning iteration {loop_test.iteration}: (Block {session.current_test_block}) (({loop_test.time_check:.2f}h of {loop_test.test_duration}h))")
            
            fsm.unlock_admin()

            if loop_test.should_run_action(test_id, loop_test.speed_test_config):
                script_logger.info(f"ITERATION {loop_test.iteration}: Running speed test.")
                fsm.speed_test()
            
            fsm.lock_admin()

            if loop_test.should_run_action(test_id, loop_test.power_cycle_config):
                script_logger.info(f"ITERATION {loop_test.iteration}: Power cycling.")
                fsm.power_off()
                is_usb3_cycle = loop_test.setUSBProtocol(test_id)
                fsm.power_on(usb3=is_usb3_cycle)
                
            loop_test.time_check = loop_test.timeComparison(time.time())
        
        # --- Block Teardown ---
        fsm.user_reset()
        fsm.power_off()
        script_logger.info("")
        script_logger.info(f"Block {test_id} complete after {loop_test.iteration} iteration(s).")
        session.end_block()

def block_1():
    """
    Executes a stress test on the Manufacturer Reset functionality.

    Test Flow:
    1. Powers on the device.
    2. Enters a loop for the specified duration.
    3. In each iteration, it performs a full Manufacturer Reset, which includes
       a hardware keypad test and key generation.
    4. Optionally runs a speed test after the reset.
    5. Locks the device, returning it to OOB (Out-of-Box) mode.
    6. Optionally power-cycles the device between iterations.
    """
    test_id = 1
    block_title = 'Manufacturer Reset'
    if test_id in loop_test.test_list:
        session.start_new_block(block_name=block_title, current_test_block=test_id)

        # --- Initial Setup ---
        script_logger.info(f"Setting up Block {test_id} ({block_title})...")
        is_usb3_initial = loop_test.setUSBProtocol(test_id)
        fsm.power_on(usb3=is_usb3_initial)
        
        # --- Main Test Loop ---
        loop_test.time_check = loop_test.timeComparison(time.time())
        loop_test.iteration = 0
        while loop_test.time_check < loop_test.test_duration:
            loop_test.iteration += 1
            script_logger.info(f"Beginning iteration {loop_test.iteration}: (Block {session.current_test_block}) (({loop_test.time_check:.2f}h of {loop_test.test_duration}h))")
            
            fsm.manufacturer_reset()

            if loop_test.should_run_action(test_id, loop_test.speed_test_config):
                script_logger.info(f"ITERATION {loop_test.iteration}: Running speed test.")
                fsm.speed_test()
                
            fsm.lock_reset()

            if loop_test.should_run_action(test_id, loop_test.power_cycle_config):
                script_logger.info(f"ITERATION {loop_test.iteration}: Power cycling.")
                fsm.power_off()
                is_usb3_cycle = loop_test.setUSBProtocol(test_id)
                fsm.power_on(usb3=is_usb3_cycle)
            
            loop_test.time_check = loop_test.timeComparison(time.time())
            
        # --- Block Teardown ---
        fsm.power_off()
        script_logger.info("")
        script_logger.info(f"Block {test_id} complete after {loop_test.iteration} iteration(s).")
        session.end_block()

def block_2():
    """
    Executes a stress test on the User Reset (Factory Default) functionality.

    Test Flow:
    1. Powers on the device.
    2. Enters a loop for the specified duration.
    3. In each iteration, it must first enroll an Admin PIN (as user reset
       requires being in Admin Mode), and then immediately performs the user reset.
    4. The device is now in OOB mode, ready for the next loop.
    5. Optionally power-cycles the device between iterations.
    """
    test_id = 2
    block_title = 'User Reset'
    if test_id in loop_test.test_list:
        session.start_new_block(block_name=block_title, current_test_block=test_id)

        # --- Initial Setup ---
        script_logger.info(f"Setting up Block {test_id} ({block_title})...")
        is_usb3_initial = loop_test.setUSBProtocol(test_id)
        fsm.power_on(usb3=is_usb3_initial)
        
        # --- Main Test Loop ---
        loop_test.time_check = loop_test.timeComparison(time.time())
        loop_test.iteration = 0
        while loop_test.time_check < loop_test.test_duration:
            loop_test.iteration += 1
            script_logger.info(f"Beginning iteration {loop_test.iteration}: (Block {session.current_test_block}) (({loop_test.time_check:.2f}h of {loop_test.test_duration}h))")
            
            # User Reset requires being in Admin Mode. The device starts in OOB mode after the last reset.
            admin_pin = pin_gen.generate_valid_pin(dut.minimum_pin_counter)
            fsm.enroll_admin_pin(new_pin_sequence=admin_pin['sequence'])
            fsm.user_reset()
            # After a user reset, we are back in OOB mode, ready for the next iteration.

            if loop_test.should_run_action(test_id, loop_test.power_cycle_config):
                script_logger.info(f"ITERATION {loop_test.iteration}: Power cycling.")
                fsm.power_off()
                is_usb3_cycle = loop_test.setUSBProtocol(test_id)
                fsm.power_on(usb3=is_usb3_cycle)

            loop_test.time_check = loop_test.timeComparison(time.time())

        # --- Block Teardown ---
        fsm.power_off()
        script_logger.info("")
        script_logger.info(f"Block {test_id} complete after {loop_test.iteration} iteration(s).")
        session.end_block()

def block_3():
    """
    Executes a simple power cycle stress test.

    Test Flow:
    1. Enters a loop for the specified duration.
    2. In each iteration, it simply powers the device on and then immediately
       powers it off.
    3. This test is designed to stress the power-on and POST logic of the device.
    4. USB protocol (2.0 vs 3.0) can be randomized for each cycle.
    """
    test_id = 3
    block_title = 'Power Cycle'
    if test_id in loop_test.test_list:
        session.start_new_block(block_name=block_title, current_test_block=test_id)

        # --- Initial Setup ---
        script_logger.info(f"Setting up Block {test_id} ({block_title})...")
        # No device setup needed for this block.
        
        # --- Main Test Loop ---
        loop_test.time_check = loop_test.timeComparison(time.time())
        loop_test.iteration = 0
        while loop_test.time_check < loop_test.test_duration:
            loop_test.iteration += 1
            script_logger.info(f"Beginning iteration {loop_test.iteration}: (Block {session.current_test_block}) (({loop_test.time_check:.2f}h of {loop_test.test_duration}h))")

            # The entire test is just the power cycle. USB protocol is decided each time.
            is_usb3_cycle = loop_test.setUSBProtocol(test_id)
            fsm.power_on(usb3=is_usb3_cycle)
            fsm.power_off()
            
            loop_test.time_check = loop_test.timeComparison(time.time())

        # --- Block Teardown ---
        script_logger.info("")
        script_logger.info(f"Block {test_id} complete after {loop_test.iteration} iteration(s).")
        session.end_block()

def block_4():
    """
    Executes a stress test on the read-only functionality.

    Test Flow:
    1. Powers on the device and enrolls a new random Admin PIN.
    2. Enters a loop for the specified duration.
    3. In each iteration, it unlocks the device with the Admin PIN and performs
       a format operation to verify read-only, and then locks it again.
    4. Optionally power-cycles the device between iterations.
    5. After the loop, it performs a user reset to clean the device for the next block.
    """
    test_id = 4
    block_title = 'Read-Only'
    if test_id in loop_test.test_list:
        session.start_new_block(block_name=block_title, current_test_block=test_id)
        
        # Determine initial USB protocol based on user/random settings
        is_usb3_initial = loop_test.setUSBProtocol(test_id)
        
        # --- Initial Setup for the Block ---
        script_logger.info(f"Setting up Block {test_id} ({block_title})...")
        fsm.power_on(usb3=is_usb3_initial)
        admin_pin = pin_gen.generate_valid_pin(dut.minimum_pin_counter)
        fsm.enroll_admin_pin(new_pin_sequence=admin_pin['sequence'])
        fsm.toggle_read_only()
        fsm.lock_admin()
        
        # --- Main Test Loop ---
        loop_test.time_check = loop_test.timeComparison(time.time())
        loop_test.iteration = 0
        while loop_test.time_check < loop_test.test_duration:
            loop_test.iteration += 1
            script_logger.info(f"Beginning iteration {loop_test.iteration}: (Block {session.current_test_block}) (({loop_test.time_check:.2f}h of {loop_test.test_duration}h))")
            
            fsm.unlock_admin()
            fsm.format_operation()

            if loop_test.should_run_action(test_id, loop_test.speed_test_config):
                script_logger.info(f"ITERATION {loop_test.iteration}: Running speed test.")
                fsm.speed_test()
            
            fsm.lock_admin()

            if loop_test.should_run_action(test_id, loop_test.power_cycle_config):
                script_logger.info(f"ITERATION {loop_test.iteration}: Power cycling.")
                fsm.power_off()
                is_usb3_cycle = loop_test.setUSBProtocol(test_id)
                fsm.power_on(usb3=is_usb3_cycle)
                
            loop_test.time_check = loop_test.timeComparison(time.time())
        
        # --- Block Teardown ---
        fsm.user_reset()
        fsm.power_off()
        script_logger.info("")
        script_logger.info(f"Block {test_id} complete after {loop_test.iteration} iteration(s).")
        session.end_block()

# Start Script ------------------------------------------------------------------- #
# Execute Block Testing ---------------- #

loop_test = StressTesting()

functions = [block_0, block_1, block_2, block_3, block_4]
for func in functions:
    func()

session.generate_summary_report()