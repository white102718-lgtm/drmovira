"""恢复扫描器纯协议；无数据库连接/平台调用/生产issuer。"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from test_launch_execution_lease_contract import NOW, binding

import orbit_api.launch_execution_recovery_scanner as module
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_lease_store import (
    ExecutionLeaseAuthority,
    LeaseOperation,
    RuntimeExpectation,
)
from orbit_api.launch_execution_recovery_scanner import (
    ExecutionRecoveryScanner,
    MaintenanceScanGrant,
    RawRecoveryHint,
    RecoveryBucket,
    RecoveryCandidate,
    RecoveryScanAuthorityProvider,
)


def uid(value):
    return str(UUID(int=value))


def grant(**changes):
    value = MaintenanceScanGrant(
        uid(700),
        uid(701),
        1,
        (binding().tenant_id,),
        LeaseOperation.RECOVER_EXPIRED,
        1,
        NOW + timedelta(hours=1),
    )
    return replace(value, **changes)


class Authority(ExecutionLeaseAuthority):
    async def authorize(self, *args):
        raise AssertionError("scanner不代替实际Store授权")

    async def verify_fact(self, *args, **kwargs):
        raise AssertionError("scanner不验证平台")


class Provider(RecoveryScanAuthorityProvider):
    def __init__(self, value=None):
        self.value = value or grant()
        self.calls = []
        self.hook = None

    async def capture(self):
        self.calls.append("capture")
        return self.value

    async def current(self, original):
        self.calls.append("current")
        return self.hook(original) if self.hook else self.value

    async def authority(self, original):
        self.calls.append("authority")
        return Authority()


class Session:
    def __init__(self, events, number):
        self.events = events
        self.number = number

    async def __aenter__(self):
        self.events.append(("open", self.number))
        return self

    async def __aexit__(self, *args):
        self.events.append(("close", self.number))

    def begin(self):
        return Transaction(self)


class Transaction:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.events.append(("begin", self.session.number))
        return self

    async def __aexit__(self, kind, *args):
        self.session.events.append(("rollback" if kind else "commit", self.session.number))


class Sessions:
    def __init__(self):
        self.events = []
        self.count = 0

    def __call__(self):
        self.count += 1
        return Session(self.events, self.count)


def candidate(tenant=None, node=900):
    attempt = replace(binding(), tenant_id=tenant or binding().tenant_id, node_id=uid(node))
    return RecoveryCandidate(
        attempt,
        RuntimeExpectation(
            1, attempt.attempt_no, attempt.fencing_token, attempt.claim_id, attempt.worker_id
        ),
    )


@asynccontextmanager
async def fake_recovery_transaction(sessions):
    # 仅扫描编排pure夹具；独占连接及真实设置协议另用下方专属测试覆盖。
    async with sessions() as session, session.begin():
        yield session


def setup(monkeypatch, *, tenants=None, hints=None, recovery=None, page_error=None):
    provider = Provider(grant(tenants=tenants) if tenants else grant())
    sessions = Sessions()
    factory = Mock(return_value=sessions)
    scanner = ExecutionRecoveryScanner(provider, factory, clock=lambda: NOW)
    calls = []

    async def page(session, tenant, bucket, position, limit):
        calls.append((tenant, bucket, position.key, limit, session.number))
        if page_error:
            raise page_error
        selected = (hints or {}).get((tenant, bucket), [])
        rows = [row for row in selected if position.key is None or row.key > position.key][:limit]
        return NOW, position.cutoff or NOW, rows

    recovered = []

    async def recover(store, session, actor, attempt, expected, request_id):
        recovered.append((session.number, actor, attempt, expected, request_id))
        if recovery:
            return await recovery(attempt)
        return SimpleNamespace(changed=True)

    monkeypatch.setattr(module, "_recovery_transaction", fake_recovery_transaction)
    monkeypatch.setattr(module, "_candidate_page", page)
    monkeypatch.setattr(module.ExecutionRecoveryStore, "recover_expired", recover)
    return scanner, provider, sessions, factory, calls, recovered


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [None, object(), SimpleNamespace(kind="TRUSTED")])
async def test_missing_real_provider_rejected_before_sessions_factory(provider):
    factory = Mock()
    scanner = ExecutionRecoveryScanner(provider, factory)
    with pytest.raises(OrbitError) as error:
        await scanner.scan_once()
    assert error.value.code == "RECOVERY_SCAN_AUTHORITY_UNAVAILABLE"
    factory.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"tenants": ()},
        {"tenants": [uid(1)]},
        {"tenants": (uid(2), uid(1))},
        {"tenants": (uid(1), uid(1))},
        {"tenants": tuple(uid(i + 1) for i in range(65))},
        {"actor_id": True},
        {"revision": 0},
        {"action": LeaseOperation.HISTORICAL_FACT},
        {"grant_id": "bad"},
        {"expires_at": NOW.replace(tzinfo=None)},
    ],
)
def test_grant_requires_exact_subject_scope_action_revision_and_utc(changes):
    with pytest.raises(ValueError):
        grant(**changes)


@pytest.mark.asyncio
async def test_expired_grant_never_initializes_database():
    factory = Mock()
    scanner = ExecutionRecoveryScanner(Provider(grant(expires_at=NOW)), factory, clock=lambda: NOW)
    with pytest.raises(OrbitError) as error:
        await scanner.scan_once()
    assert error.value.code == "RECOVERY_SCAN_AUTHORITY_EXPIRED"
    factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes", [{"actor_id": 2}, {"revision": 2}, {"tenants": (uid(999),)}, {"grant_id": uid(777)}]
)
async def test_changed_current_grant_fails_before_database(changes):
    provider = Provider()
    provider.hook = lambda g: replace(g, **changes)
    factory = Mock()
    with pytest.raises(OrbitError) as error:
        await ExecutionRecoveryScanner(provider, factory, clock=lambda: NOW).scan_once()
    assert error.value.code == "RECOVERY_SCAN_AUTHORITY_CHANGED"
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_three_buckets_only_trusted_tenants_and_each_recovery_new_transaction(monkeypatch):
    tenant = binding().tenant_id
    hints = {
        (tenant, bucket): [RawRecoveryHint((index,), candidate(node=900 + index))]
        for index, bucket in enumerate(RecoveryBucket)
    }
    scanner, provider, sessions, factory, calls, recovered = setup(monkeypatch, hints=hints)
    report = await scanner.scan_once()
    assert report.attempted == report.recovered == 3 and report.pages == 3
    assert [row[1] for row in calls] == list(RecoveryBucket)
    assert {row[0] for row in calls} == set(provider.value.tenants)
    page_sessions = {row[4] for row in calls}
    recovery_sessions = [row[0] for row in recovered]
    assert not page_sessions.intersection(recovery_sessions) and len(set(recovery_sessions)) == 3
    assert len([row for row in sessions.events if row[0] == "commit"]) == 6
    assert all(row[1] == provider.value.actor_id for row in recovered)


@pytest.mark.asyncio
async def test_candidate_budget_keeps_unprocessed_raw_cursor_and_tenant_fairness(monkeypatch):
    tenants = tuple(sorted((binding().tenant_id, uid(998))))
    hints = {
        (tenant, RecoveryBucket.EXPIRED): [
            RawRecoveryHint((i,), candidate(tenant, node=900 + i)) for i in (1, 2, 3)
        ]
        for tenant in tenants
    }
    scanner, provider, sessions, factory, calls, recovered = setup(
        monkeypatch, tenants=tenants, hints=hints
    )
    first = await scanner.scan_once(max_candidates=1)
    assert first.budget_exhausted and scanner._positions[
        (tenants[0], RecoveryBucket.EXPIRED)
    ].key == (1,)
    await scanner.scan_once(max_candidates=1)
    assert [row[2].tenant_id for row in recovered[:2]] == list(tenants)
    await scanner.scan_once(max_candidates=1)
    assert recovered[2][2].tenant_id == tenants[0] and recovered[2][2].node_id == uid(902)


@pytest.mark.asyncio
async def test_filtered_old_unknown_rows_advance_raw_keyset_without_blocking_later(monkeypatch):
    tenant = binding().tenant_id
    hints = {
        (tenant, RecoveryBucket.EXPIRED): [
            RawRecoveryHint((i,), None, blocked=False) for i in range(1, 201)
        ]
        + [RawRecoveryHint((201,), candidate())]
    }
    scanner, provider, sessions, factory, calls, recovered = setup(monkeypatch, hints=hints)
    first = await scanner.scan_once(max_raw_rows=200)
    assert first.raw_rows == 200 and first.filtered == 200 and first.blocked == 0 and not recovered
    second = await scanner.scan_once()
    assert second.recovered == 1 and recovered[0][2] == candidate().binding
    assert any(row[2] == (200,) for row in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code,metric",
    [
        (409, "EXECUTION_LEASE_STALE", "stale"),
        (503, "EXECUTION_LEASE_SOURCE_UNVERIFIED", "blocked"),
        (503, "EXECUTION_FACT_READ_TIMEOUT", "blocked"),
    ],
)
async def test_only_known_conflict_or_unverified_outcomes_are_classified(
    monkeypatch, status, code, metric
):
    async def failure(_):
        raise OrbitError(status, code, "safe")

    tenant = binding().tenant_id
    scanner, _, sessions, _, _, _ = setup(
        monkeypatch,
        hints={(tenant, RecoveryBucket.EXPIRED): [RawRecoveryHint((1,), candidate())]},
        recovery=failure,
    )
    report = await scanner.scan_once()
    assert getattr(report, metric) == 1 and report.recovered == 0
    assert any(row[0] == "rollback" for row in sessions.events)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("db error"),
        OrbitError(409, "INVALID_TRANSITION", "safe"),
        OrbitError(503, "UNKNOWN_DB_FAILURE", "safe"),
    ],
)
async def test_unclassified_failures_abort_not_swallowed_and_cursor_not_advanced(
    monkeypatch, error
):
    async def failure(_):
        raise error

    tenant = binding().tenant_id
    scanner, _, sessions, _, _, _ = setup(
        monkeypatch,
        hints={(tenant, RecoveryBucket.EXPIRED): [RawRecoveryHint((1,), candidate())]},
        recovery=failure,
    )
    with pytest.raises(type(error)):
        await scanner.scan_once()
    assert scanner._positions[(tenant, RecoveryBucket.EXPIRED)].key is None
    assert not scanner._running and any(row[0] == "rollback" for row in sessions.events)


@pytest.mark.asyncio
async def test_stop_during_recovery_drains_current_transaction_and_leaves_next_unread(monkeypatch):
    tenant = binding().tenant_id

    async def recover(_):
        scanner.request_stop()
        return SimpleNamespace(changed=True)

    scanner, _, sessions, _, _, recovered = setup(
        monkeypatch,
        hints={
            (tenant, RecoveryBucket.EXPIRED): [
                RawRecoveryHint((i,), candidate(node=900 + i)) for i in (1, 2)
            ]
        },
        recovery=recover,
    )
    report = await scanner.scan_once()
    assert report.stopped and report.recovered == 1 and len(recovered) == 1
    assert scanner._positions[(tenant, RecoveryBucket.EXPIRED)].key == (1,)
    assert sessions.events[-2][0] == "commit" and sessions.events[-1][0] == "close"


@pytest.mark.asyncio
async def test_cancel_and_concurrent_scan_do_not_leave_background_transactions(monkeypatch):
    started = asyncio.Event()

    async def waiting(_):
        started.set()
        await asyncio.Event().wait()

    tenant = binding().tenant_id
    scanner, _, sessions, factory, _, _ = setup(
        monkeypatch,
        hints={(tenant, RecoveryBucket.EXPIRED): [RawRecoveryHint((1,), candidate())]},
        recovery=waiting,
    )
    task = asyncio.create_task(scanner.scan_once())
    await started.wait()
    with pytest.raises(OrbitError) as error:
        await scanner.scan_once()
    assert error.value.code == "RECOVERY_SCAN_ALREADY_RUNNING" and factory.call_count == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        not scanner._running
        and sessions.events[-2][0] == "rollback"
        and sessions.events[-1][0] == "close"
    )
    assert scanner._positions[(tenant, RecoveryBucket.EXPIRED)].key is None


@pytest.mark.asyncio
async def test_monotonic_budget_stops_before_second_candidate_without_losing_page(monkeypatch):
    tick = [0.0]
    tenant = binding().tenant_id

    async def recovery(_):
        tick[0] += 11
        return SimpleNamespace(changed=False)

    scanner, _, _, _, _, recovered = setup(
        monkeypatch,
        hints={
            (tenant, RecoveryBucket.EXPIRED): [
                RawRecoveryHint((i,), candidate(node=900 + i)) for i in (1, 2)
            ]
        },
        recovery=recovery,
    )
    scanner.monotonic = lambda: tick[0]
    report = await scanner.scan_once(time_budget_seconds=10)
    assert report.budget_exhausted and report.noop == 1 and len(recovered) == 1
    assert scanner._positions[(tenant, RecoveryBucket.EXPIRED)].key == (1,)


class Result:
    def __init__(self, rows=None, scalar=None):
        self.rows = rows
        self.scalar = scalar

    def scalar_one(self):
        return self.scalar

    def mappings(self):
        return self

    def all(self):
        return self.rows


@pytest.mark.asyncio
@pytest.mark.parametrize("bucket", list(RecoveryBucket))
async def test_sql_candidate_page_is_bounded_raw_then_single_set_binding(bucket):
    attempt = binding()
    executions = []
    raw = {
        "task_id": attempt.task_id,
        "node_id": attempt.node_id,
        "due": NOW.replace(tzinfo=None) - timedelta(days=2),
    }
    full = asdict(attempt) | {
        "runtime_revision": 2,
        "command_state": {"EXPIRED": "RUNNING", "ACCEPTED": "ACCEPTED", "MANUAL_DUE": "UNKNOWN"}[
            bucket.value
        ],
        "node_state": {"EXPIRED": "RUNNING", "ACCEPTED": "ACCEPTED", "MANUAL_DUE": "UNKNOWN"}[
            bucket.value
        ],
    }
    returns = [Result(scalar=NOW.replace(tzinfo=None)), Result(rows=[raw]), Result(rows=[full])]

    async def execute(sql, params=None):
        executions.append((str(sql), params))
        return returns.pop(0)

    now, cutoff, hints = await module._candidate_page(
        SimpleNamespace(execute=execute), attempt.tenant_id, bucket, module._Position(), 200
    )
    assert len(executions) == 3 and len(hints) == 1 and hints[0].candidate.binding == attempt
    raw_sql, raw_params = executions[1]
    join_sql, join_params = executions[2]
    assert "LIMIT :limit" in raw_sql and raw_params["limit"] == 200
    assert "JOIN" not in raw_sql and "FOR UPDATE" not in raw_sql and "tenant_id=:tenant" in raw_sql
    assert "(a.task_id,a.node_id) IN" in join_sql and join_params["task_0"] == attempt.task_id
    if bucket is RecoveryBucket.MANUAL_DUE:
        assert raw_params["manual_cutoff"] == (NOW - timedelta(hours=24)).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_sql_filtered_noncurrent_row_is_not_silently_removed_from_raw_watermark():
    attempt = binding()
    rows = [
        Result(scalar=NOW),
        Result(rows=[{"task_id": attempt.task_id, "node_id": attempt.node_id, "due": NOW}]),
        Result(
            rows=[
                asdict(attempt)
                | {"runtime_revision": 1, "command_state": "UNKNOWN", "node_state": "UNKNOWN"}
            ]
        ),
    ]

    async def execute(*args):
        return rows.pop(0)

    _, _, hints = await module._candidate_page(
        SimpleNamespace(execute=execute),
        attempt.tenant_id,
        RecoveryBucket.EXPIRED,
        module._Position(),
        200,
    )
    assert len(hints) == 1 and hints[0].candidate is None and hints[0].key[-1] == attempt.node_id
    assert hints[0].blocked is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_candidates": 0},
        {"max_candidates": True},
        {"max_candidates": 201},
        {"max_raw_rows": 0},
        {"max_raw_rows": 10001},
        {"max_raw_rows": 1.0},
        {"time_budget_seconds": 0},
        {"time_budget_seconds": True},
        {"time_budget_seconds": float("nan")},
        {"time_budget_seconds": 61},
    ],
)
async def test_invalid_operational_budget_rejected_before_database(kwargs):
    factory = Mock()
    scanner = ExecutionRecoveryScanner(Provider(), factory, clock=lambda: NOW)
    with pytest.raises(ValueError):
        await scanner.scan_once(**kwargs)
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_timeout_in_flight_rolls_back_without_advancing_or_background_task(monkeypatch):
    async def waiting(_):
        await asyncio.Event().wait()

    tenant = binding().tenant_id
    scanner, _, sessions, _, _, _ = setup(
        monkeypatch,
        hints={(tenant, RecoveryBucket.EXPIRED): [RawRecoveryHint((1,), candidate())]},
        recovery=waiting,
    )
    with pytest.raises(TimeoutError):
        await scanner.scan_once(time_budget_seconds=0.02)
    assert (
        not scanner._running
        and sessions.events[-2][0] == "rollback"
        and sessions.events[-1][0] == "close"
    )
    assert scanner._positions[(tenant, RecoveryBucket.EXPIRED)].key is None


@pytest.mark.asyncio
async def test_current_authority_change_after_read_batch_aborts_before_recovery(monkeypatch):
    tenant = binding().tenant_id
    scanner, provider, sessions, _, _, recovered = setup(
        monkeypatch, hints={(tenant, RecoveryBucket.EXPIRED): [RawRecoveryHint((1,), candidate())]}
    )
    provider.hook = lambda g: replace(g, revision=2) if provider.calls.count("current") >= 3 else g
    with pytest.raises(OrbitError) as error:
        await scanner.scan_once()
    assert error.value.code == "RECOVERY_SCAN_AUTHORITY_CHANGED" and not recovered
    assert scanner._positions[(tenant, RecoveryBucket.EXPIRED)].key is None
    assert sessions.events[-2][0] == "commit" and sessions.events[-1][0] == "close"


@pytest.mark.asyncio
async def test_sql_clock_expiry_rejected_before_any_recovery(monkeypatch):
    scanner, provider, sessions, _, _, recovered = setup(monkeypatch)

    async def future(*args):
        return provider.value.expires_at, NOW, []

    monkeypatch.setattr(module, "_candidate_page", future)
    with pytest.raises(OrbitError) as error:
        await scanner.scan_once()
    assert error.value.code == "RECOVERY_SCAN_AUTHORITY_EXPIRED" and not recovered
    assert sessions.events[-2][0] == "rollback"


@pytest.mark.asyncio
async def test_old_cutoff_after_sql_clock_regression_is_rejected_before_candidate_query():
    execute = AsyncMock(return_value=Result(scalar=NOW))
    with pytest.raises(OrbitError):
        await module._candidate_page(
            SimpleNamespace(execute=execute),
            binding().tenant_id,
            RecoveryBucket.EXPIRED,
            module._Position(cutoff=NOW + timedelta(seconds=1)),
            200,
        )
    execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_set_binding_still_preserves_raw_hint_as_blocked():
    attempt = binding()
    rows = [
        Result(scalar=NOW),
        Result(rows=[{"task_id": attempt.task_id, "node_id": attempt.node_id}]),
        Result(rows=[]),
    ]

    async def execute(*args):
        return rows.pop(0)

    _, _, hints = await module._candidate_page(
        SimpleNamespace(execute=execute),
        attempt.tenant_id,
        RecoveryBucket.ACCEPTED,
        module._Position(),
        200,
    )
    assert len(hints) == 1 and hints[0].candidate is None


@pytest.mark.asyncio
async def test_extra_unrequested_set_binding_rejected_not_accepted_as_candidate():
    attempt = binding()
    rows = [
        Result(scalar=NOW),
        Result(rows=[{"task_id": attempt.task_id, "node_id": attempt.node_id}]),
        Result(rows=[asdict(replace(attempt, node_id=uid(555)))]),
    ]

    async def execute(*args):
        return rows.pop(0)

    with pytest.raises(OrbitError):
        await module._candidate_page(
            SimpleNamespace(execute=execute),
            attempt.tenant_id,
            RecoveryBucket.ACCEPTED,
            module._Position(),
            200,
        )


@pytest.mark.asyncio
async def test_request_stop_before_scan_skips_sessions_initialization(monkeypatch):
    scanner, _, _, factory, _, _ = setup(monkeypatch)
    scanner.request_stop()
    result = await scanner.scan_once()
    assert result.stopped and result.raw_rows == 0
    factory.assert_not_called()


class OwnedResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def one(self):
        return self.row


class OwnedConnection:
    def __init__(self):
        self.identifier = 31
        self.original = 50
        self.timeout = 50
        self.invalidated = False
        self.closed = False
        self.active = False
        self.events = []
        self.break_restore = False
        self.change_identity = False
        self.commit_failure = False
        self.hang_restore = False

    async def execute(self, sql, params=None):
        if self.invalidated:
            raise AssertionError("禁止invalidated后reconnect execute")
        self.active = True
        statement = str(sql)
        self.events.append(("execute", statement, params))
        if "CONNECTION_ID()" in statement:
            count = sum(
                "CONNECTION_ID()" in event[1] for event in self.events if event[0] == "execute"
            )
            identifier = self.identifier + (1 if self.change_identity and count > 1 else 0)
            return OwnedResult({"connection_id": identifier, "lock_wait_timeout": self.timeout})
        assert "SET SESSION innodb_lock_wait_timeout=" in statement
        if params and "seconds" in params:
            self.timeout = params["seconds"]
        else:
            if self.hang_restore:
                await asyncio.Event().wait()
            if self.break_restore:
                raise RuntimeError("fixture restore failed")
            self.timeout = params["original"]
        return OwnedResult({})

    async def commit(self):
        self.events.append(("commit",))
        self.active = False
        if self.commit_failure:
            self.commit_failure = False
            raise RuntimeError("fixture setup commit")

    async def rollback(self):
        self.events.append(("rollback",))
        self.active = False

    def in_transaction(self):
        return self.active

    async def invalidate(self):
        self.events.append(("invalidate",))
        self.invalidated = True

    async def close(self):
        self.events.append(("close",))
        self.closed = True


class OwnedBusinessSession:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def begin(self):
        return OwnedBusinessTransaction(self.connection)


class OwnedBusinessTransaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        assert not self.connection.active, "设置autobegin必须业务txn前提交"
        assert self.connection.timeout == 1
        self.connection.events.append(("business_begin",))
        self.connection.active = True

    async def __aexit__(self, kind, *args):
        if self.connection.invalidated:
            self.connection.active = False
        elif kind:
            await self.connection.rollback()
        else:
            await self.connection.commit()


def owned_sessions(connection):
    from sqlalchemy.ext.asyncio import AsyncEngine

    engine = Mock(spec=AsyncEngine)
    engine.connect = AsyncMock(return_value=connection)
    sessions = Mock(side_effect=lambda **kwargs: OwnedBusinessSession(kwargs["bind"]))
    sessions.kw = {"bind": engine}
    return sessions, engine


@pytest.mark.asyncio
async def test_owned_connection_setup_commit_business_restore_commit_same_cid():
    connection = OwnedConnection()
    sessions, engine = owned_sessions(connection)
    async with module._recovery_transaction(sessions) as business:
        assert business.connection is connection and connection.timeout == 1
    assert connection.timeout == 50 and connection.closed and not connection.invalidated
    assert not connection.active
    engine.connect.assert_awaited_once()
    sessions.assert_called_once_with(bind=connection)
    statements = [event for event in connection.events if event[0] == "execute"]
    assert len([event for event in statements if "CONNECTION_ID()" in event[1]]) == 4
    assert statements[1][2] == {"seconds": 1}
    assert next(event for event in statements if event[2] and "original" in event[2])[2] == {
        "original": 50
    }
    assert connection.events.index(("commit",)) < connection.events.index(("business_begin",))


@pytest.mark.asyncio
async def test_owned_connection_normal_rollback_restores_original_without_invalidating():
    connection = OwnedConnection()
    sessions, _ = owned_sessions(connection)
    with pytest.raises(RuntimeError):
        async with module._recovery_transaction(sessions):
            raise RuntimeError("fixture SQL1205")
    assert ("rollback",) in connection.events
    assert connection.timeout == 50 and connection.closed and not connection.invalidated


@pytest.mark.asyncio
async def test_cancel_invalidated_connection_is_closed_without_reconnect_or_reset():
    connection = OwnedConnection()
    sessions, _ = owned_sessions(connection)
    with pytest.raises(asyncio.CancelledError):
        async with module._recovery_transaction(sessions):
            connection.invalidated = True
            raise asyncio.CancelledError()
    assert connection.closed
    assert len([event for event in connection.events if event[0] == "execute"]) == 3
    assert not any(
        event[0] == "execute" and event[2] and "original" in event[2] for event in connection.events
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["restore", "identity"])
async def test_restore_failure_or_changed_cid_invalidates_owned_connection(failure):
    connection = OwnedConnection()
    sessions, _ = owned_sessions(connection)
    connection.break_restore = failure == "restore"
    connection.change_identity = failure == "identity"
    with pytest.raises(RuntimeError if failure == "restore" else OrbitError):
        async with module._recovery_transaction(sessions):
            pass
    assert connection.closed and connection.invalidated
    if failure == "identity":
        assert not any(
            event[0] == "execute" and event[2] and "original" in event[2]
            for event in connection.events
        )


@pytest.mark.asyncio
async def test_failed_setup_commit_still_restores_original_on_owned_connection():
    connection = OwnedConnection()
    connection.commit_failure = True
    sessions, _ = owned_sessions(connection)
    with pytest.raises(RuntimeError):
        async with module._recovery_transaction(sessions):
            raise AssertionError("must not reach business")
    assert connection.timeout == 50 and connection.closed and not connection.invalidated


@pytest.mark.asyncio
async def test_unknown_original_settings_fail_closed_and_discard_before_business():
    connection = OwnedConnection()
    connection.timeout = "50"
    sessions, _ = owned_sessions(connection)
    with pytest.raises(OrbitError):
        async with module._recovery_transaction(sessions):
            raise AssertionError("must not reach business")
    assert connection.invalidated and connection.closed
    assert not any(event[0] == "business_begin" for event in connection.events)


@pytest.mark.asyncio
async def test_bounded_restore_timeout_invalidates_and_closes_without_background_task(monkeypatch):
    connection = OwnedConnection()
    connection.hang_restore = True
    sessions, _ = owned_sessions(connection)
    monkeypatch.setattr(module, "CONNECTION_CLEANUP_SECONDS", 0.01)
    before = set(asyncio.all_tasks())
    with pytest.raises(TimeoutError):
        async with module._recovery_transaction(sessions):
            pass
    assert connection.invalidated and connection.closed
    assert set(asyncio.all_tasks()) == before


@pytest.mark.asyncio
async def test_unverified_engine_bind_never_attempts_connection():
    sessions = Mock()
    sessions.kw = {"bind": object()}
    with pytest.raises(OrbitError) as error:
        async with module._recovery_transaction(sessions):
            pass
    assert error.value.code == "RECOVERY_SCAN_DATABASE_UNVERIFIED"
    sessions.assert_not_called()


@pytest.mark.asyncio
async def test_cancellation_between_statements_on_valid_connection_restores_original():
    connection = OwnedConnection()
    sessions, _ = owned_sessions(connection)
    with pytest.raises(asyncio.CancelledError):
        async with module._recovery_transaction(sessions):
            raise asyncio.CancelledError()
    assert connection.closed and not connection.invalidated and connection.timeout == 50
    assert ("rollback",) in connection.events


@pytest.mark.asyncio
async def test_real_db_error_1205_is_not_swallowed_or_reclassified_as_timeout(monkeypatch):
    from pymysql.err import OperationalError
    from sqlalchemy.exc import DBAPIError

    failure = DBAPIError("fixed SQL fixture", {}, OperationalError(1205, "fixture lock wait"))

    async def blocked(_):
        raise failure

    tenant = binding().tenant_id
    scanner, _, sessions, _, _, _ = setup(
        monkeypatch,
        hints={(tenant, RecoveryBucket.EXPIRED): [RawRecoveryHint((1,), candidate())]},
        recovery=blocked,
    )
    with pytest.raises(DBAPIError) as error:
        await scanner.scan_once()
    assert error.value is failure and error.value.orig.args[0] == 1205
    assert scanner._positions[(tenant, RecoveryBucket.EXPIRED)].key is None
    assert any(event[0] == "rollback" for event in sessions.events)
