"""Tests for honest degradation display (T40).

Tests FeedHealthTracker using a MockDB that returns pre-computed feed rows.
No real database required — the tracker's logic is pure given the rows.

Covers:
1. feed-health returns per-feed status with age
2. stale feed marked as degraded
3. down feed marked as down
4. coverage computation
5. degradation summary
"""
from __future__ import annotations

from collections import namedtuple
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.health import FeedHealthTracker, router
from app.deps import get_db
from app.lib.time import now_ms

# Fixed reference time for deterministic tests (arbitrary epoch ms).
BASE_TIME_MS = 1_700_000_000_000

# Mimics a SQLAlchemy Row — supports tuple unpacking (source_id, phenomenon,
# last_update, obs_count = row) just like the real Row objects returned by
# select(col1, col2, ...).group_by(...).all().
FeedRow = namedtuple(
    "FeedRow", ["source_id", "phenomenon", "last_update", "obs_count"]
)


class MockResult:
    """Mimics SQLAlchemy Result.all()."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class MockDB:
    """Minimal Session stub: execute(stmt) returns MockResult(rows)."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows = rows or []
        self.last_stmt: Any = None

    def execute(self, stmt: Any) -> MockResult:
        self.last_stmt = stmt
        return MockResult(self.rows)

    def close(self) -> None:
        pass


def test_feed_health_returns_per_feed_status() -> None:
    """Given 3 feeds, get_feed_health returns status for each with age."""
    now = BASE_TIME_MS
    rows = [
        # water_level tau=300s; 30s old → healthy
        FeedRow("usgs", "water_level", now - 30_000, 5),
        # road_passability tau=600s; 700s old → degraded
        FeedRow("osm", "road_passability", now - 700_000, 3),
        # rainfall tau=300s; 2000s old → down
        FeedRow("noaa", "rainfall", now - 2_000_000, 2),
    ]
    db = MockDB(rows)
    tracker = FeedHealthTracker()
    result = tracker.get_feed_health("inc_test", db, current_ms=now)

    assert result["incident_id"] == "inc_test"
    assert result["total_feeds"] == 3
    assert result["healthy_feeds"] == 1

    feeds_by_name = {f["feed_name"]: f for f in result["feeds"]}
    assert "usgs:water_level" in feeds_by_name
    assert feeds_by_name["usgs:water_level"]["status"] == "healthy"
    assert feeds_by_name["usgs:water_level"]["data_age_seconds"] == 30.0

    assert feeds_by_name["osm:road_passability"]["status"] == "degraded"
    assert feeds_by_name["noaa:rainfall"]["status"] == "down"


def test_stale_feed_marked_degraded() -> None:
    """Feed with age > tau but <= 3*tau is marked degraded, not healthy."""
    now = BASE_TIME_MS
    # water_level tau=300s; age=400s (> 300, <= 900)
    rows = [FeedRow("usgs", "water_level", now - 400_000, 1)]
    db = MockDB(rows)
    tracker = FeedHealthTracker()
    result = tracker.get_feed_health("inc_test", db, current_ms=now)

    feed = result["feeds"][0]
    assert feed["status"] == "degraded"
    assert feed["data_age_seconds"] == 400.0
    assert feed["status"] != "healthy"


def test_down_feed_marked_down() -> None:
    """Feed with age > 3*tau is marked down."""
    now = BASE_TIME_MS
    # water_level tau=300s; age=1000s (> 900 = 3*tau)
    rows = [FeedRow("usgs", "water_level", now - 1_000_000, 1)]
    db = MockDB(rows)
    tracker = FeedHealthTracker()
    result = tracker.get_feed_health("inc_test", db, current_ms=now)

    feed = result["feeds"][0]
    assert feed["status"] == "down"
    assert feed["data_age_seconds"] == 1000.0


def test_coverage_computation() -> None:
    """compute_coverage returns percentage of fresh data."""
    tracker = FeedHealthTracker()
    assert tracker.compute_coverage(3, 4) == 75.0
    assert tracker.compute_coverage(0, 4) == 0.0
    assert tracker.compute_coverage(4, 4) == 100.0
    assert tracker.compute_coverage(0, 0) == 0.0


def test_degradation_summary() -> None:
    """get_degradation_summary returns level, lost_feeds, unavailable_capabilities."""
    now = BASE_TIME_MS
    rows = [
        # healthy
        FeedRow("usgs", "water_level", now - 30_000, 5),
        # degraded
        FeedRow("osm", "road_passability", now - 700_000, 3),
        # down
        FeedRow("noaa", "rainfall", now - 2_000_000, 2),
    ]
    db = MockDB(rows)
    tracker = FeedHealthTracker()
    result = tracker.get_degradation_summary("inc_test", db, current_ms=now)

    assert result["degradation_level"] == "severe"
    assert "noaa:rainfall" in result["lost_feeds"]
    assert "osm:road_passability" in result["degraded_feeds"]
    # rainfall → rainfall_nowcast, road_passability → route_planning
    assert "rainfall_nowcast" in result["unavailable_capabilities"]
    assert "route_planning" in result["unavailable_capabilities"]
    # water_level is healthy → flood_inundation_map should NOT be unavailable
    assert "flood_inundation_map" not in result["unavailable_capabilities"]


def test_degradation_summary_nominal() -> None:
    """All feeds healthy → degradation_level is nominal."""
    now = BASE_TIME_MS
    rows = [
        FeedRow("usgs", "water_level", now - 30_000, 5),
        FeedRow("osm", "road_passability", now - 100_000, 3),
    ]
    db = MockDB(rows)
    tracker = FeedHealthTracker()
    result = tracker.get_degradation_summary("inc_test", db, current_ms=now)

    assert result["degradation_level"] == "nominal"
    assert result["lost_feeds"] == []
    assert result["unavailable_capabilities"] == []


def test_degradation_summary_no_feeds() -> None:
    """No feeds → degradation_level is unknown."""
    db = MockDB(rows=[])
    tracker = FeedHealthTracker()
    result = tracker.get_degradation_summary(
        "inc_test", db, current_ms=BASE_TIME_MS
    )

    assert result["degradation_level"] == "unknown"
    assert result["total_feeds"] == 0


def test_is_stale() -> None:
    """is_stale returns True when age > threshold."""
    tracker = FeedHealthTracker()
    assert tracker.is_stale(301, 300) is True
    assert tracker.is_stale(300, 300) is False
    assert tracker.is_stale(299, 300) is False


def test_compute_data_age_clamps_negative() -> None:
    """Future observation (clock skew) → age clamped to 0."""
    tracker = FeedHealthTracker()
    age = tracker.compute_data_age(
        last_update_ms=BASE_TIME_MS + 5000,
        current_ms=BASE_TIME_MS,
    )
    assert age == 0.0


def test_uncertainty_widens_with_age() -> None:
    """Uncertainty multiplier is 1.0 for fresh data, grows for stale data."""
    now = BASE_TIME_MS
    rows = [
        # fresh: age=30s, tau=300 → multiplier=1.0
        FeedRow("usgs", "water_level", now - 30_000, 1),
        # stale: age=600s, tau=300 → multiplier=1.0+(600-300)/300=2.0
        FeedRow("usgs2", "water_level", now - 600_000, 1),
    ]
    db = MockDB(rows)
    tracker = FeedHealthTracker()
    result = tracker.get_feed_health("inc_test", db, current_ms=now)

    fresh = next(f for f in result["feeds"] if f["source_id"] == "usgs")
    stale = next(f for f in result["feeds"] if f["source_id"] == "usgs2")
    assert fresh["uncertainty_multiplier"] == 1.0
    assert stale["uncertainty_multiplier"] == 2.0


def test_feed_health_endpoint() -> None:
    """GET /api/incidents/{id}/feed-health returns per-feed status via HTTP."""
    now = now_ms()
    rows = [
        FeedRow("usgs", "water_level", now - 30_000, 5),
        FeedRow("noaa", "rainfall", now - 2_000_000, 2),
    ]
    mock_db = MockDB(rows)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db

    client = TestClient(app)
    resp = client.get("/api/incidents/inc_test/feed-health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["incident_id"] == "inc_test"
    assert body["total_feeds"] == 2
    statuses = {f["status"] for f in body["feeds"]}
    assert "healthy" in statuses
    assert "down" in statuses
