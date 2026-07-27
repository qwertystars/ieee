"""Scenario seeder — creates 3 scenarios (best/expected/worst).

Each scenario has a probability, params (JSONB), and status=queued.
The probabilities sum to 1.0: best=0.2, expected=0.6, worst=0.2.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.models.enums import ScenarioLabel, ScenarioStatus
from app.models.scenarios import Scenario
from app.seed.ids import INCIDENT_ID, ORG_ID, seed_id


@dataclass(frozen=True, slots=True)
class _ScenarioSpec:
    label: ScenarioLabel
    probability: float
    params: dict[str, Any]


_SCENARIOS: list[_ScenarioSpec] = [
    _ScenarioSpec(
        label=ScenarioLabel.best,
        probability=0.2,
        params={
            "rainfall_trajectory": [120, 80, 40, 10],
            "storm_surge_height": 1.5,
            "embankment_failure": False,
            "drainage_blockage": 0.2,
            "road_failure": [],
            "power_restoration_hours": 2,
            "shelter_inflow": 500,
            "hospital_demand": 30,
            "communication_availability": 0.95,
            "description": "Flood recedes within 6h. Minimal infrastructure damage. All shelters operational.",
        },
    ),
    _ScenarioSpec(
        label=ScenarioLabel.expected,
        probability=0.6,
        params={
            "rainfall_trajectory": [180, 120, 60, 20],
            "storm_surge_height": 2.5,
            "embankment_failure": False,
            "drainage_blockage": 0.5,
            "road_failure": ["road_1", "road_4", "road_9"],
            "power_restoration_hours": 8,
            "shelter_inflow": 1200,
            "hospital_demand": 80,
            "communication_availability": 0.70,
            "description": "Moderate flooding in Wards 1-3. 3 roads impassable. SS-02 offline 8h. Shelters at 70% capacity.",
        },
    ),
    _ScenarioSpec(
        label=ScenarioLabel.worst,
        probability=0.2,
        params={
            "rainfall_trajectory": [250, 180, 100, 40],
            "storm_surge_height": 3.5,
            "embankment_failure": True,
            "drainage_blockage": 0.9,
            "road_failure": ["road_1", "road_2", "road_3", "road_4", "road_5",
                             "road_6", "road_9", "road_10"],
            "power_restoration_hours": 24,
            "shelter_inflow": 3000,
            "hospital_demand": 200,
            "communication_availability": 0.30,
            "description": "Severe flooding. Embankment breach. 8 roads impassable. Cascading power/comm failures. Hospital overload.",
        },
    ),
]


def seed_scenarios(db: Session) -> int:
    """Create 3 scenarios (best/expected/worst) with probabilities summing to 1.0."""
    ts = now_ms()
    for sc in _SCENARIOS:
        db.add(Scenario(
            id=seed_id(f"scenario:{sc.label.value}"),
            org_id=ORG_ID,
            incident_id=INCIDENT_ID,
            label=sc.label,
            probability=sc.probability,
            params=sc.params,
            result_geojson=None,
            status=ScenarioStatus.queued,
            created_at=ts,
            completed_at=None,
        ))
    db.commit()
    return len(_SCENARIOS)
