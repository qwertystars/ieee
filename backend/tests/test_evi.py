"""Tests for the Expected Value of Information computer (T30).

Test cases:
  1. test_bridge_verification_evi — bridge 45% P(impassable), EVI > 0
  2. test_clear_alternative_evi — road with clear alternative, EVI ~ 0
  3. test_operational_display — human-readable text generated
  4. test_sensing_actions_ranked — actions ranked by EVI descending
  5. test_cost_subtracted_from_evi — higher cost reduces EVI proportionally

Verification command:
    docker compose run --rm -e PYTHONPATH=/app backend sh -c \
        "pip install pytest -q && python -m pytest tests/test_evi.py -q"
"""

from __future__ import annotations

import pytest

from app.sensing.evi import EVIComputer, make_sensing_action
from app.sensing.evi_types import (
    PlanImpact,
    PlanOutcome,
    SensingAction,
    SensingActionType,
    Uncertainty,
)

# ─── Fixtures ───────────────────────────────────────────────────────────────


def _bridge_uncertainty() -> Uncertainty:
    """Bridge with 45% P(impassable), 55% P(passable)."""
    return Uncertainty(
        id="bridge_4_status",
        description="Bridge 4 passability under flood conditions",
        probabilities={"passable": 0.55, "impassable": 0.45},
    )


def _plan_a_use_bridge() -> PlanOutcome:
    """Plan A: use bridge — 60 people if passable, 0 if impassable."""
    return PlanOutcome(
        plan_id="plan_a_use_bridge",
        outcomes={"passable": 60.0, "impassable": 0.0},
    )


def _plan_b_avoid_bridge() -> PlanOutcome:
    """Plan B: avoid bridge — 42 people regardless of bridge status."""
    return PlanOutcome(
        plan_id="plan_b_avoid_bridge",
        outcomes={"passable": 42.0, "impassable": 42.0},
    )


def _verify_bridge_action(cost: float = 0.5) -> SensingAction:
    """Sensing action: verify Bridge 4 via drone."""
    return make_sensing_action(
        action_id="verify_bridge_4",
        action_type=SensingActionType.TASK_DRONE,
        target="bridge_4",
        description="Verify Bridge 4",
        cost=cost,
        time_minutes=8.0,
    )


# ─── Tests ──────────────────────────────────────────────────────────────────


def test_bridge_verification_evi() -> None:
    """Bridge 45% P(impassable): EVI(verify_bridge) > 0 because resolving
    uncertainty changes the plan (Plan B without info, Plan A if passable).

    Without info: E[U(A)] = 0.55*60 + 0.45*0 = 33; E[U(B)] = 42 -> choose B.
    With info: 0.55*max(60,42) + 0.45*max(0,42) = 0.55*60 + 0.45*42 = 51.9.
    EVI = 51.9 - 42 - 0 = 9.9 > 0.
    """
    computer = EVIComputer()
    action = _verify_bridge_action(cost=0.0)
    result = computer.compute_evi(
        action, _plan_a_use_bridge(), _plan_b_avoid_bridge(), _bridge_uncertainty()
    )

    assert result.evi > 0, f"EVI should be positive, got {result.evi}"
    assert result.evi == pytest.approx(9.9, abs=1e-9)
    assert result.best_plan_without_info == "plan_b_avoid_bridge"
    assert result.best_plan_utility_without_info == pytest.approx(42.0)
    assert result.expected_value_with_info == pytest.approx(51.9)

    # Decision changes: passable -> plan_a, impassable -> plan_b
    assert result.decision_changes["passable"] == ("plan_a_use_bridge", 60.0)
    assert result.decision_changes["impassable"] == ("plan_b_avoid_bridge", 42.0)


def test_clear_alternative_evi() -> None:
    """Road check with clear alternative: EVI ~ 0 because observation
    doesn't change the decision (both plans yield same utility regardless).
    """
    computer = EVIComputer()
    action = make_sensing_action(
        action_id="check_road_5",
        action_type=SensingActionType.QUERY_TRAFFIC_PROBE,
        target="road_5",
        description="Check Road 5",
        cost=0.0,
        time_minutes=2.0,
    )
    uncertainty = Uncertainty(
        id="road_5_status",
        description="Road 5 passability",
        probabilities={"passable": 0.5, "impassable": 0.5},
    )
    # Both plans yield 60 people regardless of road status
    plan_a = PlanOutcome("plan_a_use_road", {"passable": 60.0, "impassable": 60.0})
    plan_b = PlanOutcome("plan_b_avoid_road", {"passable": 60.0, "impassable": 60.0})

    result = computer.compute_evi(action, plan_a, plan_b, uncertainty)

    # EVI = 60 - 60 - 0 = 0
    assert result.evi == pytest.approx(0.0, abs=1e-9)
    assert result.expected_value_with_info == pytest.approx(60.0)
    assert result.best_plan_utility_without_info == pytest.approx(60.0)


def test_operational_display() -> None:
    """Operational display text is generated with action, resources, and impact."""
    computer = EVIComputer()
    action = _verify_bridge_action()
    result = computer.compute_evi(
        action, _plan_a_use_bridge(), _plan_b_avoid_bridge(), _bridge_uncertainty()
    )
    impact = PlanImpact(
        resources_changed="two rescue boats",
        people_improved=18,
        time_constraint_minutes=8.0,
    )
    display = computer.generate_operational_display(action, result, impact)

    assert display.action_id == "verify_bridge_4"
    assert "Verify Bridge 4" in display.text
    assert "eight minutes" in display.text
    assert "two rescue boats" in display.text
    assert "18 people" in display.text
    assert display.evi == result.evi


def test_sensing_actions_ranked() -> None:
    """Multiple sensing actions are ranked by EVI descending."""
    computer = EVIComputer()
    uncertainty = _bridge_uncertainty()
    current_plan = _plan_b_avoid_bridge()
    alternatives = (_plan_a_use_bridge(),)

    # Low-cost drone verification
    drone = make_sensing_action(
        action_id="drone_verify",
        action_type=SensingActionType.TASK_DRONE,
        target="bridge_4",
        description="Drone verify Bridge 4",
        cost=0.5,
    )
    # High-cost satellite acquisition (same uncertainty resolved)
    satellite = make_sensing_action(
        action_id="satellite_check",
        action_type=SensingActionType.REQUEST_SATELLITE,
        target="bridge_4",
        description="Satellite check Bridge 4",
        cost=5.0,
    )

    results = computer.evaluate_sensing_actions(
        (drone, satellite), current_plan, alternatives, uncertainty
    )

    assert len(results) == 2
    # Drone has lower cost -> higher EVI, ranked first
    assert results[0].action_id == "drone_verify"
    assert results[1].action_id == "satellite_check"
    assert results[0].evi > results[1].evi
    # Both should have positive EVI (same uncertainty resolved, just different costs)
    assert results[0].evi > 0
    assert results[1].evi > 0


def test_cost_subtracted_from_evi() -> None:
    """Higher cost reduces EVI proportionally — cost is subtracted directly."""
    computer = EVIComputer()
    uncertainty = _bridge_uncertainty()
    plan_a = _plan_a_use_bridge()
    plan_b = _plan_b_avoid_bridge()

    low_cost = _verify_bridge_action(cost=0.0)
    high_cost = _verify_bridge_action(cost=5.0)

    low_result = computer.compute_evi(low_cost, plan_a, plan_b, uncertainty)
    high_result = computer.compute_evi(high_cost, plan_a, plan_b, uncertainty)

    # EVI difference should equal cost difference (5.0)
    assert low_result.evi - high_result.evi == pytest.approx(5.0)
    assert high_result.evi < low_result.evi
    # The expected value with info is the same (cost doesn't affect it)
    assert high_result.expected_value_with_info == low_result.expected_value_with_info
