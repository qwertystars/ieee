"""Tests for progressive precision access control (privacy.py).

Verifies that the same entity is serialized differently based on viewer's
role + task assignment, with 5 precision levels: public (ward-level),
shelter_operator, dispatcher, rescue_team, auditor.
"""

import pytest

from app.lib.privacy import (
    PII_FIELDS,
    ProgressivePrecision,
)

WARD_CENTROIDS = {
    "ward_5": (40.7128, -74.0060),
}

OBSERVATION = {
    "id": "01HTEST",
    "type": "rescue_request",
    "name": "Jane Doe",
    "phone": "+1234567890",
    "email": "jane@example.com",
    "address": "123 Main St",
    "contact": "Jane",
    "dob": "1990-01-01",
    "ssn": "123-45-6789",
    "medical_info": "asthma",
    "ward": "ward_5",
    "shelter_id": "shelter_01",
    "task_id": "task_42",
    "severity": "high",
    "status": "active",
    "location": {"lat": 40.71286, "lon": -74.00607},
    "decision_history": [{"action": "created", "ts": 1700000000}],
    "internal_notes": "priority evac",
    "audit_trail": [{"hash": "abc"}],
}


@pytest.fixture
def serializer():
    """ProgressivePrecision serializer with ward centroids configured."""
    return ProgressivePrecision(ward_centroids=WARD_CENTROIDS)


def test_progressive_precision(serializer):
    """Same observation serialized 3 ways: public=ward, dispatcher=approx, rescue=exact."""
    public = serializer.serialize(OBSERVATION, viewer_role="viewer")
    dispatch = serializer.serialize(OBSERVATION, viewer_role="responder_coordinator")
    rescue = serializer.serialize(
        OBSERVATION, viewer_role="field_responder", task_assignment="task_42"
    )

    # Public: ward-level, no exact location, has centroid.
    assert "location" not in public
    assert public.get("ward") == "ward_5"
    assert "centroid" in public

    # Dispatcher: approximate location (rounded to 3 decimals ~ 111m).
    assert "location" in dispatch
    assert dispatch["location"]["lat"] != OBSERVATION["location"]["lat"]

    # Rescue: exact location (unrounded).
    assert rescue["location"] == OBSERVATION["location"]


def test_public_strips_pii(serializer):
    """Public serializer strips all PII fields."""
    public = serializer.serialize(OBSERVATION, viewer_role="viewer")
    for field in PII_FIELDS:
        assert field not in public, f"PII field '{field}' leaked to public view"


def test_coordinate_precision_differs(serializer):
    """Coordinate precision differs by level: dispatcher ~100m, rescue exact."""
    dispatch = serializer.serialize(OBSERVATION, viewer_role="responder_coordinator")
    rescue = serializer.serialize(
        OBSERVATION, viewer_role="field_responder", task_assignment="task_42"
    )

    # Dispatcher: rounded to 3 decimals (~111m precision).
    assert dispatch["location"]["lat"] != OBSERVATION["location"]["lat"]
    assert dispatch["location"]["lon"] != OBSERVATION["location"]["lon"]

    # Rescue: exact match.
    assert rescue["location"] == OBSERVATION["location"]


def test_auditor_sees_decision_history(serializer):
    """Auditor sees decision_history, audit_trail, and internal_notes."""
    auditor = serializer.serialize(OBSERVATION, viewer_role="admin")
    assert "decision_history" in auditor
    assert "audit_trail" in auditor
    assert "internal_notes" in auditor

    # Non-auditor roles do NOT see audit-only fields.
    public = serializer.serialize(OBSERVATION, viewer_role="viewer")
    assert "decision_history" not in public
    dispatch = serializer.serialize(OBSERVATION, viewer_role="responder_coordinator")
    assert "audit_trail" not in dispatch
    rescue = serializer.serialize(
        OBSERVATION, viewer_role="field_responder", task_assignment="task_42"
    )
    assert "internal_notes" not in rescue


def test_unauthorized_role_minimal(serializer):
    """Unknown/unauthorized role gets PUBLIC (minimal data)."""
    unknown = serializer.serialize(OBSERVATION, viewer_role="random_role")
    public = serializer.serialize(OBSERVATION, viewer_role="viewer")
    assert unknown == public
    for field in PII_FIELDS:
        assert field not in unknown
    assert "location" not in unknown
