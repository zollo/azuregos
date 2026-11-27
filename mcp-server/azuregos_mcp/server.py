"""The MCP server: one tool per Azuregos API operation."""
from __future__ import annotations

import json
import logging
from typing import Any

import anyio
import jsonschema
from mcp import types
from mcp.server.lowlevel import Server

from azuregos_mcp import __version__
from azuregos_mcp.client import AzuregosClient, AzuregosError
from azuregos_mcp.spec import Operation, ToolSet, build_toolset

logger = logging.getLogger("azuregos_mcp")

INSTRUCTIONS = """\
Azuregos is a service desk in front of Azure DevOps: users submit tickets through \
admin-defined portals and each ticket becomes an ADO work item. These tools are the \
Azuregos REST API, one per endpoint, acting as the configured Azuregos user; what that \
user's role allows is enforced by the API.

To raise a ticket: portal_catalog to find a portal, get_portal for its form fields, then \
create_ticket. "My tickets" is list_my_tickets; staff can pass all_tickets=true for the queue.\
"""


def tool_for(op: Operation) -> types.Tool:
    return types.Tool(
        name=op.name,
        title=op.summary,
        description=op.tool_description(),
        input_schema=op.input_schema,
        annotations=types.ToolAnnotations(
            title=op.summary,
            read_only_hint=op.read_only,
            destructive_hint=op.destructive,
            idempotent_hint=op.idempotent,
            open_world_hint=False,
        ),
    )


def _text(text: str, *, error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=error)


class AzuregosMCP:
    """Holds the API client and the tool set, loaded from the spec on first use."""

    def __init__(self, client: AzuregosClient, spec: dict | None = None):
        self.client = client
        self._spec = spec
        self._toolset: ToolSet | None = None
        self._lock = anyio.Lock()

    async def toolset(self) -> ToolSet:
        async with self._lock:
            if self._toolset is None:
                spec = self._spec if self._spec is not None else await self.client.fetch_spec()
                self._toolset = build_toolset(spec)
                for name, why in self._toolset.skipped.items():
                    logger.warning("Not exposing %s: %s", name, why)
            return self._toolset

    async def list_tools(self, ctx: Any, params: Any) -> types.ListToolsResult:
        toolset = await self.toolset()
        return types.ListToolsResult(tools=[tool_for(op) for op in toolset.operations.values()])

    async def call_tool(
        self, ctx: Any, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        toolset = await self.toolset()
        op = toolset.operations.get(params.name)
        if op is None:
            return _text(f"Unknown tool {params.name!r}", error=True)
        arguments = params.arguments or {}
        try:
            jsonschema.validate(arguments, op.input_schema)
        except jsonschema.ValidationError as exc:
            return _text(f"Invalid arguments: {exc.message}", error=True)
        try:
            result = await self.client.call(op, arguments)
        except AzuregosError as exc:
            return _text(str(exc), error=True)
        if result is None:
            return _text("Done (no content).")
        if isinstance(result, str):
            return _text(result)
        text = json.dumps(result, indent=2, ensure_ascii=False)
        structured = result if isinstance(result, dict) else {"items": result}
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            structured_content=structured,
        )

    def server(self) -> Server:
        return Server(
            "azuregos",
            version=__version__,
            title="Azuregos",
            instructions=INSTRUCTIONS,
            on_list_tools=self.list_tools,
            on_call_tool=self.call_tool,
        )
