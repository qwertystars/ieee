"""EmergencyResponseOptimizer — rolling-horizon risk-aware CVaR optimizer (T26).

Objective (Rockafellar-Uryasev 2000):

    A* = argmin_A [ Σ p_ω L^ω(A) + λ CVaR_α(L^ω(A)) + C(A) ]

  - First term  = expected harm over scenario ensemble
  - Second term = λ × CVaR penalty (risk aversion)
  - Third term  = operational cost of the assignment portfolio

CVaR via Rockafellar-Uryasev: ``theta`` is a FREE decision variable (the
VaR, not a parameter). For each scenario s:

    excess_s = max(0, cost_s - theta)          # via add_max_equality
    CVaR     = theta + 1/(1-α) × Σ p_s × excess_s

All variables are integer-scaled (CP-SAT is integer-only). Costs are
multiplied by ``SCALE`` (1000) and rounded. Probabilities are scaled to
integers with denominator ``D`` (e.g. [0.3, 0.4, 0.3] → [3, 4, 3], D=10).

The integer objective minimized by CP-SAT is ``D × SCALE × J``:

    Σ p_int[s] × L_s + D×λ×θ + cvar_factor×λ × Σ p_int[s]×a_s + D × Σ x[r,t]×cost[r,t]

where ``cvar_factor = round(1/(1-α))`` (= 20 for α=0.95).

The FastAPI router (POST /api/optimize) lives in ``app.optimizer.api``.
"""

from __future__ import annotations

import logging
import time
from typing import cast

from ortools.sat.python import cp_model

from app.optimizer.constraints import (
    add_availability_constraints,
    add_capacity_constraints,
    add_fairness_constraints,
    add_precedence_constraints,
    add_routing_constraints,
    add_shift_constraints,
    add_skill_constraints,
)
from app.optimizer.optimizer_types import (
    Assignment,
    OptimizerInput,
    OptimizerResult,
)

logger = logging.getLogger(__name__)

# Integer scaling: CP-SAT requires all variables to be integers.
SCALE = 1000


class EmergencyResponseOptimizer:
    """CVaR risk-aware optimizer using OR-Tools CP-SAT.

    Builds a constraint program with seven simultaneous constraint families
    and a Rockafellar-Uryasev CVaR objective. Hard constraints (skills,
    availability, routing, capacity, shift, fairness, precedence) are always
    enforced — online RL is never the sole controller.
    """

    def __init__(self, inp: OptimizerInput) -> None:
        self._inp = inp
        self._model = cp_model.CpModel()
        self._x: dict[tuple[int, int], cp_model.IntVar] = {}
        self._assign: dict[int, cp_model.IntVar] = {}
        self._task_start: dict[int, cp_model.IntVar] = {}
        self._visit: dict[int, cp_model.IntVar] = {}
        self._coverage: dict[str, cp_model.IntVar] = {}
        self._loss: dict[int, cp_model.IntVar] = {}
        self._excess: dict[int, cp_model.IntVar] = {}
        self._theta: cp_model.IntVar | None = None
        self._horizon = sum(t.duration for t in inp.tasks) + 1
        self._node_of_zone: dict[str, int] = {
            z.id: i + 1 for i, z in enumerate(inp.zones)
        }
        self._p_int: list[int] = []
        self._D: int = 1
        self._cvar_factor: int = 20
        self._lam: int = 1

    def build(self) -> None:
        """Create variables, add all constraints, and set the CVaR objective."""
        inp = self._inp
        n_tasks = len(inp.tasks)
        n_resp = len(inp.responders)

        # ── Decision variables ───────────────────────────────────────
        for r_idx in range(n_resp):
            self._assign[r_idx] = self._model.new_int_var(0, n_tasks, f"a_{r_idx}")
            for t_idx in range(n_tasks):
                self._x[r_idx, t_idx] = self._model.new_bool_var(f"x_{r_idx}_{t_idx}")

        for t_idx in range(n_tasks):
            self._task_start[t_idx] = self._model.new_int_var(
                0, self._horizon, f"ts_{t_idx}"
            )

        for z in inp.zones:
            node = self._node_of_zone[z.id]
            self._visit[node] = self._model.new_bool_var(f"v_{node}")
            self._coverage[z.id] = self._model.new_int_var(0, n_resp, f"cov_{z.id}")

        # Link assign[r] = Σ (t_idx+1) × x[r,t]; at most one task per responder
        for r_idx in range(n_resp):
            self._model.add(
                self._assign[r_idx]
                == sum((t_idx + 1) * self._x[r_idx, t_idx] for t_idx in range(n_tasks))
            )
            self._model.add(sum(self._x[r_idx, t_idx] for t_idx in range(n_tasks)) <= 1)

        # Coverage[z] = Σ x[r,t] for tasks t at zone z
        for z in inp.zones:
            zone_tasks = [ti for ti, t in enumerate(inp.tasks) if t.zone_id == z.id]
            self._model.add(
                self._coverage[z.id]
                == sum(self._x[r, t] for r in range(n_resp) for t in zone_tasks)
            )

        # ── Constraints (all seven families, simultaneously) ─────────
        add_skill_constraints(self._model, self._x, self._assign, inp)
        add_availability_constraints(self._model, self._x, self._task_start, inp, self._horizon)
        add_routing_constraints(self._model, self._x, self._visit, inp, self._node_of_zone)
        add_capacity_constraints(self._model, self._x, self._task_start, inp)
        add_shift_constraints(self._model, self._x, self._task_start, inp)
        add_fairness_constraints(self._model, self._coverage, inp)
        add_precedence_constraints(self._model, self._task_start, inp)

        # ── CVaR objective (Rockafellar-Uryasev) ─────────────────────
        self._build_cvar_objective()

    def _build_cvar_objective(self) -> None:
        """Build the integer-scaled CVaR objective."""
        inp = self._inp
        alpha = inp.alpha
        cvar_factor = round(1.0 / (1.0 - alpha))  # 20 for α=0.95
        lam = round(inp.lambda_risk)

        # Scale probabilities to integers: [0.3, 0.4, 0.3] → [3, 4, 3], D=10
        max_dec = max(len(str(s.probability).split(".")[-1]) for s in inp.scenarios)
        factor = 10 ** max_dec
        p_int = [round(s.probability * factor) for s in inp.scenarios]
        D = sum(p_int)

        # Per-scenario loss L_s = Σ_z harm_z × uncovered_z (scaled by SCALE)
        # uncovered_z = max(0, demand_z - coverage_z)
        max_harm = max(
            sum(round(t.harm_if_unserved * SCALE) for t in inp.tasks) for _ in [0]
        )
        self._theta = self._model.new_int_var(0, max_harm + 1, "theta")

        obj_terms: list[cp_model.LinearExpr] = []

        for s_idx, sc in enumerate(inp.scenarios):
            # L_s = Σ_t harm_t × harm_mult × (1 - served_t)
            # served_t = OR(x[r,t] for r); unserved_t = 1 - served_t
            loss_terms = []
            for t_idx, task in enumerate(inp.tasks):
                served = self._model.new_bool_var(f"srv_{s_idx}_{t_idx}")
                self._model.add_max_equality(
                    served, [self._x[r, t_idx] for r in range(len(inp.responders))]
                )
                harm_scaled = round(task.harm_if_unserved * sc.harm_multiplier * SCALE)
                loss_terms.append(harm_scaled * (1 - served))
            L_s = self._model.new_int_var(0, max_harm * 100 + 1, f"L_{s_idx}")
            self._model.add(L_s == sum(loss_terms))
            self._loss[s_idx] = L_s

            # excess_s = max(0, L_s - theta) via add_max_equality
            a_s = self._model.new_int_var(0, max_harm * 100 + 1, f"ex_{s_idx}")
            self._model.add_max_equality(a_s, [L_s - self._theta, self._model.new_constant(0)])
            self._excess[s_idx] = a_s

            # Expected harm term: p_int[s] × L_s
            obj_terms.append(p_int[s_idx] * L_s)
            # CVaR excess term: cvar_factor × λ × p_int[s] × a_s
            obj_terms.append(cvar_factor * lam * p_int[s_idx] * a_s)

        # CVaR VaR term: D × λ × theta
        obj_terms.append(D * lam * self._theta)

        # Operational cost: D × Σ x[r,t] × cost[r,t] (scaled)
        for r_idx, resp in enumerate(inp.responders):
            cost_scaled = round(resp.cost_per_task * SCALE)
            for t_idx in range(len(inp.tasks)):
                obj_terms.append(D * cost_scaled * self._x[r_idx, t_idx])

        self._model.minimize(sum(obj_terms))
        self._p_int = p_int
        self._D = D
        self._cvar_factor = cvar_factor
        self._lam = lam

    def solve(self) -> OptimizerResult:
        """Build and solve the model. Returns an OptimizerResult."""
        self.build()
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self._inp.max_solve_seconds
        solver.parameters.num_search_workers = 8

        t0 = time.time()
        status = solver.solve(self._model)
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

        # Extract assignments
        assignments: list[Assignment] = []
        for r_idx, resp in enumerate(self._inp.responders):
            for t_idx, task in enumerate(self._inp.tasks):
                if solver.value(self._x[r_idx, t_idx]) == 1:
                    assignments.append(Assignment(
                        responder_id=resp.id,
                        task_id=task.id,
                        start_time=solver.value(self._task_start[t_idx]),
                    ))

        # Extract objective components (unscale from D × SCALE)
        D = self._D
        expected_harm = sum(
            (self._p_int[s] / D) * (solver.value(self._loss[s]) or 0) / SCALE
            for s in range(len(self._inp.scenarios))
        )
        cvar = (
            (solver.value(cast(cp_model.LinearExpr, self._theta)) or 0)
            + self._cvar_factor
            * sum(
                (self._p_int[s] / D) * (solver.value(self._excess[s]) or 0)
                for s in range(len(self._inp.scenarios))
            )
        ) / SCALE
        op_cost = sum(
            (solver.value(self._x[r, t]) or 0) * self._inp.responders[r].cost_per_task
            for r in range(len(self._inp.responders))
            for t in range(len(self._inp.tasks))
        )
        objective = expected_harm + self._inp.lambda_risk * cvar + op_cost

        coverage = {
            z.id: solver.value(self._coverage[z.id]) for z in self._inp.zones
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


__all__ = ["EmergencyResponseOptimizer"]
