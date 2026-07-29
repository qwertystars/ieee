"""FastAPI dependency providers."""

import hashlib
import logging
import threading
from collections.abc import Generator
from enum import Enum
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.jwt import JWTError, decode_token
from app.config import settings
from app.db import SessionLocal
from app.models.user import User

logger = logging.getLogger("app.deps")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)

REVOKED_TOKENS_KEY = "revoked_tokens"
REFRESH_TOKEN_PREFIX = "refresh_token:"
_redis_client: Any = None
_local_revoked_tokens: set[str] = set()
_local_revoked_lock = threading.Lock()


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
    except Exception as exc:
        logger.warning("Redis unavailable (denylist disabled): %s", exc)
        _redis_client = None
    return _redis_client


def _hash_token(token: str) -> str:
    """Return the SHA256 hex digest of a token string."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_token_revoked(token: str) -> bool:
    """Return True if token is revoked (local cache or Redis denylist).

    Checks the in-memory local cache first (survives Redis outages), then
    falls back to Redis. Returns False (fail-open) when Redis is down and
    the token is not in the local cache.
    """
    token_hash = _hash_token(token)
    with _local_revoked_lock:
        if token_hash in _local_revoked_tokens:
            return True
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(client.sismember(REVOKED_TOKENS_KEY, token_hash))
    except Exception as exc:
        logger.warning("Redis denylist check failed: %s", exc)
        return False


def check_sensitive_operation(token: str, op: SensitiveOperation) -> bool:
    """Return True if the operation should proceed, False if rejected.

    For ADMIN_CHANGE (fail-closed): if Redis is down and the token hash is
    not in the local revocation cache, reject (cannot verify token is not
    revoked). Otherwise, use is_token_revoked() (proceed if not revoked).

    For fail-open ops: use is_token_revoked() (proceed if not revoked,
    fail-open when Redis is down and token is not in local cache).
    """
    if op is SensitiveOperation.ADMIN_CHANGE:
        token_hash = _hash_token(token)
        with _local_revoked_lock:
            in_local = token_hash in _local_revoked_tokens
        if get_redis() is None and not in_local:
            logger.warning(
                "Admin change rejected (fail-closed): Redis down, token not in local cache"
            )
            return False
        return not is_token_revoked(token)
    return not is_token_revoked(token)


def revoke_token(token: str, ttl_seconds: int) -> None:
    """Add token hash to the Redis denylist with TTL and to the local cache.

    Best-effort if Redis is down — the local cache is always updated.
    """
    token_hash = _hash_token(token)
    with _local_revoked_lock:
        _local_revoked_tokens.add(token_hash)
    client = get_redis()
    if client is None:
        logger.warning("Redis unavailable — revocation skipped (best-effort, local cache updated)")
        return
    try:
        client.sadd(REVOKED_TOKENS_KEY, token_hash)
        if ttl_seconds > 0:
            client.expire(REVOKED_TOKENS_KEY, ttl_seconds)
    except Exception as exc:
        logger.warning("Redis revoke failed: %s", exc)


def _populate_local_cache_from_redis() -> None:
    """Best-effort load all revoked token hashes from Redis into the local cache."""
    client = get_redis()
    if client is None:
        return
    try:
        members = client.smembers(REVOKED_TOKENS_KEY)
        with _local_revoked_lock:
            for member in members:
                if isinstance(member, bytes):
                    member = member.decode("utf-8", errors="replace")
                _local_revoked_tokens.add(member)
    except Exception as exc:
        logger.warning("Failed to populate local revocation cache: %s", exc)


# Best-effort: populate local cache from Redis on module import.
_populate_local_cache_from_redis()


def store_refresh_token(jti: str, ttl_seconds: int) -> None:
    """Store a refresh token JTI in Redis with TTL. Best-effort if Redis is down."""
    client = get_redis()
    if client is None:
        logger.warning("Redis unavailable — refresh credential storage skipped")
        return
    try:
        client.set(REFRESH_TOKEN_PREFIX + jti, "1", ex=ttl_seconds)
    except Exception as exc:
        logger.warning("Redis refresh credential store failed: %s", exc)


def is_refresh_token_valid(jti: str) -> bool:
    """Check whether a refresh token JTI exists in Redis.

    Returns True (fail-open) when Redis is unavailable so that refresh
    still works during Redis outages.
    """
    client = get_redis()
    if client is None:
        return True
    try:
        return bool(client.exists(REFRESH_TOKEN_PREFIX + jti))
    except Exception as exc:
        logger.warning("Redis refresh credential check failed: %s", exc)
        return True


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
    if is_token_revoked(token):
        raise credentials_exc
    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exc
    email = payload.get("sub")
    if email is None:
        raise credentials_exc
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exc
    return user


# Re-export require_roles for convenience. Imported here (after get_current_user
# is defined) to avoid a circular import with app.auth.roles.
from app.auth.roles import require_roles

__all__ = [
    "SensitiveOperation",
    "check_sensitive_operation",
    "get_current_user",
    "get_db",
    "get_redis",
    "is_refresh_token_valid",
    "is_token_revoked",
    "oauth2_scheme",
    "require_roles",
    "revoke_token",
    "store_refresh_token",
]
