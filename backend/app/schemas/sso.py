"""Schemas for single sign-on: the login-page provider list and the
super-admin OIDC / SAML settings."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class AuthProviders(BaseModel):
    """Which login buttons the login page shows."""

    local: bool = True
    oidc: bool
    saml: bool
    oidc_label: str
    saml_label: str


def _http_url(v: str) -> str:
    v = v.strip()
    if not v:
        return v
    parsed = urlparse(v)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Must be an http(s) URL")
    return v


class _Stripped(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


# ── OIDC ──────────────────────────────────────────────────────────────────
class OidcSettingsWrite(_Stripped):
    """Save (or test) OIDC settings. A blank/omitted ``client_secret`` keeps the
    saved one. Required fields are only enforced when ``enabled``."""

    enabled: bool = False
    discovery_url: str = Field(default="", max_length=500)
    client_id: str = Field(default="", max_length=500)
    client_secret: str | None = Field(default=None, max_length=2000)
    redirect_uri: str = Field(default="", max_length=500)
    scopes: str = Field(default="openid email profile", max_length=500)
    button_label: str = Field(default="", max_length=100)

    @field_validator("discovery_url", "redirect_uri")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return _http_url(v)

    @field_validator("scopes")
    @classmethod
    def _check_scopes(cls, v: str) -> str:
        v = " ".join(v.split())
        if v and "openid" not in v.split():
            raise ValueError("Scopes must include 'openid'")
        return v


class OidcSettingsValues(BaseModel):
    """Non-secret values. The client secret itself is never returned."""

    enabled: bool
    discovery_url: str
    client_id: str
    client_secret_set: bool
    redirect_uri: str
    scopes: str
    button_label: str = ""


class OidcStoredSettings(OidcSettingsValues):
    updated_at: datetime
    updated_by: str | None = None


class OidcSettingsStatus(BaseModel):
    # "database" (saved in the UI) wins over "environment" (OIDC_* env vars);
    # "none" when neither has anything set.
    source: str
    enabled: bool  # the login button is shown and logins are accepted
    configured: bool
    stored: OidcStoredSettings | None
    environment: OidcSettingsValues
    # What to register with the IdP as the redirect URI.
    effective_redirect_uri: str
    default_redirect_uri: str
    error: str | None = None


class OidcTestResult(BaseModel):
    ok: bool
    issuer: str | None = None
    authorization_endpoint: str | None = None
    error: str | None = None


# ── SAML ──────────────────────────────────────────────────────────────────
class SamlSettingsWrite(_Stripped):
    """Save (or test) SAML settings. A blank/omitted ``sp_private_key`` keeps
    the saved one; clearing ``sp_x509_cert`` drops the key too."""

    enabled: bool = False
    metadata_url: str = Field(default="", max_length=500)
    metadata_xml: str = Field(default="", max_length=200_000)
    sp_entity_id: str = Field(default="azuregos", max_length=500)
    acs_url: str = Field(default="", max_length=500)
    sp_x509_cert: str = Field(default="", max_length=20_000)
    sp_private_key: str | None = Field(default=None, max_length=20_000)
    email_attribute: str = Field(default="", max_length=500)
    name_attribute: str = Field(default="", max_length=500)
    button_label: str = Field(default="", max_length=100)

    @field_validator("metadata_url", "acs_url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return _http_url(v)


class SamlSettingsValues(BaseModel):
    enabled: bool
    metadata_url: str
    metadata_xml: str = ""
    sp_entity_id: str
    acs_url: str
    sp_x509_cert: str = ""
    sp_private_key_set: bool = False
    email_attribute: str = ""
    name_attribute: str = ""
    button_label: str = ""


class SamlStoredSettings(SamlSettingsValues):
    updated_at: datetime
    updated_by: str | None = None


class SamlSettingsStatus(BaseModel):
    source: str
    enabled: bool
    configured: bool
    stored: SamlStoredSettings | None
    environment: SamlSettingsValues
    # What to register with the IdP.
    effective_acs_url: str
    effective_sp_entity_id: str
    default_acs_url: str
    error: str | None = None


class SamlTestResult(BaseModel):
    ok: bool
    idp_entity_id: str | None = None
    sso_url: str | None = None
    error: str | None = None
