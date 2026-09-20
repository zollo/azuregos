"""Liveness/readiness endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.services.ado_client import get_ado_client

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness — always cheap, no dependencies."""
    return {"status": "ok", "env": settings.env}


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
    """Readiness — checks the DB and reports ADO configuration."""
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {
        "database": db_ok,
        "ado_configured": get_ado_client().configured,
        "oidc_enabled": settings.oidc_enabled,
        "saml_enabled": settings.saml_enabled,
    }
