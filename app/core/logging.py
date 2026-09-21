"""Auralis Structured Logging Configuration."""

import logging
import sys


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configures structured console logging with timestamp, level, and logger name."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Avoid duplicate handlers if setup_logging is called multiple times
    if not root_logger.handlers:
        root_logger.addHandler(handler)
    else:
        root_logger.handlers[0] = handler

    root_logger.setLevel(numeric_level)
    return logging.getLogger("auralis")


logger = setup_logging()
