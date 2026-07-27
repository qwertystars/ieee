"""Tests for store-and-forward sync — priority ordering, dedup, conflict surfacing.

Uses the real PostgreSQL database via SessionLocal. The sync_conflicts and
edge_sync_applied tables are created by Alembic migrations. All test rows
are cleaned up.
"""

import pytest
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.lib.ulid import generate_ulid
from app.realtime.edge_sync import (
    EdgeSyncApplied,
    compute_content_hash,
)
from app.realtime.sync import (
    StoreAndForwardSync,
    SyncConflict,
)

ORG_ID = "org_test_sync"
INCIDENT_ID = "inc_test_sync"


@pytest.fixture
def db():
    """Yield a session and clean up test rows after each test."""
    session = SessionLocal()
    session.execute(delete(EdgeSyncApplied).where(EdgeSyncApplied.org_id == ORG_ID))
    session.execute(delete(SyncConflict).where(SyncConflict.org_id == ORG_ID))
    session.commit()
    try:
        yield session
    finally:
        session.execute(delete(EdgeSyncApplied).where(EdgeSyncApplied.org_id == ORG_ID))
        session.execute(delete(SyncConflict).where(SyncConflict.org_id == ORG_ID))
        session.commit()
        session.close()


def _make_item(
    item_type: str,
    payload: dict | None = None,
    sequence: int | None = None,
    item_id: str | None = None,
    content_hash: str | None = None,
) -> dict:
    """Build an outbox item with computed content_hash."""
    payload = payload or {"value": f"v_{item_type}"}
    return {
        "item_id": item_id or generate_ulid(),
        "content_hash": content_hash or compute_content_hash(payload),
        "item_type": item_type,
        "payload": payload,
        "sequence": sequence,
    }


def test_priority_ordering(db):
    """3 observations sync in priority order: text first, imagery last."""
    items = [
        _make_item("imagery", payload={"entity_id": "e1", "value": "img"}),
        _make_item("text", payload={"entity_id": "e2", "value": "txt"}),
        _make_item("coordinates", payload={"entity_id": "e3", "value": "coords"}),
    ]
    sync = StoreAndForwardSync(db)
    result = sync.sync_items(items, db, ORG_ID, INCIDENT_ID)

    assert result["applied"] == 3
    assert len(result["order"]) == 3

    rows = db.execute(
        select(EdgeSyncApplied)
        .where(EdgeSyncApplied.incident_id == INCIDENT_ID)
        .order_by(EdgeSyncApplied.id.asc())
    ).scalars().all()
    types_in_order = [r.item_type for r in rows]
    assert types_in_order == ["text", "coordinates", "imagery"]


def test_imagery_deprioritized(db):
    """Imagery items are applied last, even when listed first in the batch."""
    items = [
        _make_item("imagery", payload={"entity_id": "e1"}),
        _make_item("text", payload={"entity_id": "e2"}),
        _make_item("task_state", payload={"entity_id": "e3"}),
        _make_item("coordinates", payload={"entity_id": "e4"}),
    ]
    sync = StoreAndForwardSync(db)
    sync.sync_items(items, db, ORG_ID, INCIDENT_ID)

    rows = db.execute(
        select(EdgeSyncApplied)
        .where(EdgeSyncApplied.incident_id == INCIDENT_ID)
        .order_by(EdgeSyncApplied.id.asc())
    ).scalars().all()
    types_in_order = [r.item_type for r in rows]
    assert types_in_order[-1] == "imagery"
    assert types_in_order[0] == "text"


def test_dedup_by_content_hash(db):
    """Items with duplicate content hashes are deduped."""
    payload = {"entity_id": "e1", "value": "same"}
    h = compute_content_hash(payload)
    items = [
        _make_item("text", payload=payload, content_hash=h),
        _make_item("text", payload=payload, content_hash=h),
        _make_item("text", payload={"entity_id": "e2", "value": "different"}),
    ]
    sync = StoreAndForwardSync(db)
    result = sync.sync_items(items, db, ORG_ID, INCIDENT_ID)

    assert result["received"] == 3
    assert result["deduplicated"] == 1
    assert result["applied"] == 2


def test_conflicting_edit_returns_conflict(db):
    """Conflicting edit on same entity returns conflict response, not overwrite."""
    initial_payload = {
        "entity_type": "task", "entity_id": "task_1", "status": "pending",
    }
    sync = StoreAndForwardSync(db)
    result1 = sync.sync_items(
        [_make_item("task_state", payload=initial_payload)], db, ORG_ID, INCIDENT_ID
    )
    assert result1["applied"] == 1

    conflict_payload = {
        "entity_type": "task", "entity_id": "task_1", "status": "completed",
    }
    result2 = sync.sync_items(
        [_make_item("task_state", payload=conflict_payload)], db, ORG_ID, INCIDENT_ID
    )

    assert len(result2["conflicts"]) == 1
    conflict = result2["conflicts"][0]
    assert conflict["status"] == "conflict"
    assert conflict["local"]["status"] == "pending"
    assert conflict["remote"]["status"] == "completed"

    # Verify the original was NOT overwritten.
    rows = db.execute(
        select(EdgeSyncApplied)
        .where(EdgeSyncApplied.incident_id == INCIDENT_ID)
        .order_by(EdgeSyncApplied.id.asc())
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].payload["status"] == "pending"

    # Verify a SyncConflict row was recorded.
    conflict_rows = db.execute(
        select(SyncConflict).where(SyncConflict.incident_id == INCIDENT_ID)
    ).scalars().all()
    assert len(conflict_rows) == 1


def test_monotonic_sequence_numbers(db):
    """Items without sequence numbers get assigned monotonic sequences."""
    items = [
        _make_item("text", payload={"entity_id": "e1"}, sequence=None),
        _make_item("text", payload={"entity_id": "e2"}, sequence=None),
        _make_item("text", payload={"entity_id": "e3"}, sequence=None),
    ]
    sync = StoreAndForwardSync(db)
    sync.sync_items(items, db, ORG_ID, INCIDENT_ID)

    rows = db.execute(
        select(EdgeSyncApplied)
        .where(EdgeSyncApplied.incident_id == INCIDENT_ID)
        .order_by(EdgeSyncApplied.id.asc())
    ).scalars().all()
    sequences = [r.sequence for r in rows]
    assert sequences == sorted(sequences)
    assert sequences[0] < sequences[1] < sequences[2]


def test_crdt_merge_for_assigned_to(db):
    """CRDT fields (assigned_to) are union-merged instead of surfacing conflict."""
    initial = {
        "entity_type": "task", "entity_id": "task_2", "assigned_to": ["alice"],
    }
    sync = StoreAndForwardSync(db)
    sync.sync_items(
        [_make_item("task_state", payload=initial)], db, ORG_ID, INCIDENT_ID
    )

    conflict = {
        "entity_type": "task", "entity_id": "task_2", "assigned_to": ["bob"],
    }
    result = sync.sync_items(
        [_make_item("task_state", payload=conflict)], db, ORG_ID, INCIDENT_ID
    )

    # CRDT fields auto-merge — no conflict surfaced.
    assert len(result["conflicts"]) == 0
    assert result["applied"] == 1
    assert "merged" not in result  # merged is in the per-item result, not the summary

    # Verify the merged record was stored.
    rows = db.execute(
        select(EdgeSyncApplied)
        .where(EdgeSyncApplied.incident_id == INCIDENT_ID)
        .order_by(EdgeSyncApplied.id.asc())
    ).scalars().all()
    assert len(rows) == 2  # original + merged
    merged_row = rows[-1]
    assert set(merged_row.payload["assigned_to"]) == {"alice", "bob"}


def test_cross_batch_dedup(db):
    """Items already applied in a previous batch are skipped."""
    items = [_make_item("text", payload={"entity_id": "e1", "value": "v1"})]
    sync = StoreAndForwardSync(db)
    result1 = sync.sync_items(items, db, ORG_ID, INCIDENT_ID)
    assert result1["applied"] == 1

    result2 = sync.sync_items(items, db, ORG_ID, INCIDENT_ID)
    assert result2["received"] == 1
    assert result2["applied"] == 0
    assert result2["deduplicated"] == 1
