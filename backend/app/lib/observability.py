from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import Span

EVENT_STATES = ("accepted", "processed", "failed", "stale", "lost")
DEPENDENCY_STATES = ("configured", "reachable", "degraded", "unknown")
ALERT_BURN_RATES = (14.4, 6.0)
ERROR_BUDGET = 0.001
METRIC_LABEL_LIMIT = 32

SLO_DEFINITIONS = {
    "availability": {
        "formula": "successful_authorized_requests / eligible_requests",
        "denominator": "authenticated non-health requests received by every instance",
        "source_of_truth": "slo_successful_requests_total and slo_eligible_requests_total unioned by request_id",
        "window": "UTC calendar month",
        "threshold": 0.999,
        "burn_rate_alert": {"windows": ["1h", "6h"], "multipliers": [14.4, 6.0]},
        "cardinality_limit": "method x route_template x status_class; route templates only",
        "retention": "13 months in Prometheus-compatible long-term storage",
        "privacy_rule": "never include org, actor, email, token, IP, or raw request data",
    },
    "acknowledged_event_loss": {
        "formula": "acknowledged_absent_from_ledger / acknowledged",
        "denominator": "durable API or broker acknowledgements",
        "source_of_truth": "raw event ledger joined to acknowledgement and audit records",
        "window": "UTC calendar month and per incident",
        "threshold": 0.0,
        "burn_rate_alert": {"windows": ["5m", "1h"], "multipliers": [1.0, 1.0]},
        "cardinality_limit": "event_state x queue; no event identifiers as labels",
        "retention": "13 months counters plus immutable ledger retention policy",
        "privacy_rule": "hashes may be stored in durable records; payloads and identifiers stay out of telemetry",
    },
    "ingest_rate": {
        "formula": "processed_events / elapsed_seconds",
        "denominator": "elapsed UTC seconds with an active ingest window",
        "source_of_truth": "worker processed event counter and broker receipt timestamps",
        "window": "5 minute rolling window and 1 hour report",
        "threshold": 100.0,
        "burn_rate_alert": {"windows": ["15m", "1h"], "multipliers": [1.0, 1.0]},
        "cardinality_limit": "queue x outcome; queue names are an allowlist",
        "retention": "90 days for rate evidence",
        "privacy_rule": "no source, device, tenant, location, or payload labels",
    },
    "api_read_latency": {
        "formula": "nearest_rank(request_latency_seconds, 0.95)",
        "denominator": "all GET requests, including failures, excluding health and metrics endpoints",
        "source_of_truth": "http_request_duration_seconds histogram",
        "window": "5 minute rolling window",
        "threshold": 0.5,
        "burn_rate_alert": {"windows": ["15m", "1h"], "multipliers": [14.4, 6.0]},
        "cardinality_limit": "route_template x method; route templates only",
        "retention": "90 days",
        "privacy_rule": "route templates only and no query string or body",
    },
    "dashboard_latency": {
        "formula": "nearest_rank(request_latency_seconds, 0.95)",
        "denominator": "authenticated dashboard read requests, including failures",
        "source_of_truth": "http_request_duration_seconds histogram with request_class=dashboard",
        "window": "5 minute rolling window",
        "threshold": 2.0,
        "burn_rate_alert": {"windows": ["15m", "1h"], "multipliers": [14.4, 6.0]},
        "cardinality_limit": "dashboard route template only",
        "retention": "90 days",
        "privacy_rule": "no user, incident, coordinate, or response-body labels",
    },
    "saturation": {
        "formula": "resource_used / resource_capacity",
        "denominator": "declared CPU, memory, database connection, and worker concurrency capacity",
        "source_of_truth": "process and database pool gauges plus worker capacity",
        "window": "5 minute rolling maximum",
        "threshold": {"cpu": 0.70, "memory": 0.75, "db_connections": 0.80},
        "burn_rate_alert": {"windows": ["15m", "1h"], "multipliers": [1.0, 1.0]},
        "cardinality_limit": "resource allowlist only",
        "retention": "90 days",
        "privacy_rule": "resource names only; no hostnames, process arguments, or environment values",
    },
    "queue_age": {
        "formula": "nearest_rank(now_ms - enqueue_time_ms, 0.95)",
        "denominator": "messages present in each durable queue",
        "source_of_truth": "broker enqueue timestamp and worker receipt timestamp",
        "window": "5 minute rolling window",
        "threshold": 60.0,
        "burn_rate_alert": {"windows": ["5m", "15m"], "multipliers": [1.0, 1.0]},
        "cardinality_limit": "queue allowlist only",
        "retention": "90 days",
        "privacy_rule": "message ids, keys, tenant ids, and payloads are never labels",
    },
    "dependency_health": {
        "formula": "reachable_dependency_checks / configured_dependency_checks",
        "denominator": "dependencies with a declared endpoint and an executed probe",
        "source_of_truth": "dependency_health gauge and deep health probe result",
        "window": "current state plus 5 minute history",
        "threshold": "all required dependencies reachable; unknown never counts as healthy",
        "burn_rate_alert": {"windows": ["5m", "15m"], "multipliers": [1.0, 1.0]},
        "cardinality_limit": "dependency and state allowlists only",
        "retention": "90 days",
        "privacy_rule": "never export endpoint URLs, credentials, connection strings, or exception bodies",
    },
}

_SAFE_VALUES = frozenset({
    "api",
    "backend",
    "worker",
    "client",
    "database",
    "redis",
    "redpanda",
    "minio",
    "ollama",
    "building-damage",
    "incident-nlp",
    "sar-flood-mapping",
    "available",
    "abstain",
    "unavailable",
    "incompatible",
    "prometheus",
    "otlp",
    "observations.raw",
    "observations.normalized",
    "observations.dlq",
    "accepted",
    "processed",
    "received",
    "published",
    "stale",
    "lost",
    "reachable",
    "degraded",
    "unknown",
    "configured",
    "read",
    "write",
    "dashboard",
    "active",
    "error",
    "failed",
    "skipped",
    "synced",
    "pending",
    "conflict",
    "duplicate",
    "twitter",
    "reddit",
    "instagram",
    "youtube",
    "other",
})
_SECRET_WORDS = re.compile(r"(?:authorization|bearer|credential|password|secret|token|jwt|payload|body|email|phone|address|name)", re.IGNORECASE)
_SAFE_LABEL = re.compile(r"^[a-z0-9_.:-]{1,32}$")
_ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$", re.IGNORECASE)


def normalize_metric_label(value: str, allowed: frozenset[str] = _SAFE_VALUES) -> str:
    label = value.strip().lower()
    if label.startswith("queue."):
        label = label.removeprefix("queue.")
    if label in allowed:
        return label
    if not _SAFE_LABEL.fullmatch(label) or _ULID.fullmatch(label) or _SECRET_WORDS.search(label):
        return "other"
    return "other"


def redact_telemetry_attributes(attributes: Mapping[str, str | int | float | bool]) -> dict[str, str | int | float | bool]:
    safe: dict[str, str | int | float | bool] = {}
    for key, value in attributes.items():
        if _SECRET_WORDS.search(key) or isinstance(value, str) and _SECRET_WORDS.search(value):
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[key] = value
    return safe


def calculate_burn_rate(error_ratio: float, error_budget: float = ERROR_BUDGET) -> float:
    if error_budget <= 0:
        return float("inf") if error_ratio > 0 else 0.0
    return round(error_ratio / error_budget, 10)


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    return f"{context.trace_id:032x}" if context.is_valid else None


def inject_trace_headers(headers: MutableMapping[str, str]) -> None:
    inject(headers)


def extract_trace_context(headers: Mapping[str, str]) -> Context:
    return extract(dict(headers))


@contextmanager
def telemetry_span(name: str, attributes: Mapping[str, str | int | float | bool] | None = None) -> Iterator[Span]:
    tracer = trace.get_tracer("resqnet.observability")
    with tracer.start_as_current_span(name, attributes=redact_telemetry_attributes(attributes or {})) as span:
        yield span


__all__ = [
    "ALERT_BURN_RATES",
    "DEPENDENCY_STATES",
    "ERROR_BUDGET",
    "EVENT_STATES",
    "METRIC_LABEL_LIMIT",
    "SLO_DEFINITIONS",
    "calculate_burn_rate",
    "current_trace_id",
    "extract_trace_context",
    "inject_trace_headers",
    "normalize_metric_label",
    "redact_telemetry_attributes",
    "telemetry_span",
]
