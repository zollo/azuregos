"""Parity: every API operation is a tool, or is excluded with a reason."""
from __future__ import annotations

import copy
from pathlib import Path

import jsonschema
import pytest

from azuregos_mcp import catalog
from azuregos_mcp.spec import (
    BODY_ARG,
    HTTP_METHODS,
    TOOL_NAME_RE,
    UnsupportedOperation,
    build_toolset,
)

from .conftest import SPEC_PATH


def _all_operation_ids(spec: dict) -> set[str]:
    return {
        op["operationId"]
        for item in spec["paths"].values()
        for method, op in item.items()
        if method in HTTP_METHODS
    }


def test_every_operation_is_a_tool_or_excluded(spec):
    toolset = build_toolset(spec, strict=True)
    covered = set(toolset.operations) | set(toolset.excluded)
    assert covered == _all_operation_ids(spec)
    assert not toolset.skipped
    assert not set(toolset.operations) & set(toolset.excluded)


def test_core_workflows_are_exposed(spec):
    tools = build_toolset(spec, strict=True).operations
    for name in ("portal_catalog", "get_portal", "create_ticket", "list_my_tickets",
                 "add_ticket_comment", "create_portal", "list_users"):
        assert name in tools


def test_credential_and_browser_flows_are_excluded(spec):
    excluded = build_toolset(spec, strict=True).excluded
    for name in ("login", "register", "oidc_login", "oidc_callback", "saml_login", "saml_acs"):
        assert excluded.get(name), name


def test_tool_schemas_are_valid_and_self_contained(spec):
    for op in build_toolset(spec, strict=True).operations.values():
        assert TOOL_NAME_RE.match(op.name)
        schema = op.input_schema
        assert schema["type"] == "object"
        jsonschema.Draft202012Validator.check_schema(schema)
        # No dangling refs into the OpenAPI document.
        assert "#/components/" not in str(schema), op.name
        # Every required path parameter is required in the tool too.
        for param in op.params:
            if param.location == "path":
                assert param.name in schema["required"], (op.name, param.name)


def test_path_and_body_arguments(spec):
    tools = build_toolset(spec, strict=True).operations
    update = tools["update_portal"]
    assert update.method == "PATCH"
    assert update.path == "/api/portals/{portal_id}"
    assert set(update.input_schema["properties"]) == {"portal_id", BODY_ARG}
    validator = jsonschema.Draft202012Validator(update.input_schema)
    assert validator.is_valid({"portal_id": "6f1c…", "body": {"name": "IT help"}})
    assert not validator.is_valid({"body": {}})  # missing portal_id
    assert not validator.is_valid({"portal_id": "x", "body": {}, "extra": 1})

    tickets = tools["list_my_tickets"]
    assert tickets.read_only and not tickets.has_body
    assert "all_tickets" in tickets.input_schema["properties"]
    assert tools["delete_portal"].destructive


def test_exclusion_marker_is_honoured(spec):
    spec = copy.deepcopy(spec)
    spec["paths"]["/api/portals"]["get"]["x-azuregos-mcp"] = {"exclude": "testing"}
    toolset = build_toolset(spec, strict=True)
    assert "list_all_portals" not in toolset.operations
    assert toolset.excluded["list_all_portals"] == "testing"


def test_unsupported_operation_fails_strict_and_is_skipped_otherwise(spec):
    spec = copy.deepcopy(spec)
    spec["paths"]["/api/upload"] = {
        "post": {
            "operationId": "upload_file",
            "requestBody": {"content": {"multipart/form-data": {"schema": {}}}},
            "responses": {"200": {"description": "ok"}},
        }
    }
    with pytest.raises(UnsupportedOperation, match="upload_file"):
        build_toolset(spec, strict=True)
    toolset = build_toolset(spec)
    assert "upload_file" in toolset.skipped
    assert "create_ticket" in toolset.operations


def test_recursive_schemas_keep_defs():
    spec = {
        "paths": {
            "/api/tree": {
                "post": {
                    "operationId": "make_tree",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Node"}}
                        },
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "children": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Node"},
                        }
                    },
                }
            }
        },
    }
    op = build_toolset(spec, strict=True).operations["make_tree"]
    assert "Node" in op.input_schema["$defs"]
    validator = jsonschema.Draft202012Validator(op.input_schema)
    assert validator.is_valid({"body": {"children": [{"children": []}]}})
    assert not validator.is_valid({"body": {"children": [{"children": 3}]}})


def test_tools_md_is_up_to_date():
    """TOOLS.md must be regenerated when the API changes (see CLAUDE.md)."""
    out = Path(__file__).resolve().parents[1] / "TOOLS.md"
    assert catalog.main(["--check", "--spec", str(SPEC_PATH), "--out", str(out)]) == 0
