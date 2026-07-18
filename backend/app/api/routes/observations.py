"""Observations routes — GET /api/observations (stub)."""

from fastapi import APIRouter, Depends

from app.deps import require_roles
from app.models.user import User

router = APIRouter(prefix="/observations", tags=["observations"])


@router.get("")
def list_observations(user: User = Depends(require_roles())) -> dict:
    """List observations (stub — real logic comes later)."""
    return {"status": "ok", "endpoint": "observations", "org_id": user.org_id}
