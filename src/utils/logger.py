"""Logging configuration for the application."""

import logging
import sys
from typing import Optional


def setup_logger(
    name: str = "youtube-timestamps",
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """Set up and configure a logger.

    Args:
        name: Logger name
        level: Logging level (default: INFO)
        log_file: Optional file path to write logs to

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Clear any existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Default logger instance
logger = setup_logger()
