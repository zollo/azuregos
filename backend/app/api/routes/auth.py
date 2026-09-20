"""Authentication routes: local login/registration + OIDC + SAML."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.core.auth_providers import oidc, saml
from app.core.security import create_access_token
from app.db import get_db
from app.models.user import AuthProvider, User
from app.schemas.user import LoginRequest, RegisterRequest, Token, UserRead
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _frontend_url() -> str:
    origins = settings.cors_origin_list
    return origins[0] if origins else "http://localhost:8080"


def _token_for(user: User) -> Token:
    access = create_access_token(user.id, extra={"role": user.role.value})
    return Token(access_token=access, user=UserRead.model_validate(user))


@router.post("/login", response_model=Token)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> Token:
    user = await user_service.authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return _token_for(user)


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
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


@router.get("/providers")
async def providers() -> dict:
    """Tell the frontend which login buttons to render."""
    return {"local": True, "oidc": settings.oidc_enabled, "saml": settings.saml_enabled}


# ── OIDC / OAuth2 ────────────────────────────────────────────────────────
@router.get("/oidc/login")
async def oidc_login() -> RedirectResponse:
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="OIDC not enabled")
    url = await oidc.authorization_url()
    return RedirectResponse(url)


@router.get("/oidc/callback")
async def oidc_callback(
    code: str, state: str, db: AsyncSession = Depends(get_db)
) -> RedirectResponse:
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="OIDC not enabled")
    oidc.verify_state(state)
    claims = await oidc.exchange_code(code)
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
    token = create_access_token(user.id, extra={"role": user.role.value})
    return RedirectResponse(f"{_frontend_url()}/auth/callback#token={token}")


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


@router.get("/saml/login")
async def saml_login(request: Request) -> RedirectResponse:
    if not settings.saml_enabled:
        raise HTTPException(status_code=404, detail="SAML not enabled")
    url = saml.login_redirect_url(await _saml_request_data(request))
    return RedirectResponse(url)


@router.post("/saml/acs")
async def saml_acs(request: Request, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    if not settings.saml_enabled:
        raise HTTPException(status_code=404, detail="SAML not enabled")
    try:
        result = saml.process_acs(await _saml_request_data(request))
    except saml.SAMLError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    nameid = result["nameid"]
    attrs = result["attributes"]
    email = _first(attrs.get("email")) or _first(attrs.get(
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
    )) or nameid
    name = _first(attrs.get("displayName")) or ""
    user = await user_service.upsert_federated_user(
        db,
        provider=AuthProvider.saml,
        external_id=nameid,
        email=email,
        display_name=name,
    )
    token = create_access_token(user.id, extra={"role": user.role.value})
    return RedirectResponse(
        f"{_frontend_url()}/auth/callback#token={token}", status_code=303
    )


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value
