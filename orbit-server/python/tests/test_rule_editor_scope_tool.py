"""规则scope真实工具护栏；纯检查不构成实际SQL/HTTP验收。"""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

m = importlib.import_module("tools.rule_editor_scope_checks")
DATABASE = "orbit_py_it_" + "a" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE + "\n"),
    ],
)
def test_guard_before_sql_http_or_fixture_import(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError, match="^RULE_SCOPE_ISOLATED_UUID_REQUIRED$"):
        m.run_rule_editor_scope_checks(client, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()
    client.get.assert_not_called()


def test_ten_names_limited_not_original_account_capacity_evidence():
    assert len(m.RULE_EDITOR_SCOPE_CASES) == len(set(m.RULE_EDITOR_SCOPE_CASES)) == 10
    assert not any("Capacity" in name for name in m.RULE_EDITOR_SCOPE_CASES)
    assert len(m.TABLES) == 4 and all(
        name.startswith("orbit_rule_editor_scope_") for name in m.TABLES
    )


def test_sql_literal_parameters_and_metadata_no_unsafe_literal_percent():
    tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
    checked = 0
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Name)
            or node.func.id != "sql"
            or len(node.args) < 2
            or not isinstance(node.args[0], ast.Constant)
            or not isinstance(node.args[0].value, str)
            or not isinstance(node.args[1], ast.Tuple)
        ):
            continue
        statement = node.args[0].value
        assert statement.count("%s") == len(node.args[1].elts)
        assert "%" not in statement.replace("%s", "")
        checked += 1
    assert checked >= 20


def test_tool_uses_original_http_no_test_control_or_clean_insert():
    source = Path(m.__file__).read_text(encoding="utf-8")
    assert "fixture_login(client" in source
    assert '"/api/v1/scope-snapshots"' in source
    assert "members(filtered, identity=headers, status=404)" in source
    assert "assert counts() == baseline" in source
    assert "before insert" not in source.lower() or "ISOLATED_RULE_SCOPE_OUTBOX_1644" in source
    assert "route.fulfill" not in source and "UPDATE sys_identity_subject" not in source
