"""Ticket creation and Azure DevOps synchronization logic.

Shared by the API (best-effort immediate push on submit) and the Celery worker
(the retry loop for the offline cache).
"""
from __future__ import annotations

import html
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.portal import Portal
from app.models.ticket import SyncStatus, Ticket
from app.models.user import User
from app.schemas.portal import FieldDefinition
from app.schemas.ticket import TicketCreate
from app.services.ado_client import (
    TAG_MARKER,
    TAG_PORTAL_PREFIX,
    TAG_SUBMITTER_PREFIX,
    ADOClient,
    ADOError,
    get_ado_client,
)


class TicketValidationError(Exception):
    """Raised when a submission violates its portal's field definitions."""


def _validate_field_values(portal: Portal, values: dict) -> dict:
    """Validate submitted custom-field values against the portal definition."""
    cleaned: dict = {}
    definitions = [FieldDefinition(**f) for f in portal.fields]
    known = {d.name: d for d in definitions}

    for name, defn in known.items():
        raw = values.get(name, defn.default)
        if defn.required and (raw is None or raw == "" or raw == []):
            raise TicketValidationError(f"Field '{defn.label}' is required")
        if raw is None:
            continue
        if defn.type.value in ("select",) and defn.options and raw not in defn.options:
            raise TicketValidationError(f"Invalid option for '{defn.label}': {raw}")
        if defn.type.value == "multiselect" and defn.options:
            if not isinstance(raw, list) or any(v not in defn.options for v in raw):
                raise TicketValidationError(f"Invalid options for '{defn.label}'")
        cleaned[name] = raw

    # Silently drop values for fields the portal does not define.
    return cleaned


def build_tags(portal: Portal, ticket: Ticket) -> list[str]:
    return [
        TAG_MARKER,
        f"{TAG_PORTAL_PREFIX}{portal.slug}",
        f"{TAG_SUBMITTER_PREFIX}{ticket.submitter_email}",
    ]


def build_description(portal: Portal, ticket: Ticket) -> str:
    """Render the description, appending any custom fields not mapped to ADO."""
    definitions = {f["name"]: FieldDefinition(**f) for f in portal.fields}
    body = ticket.description or ""
    extras: list[str] = []
    for name, value in ticket.field_values.items():
        defn = definitions.get(name)
        if defn is None or defn.ado_field_ref:
            continue  # mapped fields go to real ADO fields, not the body
        label = defn.label if defn else name
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        extras.append(f"<li><strong>{html.escape(label)}:</strong> "
                      f"{html.escape(str(value))}</li>")
    if extras:
        body += "<hr/><p><em>Submitted via Azuregos portal "
        body += f"'{html.escape(portal.name)}'</em></p><ul>" + "".join(extras) + "</ul>"
    return body


def build_ado_fields(portal: Portal, ticket: Ticket) -> dict:
    """Values for custom fields that map to real ADO field reference names."""
    definitions = {f["name"]: FieldDefinition(**f) for f in portal.fields}
    mapped: dict = {}
    for name, value in ticket.field_values.items():
        defn = definitions.get(name)
        if defn and defn.ado_field_ref:
            mapped[defn.ado_field_ref] = value
    return mapped


async def create_ticket(
    db: AsyncSession,
    *,
    portal: Portal,
    user: User,
    payload: TicketCreate,
    ado: ADOClient | None = None,
) -> Ticket:
    """Persist a ticket locally, then attempt a best-effort push to ADO."""
    cleaned = _validate_field_values(portal, payload.field_values)

    ticket = Ticket(
        portal_id=portal.id,
        submitted_by_id=user.id,
        submitter_email=user.email,
        title=payload.title,
        description=payload.description,
        field_values=cleaned,
        sync_status=SyncStatus.pending,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)

    # Best-effort immediate sync. Failure is fine — the worker will retry.
    try:
        await push_ticket_to_ado(db, ticket, portal=portal, ado=ado)
    except ADOError:
        pass  # remains pending; already persisted in the cache
    return ticket


async def push_ticket_to_ado(
    db: AsyncSession,
    ticket: Ticket,
    *,
    portal: Portal | None = None,
    ado: ADOClient | None = None,
) -> Ticket:
    """Push a single cached ticket to ADO and update its sync bookkeeping."""
    if ticket.ado_work_item_id is not None:
        ticket.sync_status = SyncStatus.synced
        await db.commit()
        return ticket

    ado = ado or get_ado_client()
    if portal is None:
        portal = await db.get(Portal, ticket.portal_id)
    assert portal is not None

    ticket.sync_status = SyncStatus.syncing
    ticket.sync_attempts += 1
    ticket.last_attempt_at = datetime.now(UTC)
    await db.commit()

    if not ado.configured:
        ticket.sync_status = SyncStatus.pending
        ticket.last_error = "ADO not configured"
        await db.commit()
        raise ADOError("ADO not configured", retryable=True)

    try:
        work_item = await ado.create_work_item(
            project=portal.ado_project or settings.ado_default_project,
            work_item_type=portal.work_item_type,
            title=ticket.title,
            description=build_description(portal, ticket),
            tags=build_tags(portal, ticket),
            extra_fields=build_ado_fields(portal, ticket),
        )
    except ADOError as exc:
        ticket.last_error = str(exc)
        if not exc.retryable or ticket.sync_attempts >= settings.ado_max_retry_attempts:
            ticket.sync_status = SyncStatus.failed
        else:
            ticket.sync_status = SyncStatus.pending
        await db.commit()
        raise

    ticket.ado_work_item_id = work_item.get("id")
    ticket.ado_url = ado.web_url(work_item)
    ticket.ado_state = work_item.get("fields", {}).get("System.State")
    ticket.sync_status = SyncStatus.synced
    ticket.last_error = None
    await db.commit()
    await db.refresh(ticket)
    return ticket
