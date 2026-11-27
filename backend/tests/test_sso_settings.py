"""Admin-configured OIDC / SAML: precedence over env vars, secret handling,
enable/disable, validation, and the login-page provider list.

Runs against an in-memory SQLite database; the IdPs are faked by patching the
discovery fetch (OIDC) and by pasting metadata XML (SAML).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.config import settings
from app.core import security
from app.core.auth_providers import oidc, saml
from app.db import Base, get_db
from app.main import app
from app.models.sso_settings import SINGLETON_ID, OidcSettings, SamlSettings
from app.models.user import PortalAdmin, User, UserRole
from app.services.sso_settings import SettingsSource, resolve_oidc, resolve_saml

DISCOVERY = "https://idp.example.com/.well-known/openid-configuration"
DISCOVERY_DOC = {
    "issuer": "https://idp.example.com",
    "authorization_endpoint": "https://idp.example.com/authorize",
    "token_endpoint": "https://idp.example.com/token",
}
IDP_METADATA = """<?xml version="1.0"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.com/saml">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.com/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
"""


def _keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "azuregos-test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return cert_pem, key_pem


@pytest.fixture(scope="module")
def keypair():
    return _keypair()


@pytest.fixture
def no_env_sso(monkeypatch):
    monkeypatch.setattr(settings, "oidc_enabled", False)
    monkeypatch.setattr(settings, "oidc_discovery_url", "")
    monkeypatch.setattr(settings, "oidc_client_id", "")
    monkeypatch.setattr(settings, "oidc_client_secret", "")
    monkeypatch.setattr(settings, "oidc_redirect_uri", "")
    monkeypatch.setattr(settings, "saml_enabled", False)
    monkeypatch.setattr(settings, "saml_metadata_url", "")
    monkeypatch.setattr(settings, "saml_acs_url", "")
    monkeypatch.setattr(settings, "cors_origins", "https://desk.example.com")


@pytest.fixture
def env_oidc(no_env_sso, monkeypatch):
    monkeypatch.setattr(settings, "oidc_enabled", True)
    monkeypatch.setattr(settings, "oidc_discovery_url", "https://env-idp/.well-known/x")
    monkeypatch.setattr(settings, "oidc_client_id", "env-client")
    monkeypatch.setattr(settings, "oidc_client_secret", "env-secret")


@pytest.fixture
def fake_discovery(monkeypatch):
    state = {"error": None, "seen": []}

    async def fetch(url):
        state["seen"].append(url)
        if state["error"]:
            raise state["error"]
        return DISCOVERY_DOC

    monkeypatch.setattr(oidc, "fetch_discovery", fetch)
    return state


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
                PortalAdmin.__table__,
                OidcSettings.__table__,
                SamlSettings.__table__,
            ],
        )
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def db(sessionmaker):
    async with sessionmaker() as session:
        yield session


@pytest.fixture
async def super_admin(db):
    user = User(email="root@example.com", display_name="Root", role=UserRole.super_admin)
    db.add(user)
    await db.commit()
    return user


@pytest.fixture
async def client_as(sessionmaker):
    """An API client acting as the given user (None = anonymous)."""
    clients = []

    async def _db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _db

    async def make(user: User | None):
        if user is not None:
            app.dependency_overrides[get_current_user] = lambda: user
        transport = httpx.ASGITransport(app=app)
        c = httpx.AsyncClient(transport=transport, base_url="http://test")
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.aclose()
    app.dependency_overrides.clear()


@pytest.fixture
async def api(client_as, super_admin):
    return await client_as(super_admin)


OIDC_BODY = {
    "enabled": True,
    "discovery_url": DISCOVERY,
    "client_id": "ui-client",
    "client_secret": "ui-secret",
}


# ── Access ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("role", [UserRole.admin, UserRole.portal_admin, UserRole.end_user])
async def test_only_super_admins(client_as, db, role, no_env_sso):
    user = User(email=f"{role.value}@example.com", role=role)
    db.add(user)
    await db.commit()
    c = await client_as(user)
    for method, path in [
        ("GET", "/api/sso/oidc"),
        ("PUT", "/api/sso/oidc"),
        ("DELETE", "/api/sso/oidc"),
        ("POST", "/api/sso/oidc/test"),
        ("GET", "/api/sso/saml"),
        ("PUT", "/api/sso/saml"),
        ("DELETE", "/api/sso/saml"),
        ("POST", "/api/sso/saml/test"),
    ]:
        body = {} if method in ("PUT", "POST") else None
        resp = await c.request(method, path, json=body)
        assert resp.status_code == 403, (method, path)


# ── OIDC precedence ───────────────────────────────────────────────────────
async def test_oidc_env_used_when_nothing_saved(db, env_oidc):
    cfg = await resolve_oidc(db)
    assert cfg.source == SettingsSource.environment
    assert cfg.active
    assert cfg.client_secret == "env-secret"
    # Blank OIDC_REDIRECT_URI is derived from the first CORS origin.
    assert cfg.effective_redirect_uri == "https://desk.example.com/api/auth/oidc/callback"


async def test_oidc_none_when_nothing_set(db, no_env_sso):
    cfg = await resolve_oidc(db)
    assert cfg.source == SettingsSource.none
    assert not cfg.active


async def test_saved_oidc_disables_env(api, db, env_oidc, fake_discovery):
    """Saving disabled settings switches off an env-enabled provider."""
    resp = await api.put("/api/sso/oidc", json={"enabled": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "database"
    assert body["enabled"] is False
    assert body["environment"]["enabled"] is True
    # Disabled saves aren't checked against the IdP.
    assert fake_discovery["seen"] == []
    providers = (await api.get("/api/auth/providers")).json()
    assert providers["oidc"] is False
    assert (await api.get("/api/auth/oidc/login")).status_code == 404


async def test_save_oidc_enables_and_hides_secret(api, db, no_env_sso, fake_discovery):
    resp = await api.put("/api/sso/oidc", json={**OIDC_BODY, "button_label": "Sign in with Acme"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enabled"] is True
    assert body["stored"]["client_secret_set"] is True
    assert body["stored"]["updated_by"] == "root@example.com"
    assert "ui-secret" not in resp.text
    assert fake_discovery["seen"] == [DISCOVERY]

    row = await db.get(OidcSettings, SINGLETON_ID)
    assert row.client_secret_encrypted and "ui-secret" not in row.client_secret_encrypted

    providers = (await api.get("/api/auth/providers")).json()
    assert providers["oidc"] is True
    assert providers["oidc_label"] == "Sign in with Acme"


async def test_oidc_login_uses_saved_settings(api, no_env_sso, fake_discovery):
    await api.put("/api/sso/oidc", json={**OIDC_BODY, "scopes": "openid  email groups"})
    resp = await api.get("/api/auth/oidc/login")
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert location.startswith(DISCOVERY_DOC["authorization_endpoint"])
    assert "client_id=ui-client" in location
    assert "scope=openid+email+groups" in location
    assert "desk.example.com%2Fapi%2Fauth%2Foidc%2Fcallback" in location


async def test_oidc_blank_secret_keeps_saved(api, db, no_env_sso, fake_discovery):
    await api.put("/api/sso/oidc", json=OIDC_BODY)
    resp = await api.put(
        "/api/sso/oidc", json={**OIDC_BODY, "client_secret": "", "client_id": "c2"}
    )
    assert resp.status_code == 200, resp.text
    cfg = await resolve_oidc(db)
    assert (cfg.client_id, cfg.client_secret) == ("c2", "ui-secret")


async def test_oidc_enable_requires_fields(api, no_env_sso, fake_discovery):
    resp = await api.put("/api/sso/oidc", json={"enabled": True, "discovery_url": DISCOVERY})
    assert resp.status_code == 422
    assert "client ID" in resp.json()["detail"]
    assert "client secret" in resp.json()["detail"]


async def test_oidc_definite_discovery_error_blocks_save(api, db, no_env_sso, fake_discovery):
    fake_discovery["error"] = oidc.OIDCError("Discovery URL returned HTTP 404")
    resp = await api.put("/api/sso/oidc", json=OIDC_BODY)
    assert resp.status_code == 422
    assert "404" in resp.json()["detail"]
    assert await db.get(OidcSettings, SINGLETON_ID) is None


async def test_oidc_transient_discovery_error_allows_save(api, no_env_sso, fake_discovery):
    fake_discovery["error"] = oidc.OIDCError("timeout", transient=True)
    resp = await api.put("/api/sso/oidc", json=OIDC_BODY)
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


async def test_oidc_rejects_bad_values(api, no_env_sso, fake_discovery):
    resp = await api.put("/api/sso/oidc", json={**OIDC_BODY, "discovery_url": "file:///etc"})
    assert resp.status_code == 422
    resp = await api.put("/api/sso/oidc", json={**OIDC_BODY, "scopes": "email profile"})
    assert resp.status_code == 422
    assert fake_discovery["seen"] == []


async def test_oidc_undecryptable_secret_fails_closed(api, db, env_oidc, fake_discovery,
                                                      monkeypatch):
    await api.put("/api/sso/oidc", json=OIDC_BODY)
    monkeypatch.setattr(settings, "secret_key", "rotated")
    cfg = await resolve_oidc(db)
    assert cfg.source == SettingsSource.database
    assert not cfg.active  # no fallback to the env-enabled provider
    assert cfg.error and "SECRET_KEY" in cfg.error


async def test_oidc_delete_reverts_to_env(api, env_oidc, fake_discovery):
    await api.put("/api/sso/oidc", json={"enabled": False})
    assert (await api.delete("/api/sso/oidc")).status_code == 204
    body = (await api.get("/api/sso/oidc")).json()
    assert body["source"] == "environment"
    assert body["stored"] is None
    assert body["enabled"] is True
    assert "env-secret" not in str(body)


async def test_oidc_test_endpoint(api, no_env_sso, fake_discovery, db):
    resp = await api.post("/api/sso/oidc/test", json={"discovery_url": DISCOVERY})
    assert resp.json()["ok"] is True
    assert resp.json()["issuer"] == "https://idp.example.com"
    fake_discovery["error"] = oidc.OIDCError("nope")
    resp = await api.post("/api/sso/oidc/test", json={"discovery_url": DISCOVERY})
    assert resp.json() == {
        "ok": False, "issuer": None, "authorization_endpoint": None, "error": "nope"
    }
    assert await db.get(OidcSettings, SINGLETON_ID) is None


@pytest.mark.parametrize(
    ("response", "transient"),
    [
        (httpx.Response(404), False),
        (httpx.Response(503), True),
        (httpx.Response(200, text="<html>"), False),
        (httpx.Response(200, json={"issuer": "x"}), False),
    ],
)
async def test_fetch_discovery_classifies_errors(monkeypatch, response, transient):
    async def get(self, url, **kwargs):
        return response

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    with pytest.raises(oidc.OIDCError) as exc:
        await oidc.fetch_discovery(DISCOVERY)
    assert exc.value.transient is transient


# ── SAML ──────────────────────────────────────────────────────────────────
async def test_save_saml_with_metadata_xml(api, db, no_env_sso):
    resp = await api.put(
        "/api/sso/saml",
        json={"enabled": True, "metadata_xml": IDP_METADATA, "email_attribute": "mail"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "database"
    assert body["enabled"] is True
    assert body["effective_acs_url"] == "https://desk.example.com/api/auth/saml/acs"
    assert body["effective_sp_entity_id"] == "azuregos"
    providers = (await api.get("/api/auth/providers")).json()
    assert providers["saml"] is True
    assert providers["saml_label"] == "Continue with SSO (SAML)"


async def test_saml_login_redirects_to_idp(api, no_env_sso):
    await api.put("/api/sso/saml", json={"enabled": True, "metadata_xml": IDP_METADATA})
    resp = await api.get("/api/auth/saml/login")
    assert resp.status_code == 307
    assert resp.headers["location"].startswith("https://idp.example.com/saml/sso?SAMLRequest=")


async def test_saml_enable_requires_metadata(api, no_env_sso):
    resp = await api.put("/api/sso/saml", json={"enabled": True})
    assert resp.status_code == 422
    assert "metadata" in resp.json()["detail"]


async def test_saml_rejects_bad_metadata(api, db, no_env_sso):
    resp = await api.put("/api/sso/saml", json={"enabled": True, "metadata_xml": "<nope/>"})
    assert resp.status_code == 422
    assert await db.get(SamlSettings, SINGLETON_ID) is None


async def test_saml_disabled_is_saved_unchecked(api, no_env_sso, monkeypatch):
    monkeypatch.setattr(settings, "saml_enabled", True)
    monkeypatch.setattr(settings, "saml_metadata_url", "https://env-idp/metadata")
    resp = await api.put("/api/sso/saml", json={"enabled": False, "metadata_xml": "<nope/>"})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    assert resp.json()["environment"]["enabled"] is True


async def test_saml_sp_keypair(api, db, no_env_sso, keypair):
    cert, key = keypair
    body = {"enabled": True, "metadata_xml": IDP_METADATA, "sp_x509_cert": cert}
    # Cert without a key is refused.
    resp = await api.put("/api/sso/saml", json=body)
    assert resp.status_code == 422
    # A key that doesn't match is refused.
    _, other_key = _keypair()
    resp = await api.put("/api/sso/saml", json={**body, "sp_private_key": other_key})
    assert resp.status_code == 422
    assert "doesn't match" in resp.json()["detail"]

    resp = await api.put("/api/sso/saml", json={**body, "sp_private_key": key})
    assert resp.status_code == 200, resp.text
    assert resp.json()["stored"]["sp_private_key_set"] is True
    assert "PRIVATE KEY" not in resp.text
    row = await db.get(SamlSettings, SINGLETON_ID)
    assert "PRIVATE KEY" not in row.sp_private_key_encrypted

    # Blank key keeps the saved one; signing is on.
    resp = await api.put("/api/sso/saml", json={**body, "sp_private_key": ""})
    assert resp.status_code == 200, resp.text
    cfg = await resolve_saml(db)
    assert cfg.sp_private_key.strip() == key.strip()
    assert saml.build_settings(cfg)["security"]["authnRequestsSigned"] is True

    # Clearing the certificate drops the key too.
    resp = await api.put("/api/sso/saml", json={"enabled": True, "metadata_xml": IDP_METADATA})
    assert resp.status_code == 200
    assert resp.json()["stored"]["sp_private_key_set"] is False


async def test_saml_test_endpoint(api, no_env_sso, db):
    resp = await api.post("/api/sso/saml/test", json={"metadata_xml": IDP_METADATA})
    assert resp.json() == {
        "ok": True,
        "idp_entity_id": "https://idp.example.com/saml",
        "sso_url": "https://idp.example.com/saml/sso",
        "error": None,
    }
    resp = await api.post("/api/sso/saml/test", json={})
    assert resp.json()["ok"] is False
    assert await db.get(SamlSettings, SINGLETON_ID) is None


async def test_saml_delete_reverts_to_env(api, no_env_sso):
    await api.put("/api/sso/saml", json={"enabled": True, "metadata_xml": IDP_METADATA})
    assert (await api.delete("/api/sso/saml")).status_code == 204
    body = (await api.get("/api/sso/saml")).json()
    assert body["source"] == "none"
    assert body["enabled"] is False


def test_saml_identity_attribute_mapping():
    cfg = saml.ResolvedSaml(
        source=SettingsSource.database, enabled=True, metadata_url="", sp_entity_id="",
        acs_url="", email_attribute="mail", name_attribute="cn",
    )
    attrs = {"mail": ["a@example.com"], "cn": ["Ada"], "email": ["other@example.com"]}
    assert saml.identity_from(cfg, "nameid", attrs) == ("a@example.com", "Ada")
    cfg.email_attribute = cfg.name_attribute = ""
    assert saml.identity_from(cfg, "nameid", attrs) == ("other@example.com", "")
    assert saml.identity_from(cfg, "n@example.com", {}) == ("n@example.com", "")


# ── Secrets ───────────────────────────────────────────────────────────────
def test_secret_roundtrip():
    token = security.encrypt_secret("s")
    assert security.decrypt_secret(token) == "s"
