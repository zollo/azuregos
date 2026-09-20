"""Portal schemas, including the modular form field definition."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FieldType(str, enum.Enum):
    text = "text"
    textarea = "textarea"
    number = "number"
    select = "select"
    multiselect = "multiselect"
    date = "date"
    checkbox = "checkbox"
    email = "email"


class FieldDefinition(BaseModel):
    """One custom field on a portal form.

    ``name`` is the stable key used in ``Ticket.field_values``. If
    ``ado_field_ref`` is set (e.g. ``Microsoft.VSTS.Common.Priority``) the value
    is mapped directly onto that ADO field; otherwise the value is appended to
    the work-item description and mirrored into an Azuregos metadata tag.
    """

    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_]+$")
    label: str = Field(min_length=1, max_length=200)
    type: FieldType = FieldType.text
    required: bool = False
    placeholder: str = ""
    help_text: str = ""
    options: list[str] = Field(default_factory=list)  # for select/multiselect
    default: str | None = None
    ado_field_ref: str | None = None


class PortalBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    icon: str = "ticket"
    category_id: uuid.UUID | None = None
    ado_project: str | None = None
    work_item_type: str = "Issue"
    fields: list[FieldDefinition] = Field(default_factory=list)
    is_active: bool = True


class PortalCreate(PortalBase):
    pass


class PortalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    icon: str | None = None
    category_id: uuid.UUID | None = None
    ado_project: str | None = None
    work_item_type: str | None = None
    fields: list[FieldDefinition] | None = None
    is_active: bool | None = None


class PortalRead(PortalBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    category_name: str | None = None
    created_at: datetime


class PortalSummary(BaseModel):
    """Lightweight view for the end-user portal catalog."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str
    icon: str
    category_name: str | None = None
