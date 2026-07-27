"""Stability threshold replanner for rolling-horizon optimization (T29).

Implements SOTA spec §8.4: rolling-horizon replanning with warm-start,
deviation penalty, and in-progress action locking. Prevents responder
thrashing from small score fluctuations by limiting the number of
assignment changes per replanning cycle.

Every operational cycle:
  1. Receive new observations (new OptimizerInput)
  2. Build the optimizer model with new input
  3. Warm-start from previous plan via model.add_hint(x[r,t], prev_value)
  4. Lock in-progress assignments (already started → cannot be changed)
  5. Add deviation constraint: changed[r,t] = |x[r,t] - prev_x[r,t]|
     total_deviations = sum(changed[r,t]) <= stability_threshold
  6. Solve and return new plan with limited deviations

The stability threshold prevents re-routing teams for trivial improvements:
if the new plan would change more assignments than the threshold allows,
the solver is forced to find a solution with fewer changes.
"""

from __future__ import annotations

import time
from typing import cast

from ortools.sat.python import cp_model

from app.optimizer.engine import SCALE, EmergencyResponseOptimizer
from app.optimizer.optimizer_types import (
    Assignment,
    OptimizerInput,
    OptimizerResult,
)


class Replanner:
    """Stability-threshold replanner wrapping EmergencyResponseOptimizer.

    Builds the standard CVaR optimizer model, then adds warm-start hints,
    deviation constraints, and in-progress action locks before solving.
    """

    def __init__(self, inp: OptimizerInput) -> None:
        self._inp = inp

    def replan(
        self,
        previous_plan: tuple[Assignment, ...],
        new_input: OptimizerInput,
        stability_threshold: int = 3,
        current_time: int | None = None,
    ) -> OptimizerResult:
        """Re-optimize with stability constraints.

        Returns a new plan that deviates from ``previous_plan`` by at most
        ``stability_threshold`` assignments. If ``current_time`` is provided,
        in-progress assignments (already started) are locked and cannot
        change.
        """
        optimizer = EmergencyResponseOptimizer(new_input)
        optimizer.build()

        prev_x = self._plan_to_x_map(previous_plan, new_input)
        self.add_warm_start(optimizer._model, optimizer._x, prev_x)

        if current_time is not None:
            in_progress = self.lock_in_progress(previous_plan, current_time)
            if in_progress:
                self._lock_assignments(
                    optimizer._model, optimizer._x, in_progress, new_input
                )

        self.add_deviation_constraint(
            optimizer._model, optimizer._x, prev_x, stability_threshold
        )

        return self._solve(optimizer)

    def lock_in_progress(
        self, assignments: tuple[Assignment, ...], current_time: int
    ) -> tuple[Assignment, ...]:
        """Return assignments that are in-progress (cannot be changed).

        An assignment is in-progress if ``current_time`` falls within
        ``[start_time, start_time + task_duration)``.
        """
        task_durations = {t.id: t.duration for t in self._inp.tasks}
        return tuple(
            a
            for a in assignments
            if a.task_id in task_durations
            and a.start_time <= current_time
            < a.start_time + task_durations[a.task_id]
        )

    def compute_deviations(
        self,
        previous_plan: tuple[Assignment, ...],
        new_plan: tuple[Assignment, ...],
    ) -> int:
        """Count changed assignments between two plans.

        Each reassignment counts as 2 deviations (one removal + one
        addition). Pure additions or removals count as 1 each.
        """
        prev_pairs = {(a.responder_id, a.task_id) for a in previous_plan}
        new_pairs = {(a.responder_id, a.task_id) for a in new_plan}
        removals = len(prev_pairs - new_pairs)
        additions = len(new_pairs - prev_pairs)
        return removals + additions

    def add_warm_start(
        self,
        model: cp_model.CpModel,
        x_vars: dict[tuple[int, int], cp_model.IntVar],
        prev_x: dict[tuple[int, int], int],
    ) -> None:
        """Add warm-start hints from previous plan.

        Uses ``model.add_hint(x[r,t], prev_value)`` for every decision
        variable, guiding the solver toward the previous solution.
        """
        for key, var in x_vars.items():
            model.add_hint(var, prev_x.get(key, 0))

    def add_deviation_constraint(
        self,
        model: cp_model.CpModel,
        x_vars: dict[tuple[int, int], cp_model.IntVar],
        prev_x: dict[tuple[int, int], int],
        threshold: int,
    ) -> None:
        """Add deviation constraint: ``total_deviations <= threshold``.

        For each (r, t) pair, ``changed[r,t]`` is 1 if the assignment
        differs from the previous plan. The sum of all ``changed`` vars
        is constrained to not exceed ``threshold``.
        """
        changed_vars: list[cp_model.IntVar] = []
        for key, x_var in x_vars.items():
            prev_val = prev_x.get(key, 0)
            c = model.new_bool_var(f"changed_{key[0]}_{key[1]}")
            changed_vars.append(c)
            if prev_val == 1:
                # changed = 1 - x (changed if we removed the assignment)
                model.add(c + x_var == 1)
            else:
                # changed = x (changed if we added a new assignment)
                model.add(c == x_var)
        model.add(sum(changed_vars) <= threshold)

    def _plan_to_x_map(
        self, plan: tuple[Assignment, ...], inp: OptimizerInput
    ) -> dict[tuple[int, int], int]:
        """Convert a plan to a ``{(r_idx, t_idx): 1}`` mapping."""
        r_idx = {r.id: i for i, r in enumerate(inp.responders)}
        t_idx = {t.id: i for i, t in enumerate(inp.tasks)}
        result: dict[tuple[int, int], int] = {}
        for a in plan:
            if a.responder_id in r_idx and a.task_id in t_idx:
                result[(r_idx[a.responder_id], t_idx[a.task_id])] = 1
        return result

    def _lock_assignments(
        self,
        model: cp_model.CpModel,
        x_vars: dict[tuple[int, int], cp_model.IntVar],
        assignments: tuple[Assignment, ...],
        inp: OptimizerInput,
    ) -> None:
        """Lock in-progress assignments by fixing ``x[r,t] = 1``."""
        r_idx = {r.id: i for i, r in enumerate(inp.responders)}
        t_idx = {t.id: i for i, t in enumerate(inp.tasks)}
        for a in assignments:
            key = (r_idx[a.responder_id], t_idx[a.task_id])
            if key in x_vars:
                model.add(x_vars[key] == 1)

    def _solve(self, optimizer: EmergencyResponseOptimizer) -> OptimizerResult:
        """Solve the model and extract results (mirrors engine.solve minus build)."""
        inp = optimizer._inp
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = inp.max_solve_seconds
        solver.parameters.num_search_workers = 8

        t0 = time.time()
        status = solver.solve(optimizer._model)
        solve_time = time.time() - t0

        if status == cp_model.OPTIMAL:
            status_str = "optimal"
        elif status == cp_model.FEASIBLE:
            status_str = "feasible"
        elif status == cp_model.INFEASIBLE:
            status_str = "infeasible"
        else:
            status_str = "unknown"

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return OptimizerResult(
                status=status_str,
                assignments=(),
                objective_value=float("inf"),
                expected_harm=float("inf"),
                cvar=float("inf"),
                operational_cost=float("inf"),
                solve_time_seconds=solve_time,
            )

        assignments: list[Assignment] = []
        for r_idx, resp in enumerate(inp.responders):
            for t_idx, task in enumerate(inp.tasks):
                if solver.value(optimizer._x[r_idx, t_idx]) == 1:
                    assignments.append(
                        Assignment(
                            responder_id=resp.id,
                            task_id=task.id,
                            start_time=solver.value(optimizer._task_start[t_idx]),
                        )
                    )

        D = optimizer._D
        expected_harm = sum(
            (optimizer._p_int[s] / D)
            * solver.value(optimizer._loss[s])
            / SCALE
            for s in range(len(inp.scenarios))
        )
        cvar = (
            (solver.value(cast(cp_model.LinearExpr, optimizer._theta)) or 0)
            + optimizer._cvar_factor
            * sum(
                (optimizer._p_int[s] / D) * (solver.value(optimizer._excess[s]) or 0)
                for s in range(len(inp.scenarios))
            )
        ) / SCALE
        op_cost = sum(
            solver.value(optimizer._x[r, t]) * inp.responders[r].cost_per_task
            for r in range(len(inp.responders))
            for t in range(len(inp.tasks))
        )
        objective = expected_harm + inp.lambda_risk * cvar + op_cost
        coverage = {
            z.id: solver.value(optimizer._coverage[z.id]) for z in inp.zones
        }

        return OptimizerResult(
            status=status_str,
            assignments=tuple(assignments),
            objective_value=objective,
            expected_harm=expected_harm,
            cvar=cvar,
            operational_cost=op_cost,
            solve_time_seconds=solve_time,
            coverage=coverage,
        )


__all__ = ["Replanner"]
