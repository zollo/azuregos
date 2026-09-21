"""Category routes: public read, admin write."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.utils import slugify
from app.db import get_db
from app.models.category import Category
from app.models.portal import Portal
from app.schemas.category import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    CategoryWithCount,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryWithCount])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[CategoryWithCount]:
    """List categories with a count of their active portals."""
    result = await db.execute(
        select(Category, func.count(Portal.id))
        .outerjoin(
            Portal,
            (Portal.category_id == Category.id) & (Portal.is_active.is_(True)),
        )
        .group_by(Category.id)
        .order_by(Category.sort_order, Category.name)
    )
    out: list[CategoryWithCount] = []
    for category, count in result.all():
        item = CategoryWithCount.model_validate(category)
        item.portal_count = count
        out.append(item)
    return out


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base = slugify(name)
    slug = base
    i = 2
    while (await db.execute(select(Category).where(Category.slug == slug))).scalar_one_or_none():
        slug = f"{base}-{i}"
        i += 1
    return slug


@router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_admin)],
)
async def create_category(payload: CategoryCreate, db: AsyncSession = Depends(get_db)) -> Category:
    category = Category(
        name=payload.name,
        slug=await _unique_slug(db, payload.name),
        description=payload.description,
        icon=payload.icon,
        sort_order=payload.sort_order,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.patch(
    "/{category_id}",
    response_model=CategoryRead,
    dependencies=[Depends(get_current_admin)],
)
async def update_category(
    category_id: uuid.UUID, payload: CategoryUpdate, db: AsyncSession = Depends(get_db)
) -> Category:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        category.slug = await _unique_slug(db, data["name"])
    for key, value in data.items():
        setattr(category, key, value)
    await db.commit()
    await db.refresh(category)
    return category


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_admin)],
)
async def delete_category(category_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    # Portals keep their data; category_id is set null -> they fall into General.
    await db.delete(category)
    await db.commit()
