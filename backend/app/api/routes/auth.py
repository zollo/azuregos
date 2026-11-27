"""Authentication routes: local login/registration + OIDC + SAML."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.openapi import mcp_exclude
from app.core.auth_providers import oidc, saml
from app.core.security import create_access_token
from app.db import get_db
from app.models.user import AuthProvider, User
from app.schemas.sso import AuthProviders
from app.schemas.user import LoginRequest, RegisterRequest, Token, UserRead
from app.services import user_service
from app.services.sso_settings import (
    ResolvedOidc,
    ResolvedSaml,
    frontend_url,
    resolve_oidc,
    resolve_saml,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_CREDENTIAL_EXCHANGE = mcp_exclude(
    "Returns a bearer token; the MCP server authenticates itself and must not "
    "hand tokens to the model."
)
_BROWSER_FLOW = mcp_exclude("Browser redirect step of federated login.")


def _token_for(user: User) -> Token:
    access = create_access_token(user.id, extra={"role": user.role.value})
    return Token(access_token=access, user=UserRead.model_validate(user))


@router.post("/login", response_model=Token, openapi_extra=_CREDENTIAL_EXCHANGE)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> Token:
    user = await user_service.authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return _token_for(user)


@router.post(
    "/register",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=_CREDENTIAL_EXCHANGE,
)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> Token:
    """Self-service end-user registration (creates a local end_user account)."""
    if await user_service.get_by_email(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    user = await user_service.create_local_user(
        db,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
    )
    return _token_for(user)


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/providers", response_model=AuthProviders)
async def providers(db: AsyncSession = Depends(get_db)) -> AuthProviders:
    """Tell the frontend which login buttons to render, and their labels."""
    oidc_cfg = await resolve_oidc(db)
    saml_cfg = await resolve_saml(db)
    return AuthProviders(
        local=True,
        oidc=oidc_cfg.active,
        saml=saml_cfg.active,
        oidc_label=oidc_cfg.label,
        saml_label=saml_cfg.label,
    )


def _login_redirect(user: User, status_code: int = 307) -> RedirectResponse:
    token = create_access_token(user.id, extra={"role": user.role.value})
    return RedirectResponse(
        f"{frontend_url()}/auth/callback#token={token}", status_code=status_code
    )


# ── OIDC / OAuth2 ────────────────────────────────────────────────────────
async def _active_oidc(db: AsyncSession) -> ResolvedOidc:
    cfg = await resolve_oidc(db)
    if not cfg.active:
        raise HTTPException(status_code=404, detail="OIDC not enabled")
    return cfg


@router.get("/oidc/login", openapi_extra=_BROWSER_FLOW)
async def oidc_login(db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    cfg = await _active_oidc(db)
    try:
        url = await oidc.authorization_url(cfg)
    except oidc.OIDCError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse(url)


@router.get("/oidc/callback", openapi_extra=_BROWSER_FLOW)
async def oidc_callback(
    code: str, state: str, db: AsyncSession = Depends(get_db)
) -> RedirectResponse:
    cfg = await _active_oidc(db)
    try:
        oidc.verify_state(state)
    except oidc.OIDCError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    claims = await oidc.exchange_code(cfg, code)
    email = claims.get("email")
    subject = claims.get("sub")
    if not email or not subject:
        raise HTTPException(status_code=400, detail="OIDC response missing email/sub")
    user = await user_service.upsert_federated_user(
        db,
        provider=AuthProvider.oidc,
        external_id=str(subject),
        email=email,
        display_name=claims.get("name", ""),
    )
    return _login_redirect(user)


# ── SAML ─────────────────────────────────────────────────────────────────
async def _saml_request_data(request: Request) -> dict:
    form = {}
    if request.method == "POST":
        form = dict(await request.form())
    return {
        "scheme": request.url.scheme,
        "host": request.url.hostname or "",
        "port": request.url.port,
        "path": request.url.path,
        "query": dict(request.query_params),
        "form": form,
    }


async def _active_saml(db: AsyncSession) -> ResolvedSaml:
    cfg = await resolve_saml(db)
    if not cfg.active:
        raise HTTPException(status_code=404, detail="SAML not enabled")
    return cfg


@router.get("/saml/login", openapi_extra=_BROWSER_FLOW)
async def saml_login(request: Request, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    cfg = await _active_saml(db)
    try:
        url = saml.login_redirect_url(cfg, await _saml_request_data(request))
    except saml.SAMLError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse(url)


@router.post("/saml/acs", openapi_extra=_BROWSER_FLOW)
async def saml_acs(request: Request, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    cfg = await _active_saml(db)
    try:
        result = saml.process_acs(cfg, await _saml_request_data(request))
    except saml.SAMLError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    nameid = result["nameid"]
    email, name = saml.identity_from(cfg, nameid, result["attributes"])
    user = await user_service.upsert_federated_user(
        db,
        provider=AuthProvider.saml,
        external_id=nameid,
        email=email,
        display_name=name,
    )
    return _login_redirect(user, status_code=303)
