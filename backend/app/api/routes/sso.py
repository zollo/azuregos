"""Single sign-on settings (super admins only): OIDC and SAML.

Mirrors the ADO connection endpoints. Settings saved here override that
provider's ``OIDC_*`` / ``SAML_*`` env vars as a whole, including whether it is
enabled; ``DELETE`` reverts to the env vars. Secrets are write-only.

Saving an *enabled* provider checks it against the IdP first: a definite
problem (bad URL, not a discovery/metadata document, mismatched SP key pair)
blocks the save, while an unreachable IdP doesn't. Disabled settings are saved
without checks so they can be staged. Local sign-in always stays available, so
a broken SSO setup can't lock super admins out.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_super_admin
from app.core.auth_providers import oidc, saml
from app.core.security import encrypt_secret
from app.db import get_db
from app.models.sso_settings import SINGLETON_ID, OidcSettings, SamlSettings
from app.models.user import User
from app.schemas.sso import (
    OidcSettingsStatus,
    OidcSettingsValues,
    OidcSettingsWrite,
    OidcStoredSettings,
    OidcTestResult,
    SamlSettingsStatus,
    SamlSettingsValues,
    SamlSettingsWrite,
    SamlStoredSettings,
    SamlTestResult,
)
from app.services.sso_settings import (
    ResolvedOidc,
    ResolvedSaml,
    SettingsSource,
    default_acs_url,
    default_redirect_uri,
    env_oidc,
    env_saml,
    get_stored_oidc,
    get_stored_saml,
    resolve_oidc,
    resolve_saml,
    stored_oidc,
    stored_saml,
)

router = APIRouter(
    prefix="/sso", tags=["sso"], dependencies=[Depends(get_current_super_admin)]
)


async def _updated_by(db: AsyncSession, user_id) -> str | None:
    user = await db.get(User, user_id) if user_id else None
    return user.email if user else None


# ── OIDC ──────────────────────────────────────────────────────────────────
async def _oidc_status(db: AsyncSession) -> OidcSettingsStatus:
    row = await get_stored_oidc(db)
    env = env_oidc()
    effective = await resolve_oidc(db)
    stored = None
    if row is not None:
        stored = OidcStoredSettings(
            enabled=row.enabled,
            discovery_url=row.discovery_url,
            client_id=row.client_id,
            client_secret_set=bool(row.client_secret_encrypted),
            redirect_uri=row.redirect_uri,
            scopes=row.scopes,
            button_label=row.button_label,
            updated_at=row.updated_at,
            updated_by=await _updated_by(db, row.updated_by_id),
        )
    return OidcSettingsStatus(
        source=effective.source.value,
        enabled=effective.active,
        configured=effective.configured,
        stored=stored,
        environment=OidcSettingsValues(
            enabled=env.enabled,
            discovery_url=env.discovery_url,
            client_id=env.client_id,
            client_secret_set=bool(env.client_secret),
            redirect_uri=env.redirect_uri,
            scopes=env.scopes,
        ),
        effective_redirect_uri=effective.effective_redirect_uri,
        default_redirect_uri=default_redirect_uri(),
        error=effective.error,
    )


async def _oidc_candidate(db: AsyncSession, payload: OidcSettingsWrite) -> ResolvedOidc:
    """The submitted settings, with a blank client secret filled from the saved one."""
    secret = payload.client_secret or ""
    if not secret:
        row = await get_stored_oidc(db)
        if row is not None:
            saved = stored_oidc(row)
            if saved.error is None:
                secret = saved.client_secret
    return ResolvedOidc(
        source=SettingsSource.database,
        enabled=payload.enabled,
        discovery_url=payload.discovery_url,
        client_id=payload.client_id,
        client_secret=secret,
        redirect_uri=payload.redirect_uri,
        scopes=payload.scopes,
        button_label=payload.button_label,
    )


def _require_oidc_fields(cfg: ResolvedOidc) -> None:
    missing = [
        label
        for label, value in (
            ("discovery URL", cfg.discovery_url),
            ("client ID", cfg.client_id),
            ("client secret", cfg.client_secret),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=422, detail="To enable OIDC, set the " + ", ".join(missing) + "."
        )


@router.get("/oidc", response_model=OidcSettingsStatus)
async def get_oidc_settings(db: AsyncSession = Depends(get_db)) -> OidcSettingsStatus:
    """Which OIDC settings are in effect, plus the saved and env values (no secrets)."""
    return await _oidc_status(db)


@router.post("/oidc/test", response_model=OidcTestResult)
async def test_oidc_settings(payload: OidcSettingsWrite) -> OidcTestResult:
    """Fetch the discovery document without saving anything.

    This checks the IdP is reachable and the URL is an OpenID configuration;
    the client ID and secret can only be proven by a real sign-in.
    """
    if not payload.discovery_url:
        return OidcTestResult(ok=False, error="Enter a discovery URL to test.")
    try:
        doc = await oidc.fetch_discovery(payload.discovery_url)
    except oidc.OIDCError as exc:
        return OidcTestResult(ok=False, error=str(exc))
    return OidcTestResult(
        ok=True, issuer=doc.get("issuer"), authorization_endpoint=doc["authorization_endpoint"]
    )


@router.put("/oidc", response_model=OidcSettingsStatus)
async def save_oidc_settings(
    payload: OidcSettingsWrite,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_super_admin),
) -> OidcSettingsStatus:
    """Save OIDC settings; they then take precedence over the OIDC_* env vars."""
    cfg = await _oidc_candidate(db, payload)
    if cfg.enabled:
        _require_oidc_fields(cfg)
        try:
            await oidc.fetch_discovery(cfg.discovery_url)
        except oidc.OIDCError as exc:
            if not exc.transient:
                raise HTTPException(
                    status_code=422, detail=f"The discovery URL was rejected: {exc}"
                ) from exc

    row = await get_stored_oidc(db)
    if row is None:
        row = OidcSettings(id=SINGLETON_ID)
        db.add(row)
    row.enabled = cfg.enabled
    row.discovery_url = cfg.discovery_url
    row.client_id = cfg.client_id
    if payload.client_secret:
        row.client_secret_encrypted = encrypt_secret(payload.client_secret)
    elif row.client_secret_encrypted is None:
        row.client_secret_encrypted = ""
    row.redirect_uri = cfg.redirect_uri
    row.scopes = cfg.scopes or "openid email profile"
    row.button_label = cfg.button_label
    row.updated_by_id = admin.id
    await db.commit()
    await db.refresh(row)
    return await _oidc_status(db)


@router.delete("/oidc", status_code=status.HTTP_204_NO_CONTENT)
async def delete_oidc_settings(db: AsyncSession = Depends(get_db)):
    """Remove the saved OIDC settings, reverting to the OIDC_* env vars."""
    row = await get_stored_oidc(db)
    if row is not None:
        await db.delete(row)
        await db.commit()


# ── SAML ──────────────────────────────────────────────────────────────────
async def _saml_status(db: AsyncSession) -> SamlSettingsStatus:
    row = await get_stored_saml(db)
    env = env_saml()
    effective = await resolve_saml(db)
    stored = None
    if row is not None:
        stored = SamlStoredSettings(
            enabled=row.enabled,
            metadata_url=row.metadata_url,
            metadata_xml=row.metadata_xml,
            sp_entity_id=row.sp_entity_id,
            acs_url=row.acs_url,
            sp_x509_cert=row.sp_x509_cert,
            sp_private_key_set=bool(row.sp_private_key_encrypted),
            email_attribute=row.email_attribute,
            name_attribute=row.name_attribute,
            button_label=row.button_label,
            updated_at=row.updated_at,
            updated_by=await _updated_by(db, row.updated_by_id),
        )
    return SamlSettingsStatus(
        source=effective.source.value,
        enabled=effective.active,
        configured=effective.configured,
        stored=stored,
        environment=SamlSettingsValues(
            enabled=env.enabled,
            metadata_url=env.metadata_url,
            sp_entity_id=env.sp_entity_id,
            acs_url=env.acs_url,
        ),
        effective_acs_url=effective.effective_acs_url,
        effective_sp_entity_id=effective.effective_sp_entity_id,
        default_acs_url=default_acs_url(),
        error=effective.error,
    )


async def _saml_candidate(db: AsyncSession, payload: SamlSettingsWrite) -> ResolvedSaml:
    """The submitted settings; a blank private key keeps the saved one, unless
    the certificate was cleared (a key without its certificate is useless)."""
    key = payload.sp_private_key or ""
    if not key and payload.sp_x509_cert:
        row = await get_stored_saml(db)
        if row is not None:
            saved = stored_saml(row)
            if saved.error is None:
                key = saved.sp_private_key
    return ResolvedSaml(
        source=SettingsSource.database,
        enabled=payload.enabled,
        metadata_url=payload.metadata_url,
        metadata_xml=payload.metadata_xml,
        sp_entity_id=payload.sp_entity_id,
        acs_url=payload.acs_url,
        sp_x509_cert=payload.sp_x509_cert,
        sp_private_key=key,
        email_attribute=payload.email_attribute,
        name_attribute=payload.name_attribute,
        button_label=payload.button_label,
    )


def _pem(body: str, kind: str) -> bytes:
    if "-----BEGIN" in body:
        return body.encode()
    return f"-----BEGIN {kind}-----\n{body}\n-----END {kind}-----\n".encode()


def check_sp_keypair(cert: str, key: str) -> str | None:
    """None when the SP certificate and private key are usable together, else why not.

    Accepts PEM, or the bare base64 body python3-saml also accepts.
    """
    if not cert and not key:
        return None
    if not cert or not key:
        return "The SP certificate and private key must be set together."
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    try:
        certificate = x509.load_pem_x509_certificate(_pem(cert, "CERTIFICATE"))
    except ValueError:
        return "The SP certificate isn't a valid PEM X.509 certificate."
    private_key = None
    for kind in ("PRIVATE KEY", "RSA PRIVATE KEY"):
        try:
            private_key = serialization.load_pem_private_key(_pem(key, kind), password=None)
            break
        except (ValueError, TypeError):
            continue
    if private_key is None:
        return "The SP private key isn't a valid unencrypted PEM private key."
    fmt = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if certificate.public_key().public_bytes(*fmt) != private_key.public_key().public_bytes(*fmt):
        return "The SP private key doesn't match the SP certificate."
    return None


@router.get("/saml", response_model=SamlSettingsStatus)
async def get_saml_settings(db: AsyncSession = Depends(get_db)) -> SamlSettingsStatus:
    """Which SAML settings are in effect, plus the saved and env values (no key)."""
    return await _saml_status(db)


@router.post("/saml/test", response_model=SamlTestResult)
async def test_saml_settings(
    payload: SamlSettingsWrite, db: AsyncSession = Depends(get_db)
) -> SamlTestResult:
    """Read the IdP metadata (and check the SP key pair) without saving anything."""
    cfg = await _saml_candidate(db, payload)
    problem = check_sp_keypair(cfg.sp_x509_cert, cfg.sp_private_key)
    if problem:
        return SamlTestResult(ok=False, error=problem)
    try:
        idp = saml.parse_idp_metadata(cfg)["idp"]
    except saml.SAMLError as exc:
        return SamlTestResult(ok=False, error=str(exc))
    return SamlTestResult(
        ok=True, idp_entity_id=idp["entityId"], sso_url=idp["singleSignOnService"]["url"]
    )


@router.put("/saml", response_model=SamlSettingsStatus)
async def save_saml_settings(
    payload: SamlSettingsWrite,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_super_admin),
) -> SamlSettingsStatus:
    """Save SAML settings; they then take precedence over the SAML_* env vars."""
    cfg = await _saml_candidate(db, payload)
    problem = check_sp_keypair(cfg.sp_x509_cert, cfg.sp_private_key)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    if cfg.enabled:
        if not cfg.configured:
            raise HTTPException(
                status_code=422,
                detail="To enable SAML, set the IdP metadata URL or paste its metadata XML.",
            )
        try:
            saml.parse_idp_metadata(cfg)
        except saml.SAMLError as exc:
            if not exc.transient:
                raise HTTPException(
                    status_code=422, detail=f"The IdP metadata was rejected: {exc}"
                ) from exc

    row = await get_stored_saml(db)
    if row is None:
        row = SamlSettings(id=SINGLETON_ID)
        db.add(row)
    row.enabled = cfg.enabled
    row.metadata_url = cfg.metadata_url
    row.metadata_xml = cfg.metadata_xml
    row.sp_entity_id = cfg.sp_entity_id or "azuregos"
    row.acs_url = cfg.acs_url
    row.sp_x509_cert = cfg.sp_x509_cert
    if not cfg.sp_x509_cert:
        row.sp_private_key_encrypted = ""
    elif payload.sp_private_key:
        row.sp_private_key_encrypted = encrypt_secret(payload.sp_private_key)
    row.email_attribute = cfg.email_attribute
    row.name_attribute = cfg.name_attribute
    row.button_label = cfg.button_label
    row.updated_by_id = admin.id
    await db.commit()
    await db.refresh(row)
    return await _saml_status(db)


@router.delete("/saml", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saml_settings(db: AsyncSession = Depends(get_db)):
    """Remove the saved SAML settings, reverting to the SAML_* env vars."""
    row = await get_stored_saml(db)
    if row is not None:
        await db.delete(row)
        await db.commit()
