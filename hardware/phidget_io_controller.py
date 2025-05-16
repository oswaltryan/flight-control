# Directory: hardware
# Filename: phidget_io_controller.py
#!/usr/bin/env python3

import time
import sys
import logging # For PhidgetController's own logger and Phidget22 library
from Phidget22.Phidget import Phidget
from Phidget22.Devices.DigitalOutput import DigitalOutput
from Phidget22.Devices.DigitalInput import DigitalInput
from Phidget22.PhidgetException import PhidgetException

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
        "connect": {"phidget_id": "main_phidget", "physical_channel": 13},
        "usb3":    {"phidget_id": "main_phidget", "physical_channel": 14},
        "hold":    {"phidget_id": "main_phidget", "physical_channel": 12},
    },
    "inputs": {
        "prod_inserted": {"phidget_id": "main_phidget", "physical_channel": 0},
        "power_on":      {"phidget_id": "main_phidget", "physical_channel": 1},
    }
}

# Module-level logger, following the camera_controller.py pattern
# This logger will be used by default if no logger_instance is passed to PhidgetController
# Using __name__ (which will be 'hardware.phidget_io_controller') is a common practice.
module_logger = logging.getLogger(__name__)
module_logger.addHandler(logging.NullHandler()) # Add NullHandler to prevent "No handler found" warnings

# The _create_controller_logger function has been removed.

def enable_phidget_library_logging(level="DEBUG", app_logger=None):
    """
    Attempts to enable more verbose logging from the Phidget22 Python library
    by configuring Python's standard `logging` module for the 'Phidget22' logger.

    :param level: Logging level string (e.g., "DEBUG", "INFO", "WARNING").
    :param app_logger: The logger instance to use for messages from this function itself.
                       If None, prints directly to stderr.
    """
    # If app_logger is None, use a temporary basic logger for messages from this function.
    # This is to ensure messages from this utility are seen even if no app_logger is passed.
    # However, in practice, PhidgetController will always pass its self.logger.
    effective_logger = app_logger if app_logger else logging.getLogger("PhidgetLibConfig")
    if app_logger is None and not effective_logger.hasHandlers():
        # Basic config for the temporary logger if no app_logger and it's not configured
        _handler = logging.StreamHandler(sys.stderr)
        _formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        _handler.setFormatter(_formatter)
        effective_logger.addHandler(_handler)
        effective_logger.setLevel(logging.INFO) # Default to INFO for this utility's messages

    try:
        phidget_lib_logger = logging.getLogger("Phidget22") # Logger used by the Phidget22 library
        
        has_stderr_handler = any(
            isinstance(h, logging.StreamHandler) and getattr(h, 'stream', None) == sys.stderr
            for h in phidget_lib_logger.handlers
        )
        
        # Configure handler only if no stderr handler exists OR if the root logger also has no handlers
        # This avoids duplicate logs if root is already configured to output to stderr.
        if not has_stderr_handler and not logging.getLogger().hasHandlers():
            handler = logging.StreamHandler(sys.stderr)
            formatter = logging.Formatter('%(asctime)s - Phidget22 - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            phidget_lib_logger.addHandler(handler)

        log_level_val = getattr(logging, level.upper(), None)
        if not isinstance(log_level_val, int):
            msg = f"Warning: Invalid Phidget library log level '{level}'. Defaulting to DEBUG."
            effective_logger.warning(msg)
            log_level_val = logging.DEBUG
        
        phidget_lib_logger.setLevel(log_level_val)
        for h in phidget_lib_logger.handlers: # Ensure handlers respect the new level
            if h.level == 0 or h.level > log_level_val: # 0 is NOTSET
                 h.setLevel(log_level_val)
        
        phidget_lib_logger.propagate = True # Allow propagation to root logger
        
        # effective_logger.debug(f"Attempted to set Phidget22 Python library logging to: {level.upper()}")

    except Exception as e:
        err_msg = f"Error attempting to enable Phidget22 Python library logging: {e}"
        effective_logger.error(err_msg)


class PhidgetController:
    def __init__(self, script_map_config=DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG, logger_instance=None):
        """
        Initializes the PhidgetController for LOCAL Phidgets only.
        Uses a provided logger_instance or defaults to the module-level logger.
        It also configures logging for the underlying Phidget22 library.

        :param script_map_config: (Optional) Dictionary defining script names to physical channel mappings.
                                  If None, uses DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG.
        :param logger_instance: (Optional) An external logging.Logger instance.
        """
        self.logger = logger_instance if logger_instance else module_logger
        
        # Enable Phidget22 library specific logging, using self.logger for its own status messages.
        enable_phidget_library_logging(level="DEBUG", app_logger=self.logger)

        if script_map_config is None:
            self.script_map_config = DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG
        else:
            self.script_map_config = script_map_config
            
        self.device_configs = {
            "main_phidget": {
                "serial_number": -1, # Use -1 for any serial number (wildcard)
                "open_timeout_ms": 5000
            }
        }
        self.channels = {} # Stores script_name -> Phidget channel object
        self._opened_physical_channels = {} # Stores (phidget_id_key, type_name, physical_idx) -> Phidget channel object to avoid re-opening
        
        # Warn if network configurations are present, as they are ignored by this version
        if any(cfg.get("is_remote", False) for cfg in self.device_configs.values()):
            self.logger.warning("This PhidgetController version does not support network Phidgets. "
                                "'is_remote' configurations will be ignored.")
            
        self._initialize_channels()

    def _configure_phidget_connection(self, ph, device_key):
        """Configures Phidget object with connection details for LOCAL Phidgets."""
        config = self.device_configs.get(device_key)
        if not config:
            raise ValueError(f"No device configuration found for phidget_id: '{device_key}'")

        # Network-related configurations are ignored.
        if config.get("is_remote", False):
            self.logger.warning(f"Attempting to configure '{device_key}' as remote, but network "
                                "support is disabled in this PhidgetController. Treating as local.")

        # Local connection (direct USB or VINT Hub)
        if config.get("is_hub_port_device", False):
            ph.setIsHubPortDevice(True)
            hub_port = config.get("hub_port", -1)
            if hub_port == -1:
                self.logger.warning(f"Hub port for {device_key} is -1 (any). Ensure this is intended.")
            ph.setHubPort(hub_port)
            
            parent_sn = config.get("parent_serial_number", -1)
            if parent_sn != -1:
                 self.logger.debug(f"Parent S/N {parent_sn} noted for {device_key}. "
                                   "Ensure VINT module's own S/N or hub port is correctly configured.")
        
        # Set device serial number (applies to direct USB, VINT modules on hubs)
        if config.get("serial_number", -1) != -1:
            ph.setDeviceSerialNumber(config.get("serial_number"))
        else:
            # If it's a hub port device and no specific serial is given, it will try to open
            # any device of the correct type on the specified (or any) hub port.
            if not config.get("is_hub_port_device", False):
                #  self.logger.info(f"No serial number specified for '{device_key}'. Will attempt to open any matching local device.")
                pass

        return config.get("open_timeout_ms", 5000)


    def _initialize_channels(self):
        # self.logger.info("Initializing Phidget channels (Local Only)...")
        channel_types_map = {
            "outputs": DigitalOutput,
            "inputs": DigitalInput
        }

        for channel_type_name, phidget_class in channel_types_map.items():
            if channel_type_name not in self.script_map_config:
                self.logger.debug(f"No '{channel_type_name}' defined in script_map_config. Skipping.")
                continue

            for script_name, mapping_info in self.script_map_config[channel_type_name].items():
                phidget_id_key = mapping_info.get("phidget_id")
                physical_channel_index = mapping_info.get("physical_channel")

                if phidget_id_key is None or physical_channel_index is None:
                    self.logger.warning(f"  Skipping '{script_name}': 'phidget_id' or 'physical_channel' missing in mapping_info: {mapping_info}")
                    continue

                unique_ph_key = (phidget_id_key, channel_type_name, physical_channel_index)

                if unique_ph_key not in self._opened_physical_channels:
                    try:
                        # self.logger.info(f"  Opening {channel_type_name[:-1]} '{script_name}' (Device ID: {phidget_id_key}, PhysChan: {physical_channel_index})...")
                        ch = phidget_class()
                        timeout_ms = self._configure_phidget_connection(ch, phidget_id_key)
                        ch.setChannel(physical_channel_index)
                        
                        ch.openWaitForAttachment(timeout_ms)
                        self._opened_physical_channels[unique_ph_key] = ch
                        # self.logger.info(f"    '{script_name}' (Device: {ch.getDeviceName()} S/N {ch.getDeviceSerialNumber()} Ch {ch.getChannel()}) opened.")
                    except PhidgetException as e:
                        self.logger.error(f"Error opening {channel_type_name[:-1]} '{script_name}' (Device ID: {phidget_id_key}, PhysChan: {physical_channel_index}): PhidgetException: {e.description} (Code: {e.code})")
                        self._opened_physical_channels[unique_ph_key] = None # Mark as failed
                    except ValueError as e: # From _configure_phidget_connection or missing keys
                        self.logger.error(f"Configuration error for '{script_name}': {e}")
                        self._opened_physical_channels[unique_ph_key] = None
                    except Exception as e:
                        self.logger.error(f"Unexpected error opening {channel_type_name[:-1]} '{script_name}': {e}")
                        self._opened_physical_channels[unique_ph_key] = None

                # Assign to self.channels, whether successful or None (if failed)
                self.channels[script_name] = self._opened_physical_channels.get(unique_ph_key)
                if not self.channels[script_name]:
                     self.logger.warning(f"    Channel '{script_name}' could not be initialized and will not be usable.")
        self.logger.info("Phidget initialization complete.")

    def _get_channel_object(self, channel_name_or_alias, expected_type=None):
        """Helper to get the Phidget object, checking its existence and type."""
        # Check if the channel_name_or_alias (which could be a string or int) exists as a key in self.channels
        if channel_name_or_alias not in self.channels:
            # If it's an integer alias, it might be defined in script_map_config but not directly in self.channels' keys
            # if it wasn't successfully initialized. The error messages below will handle this.
            # This initial check is for names/aliases that are completely unknown.
             is_defined_in_map = False
             if "outputs" in self.script_map_config and channel_name_or_alias in self.script_map_config["outputs"]:
                 is_defined_in_map = True
             elif "inputs" in self.script_map_config and channel_name_or_alias in self.script_map_config["inputs"]:
                 is_defined_in_map = True
            
             if not is_defined_in_map:
                raise NameError(f"Channel '{channel_name_or_alias}' not defined in script_channel_map_config.")
        
        ch_obj = self.channels.get(channel_name_or_alias)
        if ch_obj is None:
            # This means the channel was defined in script_map_config but failed to initialize (or was an unknown name missed above)
            raise RuntimeError(f"Channel '{channel_name_or_alias}' was defined but not successfully initialized or is unavailable.")

        if expected_type and not isinstance(ch_obj, expected_type):
            raise TypeError(f"Channel '{channel_name_or_alias}' is not a {expected_type.__name__}. Found {type(ch_obj).__name__}.")
        return ch_obj

    def set_output(self, channel_name, state):
        """
        Sets the state of a digital output channel.
        :param channel_name: The script name or alias of the output channel.
        :param state: True for ON (high), False for OFF (low).
        """
        do_ch = self._get_channel_object(channel_name, DigitalOutput)
        try:
            do_ch.setState(bool(state))
            self.logger.debug(f"Output '{channel_name}' set to {'ON' if state else 'OFF'}.")
        except PhidgetException as e:
            self.logger.error(f"Error setting state for output '{channel_name}': {e.description}")
            raise

    def on(self, channel_name):
        """Turns a digital output ON."""
        self.set_output(channel_name, True)

    def off(self, channel_name):
        """Turns a digital output OFF."""
        self.set_output(channel_name, False)

    def hold(self, channel_name, duration_ms=200):
        """
        Turns a digital output ON for a specified duration, then OFF.
        :param channel_name: The script name or alias of the output channel.
        :param duration_ms: Duration of the hold in milliseconds.
        """
        # self.logger.debug(f"Holding '{channel_name}' for {duration_ms}ms.")
        try:
            self.on(channel_name)
            time.sleep(duration_ms / 1000.0)
        finally:
            try:
                self.off(channel_name)
            except Exception as e_off: # Catch errors during off()
                 self.logger.error(f"Error turning off '{channel_name}' during hold: {e_off}")
                 # Decide if you want to re-raise e_off or the original error if one occurred in 'on'

    def press(self, channel_name):
        """
        Turns a digital output ON for a specified duration (200ms), then OFF.
        This is a convenience method, essentially self.hold(channel_name, 200).
        :param channel_name: The script name or alias of the output channel.
        """
        duration_ms = 200 # Default duration for a "press"
        self.logger.debug(f"Pressing '{channel_name}' for {duration_ms}ms.")
        # Re-use the hold logic
        self.hold(channel_name, duration_ms=duration_ms)


    def sequence(self, pin_sequence: list, press_duration_ms: float = 100, pause_duration_ms: float = 100):
        """
        Presses a sequence of digital output 'pins' (script names or aliases).

        Each pin in the sequence is turned ON for 'press_duration_ms', then OFF.
        A 'pause_duration_ms' occurs after each pin is turned OFF (before the next pin is pressed),
        except after the last pin in the sequence.

        :param pin_sequence: A list of script names or aliases for the digital output channels
                             to be pressed in order. Must not be empty.
        :param press_duration_ms: The duration (in milliseconds) each pin should be held ON.
                                  Defaults to 100ms.
        :param pause_duration_ms: The duration (in milliseconds) to pause after a pin is released
                                  and before the next pin in the sequence is pressed.
                                  Defaults to 100ms.
        :raises ValueError: If pin_sequence is empty or contains invalid types, or durations are invalid.
        :raises NameError: If a pin name/alias in the sequence is not defined.
        :raises RuntimeError: If a pin in the sequence was defined but not initialized.
        :raises TypeError: If a pin in the sequence is not a DigitalOutput.
        """
        if not pin_sequence:
            raise ValueError("pin_sequence cannot be empty.")
        if not isinstance(pin_sequence, list):
            raise ValueError("pin_sequence must be a list.")
        if not all(isinstance(pin, (str, int)) for pin in pin_sequence): # Assuming pins are identified by str or int
            raise ValueError("All items in pin_sequence must be strings or integers (script names or aliases).")

        if not (isinstance(press_duration_ms, (int, float)) and press_duration_ms >= 0):
            raise ValueError("press_duration_ms must be a non-negative number.")
        if not (isinstance(pause_duration_ms, (int, float)) and pause_duration_ms >= 0):
            raise ValueError("pause_duration_ms must be a non-negative number.")

        self.logger.info(f"Executing sequence: {pin_sequence} (Press: {press_duration_ms}ms, Pause: {pause_duration_ms}ms)")

        for i, pin_name in enumerate(pin_sequence):
            self.logger.debug(f"  Pulsing pin: '{pin_name}'")
            try:
                # The hold method already handles on, sleep, off
                self.hold(pin_name, duration_ms=press_duration_ms)
            except Exception as e:
                self.logger.error(f"Error pulsing pin '{pin_name}' in sequence: {e}")
                raise # Re-raise the exception to halt the sequence or allow higher-level handling

            # Pause after the pulse, unless it's the last pin in the sequence
            if i < len(pin_sequence) - 1:
                if pause_duration_ms > 0:
                    self.logger.debug(f"  Pausing for {pause_duration_ms}ms")
                    time.sleep(pause_duration_ms / 1000.0)
        
        self.logger.info("Sequence execution complete.")

    def read_input(self, channel_name):
        """
        Reads the state of a digital input channel.
        :param channel_name: The script name or alias of the input channel.
        :return: True if input is HIGH, False if LOW.
        """
        di_ch = self._get_channel_object(channel_name, DigitalInput)
        try:
            state = di_ch.getState()
            self.logger.debug(f"Input '{channel_name}' read as {'HIGH' if state else 'LOW'}.")
            return state
        except PhidgetException as e:
            self.logger.error(f"Error reading input '{channel_name}': {e.description}")
            raise

    def wait_for_input(self, channel_name, expected_state, timeout_s=5, poll_interval_s=0.05):
        """
        Waits for a digital input channel to reach an expected state.
        :param channel_name: The script name or alias of the input channel.
        :param expected_state: True for HIGH, False for LOW.
        :param timeout_s: Maximum time to wait in seconds.
        :param poll_interval_s: How often to check the input state.
        :return: True if state reached, False if timed out.
        """
        di_ch = self._get_channel_object(channel_name, DigitalInput)
        expected_state = bool(expected_state)
        start_time = time.time()
        self.logger.info(f"Waiting for input '{channel_name}' to be {'HIGH' if expected_state else 'LOW'} (timeout: {timeout_s}s)...")
        try:
            while time.time() - start_time < timeout_s:
                if not di_ch.getAttached():
                    self.logger.warning(f"Input '{channel_name}' detached while waiting. Checking status...")
                    # Sleep a bit longer if detached, hoping for re-attachment
                    time.sleep(poll_interval_s * 5 if poll_interval_s * 5 < 1 else 1) 
                    continue # Re-check attachment status at the start of the loop

                current_state = di_ch.getState()
                if current_state == expected_state:
                    self.logger.info(f"Input '{channel_name}' reached desired state.")
                    return True
                time.sleep(poll_interval_s)
            
            # After loop, check final state if attached
            final_state_str = "UNKNOWN (Detached)"
            if di_ch.getAttached(): # Check one last time if it reattached
                final_state_str = 'HIGH' if di_ch.getState() else 'LOW'
            self.logger.warning(f"Timeout waiting for input '{channel_name}'. Last known state: {final_state_str}")
            return False
        except PhidgetException as e:
            self.logger.error(f"PhidgetException during wait_for_input on '{channel_name}': {e.description}")
            raise # Or return False, depending on desired error handling

    def close_all(self):
        self.logger.info("Closing all Phidget channels...")
        # Iterate over a copy of items in case a close operation affects the dictionary
        for unique_ph_key, ch_obj in list(self._opened_physical_channels.items()):
            if ch_obj and ch_obj.getAttached(): # If it was successfully opened and is still attached
                (ph_id_key, ch_type, phys_ch_idx) = unique_ph_key
                try:
                    if isinstance(ch_obj, DigitalOutput):
                         ch_obj.setState(False) # Ensure outputs are off
                    ch_obj.close()
                    # self.logger.info(f"  Closed Device ID: {ph_id_key}, Type: {ch_type}, PhysChan: {phys_ch_idx}")
                except PhidgetException as e:
                    self.logger.error(f"Error closing Phidget channel ({ph_id_key}, {ch_type}, {phys_ch_idx}): {e.description}")
        self._opened_physical_channels.clear()
        self.channels.clear()
        self.logger.info("All Phidget channels closed.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_all()
