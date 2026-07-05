#!/usr/bin/env python3
"""
Structured JSON Logger — every log line is a parseable JSON object.

Fields always present:
  timestamp, level, message, logger, thread
Optional fields added by context:
  session_id, agent_path, phase, latency_ms, error

Usage:
    from runtime.observability import get_logger
    log = get_logger("pipeline")
    log.info("Session started", session_id="abc123")
    log.error("Safety blocked", agent_path="safety/input_sanitizer.md", error="XSS detected")
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any


# Standard attributes present on every logging.LogRecord — exclude these from extras
_LOGRECORD_STD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "thread": record.thread,
        }
        # Merge extra fields injected via **kwargs in StructuredLogger methods
        for key, val in record.__dict__.items():
            if key not in _LOGRECORD_STD_ATTRS:
                obj[key] = val
        # Exception info
        if record.exc_info:
            obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False, default=str)


class StructuredLogger:
    """Thin wrapper over logging.Logger with structured extras."""

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        extra = {k: v for k, v in kwargs.items() if v is not None}
        self._logger.log(level, msg, extra=extra)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, msg, **kwargs)

    def exception(self, msg: str, **kwargs: Any) -> None:
        extra = {k: v for k, v in kwargs.items() if v is not None}
        self._logger.exception(msg, extra=extra)


# Global registry of loggers
_LOGGERS: dict[str, StructuredLogger] = {}
_ROOT_CONFIGURED = False


def _setup_root() -> None:
    global _ROOT_CONFIGURED
    if _ROOT_CONFIGURED:
        return
    root = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter())
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    _ROOT_CONFIGURED = True


def get_logger(name: str) -> StructuredLogger:
    _setup_root()
    if name not in _LOGGERS:
        _LOGGERS[name] = StructuredLogger(name)
    return _LOGGERS[name]


def configure_log_level(level: str | int) -> None:
    """Set root log level by name ('DEBUG', 'INFO', etc.) or int."""
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(level)


def add_file_handler(path: str | Path) -> None:
    """Add a rotating file handler emitting JSON lines."""
    from logging.handlers import RotatingFileHandler
    fh = RotatingFileHandler(path, maxBytes=10_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(_JSONFormatter())
    logging.getLogger().addHandler(fh)
