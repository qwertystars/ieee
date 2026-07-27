"""Expected Value of Information (EVI) computer for sensing actions (T30).

EVI(y) = E_y[max_A U(A|y)] - max_A U(A) - Cost(y)

  - E_y[max_A U(A|y)] = Sum_y P(y) * max_A U(A|y)   (expected best utility with info)
  - max_A U(A)         = max_A Sum_y P(y) * U(A|y)   (best utility without info)
  - Cost(y)            = sensing action cost in utility units

If EVI > 0, gathering the observation is expected to improve the decision.
If EVI ~ 0, the observation does not change the decision.

Candidate sensing actions: ask responder, task drone, request citizen photo,
call shelter, poll river sensor, request satellite, deploy LoRa relay, query
traffic-probe, contact hospital, ask utility, move UAV.
"""

from __future__ import annotations

from app.sensing.evi_types import (
    EVIResult,
    OperationalDisplay,
    PlanImpact,
    PlanOutcome,
    SensingAction,
    SensingActionType,
    Uncertainty,
)

# Default cost catalog per action type (utility units, ~person-equivalents).
# Folds together time, resource, and risk into a single scalar.
_DEFAULT_COSTS: dict[SensingActionType, float] = {
    SensingActionType.ASK_RESPONDER: 0.5,
    SensingActionType.TASK_DRONE: 2.0,
    SensingActionType.REQUEST_CITIZEN_PHOTO: 0.3,
    SensingActionType.CALL_SHELTER: 0.2,
    SensingActionType.POLL_RIVER_SENSOR: 0.1,
    SensingActionType.REQUEST_SATELLITE: 5.0,
    SensingActionType.DEPLOY_LORA_RELAY: 3.0,
    SensingActionType.QUERY_TRAFFIC_PROBE: 0.4,
    SensingActionType.CONTACT_HOSPITAL: 0.5,
    SensingActionType.ASK_UTILITY: 0.5,
    SensingActionType.MOVE_UAV: 2.5,
    SensingActionType.DEPLOY_RESCUE_BALL: 3.0,
}

# Default time to complete each action type (minutes).
_DEFAULT_TIMES: dict[SensingActionType, float] = {
    SensingActionType.ASK_RESPONDER: 2.0,
    SensingActionType.TASK_DRONE: 10.0,
    SensingActionType.REQUEST_CITIZEN_PHOTO: 5.0,
    SensingActionType.CALL_SHELTER: 3.0,
    SensingActionType.POLL_RIVER_SENSOR: 1.0,
    SensingActionType.REQUEST_SATELLITE: 60.0,
    SensingActionType.DEPLOY_LORA_RELAY: 30.0,
    SensingActionType.QUERY_TRAFFIC_PROBE: 2.0,
    SensingActionType.CONTACT_HOSPITAL: 5.0,
    SensingActionType.ASK_UTILITY: 5.0,
    SensingActionType.MOVE_UAV: 8.0,
    SensingActionType.DEPLOY_RESCUE_BALL: 15.0,
}

# Word forms for small minute counts in operational display.
_TIME_WORDS: dict[int, str] = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    15: "fifteen", 20: "twenty", 30: "thirty", 60: "sixty",
}


def make_sensing_action(
    action_id: str,
    action_type: SensingActionType,
    target: str,
    description: str,
    cost: float | None = None,
    time_minutes: float | None = None,
) -> SensingAction:
    """Create a sensing action with defaults from the cost/time catalog."""
    return SensingAction(
        id=action_id,
        action_type=action_type,
        target=target,
        cost=cost if cost is not None else _DEFAULT_COSTS[action_type],
        time_minutes=(
            time_minutes if time_minutes is not None else _DEFAULT_TIMES[action_type]
        ),
        description=description,
    )


class EVIComputer:
    """Expected Value of Information computer for sensing actions.

    Computes EVI(y) = E_y[max_A U(A|y)] - max_A U(A) - Cost(y) for each
    candidate sensing action and ranks them by EVI.
    """

    def compute_evi(
        self,
        sensing_action: SensingAction,
        plan_a: PlanOutcome,
        plan_b: PlanOutcome,
        uncertainty: Uncertainty,
    ) -> EVIResult:
        """Compute EVI for a single sensing action.

        Args:
            sensing_action: The sensing action with cost.
            plan_a: First plan's utility under each observation outcome.
            plan_b: Second plan's utility under each observation outcome.
            uncertainty: Probability distribution over observation outcomes.

        Returns:
            EVIResult with EVI, expected value with info, and per-outcome
            decision changes.
        """
        plans = (plan_a, plan_b)

        # max_A U(A) = max_A E_y[U(A|y)] = max_A Sum_y P(y) * U(A|y)
        best_plan_without = max(
            plans, key=lambda p: self._expected_utility(p, uncertainty)
        )
        best_utility_without = self._expected_utility(best_plan_without, uncertainty)

        # E_y[max_A U(A|y)] = Sum_y P(y) * max_A U(A|y)
        expected_value_with_info = 0.0
        decision_changes: dict[str, tuple[str, float]] = {}
        for outcome, prob in uncertainty.probabilities.items():
            best_for_outcome = max(
                plans, key=lambda p: p.outcomes.get(outcome, 0.0)
            )
            best_util = best_for_outcome.outcomes.get(outcome, 0.0)
            expected_value_with_info += prob * best_util
            decision_changes[outcome] = (best_for_outcome.plan_id, best_util)

        evi = expected_value_with_info - best_utility_without - sensing_action.cost

        return EVIResult(
            action_id=sensing_action.id,
            evi=evi,
            expected_value_with_info=expected_value_with_info,
            best_plan_without_info=best_plan_without.plan_id,
            best_plan_utility_without_info=best_utility_without,
            decision_changes=decision_changes,
            cost=sensing_action.cost,
        )

    def evaluate_sensing_actions(
        self,
        actions: tuple[SensingAction, ...],
        current_plan: PlanOutcome,
        alternatives: tuple[PlanOutcome, ...],
        uncertainty: Uncertainty,
    ) -> tuple[EVIResult, ...]:
        """Evaluate and rank sensing actions by EVI (descending).

        For each action, computes EVI against each alternative plan and
        keeps the best (max EVI) result. This identifies the highest-value
        plan switch each sensing action could enable.

        Args:
            actions: Candidate sensing actions.
            current_plan: The current plan's utility under each outcome.
            alternatives: Alternative plans' utilities.
            uncertainty: Probability distribution over observation outcomes.

        Returns:
            Tuple of EVIResults sorted by EVI descending.
        """
        results: list[EVIResult] = []
        for action in actions:
            best_result: EVIResult | None = None
            for alt in alternatives:
                result = self.compute_evi(action, current_plan, alt, uncertainty)
                if best_result is None or result.evi > best_result.evi:
                    best_result = result
            if best_result is not None:
                results.append(best_result)

        results.sort(key=lambda r: r.evi, reverse=True)
        return tuple(results)

    def generate_operational_display(
        self,
        action: SensingAction,
        evi: EVIResult,
        impact: PlanImpact,
    ) -> OperationalDisplay:
        """Generate human-readable operational display text.

        Example output:
            "Verify Bridge 4 within eight minutes. Confirmation would change
             the assignment of two rescue boats and potentially improve
             expected rescue coverage by 18 people."
        """
        time_str = self._format_time(impact.time_constraint_minutes)
        text = (
            f"{action.description} within {time_str}. "
            f"Confirmation would change the assignment of "
            f"{impact.resources_changed} and potentially improve expected "
            f"rescue coverage by {impact.people_improved} people."
        )
        return OperationalDisplay(
            action_id=action.id,
            text=text,
            evi=evi.evi,
        )

    @staticmethod
    def _expected_utility(plan: PlanOutcome, uncertainty: Uncertainty) -> float:
        """E_y[U(A|y)] = Sum_y P(y) * U(A|y)."""
        return sum(
            prob * plan.outcomes.get(outcome, 0.0)
            for outcome, prob in uncertainty.probabilities.items()
        )

    @staticmethod
    def _format_time(minutes: float) -> str:
        """Format minutes as a human-readable time phrase."""
        mins = int(round(minutes))
        word = _TIME_WORDS.get(mins, str(mins))
        return f"{word} minutes"


__all__ = ["EVIComputer", "make_sensing_action"]
