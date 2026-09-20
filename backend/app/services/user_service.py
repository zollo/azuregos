"""User lookups, local authentication, and federated upsert."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import AuthProvider, User, UserRole


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_by_email(db, email)
    if user is None or not user.hashed_password or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def create_local_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str = "",
    role: UserRole = UserRole.end_user,
) -> User:
    user = User(
        email=email.lower(),
        display_name=display_name or email.split("@")[0],
        hashed_password=hash_password(password),
        role=role,
        provider=AuthProvider.local,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def upsert_federated_user(
    db: AsyncSession,
    *,
    provider: AuthProvider,
    external_id: str,
    email: str,
    display_name: str = "",
) -> User:
    """Find a federated user by (provider, external_id) or email; create if new."""
    result = await db.execute(
        select(User).where(
            User.provider == provider, User.external_id == external_id
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = await get_by_email(db, email)

    if user is None:
        user = User(
            email=email.lower(),
            display_name=display_name or email.split("@")[0],
            provider=provider,
            external_id=external_id,
            role=UserRole.end_user,
        )
        db.add(user)
    else:
        # Keep federation linkage fresh.
        user.provider = provider
        user.external_id = external_id
        if display_name:
            user.display_name = display_name
    await db.commit()
    await db.refresh(user)
    return user
