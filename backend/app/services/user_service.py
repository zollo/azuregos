"""User lookups, local authentication, and federated upsert."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.portal import Portal
from app.models.user import AuthProvider, PortalAdmin, User, UserRole


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


class UnknownPortalError(ValueError):
    pass


async def ensure_portals_exist(db: AsyncSession, portal_ids: set[uuid.UUID]) -> None:
    if not portal_ids:
        return
    found = set((await db.execute(select(Portal.id).where(Portal.id.in_(portal_ids)))).scalars())
    if missing := portal_ids - found:
        raise UnknownPortalError(
            "Unknown portal(s): " + ", ".join(sorted(str(m) for m in missing))
        )


async def set_portal_assignments(
    db: AsyncSession, user: User, portal_ids: list[uuid.UUID]
) -> None:
    """Make ``user`` a portal admin of exactly ``portal_ids`` (not committed).

    Only portal admins keep assignments; for any other role they're cleared.
    Raises ``UnknownPortalError`` if a portal doesn't exist.
    """
    wanted = set(portal_ids) if user.role == UserRole.portal_admin else set()
    await ensure_portals_exist(db, wanted)
    # Diff rather than replace: re-adding a row with the same key in one flush
    # can insert before the old one is deleted.
    current = {a.portal_id: a for a in user.portal_assignments}
    for portal_id, assignment in current.items():
        if portal_id not in wanted:
            user.portal_assignments.remove(assignment)
    for portal_id in wanted - current.keys():
        user.portal_assignments.append(PortalAdmin(portal_id=portal_id))


async def count_active_super_admins(db: AsyncSession) -> int:
    """Count active super admins, locking their rows until the caller commits.

    The lock serializes concurrent demotions/deletions: with two super admins,
    two requests removing one each would otherwise both count two and leave
    none. Rows are locked in id order so the requests can't deadlock.
    """
    result = await db.execute(
        select(User.id)
        .where(User.role == UserRole.super_admin, User.is_active.is_(True))
        .order_by(User.id)
        .with_for_update()
    )
    return len(result.all())
