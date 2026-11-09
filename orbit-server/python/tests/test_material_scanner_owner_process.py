"""原生进程适配器的注入纯测；所有Win32/Popen/socket均替身，绝不启动真实进程。"""

import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from orbit_api.errors import OrbitError
from orbit_api.material_scanner_owner_process import WindowsOwnerProcessAdapter


def adapter_fixture():
    events, arguments = [], []

    class Kernel:
        def create(self):
            events.append("job-create-kill-on-close")
            return 77

        def assign(self, job, handle):
            assert (job, handle) == (77, 88)
            events.append("assign")

        def resume(self, handle):
            assert handle == 88
            events.append("resume")

        def terminate_unassigned(self, handle):
            assert handle == 88
            events.append("terminate-original-handle")

        def close(self, job):
            assert job == 77
            events.append("close-original-job")

    process = SimpleNamespace(pid=123, _handle=88)
    process.poll = lambda: None

    def wait(*, timeout):
        assert 0 < timeout <= 5
        events.append("wait-original-handle")
        return 0

    process.wait = wait

    def popen(args, **kwargs):
        events.append("popen-suspended")
        arguments.append((args, kwargs))
        return process

    kernel = Kernel()
    adapter = WindowsOwnerProcessAdapter(
        kernel=kernel, popen=popen, identity=lambda pid: (pid, 456)
    )
    return adapter, kernel, process, events, arguments


def spawn(adapter):
    return adapter.spawn(
        Path("C:/pinned/clamd.exe"), Path("C:/own/c.conf"), Path("C:/own"), time.monotonic() + 5
    )


def test_job_assignment_precedes_resume_and_argv_streams_are_bounded():
    adapter, _, _, events, arguments = adapter_fixture()
    owned = spawn(adapter)
    assert events == ["job-create-kill-on-close", "popen-suspended", "assign", "resume"]
    args, options = arguments[0]
    assert args == [str(Path("C:/pinned/clamd.exe")), "--config-file=" + str(Path("C:/own/c.conf"))]
    assert options == {
        "cwd": str(Path("C:/own")),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "shell": False,
        "creationflags": 0x08000004,
    }
    assert (owned.pid, owned.created_at_us, owned.job) == (123, 456, 77)


def test_missing_job_creation_never_calls_popen():
    adapter, kernel, _, events, _ = adapter_fixture()

    def unavailable():
        raise OrbitError(503, "SCANNER_OWNER_JOB_UNAVAILABLE", "纯测")

    kernel.create = unavailable
    with pytest.raises(OrbitError):
        spawn(adapter)
    assert not events


@pytest.mark.parametrize("failure", ["assign", "resume"])
def test_partial_start_failure_targets_only_retained_original_handle(failure):
    adapter, kernel, _, events, _ = adapter_fixture()

    def fail(*args):
        raise OrbitError(503, "SCANNER_OWNER_JOB_UNAVAILABLE", "纯测")

    setattr(kernel, failure, fail)
    with pytest.raises(OrbitError):
        spawn(adapter)
    assert events[-3:] == [
        "terminate-original-handle",
        "close-original-job",
        "wait-original-handle",
    ]
    assert "resume" not in events


def test_birth_mismatch_still_closes_only_own_job_and_never_numeric_pid_terminate():
    adapter, _, _, events, _ = adapter_fixture()
    owned = spawn(adapter)
    adapter._identity = lambda pid: (pid, 789)
    assert adapter.alive(owned) is False
    with pytest.raises(OrbitError) as problem:
        adapter.close_owned(owned, (123, 456), time.monotonic() + 5)
    assert problem.value.code == "SCANNER_OWNER_IDENTITY_CHANGED"
    assert events[-2:] == ["close-original-job", "wait-original-handle"] and owned.closed
    assert "terminate-original-handle" not in events
    adapter.close_owned(owned, (123, 456), time.monotonic() + 5)
    assert events.count("close-original-job") == 1


@pytest.mark.parametrize("exception", [psutil.NoSuchProcess(123), psutil.AccessDenied(123)])
def test_unreadable_process_identity_fails_closed_without_external_pid_action(exception):
    adapter, _, _, events, _ = adapter_fixture()
    owned = spawn(adapter)

    def absent(pid):
        raise exception

    adapter._identity = absent
    assert adapter.alive(owned) is False
    with pytest.raises(OrbitError):
        adapter.close_owned(owned, (123, 456), time.monotonic() + 5)
    assert events[-2:] == ["close-original-job", "wait-original-handle"]


def test_close_wait_timeout_is_failure_after_registry_owner_can_withdraw():
    adapter, _, process, events, _ = adapter_fixture()
    owned = spawn(adapter)

    def expired(*, timeout):
        raise subprocess.TimeoutExpired("pure-fixture", timeout)

    process.wait = expired
    with pytest.raises(OrbitError) as problem:
        adapter.close_owned(owned, (123, 456), time.monotonic() + 5)
    assert problem.value.code == "SCANNER_OWNER_CLOSE_FAILED"
    assert events[-1] == "close-original-job" and owned.job_closed and not owned.closed
    process.wait = lambda **kwargs: 0
    adapter.close_owned(owned, (123, 456), time.monotonic() + 5)
    assert owned.closed and events.count("close-original-job") == 1


@pytest.mark.parametrize("busy", [False, True])
def test_port_preflight_only_binds_loopback_and_always_closes_injected_socket(busy):
    events = []

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("socket-close")

        def settimeout(self, value):
            assert 0 < value <= 5

        def setsockopt(self, *args):
            pass

        def bind(self, address):
            assert address == ("127.0.0.1", 19311)
            if busy:
                raise OSError("pure injected collision")

    adapter = WindowsOwnerProcessAdapter(socket_factory=lambda *args: Socket())
    assert adapter.port_available(19311, time.monotonic() + 5) is not busy
    assert events == ["socket-close"]


def test_expired_start_budget_never_calls_kernel_or_popen():
    adapter, _, _, events, _ = adapter_fixture()
    with pytest.raises(OrbitError) as problem:
        adapter.spawn(
            Path("C:/pinned.exe"), Path("C:/own.conf"), Path("C:/own"), time.monotonic() - 1
        )
    assert problem.value.code == "SCANNER_OWNER_DEADLINE" and not events


def test_partial_start_unknown_cleanup_is_retained_and_blocks_another_spawn():
    adapter, kernel, _, events, _ = adapter_fixture()
    original_close = kernel.close

    def assign_failed(*args):
        raise OrbitError(503, "SCANNER_OWNER_JOB_UNAVAILABLE", "纯测")

    def close_failed(*args):
        raise OrbitError(503, "SCANNER_OWNER_CLOSE_FAILED", "纯测")

    kernel.assign, kernel.close = assign_failed, close_failed
    with pytest.raises(OrbitError):
        spawn(adapter)
    assert len(adapter._failed) == 1
    with pytest.raises(OrbitError) as error:
        spawn(adapter)
    assert error.value.code == "SCANNER_OWNER_CLEANUP_PENDING"
    assert events.count("popen-suspended") == 1
    kernel.close = original_close
    adapter.cleanup_failed(time.monotonic() + 5)
    assert not adapter._failed and events[-1] == "wait-original-handle"
