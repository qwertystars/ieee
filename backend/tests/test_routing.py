"""Tests for the route reliability engine (T28).

Test cases:
  1. test_safety_over_speed — high P(passable) preferred over low P(passable) even if slower
  2. test_k_shortest_paths — returns 3 alternatives
  3. test_responder_risk_flooded — responder risk added to flooded route
  4. test_cost_computation — cost computation correct
  5. test_travel_time_variance — variance from scenarios
  6. test_scenario_failed_segment — scenario with failed segment drops passability

Verification command:
    docker compose run --rm -e PYTHONPATH=/app backend sh -c \
        "pip install pytest -q && python -m pytest tests/test_routing.py -q"
"""

from __future__ import annotations

from app.optimizer.routing import RouteReliabilityEngine
from app.optimizer.routing_types import Route, RouteScenario, RouteSegment

# ─── Helpers ────────────────────────────────────────────────────────────────


def _segment(
    sid: str,
    length_m: float = 100.0,
    speed: float = 20.0,
    flood: float | None = None,
    damage: float | None = None,
    hazard: float = 0.0,
) -> RouteSegment:
    """Build a RouteSegment with sensible defaults."""
    return RouteSegment(
        id=sid,
        length_m=length_m,
        base_speed_mps=speed,
        flood_prob=flood,
        damage_prob=damage,
        hazard_intensity=hazard,
    )


# ─── Tests ──────────────────────────────────────────────────────────────────


def test_safety_over_speed():
    """Route with 0.9 P(passable) preferred over route with 0.3 P(passable) even if slower.

    Route A: 220m at 20 m/s = 11s, flood_prob=0.11 -> P(passable) ~ 0.90
    Route B: 200m at 20 m/s = 10s, flood_prob=0.78 -> P(passable) ~ 0.30

    With default weights (gamma=2.0):
      Cost(A) = 11 + 2*0.10 = 11.20
      Cost(B) = 10 + 2*0.70 = 11.40
    A is selected despite being slower.
    """
    engine = RouteReliabilityEngine(vehicle_class="ambulance")
    route_a = Route(
        id="A",
        segments=(_segment("a1", length_m=220.0, flood=0.11),),
    )
    route_b = Route(
        id="B",
        segments=(_segment("b1", length_m=200.0, flood=0.78),),
    )
    cost_a = engine.compute_cost(route_a)
    cost_b = engine.compute_cost(route_b)
    assert cost_a.passability > 0.85, f"route A passability={cost_a.passability}"
    assert cost_b.passability < 0.35, f"route B passability={cost_b.passability}"
    assert cost_a.total < cost_b.total, (
        f"safe route cost {cost_a.total} should be < unsafe route cost {cost_b.total}"
    )
    selected = engine.select_route((route_a, route_b))
    assert selected.id == "A"


def test_k_shortest_paths():
    """k_shortest_paths returns 3 alternative paths.

    Graph: 0->1->3->4 (weight 3), 0->2->4 (weight 4), 0->1->4 (weight 6).
    """
    engine = RouteReliabilityEngine()
    graph: dict[int, list[tuple[int, float]]] = {
        0: [(1, 1.0), (2, 3.0)],
        1: [(3, 1.0), (4, 5.0)],
        2: [(4, 1.0)],
        3: [(4, 1.0)],
        4: [],
    }
    paths = engine.k_shortest_paths(graph, 0, 4, k=3)
    assert len(paths) == 3, f"expected 3 paths, got {len(paths)}"
    for p in paths:
        assert p[0] == 0
        assert p[-1] == 4
    assert len({tuple(p) for p in paths}) == 3, "paths must be distinct"


def test_responder_risk_flooded():
    """Responder risk added to flooded route.

    Same route, but one with high hazard_intensity should have higher cost.
    """
    seg = _segment("s1", length_m=200.0, speed=20.0)
    route = Route(id="R", segments=(seg,))
    engine_safe = RouteReliabilityEngine(hazard_intensity=0.0)
    engine_flooded = RouteReliabilityEngine(hazard_intensity=0.8)
    cost_safe = engine_safe.compute_cost(route)
    cost_flooded = engine_flooded.compute_cost(route)
    assert cost_flooded.responder_risk > cost_safe.responder_risk
    assert cost_flooded.total > cost_safe.total


def test_cost_computation():
    """Cost = E[T] + eta*Var(T) + gamma*P(failure) + rho*Risk_responders."""
    seg = _segment("s1", length_m=200.0, speed=20.0, flood=0.5)
    route = Route(id="R", segments=(seg,))
    # E[T] = 200/20 = 10s
    # P(passable) = (1 - 0.5*0.9) * (1 - 0*0.5) = 0.55 (ambulance)
    # P(failure) = 0.45, Var(T) = 0 (no scenarios), Risk = 0 (no hazard)
    engine = RouteReliabilityEngine()
    cost = engine.compute_cost(route, eta=0.5, gamma=2.0, rho=1.0)
    assert cost.expected_time == 10.0
    assert cost.variance == 0.0
    assert abs(cost.passability - 0.55) < 1e-6
    assert abs(cost.failure_prob - 0.45) < 1e-6
    assert cost.responder_risk == 0.0
    expected_total = 10.0 + 0.5 * 0.0 + 2.0 * 0.45 + 1.0 * 0.0
    assert abs(cost.total - expected_total) < 1e-6


def test_travel_time_variance():
    """Var(T_r) from scenario ensemble (T23).

    Two scenarios: delay_multiplier=1.0 (p=0.5), delay_multiplier=2.0 (p=0.5).
    Nominal T = 10s. T1=10s, T2=20s. E[T] = 15s, Var = 25.0.
    """
    seg = _segment("s1", length_m=200.0, speed=20.0)
    route = Route(id="R", segments=(seg,))
    scenarios = (
        RouteScenario(scenario_id="s1", probability=0.5, delay_multiplier=1.0),
        RouteScenario(scenario_id="s2", probability=0.5, delay_multiplier=2.0),
    )
    engine = RouteReliabilityEngine(scenarios=scenarios)
    var = engine.compute_travel_time_variance(route, scenarios)
    assert abs(var - 25.0) < 1e-6
    # Cost includes variance: E[T]=10, Var=25, eta=0.5, gamma=0, rho=0
    cost = engine.compute_cost(route, eta=0.5, gamma=0.0, rho=0.0)
    assert abs(cost.total - 22.5) < 1e-6


def test_scenario_failed_segment():
    """A scenario that fails a route segment makes P(passable) drop."""
    seg = _segment("s1", length_m=200.0, speed=20.0, flood=0.0)
    route = Route(id="R", segments=(seg,))
    scenarios = (
        RouteScenario(
            scenario_id="fail",
            probability=0.5,
            failed_segments=frozenset({"s1"}),
        ),
        RouteScenario(scenario_id="ok", probability=0.5),
    )
    engine = RouteReliabilityEngine(scenarios=scenarios)
    p = engine.compute_scenario_passability(route, scenarios)
    # P(passable) = 0.5 * 0 + 0.5 * 1.0 = 0.5
    assert abs(p - 0.5) < 1e-6
