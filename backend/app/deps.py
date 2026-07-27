"""FastAPI dependency providers."""

import logging
from collections.abc import Generator
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
_redis_client: Any = None


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


def is_token_revoked(token: str) -> bool:
    """Return True if token is in the Redis denylist. False if Redis is down."""
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(client.sismember(REVOKED_TOKENS_KEY, token))
    except Exception as exc:
        logger.warning("Redis denylist check failed: %s", exc)
        return False


def revoke_token(token: str, ttl_seconds: int) -> None:
    """Add token to the Redis denylist with TTL. Best-effort if Redis is down."""
    client = get_redis()
    if client is None:
        logger.warning("Redis unavailable — revocation skipped (best-effort)")
        return
    try:
        client.sadd(REVOKED_TOKENS_KEY, token)
        if ttl_seconds > 0:
            client.expire(REVOKED_TOKENS_KEY, ttl_seconds)
    except Exception as exc:
        logger.warning("Redis revoke failed: %s", exc)


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
    "get_current_user",
    "get_db",
    "get_redis",
    "is_token_revoked",
    "oauth2_scheme",
    "require_roles",
    "revoke_token",
]
