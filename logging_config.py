from __future__ import annotations

import contextvars
import json
import logging
import logging.handlers
from pathlib import Path

# Set by AuditMiddleware per-request; read by every log record emitted
# during that request so app logs and the audit-trail row for the same
# request can be correlated by request_id.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(log_path: str, level: int = logging.INFO) -> None:
    """Idempotent -- safe to call on every app startup (including once per
    test's TestClient lifespan) without accumulating duplicate handlers."""
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    request_id_filter = _RequestIdFilter()
    formatter = _JsonFormatter()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(request_id_filter)
    root.addHandler(console_handler)

    log_file = Path(log_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(request_id_filter)
    root.addHandler(file_handler)
