"""Portal: a modular form that fronts an Azure DevOps work-item type.

A portal exposes only the fields an admin chooses. The Title and Description
(rendered as the "Discussion"/summary) fields are always present and are not
stored in ``fields`` — they are implicit. ``fields`` holds the *additional*
custom fields. See ``app.schemas.portal.FieldDefinition`` for the shape.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UUIDMixin


class Portal(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "portals"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    icon: Mapped[str] = mapped_column(String(60), default="ticket", nullable=False)

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Azure DevOps mapping
    ado_project: Mapped[str | None] = mapped_column(String(200), nullable=True)
    work_item_type: Mapped[str] = mapped_column(String(100), default="Issue", nullable=False)

    # List[FieldDefinition] — custom fields beyond Title/Description.
    fields: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    category: Mapped["Category | None"] = relationship(  # noqa: F821
        back_populates="portals", lazy="joined"
    )
    tickets: Mapped[list["Ticket"]] = relationship(  # noqa: F821
        back_populates="portal"
    )
