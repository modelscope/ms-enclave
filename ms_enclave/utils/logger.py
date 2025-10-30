# Copyright (c) Alibaba, Inc. and its affiliates.
import importlib.util
import logging
import os
import sys
import threading
from types import MethodType
from typing import Optional

init_loggers = {}

# ANSI color helpers for levelname coloring in TTY streams
RESET = '\033[0m'
LEVEL_COLORS = {
    'DEBUG': '\033[34m',  # Blue
    'INFO': '\033[32m',  # Green
    'WARNING': '\033[33m',  # Yellow
    'ERROR': '\033[31m',  # Red
    'CRITICAL': '\033[35m',  # Magenta
}

logger_format = logging.Formatter('[%(levelname)s:%(name)s] %(message)s')

info_set = set()
warning_set = set()
_once_lock = threading.Lock()


class ColorFormatter(logging.Formatter):
    """Formatter that colors only the levelname for TTY streams."""

    def __init__(self, fmt: str, datefmt: Optional[str] = None, style: str = '%', use_color: bool = True) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        try:
            if self.use_color:
                color = LEVEL_COLORS.get(record.levelname, '')
                if color:
                    record.levelname = f'{color}{record.levelname}{RESET}'
            return super().format(record)
        finally:
            record.levelname = original_levelname


def _should_use_color(stream) -> bool:
    """Decide if we should use colors for a given stream based on TTY and env."""
    # Respect NO_COLOR to disable, FORCE_COLOR or LOG_COLOR=1 to force enable
    if os.getenv('NO_COLOR'):
        return False
    if os.getenv('FORCE_COLOR') or os.getenv('LOG_COLOR') == '1':
        return True
    try:
        return hasattr(stream, 'isatty') and stream.isatty()
    except Exception:
        return False


def info_once(self: logging.Logger, msg: str, *args, **kwargs) -> None:
    hash_id = kwargs.pop('hash_id', msg)
    with _once_lock:
        if hash_id in info_set:
            return
        info_set.add(hash_id)
    self.info(msg, *args, **kwargs)


def warning_once(self: logging.Logger, msg: str, *args, **kwargs) -> None:
    hash_id = kwargs.pop('hash_id', msg)
    with _once_lock:
        if hash_id in warning_set:
            return
        warning_set.add(hash_id)
    self.warning(msg, *args, **kwargs)


def _update_handler_levels(logger: logging.Logger, log_level: int) -> None:
    """Set all handler levels to the given log level."""
    for handler in logger.handlers:
        handler.setLevel(log_level)


def get_logger(log_file: Optional[str] = None, log_level: Optional[int] = None, file_mode: str = 'w'):
    """Get project logger configured with colored console output and optional file output.

    Args:
        log_file: Log filename. If specified, a FileHandler will be added to the logger.
        log_level: Logging level. If None, resolve from env LOG_LEVEL (default INFO).
        file_mode: Mode to open the log file if log_file is provided (default 'w').
    """
    if log_level is None:
        env_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        log_level = getattr(logging, env_level, logging.INFO)

    logger_name = __name__.split('.')[0]
    logger = logging.getLogger(logger_name)
    logger.propagate = False

    # If logger is already initialized, just ensure file handler and update handler levels.
    if logger_name in init_loggers:
        add_file_handler_if_needed(logger, log_file, file_mode, log_level)
        _update_handler_levels(logger, log_level)
        return logger

    # Handle duplicate logs to the console (PyTorch DDP root StreamHandler quirk)
    for handler in logger.root.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(logging.ERROR)

    # Console handler with colorized levelname when appropriate
    stream_handler = logging.StreamHandler(stream=sys.stderr)
    use_color = _should_use_color(getattr(stream_handler, 'stream', sys.stderr))
    color_fmt = ColorFormatter('[%(levelname)s:%(name)s] %(message)s', use_color=use_color)
    stream_handler.setFormatter(color_fmt)
    stream_handler.setLevel(log_level)
    logger.addHandler(stream_handler)

    # Optional file handler (no color)
    if log_file is not None:
        file_handler = logging.FileHandler(log_file, file_mode)
        file_handler.setFormatter(logger_format)
        file_handler.setLevel(log_level)
        logger.addHandler(file_handler)

    logger.setLevel(log_level)
    init_loggers[logger_name] = True
    logger.info_once = MethodType(info_once, logger)
    logger.warning_once = MethodType(warning_once, logger)
    return logger


logger = get_logger()


def add_file_handler_if_needed(logger: logging.Logger, log_file: Optional[str], file_mode: str, log_level: int) -> None:
    """Attach a FileHandler for the given log_file if not already present.

    Ensures:
    - Only one FileHandler per log file path.
    - FileHandler uses the standard, uncolored formatter.
    - FileHandler level matches the requested log_level.
    """
    if log_file is None:
        return

    # Only worker 0 writes logs when torch DDP is present
    if importlib.util.find_spec('torch') is not None:
        is_worker0 = int(os.getenv('LOCAL_RANK', -1)) in {-1, 0}
    else:
        is_worker0 = True

    if not is_worker0:
        return

    abs_path = os.path.abspath(log_file)
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            # If a handler is already logging to the same file, just update it
            if getattr(handler, 'baseFilename', None) == abs_path:
                handler.setFormatter(logger_format)
                handler.setLevel(log_level)
                return

    # Add a new file handler for this log file
    file_handler = logging.FileHandler(abs_path, file_mode)
    file_handler.setFormatter(logger_format)
    file_handler.setLevel(log_level)
    logger.addHandler(file_handler)
