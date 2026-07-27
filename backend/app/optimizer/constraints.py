"""Constraint modeling for the CVaR optimizer (T26).

Each function adds one constraint family to the CP-SAT model. The engine
calls them in sequence after creating the decision variables.

Constraint families (modeled simultaneously):
  1. Skills — add_allowed_assignments + x[r,t]==0 for incompatible pairs
  2. Responder availability — add_cumulative (capacity=1 per responder)
  3. Vehicle-road routing — add_multiple_circuit with conditional arcs
  4. Shelter/hospital capacity — add_reservoir_constraint_with_active
  5. Shift duration — interval bounds on responder time
  6. Fairness — Coverage_z >= C_min for vulnerable zones
  7. Task precedence — end[before] <= start[after]
"""

from __future__ import annotations

from ortools.sat.python import cp_model

from app.optimizer.optimizer_types import OptimizerInput


def add_skill_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[int, int], cp_model.IntVar],
    assign: dict[int, cp_model.IntVar],
    inp: OptimizerInput,
) -> None:
    """Skill compatibility via add_allowed_assignments + x[r,t]==0.

    For each responder, ``assign[r]`` is constrained to only take values
    corresponding to tasks whose required_skill is in the responder's skill
    set (or 0 = unassigned). Incompatible x[r,t] are explicitly forced to 0.
    """
    for r_idx, resp in enumerate(inp.responders):
        allowed_tuples: list[list[int]] = [[0]]  # 0 = unassigned
        for t_idx, task in enumerate(inp.tasks):
            if task.required_skill in resp.skills:
                allowed_tuples.append([t_idx + 1])
            else:
                model.add(x[r_idx, t_idx] == 0)
        model.add_allowed_assignments([assign[r_idx]], allowed_tuples)


def add_availability_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[int, int], cp_model.IntVar],
    task_start: dict[int, cp_model.IntVar],
    inp: OptimizerInput,
    horizon: int,
) -> None:
    """Responder availability via add_cumulative (capacity=1 per responder).

    Each responder can work on at most one task at a time. Optional interval
    vars are created per (responder, task) pair, active only when x[r,t]=1.
    """
    for r_idx in range(len(inp.responders)):
        intervals: list[cp_model.IntervalVar] = []
        for t_idx, task in enumerate(inp.tasks):
            start = task_start[t_idx]
            size = task.duration
            interval = model.new_optional_interval_var(
                start, size, start + size,
                x[r_idx, t_idx], f"iv_{r_idx}_{t_idx}",
            )
            intervals.append(interval)
        model.add_cumulative(intervals, [1] * len(intervals), 1)


def add_routing_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[int, int], cp_model.IntVar],
    visit: dict[int, cp_model.IntVar],
    inp: OptimizerInput,
    node_of_zone: dict[str, int],
) -> None:
    """Vehicle-road routing via add_multiple_circuit with conditional arcs.

    Each zone is a circuit node. The depot (node 0) is the start/end.
    Arcs are conditional: an arc to a zone is only active if a responder
    whose vehicle can traverse it is assigned to a task in that zone.
    Incompatible arcs are skipped (literal forced to 0).
    """
    arcs: list[tuple[int, int, cp_model.IntVar]] = []
    for zone in inp.zones:
        z_node = node_of_zone[zone.id]
        # visit[z] = OR(x[r,t] for tasks t at zone z)
        zone_task_pairs = [
            (r_idx, t_idx)
            for r_idx, resp in enumerate(inp.responders)
            for t_idx, task in enumerate(inp.tasks)
            if task.zone_id == zone.id
        ]
        if not zone_task_pairs:
            model.add(visit[z_node] == 0)
        else:
            # Build conditional arcs: only compatible vehicle classes can use
            # the road to this zone. If no compatible responder is assigned,
            # the arc literal stays 0 (arc skipped).
            compatible_lits: list[cp_model.IntVar] = []
            for r_idx, t_idx in zone_task_pairs:
                resp = inp.responders[r_idx]
                # Check if any road arc to this zone supports resp's vehicle
                can_reach = any(
                    resp.vehicle_class in arc.vehicle_classes
                    for arc in inp.road_arcs
                    if arc.to_node == z_node
                ) if inp.road_arcs else True
                if can_reach:
                    compatible_lits.append(x[r_idx, t_idx])
                else:
                    model.add(x[r_idx, t_idx] == 0)
            if compatible_lits:
                model.add_max_equality(visit[z_node], compatible_lits)
            else:
                model.add(visit[z_node] == 0)
        arcs.append((0, z_node, visit[z_node]))
        arcs.append((z_node, 0, visit[z_node]))
    if arcs:
        model.add_multiple_circuit(arcs)


def add_capacity_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[int, int], cp_model.IntVar],
    task_start: dict[int, cp_model.IntVar],
    inp: OptimizerInput,
) -> None:
    """Shelter/hospital capacity via add_reservoir_constraint_with_active.

    Each shelter tracks occupancy over time. Tasks that add occupants
    (e.g. evacuation transport) create +1 level changes at their start time
    and -1 at their end time, active only when the task is assigned.
    """
    for shelter in inp.shelters:
        times: list[cp_model.LinearExpr] = []
        changes: list[int] = []
        actives: list[cp_model.IntVar] = []
        for t_idx, task in enumerate(inp.tasks):
            if task.zone_id != shelter.id:
                continue
            start = task_start[t_idx]
            end_expr = start + task.duration
            # +1 occupant at task start, -1 at task end
            for r_idx in range(len(inp.responders)):
                times.append(start)
                changes.append(1)
                actives.append(x[r_idx, t_idx])
                times.append(end_expr)
                changes.append(-1)
                actives.append(x[r_idx, t_idx])
        if times:
            model.add_reservoir_constraint_with_active(
                times, changes, actives,
                min_level=-shelter.initial_occupancy,
                max_level=shelter.capacity - shelter.initial_occupancy,
            )


def add_shift_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[int, int], cp_model.IntVar],
    task_start: dict[int, cp_model.IntVar],
    inp: OptimizerInput,
) -> None:
    """Shift duration: assigned tasks must fit within [shift_start, shift_end]."""
    for r_idx, resp in enumerate(inp.responders):
        for t_idx, task in enumerate(inp.tasks):
            # Task must end before shift_end (conditional on assignment)
            model.add(
                task_start[t_idx] + task.duration <= resp.shift_end
            ).only_enforce_if(x[r_idx, t_idx])
            model.add(
                task_start[t_idx] >= resp.shift_start
            ).only_enforce_if(x[r_idx, t_idx])


def add_fairness_constraints(
    model: cp_model.CpModel,
    coverage: dict[str, cp_model.IntVar],
    inp: OptimizerInput,
) -> None:
    """Fairness: Coverage_z >= C_min for vulnerable zones."""
    for zone in inp.zones:
        if zone.vulnerable and zone.c_min > 0:
            model.add(coverage[zone.id] >= zone.c_min)


def add_precedence_constraints(
    model: cp_model.CpModel,
    task_start: dict[int, cp_model.IntVar],
    inp: OptimizerInput,
) -> None:
    """Task precedence: end[before] <= start[after]."""
    task_idx = {t.id: i for i, t in enumerate(inp.tasks)}
    for i, task in enumerate(inp.tasks):
        for after_id in task.precedes:
            if after_id in task_idx:
                j = task_idx[after_id]
                model.add(
                    task_start[i] + task.duration <= task_start[j]
                )


__all__ = [
    "add_availability_constraints",
    "add_capacity_constraints",
    "add_fairness_constraints",
    "add_precedence_constraints",
    "add_routing_constraints",
    "add_shift_constraints",
    "add_skill_constraints",
]
