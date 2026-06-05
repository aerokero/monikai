"""Structured logging setup for MonikAI v2.

Two modes:
  - plain (default): human-readable, coloured-friendly format for dev
  - json: machine-readable JSON lines for prod / log aggregation

Call setup_logging() once at application startup before any modules log.

Usage:
    from backend.logging_config import setup_logging
    setup_logging(level="INFO", json_mode=False)
"""

from __future__ import annotations

import json
import logging
import logging.config
from typing import Any


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            entry["stack"] = self.formatStack(record.stack_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: str = "INFO", json_mode: bool = False) -> None:
    """Configure root logger.

    Parameters
    ----------
    level:     Standard log level name ("DEBUG", "INFO", "WARNING", …).
    json_mode: Emit JSON lines instead of human-readable text.
    """
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {
                "format": "%(asctime)s %(levelname)-8s %(name)-30s %(message)s",
                "datefmt": "%H:%M:%S",
            },
            "json": {
                "()": _JSONFormatter,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json" if json_mode else "plain",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
        # Quieten noisy third-party loggers.
        "loggers": {
            "aiosqlite": {"level": "WARNING"},
            "websockets": {"level": "WARNING"},
            "asyncio": {"level": "WARNING"},
        },
    })
