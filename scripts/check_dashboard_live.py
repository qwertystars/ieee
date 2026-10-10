"""Verify real local API reads and the simulator control/telemetry lifecycle."""

import hashlib
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    checks = []
    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=15)

    def check(method, path, expected=200, **kwargs):
        response = client.request(method, path, **kwargs)
        checks.append({"method": method, "path": path, "status": response.status_code,
            "expected": expected, "response_sha256": hashlib.sha256(response.content).hexdigest()})
        print(method, path, response.status_code, flush=True)
        assert response.status_code == expected, response.text[:500]
        return response.json() if response.content else None

    response = client.post("/api/auth/login", data={"username": "admin@demo.disaster", "password": "demo1234"})
    response.raise_for_status()
    client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
    incident = check("GET", "/api/incidents")["incidents"][0]
    incident_id = incident["id"]
    for suffix in ["situation-report", "alerts", "tasks", "hypotheses", "audit-logs", "feed-health", "degradation-summary"]:
        check("GET", f"/api/incidents/{incident_id}/{suffix}")
    for kind in ["roads", "shelters", "responders", "buildings", "hospitals", "cell_towers", "sensors", "zones"]:
        check("GET", f"/api/incidents/{incident_id}/entities?type={kind}")
    check("GET", f"/api/observations?incident_id={incident_id}")
    check("GET", "/api/simulator/status")
    check("POST", "/api/simulator/start", 403, json={"incident_id": incident_id, "org_id": "other-org"})
    started_at = int(time.time() * 1000)
    check("POST", "/api/simulator/start", 202, json={"incident_id": incident_id, "device_count": 2, "seed": 42})
    try:
        check("POST", "/api/simulator/pause", 204)
        assert check("GET", "/api/simulator/status")["state"] == "paused"
        check("POST", "/api/simulator/set-speed", 204, json={"speed": 2})
        check("POST", "/api/simulator/set-speed", 422, json={"speed": 0})
        check("POST", "/api/simulator/resume", 204)
        assert check("GET", "/api/simulator/status")["state"] == "running"
        faults = {"battery_drain": {"rate": 20}, "sensor_degradation": {"sensor": "thermal"},
            "connectivity_loss": {"duration": 30}, "blocked_route": {"alternative_heading": 90},
            "thermal_hotspot": {"temperature": 60}, "human_heat_signature": {"location": "scenario-target"},
            "water_depth": {"depth": 2}, "motion": {"direction": 180},
            "vibration": {"intensity": 5}, "environmental_temp": {"temp": 40}}
        for fault, kwargs in faults.items():
            check("POST", "/api/simulator/inject-fault", 202, json={"device_id": "rescue-ball-001", "fault_type": fault, "kwargs": kwargs})
        deadline = time.monotonic() + 10
        simulated = []
        while time.monotonic() < deadline:
            features = check("GET", f"/api/observations?incident_id={incident_id}&limit=500")["features"]
            simulated = [f for f in features if f["properties"]["source_id"].startswith("simulator:")
                and f["properties"]["observed_at"] >= started_at]
            if len(simulated) >= 8:
                break
            time.sleep(0.5)
        assert len(simulated) >= 8, "Simulator telemetry was not persisted"
        assert all(f["properties"]["provenance_chain"]["simulated"] for f in simulated)
    finally:
        check("POST", "/api/simulator/stop", 204)
    assert check("GET", "/api/audit/verify")["valid"]
    path = ROOT / "evidence/unified-dashboard/live-api.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"status": "PASS", "checks": checks, "simulator_observations": len(simulated),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "Real local APIs and persisted draft digital-twin telemetry; Rivertown seeded scenario"}, indent=2) + "\n")
    print("Real dashboard API checks completed.")


if __name__ == "__main__":
    main()
