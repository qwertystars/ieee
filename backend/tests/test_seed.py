"""Tests for the seed data package (T52).

Verifies that seed_demo.run_seed() populates the DB with the Rivertown
cyclone-flood scenario and is idempotent. Uses the real PostgreSQL via
SessionLocal, following the test_reliability.py / test_scenarios.py pattern.

Test suite:
  1. test_seed_creates_demo_scenario — all entity counts match spec
  2. test_observations_count — observations >= 50
  3. test_roads_count — roads >= 20
  4. test_shelters_count — shelters >= 3
  5. test_hypotheses_with_contradictions — hypotheses >= 5, 2 contradictory
  6. test_seed_is_idempotent — run twice, same counts
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.entities import RoadSegment, Shelter, Zone
from app.models.enums import HypothesisStatus
from app.models.hypotheses import Hypothesis
from app.models.observation import Observation
from app.models.scenarios import Scenario
from app.seed.ids import INCIDENT_ID, ORG_ID
from app.seed.seed_demo import run_seed


@pytest.fixture(scope="module", autouse=True)
def _seed_db():
    """Run the seed once for the whole module (idempotent)."""
    run_seed()
    yield SessionLocal()


@pytest.fixture
def db(_seed_db):
    """Yield a session for queries (no cleanup — seed is idempotent)."""
    yield _seed_db


def test_seed_creates_demo_scenario(db) -> None:
    """Seed creates all entity types with expected minimum counts."""
    # Zones
    zone_count = db.execute(
        select(func.count()).select_from(Zone).where(Zone.org_id == ORG_ID)
    ).scalar()
    assert zone_count >= 5, f"expected >= 5 zones, got {zone_count}"

    # Scenarios (best/expected/worst)
    sc_count = db.execute(
        select(func.count()).select_from(Scenario).where(Scenario.org_id == ORG_ID)
    ).scalar()
    assert sc_count == 3, f"expected 3 scenarios, got {sc_count}"


def test_observations_count(db) -> None:
    """Seed creates at least 50 observations."""
    count = db.execute(
        select(func.count()).select_from(Observation).where(
            Observation.org_id == ORG_ID
        )
    ).scalar()
    assert count >= 50, f"expected >= 50 observations, got {count}"


def test_roads_count(db) -> None:
    """Seed creates at least 20 road segments."""
    count = db.execute(
        select(func.count()).select_from(RoadSegment).where(
            RoadSegment.org_id == ORG_ID
        )
    ).scalar()
    assert count >= 20, f"expected >= 20 roads, got {count}"


def test_shelters_count(db) -> None:
    """Seed creates at least 3 shelters."""
    count = db.execute(
        select(func.count()).select_from(Shelter).where(
            Shelter.org_id == ORG_ID
        )
    ).scalar()
    assert count >= 3, f"expected >= 3 shelters, got {count}"


def test_hypotheses_with_contradictions(db) -> None:
    """Seed creates >= 5 hypotheses, including 2 contradictory about the same entity."""
    hyps = db.execute(
        select(Hypothesis).where(Hypothesis.org_id == ORG_ID)
    ).scalars().all()

    assert len(hyps) >= 5, f"expected >= 5 hypotheses, got {len(hyps)}"

    # All are active
    for h in hyps:
        assert h.status == HypothesisStatus.active

    # Find contradictory pair: same entity_id, different claims
    by_entity: dict[str, list[Hypothesis]] = {}
    for h in hyps:
        by_entity.setdefault(h.entity_id, []).append(h)

    contradictory_found = False
    for eid, group in by_entity.items():
        if len(group) >= 2:
            claims = {h.claim for h in group}
            if len(claims) >= 2:
                contradictory_found = True
                break

    assert contradictory_found, (
        "expected at least 2 contradictory hypotheses for the same entity"
    )


def test_seed_is_idempotent(db) -> None:
    """Running seed twice produces the same row counts."""
    # Capture counts before second run
    obs_before = db.execute(
        select(func.count()).select_from(Observation).where(
            Observation.org_id == ORG_ID
        )
    ).scalar()
    roads_before = db.execute(
        select(func.count()).select_from(RoadSegment).where(
            RoadSegment.org_id == ORG_ID
        )
    ).scalar()
    hyps_before = db.execute(
        select(func.count()).select_from(Hypothesis).where(
            Hypothesis.org_id == ORG_ID
        )
    ).scalar()

    # Commit to release any locks before run_seed.
    db.commit()

    # Run seed again
    run_seed()

    # Expire cache so we read fresh from DB
    db.expire_all()

    obs_after = db.execute(
        select(func.count()).select_from(Observation).where(
            Observation.org_id == ORG_ID
        )
    ).scalar()
    roads_after = db.execute(
        select(func.count()).select_from(RoadSegment).where(
            RoadSegment.org_id == ORG_ID
        )
    ).scalar()
    hyps_after = db.execute(
        select(func.count()).select_from(Hypothesis).where(
            Hypothesis.org_id == ORG_ID
        )
    ).scalar()

    assert obs_before == obs_after, (
        f"observations not idempotent: {obs_before} -> {obs_after}"
    )
    assert roads_before == roads_after, (
        f"roads not idempotent: {roads_before} -> {roads_after}"
    )
    assert hyps_before == hyps_after, (
        f"hypotheses not idempotent: {hyps_before} -> {hyps_after}"
    )
