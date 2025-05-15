# Directory: hardware
# Filename: basic_tutorial_1.py

#!/usr/bin/env python3

import time
import logging # Keep for PhidgetException, NameError etc. if they use logging indirectly, or for type hints.
from phidget_io_controller import PhidgetController
from Phidget22.PhidgetException import PhidgetException
import traceback

# setup_logger function has been removed from here.
# It's now handled internally by PhidgetController.

def main(): 
    pc = None # Define pc outside try so it's available in finally

    try:
        with PhidgetController() as pc:
            pc.logger.info("\n--- Starting Phidget Interaction Test ---")

            # Example: Test outputs
            pc.logger.info("\nTesting outputs...")

            pc.on("usb3")
            pc.on("connect")
            time.sleep(10)
            pc.sequence(["key1", "key1", "key2", "key2", "key3", "key3", "key4", "key4", "unlock"])
            time.sleep(10)
            pc.press("lock")
            time.sleep(3)
            pc.off("connect")
            pc.off("usb3")

            pc.logger.info("\n--- Phidget Interaction Test Complete ---")

    except PhidgetException as e:
        # If pc was initialized, use its logger. Otherwise, fallback to a temporary basic logger.
        # If __init__ fails, pc will be None (or its previous value).
        logger_to_use = None
        if pc and hasattr(pc, 'logger') and pc.logger:
            logger_to_use = pc.logger
        else:
            logger_to_use = logging.getLogger("PhidgetAppFallback")
            if not logger_to_use.hasHandlers(): # Configure fallback logger if needed
                logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        logger_to_use.error(f"A PhidgetException occurred: {e.description} (Code: {e.code})")
        logger_to_use.error(traceback.format_exc())
    except NameError as e:
        logger_to_use = None
        if pc and hasattr(pc, 'logger') and pc.logger:
            logger_to_use = pc.logger
        else:
            logger_to_use = logging.getLogger("PhidgetAppFallback")
            if not logger_to_use.hasHandlers():
                logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        logger_to_use.error(f"A NameError occurred (likely an undefined channel name used): {e}")
        logger_to_use.error(traceback.format_exc())
    except RuntimeError as e:
        logger_to_use = None
        if pc and hasattr(pc, 'logger') and pc.logger:
            logger_to_use = pc.logger
        else:
            logger_to_use = logging.getLogger("PhidgetAppFallback")
            if not logger_to_use.hasHandlers():
                logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        logger_to_use.error(f"A RuntimeError occurred (likely an uninitialized/failed channel): {e}")
        logger_to_use.error(traceback.format_exc())
    except Exception as e:
        logger_to_use = None
        if pc and hasattr(pc, 'logger') and pc.logger:
            logger_to_use = pc.logger
        else:
            logger_to_use = logging.getLogger("PhidgetAppFallback")
            if not logger_to_use.hasHandlers(): # Check and configure if no handlers
                # For general exceptions, set up a basic config if no handlers exist for the fallback.
                # This ensures the message is seen.
                _handler = logging.StreamHandler()
                _formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                _handler.setFormatter(_formatter)
                logger_to_use.addHandler(_handler)
                logger_to_use.setLevel(logging.ERROR) # Ensure level is appropriate for errors
                logger_to_use.propagate = False # Avoid duplicate messages if root logger is also configured

        logger_to_use.error(f"An unexpected error occurred: {e}") # This will use PhidgetAppFallback if pc.logger not set
        logger_to_use.error(traceback.format_exc())
    finally:
        logger_to_use = None
        if pc and hasattr(pc, 'logger') and pc.logger:
            logger_to_use = pc.logger
        else:
            logger_to_use = logging.getLogger("PhidgetAppFallback")
            # Ensure the fallback logger for 'finally' is configured to show INFO
            if not logger_to_use.hasHandlers():
                _handler = logging.StreamHandler()
                _formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                _handler.setFormatter(_formatter)
                logger_to_use.addHandler(_handler)
                logger_to_use.setLevel(logging.INFO) # Set level for the logger
                _handler.setLevel(logging.INFO)      # Set level for the handler
                logger_to_use.propagate = False

        logger_to_use.info("\nApplication finished.") # This will use PhidgetAppFallback if pc.logger not set

if __name__ == "__main__":
    main()