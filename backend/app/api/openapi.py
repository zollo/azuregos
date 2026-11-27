"""OpenAPI conventions shared by every route.

The OpenAPI spec is the contract that generated clients are built from: the
MCP server in ``mcp-server/`` turns every operation into a tool, so
operation IDs must be stable, readable and unique.
"""
from __future__ import annotations

from fastapi.routing import APIRoute

# Extension key read by the MCP server (``mcp-server/azuregos_mcp/spec.py``).
MCP_EXTENSION = "x-azuregos-mcp"


def operation_id(route: APIRoute) -> str:
    """Use the route function's name (``list_portals``) as its operation ID.

    FastAPI's default (``list_portals_api_portals_get``) leaks the path and
    method into every generated tool/module name. Route function names are
    unique across routers; ``tests/test_openapi.py`` enforces it.
    """
    return route.name


def mcp_exclude(reason: str) -> dict:
    """``openapi_extra`` for a route the MCP server must not expose as a tool.

    Every route is a tool by default. Use this only for routes an MCP client
    can't meaningfully call (browser redirects, credential exchanges the MCP
    server does itself), and say why.
    """
    return {MCP_EXTENSION: {"exclude": reason}}
