"""User schemas (DESIGN §5)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole
from app.schemas.common import ORMBase


class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: UserRole = UserRole.viewer
    organization: str | None = None
    phone: str | None = None
    status: str = "active"


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    name: str | None = None
    role: UserRole | None = None
    organization: str | None = None
    phone: str | None = None
    status: str | None = None
    password: str | None = None


class UserRead(ORMBase):
    id: uuid.UUID
    name: str
    email: EmailStr
    role: UserRole
    organization: str | None = None
    phone: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
