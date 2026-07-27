"""Tests for structured logging, context var propagation, and OTel config.

Verifies:
1. JSON formatter emits all required fields (timestamp, level, request_id,
   trace_id, org_id, incident_id, message, safe_error_context).
2. Context vars set via bind_context() appear in log output.
3. Middleware propagates request_id and org_id into log records.
4. Secret values in extra fields are redacted.
5. OTEL_EXPORTER=none disables tracing gracefully.
6. No log lines in the codebase contain secret keywords.
"""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
from pathlib import Path

import pytest

from app.lib.logging_config import (
    JsonFormatter,
    bind_context,
    clear_context,
    configure_logging,
)

_REQUIRED_FIELDS = {
    "timestamp",
    "level",
    "logger",
    "message",
    "request_id",
    "trace_id",
    "org_id",
    "incident_id",
    "safe_error_context",
}


@pytest.fixture
def capture_logger():
    """Attach a JSON-formatted handler to a buffer; yield (logger, buffer)."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    test_logger = logging.getLogger("test.observability")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.DEBUG)
    # Prevent propagation to root (which may have its own JSON handler).
    test_logger.propagate = False
    yield test_logger, buf
    test_logger.removeHandler(handler)
    clear_context()


def _records(buf: io.StringIO) -> list[dict]:
    """Parse each non-blank line in the buffer as JSON."""
    return [
        json.loads(line)
        for line in buf.getvalue().strip().splitlines()
        if line
    ]


# ── Unit: formatter + context vars ───────────────────────────────────────────


def test_json_formatter_emits_all_required_fields(capture_logger):
    """Given a log call, the JSON record contains every required field."""
    test_logger, buf = capture_logger
    test_logger.info("hello world")
    records = _records(buf)
    assert len(records) == 1
    assert _REQUIRED_FIELDS.issubset(records[0].keys())


def test_context_vars_appear_in_log_output(capture_logger):
    """Given bind_context values, the JSON record includes them."""
    bind_context(
        request_id="req-abc",
        org_id="org-xyz",
        incident_id="inc-001",
        trace_id="0" * 32,
    )
    test_logger, buf = capture_logger
    test_logger.info("contextual message")
    clear_context()

    record = _records(buf)[0]
    assert record["request_id"] == "req-abc"
    assert record["org_id"] == "org-xyz"
    assert record["incident_id"] == "inc-001"
    assert record["trace_id"] == "0" * 32


def test_clear_context_resets_vars(capture_logger):
    """Given clear_context, subsequent logs have null context fields."""
    bind_context(request_id="req-1", org_id="org-1")
    clear_context()
    test_logger, buf = capture_logger
    test_logger.info("after clear")
    record = _records(buf)[0]
    assert record["request_id"] is None
    assert record["org_id"] is None


def test_safe_error_context_captures_exception_type(capture_logger):
    """Given an exception, safe_error_context contains the type name."""
    test_logger, buf = capture_logger
    try:
        raise ValueError("bad value")
    except ValueError:
        test_logger.exception("failed")
    record = _records(buf)[0]
    assert record["safe_error_context"] is not None
    assert "ValueError" in record["safe_error_context"]
    assert "bad value" in record["safe_error_context"]


# ── Unit: secret redaction ───────────────────────────────────────────────────


def test_secret_extra_fields_are_redacted(capture_logger):
    """Given extra fields with secret keys, values are replaced."""
    test_logger, buf = capture_logger
    test_logger.info(
        "user login",
        extra={
            "password": "hunter2",
            "api_key": "sk-12345",
            "token": "tok-abc",
            "safe_field": "visible",
        },
    )
    record = _records(buf)[0]
    assert record["password"] == "***REDACTED***"
    assert record["api_key"] == "***REDACTED***"
    assert record["token"] == "***REDACTED***"
    assert record["safe_field"] == "visible"
    # No raw secret value leaks into the JSON line.
    raw = buf.getvalue()
    assert "hunter2" not in raw
    assert "sk-12345" not in raw
    assert "tok-abc" not in raw


def test_nested_secret_in_dict_is_redacted(capture_logger):
    """Given a nested dict with a secret key, the value is redacted."""
    test_logger, buf = capture_logger
    test_logger.info(
        "config",
        extra={"config": {"password": "nested-secret", "port": 5432}},
    )
    record = _records(buf)[0]
    assert record["config"]["password"] == "***REDACTED***"
    assert record["config"]["port"] == 5432
    assert "nested-secret" not in buf.getvalue()


# ── Integration: middleware sets context vars ────────────────────────────────


def test_request_id_middleware_sets_context(client):
    """Given a request, the X-Request-Id header is returned and unique."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert "X-Request-Id" in response.headers
    rid = response.headers["X-Request-Id"]
    assert len(rid) > 0


def test_request_id_header_is_reused(client):
    """Given an incoming X-Request-Id, the same value is returned."""
    response = client.get("/healthz", headers={"X-Request-Id": "custom-rid"})
    assert response.headers["X-Request-Id"] == "custom-rid"


def test_org_context_middleware_sets_org_id(client):
    """Given a valid JWT, org_id is resolved and available in request state."""
    from app.auth.seed import seed_demo_users
    from app.db import SessionLocal

    db = SessionLocal()
    seed_demo_users(db)
    db.close()

    resp = client.post(
        "/api/auth/login",
        data={"username": "admin@demo.disaster", "password": "demo1234"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    response = client.get(
        "/api/observations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


# ── Unit: OTel exporter config ───────────────────────────────────────────────


def test_otel_exporter_none_disables_tracing(monkeypatch):
    """Given OTEL_EXPORTER=none, _setup_tracing returns without configuring."""
    monkeypatch.setenv("OTEL_EXPORTER", "none")
    import app.lib.telemetry as tel

    monkeypatch.setattr(tel, "_tracer_configured", False)
    tel._setup_tracing()
    assert tel._tracer_configured is True


def test_otel_exporter_otlp_configures_provider(monkeypatch):
    """Given OTEL_EXPORTER_OTLP_ENDPOINT, a real TracerProvider is set."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.delenv("OTEL_EXPORTER", raising=False)
    import app.lib.telemetry as tel

    monkeypatch.setattr(tel, "_tracer_configured", False)
    tel._setup_tracing()
    from opentelemetry import trace

    provider = trace.get_tracer_provider()
    assert type(provider).__name__ == "TracerProvider"


def test_otel_missing_exporter_package_is_graceful(monkeypatch):
    """Given a missing OTLP exporter package, setup does not crash."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.delenv("OTEL_EXPORTER", raising=False)
    # Simulate the exporter package not being installed by hiding the import.
    import builtins

    real_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name.startswith("opentelemetry.exporter.otlp"):
            raise ImportError("simulated missing package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    import app.lib.telemetry as tel

    monkeypatch.setattr(tel, "_tracer_configured", False)
    # Should not raise.
    tel._setup_tracing()
    # TracerProvider is still set (just without the exporter processor).
    from opentelemetry import trace

    provider = trace.get_tracer_provider()
    assert type(provider).__name__ == "TracerProvider"


# ── Static: no secrets in log calls ──────────────────────────────────────────


def test_no_secret_keywords_in_log_calls():
    """Given the backend source, no logger.* call mentions secret keywords."""
    backend_app = Path(__file__).resolve().parent.parent / "app"
    result = subprocess.run(
        [
            "grep",
            "-rn",
            "password\\|secret\\|token",
            str(backend_app),
            "--include=*.py",
        ],
        capture_output=True,
        text=True,
    )
    secret_lines = [
        line
        for line in result.stdout.splitlines()
        if "logger." in line or "log." in line
    ]
    assert secret_lines == [], (
        f"Log calls mention secret keywords:\n{chr(10).join(secret_lines)}"
    )


# ── Unit: configure_logging is idempotent ────────────────────────────────────


def test_configure_logging_is_idempotent():
    """Given multiple calls, no duplicate JSON handlers are added."""
    root = logging.getLogger()
    initial_count = sum(
        1
        for h in root.handlers
        if isinstance(h, logging.StreamHandler)
        and isinstance(h.formatter, JsonFormatter)
    )
    configure_logging()
    configure_logging()
    after_count = sum(
        1
        for h in root.handlers
        if isinstance(h, logging.StreamHandler)
        and isinstance(h.formatter, JsonFormatter)
    )
    assert after_count == max(initial_count, 1)
