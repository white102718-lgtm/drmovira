"""057专项工具的隔离/合同/诊断护栏；不代替MySQL或真实HTTP结果。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from tools.rule_definition_checks import (
    RULE_DEFINITION_CASES,
    SCOPE_MEMBERS_PATH,
    TABLES,
    checked,
    definition_body,
    guard_rule_target,
)

from orbit_api.rule_contract import parse_rule_write


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("production.invalid", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, None),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 31),
    ],
)
def test_reject_non_isolated_target_without_opening_cursor(host, port, database):
    with pytest.raises(ValueError):
        guard_rule_target(SimpleNamespace(host=host, port=port), database)


def test_actual_database_name_is_checked_before_any_fixture_mutation():
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def execute(self, statement):
            assert statement == "SELECT DATABASE()"

        def fetchone(self):
            return ("unexpected",)

    connection = SimpleNamespace(host="127.0.0.1", port=13306, cursor=Cursor)
    with pytest.raises(ValueError):
        guard_rule_target(connection, "orbit_py_it_" + "a" * 32)


def test_fixture_body_is_complete_original_contract_without_defaults():
    import json

    owner, team, snapshot, profile = (str(uuid4()) for _ in range(4))
    value = definition_body("原规则", owner, team, snapshot, profile)
    parsed = parse_rule_write(json.dumps(value).encode()).model_dump()
    assert parsed == value and len(value) == 11 and len(value["schedule"]) == 7
    assert value["ownership"] == {"owner_user_id": owner, "owner_team_id": team}
    assert value["scope_snapshot_id"] == snapshot and value["metric_profile_id"] == profile


def test_bad_http_diagnostics_never_include_body_or_private_message():
    response = SimpleNamespace(
        status_code=503,
        json=lambda: {
            "code": "SOURCE_UNAVAILABLE",
            "message": "SECRET_BODY",
            "token": "SECRET_TOKEN",
        },
    )
    with pytest.raises(AssertionError) as caught:
        checked(response, 201)
    diagnostic = str(caught.value)
    assert "503" in diagnostic and "201" in diagnostic and "SOURCE_UNAVAILABLE" in diagnostic
    assert "SECRET" not in diagnostic


def test_status_match_does_not_hide_error_code_mismatch():
    response = SimpleNamespace(status_code=403, json=lambda: {"code": "WRONG_CODE"})
    with pytest.raises(AssertionError):
        checked(response, 403, code="CSRF_INVALID")


def test_matrix_has_sixteen_distinct_groups_and_eight_transaction_tables():
    assert len(RULE_DEFINITION_CASES) == len(set(RULE_DEFINITION_CASES)) == 16
    assert len(TABLES) == len(set(TABLES)) == 8
    assert all(name.startswith("pythonRule") for name in RULE_DEFINITION_CASES)


def test_private_scope_negative_uses_original_members_get_not_nonexistent_header_get():
    import json
    from pathlib import Path

    specification = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "data/ORBIT_Codex开发PRD/contracts/openapi-current.json"
        ).read_text(encoding="utf-8")
    )
    assert specification["paths"][SCOPE_MEMBERS_PATH]["get"]["x-permission"] == "accounts.read"
    assert "get" not in specification["paths"].get("/api/v1/scope-snapshots/{id}", {})
