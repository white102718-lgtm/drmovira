"""诊断护栏/原样返回与异常纯测；不连接数据库或启动请求。"""

import ast
import asyncio
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from asyncmy.cursors import RE_INSERT_VALUES
from sqlalchemy import text
from sqlalchemy.dialects.mysql.asyncmy import dialect

from orbit_api.account_scope_store import AccountScopeStore

m = importlib.import_module("tools.account_scope_capacity_diagnostics")
DATABASE = "orbit_py_it_" + "a" * 32


@pytest.fixture
def destination(tmp_path, monkeypatch):
    base = tmp_path / ".runtime" / "account-scope-capacity-profile"
    monkeypatch.setattr(m, "BASE", base)
    return base / ("b" * 32)


@pytest.mark.parametrize("name", ["", "a" * 31, "a" * 33, "G" * 32, "..", "b" * 32 + "/nested"])
def test_only_exact_uuid_child_destination(destination, name):
    with pytest.raises(ValueError):
        m.guard_output(m.BASE / name)


def test_outside_runtime_rejected_before_store_install(destination):
    original = AccountScopeStore.create
    with pytest.raises(ValueError):
        m.install_scope_create_diagnostics(destination.parent.parent / ("b" * 32))
    assert AccountScopeStore.create is original


@pytest.mark.parametrize(
    "statement,phase",
    [
        ("INSERT INTO orbit_account_scope_member (x) VALUES (:secret)", "SCOPE_MEMBER_WRITE"),
        (
            "UPDATE orbit_account_scope_snapshot SET ready=1,member_count=:secret",
            "SCOPE_SEAL_WRITE",
        ),
        ("SELECT a.id FROM orbit_ad_account a WHERE a.name=:secret FOR SHARE", "ACCOUNT_READ"),
        ("SELECT auth_version FROM sys_identity_subject WHERE user_id=:secret", "AUTH_READ"),
        ("SELECT revision FROM orbit_account_clock WHERE tenant_id=:secret", "CLOCK_READ"),
        ("SELECT very_private_secret", "OTHER"),
    ],
)
def test_classification_returns_fixed_enum_only(statement, phase):
    assert m.sql_phase(statement) == phase and phase in m.PHASES


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "exception", "cancel", "timeout"])
@pytest.mark.parametrize("own_execute", [False, True])
@pytest.mark.parametrize("copy_mode", [False, True])
async def test_create_keeps_exact_return_exception_and_execute_identity(
    destination, monkeypatch, outcome, own_execute, copy_mode
):
    class Session:
        async def execute(self, *args, **kwargs):
            return "original-sql-result"

    session = Session()
    if own_execute:
        session.execute = AsyncMock(return_value="original-sql-result")
    original_execute = session.execute
    returned = object()
    error = {
        "exception": ValueError("private_sql_token"),
        "cancel": asyncio.CancelledError(),
        "timeout": TimeoutError("private_sql_token"),
    }.get(outcome)

    async def original(_store, selected, *args, **kwargs):
        assert selected is session and args == ("private_sql_token",)
        assert (
            await selected.execute(
                "SELECT a.id FROM orbit_ad_account a", {"secret": "private_sql_token"}
            )
            == "original-sql-result"
        )
        await selected.execute(
            (
                "INSERT INTO orbit_account_scope_member (x) SELECT a.id FROM orbit_ad_account a"
                if copy_mode
                else "INSERT INTO orbit_account_scope_member (x) VALUES (:secret)"
            ),
            (
                {"member_ids": ["private_sql_token"] * 1000}
                if copy_mode
                else [{"secret": "private_sql_token"}] * 1000
            ),
        )
        if error is not None:
            raise error
        return returned

    monkeypatch.setattr(AccountScopeStore, "create", original)
    uninstall = m.install_scope_create_diagnostics(destination)
    try:
        if error is None:
            assert await AccountScopeStore(None).create(session, "private_sql_token") is returned
        else:
            with pytest.raises(type(error)) as caught:
                await AccountScopeStore(None).create(session, "private_sql_token")
            assert caught.value is error
        assert session.execute == original_execute
        assert ("execute" in vars(session)) is own_execute
        files = list(destination.glob("scope-create-*.json"))
        assert len(files) == 1
        text = files[0].read_text()
        assert "private_sql_token" not in text and "SELECT" not in text and "INSERT" not in text
        result = json.loads(text)
        assert result["execute_restored"] is True and result["calls"] == 2
        assert result["member_rows_completed"] == 1000
        assert result["member_batches_completed"] == 1
        assert (
            result["status"]
            == {
                "success": "CREATE_RETURNED",
                "exception": "EXCEPTION",
                "cancel": "CANCELLED",
                "timeout": "TIMEOUT",
            }[outcome]
        )
    finally:
        uninstall()
    assert AccountScopeStore.create is original


@pytest.mark.asyncio
async def test_failed_member_batch_not_reported_as_completed(destination, monkeypatch):
    error = RuntimeError("secret")
    session = SimpleNamespace(execute=AsyncMock(side_effect=error))

    async def original(_store, selected):
        await selected.execute(
            "INSERT INTO orbit_account_scope_member (x) VALUES (:x)", [{"x": "secret"}] * 1000
        )

    monkeypatch.setattr(AccountScopeStore, "create", original)
    uninstall = m.install_scope_create_diagnostics(destination)
    try:
        with pytest.raises(RuntimeError) as caught:
            await AccountScopeStore(None).create(session)
        assert caught.value is error
        result = json.loads(next(destination.glob("scope-create-*.json")).read_text())
        assert result["member_rows_attempted"] == 1000 and result["member_rows_completed"] == 0
        assert result["sql"]["SCOPE_MEMBER_WRITE"]["failed"] == 1
    finally:
        uninstall()


def test_double_install_rejected_without_replacing_active_wrapper(destination, monkeypatch):
    monkeypatch.setattr(AccountScopeStore, "create", AsyncMock())
    uninstall = m.install_scope_create_diagnostics(destination)
    installed = AccountScopeStore.create
    try:
        with pytest.raises(ValueError, match="ALREADY_INSTALLED"):
            m.install_scope_create_diagnostics(destination)
        assert AccountScopeStore.create is installed
    finally:
        uninstall()


class Cursor:
    def __init__(self, database):
        self.database, self.statements, self.current = database, [], []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, values=()):
        self.statements.append((statement, values))
        assert "SQL_TEXT" not in statement and "PROCESSLIST_INFO" not in statement
        if statement == "SELECT DATABASE()":
            self.current = [(self.database,)]
        else:
            assert values == (DATABASE,)
            if "GROUP BY PROCESSLIST_COMMAND" in statement:
                self.current = [("Query", 1), ("Sleep", 2), ("untrusted-secret-command", 1)]
            elif "data_lock_waits" in statement:
                self.current = [(1,)]
            else:
                self.current = [(2, 50000, 49000)]

    def fetchone(self):
        return self.current[0]

    def fetchall(self):
        return self.current


@pytest.mark.parametrize(
    "changes", [{"host": "localhost"}, {"port": 3306}, {"port": True}, {"database": "production"}]
)
def test_database_guard_before_any_sql(destination, changes):
    target = dict(host="127.0.0.1", port=13306, database=DATABASE) | changes
    admin = SimpleNamespace(host=target["host"], port=target["port"], cursor=Mock())
    with pytest.raises(ValueError):
        m.collect_timeout_diagnostic(admin, target["database"], destination)
    admin.cursor.assert_not_called()


def test_actual_selected_database_must_match_before_performance_schema(destination):
    cursor = Cursor("other")
    admin = SimpleNamespace(host="127.0.0.1", port=13306, cursor=lambda: cursor)
    with pytest.raises(ValueError):
        m.collect_timeout_diagnostic(admin, DATABASE, destination)
    assert cursor.statements == [("SELECT DATABASE()", ())]


def test_timeout_snapshot_only_fixed_technical_counts_and_bound_current_database(destination):
    cursor = Cursor(DATABASE)
    admin = SimpleNamespace(host="127.0.0.1", port=13306, cursor=lambda: cursor)
    result = m.collect_timeout_diagnostic(admin, DATABASE, destination)
    assert result["commands"] == {"QUERY": 1, "SLEEP": 2, "CONNECT": 0, "OTHER": 1}
    assert (
        result["lock_waits"],
        result["transactions"],
        result["rows_locked"],
        result["rows_modified"],
    ) == (1, 2, 50000, 49000)
    text = next(destination.glob("timeout-*.json")).read_text()
    assert DATABASE not in text and "secret" not in text and "SELECT" not in text


@pytest.mark.asyncio
async def test_parallel_create_diagnostics_keep_each_session_counts_and_restore(
    destination, monkeypatch
):
    gate = asyncio.Event()
    arrived = 0

    async def execute(statement, params):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            gate.set()
        await gate.wait()
        return "same-result"

    sessions = [SimpleNamespace(execute=execute), SimpleNamespace(execute=execute)]

    async def original(store, session, count):
        return await session.execute(
            "INSERT INTO orbit_account_scope_member (x) VALUES (:x)", [{"x": "secret"}] * count
        )

    monkeypatch.setattr(AccountScopeStore, "create", original)
    uninstall = m.install_scope_create_diagnostics(destination)
    try:
        assert (
            await asyncio.gather(
                *(
                    AccountScopeStore(None).create(session, count)
                    for session, count in zip(sessions, (1000, 7), strict=True)
                )
            )
            == ["same-result"] * 2
        )
        assert all(session.execute is execute for session in sessions)
        reports = [json.loads(path.read_text()) for path in destination.glob("scope-create-*.json")]
        assert sorted(report["member_rows_completed"] for report in reports) == [7, 1000]
        assert all(report["calls"] == 1 and report["execute_restored"] for report in reports)
    finally:
        uninstall()


@pytest.mark.asyncio
async def test_diagnostic_file_failure_does_not_change_business_return_or_restore(
    destination, monkeypatch
):
    returned = object()
    session = SimpleNamespace(execute=AsyncMock())
    previous = session.execute

    async def original(*args):
        return returned

    monkeypatch.setattr(AccountScopeStore, "create", original)
    monkeypatch.setattr(m, "_save", Mock(side_effect=OSError("private path")))
    uninstall = m.install_scope_create_diagnostics(destination)
    try:
        assert await AccountScopeStore(None).create(session) is returned
        assert session.execute is previous
    finally:
        uninstall()


def test_existing_reparse_directory_rejected(destination, monkeypatch):
    destination.mkdir(parents=True)
    original = Path.lstat

    def metadata(path, *args, **kwargs):
        if path == destination:
            return SimpleNamespace(st_mode=0o40755, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", metadata)
    with pytest.raises(ValueError, match="LINK_REJECTED"):
        m.guard_output(destination)


def test_actual_member_insert_render_matches_installed_asyncmy_bulk_regex():
    source = Path(__file__).parents[1] / "orbit_api" / "account_scope_store.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    statements = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("INSERT INTO orbit_account_scope_member ")
    ]
    assert len(statements) == 1
    rendered = str(text(statements[0]).compile(dialect=dialect()))
    assert RE_INSERT_VALUES.match(rendered) is not None
