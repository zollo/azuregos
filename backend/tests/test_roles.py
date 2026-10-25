"""Admin roles: super admin / admin / portal admin.

The permission helpers on ``User`` are checked directly; the API rules run
against an in-memory SQLite database with ADO unconfigured.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models.ado_connection import AdoConnection
from app.models.category import Category
from app.models.portal import Portal
from app.models.user import PortalAdmin, User, UserRole


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(element, compiler, **kw):
    return "JSON"


def _user(role: UserRole, portal_ids: tuple[uuid.UUID, ...] = ()) -> User:
    user = User(email=f"{role.value}-{uuid.uuid4().hex[:6]}@example.com", role=role)
    user.portal_assignments = [PortalAdmin(portal_id=p) for p in portal_ids]
    return user


# ── Permission helpers ────────────────────────────────────────────────────
def test_staff_and_admin_flags():
    assert _user(UserRole.super_admin).is_admin
    assert _user(UserRole.admin).is_admin
    assert not _user(UserRole.portal_admin).is_admin
    assert _user(UserRole.portal_admin).is_staff
    assert not _user(UserRole.end_user).is_staff
    assert _user(UserRole.super_admin).is_super_admin
    assert not _user(UserRole.admin).is_super_admin


def test_can_grant():
    sup, adm = _user(UserRole.super_admin), _user(UserRole.admin)
    assert all(sup.can_grant(r) for r in UserRole)
    assert not adm.can_grant(UserRole.super_admin)
    assert adm.can_grant(UserRole.admin)
    assert adm.can_grant(UserRole.portal_admin)
    assert adm.can_grant(UserRole.end_user)
    assert not any(_user(UserRole.portal_admin).can_grant(r) for r in UserRole)


def test_can_manage_user():
    sup, adm = _user(UserRole.super_admin), _user(UserRole.admin)
    assert sup.can_manage_user(_user(UserRole.super_admin))
    assert not adm.can_manage_user(_user(UserRole.super_admin))
    assert adm.can_manage_user(_user(UserRole.admin))
    assert not _user(UserRole.portal_admin).can_manage_user(_user(UserRole.end_user))


def test_can_manage_portal():
    mine, other = uuid.uuid4(), uuid.uuid4()
    pa = _user(UserRole.portal_admin, (mine,))
    assert pa.can_manage_portal(mine)
    assert not pa.can_manage_portal(other)
    assert _user(UserRole.admin).can_manage_portal(other)
    # Assignments only count for portal admins.
    assert not _user(UserRole.end_user, (mine,)).can_manage_portal(mine)


# ── API ───────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def no_env_ado(monkeypatch):
    for key in ("ado_org_url", "ado_pat", "ado_default_project"):
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
            tables=[
                User.__table__,
                Category.__table__,
                Portal.__table__,
                PortalAdmin.__table__,
                AdoConnection.__table__,
            ],
        )
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def db(sessionmaker):
    async with sessionmaker() as session:
        yield session


@pytest.fixture
async def portals(db):
    a = Portal(name="Alpha", slug="alpha", fields=[])
    b = Portal(name="Beta", slug="beta", fields=[])
    db.add_all([a, b])
    await db.commit()
    return a, b


@pytest.fixture
async def users(db, portals):
    alpha, _ = portals
    out = {
        "super": _user(UserRole.super_admin),
        "admin": _user(UserRole.admin),
        "portal": _user(UserRole.portal_admin, (alpha.id,)),
        "end": _user(UserRole.end_user),
    }
    db.add_all(out.values())
    await db.commit()
    return out


@pytest.fixture
async def as_user(sessionmaker):
    """``as_user(user)`` returns an API client authenticated as ``user``."""

    async def _db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    clients: list[httpx.AsyncClient] = []

    def make(user: User) -> httpx.AsyncClient:
        app.dependency_overrides[get_current_user] = lambda: user
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.aclose()
    app.dependency_overrides.clear()


def _new_user(role: str, **extra) -> dict:
    return {
        "email": f"new-{uuid.uuid4().hex[:6]}@example.com",
        "password": "password123",
        "role": role,
        **extra,
    }


async def test_only_super_admin_creates_super_admins(users, as_user):
    api = as_user(users["admin"])
    assert (await api.post("/api/users", json=_new_user("super_admin"))).status_code == 403
    assert (await api.post("/api/users", json=_new_user("admin"))).status_code == 201

    api = as_user(users["super"])
    res = await api.post("/api/users", json=_new_user("super_admin"))
    assert res.status_code == 201
    assert res.json()["role"] == "super_admin"


async def test_admin_cannot_promote_or_touch_super_admins(users, as_user):
    api = as_user(users["admin"])
    res = await api.patch(f"/api/users/{users['end'].id}", json={"role": "super_admin"})
    assert res.status_code == 403
    res = await api.patch(f"/api/users/{users['super'].id}", json={"display_name": "x"})
    assert res.status_code == 403
    assert (await api.delete(f"/api/users/{users['super'].id}")).status_code == 403


async def test_portal_admins_and_end_users_cannot_manage_users(users, as_user):
    for key in ("portal", "end"):
        assert (await as_user(users[key]).get("/api/users")).status_code == 403


async def test_last_super_admin_is_protected(users, as_user):
    sup = users["super"]
    api = as_user(sup)
    res = await api.patch(f"/api/users/{sup.id}", json={"role": "admin"})
    assert res.status_code == 400
    res = await api.patch(f"/api/users/{sup.id}", json={"is_active": False})
    assert res.status_code == 400

    # With a second super admin the demotion is allowed.
    assert (await api.post("/api/users", json=_new_user("super_admin"))).status_code == 201
    res = await api.patch(f"/api/users/{sup.id}", json={"role": "admin"})
    assert res.status_code == 200


async def test_portal_assignments(users, portals, as_user):
    alpha, beta = portals
    api = as_user(users["admin"])
    res = await api.post(
        "/api/users", json=_new_user("portal_admin", portal_ids=[str(alpha.id), str(beta.id)])
    )
    assert res.status_code == 201
    created = res.json()
    assert set(created["portal_ids"]) == {str(alpha.id), str(beta.id)}

    res = await api.patch(f"/api/users/{created['id']}", json={"portal_ids": [str(beta.id)]})
    assert res.json()["portal_ids"] == [str(beta.id)]

    # Leaving the portal_admin role clears the assignments.
    res = await api.patch(f"/api/users/{created['id']}", json={"role": "end_user"})
    assert res.json()["portal_ids"] == []

    res = await api.post(
        "/api/users", json=_new_user("portal_admin", portal_ids=[str(uuid.uuid4())])
    )
    assert res.status_code == 422


async def test_portal_admin_sees_and_edits_only_assigned_portals(users, portals, as_user):
    alpha, beta = portals
    api = as_user(users["portal"])
    listed = (await api.get("/api/portals")).json()
    assert [p["id"] for p in listed] == [str(alpha.id)]

    res = await api.patch(f"/api/portals/{alpha.id}", json={"description": "Edited"})
    assert res.status_code == 200
    assert res.json()["description"] == "Edited"
    res = await api.patch(f"/api/portals/{beta.id}", json={"description": "Nope"})
    assert res.status_code == 403

    assert (await api.post("/api/portals", json={"name": "New"})).status_code == 403
    assert (await api.delete(f"/api/portals/{alpha.id}")).status_code == 403
    assert (await api.post("/api/categories", json={"name": "Cat"})).status_code == 403


async def test_admin_creates_portals(users, as_user):
    api = as_user(users["admin"])
    res = await api.post("/api/portals", json={"name": "Gamma"})
    assert res.status_code == 201
    assert len((await api.get("/api/portals")).json()) == 3


async def test_end_user_has_no_admin_portal_access(users, as_user):
    api = as_user(users["end"])
    assert (await api.get("/api/portals")).status_code == 403


async def test_ado_connection_is_super_admin_only(users, as_user):
    for key in ("admin", "portal"):
        api = as_user(users[key])
        assert (await api.get("/api/ado/connection")).status_code == 403
        # The editor's pickers stay available to anyone who edits portals.
        assert (await api.get("/api/ado/projects")).status_code == 200
    assert (await as_user(users["super"]).get("/api/ado/connection")).status_code == 200
    assert (await as_user(users["end"]).get("/api/ado/projects")).status_code == 403
