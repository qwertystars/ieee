"""Tests for the stability threshold replanner (T29).

Test cases:
  1. test_stability_threshold — below threshold (1 change) accepted,
     above threshold (6 changes) constrained to fewer changes
  2. test_in_progress_locked — in-progress assignments cannot be changed
  3. test_warm_start — warm-start hints applied, solver produces valid result
  4. test_compute_deviations — deviation computation correct
  5. test_lock_in_progress — lock_in_progress identifies in-progress assignments

Verification command:
    docker compose run --rm -e PYTHONPATH=/app backend sh -c \
        "pip install pytest -q && python -m pytest tests/test_replan.py -q"
"""

from __future__ import annotations

from app.optimizer.engine import EmergencyResponseOptimizer
from app.optimizer.optimizer_types import (
    Assignment,
    OptimizerInput,
    Responder,
    RoadArc,
    ScenarioLoss,
    Task,
    Zone,
)
from app.optimizer.replan import Replanner

# ─── Fixtures ───────────────────────────────────────────────────────────────
# The routing constraint (add_multiple_circuit) requires ALL zones to be
# visited. So #zones must equal #responders, with multiple tasks per zone
# to allow reassignments within a zone (keeping it visited).


def _zones(n: int) -> tuple[Zone, ...]:
    """n zones z0..z(n-1), all non-vulnerable."""
    return tuple(Zone(id=f"z{i}", demand=1) for i in range(n))


def _responders(n: int) -> tuple[Responder, ...]:
    """n responders r0..r(n-1), all with skill 'medical', vehicle 'ambulance'."""
    return tuple(
        Responder(
            id=f"r{i}",
            skills=frozenset({"medical"}),
            vehicle_class="ambulance",
        )
        for i in range(n)
    )


def _tasks_two_per_zone(n_zones: int, harms: list[float]) -> tuple[Task, ...]:
    """2 tasks per zone: t0,t1 at z0; t2,t3 at z1; etc.

    ``harms`` is a flat list of ``2 * n_zones`` values.
    """
    tasks: list[Task] = []
    for z in range(n_zones):
        for i in range(2):
            t_idx = z * 2 + i
            tasks.append(
                Task(
                    id=f"t{t_idx}",
                    zone_id=f"z{z}",
                    required_skill="medical",
                    duration=3600,
                    harm_if_unserved=harms[t_idx],
                )
            )
    return tuple(tasks)


def _roads(n: int) -> tuple[RoadArc, ...]:
    """Road arcs: depot(0)→z(1)..z(n), all ambulance-accessible."""
    return tuple(
        RoadArc(
            from_node=0,
            to_node=i + 1,
            vehicle_classes=frozenset({"ambulance"}),
        )
        for i in range(n)
    )


def _input_two_per_zone(n_responders: int, harms: list[float]) -> OptimizerInput:
    """Build an OptimizerInput with n_responders and 2 tasks per zone.

    n_zones equals n_responders (routing constraint requires all zones
    visited, so we need at least 1 responder per zone).
    """
    n_zones = n_responders
    return OptimizerInput(
        zones=_zones(n_zones),
        responders=_responders(n_responders),
        tasks=_tasks_two_per_zone(n_zones, harms),
        scenarios=(ScenarioLoss(probability=1.0, harm_multiplier=1.0),),
        road_arcs=_roads(n_zones),
        alpha=0.95,
        lambda_risk=1.0,
        max_solve_seconds=30.0,
    )


def _previous_plan_even(n: int) -> tuple[Assignment, ...]:
    """Previous plan: r0→t0, r1→t2, r2→t4, ..., r(n-1)→t(2n-2).

    Each responder is assigned to the first (even-indexed) task at their
    zone, all at start_time=0.
    """
    return tuple(
        Assignment(responder_id=f"r{i}", task_id=f"t{2 * i}", start_time=0)
        for i in range(n)
    )


# ─── Tests ──────────────────────────────────────────────────────────────────


def test_stability_threshold() -> None:
    """Below threshold: 1 change accepted. Above threshold: 6 changes constrained.

    Part 1 — 5 responders, 5 zones, 10 tasks (2 per zone). Only t1 has
    high harm. Unconstrained optimal reassigns r0 from t0→t1 (within z0).
    Deviations: 2 (1 reassignment) ≤ 3 → accepted.

    Part 2 — 5 responders, 5 zones, 10 tasks. t1, t3, t5 have high harm.
    Unconstrained optimal reassigns 3 responders (6 deviations > 3).
    With threshold=3, solver finds plan with ≤ 3 deviations.
    """
    # ── Part 1: below threshold ──
    harms_low = [10.0, 100.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
    inp_low = _input_two_per_zone(5, harms_low)
    prev_low = _previous_plan_even(5)
    replanner_low = Replanner(inp_low)

    result_low = replanner_low.replan(prev_low, inp_low, stability_threshold=3)
    assert result_low.status in ("optimal", "feasible"), (
        f"expected feasible, got {result_low.status}"
    )
    dev_low = replanner_low.compute_deviations(prev_low, result_low.assignments)
    assert dev_low <= 3, f"below-threshold deviations {dev_low} should be ≤ 3"

    # ── Part 2: above threshold ──
    harms_high = [10.0, 100.0, 10.0, 100.0, 10.0, 100.0, 10.0, 10.0, 10.0, 10.0]
    inp_high = _input_two_per_zone(5, harms_high)
    prev_high = _previous_plan_even(5)
    replanner_high = Replanner(inp_high)

    # Unconstrained: high threshold allows all changes
    unconstrained = replanner_high.replan(
        prev_high, inp_high, stability_threshold=100
    )
    assert unconstrained.status in ("optimal", "feasible"), (
        f"expected feasible, got {unconstrained.status}"
    )
    unc_dev = replanner_high.compute_deviations(
        prev_high, unconstrained.assignments
    )
    assert unc_dev > 3, (
        f"unconstrained deviations {unc_dev} should be > 3 (want 6)"
    )

    # Constrained: threshold=3 forces fewer changes
    constrained = replanner_high.replan(
        prev_high, inp_high, stability_threshold=3
    )
    assert constrained.status in ("optimal", "feasible"), (
        f"expected feasible, got {constrained.status}"
    )
    con_dev = replanner_high.compute_deviations(
        prev_high, constrained.assignments
    )
    assert con_dev <= 3, f"constrained deviations {con_dev} should be ≤ 3"
    assert con_dev < unc_dev, (
        f"constrained ({con_dev}) should have fewer deviations "
        f"than unconstrained ({unc_dev})"
    )


def test_in_progress_locked() -> None:
    """In-progress assignments (already started) cannot be changed.

    3 responders, 3 zones, 6 tasks (2 per zone). t1, t3, t5 have high
    harm. Previous plan assigns r0→t0 (start=0, in-progress at t=1000)
    and r2→t4 (start=0, in-progress). The optimizer would want to
    reassign them to high-harm tasks, but in-progress lock forces them
    to stay. Only r1 (not started) can be reassigned.
    """
    harms = [10.0, 100.0, 10.0, 100.0, 10.0, 100.0]
    inp = _input_two_per_zone(3, harms)
    prev = (
        Assignment(responder_id="r0", task_id="t0", start_time=0),
        Assignment(responder_id="r1", task_id="t2", start_time=3600),
        Assignment(responder_id="r2", task_id="t4", start_time=0),
    )
    replanner = Replanner(inp)
    result = replanner.replan(
        prev, inp, stability_threshold=100, current_time=1000
    )

    assert result.status in ("optimal", "feasible"), (
        f"expected feasible, got {result.status}"
    )
    new_pairs = {(a.responder_id, a.task_id) for a in result.assignments}
    assert ("r0", "t0") in new_pairs, "in-progress r0→t0 was changed"
    assert ("r2", "t4") in new_pairs, "in-progress r2→t4 was changed"


def test_warm_start() -> None:
    """Warm-start hints are applied to the model and solver produces valid result.

    Builds the optimizer model, adds warm-start hints from a previous plan,
    and verifies that hint variables are present in the model proto. Then
    solves via replan and verifies the result is valid.
    """
    inp = _input_two_per_zone(3, [10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
    prev = _previous_plan_even(3)
    replanner = Replanner(inp)

    # Build model and add warm-start manually to inspect proto
    optimizer = EmergencyResponseOptimizer(inp)
    optimizer.build()
    prev_x = replanner._plan_to_x_map(prev, inp)
    replanner.add_warm_start(optimizer._model, optimizer._x, prev_x)

    proto = optimizer._model.proto
    assert len(proto.solution_hint.vars) > 0, "no warm-start hints found"
    assert len(proto.solution_hint.vars) == len(proto.solution_hint.values), (
        "hint vars/values length mismatch"
    )

    # Full replan should produce a valid result
    result = replanner.replan(prev, inp, stability_threshold=3)
    assert result.status in ("optimal", "feasible"), (
        f"expected feasible, got {result.status}"
    )
    assert len(result.assignments) > 0, "should have at least one assignment"


def test_compute_deviations() -> None:
    """Deviation computation: reassignment = 2, addition = 1, removal = 1."""
    inp = _input_two_per_zone(2, [10.0, 10.0, 10.0, 10.0])
    replanner = Replanner(inp)
    prev = (
        Assignment(responder_id="r0", task_id="t0", start_time=0),
        Assignment(responder_id="r1", task_id="t2", start_time=0),
    )

    # Same plan → 0 deviations
    assert replanner.compute_deviations(prev, prev) == 0

    # 1 reassignment (r1: t2→t3) → 2 deviations
    new_reassign = (
        Assignment(responder_id="r0", task_id="t0", start_time=0),
        Assignment(responder_id="r1", task_id="t3", start_time=0),
    )
    assert replanner.compute_deviations(prev, new_reassign) == 2

    # 1 removal → 1 deviation
    new_remove = (Assignment(responder_id="r0", task_id="t0", start_time=0),)
    assert replanner.compute_deviations(prev, new_remove) == 1

    # 1 addition → 1 deviation
    new_add = (
        Assignment(responder_id="r0", task_id="t0", start_time=0),
        Assignment(responder_id="r1", task_id="t2", start_time=0),
        Assignment(responder_id="r2", task_id="t4", start_time=0),
    )
    assert replanner.compute_deviations(prev, new_add) == 1

    # Full reassignment (both change) → 4 deviations
    new_full = (
        Assignment(responder_id="r0", task_id="t2", start_time=0),
        Assignment(responder_id="r1", task_id="t0", start_time=0),
    )
    assert replanner.compute_deviations(prev, new_full) == 4


def test_lock_in_progress() -> None:
    """lock_in_progress correctly identifies in-progress assignments.

    At current_time=1000:
      - r0→t0 (start=0, duration=3600) → in-progress (0 ≤ 1000 < 3600)
      - r1→t2 (start=3600, duration=3600) → not started (3600 > 1000)
      - r2→t4 (start=0, duration=3600) → in-progress (0 ≤ 1000 < 3600)
    """
    inp = _input_two_per_zone(3, [10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
    replanner = Replanner(inp)
    assignments = (
        Assignment(responder_id="r0", task_id="t0", start_time=0),
        Assignment(responder_id="r1", task_id="t2", start_time=3600),
        Assignment(responder_id="r2", task_id="t4", start_time=0),
    )

    in_progress = replanner.lock_in_progress(assignments, current_time=1000)

    assert len(in_progress) == 2, (
        f"expected 2 in-progress, got {len(in_progress)}"
    )
    in_progress_ids = {(a.responder_id, a.task_id) for a in in_progress}
    assert ("r0", "t0") in in_progress_ids
    assert ("r2", "t4") in in_progress_ids
    assert ("r1", "t2") not in in_progress_ids
