"""Auth routes — POST /api/auth/login, GET /api/auth/me, POST /api/auth/logout, POST /api/auth/refresh."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.auth.jwt import (
    JWTError,
    PrincipalType,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_token_claims,
)
from app.auth.passwords import verify_password
from app.config import settings
from app.deps import (
    consume_refresh_token,
    get_current_user,
    get_db,
    oauth2_scheme,
    revoke_refresh_family,
    revoke_token,
    store_refresh_token,
)
from app.lib.ulid import generate_ulid
from app.models.user import User
from app.schemas.auth import RefreshRequest, TokenResponse, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_token_pair(user: User, family_id: str | None = None) -> TokenResponse:
    """Issue a human token pair and register its refresh rotation family."""
    access_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    resolved_family_id = family_id or generate_ulid()
    claims = {
        "sub": user.email,
        "role": user.role,
        "org_id": user.org_id,
        "principal_type": PrincipalType.HUMAN.value,
    }
    access_token = create_access_token(data=claims, expires_delta=access_expires)
    refresh_jti = generate_ulid()
    refresh_token = create_refresh_token(
        data={**claims, "jti": refresh_jti, "family_id": resolved_family_id},
        expires_delta=refresh_expires,
    )
    store_refresh_token(
        refresh_jti,
        int(refresh_expires.total_seconds()),
        family_id=resolved_family_id,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


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
    return _issue_token_pair(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Rotate a valid refresh token exactly once into a new token pair."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise credentials_exc from None
    if not validate_token_claims(payload, "refresh", PrincipalType.HUMAN):
        raise credentials_exc
    jti = payload.get("jti")
    if not isinstance(jti, str) or not consume_refresh_token(jti):
        raise credentials_exc
    email = payload.get("sub")
    org_id = payload.get("org_id")
    if not isinstance(email, str) or not isinstance(org_id, str):
        raise credentials_exc
    user = db.query(User).filter(User.email == email, User.org_id == org_id).first()
    if user is None:
        raise credentials_exc
    family_id = payload.get("family_id")
    if not isinstance(family_id, str) or not family_id:
        raise credentials_exc
    return _issue_token_pair(user, family_id=family_id)


@router.get("/me", response_model=UserInfo)
def me(current_user: User = Depends(get_current_user)) -> UserInfo:
    """Return the authenticated user's info (id, email, role, org_id)."""
    return UserInfo.model_validate(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    body: RefreshRequest | None = None,
) -> Response:
    """Revoke the current access credential and optional refresh family."""
    ttl_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = decode_token(token)
    exp = payload.get("exp")
    if exp is not None:
        now = int(datetime.now(UTC).timestamp())
        ttl_seconds = max(int(exp) - now, 0)
    revoke_token(token, ttl_seconds, db=db, org_id=current_user.org_id)
    if body is not None:
        try:
            refresh_payload = decode_token(body.refresh_token)
        except JWTError:
            refresh_payload = {}
        family_id = refresh_payload.get("family_id")
        if (
            validate_token_claims(refresh_payload, "refresh", PrincipalType.HUMAN)
            and isinstance(family_id, str)
            and not revoke_refresh_family(family_id)
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Refresh credential authority unavailable",
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
