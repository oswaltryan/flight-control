# File: utils/config/keypad_layouts.py

"""
Centralized definition for keypad layouts to be used across the automation framework.
"""

KEYPAD_LAYOUTS = {
    'secure': [
        ['key1', 'key2'], ['key3', 'key4'], ['key5', 'key6'],
        ['key7', 'key8'], ['key9', 'key0'], ['lock', 'unlock']
    ],
    'standard': [
        ['key1', 'key2', 'key3'], ['key4', 'key5', 'key6'],
        ['key7', 'key8', 'key9'], ['lock', 'key0', 'unlock']
    ]
}