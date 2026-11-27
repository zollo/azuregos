from __future__ import annotations

import json
from pathlib import Path

import pytest

SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


@pytest.fixture(scope="session")
def spec() -> dict:
    """The committed Azuregos spec (kept in sync with the backend by its CI test)."""
    return json.loads(SPEC_PATH.read_text())
