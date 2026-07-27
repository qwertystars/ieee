"""Tests for the OGC API Features adapter.

Mocks the OGC HTTP endpoint via unittest.mock, pulls GeoJSON features, and
verifies that RoadSegment / Shelter rows are created in the real Postgres DB.
The schema is built by Alembic migrations (see conftest.py).
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.ingestion.adapters.ogc_features import (
    OGCFeaturesClient,
    sync_collection,
)
from app.models.entities import RoadSegment, Shelter

ORG_ID = "org_test_ogc"
INCIDENT_ID = "inc_test_ogc"


def _road_features(n: int = 10) -> dict:
    """Build a GeoJSON FeatureCollection with n LineString road features."""
    features = []
    for i in range(n):
        features.append({
            "type": "Feature",
            "id": f"road_{i}",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [-74.0 + i * 0.01, 40.70],
                    [-73.99 + i * 0.01, 40.71],
                ],
            },
            "properties": {"name": f"Road {i}", "status": "open"},
        })
    return {"type": "FeatureCollection", "features": features, "links": []}


def _shelter_features(n: int = 3) -> dict:
    """Build a GeoJSON FeatureCollection with n Point shelter features."""
    features = []
    for i in range(n):
        features.append({
            "type": "Feature",
            "id": f"shelter_{i}",
            "geometry": {
                "type": "Point",
                "coordinates": [-74.0 + i * 0.01, 40.70],
            },
            "properties": {
                "name": f"Shelter {i}",
                "status": "open",
                "capacity": 100 + i * 10,
                "occupancy": i * 10,
            },
        })
    return {"type": "FeatureCollection", "features": features, "links": []}


def _mock_response(fc: dict) -> httpx.Response:
    """Build an httpx.Response wrapping a GeoJSON FeatureCollection."""
    req = httpx.Request("GET", "https://mock.example.org/collections/x/items")
    return httpx.Response(200, json=fc, request=req)


@pytest.fixture
def db():
    """Yield a session and clean up all test rows after."""
    session = SessionLocal()
    session.query(RoadSegment).filter(RoadSegment.org_id == ORG_ID).delete()
    session.query(Shelter).filter(Shelter.org_id == ORG_ID).delete()
    session.commit()
    try:
        yield session
    finally:
        session.query(RoadSegment).filter(RoadSegment.org_id == ORG_ID).delete()
        session.query(Shelter).filter(Shelter.org_id == ORG_ID).delete()
        session.commit()
        session.close()


def test_pull_roads(db):
    """Mock OGC endpoint with 10 road features, verify RoadSegment rows created."""
    fc = _road_features(10)
    client = OGCFeaturesClient("https://mock.example.org")
    mock_get = AsyncMock(return_value=_mock_response(fc))
    with patch.object(client._client, "get", mock_get):
        count = asyncio.run(
            sync_collection(
                db, client, "roads", "road_segment", ORG_ID, INCIDENT_ID,
                bbox=(-74.1, 40.6, -73.9, 40.8),
            )
        )
    assert count == 10

    rows = db.query(RoadSegment).filter(RoadSegment.org_id == ORG_ID).all()
    assert len(rows) == 10

    # Verify geometry is LineString via ST_AsGeoJSON.
    row = rows[0]
    geo = db.execute(
        text("SELECT ST_AsGeoJSON(geometry) AS g FROM road_segments WHERE id = :rid"),
        {"rid": row.id},
    ).first()
    geom = json.loads(geo.g)
    assert geom["type"] == "LineString"
    assert len(geom["coordinates"]) == 2

    # Verify properties carry source provenance.
    assert row.properties["_external_id"] == "road_0"
    assert row.properties["_source"] == "ogc"
    assert row.name == "Road 0"
    assert row.status == "open"


def test_pull_shelters(db):
    """Mock with 3 shelter Point features, verify Shelter rows created."""
    fc = _shelter_features(3)
    client = OGCFeaturesClient("https://mock.example.org")
    mock_get = AsyncMock(return_value=_mock_response(fc))
    with patch.object(client._client, "get", mock_get):
        count = asyncio.run(
            sync_collection(
                db, client, "shelters", "shelter", ORG_ID, INCIDENT_ID,
            )
        )
    assert count == 3

    rows = db.query(Shelter).filter(Shelter.org_id == ORG_ID).all()
    assert len(rows) == 3

    row = rows[0]
    assert row.name == "Shelter 0"
    assert row.capacity == 100
    assert row.occupancy == 0

    # Verify geometry is Point.
    geo = db.execute(
        text("SELECT ST_AsGeoJSON(geometry) AS g FROM shelters WHERE id = :sid"),
        {"sid": row.id},
    ).first()
    geom = json.loads(geo.g)
    assert geom["type"] == "Point"


def test_upsert_conflict(db):
    """Pull same feature twice; verify no duplicate and no overwrite."""
    fc = _road_features(1)
    client = OGCFeaturesClient("https://mock.example.org")
    mock_get = AsyncMock(return_value=_mock_response(fc))
    with patch.object(client._client, "get", mock_get):
        count1 = asyncio.run(
            sync_collection(db, client, "roads", "road_segment", ORG_ID, INCIDENT_ID)
        )
        count2 = asyncio.run(
            sync_collection(db, client, "roads", "road_segment", ORG_ID, INCIDENT_ID)
        )
    # First sync inserts 1; second sync finds no changes -> 0.
    assert count1 == 1
    assert count2 == 0

    rows = db.query(RoadSegment).filter(RoadSegment.org_id == ORG_ID).all()
    assert len(rows) == 1


def test_upsert_user_edited_not_overwritten(db):
    """If a row has _user_edited=True, re-sync must not overwrite it."""
    fc = _road_features(1)
    client = OGCFeaturesClient("https://mock.example.org")
    mock_get = AsyncMock(return_value=_mock_response(fc))
    with patch.object(client._client, "get", mock_get):
        asyncio.run(
            sync_collection(db, client, "roads", "road_segment", ORG_ID, INCIDENT_ID)
        )
        # Simulate a user edit.
        row = db.query(RoadSegment).filter(RoadSegment.org_id == ORG_ID).one()
        row.name = "User Renamed"
        props = dict(row.properties or {})
        props["_user_edited"] = True
        row.properties = props
        db.commit()

        # Change the source feature and re-sync.
        fc["features"][0]["properties"]["name"] = "Source Changed"
        fc["features"][0]["properties"]["status"] = "closed"
        count = asyncio.run(
            sync_collection(db, client, "roads", "road_segment", ORG_ID, INCIDENT_ID)
        )
    assert count == 0  # skipped because _user_edited is True

    db.refresh(row)
    assert row.name == "User Renamed"  # not overwritten
