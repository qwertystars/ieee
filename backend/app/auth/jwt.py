"""JWT creation, identity claims, and verification primitives."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final

from jose import JWTError, jwt

from app.config import settings
from app.lib.ulid import generate_ulid

HUMAN_SCOPE: Final = "api:read api:write"


class PrincipalType(StrEnum):
    """Closed set of credentials accepted by the platform."""

    HUMAN = "human"
    DEVICE = "device"
    SERVICE = "service"


def _audience_for(principal_type: str) -> str:
    """Resolve the audience for a principal without accepting arbitrary audiences."""
    if principal_type == PrincipalType.DEVICE:
        return settings.DEVICE_ACCESS_AUDIENCE
    if principal_type == PrincipalType.SERVICE:
        return settings.SERVICE_ACCESS_AUDIENCE
    return settings.HUMAN_ACCESS_AUDIENCE


def _scope_for(data: dict[str, Any], principal_type: str) -> str:
    scope = data.get("scope")
    if isinstance(scope, str) and scope.strip():
        return " ".join(scope.split())
    if isinstance(scope, (list, tuple, set)):
        values = [item for item in scope if isinstance(item, str) and item]
        if values:
            return " ".join(values)
    if principal_type == PrincipalType.HUMAN:
        return HUMAN_SCOPE
    return "identity:access"


def _base_claims(data: dict[str, Any], token_type: str) -> dict[str, Any]:
    """Apply mandatory identity, audience, issuer, and lifetime metadata."""
    to_encode = dict(data)
    principal_type = str(to_encode.get("principal_type", PrincipalType.HUMAN))
    if principal_type not in {member.value for member in PrincipalType}:
        principal_type = PrincipalType.HUMAN
    now = datetime.now(UTC)
    to_encode["principal_type"] = principal_type
    to_encode["type"] = token_type
    to_encode["iss"] = settings.JWT_ISSUER
    to_encode["aud"] = (
        settings.REFRESH_TOKEN_AUDIENCE
        if token_type == "refresh"
        else _audience_for(principal_type)
    )
    to_encode["scope"] = _scope_for(to_encode, principal_type)
    to_encode.setdefault("jti", generate_ulid())
    to_encode["iat"] = now
    to_encode["nbf"] = now
    return to_encode


def create_access_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    """Create a signed access JWT with explicit principal claims."""
    to_encode = _base_claims(data, "access")
    to_encode["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    """Create a signed refresh JWT with a distinct refresh audience."""
    to_encode = _base_claims(data, "refresh")
    to_encode["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_device_access_token(
    subject: str,
    org_id: str,
    scopes: tuple[str, ...],
) -> str:
    """Create a short-lived device credential provisioned out of band."""
    return create_access_token(
        {
            "sub": subject,
            "org_id": org_id,
            "principal_type": PrincipalType.DEVICE,
            "scope": scopes,
        },
        timedelta(minutes=settings.DEVICE_ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_service_access_token(
    subject: str,
    org_id: str,
    scopes: tuple[str, ...],
) -> str:
    """Create a short-lived service credential provisioned out of band."""
    return create_access_token(
        {
            "sub": subject,
            "org_id": org_id,
            "principal_type": PrincipalType.SERVICE,
            "scope": scopes,
        },
        timedelta(minutes=settings.SERVICE_ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def validate_token_claims(
    payload: dict[str, Any],
    token_type: str,
    principal_type: PrincipalType,
    required_scope: str | None = None,
) -> bool:
    """Validate the non-cryptographic identity contract for a decoded token."""
    if payload.get("type") != token_type:
        return False
    if payload.get("principal_type") != principal_type.value:
        return False
    expected_audience = (
        settings.REFRESH_TOKEN_AUDIENCE
        if token_type == "refresh"
        else _audience_for(principal_type.value)
    )
    if payload.get("aud") != expected_audience:
        return False
    if not isinstance(payload.get("sub"), str) or not isinstance(
        payload.get("org_id"), str
    ):
        return False
    if not isinstance(payload.get("jti"), str) or not payload["jti"]:
        return False
    if required_scope is None:
        return True
    scope = payload.get("scope")
    return isinstance(scope, str) and required_scope in scope.split()


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT without logging token material."""
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        options={"verify_aud": False},
    )


__all__ = [
    "JWTError",
    "PrincipalType",
    "create_access_token",
    "create_device_access_token",
    "create_refresh_token",
    "create_service_access_token",
    "decode_token",
    "validate_token_claims",
]
