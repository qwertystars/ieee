"""OpenTelemetry traces + Prometheus metrics for the FastAPI app.

Exposes six Prometheus metrics, a Starlette middleware that records per-request
counts/durations and propagates the OTel trace ID onto request.state, and a
setup_telemetry() entry point that wires FastAPI + SQLAlchemy instrumentation.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING
from weakref import WeakSet

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.engine import Engine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.lib.observability import (
    EVENT_STATES,
    SLO_DEFINITIONS,
    calculate_burn_rate,
    current_trace_id,
    normalize_metric_label,
    redact_telemetry_attributes,
)
from app.lib.observability_metrics import (
    active_websocket_connections,
    db_queries_total,
    db_query_duration_seconds,
    http_request_duration_seconds,
    http_requests_total,
    ml_inference_time_seconds,
    optimization_solve_time_seconds,
    queue_depth,
    slo_eligible_requests_total,
    slo_successful_requests_total,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("app.telemetry")

_ID_RE = re.compile(r"/(?:[0-9a-fA-F]{8,}|[0-9A-HJKMNP-TV-Z]{26})")


def _normalize_path(path: str) -> str:
    """Replace long hex/ULID/UUID segments with {id} to limit label cardinality."""
    return _ID_RE.sub("/{id}", path)


# ── OpenTelemetry setup ─────────────────────────────────────────────────────

_tracer_configured = False
_instrumented_engines: WeakSet[Engine] = WeakSet()


def _setup_tracing() -> None:
    """Configure OpenTelemetry TracerProvider with optional OTLP export.

    - ``OTEL_EXPORTER=none`` disables tracing entirely.
    - ``OTEL_EXPORTER_OTLP_ENDPOINT`` enables OTLP HTTP export (if the
      exporter package is installed; otherwise spans are created but not
      shipped — graceful degradation).
    """
    global _tracer_configured
    if _tracer_configured:
        return

    if os.environ.get("OTEL_EXPORTER", "").lower() == "none":
        logger.debug("OTEL_EXPORTER=none — tracing disabled")
        _tracer_configured = True
        return

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider

    resource = Resource.create(
        {"service.name": "resqnet-sage-backend", "service.version": "0.1.0"}
    )
    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            )
            logger.info("OTLP exporter configured")
        except ImportError:
            logger.warning(
                "OTEL_EXPORTER_OTLP_ENDPOINT set but "
                "opentelemetry-exporter-otlp-proto-http not installed — "
                "spans will not be exported"
            )
        except Exception as exc:
            logger.warning("OTLP exporter setup failed: %s", type(exc).__name__)

    trace.set_tracer_provider(provider)
    _tracer_configured = True


def _instrument_sqlalchemy() -> None:
    from sqlalchemy import event

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from app.db import engine

        SQLAlchemyInstrumentor().instrument(engine=engine)
    except ImportError:
        logger.debug(
            "opentelemetry-instrumentation-sqlalchemy not installed — skipping"
        )
    except Exception as exc:
        logger.debug("SQLAlchemy instrumentation failed: %s", exc)

    from app.db import engine

    if engine in _instrumented_engines:
        return

    def before_cursor_execute(conn, _cursor, statement, _parameters, _context, _executemany):
        conn.info.setdefault("_resqnet_query_started", []).append(time.perf_counter())

    def after_cursor_execute(conn, _cursor, statement, _parameters, _context, _executemany):
        started = conn.info.get("_resqnet_query_started", [])
        if not started:
            return
        duration = time.perf_counter() - started.pop()
        operation = statement.lstrip().split(" ", 1)[0].lower()
        if operation not in {"select", "insert", "update", "delete", "commit"}:
            operation = "other"
        db_queries_total.labels(operation=operation, outcome="success").inc()
        db_query_duration_seconds.labels(operation=operation).observe(duration)

    def handle_error(_exception_context):
        db_queries_total.labels(operation="other", outcome="failed").inc()

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)
    event.listen(engine, "handle_error", handle_error)
    _instrumented_engines.add(engine)


# ── Middleware ───────────────────────────────────────────────────────────────


class TelemetryMiddleware(BaseHTTPMiddleware):
    """Record Prometheus metrics + propagate trace ID via request state.

    Must be added BEFORE FastAPIInstrumentor.instrument_app so the OTel
    middleware is outermost and the span is active when dispatch runs.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        from app.lib.logging_config import bind_context, clear_context

        trace_id = current_trace_id()
        if trace_id is not None:
            request.state.trace_id = trace_id
            bind_context(trace_id=trace_id)

        method = request.method
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            clear_context()
        duration = time.perf_counter() - start

        # Prefer route template (e.g. /api/observations/{id}); fall back to
        # normalized raw path to avoid label cardinality explosion.
        route = request.scope.get("route")
        if route and hasattr(route, "path"):
            path = route.path
        else:
            path = _normalize_path(request.url.path)

        status = str(response.status_code)
        http_requests_total.labels(method=method, path=path, status=status).inc()
        http_request_duration_seconds.labels(method=method, path=path).observe(
            duration
        )
        if request.url.path not in {"/healthz", "/healthz/deep", "/metrics"} and request.headers.get("Authorization", "").lower().startswith("bearer "):
            request_class = "read" if method == "GET" else "write"
            slo_eligible_requests_total.labels(request_class=request_class).inc()
            if response.status_code < 400:
                slo_successful_requests_total.labels(request_class=request_class).inc()
        if trace_id is not None:
            response.headers["X-Trace-Id"] = trace_id
        return response


# ── Public API ───────────────────────────────────────────────────────────────


def setup_telemetry(app: FastAPI) -> None:
    """Wire telemetry middleware + OpenTelemetry instrumentation into the app.

    Order matters: TelemetryMiddleware is added first (innermost) so the OTel
    FastAPI middleware (added next by instrument_app) is outermost and the
    span context is active when TelemetryMiddleware.dispatch runs.
    """
    from app.lib.logging_config import configure_logging

    configure_logging()
    app.add_middleware(TelemetryMiddleware)
    _setup_tracing()
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:
        logger.warning("FastAPI OTel instrumentation failed: %s", type(exc).__name__)
    _instrument_sqlalchemy()


def metrics_endpoint() -> Response:
    """Return Prometheus-format metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


__all__ = [
    "EVENT_STATES",
    "SLO_DEFINITIONS",
    "TelemetryMiddleware",
    "active_websocket_connections",
    "calculate_burn_rate",
    "http_request_duration_seconds",
    "http_requests_total",
    "metrics_endpoint",
    "ml_inference_time_seconds",
    "normalize_metric_label",
    "optimization_solve_time_seconds",
    "queue_depth",
    "redact_telemetry_attributes",
    "setup_telemetry",
]
