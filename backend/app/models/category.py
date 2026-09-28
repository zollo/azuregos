"""Portal category. Uncategorized portals surface under a virtual 'General'."""
from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UUIDMixin


class Category(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True, nullable=False)
    # Markdown-capable description shown to end users.
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    icon: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    portals: Mapped[list["Portal"]] = relationship(  # noqa: F821
        back_populates="category"
    )
