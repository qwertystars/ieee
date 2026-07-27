"""Integration test — audit chain tamper detection.

Verifies that the hash-chained audit log detects tampering of any row's
payload (actor, action, entity, before, after, ts). Modifying any field
without recomputing the hash breaks the chain at that index.

Uses the real PostgreSQL database via SessionLocal. No mocking.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.db import SessionLocal
from app.lib.audit import verify_chain, write_audit
from app.models.events import Event

ORG_ID = "org_test_audit_tamper"
INCIDENT_ID = "inc_test_audit_tamper"


@pytest.fixture
def db():
    """Yield a session and clean up test rows before and after."""
    session = SessionLocal()
    session.execute(delete(Event).where(Event.org_id == ORG_ID))
    session.commit()
    try:
        yield session
    finally:
        session.execute(delete(Event).where(Event.org_id == ORG_ID))
        session.commit()
        session.close()


def test_chain_valid_before_tampering(db) -> None:
    """A freshly written 3-event chain must verify as True."""
    write_audit(db, ORG_ID, INCIDENT_ID, "alice", "create", "obs:1",
                after={"v": 1})
    write_audit(db, ORG_ID, INCIDENT_ID, "bob", "update", "obs:1",
                before={"v": 1}, after={"v": 2})
    write_audit(db, ORG_ID, INCIDENT_ID, "carol", "delete", "obs:1",
                before={"v": 2})
    assert verify_chain(db, ORG_ID) is True


def test_tamper_after_field_breaks_chain(db) -> None:
    """Modifying the `after` field of the middle row breaks the chain at index 1."""
    write_audit(db, ORG_ID, INCIDENT_ID, "alice", "create", "obs:1",
                after={"v": 1})
    write_audit(db, ORG_ID, INCIDENT_ID, "bob", "update", "obs:1",
                before={"v": 1}, after={"v": 2})
    write_audit(db, ORG_ID, INCIDENT_ID, "carol", "delete", "obs:1",
                before={"v": 2})

    assert verify_chain(db, ORG_ID) is True

    # Tamper: change the middle row's `after` without updating its hash.
    middle = (
        db.query(Event)
        .filter(Event.org_id == ORG_ID, Event.action == "update")
        .one()
    )
    middle.after = {"v": 999}
    db.commit()

    result = verify_chain(db, ORG_ID)
    assert result is not True, "chain should be broken after tampering"
    assert result == 1, f"expected break at index 1, got {result}"


def test_tamper_actor_field_breaks_chain(db) -> None:
    """Modifying the `actor` field of the first row breaks the chain at index 0."""
    write_audit(db, ORG_ID, INCIDENT_ID, "alice", "create", "obs:1",
                after={"v": 1})
    write_audit(db, ORG_ID, INCIDENT_ID, "bob", "update", "obs:1",
                before={"v": 1}, after={"v": 2})

    assert verify_chain(db, ORG_ID) is True

    first = (
        db.query(Event)
        .filter(Event.org_id == ORG_ID, Event.action == "create")
        .one()
    )
    first.actor = "mallory"
    db.commit()

    result = verify_chain(db, ORG_ID)
    assert result is not True
    assert result == 0, f"expected break at index 0, got {result}"


def test_tamper_hash_directly_breaks_chain(db) -> None:
    """Directly modifying a row's hash breaks the chain at that row."""
    write_audit(db, ORG_ID, INCIDENT_ID, "alice", "create", "obs:1")
    write_audit(db, ORG_ID, INCIDENT_ID, "bob", "update", "obs:1")

    assert verify_chain(db, ORG_ID) is True

    first = (
        db.query(Event)
        .filter(Event.org_id == ORG_ID, Event.action == "create")
        .one()
    )
    first.hash = "0" * 64  # fake hash
    db.commit()

    result = verify_chain(db, ORG_ID)
    assert result is not True
    assert result == 0


def test_tamper_cascades_to_subsequent_rows(db) -> None:
    """Tampering row 0 breaks verification at row 0, not just row 1.

    Because row 1's prev_hash was computed from row 0's original hash,
    changing row 0's hash also invalidates row 1's prev_hash link.
    verify_chain reports the FIRST break (index 0).
    """
    write_audit(db, ORG_ID, INCIDENT_ID, "alice", "create", "obs:1")
    write_audit(db, ORG_ID, INCIDENT_ID, "bob", "update", "obs:1")
    write_audit(db, ORG_ID, INCIDENT_ID, "carol", "delete", "obs:1")

    assert verify_chain(db, ORG_ID) is True

    first = (
        db.query(Event)
        .filter(Event.org_id == ORG_ID, Event.action == "create")
        .one()
    )
    # Tamper: change the payload AND the hash (but to a wrong value).
    first.after = {"v": "tampered"}
    first.hash = "f" * 64
    db.commit()

    result = verify_chain(db, ORG_ID)
    assert result == 0, f"expected break at index 0, got {result}"
