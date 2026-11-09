"""真实目录工具护栏纯测；不初始化数据库或执行实际DDL。"""

import ast
import importlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_launch_execution_candidates import fixture

from orbit_api.errors import OrbitError

module = importlib.import_module("tools.launch_execution_candidate_checks")
DATABASE = "orbit_py_it_" + "a" * 32
NAME = "guard_execution_command_update"


@pytest.mark.asyncio
async def test_directory_receives_real_session_factory_not_factory_returning_factory():
    sessions = async_sessionmaker(expire_on_commit=False)
    directory = module.candidate_directory(None, sessions)
    assert directory.sessions_factory is sessions
    async with directory.sessions_factory() as session:
        assert isinstance(session, AsyncSession)
        assert not session.in_transaction()
    with pytest.raises(TypeError, match="ASYNC_SESSIONMAKER_REQUIRED"):
        module.candidate_directory(None, lambda: sessions)


def test_preparation_join_has_table_alias_boundary():
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    queries = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    preparation = [value for value in queries if "SELECT p.id,p.source_revision" in value]
    assert len(preparation) == 1
    assert "orbit_launch_execution_preparation p JOIN orbit_task t " in preparation[0]


class Cursor:
    def __init__(self, admin):
        self.admin = admin
        self.rows = []
        self.description = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        self.admin.operations.append((sql, params))
        if sql == "SELECT DATABASE()":
            self.rows = [(self.admin.selected,)]
        elif sql.startswith("SELECT EVENT_OBJECT_TABLE"):
            self.rows = [(self.admin.table, "BEFORE", self.admin.operation, "BEGIN END")]
            assert params == (DATABASE, NAME)
        elif sql.startswith("SHOW CREATE TRIGGER"):
            assert self.admin.enabled
            self.description = [("SQL Original Statement",)]
            self.rows = [(self.admin.ddl,)]
        elif sql == "DROP TRIGGER `" + NAME + "`":
            assert self.admin.enabled
            self.admin.enabled = False
        elif sql == self.admin.ddl:
            if self.admin.fail_restore:
                raise RuntimeError("pure secret-bearing database detail")
            self.admin.enabled = True
        else:
            raise AssertionError("UNEXPECTED_TEST_STATEMENT")

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return tuple(self.rows)


class Admin:
    host = "127.0.0.1"
    port = 13306

    def __init__(self):
        self.selected = DATABASE
        self.table = "orbit_launch_execution_command"
        self.operation = "UPDATE"
        self.enabled = True
        self.fail_restore = False
        self.operations = []
        self.ddl = (
            "CREATE DEFINER=`fixture`@`localhost` TRIGGER "
            + NAME
            + " BEFORE UPDATE ON orbit_launch_execution_command FOR EACH ROW BEGIN END"
        )
        self.commit = Mock()

    def cursor(self):
        return Cursor(self)


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("192.0.2.1", 13306, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", "13306", DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE + "\n"),
    ],
)
def test_target_guard_before_fixture_http_or_database(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError):
        module.run_execution_candidate_checks(client, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()
    assert not client.mock_calls


def test_case_contract_is_twelve_unique_names_no_claim_send():
    assert len(module.EXECUTION_CANDIDATE_CASES) == 12
    assert len(set(module.EXECUTION_CANDIDATE_CASES)) == 12
    assert set(module.TRIGGER_TABLES) == {
        "guard_execution_byte_update",
        "guard_execution_command_update",
        "guard_execution_task_update",
        "guard_execution_edge_update",
    }


def test_literal_fixture_statements_bind_every_parameter_exactly():
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Tuple) or len(node.elts) != 2:
            continue
        sql, params = node.elts
        if (
            not isinstance(sql, ast.Constant)
            or not isinstance(sql.value, str)
            or not sql.value.startswith(("INSERT ", "UPDATE "))
        ):
            continue
        if isinstance(params, ast.Tuple) and not any(
            isinstance(value, ast.Starred) for value in params.elts
        ):
            assert sql.value.count("%s") == len(params.elts)
            checked += 1
    assert checked >= 10


@pytest.mark.parametrize(
    "name",
    [
        "guard_exec_attempt_delete",
        "guard_execution_command_delete",
        "anything;DROP TABLE orbit_task",
        "",
        None,
    ],
)
def test_trigger_whitelist_never_expands_to_other_guards(name):
    admin = Admin()
    with pytest.raises(ValueError):
        module.trigger_definition(admin, DATABASE, name)
    assert admin.operations == []


@pytest.mark.parametrize("problem", ["database", "table", "event", "ddl"])
def test_trigger_original_identity_verified_before_drop(problem):
    admin = Admin()
    if problem == "database":
        admin.selected = "orbit_py_it_" + "b" * 32
    elif problem == "table":
        admin.table = "orbit_task"
    elif problem == "event":
        admin.operation = "DELETE"
    else:
        admin.ddl = "CREATE TRIGGER wrong BEFORE UPDATE ON orbit_task FOR EACH ROW BEGIN END"
    with pytest.raises(ValueError):
        with module.technical_corruption_trigger(admin, DATABASE, NAME):
            raise AssertionError("MUST_NOT_ENTER_CORRUPTION")
    assert not any(sql.startswith("DROP") for sql, _ in admin.operations)


@pytest.mark.parametrize("fail_body", [False, True])
def test_exact_original_ddl_restored_even_if_body_fails(fail_body):
    admin = Admin()
    original = module.trigger_definition(admin, DATABASE, NAME)
    if fail_body:
        with pytest.raises(ValueError, match="pure fault"):
            with module.technical_corruption_trigger(admin, DATABASE, NAME):
                assert not admin.enabled
                raise ValueError("pure fault")
    else:
        with module.technical_corruption_trigger(admin, DATABASE, NAME):
            assert not admin.enabled
    assert admin.enabled and module.trigger_definition(admin, DATABASE, NAME) == original
    assert sum(sql.startswith("DROP") for sql, _ in admin.operations) == 1
    assert sum(sql == admin.ddl for sql, _ in admin.operations) == 1


def test_cleanup_failure_has_fixed_preserve_marker_and_no_raw_details(capsys):
    admin = Admin()
    admin.fail_restore = True
    with pytest.raises(module.CandidateFixtureCleanupError) as caught:
        with module.technical_corruption_trigger(admin, DATABASE, NAME):
            pass
    assert caught.value.preserve_fixture_database is True
    assert caught.value.phase == "trigger-restore" and caught.value.trigger == NAME
    assert "secret" not in str(caught.value) and "secret" not in capsys.readouterr().out
    assert not admin.enabled  # 未恢复即需保留本轮UUID库，不能伪称完成。


@pytest.mark.parametrize(
    "name,phase", [("arbitrary", "row-restore"), (NAME, "request body secret")]
)
def test_cleanup_error_cannot_echo_untrusted_names_or_phases(name, phase):
    with pytest.raises(ValueError):
        module.CandidateFixtureCleanupError(name, phase)


@pytest.mark.asyncio
async def test_authority_capture_has_exact_known_task_only():
    data = fixture()
    authority = module.IsolatedCandidateAuthority(DATABASE, data["grant"])
    assert await authority.capture(data["task"]["id"]) == data["grant"]
    with pytest.raises(OrbitError):
        await authority.capture(data["prep"]["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [None, "tenant", "subject", "team", "auth_version"])
async def test_authority_revalidates_current_scope_not_just_repeating_hash(monkeypatch, bad):
    data = fixture()
    grant = data["grant"]
    context = SimpleNamespace(tenant_id=grant.tenant_id, subject_id=grant.subject_id)
    user = [grant.tenant_id, grant.subject_id, grant.owner_team_id, grant.auth_revision]
    if bad == "tenant":
        context.tenant_id = data["prep"]["id"]
    elif bad == "subject":
        context.subject_id = data["prep"]["id"]
    elif bad == "team":
        user[2] = data["prep"]["id"]
    elif bad == "auth_version":
        user[3] += 1
    # 原actor与owner在真实工具为同一admin；pure独立夹具把owner同一化。
    grant = replace(grant, owner_user_id=grant.subject_id)
    required = AsyncMock(return_value=context)
    monkeypatch.setattr(module, "require_business_access", required)
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(
            engine=SimpleNamespace(
                url=URL.create("mysql+asyncmy", host="127.0.0.1", port=13306, database=DATABASE)
            )
        ),
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one=lambda: DATABASE),
                SimpleNamespace(one=lambda: tuple(user)),
            ]
        ),
    )
    authority = module.IsolatedCandidateAuthority(DATABASE, grant)
    if bad:
        with pytest.raises(OrbitError) as caught:
            await authority.revalidate(session, grant)
        assert caught.value.code == "ISOLATED_CANDIDATE_IDENTITY_CHANGED"
    else:
        assert await authority.revalidate(session, grant) == grant
    assert required.await_args.args[1:] == (grant.actor_id, "launch", "launch.execute")
    assert required.await_args.kwargs == {"acting_subject": False}
