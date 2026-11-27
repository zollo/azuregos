"""Minimal async HTTP client for the Azuregos API."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx

from azuregos_mcp import __version__
from azuregos_mcp.spec import Operation


class AzuregosError(Exception):
    """The API answered with a non-2xx status."""

    def __init__(self, status: int, reason: str, detail: Any):
        self.status = status
        self.detail = detail
        text = detail if isinstance(detail, str) else json.dumps(detail, indent=2)
        super().__init__(f"HTTP {status} {reason}: {text}")


class AzuregosClient:
    """Talks to one Azuregos instance as one user.

    Authenticate with either a bearer ``token`` or ``email``/``password`` of a
    local account. With a password the client logs in lazily and logs in again
    once when a token expires (HTTP 401).
    """

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        email: str | None = None,
        password: str | None = None,
        verify: bool | str = True,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if email and not password:
            raise ValueError("AZUREGOS_PASSWORD is required with AZUREGOS_EMAIL")
        self._token = token
        self._email = email
        self._password = password
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            verify=verify,
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": f"azuregos-mcp/{__version__}"},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def fetch_spec(self) -> dict:
        resp = await self._http.get("/openapi.json")
        _raise_for_status(resp)
        return resp.json()

    async def _login(self) -> str:
        resp = await self._http.post(
            "/api/auth/login", json={"email": self._email, "password": self._password}
        )
        _raise_for_status(resp)
        self._token = resp.json()["access_token"]
        return self._token

    async def _auth_headers(self) -> dict[str, str]:
        token = self._token
        if token is None and self._email:
            token = await self._login()
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def call(self, op: Operation, arguments: dict[str, Any]) -> Any:
        """Call ``op`` with tool ``arguments``; returns the decoded response."""
        path = op.path
        query: dict[str, Any] = {}
        for param in op.params:
            if param.name not in arguments or arguments[param.name] is None:
                continue
            value = arguments[param.name]
            if param.location == "path":
                path = path.replace("{" + param.name + "}", quote(str(value), safe=""))
            else:
                query[param.name] = _query_value(value)
        kwargs: dict[str, Any] = {"params": query}
        if op.has_body and "body" in arguments:
            kwargs["json"] = arguments["body"]

        send = self._http.request
        resp = await send(op.method, path, headers=await self._auth_headers(), **kwargs)
        if resp.status_code == 401 and self._email:
            await self._login()
            resp = await send(op.method, path, headers=await self._auth_headers(), **kwargs)
        _raise_for_status(resp)
        if resp.status_code == 204 or not resp.content:
            return None
        if "json" in resp.headers.get("content-type", ""):
            return resp.json()
        return resp.text


def _query_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.is_success:
        return
    try:
        body = resp.json()
        detail = body.get("detail", body) if isinstance(body, dict) else body
    except ValueError:
        detail = resp.text
    raise AzuregosError(resp.status_code, resp.reason_phrase, detail)
