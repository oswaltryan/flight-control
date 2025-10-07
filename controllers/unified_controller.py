# Directory: controllers
# Filename: unified_controller.py

#!/usr/bin/env python3

import json
import logging
import sys
import os
import time 
from typing import Optional, List, Dict, Any, Union, Tuple, TYPE_CHECKING
import threading
from pprint import pprint
import subprocess
import copy

# --- Path Setup ---
CONTROLLERS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CONTROLLERS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

module_logger = logging.getLogger(__name__)

try:
    from controllers.phidget_board import PhidgetController, DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG
    from controllers.logitech_webcam import (
        LogitechLedChecker, 
        DEFAULT_DURATION_TOLERANCE_SEC as CAMERA_DEFAULT_TOLERANCE,
        DEFAULT_REPLAY_POST_FAIL_DURATION_SEC as CAMERA_DEFAULT_REPLAY_DURATION, 
    )
    from controllers.barcode_scanner import BarcodeScanner
    from Phidget22.PhidgetException import PhidgetException
    if TYPE_CHECKING: # pragma: no cover
        from controllers.finite_state_machine import DeviceUnderTest
    from utils.led_states import LEDs
    from utils.config.keypad_layouts import KEYPAD_LAYOUTS
    from usb_tool import find_apricorn_device
    from transitions import EventData
except ImportError as e_import:
    module_logger.critical(f"Critical Import Error in unified_controller.py: {e_import}. Check paths and dependencies.", exc_info=True)
    raise

# --- Custom Exception for 'pre-flight' Failures ---
class LaunchError(Exception):
    """Custom exception to be raised from 'before' callbacks on failure."""
    pass


class UnifiedController:
    _phidget_controller: Optional[PhidgetController]
    _camera_checker: Optional[LogitechLedChecker]
    _barcode_scanner: Optional[BarcodeScanner]
    logger: logging.Logger
    phidget_config_to_use: Dict[str, Any]
    effective_led_duration_tolerance: float
    scanned_serial_number: Optional[str]
    # ADDED: For type hinting, declare that this class will have a 'dut' attribute.
    dut: Optional['DeviceUnderTest']

    def __init__(self,
                 script_map_config: Optional[Dict[str, Any]] = None,
                 camera_id: int = 0,
                 led_configs: Optional[Dict[str, Any]] = None,
                 display_order: Optional[List[str]] = None,
                 logger_instance: Optional[logging.Logger] = None,
                 led_duration_tolerance_sec: Optional[float] = None,
                 replay_post_failure_duration_sec: Optional[float] = None,
                 replay_output_dir: Optional[str] = None,
                 enable_instant_replay: Optional[bool] = None,
                 skip_initial_scan: bool = False,
                 scan_retry_delay_sec: Optional[float] = None):
        self.logger = logger_instance if logger_instance else module_logger
        
        self._phidget_controller: Optional[PhidgetController] = None
        self._camera_checker: Optional[LogitechLedChecker] = None
        self._barcode_scanner: Optional[BarcodeScanner] = None
        self.scanned_serial_number: Optional[str] = None
        self.dut: Optional['DeviceUnderTest'] = None
        self.is_fully_initialized: bool = False
        self._keypad_layout: Optional[List[List[str]]] = None
        # Control retry delay for barcode scanning (useful for tests)
        try:
            env_delay = float(os.environ.get("SCAN_RETRY_DELAY_SEC", "3"))
        except ValueError:
            env_delay = 3.0
        self.scan_retry_delay_sec: float = (
            float(scan_retry_delay_sec)
            if scan_retry_delay_sec is not None
            else env_delay
        )

        phidget_init_successful = False
        camera_init_successful = False

        # --- Initialize Phidget FIRST ---
        try:
            self._phidget_controller = PhidgetController(
                script_map_config=script_map_config or DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG,
                logger_instance=self.logger.getChild("Phidget")
            )
            phidget_init_successful = True
        except Exception as e_phidget_init:
            self.logger.error(f"Failed to initialize PhidgetController: {e_phidget_init}", exc_info=True)

        # --- Initialize Barcode Scanner ---
        self._barcode_scanner = BarcodeScanner(phidget_press_callback=self.press)

        # --- [MODIFIED] Build Dynamic LED & Camera Configs FIRST ---
        from .logitech_webcam import load_all_camera_settings, PRIMARY_LED_CONFIGURATIONS, ROI_SIZE_SECURE_KEYPAD, ROI_SIZE_STANDARD_KEYPAD
        
        camera_settings_to_apply, roi_positions, target_device_name, battery_present = load_all_camera_settings()
        self.logger.debug(f"Loaded target device profile from config: '{target_device_name}'")

        # --- Initialize DUT to determine hardware properties ---
        try:
            from controllers.finite_state_machine import DeviceUnderTest

            dut_kwargs = {
                'at_controller': self,
                'target_device_profile': target_device_name,
                'power': battery_present 
            }
            if skip_initial_scan:
                self.logger.info("DUT initialization requested to skip initial barcode scan.")
                dut_kwargs['scanned_serial_number'] = "SCAN_SKIPPED_BY_TOOL"
            
            self.dut = DeviceUnderTest(**dut_kwargs)

            layout_key = 'Secure Key' if self.dut.secure_key else 'Portable'
            self._keypad_layout = KEYPAD_LAYOUTS[layout_key]
            self.logger.info(f"DUT Initialized. Keypad type: '{layout_key}'.")
        except Exception as e_dut_init:
            self.logger.error(f"Failed to initialize DeviceUnderTest (DUT): {e_dut_init}", exc_info=True)
            self.dut = None
            self.logger.warning("Defaulting to 'Portable' keypad layout due to DUT initialization error.")
            self._keypad_layout = KEYPAD_LAYOUTS['Portable']

        # --- Construct final LED configuration ---
        final_led_configs = copy.deepcopy(PRIMARY_LED_CONFIGURATIONS)

        if self.dut and self.dut.secure_key:
            roi_w, roi_h = ROI_SIZE_SECURE_KEYPAD
            self.logger.debug(f"Using SECURE keypad ROI size: {roi_w}x{roi_h}")
        else: 
            roi_w, roi_h = ROI_SIZE_STANDARD_KEYPAD
            self.logger.debug(f"Using STANDARD keypad ROI size: {roi_w}x{roi_h}")

        for led_key, position_data in roi_positions.items():
            if led_key in final_led_configs:
                x_pos = position_data.get('x')
                y_pos = position_data.get('y')
                if x_pos is not None and y_pos is not None:
                    final_led_configs[led_key]['roi'] = (x_pos, y_pos, roi_w, roi_h)
                    self.logger.debug(f"Applied dynamic ROI for '{led_key}': {final_led_configs[led_key]['roi']}")

        # --- Initialize Camera with final, dynamic configuration ---
        try:
            self._camera_checker = LogitechLedChecker(
                camera_id=camera_id,
                led_configs=final_led_configs, 
                display_order=display_order,
                logger_instance=self.logger.getChild("Camera"),
                duration_tolerance_sec=led_duration_tolerance_sec or CAMERA_DEFAULT_TOLERANCE,
                replay_post_failure_duration_sec=replay_post_failure_duration_sec or CAMERA_DEFAULT_REPLAY_DURATION,
                replay_output_dir=replay_output_dir,
                enable_instant_replay=enable_instant_replay,
                keypad_layout=self._keypad_layout,
                camera_hw_settings=camera_settings_to_apply
            )
            self._camera_checker._camera_settings_to_apply = camera_settings_to_apply
            
            if self._camera_checker.is_camera_initialized:
                camera_init_successful = True
        except Exception as e_camera_init:
            self.logger.error(f"Failed to initialize LogitechLedChecker for camera {camera_id}: {e_camera_init}", exc_info=True)

        self.is_fully_initialized = phidget_init_successful and camera_init_successful

    # --- PhidgetController Method Delegation ---
    def on(self, *channel_names: str):
        if not self._phidget_controller: self.logger.error("Phidget not initialized for 'on' command."); return
        for channel_name in channel_names:
            # Visualize the start of the press
            if self._camera_checker:
                self._camera_checker.start_key_press_for_replay(channel_name)
            # Perform the physical action
            self._phidget_controller.on(channel_name)
    def off(self, *channel_names: str):
        if not self._phidget_controller: self.logger.error("Phidget not initialized for 'off' command."); return
        for channel_name in channel_names:
            # Visualize the end of the press
            if self._camera_checker:
                self._camera_checker.stop_key_press_for_replay(channel_name)
            # Perform the physical action
            self._phidget_controller.off(channel_name)
    def hold(self, channel_name: str, duration_ms: float = 200):
        if not self._phidget_controller: self.logger.error("Phidget not init for 'hold'."); return
        if self._camera_checker:
            self._camera_checker.log_key_press_for_replay(channel_name, duration_s=duration_ms / 1000.0)
        self._phidget_controller.hold(channel_name, duration_ms)
    def press(self, channel_or_channels: Union[str, List[str]], duration_ms: float = 100):
        if not self._phidget_controller: self.logger.error("Phidget not init for 'press'."); return
        if self._camera_checker:
            keys_to_log = [channel_or_channels] if isinstance(channel_or_channels, str) else channel_or_channels
            for key in keys_to_log:
                self._camera_checker.log_key_press_for_replay(key, duration_s=duration_ms / 1000.0)
        self._phidget_controller.press(channel_or_channels, duration_ms=duration_ms)
    def sequence(self, pin_sequence: List[Any], press_duration_ms: float = 100, pause_duration_ms: float = 100):
        if not self._phidget_controller: self.logger.error("Phidget not init for 'sequence'."); return
        if self._camera_checker:
            for item in pin_sequence:
                keys_to_log = [item] if isinstance(item, str) else item
                for key in keys_to_log:
                    self._camera_checker.log_key_press_for_replay(key, duration_s=press_duration_ms / 1000.0)
        self._phidget_controller.sequence(pin_sequence, press_ms=press_duration_ms, pause_ms=pause_duration_ms)
    def read_input(self, channel_name: str) -> Optional[bool]:
        if not self._phidget_controller: self.logger.error("Phidget not init for 'read_input'."); return None
        return self._phidget_controller.read_input(channel_name)
    def wait_for_input(self, channel_name: str, expected_state: bool, timeout_s: float = 5, poll_interval_s: float = 0.05) -> bool:
        if not self._phidget_controller: self.logger.error("Phidget not init for 'wait_for_input'."); return False
        return self._phidget_controller.wait_for_input(channel_name, expected_state, timeout_s, poll_interval_s)
    
    def scan_barcode(self) -> str:
        """
        Triggers a new barcode scan and updates the controller's serial number.

        Returns:
            The scanned serial number string, or None if the scan failed or the scanner is unavailable.
        """
        if not self._barcode_scanner:
            self.logger.error("Barcode scanner not available.")
            pass
        else:
            scanned_data = None
            for retry in range(1, 4):
                scanned_data = self._barcode_scanner.await_scan()

                if scanned_data:
                    self.logger.debug(f"Scanned Serial Number: {scanned_data}")
                    self.scanned_serial_number = scanned_data
                    return scanned_data

                if retry < 3:
                    self.logger.warning(
                        f"Barcode scan attempt {retry} failed. Retrying in {self.scan_retry_delay_sec:.1f}s..."
                    )
                    time.sleep(self.scan_retry_delay_sec)
                else:
                    self.logger.warning(
                        f"Barcode scan attempt {retry} failed. On-demand barcode scan did not return data."
                    )

        manual_entry = self._prompt_manual_serial_entry()
        self.scanned_serial_number = manual_entry
        self.logger.info("Manual serial number entry accepted.")
        return manual_entry

    def _prompt_manual_serial_entry(self) -> str:
        """Prompt the operator for a serial number, allowing a single ad-hoc rescan."""
        prompt = (
            "Barcode scan failed after 3 attempts. Enter serial number manually ",
            "(type 'rescan' to try one more barcode read): ",
        )

        while True:
            try:
                manual_input = input(''.join(prompt))
            except KeyboardInterrupt:
                raise SystemExit("\nKeyboardInterrupt")
            except EOFError:
                self.logger.warning(
                    "Serial number entry interrupted (EOF). Please enter a serial number or press Ctrl+C to abort."
                )
                continue

            manual_serial = (manual_input or "").strip()

            if not manual_serial:
                self.logger.warning("Serial number is required. Please enter a value or type 'rescan'.")
                continue

            if manual_serial.lower() == "rescan":
                if not self._barcode_scanner:
                    self.logger.error(
                        "Rescan requested but barcode scanner is unavailable. Please enter the serial manually."
                    )
                    continue

                self.logger.info("Manual rescan requested after barcode failures.")
                rescanned_data = self._barcode_scanner.await_scan()
                if rescanned_data:
                    cleaned_rescan = rescanned_data.strip()
                    if cleaned_rescan.isdigit() and len(cleaned_rescan) == 12:
                        self.logger.debug(f"Rescan succeeded with serial: {cleaned_rescan}")
                        return cleaned_rescan

                    self.logger.warning(
                        "Rescan did not return a valid 12-digit serial. Please enter the serial manually."
                    )
                    continue

                self.logger.warning("Rescan attempt did not return data. Please enter the serial manually.")
                continue

            if not (manual_serial.isdigit() and len(manual_serial) == 12):
                self.logger.warning("Serial number must be exactly 12 digits.")
                continue

            return manual_serial
    # --- LogitechLedChecker Method Delegation ---
    @property
    def is_camera_ready(self) -> bool:
        return self._camera_checker is not None and self._camera_checker.is_camera_initialized

    def confirm_led_solid(self, state: dict, minimum: float = 2, timeout: float = 10,
                                 fail_leds: Optional[List[str]] = None, clear_buffer: bool = True, 
                                 manage_replay: bool = True, replay_extra_context: Optional[Dict[str, Any]] = None) -> bool:
        checker = self._camera_checker
        if checker is None or not checker.is_camera_initialized:
            self.logger.error("Camera not ready for confirm_led_solid.")
            return False
        return checker.confirm_led_solid(state, minimum, timeout, fail_leds, clear_buffer, 
                                         manage_replay=manage_replay, replay_extra_context=replay_extra_context)

    def confirm_led_solid_strict(self, state: dict, minimum: float, clear_buffer: bool = True, 
                                 manage_replay: bool = True, replay_extra_context: Optional[Dict[str, Any]] = None) -> bool:
        checker = self._camera_checker
        if checker is None or not checker.is_camera_initialized:
            self.logger.error("Camera not ready for confirm_led_solid_strict.")
            return False
        return checker.confirm_led_solid_strict(state, minimum, clear_buffer, 
                                                manage_replay=manage_replay, replay_extra_context=replay_extra_context)

    def await_led_state(self, state: dict, timeout: float = 1,
                               fail_leds: Optional[List[str]] = None, clear_buffer: bool = True, 
                               manage_replay: bool = True, replay_extra_context: Optional[Dict[str, Any]] = None) -> bool:
        checker = self._camera_checker
        if checker is None or not checker.is_camera_initialized:
            self.logger.error("Camera not ready for await_led_state.")
            return False
        return checker.await_led_state(state, timeout, fail_leds, clear_buffer, 
                                       manage_replay=manage_replay, replay_extra_context=replay_extra_context)

    def confirm_led_pattern(self, pattern: list, clear_buffer: bool = True, 
                            manage_replay: bool = True, replay_extra_context: Optional[Dict[str, Any]] = None) -> bool:
        checker = self._camera_checker
        if checker is None or not checker.is_camera_initialized:
            self.logger.error("Camera not ready for confirm_led_pattern.")
            return False
        return checker.confirm_led_pattern(pattern, clear_buffer, 
                                           manage_replay=manage_replay, replay_extra_context=replay_extra_context)

    def await_and_confirm_led_pattern(self, pattern: list, timeout: float,
                                             clear_buffer: bool = True, manage_replay: bool = True, replay_extra_context: Optional[Dict[str, Any]] = None) -> bool:
        checker = self._camera_checker
        if checker is None or not checker.is_camera_initialized:
            self.logger.error("Camera not ready for await_and_confirm_led_pattern.")
            return False
        return checker.await_and_confirm_led_pattern(pattern, timeout, clear_buffer, 
                                                     manage_replay=manage_replay, replay_extra_context=replay_extra_context)

    # --- Resource Management ---
    def close(self):
        if self._camera_checker and hasattr(self._camera_checker, 'release_camera'):
            try: self._camera_checker.release_camera()
            except Exception as e: self.logger.error(f"Error releasing camera: {e}", exc_info=True)
        if self._phidget_controller and hasattr(self._phidget_controller, 'close_all'):
            try: self._phidget_controller.close_all()
            except Exception as e: self.logger.error(f"Error closing phidget: {e}", exc_info=True)
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.close()

    def confirm_device_enum(self, serial_number: str, stable_min: float = 5, timeout: float = 15) -> Tuple[bool, Optional[Any]]:
        """
        Confirms a device is enumerated and stable in OOB/Standby mode (no data partition).
        
        Returns:
            A tuple containing:
            - bool: True if the device was found and stable, False otherwise.
            - Optional[ApricornDevice]: The device object if successful, else None.
        """
        self.logger.info(f"Confirming Device enumeration (stable: {stable_min}s, overall_timeout: {timeout}s)...")
        overall_start_time = time.time()
        
        # Use find_apricorn_device and handle the case where it returns an empty list
        devices = find_apricorn_device()
        if not devices:
            self.logger.warning("No device found on initial enum check.")
            return False, None
        
        DUT_ping_1 = None
        for device in devices:
            if device.iSerial == serial_number:
                DUT_ping_1 = device

        if DUT_ping_1 == None:
            self.logger.error(f"Could not match devices on bus with Serial Number...")
            return False, None
        
        first_device_serial = DUT_ping_1.iSerial
        if DUT_ping_1.driveSizeGB != "N/A (OOB Mode)":
            self.logger.warning(f"Device volume is exposed! Expected OOB/Standby mode.")
            return False, None
        else:
            self.logger.info(f"Initial device found with iSerial: {first_device_serial}. Verifying stability...")
        
        stability_wait_start = time.time()
        while time.time() - stability_wait_start < stable_min:
            if time.time() - overall_start_time > timeout:
                self.logger.warning(f"Overall timeout ({timeout}s) reached while waiting for stability for device {first_device_serial}.")
                return False, None
            time.sleep(0.2)

        devices_after_wait = find_apricorn_device()
        if not devices_after_wait:
            self.logger.warning(f"Device with iSerial {first_device_serial} disappeared after {time.time() - stability_wait_start:.2f}s stability wait.")
            return False, None
        
        DUT_ping_2 = None
        for device in devices_after_wait:
            if device.iSerial == serial_number:
                DUT_ping_2 = device

        if DUT_ping_2 == None:
            self.logger.error(f"Device is not stable on the bus...")
            return False, None

        if DUT_ping_2.driveSizeGB != "N/A (OOB Mode)":
            self.logger.warning(f"Device volume became exposed during stability wait!")
            pprint(DUT_ping_2)
            return False, None

        self.logger.info(f"Device with iSerial {first_device_serial} confirmed stable for at least {stable_min}s:")
        self.logger.info(f"  VID:PID  [Firm] @USB iSerial      iProduct")
        self.logger.info(f"  {DUT_ping_2.idVendor}:{DUT_ping_2.idProduct} [{DUT_ping_2.bcdDevice}] @{DUT_ping_2.bcdUSB} {DUT_ping_2.iSerial} {DUT_ping_2.iProduct}")
        return True, DUT_ping_2
    
    def confirm_drive_enum(self, serial_number: str, stable_min: float = 5, timeout: float = 15) -> Tuple[bool, Optional[Any]]:
        """
        Confirms a device's data partition is enumerated and stable.
        
        Returns:
            A tuple containing:
            - bool: True if the drive was found and stable, False otherwise.
            - Optional[ApricornDevice]: The device object if successful, else None.
        """
        self.logger.info(f"Confirming Drive enumeration (stable: {stable_min}s, overall_timeout: {timeout}s)...")
        overall_start_time = time.time()
        
        devices = find_apricorn_device()
        if not devices:
            self.logger.warning("No device found on initial enum check.")
            return False, None
        
        DUT_ping_1 = None
        for device in devices:
            if device.iSerial == serial_number:
                DUT_ping_1 = device

        if DUT_ping_1 == None:
            self.logger.error(f"Could not match devices on bus with Serial Number...")
            return False, None

        first_device_serial = DUT_ping_1.iSerial
        if DUT_ping_1.driveSizeGB == "N/A (OOB Mode)":
            self.logger.warning(f"Device volume is not exposed!")
            return False, None
        else:
            self.logger.info(f"Initial device found with iSerial: {first_device_serial}. Verifying stability...")
        
        stability_wait_start = time.time()
        while time.time() - stability_wait_start < stable_min:
            if time.time() - overall_start_time > timeout:
                self.logger.warning(f"Overall timeout ({timeout}s) reached while waiting for stability for device {first_device_serial}.")
                return False, None
            time.sleep(0.2)

        devices_after_wait = find_apricorn_device()
        if not devices_after_wait:
            self.logger.warning(f"Device with iSerial {first_device_serial} disappeared after {time.time() - stability_wait_start:.2f}s stability wait.")
            return False, None
        
        DUT_ping_2 = None
        for device in devices_after_wait:
            if device.iSerial == serial_number:
                DUT_ping_2 = device

        if DUT_ping_2 == None:
            self.logger.error(f"Device is not stable on the bus...")
            return False, None
        
        if DUT_ping_2.driveSizeGB == "N/A (OOB Mode)":
            self.logger.warning(f"Device volume disappeared during stability wait!")
            return False, None

        self.logger.info(f"Drive with iSerial {first_device_serial} confirmed stable for at least {stable_min}s:")
        self.logger.info(f"  VID:PID  [Firm] @USB iSerial      iProduct")
        self.logger.info(f"  {DUT_ping_2.idVendor}:{DUT_ping_2.idProduct} [{DUT_ping_2.bcdDevice}] @{DUT_ping_2.bcdUSB} {DUT_ping_2.iSerial} {DUT_ping_2.iProduct}")
        return True, DUT_ping_2
    
    def _format_disk(self, device, label="DUT", windows_partition_number=1):
        """
        Format an existing partition as FAT32.  exFAT ON WINDOWS ONLY!!!
        Returns True on success, False on failure.

        Windows:
        - device: disk number (int or str, e.g., 2)
        - windows_partition_number: required (int or str, e.g., 1)
        - Requires Admin; partition must already exist.

        Linux:
        - device: path to partition (str), e.g., "/dev/sdb1"
        - Uses: mkfs.vfat -F 32

        macOS:
        - device: path to disk/partition (str), e.g., "/dev/disk2s1"
        - Uses: diskutil eraseVolume FAT32
        """
        try:
            if sys.platform.startswith("win32"):
                if windows_partition_number is None:
                    raise ValueError("On Windows you must supply windows_partition_number")
                dn = str(device).strip()
                pn = str(windows_partition_number).strip()
                ps = f"""
                    $ErrorActionPreference = 'Stop'
                    $part = Get-Partition -DiskNumber {dn} -PartitionNumber {pn}
                    if (-not $part.DriveLetter) {{ $part | Add-PartitionAccessPath -AssignDriveLetter:$true }}
                    $letter = (Get-Partition -DiskNumber {dn} -PartitionNumber {pn}).DriveLetter
                    Format-Volume -DriveLetter $letter -FileSystem exFAT -NewFileSystemLabel '{label}' -Force -Confirm:$false
                    """
                subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                    check=True
                )
                return True

            elif sys.platform.startswith("linux"):
                subprocess.run(["mkfs.vfat", "-F", "32", "-n", label, str(device)], check=True)
                return True

            elif sys.platform.startswith("darwin"):
                subprocess.run(["diskutil", "eraseVolume", "FAT32", label, str(device)], check=True)
                return True

            else:
                raise NotImplementedError(f"Unsupported platform: {sys.platform}")

        except Exception as e:
            return False
    
    def _get_fio_path(self) -> str:
        """
        Determines the correct path to the bundled FIO binary based on the OS.

        Returns:
            The absolute path to the FIO executable.

        Raises:
            FileNotFoundError: If the FIO binary for the current OS is not found.
            NotImplementedError: If the current OS is not supported.
        """
        # Assumes PROJECT_ROOT is defined at the top of the file
        binaries_dir = os.path.join(PROJECT_ROOT, 'utils', 'fio')
        fio_path = None

        if sys.platform == 'darwin':
            fio_path = os.path.join(binaries_dir, 'fio-macos')
        elif sys.platform.startswith('linux'):
            fio_path = os.path.join(binaries_dir, 'fio-linux')
        elif sys.platform == 'win32':
            fio_path = os.path.join(binaries_dir, 'fio-windows.exe')
        else:
            raise NotImplementedError(f"FIO automation is not supported on this OS: {sys.platform}")

        if not os.path.isfile(fio_path):
            raise FileNotFoundError(f"FIO executable not found at the expected path: {fio_path}")
        
        # On Linux/macOS, ensure it's executable
        if not os.access(fio_path, os.X_OK) and sys.platform != 'win32':
            self.logger.warning(f"FIO binary at {fio_path} is not executable. Attempting to run it anyway, but it may fail.")

        return fio_path
    
    def _parse_fio_json_output(self, json_output: str) -> Optional[Dict[str, float]]:
        """
        Parses the JSON output from FIO to extract read and write bandwidth.

        Args:
            json_output: The string containing the FIO JSON data.

        Returns:
            A dictionary with 'read' and/or 'write' keys and their speeds in MB/s,
            or None if parsing fails.
        """
        try:
            data = json.loads(json_output)
            results = {}
            # FIO output contains a list of jobs, we are interested in the first one.
            if 'jobs' in data and data['jobs']:
                job_result = data['jobs'][0]
                
                # Check for read results
                if 'read' in job_result and job_result['read']['io_bytes'] > 0:
                    bw_bytes = job_result['read']['bw_bytes']
                    # Convert Bytes/sec to Megabytes/sec (1 MB = 1,000,000 bytes)
                    results['read'] = round(bw_bytes / 1000**2, 2)

                # Check for write results
                if 'write' in job_result and job_result['write']['io_bytes'] > 0:
                    bw_bytes = job_result['write']['bw_bytes']
                    results['write'] = round(bw_bytes / 1000**2, 2)
                
                return results if results else None
            else:
                self.logger.warning("FIO JSON output is missing 'jobs' array.")
                return None
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            self.logger.error(f"Failed to parse FIO JSON output: {e}", exc_info=True)
            return None


    def _has_admin_privileges(self) -> bool:
        '''Return True if the process is running with raw disk privileges.'''
        if sys.platform != 'win32':
            return True
        try:
            import ctypes  # type: ignore
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:  # pragma: no cover - defensive; should not trigger on Windows
            self.logger.debug(
                'Unable to determine Windows administrator privileges; assuming elevated.',
                exc_info=True,
            )
            return True

    def _normalize_windows_drive_letter(self, drive_letter: Optional[str]) -> Optional[str]:
        '''Normalize a drive letter string (e.g., "E:" or "E:, F:") to the form "E:".'''
        if not drive_letter:
            return None
        candidate = drive_letter.split(',')[0].strip()
        if not candidate or candidate.upper() == 'N/A':
            return None
        candidate = candidate.replace('\\', '').replace('/', '')
        if candidate.endswith(':'):
            candidate = candidate[:-1]
        if len(candidate) != 1 or not candidate.isalpha():
            return None
        return f"{candidate.upper()}:"

    def run_fio_tests(
        self,
        disk_path: str,
        duration: int = 10,
        tests_to_run: Optional[List[Dict[str, Any]]] = None,
        drive_letter: Optional[str] = None,
    ) -> Optional[Dict[str, float]]:
        '''
        Runs a series of specified FIO speed tests directly on the block device
        or via a file-based fallback when elevated privileges are unavailable.

        Args:
            disk_path: Device path (e.g., '/dev/sdb' or 'PhysicalDrive1').
            duration: Runtime in seconds for each test.
            tests_to_run: Optional set of test definitions; defaults to sequential R/W.
            drive_letter: Optional drive letter for Windows fallback testing.

        Returns:
            Aggregated read/write results when successful; otherwise None.
        '''
        if tests_to_run is None:
            self.logger.debug('No specific tests provided, using default sequential R/W tests.')
            tests_to_run = [
                {
                    'name': 'W-SEQ-1M-Q32',
                    'rw': 'write',
                    'bs': '1m',
                    'iodepth': 32,
                },
                {
                    'name': 'R-SEQ-1M-Q32',
                    'rw': 'read',
                    'bs': '1m',
                    'iodepth': 32,
                },
            ]

        self.logger.debug('Starting FIO speed test sequence for %ss each.', duration)

        try:
            fio_path = self._get_fio_path()
        except (FileNotFoundError, NotImplementedError) as exc:
            self.logger.error('Cannot run FIO tests: %s', exc)
            raise

        temp_file_path: Optional[str] = None
        using_temp_file = False

        if sys.platform == 'win32':
            disk_path_str = str(disk_path)
            if disk_path_str.isdigit():
                win_path = f'PhysicalDrive{disk_path_str}'
            elif disk_path_str.lower().startswith('\\.') and len(disk_path_str) > 4 and disk_path_str[4] == '\\':
                win_path = disk_path_str[4:]
            else:
                win_path = disk_path_str

            fio_target_device = f"\\\\.\\{win_path}"

            if not self._has_admin_privileges():
                normalized_drive = self._normalize_windows_drive_letter(drive_letter)
                if not normalized_drive:
                    self.logger.error(
                        'Administrator privileges are required for raw disk testing and no drive letter fallback was provided.',
                    )
                    self.logger.error(
                        'Run the toolkit as Administrator or provide a mounted drive letter for file-based FIO testing.',
                    )
                    return None

                drive_root = f"{normalized_drive}{os.sep}"
                if not os.path.isdir(drive_root):
                    self.logger.error(
                        'Fallback drive letter %s is not accessible.',
                        normalized_drive,
                    )
                    return None

                temp_file_path = os.path.normpath(
                    os.path.join(drive_root, 'apricorn_fio_benchmark.bin')
                )

                if os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                        self.logger.debug(
                            'Removed stale FIO benchmark file %s.',
                            temp_file_path,
                        )
                    except OSError as cleanup_error:
                        self.logger.warning(
                            'Could not remove existing benchmark file %s: %s',
                            temp_file_path,
                            cleanup_error,
                        )

                fio_target_device = temp_file_path
                using_temp_file = True
                self.logger.warning(
                    'Administrator privileges not detected; running FIO against temporary file %s.',
                    fio_target_device,
                )
                self.logger.debug(
                    'Targeting Windows fallback file: %s',
                    fio_target_device,
                )
            else:
                self.logger.debug(
                    'Targeting raw Windows device: %s',
                    fio_target_device,
                )
        else:
            fio_target_device = disk_path
            self.logger.debug(
                'Targeting raw Linux device: %s',
                fio_target_device,
            )

        combined_results: Dict[str, float] = {}

        try:
            for test_params in tests_to_run:
                self.logger.debug('--- Preparing FIO test: %s ---', test_params.get('name', 'Unnamed'))

                base_command = [fio_path]

                if sys.platform.startswith('linux'):
                    base_command.extend(['--ioengine=libaio'])
                elif sys.platform == 'win32':
                    base_command.extend(['--ioengine=windowsaio', '--thread'])

                base_command.extend([
                    '--direct=1',
                    '--output-format=json',
                    '--random_generator=tausworthe64',
                    f'--filename={fio_target_device}',
                    f'--runtime={duration}',
                    f"--name={test_params.get('name')}",
                    f"--rw={test_params.get('rw')}",
                    f"--bs={test_params.get('bs')}",
                    f"--iodepth={test_params.get('iodepth')}",
                    '--group_reporting',
                ])

                try:
                    self.logger.debug('Executing command: %s', ' '.join(base_command))
                    result = subprocess.run(base_command, check=True, capture_output=True, text=True)

                    parsed_result = self._parse_fio_json_output(result.stdout)
                    if parsed_result:
                        self.logger.debug(
                            "--- FIO Test '%s' Result: %s MB/s",
                            test_params.get('name'),
                            parsed_result,
                        )
                        combined_results.update(parsed_result)
                    else:
                        self.logger.error(
                            "Failed to parse results for FIO test '%s'.",
                            test_params.get('name'),
                        )
                        return None

                    if result.stderr:
                        self.logger.warning('FIO Stderr: %s', result.stderr)

                except FileNotFoundError:
                    self.logger.error("FIO command not found at '%s'.", fio_path)
                    raise
                except subprocess.CalledProcessError as exc:
                    self.logger.error(
                        "FIO test '%s' failed with exit code %s.",
                        test_params.get('name'),
                        exc.returncode,
                    )
                    self.logger.error(
                        '  This can happen if the script is not run with administrator/root privileges.',
                    )
                    self.logger.error('  Stdout: %s', exc.stdout)
                    self.logger.error('  Stderr: %s', exc.stderr)
                    return None
                except Exception as exc:  # pragma: no cover - defensive
                    self.logger.error(
                        'An unexpected error occurred during FIO test: %s',
                        exc,
                        exc_info=True,
                    )
                    return None

            if 'read' in combined_results:
                self.logger.info('Read: %s', combined_results['read'])
            if 'write' in combined_results:
                self.logger.info('Write: %s', combined_results['write'])
            if combined_results:
                self.logger.info('FIO test sequence completed successfully.')
            return combined_results if combined_results else None
        finally:
            if using_temp_file and temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    self.logger.debug(
                        'Removed temporary FIO benchmark file %s.',
                        temp_file_path,
                    )
                except OSError as cleanup_error:
                    self.logger.warning(
                        'Failed to remove temporary FIO benchmark file %s: %s',
                        temp_file_path,
                        cleanup_error,
                    )

    # --- FSM Event Handling Callbacks (High-Level) ---
    def handle_post_failure(self, event_data: Any) -> None: 
        details = event_data.kwargs.get('details', "No details provided") if event_data and hasattr(event_data, 'kwargs') else "No details provided"
        self.logger.error(f"UnifiedController: Handling POST failure. Details from FSM: {details}")

    def handle_critical_error(self, event_data: Any) -> None:
        details = event_data.kwargs.get('details', "No details provided") if event_data and hasattr(event_data, 'kwargs') else "No details provided"
        self.logger.critical(f"UnifiedController: Handling CRITICAL error. Details from FSM: {details}")

# --- For direct testing ---
if __name__ == '__main__': # pragma: no cover
    try:
        from controllers.logging import setup_logging
        setup_logging(default_log_level=logging.DEBUG) 
    except ImportError:
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logging.getLogger().critical("Could not import 'utils.logging_config.setup_logging' for direct test. Using basicConfig.")

    direct_test_logger = logging.getLogger("UnifiedControllerDirectTest")
    direct_test_logger.info("UnifiedController direct test logging configured and starting...")
    uc_instance_for_test = None
    try:
        test_replay_dir = os.path.join(PROJECT_ROOT, "logs", "test_replays_uc_direct")
        os.makedirs(test_replay_dir, exist_ok=True)

        uc_instance_for_test = UnifiedController(
            logger_instance=direct_test_logger.getChild("TestUCInstance"),
            camera_id=0, 
            led_duration_tolerance_sec=0.08, 
            replay_post_failure_duration_sec=2.0, # Shorter for quick testing
            replay_output_dir=test_replay_dir 
        )
        direct_test_logger.info(f"Test UnifiedController instance created. Camera Ready: {uc_instance_for_test.is_camera_ready}")
        if uc_instance_for_test._camera_checker:
            direct_test_logger.info(f"  Replay dir: {uc_instance_for_test._camera_checker.replay_output_dir}")

        if uc_instance_for_test.is_camera_ready:
            direct_test_logger.info("--- Testing Camera Replay with Context ---")
            fail_state = {"red": 1, "green": 1, "blue": 1} # A state likely to fail
            
            # Simulate context that an FSM might provide
            test_context = {
                "replay_script_name": os.path.basename(__file__),
                "replay_fsm_test_case": "DirectUCTest_Failure",
                "replay_some_other_info": "Value123"
            }
            direct_test_logger.info(f"Attempting confirm_led_solid for {fail_state} (expecting failure and replay with context).")
            # input("Prepare for FAILING confirm_led_solid test with context. Press Enter...")
            
            uc_instance_for_test.confirm_led_solid(
                fail_state, minimum=0.1, timeout=0.5, replay_extra_context=test_context
            )
            direct_test_logger.info(f"  Check for replay video in: {test_replay_dir}")
        else:
            direct_test_logger.warning("Camera component not ready, skipping camera replay test.")
            
    except Exception as e_test_main:
        direct_test_logger.error(f"Error during UnifiedController direct test: {e_test_main}", exc_info=True)
    finally:
        if uc_instance_for_test:
            direct_test_logger.info("Closing UnifiedController instance from direct test...")
            uc_instance_for_test.close()
        direct_test_logger.info("UnifiedController direct test finished.")



