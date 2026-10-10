"""Optimize routes — POST /api/optimize (async) + GET /api/incidents/{id}/optimize.

The existing optimizer router (POST + GET polling) lives in app.optimizer.api.
This module re-exports it AND adds an incident-scoped synchronous endpoint
that returns assignments + alternatives + trade-offs (not an opaque command).

GET /api/incidents/{id}/optimize:
  1. Builds OptimizerInput from the incident's DB data, or a demo fallback.
  2. Solves twice: fair plan (with fairness constraints) + original plan
     (constraints relaxed).
  3. Computes an EquityReport via FairnessEngine.compute_equity_report().
  4. Returns assignments + alternatives + trade-offs.
  5. If infeasible, returns an explanation diagnosing the likely cause.
  6. Applies progressive precision to coordinates based on viewer role.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.privacy import round_coords_by_role
from app.deps import get_current_user, get_db
from app.models.incident import Incident
from app.models.user import User
from app.optimizer.api import router
from app.optimizer.engine import EmergencyResponseOptimizer
from app.optimizer.fairness import FairnessEngine
from app.optimizer.fairness_types import FairnessZone, Plan
from app.optimizer.incident_input import build_input_from_db, demo_input
from app.optimizer.optimizer_types import OptimizerInput, Zone

logger = logging.getLogger("app.api.routes.optimize")

incident_router = APIRouter(prefix="/incidents", tags=["optimize"])


def _get_incident(db: Session, org_id: str, incident_id: str) -> Incident:
    inc = db.execute(
        select(Incident).where(
            Incident.org_id == org_id, Incident.id == incident_id,
        )
    ).scalars().first()
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return inc


def _explain_infeasible(inp: OptimizerInput) -> str:
    """Diagnose likely cause of infeasibility."""
    reasons: list[str] = []
    if len(inp.responders) < len(inp.tasks):
        reasons.append(
            f"not enough responders ({len(inp.responders)}) for tasks ({len(inp.tasks)})"
        )
    task_skills = {t.required_skill for t in inp.tasks}
    responder_skills: set[str] = set()
    for r in inp.responders:
        responder_skills |= r.skills
    missing = task_skills - responder_skills
    if missing:
        reasons.append(f"no responder has required skills: {sorted(missing)}")
    for s in inp.shelters:
        if s.capacity < s.initial_occupancy:
            reasons.append(f"shelter '{s.id}' over capacity (cap={s.capacity}, occ={s.initial_occupancy})")
    vulnerable = [z.id for z in inp.zones if z.vulnerable and z.c_min > 0]
    if vulnerable and len(inp.responders) < sum(z.c_min for z in inp.zones):
        reasons.append(f"vulnerable zones {vulnerable} require c_min coverage but not enough responders")
    if not reasons:
        reasons.append("constraint conflict — likely routing/vehicle incompatibility or shift window")
    return "; ".join(reasons)


def _result_to_plan(result: Any, inp: OptimizerInput) -> Plan:
    """Map OptimizerResult to a Plan for fairness comparison."""
    coverage = dict(result.coverage) if result.coverage else {}
    delays = {z.id: 0 for z in inp.zones}
    return Plan(coverage=coverage, response_delays=delays, throughput=len(result.assignments))


def _serialize_result(result: Any, inp: OptimizerInput) -> dict[str, Any]:
    """Serialize an OptimizerResult for the API response."""
    responder_map = {r.id: r for r in inp.responders}
    task_map = {t.id: t for t in inp.tasks}
    assignments = [
        {
            "responder_id": a.responder_id,
            "task_id": a.task_id,
            "start_time": a.start_time,
            "responder_vehicle_class": responder_map[a.responder_id].vehicle_class if a.responder_id in responder_map else None,
            "task_zone_id": task_map[a.task_id].zone_id if a.task_id in task_map else None,
            "task_required_skill": task_map[a.task_id].required_skill if a.task_id in task_map else None,
        }
        for a in result.assignments
    ]
    finite = lambda v: round(v, 4) if v != float("inf") else None
    return {
        "status": result.status,
        "assignments": assignments,
        "objective_value": finite(result.objective_value),
        "expected_harm": finite(result.expected_harm),
        "cvar": finite(result.cvar),
        "operational_cost": finite(result.operational_cost),
        "solve_time_seconds": round(result.solve_time_seconds, 3),
        "coverage": dict(result.coverage) if result.coverage else {},
    }


@incident_router.get("/{incident_id}/optimize")
def get_incident_optimize(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """GET /api/incidents/{id}/optimize — assignments + alternatives + trade-offs.

    Returns the fair plan (with fairness constraints), the original plan
    (without fairness constraints), and an equity report showing the
    throughput tradeoff. If infeasible, returns an explanation.
    """
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    inp = build_input_from_db(db, org_id, incident_id)
    if inp is None:
        inp = demo_input()
        source = "demo_scenario"
    else:
        source = "incident_data"

    fair_result = EmergencyResponseOptimizer(inp).solve()

    if fair_result.status == "infeasible":
        return {
            "incident_id": incident_id,
            "status": "infeasible",
            "explanation": _explain_infeasible(inp),
            "input_source": source,
            "n_responders": len(inp.responders),
            "n_tasks": len(inp.tasks),
            "n_zones": len(inp.zones),
        }

    # Original plan: relax fairness constraints (vulnerable=False, c_min=0).
    relaxed_zones = tuple(
        Zone(id=z.id, demand=z.demand, vulnerable=False, c_min=0) for z in inp.zones
    )
    relaxed_inp = OptimizerInput(
        zones=relaxed_zones, responders=inp.responders, tasks=inp.tasks,
        scenarios=inp.scenarios, road_arcs=inp.road_arcs, shelters=inp.shelters,
        alpha=inp.alpha, lambda_risk=inp.lambda_risk, max_solve_seconds=inp.max_solve_seconds,
    )
    original_result = EmergencyResponseOptimizer(relaxed_inp).solve()
    if original_result.status == "infeasible":
        original_result = fair_result  # fallback if relaxed is also infeasible

    fair_plan = _result_to_plan(fair_result, inp)
    original_plan = _result_to_plan(original_result, inp)
    fz_zones = tuple(
        FairnessZone(id=z.id, vulnerable=z.vulnerable, c_min=z.c_min) for z in inp.zones
    )
    equity = FairnessEngine().compute_equity_report(original_plan, fair_plan, fz_zones)

    role = user.role
    return {
        "incident_id": incident_id,
        "status": fair_result.status,
        "input_source": source,
        "fair_plan": _serialize_result(fair_result, inp),
        "original_plan": _serialize_result(original_result, inp),
        "equity_report": {
            "equity_applied": equity.equity_applied,
            "throughput_tradeoff_pct": equity.throughput_tradeoff_pct,
            "vulnerable_zones_protected": list(equity.vulnerable_zones_protected),
            "low_connectivity_zones_protected": list(equity.low_connectivity_zones_protected),
            "disparity_seconds": equity.disparity_seconds,
            "message": equity.message,
        },
        "progressive_precision": {
            "role": role,
            "coord_decimals": round_coords_by_role(
                {"lat": 19.0760, "lon": 72.8777}, role,
            ),
        },
    }


__all__ = ["incident_router", "router"]
