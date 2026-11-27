"""The OpenAPI spec is a contract for generated clients (see ``app/api/openapi.py``)."""
from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path

from app.api.openapi import MCP_EXTENSION

BACKEND = Path(__file__).resolve().parents[1]


def _operations():
    from app.main import app

    for path, ops in app.openapi()["paths"].items():
        for method, op in ops.items():
            yield path, method, op


def test_operation_ids_are_unique_route_names():
    ids = [op["operationId"] for _, _, op in _operations()]
    dupes = [name for name, n in Counter(ids).items() if n > 1]
    assert not dupes, f"duplicate operation IDs (rename the route functions): {dupes}"
    assert "list_all_portals" in ids


def test_mcp_exclusions_give_a_reason():
    for path, method, op in _operations():
        ext = op.get(MCP_EXTENSION)
        if ext is not None:
            assert ext.get("exclude", "").strip(), f"{method.upper()} {path}: empty reason"


def test_committed_spec_is_up_to_date():
    """docs/openapi.json must match the app; regenerate it when the API changes."""
    result = subprocess.run(
        [sys.executable, "scripts/export_openapi.py", "--check"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
