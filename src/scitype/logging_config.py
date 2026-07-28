"""Minimal rotating-file logging for the background Windows launcher."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path


LOGGER_NAME = "scitype"
LOG_DIRECTORY_NAME = "SciType"
LOG_FILE_NAME = "scitype.log"
DEFAULT_MAX_BYTES = 512 * 1024
DEFAULT_BACKUP_COUNT = 3


class LogConfigurationError(RuntimeError):
    """Raised when SciType cannot determine or initialize its log path."""


def get_log_path(
    local_app_data: str | os.PathLike[str] | None = None,
) -> Path:
    """Return ``LOCALAPPDATA/SciType/scitype.log``."""
    base_directory = (
        os.fspath(local_app_data)
        if local_app_data is not None
        else os.environ.get("LOCALAPPDATA")
    )
    if not base_directory:
        raise LogConfigurationError(
            "无法确定 LOCALAPPDATA，不能初始化 SciType 日志",
        )

    return Path(base_directory, LOG_DIRECTORY_NAME, LOG_FILE_NAME)


def configure_logging(
    log_path: str | os.PathLike[str] | None = None,
    *,
    logger_name: str = LOGGER_NAME,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    """Configure one UTF-8 rotating log without console or key-event output."""
    path = Path(log_path) if log_path is not None else get_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    except OSError as error:
        raise LogConfigurationError(
            f"无法初始化日志“{path}”：{error}",
        ) from error

    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ),
    )

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for existing_handler in list(logger.handlers):
        logger.removeHandler(existing_handler)
        existing_handler.close()
    logger.addHandler(handler)
    return logger


def close_logging(logger: logging.Logger) -> None:
    """Flush and close handlers installed on one SciType logger."""
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
