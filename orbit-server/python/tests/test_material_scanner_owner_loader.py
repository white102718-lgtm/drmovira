"""单profile私有DTO纯测；只读显式字典，不访问真实私有env或进程。"""

import json
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from orbit_api.errors import OrbitError
from orbit_api.material_scanner_owner_definition import OWNER_DEFINITIONS_KEY
from orbit_api.material_scanner_owner_loader import OWNER_ENABLED_KEY, load_owner_configuration


@pytest.fixture
def owner_definition(tmp_path):
    from test_material_scanner_owner import definition

    return definition.__wrapped__(tmp_path)


def serialized(definition):
    value = asdict(definition)
    value.pop("profile_id")
    value["database_files"] = dict(value["database_files"])

    def encode(item):
        if isinstance(item, Path):
            return str(item)
        if isinstance(item, datetime):
            return item.isoformat()
        raise TypeError

    return json.loads(json.dumps(value, default=encode))


def values(definition):
    return {
        OWNER_ENABLED_KEY: "true",
        OWNER_DEFINITIONS_KEY: json.dumps({definition.profile_id: serialized(definition)}),
    }


def test_missing_or_explicit_disabled_never_parses_artifact_definition():
    assert load_owner_configuration(lambda: {}).enabled is False
    assert (
        load_owner_configuration(
            lambda: {OWNER_ENABLED_KEY: "false", OWNER_DEFINITIONS_KEY: "invalid"}
        ).definition
        is None
    )


def test_exact_dto_round_trip_and_unrelated_private_change_does_not_change_source(owner_definition):
    from dataclasses import replace

    source = values(owner_definition)
    loaded = load_owner_configuration(lambda: source)
    assert (
        loaded.definition
        == replace(owner_definition, database_files=tuple(sorted(owner_definition.database_files)))
        and loaded.enabled
    )
    source["ORBIT_PYTHON_UNRELATED_SECRET"] = "never-copied"
    assert load_owner_configuration(lambda: source) == loaded
    assert "never-copied" not in repr(loaded)


@pytest.mark.parametrize("flag", [True, False, "TRUE", "1", None, 1])
def test_enabled_flag_is_explicit_strict_boolean_string(flag):
    with pytest.raises(OrbitError):
        load_owner_configuration(lambda: {OWNER_ENABLED_KEY: flag})


@pytest.mark.parametrize("raw", ["{}", "[]", "null", '{"p":{},"p":{}}', "x" * (256 * 1024 + 1)])
def test_invalid_or_duplicate_or_oversize_payload_rejected(raw):
    with pytest.raises(OrbitError):
        load_owner_configuration(lambda: {OWNER_ENABLED_KEY: "true", OWNER_DEFINITIONS_KEY: raw})


@pytest.mark.parametrize(
    "field,value",
    [
        ("pid", 123),
        ("revision", True),
        ("executable", "relative.exe"),
        ("owned_root", "//remote/share"),
        ("expires_at", "2026-11-08T00:00:00"),
        ("expires_at", "2026-11-08T00:00:00+08:00"),
    ],
)
def test_unknown_operational_fields_paths_and_dates_fail_safe(owner_definition, field, value):
    source = serialized(owner_definition)
    source[field] = value
    with pytest.raises(OrbitError) as error:
        load_owner_configuration(
            lambda: {
                OWNER_ENABLED_KEY: "true",
                OWNER_DEFINITIONS_KEY: json.dumps({owner_definition.profile_id: source}),
            }
        )
    assert error.value.code == "SCANNER_OWNER_CONFIGURATION_INVALID"
    assert "relative.exe" not in error.value.message


def test_only_one_profile_and_current_definition_window(owner_definition):
    source = serialized(owner_definition)
    with pytest.raises(OrbitError):
        load_owner_configuration(
            lambda: {
                OWNER_ENABLED_KEY: "true",
                OWNER_DEFINITIONS_KEY: json.dumps({"a": source, "b": source}),
            }
        )
    with pytest.raises(OrbitError):
        load_owner_configuration(
            lambda: values(owner_definition), now=owner_definition.expires_at + timedelta(seconds=1)
        )


def test_policy_unknown_or_missing_field_cannot_degrade_defaults(owner_definition):
    source = serialized(owner_definition)
    source["policy"].pop("deadline_seconds")
    with pytest.raises(OrbitError):
        load_owner_configuration(
            lambda: {
                OWNER_ENABLED_KEY: "true",
                OWNER_DEFINITIONS_KEY: json.dumps({owner_definition.profile_id: source}),
            }
        )


def test_changed_definition_revision_changes_canonical_snapshot(owner_definition):
    from dataclasses import replace

    first = load_owner_configuration(lambda: values(owner_definition))
    second = load_owner_configuration(lambda: values(replace(owner_definition, revision=2)))
    assert first.sha256 != second.sha256
