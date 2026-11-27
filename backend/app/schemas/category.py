"""Category schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

_NAME = "Display name. The URL slug is derived from it."
_DESCRIPTION = "Description shown in the catalog (Markdown)."
_ICON = "Lucide icon name; empty uses the default icon."
_SORT_ORDER = "Position in the catalog; lower numbers come first."


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=120, description=_NAME)
    description: str = Field(default="", description=_DESCRIPTION)
    icon: str = Field(default="", description=_ICON)
    sort_order: int = Field(default=0, description=_SORT_ORDER)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120, description=_NAME)
    description: str | None = Field(default=None, description=_DESCRIPTION)
    icon: str | None = Field(default=None, description=_ICON)
    sort_order: int | None = Field(default=None, description=_SORT_ORDER)


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    created_at: datetime


class CategoryWithCount(CategoryRead):
    portal_count: int = 0
