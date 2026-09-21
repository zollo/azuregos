"""Unit tests for portal work-item-type validation (no DB / no network)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes import portals
from app.services.ado_client import ADOError


class _FakeClient:
    def __init__(self, *, configured=True, types=None, raise_exc=None, default_project="P"):
        self.configured = configured
        self.default_project = default_project
        self._types = types or []
        self._raise = raise_exc

    async def list_work_item_types(self, project):
        if self._raise:
            raise self._raise
        return self._types


def _patch(monkeypatch, client):
    monkeypatch.setattr(portals, "get_ado_client", lambda: client)


async def test_skips_when_ado_not_configured(monkeypatch):
    _patch(monkeypatch, _FakeClient(configured=False))
    # Should not raise even though the type is nonsense.
    await portals._validate_work_item_type("P", "Nonexistent")


async def test_accepts_valid_type(monkeypatch):
    _patch(monkeypatch, _FakeClient(types=[{"name": "Issue"}, {"name": "Bug"}]))
    await portals._validate_work_item_type("P", "Issue")


async def test_rejects_invalid_type(monkeypatch):
    _patch(monkeypatch, _FakeClient(types=[{"name": "Issue"}, {"name": "Bug"}]))
    with pytest.raises(HTTPException) as exc:
        await portals._validate_work_item_type("P", "Epic")
    assert exc.value.status_code == 422
    assert "Epic" in exc.value.detail
    assert "Issue" in exc.value.detail  # lists the valid options


async def test_rejects_missing_project(monkeypatch):
    err = ADOError("not found", status_code=404, retryable=False)
    _patch(monkeypatch, _FakeClient(raise_exc=err))
    with pytest.raises(HTTPException) as exc:
        await portals._validate_work_item_type("Ghost", "Issue")
    assert exc.value.status_code == 422
    assert "Ghost" in exc.value.detail


async def test_skips_on_transient_ado_error(monkeypatch):
    err = ADOError("boom", status_code=503, retryable=True)
    _patch(monkeypatch, _FakeClient(raise_exc=err))
    # Transient error must not block the save.
    await portals._validate_work_item_type("P", "AnythingGoesNow")
