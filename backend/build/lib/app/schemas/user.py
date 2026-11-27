"""User & auth schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import AuthProvider, UserRole


class UserBase(BaseModel):
    email: EmailStr
    display_name: str = ""
    role: UserRole = UserRole.end_user


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)
    # Portals a portal admin may edit; ignored for other roles.
    portal_ids: list[uuid.UUID] = []


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: AuthProvider
    is_active: bool
    created_at: datetime
    portal_ids: list[uuid.UUID] = []


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    portal_ids: list[uuid.UUID] | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = ""
