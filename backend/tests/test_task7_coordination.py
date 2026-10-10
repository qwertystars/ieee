from __future__ import annotations

from unittest.mock import MagicMock, patch

import anyio
import pytest
from sqlalchemy import delete, select

from app.auth.abac import ABACEngine
from app.auth.abac_types import Actor, Context, Subject
from app.db import SessionLocal
from app.deps import (
    SensitiveOperation,
    check_sensitive_operation,
    is_token_revoked_strict,
    revoke_token,
)
from app.eval.jobs import EvaluationJobStore
from app.models.coordination import CredentialState, EmergencyOverrideRecord, EvaluationJob
from app.models.events import Event
from app.models.user import User
from app.realtime.manager import WebSocketManager
from app.realtime.routes import _can_access_incident


class MockWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, message: dict[str, object]) -> None:
        self.sent.append(message)


def _actor(org_id: str, user_id: str, role: str = "admin") -> Actor:
    return Actor(user_id=user_id, role=role, org_id=org_id, incident_assignments=())


def _subject(org_id: str) -> Subject:
    return Subject(
        type="observation",
        sensitivity="sensitive",
        org_id=org_id,
        incident_id="incident-1",
        jurisdiction="all",
    )


def test_override_is_visible_after_engine_restart_and_org_scoped() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(EmergencyOverrideRecord))
        db.commit()
        admin = _actor("org-a", "admin-a")
        target = _actor("org-a", "target-a", role="field_responder")
        foreign = _actor("org-b", "target-a", role="field_responder")
        engine = ABACEngine(db=db)
        engine.grant_emergency_override(db, admin, target.user_id, "incident response")

        restarted = ABACEngine(db=db)
        assert restarted.can(target, "read", _subject("org-a"), Context("org-a"))
        assert not restarted.can(foreign, "read", _subject("org-b"), Context("org-b"))
        record = db.execute(
            select(EmergencyOverrideRecord).where(
                EmergencyOverrideRecord.org_id == "org-a",
                EmergencyOverrideRecord.target_user_id == target.user_id,
            )
        ).scalar_one()
        audit = db.query(Event).filter(
            Event.org_id == "org-a",
            Event.action == "emergency_override_grant",
        ).one()
        assert audit.after["override_id"] == record.id
    finally:
        db.execute(delete(EmergencyOverrideRecord))
        db.commit()
        db.close()


def test_revocation_denies_when_redis_is_partitioned() -> None:
    redis_client = MagicMock()
    redis_client.set.return_value = True
    token = "task7-partition-token"
    with patch("app.deps.get_redis", return_value=redis_client):
        revoke_token(token, 60)
    with patch("app.deps.get_redis", return_value=None):
        assert is_token_revoked_strict(token) is True


def test_stale_redis_cannot_resurrect_durable_revocation() -> None:
    db = SessionLocal()
    try:
        token = "task7-stale-replica-token"
        revoke_token(token, 60, db=db, org_id="org-a")
        stale = MagicMock()
        stale.exists.return_value = 0
        with patch("app.deps.get_redis", return_value=stale):
            assert is_token_revoked_strict(token, db) is True
    finally:
        db.execute(delete(CredentialState))
        db.commit()
        db.close()


def test_sensitive_operation_checks_durable_revocation_before_redis() -> None:
    db = SessionLocal()
    try:
        token = "task7-durable-sensitive-token"
        revoke_token(token, 60, db=db, org_id="org-a")
        stale = MagicMock()
        stale.exists.return_value = 0
        with patch("app.deps.get_redis", return_value=stale):
            assert not check_sensitive_operation(
                token,
                SensitiveOperation.ADMIN_CHANGE,
                db=db,
            )
    finally:
        db.execute(delete(CredentialState))
        db.commit()
        db.close()


def test_split_brain_override_revoke_wins_from_second_engine() -> None:
    first_db = SessionLocal()
    second_db = SessionLocal()
    try:
        first_db.execute(delete(EmergencyOverrideRecord))
        first_db.commit()
        admin = _actor("org-a", "admin-a")
        target = _actor("org-a", "target-a", role="field_responder")
        first = ABACEngine(db=first_db)
        second = ABACEngine(db=second_db)
        first.grant_emergency_override(first_db, admin, target.user_id, "split-brain test")
        assert second.revoke_emergency_override(second_db, admin, target.user_id)
        assert not first.can(target, "read", _subject("org-a"), Context("org-a"))
    finally:
        first_db.execute(delete(EmergencyOverrideRecord))
        first_db.commit()
        first_db.close()
        second_db.close()


def test_evaluation_job_survives_store_restart_and_cross_org_isolation() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(EvaluationJob))
        db.commit()
        first = EvaluationJobStore(db)
        job = first.create("org-a", "user-a", "eval", {"seed": 7})
        restarted = EvaluationJobStore(db)
        assert restarted.get(job.id, "org-a") is not None
        assert restarted.get(job.id, "org-b") is None
    finally:
        db.execute(delete(EvaluationJob))
        db.commit()
        db.close()


def test_evaluation_job_claim_is_exclusive_across_sessions() -> None:
    first_db = SessionLocal()
    second_db = SessionLocal()
    try:
        first_db.execute(delete(EvaluationJob))
        first_db.commit()
        job = EvaluationJobStore(first_db).create(
            "org-a", "user-a", "optimizer", {"seed": 7},
        )
        first_claim = EvaluationJobStore(first_db).claim(job.id, "org-a")
        second_claim = EvaluationJobStore(second_db).claim(job.id, "org-a")
        assert first_claim is not None
        assert second_claim is None
    finally:
        first_db.execute(delete(EvaluationJob))
        first_db.commit()
        first_db.close()
        second_db.close()


def test_realtime_shared_fanout_is_org_scoped() -> None:
    envelopes: list[dict[str, object]] = []

    async def publish(envelope: dict[str, object]) -> None:
        envelopes.append(envelope)

    async def scenario() -> None:
        first = WebSocketManager(publisher=publish)
        second = WebSocketManager()
        same_org = MockWebSocket()
        foreign_org = MockWebSocket()
        await first.connect(same_org, "incident-1", "admin", "org-a")
        await second.connect(foreign_org, "incident-1", "admin", "org-b")
        await first.broadcast("incident-1", {"type": "state", "payload": {"x": 1}}, "org-a")
        await second.handle_shared_message(envelopes[0])
        assert same_org.sent == [{"type": "state", "payload": {"x": 1}}]
        assert foreign_org.sent == []

    anyio.run(scenario)


def test_realtime_shared_fanout_rejects_unscoped_envelopes() -> None:
    delivered: list[dict[str, object]] = []

    async def scenario() -> None:
        manager = WebSocketManager()
        websocket = MockWebSocket()
        await manager.connect(websocket, "incident-1", "admin", "org-a")
        await manager.handle_shared_message(
            {
                "origin": "other-instance",
                "incident_id": "incident-1",
                "message": {"type": "state", "payload": {"secret": "x"}},
            }
        )
        delivered.extend(websocket.sent)

    anyio.run(scenario)
    assert delivered == []


def test_realtime_broadcast_does_not_publish_without_tenant_scope() -> None:
    envelopes: list[dict[str, object]] = []

    async def publish(envelope: dict[str, object]) -> None:
        envelopes.append(envelope)

    async def scenario() -> None:
        await WebSocketManager(publisher=publish).broadcast(
            "incident-1", {"type": "state", "payload": {}},
        )

    anyio.run(scenario)
    assert envelopes == []


def test_realtime_access_does_not_treat_incident_url_as_assignment() -> None:
    db = SessionLocal()
    try:
        user = User(
            id="01TASK7UNASSIGNEDUSER000000",
            email="task7-unassigned@example.test",
            hashed_password="unused",
            role="field_responder",
            org_id="org-a",
            created_at=1,
        )
        assert not _can_access_incident(user, "incident-a", "org-a", db)
    finally:
        db.close()


@pytest.mark.parametrize("limit", [1, 2])
def test_rate_limit_state_is_not_process_local(limit: int) -> None:
    from app.lib.rate_limit import consume_rate_limit

    client = MagicMock()
    client.pipeline.return_value.__enter__.return_value.incr.return_value = 1
    client.pipeline.return_value.__enter__.return_value.execute.return_value = [1, True]
    with patch("app.lib.rate_limit.get_redis", return_value=client):
        assert consume_rate_limit("org-a", "user-a", limit, 60)
        client.pipeline.assert_called()
