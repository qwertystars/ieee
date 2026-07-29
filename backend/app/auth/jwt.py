"""JWT creation and verification using python-jose (HS256)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.config import settings


def create_access_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    """Create a signed access JWT with the given claims and expiration."""
    to_encode = dict(data)
    to_encode["type"] = "access"
    to_encode["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    """Create a signed refresh JWT with the given claims and expiration.

    Distinguished from access tokens by the ``type: refresh`` claim.
    """
    to_encode = dict(data)
    to_encode["type"] = "refresh"
    to_encode["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises JWTError on invalid/expired tokens."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


__all__ = ["JWTError", "create_access_token", "create_refresh_token", "decode_token"]
