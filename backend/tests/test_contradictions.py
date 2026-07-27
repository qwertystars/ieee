"""Integration test — contradictory hypothesis detection.

Verifies that the seed creates contradictory hypotheses (same entity_id,
different claims) and that they are preserved with status=active. The system
does NOT silently resolve contradictions — both are kept for the human
decision-maker.

Uses the real PostgreSQL database via SessionLocal. No mocking.
"""

from __future__ import annotations

from collections import defaultdict

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.enums import HypothesisStatus
from app.models.hypotheses import Hypothesis
from app.seed.ids import ORG_ID
from app.seed.seed_demo import seed_demo


@pytest.fixture(scope="module", autouse=True)
def _seed_db():
    """Run the seed once for the whole module (idempotent)."""
    seed_demo()
    yield SessionLocal()


@pytest.fixture
def db(_seed_db):
    """Yield a session for queries."""
    yield _seed_db


def test_contradictory_pair_exists(db) -> None:
    """At least one entity has two active hypotheses with different claims."""
    hyps = db.execute(
        select(Hypothesis).where(Hypothesis.org_id == ORG_ID)
    ).scalars().all()

    by_entity: dict[str, list[Hypothesis]] = defaultdict(list)
    for h in hyps:
        by_entity[h.entity_id].append(h)

    contradictory_found = False
    for eid, group in by_entity.items():
        if len(group) >= 2:
            claims = {h.claim for h in group}
            if len(claims) >= 2:
                contradictory_found = True
                break

    assert contradictory_found, (
        "no contradictory hypothesis pair found (same entity_id, different claims)"
    )


def test_contradictory_hypotheses_both_active(db) -> None:
    """Contradictory hypotheses are both status=active (not auto-resolved)."""
    hyps = db.execute(
        select(Hypothesis).where(Hypothesis.org_id == ORG_ID)
    ).scalars().all()

    by_entity: dict[str, list[Hypothesis]] = defaultdict(list)
    for h in hyps:
        by_entity[h.entity_id].append(h)

    for eid, group in by_entity.items():
        if len(group) >= 2:
            claims = {h.claim for h in group}
            if len(claims) >= 2:
                # Found a contradictory pair — both must be active.
                for h in group:
                    assert h.status == HypothesisStatus.active, (
                        f"hypothesis {h.id} status={h.status}, expected active"
                    )
                return

    # If no contradictory pair found, fail (covered by test above).
    assert False, "no contradictory pair to check"  # noqa: B011


def test_bridge_passable_impassable_pair(db) -> None:
    """The specific Bridge BR-04 contradictory pair exists in seed data."""
    hyps = db.execute(
        select(Hypothesis).where(Hypothesis.org_id == ORG_ID)
    ).scalars().all()

    claims = {h.claim for h in hyps}
    assert any("passable" in c.lower() for c in claims), (
        "no 'passable' hypothesis found"
    )
    assert any("impassable" in c.lower() for c in claims), (
        "no 'impassable' hypothesis found"
    )


def test_hypotheses_have_supporting_evidence(db) -> None:
    """Each hypothesis has supporting_evidence (traceable provenance)."""
    hyps = db.execute(
        select(Hypothesis).where(Hypothesis.org_id == ORG_ID)
    ).scalars().all()

    for h in hyps:
        assert h.supporting_evidence is not None, (
            f"hypothesis {h.id} has no supporting_evidence"
        )
        assert "source" in h.supporting_evidence, (
            f"hypothesis {h.id} supporting_evidence missing 'source'"
        )


def test_at_least_five_hypotheses(db) -> None:
    """Seed creates at least 5 hypotheses."""
    count = db.execute(
        select(func.count()).select_from(Hypothesis).where(
            Hypothesis.org_id == ORG_ID
        )
    ).scalar()
    assert count >= 5, f"expected >= 5 hypotheses, got {count}"
