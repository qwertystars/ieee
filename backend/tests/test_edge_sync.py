"""Tests for edge-first sync — outbox dedup and ordered application.

Uses the real PostgreSQL database via SessionLocal. The edge_sync_applied
and edge_sync_state tables are created by Alembic migrations. All test rows
are cleaned up.
"""

import pytest
from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.lib.audit import verify_chain
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.main import app
from app.models.events import AuditChainHead, Event
from app.realtime.edge_sync import (
    EdgeSync,
    EdgeSyncApplied,
    EdgeSyncState,
    compute_content_hash,
)
from app.realtime.sync import SyncConflict

ORG_ID = "org_test_edge_sync"
INCIDENT_ID = "inc_test_edge_sync"


@pytest.fixture
def db():
    """Yield a session and clean up test rows after each test."""
    session = SessionLocal()
    session.execute(delete(EdgeSyncApplied).where(EdgeSyncApplied.org_id == ORG_ID))
    session.execute(delete(EdgeSyncState).where(EdgeSyncState.org_id == ORG_ID))
    session.execute(delete(SyncConflict).where(SyncConflict.org_id == ORG_ID))
    session.execute(delete(Event).where(Event.org_id == ORG_ID))
    session.execute(delete(AuditChainHead).where(AuditChainHead.org_id == ORG_ID))
    session.commit()
    try:
        yield session
    finally:
        session.execute(delete(EdgeSyncApplied).where(EdgeSyncApplied.org_id == ORG_ID))
        session.execute(delete(EdgeSyncState).where(EdgeSyncState.org_id == ORG_ID))
        session.execute(delete(SyncConflict).where(SyncConflict.org_id == ORG_ID))
        session.execute(delete(Event).where(Event.org_id == ORG_ID))
        session.execute(delete(AuditChainHead).where(AuditChainHead.org_id == ORG_ID))
        session.commit()
        session.close()


def _make_item(
    sequence: int,
    payload: dict | None = None,
    content_hash: str | None = None,
    item_type: str = "status_update",
    item_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Build an outbox item with computed content_hash."""
    payload = payload or {"value": f"v_{sequence}"}
    return {
        "item_id": item_id or generate_ulid(),
        "idempotency_key": idempotency_key or generate_ulid(),
        "content_hash": content_hash or compute_content_hash(payload),
        "item_type": item_type,
        "payload": payload,
        "created_at": now_ms() - 1000 + sequence,
        "sequence": sequence,
        "device_id": "device_test_edge_sync",
        "device_sequence": sequence,
        "protocol_version": 2,
    }


def test_sync_receives_outbox_items(db):
    """sync receives outbox items and applies them all."""
    items = [_make_item(1), _make_item(2), _make_item(3)]
    sync = EdgeSync(db)
    result = sync.sync(items, db, ORG_ID, INCIDENT_ID)

    assert result["received"] == 3
    assert result["applied"] == 3
    assert result["duplicates"] == 0
    assert result["errors"] == 0

    count = db.execute(
        select(func.count())
        .select_from(EdgeSyncApplied)
        .where(EdgeSyncApplied.incident_id == INCIDENT_ID)
    ).scalar()
    assert count == 3


def test_dedup_by_content_hash(db):
    """Items with duplicate content hashes within a batch are deduplicated."""
    payload = {"value": "same"}
    h = compute_content_hash(payload)
    items = [
        _make_item(1, payload=payload, content_hash=h),
        _make_item(2, payload=payload, content_hash=h),
        _make_item(3, payload={"value": "different"}),
    ]
    sync = EdgeSync(db)
    result = sync.sync(items, db, ORG_ID, INCIDENT_ID)

    assert result["received"] == 3
    assert result["deduplicated"] == 1
    assert result["applied"] == 2
    assert result["duplicates"] == 0

    count = db.execute(
        select(func.count())
        .select_from(EdgeSyncApplied)
        .where(EdgeSyncApplied.incident_id == INCIDENT_ID)
    ).scalar()
    assert count == 2


def test_apply_in_order(db):
    """Items are applied in sequence order, not received order."""
    items = [
        _make_item(3, payload={"value": "third"}),
        _make_item(1, payload={"value": "first"}),
        _make_item(2, payload={"value": "second"}),
    ]
    sync = EdgeSync(db)
    sync.sync(items, db, ORG_ID, INCIDENT_ID)

    rows = db.execute(
        select(EdgeSyncApplied)
        .where(EdgeSyncApplied.incident_id == INCIDENT_ID)
        .order_by(EdgeSyncApplied.id.asc())
    ).scalars().all()

    sequences = [r.sequence for r in rows]
    assert sequences == [1, 2, 3]

    values = [r.payload["value"] for r in rows]
    assert values == ["first", "second", "third"]


def test_duplicate_items_skipped(db):
    """Items already applied in a previous batch are skipped."""
    items = [_make_item(1), _make_item(2), _make_item(3)]
    sync = EdgeSync(db)

    result1 = sync.sync(items, db, ORG_ID, INCIDENT_ID)
    assert result1["applied"] == 3
    assert result1["duplicates"] == 0

    result2 = sync.sync(items, db, ORG_ID, INCIDENT_ID)
    assert result2["received"] == 3
    assert result2["applied"] == 0
    assert result2["duplicates"] == 3

    count = db.execute(
        select(func.count())
        .select_from(EdgeSyncApplied)
        .where(EdgeSyncApplied.incident_id == INCIDENT_ID)
    ).scalar()
    assert count == 3


def test_sync_status_returns_correct_count(db):
    """get_sync_status returns correct applied and pending counts."""
    sync = EdgeSync(db)

    status = sync.get_sync_status(INCIDENT_ID)
    assert status["applied_count"] == 0
    assert status["pending_count"] == 0
    assert status["last_sync_at"] is None

    items = [_make_item(1), _make_item(2), _make_item(3)]
    sync.sync(items, db, ORG_ID, INCIDENT_ID)

    status = sync.get_sync_status(INCIDENT_ID)
    assert status["applied_count"] == 3
    assert status["pending_count"] == 0
    assert status["last_sync_at"] is not None

    sync.sync(items, db, ORG_ID, INCIDENT_ID)
    status = sync.get_sync_status(INCIDENT_ID)
    assert status["applied_count"] == 3
    assert status["pending_count"] == 3


def test_acknowledgements_are_idempotent_and_audited(db):
    item = _make_item(1, item_id=generate_ulid())
    sync = EdgeSync(db)
    first = sync.sync([item], db, ORG_ID, INCIDENT_ID)
    second = sync.sync([item], db, ORG_ID, INCIDENT_ID)

    assert first["acknowledgements"][0]["status"] == "acked"
    assert second["acknowledgements"][0]["status"] == "duplicate"
    assert verify_chain(db, ORG_ID) is True


def test_device_sequence_replay_fails_closed(db):
    sync = EdgeSync(db)
    sync.sync([_make_item(1, payload={"value": "first"})], db, ORG_ID, INCIDENT_ID)
    replay = _make_item(2, payload={"value": "different"})
    replay["device_sequence"] = 1

    result = sync.sync([replay], db, ORG_ID, INCIDENT_ID)

    assert result["errors"] == 1
    assert result["acknowledgements"][0]["reason"] == "device_sequence_replay"


def test_future_queue_item_fails_closed(db):
    item = _make_item(1)
    item["created_at"] = now_ms() + 31_000

    result = EdgeSync(db).sync([item], db, ORG_ID, INCIDENT_ID)

    assert result["errors"] == 1
    assert result["acknowledgements"][0]["reason"] == "queue_age_or_clock_skew"


def test_reinstalled_device_requires_reenrollment(db):
    item = _make_item(1)
    item["reinstalled"] = True

    result = EdgeSync(db).sync([item], db, ORG_ID, INCIDENT_ID)

    assert result["errors"] == 1
    assert result["acknowledgements"][0]["reason"] == "device_reenrollment_required"


def test_content_hash_mismatch_fails_closed(db):
    item = _make_item(1)
    item["content_hash"] = "0" * 64

    result = EdgeSync(db).sync([item], db, ORG_ID, INCIDENT_ID)

    assert result["errors"] == 1
    assert result["acknowledgements"][0]["reason"] == "content_hash_mismatch"


def test_reused_idempotency_key_is_duplicate_even_with_new_item_id(db):
    key = generate_ulid()
    first = _make_item(1, idempotency_key=key)
    second = _make_item(2, payload={"value": "same-key"}, idempotency_key=key)
    sync = EdgeSync(db)

    sync.sync([first], db, ORG_ID, INCIDENT_ID)
    result = sync.sync([second], db, ORG_ID, INCIDENT_ID)

    assert result["duplicates"] == 1
    assert result["acknowledgements"][0]["reason"] == "idempotent_replay"


def test_stale_queue_item_is_terminal_failure(db):
    item = _make_item(1)
    item["created_at"] = now_ms() - 8 * 24 * 60 * 60 * 1000

    result = EdgeSync(db).sync([item], db, ORG_ID, INCIDENT_ID)

    assert result["errors"] == 1
    assert result["acknowledgements"][0]["reason"] == "queue_age_or_clock_skew"


def test_task_conflict_requires_human_resolution(db):
    sync = EdgeSync(db)
    first = _make_item(1, item_type="task_state", payload={"entity_type": "task", "entity_id": "task-1", "status": "assigned"})
    second = _make_item(2, item_type="task_state", payload={"entity_type": "task", "entity_id": "task-1", "status": "completed"})
    sync.sync([first], db, ORG_ID, INCIDENT_ID)

    result = sync.sync([second], db, ORG_ID, INCIDENT_ID)

    assert result["conflicts"] == 1
    assert result["acknowledgements"][0]["reason"] == "human_resolution_required"
    assert db.execute(select(func.count()).select_from(EdgeSyncApplied).where(EdgeSyncApplied.incident_id == INCIDENT_ID)).scalar() == 1


def test_conflict_with_omitted_hash_uses_computed_digest(db):
    sync = EdgeSync(db)
    first = _make_item(1, item_type="task_state", payload={"entity_type": "task", "entity_id": "task-2", "status": "assigned"})
    second_payload = {"entity_type": "task", "entity_id": "task-2", "status": "completed"}
    second = _make_item(2, item_type="task_state", payload=second_payload)
    second.pop("content_hash")

    sync.sync([first], db, ORG_ID, INCIDENT_ID)
    result = sync.sync([second], db, ORG_ID, INCIDENT_ID)

    assert result["conflicts"] == 1
    conflict = db.execute(select(SyncConflict).where(SyncConflict.incident_id == INCIDENT_ID)).scalar_one()
    assert conflict.content_hash_remote == compute_content_hash(second_payload)


def test_authenticated_edge_sync_routes_are_registered():
    paths = set(app.openapi()["paths"])

    assert "/api/incidents/{incident_id}/sync" in paths
