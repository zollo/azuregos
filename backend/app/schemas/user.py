"""User & auth schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import AuthProvider, UserRole

_DISPLAY_NAME = "Name shown in the UI and on ADO comments."
_ROLE = (
    "super_admin > admin > portal_admin > end_user. Only a super admin can grant super_admin."
)
_PASSWORD = "Password for local sign-in."
_PORTAL_IDS = "IDs of the portals a portal_admin manages; ignored for other roles."


class UserBase(BaseModel):
    email: EmailStr = Field(description="Sign-in email address; it can't be changed later.")
    display_name: str = Field(default="", description=_DISPLAY_NAME)
    role: UserRole = Field(default=UserRole.end_user, description=_ROLE)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128, description=_PASSWORD)
    portal_ids: list[uuid.UUID] = Field(default=[], description=_PORTAL_IDS)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: AuthProvider
    is_active: bool
    created_at: datetime
    portal_ids: list[uuid.UUID] = []


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, description=_DISPLAY_NAME)
    role: UserRole | None = Field(default=None, description=_ROLE)
    is_active: bool | None = Field(
        default=None, description="Whether the account can sign in."
    )
    password: str | None = Field(
        default=None, min_length=8, max_length=128, description=_PASSWORD
    )
    portal_ids: list[uuid.UUID] | None = Field(default=None, description=_PORTAL_IDS)


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
