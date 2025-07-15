import logging
import sys

# Set up proper logging with default values for all fields
def setup_logging():
    logger = logging.getLogger(None)
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers to avoid duplicates
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)

    # Create a formatter that has defaults for all fields
    formatter = logging.Formatter(
        '[%(asctime)s.%(msecs)03d] [%(levelname)s] [%(name)s] '
        '%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Set up console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
