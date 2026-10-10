"""Structured JSON logging with contextvars for request/trace correlation.

Configure via ``configure_logging()`` at app startup (called from
``setup_telemetry``). Middleware sets context vars (request_id, org_id,
incident_id, trace_id) via ``bind_context()``. The JSON formatter reads
these vars and includes them in every log record.

Emitted fields: timestamp, level, logger, message, request_id, trace_id,
org_id, incident_id, safe_error_context.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.lib.audit_privacy import redact_text

# ── Context vars — set by middleware, read by the JSON formatter ────────────

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_org_id: ContextVar[str | None] = ContextVar("org_id", default=None)
_incident_id: ContextVar[str | None] = ContextVar("incident_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)

# ── Secret redaction ────────────────────────────────────────────────────────

_REDACTED_KEYS = frozenset({
    "password", "secret", "token", "api_key", "apikey",
    "access_token", "refresh_token", "authorization",
    "jwt", "jwt_secret", "minio_secret_key", "minio_access_key",
    "bearer", "credential", "private_key",
    "email", "phone", "address", "contact", "dob", "ssn", "medical_info",
})

_REDACTED = "***REDACTED***"

# Standard LogRecord attributes — everything else is "extra".
_STD_RECORD_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info",
    "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "taskName",
    "message", "asctime",
})


def bind_context(
    *,
    request_id: str | None = None,
    org_id: str | None = None,
    incident_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Set context vars for the current async task.

    Called by middleware after extracting values from the request.
    """
    if request_id is not None:
        _request_id.set(request_id)
    if org_id is not None:
        _org_id.set(org_id)
    if incident_id is not None:
        _incident_id.set(incident_id)
    if trace_id is not None:
        _trace_id.set(trace_id)


def clear_context() -> None:
    """Reset all context vars (call at response end to prevent leakage)."""
    _request_id.set(None)
    _org_id.set(None)
    _incident_id.set(None)
    _trace_id.set(None)


def _redact(value: Any) -> Any:
    """Recursively redact sensitive keys in dict/list structures."""
    if isinstance(value, dict):
        return {
            k: (_REDACTED if k.lower() in _REDACTED_KEYS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON with context var fields."""

    def format(self, record: logging.LogRecord) -> str:
        safe_error_context: str | None = None
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            safe_error_context = redact_text(f"{type(exc).__name__}: {exc}")

        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "request_id": _request_id.get(),
            "trace_id": _trace_id.get(),
            "org_id": _org_id.get(),
            "incident_id": _incident_id.get(),
            "safe_error_context": safe_error_context,
        }

        # Attach redacted "extra" fields.
        for key, val in record.__dict__.items():
            if key not in _STD_RECORD_ATTRS and key not in payload:
                if key.lower() in _REDACTED_KEYS:
                    payload[key] = _REDACTED
                else:
                    payload[key] = _redact(val)

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Configure root logger with JSON formatter. Idempotent."""
    env = os.environ.get("ENVIRONMENT", "development")
    level = logging.DEBUG if env == "development" else logging.INFO

    root = logging.getLogger()
    already = any(
        isinstance(h, logging.StreamHandler)
        and isinstance(h.formatter, JsonFormatter)
        for h in root.handlers
    )
    if already:
        return

    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    for name in ("uvicorn.access", "httpx", "httpcore", "watchfiles.main"):
        logging.getLogger(name).setLevel(logging.WARNING)


__all__ = [
    "JsonFormatter",
    "bind_context",
    "clear_context",
    "configure_logging",
]
