from datetime import UTC, datetime


def test_business_window_uses_account_day_and_inclusive_90_days():
    from orbit_api.meta_sync_runtime import business_window

    start, end = business_window("America/Los_Angeles", datetime(2026, 1, 1, 2, tzinfo=UTC), 90)
    assert end.isoformat() == "2025-12-31"
    assert (end - start).days == 89


def test_fast_refresh_is_seven_business_days():
    from orbit_api.meta_sync_runtime import business_window

    start, end = business_window("Asia/Shanghai", datetime(2026, 1, 1, 20, tzinfo=UTC), 7)
    assert end.isoformat() == "2026-01-02"
    assert (end - start).days == 6


async def test_runtime_continues_after_unavailable_head_job(monkeypatch):
    from contextlib import asynccontextmanager

    from orbit_api.errors import OrbitError
    from orbit_api.meta_sync_runtime import MetaSyncRuntime

    class Result:
        def mappings(self):
            return self

        def all(self):
            return [{"id": "first", "actor_id": 1}, {"id": "second", "actor_id": 2}]

        def first(self):
            return self.all()[0]

    class Session:
        def begin(self):
            return context(self)

        async def execute(self, *args):
            return Result()

    @asynccontextmanager
    async def context(value):
        yield value

    class Worker:
        def __init__(self, *args):
            pass

        async def run(self, actor, job):
            if job == "first":
                raise OrbitError(409, "META_SOURCE_CHANGED", "来源已失效")
            return {"job_id": job}

    monkeypatch.setattr("orbit_api.meta_metric_worker.MetaMetricWorker", Worker)
    runtime = MetaSyncRuntime(lambda: context(Session()), None, "v24.0")

    async def close(*args):
        pass

    monkeypatch.setattr(runtime, "close_unavailable", close, raising=False)
    assert await runtime.run_one() == {"job_id": "second"}


async def test_twenty_terminal_jobs_cannot_starve_next_job_and_transient_does_not_exit(monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    from orbit_api.errors import OrbitError
    from orbit_api.meta_read_contract import MetaReadFailure
    from orbit_api.meta_sync_runtime import MetaSyncRuntime

    codes = [
        "META_PROFILE_CHANGED",
        "METRICS_DATA_UNVERIFIED",
        "METRIC_PROFILE_SOURCE_CHANGED",
        "META_RETRY_EXHAUSTED",
    ]
    jobs = [
        dict(tenant_id="tenant", id=str(i), actor_id=1, state="INVENTORY", checkpoint_json={})
        for i in range(22)
    ]

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def mappings(self):
            return self

        def all(self):
            return self.rows

        def first(self):
            return self.rows[0] if self.rows else None

    class Session:
        def begin(self):
            return context(self)

        async def execute(self, sql, params=None):
            statement = str(sql)
            if statement.startswith("UPDATE"):
                next(j for j in jobs if j["id"] == params["id"])["state"] = "FAILED"
                return Result([])
            if "FOR UPDATE" in statement:
                return Result(
                    [j for j in jobs if j["id"] == params["id"] and j["state"] != "FAILED"]
                )
            return Result([j for j in jobs if j["state"] == "INVENTORY"][:20])

    @asynccontextmanager
    async def context(value):
        yield value

    class Worker:
        def __init__(self, *args):
            pass

        async def run(self, actor, identifier):
            index = int(identifier)
            if index < 20:
                raise OrbitError(409, codes[index % 4], "unavailable")
            if index == 20:
                jobs[index]["state"] = "RETRY_WAIT"
                raise MetaReadFailure("META_RATE_LIMITED", retryable=True)
            return {"job_id": identifier}

    monkeypatch.setattr("orbit_api.meta_metric_worker.MetaMetricWorker", Worker)
    monkeypatch.setattr(
        "orbit_api.meta_metric_collection.MetaMetricCollectionStore._event", AsyncMock()
    )
    runtime = MetaSyncRuntime(lambda: context(Session()), None, "v24.0")
    assert await runtime.run_one() is None
    assert all(j["state"] == "FAILED" for j in jobs[:20])
    assert await runtime.run_one() == {"job_id": "21"}
    assert jobs[20]["state"] == "RETRY_WAIT"


async def test_enqueue_connection_override_wins_even_when_scheduler_disabled(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from config import orbit_runtime

    from orbit_api.meta_sync_runtime import enqueue_metrics

    monkeypatch.setattr(
        orbit_runtime, "private_values", lambda: {"ORBIT_META_GRAPH_VERSION": "v24.0"}
    )
    override = {
        "profile_id": "connection-profile",
        "adapter_version": "connection-adapter",
        "scheduler_enabled": False,
    }
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: override))
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    begin = AsyncMock(return_value={"job_id": "job"})
    monkeypatch.setattr("orbit_api.meta_metric_collection.MetaMetricCollectionStore.begin", begin)
    assert await enqueue_metrics(
        session,
        SimpleNamespace(tenant_id="tenant", actor_id=1),
        {"id": "account", "timezone_id": "UTC"},
        "request",
    ) == {"job_id": "job"}
    assert session.execute.await_count == 1
    assert begin.await_args.args[3:5] == ("connection-profile", "connection-adapter")
    # scheduler=false only controls automation; explicit/manual backfill retains chosen mapping.


async def test_enqueue_uses_tenant_fallback_only_when_override_absent(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from config import orbit_runtime

    from orbit_api.meta_sync_runtime import enqueue_metrics

    monkeypatch.setattr(
        orbit_runtime, "private_values", lambda: {"ORBIT_META_GRAPH_VERSION": "v24.0"}
    )
    fallback = {"profile_id": "tenant-profile", "adapter_version": "tenant-adapter"}
    results = [None, fallback]
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(mappings=lambda row=row: SimpleNamespace(first=lambda: row))
                for row in results
            ]
        )
    )
    begin = AsyncMock(return_value={})
    monkeypatch.setattr("orbit_api.meta_metric_collection.MetaMetricCollectionStore.begin", begin)
    await enqueue_metrics(
        session,
        SimpleNamespace(tenant_id="tenant", actor_id=1),
        {"id": "account", "timezone_id": "UTC"},
        "request",
    )
    assert session.execute.await_count == 2
    assert begin.await_args.args[3:5] == ("tenant-profile", "tenant-adapter")


async def test_schedule_pages_same_tenant_connections_and_ignores_disabled_policy(monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    from orbit_api.meta_sync_runtime import MetaSyncRuntime

    policies = [
        dict(tenant_id="tenant", policy_connection=f"{i:03}", scheduler_enabled=i != 50)
        for i in range(102)
    ]

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def mappings(self):
            return self

        def all(self):
            return self.rows

    class Session:
        async def execute(self, sql, params):
            query = str(sql)
            if "FROM orbit_meta_sync_policy " in query:
                return Result([])
            assert "scheduler_enabled=1" in query
            assert "tenant_id=:tenant AND connection_id>:connection" in query
            return Result(
                [
                    p
                    for p in policies
                    if p["scheduler_enabled"]
                    and (p["tenant_id"], p["policy_connection"])
                    > (params["tenant"], params["connection"])
                ][:100]
            )

    @asynccontextmanager
    async def context():
        yield Session()

    runtime = MetaSyncRuntime(context, None, "v24.0")
    schedule = AsyncMock(return_value=1)
    monkeypatch.setattr(runtime, "_schedule_policy", schedule)
    assert await runtime.schedule() == 101
    ids = [call.args[0]["policy_connection"] for call in schedule.await_args_list]
    assert len(set(ids)) == 101 and "050" not in ids and ids[-1] == "101"


async def test_disabled_override_created_after_scan_blocks_tenant_schedule(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from orbit_api.meta_sync_runtime import MetaSyncRuntime

    current = SimpleNamespace(
        tenant_id="tenant", actor_id=1, subject_id="subject", data_role="SUPER_ADMIN"
    )
    monkeypatch.setattr(
        "orbit_api.authorization.require_business_access", AsyncMock(return_value=current)
    )
    monkeypatch.setattr("orbit_api.account_access.clock", AsyncMock())
    enqueue = AsyncMock()
    monkeypatch.setattr("orbit_api.meta_sync_runtime.enqueue_metrics", enqueue)
    scans = 0

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def mappings(self):
            return self

        def all(self):
            return self.rows

        def one(self):
            return self.rows[0]

        def first(self):
            return self.rows[0] if self.rows else None

    class Session:
        def begin(self):
            return context()

        async def execute(self, sql, params):
            nonlocal scans
            query = str(sql)
            if query.startswith("SELECT a.*"):
                assert "NOT EXISTS" in query and "cp.connection_id=s.connection_id" in query
                scans += 1
                return Result([{"id": "account"}] if scans == 1 else [])
            if query.startswith("SELECT revision"):
                return Result([{"revision": 1, "scheduler_enabled": True}])
            if query.startswith("SELECT s.connection_id"):
                assert "FOR SHARE" in query
                # A disabled override was added after the first scan completed.
                return Result(
                    [{"connection_id": "connection", "override_connection": "connection"}]
                )
            assert query.startswith("UPDATE orbit_meta_sync_policy")
            return Result([])

    @asynccontextmanager
    async def context():
        yield Session()

    runtime = MetaSyncRuntime(context, None, "v24.0")
    count = await runtime._schedule_policy(
        {
            "tenant_id": "tenant",
            "actor_id": 1,
            "revision": 1,
            "last_daily_date": None,
            "last_fast_slot": None,
        }
    )
    assert count == 0
    enqueue.assert_not_awaited()


async def test_adapter_translates_revoked_source_and_unavailable_credentials(monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    import pytest

    from orbit_api.account_platform import AccountReadFailure
    from orbit_api.errors import OrbitError
    from orbit_api.meta_read_contract import MetaReadFailure
    from orbit_api.meta_sync_runtime import MetaSyncRuntime

    class Session:
        def begin(self):
            return context()

    @asynccontextmanager
    async def context():
        yield Session()

    runtime = MetaSyncRuntime(context, None, "v24.0")
    job = {"tenant_id": "tenant", "connection_id": "connection", "connection_revision": 1}
    loader = AsyncMock(side_effect=AccountReadFailure("META_CONNECTION_SOURCE_CHANGED"))
    monkeypatch.setattr("orbit_api.meta_account_sources.load_connection", loader)
    with pytest.raises(OrbitError) as error:
        await runtime.adapter(job)
    assert error.value.code == "META_SOURCE_CHANGED"
    loader.side_effect = AccountReadFailure("META_CONNECTION_SOURCE_UNAVAILABLE")
    with pytest.raises(MetaReadFailure) as error:
        await runtime.adapter(job)
    assert error.value.code == "META_TRANSIENT_FAILURE" and error.value.retryable
    loader.side_effect = RuntimeError("unexpected-programming-error")
    with pytest.raises(RuntimeError):
        await runtime.adapter(job)
