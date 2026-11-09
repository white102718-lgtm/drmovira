"""原schema专项校验器的反例；真实HTTP业务验证仍由隔离队列负责。"""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def validate(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("channel_field_contract_checks").assert_original_schema


def test_closed_object_rejects_unknown_or_missing_fields(validate):
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    validate({"name": "原字段"}, schema, {})
    for value in ({}, {"name": "原字段", "invented": "额外字段"}, {"name": 3}):
        with pytest.raises(AssertionError):
            validate(value, schema, {})


def test_unicode_length_is_codepoints_not_utf16_bytes(validate):
    schema = {"type": "string", "minLength": 0, "maxLength": 100}
    validate("😀" * 100, schema, {})
    with pytest.raises(AssertionError):
        validate("😀" * 101, schema, {})


@pytest.mark.parametrize("value", [True, 0, 9007199254740992, 1.5])
def test_revision_requires_bounded_integer_without_boolean_coercion(validate, value):
    with pytest.raises(AssertionError):
        validate(value, {"type": "integer", "minimum": 1, "maximum": 9007199254740991}, {})


def test_cursor_anyof_null_or_nonempty_bounded_string(validate):
    schema = {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 3}, {"type": "null"}]}
    for value in (None, "abc"):
        validate(value, schema, {})
    for value in ("", "abcd", False):
        with pytest.raises(AssertionError):
            validate(value, schema, {})


def test_reference_resolution_checks_nested_owner_constraints(validate):
    schemas = {
        "Owners": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "minItems": 1,
            "maxItems": 2,
        }
    }
    schema = {"$ref": "#/components/schemas/Owners"}
    validate(["10000000-0000-4000-8000-000000000001"], schema, schemas)
    with pytest.raises(AssertionError):
        validate([], schema, schemas)
    with pytest.raises(ValueError):
        validate(["invalid"], schema, schemas)


def test_new_unknown_contract_keyword_fails_instead_of_weakening_validation(validate):
    with pytest.raises(AssertionError, match="未支持约束"):
        validate("value", {"type": "string", "newConstraint": True}, {})


def test_datetime_must_have_real_timezone(validate):
    validate("2026-11-08T00:00:00.123Z", {"type": "string", "format": "date-time"}, {})
    with pytest.raises(AssertionError):
        validate("2026-11-08T00:00:00", {"type": "string", "format": "date-time"}, {})
