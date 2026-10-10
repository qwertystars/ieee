"""FastAPI router for the CVaR optimizer — POST /api/optimize + GET polling.

The optimizer runs asynchronously via BackgroundTasks. POST starts the solve
and returns a task_id; GET /{task_id} polls for the result (within 30s).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.deps import get_db, require_roles
from app.eval.jobs import EvaluationJobStore, job_response
from app.models.user import User
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/optimize", tags=["optimize"])

class OptimizeRequest(BaseModel):
    """JSON request body for POST /api/optimize."""

    zones: list[dict[str, Any]]
    responders: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    scenarios: list[dict[str, Any]]
    road_arcs: list[dict[str, Any]] = Field(default_factory=list)
    shelters: list[dict[str, Any]] = Field(default_factory=list)
    alpha: float = 0.95
    lambda_risk: float = 1.0
    max_solve_seconds: float = 30.0


def _parse_request(req: OptimizeRequest) -> OptimizerInput:
    """Parse the Pydantic request into an OptimizerInput."""
    zones = tuple(
        Zone(id=z["id"], demand=z.get("demand", 1),
             vulnerable=z.get("vulnerable", False), c_min=z.get("c_min", 0))
        for z in req.zones
    )
    responders = tuple(
        Responder(id=r["id"], skills=frozenset(r["skills"]),
                  vehicle_class=r["vehicle_class"],
                  shift_start=r.get("shift_start", 0),
                  shift_end=r.get("shift_end", 86_400_000),
                  cost_per_task=r.get("cost_per_task", 1.0))
        for r in req.responders
    )
    tasks = tuple(
        Task(id=t["id"], zone_id=t["zone_id"], required_skill=t["required_skill"],
             duration=t.get("duration", 3600),
             precedes=tuple(t.get("precedes", [])),
             harm_if_unserved=t.get("harm_if_unserved", 100.0))
        for t in req.tasks
    )
    scenarios = tuple(
        ScenarioLoss(probability=s["probability"],
                     harm_multiplier=s.get("harm_multiplier", 1.0))
        for s in req.scenarios
    )
    road_arcs = tuple(
        RoadArc(from_node=a["from_node"], to_node=a["to_node"],
                vehicle_classes=frozenset(a["vehicle_classes"]),
                travel_time=a.get("travel_time", 0))
        for a in req.road_arcs
    )
    shelters = tuple(
        Shelter(id=s["id"], capacity=s["capacity"],
                initial_occupancy=s.get("initial_occupancy", 0))
        for s in req.shelters
    )
    return OptimizerInput(
        zones=zones, responders=responders, tasks=tasks, scenarios=scenarios,
        road_arcs=road_arcs, shelters=shelters,
        alpha=req.alpha, lambda_risk=req.lambda_risk,
        max_solve_seconds=req.max_solve_seconds,
    )


def _run_optimize(task_id: str, inp: OptimizerInput, org_id: str) -> None:
    """Background task: solve and store the result."""
    db = SessionLocal()
    try:
        result = EmergencyResponseOptimizer(inp).solve()
        EvaluationJobStore(db).complete(task_id, org_id, {
            "status": result.status,
            "result": {
                "status": result.status,
                "assignments": [
                    {"responder_id": a.responder_id, "task_id": a.task_id,
                     "start_time": a.start_time}
                    for a in result.assignments
                ],
                "objective_value": result.objective_value,
                "expected_harm": result.expected_harm,
                "cvar": result.cvar,
                "operational_cost": result.operational_cost,
                "solve_time_seconds": result.solve_time_seconds,
                "coverage": result.coverage,
            },
        })
    except Exception as exc:
        logger.exception("Optimize task %s failed", task_id)
        EvaluationJobStore(db).fail(task_id, org_id, str(exc))
    finally:
        db.close()


@router.post("")
async def optimize(
    req: OptimizeRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles()),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """POST /api/optimize — start async solve, return task_id for polling."""
    inp = _parse_request(req)
    job = EvaluationJobStore(db).create(user.org_id, user.id, "optimizer", req.model_dump())
    task_id = job.id
    background_tasks.add_task(_run_optimize, task_id, inp, user.org_id)
    return {"task_id": task_id, "status": "pending"}


@router.get("/{task_id}")
async def get_optimize_result(
    task_id: str,
    user: User = Depends(require_roles()),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """GET /api/optimize/{task_id} — poll for the result (within 30s)."""
    job = EvaluationJobStore(db).get(task_id, user.org_id)
    if job is None:
        raise HTTPException(status_code=404, detail="task not found")
    return job_response(job)


__all__ = ["OptimizeRequest", "router"]
