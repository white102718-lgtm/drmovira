"""时间预览工具纯护栏；不启动真实SQL/HTTP。"""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

core = importlib.import_module("tools.rule_schedule_preview_checks")
DATABASE = "orbit_py_it_" + "c" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE + "\n"),
    ],
)
def test_guard_precedes_all_sql_or_http(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError):
        core.run_rule_schedule_preview_checks(client, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()
    client.post.assert_not_called()


def test_seven_limited_preview_cases_not_production_scheduler_or_cancel():
    assert len(core.RULE_SCHEDULE_PREVIEW_CASES) == 7
    assert len(set(core.RULE_SCHEDULE_PREVIEW_CASES)) == 7
    assert all(
        name.startswith("pythonRuleSchedulePreview") for name in core.RULE_SCHEDULE_PREVIEW_CASES
    )


def test_sql_literal_parameters_and_no_deleting_original_clock_to_fake_first_use():
    tree = ast.parse(Path(core.__file__).read_text(encoding="utf-8"))
    checked = 0
    for call in ast.walk(tree):
        if (
            not isinstance(call, ast.Call)
            or not isinstance(call.func, ast.Name)
            or call.func.id != "sql"
            or not call.args
        ):
            continue
        if not isinstance(call.args[0], ast.Constant) or type(call.args[0].value) is not str:
            continue
        statement = call.args[0].value
        assert "DELETE FROM orbit_rule_clock" not in statement
        assert "INSERT INTO orbit_rule_clock" not in statement
        if len(call.args) > 1 and isinstance(call.args[1], ast.Tuple):
            assert statement.count("%s") == len(call.args[1].elts)
            checked += 1
    assert checked >= 20
