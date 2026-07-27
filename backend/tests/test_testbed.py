"""Tests for the digital twin testbed (T41).

Verifies that DigitalTwinTestbed generates a city-scale digital twin with
the expected entity counts, is deterministic (same seed -> identical output),
produces different output for different seeds, generates a reproducible
observation stream, and respects configurable parameters.

No DB needed — the testbed is fully in-memory. Uses numpy for reproducibility.
Run: docker compose run --rm -e PYTHONPATH=/app backend sh -c \
    "pip install pytest -q && python -m pytest tests/test_testbed.py -q"
"""

from __future__ import annotations

import pytest

from app.eval.testbed import DigitalTwinTestbed
from app.eval.testbed_types import (
    BuildingType,
    ObservationSource,
    RoadClass,
    TestbedParams,
)

DEFAULT_PARAMS = TestbedParams()


def test_generates_testbed_with_expected_counts() -> None:
    """Testbed has >= 1000 buildings, 50 roads, 5 shelters, 2 hospitals, 10000 pop."""
    tb = DigitalTwinTestbed()
    infra = tb.generate(seed=42, params=DEFAULT_PARAMS)
    assert len(infra.buildings) >= 1000, f"buildings: {len(infra.buildings)}"
    assert len(infra.roads.edges) >= 50, f"roads: {len(infra.roads.edges)}"
    assert len(infra.shelters) >= 5, f"shelters: {len(infra.shelters)}"
    assert len(infra.hospitals) >= 2, f"hospitals: {len(infra.hospitals)}"
    total_pop = sum(h.population for h in infra.population)
    assert total_pop >= 10000, f"population: {total_pop}"
    assert len(infra.substations) >= 1, "substations missing"
    assert len(infra.cell_towers) >= 1, "cell towers missing"
    assert len(infra.responder_stations) >= 1, "responder stations missing"
    assert len(infra.citizen_devices) >= 1, "citizen devices missing"
    assert infra.terrain.grid.shape == (50, 50), "DEM grid wrong shape"
    assert infra.terrain.resolution == 50


def test_deterministic() -> None:
    """Same seed + same params produces identical infrastructure."""
    tb1 = DigitalTwinTestbed()
    tb1.generate(seed=42, params=DEFAULT_PARAMS)
    tb2 = DigitalTwinTestbed()
    tb2.generate(seed=42, params=DEFAULT_PARAMS)
    assert tb1.fingerprint() == tb2.fingerprint(), "same seed should produce same output"
    infra1, infra2 = tb1.get_infrastructure(), tb2.get_infrastructure()
    assert len(infra1.buildings) == len(infra2.buildings)
    assert infra1.buildings[0].id == infra2.buildings[0].id
    assert infra1.buildings[0].lon == infra2.buildings[0].lon
    assert infra1.buildings[0].vulnerability_score == infra2.buildings[0].vulnerability_score


def test_different_seed_produces_different_output() -> None:
    """Different seeds produce different infrastructure."""
    tb1 = DigitalTwinTestbed()
    tb1.generate(seed=42, params=DEFAULT_PARAMS)
    tb2 = DigitalTwinTestbed()
    tb2.generate(seed=99, params=DEFAULT_PARAMS)
    assert tb1.fingerprint() != tb2.fingerprint(), "different seeds should differ"
    infra1, infra2 = tb1.get_infrastructure(), tb2.get_infrastructure()
    assert infra1.buildings[0].lon != infra2.buildings[0].lon, "building[0] lon should differ"


def test_observation_stream_reproducible() -> None:
    """Observation stream is reproducible with same seed + infrastructure."""
    tb = DigitalTwinTestbed()
    tb.generate(seed=42, params=DEFAULT_PARAMS)
    stream1 = tb.generate_observation_stream(seed=42, duration_hours=24)
    stream2 = tb.generate_observation_stream(seed=42, duration_hours=24)
    assert len(stream1) > 0, "stream should not be empty"
    assert len(stream1) == len(stream2), "stream length should match"
    assert stream1 == stream2, "same seed should produce identical stream"
    sources = {obs.source_type for obs in stream1}
    assert ObservationSource.sensor in sources, "stream should have sensor readings"
    assert ObservationSource.citizen_report in sources, "stream should have citizen reports"
    assert ObservationSource.official_alert in sources, "stream should have official alerts"
    timestamps = [obs.timestamp_ms for obs in stream1]
    assert timestamps == sorted(timestamps), "stream should be time-ordered"
    stream_short = tb.generate_observation_stream(seed=42, duration_hours=6)
    assert len(stream_short) < len(stream1), "shorter duration should have fewer observations"


def test_configurable_parameters() -> None:
    """Different params produce different output sizes."""
    small = TestbedParams(building_count=500, population=5000, road_count=30)
    large = TestbedParams(building_count=2000, population=20000, road_count=80)
    tb_small = DigitalTwinTestbed()
    infra_small = tb_small.generate(seed=42, params=small)
    tb_large = DigitalTwinTestbed()
    infra_large = tb_large.generate(seed=42, params=large)
    assert len(infra_small.buildings) == 500
    assert len(infra_large.buildings) == 2000
    assert len(infra_small.roads.edges) >= 30
    assert len(infra_large.roads.edges) >= 80
    pop_small = sum(h.population for h in infra_small.population)
    pop_large = sum(h.population for h in infra_large.population)
    assert pop_small == 5000, f"small pop: {pop_small}"
    assert pop_large == 20000, f"large pop: {pop_large}"


def test_get_methods_return_correct_data() -> None:
    """get_infrastructure, get_population, get_road_graph return expected data."""
    tb = DigitalTwinTestbed()
    tb.generate(seed=42, params=DEFAULT_PARAMS)
    infra = tb.get_infrastructure()
    pop = tb.get_population()
    roads = tb.get_road_graph()
    assert infra is not None
    assert len(pop) == 36  # 6x6 H3 grid
    assert all(h.h3_index.startswith("h3_") for h in pop)
    assert all(h.vulnerability in ("low", "medium", "high") for h in pop)
    assert len(roads.nodes) > 0
    assert len(roads.edges) >= 50
    assert all(e.road_class in list(RoadClass) for e in roads.edges)
    assert all(b.building_type in list(BuildingType) for b in infra.buildings)


def test_generate_before_observation_stream_raises() -> None:
    """generate_observation_stream raises if generate() not called first."""
    tb = DigitalTwinTestbed()
    with pytest.raises(RuntimeError, match="Call generate"):
        tb.generate_observation_stream(seed=42, duration_hours=24)
    with pytest.raises(RuntimeError, match="Call generate"):
        tb.get_infrastructure()
