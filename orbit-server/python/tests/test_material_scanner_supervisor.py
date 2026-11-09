"""独立生命周期注入纯测；不运行真实进程、SQL、env或共享API。"""

import asyncio
from dataclasses import replace

import pytest

from orbit_api.errors import OrbitError
from orbit_api.material_scanner_owner import MaterialScannerOwner
from orbit_api.material_scanner_owner_loader import OwnerConfiguration, disabled_owner_configuration
from orbit_api.material_scanner_registry import MaterialScannerRegistry, ScannerProbeResult
from orbit_api.material_scanner_supervisor import MaterialScannerSupervisor


@pytest.fixture
def setup(tmp_path):
    from test_material_scanner_owner import FakeAdapter, definition

    current = [OwnerConfiguration(True, definition.__wrapped__(tmp_path), "a" * 64)]
    registry, events = MaterialScannerRegistry(), []
    entered, release = asyncio.Event(), asyncio.Event()

    async def audit(event):
        events.append(event["action"])

    async def health(scanner, deadline):
        private = MaterialScannerRegistry()
        return ScannerProbeResult(
            "READ_VERIFIED", "显式注入非真实扫描", private.publish(scanner, "纯测")
        )

    def owner_factory(registry, *, audit_sink):
        return MaterialScannerOwner(
            registry, audit_sink=audit_sink, adapter=FakeAdapter(registry), health=health
        )

    class Worker:
        def __init__(self, sessions, objects, *, registry):
            assert registry is setup_registry
            self.calls = 0

        async def run_once(self, limit):
            assert limit == 1
            self.calls += 1
            entered.set()
            await release.wait()
            return [{"state": "READY"}]

    setup_registry = registry
    supervisor = MaterialScannerSupervisor(
        registry=registry,
        sessions=lambda: None,
        objects=object(),
        snapshot_provider=lambda: current[0],
        owner_factory=owner_factory,
        worker_factory=Worker,
        audit_sink=audit,
        drain_seconds=1,
        cleanup_seconds=2,
    )
    return supervisor, current, events, entered, release


async def test_constructor_and_missing_provider_do_not_load_or_start():
    supervisor = MaterialScannerSupervisor(
        registry=MaterialScannerRegistry(), sessions=lambda: None, objects=None
    )
    assert supervisor.state == "NEW" and not supervisor.registry.candidates()
    assert await supervisor.start() is False and supervisor.state == "DISABLED"
    assert await supervisor.shutdown() and supervisor.state == "STOPPED"


async def test_start_audited_owner_and_same_registry_worker_then_stop(setup):
    supervisor, current, events, entered, release = setup
    assert await supervisor.start() and supervisor.state == "RUNNING"
    assert events == ["STARTING", "STARTED"] and len(supervisor.registry.candidates()) == 1
    release.set()
    assert await supervisor.run_once() == [{"state": "READY"}]
    assert await supervisor.monitor_once()
    assert await supervisor.shutdown() and supervisor.state == "STOPPED"
    assert events[-1] == "STOPPED" and not supervisor.registry.candidates()


async def test_repeated_start_is_rejected_without_second_spawn(setup):
    supervisor, *_ = setup
    await supervisor.start()
    with pytest.raises(OrbitError) as error:
        await supervisor.start()
    assert error.value.code == "SCANNER_SUPERVISOR_ALREADY_STARTED"
    await supervisor.shutdown()


async def test_concurrent_run_once_rejected_and_cancelled_caller_does_not_forget_inflight(setup):
    supervisor, current, events, entered, release = setup
    await supervisor.start()
    running = asyncio.create_task(supervisor.run_once())
    await entered.wait()
    with pytest.raises(OrbitError) as error:
        await supervisor.run_once()
    assert error.value.code == "SCANNER_SUPERVISOR_WORKER_BUSY"
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert supervisor._inflight is not None and not supervisor._inflight.done()
    release.set()
    assert await supervisor.shutdown()


async def test_shutdown_waits_for_inflight_and_stops_new_claims(setup):
    supervisor, current, events, entered, release = setup
    await supervisor.start()
    running = asyncio.create_task(supervisor.run_once())
    await entered.wait()
    closing = asyncio.create_task(supervisor.shutdown())
    await asyncio.sleep(0)
    assert not supervisor.accepting and not closing.done()
    release.set()
    assert await closing and await running == [{"state": "READY"}]


async def test_shutdown_timeout_keeps_inflight_and_cannot_claim_clean_exit(setup):
    supervisor, current, events, entered, release = setup
    await supervisor.start()
    running = asyncio.create_task(supervisor.run_once())
    await entered.wait()
    with pytest.raises(OrbitError) as error:
        await supervisor.shutdown()
    assert error.value.code == "SCANNER_SUPERVISOR_INFLIGHT_PENDING"
    assert supervisor.state == "FAILED" and not supervisor.registry.candidates()
    assert not supervisor._inflight.done()
    release.set()
    await running
    assert await supervisor.shutdown() is False


async def test_configuration_change_monitor_withdraws_stops_and_never_restarts(setup):
    supervisor, current, events, entered, release = setup
    await supervisor.start()
    current[0] = replace(current[0], sha256="b" * 64)
    assert await supervisor.monitor_once() is False
    assert supervisor.state == "FAILED" and not supervisor.accepting
    assert not supervisor.registry.candidates() and events[-1] == "STOPPED"
    with pytest.raises(OrbitError):
        await supervisor.run_once()
    current[0] = replace(current[0], sha256="a" * 64)
    assert await supervisor.monitor_once() is False
    assert await supervisor.shutdown() is False


async def test_disabled_configuration_before_claim_stops_without_running_worker(setup):
    supervisor, current, events, entered, release = setup
    await supervisor.start()
    current[0] = disabled_owner_configuration()
    with pytest.raises(OrbitError):
        await supervisor.run_once()
    assert not entered.is_set() and not supervisor.registry.candidates()
    await supervisor.shutdown()


async def test_other_api_registry_is_always_empty_despite_worker_owner_started(setup):
    supervisor, *_ = setup
    api_registry = MaterialScannerRegistry()
    await supervisor.start()
    assert supervisor.registry.candidates() and api_registry.candidates() == []
    await supervisor.shutdown()


async def test_cancelled_start_latches_failure_and_no_publication(setup):
    supervisor, *_ = setup
    entered = asyncio.Event()

    async def block(event):
        entered.set()
        await asyncio.Event().wait()

    supervisor.audit_sink = block
    task = asyncio.create_task(supervisor.start())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert supervisor.state == "FAILED" and not supervisor.registry.candidates()
    assert await supervisor.shutdown() is False


async def test_cancelled_shutdown_keeps_owner_stop_task_until_owned_cleanup_returns(setup):
    supervisor, current, events, entered, release = setup
    await supervisor.start()
    closing_entered, closing_release = asyncio.Event(), asyncio.Event()
    original = supervisor._owner.stop
    cancelled = []

    async def slow_stop():
        closing_entered.set()
        try:
            await closing_release.wait()
            return await original()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    supervisor._owner.stop = slow_stop
    closing = asyncio.create_task(supervisor.shutdown())
    await closing_entered.wait()
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert supervisor.state == "FAILED" and not supervisor.registry.candidates()
    assert supervisor._owner_stop_task is not None and not supervisor._owner_stop_task.done()
    closing_release.set()
    await supervisor._cleanup_task
    assert not cancelled and events[-1] == "STOPPED"
    assert await supervisor.shutdown() is False


async def test_worker_fault_withdraws_and_latches_failure(setup):
    supervisor, *_ = setup
    await supervisor.start()

    async def fail(**kwargs):
        raise RuntimeError("private-worker-data")

    supervisor._worker.run_once = fail
    with pytest.raises(OrbitError) as error:
        await supervisor.run_once()
    assert error.value.code == "SCANNER_SUPERVISOR_WORKER_FAILED"
    assert not supervisor.registry.candidates() and supervisor.state == "FAILED"
    assert "private" not in error.value.message
    await supervisor.shutdown()


async def test_persistent_started_failure_never_constructs_worker_or_publishes(setup):
    supervisor, *_ = setup

    async def audit(event):
        if event["action"] == "STARTED":
            raise OrbitError(503, "SCANNER_OWNER_AUDIT_UNAVAILABLE", "纯测SQL失败")

    supervisor.audit_sink = audit
    with pytest.raises(OrbitError) as error:
        await supervisor.start()
    assert error.value.code == "SCANNER_OWNER_AUDIT_UNAVAILABLE"
    assert supervisor._worker is None and not supervisor.registry.candidates()
    assert await supervisor.shutdown() is False


async def test_source_changes_during_start_close_owner_before_worker_constructed(setup):
    supervisor, current, events, entered, release = setup
    calls = []

    def source():
        calls.append(True)
        return current[0] if len(calls) == 1 else replace(current[0], sha256="b" * 64)

    supervisor.snapshot_provider = source
    with pytest.raises(OrbitError) as error:
        await supervisor.start()
    assert error.value.code == "SCANNER_OWNER_CONFIGURATION_CHANGED"
    assert supervisor._worker is None and not supervisor.registry.candidates()
    assert events == ["STARTING", "STARTED", "STOPPED"]
    await supervisor.shutdown()


async def test_owner_stop_timeout_retains_exact_task_and_never_reports_clean_exit(setup):
    supervisor, *_ = setup
    supervisor.cleanup_seconds = 1
    await supervisor.start()
    release = asyncio.Event()
    original = supervisor._owner.stop
    calls = []

    async def slow_stop():
        calls.append(True)
        await release.wait()
        return await original()

    supervisor._owner.stop = slow_stop
    with pytest.raises(OrbitError) as error:
        await supervisor.shutdown()
    assert error.value.code == "SCANNER_SUPERVISOR_CLEANUP_PENDING"
    retained = supervisor._owner_stop_task
    assert retained is not None and not retained.done() and not supervisor.registry.candidates()
    release.set()
    assert await supervisor.shutdown() is False
    assert retained.done() and len(calls) == 1 and supervisor.state == "FAILED"


async def test_runtime_expiry_stops_claims_without_renewal_or_registry_rebuild(setup):
    supervisor, *_ = setup
    await supervisor.start()
    expiry = supervisor._binding.profile.expires_at
    supervisor._owner.clock = lambda: expiry
    assert await supervisor.monitor_once() is False
    assert not supervisor.accepting and supervisor.state == "FAILED"
    assert not supervisor.registry.candidates()
    await supervisor.shutdown()


async def test_stop_audit_failure_is_latched_even_when_owned_process_has_closed(setup):
    supervisor, *_ = setup
    await supervisor.start()

    async def failing_audit(event):
        raise OrbitError(503, "SCANNER_OWNER_AUDIT_UNAVAILABLE", "注入审计不可用")

    supervisor._owner.audit_sink = failing_audit
    with pytest.raises(OrbitError):
        await supervisor.shutdown()
    assert not supervisor.registry.candidates() and supervisor.state == "FAILED"
    assert await supervisor.shutdown() is False


async def test_invalid_snapshot_never_constructs_owner_or_worker(setup):
    supervisor, *_ = setup
    supervisor.snapshot_provider = lambda: OwnerConfiguration(True, None, "not-sha")
    with pytest.raises(OrbitError):
        await supervisor.start()
    assert supervisor._owner is None and supervisor._worker is None
    assert supervisor.state == "FAILED"


@pytest.mark.parametrize("observer", ["run_once", "monitor_once"])
async def test_cancelled_waiter_late_worker_failure_is_latched_before_next_claim(setup, observer):
    supervisor, current, events, entered, release = setup
    await supervisor.start()
    calls = []

    async def late_failure(*, limit):
        assert limit == 1
        calls.append(True)
        entered.set()
        await release.wait()
        raise RuntimeError("late-private-worker-error")

    supervisor._worker.run_once = late_failure
    caller = asyncio.create_task(supervisor.run_once())
    await entered.wait()
    old_task = supervisor._inflight
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert not old_task.done()
    release.set()
    with pytest.raises(RuntimeError):
        await old_task
    if observer == "run_once":
        with pytest.raises(OrbitError) as error:
            await supervisor.run_once()
        assert error.value.code == "SCANNER_SUPERVISOR_WORKER_FAILED"
        assert "private" not in error.value.message
    else:
        assert await supervisor.monitor_once() is False
    assert supervisor._inflight is old_task and len(calls) == 1
    assert not supervisor.accepting and supervisor.state == "FAILED"
    assert supervisor.last_error_code == "SCANNER_SUPERVISOR_WORKER_FAILED"
    assert not supervisor.registry.candidates() and events[-1] == "STOPPED"
    with pytest.raises(OrbitError):
        await supervisor.run_once()
    assert len(calls) == 1 and await supervisor.shutdown() is False
