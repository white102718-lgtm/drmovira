"""真实规则闭环工具护栏纯测；不运行HTTP/数据库。"""

import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

core = importlib.import_module("tools.rules_definition_flow_checks")
DATABASE = "orbit_py_it_" + "e" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 13306.0, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE + "\n"),
    ],
)
def test_invalid_target_rejected_before_importing_fixture_or_sql(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError):
        core.run_rules_definition_flow_checks(client, admin, {}, "", None, database, [])
    admin.cursor.assert_not_called()
    assert not client.mock_calls


def test_actual_database_is_checked_before_fixture_mutation():
    statements = []

    class Cursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, values=()):
            statements.append((statement, values))

        def fetchall(self):
            return (("foreign",),)

    admin = SimpleNamespace(
        host="127.0.0.1", port=13306, cursor=Cursor, commit=Mock(), rollback=Mock()
    )
    client = Mock()
    cases = []
    with pytest.raises(ValueError, match="^RULE_FLOW_ACTUAL_DATABASE_REQUIRED$"):
        core.run_rules_definition_flow_checks(client, admin, {}, "", None, DATABASE, cases)
    assert statements == [("SELECT DATABASE()", ())]
    assert not client.mock_calls and cases == []


def test_fixed_case_names_and_native_identity_reservations():
    assert len(core.RULES_DEFINITION_FLOW_CASES) == 8
    assert len(set(core.RULES_DEFINITION_FLOW_CASES)) == 8
    assert all(
        name.startswith("pythonRulesDefinition") for name in core.RULES_DEFINITION_FLOW_CASES
    )
    assert core.NATIVE_ACTORS == (990680, 990681)


@pytest.mark.parametrize(
    "status,permissions",
    [
        (403, []),
        (200, ["rules.read", None]),
        (200, ["rules.read", "*:*:*"]),
        (200, ["sensitive-unregistered-value"]),
        (200, None),
    ],
)
def test_info_failure_diagnostic_is_fixed_whitelist_and_preserves_exact_assertion(
    status, permissions, capsys
):
    import json

    response = SimpleNamespace(
        status_code=status, json=lambda: {"permissions": permissions, "token": "never-print-secret"}
    )
    with pytest.raises(AssertionError, match="RULE_FLOW_READ_ONLY_INFO_MISMATCH"):
        core.assert_read_only_info(response)
    raw = capsys.readouterr().out
    diagnostic = json.loads(raw)
    assert diagnostic["status"] == status
    assert "never-print-secret" not in raw and "sensitive-unregistered-value" not in raw
    assert set(diagnostic) == {
        "scope",
        "phase",
        "status",
        "permissions_type_valid",
        "known_permissions",
        "empty_permission_count",
        "other_permission_count",
    }


def test_info_exact_read_only_success_has_no_diagnostic(capsys):
    core.assert_read_only_info(
        SimpleNamespace(status_code=200, json=lambda: {"permissions": ["rules.read"]})
    )
    assert capsys.readouterr().out == ""


def test_native_three_structural_empty_menu_permissions_are_not_actions(capsys):
    core.assert_read_only_info(
        SimpleNamespace(status_code=200, json=lambda: {"permissions": ["", "rules.read", "", ""]})
    )
    assert capsys.readouterr().out == ""
