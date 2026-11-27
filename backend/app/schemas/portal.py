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

    name: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_]+$",
        description="Stable key of the value in the ticket's field values.",
    )
    label: str = Field(min_length=1, max_length=200, description="Label shown on the form.")
    type: FieldType = Field(default=FieldType.text, description="Input type.")
    required: bool = Field(default=False, description="Whether the submitter must fill it in.")
    placeholder: str = Field(default="", description="Placeholder text of the input.")
    help_text: str = Field(default="", description="Help text shown under the input.")
    options: list[str] = Field(
        default_factory=list, description="Choices of a select or multiselect field."
    )
    default: str | None = Field(default=None, description="Initial value of the input.")
    ado_field_ref: str | None = Field(
        default=None,
        description=(
            "ADO field reference name to map the value onto, e.g. "
            "Microsoft.VSTS.Common.Priority. Unmapped values go into the description."
        ),
    )


_NAME = "Display name. The URL slug is derived from it."
_DESCRIPTION = "Description shown in the catalog and on the form (Markdown)."
_ICON = "Lucide icon name; empty inherits the category's icon."
_CATEGORY_ID = "ID of the catalog category; null puts the portal under General."
_ADO_PROJECT = "ADO project for the work items; null uses the connection's default project."
_WORK_ITEM_TYPE = "ADO work item type created for each ticket."
_AREA_PATH = "ADO area path (Project\\Team) for the work items; null uses the project root."
_FIELDS = "Custom form fields. Title and Description are implicit and not listed here."
_IS_ACTIVE = "Whether end users can see and submit to the portal."


class PortalBase(BaseModel):
    name: str = Field(min_length=1, max_length=160, description=_NAME)
    description: str = Field(default="", description=_DESCRIPTION)
    icon: str = Field(default="", description=_ICON)
    category_id: uuid.UUID | None = Field(default=None, description=_CATEGORY_ID)
    ado_project: str | None = Field(default=None, description=_ADO_PROJECT)
    work_item_type: str = Field(default="Issue", description=_WORK_ITEM_TYPE)
    area_path: str | None = Field(default=None, description=_AREA_PATH)
    fields: list[FieldDefinition] = Field(default_factory=list, description=_FIELDS)
    is_active: bool = Field(default=True, description=_IS_ACTIVE)


class PortalCreate(PortalBase):
    pass


class PortalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160, description=_NAME)
    description: str | None = Field(default=None, description=_DESCRIPTION)
    icon: str | None = Field(default=None, description=_ICON)
    category_id: uuid.UUID | None = Field(default=None, description=_CATEGORY_ID)
    ado_project: str | None = Field(default=None, description=_ADO_PROJECT)
    work_item_type: str | None = Field(default=None, description=_WORK_ITEM_TYPE)
    area_path: str | None = Field(default=None, description=_AREA_PATH)
    fields: list[FieldDefinition] | None = Field(default=None, description=_FIELDS)
    is_active: bool | None = Field(default=None, description=_IS_ACTIVE)


class PortalRead(PortalBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    category_name: str | None = None
    # Resolved icon after trickle-down (portal icon, else category, else default).
    effective_icon: str = "ticket"
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
