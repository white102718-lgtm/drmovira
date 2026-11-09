"""显式任务驱动纯测：无SQL/进程，验证scan期间独立monitor和停止后单任务排空。"""

import asyncio

import pytest

from orbit_api.material_worker_service import run_material_worker_service


class Supervisor:
    def __init__(self, rows=None):
        self.rows = [] if rows is None else rows
        self.state, self.accepting, self.calls, self.monitors = "NEW", False, 0, 0
        self._owner = self._inflight = self._owner_stop_task = self._cleanup_task = None
        self.source_seconds, self.drain_seconds, self.cleanup_seconds = 1, 1, 1
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.release.set()
        self.monitor_action = None

    async def start(self):
        self.state, self.accepting = "RUNNING", True
        return True

    async def run_once(self):
        assert self.accepting
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return self.rows

    async def monitor_once(self):
        self.monitors += 1
        if self.monitor_action:
            return await self.monitor_action()
        return True

    async def shutdown(self):
        self.accepting = False
        if self.calls:
            await self.release.wait()
        self.state = "STOPPED" if self.state != "FAILED" else "FAILED"
        return self.state == "STOPPED"


async def test_once_idle_has_no_implicit_second_claim():
    supervisor = Supervisor()
    result = await run_material_worker_service(supervisor, mode="once", stop=asyncio.Event())
    assert result == {
        "result": "IDLE",
        "code": "MATERIAL_WORKER_IDLE",
        "cycles": 1,
        "processed": 0,
        "ready": 0,
        "failed": 0,
        "cleanup_complete": True,
    }
    assert supervisor.calls == 1 and supervisor.state == "STOPPED"


async def test_once_ready_counts_only_safe_totals():
    supervisor = Supervisor([{"asset_id": "do-not-log", "state": "READY"}])
    report = []
    result = await run_material_worker_service(
        supervisor, mode="once", stop=asyncio.Event(), report=report.append
    )
    assert result["ready"] == 1 and result["processed"] == 1 and result["cleanup_complete"]
    assert "do-not-log" not in str(result) + str(report)


async def test_monitor_continues_during_one_slow_scan_then_cleanup():
    supervisor = Supervisor([{"state": "READY"}])
    supervisor.release.clear()

    async def monitor():
        assert supervisor.entered.is_set()
        if supervisor.monitors >= 2:
            supervisor.release.set()
        return True

    supervisor.monitor_action = monitor
    result = await run_material_worker_service(
        supervisor, mode="once", stop=asyncio.Event(), monitor_interval=0.01
    )
    assert supervisor.monitors >= 2 and supervisor.calls == 1 and result["ready"] == 1
    assert result["cleanup_complete"]


async def test_stop_signal_during_processing_does_not_claim_next_and_counts_drained_result():
    supervisor = Supervisor([{"state": "READY"}])
    supervisor.release.clear()
    stop = asyncio.Event()
    task = asyncio.create_task(run_material_worker_service(supervisor, mode="serve", stop=stop))
    await supervisor.entered.wait()
    stop.set()
    await asyncio.sleep(0)
    supervisor.release.set()
    result = await task
    assert supervisor.calls == 1 and result["result"] == "STOPPED" and result["ready"] == 1
    assert not supervisor.accepting and result["cleanup_complete"]


async def test_monitor_failure_stops_and_never_tries_another_cycle():
    supervisor = Supervisor([{"state": "READY"}])
    supervisor.release.clear()

    async def monitor():
        supervisor.state = "FAILED"
        supervisor.release.set()
        return False

    supervisor.monitor_action = monitor
    result = await run_material_worker_service(
        supervisor, mode="serve", stop=asyncio.Event(), monitor_interval=0.01
    )
    assert result["result"] == "FAILED" and result["code"] == "MATERIAL_WORKER_MONITOR_FAILED"
    assert supervisor.calls == 1


async def test_once_handled_failure_is_completed_operation_with_failed_count():
    supervisor = Supervisor([{"state": "PROCESSING_FAILED"}])
    result = await run_material_worker_service(supervisor, mode="once", stop=asyncio.Event())
    assert result["result"] == "COMPLETED" and result["failed"] == 1 and result["ready"] == 0
    assert supervisor.calls == 1 and result["cleanup_complete"]


async def test_serve_quarantined_then_ready_does_not_retry_or_stop_on_historical_failed_count():
    supervisor = Supervisor()
    identities = []
    queue = [
        {"asset_id": "bad-object", "state": "QUARANTINED"},
        {"asset_id": "different-good-object", "state": "READY"},
    ]

    async def next_item():
        supervisor.calls += 1
        row = queue.pop(0)
        identities.append(row["asset_id"])
        return [row]

    supervisor.run_once = next_item
    result = await run_material_worker_service(
        supervisor, mode="serve", stop=asyncio.Event(), cycles=2
    )
    assert result["result"] == "COMPLETED" and result["processed"] == 2
    assert result["ready"] == 1 and result["failed"] == 1 and result["cycles"] == 2
    assert identities == ["bad-object", "different-good-object"] and supervisor.calls == 2
    assert result["cleanup_complete"]


@pytest.mark.parametrize("state", ["UPLOAD_FAILED", "PROCESSING_FAILED", "STALE"])
async def test_other_handled_terminal_states_complete_without_ready_promotion(state):
    supervisor = Supervisor([{"state": state}])
    result = await run_material_worker_service(supervisor, mode="once", stop=asyncio.Event())
    assert result["result"] == "COMPLETED" and result["ready"] == 0 and result["failed"] == 1


@pytest.mark.parametrize(
    "rows",
    [
        [{}],
        [{"state": "SCANNING"}],
        [{"state": ["READY"]}],
        [{"state": "READY"}, {"state": "READY"}],
        None,
    ],
)
async def test_unknown_result_protocol_stops_service_nonzero_semantics(rows):
    supervisor = Supervisor()
    supervisor.rows = rows
    result = await run_material_worker_service(supervisor, mode="serve", stop=asyncio.Event())
    assert result["result"] == "FAILED" and supervisor.calls == 1


async def test_unhandled_worker_exception_stops_service_without_retry_or_secret_log():
    supervisor = Supervisor()

    async def broken():
        supervisor.calls += 1
        raise RuntimeError("private-worker-detail")

    supervisor.run_once = broken
    result = await run_material_worker_service(supervisor, mode="serve", stop=asyncio.Event())
    assert result["result"] == "FAILED" and supervisor.calls == 1
    assert "private" not in str(result)


async def test_pre_set_stop_never_starts_owner_or_claims():
    stop = asyncio.Event()
    stop.set()
    supervisor = Supervisor()
    result = await run_material_worker_service(supervisor, mode="once", stop=stop)
    assert result["result"] == "STOPPED" and supervisor.calls == 0


async def test_serve_cycles_are_bounded_without_parallel_claims():
    supervisor = Supervisor()
    result = await run_material_worker_service(
        supervisor, mode="serve", stop=asyncio.Event(), cycles=2, interval=1
    )
    assert result["cycles"] == 2 and supervisor.calls == 2


@pytest.mark.parametrize(
    "options",
    [
        {"mode": "automatic"},
        {"interval": 0},
        {"interval": True},
        {"cycles": 0},
        {"cycles": 1001},
        {"mode": "once", "cycles": 1},
        {"monitor_interval": 0},
    ],
)
async def test_invalid_service_budgets_never_start(options):
    supervisor = Supervisor()
    with pytest.raises(ValueError):
        await run_material_worker_service(
            supervisor, stop=asyncio.Event(), **({"mode": "serve"} | options)
        )
    assert supervisor.state == "NEW"


async def test_shutdown_failure_retains_nonzero_cleanup_status():
    supervisor = Supervisor()

    async def failure():
        raise RuntimeError("secret-db-detail")

    supervisor.shutdown = failure
    result = await run_material_worker_service(supervisor, mode="once", stop=asyncio.Event())
    assert result["result"] == "FAILED" and not result["cleanup_complete"]
    assert result["code"] == "MATERIAL_WORKER_CLEANUP_UNVERIFIED"
    assert "secret" not in str(result) and supervisor.service_retained_tasks["shutdown"].done()


async def test_external_service_cancellation_drains_then_propagates_without_next_claim():
    supervisor = Supervisor([{"state": "READY"}])
    supervisor.release.clear()
    task = asyncio.create_task(
        run_material_worker_service(supervisor, mode="serve", stop=asyncio.Event())
    )
    await supervisor.entered.wait()
    task.cancel()
    supervisor.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert supervisor.calls == 1 and not supervisor.accepting and supervisor.state == "STOPPED"
