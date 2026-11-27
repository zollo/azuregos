"""Minimal OIDC / OAuth2 Authorization Code flow using httpx.

Kept dependency-light and stateless: we don't require a server-side session.
The ``state`` parameter is a short signed JWT so the callback can be validated
without shared storage.

The provider settings come from ``app.services.sso_settings.resolve_oidc`` (the
admin UI or the ``OIDC_*`` env vars) and are passed in on every call.
"""
from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings
from app.services.sso_settings import ResolvedOidc


class OIDCError(Exception):
    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        # True when the IdP was just unreachable (network error, 5xx) rather
        # than definitely misconfigured.
        self.transient = transient


# Discovery documents, keyed by URL, so a changed URL is picked up immediately.
_DISCOVERY_TTL_SECONDS = 3600
_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}

_REQUIRED_ENDPOINTS = ("authorization_endpoint", "token_endpoint")


async def fetch_discovery(url: str) -> dict[str, Any]:
    """Fetch and sanity-check a discovery document (uncached).

    Raises ``OIDCError``; ``transient`` is set when the IdP couldn't be reached.
    """
    if not url:
        raise OIDCError("OIDC discovery URL not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise OIDCError(f"Couldn't reach the discovery URL: {exc}", transient=True) from exc
    if resp.status_code >= 500:
        raise OIDCError(f"Discovery URL returned HTTP {resp.status_code}", transient=True)
    if resp.status_code >= 400:
        raise OIDCError(f"Discovery URL returned HTTP {resp.status_code}")
    try:
        doc = resp.json()
    except ValueError as exc:
        raise OIDCError("Discovery URL didn't return JSON") from exc
    if not isinstance(doc, dict):
        raise OIDCError("Discovery URL didn't return an OpenID configuration")
    missing = [k for k in _REQUIRED_ENDPOINTS if not doc.get(k)]
    if missing:
        raise OIDCError(
            "Not an OpenID configuration document (missing " + ", ".join(missing) + ")"
        )
    return doc


async def _discovery(cfg: ResolvedOidc) -> dict[str, Any]:
    cached = _discovery_cache.get(cfg.discovery_url)
    if cached and time.monotonic() - cached[0] < _DISCOVERY_TTL_SECONDS:
        return cached[1]
    doc = await fetch_discovery(cfg.discovery_url)
    _discovery_cache[cfg.discovery_url] = (time.monotonic(), doc)
    return doc


def _make_state() -> str:
    payload = {
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(UTC) + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def verify_state(state: str) -> None:
    try:
        jwt.decode(state, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise OIDCError("Invalid or expired OAuth state") from exc


async def authorization_url(cfg: ResolvedOidc) -> str:
    disco = await _discovery(cfg)
    params = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": cfg.effective_redirect_uri,
        "scope": cfg.effective_scopes,
        "state": _make_state(),
    }
    return f"{disco['authorization_endpoint']}?{urlencode(params)}"


async def exchange_code(cfg: ResolvedOidc, code: str) -> dict[str, Any]:
    """Exchange an auth code for tokens, then fetch userinfo/claims."""
    disco = await _discovery(cfg)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg.effective_redirect_uri,
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(disco["token_endpoint"], data=data)
        token_resp.raise_for_status()
        tokens = token_resp.json()

        # Prefer verified userinfo; fall back to decoding the id_token claims.
        if "userinfo_endpoint" in disco and tokens.get("access_token"):
            ui = await client.get(
                disco["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            ui.raise_for_status()
            return ui.json()

    claims = jwt.decode(tokens["id_token"], options={"verify_signature": False})
    return claims
