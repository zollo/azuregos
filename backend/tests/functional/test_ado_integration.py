"""Functional tests against a live Azure DevOps instance.

These exercise the real REST API through ``ADOClient`` and the Azuregos
tag/description conventions used by ``ticket_service``. They require
ADO_ORG_URL + ADO_PAT in the environment (see conftest) and are skipped
otherwise. Every work item created here is deleted in teardown.
"""
from __future__ import annotations

import asyncio
import types
import uuid

import pytest

from app.services import ticket_service
from app.services.ado_client import (
    TAG_MARKER,
    TAG_PORTAL_PREFIX,
    TAG_SUBMITTER_PREFIX,
    ADOClient,
    ADOError,
)

pytestmark = pytest.mark.functional


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


async def _query_with_retry(
    client: ADOClient, project: str, tag: str, attempts: int = 6, delay: float = 2.0
) -> list[int]:
    """WIQL tag search is eventually consistent; retry briefly."""
    ids: list[int] = []
    for _ in range(attempts):
        ids = await client.query_by_tag(project, tag)
        if ids:
            return ids
        await asyncio.sleep(delay)
    return ids


async def test_authentication_lists_projects(ado_client: ADOClient):
    """The PAT authenticates and we can read the org's projects."""
    projects = await ado_client.list_projects()
    assert isinstance(projects, list)
    assert projects, "expected at least one project in the organization"
    assert all("name" in p for p in projects)


async def test_list_work_item_types(ado_client: ADOClient, ado_project: str):
    types = await ado_client.list_work_item_types(ado_project)
    names = [t["name"] for t in types]
    assert names, f"expected work-item types for project {ado_project}"


async def test_create_fetch_and_query_work_item(
    ado_client: ADOClient,
    ado_project: str,
    work_item_type: str,
    created_work_items: list[int],
):
    """Full round trip: create with Azuregos tags, read it back, find it by
    the submitter tag via WIQL."""
    submitter = f"{_unique('func')}@example.com"
    title = _unique("Azuregos functional test")
    tags = [
        TAG_MARKER,
        f"{TAG_PORTAL_PREFIX}func-test",
        f"{TAG_SUBMITTER_PREFIX}{submitter}",
    ]

    work_item = await ado_client.create_work_item(
        project=ado_project,
        work_item_type=work_item_type,
        title=title,
        description="<div>Created by the Azuregos functional test suite.</div>",
        tags=tags,
    )
    wid = work_item["id"]
    created_work_items.append(wid)

    # Creation response
    assert isinstance(wid, int)
    assert ADOClient.web_url(work_item), "expected an html link on the work item"
    fields = work_item["fields"]
    assert fields["System.Title"] == title
    stored_tags = fields.get("System.Tags", "")
    assert TAG_MARKER in stored_tags
    assert f"{TAG_SUBMITTER_PREFIX}{submitter}" in stored_tags

    # Fetch it back independently
    fetched = await ado_client.get_work_item(wid)
    assert fetched["id"] == wid
    assert fetched["fields"]["System.Title"] == title

    # Find it by the submitter tag (this is how "my tickets" is recoverable)
    found = await _query_with_retry(
        ado_client, ado_project, f"{TAG_SUBMITTER_PREFIX}{submitter}"
    )
    assert wid in found, "created work item was not returned by the tag query"


async def test_ticket_service_render_roundtrip(
    ado_client: ADOClient,
    ado_project: str,
    work_item_type: str,
    created_work_items: list[int],
):
    """The ticket_service tag/description builders produce a work item that
    lands correctly in ADO, including an unmapped custom field appended to the
    description."""
    submitter = f"{_unique('svc')}@example.com"
    portal = types.SimpleNamespace(
        name="IT Help",
        slug="it-help",
        fields=[{"name": "department", "label": "Department", "type": "text"}],
    )
    ticket = types.SimpleNamespace(
        description="My laptop won't boot.",
        field_values={"department": "Finance"},
        submitter_email=submitter,
    )

    work_item = await ado_client.create_work_item(
        project=ado_project,
        work_item_type=work_item_type,
        title=_unique("Azuregos svc render"),
        description=ticket_service.build_description(portal, ticket),
        tags=ticket_service.build_tags(portal, ticket),
        extra_fields=ticket_service.build_ado_fields(portal, ticket),
    )
    wid = work_item["id"]
    created_work_items.append(wid)

    fetched = await ado_client.get_work_item(wid)
    description = fetched["fields"].get("System.Description", "")
    # The unmapped "department" field is rendered into the description body.
    assert "Department" in description and "Finance" in description
    assert f"{TAG_PORTAL_PREFIX}it-help" in fetched["fields"].get("System.Tags", "")


async def test_create_with_mapped_ado_field(
    ado_client: ADOClient,
    ado_project: str,
    work_item_type: str,
    created_work_items: list[int],
):
    """A field mapped to a real ADO reference name is set on the work item.

    Uses Priority, which not every process/type exposes; if ADO rejects it the
    test is skipped rather than failed.
    """
    try:
        work_item = await ado_client.create_work_item(
            project=ado_project,
            work_item_type=work_item_type,
            title=_unique("Azuregos mapped field"),
            description="mapped field test",
            tags=[TAG_MARKER],
            extra_fields={"Microsoft.VSTS.Common.Priority": 2},
        )
    except ADOError as exc:
        pytest.skip(f"Priority not settable for {work_item_type}: {exc}")

    wid = work_item["id"]
    created_work_items.append(wid)
    fetched = await ado_client.get_work_item(wid)
    assert fetched["fields"].get("Microsoft.VSTS.Common.Priority") == 2


async def test_comment_add_and_list_roundtrip(
    ado_client: ADOClient,
    ado_project: str,
    work_item_type: str,
    created_work_items: list[int],
):
    """Post discussion comments to a work item and read them back in order."""
    work_item = await ado_client.create_work_item(
        project=ado_project,
        work_item_type=work_item_type,
        title=_unique("Azuregos discussion"),
        description="",
        tags=[TAG_MARKER],
    )
    wid = work_item["id"]
    created_work_items.append(wid)

    first = await ado_client.add_comment(ado_project, wid, "First reply")
    assert first.get("id")
    await ado_client.add_comment(ado_project, wid, "Second <b>reply</b>")

    comments = await ado_client.list_comments(ado_project, wid)
    texts = [c.get("text", "") for c in comments]
    assert len(comments) >= 2
    # Returned oldest-first
    assert "First reply" in texts[0]
    assert any("Second" in t for t in texts)


async def test_invalid_project_raises_non_retryable(ado_client: ADOClient):
    """A bad project surfaces as a non-retryable ADOError (so the retry loop
    won't hammer it forever)."""
    with pytest.raises(ADOError) as excinfo:
        await ado_client.create_work_item(
            project="___no_such_project___",
            work_item_type="Issue",
            title="should not be created",
            description="",
            tags=[TAG_MARKER],
        )
    assert excinfo.value.retryable is False
