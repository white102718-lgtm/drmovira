"""调度生命周期单测；不以测试替身证明真实投递或数据库验收。"""

import asyncio

import pytest

from orbit_api.invitation_job import run_job


class Worker:
    def __init__(self, stop=None):
        self.events = []
        self.stop = stop

    async def recover_interrupted(self, limit):
        self.events.append(("recover", limit))
        return 2

    async def run_once(self, limit):
        self.events.append(("send", limit))
        if self.stop is not None:
            self.stop.set()
        return {"claimed": 1, "accepted": 0, "failed": 0, "unknown": 1}


async def test_one_cycle_recovers_before_bounded_single_claims():
    worker = Worker()
    result = await run_job(worker, send=True, limit=2, stop=asyncio.Event())
    assert worker.events == [("recover", 2), ("send", 1), ("send", 1)]
    assert result == {
        "recovered_unknown": 2,
        "claimed": 2,
        "accepted": 0,
        "failed": 0,
        "unknown": 2,
    }


async def test_recovery_never_sends():
    worker = Worker()
    assert await run_job(worker, send=False, limit=3, stop=asyncio.Event()) == {
        "recovered_unknown": 2
    }
    assert worker.events == [("recover", 3)]


async def test_stop_during_one_delivery_never_starts_next():
    stop = asyncio.Event()
    worker = Worker(stop)
    result = await run_job(worker, send=True, limit=100, stop=stop, cycles=None)
    assert result["claimed"] == 1 and worker.events == [("recover", 100), ("send", 1)]


async def test_pre_stopped_job_has_no_database_or_network_calls():
    stop = asyncio.Event()
    stop.set()
    worker = Worker()
    assert await run_job(worker, send=True, limit=1, stop=stop) == {
        "result": "STOPPED",
        "cycles": 0,
    }
    assert worker.events == []


async def test_idle_wait_is_interruptible():
    stop = asyncio.Event()
    worker = Worker()
    task = asyncio.create_task(run_job(worker, send=False, limit=1, stop=stop, cycles=None))
    await asyncio.sleep(0)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert worker.events == [("recover", 1)]


async def test_failures_are_redacted_and_bounded(monkeypatch):
    worker = Worker()

    async def failed(_):
        worker.events.append("failed")
        raise RuntimeError("secret-connection-and-token")

    async def timeout(*args, **kwargs):
        args[0].close()
        raise TimeoutError

    worker.recover_interrupted = failed
    monkeypatch.setattr(asyncio, "wait_for", timeout)
    reports = []
    result = await run_job(
        worker, send=True, limit=2, stop=asyncio.Event(), cycles=None, report=reports.append
    )
    assert worker.events == ["failed"] * 3
    assert result["code"] == "INVITATION_WORKER_REPEATED_FAILURE"
    assert "secret" not in repr(reports)


@pytest.mark.parametrize(
    "options", [{"limit": 0}, {"interval": 4}, {"cycles": 0}, {"cycles": True}]
)
async def test_invalid_limits_cannot_start(options):
    settings = {"send": True, "limit": 1, "stop": asyncio.Event()} | options
    worker = Worker()
    with pytest.raises(ValueError):
        await run_job(worker, **settings)
    assert worker.events == []
