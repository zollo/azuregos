"""Resolve which OIDC / SAML single sign-on configuration is in effect.

Each provider has two possible sources, exactly like the ADO connection
(``app.services.ado_connection``):

* **database** — settings a super admin saved at ``/admin/sso``.
* **environment** — the ``OIDC_*`` / ``SAML_*`` env vars.

Precedence is per provider: saved settings win and replace that provider's env
vars as a whole, *including* the enabled flag (so the UI can switch off a
provider the env vars turn on). Deleting them reverts to the env vars. Rows are
read on every call, so changes apply without a restart.

A saved secret that can't be decrypted (``SECRET_KEY`` rotated) fails closed:
the provider is reported with an error and its login is refused, rather than
silently falling back to the env vars.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import SecretDecryptionError, decrypt_secret
from app.models.sso_settings import SINGLETON_ID, OidcSettings, SamlSettings

logger = logging.getLogger(__name__)

DEFAULT_OIDC_SCOPES = "openid email profile"
DEFAULT_SP_ENTITY_ID = "azuregos"
DEFAULT_OIDC_LABEL = "Continue with SSO (OIDC)"
DEFAULT_SAML_LABEL = "Continue with SSO (SAML)"
OIDC_CALLBACK_PATH = "/api/auth/oidc/callback"
SAML_ACS_PATH = "/api/auth/saml/acs"


class SettingsSource(StrEnum):
    database = "database"
    environment = "environment"
    none = "none"


def frontend_url() -> str:
    """Where the SPA lives: the first CORS origin. Federated logins land here,
    and the SPA's nginx proxies ``/api`` to the backend, so it's also the base
    for the default callback URLs."""
    origins = settings.cors_origin_list
    return (origins[0] if origins else "http://localhost:8080").rstrip("/")


def default_redirect_uri() -> str:
    return frontend_url() + OIDC_CALLBACK_PATH


def default_acs_url() -> str:
    return frontend_url() + SAML_ACS_PATH


@dataclass
class ResolvedOidc:
    source: SettingsSource
    enabled: bool
    discovery_url: str
    client_id: str
    client_secret: str
    redirect_uri: str  # as configured; may be blank
    scopes: str
    button_label: str
    error: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.discovery_url and self.client_id and self.client_secret)

    @property
    def active(self) -> bool:
        """Offer the login button and accept logins."""
        return self.enabled and self.configured and self.error is None

    @property
    def effective_redirect_uri(self) -> str:
        return self.redirect_uri or default_redirect_uri()

    @property
    def effective_scopes(self) -> str:
        return " ".join(self.scopes.split()) or DEFAULT_OIDC_SCOPES

    @property
    def label(self) -> str:
        return self.button_label or DEFAULT_OIDC_LABEL


@dataclass
class ResolvedSaml:
    source: SettingsSource
    enabled: bool
    metadata_url: str
    sp_entity_id: str
    acs_url: str  # as configured; may be blank
    metadata_xml: str = ""
    sp_x509_cert: str = ""
    sp_private_key: str = ""
    email_attribute: str = ""
    name_attribute: str = ""
    button_label: str = ""
    error: str | None = field(default=None)

    @property
    def configured(self) -> bool:
        return bool(self.metadata_url or self.metadata_xml.strip())

    @property
    def active(self) -> bool:
        return self.enabled and self.configured and self.error is None

    @property
    def effective_acs_url(self) -> str:
        return self.acs_url or default_acs_url()

    @property
    def effective_sp_entity_id(self) -> str:
        return self.sp_entity_id or DEFAULT_SP_ENTITY_ID

    @property
    def label(self) -> str:
        return self.button_label or DEFAULT_SAML_LABEL


# ── OIDC ──────────────────────────────────────────────────────────────────
def env_oidc() -> ResolvedOidc:
    any_set = bool(settings.oidc_enabled or settings.oidc_discovery_url or settings.oidc_client_id)
    return ResolvedOidc(
        source=SettingsSource.environment if any_set else SettingsSource.none,
        enabled=settings.oidc_enabled,
        discovery_url=settings.oidc_discovery_url,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        redirect_uri=settings.oidc_redirect_uri,
        scopes=settings.oidc_scopes,
        button_label="",
    )


async def get_stored_oidc(db: AsyncSession) -> OidcSettings | None:
    return await db.get(OidcSettings, SINGLETON_ID)


def stored_oidc(row: OidcSettings) -> ResolvedOidc:
    secret, error = "", None
    if row.client_secret_encrypted:
        try:
            secret = decrypt_secret(row.client_secret_encrypted)
        except SecretDecryptionError:
            logger.error("Saved OIDC client secret can't be decrypted; was SECRET_KEY changed?")
            error = "The saved client secret can't be decrypted (SECRET_KEY changed?). Re-enter it."
    return ResolvedOidc(
        source=SettingsSource.database,
        enabled=row.enabled,
        discovery_url=row.discovery_url,
        client_id=row.client_id,
        client_secret=secret,
        redirect_uri=row.redirect_uri,
        scopes=row.scopes,
        button_label=row.button_label,
        error=error,
    )


async def resolve_oidc(db: AsyncSession) -> ResolvedOidc:
    row = await get_stored_oidc(db)
    return stored_oidc(row) if row is not None else env_oidc()


# ── SAML ──────────────────────────────────────────────────────────────────
def env_saml() -> ResolvedSaml:
    any_set = bool(settings.saml_enabled or settings.saml_metadata_url)
    return ResolvedSaml(
        source=SettingsSource.environment if any_set else SettingsSource.none,
        enabled=settings.saml_enabled,
        metadata_url=settings.saml_metadata_url,
        sp_entity_id=settings.saml_sp_entity_id,
        acs_url=settings.saml_acs_url,
    )


async def get_stored_saml(db: AsyncSession) -> SamlSettings | None:
    return await db.get(SamlSettings, SINGLETON_ID)


def stored_saml(row: SamlSettings) -> ResolvedSaml:
    key, error = "", None
    if row.sp_private_key_encrypted:
        try:
            key = decrypt_secret(row.sp_private_key_encrypted)
        except SecretDecryptionError:
            logger.error("Saved SAML SP private key can't be decrypted; was SECRET_KEY changed?")
            error = (
                "The saved SP private key can't be decrypted (SECRET_KEY changed?). Re-enter it."
            )
    return ResolvedSaml(
        source=SettingsSource.database,
        enabled=row.enabled,
        metadata_url=row.metadata_url,
        metadata_xml=row.metadata_xml,
        sp_entity_id=row.sp_entity_id,
        acs_url=row.acs_url,
        sp_x509_cert=row.sp_x509_cert,
        sp_private_key=key,
        email_attribute=row.email_attribute,
        name_attribute=row.name_attribute,
        button_label=row.button_label,
        error=error,
    )


async def resolve_saml(db: AsyncSession) -> ResolvedSaml:
    row = await get_stored_saml(db)
    return stored_saml(row) if row is not None else env_saml()
