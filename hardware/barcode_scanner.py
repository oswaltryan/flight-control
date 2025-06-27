# Directory: hardware
# Filename: barcode_scanner.py

import sys
import time
import threading
import logging
from pynput import keyboard
from typing import Optional, Callable, Dict

# Import platform-specific modules for flushing input
if sys.platform == "win32":
    import msvcrt
else:
    # termios works on both Linux and macOS
    import termios # pragma: no cover

logger = logging.getLogger(__name__)

class BarcodeScanner:
    """
    A controller to handle a blocking barcode scan operation.
    """
    def __init__(self, phidget_press_callback: Callable):
        """
        Initializes the BarcodeScanner.

        Args:
            phidget_press_callback: A function that can be called to trigger
                                    a Phidget output. This decouples the scanner
                                    from the full UnifiedController.
        """
        self.press_phidget_output = phidget_press_callback

    def await_scan(self, timeout: int = 1) -> Optional[str]:
        """
        Triggers scanner hardware and captures barcode input without echoing.

        This method is a blocking call that:
        1. Prompts the operator.
        2. Activates the scanner hardware trigger.
        3. Listens for fast keyboard input (the scan).
        4. Flushes the input buffer to prevent leaking characters to the terminal.
        5. Returns the scanned data.

        Args:
            timeout (int): The maximum time in seconds to wait for a scan.

        Returns:
            The scanned data as a string if successful, otherwise None.
        """

        result_container: Dict[str, Optional[str]] = {"data": None}
        scan_complete_event = threading.Event()
        
        buffer = ""
        last_key_time = time.time()
        
        def on_press(key):
            nonlocal buffer, last_key_time
            if scan_complete_event.is_set():
                return
            
            current_time = time.time()
            if current_time - last_key_time > 0.05: # 50ms keystroke timeout
                buffer = ""
            last_key_time = current_time

            if key == keyboard.Key.enter:
                if buffer:
                    result_container["data"] = buffer
                    scan_complete_event.set()
                buffer = ""
            else:
                try:
                    buffer += key.char
                except AttributeError:
                    pass
        
        listener = keyboard.Listener(on_press=on_press)
        
        # This implementation holds the trigger for the full duration of the timeout.
        trigger_thread = threading.Thread(target=self.press_phidget_output, args=("barcode", timeout * 1000))

        try:
            listener.start()
            trigger_thread.start() # Start the phidget trigger in parallel
            
            # Wait for the scan to complete or for the timeout to expire
            scan_complete_event.wait(timeout=timeout)

        finally:
            # Ensure the listener and trigger thread are cleaned up
            listener.stop()
            trigger_thread.join(timeout=1) # Give the phidget thread a moment to finish
            listener.join()
            
            logger.debug("Flushing standard input buffer...")
            try:
                if sys.platform == "win32":
                    while msvcrt.kbhit():
                        msvcrt.getch()
                else:
                    termios.tcflush(sys.stdin, termios.TCIOFLUSH)
            except Exception as e:
                logger.warning(f"Could not flush stdin buffer: {e}")
            
        scanned_data = result_container["data"]
        if scanned_data:
            logger.debug(f"Scan captured data: '{scanned_data}'")
            return scanned_data
        else:
            logger.debug("No data was captured from the barcode scan prompt (or it timed out).")
            return None