"""Aggregate all API routers under a single /api router."""
from fastapi import APIRouter

from app.api.routes import auth, categories, health, portals, tickets, users

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(categories.router)
api_router.include_router(portals.router)
api_router.include_router(tickets.router)
