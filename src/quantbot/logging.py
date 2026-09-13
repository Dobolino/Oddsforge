"""Logging setup for QuantBot.

Uses :mod:`rich` for readable console output in development and a plain JSON
formatter for production. Call :func:`configure_logging` once at process start.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from rich.logging import RichHandler

from quantbot.config import Settings, get_settings

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Minimal structured JSON formatter for production logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Attach any structured extras passed via ``logger.info(..., extra={...})``.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_KEYS and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


_RESERVED_LOG_KEYS = set(
    logging.makeLogRecord({}).__dict__.keys()
) | {"message", "asctime"}


def configure_logging(settings: Settings | None = None, *, force: bool = False) -> None:
    """Configure the root logger.

    Idempotent: subsequent calls are ignored unless ``force`` is ``True``.
    """

    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    settings = settings or get_settings()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level)

    handler: logging.Handler
    if settings.log_json:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
    else:
        handler = RichHandler(rich_tracebacks=True, show_path=False, markup=False)
        handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))

    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger, configuring logging on first use."""

    configure_logging()
    return logging.getLogger(name)
