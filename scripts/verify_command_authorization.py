#!/usr/bin/env python3
# /// script
# dependencies = []
# ///

import argparse
import base64
import sys
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path.cwd()))

from app.auth.command_authorization import build_signature_bytes
from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.main import app
from app.models.alert import Alert, AlertDecision, CommandApproval, CommandSigningKey
from app.models.entities import OperationalTask
from app.models.incident import Incident
from app.models.user import User


@dataclass(frozen=True, slots=True)
class Signer:
    user_id: str
    key_id: str
    private_key: Ed25519PrivateKey


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/auth/login", data={"username": email, "password": "demo1234"})
    if response.status_code != 200:
        raise RuntimeError(f"login failed for {email}: {response.text}")
    return response.json()["access_token"]


def _signer(email: str) -> Signer:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        key_id = generate_ulid()
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        db.add(CommandSigningKey(
            id=generate_ulid(), org_id=user.org_id, user_id=user.id, key_id=key_id,
            public_key=base64.b64encode(public_key).decode("ascii"), active=True,
            created_at=now_ms(),
        ))
        db.commit()
        return Signer(user.id, key_id, private_key)
    finally:
        db.close()


def _fixture() -> tuple[str, str]:
    db = SessionLocal()
    try:
        ts = now_ms()
        incident_id, alert_id = generate_ulid(), generate_ulid()
        db.add(Incident(
            id=incident_id, org_id="org_demo", title="Command verifier",
            disaster_type="flood", severity="high", status="active",
            start_time=ts, created_at=ts, updated_at=ts,
        ))
        db.flush()
        db.add(Alert(
            id=alert_id, org_id="org_demo", incident_id=incident_id,
            alert_type="trapped_person", title="Verifier alert", message="Test alert",
            severity="high", recommended_action="Dispatch verifier rescue task",
            confidence_vector={"s": 0.9, "c": 0.9}, status="draft", created_by="verifier",
            created_at=ts, updated_at=ts,
        ))
        db.commit()
        return incident_id, alert_id
    finally:
        db.close()


def _approval(
    signer: Signer,
    incident_id: str,
    alert_id: str,
    command_type: str,
    rationale: str,
    signed_at: int,
) -> dict[str, str | int]:
    nonce = generate_ulid()
    expires_at = signed_at + 300_000
    payload = {
        "incident_id": incident_id, "alert_id": alert_id,
        "command_type": command_type, "rationale": rationale,
    }
    signature = signer.private_key.sign(
        build_signature_bytes(payload, nonce=nonce, expires_at_ms=expires_at)
    )
    return {
        "user_id": signer.user_id, "key_id": signer.key_id, "nonce": nonce,
        "signed_at_ms": signed_at, "expires_at_ms": expires_at,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def _command(
    client: TestClient,
    token: str,
    incident_id: str,
    alert_id: str,
    approval: dict[str, str | int],
    rationale: str,
    command_type: str = "task_creation",
) -> tuple[int, dict[str, object]]:
    response = client.post(
        f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
        json={"command_type": command_type, "rationale": rationale, "approval": approval},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": generate_ulid()},
    )
    return response.status_code, response.json()


def _cleanup(incident_id: str, alert_id: str, key_ids: list[str]) -> None:
    db = SessionLocal()
    try:
        db.query(OperationalTask).filter(OperationalTask.source_alert_id == alert_id).delete()
        decisions = db.query(AlertDecision).filter(AlertDecision.alert_id == alert_id).all()
        decision_ids = [decision.id for decision in decisions]
        if decision_ids:
            db.query(CommandApproval).filter(CommandApproval.decision_id.in_(decision_ids)).delete(
                synchronize_session=False
            )
        db.query(AlertDecision).filter(AlertDecision.alert_id == alert_id).delete()
        db.query(CommandSigningKey).filter(CommandSigningKey.key_id.in_(key_ids)).delete(
            synchronize_session=False
        )
        db.query(Alert).filter(Alert.id == alert_id).delete()
        db.query(Incident).filter(Incident.id == incident_id).delete()
        db.commit()
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, choices=("two-person-dispatch", "single-approver-or-stale-signature"))
    parser.add_argument("--freshness-s", type=int, default=300)
    parser.add_argument("--expect-one-task", action="store_true")
    parser.add_argument("--expect-two-distinct-roles", action="store_true")
    parser.add_argument("--expect-deny", action="store_true")
    parser.add_argument("--expect-zero-tasks", action="store_true")
    args = parser.parse_args()
    if args.freshness_s != 300:
        raise SystemExit("only the canonical 300 second freshness window is supported")
    db = SessionLocal()
    key_ids: list[str] = []
    try:
        seed_demo_users(db)
    finally:
        db.close()
    incident_id, alert_id = _fixture()
    try:
        with TestClient(app) as client:
            manager_token = _login(client, "emergency_manager@demo.disaster")
            coordinator_token = _login(client, "responder_coordinator@demo.disaster")
            manager = _signer("emergency_manager@demo.disaster")
            coordinator = _signer("responder_coordinator@demo.disaster")
            key_ids.extend((manager.key_id, coordinator.key_id))
            rationale = "The incident requires a coordinated rescue response."
            if args.scenario == "two-person-dispatch":
                first_status, _ = _command(
                    client, manager_token, incident_id, alert_id,
                    _approval(manager, incident_id, alert_id, "task_creation", rationale, now_ms()), rationale,
                )
                second_status, second_body = _command(
                    client, coordinator_token, incident_id, alert_id,
                    _approval(coordinator, incident_id, alert_id, "task_creation", rationale, now_ms()), rationale,
                )
                db = SessionLocal()
                try:
                    task_count = db.query(OperationalTask).filter(
                        OperationalTask.source_alert_id == alert_id,
                    ).count()
                    roles = {row.approver_role for row in db.query(CommandApproval).filter(
                        CommandApproval.alert_id == alert_id,
                    ).all()}
                finally:
                    db.close()
                passed = first_status == 202 and second_status == 200
                passed = passed and (not args.expect_one_task or task_count == 1)
                passed = passed and (not args.expect_two_distinct_roles or roles == {
                    "emergency_manager", "responder_coordinator",
                })
                if not passed or not second_body.get("task_id"):
                    raise SystemExit(f"unexpected happy-path result: {first_status}, {second_status}, {second_body}")
            else:
                stale_status, _ = _command(
                    client, manager_token, incident_id, alert_id,
                    _approval(manager, incident_id, alert_id, "task_creation", rationale, now_ms() - 301_000), rationale,
                )
                db = SessionLocal()
                try:
                    task_count = db.query(OperationalTask).filter(
                        OperationalTask.source_alert_id == alert_id,
                    ).count()
                finally:
                    db.close()
                if not args.expect_deny or stale_status != 422:
                    raise SystemExit(f"stale signature unexpectedly accepted: {stale_status}")
                if args.expect_zero_tasks and task_count != 0:
                    raise SystemExit(f"unexpected task count: {task_count}")
        print("PASS")
        return 0
    finally:
        _cleanup(incident_id, alert_id, key_ids)


if __name__ == "__main__":
    sys.exit(main())
