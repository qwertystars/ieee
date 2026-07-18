"""Optimize routes — GET /api/optimize (stub)."""

from fastapi import APIRouter, Depends

from app.deps import require_roles
from app.models.user import User

router = APIRouter(prefix="/optimize", tags=["optimize"])


@router.get("")
def optimize(user: User = Depends(require_roles())) -> dict:
    """Run optimization (stub — real logic comes later)."""
    return {"status": "ok", "endpoint": "optimize", "org_id": user.org_id}
