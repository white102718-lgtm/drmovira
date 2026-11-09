"""窄恢复Store真实SQL只读专项；技术authority不代表Meta/设备或平台写权限。"""

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import UTC, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

from sqlalchemy import URL, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_lease_contract import (
    AttemptBinding,
    AttemptFact,
    EvidenceSource,
    FactKind,
    SendPhase,
)
from orbit_api.launch_execution_lease_store import (
    ExecutionLeaseAuthority,
    ExecutionLeaseStore,
    FactValidationReceipt,
    LeaseAuthorityGrant,
    LeaseOperation,
    RuntimeExpectation,
)

if __package__:
    from .launch_execution_fixture import create_protocol_plan
    from .launch_execution_lease_checks import guard_execution_lease_target
else:
    from launch_execution_fixture import create_protocol_plan
    from launch_execution_lease_checks import guard_execution_lease_target

EXECUTION_LEASE_STORE_CASES = [
    "pythonExecutionLeaseStoreDefaultAuthorityFailsBeforeSql",
    "pythonExecutionLeaseStoreActualAcceptedSourceAndExpiredCurrentHeadReadOnly",
    "pythonExecutionLeaseStoreExpectedRevisionFenceClaimWorkerExactCas",
    "pythonExecutionLeaseStoreActual288FactsAndLateIntentThreeReadbackConflicts",
    "pythonExecutionLeaseStoreOldRrSnapshotUsesCurrentTaskPreparationAndHead",
    "pythonExecutionLeaseStoreActualSequenceKeysetExplain",
    "pythonExecutionLeaseStoreCommandLockActuallyBlocksConcurrentFactAppend",
]
EXECUTION_FACT_APPEND_CASES = [
    "pythonExecutionFactAppendExactMicrosecondsAndOriginalReplayAcrossSqlSecond",
    "pythonExecutionFactAppendLateOldFenceLeavesAllCurrentFieldsUnchanged",
    "pythonExecutionFactAppendActualOutbox1644RollbackAndSameEventRetry",
    "pythonExecutionFactAppendConcurrentSameEventReturnsOneReceiptAndAudit",
]


class IsolatedLeaseEvidenceAuthority(ExecutionLeaseAuthority):
    """只允许本轮UUID库及固定证据字典；绝不注册生产、不授发送权。"""

    def __init__(self, database, bindings, evidence):
        self.database = database
        self.bindings = MappingProxyType(dict(bindings))
        self.evidence = MappingProxyType(evidence)
        self.verified = 0

    async def authorize(self, session, actor_id, binding, operation):
        # AsyncSession可绑定AsyncEngine或固定AsyncConnection；同步bind统一经engine取URL。
        url = session.get_bind().engine.url
        try:
            guard_execution_lease_target(url, self.database)
        except ValueError:
            raise OrbitError(
                503, "ISOLATED_LEASE_AUTHORITY_REJECTED", "仅允许本轮SQL技术证据"
            ) from None
        if (
            url.host != "127.0.0.1"
            or url.port != 13306
            or url.database != self.database
            or self.bindings.get(binding.node_id) != binding
            or actor_id != binding.actor_id
            or operation not in {LeaseOperation.RECOVER_EXPIRED, LeaseOperation.HISTORICAL_FACT}
        ):
            raise OrbitError(503, "ISOLATED_LEASE_AUTHORITY_REJECTED", "仅允许本轮SQL技术证据")
        actual = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
        if actual != self.database:
            raise OrbitError(503, "ISOLATED_LEASE_AUTHORITY_REJECTED", "仅允许本轮SQL技术证据")
        return LeaseAuthorityGrant(actor_id, binding, operation)

    async def verify_fact(self, session, fact, *, recorded_at):
        known = self.evidence.get(fact.event_id)
        if known is None or hashlib.sha256(known).hexdigest() != fact.evidence_sha256:
            raise OrbitError(503, "ISOLATED_LEASE_EVIDENCE_REJECTED", "真实技术样本未匹配")
        document = json.loads(known)
        expected = evidence_document(
            fact.binding,
            fact.event_id,
            fact.kind,
            fact.phase,
            fact.source,
            fact.occurred_at,
            fact.external_id,
        )
        if document != expected or known != canonical(expected).encode():
            raise OrbitError(503, "ISOLATED_LEASE_EVIDENCE_REJECTED", "真实技术样本未匹配")
        self.verified += 1
        return FactValidationReceipt.for_fact(fact, recorded_at=recorded_at)


def evidence_document(binding, identifier, kind, phase, source, occurred_at, external_id):
    return {
        "fixture": "ISOLATED_SQL_NOT_PLATFORM_AUTHORITY",
        "tenant": binding.tenant_id,
        "task": binding.task_id,
        "node": binding.node_id,
        "command_hash": binding.command_hash,
        "manifest_hash": binding.manifest_hash,
        "source_hash": binding.source_hash,
        "attempt": binding.attempt_no,
        "fence": binding.fencing_token,
        "claim": binding.claim_id,
        "worker": binding.worker_id,
        "event": identifier,
        "kind": kind.value,
        "phase": phase.value,
        "source": source.value,
        "occurred_at": occurred_at.isoformat(),
        "external_id": external_id,
        "fixture_observation": {
            "classification": kind.value,
            "request_correlation": "fixture-operation:" + identifier,
            "submitted": kind not in {FactKind.PROVED_NOT_SENT, FactKind.WRITE_INTENT},
            "platform_object": external_id,
        },
    }


async def append_with_owned_connection(engine, store, record, *, replay_clock=None):
    """会话时钟只影响本次独占物理连接；commit后不能转投另一个池连接。"""
    async with engine.connect() as connection:
        original_id = None
        try:
            if replay_clock is not None:
                from datetime import datetime

                original_id = (
                    await connection.execute(text("SELECT CONNECTION_ID()"))
                ).scalar_one()
                delta = replay_clock - datetime(1970, 1, 1, tzinfo=UTC)
                timestamp = (
                    Decimal(delta.days * 86400 + delta.seconds)
                    + Decimal(delta.microseconds) / 1000000
                )
                await connection.execute(text("SET SESSION timestamp=:value"), {"value": timestamp})
                await connection.commit()  # 只提交SET，显式Connection仍持同一物理连接。
            async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                async with session.begin():
                    if replay_clock is not None:
                        current_id = (
                            await session.execute(text("SELECT CONNECTION_ID()"))
                        ).scalar_one()
                        actual = (
                            await session.execute(text("SELECT UTC_TIMESTAMP(6)"))
                        ).scalar_one()
                        crossed = isinstance(actual, datetime) and actual.replace(
                            tzinfo=UTC
                        ).replace(microsecond=0) > (replay_clock - timedelta(seconds=2)).replace(
                            microsecond=0
                        )
                        if current_id != original_id or not crossed:
                            print(
                                json.dumps(
                                    {
                                        "scope": "execution-fact-fixture",
                                        "phase": "session-clock-mismatch",
                                        "connection_before": original_id,
                                        "connection_after": current_id,
                                        "expected_type": type(replay_clock).__name__,
                                        "expected_time": replay_clock.isoformat(),
                                        "actual_type": type(actual).__name__,
                                        "actual_time": actual.isoformat()
                                        if isinstance(actual, datetime)
                                        else None,
                                    }
                                ),
                                flush=True,
                            )
                        assert current_id == original_id and crossed
                    return await store.append_verified_fact(session, 1, record, str(uuid4()))
        finally:
            if replay_clock is not None:
                try:
                    if original_id is None:
                        raise AssertionError("OWNED_CONNECTION_ID_UNVERIFIED")
                    if connection.in_transaction():
                        await connection.rollback()
                    reset_id = (
                        await connection.execute(text("SELECT CONNECTION_ID()"))
                    ).scalar_one()
                    assert reset_id == original_id
                    await connection.execute(text("SET SESSION timestamp=0"))
                    await connection.commit()
                except BaseException:
                    # 无法确认原连接归零时丢弃连接，不能将带测试时钟的会话归还池。
                    await connection.invalidate()
                    raise


def run_execution_lease_store_checks(
    client, admin, headers, password, cache, database, cases, *, include_append=False
):
    guard_execution_lease_target(admin, database)
    if type(include_append) is not bool:
        raise ValueError("追加专项必须显式布尔开关")

    def query(sql, values=()):
        with admin.cursor() as cursor:
            cursor.execute(sql, values)
            result = cursor.fetchall()
        admin.commit()
        return result

    def execute(sql, values=()):
        with admin.cursor() as cursor:
            cursor.execute(sql, values)
            return cursor.rowcount

    def checked(response, status):
        assert response.status_code == status, {
            "expected_status": status,
            "actual_status": response.status_code,
        }
        return response.json()

    assert query("SELECT DATABASE()")[0][0] == database
    if include_append:
        migration = (
            Path(__file__).resolve().parents[1]
            / "python/orbit_api/migrations"
            / "050_execution_fact_microseconds.sql"
        )
        sql = migration.read_text(encoding="utf-8")
        assert "MODIFY COLUMN occurred_at DATETIME(6) NOT NULL" in sql
        assert "MODIFY COLUMN recorded_at DATETIME(6) NOT NULL" in sql
        assert dict(
            query(
                "SELECT COLUMN_NAME,DATETIME_PRECISION FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='orbit_execution_attempt_fact' "
                "AND COLUMN_NAME IN('occurred_at','recorded_at')"
            )
        ) == {"occurred_at": 6, "recorded_at": 6}
    tenant, owner, team = query(
        "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1"
    )[0]
    capabilities = checked(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)

    def write(revision):
        return headers | {
            "X-CSRF-Token": capabilities["csrf_token"],
            "If-Match": f'"{revision}"',
            "Idempotency-Key": str(uuid4()),
        }

    def validated_plan():
        item = create_protocol_plan(admin, tenant, owner, team)
        result = checked(
            client.post(
                f"/api/v1/launch-plans/{item['id']}/validate", headers=write(1), json=item["body"]
            ),
            200,
        )
        assert result["valid"] and result["hash"]
        return item, result

    bindings, evidence, timestamps = {}, {}, {}

    def accept_and_seed(item, validation, *, count=4):
        task = checked(
            client.post(
                f"/api/v1/launch-plans/{item['id']}/execute",
                headers=write(2),
                json={"hash": validation["hash"], "activate_ack": False},
            ),
            202,
        )
        assert task["state"] == "QUEUED" and task["revision"] == 1
        prep = query(
            "SELECT id,manifest_hash,payload_hash,authorization_fingerprint,actor_id,subject_id,"
            "auth_version FROM orbit_launch_execution_preparation WHERE tenant_id=%s "
            "AND task_id=%s AND state='ACCEPTED'",
            (tenant, task["id"]),
        )[0]
        commands = query(
            "SELECT node_id,resolved_configuration_hash FROM orbit_launch_execution_command "
            "WHERE tenant_id=%s AND task_id=%s ORDER BY ordinal LIMIT %s",
            (tenant, task["id"], count),
        )
        assert len(commands) == count
        assert query(
            "SELECT manifest_phase,node_count,expected_node_count FROM orbit_task WHERE "
            "tenant_id=%s AND id=%s",
            (tenant, task["id"]),
        )[0] == ("COMPLETE", task["node_count"], task["node_count"])
        now = query("SELECT UTC_TIMESTAMP(3)")[0][0].replace(tzinfo=UTC)
        chosen = []
        admin.begin()
        try:
            # 只为读取协议构造运行技术样本；不是Worker领取或实际发出命令。
            for node, command_hash in commands:
                attempt = AttemptBinding(
                    tenant,
                    task["id"],
                    node,
                    prep[0],
                    str(uuid4()),
                    str(uuid4()),
                    1,
                    1,
                    command_hash,
                    prep[1],
                    prep[2],
                    hashlib.sha256(canonical(["ISOLATED_SQL_NOT_SEND", node]).encode()).hexdigest(),
                    prep[3],
                    task["execution_mode"],
                    prep[4],
                    prep[5],
                    owner,
                    team,
                    prep[6],
                )
                execute(
                    "INSERT INTO orbit_execution_attempt(tenant_id,task_id,node_id,preparation_id,"
                    "attempt_no,fencing_token,claim_id,worker_id,execution_mode,command_hash,"
                    "manifest_hash,source_hash,authority_hash,authorization_hash,actor_id,subject_id,"
                    "owner_user_id,owner_team_id,auth_version,created_at) VALUES("
                    "%s,%s,%s,%s,1,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        tenant,
                        task["id"],
                        node,
                        prep[0],
                        attempt.claim_id,
                        attempt.worker_id,
                        attempt.execution_mode,
                        command_hash,
                        prep[1],
                        prep[2],
                        attempt.authority_hash,
                        prep[3],
                        prep[4],
                        prep[5],
                        owner,
                        team,
                        prep[6],
                        (now - timedelta(minutes=2)).replace(tzinfo=None),
                    ),
                )
                execute(
                    "INSERT INTO orbit_execution_command_runtime(tenant_id,task_id,node_id,"
                    "revision,"
                    "active_attempt,fencing_token,claim_id,worker_id,lease_expires_at,created_at,"
                    "updated_at) VALUES(%s,%s,%s,1,1,1,%s,%s,%s,%s,%s)",
                    (
                        tenant,
                        task["id"],
                        node,
                        attempt.claim_id,
                        attempt.worker_id,
                        (now - timedelta(seconds=1)).replace(tzinfo=None),
                        (now - timedelta(minutes=2)).replace(tzinfo=None),
                        now.replace(tzinfo=None),
                    ),
                )
                execute(
                    "UPDATE orbit_launch_execution_command SET state='RUNNING',attempt=1,"
                    "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                    (tenant, task["id"], node),
                )
                execute(
                    "UPDATE orbit_task_node SET state='RUNNING',attempt=1,"
                    "updated_at=UTC_TIMESTAMP(3) "
                    "WHERE tenant_id=%s AND task_id=%s AND id=%s",
                    (tenant, task["id"], node),
                )
                bindings[node] = attempt
                timestamps[node] = now - timedelta(seconds=1)
                chosen.append(attempt)
            admin.commit()
        except BaseException:
            admin.rollback()
            raise
        return task, chosen

    fact_sql = (
        "INSERT INTO orbit_execution_attempt_fact(tenant_id,task_id,node_id,attempt_no,"
        "fencing_token,"
        "claim_id,worker_id,event_id,sequence_no,fact_kind,send_phase,evidence_source,evidence_sha256,"
        "external_id,occurred_at,recorded_at) VALUES(%s,%s,%s,1,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
        "UTC_TIMESTAMP(3))"
    )

    def fact_parameters(attempt, sequence, kind):
        identifier = str(uuid4())
        phase, source = {
            FactKind.PROVED_NOT_SENT: (
                SendPhase.BEFORE_DISPATCH,
                EvidenceSource.TRANSPORT_PROVEN_NO_SEND,
            ),
            FactKind.WRITE_INTENT: (SendPhase.BEFORE_DISPATCH, EvidenceSource.LOCAL_INTENT),
            FactKind.READBACK_SUCCEEDED: (SendPhase.READBACK, EvidenceSource.PLATFORM_READBACK),
            FactKind.READBACK_REJECTED: (SendPhase.READBACK, EvidenceSource.PLATFORM_READBACK),
            FactKind.READBACK_INCONCLUSIVE: (SendPhase.READBACK, EvidenceSource.PLATFORM_READBACK),
        }[kind]
        occurred = timestamps[attempt.node_id]
        external = "123456" if kind is FactKind.READBACK_SUCCEEDED else None
        document = canonical(
            evidence_document(attempt, identifier, kind, phase, source, occurred, external)
        ).encode()
        evidence[identifier] = document
        return (
            tenant,
            attempt.task_id,
            attempt.node_id,
            attempt.claim_id,
            attempt.worker_id,
            identifier,
            sequence,
            kind.value,
            phase.value,
            source.value,
            hashlib.sha256(document).hexdigest(),
            external,
            occurred.replace(tzinfo=None),
        )

    def add_facts(attempt, begin, end, kind):
        rows = [fact_parameters(attempt, seq, kind) for seq in range(begin, end + 1)]
        admin.begin()
        try:
            with admin.cursor() as cursor:
                cursor.executemany(fact_sql, rows)
            admin.commit()
        except BaseException:
            admin.rollback()
            raise

    item, validation = validated_plan()
    task, chosen = accept_and_seed(item, validation)
    add_facts(chosen[0], 1, 1, FactKind.PROVED_NOT_SENT)

    def credential(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=credential(admin.user),
        password=credential(admin.password),
        host="127.0.0.1",
        port=13306,
        database=database,
    )

    def expected(attempt):
        return RuntimeExpectation(1, 1, 1, attempt.claim_id, attempt.worker_id)

    async def internal():
        engine = create_async_engine(
            url, echo=False, hide_parameters=True, isolation_level="REPEATABLE READ"
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        sql_count = [0]

        def counted(*_args):
            sql_count[0] += 1

        event.listen(engine.sync_engine, "before_cursor_execute", counted)
        try:
            async with sessions() as session, session.begin():
                before = sql_count[0]
                try:
                    await ExecutionLeaseStore().capture_recovery(
                        session, 1, chosen[0], expected(chosen[0])
                    )
                except OrbitError as error:
                    assert error.code == "EXECUTION_LEASE_AUTHORITY_UNAVAILABLE"
                else:
                    raise AssertionError("DEFAULT_AUTHORITY_MUST_DENY")
                assert sql_count[0] == before
            cases.append(EXECUTION_LEASE_STORE_CASES[0])

            authority = IsolatedLeaseEvidenceAuthority(database, bindings, evidence)
            store = ExecutionLeaseStore(authority)

            async def captured(attempt, *, guard=None):
                async with sessions() as session, session.begin():
                    result = await store.capture_recovery(
                        session, 1, attempt, guard or expected(attempt)
                    )
                    return result.summary, result.decision(session)

            summary, decision = await captured(chosen[0])
            assert summary.total_count == 1 and decision.state_path == ("RUNNING", "FAILED")
            assert decision.retryable
            cases.append(EXECUTION_LEASE_STORE_CASES[1])

            for changes in (
                {"revision": 2},
                {"attempt_no": 2},
                {"fencing_token": 2},
                {"claim_id": str(uuid4())},
                {"worker_id": str(uuid4())},
            ):
                try:
                    await captured(chosen[0], guard=replace(expected(chosen[0]), **changes))
                except OrbitError as error:
                    assert error.status == 409 and error.code == "EXECUTION_LEASE_STALE"
                else:
                    raise AssertionError("EXPECTED_HEAD_MUST_MATCH")
            cases.append(EXECUTION_LEASE_STORE_CASES[2])

            add_facts(chosen[0], 2, 288, FactKind.PROVED_NOT_SENT)
            add_facts(chosen[0], 289, 289, FactKind.WRITE_INTENT)
            summary, decision = await captured(chosen[0])
            assert summary.total_count == 289 and len(summary.representatives) == 2
            assert decision.state_path[-1] == "UNKNOWN" and not decision.retryable
            for attempt, kind in zip(
                chosen[1:],
                (
                    FactKind.READBACK_SUCCEEDED,
                    FactKind.READBACK_REJECTED,
                    FactKind.READBACK_INCONCLUSIVE,
                ),
                strict=True,
            ):
                add_facts(attempt, 1, 288, FactKind.PROVED_NOT_SENT)
                add_facts(attempt, 289, 289, kind)
                summary, decision = await captured(attempt)
                assert summary.total_count == 289 and len(summary.representatives) == 2
                assert decision.code == "SEND_EVIDENCE_CONFLICT" and not decision.retryable
            cases.append(EXECUTION_LEASE_STORE_CASES[3])

            async with sessions() as old, old.begin():
                await old.execute(text("SELECT COUNT(*) FROM orbit_launch_execution_preparation"))
                second_item, second_validation = validated_plan()
                second_task, second_chosen = accept_and_seed(
                    second_item, second_validation, count=1
                )
                second_attempt = second_chosen[0]
                add_facts(second_attempt, 1, 1, FactKind.PROVED_NOT_SENT)
                old_state = (
                    await old.execute(
                        text(
                            "SELECT state FROM orbit_launch_execution_preparation "
                            "WHERE tenant_id=:tenant AND id=:id"
                        ),
                        {"tenant": tenant, "id": second_attempt.preparation_id},
                    )
                ).scalar_one_or_none()
                assert old_state is None  # 实际旧RR快照不见后来ACCEPTED；不是mock旧状态。
                second_authority = IsolatedLeaseEvidenceAuthority(database, bindings, evidence)
                result = await ExecutionLeaseStore(second_authority).capture_recovery(
                    old, 1, second_attempt, expected(second_attempt)
                )
                assert result.summary.total_count == 1 and result.decision(old).retryable
                assert second_task["id"] == second_attempt.task_id
            cases.append(EXECUTION_LEASE_STORE_CASES[4])

            with admin.cursor() as cursor:
                cursor.execute(
                    "EXPLAIN SELECT sequence_no,fact_kind FROM orbit_execution_attempt_fact "
                    "WHERE tenant_id=%s AND task_id=%s AND node_id=%s AND attempt_no=1 "
                    "AND sequence_no>200 ORDER BY sequence_no LIMIT 200",
                    (tenant, chosen[0].task_id, chosen[0].node_id),
                )
                plan = dict(
                    zip(
                        (column[0] for column in cursor.description), cursor.fetchone(), strict=True
                    )
                )
            admin.commit()
            assert plan["key"] == "uq_exec_fact_sequence"
            assert "filesort" not in str(plan["Extra"]).lower()
            cases.append(EXECUTION_LEASE_STORE_CASES[5])

            waiting = asyncio.Event()
            writer_id = []
            params = fact_parameters(chosen[0], 290, FactKind.READBACK_INCONCLUSIVE)
            writer = None

            async def append_with_command_lock():
                async with sessions() as peer, peer.begin():
                    writer_id.append(
                        (await peer.execute(text("SELECT CONNECTION_ID()"))).scalar_one()
                    )
                    waiting.set()
                    await peer.execute(
                        text(
                            "SELECT node_id FROM orbit_launch_execution_command "
                            "WHERE tenant_id=:tenant "
                            "AND task_id=:task AND node_id=:node FOR UPDATE"
                        ),
                        {"tenant": tenant, "task": chosen[0].task_id, "node": chosen[0].node_id},
                    )
                    # 明确技术SQL追加，尚无生产append API；与command锁协议保持一致。
                    columns = (
                        "tenant_id,task_id,node_id,claim_id,worker_id,event_id,sequence_no,fact_kind,"
                        "send_phase,evidence_source,evidence_sha256,external_id,occurred_at"
                    )
                    keys = [f"v{n}" for n in range(len(params))]
                    await peer.execute(
                        text(
                            "INSERT INTO orbit_execution_attempt_fact(" + columns + ",attempt_no,"
                            "fencing_token,recorded_at) VALUES("
                            + ",".join(":" + key for key in keys)
                            + ",1,1,UTC_TIMESTAMP(3))"
                        ),
                        dict(zip(keys, params, strict=True)),
                    )

            try:
                async with sessions() as holder, holder.begin():
                    result = await store.capture_recovery(holder, 1, chosen[0], expected(chosen[0]))
                    assert result.summary.total_count == 289
                    writer = asyncio.create_task(append_with_command_lock())
                    await asyncio.wait_for(waiting.wait(), 5)
                    async with asyncio.timeout(5):
                        while not query(
                            "SELECT COUNT(*) FROM performance_schema.data_lock_waits w "
                            "JOIN performance_schema.threads t ON "
                            "t.THREAD_ID=w.REQUESTING_THREAD_ID "
                            "JOIN performance_schema.data_locks d ON "
                            "d.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID "
                            "WHERE t.PROCESSLIST_ID=%s AND d.OBJECT_SCHEMA=%s "
                            "AND d.OBJECT_NAME='orbit_launch_execution_command'",
                            (writer_id[0], database),
                        )[0][0]:
                            assert not writer.done()
                            await asyncio.sleep(0.02)
                    assert not writer.done()
                    assert (
                        query(
                            "SELECT COUNT(*) FROM orbit_execution_attempt_fact WHERE tenant_id=%s "
                            "AND task_id=%s AND node_id=%s",
                            (tenant, task["id"], chosen[0].node_id),
                        )[0][0]
                        == 289
                    )
                await asyncio.wait_for(writer, 5)
                summary, decision = await captured(chosen[0])
                assert summary.total_count == 290 and not decision.retryable
            finally:
                if writer is not None:
                    if not writer.done():
                        writer.cancel()
                    await asyncio.gather(writer, return_exceptions=True)
            cases.append(EXECUTION_LEASE_STORE_CASES[6])

            if include_append:
                from sqlalchemy.exc import DBAPIError

                def append_fact(attempt, microsecond=123499):
                    base = query("SELECT UTC_TIMESTAMP(6)")[0][0].replace(tzinfo=UTC)
                    occurred = (base - timedelta(minutes=2)).replace(
                        second=59, microsecond=microsecond
                    )
                    identifier = str(uuid4())
                    kind = FactKind.PROVED_NOT_SENT
                    phase, source = (
                        SendPhase.BEFORE_DISPATCH,
                        EvidenceSource.TRANSPORT_PROVEN_NO_SEND,
                    )
                    document = canonical(
                        evidence_document(attempt, identifier, kind, phase, source, occurred, None)
                    ).encode()
                    evidence[identifier] = document
                    return AttemptFact(
                        attempt,
                        identifier,
                        kind,
                        phase,
                        source,
                        hashlib.sha256(document).hexdigest(),
                        occurred,
                    )

                async def appended(record, *, replay_clock=None):
                    return await append_with_owned_connection(
                        engine, store, record, replay_clock=replay_clock
                    )

                def current_snapshot(attempt):
                    args = (tenant, attempt.task_id, attempt.node_id)
                    return (
                        query(
                            "SELECT * FROM orbit_execution_command_runtime "
                            "WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                            args,
                        ),
                        query(
                            "SELECT * FROM orbit_launch_execution_command "
                            "WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                            args,
                        ),
                        query(
                            "SELECT * FROM orbit_task_node "
                            "WHERE tenant_id=%s AND task_id=%s AND id=%s",
                            args,
                        ),
                        query("SELECT * FROM orbit_task WHERE tenant_id=%s AND id=%s", args[:2]),
                        query("SELECT revision FROM orbit_task_clock WHERE tenant_id=%s", args[:1]),
                        query(
                            "SELECT COUNT(*) FROM orbit_task_event "
                            "WHERE tenant_id=%s AND task_id=%s",
                            args[:2],
                        ),
                    )

                def counts(attempt):
                    args = (tenant, attempt.task_id)
                    return tuple(
                        query(
                            "SELECT COUNT(*) FROM " + table + " WHERE tenant_id=%s AND task_id=%s",
                            args,
                        )[0][0]
                        for table in (
                            "orbit_execution_attempt_fact",
                            "orbit_task_audit",
                            "orbit_task_outbox",
                        )
                    )

                baseline = current_snapshot(chosen[0])
                before_counts = counts(chosen[0])
                first_record = None
                for microsecond in (123499, 123500, 999999):
                    record = append_fact(chosen[0], microsecond)
                    receipt = await appended(record)
                    saved = query(
                        "SELECT occurred_at,recorded_at FROM orbit_execution_attempt_fact "
                        "WHERE tenant_id=%s AND event_id=%s",
                        (tenant, record.event_id),
                    )[0]
                    assert saved == (
                        record.occurred_at.replace(tzinfo=None),
                        receipt.recorded_at.replace(tzinfo=None),
                    )
                    assert saved[0].microsecond == microsecond
                    replay = await appended(
                        record, replay_clock=receipt.recorded_at + timedelta(seconds=2)
                    )
                    assert replay == receipt
                    first_record = first_record or record
                try:
                    await appended(replace(first_record, evidence_sha256="f" * 64))
                except OrbitError as error:
                    assert error.status == 409 and error.code == "EXECUTION_FACT_CONFLICT"
                else:
                    raise AssertionError("SAME_EVENT_DIFFERENT_BODY_MUST_CONFLICT")
                assert counts(chosen[0]) == tuple(value + 3 for value in before_counts)
                assert current_snapshot(chosen[0]) == baseline
                cases.append(EXECUTION_FACT_APPEND_CASES[0])

                current = replace(
                    chosen[0],
                    attempt_no=2,
                    fencing_token=2,
                    claim_id=str(uuid4()),
                    worker_id=str(uuid4()),
                )
                from dataclasses import asdict

                fields = asdict(current)
                admin.begin()
                try:
                    execute(
                        "INSERT INTO orbit_execution_attempt("
                        + ",".join(fields)
                        + ",created_at) VALUES("
                        + ",".join("%(" + name + ")s" for name in fields)
                        + ",UTC_TIMESTAMP(3))",
                        fields,
                    )
                    execute(
                        "UPDATE orbit_execution_command_runtime SET revision=revision+1,"
                        "active_attempt=2,fencing_token=2,claim_id=%s,worker_id=%s,"
                        "lease_expires_at=NULL,updated_at=UTC_TIMESTAMP(3) "
                        "WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                        (
                            current.claim_id,
                            current.worker_id,
                            tenant,
                            current.task_id,
                            current.node_id,
                        ),
                    )
                    for table, id_column in (
                        ("orbit_launch_execution_command", "node_id"),
                        ("orbit_task_node", "id"),
                    ):
                        execute(
                            "UPDATE "
                            + table
                            + " SET state='SUCCEEDED',attempt=2,updated_at=UTC_TIMESTAMP(3) "
                            "WHERE tenant_id=%s AND task_id=%s AND " + id_column + "=%s",
                            (tenant, current.task_id, current.node_id),
                        )
                    admin.commit()
                except BaseException:
                    admin.rollback()
                    raise
                baseline = current_snapshot(current)
                late = append_fact(chosen[0], 123500)
                await appended(late)
                assert query(
                    "SELECT attempt_no,fencing_token,claim_id FROM orbit_execution_attempt_fact "
                    "WHERE tenant_id=%s AND event_id=%s",
                    (tenant, late.event_id),
                )[0] == (1, 1, chosen[0].claim_id)
                assert current_snapshot(current) == baseline
                cases.append(EXECUTION_FACT_APPEND_CASES[1])

                record = append_fact(chosen[1], 999999)
                baseline = current_snapshot(chosen[1])
                before_counts = counts(chosen[1])
                trigger = "it_fact_append_outbox_" + uuid4().hex[:12]
                try:
                    execute(
                        f"CREATE TRIGGER {trigger} BEFORE INSERT ON orbit_task_outbox FOR EACH ROW "
                        f"BEGIN IF NEW.task_id='{task['id']}' THEN SIGNAL SQLSTATE '45000' "
                        "SET MESSAGE_TEXT='ISOLATED_FACT_OUTBOX_REJECTED'; END IF; END"
                    )
                    admin.commit()
                    try:
                        await appended(record)
                    except DBAPIError as error:
                        assert error.orig.args[0] == 1644
                    else:
                        raise AssertionError("OUTBOX_1644_MUST_ROLLBACK")
                    assert current_snapshot(chosen[1]) == baseline
                    assert counts(chosen[1]) == before_counts
                    assert (
                        query(
                            "SELECT COUNT(*) FROM orbit_execution_attempt_fact WHERE tenant_id=%s "
                            "AND event_id=%s",
                            (tenant, record.event_id),
                        )[0][0]
                        == 0
                    )
                finally:
                    admin.rollback()
                    execute(f"DROP TRIGGER IF EXISTS {trigger}")
                    admin.commit()
                receipt = await appended(record)
                assert receipt.event_id == record.event_id
                assert counts(chosen[1]) == tuple(value + 1 for value in before_counts)
                assert current_snapshot(chosen[1]) == baseline
                cases.append(EXECUTION_FACT_APPEND_CASES[2])

                record = append_fact(chosen[2], 123499)
                baseline = current_snapshot(chosen[2])
                before_counts = counts(chosen[2])
                contenders = [asyncio.create_task(appended(record)) for _ in range(2)]
                try:
                    receipts = await asyncio.wait_for(asyncio.gather(*contenders), 10)
                    assert receipts[0] == receipts[1]
                    assert counts(chosen[2]) == tuple(value + 1 for value in before_counts)
                    assert current_snapshot(chosen[2]) == baseline
                finally:
                    for contender in contenders:
                        if not contender.done():
                            contender.cancel()
                    await asyncio.gather(*contenders, return_exceptions=True)
                cases.append(EXECUTION_FACT_APPEND_CASES[3])
        finally:
            await engine.dispose()

    asyncio.run(internal())
    return {
        "lease_store_cases": len(EXECUTION_LEASE_STORE_CASES),
        "fact_append_cases": len(EXECUTION_FACT_APPEND_CASES) if include_append else 0,
        "claim_count": 0,
        "send_count": 0,
    }
