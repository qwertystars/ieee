"""Integration test — seed idempotency.

Verifies that running seed_demo() twice produces the same row counts for
all entity types. The seed uses deterministic IDs (SHA-256 of stable keys)
and delete-then-insert per org+incident scope, so re-running is safe.

Uses the real PostgreSQL database via SessionLocal. No mocking.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.alert import Alert
from app.models.entities import (
    Building,
    Hospital,
    RoadSegment,
    Shelter,
    Zone,
)
from app.models.hypotheses import Hypothesis
from app.models.incident import Incident
from app.models.observation import Observation
from app.models.recommendation import Recommendation
from app.models.scenarios import Scenario
from app.seed.ids import ORG_ID
from app.seed.seed_demo import seed_demo


def _count_all(db) -> dict[str, int]:
    """Count all demo-scenario rows grouped by entity type."""
    counts: dict[str, int] = {}
    counts["incidents"] = db.execute(
        select(func.count()).select_from(Incident).where(
            Incident.org_id == ORG_ID)
    ).scalar()
    counts["zones"] = db.execute(
        select(func.count()).select_from(Zone).where(Zone.org_id == ORG_ID)
    ).scalar()
    counts["roads"] = db.execute(
        select(func.count()).select_from(RoadSegment).where(
            RoadSegment.org_id == ORG_ID)
    ).scalar()
    counts["shelters"] = db.execute(
        select(func.count()).select_from(Shelter).where(
            Shelter.org_id == ORG_ID)
    ).scalar()
    counts["hospitals"] = db.execute(
        select(func.count()).select_from(Hospital).where(
            Hospital.org_id == ORG_ID)
    ).scalar()
    counts["buildings"] = db.execute(
        select(func.count()).select_from(Building).where(
            Building.org_id == ORG_ID)
    ).scalar()
    counts["observations"] = db.execute(
        select(func.count()).select_from(Observation).where(
            Observation.org_id == ORG_ID)
    ).scalar()
    counts["hypotheses"] = db.execute(
        select(func.count()).select_from(Hypothesis).where(
            Hypothesis.org_id == ORG_ID)
    ).scalar()
    counts["scenarios"] = db.execute(
        select(func.count()).select_from(Scenario).where(
            Scenario.org_id == ORG_ID)
    ).scalar()
    counts["alerts"] = db.execute(
        select(func.count()).select_from(Alert).where(Alert.org_id == ORG_ID)
    ).scalar()
    counts["recommendations"] = db.execute(
        select(func.count()).select_from(Recommendation).where(
            Recommendation.org_id == ORG_ID)
    ).scalar()
    return counts


@pytest.fixture(scope="module", autouse=True)
def _seed_once():
    """Run seed once before the module, then again inside the test."""
    seed_demo()
    yield SessionLocal()


def test_seed_twice_produces_same_counts(_seed_once) -> None:
    """Running seed_demo() twice yields identical row counts for all entities."""
    db = _seed_once
    before = _count_all(db)
    db.commit()

    seed_demo()
    db.expire_all()
    after = _count_all(db)

    for entity, count_before in before.items():
        count_after = after[entity]
        assert count_before == count_after, (
            f"{entity} not idempotent: {count_before} -> {count_after}"
        )


def test_seed_returns_nonzero_counts(_seed_once) -> None:
    """Seed produces non-zero counts for all entity types."""
    db = _seed_once
    counts = _count_all(db)
    for entity, count in counts.items():
        assert count > 0, f"{entity} count is 0 after seed"


def test_seed_observations_at_least_fifty(_seed_once) -> None:
    """Seed creates at least 50 observations (per spec)."""
    db = _seed_once
    counts = _count_all(db)
    assert counts["observations"] >= 50, (
        f"expected >= 50 observations, got {counts['observations']}"
    )


def test_seed_scenarios_exactly_three(_seed_once) -> None:
    """Seed creates exactly 3 scenarios (best/expected/worst)."""
    db = _seed_once
    counts = _count_all(db)
    assert counts["scenarios"] == 3, (
        f"expected 3 scenarios, got {counts['scenarios']}"
    )
