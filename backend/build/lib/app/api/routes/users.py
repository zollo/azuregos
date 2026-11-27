"""Admin user management.

Admins and super admins manage users. Only a super admin may grant the
super_admin role or change a super admin's account, and the last active super
admin can't be demoted, disabled or deleted.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.security import hash_password
from app.db import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(get_current_admin)])


def _check_grant(actor: User, role: UserRole) -> None:
    if not actor.can_grant(role):
        raise HTTPException(
            status_code=403, detail=f"You can't grant the {role.value} role"
        )


def _check_manage(actor: User, target: User) -> None:
    if not actor.can_manage_user(target):
        raise HTTPException(
            status_code=403, detail="Only a super admin can change a super admin's account"
        )


async def _guard_last_super_admin(db: AsyncSession, target: User) -> None:
    """Refuse to remove the last active super admin (call before the change)."""
    if target.is_super_admin and target.is_active:
        if await user_service.count_active_super_admins(db) <= 1:
            raise HTTPException(
                status_code=400, detail="There must be at least one active super admin"
            )


async def _assign_portals(db: AsyncSession, user: User, portal_ids: list[uuid.UUID]) -> None:
    try:
        await user_service.set_portal_assignments(db, user, portal_ids)
    except user_service.UnknownPortalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[UserRead])
async def list_users(db: AsyncSession = Depends(get_db)) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> User:
    _check_grant(admin, payload.role)
    if await user_service.get_by_email(db, payload.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    portal_ids = payload.portal_ids if payload.role == UserRole.portal_admin else []
    try:
        await user_service.ensure_portals_exist(db, set(portal_ids))
    except user_service.UnknownPortalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = await user_service.create_local_user(
        db,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        role=payload.role,
    )
    if portal_ids:
        await _assign_portals(db, user, portal_ids)
        await db.commit()
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    _check_manage(admin, user)
    if payload.role is not None and payload.role != user.role:
        _check_grant(admin, payload.role)
        await _guard_last_super_admin(db, user)
    if payload.is_active is False:
        await _guard_last_super_admin(db, user)

    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)
    if payload.portal_ids is not None or payload.role is not None:
        portal_ids = payload.portal_ids if payload.portal_ids is not None else user.portal_ids
        await _assign_portals(db, user, portal_ids)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    _check_manage(admin, user)
    await _guard_last_super_admin(db, user)
    await db.delete(user)
    await db.commit()
