"""Resolve which Azure DevOps connection is in effect.

There are two sources:

* **database** — a connection an admin saved in the UI (``ado_connection``).
* **environment** — the ``ADO_ORG_URL`` / ``ADO_PAT`` / ``ADO_DEFAULT_PROJECT``
  env vars (the original, still-supported method).

Precedence: a saved connection wins over the env vars, and replaces them as a
whole (fields are never mixed across sources, so a PAT can't end up paired with
another org's URL). Deleting the saved connection reverts to the env vars.

The row is read on every call so the API and the Celery worker pick up changes
without a restart.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import SecretDecryptionError, decrypt_secret
from app.models.ado_connection import SINGLETON_ID, AdoConnection
from app.services.ado_client import ADOClient

logger = logging.getLogger(__name__)


class ConnectionSource(StrEnum):
    database = "database"
    environment = "environment"
    none = "none"


@dataclass
class ResolvedConnection:
    source: ConnectionSource
    org_url: str
    pat: str
    default_project: str
    # Set when a saved connection exists but can't be used (e.g. its PAT can't
    # be decrypted after a SECRET_KEY rotation).
    error: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.org_url and self.pat)

    def client(self) -> ADOClient:
        return ADOClient(
            org_url=self.org_url, pat=self.pat, default_project=self.default_project
        )


def env_connection() -> ResolvedConnection:
    configured = bool(settings.ado_org_url and settings.ado_pat)
    return ResolvedConnection(
        source=ConnectionSource.environment if configured else ConnectionSource.none,
        org_url=settings.ado_org_url,
        pat=settings.ado_pat,
        default_project=settings.ado_default_project,
    )


async def get_stored_connection(db: AsyncSession) -> AdoConnection | None:
    return await db.get(AdoConnection, SINGLETON_ID)


def stored_connection(row: AdoConnection) -> ResolvedConnection:
    try:
        pat = decrypt_secret(row.pat_encrypted)
    except SecretDecryptionError:
        logger.error("Saved ADO PAT can't be decrypted; was SECRET_KEY changed?")
        # Fail closed rather than silently falling back to the env vars: the
        # admin explicitly chose this connection.
        return ResolvedConnection(
            source=ConnectionSource.database,
            org_url=row.org_url,
            pat="",
            default_project=row.default_project,
            error="The saved PAT can't be decrypted (SECRET_KEY changed?). Re-enter it.",
        )
    return ResolvedConnection(
        source=ConnectionSource.database,
        org_url=row.org_url,
        pat=pat,
        default_project=row.default_project,
    )


async def resolve_connection(db: AsyncSession) -> ResolvedConnection:
    row = await get_stored_connection(db)
    if row is not None:
        return stored_connection(row)
    return env_connection()


async def get_ado_client(db: AsyncSession) -> ADOClient:
    """The ADO client for the connection currently in effect."""
    return (await resolve_connection(db)).client()
