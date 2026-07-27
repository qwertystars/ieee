"""Tests for the ABAC policy engine (can + emergency override).

Uses the real PostgreSQL database via SessionLocal for audit-chain tests
(grant/revoke write to the events table). Policy-only tests use a fresh
ABACEngine with an injectable clock for deterministic override-expiry checks.
"""

import pytest
from sqlalchemy import delete

from app.auth.abac import DEFAULT_OVERRIDE_TTL_SECONDS, ABACEngine
from app.auth.abac_types import Actor, Context, Subject
from app.db import SessionLocal
from app.models.events import Event

ORG = "org_test_abac"
INC = "inc_test_abac"
OTHER_ORG = "org_test_abac_other"


@pytest.fixture
def db():
    """Yield a session backed by the real Postgres DB and clean up after."""
    session = SessionLocal()
    session.execute(delete(Event).where(Event.org_id == ORG))
    session.execute(delete(Event).where(Event.org_id == OTHER_ORG))
    session.commit()
    try:
        yield session
    finally:
        session.execute(delete(Event).where(Event.org_id == ORG))
        session.execute(delete(Event).where(Event.org_id == OTHER_ORG))
        session.commit()
        session.close()


def _ctx(org: str = ORG, inc: str = INC, emergency: bool = False) -> Context:
    return Context(
        current_org_id=org,
        current_incident_id=inc,
        emergency_mode=emergency,
    )


def _subject(
    type_: str = "observation",
    sensitivity: str = "internal",
    org: str = ORG,
    inc: str = INC,
    jurisdiction: str = "zone_north",
    task_id: str | None = None,
) -> Subject:
    return Subject(
        type=type_,
        sensitivity=sensitivity,
        org_id=org,
        incident_id=inc,
        jurisdiction=jurisdiction,
        task_id=task_id,
    )


def _actor(
    role: str = "field_responder",
    org: str = ORG,
    assignments: tuple[str, ...] = (INC,),
    jurisdiction: str = "zone_north",
    current_task: str | None = None,
    user_id: str = "user_field_001",
) -> Actor:
    return Actor(
        user_id=user_id,
        role=role,
        org_id=org,
        incident_assignments=assignments,
        jurisdiction=jurisdiction,
        current_task=current_task,
    )


# ── Policy rule tests ─────────────────────────────────────────────────────


def test_user_without_jurisdiction_denied():
    """Field responder in zone_north cannot read data in zone_south."""
    engine = ABACEngine()
    actor = _actor(jurisdiction="zone_north")
    subject = _subject(jurisdiction="zone_south", sensitivity="internal")
    assert engine.can(actor, "read", subject, _ctx()) is False


def test_user_with_matching_incident_assignment_can_access():
    """Field responder assigned to the incident can read internal data."""
    engine = ABACEngine()
    actor = _actor(
        role="field_responder",
        assignments=(INC,),
        jurisdiction="zone_north",
    )
    subject = _subject(sensitivity="internal", jurisdiction="zone_north")
    assert engine.can(actor, "read", subject, _ctx()) is True


def test_sensitive_data_requires_elevated_role():
    """Field responder cannot read sensitive data without task assignment."""
    engine = ABACEngine()
    actor = _actor(role="field_responder", current_task=None)
    subject = _subject(sensitivity="sensitive")
    assert engine.can(actor, "read", subject, _ctx()) is False


def test_sensitive_data_accessible_with_task_assignment():
    """Field responder with matching current_task can read sensitive task data."""
    engine = ABACEngine()
    actor = _actor(role="field_responder", current_task="task_001")
    subject = _subject(type_="task", sensitivity="sensitive", task_id="task_001")
    assert engine.can(actor, "read", subject, _ctx()) is True


def test_admin_can_access_everything():
    """Admin role bypasses jurisdiction, incident, and sensitivity checks."""
    engine = ABACEngine()
    admin = _actor(
        role="admin",
        assignments=(),  # not assigned to any incident
        jurisdiction="zone_east",  # different jurisdiction
        user_id="user_admin_001",
    )
    subject = _subject(sensitivity="sensitive", jurisdiction="zone_north")
    assert engine.can(admin, "read", subject, _ctx()) is True
    assert engine.can(admin, "write", subject, _ctx()) is True
    assert engine.can(admin, "delete", subject, _ctx()) is True
    assert engine.can(admin, "approve", subject, _ctx()) is True


def test_cross_org_access_denied():
    """User in org A cannot access data in org B."""
    engine = ABACEngine()
    actor = _actor(org=ORG)
    subject = _subject(org=OTHER_ORG)
    assert engine.can(actor, "read", subject, _ctx(org=ORG)) is False


def test_viewer_can_read_but_not_write():
    """Viewer role has read access but not write/delete/approve."""
    engine = ABACEngine()
    viewer = _actor(role="viewer", assignments=(INC,))
    subject = _subject(sensitivity="internal")
    assert engine.can(viewer, "read", subject, _ctx()) is True
    assert engine.can(viewer, "write", subject, _ctx()) is False
    assert engine.can(viewer, "delete", subject, _ctx()) is False


def test_unknown_action_denied():
    """An action not in the known set is denied."""
    engine = ABACEngine()
    admin = _actor(role="admin")
    subject = _subject()
    assert engine.can(admin, "teleport", subject, _ctx()) is False


def test_emergency_manager_bypasses_incident_assignment():
    """Emergency_manager can access data without being assigned to the incident."""
    engine = ABACEngine()
    em = _actor(
        role="emergency_manager",
        assignments=(),  # not assigned
        jurisdiction="zone_north",
        user_id="user_em_001",
    )
    subject = _subject(sensitivity="internal", jurisdiction="zone_north")
    assert engine.can(em, "read", subject, _ctx()) is True
    assert engine.can(em, "write", subject, _ctx()) is True
    # Sensitive data still requires admin or task assignment for EM.
    sensitive = _subject(sensitivity="sensitive")
    assert engine.can(em, "read", sensitive, _ctx()) is True  # EM is elevated


# ── Emergency override tests ──────────────────────────────────────────────


def test_emergency_override_grants_temporary_access(db):
    """Admin grants override to field responder; responder can now access data."""
    engine = ABACEngine()
    admin = _actor(
        role="admin",
        assignments=(),
        jurisdiction="zone_north",
        user_id="user_admin_002",
    )
    responder = _actor(
        role="field_responder",
        assignments=(),  # not assigned to the incident
        jurisdiction="zone_south",  # wrong jurisdiction
        user_id="user_resp_002",
    )
    subject = _subject(sensitivity="internal", jurisdiction="zone_north")
    # Before override: denied (wrong jurisdiction + not assigned).
    assert engine.can(responder, "read", subject, _ctx()) is False

    # Grant override.
    override = engine.grant_emergency_override(
        db, admin, responder.user_id, "Crisis: responder needs cross-zone access",
    )
    assert override.granted_by == admin.user_id
    assert override.expires_at > override.granted_at

    # After override: responder can now read (override bypasses jurisdiction
    # and incident checks).
    assert engine.can(responder, "read", subject, _ctx()) is True

    # Audit entry was written.
    from sqlalchemy import select

    rows = db.execute(
        select(Event).where(
            Event.org_id == ORG,
            Event.action == "emergency_override_grant",
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor == admin.user_id
    assert rows[0].entity == f"user:{responder.user_id}"
    assert rows[0].after["reason"] == "Crisis: responder needs cross-zone access"


def test_emergency_override_expires_after_ttl(db):
    """After TTL elapses, the override is no longer active."""
    clock_state = [1_700_000_000_000]  # fixed start time
    engine = ABACEngine(clock=lambda: clock_state[0])

    admin = _actor(
        role="admin",
        assignments=(),
        jurisdiction="zone_north",
        user_id="user_admin_003",
    )
    responder = _actor(
        role="field_responder",
        assignments=(),
        jurisdiction="zone_south",
        user_id="user_resp_003",
    )
    subject = _subject(sensitivity="internal", jurisdiction="zone_north")

    # Grant override with 1-second TTL.
    engine.grant_emergency_override(
        db=db,
        admin_actor=admin,
        target_user_id=responder.user_id,
        reason="Short-lived override",
        ttl_seconds=1,
    )
    # Override active: access granted.
    assert engine.can(responder, "read", subject, _ctx()) is True

    # Advance clock past TTL (1 second = 1000 ms; advance by 1001 ms).
    clock_state[0] += 1001
    # Override expired: access denied.
    assert engine.can(responder, "read", subject, _ctx()) is False


def test_revoke_emergency_override(db):
    """Admin revokes an active override; access is immediately withdrawn."""
    engine = ABACEngine()
    admin = _actor(
        role="admin",
        assignments=(),
        jurisdiction="zone_north",
        user_id="user_admin_004",
    )
    responder = _actor(
        role="field_responder",
        assignments=(),
        jurisdiction="zone_south",
        user_id="user_resp_004",
    )
    subject = _subject(sensitivity="internal", jurisdiction="zone_north")

    engine.grant_emergency_override(
        db, admin, responder.user_id, "Temporary access for evacuation",
    )
    assert engine.can(responder, "read", subject, _ctx()) is True

    revoked = engine.revoke_emergency_override(db, admin, responder.user_id)
    assert revoked is True
    assert engine.can(responder, "read", subject, _ctx()) is False

    # Revoking a non-existent override returns False.
    assert engine.revoke_emergency_override(db, admin, "nonexistent") is False


def test_non_admin_cannot_grant_override(db):
    """Emergency_manager cannot grant overrides (only admin)."""
    engine = ABACEngine()
    em = _actor(
        role="emergency_manager",
        assignments=(),
        jurisdiction="zone_north",
        user_id="user_em_002",
    )
    with pytest.raises(PermissionError, match="only admin"):
        engine.grant_emergency_override(
            db, em, "user_target_001", "should fail",
        )


def test_grant_override_requires_reason(db):
    """Empty reason is rejected."""
    engine = ABACEngine()
    admin = _actor(role="admin", user_id="user_admin_005")
    with pytest.raises(ValueError, match="reason is required"):
        engine.grant_emergency_override(
            db, admin, "user_target_002", "  ",
        )


def test_default_override_ttl_is_one_hour():
    """DEFAULT_OVERRIDE_TTL_SECONDS is 3600 (1 hour)."""
    assert DEFAULT_OVERRIDE_TTL_SECONDS == 3600
