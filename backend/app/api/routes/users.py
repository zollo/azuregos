"""Admin user management."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.security import hash_password
from app.db import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=list[UserRead])
async def list_users(db: AsyncSession = Depends(get_db)) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    if await user_service.get_by_email(db, payload.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    return await user_service.create_local_user(
        db,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        role=payload.role,
    )


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID, payload: UserUpdate, db: AsyncSession = Depends(get_db)
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)
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
    await db.delete(user)
    await db.commit()
