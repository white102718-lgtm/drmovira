"""恢复提交编排纯测；SQL约束、锁与整事务回滚仍需主线真实验收。"""

from collections import Counter
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_launch_execution_lease_contract import NOW, binding

import orbit_api.launch_execution_recovery_store as module
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_lease_contract import RecoveryDecision
from orbit_api.launch_execution_lease_store import ExecutionLeaseAuthority, RuntimeExpectation
from orbit_api.launch_execution_recovery_store import ExecutionRecoveryStore


class Authority(ExecutionLeaseAuthority):
    async def authorize(self, *args):
        raise AssertionError("capture单独既有测试覆盖")

    async def verify_fact(self, *args, **kwargs):
        raise AssertionError("capture单独既有测试覆盖")


@pytest.mark.asyncio
@pytest.mark.parametrize("authority", [None, object(), SimpleNamespace(kind="TRUSTED")])
async def test_missing_authority_fails_before_sql(authority):
    session = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(OrbitError) as error:
        await ExecutionRecoveryStore(authority).recover_expired(session, 1, None, None, None)
    assert error.value.status == 503
    session.execute.assert_not_awaited()


def setup(
    monkeypatch, path=("RUNNING", "UNKNOWN"), *, manual=False, task_manual=False, count_state=None
):
    attempt = binding()
    expected = RuntimeExpectation(
        3, attempt.attempt_no, attempt.fencing_token, attempt.claim_id, attempt.worker_id
    )
    task = dict(
        node_count=2,
        revision=7,
        latest_sequence=9,
        latest_event_id=None,
        state="RUNNING",
        needs_manual_reconciliation=task_manual,
    )
    runtime = dict(
        unknown_since=NOW.replace(tzinfo=None) - timedelta(hours=25)
        if path[0] == "UNKNOWN"
        else None,
        next_reconcile_at=None,
        needs_manual_reconciliation=False,
    )
    decision = RecoveryDecision(
        path,
        "UNKNOWN_MANUAL_REQUIRED" if manual else "LEASE_OUTCOME_UNKNOWN",
        needs_manual_reconciliation=manual,
    )
    captured = SimpleNamespace(
        snapshot=SimpleNamespace(state=path[0]),
        database_now=NOW,
        summary=SimpleNamespace(total_count=289, last_sequence=289, root_sha256="a" * 64),
        decision=lambda session: decision,
    )
    monkeypatch.setattr(
        module.ExecutionLeaseStore, "capture_recovery", AsyncMock(return_value=captured)
    )

    async def one(session, sql, values):
        if "SELECT * FROM orbit_task " in sql:
            return task
        if "SELECT * FROM orbit_execution_command_runtime" in sql:
            return runtime
        if "orbit_task_clock" in sql:
            return {"revision": 4}
        if "UTC_TIMESTAMP" in sql:
            return {"now": NOW.replace(tzinfo=None)}
        raise AssertionError("未知读取")

    monkeypatch.setattr(module, "_one", one)
    monkeypatch.setattr(
        module,
        "_current_task_counts",
        AsyncMock(return_value=(Counter(count_state or {path[0]: 1, "QUEUED": 1}), False)),
    )
    monkeypatch.setattr(module, "_verify_edge_links", AsyncMock())
    inserts, writes = [], []

    async def insert(session, table, values):
        inserts.append((table, values))

    async def write(session, sql, values):
        writes.append((sql, values))

    monkeypatch.setattr(module, "_insert", insert)
    monkeypatch.setattr(module, "_write", write)
    return attempt, expected, inserts, writes


@pytest.mark.asyncio
async def test_two_original_node_edges_preserve_events_and_clock_once(monkeypatch):
    attempt, expected, inserts, writes = setup(monkeypatch, ("RUNNING", "ACCEPTED", "VERIFYING"))
    result = await ExecutionRecoveryStore(Authority()).recover_expired(
        object(), 1, attempt, expected, "00000000-0000-0000-0000-000000000099"
    )
    events = [v for t, v in inserts if t == "orbit_task_event"]
    assert [v["state"] for v in events] == ["ACCEPTED", "VERIFYING"]
    assert [v["task_revision"] for v in events] == [8, 9]
    assert [v["sequence"] for v in events] == [10, 11]
    assert all(v["node_id"] == attempt.node_id for v in events)
    assert (
        result.task_revision == 9
        and result.runtime_revision == 4
        and result.node_state == "VERIFYING"
    )
    assert sum("UPDATE orbit_task_clock " in sql for sql, _ in writes) == 1
    assert sum("UPDATE orbit_execution_command_runtime " in sql for sql, _ in writes) == 1
    assert len([v for t, v in inserts if t == "orbit_task_audit"]) == 2
    assert len([v for t, v in inserts if t == "orbit_task_outbox"]) == 2
    assert inserts[0][1]["fact_count"] == 289
    assert inserts[0][1]["fact_root_sha256"] == "a" * 64
    assert writes[-1][1] == {"tenant": attempt.tenant_id, "id": result.decision_id}
    assert "publication_phase='SEALED'" in writes[-1][0]


@pytest.mark.asyncio
async def test_node_event_state_is_not_task_aggregate(monkeypatch):
    attempt, expected, inserts, writes = setup(
        monkeypatch, ("ACCEPTED", "VERIFYING"), count_state={"ACCEPTED": 1, "UNKNOWN": 1}
    )
    result = await ExecutionRecoveryStore(Authority()).recover_expired(
        object(), 1, attempt, expected, "00000000-0000-0000-0000-000000000099"
    )
    assert result.task_state == "UNKNOWN"
    event = next(v for t, v in inserts if t == "orbit_task_event")
    edge = next(v for t, v in inserts if t == "orbit_execution_recovery_edge")
    assert event["state"] == "VERIFYING" and edge["task_after_state"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_noop_does_not_write_ledger_revisions_or_events(monkeypatch):
    attempt, expected, inserts, writes = setup(monkeypatch, ("RUNNING",))
    result = await ExecutionRecoveryStore(Authority()).recover_expired(
        object(), 1, attempt, expected, "00000000-0000-0000-0000-000000000099"
    )
    assert not result.changed and result.decision_id is None
    assert not inserts and not writes


@pytest.mark.asyncio
async def test_manual_change_is_one_unknown_event_not_new_attempt(monkeypatch):
    attempt, expected, inserts, writes = setup(monkeypatch, ("UNKNOWN",), manual=True)
    result = await ExecutionRecoveryStore(Authority()).recover_expired(
        object(), 1, attempt, expected, "00000000-0000-0000-0000-000000000099"
    )
    assert result.node_state == "UNKNOWN" and result.task_revision == 8
    edge = next(v for t, v in inserts if t == "orbit_execution_recovery_edge")
    assert (
        edge["edge_kind"] == "MANUAL"
        and edge["node_before_state"] == edge["node_after_state"] == "UNKNOWN"
    )
    assert not any("UPDATE orbit_task_node " in sql for sql, _ in writes)
    runtime = next(v for sql, v in writes if "UPDATE orbit_execution_command_runtime " in sql)
    assert runtime["manual"] is True and runtime["next_read"] is None
    assert runtime["attempt"] == expected.attempt_no
    assert not any("last_reconciled_at=" in sql or "attempt=attempt+" in sql for sql, _ in writes)


@pytest.mark.asyncio
async def test_audit_outbox_failure_propagates_without_sealing(monkeypatch):
    attempt, expected, inserts, writes = setup(monkeypatch)
    original = module._insert

    async def failing(session, table, values):
        if table == "orbit_task_outbox":
            raise RuntimeError("fixture rollback required")
        await original(session, table, values)

    monkeypatch.setattr(module, "_insert", failing)
    with pytest.raises(RuntimeError):
        await ExecutionRecoveryStore(Authority()).recover_expired(
            object(), 1, attempt, expected, "00000000-0000-0000-0000-000000000099"
        )
    assert not any("publication_phase='SEALED'" in sql for sql, _ in writes)
    assert not any("UPDATE orbit_task_clock " in sql for sql, _ in writes)


class MappingResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


@pytest.mark.asyncio
async def test_current_node_scan_crosses_500_and_batches_unknown_runtime_reads():
    from uuid import UUID

    rows = [
        {
            "id": str(UUID(int=i + 1)),
            "ordinal": i,
            "state": "UNKNOWN" if i in (0, 500) else "QUEUED",
        }
        for i in range(501)
    ]
    calls = []

    async def execute(sql, values):
        calls.append((str(sql), values))
        if "FROM orbit_task_node" in str(sql):
            return MappingResult([r for r in rows if r["ordinal"] > values["after"]][:500])
        assert "ORDER BY node_id FOR SHARE" in str(sql)
        identifiers = sorted(v for k, v in values.items() if k.startswith("unknown_"))
        return MappingResult(
            [
                {
                    "node_id": identifier,
                    "unknown_since": NOW - timedelta(hours=25),
                    "needs_manual_reconciliation": False,
                }
                for identifier in identifiers
            ]
        )

    session = SimpleNamespace(execute=execute)
    counts, manual = await module._current_task_counts(
        session, {"tenant": "t", "task": "x"}, 501, NOW
    )
    assert counts == Counter(UNKNOWN=2, QUEUED=499) and manual is True
    assert len(calls) == 5
    assert all("FOR SHARE" in sql for sql, _ in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem", ["gap", "missing", "unknown_state", "runtime_missing", "runtime_future"]
)
async def test_current_scan_rejects_incomplete_or_untrusted_other_nodes(problem):
    rows = [
        {
            "id": "x",
            "ordinal": 1 if problem == "gap" else 0,
            "state": "BAD" if problem == "unknown_state" else "UNKNOWN",
        }
    ]

    async def execute(sql, values):
        if "FROM orbit_task_node" in str(sql):
            return MappingResult(rows if values["after"] == -1 else [])
        if problem == "runtime_missing":
            return MappingResult([])
        return MappingResult(
            [
                {
                    "node_id": "x",
                    "unknown_since": NOW + timedelta(seconds=1)
                    if problem == "runtime_future"
                    else NOW,
                    "needs_manual_reconciliation": False,
                }
            ]
        )

    with pytest.raises(OrbitError):
        await module._current_task_counts(
            SimpleNamespace(execute=execute),
            {"tenant": "t", "task": "x"},
            2 if problem == "missing" else 1,
            NOW,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("ordinals", [[], [1], [1, 3], [1, 2, 3]])
async def test_seal_requires_exact_actual_event_audit_outbox_links(ordinals):
    session = SimpleNamespace(
        execute=AsyncMock(return_value=MappingResult([{"ordinal": i} for i in ordinals]))
    )
    with pytest.raises(OrbitError):
        await module._verify_edge_links(
            session, {"tenant": "t", "task": "x", "node": "n"}, "d", "r", 1, NOW, 2
        )
    sql = str(session.execute.await_args.args[0])
    assert (
        "JOIN orbit_task_event" in sql
        and "JOIN orbit_task_audit" in sql
        and "JOIN orbit_task_outbox" in sql
    )
    assert "v.state=e.node_after_state" in sql and "v.task_revision=e.task_revision" in sql


@pytest.mark.asyncio
async def test_failed_cas_propagates_conflict():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(rowcount=0)))
    with pytest.raises(OrbitError) as error:
        await module._write(session, "UPDATE fixed_table SET revision=revision+1", {})
    assert error.value.status == 409
