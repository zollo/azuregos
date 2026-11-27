"""SAML 2.0 SP helpers built on python3-saml.

The settings come from ``app.services.sso_settings.resolve_saml`` (the admin UI
or the ``SAML_*`` env vars) and are passed in on every call. The IdP is
described by its metadata URL or by pasted metadata XML. When an SP signing
certificate and private key are configured, AuthnRequests are signed and the
SP metadata advertises the certificate.
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.sso_settings import ResolvedSaml

EMAIL_CLAIM = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
NAME_CLAIM = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"


class SAMLError(Exception):
    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        # True when the metadata URL was just unreachable.
        self.transient = transient


def _lazy_imports():
    # Imported lazily so the app boots even if xmlsec native libs are absent
    # in environments where SAML is disabled.
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
        from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
    except ImportError as exc:  # pragma: no cover - depends on native libs
        raise SAMLError(f"SAML support isn't available in this build: {exc}") from exc
    return OneLogin_Saml2_Auth, OneLogin_Saml2_IdPMetadataParser


def parse_idp_metadata(cfg: ResolvedSaml) -> dict[str, Any]:
    """The IdP part of python3-saml's settings, from the URL or the pasted XML."""
    _, parser = _lazy_imports()
    if cfg.metadata_url:
        try:
            data = parser.parse_remote(cfg.metadata_url, timeout=10)
        except SAMLError:
            raise
        except OSError as exc:  # urllib network errors
            raise SAMLError(f"Couldn't fetch the IdP metadata: {exc}", transient=True) from exc
        except Exception as exc:  # noqa: BLE001 - parser raises assorted errors
            raise SAMLError(f"Couldn't read the IdP metadata: {exc}") from exc
    elif cfg.metadata_xml.strip():
        try:
            data = parser.parse(cfg.metadata_xml)
        except Exception as exc:  # noqa: BLE001
            raise SAMLError(f"Couldn't read the IdP metadata XML: {exc}") from exc
    else:
        raise SAMLError("SAML IdP metadata (URL or XML) not configured")
    idp = data.get("idp") or {}
    if not idp.get("entityId") or not (idp.get("singleSignOnService") or {}).get("url"):
        raise SAMLError("The IdP metadata has no entity ID or single sign-on URL")
    return data


def build_settings(cfg: ResolvedSaml) -> dict[str, Any]:
    idp_data = parse_idp_metadata(cfg)
    sp: dict[str, Any] = {
        "entityId": cfg.effective_sp_entity_id,
        "assertionConsumerService": {
            "url": cfg.effective_acs_url,
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
        },
        "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
    }
    signing = bool(cfg.sp_x509_cert and cfg.sp_private_key)
    if signing:
        sp["x509cert"] = cfg.sp_x509_cert
        sp["privateKey"] = cfg.sp_private_key
    saml_settings: dict[str, Any] = {
        "strict": True,
        "debug": settings.env == "development",
        "sp": sp,
        "security": {"authnRequestsSigned": signing},
    }
    saml_settings.update(idp_data)
    return saml_settings


def _prepare_request(request_data: dict[str, Any]) -> dict[str, Any]:
    """Adapt a FastAPI request into python3-saml's expected dict."""
    return {
        "https": "on" if request_data["scheme"] == "https" else "off",
        "http_host": request_data["host"],
        "server_port": request_data.get("port"),
        "script_name": request_data["path"],
        "get_data": request_data["query"],
        "post_data": request_data["form"],
    }


def init_auth(cfg: ResolvedSaml, request_data: dict[str, Any]):
    OneLogin_Saml2_Auth, _ = _lazy_imports()
    return OneLogin_Saml2_Auth(_prepare_request(request_data), build_settings(cfg))


def login_redirect_url(cfg: ResolvedSaml, request_data: dict[str, Any]) -> str:
    auth = init_auth(cfg, request_data)
    return auth.login()


def process_acs(cfg: ResolvedSaml, request_data: dict[str, Any]) -> dict[str, Any]:
    """Validate a SAML response; return the attributes/nameid on success."""
    auth = init_auth(cfg, request_data)
    auth.process_response()
    errors = auth.get_errors()
    if errors:
        raise SAMLError(f"SAML validation failed: {errors} {auth.get_last_error_reason()}")
    if not auth.is_authenticated():
        raise SAMLError("SAML assertion not authenticated")
    return {
        "nameid": auth.get_nameid(),
        "attributes": auth.get_attributes(),
    }


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def identity_from(cfg: ResolvedSaml, nameid: str, attrs: dict[str, Any]) -> tuple[str, str]:
    """(email, display name) from an assertion, honouring configured attribute names."""
    email = None
    if cfg.email_attribute:
        email = _first(attrs.get(cfg.email_attribute))
    email = email or _first(attrs.get("email")) or _first(attrs.get(EMAIL_CLAIM)) or nameid
    name = None
    if cfg.name_attribute:
        name = _first(attrs.get(cfg.name_attribute))
    name = name or _first(attrs.get("displayName")) or _first(attrs.get(NAME_CLAIM)) or ""
    return email, name
