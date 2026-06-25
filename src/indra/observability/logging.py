"""Structured JSON logging for Indra.

Uses the stdlib ``logging`` module with a JSON formatter so logs are
machine-parseable without pulling in an extra dependency. All Indra
modules should call :func:`get_logger` rather than ``logging.getLogger``
directly so a consistent format is guaranteed.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Renders each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "indra_extra", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("indra")
    root.setLevel(level.upper())
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the ``indra`` root logger."""
    configure_logging()
    return logging.getLogger(f"indra.{name}")


def log_with(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Log ``message`` with structured ``fields`` attached as JSON."""
    logger.log(level, message, extra={"indra_extra": fields})
