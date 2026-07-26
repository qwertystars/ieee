"""Auth routes — POST /api/auth/login, GET /api/auth/me, POST /api/auth/logout."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.auth.jwt import JWTError, create_access_token, decode_token
from app.auth.passwords import verify_password
from app.config import settings
from app.deps import get_db, get_current_user, oauth2_scheme, revoke_token
from app.models.user import User
from app.schemas.auth import TokenResponse, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate with username (email) + password, receive a JWT."""
    user = db.query(User).filter(User.email == form.username).first()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(
        data={"sub": user.email, "role": user.role, "org_id": user.org_id},
        expires_delta=expires,
    )
    return TokenResponse(access_token=token, token_type="bearer")


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
            now = int(datetime.now(timezone.utc).timestamp())
            ttl_seconds = max(int(exp) - now, 0)
    except JWTError:
        # Token already validated by get_current_user; fall back to default TTL.
        pass
    revoke_token(token, ttl_seconds)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
