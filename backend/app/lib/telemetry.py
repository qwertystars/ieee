"""OpenTelemetry traces + Prometheus metrics for the FastAPI app.

Exposes six Prometheus metrics, a Starlette middleware that records per-request
counts/durations and propagates the OTel trace ID onto request.state, and a
setup_telemetry() entry point that wires FastAPI + SQLAlchemy instrumentation.
"""

import logging
import re
import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.telemetry")

# ── Prometheus metrics ───────────────────────────────────────────────────────

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
active_websocket_connections = Gauge(
    "active_websocket_connections",
    "Active WebSocket connections",
)
optimization_solve_time_seconds = Histogram(
    "optimization_solve_time_seconds",
    "Optimization solver time in seconds",
    buckets=(0.1, 0.5, 1, 5, 10, 30, 60, 120, 300),
)
ml_inference_time_seconds = Histogram(
    "ml_inference_time_seconds",
    "ML model inference time in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
queue_depth = Gauge(
    "queue_depth",
    "Queue depth (pending messages)",
    ["queue_name"],
)

# ── Path normalization (cardinality control) ─────────────────────────────────

_ID_RE = re.compile(r"/[0-9a-fA-F]{8,}")


def _normalize_path(path: str) -> str:
    """Replace long hex/ULID/UUID segments with {id} to limit label cardinality."""
    return _ID_RE.sub("/{id}", path)


# ── OpenTelemetry setup ─────────────────────────────────────────────────────

_tracer_configured = False


def _setup_tracing() -> None:
    """Configure OpenTelemetry TracerProvider.

    No span exporter is wired — spans are created for trace-ID propagation but
    not shipped anywhere. Add an OTLP/Jaeger exporter in production.
    """
    global _tracer_configured
    if _tracer_configured:
        return
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider

    resource = Resource.create(
        {"service.name": "resqnet-sage-backend", "service.version": "0.1.0"}
    )
    trace.set_tracer_provider(TracerProvider(resource=resource))
    _tracer_configured = True


def _instrument_sqlalchemy() -> None:
    """Best-effort SQLAlchemy instrumentation (optional dependency)."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from app.db import engine

        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except ImportError:
        logger.debug(
            "opentelemetry-instrumentation-sqlalchemy not installed — skipping"
        )
    except Exception as exc:
        logger.debug("SQLAlchemy instrumentation failed: %s", exc)


# ── Middleware ───────────────────────────────────────────────────────────────


class TelemetryMiddleware(BaseHTTPMiddleware):
    """Record Prometheus metrics + propagate trace ID via request state.

    Must be added BEFORE FastAPIInstrumentor.instrument_app so the OTel
    middleware is outermost and the span is active when dispatch runs.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Propagate trace ID (OTel span is active — OTel middleware is outermost).
        try:
            from opentelemetry import trace

            ctx = trace.get_current_span().get_span_context()
            if ctx and ctx.is_valid:
                request.state.trace_id = f"{ctx.trace_id:032x}"
                request.state.span_id = f"{ctx.span_id:016x}"
        except Exception:
            pass

        method = request.method
        start = time.perf_counter()
        response = await call_next(request)
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
        return response


# ── Public API ───────────────────────────────────────────────────────────────


def setup_telemetry(app) -> None:
    """Wire telemetry middleware + OpenTelemetry instrumentation into the app.

    Order matters: TelemetryMiddleware is added first (innermost) so the OTel
    FastAPI middleware (added next by instrument_app) is outermost and the
    span context is active when TelemetryMiddleware.dispatch runs.
    """
    app.add_middleware(TelemetryMiddleware)
    _setup_tracing()
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:
        logger.warning("FastAPI OTel instrumentation failed: %s", exc)
    _instrument_sqlalchemy()


def metrics_endpoint() -> Response:
    """Return Prometheus-format metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


__all__ = [
    "setup_telemetry",
    "metrics_endpoint",
    "TelemetryMiddleware",
    "http_requests_total",
    "http_request_duration_seconds",
    "active_websocket_connections",
    "optimization_solve_time_seconds",
    "ml_inference_time_seconds",
    "queue_depth",
]
