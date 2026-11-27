"""End to end over MCP: an in-process client calls tools, a fake API answers."""
from __future__ import annotations

import json

import httpx
from mcp import Client

from azuregos_mcp.client import AzuregosClient
from azuregos_mcp.server import AzuregosMCP


class FakeAPI:
    """Records requests and answers a few Azuregos endpoints."""

    def __init__(self, spec: dict, *, expire_first_token: bool = False):
        self.spec = spec
        self.requests: list[httpx.Request] = []
        self.logins = 0
        self.expire_first_token = expire_first_token

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if path == "/openapi.json":
            return httpx.Response(200, json=self.spec)
        if path == "/api/auth/login":
            self.logins += 1
            return httpx.Response(200, json={"access_token": f"tok{self.logins}", "user": {}})
        auth = request.headers.get("authorization")
        if auth is None or (self.expire_first_token and auth == "Bearer tok1"):
            return httpx.Response(401, json={"detail": "Could not validate credentials"})
        if (method, path) == ("GET", "/api/tickets"):
            flag = request.url.params.get("all_tickets")
            return httpx.Response(200, json=[{"id": "t1", "all": flag}])
        if (method, request.url.raw_path) == ("PATCH", b"/api/portals/p%201"):
            return httpx.Response(200, json={"id": "p 1", **json.loads(request.content)})
        if (method, path) == ("DELETE", "/api/users/u1"):
            return httpx.Response(204)
        if (method, path) == ("GET", "/api/users"):
            return httpx.Response(403, json={"detail": "Administrator privileges required"})
        return httpx.Response(404, json={"detail": "Not Found"})


def _server(api: FakeAPI, **auth):
    auth = auth or {"token": "static"}
    client = AzuregosClient(
        "https://azuregos.test/", transport=httpx.MockTransport(api), **auth
    )
    return AzuregosMCP(client).server()


async def test_lists_one_tool_per_operation_from_the_live_spec(spec):
    api = FakeAPI(spec)
    async with Client(_server(api)) as mcp:
        tools = {t.name: t for t in (await mcp.list_tools()).tools}
    assert api.requests[0].url.path == "/openapi.json"
    assert "create_ticket" in tools and "login" not in tools
    assert tools["delete_portal"].annotations.destructive_hint is True
    assert tools["list_my_tickets"].annotations.read_only_hint is True
    assert "GET /api/tickets" in tools["list_my_tickets"].description


async def test_query_parameters_and_bearer_token(spec):
    api = FakeAPI(spec)
    async with Client(_server(api)) as mcp:
        result = await mcp.call_tool("list_my_tickets", {"all_tickets": True})
    assert not result.is_error
    assert json.loads(result.content[0].text) == [{"id": "t1", "all": "true"}]
    assert result.structured_content == {"items": [{"id": "t1", "all": "true"}]}
    call = api.requests[-1]
    assert call.headers["authorization"] == "Bearer static"


async def test_path_parameters_are_escaped_and_body_is_sent(spec):
    api = FakeAPI(spec)
    async with Client(_server(api)) as mcp:
        result = await mcp.call_tool(
            "update_portal", {"portal_id": "p 1", "body": {"name": "IT help"}}
        )
    assert not result.is_error, result.content[0].text
    assert result.structured_content == {"id": "p 1", "name": "IT help"}
    assert api.requests[-1].url.raw_path == b"/api/portals/p%201"


async def test_no_content_and_api_errors(spec):
    api = FakeAPI(spec)
    async with Client(_server(api)) as mcp:
        deleted = await mcp.call_tool("delete_user", {"user_id": "u1"})
        forbidden = await mcp.call_tool("list_users", {})
    assert not deleted.is_error and "no content" in deleted.content[0].text
    assert forbidden.is_error
    assert forbidden.content[0].text == "HTTP 403 Forbidden: Administrator privileges required"


async def test_invalid_arguments_never_reach_the_api(spec):
    api = FakeAPI(spec)
    async with Client(_server(api)) as mcp:
        await mcp.list_tools()
        before = len(api.requests)
        missing = await mcp.call_tool("update_portal", {"body": {}})
        unknown = await mcp.call_tool("no_such_tool", {})
    assert missing.is_error and "portal_id" in missing.content[0].text
    assert unknown.is_error
    assert len(api.requests) == before


async def test_password_login_and_relogin_on_expiry(spec):
    api = FakeAPI(spec, expire_first_token=True)
    async with Client(_server(api, email="bot@example.com", password="pw")) as mcp:
        result = await mcp.call_tool("list_my_tickets", {})
    assert not result.is_error
    assert api.logins == 2
    login = next(r for r in api.requests if r.url.path == "/api/auth/login")
    assert json.loads(login.content) == {"email": "bot@example.com", "password": "pw"}
    assert api.requests[-1].headers["authorization"] == "Bearer tok2"
