"""User model: local + federated (OIDC/SAML) accounts, and their roles.

Roles, highest first:

- ``super_admin``: everything, including the Azure DevOps connection and
  granting ``super_admin``.
- ``admin``: portals, categories, the ticket queue and users, but can't grant
  ``super_admin`` or change a super admin's account.
- ``portal_admin``: edits only the portals assigned to them (``portal_admins``)
  and sees those portals' tickets.
- ``end_user``: submits and tracks their own tickets.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    portal_admin = "portal_admin"
    end_user = "end_user"


# Higher outranks lower; a non-super admin may grant roles up to their own.
ROLE_RANK = {
    UserRole.end_user: 0,
    UserRole.portal_admin: 1,
    UserRole.admin: 2,
    UserRole.super_admin: 3,
}


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

    # Portals a portal admin may edit. Loaded with the user (it's only ids).
    portal_assignments: Mapped[list["PortalAdmin"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.super_admin

    @property
    def is_admin(self) -> bool:
        """Full admin: every portal and ticket (admin or super admin)."""
        return self.role in (UserRole.admin, UserRole.super_admin)

    @property
    def is_staff(self) -> bool:
        """Any admin role, i.e. may open the admin area."""
        return self.role != UserRole.end_user

    @property
    def portal_ids(self) -> list[uuid.UUID]:
        return [a.portal_id for a in self.portal_assignments]

    def can_manage_portal(self, portal_id: uuid.UUID) -> bool:
        if self.is_admin:
            return True
        return self.role == UserRole.portal_admin and portal_id in self.portal_ids

    def can_grant(self, role: UserRole) -> bool:
        """Whether this user may give ``role`` to someone."""
        if self.is_super_admin:
            return True
        return self.is_admin and ROLE_RANK[role] <= ROLE_RANK[self.role]

    def can_manage_user(self, other: User) -> bool:
        """Whether this user may edit or delete ``other``'s account."""
        if self.is_super_admin:
            return True
        return self.is_admin and not other.is_super_admin


class PortalAdmin(Base):
    """Assigns a portal admin to a portal they may edit."""

    __tablename__ = "portal_admins"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    portal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portals.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
