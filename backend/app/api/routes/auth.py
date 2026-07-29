"""Auth routes — POST /api/auth/login, GET /api/auth/me, POST /api/auth/logout, POST /api/auth/refresh."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.auth.jwt import JWTError, create_access_token, create_refresh_token, decode_token
from app.auth.passwords import verify_password
from app.config import settings
from app.deps import (
    get_current_user,
    get_db,
    is_refresh_token_valid,
    oauth2_scheme,
    revoke_token,
    store_refresh_token,
)
from app.lib.ulid import generate_ulid
from app.models.user import User
from app.schemas.auth import RefreshRequest, TokenResponse, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate with username (email) + password, receive access + refresh JWTs."""
    user = db.query(User).filter(User.email == form.username).first()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    claims = {"sub": user.email, "role": user.role, "org_id": user.org_id}
    access_token = create_access_token(data=claims, expires_delta=access_expires)
    jti = generate_ulid()
    refresh_token = create_refresh_token(
        data={**claims, "jti": jti},
        expires_delta=refresh_expires,
    )
    store_refresh_token(jti, int(refresh_expires.total_seconds()))
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest) -> TokenResponse:
    """Exchange a valid refresh token for a new access token."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise credentials_exc
    if payload.get("type") != "refresh":
        raise credentials_exc
    jti = payload.get("jti")
    if jti is not None and not is_refresh_token_valid(jti):
        raise credentials_exc
    email = payload.get("sub")
    if email is None:
        raise credentials_exc
    access_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": email,
            "role": payload.get("role"),
            "org_id": payload.get("org_id"),
        },
        expires_delta=access_expires,
    )
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserInfo)
def me(current_user: User = Depends(get_current_user)) -> UserInfo:
    """Return the authenticated user's info (id, email, role, org_id)."""
    return UserInfo.model_validate(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Revoke the current JWT by adding it to the Redis denylist.

    Best-effort: if Redis is unavailable, logs a warning and still returns 204.
    """
    ttl_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    try:
        payload = decode_token(token)
        exp = payload.get("exp")
        if exp is not None:
            now = int(datetime.now(UTC).timestamp())
            ttl_seconds = max(int(exp) - now, 0)
    except JWTError:
        # Token already validated by get_current_user; fall back to default TTL.
        pass
    revoke_token(token, ttl_seconds)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
