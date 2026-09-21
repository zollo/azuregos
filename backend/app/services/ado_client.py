"""Thin async Azure DevOps REST client.

We talk to the ADO REST API (v7.1) directly with httpx rather than the heavy,
sync-only official SDK. Auth is a Personal Access Token sent via HTTP Basic
(empty username, PAT as password).

Metadata convention
-------------------
Azuregos stores its own metadata as ADO **tags** so no custom fields are
required on the target project:

* ``azuregos``                      — marks the item as Azuregos-managed
* ``azuregos-portal:<portal_slug>`` — which portal created it
* ``azuregos-submitter:<email>``    — who submitted it (for "my tickets")

This lets us find a user's tickets with a WIQL tag query even if our local
cache is wiped.
"""
from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from app.config import settings

API_VERSION = "7.1"

TAG_MARKER = "azuregos"
TAG_PORTAL_PREFIX = "azuregos-portal:"
TAG_SUBMITTER_PREFIX = "azuregos-submitter:"


class ADOError(Exception):
    """Raised when an ADO call fails. ``retryable`` guides the retry loop."""

    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = True):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _auth_header(pat: str) -> str:
    token = base64.b64encode(f":{pat}".encode()).decode()
    return f"Basic {token}"


class ADOClient:
    def __init__(
        self,
        org_url: str | None = None,
        pat: str | None = None,
        default_project: str | None = None,
    ):
        self.org_url = (org_url or settings.ado_org_url).rstrip("/")
        self.pat = pat or settings.ado_pat
        self.default_project = default_project or settings.ado_default_project

    @property
    def configured(self) -> bool:
        return bool(self.org_url and self.pat)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"Authorization": _auth_header(self.pat)},
        )

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        # 4xx (except 429) are usually permanent: bad field, bad project, auth.
        retryable = resp.status_code == 429 or resp.status_code >= 500
        raise ADOError(
            f"ADO {resp.status_code}: {resp.text[:500]}",
            status_code=resp.status_code,
            retryable=retryable,
        )

    async def create_work_item(
        self,
        *,
        project: str,
        work_item_type: str,
        title: str,
        description: str,
        tags: list[str],
        extra_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a work item via JSON Patch. Returns the ADO work-item JSON."""
        project = project or self.default_project
        if not project:
            raise ADOError("No ADO project configured", retryable=False)

        patch: list[dict[str, Any]] = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description", "value": description or ""},
        ]
        if tags:
            patch.append(
                {"op": "add", "path": "/fields/System.Tags", "value": "; ".join(tags)}
            )
        for ref, value in (extra_fields or {}).items():
            patch.append({"op": "add", "path": f"/fields/{ref}", "value": value})

        url = (
            f"{self.org_url}/{project}/_apis/wit/workitems/"
            f"${work_item_type}?api-version={API_VERSION}"
        )
        try:
            async with self._client() as client:
                resp = await client.post(
                    url,
                    content=json.dumps(patch),
                    headers={"Content-Type": "application/json-patch+json"},
                )
        except httpx.RequestError as exc:
            raise ADOError(f"Network error contacting ADO: {exc}", retryable=True) from exc

        self._raise_for_status(resp)
        return resp.json()

    async def get_work_item(self, work_item_id: int) -> dict[str, Any]:
        url = f"{self.org_url}/_apis/wit/workitems/{work_item_id}?api-version={API_VERSION}"
        try:
            async with self._client() as client:
                resp = await client.get(url)
        except httpx.RequestError as exc:
            raise ADOError(f"Network error contacting ADO: {exc}", retryable=True) from exc
        self._raise_for_status(resp)
        return resp.json()

    async def query_by_tag(self, project: str, tag: str) -> list[int]:
        """Return work-item IDs carrying ``tag`` via WIQL."""
        project = project or self.default_project
        wiql = {
            "query": (
                "SELECT [System.Id] FROM WorkItems "
                f"WHERE [System.Tags] CONTAINS '{tag}' "
                "ORDER BY [System.ChangedDate] DESC"
            )
        }
        url = f"{self.org_url}/{project}/_apis/wit/wiql?api-version={API_VERSION}"
        try:
            async with self._client() as client:
                resp = await client.post(url, json=wiql)
        except httpx.RequestError as exc:
            raise ADOError(f"Network error contacting ADO: {exc}", retryable=True) from exc
        self._raise_for_status(resp)
        return [item["id"] for item in resp.json().get("workItems", [])]

    async def list_projects(self) -> list[dict[str, Any]]:
        """List the org's projects (also handy for admin project pickers)."""
        url = f"{self.org_url}/_apis/projects?api-version={API_VERSION}"
        try:
            async with self._client() as client:
                resp = await client.get(url)
        except httpx.RequestError as exc:
            raise ADOError(f"Network error contacting ADO: {exc}", retryable=True) from exc
        self._raise_for_status(resp)
        return resp.json().get("value", [])

    async def list_work_item_types(self, project: str) -> list[dict[str, Any]]:
        """List a project's work-item types (for portal configuration)."""
        project = project or self.default_project
        url = f"{self.org_url}/{project}/_apis/wit/workitemtypes?api-version={API_VERSION}"
        try:
            async with self._client() as client:
                resp = await client.get(url)
        except httpx.RequestError as exc:
            raise ADOError(f"Network error contacting ADO: {exc}", retryable=True) from exc
        self._raise_for_status(resp)
        return resp.json().get("value", [])

    async def delete_work_item(self, work_item_id: int, *, destroy: bool = False) -> None:
        """Delete a work item. By default it goes to the recycle bin; ``destroy``
        permanently removes it. Used to clean up after functional tests."""
        url = (
            f"{self.org_url}/_apis/wit/workitems/{work_item_id}"
            f"?api-version={API_VERSION}&destroy={str(destroy).lower()}"
        )
        try:
            async with self._client() as client:
                resp = await client.delete(url)
        except httpx.RequestError as exc:
            raise ADOError(f"Network error contacting ADO: {exc}", retryable=True) from exc
        self._raise_for_status(resp)

    @staticmethod
    def web_url(work_item: dict[str, Any]) -> str | None:
        links = work_item.get("_links", {})
        html = links.get("html", {})
        return html.get("href")


def get_ado_client() -> ADOClient:
    return ADOClient()
