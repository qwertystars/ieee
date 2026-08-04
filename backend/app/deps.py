"""FastAPI dependency providers."""

import hashlib
import logging
from collections.abc import Generator
from enum import Enum
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.jwt import (
    JWTError,
    PrincipalType,
    decode_token,
    validate_token_claims,
)
from app.config import settings
from app.db import SessionLocal
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.coordination import CredentialState
from app.models.user import User

logger = logging.getLogger("app.deps")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)

REVOKED_TOKENS_KEY = "revoked_tokens"
REVOKED_TOKEN_PREFIX = "revoked_token:"
REFRESH_TOKEN_PREFIX = "refresh_token:"
REFRESH_USED_PREFIX = "refresh_used:"
REFRESH_FAMILY_REVOKED_PREFIX = "refresh_family_revoked:"
_redis_client: Any = None


class SensitiveOperation(str, Enum):
    """Sensitive operations with hybrid fail-closed/fail-open policies.

    ADMIN_CHANGE is fail-closed: rejected when Redis is down and the token
    is not in the local revocation cache (cannot verify token is not revoked).
    The fail-open ops proceed during Redis outages, with a break-glass audit.
    """

    ADMIN_CHANGE = "admin_change"
    ALERT_APPROVAL = "alert_approval"
    EMERGENCY_OVERRIDE = "emergency_override"
    OPERATIONAL_DISPATCH = "operational_dispatch"


def get_redis() -> Any | None:
    """Lazy Redis singleton. Returns None if Redis is unreachable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis

        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        client.ping()
        _redis_client = client
    except (OSError, RedisError, TimeoutError, ValueError) as exc:
        logger.warning("Redis unavailable (denylist disabled): %s", exc)
        _redis_client = None
    return _redis_client


def _hash_token(token: str) -> str:
    """Return the SHA256 hex digest of a token string."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_token_revoked(token: str, db: Session | None = None) -> bool:
    """Return True if revocation cannot be verified or is recorded."""
    token_hash = _hash_token(token)
    if db is not None:
        try:
            state = db.execute(
                select(CredentialState).where(
                    CredentialState.credential_hash == token_hash,
                    CredentialState.state.in_(("revoked", "quarantined")),
                    CredentialState.expires_at_ms > now_ms(),
                )
            ).scalar_one_or_none()
        except SQLAlchemyError:
            return True
        if state is not None:
            return True
    client = get_redis()
    if client is None:
        return True
    try:
        result = client.exists(REVOKED_TOKEN_PREFIX + token_hash)
        return result == 1 or result is True
    except (OSError, RedisError, TimeoutError) as exc:
        logger.warning("Redis denylist check failed: %s", exc)
        return True


def is_token_revoked_strict(token: str, db: Session | None = None) -> bool:
    """Return True when revocation is confirmed or cannot be verified."""
    return is_token_revoked(token, db)


def check_sensitive_operation(
    token: str,
    op: SensitiveOperation,
    db: Session | None = None,
) -> bool:
    """Return True if the operation should proceed, False if rejected.

    Every protected operation is denied if the shared revocation authority is
    unavailable or reports the credential as revoked.
    """
    return not is_token_revoked(token, db)


def revoke_token(
    token: str,
    ttl_seconds: int,
    db: Session | None = None,
    org_id: str | None = None,
) -> None:
    """Persist a revocation and publish the same bounded TTL to Redis."""
    token_hash = _hash_token(token)
    expires_at_ms = now_ms() + max(ttl_seconds, 0) * 1000
    if db is not None and ttl_seconds > 0:
        existing = db.execute(
            select(CredentialState).where(CredentialState.credential_hash == token_hash)
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                CredentialState(
                    id=generate_ulid(),
                    org_id=org_id,
                    credential_hash=token_hash,
                    state="revoked",
                    reason="credential revoked",
                    created_at_ms=now_ms(),
                    expires_at_ms=expires_at_ms,
                )
            )
        else:
            existing.state = "revoked"
            existing.expires_at_ms = expires_at_ms
            existing.reason = "credential revoked"
        db.commit()
    client = get_redis()
    if client is None:
        logger.warning("Redis unavailable — protected authorization will fail closed")
        return
    try:
        client.set(REVOKED_TOKEN_PREFIX + token_hash, "1", ex=max(ttl_seconds, 1))
        if ttl_seconds > 0:
            client.expire(REVOKED_TOKEN_PREFIX + token_hash, ttl_seconds)
    except (OSError, RedisError, TimeoutError) as exc:
        logger.warning("Redis revoke failed: %s", exc)


def store_refresh_token(
    jti: str,
    ttl_seconds: int,
    family_id: str | None = None,
) -> None:
    """Store a refresh JTI and its family with a bounded TTL."""
    client = get_redis()
    if client is None:
        logger.warning("Redis unavailable — refresh credential storage skipped")
        return
    try:
        client.set(REFRESH_TOKEN_PREFIX + jti, family_id or jti, ex=ttl_seconds)
    except (OSError, RedisError, TimeoutError) as exc:
        logger.warning("Redis refresh credential store failed: %s", exc)


def is_refresh_token_valid(jti: str) -> bool:
    """Check whether a refresh token JTI exists in Redis.

    Returns False when Redis is unavailable so refresh cannot bypass the
    shared credential authority.
    """
    client = get_redis()
    if client is None:
        return False
    try:
        family = client.get(REFRESH_TOKEN_PREFIX + jti)
        if family in (None, "", b""):
            return False
        if isinstance(family, bytes):
            family = family.decode("utf-8")
        return not bool(client.exists(REFRESH_FAMILY_REVOKED_PREFIX + str(family)))
    except (OSError, RedisError, TimeoutError) as exc:
        logger.warning("Redis refresh credential check failed: %s", exc)
        return False


def consume_refresh_token(jti: str) -> bool:
    """Atomically consume a refresh JTI and quarantine its family on replay."""
    client = get_redis()
    if client is None:
        return False
    try:
        family = client.getdel(REFRESH_TOKEN_PREFIX + jti)
        if family in (None, "", b""):
            used_family = client.get(REFRESH_USED_PREFIX + jti)
            if used_family not in (None, "", b""):
                if isinstance(used_family, bytes):
                    used_family = used_family.decode("utf-8")
                client.set(
                    REFRESH_FAMILY_REVOKED_PREFIX + str(used_family),
                    "1",
                    ex=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
                )
            return False
        if isinstance(family, bytes):
            family = family.decode("utf-8")
        family_text = str(family)
        if client.exists(REFRESH_FAMILY_REVOKED_PREFIX + family_text):
            return False
        client.set(
            REFRESH_USED_PREFIX + jti,
            family_text,
            ex=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )
        return True
    except (OSError, RedisError, TimeoutError) as exc:
        logger.warning("Redis refresh credential consume failed: %s", exc)
        return False


def revoke_refresh_family(family_id: str) -> bool:
    """Revoke every refresh credential in a rotation family."""
    client = get_redis()
    if client is None:
        return False
    try:
        client.set(
            REFRESH_FAMILY_REVOKED_PREFIX + family_id,
            "1",
            ex=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )
        return True
    except (OSError, RedisError, TimeoutError) as exc:
        logger.warning("Redis refresh family revoke failed: %s", exc)
        return False


def get_db() -> Generator[Session, None, None]:
    """Yield a database session, closing it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode the JWT Bearer token and return the authenticated User.

    Raises 401 if the token is invalid, expired, revoked, or the user doesn't exist.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if is_token_revoked(token, db):
        raise credentials_exc
    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exc
    if not validate_token_claims(payload, "access", PrincipalType.HUMAN):
        raise credentials_exc
    email = payload.get("sub")
    if email is None:
        raise credentials_exc
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exc
    if payload.get("org_id") != user.org_id:
        raise credentials_exc
    return user


def authenticate_realtime_token(token: str | None, db: Session) -> User:
    """Authenticate an access JWT for realtime and polling endpoints."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None or is_token_revoked_strict(token, db):
        raise credentials_exc
    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exc from None
    if not validate_token_claims(payload, "access", PrincipalType.HUMAN):
        raise credentials_exc
    email = payload.get("sub")
    token_org_id = payload.get("org_id")
    if not isinstance(email, str) or not isinstance(token_org_id, str):
        raise credentials_exc
    user = db.query(User).filter(User.email == email).first()
    if user is None or user.org_id != token_org_id:
        raise credentials_exc
    return user


def get_realtime_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve a realtime principal with fail-closed auth-state checks."""
    return authenticate_realtime_token(token, db)


# Re-export require_roles for convenience. Imported here (after get_current_user
# is defined) to avoid a circular import with app.auth.roles.
from app.auth.roles import require_roles

__all__ = [
    "SensitiveOperation",
    "authenticate_realtime_token",
    "check_sensitive_operation",
    "consume_refresh_token",
    "get_current_user",
    "get_db",
    "get_realtime_user",
    "get_redis",
    "is_refresh_token_valid",
    "is_token_revoked",
    "is_token_revoked_strict",
    "oauth2_scheme",
    "require_roles",
    "revoke_refresh_family",
    "revoke_token",
    "store_refresh_token",
]
