"""Scenarios routes — GET /api/scenarios (stub)."""

from fastapi import APIRouter, Depends

from app.deps import require_roles
from app.models.user import User

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("")
def list_scenarios(user: User = Depends(require_roles())) -> dict:
    """List scenarios (stub — real logic comes later)."""
    return {"status": "ok", "endpoint": "scenarios", "org_id": user.org_id}
