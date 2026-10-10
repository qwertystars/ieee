from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import delete

from app.db import SessionLocal
from app.lib.audit import verify_chain, write_audit
from app.lib.idempotency import IdempotencyConflictError, IdempotencyKey, check_and_record
from app.models.events import AuditChainHead, Event, RawEvent


@pytest.fixture
def audit_db():
    session = SessionLocal()
    org_id = "org_task4_adversarial"
    session.execute(delete(Event).where(Event.org_id == org_id))
    session.execute(delete(AuditChainHead).where(AuditChainHead.org_id == org_id))
    session.execute(delete(IdempotencyKey).where(IdempotencyKey.org_id == org_id))
    session.commit()
    try:
        yield session, org_id
    finally:
        session.execute(delete(Event).where(Event.org_id == org_id))
        session.execute(delete(AuditChainHead).where(AuditChainHead.org_id == org_id))
        session.execute(delete(IdempotencyKey).where(IdempotencyKey.org_id == org_id))
        session.commit()
        session.close()


def _three_events(db, org_id: str) -> list[Event]:
    return [write_audit(db, org_id, "incident-1", "actor", "create", f"entity-{i}") for i in range(3)]


def test_raw_event_accepts_non_negative_integer_timestamps() -> None:
    event = RawEvent(
        event_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        org_id="org-1",
        incident_id="incident-1",
        source_id="sensor-1",
        external_id="external-1",
        event_type="sensor.observation",
        source_time_ms=0,
        receipt_time_ms=1_721_300_000_000,
        sequence=1,
        payload={},
    )

    assert event.source_time_ms == 0
    assert event.receipt_time_ms == 1_721_300_000_000


@pytest.mark.parametrize("timestamp_value", [True, 1.0, 1.5, "1721300000000", -1])
def test_raw_event_rejects_non_integral_or_negative_timestamps(timestamp_value) -> None:
    for field_name in ("source_time_ms", "receipt_time_ms"):
        with pytest.raises(ValueError):
            RawEvent(
                event_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
                org_id="org-1",
                incident_id="incident-1",
                source_id="sensor-1",
                external_id="external-1",
                event_type="sensor.observation",
                source_time_ms=0 if field_name == "receipt_time_ms" else timestamp_value,
                receipt_time_ms=0 if field_name == "source_time_ms" else timestamp_value,
                sequence=1,
                payload={},
            )


def test_tail_truncation_is_detected_by_persisted_chain_head(audit_db) -> None:
    db, org_id = audit_db
    events = _three_events(db, org_id)
    db.delete(events[-1])
    db.commit()
    assert verify_chain(db, org_id) == 2


def test_empty_events_with_persisted_head_is_invalid(audit_db) -> None:
    db, org_id = audit_db
    write_audit(db, org_id, "incident-1", "actor", "create", "entity-1")
    db.query(Event).filter(Event.org_id == org_id).delete()
    db.commit()
    assert verify_chain(db, org_id) == 0


def test_canonical_hash_binds_serialization_version(audit_db) -> None:
    db, org_id = audit_db
    write_audit(db, org_id, "incident-1", "actor", "create", "entity-1")
    event = db.query(Event).filter(Event.org_id == org_id).one()
    event.serialization_version = "rfc8785-v3"
    db.commit()
    assert verify_chain(db, org_id) == 0


def test_canonical_hash_binds_nested_provenance_fields(audit_db) -> None:
    db, org_id = audit_db
    write_audit(
        db,
        org_id,
        "incident-1",
        "actor",
        "create",
        "entity-1",
        provenance={"model_id": "model-1", "model_version": "1.0"},
    )
    event = db.query(Event).filter(Event.org_id == org_id).one()
    event.provenance = {"model_id": "model-2", "model_version": "1.0"}
    db.commit()
    assert verify_chain(db, org_id) == 0


def test_reordered_sequence_is_rejected(audit_db) -> None:
    db, org_id = audit_db
    events = _three_events(db, org_id)
    events[0].sequence = 4
    db.commit()
    assert verify_chain(db, org_id) == 0


def test_forked_predecessor_is_rejected(audit_db) -> None:
    db, org_id = audit_db
    events = _three_events(db, org_id)
    events[2].prev_hash = events[0].hash
    db.commit()
    assert verify_chain(db, org_id) == 2


def test_duplicate_external_id_with_different_payload_is_conflict(audit_db) -> None:
    db, org_id = audit_db
    assert check_and_record(db, "sensor", "external-1", org_id=org_id, payload={"v": 1}) is True
    assert check_and_record(db, "sensor", "external-1", org_id=org_id, payload={"v": 1}) is False
    with pytest.raises(IdempotencyConflictError):
        check_and_record(db, "sensor", "external-1", org_id=org_id, payload={"v": 2})


def test_missing_payload_and_supplied_payload_are_conflicts(audit_db) -> None:
    db, org_id = audit_db
    assert check_and_record(db, "sensor", "external-2", org_id=org_id) is True
    with pytest.raises(IdempotencyConflictError):
        check_and_record(db, "sensor", "external-2", org_id=org_id, payload={"v": 1})


def test_supplied_payload_and_missing_payload_are_conflicts(audit_db) -> None:
    db, org_id = audit_db
    assert check_and_record(db, "sensor", "external-3", org_id=org_id, payload={"v": 1}) is True
    with pytest.raises(IdempotencyConflictError):
        check_and_record(db, "sensor", "external-3", org_id=org_id)


def test_task4_migration_downgrade_refuses_data_loss() -> None:
    path = Path(__file__).parents[1] / "alembic/versions/0006_canonical_event_contracts.py"
    spec = importlib.util.spec_from_file_location("task4_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with pytest.raises(RuntimeError):
        migration.downgrade()
