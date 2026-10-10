#!/usr/bin/env python3
# /// script
# dependencies = []
# ///

from __future__ import annotations

import argparse
import base64
import sys
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))

from app.auth.command_authorization import build_signature_bytes
from app.auth.passwords import hash_password
from app.db import SessionLocal, engine
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.main import app
from app.models.alert import Alert, AlertDecision, CommandApproval, CommandSigningKey
from app.models.entities import OperationalTask
from app.models.events import AuditChainHead, Event
from app.models.incident import Incident
from app.models.user import User

ORG_ID = "org_task21_verifier"


@dataclass(frozen=True, slots=True)
class Signer:
    email: str
    user_id: str
    key_id: str
    private_key: Ed25519PrivateKey


def _signer(db, role: str) -> Signer:
    email = f"{role}@task21.invalid"
    user = User(id=generate_ulid(), email=email, hashed_password=hash_password("task21"), role=role, org_id=ORG_ID, created_at=now_ms())
    db.add(user)
    db.flush()
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = generate_ulid()
    db.add(CommandSigningKey(id=generate_ulid(), org_id=ORG_ID, user_id=user.id, key_id=key_id, public_key=base64.b64encode(public_key).decode("ascii"), active=True, created_at=now_ms()))
    return Signer(email, user.id, key_id, private_key)


def _approval(signer: Signer, incident_id: str, alert_id: str, signed_at: int, expires_at: int | None = None, nonce: str | None = None) -> dict[str, str | int]:
    resolved_expiry = signed_at + 300_000 if expires_at is None else expires_at
    resolved_nonce = generate_ulid() if nonce is None else nonce
    payload = {"incident_id": incident_id, "alert_id": alert_id, "command_type": "task_creation", "rationale": "Task 21 denial fixture"}
    signature = signer.private_key.sign(build_signature_bytes(payload, nonce=resolved_nonce, expires_at_ms=resolved_expiry))
    return {"user_id": signer.user_id, "key_id": signer.key_id, "nonce": resolved_nonce, "signed_at_ms": signed_at, "expires_at_ms": resolved_expiry, "signature": base64.b64encode(signature).decode("ascii")}


def _cleanup() -> None:
    db = SessionLocal()
    try:
        db.query(OperationalTask).filter(OperationalTask.org_id == ORG_ID).delete(synchronize_session=False)
        decision_ids = [row.id for row in db.query(AlertDecision).filter(AlertDecision.org_id == ORG_ID).all()]
        if decision_ids:
            db.query(CommandApproval).filter(CommandApproval.decision_id.in_(decision_ids)).delete(synchronize_session=False)
        db.query(AlertDecision).filter(AlertDecision.org_id == ORG_ID).delete(synchronize_session=False)
        db.query(CommandSigningKey).filter(CommandSigningKey.org_id == ORG_ID).delete(synchronize_session=False)
        db.query(Alert).filter(Alert.org_id == ORG_ID).delete(synchronize_session=False)
        db.query(Incident).filter(Incident.org_id == ORG_ID).delete(synchronize_session=False)
        db.query(User).filter(User.org_id == ORG_ID).delete(synchronize_session=False)
        db.query(Event).filter(Event.org_id == ORG_ID).delete(synchronize_session=False)
        db.query(AuditChainHead).filter(AuditChainHead.org_id == ORG_ID).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _schema_ready() -> bool:
    return "operational_tasks" in inspect(engine).get_table_names()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, choices=("stale-expired-replay-and-unauthorized-export",))
    parser.add_argument("--freshness-s", type=int, default=300)
    parser.add_argument("--require-ed25519", action="store_true")
    parser.add_argument("--require-dual-control", action="store_true")
    args = parser.parse_args()
    if args.freshness_s != 300 or not args.require_ed25519 or not args.require_dual_control:
        raise SystemExit("canonical Task 21 integrity flags are required")
    if not _schema_ready():
        print("status=DEFERRED_EXTERNAL")
        return 2
    _cleanup()
    db = SessionLocal()
    try:
        ts = now_ms()
        manager, coordinator = _signer(db, "emergency_manager"), _signer(db, "responder_coordinator")
        incident_id, alert_id = generate_ulid(), generate_ulid()
        db.add(Incident(id=incident_id, org_id=ORG_ID, title="Task 21", disaster_type="flood", severity="high", status="active", start_time=ts, created_at=ts, updated_at=ts))
        db.flush()
        db.add(Alert(id=alert_id, org_id=ORG_ID, incident_id=incident_id, alert_type="trapped_person", title="Task 21", message="integrity fixture", severity="high", recommended_action="dispatch", confidence_vector={"s": 1.0}, status="draft", created_by=manager.user_id, created_at=ts, updated_at=ts))
        db.commit()
        decision = AlertDecision(id=generate_ulid(), org_id=ORG_ID, incident_id=incident_id, alert_id=alert_id, command_type="task_creation", status="awaiting_second_approval", rationale="replay fixture", payload={"incident_id": incident_id, "alert_id": alert_id, "command_type": "task_creation", "rationale": "Task 21 denial fixture"}, created_by=manager.user_id, created_at=ts, updated_at=ts)
        db.add(decision)
        db.flush()
        replay = _approval(manager, incident_id, alert_id, ts)
        db.add(CommandApproval(id=generate_ulid(), org_id=ORG_ID, incident_id=incident_id, alert_id=alert_id, decision_id=decision.id, approver_id=manager.user_id, approver_role="emergency_manager", key_id=manager.key_id, nonce=replay["nonce"], signed_at_ms=replay["signed_at_ms"], expires_at_ms=replay["expires_at_ms"], signature=replay["signature"], created_at=ts))
        db.commit()
    finally:
        db.close()
    try:
        with TestClient(app) as client:
            manager_token = client.post("/api/auth/login", data={"username": manager.email, "password": "task21"}).json()["access_token"]
            coordinator_token = client.post("/api/auth/login", data={"username": coordinator.email, "password": "task21"}).json()["access_token"]
            def submit(token: str, approval: dict[str, str | int], key: str | None = None) -> int:
                return client.post(f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch", json={"command_type": "task_creation", "rationale": "Task 21 denial fixture", "approval": approval}, headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key or generate_ulid()}).status_code
            assert submit(manager_token, _approval(manager, incident_id, alert_id, ts - 301_000)) == 422
            assert submit(manager_token, _approval(manager, incident_id, alert_id, ts, expires_at=ts - 1)) == 422
            assert submit(manager_token, replay) == 409
            assert client.get(f"/api/privacy/subjects/{manager.user_id}/export", headers={"Authorization": f"Bearer {coordinator_token}"}).status_code == 403
            reconstruction = client.get(f"/api/incidents/{incident_id}/audit-reconstruction", headers={"Authorization": f"Bearer {manager_token}"})
            assert reconstruction.status_code == 200 and reconstruction.json()["integrity"]["audit_chain_valid"] is True
        db = SessionLocal()
        try:
            assert db.query(OperationalTask).filter(OperationalTask.org_id == ORG_ID).count() == 0
            assert db.query(Event).filter(Event.org_id == ORG_ID, Event.action.like("security.denied.%")).count() >= 4
        finally:
            db.close()
        print("PASS")
        return 0
    finally:
        _cleanup()


if __name__ == "__main__":
    sys.exit(main())
