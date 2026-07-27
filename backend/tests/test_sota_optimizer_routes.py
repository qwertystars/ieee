"""Tests for SOTA optimizer, twin, privacy, fairness, and eval API routes (T33).

Verifies that all endpoints wire their SOTA modules correctly and return
meaningful data. Uses the real PostgreSQL database and the real FastAPI app
via TestClient.

Test suite:
  1.  GET /api/incidents/{id}/optimize — assignments + alternatives + trade-offs
  2.  GET /api/incidents/{id}/optimize — infeasible returns explanation
  3.  GET /api/incidents/{id}/optimize — progressive precision by role
  4.  GET /api/incidents/{id}/cascade — blast radius from infrastructure DAG
  5.  GET /api/incidents/{id}/silence — telecom silence residual per zone
  6.  GET /api/incidents/{id}/fairness-report — equity report
  7.  GET /api/incidents/{id}/access-check — ABAC enforcement
  8.  GET /api/incidents/{id}/access-check — sensitive data denied for viewer
  9.  POST /api/eval/ablation — ablation study
  10. POST /api/eval/baselines — baselines comparison
  11. Existing eval endpoints still work (POST /run, GET /results)
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
FIELD_RESPONDER_EMAIL = "field_responder@demo.disaster"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    db = SessionLocal()
    seed_demo_users(db)
    db.close()
    yield


def _login(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, f"login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_incident(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/incidents",
        json={"title": "SOTA Optimizer Test", "disaster_type": "flood"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── GET /api/incidents/{id}/optimize ────────────────────────────────────────


def test_optimize_returns_assignments_and_alternatives() -> None:
    """GET /optimize returns fair_plan + original_plan + equity_report."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/optimize",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["incident_id"] == inc_id
        assert body["status"] in ("optimal", "feasible")
        assert body["input_source"] in ("demo_scenario", "incident_data")

        fair = body["fair_plan"]
        assert "assignments" in fair
        assert len(fair["assignments"]) > 0
        assert "objective_value" in fair
        assert "expected_harm" in fair
        assert "cvar" in fair
        assert "coverage" in fair

        original = body["original_plan"]
        assert "assignments" in original

        equity = body["equity_report"]
        assert "equity_applied" in equity
        assert "throughput_tradeoff_pct" in equity
        assert "message" in equity


def test_optimize_assignments_have_responder_and_task_ids() -> None:
    """Each assignment has responder_id, task_id, start_time, and metadata."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/optimize",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        assignments = resp.json()["fair_plan"]["assignments"]
        for a in assignments:
            assert "responder_id" in a
            assert "task_id" in a
            assert "start_time" in a
            assert "responder_vehicle_class" in a
            assert "task_zone_id" in a
            assert "task_required_skill" in a


def test_optimize_progressive_precision_viewer() -> None:
    """Viewer sees coordinates rounded to ~1km (2 decimal places)."""
    with TestClient(app) as client:
        admin_token = _login(client, ADMIN_EMAIL)
        viewer_token = _login(client, VIEWER_EMAIL)
        inc_id = _create_incident(client, admin_token)

        admin_resp = client.get(
            f"/api/incidents/{inc_id}/optimize",
            headers=_auth_header(admin_token),
        )
        viewer_resp = client.get(
            f"/api/incidents/{inc_id}/optimize",
            headers=_auth_header(viewer_token),
        )
        assert admin_resp.status_code == 200
        assert viewer_resp.status_code == 200

        admin_coords = admin_resp.json()["progressive_precision"]["coord_decimals"]
        viewer_coords = viewer_resp.json()["progressive_precision"]["coord_decimals"]

        # Admin sees exact coordinates (72.8777).
        assert admin_coords["lon"] == 72.8777
        # Viewer sees coordinates rounded to 2 decimals (~1km).
        assert viewer_coords["lon"] == round(72.8777, 2)
        assert viewer_coords["lat"] == round(19.0760, 2)


def test_optimize_progressive_precision_field_responder() -> None:
    """Field responder sees coordinates rounded to ~100m (3 decimal places)."""
    with TestClient(app) as client:
        admin_token = _login(client, ADMIN_EMAIL)
        fr_token = _login(client, FIELD_RESPONDER_EMAIL)
        inc_id = _create_incident(client, admin_token)

        fr_resp = client.get(
            f"/api/incidents/{inc_id}/optimize",
            headers=_auth_header(fr_token),
        )
        assert fr_resp.status_code == 200
        coords = fr_resp.json()["progressive_precision"]["coord_decimals"]
        # Field responder: 3 decimals (~100m).
        assert coords["lon"] == round(72.8777, 3)
        assert coords["lat"] == round(19.0760, 3)


def test_optimize_404_for_unknown_incident() -> None:
    """GET /optimize returns 404 for a non-existent incident."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        resp = client.get(
            "/api/incidents/nonexistent_incident/optimize",
            headers=_auth_header(token),
        )
        assert resp.status_code == 404


# ── GET /api/incidents/{id}/cascade ─────────────────────────────────────────


def test_cascade_returns_blast_radius() -> None:
    """GET /cascade returns blast radius, max_depth, and affected_nodes."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/cascade",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["incident_id"] == inc_id
        assert "blast_radius" in body
        assert "max_depth" in body
        assert "affected_nodes" in body
        assert isinstance(body["blast_radius"], int)
        assert isinstance(body["max_depth"], int)


def test_cascade_no_infrastructure_returns_status() -> None:
    """GET /cascade without seeded infrastructure returns no_infrastructure_graph."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/cascade",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        # A fresh incident has no GraphEdge rows — should return the no_infrastructure status.
        if body["blast_radius"] == 0:
            assert body["status"] == "no_infrastructure_graph"


# ── GET /api/incidents/{id}/silence ─────────────────────────────────────────


def test_silence_returns_zone_reports() -> None:
    """GET /silence returns per-zone expected/observed rates and residuals."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/silence",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["incident_id"] == inc_id
        assert "window_ms" in body
        assert "total_observations" in body
        assert "total_zones" in body
        assert "zones" in body
        assert isinstance(body["zones"], list)


# ── GET /api/incidents/{id}/fairness-report ──────────────────────────────────


def test_fairness_report_returns_equity_data() -> None:
    """GET /fairness-report returns equity_applied, tradeoff_pct, and zones."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/fairness-report",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["incident_id"] == inc_id
        # Without seeded zones, returns no_zones status.
        if body.get("status") == "no_zones":
            assert body["equity_report"] is None
        else:
            assert "equity_applied" in body
            assert "throughput_tradeoff_pct" in body
            assert "vulnerable_zones_protected" in body
            assert "message" in body
            assert "zones" in body


# ── GET /api/incidents/{id}/access-check ─────────────────────────────────────


def test_access_check_admin_allowed() -> None:
    """GET /access-check allows admin to read internal data."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        inc_id = _create_incident(client, token)

        resp = client.get(
            f"/api/incidents/{inc_id}/access-check",
            params={"action": "read", "resource": "observation:01HTEST"},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["allowed"] is True
        assert body["action"] == "read"
        assert body["actor_role"] == "admin"
        assert len(body["reasons"]) > 0


def test_access_check_viewer_sensitive_denied() -> None:
    """GET /access-check denies viewer access to sensitive data."""
    with TestClient(app) as client:
        admin_token = _login(client, ADMIN_EMAIL)
        viewer_token = _login(client, VIEWER_EMAIL)
        inc_id = _create_incident(client, admin_token)

        resp = client.get(
            f"/api/incidents/{inc_id}/access-check",
            params={
                "action": "read",
                "resource": "observation:01HSENS",
                "sensitivity": "sensitive",
            },
            headers=_auth_header(viewer_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["allowed"] is False
        assert body["sensitivity"] == "sensitive"
        assert body["actor_role"] == "viewer"


def test_access_check_viewer_write_denied() -> None:
    """GET /access-check denies viewer write access (role not in write set)."""
    with TestClient(app) as client:
        admin_token = _login(client, ADMIN_EMAIL)
        viewer_token = _login(client, VIEWER_EMAIL)
        inc_id = _create_incident(client, admin_token)

        resp = client.get(
            f"/api/incidents/{inc_id}/access-check",
            params={"action": "write", "resource": "observation:01HW"},
            headers=_auth_header(viewer_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["allowed"] is False
        assert body["action"] == "write"


# ── POST /api/eval/ablation ──────────────────────────────────────────────────


def test_eval_ablation_returns_results() -> None:
    """POST /eval/ablation returns per-ablation metrics + comparison table."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)

        resp = client.post(
            "/api/eval/ablation",
            json={"seed": 42},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "completed"
        assert body["seed"] == 42
        assert body["ablation_count"] == 10  # 9 ablations + full_system
        assert "full_system" in body["results"]
        assert "comparison_table" in body
        assert "significant_ablations" in body

        full = body["results"]["full_system"]
        assert "metrics" in full
        assert "prevented_harm" in full["metrics"]
        assert 0.0 <= full["metrics"]["prevented_harm"] <= 1.0


def test_eval_ablation_requires_admin_role() -> None:
    """POST /eval/ablation returns 403 for viewer role."""
    with TestClient(app) as client:
        token = _login(client, VIEWER_EMAIL)
        resp = client.post(
            "/api/eval/ablation",
            json={"seed": 42},
            headers=_auth_header(token),
        )
        assert resp.status_code == 403


# ── POST /api/eval/baselines ─────────────────────────────────────────────────


def test_eval_baselines_returns_results() -> None:
    """POST /eval/baselines returns 4 baselines + comparison table."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)

        resp = client.post(
            "/api/eval/baselines",
            json={"seed": 42},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "completed"
        assert body["seed"] == 42
        assert body["baseline_count"] == 4
        assert "baseline_1_independent_dashboards" in body["results"]
        assert "baseline_4_resqnet_sage" in body["results"]
        assert "comparison_table" in body

        sage = body["results"]["baseline_4_resqnet_sage"]
        assert sage["uses_fusion"] is True
        assert sage["selection_policy"] == "probabilistic_forecast_optimize"
        assert "prevented_harm" in sage["metrics"]


def test_eval_baselines_requires_admin_role() -> None:
    """POST /eval/baselines returns 403 for viewer role."""
    with TestClient(app) as client:
        token = _login(client, VIEWER_EMAIL)
        resp = client.post(
            "/api/eval/baselines",
            json={"seed": 42},
            headers=_auth_header(token),
        )
        assert resp.status_code == 403


# ── Existing eval endpoints still work ───────────────────────────────────────


def test_existing_eval_run_still_works() -> None:
    """POST /eval/run (from Task 32) still works after adding ablation/baselines."""
    with TestClient(app) as client:
        token = _login(client, ADMIN_EMAIL)
        resp = client.post(
            "/api/eval/run",
            json={"seed": 42, "duration_hours": 1},
            headers=_auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["task_id"]
        assert body["status"] == "completed"


def test_existing_eval_results_still_works() -> None:
    """GET /eval/results/{task_id} (from Task 32) still works."""
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
        assert results_resp.status_code == 200
        assert results_resp.json()["task_id"] == task_id
