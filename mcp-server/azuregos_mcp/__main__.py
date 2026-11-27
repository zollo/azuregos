"""``azuregos-mcp``: run the Azuregos MCP server over stdio.

Configuration (environment variables, or the matching flags):

  AZUREGOS_URL         Base URL of the Azuregos instance (required),
                       e.g. https://azuregos.example.com
  AZUREGOS_TOKEN       Bearer token, or
  AZUREGOS_EMAIL       Local account to sign in as, with
  AZUREGOS_PASSWORD    its password
  AZUREGOS_VERIFY_TLS  "false" to skip TLS verification, or a CA bundle path
  AZUREGOS_SPEC        Optional OpenAPI file to build tools from instead of
                       the instance's /openapi.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

import anyio
from mcp.server.stdio import stdio_server

from azuregos_mcp.client import AzuregosClient
from azuregos_mcp.server import AzuregosMCP


def _verify(value: str | None) -> bool | str:
    if value is None or value.lower() in ("", "1", "true", "yes"):
        return True
    if value.lower() in ("0", "false", "no"):
        return False
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    env = os.environ.get
    parser = argparse.ArgumentParser(
        prog="azuregos-mcp",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", default=env("AZUREGOS_URL"))
    parser.add_argument("--token", default=env("AZUREGOS_TOKEN"))
    parser.add_argument("--email", default=env("AZUREGOS_EMAIL"))
    parser.add_argument("--password", default=env("AZUREGOS_PASSWORD"))
    parser.add_argument("--verify-tls", default=env("AZUREGOS_VERIFY_TLS"))
    parser.add_argument("--spec", default=env("AZUREGOS_SPEC"))
    args = parser.parse_args(argv)
    if not args.url:
        parser.error("set AZUREGOS_URL (or --url)")
    if not args.token and not args.email:
        parser.error("set AZUREGOS_TOKEN, or AZUREGOS_EMAIL and AZUREGOS_PASSWORD")
    return args


async def _run(args: argparse.Namespace) -> None:
    spec = None
    if args.spec:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
    client = AzuregosClient(
        args.url,
        token=args.token,
        email=args.email,
        password=args.password,
        verify=_verify(args.verify_tls),
    )
    app = AzuregosMCP(client, spec)
    server = app.server()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await client.aclose()


def main(argv: list[str] | None = None) -> None:
    # stdout is the MCP channel; logs go to stderr.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    anyio.run(_run, parse_args(argv))


if __name__ == "__main__":
    main()
