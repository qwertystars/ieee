"""Sensing action catalog with EVI ranking and operational display (T31).

Catalog of candidate sensing actions for disaster response, each with
multi-dimensional cost (time, resource, risk), expected information gain,
and potential impact on the response plan. The catalog ranks actions by
expected information gain (EVI) and generates operational display text
for human operators.

Sensing actions must NOT be dispatched autonomously — ``dispatch_action``
creates a task row in ``pending`` status, requiring human approval before
any resource-consuming action is executed.

SOTA spec §9.3 action types: ask_responder, task_drone, request_citizen_photo,
call_shelter, poll_river_sensor, request_satellite, deploy_lora_relay,
query_traffic_probe, contact_hospital, ask_utility, move_uav.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.entities import OperationalTask
from app.sensing.catalog_types import (
    ActionCost,
    ActionRecommendation,
    CatalogAction,
    DispatchResult,
    RiskLevel,
)
from app.sensing.evi_types import SensingActionType

# Word forms for small minute counts in operational display.
_TIME_WORDS: dict[int, str] = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    15: "fifteen", 20: "twenty", 30: "thirty", 60: "sixty",
}

# Catalog of 11 sensing actions (SOTA spec §9.3).
# expected_information_gain is the typical EVI for this action type.
_ACTIONS: tuple[CatalogAction, ...] = (
    CatalogAction(
        id="ask_responder",
        action_type=SensingActionType.ASK_RESPONDER,
        description="Ask field responder for ground truth",
        target="responder",
        cost=ActionCost(time_minutes=2.0, resource="radio_call", risk_level=RiskLevel.LOW),
        expected_information_gain=0.60,
        potential_impact_on_plan="confirm ground conditions at the responder location and adjust task assignments",
    ),
    CatalogAction(
        id="task_drone",
        action_type=SensingActionType.TASK_DRONE,
        description="Task drone for aerial reconnaissance",
        target="drone",
        cost=ActionCost(time_minutes=10.0, resource="uav_unit", risk_level=RiskLevel.MEDIUM),
        expected_information_gain=0.85,
        potential_impact_on_plan="verify bridge or road passability and reassign rescue boats accordingly",
    ),
    CatalogAction(
        id="request_citizen_photo",
        action_type=SensingActionType.REQUEST_CITIZEN_PHOTO,
        description="Request citizen photo via app",
        target="citizen_app",
        cost=ActionCost(time_minutes=5.0, resource="app_notification", risk_level=RiskLevel.LOW),
        expected_information_gain=0.40,
        potential_impact_on_plan="corroborate hazard reports and refine the flood extent map",
    ),
    CatalogAction(
        id="call_shelter",
        action_type=SensingActionType.CALL_SHELTER,
        description="Call shelter for status update",
        target="shelter",
        cost=ActionCost(time_minutes=3.0, resource="phone_call", risk_level=RiskLevel.LOW),
        expected_information_gain=0.30,
        potential_impact_on_plan="confirm shelter capacity and redirect overflow evacuees",
    ),
    CatalogAction(
        id="poll_river_sensor",
        action_type=SensingActionType.POLL_RIVER_SENSOR,
        description="Poll river gauge sensor",
        target="river_sensor",
        cost=ActionCost(time_minutes=1.0, resource="iot_query", risk_level=RiskLevel.LOW),
        expected_information_gain=0.70,
        potential_impact_on_plan="verify river level and update flood evacuation trigger thresholds",
    ),
    CatalogAction(
        id="request_satellite",
        action_type=SensingActionType.REQUEST_SATELLITE,
        description="Request satellite imagery",
        target="satellite",
        cost=ActionCost(time_minutes=60.0, resource="satellite_tasking", risk_level=RiskLevel.HIGH),
        expected_information_gain=0.90,
        potential_impact_on_plan="obtain wide-area damage assessment and reprioritize all response sectors",
    ),
    CatalogAction(
        id="deploy_lora_relay",
        action_type=SensingActionType.DEPLOY_LORA_RELAY,
        description="Deploy LoRa relay for communications",
        target="lora_relay",
        cost=ActionCost(time_minutes=30.0, resource="field_team", risk_level=RiskLevel.HIGH),
        expected_information_gain=0.50,
        potential_impact_on_plan="restore communications in isolated zones and re-enable telemetry",
    ),
    CatalogAction(
        id="query_traffic_probe",
        action_type=SensingActionType.QUERY_TRAFFIC_PROBE,
        description="Query traffic probe data",
        target="traffic_probe",
        cost=ActionCost(time_minutes=2.0, resource="api_query", risk_level=RiskLevel.LOW),
        expected_information_gain=0.35,
        potential_impact_on_plan="verify road passability and reroute evacuation corridors",
    ),
    CatalogAction(
        id="contact_hospital",
        action_type=SensingActionType.CONTACT_HOSPITAL,
        description="Contact hospital for capacity",
        target="hospital",
        cost=ActionCost(time_minutes=5.0, resource="phone_call", risk_level=RiskLevel.LOW),
        expected_information_gain=0.50,
        potential_impact_on_plan="confirm hospital capacity and update patient diversion plan",
    ),
    CatalogAction(
        id="ask_utility",
        action_type=SensingActionType.ASK_UTILITY,
        description="Ask utility company for grid status",
        target="utility",
        cost=ActionCost(time_minutes=5.0, resource="phone_call", risk_level=RiskLevel.LOW),
        expected_information_gain=0.45,
        potential_impact_on_plan="verify power grid status and predict infrastructure cascade impact",
    ),
    CatalogAction(
        id="move_uav",
        action_type=SensingActionType.MOVE_UAV,
        description="Move UAV to new observation position",
        target="uav",
        cost=ActionCost(time_minutes=8.0, resource="uav_unit", risk_level=RiskLevel.MEDIUM),
        expected_information_gain=0.55,
        potential_impact_on_plan="reposition for better observation angle and improve damage assessment coverage",
    ),
    CatalogAction(
        id="deploy_rescue_ball",
        action_type=SensingActionType.DEPLOY_RESCUE_BALL,
        description="Deploy rescue ball device for situational awareness",
        target="rescue_ball",
        cost=ActionCost(time_minutes=15.0, resource="rescue_ball_unit", risk_level=RiskLevel.MEDIUM),
        expected_information_gain=0.65,
        potential_impact_on_plan="deploy a self-contained sensing sphere into flooded areas for thermal, acoustic, and IMU reconnaissance",
    ),
)

_ACTIONS_BY_ID: dict[str, CatalogAction] = {a.id: a for a in _ACTIONS}

# Priority mapping from risk level to task priority.
_RISK_PRIORITY: dict[RiskLevel, str] = {
    RiskLevel.LOW: "low",
    RiskLevel.MEDIUM: "medium",
    RiskLevel.HIGH: "high",
}


class SensingActionCatalog:
    """Catalog of sensing actions with EVI ranking and dispatch.

    Provides the static catalog of candidate sensing actions, ranks them by
    expected information gain (EVI), generates operational display text, and
    dispatches actions as ``pending`` tasks requiring human approval.
    """

    def get_actions(self) -> list[CatalogAction]:
        """Return all sensing actions in the catalog."""
        return list(_ACTIONS)

    def get_action(self, action_id: str) -> CatalogAction | None:
        """Return a single sensing action by ID, or None if not found."""
        return _ACTIONS_BY_ID.get(action_id)

    def get_top_actions(
        self,
        incident_id: str,
        n: int = 3,
    ) -> list[ActionRecommendation]:
        """Return top-N sensing actions by expected information gain.

        Each action includes operational display text for human operators.
        Ranking is by ``expected_information_gain`` descending — the typical
        EVI for each action type.
        """
        ranked = sorted(
            _ACTIONS,
            key=lambda a: a.expected_information_gain,
            reverse=True,
        )
        return [
            ActionRecommendation(
                action=action,
                display_text=self._format_display(action),
            )
            for action in ranked[:n]
        ]

    def dispatch_action(
        self,
        incident_id: str,
        action_id: str,
        db: Session,
        org_id: str = "system",
    ) -> DispatchResult:
        """Create a task row for a sensing action — pending human approval.

        Sensing actions must NOT be dispatched autonomously. This method
        creates an ``OperationalTask`` row with ``status="pending"``,
        requiring a human operator to approve before execution.

        Raises ``ValueError`` if ``action_id`` is not in the catalog.
        """
        action = _ACTIONS_BY_ID.get(action_id)
        if action is None:
            raise ValueError(f"Unknown sensing action: {action_id}")

        task_id = generate_ulid()
        now = now_ms()
        task = OperationalTask(
            id=task_id,
            org_id=org_id,
            incident_id=incident_id,
            created_at=now,
            updated_at=now,
            title=f"Sensing: {action.description}",
            status="pending",
            priority=_RISK_PRIORITY[action.cost.risk_level],
            properties={
                "action_id": action.id,
                "action_type": action.action_type.value,
                "sensing": True,
                "requires_approval": True,
                "target": action.target,
            },
        )
        db.add(task)
        db.commit()
        return DispatchResult(
            task_id=task_id,
            action_id=action_id,
            incident_id=incident_id,
            status="pending",
        )

    @staticmethod
    def _format_display(action: CatalogAction) -> str:
        """Generate operational display text for a sensing action.

        Example: "Recommended information request: Task drone for aerial
        reconnaissance within ten minutes. Confirmation would verify bridge
        or road passability and reassign rescue boats accordingly."
        """
        mins = round(action.cost.time_minutes)
        time_word = _TIME_WORDS.get(mins, str(mins))
        return (
            f"Recommended information request: {action.description} "
            f"within {time_word} minutes. Confirmation would "
            f"{action.potential_impact_on_plan}."
        )


__all__ = ["SensingActionCatalog"]
