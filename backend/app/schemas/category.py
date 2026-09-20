"""Category schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    icon: str = "folder"
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    icon: str | None = None
    sort_order: int | None = None


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    created_at: datetime


class CategoryWithCount(CategoryRead):
    portal_count: int = 0
