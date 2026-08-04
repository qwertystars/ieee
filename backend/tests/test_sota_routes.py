"""Tests for SOTA fusion and perception API routes (T32).

Verifies that all endpoints return meaningful responses and that ML features
degrade gracefully when model weights are unavailable. Uses the real
PostgreSQL database and the real FastAPI app via TestClient.

Test suite:
  1.  GET /api/incidents/{id}/scenarios — scenario ensemble with best/expected/worst
  2.  GET /api/incidents/{id}/world-state — DBN state distribution
  3.  GET /api/incidents/{id}/calibration — Brier/ECE/coverage metrics
   4.  GET /api/incidents/{id}/flood-map — degrades to unavailable
   5.  GET /api/incidents/{id}/flood-ensemble — abstains without ensemble input
  6.  GET /api/incidents/{id}/sensing-actions — 12 actions including rescue ball
  7.  POST /api/incidents/{id}/sensing-actions/{action_id}/dispatch — pending task
   8.  POST /api/incidents/{id}/damage-assessment — degrades to unavailable
   9.  POST /api/incidents/{id}/nlp-report — degrades to unavailable
  10. POST /api/eval/run — testbed evaluation with task_id
  11. GET /api/eval/results/{task_id} — retrieve eval results
  12. Rescue ball present in sensing actions catalog
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

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

PASSWORD = "demo1234"
ADMIN_EMAIL = "admin@demo.disaster"
VIEWER_EMAIL = "viewer@demo.disaster"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    """Seed demo users once for the module."""
    db = SessionLocal()
    seed_demo_users(db)
    db.close()
    yield


def _login(client: TestClient, email: str) -> str:
    """Login and return the JWT bearer token."""
    resp = client.post(
        "/api/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, f"login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_incident(client: TestClient, token: str) -> str:
    """Create an incident and return its ID."""
    resp = client.post(
        "/api/incidents",
        json={"title": "SOTA Routes Test", "disaster_type": "flood"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── Scenarios ───────────────────────────────────────────────────────────────


def test_get_scenarios_returns_ensemble() -> None:
    """GET /scenarios returns best/expected/worst with probabilities summing to ~1."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/scenarios?n=10&seed=42",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["incident_id"] == inc_id
        assert body["n"] == 10
        assert body["seed"] == 42
        assert len(body["best"]) > 0
        assert len(body["expected"]) > 0
        assert len(body["worst"]) > 0
        total_prob = sum(
            s["probability"]
            for label in ("best", "expected", "worst")
            for s in body[label]
        )
        assert abs(total_prob - 1.0) < 0.01


def test_get_scenarios_404_for_unknown_incident() -> None:
    """GET /scenarios returns 404 for a non-existent incident."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        resp = client.get(
            "/api/incidents/nonexistent_incident/scenarios",
            headers=_auth_header(token),
        )
        assert resp.status_code == 404


# ── World state ─────────────────────────────────────────────────────────────


def test_get_world_state_returns_dbn_distribution() -> None:
    """GET /world-state returns DBN state distribution with 5 severity levels."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/world-state",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["incident_id"] == inc_id
        assert body["hazard_type"] == "flood"
        dist = body["state_distribution"]
        assert set(dist.keys()) == {"none", "minor", "moderate", "severe", "extreme"}
        assert abs(sum(dist.values()) - 1.0) < 0.01


# ── Calibration ─────────────────────────────────────────────────────────────


def test_get_calibration_returns_metrics() -> None:
    """GET /calibration returns Brier score, ECE, and conformal coverage."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/calibration",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["incident_id"] == inc_id
        assert "brier_score" in body
        assert "ece" in body
        assert "conformal_coverage" in body
        assert "nll" in body
        assert "reliability" in body
        assert body["n_samples"] == 20
        assert 0.0 <= body["brier_score"] <= 1.0
        assert 0.0 <= body["ece"] <= 1.0
        assert 0.0 <= body["conformal_coverage"] <= 1.0


# ── Flood map (degrades gracefully) ─────────────────────────────────────────


def test_get_flood_map_degrades_gracefully(degrade_env: None) -> None:
    """GET /flood-map returns unavailable when weights are missing."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/flood-map",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "unavailable"
        assert body["feature"] == "flood_mapping"


# ── Flood ensemble (degrades gracefully) ─────────────────────────────────────


def test_get_flood_ensemble_degrades_gracefully() -> None:
    """GET /flood-ensemble abstains when ensemble input is missing."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/flood-ensemble",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "abstain"
        assert body["feature"] == "ensemble"


# ── Sensing actions ─────────────────────────────────────────────────────────


def test_list_sensing_actions_includes_rescue_ball() -> None:
    """GET /sensing-actions returns 12 actions including deploy_rescue_ball."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/sensing-actions",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["incident_id"] == inc_id
        assert body["count"] == 12
        action_ids = {a["id"] for a in body["actions"]}
        assert "deploy_rescue_ball" in action_ids

        rescue_ball = next(
            a for a in body["actions"] if a["id"] == "deploy_rescue_ball"
        )
        assert rescue_ball["action_type"] == "deploy_rescue_ball"
        assert rescue_ball["target"] == "rescue_ball"
        assert rescue_ball["cost"]["resource"] == "rescue_ball_unit"


def test_list_sensing_actions_top_n() -> None:
    """GET /sensing-actions?top=3 returns top-3 with display text."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/sensing-actions?top=3",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["count"] == 3
        for action in body["actions"]:
            assert "display_text" in action
            assert "Recommended information request:" in action["display_text"]


def test_dispatch_sensing_action_creates_pending_task() -> None:
    """POST /sensing-actions/{action_id}/dispatch creates a pending task."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.post(
            f"/api/incidents/{inc_id}/sensing-actions/task_drone/dispatch",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["action_id"] == "task_drone"
        assert body["incident_id"] == inc_id
        assert body["status"] == "pending"
        assert body["task_id"]
        assert body["dispatched_by"] == ADMIN_EMAIL


def test_dispatch_unknown_action_returns_404() -> None:
    """POST /sensing-actions/{action_id}/dispatch returns 404 for unknown action."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.post(
            f"/api/incidents/{inc_id}/sensing-actions/nonexistent_action/dispatch",
            headers=_auth_header(token),
        )
        assert resp.status_code == 404


def test_dispatch_rescue_ball() -> None:
    """POST /sensing-actions/deploy_rescue_ball/dispatch creates a pending task."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.post(
            f"/api/incidents/{inc_id}/sensing-actions/deploy_rescue_ball/dispatch",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["action_id"] == "deploy_rescue_ball"
        assert body["status"] == "pending"


# ── Damage assessment (degrades gracefully) ──────────────────────────────────


def test_damage_assessment_degrades_gracefully(degrade_env: None) -> None:
    """POST /damage-assessment returns unavailable when weights are missing."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.post(
            f"/api/incidents/{inc_id}/damage-assessment",
            json={"flood_prob": 0.6, "damage_prob": 0.3, "road_class": "primary"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "unavailable"
        assert body["feature"] == "damage"


# ── NLP report (degrades gracefully) ────────────────────────────────────────


def test_nlp_report_degrades_gracefully(degrade_env: None) -> None:
    """POST /nlp-report returns unavailable when weights are missing."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.post(
            f"/api/incidents/{inc_id}/nlp-report",
            json={"text": "There is severe flooding near the river bank."},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "unavailable"
        assert body["feature"] == "nlp"


# ── Eval run ────────────────────────────────────────────────────────────────


def test_eval_run_returns_task_id() -> None:
    """POST /eval/run returns a task_id with infrastructure summary."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)

        resp = client.post(
            "/api/eval/run",
            json={"seed": 42, "duration_hours": 3},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["task_id"]
        assert body["status"] == "completed"
        assert body["seed"] == 42
        assert body["duration_hours"] == 3
        assert body["fingerprint"]
        infra = body["infrastructure_summary"]
        assert infra["buildings"] > 0
        assert infra["roads"] > 0
        assert body["observation_count"] > 0


def test_eval_run_with_custom_params() -> None:
    """POST /eval/run accepts custom TestbedParams overrides."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)

        resp = client.post(
            "/api/eval/run",
            json={
                "seed": 99,
                "duration_hours": 2,
                "params": {"building_count": 500, "road_count": 25},
            },
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["infrastructure_summary"]["buildings"] == 500
        assert body["infrastructure_summary"]["roads"] == 25


def test_eval_results_retrieval() -> None:
    """GET /eval/results/{task_id} returns the stored evaluation results."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)

        run_resp = client.post(
            "/api/eval/run",
            json={"seed": 7, "duration_hours": 1},
            headers=_auth_header(token),
        )
        assert run_resp.status_code == 200
        task_id = run_resp.json()["task_id"]

        results_resp = client.get(
            f"/api/eval/results/{task_id}",
            headers=_auth_header(token),
        )
        assert results_resp.status_code == 200, results_resp.text
        body = results_resp.json()
        assert body["task_id"] == task_id
        assert body["seed"] == 7
        assert body["status"] == "completed"


def test_eval_results_404_for_unknown_task() -> None:
    """GET /eval/results/{task_id} returns 404 for unknown task_id."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        resp = client.get(
            "/api/eval/results/nonexistent_task_id",
            headers=_auth_header(token),
        )
        assert resp.status_code == 404


def test_eval_run_requires_admin_role() -> None:
    """POST /eval/run returns 403 for viewer role (not admin/emergency_manager)."""
    with TestClient(app) as client:
        token = _login(client, VIEWER_EMAIL)
        resp = client.post(
            "/api/eval/run",
            json={"seed": 1},
            headers=_auth_header(token),
        )
        assert resp.status_code == 403


def _create_alert_for_command(
    db,
    *,
    org_id: str = "org_demo",
    recommended_action: str | None = "Monitor river gauge",
) -> tuple[str, str]:
    ts = now_ms()
    incident_id = generate_ulid()
    alert_id = generate_ulid()
    db.add(Incident(
        id=incident_id,
        org_id=org_id,
        title="Command workflow test",
        disaster_type="flood",
        severity="high",
        status="active",
        start_time=ts,
        created_at=ts,
        updated_at=ts,
    ))
    db.flush()
    db.add(Alert(
        id=alert_id,
        org_id=org_id,
        incident_id=incident_id,
        alert_type="public_warning" if recommended_action is None else "status_update",
        title="Command workflow alert",
        message="A command workflow test alert.",
        severity="high",
        recommended_action=recommended_action,
        confidence_vector={"s": 0.8, "c": 0.8},
        status="draft",
        created_by="test",
        created_at=ts,
        updated_at=ts,
    ))
    db.commit()
    return incident_id, alert_id


def _install_command_key(email: str) -> tuple[str, Ed25519PrivateKey]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        key_id = generate_ulid()
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes_raw()
        db.add(CommandSigningKey(
            id=generate_ulid(),
            org_id=user.org_id,
            user_id=user.id,
            key_id=key_id,
            public_key=base64.b64encode(public_key).decode("ascii"),
            active=True,
            created_at=now_ms(),
        ))
        db.commit()
        return key_id, private_key
    finally:
        db.close()


def _signed_command(
    *,
    incident_id: str,
    alert_id: str,
    command_type: str,
    rationale: str,
    key_id: str,
    user_id: str,
    private_key: Ed25519PrivateKey,
    signed_at_ms: int | None = None,
    expires_at_ms: int | None = None,
) -> dict[str, str | int]:
    signed_at = signed_at_ms if signed_at_ms is not None else now_ms()
    expires_at = expires_at_ms if expires_at_ms is not None else signed_at + 300_000
    nonce = generate_ulid()
    signature_payload = {
        "incident_id": incident_id,
        "alert_id": alert_id,
        "command_type": command_type,
        "rationale": rationale,
    }
    signature = private_key.sign(build_signature_bytes(
        signature_payload,
        nonce=nonce,
        expires_at_ms=expires_at,
    ))
    return {
        "user_id": user_id,
        "key_id": key_id,
        "nonce": nonce,
        "signed_at_ms": signed_at,
        "expires_at_ms": expires_at,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def test_non_dispatch_alert_approval_persists_decision_without_task() -> None:
    with TestClient(app) as client:
        token = _login(client, "emergency_manager@demo.disaster")
        db = SessionLocal()
        try:
            incident_id, alert_id = _create_alert_for_command(db)
        finally:
            db.close()

        response = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/approve",
            json={"review_rationale": "Monitor-only alert approved"},
            headers=_auth_header(token),
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    db = SessionLocal()
    try:
        assert db.query(OperationalTask).filter(
            OperationalTask.incident_id == incident_id,
            OperationalTask.properties["alert_id"].as_string() == alert_id,
        ).count() == 0
    finally:
        db.close()


def test_dispatch_requires_two_signed_distinct_roles_and_is_idempotent() -> None:
    with TestClient(app) as client:
        manager_token = _login(client, "emergency_manager@demo.disaster")
        coordinator_token = _login(client, "responder_coordinator@demo.disaster")
        db = SessionLocal()
        try:
            incident_id, alert_id = _create_alert_for_command(
                db, recommended_action="Dispatch rescue boat"
            )
            manager_id = db.query(User).filter(
                User.email == "emergency_manager@demo.disaster"
            ).one().id
            coordinator_id = db.query(User).filter(
                User.email == "responder_coordinator@demo.disaster"
            ).one().id
        finally:
            db.close()
        manager_key_id, manager_key = _install_command_key(
            "emergency_manager@demo.disaster"
        )
        coordinator_key_id, coordinator_key = _install_command_key(
            "responder_coordinator@demo.disaster"
        )
        rationale = "Dispatch is required to reach stranded residents."
        manager_approval = _signed_command(
            incident_id=incident_id,
            alert_id=alert_id,
            command_type="task_creation",
            rationale=rationale,
            key_id=manager_key_id,
            user_id=manager_id,
            private_key=manager_key,
        )
        coordinator_approval = _signed_command(
            incident_id=incident_id,
            alert_id=alert_id,
            command_type="task_creation",
            rationale=rationale,
            key_id=coordinator_key_id,
            user_id=coordinator_id,
            private_key=coordinator_key,
        )
        body = {
            "command_type": "task_creation",
            "rationale": rationale,
            "approval": manager_approval,
        }
        first = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json=body,
            headers={**_auth_header(manager_token), "Idempotency-Key": generate_ulid()},
        )
        assert first.status_code == 202, first.text
        assert first.json()["task_id"] is None

        body["approval"] = coordinator_approval
        second_key = generate_ulid()
        second = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json=body,
            headers={**_auth_header(coordinator_token), "Idempotency-Key": second_key},
        )
        assert second.status_code == 200, second.text
        task_id = second.json()["task_id"]

        retry = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json=body,
            headers={**_auth_header(coordinator_token), "Idempotency-Key": second_key},
        )
        assert retry.status_code == 200, retry.text
        assert retry.json()["task_id"] == task_id

        conflict_body = {**body, "rationale": "A different command payload"}
        conflict = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json=conflict_body,
            headers={**_auth_header(coordinator_token), "Idempotency-Key": second_key},
        )
        assert conflict.status_code == 409

    db = SessionLocal()
    try:
        assert db.query(OperationalTask).filter(
            OperationalTask.incident_id == incident_id,
            OperationalTask.source_alert_id == alert_id,
        ).count() == 1
    finally:
        db.close()


def test_dispatch_rejects_single_stale_and_wrong_role_approvals() -> None:
    with TestClient(app) as client:
        manager_token = _login(client, "emergency_manager@demo.disaster")
        viewer_token = _login(client, VIEWER_EMAIL)
        db = SessionLocal()
        try:
            incident_id, alert_id = _create_alert_for_command(
                db, recommended_action="Commit evacuation resources"
            )
            manager_id = db.query(User).filter(
                User.email == "emergency_manager@demo.disaster"
            ).one().id
            viewer_id = db.query(User).filter(User.email == VIEWER_EMAIL).one().id
        finally:
            db.close()
        manager_key_id, manager_key = _install_command_key(
            "emergency_manager@demo.disaster"
        )
        stale = _signed_command(
            incident_id=incident_id,
            alert_id=alert_id,
            command_type="resource_commitment",
            rationale="Stale authorization test",
            key_id=manager_key_id,
            user_id=manager_id,
            private_key=manager_key,
            signed_at_ms=now_ms() - 301_000,
        )
        stale_response = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json={
                "command_type": "resource_commitment",
                "rationale": "Stale authorization test",
                "approval": stale,
            },
            headers={**_auth_header(manager_token), "Idempotency-Key": generate_ulid()},
        )
        assert stale_response.status_code == 422

        wrong_key_id, wrong_key = _install_command_key(VIEWER_EMAIL)
        wrong = _signed_command(
            incident_id=incident_id,
            alert_id=alert_id,
            command_type="resource_commitment",
            rationale="Wrong role test",
            key_id=wrong_key_id,
            user_id=viewer_id,
            private_key=wrong_key,
        )
        wrong_response = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json={
                "command_type": "resource_commitment",
                "rationale": "Wrong role test",
                "approval": wrong,
            },
            headers={"Authorization": f"Bearer {viewer_token}", "Idempotency-Key": generate_ulid()},
        )
        assert wrong_response.status_code == 403

    db = SessionLocal()
    try:
        assert db.query(OperationalTask).filter(
            OperationalTask.source_alert_id == alert_id,
        ).count() == 0
    finally:
        db.close()


def test_concurrent_distinct_approvals_create_one_task() -> None:
    with TestClient(app) as client:
        manager_token = _login(client, "emergency_manager@demo.disaster")
        coordinator_token = _login(client, "responder_coordinator@demo.disaster")
        db = SessionLocal()
        try:
            incident_id, alert_id = _create_alert_for_command(
                db, recommended_action="Dispatch concurrent rescue task"
            )
            manager_id = db.query(User).filter(
                User.email == "emergency_manager@demo.disaster"
            ).one().id
            coordinator_id = db.query(User).filter(
                User.email == "responder_coordinator@demo.disaster"
            ).one().id
        finally:
            db.close()
        manager_key_id, manager_key = _install_command_key(
            "emergency_manager@demo.disaster"
        )
        coordinator_key_id, coordinator_key = _install_command_key(
            "responder_coordinator@demo.disaster"
        )
        rationale = "Concurrent approvals must converge on one task."
        manager_approval = _signed_command(
            incident_id=incident_id, alert_id=alert_id, command_type="task_creation",
            rationale=rationale, key_id=manager_key_id, user_id=manager_id,
            private_key=manager_key,
        )
        coordinator_approval = _signed_command(
            incident_id=incident_id, alert_id=alert_id, command_type="task_creation",
            rationale=rationale, key_id=coordinator_key_id, user_id=coordinator_id,
            private_key=coordinator_key,
        )

        def submit(token: str, approval: dict[str, str | int]) -> int:
            response = client.post(
                f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
                json={"command_type": "task_creation", "rationale": rationale,
                      "approval": approval},
                headers={**_auth_header(token), "Idempotency-Key": generate_ulid()},
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(
                submit,
                (manager_token, coordinator_token),
                (manager_approval, coordinator_approval),
            ))
        assert sorted(statuses) == [200, 202]

    db = SessionLocal()
    try:
        assert db.query(OperationalTask).filter(
            OperationalTask.source_alert_id == alert_id,
        ).count() == 1
    finally:
        db.close()


def test_command_transaction_rolls_back_before_audit_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as client:
        manager_token = _login(client, "emergency_manager@demo.disaster")
        db = SessionLocal()
        try:
            incident_id, alert_id = _create_alert_for_command(
                db, recommended_action="Rollback command"
            )
            manager_id = db.query(User).filter(
                User.email == "emergency_manager@demo.disaster"
            ).one().id
        finally:
            db.close()
        key_id, private_key = _install_command_key("emergency_manager@demo.disaster")
        rationale = "Audit failure must not leave an approval row."
        approval = _signed_command(
            incident_id=incident_id, alert_id=alert_id, command_type="task_creation",
            rationale=rationale, key_id=key_id, user_id=manager_id,
            private_key=private_key,
        )

        def fail_audit(*args: object, **kwargs: object) -> None:
            raise RuntimeError("forced audit failure")

        monkeypatch.setattr("app.api.routes.alert_commands.write_audit", fail_audit)
        with pytest.raises(RuntimeError, match="forced audit failure"):
            client.post(
                f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
                json={"command_type": "task_creation", "rationale": rationale,
                      "approval": approval},
                headers={**_auth_header(manager_token), "Idempotency-Key": generate_ulid()},
            )

    db = SessionLocal()
    try:
        assert db.query(AlertDecision).filter(
            AlertDecision.alert_id == alert_id,
        ).count() == 0
        assert db.query(OperationalTask).filter(
            OperationalTask.source_alert_id == alert_id,
        ).count() == 0
    finally:
        db.close()


def test_dispatch_rejects_malformed_approval_and_cross_org_incident() -> None:
    with TestClient(app) as client:
        manager_token = _login(client, "emergency_manager@demo.disaster")
        db = SessionLocal()
        try:
            incident_id, alert_id = _create_alert_for_command(db)
        finally:
            db.close()
        malformed = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json={"command_type": "task_creation", "rationale": "bad payload", "approval": {}},
            headers={**_auth_header(manager_token), "Idempotency-Key": generate_ulid()},
        )
        assert malformed.status_code == 422
        cross_org = client.post(
            f"/api/incidents/foreign-incident/alerts/{alert_id}/dispatch",
            json={"command_type": "task_creation", "rationale": "cross org", "approval": {
                "user_id": "foreign-user", "key_id": "foreign-key", "nonce": generate_ulid(),
                "signed_at_ms": now_ms(), "expires_at_ms": now_ms() + 300_000,
                "signature": "not-a-signature",
            }},
            headers={**_auth_header(manager_token), "Idempotency-Key": generate_ulid()},
        )
        assert cross_org.status_code == 404

    db = SessionLocal()
    try:
        assert db.query(OperationalTask).filter(
            OperationalTask.source_alert_id == alert_id,
        ).count() == 0
    finally:
        db.close()


def test_dispatch_rejects_invalid_signature_without_creating_decision() -> None:
    with TestClient(app) as client:
        manager_token = _login(client, "emergency_manager@demo.disaster")
        db = SessionLocal()
        try:
            incident_id, alert_id = _create_alert_for_command(db)
            manager_id = db.query(User).filter(
                User.email == "emergency_manager@demo.disaster"
            ).one().id
        finally:
            db.close()
        key_id, private_key = _install_command_key("emergency_manager@demo.disaster")
        approval = _signed_command(
            incident_id=incident_id, alert_id=alert_id, command_type="task_creation",
            rationale="Invalid signature test", key_id=key_id, user_id=manager_id,
            private_key=private_key,
        )
        approval["signature"] = "not-a-valid-ed25519-signature"
        response = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json={"command_type": "task_creation", "rationale": "Invalid signature test", "approval": approval},
            headers={**_auth_header(manager_token), "Idempotency-Key": generate_ulid()},
        )
        assert response.status_code == 422

    db = SessionLocal()
    try:
        assert db.query(AlertDecision).filter(AlertDecision.alert_id == alert_id).count() == 0
    finally:
        db.close()


def test_dispatch_rejects_expired_signature_without_creating_decision() -> None:
    with TestClient(app) as client:
        manager_token = _login(client, "emergency_manager@demo.disaster")
        db = SessionLocal()
        try:
            incident_id, alert_id = _create_alert_for_command(db)
            manager_id = db.query(User).filter(
                User.email == "emergency_manager@demo.disaster"
            ).one().id
        finally:
            db.close()
        key_id, private_key = _install_command_key("emergency_manager@demo.disaster")
        signed_at = now_ms() - 100_000
        approval = _signed_command(
            incident_id=incident_id, alert_id=alert_id, command_type="task_creation",
            rationale="Expired signature test", key_id=key_id, user_id=manager_id,
            private_key=private_key, signed_at_ms=signed_at, expires_at_ms=now_ms() - 1,
        )
        response = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json={"command_type": "task_creation", "rationale": "Expired signature test", "approval": approval},
            headers={**_auth_header(manager_token), "Idempotency-Key": generate_ulid()},
        )
        assert response.status_code == 422

    db = SessionLocal()
    try:
        assert db.query(AlertDecision).filter(AlertDecision.alert_id == alert_id).count() == 0
    finally:
        db.close()


def test_dispatch_rejects_revoked_signing_key_without_creating_decision() -> None:
    with TestClient(app) as client:
        manager_token = _login(client, "emergency_manager@demo.disaster")
        db = SessionLocal()
        try:
            incident_id, alert_id = _create_alert_for_command(db)
            manager_id = db.query(User).filter(
                User.email == "emergency_manager@demo.disaster"
            ).one().id
        finally:
            db.close()
        key_id, private_key = _install_command_key("emergency_manager@demo.disaster")
        db = SessionLocal()
        try:
            key = db.query(CommandSigningKey).filter(CommandSigningKey.key_id == key_id).one()
            key.revoked_at = now_ms()
            db.commit()
        finally:
            db.close()
        approval = _signed_command(
            incident_id=incident_id, alert_id=alert_id, command_type="task_creation",
            rationale="Revoked key test", key_id=key_id, user_id=manager_id,
            private_key=private_key,
        )
        response = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json={"command_type": "task_creation", "rationale": "Revoked key test", "approval": approval},
            headers={**_auth_header(manager_token), "Idempotency-Key": generate_ulid()},
        )
        assert response.status_code == 403

    db = SessionLocal()
    try:
        assert db.query(AlertDecision).filter(AlertDecision.alert_id == alert_id).count() == 0
    finally:
        db.close()


def test_dispatch_rejects_replayed_nonce_without_creating_second_approval() -> None:
    with TestClient(app) as client:
        manager_token = _login(client, "emergency_manager@demo.disaster")
        db = SessionLocal()
        try:
            incident_id, alert_id = _create_alert_for_command(db)
            manager_id = db.query(User).filter(
                User.email == "emergency_manager@demo.disaster"
            ).one().id
        finally:
            db.close()
        key_id, private_key = _install_command_key("emergency_manager@demo.disaster")
        approval = _signed_command(
            incident_id=incident_id, alert_id=alert_id, command_type="task_creation",
            rationale="Replay nonce test", key_id=key_id, user_id=manager_id,
            private_key=private_key,
        )
        body = {"command_type": "task_creation", "rationale": "Replay nonce test", "approval": approval}
        first = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json=body,
            headers={**_auth_header(manager_token), "Idempotency-Key": generate_ulid()},
        )
        assert first.status_code == 202
        replay = client.post(
            f"/api/incidents/{incident_id}/alerts/{alert_id}/dispatch",
            json=body,
            headers={**_auth_header(manager_token), "Idempotency-Key": generate_ulid()},
        )
        assert replay.status_code == 409

    db = SessionLocal()
    try:
        assert db.query(CommandApproval).filter(CommandApproval.alert_id == alert_id).count() == 1
    finally:
        db.close()
