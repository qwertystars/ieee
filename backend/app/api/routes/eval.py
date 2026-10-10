"""Eval API routes — testbed evaluation run and results retrieval.

Wires the DigitalTwinTestbed to API endpoints:
  - POST /run           — generate testbed infrastructure + observation stream
  - GET  /results/{task_id} — retrieve stored evaluation results

Evaluation job state and results are stored in PostgreSQL rows keyed by the
organization-scoped ULID task_id, so reads converge across backend instances
and survive process restart. Task 33 extends this file with ablation/baselines.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import get_db, require_roles
from app.eval.jobs import EvaluationJobStore, job_response
from app.lib.time import now_ms
from app.models.user import User

logger = logging.getLogger("app.api.routes.eval")

router = APIRouter(prefix="/eval", tags=["eval"])

_WRITE_ROLES = ("admin", "emergency_manager")

class EvalRunRequest(BaseModel):
    """Request body for POST /eval/run."""

    seed: int = Field(default=42, ge=0, description="Deterministic seed")
    duration_hours: int = Field(default=6, ge=1, le=168)
    params: dict[str, Any] | None = Field(
        default=None, description="Override TestbedParams fields"
    )


@router.post("/run")
def run_eval(
    payload: EvalRunRequest,
    user: User = Depends(require_roles(*_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run a testbed evaluation — generates infrastructure + observation stream."""
    from app.eval.testbed import DigitalTwinTestbed
    from app.eval.testbed_types import TestbedParams

    store = EvaluationJobStore(db)
    job = store.create(
        user.org_id,
        user.id,
        "eval",
        {"seed": payload.seed, "duration_hours": payload.duration_hours, "params": payload.params or {}},
    )
    params = TestbedParams(**payload.params) if payload.params else TestbedParams()
    testbed = DigitalTwinTestbed(params=params)
    infra = testbed.generate(seed=payload.seed)
    observations = testbed.generate_observation_stream(
        seed=payload.seed + 1, duration_hours=payload.duration_hours,
    )
    fingerprint = testbed.fingerprint()

    task_id = job.id
    result: dict[str, Any] = {
        "task_id": task_id,
        "status": "completed",
        "seed": payload.seed,
        "duration_hours": payload.duration_hours,
        "fingerprint": fingerprint,
        "infrastructure_summary": {
            "buildings": len(infra.buildings),
            "roads": len(infra.roads.edges),
            "hospitals": len(infra.hospitals),
            "shelters": len(infra.shelters),
            "population_hexes": len(infra.population),
            "substations": len(infra.substations),
            "cell_towers": len(infra.cell_towers),
            "responder_stations": len(infra.responder_stations),
            "citizen_devices": len(infra.citizen_devices),
        },
        "observation_count": len(observations),
        "observation_sources": _count_by_source(observations),
        "params": payload.params or {},
        "created_at": now_ms(),
        "created_by": user.email,
    }
    store.complete(task_id, user.org_id, result)
    return result


@router.get("/results/{task_id}")
def get_eval_results(
    task_id: str,
    user: User = Depends(require_roles()),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve stored evaluation results by task_id."""
    job = EvaluationJobStore(db).get(task_id, user.org_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"eval task not found: {task_id}",
        )
    return job_response(job)


def _count_by_source(observations: list[Any]) -> dict[str, int]:
    """Count observations by source type."""
    counts: dict[str, int] = {}
    for obs in observations:
        key = obs.source_type.value
        counts[key] = counts.get(key, 0) + 1
    return counts


# ── Ablation study (T45) ────────────────────────────────────────────────────


class AblationRequest(BaseModel):
    """Request body for POST /eval/ablation."""

    seed: int = Field(default=42, ge=0, description="Deterministic seed")
    ablation_types: list[str] | None = Field(
        default=None,
        description="Subset of ablation types to run; None = all 9 + full_system",
    )


@router.post("/ablation")
def run_ablation(
    payload: AblationRequest,
    user: User = Depends(require_roles(*_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """POST /eval/ablation — run ablation study removing one component at a time.

    Runs the full system + 9 ablations (each removing one component) on the
    same testbed seed. Returns per-ablation metrics and a comparison table.
    """
    from app.eval.ablation import ABLATION_TYPES, AblationRunner
    from app.eval.testbed import DigitalTwinTestbed
    from app.eval.testbed_types import TestbedParams

    store = EvaluationJobStore(db)
    job = store.create(user.org_id, user.id, "ablation", {"seed": payload.seed})
    testbed = DigitalTwinTestbed(params=TestbedParams())
    testbed.generate(seed=payload.seed)
    runner = AblationRunner()

    if payload.ablation_types is None:
        results = runner.run_all_ablations(testbed, seed=payload.seed)
    else:
        results = {"full_system": runner.run_ablation("full_system", testbed, payload.seed)}
        for at in payload.ablation_types:
            if at in ABLATION_TYPES:
                results[at] = runner.run_ablation(at, testbed, payload.seed)

    comparison = runner.compare_ablations(results)
    significant = runner.get_significant_ablations(results)

    response = {
        "task_id": job.id,
        "status": "completed",
        "seed": payload.seed,
        "ablation_count": len(results),
        "results": {
            key: {
                "ablation_type": r.ablation_type,
                "components_disabled": list(r.components_disabled),
                "metrics": {
                    "prevented_harm": r.metrics.prevented_harm,
                    "response_time_ms": r.metrics.response_time_ms,
                    "coverage": r.metrics.coverage,
                    "actions_taken": r.metrics.actions_taken,
                    "high_severity_events": r.metrics.high_severity_events,
                },
                "actions_count": len(r.actions),
            }
            for key, r in results.items()
        },
        "comparison_table": comparison,
        "significant_ablations": significant,
        "created_at": now_ms(),
        "created_by": user.email,
    }
    store.complete(job.id, user.org_id, response)
    return response


# ── Baselines comparison (T43) ──────────────────────────────────────────────


class BaselinesRequest(BaseModel):
    """Request body for POST /eval/baselines."""

    seed: int = Field(default=42, ge=0, description="Deterministic seed")


@router.post("/baselines")
def run_baselines(
    payload: BaselinesRequest,
    user: User = Depends(require_roles(*_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """POST /eval/baselines — run 4-baseline comparison on the same testbed.

    Runs all 4 baselines (independent dashboards, unified visualization,
    current ResQNet, ResQNet-SAGE) on the same seed and returns per-baseline
    metrics with a comparison table.
    """
    from app.eval.baselines import BaselineRunner
    from app.eval.testbed import DigitalTwinTestbed
    from app.eval.testbed_types import TestbedParams

    store = EvaluationJobStore(db)
    job = store.create(user.org_id, user.id, "baselines", {"seed": payload.seed})
    testbed = DigitalTwinTestbed(params=TestbedParams())
    testbed.generate(seed=payload.seed)
    runner = BaselineRunner()
    results = runner.run_all_baselines(testbed, seed=payload.seed)
    comparison = runner.compare_baselines(results)

    response = {
        "task_id": job.id,
        "status": "completed",
        "seed": payload.seed,
        "baseline_count": len(results),
        "results": {
            key: {
                "name": r.name,
                "uses_fusion": r.uses_fusion,
                "selection_policy": r.selection_policy,
                "metrics": {
                    "prevented_harm": r.metrics.prevented_harm,
                    "response_time_ms": r.metrics.response_time_ms,
                    "coverage": r.metrics.coverage,
                    "actions_taken": r.metrics.actions_taken,
                    "high_severity_events": r.metrics.high_severity_events,
                },
                "actions_count": len(r.actions),
            }
            for key, r in results.items()
        },
        "comparison_table": comparison,
        "created_at": now_ms(),
        "created_by": user.email,
    }
    store.complete(job.id, user.org_id, response)
    return response
