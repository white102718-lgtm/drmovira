"""真实定义工具护栏纯测；不启动DB/HTTP，不把技术ENABLED称启用验收。"""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

core = importlib.import_module("tools.rule_editor_definition_checks")
DATABASE = "orbit_py_it_" + "e" * 32


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
def test_invalid_guard_before_sql_or_http(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError):
        core.run_rule_editor_definition_checks(client, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()
    client.get.assert_not_called()


def test_exact_seven_independent_cases_not_original_rule_simulation_acceptance():
    assert (
        len(core.RULE_EDITOR_DEFINITION_CASES) == len(set(core.RULE_EDITOR_DEFINITION_CASES)) == 7
    )
    assert all(
        name.startswith("pythonRuleEditDefinition") for name in core.RULE_EDITOR_DEFINITION_CASES
    )


def test_actual_nested_rule_page_component_not_fabricated_parent_or_read_permission():
    assert core.has_rule_page(
        [
            {
                "component": "Layout",
                "children": [
                    {"component": "ParentView", "children": [{"component": "orbit/rules/index"}]}
                ],
            }
        ]
    )
    assert not core.has_rule_page(
        [{"component": "ParentView", "path": "/orbit/rules", "children": []}]
    )
    with pytest.raises(AssertionError):
        core.has_rule_page({"component": "orbit/rules/index"})


def test_all_literal_bound_sql_tuple_arity_and_no_guard_shutdown_statements():
    tree = ast.parse(Path(core.__file__).read_text(encoding="utf-8"))
    checked = 0
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or not call.args:
            continue
        statement = call.args[0]
        if not isinstance(statement, ast.Constant) or not isinstance(statement.value, str):
            continue
        is_sql = isinstance(call.func, ast.Name) and call.func.id == "sql"
        is_execute = isinstance(call.func, ast.Attribute) and call.func.attr == "execute"
        if not is_sql and not is_execute:
            continue
        assert not any(
            forbidden in statement.value.upper()
            for forbidden in ("DROP TRIGGER", "FOREIGN_KEY_CHECKS", "SET GLOBAL", "KILL ")
        )
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Tuple):
            assert statement.value.count("%s") == len(call.args[1].elts)
            checked += 1
    assert checked >= 20
