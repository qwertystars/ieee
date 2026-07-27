"""Eval API routes — testbed evaluation run and results retrieval.

Wires the DigitalTwinTestbed to API endpoints:
  - POST /run           — generate testbed infrastructure + observation stream
  - GET  /results/{task_id} — retrieve stored evaluation results

Results are stored in an in-memory dict keyed by task_id (ULID). This is
sufficient for single-process demo operation; production would use a DB
table or queue. Task 33 will extend this file with ablation/baselines.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import require_roles
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.user import User

logger = logging.getLogger("app.api.routes.eval")

router = APIRouter(prefix="/eval", tags=["eval"])

_WRITE_ROLES = ("admin", "emergency_manager")

# In-memory result store (single-process demo). Keyed by task_id.
_results: dict[str, dict[str, Any]] = {}


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
) -> dict[str, Any]:
    """Run a testbed evaluation — generates infrastructure + observation stream."""
    from app.eval.testbed import DigitalTwinTestbed
    from app.eval.testbed_types import TestbedParams

    params = TestbedParams(**payload.params) if payload.params else TestbedParams()
    testbed = DigitalTwinTestbed(params=params)
    infra = testbed.generate(seed=payload.seed)
    observations = testbed.generate_observation_stream(
        seed=payload.seed + 1, duration_hours=payload.duration_hours,
    )
    fingerprint = testbed.fingerprint()

    task_id = generate_ulid()
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
    _results[task_id] = result
    return result


@router.get("/results/{task_id}")
def get_eval_results(
    task_id: str,
    user: User = Depends(require_roles()),
) -> dict[str, Any]:
    """Retrieve stored evaluation results by task_id."""
    result = _results.get(task_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"eval task not found: {task_id}",
        )
    return result


def _count_by_source(observations: list[Any]) -> dict[str, int]:
    """Count observations by source type."""
    counts: dict[str, int] = {}
    for obs in observations:
        key = obs.source_type.value
        counts[key] = counts.get(key, 0) + 1
    return counts
