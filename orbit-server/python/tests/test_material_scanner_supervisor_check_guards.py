"""独立lifecycle工具护栏；不运行入口、真实进程或MySQL。"""

import asyncio
import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest


@pytest.fixture
def checks():
    path = Path(__file__).resolve().parents[2] / "tools/material_scanner_supervisor_checks.py"
    spec = importlib.util.spec_from_file_location("supervisor_checks_guards", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def root(tmp_path, name):
    base = tmp_path / "integration-objects"
    base.mkdir()
    target = base / name / "materials"
    target.mkdir(parents=True)
    return base, target


@pytest.mark.parametrize(
    "name", ["run-eight123", "run-" + "a" * 31, "run-" + "A" * 32, "run-" + "a" * 33]
)
def test_existing_legacy_or_non_uuid_bundle_is_not_a_valid_new_supervisor_root(
    checks, tmp_path, name
):
    base, target = root(tmp_path, name)
    with pytest.raises(ValueError):
        checks.validate_supervisor_object_root(target, base=base)
    assert target.is_dir()


def test_only_existing_empty_exact_uuid_material_root_is_accepted_without_mutation(
    checks, tmp_path
):
    base, target = root(tmp_path, "run-" + "a" * 32)
    assert checks.validate_supervisor_object_root(target, base=base) == target
    assert list(target.iterdir()) == []
    with pytest.raises(ValueError):
        checks.validate_supervisor_object_root(target, base=tmp_path)


def test_nonempty_object_root_rejected_and_sentinel_preserved(checks, tmp_path):
    base, target = root(tmp_path, "run-" + "b" * 32)
    sentinel = target / "existing-object"
    sentinel.write_bytes(b"preserve")
    with pytest.raises(ValueError):
        checks.validate_supervisor_object_root(target, base=base)
    assert sentinel.read_bytes() == b"preserve"


def test_wrong_leaf_or_relative_path_cannot_enter_existing_objects(checks, tmp_path):
    base, target = root(tmp_path, "run-" + "a" * 32)
    other = target.parent / "accounts"
    other.mkdir()
    for value in (other, Path("relative/materials")):
        with pytest.raises(ValueError):
            checks.validate_supervisor_object_root(value, base=base)


def test_fixture_loader_values_include_only_owner_namespace_and_complete_dto(checks, tmp_path):
    from test_material_scanner_owner import definition

    from orbit_api.material_scanner_owner_definition import OWNER_DEFINITIONS_KEY
    from orbit_api.material_scanner_owner_loader import OWNER_ENABLED_KEY, load_owner_configuration

    original = definition.__wrapped__(tmp_path)
    values = checks.supervisor_fixture_values(original)
    assert set(values) == {OWNER_ENABLED_KEY, OWNER_DEFINITIONS_KEY}
    assert values[OWNER_ENABLED_KEY] == "true"
    loaded = load_owner_configuration(lambda: values)
    assert loaded.definition == replace(
        original, database_files=tuple(sorted(original.database_files))
    )


def test_import_does_not_start_process_create_object_or_connect_database(monkeypatch):
    import subprocess

    import psutil
    import sqlalchemy.ext.asyncio

    def forbidden(*args, **kwargs):
        pytest.fail("工具导入不得有运行副作用")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(psutil, "Process", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr(sqlalchemy.ext.asyncio, "create_async_engine", forbidden)
    path = Path(__file__).resolve().parents[2] / "tools/material_scanner_supervisor_checks.py"
    spec = importlib.util.spec_from_file_location("supervisor_import_only", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.MATERIAL_SCANNER_SUPERVISOR_CASES) == 5


def test_fixed_object_base_matches_backend_runner_root(checks):
    backend = Path(__file__).resolve().parents[2]
    assert checks.OBJECT_BASE == backend / ".runtime/integration-objects"


def runtime_verified():
    return {
        "owned_births_exited": True,
        "owned_port_released": True,
        "protected_process_unchanged": True,
    }


async def test_cleanup_without_started_supervisor_still_requires_runtime_verification(checks):
    result = await checks.confirm_supervisor_cleanup(None, runtime_verified, budget_seconds=0.1)
    assert result["cleanup_complete"] and result["pending_roles"] == []


async def test_exact_shutdown_task_cancel_preserves_then_waits_for_native_cleanup_task(checks):
    from types import SimpleNamespace

    release = asyncio.Event()
    seen = []

    class Supervisor:
        _inflight = _owner_stop_task = _cleanup_task = None
        _owner = SimpleNamespace(_owned=None, _unclosed=[], adapter=SimpleNamespace(_failed=[]))

        async def shutdown(self):
            seen.append(asyncio.current_task())
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:

                async def actual_cleanup():
                    await release.wait()

                self._cleanup_task = asyncio.create_task(actual_cleanup())
                raise

    supervisor = Supervisor()

    async def complete():
        await asyncio.sleep(0.06)
        release.set()

    releaser = asyncio.create_task(complete())
    result = await checks.confirm_supervisor_cleanup(
        supervisor, runtime_verified, budget_seconds=0.12
    )
    await releaser
    assert len(seen) == 1 and seen[0].done() and seen[0].cancelled()
    assert supervisor._cleanup_task.done() and result["cleanup_complete"]


async def test_cleanup_uncertain_retains_precise_task_references_and_never_verifies(checks):
    from types import SimpleNamespace

    release = asyncio.Event()

    class Supervisor:
        _inflight = _owner_stop_task = _cleanup_task = None
        _owner = SimpleNamespace(_owned=None, _unclosed=[], adapter=SimpleNamespace(_failed=[]))

        async def shutdown(self):
            try:
                await release.wait()
            except asyncio.CancelledError:
                self._cleanup_task = asyncio.create_task(release.wait())
                raise

    supervisor = Supervisor()
    try:
        with pytest.raises(checks.SupervisorCleanupUnverified) as error:
            await checks.confirm_supervisor_cleanup(
                supervisor, runtime_verified, budget_seconds=0.06
            )
        problem = error.value
        assert not problem.safe_metrics["cleanup_complete"]
        assert problem.retained_tasks["supervisor_cleanup"] is supervisor._cleanup_task
        assert problem.retained_tasks["shutdown"].cancelled()
        assert problem in checks.UNRESOLVED_CLEANUPS
        assert problem.safe_metrics["pending_roles"] == ["supervisor_cleanup"]
    finally:
        release.set()
        if supervisor._cleanup_task is not None:
            await supervisor._cleanup_task


@pytest.mark.parametrize(
    "failed_field", ["owned_births_exited", "owned_port_released", "protected_process_unchanged"]
)
async def test_any_runtime_cleanup_failure_blocks_cleanup_complete(checks, failed_field):
    state = runtime_verified()
    state[failed_field] = False
    with pytest.raises(checks.SupervisorCleanupUnverified) as error:
        await checks.confirm_supervisor_cleanup(None, lambda: state, budget_seconds=0.1)
    assert error.value.safe_metrics["cleanup_complete"] is False


async def test_completed_failed_cleanup_task_does_not_become_verified(checks):
    from types import SimpleNamespace

    async def fail():
        raise RuntimeError("private-database-or-path")

    failed = asyncio.create_task(fail())
    try:
        await failed
    except RuntimeError:
        pass

    class Supervisor:
        _inflight = _owner_stop_task = None
        _cleanup_task = failed
        _owner = SimpleNamespace(_owned=None, _unclosed=[], adapter=SimpleNamespace(_failed=[]))

        async def shutdown(self):
            return False

    with pytest.raises(checks.SupervisorCleanupUnverified) as error:
        await checks.confirm_supervisor_cleanup(Supervisor(), runtime_verified, budget_seconds=0.1)
    assert error.value.safe_metrics["failed_roles"] == ["supervisor_cleanup"]
    assert "private" not in str(error.value)


async def test_cancelled_inflight_task_is_not_proof_that_its_thread_has_finished(checks):
    from types import SimpleNamespace

    task = asyncio.create_task(asyncio.Event().wait())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    class Supervisor:
        _inflight = task
        _owner_stop_task = _cleanup_task = None
        _owner = SimpleNamespace(_owned=None, _unclosed=[], adapter=SimpleNamespace(_failed=[]))

        async def shutdown(self):
            return False

    with pytest.raises(checks.SupervisorCleanupUnverified) as error:
        await checks.confirm_supervisor_cleanup(Supervisor(), runtime_verified, budget_seconds=0.1)
    assert error.value.safe_metrics["failed_roles"] == ["inflight"]
