"""Fixtures for functional tests that hit a live Azure DevOps instance.

Credentials are read from the environment (never hard-coded):

    ADO_ORG_URL              e.g. https://dev.azure.com/your-org   (required)
    ADO_PAT                  a Personal Access Token               (required)
    ADO_DEFAULT_PROJECT      project to use (optional; else the first project)
    ADO_TEST_WORK_ITEM_TYPE  work-item type (optional; else a sensible default)

For convenience you may drop these in `backend/.env.test` (git-ignored). If
ADO_ORG_URL / ADO_PAT are not set, every test here is skipped, so this suite is
safe to include in a normal `pytest` run and in CI.
"""
from __future__ import annotations

import asyncio
import os
import pathlib

import pytest

# Load backend/.env.test into the environment (if present) BEFORE importing the
# client, so the token never has to be committed or exported by hand.
_ENV_TEST = pathlib.Path(__file__).resolve().parents[2] / ".env.test"
if _ENV_TEST.exists():
    for _line in _ENV_TEST.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from app.services.ado_client import ADOClient  # noqa: E402

# Work-item types we prefer for the create tests, most-portable first.
_PREFERRED_TYPES = ["Issue", "Task", "Bug", "User Story", "Product Backlog Item", "Epic"]


@pytest.fixture(scope="session")
def ado_client() -> ADOClient:
    org = os.environ.get("ADO_ORG_URL")
    pat = os.environ.get("ADO_PAT")
    if not org or not pat:
        pytest.skip("ADO_ORG_URL / ADO_PAT not set — skipping live ADO functional tests")
    project = os.environ.get("ADO_DEFAULT_PROJECT") or os.environ.get("ADO_TEST_PROJECT") or ""
    return ADOClient(org_url=org, pat=pat, default_project=project)


@pytest.fixture(scope="session")
def ado_project(ado_client: ADOClient) -> str:
    if ado_client.default_project:
        return ado_client.default_project
    projects = asyncio.run(ado_client.list_projects())
    if not projects:
        pytest.skip("No projects available in the ADO organization")
    return projects[0]["name"]


@pytest.fixture(scope="session")
def work_item_type(ado_client: ADOClient, ado_project: str) -> str:
    override = os.environ.get("ADO_TEST_WORK_ITEM_TYPE")
    if override:
        return override
    names = [t["name"] for t in asyncio.run(ado_client.list_work_item_types(ado_project))]
    for preferred in _PREFERRED_TYPES:
        if preferred in names:
            return preferred
    if not names:
        pytest.skip(f"No work-item types found for project {ado_project}")
    return names[0]


@pytest.fixture
def created_work_items(ado_client: ADOClient):
    """Collect IDs created during a test and permanently remove them after,
    so the dev instance stays clean."""
    ids: list[int] = []
    yield ids
    for wid in ids:
        try:
            asyncio.run(ado_client.delete_work_item(wid, destroy=True))
        except Exception:  # noqa: BLE001
            pass  # best-effort cleanup
