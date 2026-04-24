"""
Logging configuration for the Zotero RAG Assistant.

Reads LOG_LEVEL and LOG_FILE from the environment (via .env) and sets up
a root logger with both a console handler and an optional file handler.
Call get_logger(__name__) in any module to get a properly configured logger.
"""

import logging
from pathlib import Path

from src.config import settings

_LOG_LEVEL: str = settings.log_level.upper()
_LOG_FILE: str | None = settings.log_file

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure() -> None:
    """Set up handlers on the root logger once."""
    global _configured
    if _configured:
        return

    level = getattr(logging, _LOG_LEVEL, logging.INFO)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler (optional)
    if _LOG_FILE:
        log_path = Path(_LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger, initialising logging on first call.

    Args:
        name: Typically __name__ of the calling module.

    Returns:
        A configured :class:`logging.Logger` instance.
    """
    _configure()
    return logging.getLogger(name)
