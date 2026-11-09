"""独立SQL工具安全协议，不以替身充当真实MySQL/锁护栏验收。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pymysql
import pytest
from tools.launch_execution_guard_checks import (
    LAUNCH_EXECUTION_GUARD_CASES,
    error_number,
    guard_target,
)


@pytest.mark.parametrize(
    ("host", "port", "database"),
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit_database"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
    ],
)
def test_guard_refuses_other_target_without_opening_cursor(host, port, database):
    connection = SimpleNamespace(host=host, port=port, cursor=Mock())
    with pytest.raises(ValueError):
        guard_target(connection, database)
    connection.cursor.assert_not_called()


def test_guard_checks_actual_database_in_addition_to_declared_name():
    cursor = Mock()
    cursor.fetchone.return_value = ("orbit_py_it_" + "b" * 32,)
    manager = Mock()
    manager.__enter__ = Mock(return_value=cursor)
    manager.__exit__ = Mock(return_value=False)
    connection = SimpleNamespace(host="127.0.0.1", port=13306, cursor=Mock(return_value=manager))
    with pytest.raises(ValueError):
        guard_target(connection, "orbit_py_it_" + "a" * 32)
    cursor.execute.assert_called_once_with("SELECT DATABASE()")


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (pymysql.err.OperationalError(1213, "must-not-leak-body"), 1213),
        (pymysql.err.OperationalError(1644, "must-not-leak-body"), 1644),
        (pymysql.err.OperationalError(3819, "must-not-leak-body"), 3819),
        (pymysql.err.OperationalError("1213", "must-not-leak-body"), None),
        (ValueError("must-not-leak-body"), None),
    ],
)
def test_diagnostics_only_expose_numeric_mysql_errno(failure, expected):
    assert error_number(failure) == expected


def test_case_inventory_is_unique_and_does_not_claim_execute_acceptance():
    assert len(LAUNCH_EXECUTION_GUARD_CASES) == len(set(LAUNCH_EXECUTION_GUARD_CASES)) == 11
    assert all(name.startswith("pythonExecutionGuard") for name in LAUNCH_EXECUTION_GUARD_CASES)


def test_lock_observer_retains_refresh_gap_and_real_lock_condition(monkeypatch):
    import tools.launch_execution_guard_checks as tool

    cursor = Mock()
    cursor.fetchone.side_effect = [None, ("LOCK WAIT",)]
    manager = Mock()
    manager.__enter__ = Mock(return_value=cursor)
    manager.__exit__ = Mock(return_value=False)
    connection = SimpleNamespace(cursor=Mock(return_value=manager))
    sleeps = []
    monkeypatch.setattr(tool.time, "sleep", sleeps.append)
    tool._locked_wait(connection, 123)
    assert cursor.execute.call_count == 2
    assert sleeps == [0.12]


def test_finished_waiter_reports_only_numeric_failure_before_metadata_query(capsys):
    from concurrent.futures import Future

    import tools.launch_execution_guard_checks as tool

    pending = Future()
    pending.set_exception(pymysql.err.OperationalError(1644, "secret-body-must-not-leak"))
    connection = SimpleNamespace(cursor=Mock())
    with pytest.raises(AssertionError) as failure:
        tool._locked_wait(connection, 123, pending=pending)
    assert failure.value.args[0]["actual_errno"] == 1644
    assert failure.value.args[0]["phase"] == "waiter_finished_error"
    assert "secret-body" not in capsys.readouterr().out
    connection.cursor.assert_not_called()
