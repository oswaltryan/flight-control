#!/usr/bin/env python3

import time
import logging
from phidget_io_controller import PhidgetController, enable_phidget_library_logging # DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG is now internal to phidget_manager
from Phidget22.PhidgetException import PhidgetException
import traceback

# The script_channel_map_config is NO LONGER defined here.
# It will use the DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG from phidget_manager.py
# unless explicitly overridden when creating PhidgetController.

# !!! IMPORTANT: DEFINE YOUR PHIDGET DEVICE CONNECTION DETAILS HERE !!!
# This dictionary maps the 'phidget_id' (used in DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG)
# to actual Phidget connection parameters.
phidget_device_configs = {
    "main_phidget": {
        "serial_number": -1,  # <--- REPLACE with your Phidget's serial number, or -1 for any.
                              # e.g., 684321 (for a 1018_2B, REL1100_0, DAQ1400_0 etc.)
        "open_timeout_ms": 5000
        
        # --- Example: VINT Hub Port Device ---
        # "is_hub_port_device": True,
        # "hub_port": 0,
        # "serial_number": 700000, # Serial number of the VINT device itself (if it has one)
        # "parent_serial_number": 600000, # Serial number of the VINT Hub (e.g., HUB0000_0)
        # "open_timeout_ms": 5000

        # --- Example: Network Phidget (e.g., on PhidgetSBC) ---
        # "is_remote": True,
        # "server_name": "phidgetsbc.local", # Or IP address
        # "password": "", # If server is password protected
        # "serial_number": -1, # Serial of the specific device on the remote server, or -1 for any
        # "open_timeout_ms": 10000
    },
    # --- Example: Configuration for a second Phidget device (if your map uses it) ---
    # "safety_interface": {
    #     "serial_number": 987654, # Serial of the second Phidget
    #     "open_timeout_ms": 3000
    # }
}

def setup_logger():
    logger = logging.getLogger("PhidgetApp")
    logger.setLevel(logging.DEBUG) 
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

def main():
    app_logger = setup_logger()
    
    # enable_phidget_library_logging(level="INFO") 

    if phidget_device_configs.get("main_phidget", {}).get("serial_number", 0) == -1: # Make check safer
        app_logger.warning("="*50)
        app_logger.warning("!!! 'main_phidget' serial number is -1 in `phidget_device_configs`. !!!")
        app_logger.warning("!!! The script will try to open the first available Phidget matching criteria. !!!")
        app_logger.warning("!!! Please update `phidget_device_configs` with your specific details for reliability. !!!")
        app_logger.warning("="*50)

    try:
        # Create PhidgetController. It will use DEFAULT_SCRIPT_CHANNEL_MAP_CONFIG
        # from phidget_manager.py because we are not passing a script_map_config argument.
        with PhidgetController(device_configs=phidget_device_configs, logger=app_logger) as pc:
            app_logger.info("\n--- Starting Phidget Interaction Test ---")

            # Example: Test outputs
            app_logger.info("\nTesting outputs...")
            
            app_logger.info("Holding 'key0' (alias 'unlock')")
            pc.hold("key0", 500)
            time.sleep(0.5)

            app_logger.info("Turning 'key1' (alias 1) ON")
            pc.on("key1") # or pc.on(1)
            time.sleep(1)
            app_logger.info("Turning 'key1' OFF")
            pc.off(1) 
            time.sleep(0.5)

            # ... (rest of your test logic from previous example) ...

            app_logger.info("Holding 'lock' relay")
            pc.hold("lock", 300)
            time.sleep(0.5)

            app_logger.info("Holding 'hold' (alias 12) relay")
            pc.hold(12, 300)
            time.sleep(0.5)
            
            app_logger.info("Holding 'connect' (mapped to key5)")
            pc.hold("connect", 300)
            time.sleep(0.5)

            app_logger.info("Holding 'usb3' (mapped to key4)")
            pc.hold("usb3", 300)
            time.sleep(0.5)

            app_logger.info("Pressing 'key2' relay")
            pc.hold("key1")
            time.sleep(0.5)

            app_logger.info("Pressing 'key2' relay")
            pc.hold("key2")
            time.sleep(0.5)

            app_logger.info("\nTesting inputs...")
            # Check if 'prod_inserted' is actually available before trying to use it
            # This checks if it was successfully initialized by the controller
            if "prod_inserted" in pc.channels and pc.channels["prod_inserted"] is not None:
                prod_state = pc.read_input("prod_inserted")
                app_logger.info(f"Initial 'prod_inserted' state: {'HIGH' if prod_state else 'LOW'}")
            else:
                app_logger.warning("Skipping 'prod_inserted' test as channel is not available or configured correctly.")

            if "power_on" in pc.channels and pc.channels["power_on"] is not None:
                power_state = pc.read_input("power_on")
                app_logger.info(f"Initial 'power_on' state: {'HIGH' if power_state else 'LOW'}")
            else:
                app_logger.warning("Skipping 'power_on' test as channel is not available or configured correctly.")


            app_logger.info("\n--- Phidget Interaction Test Complete ---")

    except PhidgetException as e:
        app_logger.error(f"A PhidgetException occurred: {e.description} (Code: {e.code})")
        app_logger.error(traceback.format_exc())
    except NameError as e:
        app_logger.error(f"A NameError occurred (likely an undefined channel name used): {e}")
        app_logger.error(traceback.format_exc())
    except RuntimeError as e:
        app_logger.error(f"A RuntimeError occurred (likely an uninitialized/failed channel): {e}")
        app_logger.error(traceback.format_exc())
    except Exception as e:
        app_logger.error(f"An unexpected error occurred: {e}")
        app_logger.error(traceback.format_exc())
    finally:
        app_logger.info("\nApplication finished.")

if __name__ == "__main__":
    main()