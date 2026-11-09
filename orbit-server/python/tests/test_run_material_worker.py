"""CLI/引导纯测：无真实private/env读取、无SQL/socket/进程启动。"""

import importlib.util
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def cli():
    path = Path(__file__).resolve().parents[2] / "tools/run_material_worker.py"
    spec = importlib.util.spec_from_file_location("material_worker_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--once", "--serve"],
        ["--once", "--cycles", "1"],
        ["--serve", "--cycles", "0"],
        ["--serve", "--cycles", "1001"],
        ["--serve", "--interval", "0"],
        ["--once", "--token", "secret"],
        ["--once", "--host", "remote"],
        ["--once", "--path", "other"],
    ],
)
def test_explicit_mode_and_no_credentials_or_path_arguments(cli, args):
    with pytest.raises(SystemExit):
        cli.arguments(args)


def test_once_and_bounded_serve_options(cli):
    assert cli.arguments(["--once"]).once
    options = cli.arguments(["--serve", "--cycles", "2", "--interval", "3"])
    assert options.serve and options.cycles == 2 and options.interval == 3


def test_invalid_cli_arguments_do_not_echo_accidental_token(cli, capsys):
    with pytest.raises(SystemExit):
        cli.arguments(["--once", "--token", "private-token-value"])
    output = capsys.readouterr()
    assert "private-token" not in output.err + output.out
    assert "MATERIAL_WORKER_ARGUMENTS_INVALID" in output.err


async def test_disabled_returns_before_database_objects_lock_and_signal(cli):
    def forbidden(*args, **kwargs):
        pytest.fail("关闭模式不得初始化依赖")

    result = await cli.execute(
        cli.arguments(["--once"]),
        values_provider=lambda: {},
        data_sources=SimpleNamespace(initialize=forbidden),
        objects_factory=forbidden,
        lock_factory=forbidden,
        supervisor_factory=forbidden,
        service_runner=forbidden,
    )
    assert result["result"] == "DISABLED" and result["cleanup_complete"]


@pytest.mark.parametrize("cleanup_complete", [True, False])
async def test_enabled_uses_only_explicit_private_object_root_same_registry_and_safe_sessions(
    cli, tmp_path, cleanup_complete
):
    from test_material_scanner_owner import definition
    from test_material_scanner_owner_loader import values

    private = values(definition.__wrapped__(tmp_path))
    private["ORBIT_PYTHON_MATERIAL_OBJECT_ROOT"] = str(tmp_path)
    calls = []

    class Database:
        async def initialize(self, *, log_enabled):
            assert log_enabled is False
            calls.append("db-init")

        def session(self, *, log_sql):
            assert log_sql is False
            calls.append("session")
            return object()

        async def dispose_all(self):
            calls.append("dispose")

    @contextmanager
    def lock(path):
        assert path.name == "material-worker.lock" and path.parent.name == ".runtime"
        calls.append("lock")
        yield
        calls.append("unlock")

    def objects(path):
        assert path == tmp_path
        calls.append("objects")
        return object()

    def factory(**kwargs):
        assert kwargs["snapshot_provider"]().enabled
        kwargs["sessions"]()
        calls.append("supervisor")
        return object()

    async def run(supervisor, **kwargs):
        assert kwargs["mode"] == "once" and kwargs["cycles"] is None
        calls.append("run")
        return {
            "result": "IDLE" if cleanup_complete else "FAILED",
            "cleanup_complete": cleanup_complete,
        }

    result = await cli.execute(
        cli.arguments(["--once"]),
        values_provider=lambda: private,
        data_sources=Database(),
        objects_factory=objects,
        supervisor_factory=factory,
        service_runner=run,
        lock_factory=lock,
        install_signals=False,
    )
    assert result["result"] == ("IDLE" if cleanup_complete else "FAILED")
    assert calls == [
        "objects",
        "lock",
        "db-init",
        "session",
        "supervisor",
        "run",
        "unlock",
    ] + (["dispose"] if cleanup_complete else [])


def test_disabled_main_never_acquires_lock_or_runs_event_loop(cli, monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "initial_configuration", lambda: ({}, SimpleNamespace(enabled=False), None)
    )

    def forbidden(*args, **kwargs):
        pytest.fail("关闭模式不能获取进程锁或运行入口")

    monkeypatch.setattr(cli, "process_lock", forbidden)
    monkeypatch.setattr(cli.asyncio, "run", forbidden)
    assert cli.main(["--once"]) == 0
    assert "MATERIAL_WORKER_DISABLED" in capsys.readouterr().out


def test_main_holds_fixed_lock_through_entire_asyncio_run_and_preserves_failure_exit(
    cli, monkeypatch, capsys
):
    calls = []
    monkeypatch.setattr(
        cli, "initial_configuration", lambda: ({}, SimpleNamespace(enabled=True), None)
    )

    @contextmanager
    def lock():
        calls.append("lock")
        yield
        calls.append("unlock")

    async def execute(options, **kwargs):
        calls.append("execute")
        return {
            "result": "FAILED",
            "code": "MATERIAL_WORKER_CLEANUP_UNVERIFIED",
            "cleanup_complete": False,
        }

    monkeypatch.setattr(cli, "process_lock", lock)
    monkeypatch.setattr(cli, "execute", execute)
    assert cli.main(["--once"]) == 1
    assert calls == ["lock", "execute", "unlock"]
    assert "cleanup_complete" in capsys.readouterr().out


def test_main_does_not_echo_private_exception(cli, monkeypatch, capsys):
    def broken():
        raise RuntimeError("private-database-password")

    monkeypatch.setattr(cli, "initial_configuration", broken)
    assert cli.main(["--once"]) == 1
    output = capsys.readouterr().out
    assert "private" not in output and "MATERIAL_WORKER_FAILED" in output
