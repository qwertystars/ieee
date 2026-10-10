"""Tests for the scenario ensemble generator (T23).

Unit tests for ensemble generation (no DB) + integration test for DB storage.
The DB tests use the real PostgreSQL via SessionLocal, following the
test_reliability.py pattern. All test rows are cleaned up after each test.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.db import SessionLocal
from app.models.enums import ScenarioLabel, ScenarioStatus
from app.models.scenarios import Scenario as ScenarioRow
from app.twin.scenario_types import WorldStateSnapshot
from app.twin.scenarios import (
    DEFAULT_N,
    MAX_SCENARIOS,
    MIN_SCENARIOS,
    ScenarioGenerator,
)

# Mock world state for deterministic tests — moderate flood severity.
MOCK_WORLD_STATE = WorldStateSnapshot(
    flood_severity_dist={
        "none": 0.1,
        "minor": 0.2,
        "moderate": 0.4,
        "severe": 0.2,
        "extreme": 0.1,
    },
    flood_extent_pct=25.0,
    flood_uncertainty=0.15,
    road_ids=("road_001", "road_002", "road_003", "road_004", "road_005"),
    current_time_ms=1_700_000_000_000,
)

ORG_ID = "test_scenarios_org"
INCIDENT_ID = "test_scenarios_incident"


def _params_key(sc):
    """Hashable key for a Scenario's params (tuples instead of lists)."""
    p = sc.params
    return (
        p.rainfall_trajectory,
        p.storm_surge_height,
        p.embankment_failure,
        p.drainage_blockage,
        p.road_failure,
        p.power_restoration_hours,
        p.shelter_inflow,
        p.hospital_demand,
        p.communication_availability,
    )


@pytest.fixture
def db():
    """Yield a session and clean up all test rows after each test."""
    session = SessionLocal()
    session.execute(delete(ScenarioRow).where(ScenarioRow.org_id == ORG_ID))
    session.commit()
    try:
        yield session
    finally:
        session.execute(delete(ScenarioRow).where(ScenarioRow.org_id == ORG_ID))
        session.commit()
        session.close()


def test_ensemble_generation() -> None:
    """Generate 20 scenarios: unique params + probability, probs sum to ~1.0."""
    gen = ScenarioGenerator(MOCK_WORLD_STATE, seed=42)
    scenarios = gen.generate(n=20)
    assert len(scenarios) == 20
    for sc in scenarios:
        assert sc.id
        assert 0.0 < sc.probability <= 1.0
        assert sc.label in (
            ScenarioLabel.best,
            ScenarioLabel.expected,
            ScenarioLabel.worst,
        )
    total = sum(sc.probability for sc in scenarios)
    assert abs(total - 1.0) < 1e-9, f"probabilities sum to {total}, expected 1.0"
    unique = {_params_key(sc) for sc in scenarios}
    assert len(unique) == 20, "all scenarios should have unique params"


def test_probabilities_sum_to_one() -> None:
    """Probabilities sum to ~1.0 for various ensemble sizes."""
    gen = ScenarioGenerator(MOCK_WORLD_STATE, seed=42)
    for n in (10, 20, 30, 50):
        scenarios = gen.generate(n=n)
        total = sum(sc.probability for sc in scenarios)
        assert abs(total - 1.0) < 1e-9, f"n={n}: probs sum to {total}"


def test_different_seeds_produce_different_scenarios() -> None:
    """Different seeds produce different ensembles."""
    gen_a = ScenarioGenerator(MOCK_WORLD_STATE, seed=42)
    gen_b = ScenarioGenerator(MOCK_WORLD_STATE, seed=99)
    scenarios_a = gen_a.generate(n=20)
    scenarios_b = gen_b.generate(n=20)
    keys_a = {_params_key(sc) for sc in scenarios_a}
    keys_b = {_params_key(sc) for sc in scenarios_b}
    assert keys_a != keys_b, "different seeds should produce different params"


def test_same_seed_produces_same_scenarios() -> None:
    """Same seed produces identical ensembles."""
    gen_a = ScenarioGenerator(MOCK_WORLD_STATE, seed=42)
    gen_b = ScenarioGenerator(MOCK_WORLD_STATE, seed=42)
    scenarios_a = gen_a.generate(n=20)
    scenarios_b = gen_b.generate(n=20)
    assert len(scenarios_a) == len(scenarios_b)
    for sa, sb in zip(scenarios_a, scenarios_b, strict=True):
        assert _params_key(sa) == _params_key(sb)
        assert abs(sa.probability - sb.probability) < 1e-12
        assert sa.label == sb.label


def test_scenario_count_configurable() -> None:
    """Can generate 10, 20, and 50 scenarios."""
    gen = ScenarioGenerator(MOCK_WORLD_STATE, seed=42)
    for n in (MIN_SCENARIOS, DEFAULT_N, MAX_SCENARIOS):
        scenarios = gen.generate(n=n)
        assert len(scenarios) == n


def test_invalid_count_rejected() -> None:
    """Counts outside [10, 50] are rejected."""
    gen = ScenarioGenerator(MOCK_WORLD_STATE, seed=42)
    with pytest.raises(ValueError):
        gen.generate(n=5)
    with pytest.raises(ValueError):
        gen.generate(n=100)


def test_labels_assigned_by_tertiles() -> None:
    """Best/expected/worst labels are assigned by severity tertiles."""
    gen = ScenarioGenerator(MOCK_WORLD_STATE, seed=42)
    scenarios = gen.generate(n=20)
    labels = [sc.label for sc in scenarios]
    assert ScenarioLabel.best in labels
    assert ScenarioLabel.expected in labels
    assert ScenarioLabel.worst in labels
    third = 20 // 3
    assert labels.count(ScenarioLabel.best) == third
    assert labels.count(ScenarioLabel.worst) == third


def test_store_scenarios_to_db(db) -> None:
    """Scenarios are persisted to the scenarios table with correct fields."""
    gen = ScenarioGenerator(MOCK_WORLD_STATE, seed=42)
    scenarios = gen.generate(n=10)
    ids = gen.store(db, scenarios, org_id=ORG_ID, incident_id=INCIDENT_ID)
    assert len(ids) == 10
    rows = (
        db.query(ScenarioRow)
        .filter(ScenarioRow.org_id == ORG_ID)
        .order_by(ScenarioRow.id)
        .all()
    )
    assert len(rows) == 10
    stored_ids = {r.id for r in rows}
    for sc in scenarios:
        assert sc.id in stored_ids
    for row in rows:
        assert row.org_id == ORG_ID
        assert row.incident_id == INCIDENT_ID
        assert row.label in (
            ScenarioLabel.best,
            ScenarioLabel.expected,
            ScenarioLabel.worst,
        )
        assert row.status == ScenarioStatus.queued
        assert row.params is not None
        assert "rainfall_trajectory" in row.params
        assert row.result_geojson is None
        assert row.completed_at is None
