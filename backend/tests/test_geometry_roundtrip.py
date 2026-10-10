"""Integration test — GeoJSON geometry round-trip through PostgreSQL/PostGIS.

Verifies that Point and Polygon geometries inserted via the API (as GeoJSON)
are correctly stored in PostGIS and read back as identical GeoJSON via
ST_AsGeoJSON. The full round-trip exercises:
  API → ST_SetSRID(ST_GeomFromGeoJSON(...)) → PostGIS storage → ST_AsGeoJSON → API response

Uses the real PostgreSQL/PostGIS database and the real FastAPI app.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.main import app

PASSWORD = "demo1234"


@pytest.fixture(scope="module", autouse=True)
def _seed_users() -> None:
    db = SessionLocal()
    seed_demo_users(db)
    db.close()


def _login(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_incident(client: TestClient, token: str, title: str) -> str:
    resp = client.post(
        "/api/incidents",
        json={"title": title, "disaster_type": "flood"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_observation(
    client: TestClient, token: str, incident_id: str, geometry: dict
) -> dict:
    feature = {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "event_type": "sensor_observation",
            "phenomenon": "water_level",
            "value": 2.5,
            "unit": "m",
            "source_id": "test_geom_src",
            "source_type": "sensor",
        },
    }
    resp = client.post(
        f"/api/observations?incident_id={incident_id}",
        json=feature,
        headers=_auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_point_geometry_roundtrip() -> None:
    """Point geometry survives the API → PostGIS → API round-trip intact."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        inc_id = _create_incident(client, token, "Point Roundtrip")

        lon, lat = -73.9857, 40.7484
        geometry = {"type": "Point", "coordinates": [lon, lat]}
        created = _create_observation(client, token, inc_id, geometry)
        obs_id = created["properties"]["observation_id"]

        # Read it back via GET /api/observations/{id}.
        resp = client.get(
            f"/api/observations/{obs_id}",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        result = resp.json()

        assert result["geometry"]["type"] == "Point"
        coords = result["geometry"]["coordinates"]
        assert abs(coords[0] - lon) < 1e-6, (
            f"lon mismatch: expected {lon}, got {coords[0]}"
        )
        assert abs(coords[1] - lat) < 1e-6, (
            f"lat mismatch: expected {lat}, got {coords[1]}"
        )


def test_polygon_geometry_roundtrip() -> None:
    """Polygon geometry survives the API → PostGIS → API round-trip intact."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        inc_id = _create_incident(client, token, "Polygon Roundtrip")

        coords = [
            [-73.98, 40.74],
            [-73.97, 40.74],
            [-73.97, 40.75],
            [-73.98, 40.75],
            [-73.98, 40.74],  # closed ring
        ]
        geometry = {"type": "Polygon", "coordinates": [coords]}
        created = _create_observation(client, token, inc_id, geometry)
        obs_id = created["properties"]["observation_id"]

        resp = client.get(
            f"/api/observations/{obs_id}",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        result = resp.json()

        assert result["geometry"]["type"] == "Polygon"
        ring = result["geometry"]["coordinates"][0]
        assert len(ring) == 5, f"expected 5 vertices, got {len(ring)}"
        for i, (lon, lat) in enumerate(coords):
            assert abs(ring[i][0] - lon) < 1e-6, (
                f"vertex {i} lon mismatch: expected {lon}, got {ring[i][0]}"
            )
            assert abs(ring[i][1] - lat) < 1e-6, (
                f"vertex {i} lat mismatch: expected {lat}, got {ring[i][1]}"
            )


def test_point_in_list_endpoint() -> None:
    """List endpoint returns GeoJSON FeatureCollection with correct geometry."""
    with TestClient(app) as client:
        token = _login(client, "admin@demo.disaster")
        inc_id = _create_incident(client, token, "List Geometry")

        lon, lat = -122.4194, 37.7749
        geometry = {"type": "Point", "coordinates": [lon, lat]}
        _create_observation(client, token, inc_id, geometry)

        resp = client.get(
            f"/api/observations?incident_id={inc_id}",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "FeatureCollection"
        assert len(body["features"]) >= 1

        feat = body["features"][0]
        assert feat["geometry"]["type"] == "Point"
        coords = feat["geometry"]["coordinates"]
        assert abs(coords[0] - lon) < 1e-6
        assert abs(coords[1] - lat) < 1e-6
