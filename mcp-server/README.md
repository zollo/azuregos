# Azuregos MCP server

An [MCP](https://modelcontextprotocol.io) server that gives an AI assistant the
whole Azuregos API: browse portals, raise and follow tickets, comment, and (for
staff) manage portals, categories, users and the Azure DevOps connection.

There's one tool per API operation, generated at startup from the instance's
`/openapi.json`. Nothing is hand-written per endpoint, so the tools always match
the Azuregos version you point it at, and a new API endpoint is a new tool with
no change here. [TOOLS.md](TOOLS.md) lists the tools for the current `main`.

The server acts as one Azuregos user and the API enforces that user's role, so
an end user's assistant can only do what that end user can do in the web app.

## Run it

It talks MCP over stdio. With [uv](https://docs.astral.sh/uv/), no install
step is needed. Replace `vX.Y.Z` with the release tag your instance runs (the
Azuregos version on its `/info` page), or drop `@vX.Y.Z` to track `main`:

```bash
uvx --from "git+https://github.com/zollo/azuregos@vX.Y.Z#subdirectory=mcp-server" azuregos-mcp
```

or `pip install "./mcp-server"` from a checkout and run `azuregos-mcp`.

| Variable | |
|---|---|
| `AZUREGOS_URL` | Base URL of the instance, e.g. `https://azuregos.example.com` (required) |
| `AZUREGOS_EMAIL` / `AZUREGOS_PASSWORD` | A **local** Azuregos account to sign in as. The server logs in and renews the token itself. |
| `AZUREGOS_TOKEN` | Or a bearer token (expires after `ACCESS_TOKEN_EXPIRE_MINUTES`, 60 by default) |
| `AZUREGOS_VERIFY_TLS` | `false` to skip TLS verification, or the path to a CA bundle |
| `AZUREGOS_SPEC` | Optional OpenAPI file to build the tools from instead of `/openapi.json` |

Each variable also has a flag (`--url`, `--email`, …; see `azuregos-mcp --help`).
Accounts that sign in with OIDC or SAML have no password: create a local
account for the assistant, with the role it should have.

### Claude Code

```bash
claude mcp add azuregos \
  -e AZUREGOS_URL=https://azuregos.example.com \
  -e AZUREGOS_EMAIL=assistant@example.com -e AZUREGOS_PASSWORD=... \
  -- uvx --from "git+https://github.com/zollo/azuregos@vX.Y.Z#subdirectory=mcp-server" azuregos-mcp
```

### Claude Desktop and other clients

```json
{
  "mcpServers": {
    "azuregos": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/zollo/azuregos@vX.Y.Z#subdirectory=mcp-server", "azuregos-mcp"],
      "env": {
        "AZUREGOS_URL": "https://azuregos.example.com",
        "AZUREGOS_EMAIL": "assistant@example.com",
        "AZUREGOS_PASSWORD": "..."
      }
    }
  }
}
```

## How tools map to the API

- **Name**: the operation ID, which the backend sets to the route function's
  name (`list_my_tickets`, `update_portal`).
- **Arguments**: path and query parameters by name, plus `body` for the JSON
  request body. Schemas come straight from the spec (referenced models are
  inlined), and arguments are validated against them before any request is sent.
- **Annotations**: `GET` is read-only, `DELETE` is destructive, `PUT`/`DELETE`
  are idempotent.
- **Results**: the JSON response; non-2xx answers come back as a tool error
  with the API's `detail` (e.g. `HTTP 403 Forbidden: Administrator privileges required`).
- **Not exposed**: routes the backend marks with
  `openapi_extra=mcp_exclude("<reason>")`: the login/register credential
  exchanges (the server signs in itself and never hands a token to the model)
  and the browser-only OIDC/SAML redirects.

## Development

```bash
cd mcp-server
pip install -e ".[dev]"
ruff check . && pytest -q
python -m azuregos_mcp.catalog   # regenerate TOOLS.md after the API changes
```

The tests build the tools from the committed spec, `docs/openapi.json`, and
fail if any operation is neither a tool nor excluded with a reason, if a tool
schema is invalid, or if `TOOLS.md` is stale. The backend's own tests fail if
`docs/openapi.json` doesn't match the app. Together, any API change has to show
up as a reviewed change to the tool catalog.
