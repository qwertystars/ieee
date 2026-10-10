"""Contracts used by the unified dashboard; no ML or hardware required."""

from fastapi.testclient import TestClient

from ble_localization.main import app as mesh_app
from route_engine.thermal_server import app as thermal_app


def test_mesh_sync_broadcasts_to_dashboard_and_reset_clears():
    with TestClient(mesh_app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        client.post("/api/mesh/reset")
        with client.websocket_connect("/ws/route") as socket:
            assert socket.receive_json()["survivors"] == []
            response = client.post("/api/mesh/sync", json={
                "device_id": "test-relay", "device_lat": 17.4, "device_lng": 78.3,
                "timestamp": "2026-10-10T00:00:00Z", "survivor_count": 1,
                "mesh_table": [{"survivor_id": "test-beacon", "rssi": -60,
                    "relay_lat": 17.401, "relay_lng": 78.301, "relay_node_id": "test-relay"}],
            })
            assert response.status_code == 200
            state = socket.receive_json()
            assert state["survivors"][0]["id"] == "test-beacon"
            assert state["survivors"][0]["lat"] == 17.401
            assert state["survivors"][0]["urgency"] == "medium"
            assert len(state["path"]) == 2
            assert client.post("/api/mesh/reset").status_code == 200
            assert socket.receive_json()["survivors"] == []


def test_mesh_rejects_malformed_phone_payload():
    with TestClient(mesh_app) as client:
        assert client.post("/api/mesh/sync", json={"mesh_table": "invalid"}).status_code == 422


def test_thermal_feed_has_draft_status_and_valid_camera_coordinates():
    with TestClient(thermal_app) as client:
        client.delete("/api/hazard")
        response = client.post("/api/hazard", json={"coords": [0.2, 0.8], "confidence": 0.9, "radius": 5})
        assert response.status_code == 201
        record = response.json()
        assert record["review_status"] == "draft"
        assert record["timestamp"] > 0
        assert client.get("/api/hazard").json()[0] == record
        assert client.post("/api/hazard", json={"coords": [1.2, 0.8], "confidence": 0.9, "radius": 5}).status_code == 422
        assert client.get("/api/hazard?limit=0").status_code == 400
        client.delete("/api/hazard")
