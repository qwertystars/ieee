"""Auth schemas — Pydantic v2 models for login and token responses."""

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    """Form-encoded login request (username + password)."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response returned after successful login."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "access_token": "eyJhbGciOiJIUzI1NiIs...",
            "token_type": "bearer",
        }
    })

    access_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    """Public user information (no password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    org_id: str


__all__ = ["LoginRequest", "TokenResponse", "UserInfo"]
