import logging
import sys


def setup_logger(name: str) -> logging.Logger:
    """
    Sets up a standardized logging configuration for the ETL pipeline modules.

    Args:
        name: Name of the logger module.

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - [%(name)s] %(message)s"
        )

        # Console Handler outputting to stdout
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Prevent logs from double-bubbling to the root logger if configured elsewhere
        logger.propagate = False

    return logger
