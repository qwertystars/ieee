"""Role-based access control — require_roles dependency factory."""

from collections.abc import Callable, Sequence

from fastapi import Depends, HTTPException, status

from app.deps import get_current_user
from app.models.user import User


def require_roles(*roles: str) -> Callable[..., User]:
    """Return a dependency that checks the current user has one of the given roles.

    If no roles are passed, any authenticated user is allowed.
    """

    def _checker(user: User = Depends(get_current_user)) -> User:
        if roles and user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{user.role}' not allowed; requires one of {list(roles)}",
            )
        return user

    return _checker


def check_roles(user: User, roles: Sequence[str]) -> None:
    """Raise 403 if the user's role is not in the allowed set."""
    if roles and user.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role '{user.role}' not allowed; requires one of {list(roles)}",
        )


__all__ = ["check_roles", "require_roles"]
