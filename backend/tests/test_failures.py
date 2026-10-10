"""Tests for the failure injection framework (T42).

Verifies: 50% feed loss removes ~50% of observations, false reports are flagged
by confidence_vector, tower failure cascades to silence residual, road failure
marks roads as impassable, shelter capacity change adjusts capacity, and
apply_failures orchestrates multiple failure types.

No DB needed — operates on the in-memory testbed.
Run: docker compose run --rm -e PYTHONPATH=/app backend sh -c \
    "pip install pytest -q && python -m pytest tests/test_failures.py -q"
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from app.eval.failures import FailureInjector, confidence_vector
from app.eval.testbed import DigitalTwinTestbed
from app.eval.testbed_types import (
    EntityStatus,
    ObservationSource,
    TestbedObservation,
    TestbedParams,
)

DEFAULT_PARAMS = TestbedParams()


@pytest.fixture
def testbed() -> DigitalTwinTestbed:
    tb = DigitalTwinTestbed()
    tb.generate(seed=42, params=DEFAULT_PARAMS)
    return tb


@pytest.fixture
def observations(testbed: DigitalTwinTestbed) -> list[TestbedObservation]:
    return testbed.generate_observation_stream(seed=42, duration_hours=24)


@pytest.fixture
def injector() -> FailureInjector:
    return FailureInjector(seed=42)


# --- Stopping condition 1: 50% feed loss -> ~50% fewer observations ---

def test_feed_loss_removes_half(testbed, observations, injector):
    """50% feed loss removes ~50% of observations."""
    original_count = len(observations)
    reduced = injector.inject_feed_loss(observations, loss_pct=50)
    assert len(reduced) < original_count, "feed loss should reduce count"
    expected = int(original_count * 0.5)
    assert abs(len(reduced) - expected) <= 1, (
        f"expected ~{expected} obs after 50% loss, got {len(reduced)}"
    )


def test_feed_loss_30_pct(testbed, observations, injector):
    """30% feed loss removes ~30% of observations."""
    original_count = len(observations)
    reduced = injector.inject_feed_loss(observations, loss_pct=30)
    expected = int(original_count * 0.7)
    assert abs(len(reduced) - expected) <= 1, (
        f"expected ~{expected} obs after 30% loss, got {len(reduced)}"
    )


def test_feed_loss_70_pct(testbed, observations, injector):
    """70% feed loss removes ~70% of observations."""
    original_count = len(observations)
    reduced = injector.inject_feed_loss(observations, loss_pct=70)
    expected = int(original_count * 0.3)
    assert abs(len(reduced) - expected) <= 1, (
        f"expected ~{expected} obs after 70% loss, got {len(reduced)}"
    )


def test_feed_loss_zero_pct(testbed, observations, injector):
    """0% feed loss returns all observations."""
    reduced = injector.inject_feed_loss(observations, loss_pct=0)
    assert len(reduced) == len(observations)


# --- Stopping condition 2: false report injected, flagged by confidence vector ---

def test_false_report_flagged_by_confidence_vector(testbed, observations, injector):
    """False reports are flagged by confidence_vector (score 0.0)."""
    injected = injector.inject_false_reports(observations, count=5)
    assert len(injected) == len(observations) + 5
    confidences = confidence_vector(injected)
    low_conf = [c for c in confidences if c < 0.5]
    assert len(low_conf) >= 5, (
        f"expected >= 5 low-confidence obs, got {len(low_conf)}"
    )
    misinfo = [o for o in injected if o.event_type == "misinformation"]
    assert len(misinfo) == 5


def test_adversarial_misinformation_flagged(testbed, observations, injector):
    """Adversarial misinformation is flagged by confidence_vector."""
    injected = injector.inject_adversarial_misinformation(observations, count=3)
    confidences = confidence_vector(injected)
    low_conf = [c for c in confidences if c < 0.5]
    assert len(low_conf) >= 3
    adversarial = [o for o in injected if o.event_type == "adversarial"]
    assert len(adversarial) == 3
    assert all(o.value == 1.0 for o in adversarial), "adversarial should have max severity"


def test_normal_reports_have_high_confidence(testbed, observations, injector):
    """Normal observations have confidence 1.0."""
    confidences = confidence_vector(observations)
    assert all(c == 1.0 for c in confidences), "normal obs should have confidence 1.0"


# --- Stopping condition 3: tower failure -> cascade -> silence residual ---

def test_tower_failure_marks_tower_offline(testbed, injector):
    """Tower failure sets tower status to offline."""
    infra = testbed.get_infrastructure()
    tower_id = infra.cell_towers[0].id
    new_infra = injector.inject_tower_failure(infra, tower_id)
    tower = next(t for t in new_infra.cell_towers if t.id == tower_id)
    assert tower.status == EntityStatus.offline
    other_towers = [t for t in new_infra.cell_towers if t.id != tower_id]
    assert all(t.status == EntityStatus.operational for t in other_towers)


def test_tower_failure_cascade_silences_reports(testbed, observations, injector):
    """Tower failure cascades: citizen reports near offline tower are silenced."""
    infra = testbed.get_infrastructure()
    big_tower = dataclasses.replace(infra.cell_towers[0], range_m=100_000.0)
    new_towers = (big_tower,) + infra.cell_towers[1:]
    infra = dataclasses.replace(infra, cell_towers=new_towers)
    new_infra = injector.inject_tower_failure(infra, big_tower.id)
    silenced = injector.apply_tower_cascade(new_infra, observations)
    citizen_before = sum(
        1 for o in observations if o.source_type == ObservationSource.citizen_report
    )
    citizen_after = sum(
        1 for o in silenced if o.source_type == ObservationSource.citizen_report
    )
    assert citizen_after < citizen_before, (
        f"cascade should reduce citizen reports: before={citizen_before}, after={citizen_after}"
    )
    sensor_count = sum(1 for o in silenced if o.source_type == ObservationSource.sensor)
    sensor_before = sum(1 for o in observations if o.source_type == ObservationSource.sensor)
    assert sensor_count == sensor_before, "sensors should not be silenced by tower failure"


def test_tower_cascade_no_offline_towers(testbed, observations, injector):
    """Cascade with no offline towers returns all observations."""
    infra = testbed.get_infrastructure()
    result = injector.apply_tower_cascade(infra, observations)
    assert len(result) == len(observations)


# --- Stopping condition 4: road failure ---

def test_road_failure_marks_roads(testbed, injector):
    """Road failure marks count roads as failed (flood_vulnerability = 1.0)."""
    infra = testbed.get_infrastructure()
    new_roads = injector.inject_road_failure(infra.roads, count=5)
    failed = [e for e in new_roads.edges if e.flood_vulnerability >= 1.0]
    assert len(failed) >= 5, f"expected >= 5 failed roads, got {len(failed)}"
    total = len(new_roads.edges)
    assert total == len(infra.roads.edges), "road count should not change"


def test_road_failure_all_roads(testbed, injector):
    """Road failure with count > edges marks all roads as failed."""
    infra = testbed.get_infrastructure()
    n = len(infra.roads.edges)
    new_roads = injector.inject_road_failure(infra.roads, count=n + 100)
    failed = [e for e in new_roads.edges if e.flood_vulnerability >= 1.0]
    assert len(failed) == n, "all roads should be failed"


# --- Stopping condition 5: shelter capacity change ---

def test_shelter_capacity_decrease(testbed, injector):
    """Shelter capacity decrease by 30% reduces capacity."""
    infra = testbed.get_infrastructure()
    new_shelters = injector.inject_shelter_capacity_change(infra.shelters, change_pct=-30)
    for old, new in zip(infra.shelters, new_shelters):
        expected = max(0, int(old.capacity * 0.7))
        assert new.capacity == expected, (
            f"shelter {old.id}: expected {expected}, got {new.capacity}"
        )


def test_shelter_capacity_increase(testbed, injector):
    """Shelter capacity increase by 50% raises capacity."""
    infra = testbed.get_infrastructure()
    new_shelters = injector.inject_shelter_capacity_change(infra.shelters, change_pct=50)
    for old, new in zip(infra.shelters, new_shelters):
        expected = int(old.capacity * 1.5)
        assert new.capacity == expected


# --- Additional failure type tests ---

def test_delay_adds_to_official_reports(testbed, observations, injector):
    """Delay adds delay_minutes to official alert timestamps only."""
    delayed = injector.inject_delay(observations, delay_minutes=30)
    official_before = [o for o in observations if o.source_type == ObservationSource.official_alert]
    official_after = [o for o in delayed if o.source_type == ObservationSource.official_alert]
    assert len(official_before) == len(official_after)
    for ob, oa in zip(official_before, official_after):
        assert oa.timestamp_ms == ob.timestamp_ms + 30 * 60_000
    sensor_before = [o for o in observations if o.source_type == ObservationSource.sensor]
    sensor_after = [o for o in delayed if o.source_type == ObservationSource.sensor]
    for sb, sa in zip(sensor_before, sensor_after):
        assert sa.timestamp_ms == sb.timestamp_ms, "sensors should not be delayed"


def test_duplicates_increase_count(testbed, observations, injector):
    """Duplicate injection increases observation count."""
    injected = injector.inject_duplicates(observations, count=10)
    assert len(injected) == len(observations) + 10


def test_geolocation_ambiguity_rounds_coords(testbed, observations, injector):
    """Geolocation ambiguity rounds coords for pct% of observations."""
    ambiguous = injector.inject_geolocation_ambiguity(observations, pct=50)
    assert len(ambiguous) == len(observations)
    rounded = sum(
        1 for o in ambiguous
        if o.lon == round(o.lon, 1) and o.lat == round(o.lat, 1)
    )
    assert rounded > 0, "some observations should have rounded coords"


def test_multilingual_adds_language_tag(testbed, observations, injector):
    """Multilingual injection adds language tag to citizen report event_type."""
    multilingual = injector.inject_multilingual(observations, pct=100)
    citizen = [o for o in multilingual if o.source_type == ObservationSource.citizen_report]
    tagged = [o for o in citizen if any(o.event_type.endswith(f"_{l}") for l in
                                        ("hi", "en_hi", "ta", "bn", "te", "mr"))]
    assert len(tagged) == len(citizen), "all citizen reports should be tagged"


def test_cloud_cover_blocks_imagery(injector):
    """Cloud cover zeroes out optical imagery."""
    data = np.ones((10, 10), dtype=np.float32)
    blocked = injector.inject_cloud_cover(data)
    assert blocked.shape == data.shape
    assert np.all(blocked == 0.0)


def test_sar_noise_adds_noise(injector):
    """SAR noise adds noise to flood map but keeps it in [0, 1]."""
    flood_map = np.full((10, 10), 0.5, dtype=np.float32)
    noisy = injector.inject_sar_noise(flood_map, noise_level=0.1)
    assert noisy.shape == flood_map.shape
    assert np.all(noisy >= 0.0) and np.all(noisy <= 1.0)
    assert not np.array_equal(noisy, flood_map), "noise should change the map"


def test_responder_unavailability(testbed, injector):
    """Responder unavailability marks count responders as offline."""
    infra = testbed.get_infrastructure()
    new_resp = injector.inject_responder_unavailability(infra.responder_stations, count=2)
    offline = [r for r in new_resp if r.status == EntityStatus.offline]
    assert len(offline) == 2


def test_hospital_closure(testbed, injector):
    """Hospital closure marks the specified hospital as offline."""
    infra = testbed.get_infrastructure()
    hosp_id = infra.hospitals[0].id
    new_hosp = injector.inject_hospital_closure(infra.hospitals, hosp_id)
    closed = next(h for h in new_hosp if h.id == hosp_id)
    assert closed.status == EntityStatus.offline
    others = [h for h in new_hosp if h.id != hosp_id]
    assert all(h.status == EntityStatus.operational for h in others)


# --- apply_failures orchestration ---

def test_apply_failures_multiple(testbed, injector):
    """apply_failures applies multiple failure types and returns metrics."""
    infra = testbed.get_infrastructure()
    tower_id = infra.cell_towers[0].id
    config = [
        {"type": "feed_loss", "params": {"loss_pct": 30}},
        {"type": "tower_failure", "params": {"tower_id": tower_id}},
        {"type": "road_failure", "params": {"count": 3}},
        {"type": "shelter_capacity_change", "params": {"change_pct": -20}},
    ]
    result = injector.apply_failures(testbed, config)
    assert result["metrics"]["original_obs_count"] > result["metrics"]["final_obs_count"]
    assert result["metrics"]["failed_towers"] >= 1
    assert result["metrics"]["failed_roads"] >= 3
    assert result["metrics"]["original_obs_count"] > 0


def test_apply_failures_empty_config(testbed, injector):
    """apply_failures with empty config applies only the tower cascade (no-op)."""
    infra_before = testbed.get_infrastructure()
    pre_failed_roads = sum(
        1 for e in infra_before.roads.edges if e.flood_vulnerability >= 1.0
    )
    result = injector.apply_failures(testbed, [])
    assert result["metrics"]["failed_towers"] == 0
    assert result["metrics"]["failed_roads"] == pre_failed_roads
    assert result["metrics"]["final_obs_count"] > 0


def test_apply_failures_with_false_reports(testbed, injector):
    """apply_failures with false reports adds low-confidence observations."""
    config = [{"type": "false_reports", "params": {"count": 5}}]
    result = injector.apply_failures(testbed, config)
    confidences = confidence_vector(result["observations"])
    low_conf = [c for c in confidences if c < 0.5]
    assert len(low_conf) >= 5
