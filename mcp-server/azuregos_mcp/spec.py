"""Turn an Azuregos OpenAPI spec into MCP tool definitions.

One operation becomes one tool:

* the tool name is the ``operationId`` (the backend's route function name);
* path and query parameters become top-level arguments with their own schemas;
* a JSON request body becomes the ``body`` argument, with every component
  schema it references inlined (only recursive ones stay ``$ref``s, in
  ``$defs``);
* operations marked ``x-azuregos-mcp: {exclude: <reason>}`` are skipped.

Nothing here is Azuregos-specific beyond that extension key, and nothing is
hand-maintained per endpoint: a new route is a new tool.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

MCP_EXTENSION = "x-azuregos-mcp"
HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
BODY_ARG = "body"
# Tool names allowed by the MCP spec.
TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")

_COMPONENT_PREFIX = "#/components/schemas/"
_DEFS_PREFIX = "#/$defs/"


class UnsupportedOperation(ValueError):
    """An operation that can't be mapped to a tool (yet)."""


@dataclass(frozen=True)
class Param:
    name: str
    location: str  # "path" | "query"


@dataclass(frozen=True)
class Operation:
    name: str
    method: str
    path: str
    summary: str
    description: str
    input_schema: dict[str, Any]
    params: tuple[Param, ...] = ()
    has_body: bool = False
    requires_auth: bool = False
    tags: tuple[str, ...] = field(default=())

    @property
    def read_only(self) -> bool:
        return self.method in ("GET", "HEAD", "OPTIONS")

    @property
    def destructive(self) -> bool:
        return self.method == "DELETE"

    @property
    def idempotent(self) -> bool:
        return self.method in ("GET", "HEAD", "OPTIONS", "PUT", "DELETE")

    def tool_description(self) -> str:
        parts = [self.summary]
        if self.description and self.description.strip() != self.summary:
            parts.append(self.description.strip())
        endpoint = f"Endpoint: {self.method} {self.path}."
        if self.requires_auth:
            endpoint += " Runs as the signed-in Azuregos user; their role decides what's allowed."
        parts.append(endpoint)
        return "\n\n".join(parts)


@dataclass(frozen=True)
class ToolSet:
    operations: dict[str, Operation]
    excluded: dict[str, str]  # operationId -> reason
    skipped: dict[str, str]  # operationId -> why it couldn't be mapped (non-strict only)


def _rewrite_refs(node: Any) -> Any:
    """Point ``#/components/schemas/X`` refs at ``#/$defs/X``."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith(_COMPONENT_PREFIX):
                out[key] = _DEFS_PREFIX + value[len(_COMPONENT_PREFIX) :]
            else:
                out[key] = _rewrite_refs(value)
        return out
    if isinstance(node, list):
        return [_rewrite_refs(v) for v in node]
    return node


def _inline(node: Any, components: dict[str, Any], stack: tuple[str, ...], keep: set[str]) -> Any:
    """Inline ``$ref``s so clients that don't follow refs still see the full shape.

    A recursive reference is left as a ``$ref`` and its name added to ``keep``
    so the caller can ship it in ``$defs``.
    """
    if isinstance(node, list):
        return [_inline(v, components, stack, keep) for v in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith(_DEFS_PREFIX):
        name = ref[len(_DEFS_PREFIX) :]
        if name not in components:
            raise UnsupportedOperation(f"reference to unknown schema {name!r}")
        if name in stack:
            keep.add(name)
            return node
        resolved = _inline(copy.deepcopy(components[name]), components, (*stack, name), keep)
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        return {**resolved, **_inline(siblings, components, stack, keep)}
    return {k: _inline(v, components, stack, keep) for k, v in node.items()}


def _recursive_defs(keep: set[str], components: dict[str, Any]) -> dict[str, Any]:
    defs: dict[str, Any] = {}
    pending = set(keep)
    while pending:
        name = pending.pop()
        more: set[str] = set()
        defs[name] = _inline(copy.deepcopy(components[name]), components, (name,), more)
        pending |= more - defs.keys()
    return dict(sorted(defs.items()))


def _operation(
    path: str, method: str, op: dict, path_item: dict, components: dict[str, Any]
) -> Operation:
    op_id = op.get("operationId")
    if not op_id:
        raise UnsupportedOperation(f"{method.upper()} {path} has no operationId")
    if not TOOL_NAME_RE.match(op_id):
        raise UnsupportedOperation(f"operationId {op_id!r} isn't a valid MCP tool name")

    keep: set[str] = set()
    properties: dict[str, Any] = {}
    required: list[str] = []
    params: list[Param] = []
    # Path-level parameters apply to every operation; operation-level ones win.
    merged = {(p["name"], p["in"]): p for p in path_item.get("parameters", [])}
    merged.update({(p["name"], p["in"]): p for p in op.get("parameters", [])})
    for (name, location), param in merged.items():
        if location not in ("path", "query"):
            raise UnsupportedOperation(f"{op_id}: {location} parameter {name!r}")
        if name == BODY_ARG:
            raise UnsupportedOperation(f"{op_id}: parameter named {BODY_ARG!r} clashes with body")
        schema = _inline(_rewrite_refs(param.get("schema", {})), components, (), keep)
        if param.get("description"):
            schema["description"] = param["description"]
        properties[name] = schema
        params.append(Param(name, location))
        if param.get("required") or location == "path":
            required.append(name)

    has_body = False
    body = op.get("requestBody")
    if body:
        content = body.get("content", {})
        if "application/json" not in content:
            raise UnsupportedOperation(
                f"{op_id}: request body type {sorted(content)} (only application/json)"
            )
        schema = _inline(
            _rewrite_refs(content["application/json"].get("schema", {})), components, (), keep
        )
        schema.setdefault("description", body.get("description") or "JSON request body.")
        properties[BODY_ARG] = schema
        has_body = True
        if body.get("required"):
            required.append(BODY_ARG)

    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        input_schema["required"] = required
    if keep:
        input_schema["$defs"] = _recursive_defs(keep, components)

    summary = op.get("summary") or op_id.replace("_", " ").capitalize()
    return Operation(
        name=op_id,
        method=method.upper(),
        path=path,
        summary=summary,
        description=op.get("description", ""),
        input_schema=input_schema,
        params=tuple(params),
        has_body=has_body,
        requires_auth=bool(op.get("security")),
        tags=tuple(op.get("tags", ())),
    )


def build_toolset(spec: dict, *, strict: bool = False) -> ToolSet:
    """Map every operation in ``spec`` to a tool.

    ``strict`` raises on an operation that can't be mapped (CI uses it so a
    new endpoint never silently goes missing); otherwise it's skipped and
    reported in ``ToolSet.skipped``.
    """
    components = _rewrite_refs(spec.get("components", {}).get("schemas", {}))
    operations: dict[str, Operation] = {}
    excluded: dict[str, str] = {}
    skipped: dict[str, str] = {}
    for path, path_item in spec.get("paths", {}).items():
        for method in HTTP_METHODS:
            op = path_item.get(method)
            if op is None:
                continue
            name = op.get("operationId") or f"{method.upper()} {path}"
            ext = op.get(MCP_EXTENSION) or {}
            if ext.get("exclude"):
                excluded[name] = ext["exclude"]
                continue
            try:
                operation = _operation(path, method, op, path_item, components)
            except UnsupportedOperation as exc:
                if strict:
                    raise
                skipped[name] = str(exc)
                continue
            if operation.name in operations:
                raise UnsupportedOperation(f"duplicate operationId {operation.name!r}")
            operations[operation.name] = operation
    return ToolSet(operations=operations, excluded=excluded, skipped=skipped)
