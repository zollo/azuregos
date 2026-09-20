"""SAML 2.0 SP helpers built on python3-saml.

The IdP is configured from its metadata URL (``SAML_METADATA_URL``). The SP is
described by ``SAML_SP_ENTITY_ID`` and ``SAML_ACS_URL``. For production you
should add SP signing certificates to ``settings`` below; the defaults request
no SP-side signing, which is fine for many IdPs behind TLS.
"""
from __future__ import annotations

from typing import Any

from app.config import settings


class SAMLError(Exception):
    pass


def _lazy_imports():
    # Imported lazily so the app boots even if xmlsec native libs are absent
    # in environments where SAML is disabled.
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser

    return OneLogin_Saml2_Auth, OneLogin_Saml2_IdPMetadataParser


def build_settings() -> dict[str, Any]:
    if not settings.saml_metadata_url:
        raise SAMLError("SAML metadata URL not configured")
    _, IdPMetadataParser = _lazy_imports()
    idp_data = IdPMetadataParser.parse_remote(settings.saml_metadata_url)
    saml_settings: dict[str, Any] = {
        "strict": True,
        "debug": settings.env == "development",
        "sp": {
            "entityId": settings.saml_sp_entity_id,
            "assertionConsumerService": {
                "url": settings.saml_acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
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


def init_auth(request_data: dict[str, Any]):
    OneLogin_Saml2_Auth, _ = _lazy_imports()
    return OneLogin_Saml2_Auth(_prepare_request(request_data), build_settings())


def login_redirect_url(request_data: dict[str, Any]) -> str:
    auth = init_auth(request_data)
    return auth.login()


def process_acs(request_data: dict[str, Any]) -> dict[str, Any]:
    """Validate a SAML response; return the attributes/nameid on success."""
    auth = init_auth(request_data)
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
