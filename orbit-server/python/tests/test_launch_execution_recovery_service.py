"""独立恢复调度协议纯测；不初始化DB、不启动正式服务。"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_launch_execution_lease_contract import NOW
from test_launch_execution_recovery_scanner import Provider, grant

import orbit_api.launch_execution_recovery_service as module
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_recovery_scanner import RecoveryScanReport
from orbit_api.launch_execution_recovery_service import ExecutionRecoveryService


def result(**changes):
    return replace(RecoveryScanReport(1, 1, 1, 1, 0, 0, 0, 0, False, False), **changes)


class Scanner:
    def __init__(self, provider, hook=None):
        self.provider, self.hook = provider, hook
        self.calls = 0
        self.stopped = False

    async def scan_once(self, **kwargs):
        self.calls += 1
        if self.hook:
            return await self.hook(self)
        return result()

    def request_stop(self):
        self.stopped = True


def service(hook=None, provider=None):
    scanners = []

    def factory(fixed):
        scanners.append(Scanner(fixed, hook))
        return scanners[-1]

    return ExecutionRecoveryService(provider or Provider(), factory, clock=lambda: NOW), scanners


@pytest.mark.asyncio
async def test_default_rejects_before_factory_or_tasks():
    factory = Mock()
    value = ExecutionRecoveryService(scanner_factory=factory)
    before = asyncio.all_tasks()
    with pytest.raises(OrbitError, match="维护主体") as caught:
        await value.run(mode="once", stop=asyncio.Event())
    assert caught.value.status == 503
    factory.assert_not_called()
    assert asyncio.all_tasks() == before
    assert value.state == "FAILED"


@pytest.mark.asyncio
async def test_once_and_no_restart():
    value, scanners = service()
    records = []
    outcome = await value.run(mode="once", stop=asyncio.Event(), report=records.append)
    assert outcome == {
        "result": "COMPLETED",
        "cycles": 1,
        "recovered": 1,
        "blocked": 0,
        "stale": 0,
        "raw_rows": 1,
        "cleanup_complete": True,
    }
    assert value.state == "STOPPED" and scanners[0].stopped
    assert records[0]["code"] == "RECOVERY_SERVICE_CYCLE"
    with pytest.raises(OrbitError) as caught:
        await value.run(mode="once", stop=asyncio.Event())
    assert caught.value.status == 409


@pytest.mark.asyncio
async def test_initial_stop_creates_no_scanner():
    value, scanners = service()
    stop = asyncio.Event()
    stop.set()
    assert (await value.run(mode="serve", stop=stop))["cycles"] == 0
    assert scanners == [] and value.state == "STOPPED"


@pytest.mark.asyncio
async def test_budget_cycles_serial_and_fixed_capture():
    active = 0

    async def hook(scanner):
        nonlocal active
        active += 1
        assert active == 1
        assert await scanner.provider.capture() == grant()
        await asyncio.sleep(0)
        active -= 1
        return result(budget_exhausted=True)

    provider = Provider()
    value, scanners = service(hook, provider)
    outcome = await value.run(mode="serve", stop=asyncio.Event(), cycles=2)
    assert outcome["cycles"] == scanners[0].calls == 2
    assert provider.calls.count("capture") == 1


@pytest.mark.asyncio
async def test_authorization_changes_stop_before_factory():
    provider = Provider()
    provider.hook = lambda original: replace(original, revision=2)
    value, scanners = service(provider=provider)
    with pytest.raises(OrbitError) as caught:
        await value.run(mode="once", stop=asyncio.Event())
    assert caught.value.code == "RECOVERY_SERVICE_AUTHORITY_CHANGED"
    assert scanners == [] and value.state == "FAILED"


@pytest.mark.asyncio
async def test_stop_interrupts_normal_and_blocked_wait():
    for blocked in (0, 1):
        stop = asyncio.Event()
        ran = asyncio.Event()

        async def hook(scanner, ran=ran, blocked=blocked):
            ran.set()
            return result(blocked=blocked)

        value, scanners = service(hook)
        task = asyncio.create_task(value.run(mode="serve", stop=stop, interval_seconds=300))
        await ran.wait()
        await asyncio.sleep(0)
        stop.set()
        outcome = await asyncio.wait_for(task, 0.2)
        assert outcome["result"] == "STOPPED"
        assert scanners[0].calls == 1 and value.state == "STOPPED"


@pytest.mark.asyncio
async def test_stop_drains_inflight_and_rejects_duplicate():
    started, release, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def hook(scanner):
        started.set()
        await release.wait()
        return result()

    value, scanners = service(hook)
    task = asyncio.create_task(value.run(mode="serve", stop=stop))
    await started.wait()
    with pytest.raises(OrbitError) as caught:
        await value.run(mode="once", stop=asyncio.Event())
    assert caught.value.status == 409
    stop.set()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    await task
    assert scanners[0].calls == 1 and value.active_task.done()


@pytest.mark.asyncio
async def test_late_failure_during_drain_is_not_hidden():
    started, release, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def hook(scanner):
        started.set()
        await release.wait()
        raise RuntimeError("pure late failure")

    value, _ = service(hook)
    task = asyncio.create_task(value.run(mode="serve", stop=stop))
    await started.wait()
    stop.set()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(RuntimeError):
        await task
    assert value.state == "FAILED"


@pytest.mark.asyncio
async def test_cancel_caller_waits_for_inflight_and_propagates():
    started, release = asyncio.Event(), asyncio.Event()

    async def hook(scanner):
        started.set()
        await release.wait()
        return result()

    value, _ = service(hook)
    task = asyncio.create_task(value.run(mode="serve", stop=asyncio.Event()))
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert value.state == "FAILED" and value.active_task.done()


@pytest.mark.asyncio
async def test_drain_timeout_cancels_and_awaits_exact_task():
    started, cancelled, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def hook(scanner):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    value, _ = service(hook)
    before = asyncio.all_tasks()
    task = asyncio.create_task(value.run(mode="serve", stop=stop, drain_seconds=0.001))
    await started.wait()
    stop.set()
    await task
    assert cancelled.is_set() and value.active_task.cancelled()
    assert asyncio.all_tasks() == before


@pytest.mark.asyncio
async def test_backoff_caps_resets_and_budget_never_busy_loops(monkeypatch):
    delays = []
    native_timeout = asyncio.timeout

    @asynccontextmanager
    async def timeout(seconds):
        if seconds != 5:
            delays.append(seconds)
        async with native_timeout(5 if seconds == 5 else 0.001):
            yield

    monkeypatch.setattr(module.asyncio, "timeout", timeout)

    async def hook(scanner):
        return result(blocked=1 if scanner.calls <= 3 else 0, budget_exhausted=scanner.calls == 4)

    value, _ = service(hook)
    outcome = await value.run(mode="serve", stop=asyncio.Event(), cycles=6, interval_seconds=100)
    assert outcome["cycles"] == 6 and outcome["blocked"] == 3
    assert delays == [200, 300, 300, 0.1, 100]


@pytest.mark.asyncio
async def test_cleanup_uncertain_retains_exact_task(monkeypatch):
    started, cancelled, release, stop = (asyncio.Event() for _ in range(4))
    native_wait = asyncio.wait

    async def wait(tasks, **kwargs):
        if kwargs.get("timeout") == 5:
            await cancelled.wait()
            return set(), tasks
        return await native_wait(tasks, **kwargs)

    monkeypatch.setattr(module.asyncio, "wait", wait)

    async def hook(scanner):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            await release.wait()  # 明确的pure不合作任务，不假装已退出。
        return result()

    value, _ = service(hook)
    task = asyncio.create_task(value.run(mode="serve", stop=stop, drain_seconds=0.001))
    await started.wait()
    stop.set()
    try:
        with pytest.raises(OrbitError) as caught:
            await task
        assert caught.value.code == "RECOVERY_SERVICE_CLEANUP_UNVERIFIED"
        assert value.state == "FAILED" and value.retained_tasks == (value.active_task,)
    finally:
        release.set()
        await value.active_task


@pytest.mark.asyncio
async def test_repeated_cancellation_retains_inflight():
    started, release = asyncio.Event(), asyncio.Event()

    async def hook(scanner):
        started.set()
        await release.wait()
        return result()

    value, _ = service(hook)
    task = asyncio.create_task(value.run(mode="serve", stop=asyncio.Event()))
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
        assert value.state == "FAILED" and value.retained_tasks == (value.active_task,)
    finally:
        release.set()
        await value.active_task


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RuntimeError("pure DB failure"), OrbitError(503, "SOURCE_REVOKED", "pure")]
)
async def test_errors_never_retry(error):
    async def hook(scanner):
        raise error

    value, scanners = service(hook)
    with pytest.raises(type(error)):
        await value.run(mode="serve", stop=asyncio.Event())
    assert scanners[0].calls == 1 and value.state == "FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "options",
    [
        {"interval_seconds": 0.9},
        {"interval_seconds": 301},
        {"interval_seconds": True},
        {"budget_interval_seconds": 0.09},
        {"drain_seconds": 5.1},
        {"drain_seconds": float("nan")},
        {"cycles": 0},
        {"cycles": True},
        {"max_candidates": True},
        {"max_raw_rows": 10001},
        {"time_budget_seconds": 61},
    ],
)
async def test_bad_options_no_factory(options):
    value, scanners = service()
    with pytest.raises(ValueError):
        await value.run(mode="serve", stop=asyncio.Event(), **options)
    assert value.state == "NEW" and scanners == []
