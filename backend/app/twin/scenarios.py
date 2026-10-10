"""Scenario ensemble generator — N scenarios varying rainfall, surge, drainage,
road failure, power, shelter, hospital, and comms.

Reads current world state from T16 (WorldStateEstimator DBN) + T18 (flood maps)
+ infrastructure status via a ``WorldStateSnapshot``, and produces an ensemble
of N scenarios (10-50) with probabilities summing to 1.0. Each scenario varies
9 parameters. Uses numpy with a configurable seed for reproducibility.

This is an ENSEMBLE generator, not a single forecast. The ensemble Ω =
{ω_1, ..., ω_N} captures the uncertainty space for downstream robust
optimization (T24+).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import ScenarioLabel, ScenarioStatus
from app.models.scenarios import Scenario as ScenarioRow
from app.twin.scenario_types import (
    Scenario,
    ScenarioParams,
    WorldStateSnapshot,
)

# Severity state ordering (must match DEFAULT_SEVERITY_STATES in world_state.py).
_SEVERITY_STATES: tuple[str, ...] = (
    "none", "minor", "moderate", "severe", "extreme",
)

DEFAULT_N: int = 20
MAX_SCENARIOS: int = 50
MIN_SCENARIOS: int = 10
_TRAJECTORY_HOURS: int = 6


def _expected_severity(dist: dict[str, float]) -> float:
    """Compute expected severity index [0, 4] from a distribution."""
    return float(sum(i * dist.get(s, 0.0) for i, s in enumerate(_SEVERITY_STATES)))


class ScenarioGenerator:
    """Generate an ensemble of N scenarios from the current world state.

    The same seed always produces the same ensemble; different seeds produce
    different ensembles. Probabilities are assigned via a Gaussian kernel on
    severity deviation from the expected world state, normalized to sum to 1.0.
    """

    def __init__(
        self,
        world_state: WorldStateSnapshot,
        seed: int = 42,
        max_scenarios: int = MAX_SCENARIOS,
    ) -> None:
        if max_scenarios < MIN_SCENARIOS:
            raise ValueError(
                f"max_scenarios must be >= {MIN_SCENARIOS}, got {max_scenarios}"
            )
        self._ws = world_state
        self._rng = np.random.default_rng(seed)
        self._max = max_scenarios
        self._expected_sev = _expected_severity(world_state.flood_severity_dist)

    def generate(self, n: int = DEFAULT_N) -> list[Scenario]:
        """Generate N scenarios with probabilities summing to ~1.0."""
        if n < MIN_SCENARIOS or n > self._max:
            raise ValueError(
                f"n must be in [{MIN_SCENARIOS}, {self._max}], got {n}"
            )
        params_list = [self._sample_params() for _ in range(n)]
        probs = self._compute_probabilities(params_list)
        labels = self._assign_labels(params_list)
        return [
            Scenario(
                id=generate_ulid(),
                label=labels[i],
                probability=probs[i],
                params=params_list[i],
            )
            for i in range(n)
        ]

    def _sample_params(self) -> ScenarioParams:
        """Sample a single scenario's parameters centered on the world state."""
        sev = self._expected_sev
        base_rain = 5.0 + sev * 12.0
        rain = tuple(
            float(max(0.0, self._rng.normal(base_rain, base_rain * 0.3)))
            for _ in range(_TRAJECTORY_HOURS)
        )
        surge = float(max(0.0, self._rng.normal(sev * 0.6, 0.4)))
        p_embank = min(0.8, sev / 5.0 * 0.6)
        embank_fail = bool(self._rng.random() < p_embank)
        p_drain = min(0.85, sev / 5.0 * 0.7)
        drain_block = bool(self._rng.random() < p_drain)
        road_fail = self._sample_road_failure()
        power_hours = float(self._rng.uniform(1.0 + sev * 4.0, 48.0))
        shelter_max = max(1, int(100 + sev * 180))
        shelter = int(self._rng.integers(0, shelter_max))
        hospital_max = max(1, int(50 + sev * 90))
        hospital = int(self._rng.integers(0, hospital_max))
        comm = float(max(0.0, min(1.0, self._rng.normal(1.0 - sev * 0.15, 0.1))))
        return ScenarioParams(
            rainfall_trajectory=rain,
            storm_surge_height=surge,
            embankment_failure=embank_fail,
            drainage_blockage=drain_block,
            road_failure=road_fail,
            power_restoration_hours=power_hours,
            shelter_inflow=shelter,
            hospital_demand=hospital,
            communication_availability=comm,
        )

    def _sample_road_failure(self) -> tuple[str, ...]:
        """Sample a subset of road IDs that fail in this scenario."""
        n_roads = len(self._ws.road_ids)
        if n_roads == 0:
            return ()
        n_failed = int(self._rng.integers(0, n_roads + 1))
        if n_failed == 0:
            return ()
        failed = self._rng.choice(
            np.array(self._ws.road_ids), size=n_failed, replace=False
        )
        return tuple(str(r) for r in failed)

    def _compute_probabilities(
        self, params_list: list[ScenarioParams]
    ) -> list[float]:
        """Compute scenario probabilities via Gaussian kernel on severity deviation.

        Scenarios closer to the expected world-state severity get higher
        probability. Weights are normalized to sum to 1.0.
        """
        scores = np.array([self._severity_score(p) for p in params_list])
        target = self._expected_sev / 4.0  # normalize to [0, 1]
        deviations = np.abs(scores - target)
        sigma = max(float(deviations.std()), 0.1)
        weights = np.exp(-(deviations**2) / (2.0 * sigma**2))
        total = float(weights.sum())
        if total <= 0.0:
            return [1.0 / len(params_list)] * len(params_list)
        return [float(w / total) for w in weights]

    def _severity_score(self, p: ScenarioParams) -> float:
        """Composite severity score in [0, 1] for labeling and probability."""
        rain_score = min(1.0, sum(p.rainfall_trajectory) / 300.0)
        surge_score = min(1.0, p.storm_surge_height / 3.0)
        n_roads = max(1, len(self._ws.road_ids))
        infra_score = (
            0.3 * float(p.embankment_failure)
            + 0.3 * float(p.drainage_blockage)
            + 0.4 * (len(p.road_failure) / n_roads)
        )
        demand_score = min(
            1.0, (p.shelter_inflow / 1000.0 + p.hospital_demand / 500.0) / 2.0
        )
        comm_score = 1.0 - p.communication_availability
        power_score = min(1.0, 1.0 - p.power_restoration_hours / 48.0)
        return float(
            0.25 * rain_score
            + 0.20 * surge_score
            + 0.20 * infra_score
            + 0.15 * demand_score
            + 0.10 * comm_score
            + 0.10 * power_score
        )

    def _assign_labels(
        self, params_list: list[ScenarioParams]
    ) -> list[ScenarioLabel]:
        """Assign best/expected/worst labels by severity tertiles."""
        scores = [self._severity_score(p) for p in params_list]
        sorted_idx = sorted(range(len(scores)), key=lambda i: scores[i])
        n = len(scores)
        labels: list[ScenarioLabel] = [ScenarioLabel.expected] * n
        third = max(1, n // 3)
        for rank, idx in enumerate(sorted_idx):
            if rank < third:
                labels[idx] = ScenarioLabel.best
            elif rank >= n - third:
                labels[idx] = ScenarioLabel.worst
        return labels

    def store(
        self,
        db: Session,
        scenarios: Sequence[Scenario],
        org_id: str,
        incident_id: str,
    ) -> list[str]:
        """Persist scenarios to the scenarios table. Returns the stored IDs."""
        now = now_ms()
        ids: list[str] = []
        for sc in scenarios:
            row = ScenarioRow(
                id=sc.id,
                org_id=org_id,
                incident_id=incident_id,
                label=sc.label,
                probability=sc.probability,
                params=sc.to_params_dict(),
                result_geojson=None,
                status=ScenarioStatus.queued,
                created_at=now,
                completed_at=None,
            )
            db.add(row)
            ids.append(sc.id)
        db.commit()
        return ids


__all__ = ["DEFAULT_N", "MAX_SCENARIOS", "MIN_SCENARIOS", "ScenarioGenerator"]
