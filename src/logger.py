import logging
import os
from datetime import datetime

# --- Centralized Logger ---

# Create the logs directory if it doesn't exist.
LOGS_DIR = 'logs'
os.makedirs(LOGS_DIR, exist_ok=True)

# Generate a unique, timestamped log file name for each run.
LOG_FILENAME = datetime.now().strftime(f"{LOGS_DIR}/run-%Y-%m-%d_%H-%M-%S.log")

def setup_logger():
    """
    Sets up a centralized logger that writes to a timestamped file.
    Returns the configured logger instance.
    """
    # Get the root logger.
    logger = logging.getLogger()
    logger.setLevel(logging.INFO) # Set the minimum level of messages to capture.

    # Avoid adding multiple handlers if this function is called more than once.
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create a handler to write log messages to our timestamped file.
    file_handler = logging.FileHandler(LOG_FILENAME)
    file_handler.setLevel(logging.INFO)

    # Create a handler to also print log messages to the console.
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)

    # Define the format for our log messages.
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    # Add the configured handlers to the logger.
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger

# Create a single logger instance to be imported by other modules.
log = setup_logger()

# Log the creation of the log file itself.
log.info(f"Logging initialized. Log file created at: {LOG_FILENAME}")