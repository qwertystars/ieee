"""FastAPI dependency providers."""

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.jwt import JWTError, decode_token
from app.db import SessionLocal
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)


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

    Raises 401 if the token is invalid, expired, or the user doesn't exist.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
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
from app.auth.roles import require_roles  # noqa: E402, F401

__all__ = ["get_db", "get_current_user", "oauth2_scheme", "require_roles"]
