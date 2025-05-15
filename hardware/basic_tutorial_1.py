#!/usr/bin/env python3

import time
import logging
from phidget_io_controller import PhidgetController, enable_phidget_library_logging
from Phidget22.PhidgetException import PhidgetException
import traceback

phidget_device_configs = {
    "main_phidget": {
        "serial_number": -1,
        "open_timeout_ms": 5000
    }
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

            pc.on("usb3")
            pc.on("connect")
            time.sleep(10)
            pc.sequence(["key1", "key1", "key2", "key2", "key3", "key3", "key4", "key4", "unlock"])
            time.sleep(10)
            pc.press("lock")
            time.sleep(3)
            pc.off("connect")
            pc.off("usb3")

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