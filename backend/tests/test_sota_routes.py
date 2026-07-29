"""Tests for SOTA fusion and perception API routes (T32).

Verifies that all endpoints return meaningful responses and that ML features
degrade gracefully when model weights are unavailable. Uses the real
PostgreSQL database and the real FastAPI app via TestClient.

Test suite:
  1.  GET /api/incidents/{id}/scenarios — scenario ensemble with best/expected/worst
  2.  GET /api/incidents/{id}/world-state — DBN state distribution
  3.  GET /api/incidents/{id}/calibration — Brier/ECE/coverage metrics
  4.  GET /api/incidents/{id}/flood-map — degrades to model_unavailable
  5.  GET /api/incidents/{id}/flood-ensemble — degrades to model_unavailable
  6.  GET /api/incidents/{id}/sensing-actions — 12 actions including rescue ball
  7.  POST /api/incidents/{id}/sensing-actions/{action_id}/dispatch — pending task
  8.  POST /api/incidents/{id}/damage-assessment — degrades to model_unavailable
  9.  POST /api/incidents/{id}/nlp-report — degrades to model_unavailable
  10. POST /api/eval/run — testbed evaluation with task_id
  11. GET /api/eval/results/{task_id} — retrieve eval results
  12. Rescue ball present in sensing actions catalog
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.main import app

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
    """GET /flood-map returns model_unavailable when weights are missing."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/flood-map",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "model_unavailable"
        assert body["feature"] == "flood_mapping"


# ── Flood ensemble (degrades gracefully) ─────────────────────────────────────


def test_get_flood_ensemble_degrades_gracefully() -> None:
    """GET /flood-ensemble returns model_unavailable when weights are missing."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/flood-ensemble",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "model_unavailable"
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
    """POST /damage-assessment returns model_unavailable when weights are missing."""
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
        assert body["status"] == "model_unavailable"
        assert body["feature"] == "damage"


# ── NLP report (degrades gracefully) ────────────────────────────────────────


def test_nlp_report_degrades_gracefully(degrade_env: None) -> None:
    """POST /nlp-report returns model_unavailable when weights are missing."""
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
        assert body["status"] == "model_unavailable"
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
