"""Ticket schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ticket import SyncStatus


class TicketCreate(BaseModel):
    portal_id: uuid.UUID
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    # Values for the portal's custom fields, keyed by FieldDefinition.name
    field_values: dict = Field(default_factory=dict)


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portal_id: uuid.UUID
    title: str
    description: str
    field_values: dict
    submitter_email: str
    ado_work_item_id: int | None
    ado_url: str | None
    ado_state: str | None
    sync_status: SyncStatus
    sync_attempts: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class TicketListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    portal_id: uuid.UUID
    ado_work_item_id: int | None
    ado_url: str | None
    ado_state: str | None
    sync_status: SyncStatus
    created_at: datetime
