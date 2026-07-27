"""Tests for source reliability tracking via Beta(alpha, beta) conjugate prior (T14).

Uses the real PostgreSQL database via SessionLocal. The source_reliability
table is created by Alembic migrations. All test rows are cleaned up after
each test.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.db import SessionLocal
from app.fusion.reliability import (
    SourceReliability,
    SourceReliabilityTracker,
)
from app.lib.time import now_ms

# Unique source_id per test module to avoid collisions with other test modules.
SOURCE = "test_reliability_source"


@pytest.fixture
def db():
    """Yield a session and clean up all test rows after each test."""
    session = SessionLocal()
    session.execute(delete(SourceReliability).where(SourceReliability.source_id == SOURCE))
    session.commit()
    try:
        yield session
    finally:
        session.execute(
            delete(SourceReliability).where(SourceReliability.source_id == SOURCE)
        )
        session.commit()
        session.close()


def test_prior_reliability(db):
    """A new source with no data returns the prior Beta(2,2): expected=0.5, CI=(0.1, 0.9)."""
    tracker = SourceReliabilityTracker(db)
    expected, ci_lo, ci_hi = tracker.get_reliability(SOURCE)
    assert expected == 0.5
    assert ci_lo == 0.1
    assert ci_hi == 0.9


def test_correct_increases_reliability(db):
    """3 correct reports -> alpha=5, beta=2, expected=5/7≈0.714 > 0.6."""
    tracker = SourceReliabilityTracker(db)
    for _ in range(3):
        tracker.update(SOURCE, verified_correct=True)
    expected, ci_lo, ci_hi = tracker.get_reliability(SOURCE)
    # alpha = 2 + 3 = 5, beta = 2, expected = 5/7 ≈ 0.714
    assert expected > 0.6, f"expected={expected} should be > 0.6 after 3 correct"
    assert ci_lo < expected < ci_hi


def test_disproven_decreases_reliability(db):
    """2 disproven reports -> alpha=2, beta=4, expected=2/6≈0.333 < 0.4."""
    tracker = SourceReliabilityTracker(db)
    for _ in range(2):
        tracker.update(SOURCE, verified_correct=False)
    expected, ci_lo, ci_hi = tracker.get_reliability(SOURCE)
    # alpha = 2, beta = 2 + 2 = 4, expected = 2/6 ≈ 0.333
    assert expected < 0.4, f"expected={expected} should be < 0.4 after 2 disproven"
    assert ci_lo < expected < ci_hi


def test_conditioned_reliability(db):
    """Same source reliable for roads (α=10, β=1) but poor for flood_depth (α=1, β=10)."""
    tracker = SourceReliabilityTracker(db)
    # Insert conditioned rows directly to set exact alpha/beta values.
    db.add(
        SourceReliability(
            source_id=SOURCE,
            phenomenon_type="road_passability",
            alpha=10.0,
            beta=1.0,
            updated_at=now_ms(),
        )
    )
    db.add(
        SourceReliability(
            source_id=SOURCE,
            phenomenon_type="flood_depth",
            alpha=1.0,
            beta=10.0,
            updated_at=now_ms(),
        )
    )
    db.commit()

    road_exp, road_lo, road_hi = tracker.get_reliability(SOURCE, "road_passability")
    flood_exp, flood_lo, flood_hi = tracker.get_reliability(SOURCE, "flood_depth")

    # Roads: 10/11 ≈ 0.909 (reliable)
    assert road_exp > 0.8, f"road expected={road_exp} should be > 0.8"
    assert road_lo < road_exp < road_hi

    # Flood depth: 1/11 ≈ 0.091 (poor)
    assert flood_exp < 0.2, f"flood_depth expected={flood_exp} should be < 0.2"
    assert flood_lo < flood_exp < flood_hi

    # The same source is reliable for one phenomenon and poor for another.
    assert road_exp > flood_exp


def test_time_decay(db):
    """apply_time_decay multiplies alpha and beta by decay_factor for all rows."""
    tracker = SourceReliabilityTracker(db)
    # Set up a global row and a conditioned row with known values.
    db.add(
        SourceReliability(
            source_id=SOURCE,
            phenomenon_type=None,
            alpha=10.0,
            beta=2.0,
            updated_at=now_ms(),
        )
    )
    db.add(
        SourceReliability(
            source_id=SOURCE,
            phenomenon_type="road_passability",
            alpha=8.0,
            beta=4.0,
            updated_at=now_ms(),
        )
    )
    db.commit()

    # Apply decay_factor=0.5: alpha_eff = alpha * 0.5, beta_eff = beta * 0.5.
    tracker.apply_time_decay(SOURCE, decay_factor=0.5)

    # Verify both rows were decayed.
    rows = (
        db.query(SourceReliability)
        .filter(SourceReliability.source_id == SOURCE)
        .order_by(SourceReliability.phenomenon_type.asc())
        .all()
    )
    assert len(rows) == 2

    # Global row (phenomenon_type is None, sorts first with NULLS FIRST in PG).
    global_row = next(r for r in rows if r.phenomenon_type is None)
    assert global_row.alpha == pytest.approx(5.0)
    assert global_row.beta == pytest.approx(1.0)

    # Conditioned row.
    road_row = next(r for r in rows if r.phenomenon_type == "road_passability")
    assert road_row.alpha == pytest.approx(4.0)
    assert road_row.beta == pytest.approx(2.0)


def test_get_conditioned_reliability(db):
    """get_conditioned_reliability returns dict of per-phenomenon results."""
    tracker = SourceReliabilityTracker(db)
    # Global row (should be EXCLUDED from the conditioned dict).
    db.add(
        SourceReliability(
            source_id=SOURCE,
            phenomenon_type=None,
            alpha=5.0,
            beta=5.0,
            updated_at=now_ms(),
        )
    )
    # Two conditioned rows.
    db.add(
        SourceReliability(
            source_id=SOURCE,
            phenomenon_type="road_passability",
            alpha=10.0,
            beta=1.0,
            updated_at=now_ms(),
        )
    )
    db.add(
        SourceReliability(
            source_id=SOURCE,
            phenomenon_type="flood_depth",
            alpha=1.0,
            beta=10.0,
            updated_at=now_ms(),
        )
    )
    db.commit()

    result = tracker.get_conditioned_reliability(SOURCE)

    # Only per-phenomenon rows are included (global row excluded).
    assert set(result.keys()) == {"road_passability", "flood_depth"}
    assert result["road_passability"][0] == pytest.approx(10.0 / 11.0)
    assert result["flood_depth"][0] == pytest.approx(1.0 / 11.0)
    # Each value is a (expected, ci_lo, ci_hi) tuple.
    for phen, (exp, lo, hi) in result.items():
        assert lo < exp < hi, f"{phen}: ci {lo},{hi} should bracket expected {exp}"


def test_update_creates_row_if_missing(db):
    """update on an unknown source creates a row starting from the prior Beta(2,2)."""
    tracker = SourceReliabilityTracker(db)

    # No row exists initially -> get_reliability returns prior.
    expected, _, _ = tracker.get_reliability(SOURCE)
    assert expected == 0.5

    # One correct update creates a row from prior: alpha=2+1=3, beta=2.
    tracker.update(SOURCE, verified_correct=True)
    expected, ci_lo, ci_hi = tracker.get_reliability(SOURCE)
    # alpha=3, beta=2, expected=3/5=0.6
    assert expected == pytest.approx(0.6)
    assert ci_lo < expected < ci_hi

    # Verify the row was actually persisted.
    row = (
        db.query(SourceReliability)
        .filter(
            SourceReliability.source_id == SOURCE,
            SourceReliability.phenomenon_type.is_(None),
        )
        .one()
    )
    assert row.alpha == pytest.approx(3.0)
    assert row.beta == pytest.approx(2.0)


def test_ci_widens_with_uncertainty(db):
    """Beta(2,2) has a wider 95% CI than Beta(100,100).

    Less data (smaller alpha+beta) means more uncertainty, so the credible
    interval is wider. scipy.stats.beta.ppf computes the quantiles.
    """
    tracker = SourceReliabilityTracker(db)

    # Beta(2,2): low confidence, wide CI.
    db.add(
        SourceReliability(
            source_id=SOURCE,
            phenomenon_type=None,
            alpha=2.0,
            beta=2.0,
            updated_at=now_ms(),
        )
    )
    db.commit()
    _, lo_low, hi_low = tracker.get_reliability(SOURCE)
    width_low = hi_low - lo_low

    # Replace with Beta(100,100): high confidence, narrow CI.
    db.execute(delete(SourceReliability).where(SourceReliability.source_id == SOURCE))
    db.add(
        SourceReliability(
            source_id=SOURCE,
            phenomenon_type=None,
            alpha=100.0,
            beta=100.0,
            updated_at=now_ms(),
        )
    )
    db.commit()
    _, lo_high, hi_high = tracker.get_reliability(SOURCE)
    width_high = hi_high - lo_high

    # Both CIs bracket 0.5 (symmetric priors).
    assert lo_low < 0.5 < hi_low
    assert lo_high < 0.5 < hi_high
    # The uncertain distribution has a wider CI.
    assert width_low > width_high, (
        f"Beta(2,2) width={width_low} should be > Beta(100,100) width={width_high}"
    )
