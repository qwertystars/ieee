"""Data types for the sensing action catalog (T31).

The catalog stores static metadata about each candidate sensing action:
its cost (time, resource, risk), expected information gain, and potential
impact on the response plan. ``dispatch_action`` creates an
``OperationalTask`` row in ``pending`` status — human approval is required
before a resource-consuming action is executed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.sensing.evi_types import SensingActionType


class RiskLevel(str, Enum):
    """Risk classification for a sensing action."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class ActionCost:
    """Multi-dimensional cost of a sensing action.

    ``time_minutes`` is wall-clock time to complete. ``resource`` names the
    resource consumed (e.g. "uav_unit", "phone_call"). ``risk_level`` is the
    operational risk to personnel or equipment.
    """

    time_minutes: float
    resource: str
    risk_level: RiskLevel


@dataclass(frozen=True, slots=True)
class CatalogAction:
    """A sensing action in the catalog with full metadata.

    ``expected_information_gain`` is the typical EVI for this action type —
    the expected reduction in decision uncertainty from gathering the
    observation. ``potential_impact_on_plan`` is a human-readable description
    of how the observation could change the response plan.
    """

    id: str
    action_type: SensingActionType
    description: str
    target: str
    cost: ActionCost
    expected_information_gain: float
    potential_impact_on_plan: str


@dataclass(frozen=True, slots=True)
class ActionRecommendation:
    """A top-N sensing action with operational display text."""

    action: CatalogAction
    display_text: str


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Result of dispatching a sensing action — always pending human approval.

    ``status`` is ``"pending"`` because sensing actions must NOT be
    dispatched autonomously. A human operator must approve the task before
    any resource-consuming action is executed.
    """

    task_id: str
    action_id: str
    incident_id: str
    status: str


__all__ = [
    "ActionCost",
    "ActionRecommendation",
    "CatalogAction",
    "DispatchResult",
    "RiskLevel",
]
