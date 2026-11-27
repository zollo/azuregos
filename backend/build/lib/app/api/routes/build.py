"""Build information endpoint (authenticated users only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models.user import User
from app.schemas.build import BuildInfo
from app.services.ado_connection import resolve_connection

router = APIRouter(tags=["build"])


@router.get("/build-info", response_model=BuildInfo)
async def build_info(
    _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> BuildInfo:
    """Current build/runtime info. Requires authentication."""
    ado = await resolve_connection(db)
    return BuildInfo(
        version=settings.app_version,
        git_commit=settings.git_commit,
        build_time=settings.build_time,
        environment=settings.env,
        ado_configured=ado.configured,
        ado_source=ado.source.value,
    )
