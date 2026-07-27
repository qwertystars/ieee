"""Dataclasses for Expected Value of Information (EVI) computation (T30).

EVI(y) = E_y[max_A U(A|y)] - max_A U(A) - Cost(y)

If EVI > 0, gathering the observation is expected to improve the decision.
If EVI ~ 0, the observation does not change the decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SensingActionType(str, Enum):
    """Catalog of candidate sensing actions for disaster response."""

    ASK_RESPONDER = "ask_responder"
    TASK_DRONE = "task_drone"
    REQUEST_CITIZEN_PHOTO = "request_citizen_photo"
    CALL_SHELTER = "call_shelter"
    POLL_RIVER_SENSOR = "poll_river_sensor"
    REQUEST_SATELLITE = "request_satellite"
    DEPLOY_LORA_RELAY = "deploy_lora_relay"
    QUERY_TRAFFIC_PROBE = "query_traffic_probe"
    CONTACT_HOSPITAL = "contact_hospital"
    ASK_UTILITY = "ask_utility"
    MOVE_UAV = "move_uav"
    DEPLOY_RESCUE_BALL = "deploy_rescue_ball"


@dataclass(frozen=True, slots=True)
class SensingAction:
    """A candidate sensing action with cost and timing.

    ``cost`` is in utility units (e.g. person-equivalents) so it can be
    subtracted directly from the EVI. It folds together time, resource,
    and risk costs into a single scalar. ``time_minutes`` is the wall-clock
    time to complete the action, used for operational display.
    """

    id: str
    action_type: SensingActionType
    target: str
    cost: float
    time_minutes: float
    description: str


@dataclass(frozen=True, slots=True)
class PlanOutcome:
    """Utility of a plan under each possible observation outcome.

    ``outcomes`` maps observation value to utility. For binary uncertainty
    over bridge passability: ``{"passable": 60.0, "impassable": 0.0}``.
    """

    plan_id: str
    outcomes: dict[str, float]


@dataclass(frozen=True, slots=True)
class Uncertainty:
    """A discrete uncertainty over observation outcomes.

    ``probabilities`` maps outcome value to probability, summing to 1.0.
    """

    id: str
    description: str
    probabilities: dict[str, float]


@dataclass(frozen=True, slots=True)
class EVIResult:
    """Result of EVI computation for a single sensing action.

    ``decision_changes`` maps each observation outcome to the plan that
    would be chosen given that outcome, and its utility. This identifies
    whether the observation actually changes the decision.
    """

    action_id: str
    evi: float
    expected_value_with_info: float
    best_plan_without_info: str
    best_plan_utility_without_info: float
    decision_changes: dict[str, tuple[str, float]]
    cost: float


@dataclass(frozen=True, slots=True)
class PlanImpact:
    """Operational impact of acting on the sensing result.

    Used by ``generate_operational_display`` to produce human-readable text.
    ``resources_changed`` describes what gets reassigned (e.g. "two rescue
    boats"). ``people_improved`` is the best-case utility gain from
    switching plans. ``time_constraint_minutes`` is the deadline.
    """

    resources_changed: str
    people_improved: int
    time_constraint_minutes: float


@dataclass(frozen=True, slots=True)
class OperationalDisplay:
    """Human-readable operational display for a sensing recommendation."""

    action_id: str
    text: str
    evi: float


__all__ = [
    "SensingActionType",
    "SensingAction",
    "PlanOutcome",
    "Uncertainty",
    "EVIResult",
    "PlanImpact",
    "OperationalDisplay",
]
