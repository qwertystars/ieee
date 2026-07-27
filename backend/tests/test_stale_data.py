"""Integration test — stale data detection via FeedHealthTracker.

Verifies that observations with old `observed_at` timestamps are correctly
classified as degraded or down by the FeedHealthTracker. The tracker uses
per-phenomenon tau values: age <= tau → healthy, tau < age <= 3*tau →
degraded, age > 3*tau → down.

Uses the real PostgreSQL database via SessionLocal. No mocking.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.db import SessionLocal
from app.fusion.freshness import TAU_BY_PHENOMENON
from app.lib.time import now_ms
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.observation import Observation
from app.api.routes.health import FeedHealthTracker

ORG_ID = "org_test_stale"
INCIDENT_ID = "inc_test_stale"


def _make_observation(
    obs_id: str,
    source_id: str,
    phenomenon: str,
    observed_at: int,
) -> Observation:
    """Build a minimal Observation row for staleness testing."""
    from geoalchemy2.elements import WKTElement

    return Observation(
        observation_id=obs_id,
        event_type="sensor_observation",
        phenomenon=phenomenon,
        value=1.0,
        unit="m",
        geometry=WKTElement("POINT(-73.9 40.7)", srid=4326),
        geometry_uncertainty=5.0,
        observed_at=observed_at,
        valid_from=observed_at,
        received_at=observed_at,
        source_id=source_id,
        source_type=SourceType.sensor,
        collection_method="gauge",
        source_reliability=0.9,
        freshness=1.0,
        corroboration_state=CorroborationState.uncorroborated,
        quality_flags={},
        access_policy=AccessPolicy.internal,
        provenance_chain={},
        raw_data_hash="sha256:stale_test",
        org_id=ORG_ID,
        incident_id=INCIDENT_ID,
    )


@pytest.fixture
def db():
    """Yield a session and clean up test rows before and after."""
    session = SessionLocal()
    session.execute(
        delete(Observation).where(Observation.org_id == ORG_ID)
    )
    session.commit()
    try:
        yield session
    finally:
        session.execute(
            delete(Observation).where(Observation.org_id == ORG_ID)
        )
        session.commit()
        session.close()


def test_fresh_observation_classified_healthy(db) -> None:
    """An observation observed 30s ago (tau=300s for water_level) → healthy."""
    now = now_ms()
    obs = _make_observation(
        "obs_stale_001", "usgs", "water_level", now - 30_000
    )
    db.add(obs)
    db.commit()

    tracker = FeedHealthTracker()
    result = tracker.get_feed_health(INCIDENT_ID, db, current_ms=now)

    assert result["total_feeds"] == 1
    feed = result["feeds"][0]
    assert feed["status"] == "healthy", (
        f"expected healthy, got {feed['status']}"
    )
    assert feed["data_age_seconds"] == 30.0


def test_stale_observation_classified_degraded(db) -> None:
    """An observation 400s old (tau=300s) → degraded (tau < age <= 3*tau)."""
    now = now_ms()
    obs = _make_observation(
        "obs_stale_002", "usgs", "water_level", now - 400_000
    )
    db.add(obs)
    db.commit()

    tracker = FeedHealthTracker()
    result = tracker.get_feed_health(INCIDENT_ID, db, current_ms=now)

    feed = result["feeds"][0]
    assert feed["status"] == "degraded", (
        f"expected degraded, got {feed['status']}"
    )
    assert feed["data_age_seconds"] == 400.0


def test_very_stale_observation_classified_down(db) -> None:
    """An observation 1000s old (tau=300s, 3*tau=900s) → down."""
    now = now_ms()
    obs = _make_observation(
        "obs_stale_003", "usgs", "water_level", now - 1_000_000
    )
    db.add(obs)
    db.commit()

    tracker = FeedHealthTracker()
    result = tracker.get_feed_health(INCIDENT_ID, db, current_ms=now)

    feed = result["feeds"][0]
    assert feed["status"] == "down", (
        f"expected down, got {feed['status']}"
    )


def test_degradation_summary_reports_lost_feeds(db) -> None:
    """Degradation summary lists down feeds as lost_feeds."""
    now = now_ms()
    # healthy feed
    db.add(_make_observation(
        "obs_stale_004", "usgs", "water_level", now - 30_000))
    # down feed
    db.add(_make_observation(
        "obs_stale_005", "noaa", "rainfall", now - 2_000_000))
    db.commit()

    tracker = FeedHealthTracker()
    result = tracker.get_degradation_summary(INCIDENT_ID, db, current_ms=now)

    assert result["degradation_level"] == "severe"
    assert "noaa:rainfall" in result["lost_feeds"]
    assert "flood_inundation_map" not in result["unavailable_capabilities"]
    assert "rainfall_nowcast" in result["unavailable_capabilities"]


def test_uncertainty_widens_for_stale_data(db) -> None:
    """Uncertainty multiplier is 1.0 for fresh data, >1.0 for stale data."""
    now = now_ms()
    # fresh: age=30s, tau=300s → multiplier=1.0
    db.add(_make_observation(
        "obs_stale_006", "usgs", "water_level", now - 30_000))
    # stale: age=600s, tau=300s → multiplier=1.0+(600-300)/300=2.0
    db.add(_make_observation(
        "obs_stale_007", "usgs2", "water_level", now - 600_000))
    db.commit()

    tracker = FeedHealthTracker()
    result = tracker.get_feed_health(INCIDENT_ID, db, current_ms=now)

    fresh = next(f for f in result["feeds"] if f["source_id"] == "usgs")
    stale = next(f for f in result["feeds"] if f["source_id"] == "usgs2")
    assert fresh["uncertainty_multiplier"] == 1.0
    assert stale["uncertainty_multiplier"] == 2.0


def test_no_feeds_returns_unknown(db) -> None:
    """No observations → degradation_level is 'unknown'."""
    tracker = FeedHealthTracker()
    result = tracker.get_degradation_summary(INCIDENT_ID, db)
    assert result["degradation_level"] == "unknown"
    assert result["total_feeds"] == 0
