from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _login() -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        data={"username": "emergency_manager@demo.disaster", "password": "demo1234"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_command_center_dashboard_when_demo_event_loaded() -> None:
    headers = _login()

    events_response = client.get("/api/events", headers=headers)
    assert events_response.status_code == 200
    events = events_response.json()
    assert len(events) == 1
    event_id = events[0]["id"]
    assert events[0]["name"] == "Rivertown Urban Flood"

    summary_response = client.get(f"/api/events/{event_id}/dashboard-summary", headers=headers)
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["critical_areas"] == 1
    assert summary["roads_blocked"] == 2
    assert summary["active_recommendations"] >= 2

    layers_response = client.get(f"/api/events/{event_id}/map-layers", headers=headers)
    assert layers_response.status_code == 200
    layers = layers_response.json()
    assert len(layers["areas"]) >= 3
    assert len(layers["reports"]) >= 4
    assert len(layers["shelters"]) >= 3


def test_field_report_updates_dashboard_when_valid_report_submitted() -> None:
    headers = _login()
    event_id = client.get("/api/events", headers=headers).json()[0]["id"]

    create_response = client.post(
        f"/api/events/{event_id}/reports",
        headers=headers,
        json={
            "event_id": event_id,
            "reporter_type": "field_responder",
            "report_category": "road_blocked",
            "description": "Bridge approach is underwater; two vehicles stranded.",
            "geometry": {"type": "Point", "coordinates": [-80.014, 26.012]},
            "urgency": "critical",
        },
    )
    assert create_response.status_code == 201
    report = create_response.json()
    assert report["verification_status"] == "high"
    assert report["confidence_score"] >= 0.8

    summary = client.get(f"/api/events/{event_id}/dashboard-summary", headers=headers).json()
    assert summary["total_reports"] >= 5
    assert summary["unverified_reports"] >= 1


def test_field_report_rejected_when_location_missing() -> None:
    headers = _login()
    event_id = client.get("/api/events", headers=headers).json()[0]["id"]

    response = client.post(
        f"/api/events/{event_id}/reports",
        headers=headers,
        json={
            "event_id": event_id,
            "reporter_type": "citizen",
            "report_category": "flooding",
            "description": "Water is entering houses near Lake Road.",
            "urgency": "high",
        },
    )
    assert response.status_code == 422
    assert "geometry" in response.text


def test_recommendation_approval_and_situation_report_when_manager_reviews() -> None:
    headers = _login()
    event_id = client.get("/api/events", headers=headers).json()[0]["id"]

    recs_response = client.get(f"/api/events/{event_id}/recommendations", headers=headers)
    assert recs_response.status_code == 200
    recommendation = next(item for item in recs_response.json() if item["status"] == "draft")

    approve_response = client.post(
        f"/api/events/{event_id}/recommendations/{recommendation['id']}/approve",
        headers=headers,
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    report_response = client.post(
        f"/api/events/{event_id}/situation-report",
        headers=headers,
        json={"format": "text"},
    )
    assert report_response.status_code == 200
    assert "Rivertown Urban Flood" in report_response.text
    assert "APPROVED" in report_response.text


def test_field_operations_when_responder_opens_mobile_workflow() -> None:
    headers = _login()
    event_id = client.get("/api/events", headers=headers).json()[0]["id"]

    teams_response = client.get(f"/api/events/{event_id}/teams", headers=headers)
    assert teams_response.status_code == 200
    teams = teams_response.json()
    assert len(teams) >= 2
    team_id = teams[0]["id"]

    location_response = client.patch(
        f"/api/teams/{team_id}/location",
        headers=headers,
        json={"current_location": {"type": "Point", "coordinates": [-80.02, 26.02]}},
    )
    assert location_response.status_code == 200
    assert location_response.json()["current_location"]["coordinates"] == [-80.02, 26.02]

    tasks_response = client.get(f"/api/events/{event_id}/tasks", headers=headers)
    assert tasks_response.status_code == 200
    task = tasks_response.json()[0]
    task_response = client.patch(f"/api/tasks/{task['id']}", headers=headers, json={"status": "accepted"})
    assert task_response.status_code == 200
    assert task_response.json()["status"] == "accepted"

    roads_response = client.get(f"/api/events/{event_id}/roads/status", headers=headers)
    assert roads_response.status_code == 200
    road = roads_response.json()[0]
    road_response = client.patch(
        f"/api/roads/{road['id']}/status",
        headers=headers,
        json={"status": "dangerous", "reason": "Field report: dangerous conditions", "confidence_score": 0.9},
    )
    assert road_response.status_code == 200
    assert road_response.json()["status"] == "dangerous"
