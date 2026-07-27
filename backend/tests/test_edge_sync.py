"""Tests for edge-first sync — outbox dedup and ordered application.

Uses the real PostgreSQL database via SessionLocal. The edge_sync_applied
and edge_sync_state tables are created by Alembic migrations. All test rows
are cleaned up.
"""

import pytest
from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.lib.ulid import generate_ulid
from app.realtime.edge_sync import (
    EdgeSync,
    EdgeSyncApplied,
    EdgeSyncState,
    compute_content_hash,
)

ORG_ID = "org_test_edge_sync"
INCIDENT_ID = "inc_test_edge_sync"


@pytest.fixture
def db():
    """Yield a session and clean up test rows after each test."""
    session = SessionLocal()
    session.execute(delete(EdgeSyncApplied).where(EdgeSyncApplied.org_id == ORG_ID))
    session.execute(delete(EdgeSyncState).where(EdgeSyncState.org_id == ORG_ID))
    session.commit()
    try:
        yield session
    finally:
        session.execute(delete(EdgeSyncApplied).where(EdgeSyncApplied.org_id == ORG_ID))
        session.execute(delete(EdgeSyncState).where(EdgeSyncState.org_id == ORG_ID))
        session.commit()
        session.close()


def _make_item(
    sequence: int,
    payload: dict | None = None,
    content_hash: str | None = None,
    item_type: str = "status_update",
    item_id: str | None = None,
) -> dict:
    """Build an outbox item with computed content_hash."""
    payload = payload or {"value": f"v_{sequence}"}
    return {
        "item_id": item_id or generate_ulid(),
        "content_hash": content_hash or compute_content_hash(payload),
        "item_type": item_type,
        "payload": payload,
        "created_at": 1721300000000 + sequence,
        "sequence": sequence,
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
