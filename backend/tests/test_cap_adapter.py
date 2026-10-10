"""Tests for the CAP 1.2 adapter — parse, ingest, and idempotency.

Uses the real PostgreSQL database via SessionLocal (same pattern as
test_audit.py / test_idempotency.py). All test rows are cleaned up after
each test.
"""

import json

import pytest
from sqlalchemy import delete, text

from app.db import SessionLocal
from app.ingestion.adapters.cap import ingest_cap_alert, parse_cap_alert
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.observation import Observation

ORG_ID = "org_test_cap"
INCIDENT_ID = "inc_test_cap"

# Sample CAP 1.2 alert — Flood Warning for Rivertown downtown (polygon).
SAMPLE_CAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>RIV-FLW-20260718-001</identifier>
  <sender>nws.rivertown.gov</sender>
  <sent>2026-07-18T10:00:00Z</sent>
  <status>Actual</status>
  <msgType>alert</msgType>
  <scope>Public</scope>
  <info>
    <language>en-US</language>
    <category>Met</category>
    <event>Flood Warning</event>
    <urgency>Expected</urgency>
    <severity>Severe</severity>
    <certainty>Likely</certainty>
    <effective>2026-07-18T10:00:00Z</effective>
    <onset>2026-07-18T11:00:00Z</onset>
    <expires>2026-07-18T22:00:00Z</expires>
    <senderName>NWS Rivertown</senderName>
    <headline>Flood Warning for Rivertown downtown</headline>
    <description>Heavy rainfall expected to cause flooding in low-lying areas.</description>
    <area>
      <areaDesc>Rivertown downtown district</areaDesc>
      <polygon>40.70,-73.95 40.80,-73.95 40.80,-73.85 40.70,-73.85</polygon>
    </area>
  </info>
</alert>"""

# CAP alert with a circle instead of a polygon.
SAMPLE_CAP_CIRCLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>RIV-FLW-20260718-002</identifier>
  <sender>nws.rivertown.gov</sender>
  <sent>2026-07-18T11:00:00Z</sent>
  <status>Actual</status>
  <msgType>alert</msgType>
  <scope>Public</scope>
  <info>
    <event>Flash Flood</event>
    <urgency>Immediate</urgency>
    <severity>Extreme</severity>
    <certainty>Observed</certainty>
    <effective>2026-07-18T11:00:00Z</effective>
    <expires>2026-07-18T23:00:00Z</expires>
    <area>
      <areaDesc>Rivertown industrial zone</areaDesc>
      <circle>40.75,-73.90 5</circle>
    </area>
  </info>
</alert>"""


@pytest.fixture
def db():
    """Yield a session backed by real Postgres; clean up test rows after."""
    session = SessionLocal()
    session.execute(delete(Observation).where(Observation.org_id == ORG_ID))
    session.commit()
    try:
        yield session
    finally:
        session.execute(delete(Observation).where(Observation.org_id == ORG_ID))
        session.commit()
        session.close()


def test_parse_cap_alert():
    """Parse sample CAP XML; verify geometry, severity, urgency extracted."""
    parsed = parse_cap_alert(SAMPLE_CAP_XML)

    assert parsed["alert_id"] == "RIV-FLW-20260718-001"
    assert parsed["sender"] == "nws.rivertown.gov"
    assert parsed["event"] == "Flood Warning"
    assert parsed["urgency"] == "Expected"
    assert parsed["severity"] == "Severe"
    assert parsed["certainty"] == "Likely"
    assert parsed["area_desc"] == "Rivertown downtown district"
    assert parsed["expires"] == "2026-07-18T22:00:00Z"

    # Polygon geometry: WKT POLYGON with lon/lat ordering.
    assert parsed["geometry_wkt"].startswith("POLYGON")
    assert parsed["geometry_uncertainty"] == 0.0


def test_parse_cap_circle():
    """Circle geometry produces a buffered polygon with radius in uncertainty."""
    parsed = parse_cap_alert(SAMPLE_CAP_CIRCLE_XML)

    assert parsed["severity"] == "Extreme"
    assert parsed["geometry_wkt"].startswith("POLYGON")
    # 5 km radius -> 5000 meters uncertainty.
    assert parsed["geometry_uncertainty"] == 5000.0


def test_ingest_cap_alert(db):
    """Ingest to DB; verify observation row created with correct fields."""
    obs_id = ingest_cap_alert(db, SAMPLE_CAP_XML, ORG_ID, INCIDENT_ID)

    assert len(obs_id) == 26  # ULID

    row = db.execute(
        text(
            "SELECT observation_id, event_type, phenomenon, source_id, "
            "source_type, collection_method, access_policy, "
            "corroboration_state, raw_data_hash, valid_until, "
            "ST_AsGeoJSON(geometry) AS geojson "
            "FROM observations WHERE observation_id = :oid"
        ),
        {"oid": obs_id},
    ).first()

    assert row is not None
    assert row.observation_id == obs_id
    assert row.event_type == "official_alert"
    assert row.phenomenon == "Flood Warning"
    assert row.source_id == "cap:nws.rivertown.gov:RIV-FLW-20260718-001"
    assert row.source_type == SourceType.official_feed.value
    assert row.collection_method == "cap_xml"
    assert row.access_policy == AccessPolicy.sensitive.value  # Severe -> sensitive
    assert row.corroboration_state == CorroborationState.uncorroborated.value
    assert row.raw_data_hash.startswith("sha256:")
    assert row.valid_until is not None  # expires mapped to valid_until

    geo = json.loads(row.geojson)
    assert geo["type"] == "Polygon"
    # GeoJSON coordinates are [lng, lat]; first ring, first point.
    ring = geo["coordinates"][0]
    assert abs(ring[0][0] - (-73.95)) < 1e-6  # lon of first vertex
    assert abs(ring[0][1] - 40.70) < 1e-6  # lat of first vertex


def test_idempotent_reparse(db):
    """Ingesting the same XML twice produces one observation with the same id."""
    first_id = ingest_cap_alert(db, SAMPLE_CAP_XML, ORG_ID, INCIDENT_ID)
    second_id = ingest_cap_alert(db, SAMPLE_CAP_XML, ORG_ID, INCIDENT_ID)

    assert first_id == second_id

    count = db.execute(
        text(
            "SELECT count(*) FROM observations "
            "WHERE source_id = :sid AND org_id = :org"
        ),
        {"sid": "cap:nws.rivertown.gov:RIV-FLW-20260718-001", "org": ORG_ID},
    ).scalar()
    assert count == 1


def test_ingest_circle_alert(db):
    """Circle-based alert ingests with buffered geometry and sensitive policy."""
    obs_id = ingest_cap_alert(db, SAMPLE_CAP_CIRCLE_XML, ORG_ID, INCIDENT_ID)

    row = db.execute(
        text(
            "SELECT access_policy, geometry_uncertainty, "
            "ST_AsGeoJSON(geometry) AS geojson "
            "FROM observations WHERE observation_id = :oid"
        ),
        {"oid": obs_id},
    ).first()

    assert row is not None
    assert row.access_policy == AccessPolicy.sensitive.value  # Extreme -> sensitive
    assert row.geometry_uncertainty == 5000.0
    geo = json.loads(row.geojson)
    assert geo["type"] == "Polygon"


def test_supersedes_on_update(db):
    """An Update message with references sets the supersedes field."""
    # First: ingest the original alert.
    original_id = ingest_cap_alert(db, SAMPLE_CAP_XML, ORG_ID, INCIDENT_ID)

    # Second: ingest an Update that references the original.
    update_xml = SAMPLE_CAP_XML.replace(
        "<msgType>alert</msgType>",
        "<msgType>Update</msgType>",
    ).replace(
        "<scope>Public</scope>",
        '<scope>Public</scope>\n  <references>nws.rivertown.gov,RIV-FLW-20260718-001,2026-07-18T10:00:00Z</references>',
    )
    update_id = ingest_cap_alert(db, update_xml, ORG_ID, INCIDENT_ID)

    assert update_id != original_id

    row = db.execute(
        text(
            "SELECT supersedes FROM observations "
            "WHERE observation_id = :oid"
        ),
        {"oid": update_id},
    ).first()
    assert row.supersedes == original_id
