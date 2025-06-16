# Directory: utils
# Filename: logging_config.py

import logging
import sys
import os

# Default log format matching your example (without logger name for cleaner output)
DEFAULT_LOG_FORMAT = '%(asctime)s.%(msecs)03d  %(levelname)-8s  %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# --- Configuration for Specific Logger Levels ---
# Keys are logger names. 'root' is the default for unlisted loggers.
LOG_LEVEL_CONFIG = {
    "root": logging.INFO,
    "GlobalATController": logging.INFO,
    "GlobalATController.UnifiedInstance": logging.INFO,
    "GlobalATController.UnifiedInstance.Phidget": logging.INFO,
    "GlobalATController.UnifiedInstance.Camera": logging.INFO, # For detailed LED state logs
    "camera.camera_controller": logging.INFO, # If LogitechLedChecker used standalone
    "hardware.phidget_io_controller": logging.INFO, # If PhidgetController used standalone
    "controllers.unified_controller": logging.INFO, # For UnifiedController's own messages
    "Phidget22": logging.WARNING, # Default verbosity for the Phidget22 library itself
    "transitions": logging.WARNING,
    # "MyMainScript": logging.DEBUG # Example if you have another main script
}

# --- Configuration for Log Output ---
# LOG_FILE_PATH = "logs/automation_activity.log"
# ENABLE_FILE_LOGGING = True
LOG_FILE_MODE = "a" # "a" for append, "w" for overwrite

ENABLE_CONSOLE_LOGGING = True


def setup_logging(
    default_log_level=None,
    log_format=DEFAULT_LOG_FORMAT,
    date_format=DEFAULT_DATE_FORMAT,
    log_level_overrides=None,
    log_to_console=ENABLE_CONSOLE_LOGGING,
    log_file_path=None,
    log_file_mode=LOG_FILE_MODE
):
    """
    Configures the Python logging system. Call once at application start.
    """
    effective_root_level = default_log_level if default_log_level is not None else LOG_LEVEL_CONFIG.get("root", logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(effective_root_level)

    # Remove existing handlers from root to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(log_format, datefmt=date_format)
    console_handler = None # To check if it was added, for error logging during setup

    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # MODIFIED: Logic now checks if a path was provided.
    if log_file_path:
        try:
            log_dir = os.path.dirname(log_file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            file_handler = logging.FileHandler(log_file_path, mode=log_file_mode, encoding='utf-8')
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            error_msg = f"Error setting up file logging to '{log_file_path}': {e}"
            if console_handler: # Safely use root_logger if console is up
                root_logger.error(error_msg, exc_info=True)
            else:
                print(error_msg, file=sys.stderr)

    combined_log_levels = LOG_LEVEL_CONFIG.copy()
    if log_level_overrides:
        combined_log_levels.update(log_level_overrides)

    for logger_name, level in combined_log_levels.items():
        if logger_name.lower() == "root":
            continue
        try:
            numeric_level = level
            if isinstance(level, str): # Convert string level to numeric
                numeric_level = getattr(logging, level.upper(), None)
            
            if not isinstance(numeric_level, int):
                raise ValueError(f"Invalid log level: {level}")
            logging.getLogger(logger_name).setLevel(numeric_level)
        except (ValueError, AttributeError) as e:
            msg = f"Warning: Could not set log level for '{logger_name}' to '{level}': {e}"
            if console_handler:
                root_logger.warning(msg)
            else:
                print(msg, file=sys.stderr)
    
    startup_logger = logging.getLogger("LoggingConfig") # Or root_logger
    # MODIFIED: The log message now accurately reflects the file logging status.
    file_logging_status = f"'{log_file_path}'" if log_file_path else "Disabled"
    startup_logger.info(f"Logging configured. Root level: {logging.getLevelName(root_logger.level)}. Console: {log_to_console}, File: {file_logging_status}.")
    if combined_log_levels:
        startup_logger.debug(f"Specific logger levels applied: {combined_log_levels}")