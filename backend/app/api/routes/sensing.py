"""Sensing routes — GET /api/sensing (stub)."""

from fastapi import APIRouter, Depends

from app.deps import require_roles
from app.models.user import User

router = APIRouter(prefix="/sensing", tags=["sensing"])


@router.get("")
def sensing(user: User = Depends(require_roles())) -> dict:
    """Sensing pipeline status (stub — real logic comes later)."""
    return {"status": "ok", "endpoint": "sensing", "org_id": user.org_id}
