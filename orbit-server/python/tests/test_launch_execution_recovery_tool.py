"""恢复SQL专项严格隔离护栏；不连接DB、不启动HTTP或引擎。"""

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

module = importlib.import_module("tools.launch_execution_recovery_checks")
DATABASE = "orbit_py_it_" + "a" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("192.0.2.1", 13306, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", "13306", DATABASE),
        ("127.0.0.1", 13306.0, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE[:-1]),
        ("127.0.0.1", 13306, DATABASE + "\n"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
        ("127.0.0.1", 13306, None),
    ],
)
def test_wrong_target_rejected_before_database_or_http(host, port, database):
    client = Mock()
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    with pytest.raises(ValueError):
        module.run_execution_recovery_checks(client, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()
    assert not client.mock_calls


def test_actual_selected_database_must_match_uuid_before_any_http():
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchall.return_value = (("orbit_py_it_" + "b" * 32,),)
    client = Mock()
    admin = SimpleNamespace(
        host="127.0.0.1", port=13306, cursor=Mock(return_value=cursor), commit=Mock()
    )
    with pytest.raises(AssertionError):
        module.run_execution_recovery_checks(client, admin, {}, "unused", None, DATABASE, [])
    cursor.execute.assert_called_once_with("SELECT DATABASE()", ())
    assert not client.mock_calls


def test_schema_metadata_like_is_bound_parameter_and_six_triggers_remain_required():
    queries = Mock(side_effect=[((2,),), ((6,),)])
    module.assert_recovery_schema(queries)
    assert len(queries.call_args_list) == 2
    first, second = queries.call_args_list
    assert "information_schema.TABLES" in first.args[0]
    assert second.args == (
        "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE "
        "TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME LIKE %s",
        ("guard_exec_recovery_%",),
    )
    # 与格式驱动相同，参数内的%不被递归格式化；SQL文本只含合法占位符。
    assert (second.args[0] % second.args[1]).endswith("LIKE guard_exec_recovery_%")


def test_wrong_trigger_count_is_still_rejected_after_binding_fix():
    with pytest.raises(AssertionError):
        module.assert_recovery_schema(Mock(side_effect=[((2,),), ((5,),)]))
