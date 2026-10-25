"""Azure DevOps admin endpoints: the connection settings and the metadata
pickers (projects / work-item types / area paths) used by the portal editor."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.security import encrypt_secret
from app.db import get_db
from app.models.ado_connection import SINGLETON_ID, AdoConnection
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

router = APIRouter(prefix="/ado", tags=["ado"], dependencies=[Depends(get_current_admin)])


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


def _default_project_error(client: ADOClient, projects: list[dict]) -> str | None:
    if not client.default_project:
        return None
    names = {(p.get("name") or "").lower() for p in projects}
    if client.default_project.lower() in names:
        return None
    return f"Project '{client.default_project}' was not found in this organization"


async def _check_connection(client: ADOClient) -> AdoConnectionTestResult:
    """Try the connection by listing projects. Never raises."""
    try:
        projects = await client.list_projects()
    except ADOError as exc:
        return AdoConnectionTestResult(ok=False, error=str(exc))
    error = _default_project_error(client, projects)
    return AdoConnectionTestResult(ok=error is None, project_count=len(projects), error=error)


@router.get("/connection", response_model=AdoConnectionStatus)
async def get_connection(db: AsyncSession = Depends(get_db)) -> AdoConnectionStatus:
    """Which connection is in effect, plus the saved and env values (no PATs)."""
    return await _connection_status(db)


@router.post("/connection/test", response_model=AdoConnectionTestResult)
async def test_connection(
    payload: AdoConnectionWrite, db: AsyncSession = Depends(get_db)
) -> AdoConnectionTestResult:
    """Check connection values without saving. A blank PAT uses the saved one."""
    pat = await _payload_pat(db, payload)
    client = ADOClient(org_url=payload.org_url, pat=pat, default_project=payload.default_project)
    return await _check_connection(client)


@router.put("/connection", response_model=AdoConnectionStatus)
async def save_connection(
    payload: AdoConnectionWrite,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> AdoConnectionStatus:
    """Save the UI connection; it then takes precedence over the ADO_* env vars.

    The values are verified against ADO first. A definite rejection (bad PAT,
    unknown org/project) blocks the save; a transient error doesn't, matching
    how portal saves treat an unreachable ADO.
    """
    pat = await _payload_pat(db, payload)
    client = ADOClient(org_url=payload.org_url, pat=pat, default_project=payload.default_project)
    try:
        projects = await client.list_projects()
    except ADOError as exc:
        if not exc.retryable:
            raise HTTPException(
                status_code=422, detail=f"Azure DevOps rejected the connection: {exc}"
            ) from exc
    else:
        error = _default_project_error(client, projects)
        if error is not None:
            raise HTTPException(status_code=422, detail=error)

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


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(db: AsyncSession = Depends(get_db)):
    """Remove the saved connection, reverting to the ADO_* env vars."""
    row = await get_stored_connection(db)
    if row is not None:
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
