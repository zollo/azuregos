"""Unit tests for portal work-item-type validation (no DB / no network)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes import portals
from app.services.ado_client import ADOError


class _FakeClient:
    def __init__(
        self, *, configured=True, types=None, areas=None, raise_exc=None, default_project="P"
    ):
        self.configured = configured
        self.default_project = default_project
        self._types = types or []
        self._areas = areas or []
        self._raise = raise_exc

    async def list_work_item_types(self, project):
        if self._raise:
            raise self._raise
        return self._types

    async def list_area_paths(self, project):
        if self._raise:
            raise self._raise
        return self._areas


async def test_skips_when_ado_not_configured():
    client = _FakeClient(configured=False)
    # Should not raise even though the type is nonsense.
    await portals._validate_work_item_type(client, "P", "Nonexistent")


async def test_accepts_valid_type():
    client = _FakeClient(types=[{"name": "Issue"}, {"name": "Bug"}])
    await portals._validate_work_item_type(client, "P", "Issue")


async def test_rejects_invalid_type():
    client = _FakeClient(types=[{"name": "Issue"}, {"name": "Bug"}])
    with pytest.raises(HTTPException) as exc:
        await portals._validate_work_item_type(client, "P", "Epic")
    assert exc.value.status_code == 422
    assert "Epic" in exc.value.detail
    assert "Issue" in exc.value.detail  # lists the valid options


async def test_rejects_missing_project():
    err = ADOError("not found", status_code=404, retryable=False)
    client = _FakeClient(raise_exc=err)
    with pytest.raises(HTTPException) as exc:
        await portals._validate_work_item_type(client, "Ghost", "Issue")
    assert exc.value.status_code == 422
    assert "Ghost" in exc.value.detail


async def test_skips_on_transient_ado_error():
    err = ADOError("boom", status_code=503, retryable=True)
    client = _FakeClient(raise_exc=err)
    # Transient error must not block the save.
    await portals._validate_work_item_type(client, "P", "AnythingGoesNow")


# ── Area path validation ──────────────────────────────────────────────────
async def test_area_path_blank_is_allowed():
    # Not configured / no lookup needed; project root is always valid.
    client = _FakeClient(areas=[])
    await portals._validate_area_path(client, "P", None)
    await portals._validate_area_path(client, "P", "")


async def test_area_path_valid():
    client = _FakeClient(areas=["P", "P\\Team", "P\\Team\\Sub"])
    await portals._validate_area_path(client, "P", "P\\Team\\Sub")


async def test_area_path_invalid_rejected():
    client = _FakeClient(areas=["P", "P\\Team"])
    with pytest.raises(HTTPException) as exc:
        await portals._validate_area_path(client, "P", "P\\Nope")
    assert exc.value.status_code == 422
    assert "P\\Nope" in exc.value.detail


async def test_area_path_skips_when_not_configured():
    client = _FakeClient(configured=False)
    await portals._validate_area_path(client, "P", "P\\Whatever")


async def test_area_path_skips_on_transient_error():
    err = ADOError("boom", status_code=503, retryable=True)
    client = _FakeClient(raise_exc=err)
    await portals._validate_area_path(client, "P", "P\\Team")
