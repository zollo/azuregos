"""Portal routes: public catalog + form fetch, admin CRUD."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.core.utils import slugify
from app.db import get_db
from app.models.category import Category
from app.models.portal import Portal
from app.models.user import User
from app.schemas.portal import (
    PortalCreate,
    PortalRead,
    PortalSummary,
    PortalUpdate,
)

router = APIRouter(prefix="/portals", tags=["portals"])

GENERAL = "General"


def _to_read(portal: Portal) -> PortalRead:
    data = PortalRead.model_validate(portal)
    data.category_name = portal.category.name if portal.category else GENERAL
    return data


# ── Public catalog (any authenticated user) ──────────────────────────────
@router.get("/catalog")
async def catalog(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    """Active portals grouped by category, with uncategorized under 'General'."""
    result = await db.execute(
        select(Portal).where(Portal.is_active.is_(True)).order_by(Portal.name)
    )
    portals = list(result.scalars().all())

    groups: dict[str, dict] = {}
    for p in portals:
        name = p.category.name if p.category else GENERAL
        sort_order = p.category.sort_order if p.category else 9999
        grp = groups.setdefault(
            name,
            {
                "category": name,
                "icon": p.category.icon if p.category else "folder",
                "sort_order": sort_order,
                "portals": [],
            },
        )
        grp["portals"].append(PortalSummary.model_validate(p).model_dump())

    ordered = sorted(groups.values(), key=lambda g: (g["sort_order"], g["category"]))
    return ordered


@router.get("/{slug}", response_model=PortalRead)
async def get_portal(
    slug: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PortalRead:
    result = await db.execute(select(Portal).where(Portal.slug == slug))
    portal = result.scalar_one_or_none()
    if portal is None or not portal.is_active:
        raise HTTPException(status_code=404, detail="Portal not found")
    return _to_read(portal)


# ── Admin CRUD ───────────────────────────────────────────────────────────
@router.get("", response_model=list[PortalRead], dependencies=[Depends(get_current_admin)])
async def list_all_portals(db: AsyncSession = Depends(get_db)) -> list[PortalRead]:
    result = await db.execute(select(Portal).order_by(Portal.name))
    return [_to_read(p) for p in result.scalars().all()]


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base = slugify(name)
    slug = base
    i = 2
    while (await db.execute(select(Portal).where(Portal.slug == slug))).scalar_one_or_none():
        slug = f"{base}-{i}"
        i += 1
    return slug


async def _validate_category(db: AsyncSession, category_id: uuid.UUID | None) -> None:
    if category_id is not None and await db.get(Category, category_id) is None:
        raise HTTPException(status_code=422, detail="Category does not exist")


@router.post(
    "",
    response_model=PortalRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_admin)],
)
async def create_portal(
    payload: PortalCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> PortalRead:
    await _validate_category(db, payload.category_id)
    portal = Portal(
        name=payload.name,
        slug=await _unique_slug(db, payload.name),
        description=payload.description,
        icon=payload.icon,
        category_id=payload.category_id,
        ado_project=payload.ado_project,
        work_item_type=payload.work_item_type,
        fields=[f.model_dump() for f in payload.fields],
        is_active=payload.is_active,
        created_by_id=admin.id,
    )
    db.add(portal)
    await db.commit()
    await db.refresh(portal)
    return _to_read(portal)


@router.patch(
    "/{portal_id}",
    response_model=PortalRead,
    dependencies=[Depends(get_current_admin)],
)
async def update_portal(
    portal_id: uuid.UUID, payload: PortalUpdate, db: AsyncSession = Depends(get_db)
) -> PortalRead:
    portal = await db.get(Portal, portal_id)
    if portal is None:
        raise HTTPException(status_code=404, detail="Portal not found")
    data = payload.model_dump(exclude_unset=True)
    if "category_id" in data:
        await _validate_category(db, data["category_id"])
    if "fields" in data and data["fields"] is not None:
        data["fields"] = [f for f in data["fields"]]  # already dicts via model_dump
    if "name" in data:
        portal.slug = await _unique_slug(db, data["name"])
    for key, value in data.items():
        setattr(portal, key, value)
    await db.commit()
    await db.refresh(portal)
    return _to_read(portal)


@router.delete(
    "/{portal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_admin)],
)
async def delete_portal(portal_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    portal = await db.get(Portal, portal_id)
    if portal is None:
        raise HTTPException(status_code=404, detail="Portal not found")
    await db.delete(portal)
    await db.commit()
