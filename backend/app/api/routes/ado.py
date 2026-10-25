"""Azure DevOps admin endpoints: the connection settings and the metadata
pickers (projects / work-item types / area paths) used by the portal editor.

The connection is super-admin only: its PAT is the identity every ticket and
reply is posted under, and switching it affects every portal. The pickers are
open to anyone who can edit a portal, portal admins included.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_staff, get_current_super_admin
from app.core.security import encrypt_secret
from app.db import get_db
from app.models.ado_connection import SINGLETON_ID, AdoConnection
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ado import (
    AdoConnectionStatus,
    AdoConnectionTestResult,
    AdoConnectionValues,
    AdoConnectionWrite,
    AdoStoredConnection,
)
from app.services.ado_client import ADOClient, ADOError
from app.services.ado_connection import (
    env_connection,
    get_ado_client,
    get_stored_connection,
    resolve_connection,
    stored_connection,
)

router = APIRouter(prefix="/ado", tags=["ado"], dependencies=[Depends(get_current_staff)])


# ── Connection settings ───────────────────────────────────────────────────
async def _connection_status(db: AsyncSession) -> AdoConnectionStatus:
    row = await get_stored_connection(db)
    env = env_connection()
    effective = await resolve_connection(db)
    stored = None
    if row is not None:
        updated_by = await db.get(User, row.updated_by_id) if row.updated_by_id else None
        stored = AdoStoredConnection(
            org_url=row.org_url,
            default_project=row.default_project,
            pat_set=bool(row.pat_encrypted),
            updated_at=row.updated_at,
            updated_by=updated_by.email if updated_by else None,
        )
    return AdoConnectionStatus(
        source=effective.source.value,
        configured=effective.configured,
        stored=stored,
        environment=AdoConnectionValues(
            org_url=env.org_url, default_project=env.default_project, pat_set=bool(env.pat)
        ),
        error=effective.error,
    )


async def _payload_pat(db: AsyncSession, payload: AdoConnectionWrite) -> str:
    """The PAT to use: the submitted one, else the saved one."""
    if payload.pat:
        return payload.pat
    row = await get_stored_connection(db)
    pat = stored_connection(row).pat if row is not None else ""
    if not pat:
        raise HTTPException(status_code=422, detail="A personal access token is required")
    return pat


async def _verify(client: ADOClient) -> int:
    """Check a connection; returns the number of projects visible.

    Raises ``ADOError``: non-retryable for a definite rejection (bad PAT, not an
    ADO org, unknown default project), retryable when ADO is just unreachable.
    """
    projects = await client.list_projects()
    if client.default_project:
        # Look it up directly: the project list is paginated.
        try:
            await client.get_project(client.default_project)
        except ADOError as exc:
            if exc.status_code != 404:
                raise
            raise ADOError(
                f"Project '{client.default_project}' was not found in this organization",
                status_code=404,
                retryable=False,
            ) from exc
    return len(projects)


def _same_org(a: str, b: str) -> bool:
    return a.strip().rstrip("/").lower() == b.strip().rstrip("/").lower()


async def _linked_ticket_count(db: AsyncSession) -> int:
    return await db.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.ado_work_item_id.is_not(None))
    ) or 0


async def _guard_org_switch(db: AsyncSession, new_org_url: str) -> None:
    """Block switching organizations while tickets are linked to work items.

    Tickets store only a work-item ID, so pointing them at another org would
    make refreshes and discussions hit unrelated work items with the same ID.
    """
    current = await resolve_connection(db)
    if not current.org_url or not new_org_url or _same_org(current.org_url, new_org_url):
        return
    linked = await _linked_ticket_count(db)
    if linked:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{linked} ticket(s) are linked to work items in {current.org_url}. "
                "Switching to a different organization would point them at unrelated "
                "work items, so it isn't allowed."
            ),
        )


@router.get(
    "/connection",
    response_model=AdoConnectionStatus,
    dependencies=[Depends(get_current_super_admin)],
)
async def get_connection(db: AsyncSession = Depends(get_db)) -> AdoConnectionStatus:
    """Which connection is in effect, plus the saved and env values (no PATs)."""
    return await _connection_status(db)


@router.post(
    "/connection/test",
    response_model=AdoConnectionTestResult,
    dependencies=[Depends(get_current_super_admin)],
)
async def test_connection(
    payload: AdoConnectionWrite, db: AsyncSession = Depends(get_db)
) -> AdoConnectionTestResult:
    """Check connection values without saving. A blank PAT uses the saved one."""
    pat = await _payload_pat(db, payload)
    client = ADOClient(org_url=payload.org_url, pat=pat, default_project=payload.default_project)
    try:
        count = await _verify(client)
    except ADOError as exc:
        return AdoConnectionTestResult(ok=False, error=str(exc))
    return AdoConnectionTestResult(ok=True, project_count=count)


@router.put("/connection", response_model=AdoConnectionStatus)
async def save_connection(
    payload: AdoConnectionWrite,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_super_admin),
) -> AdoConnectionStatus:
    """Save the UI connection; it then takes precedence over the ADO_* env vars.

    The values are verified against ADO first. A definite rejection (bad PAT,
    unknown org/project) blocks the save; a transient error doesn't, matching
    how portal saves treat an unreachable ADO.
    """
    pat = await _payload_pat(db, payload)
    await _guard_org_switch(db, payload.org_url)
    client = ADOClient(org_url=payload.org_url, pat=pat, default_project=payload.default_project)
    try:
        await _verify(client)
    except ADOError as exc:
        if not exc.retryable:
            raise HTTPException(
                status_code=422, detail=f"Azure DevOps rejected the connection: {exc}"
            ) from exc

    row = await get_stored_connection(db)
    if row is None:
        row = AdoConnection(id=SINGLETON_ID)
        db.add(row)
    row.org_url = payload.org_url
    row.default_project = payload.default_project
    row.pat_encrypted = encrypt_secret(pat)
    row.updated_by_id = admin.id
    await db.commit()
    await db.refresh(row)
    return await _connection_status(db)


@router.delete(
    "/connection",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_super_admin)],
)
async def delete_connection(db: AsyncSession = Depends(get_db)):
    """Remove the saved connection, reverting to the ADO_* env vars."""
    row = await get_stored_connection(db)
    if row is not None:
        await _guard_org_switch(db, env_connection().org_url)
        await db.delete(row)
        await db.commit()


# ── Metadata pickers ──────────────────────────────────────────────────────


@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db)) -> dict:
    """Projects in the configured org. Never errors hard so the editor can fall
    back to a free-text field: returns ``configured`` and an optional ``error``.
    """
    client = await get_ado_client(db)
    if not client.configured:
        return {"configured": False, "projects": [], "error": None}
    try:
        items = await client.list_projects()
    except ADOError as exc:
        return {"configured": True, "projects": [], "error": str(exc)}
    return {
        "configured": True,
        "default_project": client.default_project or None,
        "projects": [{"id": p.get("id"), "name": p.get("name")} for p in items],
        "error": None,
    }


@router.get("/work-item-types")
async def list_work_item_types(
    project: str | None = None, db: AsyncSession = Depends(get_db)
) -> dict:
    """Work-item types for ``project`` (or the server default if omitted)."""
    client = await get_ado_client(db)
    if not client.configured:
        return {"configured": False, "work_item_types": [], "error": None}
    proj = project or client.default_project
    if not proj:
        return {"configured": True, "work_item_types": [], "error": "No project specified"}
    try:
        items = await client.list_work_item_types(proj)
    except ADOError as exc:
        return {"configured": True, "work_item_types": [], "error": str(exc)}
    return {
        "configured": True,
        "work_item_types": [
            {"name": t.get("name"), "reference_name": t.get("referenceName")}
            for t in items
        ],
        "error": None,
    }


@router.get("/area-paths")
async def list_area_paths(
    project: str | None = None, db: AsyncSession = Depends(get_db)
) -> dict:
    """Valid area paths for ``project`` (or the server default if omitted)."""
    client = await get_ado_client(db)
    if not client.configured:
        return {"configured": False, "area_paths": [], "error": None}
    proj = project or client.default_project
    if not proj:
        return {"configured": True, "area_paths": [], "error": "No project specified"}
    try:
        paths = await client.list_area_paths(proj)
    except ADOError as exc:
        return {"configured": True, "area_paths": [], "error": str(exc)}
    return {"configured": True, "area_paths": paths, "error": None}
