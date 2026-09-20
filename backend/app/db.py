"""Database engine, session factory, and the declarative base."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.env == "development",
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


def create_worker_engine() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """A short-lived engine + sessionmaker for Celery tasks.

    Celery runs each task in a fresh ``asyncio.run`` loop. A pooled connection
    is bound to the loop that created it, so reusing the app's shared engine
    across loops raises "attached to a different loop". ``NullPool`` sidesteps
    this by never reusing connections; the caller disposes the engine per run.
    """
    worker_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    return worker_engine, async_sessionmaker(
        worker_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
