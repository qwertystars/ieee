"""Auth schemas — Pydantic v2 models for login and token responses."""

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    """Form-encoded login request (username + password)."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response returned after successful login.

    ``refresh_token`` is optional so the same model can be reused for the
    refresh endpoint, which only issues a new access token.
    """

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "access_token": "eyJhbGciOiJIUzI1NiIs...",
            "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
            "token_type": "bearer",
        }
    })

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Request body for POST /api/auth/refresh."""

    refresh_token: str


class UserInfo(BaseModel):
    """Public user information (no password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    org_id: str


__all__ = ["LoginRequest", "RefreshRequest", "TokenResponse", "UserInfo"]
