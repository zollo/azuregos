from __future__ import annotations

from ansible_collections.zollo.azuregos.plugins.module_utils.azuregos import (
    schema_errors,
    strip_none,
    values_equal,
)

NAME = {"type": "string", "minLength": 1, "maxLength": 5, "pattern": "^[a-z]+$"}


def test_string_constraints():
    assert schema_errors(NAME, "abc", "name") == []
    assert "at most 5" in schema_errors(NAME, "abcdef", "name")[0]
    assert "must match" in schema_errors(NAME, "ab1", "name")[0]
    assert "at least 1" in schema_errors(NAME, "", "name")[0]


def test_nullable_and_formats():
    nullable_uuid = {"anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}]}
    assert schema_errors(nullable_uuid, None, "id") == []
    assert schema_errors(nullable_uuid, "6f9619ff-8b86-d011-b42d-00cf4fc964ff", "id") == []
    assert schema_errors(nullable_uuid, "nope", "id") == ["id must be a UUID"]
    assert schema_errors({"type": "string"}, None, "x") == ["x may not be null"]
    assert schema_errors({"type": "string", "format": "email"}, "a@b", "e")


def test_nested_objects():
    item = {"type": "object", "required": ["name"], "properties": {"name": NAME}}
    schema = {"type": "array", "items": item}
    assert schema_errors(schema, [{"name": "ok"}], "fields") == []
    errs = schema_errors(schema, [{"name": "ok"}, {"name": "BAD"}, {}], "fields")
    assert errs == ["fields[1].name must match ^[a-z]+$", "fields[2].name is required"]


def test_values_equal():
    upper = "6F9619FF-8B86-D011-B42D-00CF4FC964FF"
    assert values_equal(upper, upper.lower())
    assert values_equal(["b", "a"], ["a", "b"], unordered=True)
    assert not values_equal(["b", "a"], ["a", "b"])
    # An unset suboption matches the empty value the API filled in.
    filled = [{"name": "x", "options": [], "extra": 1}]
    assert values_equal([{"name": "x", "options": None}], filled)
    assert not values_equal([{"name": "x", "options": None}], [{"name": "x", "options": ["a"]}])
    assert not values_equal({"a": 1}, None)


def test_strip_none():
    assert strip_none([{"a": None, "b": {"c": None, "d": 1}}]) == [{"b": {"d": 1}}]
