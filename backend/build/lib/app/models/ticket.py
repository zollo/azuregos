"""Ticket: a submission through a portal.

This table doubles as the *offline cache*. When a submission cannot be pushed
to Azure DevOps (ADO down, auth error, transient failure) it is stored here
with ``sync_status = pending`` and the worker retries it periodically. Once it
lands in ADO, ``ado_work_item_id`` is populated and the status becomes
``synced``.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UUIDMixin


class SyncStatus(str, enum.Enum):
    pending = "pending"      # queued, not yet in ADO
    syncing = "syncing"      # a worker is currently pushing it
    synced = "synced"        # present in ADO (ado_work_item_id set)
    failed = "failed"        # exceeded max attempts; needs attention


class Ticket(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tickets"

    portal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    submitted_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Denormalized so we can tag/query ADO even if the user record changes.
    submitter_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)

    # Always-present fields
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Custom field values keyed by field name, as defined by the portal.
    field_values: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # ADO linkage
    ado_work_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ado_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ado_state: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Sync bookkeeping (the offline-cache retry loop)
    sync_status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, name="sync_status"),
        default=SyncStatus.pending,
        nullable=False,
        index=True,
    )
    sync_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    portal: Mapped["Portal"] = relationship(back_populates="tickets", lazy="joined")  # noqa: F821
