"""Ticket routes: submit through a portal, track your own tickets."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.core.utils import html_to_text, text_to_html
from app.db import get_db
from app.models.portal import Portal
from app.models.ticket import SyncStatus, Ticket
from app.models.user import User
from app.schemas.ticket import (
    CommentCreate,
    TicketComment,
    TicketCreate,
    TicketListItem,
    TicketRead,
)
from app.services import ticket_service
from app.services.ado_client import ADOError, get_ado_client

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Ticket:
    portal = await db.get(Portal, payload.portal_id)
    if portal is None or not portal.is_active:
        raise HTTPException(status_code=404, detail="Portal not found")
    try:
        ticket = await ticket_service.create_ticket(
            db, portal=portal, user=user, payload=payload
        )
    except ticket_service.TicketValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ticket


@router.get("", response_model=list[TicketListItem])
async def list_my_tickets(
    all_tickets: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Ticket]:
    """List the caller's tickets. Admins may pass ?all_tickets=true for every ticket."""
    stmt = select(Ticket).order_by(Ticket.created_at.desc())
    if not (all_tickets and user.is_admin):
        stmt = stmt.where(Ticket.submitted_by_id == user.id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{ticket_id}", response_model=TicketRead)
async def get_ticket(
    ticket_id: uuid.UUID,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Ticket:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.submitted_by_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not your ticket")

    # Optionally pull the latest state (e.g. status) from ADO.
    if refresh and ticket.ado_work_item_id:
        ado = get_ado_client()
        if ado.configured:
            try:
                wi = await ado.get_work_item(ticket.ado_work_item_id)
                ticket.ado_state = wi.get("fields", {}).get("System.State")
                await db.commit()
                await db.refresh(ticket)
            except ADOError:
                pass
    return ticket


@router.post(
    "/{ticket_id}/retry",
    response_model=TicketRead,
    dependencies=[Depends(get_current_admin)],
)
async def retry_ticket(ticket_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Ticket:
    """Force an immediate re-sync of a pending/failed ticket (admin)."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.sync_status == SyncStatus.synced:
        return ticket
    # Reset failed state so it is eligible again, then try now.
    if ticket.sync_status == SyncStatus.failed:
        ticket.sync_status = SyncStatus.pending
        await db.commit()
    try:
        await ticket_service.push_ticket_to_ado(db, ticket)
    except ADOError as exc:
        raise HTTPException(status_code=502, detail=f"ADO sync failed: {exc}") from exc
    return ticket


# ── Discussion / comments ────────────────────────────────────────────────
async def _get_owned_ticket(ticket_id: uuid.UUID, db: AsyncSession, user: User) -> Ticket:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.submitted_by_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not your ticket")
    return ticket


def _to_comment(raw: dict) -> TicketComment:
    author = raw.get("createdBy") or {}
    return TicketComment(
        id=raw["id"],
        text=html_to_text(raw.get("text", "")),
        author=author.get("displayName") or "Unknown",
        author_email=author.get("uniqueName"),
        created_at=raw["createdDate"],
    )


@router.get("/{ticket_id}/comments", response_model=list[TicketComment])
async def list_ticket_comments(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TicketComment]:
    """The ADO discussion for a ticket. Empty until it's been synced to ADO."""
    ticket = await _get_owned_ticket(ticket_id, db, user)
    if not ticket.ado_work_item_id:
        return []
    ado = get_ado_client()
    if not ado.configured:
        return []
    project = ticket.portal.ado_project or ado.default_project
    try:
        raw = await ado.list_comments(project, ticket.ado_work_item_id)
    except ADOError as exc:
        raise HTTPException(status_code=502, detail=f"Could not load discussion: {exc}") from exc
    return [_to_comment(c) for c in raw]


@router.post(
    "/{ticket_id}/comments",
    response_model=TicketComment,
    status_code=status.HTTP_201_CREATED,
)
async def add_ticket_comment(
    ticket_id: uuid.UUID,
    payload: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketComment:
    """Post a reply to a ticket's discussion.

    Comments are created in ADO under the service account, so we prepend an
    attribution line naming the real author.
    """
    ticket = await _get_owned_ticket(ticket_id, db, user)
    if not ticket.ado_work_item_id:
        raise HTTPException(
            status_code=409,
            detail="This ticket hasn't been submitted to the service desk yet.",
        )
    ado = get_ado_client()
    if not ado.configured:
        raise HTTPException(status_code=503, detail="Azure DevOps is not configured")

    who = user.display_name or user.email
    attribution = text_to_html(f"{who} ({user.email})")
    body = f"<b>{attribution}</b> via Azuregos:<br>{text_to_html(payload.text)}"
    project = ticket.portal.ado_project or ado.default_project
    try:
        created = await ado.add_comment(project, ticket.ado_work_item_id, body)
    except ADOError as exc:
        raise HTTPException(status_code=502, detail=f"Could not post comment: {exc}") from exc
    return _to_comment(created)
