"""Eval routes — GET /api/eval (stub)."""

from fastapi import APIRouter, Depends

from app.deps import require_roles
from app.models.user import User

router = APIRouter(prefix="/eval", tags=["eval"])


@router.get("")
def eval_endpoint(user: User = Depends(require_roles())) -> dict:
    """Evaluation pipeline (stub — real logic comes later)."""
    return {"status": "ok", "endpoint": "eval", "org_id": user.org_id}
