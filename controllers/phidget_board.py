# Directory: controllers
# Filename: phidget_board.py
#!/usr/bin/env python3

import time
import sys
import logging # Standard library logging
from Phidget22.Phidget import Phidget
from Phidget22.Devices.DigitalOutput import DigitalOutput
from Phidget22.Devices.DigitalInput import DigitalInput
from Phidget22.PhidgetException import PhidgetException
from Phidget22.ErrorCode import ErrorCode
from typing import Optional, List, Any, Union

# Get the logger for this module. Its name will be 'controllers.phidget_board'.
# Configuration (handlers, level, format) comes from the global setup.
module_logger = logging.getLogger(__name__)

# --- Default Script Channel Map Configuration ---
DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG = {
    "outputs": {
        "key0":    {"phidget_id": "main_phidget", "physical_channel": 0},
        "key1":    {"phidget_id": "main_phidget", "physical_channel": 1},
        "key2":    {"phidget_id": "main_phidget", "physical_channel": 2},
        "key3":    {"phidget_id": "main_phidget", "physical_channel": 3},
        "key4":    {"phidget_id": "main_phidget", "physical_channel": 4},
        "key5":    {"phidget_id": "main_phidget", "physical_channel": 5},
        "key6":    {"phidget_id": "main_phidget", "physical_channel": 6},
        "key7":    {"phidget_id": "main_phidget", "physical_channel": 7},
        "key8":    {"phidget_id": "main_phidget", "physical_channel": 8},
        "key9":    {"phidget_id": "main_phidget", "physical_channel": 9},
        "lock":    {"phidget_id": "main_phidget", "physical_channel": 10},
        "unlock":  {"phidget_id": "main_phidget", "physical_channel": 11},
        "hold":    {"phidget_id": "main_phidget", "physical_channel": 12},
        "connect": {"phidget_id": "main_phidget", "physical_channel": 13},
        "usb3":    {"phidget_id": "main_phidget", "physical_channel": 14},
        "barcode": {"phidget_id": "main_phidget", "physical_channel": 15}
        
    },
    "inputs": {
        "prod_inserted": {"phidget_id": "main_phidget", "physical_channel": 0},
        "power_on":      {"phidget_id": "main_phidget", "physical_channel": 1},
    }
}

# Default device configurations (can be overridden or extended by constructor argument)
DEFAULT_DEVICE_CONFIGS = {
    "main_phidget": {
        "serial_number": -1,
        "open_timeout_ms": 5000,
        "is_remote": False,
    }
}

class PhidgetController:
    def __init__(self,
                 script_map_config=None,
                 device_configs=None,
                 logger_instance=None):
        self.logger = logger_instance if logger_instance else module_logger
        self.script_map_config = script_map_config if script_map_config is not None else DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG
        self.device_configs = DEFAULT_DEVICE_CONFIGS.copy()
        if device_configs:
            for key, val in device_configs.items():
                if key in self.device_configs: self.device_configs[key].update(val)
                else: self.device_configs[key] = val
        self.logger.debug(f"Using device configurations: {self.device_configs}")
        self.channels = {}
        self._opened_physical_channels = {}
        self._initialize_channels()

    def _configure_phidget_connection(self, ph: Phidget, device_key: str):
        config = self.device_configs.get(device_key)
        if not config:
            self.logger.error(f"No device configuration for phidget_id: '{device_key}'"); raise ValueError(f"No config for '{device_key}'")
        if not config.get("is_remote", False):
            ph.setIsRemote(False)
            if config.get("is_hub_port_device", False):
                ph.setIsHubPortDevice(True); hub_port = config.get("hub_port", -1)
                if hub_port == -1: self.logger.debug(f"Hub port for {device_key} is any.")
                ph.setHubPort(hub_port)
                if config.get("parent_serial_number", -1) != -1: self.logger.debug(f"Parent S/N {config['parent_serial_number']} for {device_key}.")
        serial_to_set = config.get("serial_number", -1); ph.setDeviceSerialNumber(serial_to_set)
        if serial_to_set == -1: self.logger.debug(f"No S/N for {'remote' if config.get('is_remote') else 'local'} '{device_key}'. Will open any.")
        return config.get("open_timeout_ms", 5000)

    def _initialize_channels(self):
        types_map = {"outputs": DigitalOutput, "inputs": DigitalInput}
        for type_name, ph_class in types_map.items():
            if type_name not in self.script_map_config: self.logger.debug(f"No '{type_name}' in config."); continue
            for script_name, map_info in self.script_map_config[type_name].items():
                ph_id_key, phys_ch_idx = map_info.get("phidget_id"), map_info.get("physical_channel")
                if ph_id_key is None or phys_ch_idx is None: self.logger.warning(f"Skip '{script_name}': missing phidget_id/physical_channel."); continue
                unique_key = (ph_id_key, type_name, phys_ch_idx)
                if unique_key not in self._opened_physical_channels:
                    self.logger.debug(f"  Opening {type_name[:-1]} '{script_name}' (DevKey: {ph_id_key}, PhysChan: {phys_ch_idx}).")
                    try:
                        ch = ph_class(); timeout = self._configure_phidget_connection(ch, ph_id_key); ch.setChannel(phys_ch_idx)
                        self.logger.debug(f"    Opening '{script_name}' with timeout {timeout}ms...")
                        ch.openWaitForAttachment(timeout)
                        self.logger.debug(f"    Opened '{script_name}'. Dev: {ch.getDeviceName()}, S/N: {ch.getDeviceSerialNumber()}, Ch: {ch.getChannel()}, HubPort: {ch.getHubPort() if ch.getIsHubPortDevice() else 'N/A'}, Remote: {ch.getIsRemote()}")
                        self._opened_physical_channels[unique_key] = ch
                    except PhidgetException as e:
                        log_msg = f"Error opening {type_name[:-1]} '{script_name}' (DevKey {ph_id_key}, Ch {phys_ch_idx}): PhidgetExc: {e.description} (Code {e.code}, {ErrorCode.getName(e.code)})"
                        if e.code == ErrorCode.EPHIDGET_TIMEOUT: log_msg += ". Check connection/settings."
                        self.logger.error(log_msg); self._opened_physical_channels[unique_key] = None
                    except Exception as e: self.logger.error(f"Unexpected error opening {type_name[:-1]} '{script_name}': {e}", exc_info=True); self._opened_physical_channels[unique_key] = None
                self.channels[script_name] = self._opened_physical_channels.get(unique_key)
                if not self.channels[script_name] and unique_key in self._opened_physical_channels: self.logger.warning(f"    Channel '{script_name}' failed init.")
        self.logger.debug("Phidget module initialized.")

    def _get_channel_object(self, name, expected_type=None):
        if name not in self.channels:
            is_def = any(name in self.script_map_config.get(t, {}) for t in ["outputs", "inputs"])
            if is_def: raise RuntimeError(f"Channel '{name}' defined but failed init.")
            raise NameError(f"Channel '{name}' not defined.")
        ch = self.channels.get(name)
        if ch is None: raise RuntimeError(f"Channel '{name}' is None (failed init).")
        if expected_type and not isinstance(ch, expected_type): raise TypeError(f"Channel '{name}' not {expected_type.__name__}, found {type(ch).__name__}.")
        if not ch.getAttached():
            self.logger.error(f"Channel '{name}' (S/N {ch.getDeviceSerialNumber()}, Ch {ch.getChannel()}) not attached.")
            raise PhidgetException(ErrorCode.EPHIDGET_NOTATTACHED)
        return ch

    def set_output(self, name, state):
        do_ch = self._get_channel_object(name, DigitalOutput)
        try: do_ch.setState(bool(state)); self.logger.debug(f"Output '{name}' set to {'ON' if state else 'OFF'}.")
        except PhidgetException as e: self.logger.error(f"Error setting output '{name}': {e.description}", exc_info=False); raise

    def on(self, name): self.set_output(name, True)
    
    def off(self, name): self.set_output(name, False)

    def hold(self, name: str, duration_ms: float = 200):
        self.logger.debug(f"Holding '{name}' ON for {duration_ms}ms.")
        try:
            self.on(name)
            time.sleep(duration_ms / 1000.0)
        finally:
            try:
                self.off(name)
            except Exception as e:
                self.logger.error(f"Error turning off '{name}' during hold: {e}", exc_info=True)

    def press(self, channel_or_channels: Union[str, List[str]], duration_ms: float = 100):
        """
        Turns on an output channel, holds, then releases. Can handle single or
        multiple channels for simultaneous presses.

        Args:
            channel_or_channels (Union[str, List[str]]): A single channel name (str)
                or a list of channel names (List[str]) to be pressed simultaneously.
            duration_ms (float): The duration for the press in milliseconds. Default 100.

        Example:
            press("lock")
                # 'Press' lock key (holding for 0.1s)

            press("key1", duration_ms=500)
                # 'Press' channel "key1" (holding for 0.5s)

            press(["key1", "key2"], duration_ms=3000)
                # 'Press' key1 and key2 simultaneously (holding for 3s)
        """
        if isinstance(channel_or_channels, list):
            self._pulse_simultaneous(channel_or_channels, duration_ms=duration_ms)
        elif isinstance(channel_or_channels, str):
            self.hold(channel_or_channels, duration_ms=duration_ms)
        else:
            raise TypeError(f"Argument for 'press' must be a string or a list of strings, but got {type(channel_or_channels)}.")

    def _pulse_simultaneous(self, pins: List[str], duration_ms: float):
        """Turns on a list of pins simultaneously, holds, then turns them off."""
        self.logger.debug(f"Simultaneous press: {pins} for {duration_ms}ms.")
        try:
            for pin in pins:
                self.on(pin)
            time.sleep(duration_ms / 1000.0)
        finally:
            for pin in pins:
                try:
                    self.off(pin)
                except Exception as e:
                    self.logger.error(f"Error turning off '{pin}' during simultaneous pulse: {e}", exc_info=True)

    def sequence(self, pins: List[Any], press_ms: float = 100, pause_ms: float = 100):
        """
        'Presses' a list of outputs sequentially. The sequence is a list where each
        item can be a channel name (str) for a single press, or a nested list of
        channel names for a simultaneous press.

        Args:
            pins (List[Any]): A list of single channel names (str) or nested
                              lists of channel names (List[str]).
            press_ms (float): The duration for each press in milliseconds. Default 100.
            pause_ms (float): The pause between presses in milliseconds. Default 100.
        """
        if not isinstance(pins, list):
            raise ValueError(f"Pins argument must be a list, but got {type(pins)}")
        if not isinstance(press_ms, (int, float)) or press_ms < 0:
            raise ValueError(f"press_ms must be a non-negative number, but got {press_ms}")
        if not isinstance(pause_ms, (int, float)) or pause_ms < 0:
            raise ValueError(f"pause_ms must be a non-negative number, but got {pause_ms}")
        
        self.logger.debug(f"Sequence: {pins} (Press: {press_ms}ms, Pause: {pause_ms}ms)")
        
        for i, item in enumerate(pins):
            if isinstance(item, list):
                self._pulse_simultaneous(item, duration_ms=press_ms)
            elif isinstance(item, str):
                self.hold(item, duration_ms=press_ms)
            else:
                raise TypeError(f"Sequence item must be a string or a list of strings, but got {type(item)}.")

            if i < len(pins) - 1 and pause_ms > 0:
                self.logger.debug(f"  Pause {pause_ms}ms.")
                time.sleep(pause_ms / 1000.0)

    def read_input(self, name: str) -> Optional[bool]:
        di_ch = self._get_channel_object(name, DigitalInput)
        try:
            state = di_ch.getState()
            self.logger.info(f"Input '{name}' read as {'HIGH' if state else 'LOW'}.")
            return state
        except PhidgetException as e:
            self.logger.error(f"Error reading input '{name}': {e.description}", exc_info=False)
            raise

    def wait_for_input(self, name: str, expected_state: bool, timeout_s: float = 5, poll_s: float = 0.05) -> bool:
        expected = bool(expected_state); start = time.time()
        self.logger.info(f"Waiting for input '{name}' to be {'HIGH' if expected else 'LOW'} (timeout: {timeout_s}s)...")
        while time.time() - start < timeout_s:
            try:
                ch = self._get_channel_object(name, DigitalInput)
                if ch.getState() == expected:
                    self.logger.info(f"Input '{name}' reached state {'HIGH' if expected else 'LOW'}.")
                    return True
            except PhidgetException as e:
                if e.code == ErrorCode.EPHIDGET_NOTATTACHED:
                    channel_for_log = self.channels.get(name)
                    serial_info = channel_for_log.getDeviceSerialNumber() if channel_for_log else "N/A"
                    self.logger.warning(f"Input '{name}' detached. Retrying. (S/N {serial_info})")
                else:
                    self.logger.error(f"PhidgetExc waiting for '{name}': {e.description}", exc_info=False)
            except (NameError, RuntimeError, TypeError) as e:
                self.logger.error(f"Cannot wait for '{name}': {e}", exc_info=True)
                raise
            time.sleep(poll_s)
        last_state = "UNKNOWN"; ch = self.channels.get(name)
        try:
            if ch and ch.getAttached():
                last_state = 'HIGH' if ch.getState() else 'LOW'
            elif ch:
                last_state = "NOT ATTACHED"
        except:
            pass
        self.logger.warning(f"Timeout waiting for '{name}' to be {'HIGH' if expected else 'LOW'}. Last state: {last_state}.")
        return False

    def close_all(self):
        closed, failed = 0, 0
        for key, ch in list(self._opened_physical_channels.items()):
            if ch:
                log_ref = f"DevKey '{key[0]}', Type '{key[1]}', PhysCh {key[2]} (Scripts: {[s for s,c in self.channels.items() if c==ch]})"
                if ch.getAttached():
                    try:
                        if isinstance(ch, DigitalOutput) and ch.getState(): self.logger.debug(f"  OFF output {log_ref} pre-close."); ch.setState(False)
                        ch.close(); closed +=1
                    except PhidgetException as e: self.logger.error(f"Error closing {log_ref}: {e.description}", exc_info=False); failed+=1
                else: self.logger.debug(f"  {log_ref} not attached/already closed."); ch.close() # Close non-attached too
        self._opened_physical_channels.clear(); self.channels.clear()
        self.logger.info(f"Phidgets close complete. Closed: {closed}, Errors: {failed}.")

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.close_all()