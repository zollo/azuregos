"""The generated collection matches the OpenAPI spec snapshot."""
from __future__ import annotations

import ast
import json

import generate
import pytest
from ansible_collections.zollo.azuregos.plugins.module_utils import azuregos

SPEC = json.loads(generate.SPEC_PATH.read_text())


def module_globals(name: str) -> dict:
    tree = ast.parse((generate.MODULES_DIR / f"{name}.py").read_text())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in (
            "OPTIONS", "RESOURCE"
        ):
            out[node.targets[0].id] = ast.literal_eval(node.value)
    return out


def test_generated_files_are_up_to_date():
    assert generate.main(["--check"]) == 0


def test_every_api_operation_is_covered_or_ignored():
    config = generate.yaml.safe_load(generate.CONFIG_PATH.read_text())
    spec = generate.Spec(SPEC)
    mods = [generate.build_module(n, c, spec) for n, c in config["modules"].items()]
    assert generate.check_coverage(spec, config, mods) == []


def test_new_operation_without_a_decision_fails():
    doc = json.loads(json.dumps(SPEC))
    doc["paths"]["/api/widgets"] = {"post": {"responses": {}}}
    with pytest.raises(generate.GeneratorError, match="POST /api/widgets"):
        generate.generate(doc)


def test_connection_options_match_runtime():
    assert set(azuregos.CONNECTION_ARGS) == generate.CONNECTION_OPTIONS


def _modules(kind):
    config = generate.yaml.safe_load(generate.CONFIG_PATH.read_text())
    return [(n, c) for n, c in sorted(config["modules"].items()) if c["kind"] == kind]


@pytest.mark.parametrize("name,cfg", _modules("collection"))
def test_collection_options_follow_the_request_schemas(name, cfg):
    spec = generate.Spec(SPEC)
    g = module_globals(name)
    options = g["OPTIONS"]
    for op in ("create", "update"):
        _, _, operation = spec.operation(cfg[op])
        schema = spec.request_schema(operation)
        assert g["RESOURCE"][op]["schema"]["properties"].keys() == schema["properties"].keys()
        for prop, sub in schema["properties"].items():
            inner, _ = generate.split_nullable(sub)
            assert prop in options, f"{name}: {prop} missing"
            assert options[prop]["type"] == generate.ANSIBLE_TYPES[inner["type"]]
            if "enum" in inner:
                assert options[prop]["choices"] == inner["enum"]
            # Top-level options never carry a default: unset means "leave it".
            assert "default" not in options[prop]


def test_list_item_suboptions_follow_the_spec():
    spec = generate.Spec(SPEC)
    field = spec.resolve({"$ref": "#/components/schemas/FieldDefinition"})
    sub = module_globals("portal")["OPTIONS"]["fields"]["options"]
    assert sub.keys() == field["properties"].keys()
    for name in field["required"]:
        assert sub[name]["required"] is True
    assert sub["type"]["choices"] == SPEC["components"]["schemas"]["FieldType"]["enum"]
    assert sub["type"]["default"] == "text"


def test_write_only_fields_are_no_log():
    assert module_globals("user")["OPTIONS"]["password"]["no_log"] is True
    assert module_globals("ado_connection")["OPTIONS"]["pat"]["no_log"] is True


def test_option_clashing_with_connection_options_is_rejected():
    doc = json.loads(json.dumps(SPEC))
    doc["components"]["schemas"]["CategoryCreate"]["properties"]["api_url"] = {"type": "string"}
    with pytest.raises(generate.GeneratorError, match="clash"):
        generate.generate(doc)
