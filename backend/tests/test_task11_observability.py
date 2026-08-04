from __future__ import annotations

from app.api.routes.service_health import _dependency_status
from app.lib.telemetry import (
    EVENT_STATES,
    SLO_DEFINITIONS,
    calculate_burn_rate,
    normalize_metric_label,
    redact_telemetry_attributes,
)


def test_sli_contract_declares_operational_evidence() -> None:
    required = {
        "formula",
        "denominator",
        "source_of_truth",
        "window",
        "threshold",
        "burn_rate_alert",
        "cardinality_limit",
        "retention",
        "privacy_rule",
    }

    assert {"availability", "acknowledged_event_loss", "ingest_rate", "api_read_latency", "dashboard_latency", "saturation", "queue_age", "dependency_health"} <= set(SLO_DEFINITIONS)
    assert all(required <= set(definition) for definition in SLO_DEFINITIONS.values())


def test_burn_rate_uses_error_budget_ratio() -> None:
    assert calculate_burn_rate(error_ratio=0.0144, error_budget=0.001) == 14.4
    assert calculate_burn_rate(error_ratio=0.006, error_budget=0.001) == 6.0


def test_metric_labels_are_bounded_and_never_identifiers() -> None:
    assert normalize_metric_label("source-01KZZZZZZZZZZZZZZZZZZZZZZ") == "other"
    assert normalize_metric_label("queue.observations.normalized") == "observations.normalized"
    assert normalize_metric_label("Bearer eyJhbGciOiJIUzI1NiJ9") == "other"


def test_telemetry_redaction_removes_secret_and_payload_values() -> None:
    safe = redact_telemetry_attributes(
        {
            "authorization": "Bearer secret-token",
            "password": "hunter2",
            "raw_payload": {"email": "person@example.test", "value": 2},
            "status": "failed",
        }
    )
    assert safe == {"status": "failed"}
    assert "secret-token" not in str(safe)
    assert "person@example.test" not in str(safe)


def test_event_state_registry_is_the_dashboard_state_machine() -> None:
    assert EVENT_STATES == ("accepted", "processed", "failed", "stale", "lost")


def test_unknown_dependency_is_not_reported_as_reachable() -> None:
    assert _dependency_status(True, None) == "unknown"
    assert _dependency_status(True, False) == "degraded"
    assert _dependency_status(True, True) == "reachable"


def test_queue_backlog_policy_has_a_bounded_age_threshold() -> None:
    assert SLO_DEFINITIONS["queue_age"]["threshold"] == 60.0
