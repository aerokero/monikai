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
import os
from pathlib import Path
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


def get_application_log_path() -> Path:
    """Return the log file path used by the diagnostics API.

    The native Odysseus backend uses ``ODYSSEUS_DATA_DIR`` when it is set and
    otherwise keeps its data below ``backend/odysseus/data``.  Keep that
    resolution in one place so the writer and the reader cannot silently use
    different directories.
    """
    configured_data_dir = os.environ.get("ODYSSEUS_DATA_DIR")
    data_dir = (
        Path(configured_data_dir)
        if configured_data_dir
        else Path(__file__).resolve().parent / "odysseus" / "data"
    )
    return data_dir / "logs" / "app.log"


def setup_logging(
    level: str = "INFO",
    json_mode: bool = False,
    log_file: str | os.PathLike[str] | None = None,
) -> None:
    """Configure root logger.

    Parameters
    ----------
    level:     Standard log level name ("DEBUG", "INFO", "WARNING", …).
    json_mode: Emit JSON lines instead of human-readable text.
    log_file:  Optional path for the rotating application log file.
    """
    normalized_level = str(level or "INFO").upper()
    log_path = Path(log_file) if log_file else get_application_log_path()
    file_logging_error = None

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        include_file_handler = True
    except OSError as exc:
        include_file_handler = False
        file_logging_error = exc

    handlers: dict[str, dict[str, Any]] = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if json_mode else "plain",
            "stream": "ext://sys.stdout",
        },
    }
    active_handlers = ["console"]

    if include_file_handler:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "file",
            "filename": str(log_path),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "encoding": "utf-8",
            "delay": True,
        }
        active_handlers.append("file")

    logger_config = {
        "aiosqlite": {"level": "WARNING"},
        "websockets": {"level": "WARNING"},
        "asyncio": {"level": "WARNING"},
    }

    # Uvicorn configures these loggers separately from the root logger. Bind
    # them to the same handlers so request/access output also appears in the
    # viewer instead of only in ``docker logs``.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger_config[logger_name] = {
            "level": normalized_level,
            "handlers": active_handlers,
            "propagate": False,
        }

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {
                "format": "%(asctime)s %(levelname)-8s %(name)-30s %(message)s",
                "datefmt": "%H:%M:%S",
            },
            # The UI uses the explicit `` - LEVEL - `` markers for local
            # level filtering. Keep the console format backwards compatible.
            "file": {
                "format": "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
                "datefmt": "%H:%M:%S",
            },
            "json": {
                "()": _JSONFormatter,
            },
        },
        "handlers": handlers,
        "root": {
            "level": normalized_level,
            "handlers": active_handlers,
        },
        "loggers": logger_config,
    }

    try:
        logging.config.dictConfig(config)
    except (OSError, ValueError) as exc:
        # A read-only or unavailable data volume must not prevent MonikAI from
        # starting. Fall back to stdout, while making the reason visible there.
        if not include_file_handler:
            raise

        handlers.pop("file", None)
        active_handlers[:] = ["console"]
        for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            logger_config[logger_name]["handlers"] = active_handlers
        config["handlers"] = handlers
        config["root"]["handlers"] = active_handlers
        logging.config.dictConfig(config)
        file_logging_error = exc

    if file_logging_error:
        logging.getLogger(__name__).warning(
            "Application file logging unavailable at %s: %s",
            log_path,
            file_logging_error,
        )
