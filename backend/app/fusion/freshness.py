"""Phenomenon-specific freshness decay.

Computes freshness F = exp(-age / tau) where age is the elapsed seconds
since observation and tau is phenomenon-specific. Freshness is computed on
READ (not write) so it always reflects the current moment.

Timestamps are UTC epoch milliseconds (BigInteger); tau values are in seconds.
"""

from __future__ import annotations

import math
from typing import Protocol

from app.lib.time import now_ms

# Default tau (decay constant) in seconds for unknown phenomena.
DEFAULT_TAU: int = 600  # 10 minutes

# Per-phenomenon tau values in seconds. Slowly-changing phenomena (building
# footprints, demographics) have large tau; fast-changing phenomena (responder
# position, water level) have small tau.
TAU_BY_PHENOMENON: dict[str, int] = {
    "responder_position": 60,  # 1 minute
    "road_passability": 600,  # 10 minutes
    "shelter_capacity": 1800,  # 30 minutes
    "building_footprint": 86400,  # 1 day
    "demographic_vulnerability": 2592000,  # 30 days
    "water_level": 300,  # 5 minutes
    "flood_depth": 600,  # 10 minutes
    "rainfall": 300,  # 5 minutes
    "wind_speed": 300,  # 5 minutes
}


class _ObsLike(Protocol):
    """Structural type for objects with observed_at and phenomenon fields."""

    observed_at: int
    phenomenon: str


class FreshnessCalculator:
    """Computes phenomenon-specific freshness scores for observations.

    Freshness is computed on read, not stored at write time, so the value
    always reflects the current moment. Per-phenomenon tau values can be
    overridden per-instance (tenant-overridable config); a future DB table
    can back this dict.
    """

    def __init__(self, tau_overrides: dict[str, int] | None = None) -> None:
        # Copy the base defaults so instance updates don't mutate the
        # module-level dict.
        self._overrides: dict[str, int] = dict(TAU_BY_PHENOMENON)
        if tau_overrides:
            self._overrides.update(tau_overrides)

    def get_tau(self, phenomenon: str) -> int:
        """Return the tau (seconds) for a phenomenon type.

        Falls back to DEFAULT_TAU for unknown phenomena.
        """
        return self._overrides.get(phenomenon, DEFAULT_TAU)

    def compute_freshness(
        self,
        observed_at: int,
        current_time: int,
        phenomenon: str,
    ) -> float:
        """Compute freshness F = exp(-age_seconds / tau).

        Timestamps are UTC epoch milliseconds. Returns a float in [0.0, 1.0]:
        - age 0 (just observed) -> 1.0
        - large age -> approaches 0.0
        - future observations (observed_at > current_time) clamped to 1.0
        """
        tau = self.get_tau(phenomenon)
        age_ms = current_time - observed_at
        if age_ms <= 0:
            return 1.0
        age_seconds = age_ms / 1000.0
        return math.exp(-age_seconds / tau)

    def compute_for_observation(self, observation: _ObsLike) -> float:
        """Convenience: compute freshness for an observation object.

        Uses the observation's observed_at and phenomenon fields and the
        current wall-clock time.
        """
        return self.compute_freshness(
            observed_at=observation.observed_at,
            current_time=now_ms(),
            phenomenon=observation.phenomenon,
        )

    def update_tau(self, phenomenon: str, tau: int) -> None:
        """Override the tau for a phenomenon (tenant-overridable config).

        Stored in the instance dict for now; a future DB table can persist
        per-tenant overrides.
        """
        if tau <= 0:
            raise ValueError(f"tau must be positive, got {tau}")
        self._overrides[phenomenon] = tau


__all__ = [
    "DEFAULT_TAU",
    "TAU_BY_PHENOMENON",
    "FreshnessCalculator",
]
