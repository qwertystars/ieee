"""Hypotheses routes — GET /api/hypotheses (stub)."""

from fastapi import APIRouter, Depends

from app.deps import require_roles
from app.models.user import User

router = APIRouter(prefix="/hypotheses", tags=["hypotheses"])


@router.get("")
def list_hypotheses(user: User = Depends(require_roles())) -> dict:
    """List hypotheses (stub — real logic comes later)."""
    return {"status": "ok", "endpoint": "hypotheses", "org_id": user.org_id}
