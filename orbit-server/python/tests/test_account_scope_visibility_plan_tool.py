"""性能工具边界/计划脱敏纯测；不证明真实SQL计划或5万容量。"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

path = Path(__file__).resolve().parents[2] / "tools/account_scope_visibility_plan_checks.py"
spec = importlib.util.spec_from_file_location("scope_plan_tool", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_plan_summary_keeps_real_indexes_and_rows_but_not_where_constants():
    plan = {
        "query_block": {
            "nested_loop": [
                {
                    "table": {
                        "table_name": "a",
                        "key": "PRIMARY",
                        "rows_examined_per_scan": 1,
                        "rows_produced_per_join": 50000,
                        "attached_condition": "private fixture condition",
                    }
                }
            ]
        }
    }
    assert module.summary(plan) == [
        {
            "table_name": "a",
            "key": "PRIMARY",
            "rows_examined_per_scan": 1,
            "rows_produced_per_join": 50000,
        }
    ]


@pytest.mark.parametrize(
    "database,host,port",
    [
        ("production", "127.0.0.1", 13306),
        ("orbit_py_it_" + "a" * 32, "remote", 13306),
        ("orbit_py_it_" + "a" * 32, "127.0.0.1", 3306),
    ],
)
def test_reject_nonexclusive_database_before_any_fixture_write(database, host, port):
    with pytest.raises(ValueError):
        module.run_account_scope_visibility_plan_checks(
            None, SimpleNamespace(host=host, port=port), {}, "unused", None, database, []
        )
