"""User model: local + federated (OIDC/SAML) accounts."""
from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    admin = "admin"
    end_user = "end_user"


class AuthProvider(str, enum.Enum):
    local = "local"
    oidc = "oidc"
    saml = "saml"


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_provider_external_id"),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # Null for federated accounts that never set a local password.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.end_user, nullable=False
    )
    provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, name="auth_provider"), default=AuthProvider.local, nullable=False
    )
    # Subject/nameID from the IdP for federated accounts.
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.admin
