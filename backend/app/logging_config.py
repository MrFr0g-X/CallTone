"""JSON structured logging for CallTone backend.

Why JSON: ops greps and log shippers (Loki, CloudWatch) parse JSON
natively. Plain text logs force regex-everything and break the moment
someone changes a message string.

Usage:
    from app.logging_config import configure_logging, get_logger
    configure_logging()
    log = get_logger(__name__)
    log.info("upload_received", extra={"call_id": cid, "bytes": size})

Anything passed via `extra` is merged into the JSON record. Reserved
log-record fields (msg, args, etc.) are not emitted.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any


# LogRecord built-in attributes we should NOT echo into the JSON payload.
# (Everything else in record.__dict__ is treated as user-supplied `extra`.)
_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Render each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str | None = None) -> None:
    """Install the JSON formatter on the root logger.

    Idempotent — safe to call from app startup AND from test fixtures.
    Reads `LOG_LEVEL` env var (default: INFO).
    """
    log_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    # Remove any handlers we previously installed so re-configuration
    # doesn't duplicate every line.
    for existing in list(root.handlers):
        if getattr(existing, "_calltone_json", False):
            root.removeHandler(existing)
    handler._calltone_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(log_level)

    # Tame uvicorn's default text logger so its output joins our JSON stream
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(noisy)
        lg.handlers = [handler]
        lg.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
