"""Azure DevOps metadata endpoints for the admin UI (project / type pickers)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_admin
from app.services.ado_client import ADOError, get_ado_client

router = APIRouter(prefix="/ado", tags=["ado"], dependencies=[Depends(get_current_admin)])


@router.get("/projects")
async def list_projects() -> dict:
    """Projects in the configured org. Never errors hard so the editor can fall
    back to a free-text field: returns ``configured`` and an optional ``error``.
    """
    client = get_ado_client()
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
async def list_work_item_types(project: str | None = None) -> dict:
    """Work-item types for ``project`` (or the server default if omitted)."""
    client = get_ado_client()
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
