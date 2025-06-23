# Directory: utils/
# Filename: pin_generator.py

import random
import string
import collections
import copy
from typing import Any, Optional, Tuple

# The template is a constant for the class.
PIN_TEMPLATE = {
    'string': '',
    'sequence': [],
    'digit': 0,
    'valid': False,
    'reason': '',
    'keypress': {}
}

class PINGenerator:
    """
    A class to generate valid and specific types of invalid PINs for testing.
    It holds a reference to the DUT model to ensure checks are always up-to-date.
    """
    def __init__(self, dut_model: Any):
        """
        Initializes the generator with a reference to the device-under-test model.
        """
        if not hasattr(dut_model, 'self_destruct_pin'):
            raise TypeError("The provided dut_model must have a 'self_destruct_pin' attribute.")
        self.dut_model = dut_model

    def _is_pin_invalid(self, pin_string: str) -> Tuple[bool, str]:
        """Checks if a PIN is invalid based on the latest DUT state."""
        current_sdp_list = self.dut_model.self_destruct_pin
        current_sdp_str = "".join(current_sdp_list) if current_sdp_list else None
        
        if current_sdp_str and pin_string == current_sdp_str:
            return True, "matches Self-Destruct PIN"
        if len(set(pin_string)) == 1:
            return True, "is repeating"
        
        # This check is now redundant due to the numerical generation, but it's
        # a good safeguard to keep in the validation function.
        all_digits = "0123456789"
        reversed_digits = "9876543210"
        if pin_string in all_digits or pin_string in reversed_digits:
            return True, "is sequential"

        return False, "is valid"

    def _populate_pin_info(self, pin_str: str) -> dict:
        """Helper function to create the final dictionary from a PIN string."""
        pin_info = copy.deepcopy(PIN_TEMPLATE)
        is_invalid, reason = self._is_pin_invalid(pin_str)
        
        pin_info.update({
            'string': pin_str,
            'digit': len(pin_str),
            'valid': not is_invalid,
            'reason': reason,
            'sequence': [f"key{d}" for d in pin_str] + ["unlock"]
        })

        pin_info['keypress'] = dict(collections.Counter(pin_info['sequence']))
        return pin_info

    def generate_valid_pin(self, length: int) -> dict:
        """
        Generates a random PIN of a given length that is GUARANTEED to be valid
        against the current DUT state.
        """
        if not 2 <= length <= 16:
            raise ValueError("PIN length must be between 2 and 16.")
        
        for _ in range(500): # Safety break
            pin_str = ''.join(random.choices(string.digits, k=length))
            if not self._is_pin_invalid(pin_str)[0]:
                return self._populate_pin_info(pin_str)
        
        raise RuntimeError(f"Could not generate a valid PIN of length {length} after 500 attempts.")

    def generate_invalid_pin(self, invalid_type: str, length: int, **kwargs) -> dict:
        """
        Generates a specifically invalid PIN based on the requested type.
        """
        pin_str = ""
        if invalid_type == "repeating":
            digit = str(random.randint(0, 9))
            pin_str = digit * length
        
        elif invalid_type == "sequential":
            if not 2 <= length <= 10:
                raise ValueError("Sequential PIN length must be between 2 and 10.")
            
            if 'reverse' in kwargs:
                is_reverse = kwargs['reverse']
            else:
                is_reverse = random.choice([True, False])
            
            if not is_reverse:
                max_start_digit = 10 - length
                start_digit = random.randint(0, max_start_digit)
                pin_list = [str(start_digit + i) for i in range(length)]
                pin_str = "".join(pin_list)
            else:
                min_start_digit = length - 1
                start_digit = random.randint(min_start_digit, 9)
                pin_list = [str(start_digit - i) for i in range(length)]
                pin_str = "".join(pin_list)
            
        else:
            raise ValueError(f"Invalid type '{invalid_type}'. Choose from 'repeating' or 'sequential'.")
        
        return self._populate_pin_info(pin_str)

    def get_self_destruct_pin_info(self) -> Optional[dict]:
        """
        Retrieves the current Self-Destruct PIN and formats it as a PIN info object.
        """
        current_sdp_list = self.dut_model.self_destruct_pin
        if not current_sdp_list:
            return None
        
        pin_str = "".join(current_sdp_list)
        return self._populate_pin_info(pin_str)