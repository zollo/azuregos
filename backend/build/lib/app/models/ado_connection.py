"""Admin-configured Azure DevOps connection (overrides the ADO_* env vars).

A singleton row (``id`` is always 1). When present it fully replaces the
environment configuration; deleting it reverts to the env vars. The PAT is
encrypted at rest (see ``app.core.secrets``) and never returned by the API.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin

SINGLETON_ID = 1


class AdoConnection(TimestampMixin, Base):
    __tablename__ = "ado_connection"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_ID)
    org_url: Mapped[str] = mapped_column(String(500), nullable=False)
    pat_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    default_project: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
