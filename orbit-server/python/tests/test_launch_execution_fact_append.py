"""事实追加独立纯测；事务/SQL替身不替代050真实精度及1644验收。"""

import copy
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_launch_execution_lease_contract import NOW, fact, uid
from test_launch_execution_lease_store import FixtureAuthority, Result, Session

import orbit_api.launch_execution_lease_store as module
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_lease_contract import MAX_ATTEMPT


class AppendSession(Session):
    def __init__(self):
        super().__init__()
        self.stored = {}
        self.audits, self.outbox = {}, {}
        self.writes = []
        self.now = NOW + timedelta(seconds=2, microseconds=999999)
        self.precision = 6
        self.reject_outbox = False
        self.tail_override = None

    @asynccontextmanager
    async def atomic(self):
        before = copy.deepcopy((self.stored, self.audits, self.outbox))
        try:
            yield
        except BaseException:
            self.stored, self.audits, self.outbox = before
            raise

    async def execute(self, statement, values=None):
        sql = str(statement)
        if sql.startswith("INSERT "):
            self.writes.append(sql)
            if "INSERT INTO orbit_execution_attempt_fact" in sql:
                assert values["event"] not in self.stored
                self.stored[values["event"]] = {
                    "task_id": values["task"],
                    "node_id": values["node"],
                    "attempt_no": values["attempt"],
                    "fencing_token": values["fence"],
                    "claim_id": values["claim"],
                    "worker_id": values["worker"],
                    "event_id": values["event"],
                    "sequence_no": values["sequence"],
                    "fact_kind": values["kind"],
                    "send_phase": values["phase"],
                    "evidence_source": values["source"],
                    "evidence_sha256": values["hash"],
                    "external_id": values["external"],
                    "occurred_at": values["occurred"],
                    "recorded_at": values["recorded"],
                }
            elif "INSERT INTO orbit_task_audit" in sql:
                assert values["audit"] not in self.audits
                self.audits[values["audit"]] = dict(values)
            elif "INSERT INTO orbit_task_outbox" in sql:
                if self.reject_outbox:
                    raise RuntimeError("isolated outbox rejected")
                assert values["audit"] in self.audits
                self.outbox[values["audit"]] = dict(values)
            else:
                raise AssertionError("禁止新状态/版本/事件写入")
            return SimpleNamespace(rowcount=1)
        if "information_schema.COLUMNS" in sql:
            return Result(
                [
                    {"name": "occurred_at", "precision_value": self.precision},
                    {"name": "recorded_at", "precision_value": self.precision},
                ]
            )
        if "FROM orbit_execution_attempt_fact " in sql:
            if "event_id=:event" in sql:
                old = self.stored.get(values["event"])
                return Result([old] if old else [])
            if "ORDER BY sequence_no DESC" in sql:
                tail = self.tail_override
                if tail is None:
                    tail = max((row["sequence_no"] for row in self.stored.values()), default=0)
                return Result([{"sequence_no": tail}] if tail else [])
            raise AssertionError("追加不读取半包或使用调用者sequence")
        if "FROM orbit_task_audit a JOIN orbit_task_outbox" in sql:
            audit = values["audit"]
            return Result([{"id": audit}] if audit in self.audits and audit in self.outbox else [])
        if sql == "SELECT UTC_TIMESTAMP(6) AS now":
            return Result([{"now": self.now.replace(tzinfo=None)}])
        return await super().execute(statement, values)


async def append(session, record=None, *, authority=None, request=None):
    store = module.ExecutionLeaseStore(authority or FixtureAuthority())
    record = record or fact(binding=session.binding)
    return await store.append_verified_fact(session, 1, record, request or uid(90))


@pytest.mark.asyncio
@pytest.mark.parametrize("authority", [None, True, SimpleNamespace(kind="TRUSTED")])
async def test_append_without_explicit_authority_denies_before_sql(authority):
    session = AppendSession()
    with pytest.raises(OrbitError) as error:
        await module.ExecutionLeaseStore(authority).append_verified_fact(
            session, 1, fact(binding=session.binding), uid(90)
        )
    assert error.value.code == "EXECUTION_LEASE_AUTHORITY_UNAVAILABLE"
    assert not session.calls and not session.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("microsecond", [123499, 123500, 999999])
async def test_append_preserves_original_microseconds_and_replay_original_recorded_at(microsecond):
    session = AppendSession()
    record = fact(binding=session.binding, occurred_at=NOW.replace(microsecond=microsecond))
    first = await append(session, record)
    assert session.stored[record.event_id]["occurred_at"].microsecond == microsecond
    assert first.recorded_at == session.now
    session.now += timedelta(days=1)
    second = await append(session, record, request=uid(91))
    assert second == first
    assert len(session.stored) == len(session.audits) == len(session.outbox) == 1


@pytest.mark.asyncio
async def test_append_computes_contiguous_sequence_and_does_not_accept_caller_time_or_sequence():
    session = AppendSession()
    receipts = []
    for n in range(3):
        receipts.append(await append(session, fact(binding=session.binding, event_id=uid(200 + n))))
    assert [receipt.sequence_no for receipt in receipts] == [1, 2, 3]
    for extras in ({"sequence_no": 99}, {"recorded_at": NOW}):
        with pytest.raises(TypeError):
            await module.ExecutionLeaseStore(FixtureAuthority()).append_verified_fact(
                session, 1, fact(binding=session.binding), uid(90), **extras
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("evidence_sha256", "e" * 64),
        ("occurred_at", NOW + timedelta(microseconds=1)),
        ("external_id", "123"),
    ],
)
async def test_same_event_different_content_conflicts_without_new_audit(field, value):
    session = AppendSession()
    record = fact(binding=session.binding)
    await append(session, record)
    with pytest.raises(OrbitError) as error:
        await append(session, replace(record, **{field: value}))
    assert error.value.status == 409 and error.value.code == "EXECUTION_FACT_CONFLICT"
    assert len(session.stored) == len(session.audits) == len(session.outbox) == 1


@pytest.mark.asyncio
async def test_historical_authorization_is_distinct_from_current_recovery_permission():
    session, authority = AppendSession(), FixtureAuthority()
    authority.grant_transform = lambda grant: replace(
        grant, operation=module.LeaseOperation.RECOVER_EXPIRED
    )
    with pytest.raises(OrbitError) as error:
        await append(session, authority=authority)
    assert error.value.code == "EXECUTION_LEASE_AUTHORITY_UNAVAILABLE"
    assert not session.calls and not session.writes


@pytest.mark.asyncio
async def test_source_fact_needs_exact_verification_not_just_valid_shape():
    session, authority = AppendSession(), FixtureAuthority()
    authority.fact_transform = lambda receipt: None
    with pytest.raises(OrbitError):
        await append(session, authority=authority)
    assert not session.writes


@pytest.mark.asyncio
async def test_old_fence_appends_only_history_and_never_changes_current_head_or_task_fields():
    session = AppendSession()
    session.runtime.update(active_attempt=2, fencing_token=2, claim_id=uid(81), worker_id=uid(82))
    session.command.update(state="SUCCEEDED", attempt=2)
    session.node.update(state="SUCCEEDED", attempt=2)
    before = copy.deepcopy(
        (session.runtime, session.command, session.node, session.task, session.clock)
    )
    receipt = await append(session)
    assert receipt.sequence_no == 1
    assert (session.runtime, session.command, session.node, session.task, session.clock) == before
    assert len(session.stored) == 1
    assert all(sql.startswith("INSERT ") for sql in session.writes)


@pytest.mark.asyncio
async def test_unsupported_legacy_precision_fails_without_rounding_any_fact():
    session = AppendSession()
    session.precision = 3
    with pytest.raises(OrbitError) as error:
        await append(session)
    assert error.value.code == "EXECUTION_FACT_PRECISION_UNVERIFIED"
    assert not session.writes


@pytest.mark.asyncio
async def test_outer_rollback_keeps_fact_audit_outbox_atomic_and_retry_uses_same_sequence():
    session = AppendSession()
    session.reject_outbox = True
    with pytest.raises(RuntimeError, match="isolated outbox rejected"):
        async with session.atomic():
            await append(session)
    assert not session.stored and not session.audits and not session.outbox
    session.reject_outbox = False
    async with session.atomic():
        receipt = await append(session)
    assert receipt.sequence_no == 1
    assert len(session.stored) == len(session.audits) == len(session.outbox) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["audits", "outbox"])
async def test_replay_does_not_hide_missing_original_audit_or_outbox(missing):
    session = AppendSession()
    await append(session)
    getattr(session, missing).clear()
    with pytest.raises(OrbitError) as error:
        await append(session)
    assert error.value.code == "EXECUTION_LEASE_SOURCE_UNVERIFIED"


@pytest.mark.asyncio
async def test_future_observation_or_future_recorded_time_cannot_be_replayed():
    session = AppendSession()
    with pytest.raises(OrbitError):
        await append(
            session,
            fact(binding=session.binding, occurred_at=session.now + timedelta(microseconds=1)),
        )
    assert not session.writes
    await append(session)
    session.now = NOW - timedelta(days=1)
    with pytest.raises(OrbitError):
        await append(session)


@pytest.mark.asyncio
async def test_sequence_exhaustion_does_not_wrap_or_add_partial_rows():
    session = AppendSession()
    session.tail_override = MAX_ATTEMPT
    with pytest.raises(OrbitError) as error:
        await append(session)
    assert error.value.code == "EXECUTION_FACT_SEQUENCE_EXHAUSTED"
    assert not session.writes


def test_precision_candidate_only_expands_two_fact_columns_and_keeps_not_null():
    sql = (
        Path(__file__).resolve().parents[2]
        / "docs/orbit/sql-drafts/050_execution_fact_microseconds_candidate.sql"
    ).read_text(encoding="utf-8")
    assert sql.count("ALTER TABLE") == 1
    assert sql.count("MODIFY COLUMN") == 2
    assert sql.count("DATETIME(6) NOT NULL COMMENT") == 2
    assert "DROP " not in sql and "UPDATE " not in sql and "CREATE " not in sql
