"""Build/runtime information schema."""
from __future__ import annotations

from pydantic import BaseModel


class BuildInfo(BaseModel):
    name: str = "Azuregos API"
    version: str
    git_commit: str
    build_time: str
    environment: str
    ado_configured: bool
