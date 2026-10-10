from __future__ import annotations

import pytest

from app.lib.audit import _canonical_payload, _compute_hash, canonical_json_bytes
from app.models.events import Decision, ModelProvenance, Prediction, RawEvent, is_schema_compatible
from app.models.observation import NormalizedObservation


def test_legacy_audit_payload_bytes_are_characterized() -> None:
    payload = _canonical_payload(
        "alice",
        "create",
        "observation:01J9TEST",
        None,
        {"value": 1.5},
        1_721_300_000_000,
    )

    assert payload == (
        '{"action":"create","actor":"alice","after":{"value":1.5},'
        '"before":null,"entity":"observation:01J9TEST","ts":1721300000000}'
    )


def test_legacy_audit_hash_input_is_characterized() -> None:
    payload = _canonical_payload("alice", "create", "obs:1", None, {"v": 1}, 10)

    assert _compute_hash("", payload) == (
        "0774b375a3da3880e342a52d7b556340f9fadb11d6967227fa06dd255916fa6a"
    )


def test_canonical_json_uses_rfc8785_compatible_bytes() -> None:
    value = {"z": 1.0, "a": "café", "nested": {"b": True, "a": None}}

    assert canonical_json_bytes(value) == (
        b'{"a":"caf\xc3\xa9","nested":{"a":null,"b":true},"z":1}'
    )


def test_raw_event_requires_canonical_scope_and_times() -> None:
    with pytest.raises(ValueError):
        RawEvent(
            event_id="not-an-ulid",
            org_id="org-1",
            incident_id="incident-1",
            source_id="sensor-1",
            external_id="ext-1",
            event_type="sensor.observation",
            source_time_ms=1,
            receipt_time_ms=2,
            sequence=1,
            payload={},
        )


def test_schema_compatibility_accepts_minor_and_rejects_major_changes() -> None:
    assert is_schema_compatible("1.1") is True
    assert is_schema_compatible("2.0") is False
    assert is_schema_compatible("not-a-version") is False


def test_malformed_model_provenance_is_rejected() -> None:
    with pytest.raises(ValueError):
        ModelProvenance(
            model_id="",
            model_version="2.0.0",
            feature_schema_version="1.0.0",
            preprocessing_version="1.0.0",
            calibration_version="1.0.0",
            output_schema_version="1.0.0",
        )


def test_prediction_and_decision_lineage_ids_are_ulids() -> None:
    provenance = ModelProvenance(
        model_id="flood-model",
        model_version="2.0.0",
        feature_schema_version="1.0.0",
        preprocessing_version="1.0.0",
        calibration_version="1.0.0",
        output_schema_version="1.0.0",
    )
    with pytest.raises(ValueError):
        Prediction(
            prediction_id="prediction-1",
            org_id="org-1",
            incident_id="incident-1",
            source_event_ids=("01ARZ3NDEKTSV4RRFFQ69G5FAV",),
            generated_at_ms=1,
            valid_from_ms=1,
            output={},
            provenance=provenance,
        )
    with pytest.raises(ValueError):
        Decision(
            decision_id="decision-1",
            org_id="org-1",
            incident_id="incident-1",
            prediction_ids=("prediction-1",),
            decision_type="dispatch",
            decision={"approved": False},
            rationale="not ready",
            actor="operator-1",
            decided_at_ms=1,
        )


def test_raw_event_is_immutable_and_hashes_provenance() -> None:
    provenance = ModelProvenance(
        model_id="flood-model",
        model_version="2.0.0",
        feature_schema_version="1.0.0",
        preprocessing_version="1.0.0",
        calibration_version="1.0.0",
        output_schema_version="1.0.0",
    )
    event = RawEvent(
        event_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        org_id="org-1",
        incident_id="incident-1",
        source_id="sensor-1",
        external_id="ext-1",
        event_type="sensor.observation",
        source_time_ms=1,
        receipt_time_ms=2,
        sequence=1,
        payload={"value": 2.5},
        provenance=provenance,
    )

    with pytest.raises((TypeError, ValueError)):
        event.sequence = 2
    assert event.canonical_hash().startswith("sha256:")


def test_normalized_observation_rebuild_preserves_lineage() -> None:
    event = RawEvent(
        event_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        org_id="org-1",
        incident_id="incident-1",
        source_id="sensor-1",
        external_id="ext-1",
        event_type="sensor.observation",
        source_time_ms=1,
        receipt_time_ms=2,
        sequence=1,
        payload={"phenomenon": "water_level", "value": 2.5, "unit": "m"},
    )

    observation = NormalizedObservation.from_raw_event(event)

    assert observation.raw_event_id == event.event_id
    assert observation.source_time_ms == event.source_time_ms
    assert observation.receipt_time_ms == event.receipt_time_ms
    assert observation.payload_hash == event.canonical_hash()
