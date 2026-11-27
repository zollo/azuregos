"""Schemas for the admin-configured Azure DevOps connection."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class AdoConnectionWrite(BaseModel):
    """Save (or test) a connection. A blank ``pat`` keeps the saved one."""

    org_url: str = Field(min_length=1, max_length=500)
    pat: str | None = Field(default=None, max_length=500)
    default_project: str = Field(default="", max_length=200)

    @field_validator("org_url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Must be an http(s) URL, e.g. https://dev.azure.com/your-org")
        return v

    @field_validator("pat", "default_project")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class AdoConnectionValues(BaseModel):
    """A connection's non-secret values. The PAT itself is never returned."""

    org_url: str
    default_project: str
    pat_set: bool


class AdoStoredConnection(AdoConnectionValues):
    updated_at: datetime
    updated_by: str | None = None


class AdoConnectionStatus(BaseModel):
    # Which source is in effect: "database" (saved in the UI) wins over
    # "environment" (ADO_* env vars); "none" when neither is configured.
    source: str
    configured: bool
    stored: AdoStoredConnection | None
    environment: AdoConnectionValues
    error: str | None = None


class AdoConnectionTestResult(BaseModel):
    ok: bool
    project_count: int = 0
    error: str | None = None
