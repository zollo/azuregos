import types

import pytest

from app.core.utils import slugify
from app.services import ticket_service
from app.services.ado_client import (
    TAG_MARKER,
    TAG_PORTAL_PREFIX,
    TAG_SUBMITTER_PREFIX,
)


def _portal(fields):
    """A lightweight stand-in for the Portal ORM object."""
    return types.SimpleNamespace(name="IT Help", slug="it-help", fields=fields)


def _ticket(field_values, description="Please help"):
    return types.SimpleNamespace(
        description=description,
        field_values=field_values,
        submitter_email="user@example.com",
    )


def test_slugify():
    assert slugify("Hello World!") == "hello-world"
    assert slugify("  Múltiple   Spaces ") == "multiple-spaces"
    assert slugify("") == "item"


def test_validate_required_field_missing():
    portal = _portal([{"name": "priority", "label": "Priority", "type": "text", "required": True}])
    with pytest.raises(ticket_service.TicketValidationError):
        ticket_service._validate_field_values(portal, {})


def test_validate_select_option():
    portal = _portal(
        [{"name": "sev", "label": "Severity", "type": "select",
          "required": True, "options": ["low", "high"]}]
    )
    assert ticket_service._validate_field_values(portal, {"sev": "high"}) == {"sev": "high"}
    with pytest.raises(ticket_service.TicketValidationError):
        ticket_service._validate_field_values(portal, {"sev": "nope"})


def test_validate_drops_unknown_fields():
    portal = _portal([{"name": "known", "label": "Known", "type": "text"}])
    cleaned = ticket_service._validate_field_values(portal, {"known": "x", "sneaky": "y"})
    assert cleaned == {"known": "x"}


def test_build_tags():
    portal = _portal([])
    tags = ticket_service.build_tags(portal, _ticket({}))
    assert TAG_MARKER in tags
    assert f"{TAG_PORTAL_PREFIX}it-help" in tags
    assert f"{TAG_SUBMITTER_PREFIX}user@example.com" in tags


def test_build_description_appends_unmapped_fields():
    portal = _portal([{"name": "dept", "label": "Department", "type": "text"}])
    body = ticket_service.build_description(portal, _ticket({"dept": "Finance"}))
    assert "Department" in body and "Finance" in body


def test_build_ado_fields_only_mapped():
    portal = _portal(
        [
            {"name": "prio", "label": "Priority", "type": "text",
             "ado_field_ref": "Microsoft.VSTS.Common.Priority"},
            {"name": "dept", "label": "Department", "type": "text"},
        ]
    )
    mapped = ticket_service.build_ado_fields(
        portal, _ticket({"prio": 2, "dept": "Finance"})
    )
    assert mapped == {"Microsoft.VSTS.Common.Priority": 2}
