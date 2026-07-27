"""Tests for the CVaR risk-aware optimizer (T26).

Test cases:
  1. test_feasible_with_constraints — 3 zones, 4 responders, 3 scenarios → feasible
  2. test_infeasible — shelter over-capacity → INFEASIBLE
  3. test_skill_gate — unqualified responder rejected
  4. test_vehicle_road_incompatibility — boat-only zone, non-boat rejected
  5. test_fairness_minimum — vulnerable zone gets >= C_min coverage
  6. test_solve_time — solve time < 30s

Verification command:
    docker compose run --rm -e PYTHONPATH=/app backend sh -c \
        "pip install pytest -q && python -m pytest tests/test_optimizer.py -q"
"""

from __future__ import annotations

from app.optimizer.engine import EmergencyResponseOptimizer
from app.optimizer.optimizer_types import (
    OptimizerInput,
    Responder,
    RoadArc,
    ScenarioLoss,
    Shelter,
    Task,
    Zone,
)

# ─── Fixtures ───────────────────────────────────────────────────────────────


def _standard_zones() -> tuple[Zone, ...]:
    """3 zones: z0 vulnerable (c_min=1), z1 normal, z2 boat-only."""
    return (
        Zone(id="z0", demand=1, vulnerable=True, c_min=1),
        Zone(id="z1", demand=1, vulnerable=False),
        Zone(id="z2", demand=1, vulnerable=False),
    )


def _standard_responders() -> tuple[Responder, ...]:
    """4 responders with varied skills and vehicles."""
    return (
        Responder(id="r0", skills=frozenset({"medical", "search"}), vehicle_class="ambulance"),
        Responder(id="r1", skills=frozenset({"medical"}), vehicle_class="ambulance"),
        Responder(id="r2", skills=frozenset({"search", "evacuation"}), vehicle_class="boat"),
        Responder(id="r3", skills=frozenset({"evacuation"}), vehicle_class="high_clearance"),
    )


def _standard_tasks() -> tuple[Task, ...]:
    """3 tasks: t0 medical at z0, t1 search at z1, t2 evacuation at z2."""
    return (
        Task(id="t0", zone_id="z0", required_skill="medical", duration=3600, harm_if_unserved=100.0),
        Task(id="t1", zone_id="z1", required_skill="search", duration=3600, harm_if_unserved=50.0),
        Task(id="t2", zone_id="z2", required_skill="evacuation", duration=3600, harm_if_unserved=75.0),
    )


def _standard_scenarios() -> tuple[ScenarioLoss, ...]:
    """3 scenarios: p=[0.3, 0.4, 0.3], varied harm multipliers."""
    return (
        ScenarioLoss(probability=0.3, harm_multiplier=1.0),
        ScenarioLoss(probability=0.4, harm_multiplier=1.5),
        ScenarioLoss(probability=0.3, harm_multiplier=0.8),
    )


def _standard_roads() -> tuple[RoadArc, ...]:
    """Road arcs: depot(0)→z0(1), depot→z1(2), depot→z2(3) boat-only."""
    return (
        RoadArc(from_node=0, to_node=1, vehicle_classes=frozenset({"ambulance", "boat", "high_clearance"})),
        RoadArc(from_node=0, to_node=2, vehicle_classes=frozenset({"ambulance", "boat", "high_clearance"})),
        RoadArc(from_node=0, to_node=3, vehicle_classes=frozenset({"boat"})),
    )


def _standard_shelter() -> tuple[Shelter, ...]:
    """Shelter at z2 with capacity 10."""
    return (Shelter(id="z2", capacity=10, initial_occupancy=0),)


def _standard_input() -> OptimizerInput:
    return OptimizerInput(
        zones=_standard_zones(),
        responders=_standard_responders(),
        tasks=_standard_tasks(),
        scenarios=_standard_scenarios(),
        road_arcs=_standard_roads(),
        shelters=_standard_shelter(),
        alpha=0.95,
        lambda_risk=1.0,
        max_solve_seconds=30.0,
    )


# ─── Tests ──────────────────────────────────────────────────────────────────


def test_feasible_with_constraints() -> None:
    """3 zones, 4 responders, 3 scenarios → feasible assignment with objective, CVaR, harm."""
    opt = EmergencyResponseOptimizer(_standard_input())
    result = opt.solve()

    assert result.status in ("optimal", "feasible"), f"expected feasible, got {result.status}"
    assert len(result.assignments) > 0, "should have at least one assignment"
    assert result.objective_value < float("inf"), "objective should be finite"
    assert result.expected_harm >= 0.0, "expected harm should be non-negative"
    assert result.cvar >= 0.0, "CVaR should be non-negative"
    assert result.operational_cost >= 0.0, "operational cost should be non-negative"

    # Verify each assignment has valid responder_id and task_id
    responder_ids = {r.id for r in _standard_responders()}
    task_ids = {t.id for t in _standard_tasks()}
    for a in result.assignments:
        assert a.responder_id in responder_ids, f"unknown responder {a.responder_id}"
        assert a.task_id in task_ids, f"unknown task {a.task_id}"


def test_infeasible() -> None:
    """Shelter over-capacity (capacity=0) + forced assignment → INFEASIBLE."""
    zones = (
        Zone(id="z0", demand=1, vulnerable=False),
        Zone(id="z1", demand=1, vulnerable=False),
        Zone(id="z2", demand=1, vulnerable=True, c_min=1),  # force assignment at z2
    )
    shelters = (Shelter(id="z2", capacity=0, initial_occupancy=0),)  # no capacity
    inp = OptimizerInput(
        zones=zones,
        responders=_standard_responders(),
        tasks=_standard_tasks(),
        scenarios=_standard_scenarios(),
        road_arcs=_standard_roads(),
        shelters=shelters,
        alpha=0.95,
        lambda_risk=1.0,
        max_solve_seconds=30.0,
    )
    opt = EmergencyResponseOptimizer(inp)
    result = opt.solve()

    assert result.status == "infeasible", (
        f"expected infeasible (shelter cap=0 + fairness forces assignment), got {result.status}"
    )


def test_skill_gate() -> None:
    """Unqualified responder rejected — r1 (medical only) can't do t1 (search)."""
    opt = EmergencyResponseOptimizer(_standard_input())
    result = opt.solve()

    assert result.status in ("optimal", "feasible"), f"expected feasible, got {result.status}"

    # r1 has skills={medical} only — must NOT be assigned to t1 (search) or t2 (evacuation)
    r1_assignments = [a for a in result.assignments if a.responder_id == "r1"]
    for a in r1_assignments:
        assert a.task_id == "t0", (
            f"r1 (medical only) assigned to {a.task_id}, expected t0 (medical) only"
        )

    # Verify no responder is assigned to a task they lack skills for
    responder_map = {r.id: r for r in _standard_responders()}
    task_map = {t.id: t for t in _standard_tasks()}
    for a in result.assignments:
        resp = responder_map[a.responder_id]
        task = task_map[a.task_id]
        assert task.required_skill in resp.skills, (
            f"{resp.id} (skills={resp.skills}) assigned to {task.id} "
            f"(requires {task.required_skill})"
        )


def test_vehicle_road_incompatibility() -> None:
    """Boat-only zone (z2) — non-boat responders can't be assigned there."""
    opt = EmergencyResponseOptimizer(_standard_input())
    result = opt.solve()

    assert result.status in ("optimal", "feasible"), f"expected feasible, got {result.status}"

    # z2 is only reachable by boat (road arc to_node=3 has vehicle_classes={boat})
    # r0, r1 (ambulance), r3 (high_clearance) must NOT be assigned to t2 (at z2)
    responder_map = {r.id: r for r in _standard_responders()}
    for a in result.assignments:
        if a.task_id == "t2":
            resp = responder_map[a.responder_id]
            assert resp.vehicle_class == "boat", (
                f"{resp.id} (vehicle={resp.vehicle_class}) assigned to t2 at z2 "
                f"(boat-only zone) — only boat responders allowed"
            )


def test_fairness_minimum() -> None:
    """Vulnerable zone z0 gets >= C_min (1) coverage."""
    opt = EmergencyResponseOptimizer(_standard_input())
    result = opt.solve()

    assert result.status in ("optimal", "feasible"), f"expected feasible, got {result.status}"
    assert result.coverage.get("z0", 0) >= 1, (
        f"vulnerable zone z0 coverage={result.coverage.get('z0', 0)}, expected >= 1"
    )


def test_solve_time() -> None:
    """Solve time < 30 seconds for the standard 3-zone, 4-responder instance."""
    opt = EmergencyResponseOptimizer(_standard_input())
    result = opt.solve()

    assert result.solve_time_seconds < 30.0, (
        f"solve time {result.solve_time_seconds:.2f}s exceeds 30s limit"
    )
