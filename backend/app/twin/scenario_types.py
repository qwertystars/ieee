"""Scenario ensemble types — dataclasses for scenario generation.

Each scenario varies 9 parameters: rainfall trajectory, storm-surge height,
embankment failure, drainage blockage, road failure, power restoration,
shelter inflow, hospital demand, communication availability. Scenarios are
generated as an ensemble (N scenarios with probabilities summing to 1.0),
never a single forecast.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.enums import ScenarioLabel


@dataclass(frozen=True, slots=True)
class WorldStateSnapshot:
    """Parsed world state read from T16 (DBN) + T18 (flood maps) + infrastructure.

    The ScenarioGenerator consumes this snapshot rather than the raw estimator
    and flood-map objects, decoupling generation from upstream APIs and making
    testing straightforward (no pgmpy/torch needed in tests).
    """

    flood_severity_dist: dict[str, float]
    flood_extent_pct: float
    flood_uncertainty: float
    road_ids: tuple[str, ...]
    current_time_ms: int


@dataclass(frozen=True, slots=True)
class ScenarioParams:
    """Per-scenario varied parameters (9 dimensions of variation)."""

    rainfall_trajectory: tuple[float, ...]
    storm_surge_height: float
    embankment_failure: bool
    drainage_blockage: bool
    road_failure: tuple[str, ...]
    power_restoration_hours: float
    shelter_inflow: int
    hospital_demand: int
    communication_availability: float


@dataclass(frozen=True, slots=True)
class Scenario:
    """A single scenario in the ensemble Ω = {ω_1, ..., ω_N}."""

    id: str
    label: ScenarioLabel
    probability: float
    params: ScenarioParams

    def to_params_dict(self) -> dict[str, Any]:
        """Serialize params to a JSONB-compatible dict for storage."""
        p = self.params
        return {
            "rainfall_trajectory": list(p.rainfall_trajectory),
            "storm_surge_height": p.storm_surge_height,
            "embankment_failure": p.embankment_failure,
            "drainage_blockage": p.drainage_blockage,
            "road_failure": list(p.road_failure),
            "power_restoration_hours": p.power_restoration_hours,
            "shelter_inflow": p.shelter_inflow,
            "hospital_demand": p.hospital_demand,
            "communication_availability": p.communication_availability,
        }


__all__ = ["Scenario", "ScenarioParams", "WorldStateSnapshot"]
