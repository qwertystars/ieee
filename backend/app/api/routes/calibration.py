from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.routes.calibration_helpers import fit_samples, list_contracts, store_samples
from app.deps import get_current_user, get_db
from app.models.user import User

router = APIRouter(prefix="/incidents/{incident_id}/calibration", tags=["calibration"])


@router.post("/data", status_code=status.HTTP_201_CREATED)
def store_calibration_data(
    incident_id: str,
    request: Request,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return store_samples(db, incident_id, request.state.org_id or "", payload)


@router.post("/fit")
def fit_calibration(
    incident_id: str,
    request: Request,
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return fit_samples(db, incident_id, request.state.org_id or "", payload)


@router.get("/contracts")
def get_calibration_contracts(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return list_contracts(db, request.state.org_id or "", incident_id)
