"""Source reliability tracking via Beta(alpha, beta) conjugate prior.

Each source's reliability is modeled as a Beta distribution. Field verification
updates alpha (correct) or beta (disproven). Per-phenomenon-type conditioning
allows a source to be reliable for roads but poor for flood_depth.

All credibility is updatable — no permanent scores are assigned.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Float, Integer, String, select
from sqlalchemy.orm import Session

from app.db import Base
from app.lib.time import now_ms

# Prior hyperparameters: Beta(2, 2) -> expected 0.5, wide uncertainty.
_PRIOR_ALPHA = 2.0
_PRIOR_BETA = 2.0
# Hardcoded 95% CI for the prior (no-data case). The actual scipy-computed
# CI for Beta(2, 2) is (~0.068, ~0.932); the task spec mandates (0.1, 0.9).
_PRIOR_EXPECTED = 0.5
_PRIOR_CI_LOWER = 0.1
_PRIOR_CI_UPPER = 0.9


def _beta_ci(alpha: float, beta: float) -> tuple[float, float]:
    """95% credible interval for Beta(alpha, beta) via scipy.stats.beta.ppf."""
    from scipy.stats import beta as beta_dist

    lo = float(beta_dist.ppf(0.025, alpha, beta))
    hi = float(beta_dist.ppf(0.975, alpha, beta))
    return (lo, hi)


class SourceReliability(Base):
    """Beta(alpha, beta) parameters for a source, optionally per phenomenon type.

    phenomenon_type is NULL for the global (unconditioned) reliability row.
    Per-type rows store independent (alpha, beta) for that phenomenon.
    """

    __tablename__ = "source_reliability"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String, nullable=False, index=True)
    phenomenon_type = Column(String, nullable=True)  # NULL for global
    alpha = Column(Float, nullable=False, default=_PRIOR_ALPHA)
    beta = Column(Float, nullable=False, default=_PRIOR_BETA)
    updated_at = Column(BigInteger, nullable=False, default=now_ms)


class SourceReliabilityTracker:
    """Tracks source reliability via Beta(alpha, beta) with field verification.

    - Prior: Beta(2, 2) -> expected 0.5
    - update(correct=True):  alpha += 1
    - update(correct=False): beta  += 1
    - Per (source_id, phenomenon_type) conditioning supported
    - Time decay: alpha_eff = alpha * decay, beta_eff = beta * decay
    - All scores are always updatable (no permanent credibility)
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def _get_row(
        self, source_id: str, phenomenon_type: str | None
    ) -> SourceReliability | None:
        """Fetch the reliability row for (source_id, phenomenon_type)."""
        stmt = select(SourceReliability).where(
            SourceReliability.source_id == source_id
        )
        if phenomenon_type is None:
            stmt = stmt.where(SourceReliability.phenomenon_type.is_(None))
        else:
            stmt = stmt.where(
                SourceReliability.phenomenon_type == phenomenon_type
            )
        return self.db.execute(stmt).scalars().first()

    def get_reliability(
        self, source_id: str, phenomenon_type: str | None = None
    ) -> tuple[float, float, float]:
        """Return (expected_reliability, ci_lower, ci_upper).

        Expected = alpha / (alpha + beta). 95% CI via scipy.stats.beta.ppf.
        If no data exists, returns the prior (0.5, 0.1, 0.9).
        """
        row = self._get_row(source_id, phenomenon_type)
        if row is None:
            return (_PRIOR_EXPECTED, _PRIOR_CI_LOWER, _PRIOR_CI_UPPER)
        alpha, beta = float(row.alpha), float(row.beta)
        expected = alpha / (alpha + beta)
        ci_lo, ci_hi = _beta_ci(alpha, beta)
        return (expected, ci_lo, ci_hi)

    def update(
        self,
        source_id: str,
        verified_correct: bool,
        phenomenon_type: str | None = None,
    ) -> None:
        """Update alpha (correct) or beta (disproven).

        Creates a row starting from the prior Beta(2, 2) if none exists.
        Stores per (source_id, phenomenon_type) when phenomenon_type is given.
        """
        row = self._get_row(source_id, phenomenon_type)
        if row is None:
            row = SourceReliability(
                source_id=source_id,
                phenomenon_type=phenomenon_type,
                alpha=_PRIOR_ALPHA,
                beta=_PRIOR_BETA,
                updated_at=now_ms(),
            )
            self.db.add(row)
        if verified_correct:
            row.alpha = float(row.alpha) + 1  # type: ignore[assignment]
        else:
            row.beta = float(row.beta) + 1  # type: ignore[assignment]
        row.updated_at = now_ms()  # type: ignore[assignment]
        self.db.commit()

    def apply_time_decay(
        self, source_id: str, decay_factor: float
    ) -> None:
        """Decay alpha and beta by decay_factor for ALL rows of this source.

        alpha_eff = alpha * decay_factor, beta_eff = beta * decay_factor.
        Applies to both the global row and all per-phenomenon-type rows so
        old performance does not dominate new evidence.
        """
        rows = self.db.execute(
            select(SourceReliability).where(
                SourceReliability.source_id == source_id
            )
        ).scalars().all()
        for row in rows:
            row.alpha = float(row.alpha) * decay_factor  # type: ignore[assignment]
            row.beta = float(row.beta) * decay_factor  # type: ignore[assignment]
            row.updated_at = now_ms()  # type: ignore[assignment]
        self.db.commit()

    def get_conditioned_reliability(self, source_id: str) -> dict:
        """Return per-phenomenon-type reliability for this source.

        Returns {phenomenon_type: (expected, ci_lower, ci_upper)}.
        Only includes rows with a non-NULL phenomenon_type (excludes the
        global row). A source can be reliable for roads but poor for
        flood_depth.
        """
        rows = self.db.execute(
            select(SourceReliability).where(
                SourceReliability.source_id == source_id,
                SourceReliability.phenomenon_type.is_not(None),
            )
        ).scalars().all()
        result: dict[str, tuple[float, float, float]] = {}
        for row in rows:
            alpha, beta = float(row.alpha), float(row.beta)
            expected = alpha / (alpha + beta)
            ci_lo, ci_hi = _beta_ci(alpha, beta)
            result[str(row.phenomenon_type)] = (expected, ci_lo, ci_hi)
        return result


__all__ = ["SourceReliability", "SourceReliabilityTracker"]
