"""Structured JSON logging.

Every log line carries ``request_id`` and ``module`` so a single failing request
can be traced across modules: search the logs for its request id.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core import context


def module_from_logger(name: str) -> str:
    """``app.modules.orders.service`` -> ``orders``; anything else -> context value."""
    parts = name.split(".")
    if len(parts) >= 3 and parts[0] == "app" and parts[1] == "modules":
        return parts[2]
    return context.current().module


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "module": module_from_logger(record.name),
            "request_id": context.current().request_id,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # uvicorn's own access log is replaced by our request log middleware.
    logging.getLogger("uvicorn.access").disabled = True
