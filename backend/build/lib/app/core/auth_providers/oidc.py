"""Minimal OIDC / OAuth2 Authorization Code flow using httpx.

Kept dependency-light and stateless: we don't require a server-side session.
The ``state`` parameter is a short signed JWT so the callback can be validated
without shared storage.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.config import settings


class OIDCError(Exception):
    pass


_discovery_cache: dict[str, Any] = {}


async def _discovery() -> dict[str, Any]:
    if not settings.oidc_discovery_url:
        raise OIDCError("OIDC discovery URL not configured")
    if _discovery_cache:
        return _discovery_cache
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(settings.oidc_discovery_url)
        resp.raise_for_status()
        _discovery_cache.update(resp.json())
    return _discovery_cache


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


async def authorization_url() -> str:
    disco = await _discovery()
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": "openid email profile",
        "state": _make_state(),
    }
    return f"{disco['authorization_endpoint']}?{urlencode(params)}"


async def exchange_code(code: str) -> dict[str, Any]:
    """Exchange an auth code for tokens, then fetch userinfo/claims."""
    disco = await _discovery()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oidc_redirect_uri,
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
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
