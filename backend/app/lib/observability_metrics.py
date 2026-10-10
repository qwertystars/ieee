from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

from app.lib.observability import EVENT_STATES, normalize_metric_label

http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
active_websocket_connections = Gauge("active_websocket_connections", "Active WebSocket connections")
optimization_solve_time_seconds = Histogram(
    "optimization_solve_time_seconds", "Optimization solver time in seconds", buckets=(0.1, 0.5, 1, 5, 10, 30, 60, 120, 300)
)
ml_inference_time_seconds = Histogram(
    "ml_inference_time_seconds", "ML model inference time in seconds", ["model"], buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
)
queue_depth = Gauge("queue_depth", "Queue depth (pending messages)", ["queue_name"])
queue_age_seconds = Histogram(
    "queue_age_seconds", "Age of queued messages in seconds", ["queue_name"], buckets=(1, 5, 15, 30, 60, 120, 300, 900, 3600)
)
queue_messages_total = Counter(
    "queue_messages_total", "Messages crossing a durable queue boundary", ["queue_name", "outcome"]
)
event_state_total = Counter(
    "event_state_total", "Durable event state transitions", ["component", "event_state", "queue_name"]
)
worker_messages_total = Counter(
    "worker_messages_total", "Worker message outcomes", ["worker", "outcome"]
)
worker_retries_total = Counter("worker_retries_total", "Worker retry attempts", ["worker"])
db_queries_total = Counter("db_queries_total", "Database query outcomes", ["operation", "outcome"])
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds", "Database query duration", ["operation"], buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)
)
model_inference_total = Counter(
    "model_inference_total", "Model inference outcomes", ["model", "state"]
)
offline_sync_total = Counter(
    "offline_sync_total", "Offline sync item outcomes", ["status"]
)
external_feed_total = Counter(
    "external_feed_total", "External feed outcomes", ["feed", "outcome"]
)
dependency_health = Gauge(
    "dependency_health", "Dependency state, one for the current bounded state", ["dependency", "state"]
)
saturation_utilization = Gauge(
    "saturation_utilization", "Resource utilization ratio", ["resource"]
)
slo_eligible_requests_total = Counter(
    "slo_eligible_requests_total", "Eligible requests for availability SLO", ["request_class"]
)
slo_successful_requests_total = Counter(
    "slo_successful_requests_total", "Successful requests for availability SLO", ["request_class"]
)


def record_event_state(state: str, component: str, queue_name: str = "other") -> None:
    if state not in EVENT_STATES:
        state = "failed"
    event_state_total.labels(
        component=normalize_metric_label(component),
        event_state=state,
        queue_name=normalize_metric_label(queue_name),
    ).inc()


def record_queue_message(queue_name: str, outcome: str) -> None:
    queue_messages_total.labels(
        queue_name=normalize_metric_label(queue_name),
        outcome=normalize_metric_label(outcome),
    ).inc()


def record_worker_message(outcome: str, worker: str = "worker") -> None:
    worker_messages_total.labels(
        worker=normalize_metric_label(worker), outcome=normalize_metric_label(outcome)
    ).inc()


def record_model_inference(model: str, state: str, duration_seconds: float) -> None:
    safe_model = normalize_metric_label(model)
    model_inference_total.labels(model=safe_model, state=normalize_metric_label(state)).inc()
    ml_inference_time_seconds.labels(model=safe_model).observe(duration_seconds)


def record_offline_sync(status: str) -> None:
    offline_sync_total.labels(status=normalize_metric_label(status)).inc()


def record_external_feed(feed: str, outcome: str) -> None:
    external_feed_total.labels(
        feed=normalize_metric_label(feed), outcome=normalize_metric_label(outcome)
    ).inc()


def record_dependency(name: str, state: str) -> None:
    safe_name = normalize_metric_label(name)
    safe_state = normalize_metric_label(state)
    for candidate in ("configured", "reachable", "degraded", "unknown"):
        dependency_health.labels(dependency=safe_name, state=candidate).set(float(candidate == safe_state))


__all__ = [
    "active_websocket_connections",
    "db_queries_total",
    "db_query_duration_seconds",
    "dependency_health",
    "event_state_total",
    "external_feed_total",
    "http_request_duration_seconds",
    "http_requests_total",
    "ml_inference_time_seconds",
    "model_inference_total",
    "offline_sync_total",
    "optimization_solve_time_seconds",
    "queue_age_seconds",
    "queue_depth",
    "queue_messages_total",
    "record_dependency",
    "record_event_state",
    "record_external_feed",
    "record_model_inference",
    "record_offline_sync",
    "record_queue_message",
    "record_worker_message",
    "saturation_utilization",
    "slo_eligible_requests_total",
    "slo_successful_requests_total",
    "worker_messages_total",
    "worker_retries_total",
]
