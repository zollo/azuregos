"""Portal routes: public catalog + form fetch, admin CRUD."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.config import settings
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
from app.services.ado_client import ADOError, get_ado_client

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


async def _validate_work_item_type(ado_project: str | None, work_item_type: str) -> None:
    """Reject a work-item type that isn't valid for the target ADO project.

    Only enforced when we can actually reach ADO and read the project's types:
    if ADO isn't configured, or the lookup fails transiently, the save is
    allowed (a missing project, however, is rejected).
    """
    client = get_ado_client()
    if not client.configured:
        return
    project = ado_project or settings.ado_default_project
    if not project:
        return
    try:
        types = await client.list_work_item_types(project)
    except ADOError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=422,
                detail=f"Azure DevOps project '{project}' was not found",
            ) from exc
        return  # transient/network error — don't block the save
    names = {t.get("name") for t in types if t.get("name")}
    if work_item_type not in names:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Work item type '{work_item_type}' is not valid for project "
                f"'{project}'. Valid types: {', '.join(sorted(names))}"
            ),
        )


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
    await _validate_work_item_type(payload.ado_project, payload.work_item_type)
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
    # Validate the effective project/type if either is changing.
    if "work_item_type" in data or "ado_project" in data:
        await _validate_work_item_type(
            data.get("ado_project", portal.ado_project),
            data.get("work_item_type", portal.work_item_type),
        )
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
async def delete_portal(portal_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    portal = await db.get(Portal, portal_id)
    if portal is None:
        raise HTTPException(status_code=404, detail="Portal not found")
    await db.delete(portal)
    await db.commit()
