"""Schema tests — verify geometry round-trip for observations."""

import json

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import text

from app.db import SessionLocal, engine
from app.models import Observation
from app.models.enums import (
    AccessPolicy,
    CorroborationState,
    SourceType,
)


@pytest.fixture(scope="module")
def db_setup():
    """Ensure tables exist for the test module (migration already applied)."""
    # The migration is expected to have been run via `alembic upgrade head`.
    yield SessionLocal()


def test_observation_geometry_roundtrip(db_setup):
    """Insert an observation with a GeoJSON Point and read it back with ST_AsGeoJSON."""
    db = db_setup
    ulid = "01J9TESTOBSERVATION001"
    wkt = WKTElement("POINT(-73.9857 40.7484)", srid=4326)

    obs = Observation(
        observation_id=ulid,
        event_type="flood",
        phenomenon="water_level",
        value=1.5,
        unit="m",
        geometry=wkt,
        geometry_uncertainty=5.0,
        observed_at=1721300000000,
        valid_from=1721300000000,
        received_at=1721300001000,
        source_id="src_test_001",
        source_type=SourceType.sensor,
        collection_method="stream_gauge",
        source_reliability=0.9,
        freshness=0.95,
        corroboration_state=CorroborationState.uncorroborated,
        quality_flags={"outlier": False},
        access_policy=AccessPolicy.internal,
        provenance_chain={"steps": ["ingest", "normalize"]},
        raw_data_hash="sha256:abc123",
        org_id="org_test",
        incident_id="inc_test_001",
    )
    db.add(obs)
    db.commit()

    row = db.execute(
        text(
            "SELECT observation_id, ST_AsGeoJSON(geometry) AS geojson "
            "FROM observations WHERE observation_id = :oid"
        ),
        {"oid": ulid},
    ).first()
    db.query(Observation).filter_by(observation_id=ulid).delete()
    db.commit()

    assert row is not None, "observation row not found"
    geo = json.loads(row.geojson)
    assert geo["type"] == "Point"
    # GeoJSON orders coordinates as [lng, lat]
    assert abs(geo["coordinates"][0] - (-73.9857)) < 1e-6
    assert abs(geo["coordinates"][1] - 40.7484) < 1e-6
