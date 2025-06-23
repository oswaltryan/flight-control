import sys
import os
import logging
from pprint import pprint
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
        self.timeCheck: float = 0.0
        self.iteration: int = 0 
        self.testList: list = self.userInputTestList()
        self.usb2TestList: list = self.testListUSBInquiry()
        self.loopTimer: float = self.userInputBlockDuration()
        self.powerCycleList: list = self.powerCycleInquiry()
        self.speedTestList: list = self.speedTestInquiry()

    def timeComparison(self, current_time: float) -> float:
        """Return elapsed time since blockStart in hours, rounded to 2 decimals."""
        return round((current_time - session.block_start_time) / 3600, 2)

    def userInputTestList(self) -> list[int]:
        options = list(range(6))  # valid IDs 0–5

        script_logger.info("Available tests:")
        script_logger.info("                 0) Admin PIN")
        script_logger.info("                 1) Read-Only/Read-Write")
        script_logger.info("                 2) Manufacturer Reset")
        script_logger.info("                 3) User Reset")
        script_logger.info("                 4) Power Cycle")
        script_logger.info("                 5) Disk Integrity")

        while True:
            script_logger.info("")
            raw = input("Enter a list of tests (space separated). Leave blank to run all: ").strip()
            script_logger.info("")

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
                    script_logger.warning(f"Invalid entries: {', '.join(invalid)} — please enter numbers 0–5 only.")
                    script_logger.info(f"Invalid test IDs entered: {invalid}")
                    continue

            selected.sort()
            self.testList = selected
            script_logger.info(f"Tests selected for execution: {self.testList}")
            return self.testList

    def testListUSBInquiry(self) -> list[int]:
        usb2_list: list[int] = []
        acceptable = {'y', 'yes', 'n', 'no'}

        while True:
            script_logger.info("")
            answer = input("Should any of the blocks execute USB2 testing? (Y/N): ").strip().lower()

            if answer not in acceptable:
                script_logger.warning("Please answer Y or N.")
                continue

            if answer in {'n', 'no'}:
                return usb2_list

            # User said yes
            script_logger.info("")
            raw = input("Enter tests for USB2 (space separated, blank = all): ").strip()

            if not raw:
                usb2_list = self.testList.copy()
                break

            tokens = raw.split()
            invalid = []
            for tok in tokens:
                if tok.isdigit():
                    num = int(tok)
                    if num in self.testList and num not in usb2_list:
                        usb2_list.append(num)
                    else:
                        invalid.append(tok)
                else:
                    invalid.append(tok)

            if invalid:
                script_logger.warning(f"Invalid test IDs: {', '.join(invalid)} — must be numeric and in {self.testList}. Try again.")
                script_logger.info(f"Invalid USB2 test entries: {invalid}")
                usb2_list.clear()
                continue

            break

        usb2_list.sort()
        # script_logger.info(f"USB2 will run for tests: {usb2_list}\n")
        return usb2_list

    def userInputBlockDuration(self) -> float:
        raw = ""
        while True:
            try:
                script_logger.info("")
                raw = input("Enter how many hours each test should loop (positive number): ").strip()

                value = float(raw)
                if value <= 0:
                    raise ValueError("Duration must be greater than zero.")

                self.loopTimer = value
                return self.loopTimer

            except ValueError as e:
                script_logger.warning(f"Invalid input: {e}. Please enter a positive numeric value.")
            except KeyboardInterrupt:
                script_logger.warning("User cancelled block duration input via KeyboardInterrupt.")
                raise

    def powerCycleInquiry(self) -> list[int]:
        power_cycle: list[int] = []
        valid_yes_no = {'y', 'yes', 'n', 'no'}

        while True:
            script_logger.info("")
            answer = input("Should the device be power‑cycled between iterations? (Y/N): ").strip().lower()

            if answer not in valid_yes_no:
                script_logger.warning("Please answer Y or N.")
                continue

            if answer in {'n', 'no'}:
                return []

            # User said yes
            if len(self.testList) == 1:
                script_logger.info(f"Power cycle enabled for test: {self.testList}")
                return self.testList.copy()

            while True:
                raw = input("Enter tests to power cycle (space separated; blank = all): ").strip()

                if not raw:
                    power_cycle = self.testList.copy()
                    break

                invalid = []
                for tok in raw.split():
                    if tok.isdigit():
                        num = int(tok)
                        if num in self.testList and num not in power_cycle:
                            power_cycle.append(num)
                        else:
                            invalid.append(tok)
                    else:
                        invalid.append(tok)

                if invalid:
                    script_logger.warning(f"Invalid entries: {', '.join(invalid)} — must be in {self.testList}. Try again.")
                    power_cycle.clear()
                    continue
                else:
                    break
            break

        power_cycle.sort()
        script_logger.info(f"Power cycle enabled for tests: {power_cycle}")
        return power_cycle
   
    def speedTestInquiry(self) -> list[int]:
        speed_tests: list[int] = []
        valid_yes_no = {'y', 'yes', 'n', 'no'}

        while True:
            script_logger.info("")
            answer = input("Should any of the blocks execute a speed test? (Y/N): ").strip().lower()
            script_logger.info("")
            # script_logger.info(f"Should any of the blocks execute a speed test? {answer}\n")

            if answer not in valid_yes_no:
                script_logger.warning("Please answer Y or N.")
                continue

            if answer in {'n', 'no'}:
                return []

            # User said yes
            if len(self.testList) == 1:
                self.speedTestList = self.testList.copy()
                # script_logger.info(f"Speed test enabled for tests: {self.speedTestList}\n")
                return self.speedTestList

            raw = input("Enter tests for speed test (space separated; blank = all applicable): ").strip()
            script_logger.info("")

            if not raw:
                speed_tests = [t for t in self.testList if t not in {3, 4}]
            else:
                invalid = []
                for tok in raw.split():
                    if tok.isdigit():
                        num = int(tok)
                        if num in self.testList and num not in speed_tests:
                            speed_tests.append(num)
                        else:
                            invalid.append(tok)
                    else:
                        invalid.append(tok)

                if invalid:
                    script_logger.warning(f"Invalid entries: {', '.join(invalid)} — must be numeric and in {self.testList}. Try again.")
                    script_logger.warning(f"Invalid speed test entries: {invalid}")
                    speed_tests.clear()
                    continue

            speed_tests.sort()
            script_logger.info(f"Speed test enabled for tests: {speed_tests}")
            return speed_tests

    def setUSBProtocol(self) -> bool:
        """Use USB3 (True) unless current test block is in the USB2 list."""
        return session.current_test_block in self.usb2TestList
    


def block_0():
    if 0 in loop_test.testList:

        session.start_new_block(block_name='pin_unlock')
        usbProtocol = loop_test.setUSBProtocol()

        loop_test.timeCheck = 0.0
        iteration = 0            
        fsm.power_on(usb3=usbProtocol)
        admin_pin = pin_gen.generate_valid_pin(dut.minimum_pin_counter)
        fsm.enroll_admin_pin(new_pin_sequence=admin_pin['sequence'])
        fsm.lock_admin()
        loop_test.timeCheck = loop_test.timeComparison(time.time())
        while loop_test.timeCheck < loop_test.loopTimer:
            iteration += 1
            script_logger.info(f"Beginning iteration {iteration}: (Block {session.current_test_block}) (({loop_test.timeCheck}h of {loop_test.loopTimer}h))")
            fsm.unlock_admin()
            if 0 in loop_test.speedTestList:
                # speedTest()
                pass
            fsm.lock_admin()
            if 0 in loop_test.powerCycleList:
                fsm.power_off()
                fsm.power_on(usb3=usbProtocol)
                pass
            loop_test.timeCheck = loop_test.timeComparison(time.time())
        else:
            fsm.user_reset()
            fsm.power_off(forceOff=True)
            script_logger.info("")
            script_logger.info(f"{iteration} loop(s) completed")
            script_logger.info("")

        session.end_block()

    else:
        pass


# Start Script ------------------------------------------------------------------- #
# Execute Block Testing ---------------- #

loop_test = StressTesting()

functions = [block_0]
try:
    for func in functions:
        try:
            func()
        except Exception as e:
            print(e)
            script_logger.warning(f"{session.script_title}, Block {func.__name__[-1]} failed. Skipping to the next function.")
        except KeyboardInterrupt:
            session.end_block()
finally:
    session.generate_summary_report()