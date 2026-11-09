"""独立scope容量工具护栏纯测；不装载真实账户/运行HTTP或数据库。"""

import ast
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from pymysql.cursors import RE_INSERT_VALUES

m = importlib.import_module("tools.account_scope_profile_checks")
diagnostics = importlib.import_module("tools.account_scope_capacity_diagnostics")
DATABASE = "orbit_py_it_" + "a" * 32


@pytest.mark.parametrize(
    "changes",
    [
        {"host": "localhost"},
        {"host": "192.0.2.1"},
        {"port": 3306},
        {"port": True},
        {"database": "orbit"},
        {"database": DATABASE + "\n"},
    ],
)
def test_invalid_target_no_sql_or_http(tmp_path, changes):
    target = dict(host="127.0.0.1", port=13306, database=DATABASE) | changes
    admin = SimpleNamespace(host=target["host"], port=target["port"], cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError):
        m.run_scope_create_profile_checks(
            client, admin, {}, "unused", None, target["database"], [], diagnostic_dir=tmp_path
        )
    admin.cursor.assert_not_called()
    client.get.assert_not_called()
    client.post.assert_not_called()


def test_fixed_three_new_cases_do_not_impersonate_original_capacity_evidence():
    assert len(m.SCOPE_CREATE_PROFILE_CASES) == len(set(m.SCOPE_CREATE_PROFILE_CASES)) == 3
    assert all(name.startswith("pythonScopeCreateProfile") for name in m.SCOPE_CREATE_PROFILE_CASES)
    assert m.COUNT == 50000 and m.PAGE_SIZE == 200


def test_seed_statement_has_only_bulk_placeholders_and_no_spend_insert():
    tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
    sql = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    insert = [value for value in sql if value.startswith("INSERT INTO ")]
    assert len(insert) == 1 and insert[0].startswith("INSERT INTO orbit_ad_account(")
    assert insert[0].count("%s") == 15 and RE_INSERT_VALUES.match(insert[0])
    assert not any("INSERT INTO orbit_account_spend_day" in value for value in sql)


def test_hash_keeps_all_original_seven_frozen_fields_and_order():
    row = ("id", "external", "中文名称", 1, "owner", "team", "USD")
    expected = __import__("hashlib").sha256(m.canonical([list(row)]).encode()).hexdigest()
    assert m.member_digest([row]) == expected
    for index in range(7):
        changed = list(row)
        changed[index] = 2 if index == 3 else "changed"
        assert m.member_digest([changed]) != expected
    assert m.member_digest([row, row[:-1] + ("EUR",)]) != m.member_digest(
        [row[:-1] + ("EUR",), row]
    )
    with pytest.raises(ValueError):
        m.member_digest([row[:-1]])


class Cursor:
    def __init__(self, database=DATABASE):
        self.database, self.stored, self.rows, self.statements = database, [], [], []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, params=()):
        self.statements.append((statement, params))
        if statement == "SELECT DATABASE()":
            self.rows = [(self.database,)]
        elif statement == (
            "SELECT @@global.innodb_buffer_pool_size,@@global.innodb_redo_log_capacity,"
            "@@global.innodb_flush_log_at_trx_commit"
        ):
            self.rows = [(1073741824, 1073741824, 1)]
        elif statement.startswith("SELECT b.tenant_id,b.id,b.team_id"):
            self.rows = [("tenant", "owner", "team")]
        elif statement.startswith("UPDATE orbit_account_clock"):
            self.rows = []
        elif statement.startswith("SELECT id,external_id,name,revision"):
            self.rows = [(r[1], r[2], r[3], 1, r[5], r[6], r[7]) for r in self.stored]
        elif statement.startswith("SELECT COUNT(*) FROM orbit_account_spend_day"):
            self.rows = [(0,)]
        else:
            raise AssertionError("UNEXPECTED_PURE_STATEMENT")

    def executemany(self, statement, params):
        assert RE_INSERT_VALUES.match(statement)
        self.stored.extend(params)

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows


@pytest.fixture
def harness(tmp_path, monkeypatch):
    base = tmp_path / ".runtime" / "account-scope-capacity-profile"
    monkeypatch.setattr(diagnostics, "BASE", base)
    destination = base / ("b" * 32)
    cursor = Cursor()
    admin = SimpleNamespace(
        host="127.0.0.1",
        port=13306,
        cursor=lambda: cursor,
        begin=Mock(),
        commit=Mock(),
        rollback=Mock(),
    )
    client = Mock()
    client.timeout = httpx.Timeout(10)
    client.get.return_value = httpx.Response(
        200,
        json={"csrf_token": "private_csrf_fixture"},
        headers={"cache-control": "no-store", "x-request-id": "pure"},
    )
    return destination, cursor, admin, client


def test_client_read_timeout_must_remain_original_ten_seconds(harness):
    directory, cursor, admin, client = harness
    client.timeout = httpx.Timeout(30)
    with pytest.raises(ValueError, match="TEN_SECOND"):
        m.run_scope_create_profile_checks(
            client, admin, {}, "unused", None, DATABASE, [], diagnostic_dir=directory
        )
    assert cursor.statements == []
    client.post.assert_not_called()


def test_actual_database_guard_before_seed_or_http(harness):
    directory, cursor, admin, client = harness
    cursor.database = "not-this-fixture"
    with pytest.raises(AssertionError):
        m.run_scope_create_profile_checks(
            client, admin, {}, "unused", None, DATABASE, [], diagnostic_dir=directory
        )
    assert cursor.stored == [] and cursor.statements == [("SELECT DATABASE()", ())]
    client.get.assert_not_called()


@pytest.mark.parametrize("diagnostic_fails", [False, True])
def test_post_readtimeout_is_same_exception_after_diagnostic_no_retry_or_timeout_override(
    harness, monkeypatch, diagnostic_fails
):
    directory, cursor, admin, client = harness
    monkeypatch.setattr(m, "COUNT", 500)  # 纯工具护栏缩小本地替身，绝非真实容量证据。
    error = httpx.ReadTimeout("private_request_body_or_key")
    client.post.side_effect = error
    collector = (
        Mock(side_effect=RuntimeError("private_database_detail"))
        if diagnostic_fails
        else Mock(return_value={"collected": True})
    )
    monkeypatch.setattr(m, "collect_timeout_diagnostic", collector)
    cases = []
    with pytest.raises(httpx.ReadTimeout) as caught:
        m.run_scope_create_profile_checks(
            client,
            admin,
            {"Authorization": "private_bearer"},
            "unused",
            None,
            DATABASE,
            cases,
            diagnostic_dir=directory,
        )
    assert caught.value is error and client.post.call_count == 1
    assert "timeout" not in client.post.call_args.kwargs
    collector.assert_called_once_with(admin, DATABASE, directory)
    assert cases == m.SCOPE_CREATE_PROFILE_CASES[:1]
    assert len(cursor.stored) == 500 and admin.begin.call_count == 2
    output = (directory / "scope-profile-report.json").read_text()
    assert "private" not in output and "Authorization" not in output
    result = json.loads(output)
    assert result["mysql_settings"] == {
        "buffer_pool_bytes": 1073741824,
        "redo_capacity_bytes": 1073741824,
        "flush_log_at_trx_commit": 1,
    }
    assert result["status"] == "READ_TIMEOUT" and result["daily_facts"] == 0
    assert result["timeout_diagnostic"] == (
        {"collected": False} if diagnostic_fails else {"collected": True}
    )
