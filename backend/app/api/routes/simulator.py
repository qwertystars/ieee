"""Simulator API routes — start/stop/status/inject-fault for the simulation engine.

Exposes the ``SimulationEngine`` via a REST API. Start/stop/inject-fault require
``admin`` or ``emergency_manager`` roles; status is available to any
authenticated user. A module-level singleton engine serves all requests.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import require_roles
from app.models.user import User
from app.simulator.engine import SimulationEngine

router = APIRouter(prefix="/simulator", tags=["simulator"])

# Module-level singleton engine.
_engine = SimulationEngine(seed=42)


class StartRequest(BaseModel):
    """Request body for POST /api/simulator/start."""

    org_id: str
    incident_id: str
    device_count: int = Field(default=2, ge=1, le=10)
    seed: int = 42


class InjectFaultRequest(BaseModel):
    """Request body for POST /api/simulator/inject-fault."""

    device_id: str
    fault_type: str
    kwargs: dict = Field(default_factory=dict)


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
def start_simulation(
    req: StartRequest,
    user: User = Depends(require_roles("admin", "emergency_manager")),
) -> dict:
    """Start the simulation. Returns 202 with device IDs."""
    _engine._seed = req.seed
    try:
        device_ids = _engine.start(req.org_id, req.incident_id, req.device_count)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"device_ids": device_ids, "seed": req.seed, "started_by": user.email}


@router.post("/stop", status_code=status.HTTP_204_NO_CONTENT)
async def stop_simulation(
    user: User = Depends(require_roles("admin", "emergency_manager")),
) -> None:
    """Stop the simulation. Returns 204 No Content."""
    await _engine.stop()


@router.get("/status")
def get_status(user: User = Depends(require_roles())) -> dict:
    """Return the current simulation state."""
    return _engine.status()


@router.post("/inject-fault", status_code=status.HTTP_202_ACCEPTED)
def inject_fault(
    req: InjectFaultRequest,
    user: User = Depends(require_roles("admin", "emergency_manager")),
) -> dict:
    """Inject a fault into a device. Returns 202 with the fault details."""
    try:
        _engine.inject_fault(req.device_id, req.fault_type, **req.kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "device_id": req.device_id,
        "fault_type": req.fault_type,
        "injected_by": user.email,
    }


__all__ = ["router"]
