"""Admin-configured single sign-on settings (override the OIDC_* / SAML_* env vars).

One singleton row per provider (``id`` is always 1). Like the ADO connection, a
saved row replaces that provider's environment configuration as a whole,
including whether it is enabled; deleting it reverts to the env vars. Secrets
(the OIDC client secret, the SAML SP private key) are encrypted at rest with
``app.core.security.encrypt_secret`` and never returned by the API.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin

SINGLETON_ID = 1


class OidcSettings(TimestampMixin, Base):
    __tablename__ = "oidc_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_ID)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    discovery_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    client_id: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    client_secret_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Blank = derived from the first CORS origin (``<origin>/api/auth/oidc/callback``).
    redirect_uri: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    scopes: Mapped[str] = mapped_column(
        String(500), default="openid email profile", nullable=False
    )
    button_label: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SamlSettings(TimestampMixin, Base):
    __tablename__ = "saml_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_ID)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # The IdP: its metadata URL, or pasted metadata XML (used when the URL is blank).
    metadata_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    metadata_xml: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sp_entity_id: Mapped[str] = mapped_column(String(500), default="azuregos", nullable=False)
    # Blank = derived from the first CORS origin (``<origin>/api/auth/saml/acs``).
    acs_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    # Optional SP signing pair; with it, AuthnRequests are signed.
    sp_x509_cert: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sp_private_key_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Blank = the built-in fallbacks (email / emailaddress claim / NameID, displayName).
    email_attribute: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    name_attribute: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    button_label: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
