"""Azuregos FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.config import settings
from app.db import AsyncSessionLocal
from app.models.user import UserRole
from app.services import user_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("azuregos")


async def _bootstrap_admin() -> None:
    """Create the initial admin account if it does not exist yet."""
    async with AsyncSessionLocal() as db:
        existing = await user_service.get_by_email(db, settings.bootstrap_admin_email)
        if existing:
            return
        await user_service.create_local_user(
            db,
            email=settings.bootstrap_admin_email,
            password=settings.bootstrap_admin_password,
            display_name="Administrator",
            role=UserRole.admin,
        )
        logger.info("Bootstrapped admin user %s", settings.bootstrap_admin_email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await _bootstrap_admin()
    except Exception:  # noqa: BLE001
        # Don't crash the API if bootstrap fails (e.g. migrations not yet run).
        logger.exception("Admin bootstrap failed; continuing")
    yield


app = FastAPI(
    title="Azuregos",
    description="A service-desk front end for Azure DevOps.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root() -> dict:
    return {"name": "Azuregos", "version": app.version, "docs": "/docs"}
