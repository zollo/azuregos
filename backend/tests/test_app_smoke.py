"""Smoke test: the FastAPI app builds and its schema generates.

This exercises route registration and response-model validation for every
endpoint, catching mistakes like a body-bearing response on a 204 route
before they break `uvicorn` at startup.
"""
from __future__ import annotations


def test_app_and_openapi_build():
    from app.main import app

    assert app.title == "Azuregos"
    schema = app.openapi()
    assert schema["info"]["title"] == "Azuregos"

    paths = schema["paths"]
    # A representative sampling of routes across the routers.
    assert "/api/health" in paths
    assert "/api/portals" in paths
    assert "/api/ado/projects" in paths
    assert "/api/tickets" in paths
