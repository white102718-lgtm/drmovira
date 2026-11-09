"""048/049专属SQL工具纯护栏；不连接MySQL，不冒充真实七组schema验收。"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pymysql
import pytest

PATH = Path(__file__).resolve().parents[2] / "tools/metric_fact_schema_checks.py"
spec = importlib.util.spec_from_file_location("metric_fact_schema_tool_guard", PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("192.0.2.1", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 31),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 32 + "\n"),
        ("127.0.0.1", 13306, None),
    ],
)
def test_all_entry_guards_before_any_cursor(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    for target in (
        lambda: module.MetricFactSqlFixture(admin, database),
        lambda: module.run_metric_fact_schema_checks(admin, database, []),
    ):
        with pytest.raises(ValueError):
            target()
    admin.cursor.assert_not_called()


def test_actual_database_mismatch_refuses_before_query_or_mutation():
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.return_value = ("not_this_run",)
    admin = SimpleNamespace(host="127.0.0.1", port=13306, cursor=lambda: cursor)
    with pytest.raises(ValueError):
        module.MetricFactSqlFixture(admin, "orbit_py_it_" + "a" * 32)
    cursor.execute.assert_called_once_with("SELECT DATABASE()")


@pytest.mark.parametrize(
    "value,expected",
    [("中间", "%中间%"), ("a_b%c!d", "%a!_b!%c!!d%"), ("%", "%!%%"), ("", "%%")],
)
def test_contains_is_literal_contains_not_prefix_or_user_pattern(value, expected):
    assert module.literal_contains(value) == expected


def fixture_without_database():
    fixture = object.__new__(module.MetricFactSqlFixture)
    fixture.tenant, fixture.owner, fixture.team = "tenant", "owner", "team"
    fixture.now = "trusted_fixed_fixture_utc"
    fixture.sql = Mock(return_value=1)
    fixture.denied = Mock()
    return fixture


@pytest.mark.parametrize(
    "table,row",
    [
        ("sys_user", {"id": 1}),
        ("orbit_metric_entity_snapshot", {"name); DROP": 1}),
        ("orbit_metric_entity_snapshot", {}),
    ],
)
def test_insert_rejects_unowned_identifiers_before_sql(table, row):
    fixture = fixture_without_database()
    with pytest.raises(ValueError):
        fixture.insert(table, row)
    fixture.sql.assert_not_called()
    fixture.denied.assert_not_called()


def test_bound_insert_does_not_interpolate_raw_name_or_authorize_it():
    fixture = fixture_without_database()
    row = {"tenant_id": "tenant", "id": "id", "name": "SQL_ONLY_'%_!"}
    assert fixture.insert("orbit_metric_entity_snapshot", row) == row
    statement, arguments = fixture.sql.call_args.args
    assert row["name"] not in statement
    assert arguments == tuple(row.values()) and statement.count("%s") == 3


def test_fact_fixture_uses_all_four_exact_snapshots_and_can_test_one_fk_without_unique_collision():
    fixture = fixture_without_database()
    fixture.insert = Mock(side_effect=lambda _table, row, **kwargs: (row, kwargs))
    tree = [{"id": f"snapshot-{i}", "entity_id": f"entity-{i}"} for i in range(4)]
    cell = {
        "id": "fresh-cell",
        "account_id": "account",
        "business_date": "2026-01-01",
        "profile_id": "profile",
        "profile_version": "observed-v001",
        "capture_sequence": 205,
    }
    row, options = fixture.fact(
        cell, tree, changes={"ad_snapshot_id": "wrong-parent-only"}, deny={1452}
    )
    assert row["cell_id"] == "fresh-cell" and row["capture_sequence"] == 205
    assert row["account_snapshot_id"] == "snapshot-0"
    assert row["campaign_snapshot_id"] == "snapshot-1"
    assert row["adset_snapshot_id"] == "snapshot-2"
    assert row["ad_snapshot_id"] == "wrong-parent-only"
    assert row["ad_id"] == "entity-3" and options == {"deny": {1452}}
    assert not any(key.endswith("name") for key in row)


@pytest.mark.parametrize("code,allowed", [(1452, {1452}), (1644, {1644}), (1062, {1062})])
def test_expected_sql_denial_rolls_back_without_printing_original_message(code, allowed):
    fixture = fixture_without_database()
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.execute.side_effect = pymysql.err.IntegrityError(code, "DO_NOT_LOG_PAYLOAD")
    fixture.admin = SimpleNamespace(cursor=lambda: cursor, begin=Mock(), rollback=Mock())
    module.MetricFactSqlFixture.denied(fixture, "fixed statement", ("private",), allowed)
    fixture.admin.begin.assert_called_once()
    fixture.admin.rollback.assert_called_once()


def test_unexpected_sql_code_and_success_both_fail_closed_and_rollback():
    fixture = fixture_without_database()
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    fixture.admin = SimpleNamespace(cursor=lambda: cursor, begin=Mock(), rollback=Mock())
    cursor.execute.side_effect = pymysql.err.OperationalError(2013, "DO_NOT_LOG_SQL_OR_PAYLOAD")
    with pytest.raises(AssertionError) as result:
        module.MetricFactSqlFixture.denied(fixture, "fixed", ("private",), {1452})
    assert "2013" in str(result.value) and "DO_NOT_LOG" not in str(result.value)
    cursor.execute.side_effect = None
    with pytest.raises(AssertionError, match="却成功"):
        module.MetricFactSqlFixture.denied(fixture, "fixed", (), {1452})
    assert fixture.admin.rollback.call_count == 2


def test_unexpected_positive_sql_error_is_fixed_code_only_and_no_commit():
    fixture = fixture_without_database()
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.execute.side_effect = pymysql.err.OperationalError(2013, "DO_NOT_LOG_SQL_OR_PAYLOAD")
    fixture.admin = SimpleNamespace(cursor=lambda: cursor, commit=Mock(), rollback=Mock())
    with pytest.raises(AssertionError) as result:
        module.MetricFactSqlFixture.sql(fixture, "fixed", ("private",))
    assert str(result.value) == "{'unexpected_sql_code': 2013}"
    fixture.admin.commit.assert_not_called()
    fixture.admin.rollback.assert_called_once()


def test_latest_sql_keeps_latest_ranking_before_tombstone_and_never_ad_history_fallback():
    assert "PARTITION BY c.tenant_id,c.account_id,c.business_date" in module.LATEST_CELL_SQL
    assert "ORDER BY c.capture_sequence DESC" in module.LATEST_CELL_SQL
    assert "p.state='PUBLISHED'" in module.LATEST_CELL_SQL
    assert "p.generation<=%s" in module.LATEST_CELL_SQL
    assert "f.cell_id=c.id AND f.is_deleted=0" in module.LATEST_CELL_SQL
    assert "WHERE c.rn=1" in module.LATEST_CELL_SQL
    assert "OFFSET" not in module.LATEST_CELL_SQL


def test_exact_seven_names_and_readme_limits_do_not_claim_publisher_or_http_success():
    assert len(module.METRIC_FACT_SCHEMA_CASES) == len(set(module.METRIC_FACT_SCHEMA_CASES)) == 7
    source = PATH.read_text(encoding="utf-8")
    assert "SQL_ONLY_NOT_PLATFORM" in source
    assert "hash唯一冲突不是全文比较协议" in source
    assert "'IMAGE','image/png','UPLOADING'" in source
    assert "'image/png','READY'" not in source
    assert "client.post" not in source and "requests." not in source
