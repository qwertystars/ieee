"""Simulator API routes — start/stop/status/inject-fault for the simulation engine.

Exposes the ``SimulationEngine`` via a REST API. Start/stop/inject-fault require
``admin`` or ``emergency_manager`` roles; status is available to any
authenticated user. Each organization has its own simulation engine.
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import SessionLocal
from app.deps import require_roles
from app.lib.audit import write_audit
from app.models.incident import Incident
from app.models.user import User
from app.simulator.engine import SimulationEngine

router = APIRouter(prefix="/simulator", tags=["simulator"])

# Organization-scoped engines.
_engines: dict[str, SimulationEngine] = {}


def _engine_for(user: User) -> SimulationEngine:
    if user.org_id not in _engines:
        _engines[user.org_id] = SimulationEngine(seed=42)
    return _engines[user.org_id]


def _audit(user: User, action: str) -> None:
    engine = _engine_for(user)
    if not engine._incident_id:
        return
    with SessionLocal() as db:
        write_audit(db, org_id=user.org_id, incident_id=engine._incident_id,
            actor=user.email, action=f"simulator.{action}", entity="digital_twin",
            after=engine.status())


def _incident_exists(org_id: str, incident_id: str) -> bool:
    with SessionLocal() as db:
        return db.scalar(select(Incident.id).where(
            Incident.org_id == org_id, Incident.id == incident_id,
        )) is not None


class StartRequest(BaseModel):
    """Request body for POST /api/simulator/start."""

    org_id: str | None = None
    incident_id: str
    device_count: int = Field(default=2, ge=1, le=10)
    seed: int = 42


class InjectFaultRequest(BaseModel):
    """Request body for POST /api/simulator/inject-fault."""

    device_id: str
    fault_type: str
    kwargs: dict = Field(default_factory=dict)


class SpeedRequest(BaseModel):
    speed: float = Field(gt=0, le=20, allow_inf_nan=False)


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
async def start_simulation(
    req: StartRequest,
    user: User = Depends(require_roles("admin", "emergency_manager")),
) -> dict:
    """Start the simulation. Returns 202 with device IDs.

    Async so the engine's ``asyncio.create_task(self._run_loop())`` runs
    inside the FastAPI event loop — a sync ``def`` route executes in a
    threadpool thread with no running loop, which raises
    ``RuntimeError: no running event loop`` and prevents observations from
    being published.
    """
    if req.org_id is not None and req.org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Organization mismatch")
    if not await anyio.to_thread.run_sync(_incident_exists, user.org_id, req.incident_id):
        raise HTTPException(status_code=404, detail="Incident not found")
    engine = _engine_for(user)
    engine._seed = req.seed
    try:
        device_ids = engine.start(user.org_id, req.incident_id, req.device_count)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await anyio.to_thread.run_sync(_audit, user, "start")
    return {"device_ids": device_ids, "seed": req.seed, "started_by": user.email}


@router.post("/stop", status_code=status.HTTP_204_NO_CONTENT)
async def stop_simulation(
    user: User = Depends(require_roles("admin", "emergency_manager")),
) -> None:
    """Stop the simulation. Returns 204 No Content."""
    await _engine_for(user).stop()
    await anyio.to_thread.run_sync(_audit, user, "stop")


@router.get("/status")
def get_status(user: User = Depends(require_roles())) -> dict:
    """Return the current simulation state."""
    return _engine_for(user).status()


@router.post("/pause", status_code=204)
def pause_simulation(user: User = Depends(require_roles("admin", "emergency_manager"))) -> None:
    _engine_for(user).pause()
    _audit(user, "pause")


@router.post("/resume", status_code=204)
def resume_simulation(user: User = Depends(require_roles("admin", "emergency_manager"))) -> None:
    _engine_for(user).resume()
    _audit(user, "resume")


@router.post("/set-speed", status_code=204)
def set_speed(req: SpeedRequest, user: User = Depends(require_roles("admin", "emergency_manager"))) -> None:
    _engine_for(user).set_speed(req.speed)
    _audit(user, "set_speed")


@router.post("/inject-fault", status_code=status.HTTP_202_ACCEPTED)
def inject_fault(
    req: InjectFaultRequest,
    user: User = Depends(require_roles("admin", "emergency_manager")),
) -> dict:
    """Inject a fault into a device. Returns 202 with the fault details."""
    try:
        _engine_for(user).inject_fault(req.device_id, req.fault_type, **req.kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(user, "inject_fault")
    return {
        "device_id": req.device_id,
        "fault_type": req.fault_type,
        "injected_by": user.email,
    }


__all__ = ["router"]
