"""日历真实工具前置/局部计时护栏；不连接DB/运行HTTP。"""

import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

core = importlib.import_module("tools.rule_simulation_calendar_checks")
DATABASE = "orbit_py_it_" + "c" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE + "\n"),
        ("127.0.0.1", 13306.0, DATABASE),
    ],
)
def test_target_reuses_strict_guard_before_any_fixture_sql_or_http(host, port, database):
    client = Mock()
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    with pytest.raises(ValueError):
        core.run_rule_simulation_calendar_checks(client, admin, {}, "", None, database, [])
    admin.cursor.assert_not_called()
    assert not client.mock_calls


def test_actual_selected_database_refusal_precedes_all_fixture_writes():
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
    with pytest.raises(ValueError):
        core.run_rule_simulation_calendar_checks(client, admin, {}, "", None, DATABASE, [])
    assert statements == [("SELECT DATABASE()", ())] and not client.mock_calls


@pytest.mark.asyncio
async def test_fixed_statement_counter_only_current_session_preserves_args_and_restores():
    calls = []

    async def original(statement, *args, **kwargs):
        calls.append((statement, args, kwargs))
        return "unchanged_result"

    session = SimpleNamespace(execute=original)
    other = SimpleNamespace(execute=original)
    with core.count_calendar_time(session) as counter:
        assert await session.execute(core.TIME_SQL) == "unchanged_result"
        await session.execute(
            "SELECT harmless", {"sensitive": "pure-not-logged"}, execution_options={"a": True}
        )
        await other.execute(core.TIME_SQL)
        assert counter == {"utc_reference_calls": 1}
        assert set(counter) == {"utc_reference_calls"}
    assert session.execute is original and other.execute is original
    assert calls[1] == (
        "SELECT harmless",
        ({"sensitive": "pure-not-logged"},),
        {"execution_options": {"a": True}},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["cancel", "exception"])
async def test_counter_restoration_does_not_mask_original_cancel_or_failure(kind):
    error = asyncio.CancelledError() if kind == "cancel" else RuntimeError("pure")

    async def original(*args, **kwargs):
        raise error

    session = SimpleNamespace(execute=original)
    with pytest.raises(type(error)) as caught:
        with core.count_calendar_time(session) as counter:
            await session.execute(core.TIME_SQL)
    assert caught.value is error and session.execute is original
    assert counter == {"utc_reference_calls": 1}


def test_fixed_cases_reserved_native_and_original_window_values():
    assert core.NATIVE_ACTOR == 990671
    assert core.NATIVE_ACTOR != 990670 and not 990631 <= core.NATIVE_ACTOR <= 990654
    assert (
        len(core.RULE_SIMULATION_CALENDAR_CASES)
        == len(set(core.RULE_SIMULATION_CALENDAR_CASES))
        == 7
    )
    assert core.WINDOWS == ("TODAY", "YESTERDAY", "LAST_3D", "LAST_7D")


@pytest.mark.asyncio
async def test_profile_wrapper_counts_any_execute_attempt_and_restores_exact_method():
    calls = []

    async def original(statement, *args, **kwargs):
        calls.append(statement)
        return "unchanged"

    session = SimpleNamespace(execute=original)
    with core.count_profile_execute(session) as count:
        assert count == {"execute_calls": 0}
        operation = session.execute("fixed-pure-select")
        # 不等await就计数，防止方法补SQL但遗忘await仍被误认零查询。
        assert count == {"execute_calls": 1}
        assert await operation == "unchanged"
    assert session.execute is original and calls == ["fixed-pure-select"]
