"""Tests for the hash-chained audit log (write_audit + verify_chain).

Uses the real PostgreSQL database via SessionLocal. Cleans up all test rows
after each test to keep the chain pristine for subsequent runs.
"""

import pytest
from sqlalchemy import delete

from app.db import SessionLocal
from app.lib.audit import verify_chain, write_audit
from app.models.events import AuditChainHead, Event

ORG_ID = "org_test_audit"
INCIDENT_ID = "inc_test_audit"


@pytest.fixture
def db():
    """Yield a session backed by the real Postgres DB and clean up after."""
    session = SessionLocal()
    # Pre-clean any leftover rows for this org.
    session.execute(delete(Event).where(Event.org_id == ORG_ID))
    session.execute(delete(AuditChainHead).where(AuditChainHead.org_id == ORG_ID))
    session.commit()
    try:
        yield session
    finally:
        session.execute(delete(Event).where(Event.org_id == ORG_ID))
        session.execute(delete(AuditChainHead).where(AuditChainHead.org_id == ORG_ID))
        session.commit()
        session.close()


def test_write_audit_appends_with_correct_hash(db):
    """A single event has empty prev_hash and a hash over ("" + payload)."""
    ev = write_audit(
        db,
        org_id=ORG_ID,
        incident_id=INCIDENT_ID,
        actor="alice",
        action="create",
        entity="observation:01J9TEST",
        before=None,
        after={"value": 1.5},
    )
    assert ev.prev_hash == ""
    assert ev.hash  # non-empty
    assert len(ev.id) == 26
    # verify_chain should report a valid single-event chain.
    assert verify_chain(db, ORG_ID) is True


def test_three_event_chain_valid(db):
    """Insert 3 events, recomputes hashes, asserts chain validity."""
    e1 = write_audit(
        db, ORG_ID, INCIDENT_ID, "alice", "create", "obs:1",
        before=None, after={"v": 1},
    )
    e2 = write_audit(
        db, ORG_ID, INCIDENT_ID, "bob", "update", "obs:1",
        before={"v": 1}, after={"v": 2},
    )
    e3 = write_audit(
        db, ORG_ID, INCIDENT_ID, "carol", "delete", "obs:1",
        before={"v": 2}, after=None,
    )
    # Chain links: e2.prev_hash == e1.hash, e3.prev_hash == e2.hash
    assert e2.prev_hash == e1.hash
    assert e3.prev_hash == e2.hash
    # Full chain verifies.
    result = verify_chain(db, ORG_ID)
    assert result is True


def test_tamper_middle_row_breaks_chain(db):
    """Tampering the middle row's `after` field must break verification."""
    write_audit(
        db, ORG_ID, INCIDENT_ID, "alice", "create", "obs:1",
        before=None, after={"v": 1},
    )
    write_audit(
        db, ORG_ID, INCIDENT_ID, "bob", "update", "obs:1",
        before={"v": 1}, after={"v": 2},
    )
    write_audit(
        db, ORG_ID, INCIDENT_ID, "carol", "delete", "obs:1",
        before={"v": 2}, after=None,
    )
    # Sanity: chain is valid before tampering.
    assert verify_chain(db, ORG_ID) is True

    # Tamper the middle row: change `after` without updating the hash.
    middle = (
        db.query(Event)
        .filter(Event.org_id == ORG_ID, Event.action == "update")
        .one()
    )
    middle.after = {"v": 999}  # tampered
    db.commit()

    result = verify_chain(db, ORG_ID)
    # verify_chain returns the index of the first mismatch (the middle row, idx=1),
    # which is not True.
    assert result is not True
    assert result == 1


def test_empty_chain_is_valid(db):
    """An org with no events has a trivially valid chain."""
    assert verify_chain(db, ORG_ID) is True


def test_chain_isolated_per_org(db):
    """Events for different orgs do not interfere with each other's chains."""
    other_org = "org_test_audit_other"
    try:
        write_audit(db, ORG_ID, INCIDENT_ID, "alice", "create", "obs:1")
        write_audit(db, other_org, INCIDENT_ID, "mallory", "create", "obs:2")
        assert verify_chain(db, ORG_ID) is True
        assert verify_chain(db, other_org) is True
    finally:
        db.execute(delete(Event).where(Event.org_id == other_org))
        db.commit()
