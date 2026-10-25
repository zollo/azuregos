"""The admin-configured ADO connection: precedence, PAT handling, and the API.

Runs against an in-memory SQLite database holding just the tables involved;
ADO itself is faked by patching ``ADOClient.list_projects``.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.api.routes import ado as ado_routes
from app.config import settings
from app.core import security
from app.db import Base, get_db
from app.main import app
from app.models.ado_connection import SINGLETON_ID, AdoConnection
from app.models.user import PortalAdmin, User, UserRole
from app.services.ado_client import ADOClient, ADOError
from app.services.ado_connection import ConnectionSource, resolve_connection

ENV = {
    "ado_org_url": "https://dev.azure.com/env-org",
    "ado_pat": "env-pat",
    "ado_default_project": "EnvProject",
}


@pytest.fixture
def env_ado(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setattr(settings, key, value)


@pytest.fixture
def no_env_ado(monkeypatch):
    for key in ENV:
        monkeypatch.setattr(settings, key, "")


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[User.__table__, PortalAdmin.__table__, AdoConnection.__table__],
        )
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def db(sessionmaker):
    async with sessionmaker() as session:
        yield session


@pytest.fixture
async def admin(db):
    user = User(email="admin@example.com", display_name="Admin", role=UserRole.super_admin)
    db.add(user)
    await db.commit()
    return user


class _FakeADO:
    """Patches the ADO calls used to verify a connection, recording the
    (org_url, pat) pairs they saw."""

    def __init__(self, monkeypatch):
        self.projects = [{"id": "1", "name": "UiProject"}]
        self.error: ADOError | None = None
        self.seen: list[tuple[str, str]] = []
        fake = self

        async def list_projects(client: ADOClient):
            fake.seen.append((client.org_url, client.pat))
            if fake.error:
                raise fake.error
            return fake.projects

        async def get_project(client: ADOClient, project: str):
            for p in fake.projects:
                if p["name"].lower() == project.lower():
                    return p
            raise ADOError("ADO 404", status_code=404, retryable=False)

        monkeypatch.setattr(ADOClient, "list_projects", list_projects)
        monkeypatch.setattr(ADOClient, "get_project", get_project)


@pytest.fixture
def fake_ado(monkeypatch):
    return _FakeADO(monkeypatch)


@pytest.fixture
def linked_tickets(monkeypatch):
    """How many tickets are linked to ADO work items (the tickets table isn't
    created in SQLite)."""
    state = {"count": 0}

    async def count(db):
        return state["count"]

    monkeypatch.setattr(ado_routes, "_linked_ticket_count", count)
    return state


@pytest.fixture
async def api(sessionmaker, admin, linked_tickets):
    async def _db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: admin
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _save_row(db, *, org_url="https://dev.azure.com/ui-org", pat="ui-pat", project=""):
    db.add(
        AdoConnection(
            id=SINGLETON_ID,
            org_url=org_url,
            pat_encrypted=security.encrypt_secret(pat),
            default_project=project,
        )
    )
    await db.commit()


# ── Secret encryption ─────────────────────────────────────────────────────
def test_secret_roundtrip_and_not_plaintext():
    token = security.encrypt_secret("s3cret")
    assert "s3cret" not in token
    assert security.decrypt_secret(token) == "s3cret"


def test_secret_unreadable_after_key_rotation(monkeypatch):
    token = security.encrypt_secret("s3cret")
    monkeypatch.setattr(settings, "secret_key", "a-different-key")
    with pytest.raises(security.SecretDecryptionError):
        security.decrypt_secret(token)


# ── Precedence ────────────────────────────────────────────────────────────
async def test_env_used_when_nothing_saved(db, env_ado):
    conn = await resolve_connection(db)
    assert conn.source == ConnectionSource.environment
    assert (conn.org_url, conn.pat, conn.default_project) == (
        ENV["ado_org_url"],
        ENV["ado_pat"],
        ENV["ado_default_project"],
    )


async def test_none_when_nothing_configured(db, no_env_ado):
    conn = await resolve_connection(db)
    assert conn.source == ConnectionSource.none
    assert not conn.configured


async def test_saved_connection_wins_and_is_not_mixed_with_env(db, env_ado):
    await _save_row(db, project="")
    conn = await resolve_connection(db)
    assert conn.source == ConnectionSource.database
    assert conn.org_url == "https://dev.azure.com/ui-org"
    assert conn.pat == "ui-pat"
    # Blank in the saved connection stays blank: no fallback to EnvProject.
    assert conn.default_project == ""
    assert conn.client().default_project == ""


async def test_undecryptable_saved_pat_fails_closed(db, env_ado, monkeypatch):
    await _save_row(db)
    monkeypatch.setattr(settings, "secret_key", "rotated")
    conn = await resolve_connection(db)
    assert conn.source == ConnectionSource.database
    assert not conn.configured
    assert conn.error and "SECRET_KEY" in conn.error


# ── 203 sign-in page ──────────────────────────────────────────────────────
def test_203_is_treated_as_auth_failure():
    resp = httpx.Response(203, text="<html>Sign in</html>")
    with pytest.raises(ADOError) as exc:
        ADOClient._raise_for_status(resp)
    assert exc.value.status_code == 401
    assert not exc.value.retryable


# ── API ───────────────────────────────────────────────────────────────────
async def test_get_reports_env_source_without_pat(api, env_ado):
    resp = await api.get("/api/ado/connection")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "environment"
    assert body["stored"] is None
    assert body["environment"] == {
        "org_url": ENV["ado_org_url"],
        "default_project": ENV["ado_default_project"],
        "pat_set": True,
    }
    assert "env-pat" not in resp.text


async def test_save_then_get_uses_database(api, env_ado, fake_ado, db):
    resp = await api.put(
        "/api/ado/connection",
        json={"org_url": "https://dev.azure.com/ui-org/", "pat": "ui-pat",
              "default_project": "UiProject"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "database"
    assert body["stored"]["org_url"] == "https://dev.azure.com/ui-org"  # trailing / trimmed
    assert body["stored"]["pat_set"] is True
    assert body["stored"]["updated_by"] == "admin@example.com"
    assert "ui-pat" not in resp.text
    # Verified with the submitted values before saving.
    assert fake_ado.seen == [("https://dev.azure.com/ui-org", "ui-pat")]

    row = await db.get(AdoConnection, SINGLETON_ID)
    assert row.pat_encrypted != "ui-pat"


async def test_save_requires_pat_when_none_saved(api, fake_ado):
    resp = await api.put("/api/ado/connection", json={"org_url": "https://dev.azure.com/o"})
    assert resp.status_code == 422
    assert "personal access token" in resp.json()["detail"]


async def test_blank_pat_keeps_saved_one(api, fake_ado, db):
    await _save_row(db, pat="original-pat")
    resp = await api.put(
        "/api/ado/connection",
        json={"org_url": "https://dev.azure.com/new-org", "pat": ""},
    )
    assert resp.status_code == 200, resp.text
    assert fake_ado.seen[-1] == ("https://dev.azure.com/new-org", "original-pat")
    conn = await resolve_connection(db)
    assert conn.pat == "original-pat"
    assert conn.org_url == "https://dev.azure.com/new-org"


async def test_save_rejects_bad_pat(api, fake_ado, db):
    fake_ado.error = ADOError("ADO 401", status_code=401, retryable=False)
    resp = await api.put(
        "/api/ado/connection", json={"org_url": "https://dev.azure.com/o", "pat": "bad"}
    )
    assert resp.status_code == 422
    assert await db.get(AdoConnection, SINGLETON_ID) is None


async def test_save_rejects_unknown_default_project(api, fake_ado):
    resp = await api.put(
        "/api/ado/connection",
        json={"org_url": "https://dev.azure.com/o", "pat": "p", "default_project": "Ghost"},
    )
    assert resp.status_code == 422
    assert "Ghost" in resp.json()["detail"]


async def test_save_allowed_on_transient_error(api, fake_ado):
    fake_ado.error = ADOError("timeout", retryable=True)
    resp = await api.put(
        "/api/ado/connection", json={"org_url": "https://dev.azure.com/o", "pat": "p"}
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "database"


async def test_save_rejects_non_http_url(api, fake_ado):
    resp = await api.put("/api/ado/connection", json={"org_url": "file:///etc", "pat": "p"})
    assert resp.status_code == 422
    assert fake_ado.seen == []


async def test_test_endpoint_reports_without_saving(api, fake_ado, db):
    fake_ado.error = ADOError("ADO 401", status_code=401, retryable=False)
    resp = await api.post(
        "/api/ado/connection/test", json={"org_url": "https://dev.azure.com/o", "pat": "p"}
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert "401" in resp.json()["error"]
    fake_ado.error = None
    resp = await api.post(
        "/api/ado/connection/test", json={"org_url": "https://dev.azure.com/o", "pat": "p"}
    )
    assert resp.json() == {"ok": True, "project_count": 1, "error": None}
    assert await db.get(AdoConnection, SINGLETON_ID) is None


async def test_delete_reverts_to_env(api, env_ado, db):
    await _save_row(db)
    resp = await api.delete("/api/ado/connection")
    assert resp.status_code == 204
    resp = await api.get("/api/ado/connection")
    assert resp.json()["source"] == "environment"
    assert resp.json()["stored"] is None


# ── Organization switches ─────────────────────────────────────────────────
async def test_switching_org_blocked_while_tickets_linked(api, env_ado, fake_ado, linked_tickets):
    linked_tickets["count"] = 3
    resp = await api.put(
        "/api/ado/connection", json={"org_url": "https://dev.azure.com/other", "pat": "p"}
    )
    assert resp.status_code == 409
    assert "3 ticket(s)" in resp.json()["detail"]
    assert fake_ado.seen == []


async def test_same_org_allowed_while_tickets_linked(api, env_ado, fake_ado, linked_tickets):
    linked_tickets["count"] = 3
    # Same org as ADO_ORG_URL, differing only in case and trailing slash.
    resp = await api.put(
        "/api/ado/connection", json={"org_url": "https://DEV.azure.com/env-org/", "pat": "p"}
    )
    assert resp.status_code == 200, resp.text


async def test_delete_blocked_when_env_is_another_org(api, env_ado, db, linked_tickets):
    await _save_row(db)  # ui-org, while env is env-org
    linked_tickets["count"] = 1
    resp = await api.delete("/api/ado/connection")
    assert resp.status_code == 409
    assert await db.get(AdoConnection, SINGLETON_ID) is not None


async def test_delete_allowed_when_env_unset(api, no_env_ado, db, linked_tickets):
    await _save_row(db)
    linked_tickets["count"] = 1
    resp = await api.delete("/api/ado/connection")
    assert resp.status_code == 204


# ── Response validation ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>Sign in</html>"),
        httpx.Response(200, json={}),
        httpx.Response(200, json=[1, 2]),
    ],
)
async def test_list_projects_rejects_non_ado_responses(monkeypatch, response):
    async def get(self, url, **kwargs):
        return response

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    client = ADOClient(org_url="https://example.com", pat="p", default_project="")
    with pytest.raises(ADOError) as exc:
        await client.list_projects()
    assert not exc.value.retryable


async def test_default_project_found_beyond_first_page(api, fake_ado, monkeypatch):
    # Missing from the (first page of the) list, but the direct lookup finds it.
    async def get_project(client, project):
        return {"name": project}

    fake_ado.projects = []
    monkeypatch.setattr(ADOClient, "get_project", get_project)
    resp = await api.post(
        "/api/ado/connection/test",
        json={"org_url": "https://dev.azure.com/o", "pat": "p", "default_project": "Late"},
    )
    assert resp.json()["ok"] is True
