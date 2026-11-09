"""052窄恢复真实SQL专项；原202完整来源+隔离技术事实，零领取/发送。"""

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import UTC, timedelta
from uuid import uuid4

from pymysql import MySQLError
from sqlalchemy import URL, event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
    ExecutionLeaseStore,
    RuntimeExpectation,
    fact_chain_seed,
    fact_chain_step,
)
from orbit_api.launch_execution_recovery_store import ExecutionRecoveryStore
from orbit_api.task_event_store import TaskEventStore

if __package__:
    from .launch_execution_fixture import create_protocol_plan
    from .launch_execution_lease_checks import guard_execution_lease_target
    from .launch_execution_lease_store_checks import (
        IsolatedLeaseEvidenceAuthority,
        evidence_document,
    )
else:
    from launch_execution_fixture import create_protocol_plan
    from launch_execution_lease_checks import guard_execution_lease_target
    from launch_execution_lease_store_checks import (
        IsolatedLeaseEvidenceAuthority,
        evidence_document,
    )

RECOVERY_COMMIT_CASES = [
    "pythonRecovery052ActualSchemaAndDefaultAuthorityZeroSql",
    "pythonRecovery052ProvenNotSentAtomicFailedAndCompleteLedger",
    "pythonRecovery052AckPreservesAcceptedVerifyingTwoNodeEvents",
    "pythonRecovery052AcceptedRequiresVerifyingWithoutTaskAggregateSubstitution",
    "pythonRecovery052ExpiredVerifyingBecomesUnknownNoAttemptIncrease",
    "pythonRecovery052AckNotSentAnd289thReadbackConflictFailClosed",
    "pythonRecovery052UnexpiredLeaseNoopLeavesEveryTableUnchanged",
    "pythonRecovery052UnknownFiveMinutesNoopAnd24HourManualOriginalAttempt",
    "pythonRecovery052OtherUnknownManualFlagSurvivesWholeTaskAggregation",
    "pythonRecovery052FiveExpectedFieldsAndCrossTransactionCaptureRejected",
    "pythonRecovery052ConcurrentRecoveryOnlyOneExactCasCommits",
    "pythonRecovery052Outbox1644RollsBackAllTablesAndSameExpectedRetry",
    "pythonRecovery052SealedLedgerImmutableFactRootAndSseCleanupUnblocked",
]


def assert_recovery_schema(query):
    """通配符作为参数，避免PyMySQL把字面百分号当参数格式符。"""
    assert (
        query(
            "SELECT COUNT(*) FROM information_schema.TABLES WHERE "
            "TABLE_SCHEMA=DATABASE() AND TABLE_NAME "
            "IN('orbit_execution_recovery_decision','orbit_execution_recovery_edge')"
        )[0][0]
        == 2
    )
    assert (
        query(
            "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE "
            "TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME LIKE %s",
            ("guard_exec_recovery_%",),
        )[0][0]
        == 6
    )


def run_execution_recovery_checks(client, admin, headers, password, cache, database, cases):
    guard_execution_lease_target(admin, database)

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

    def accept_and_seed(item, validation, *, count=1):
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
                    "manifest_hash,source_hash,authority_hash,authorization_hash,actor_id,"
                    "subject_id,"
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
                        (now - timedelta(days=2)).replace(tzinfo=None),
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
                        (now - timedelta(days=2)).replace(tzinfo=None),
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

    def new_task(*, count=1):
        item, validation = validated_plan()
        task, attempts = accept_and_seed(item, validation, count=count)
        return task, attempts

    def change(attempt, *, state=None, lease_future=False, unknown_age=None, manual=False):
        admin.begin()
        try:
            if state:
                for table, column in [
                    ("orbit_launch_execution_command", "node_id"),
                    ("orbit_task_node", "id"),
                ]:
                    execute(
                        f"UPDATE {table} SET state=%s,updated_at=UTC_TIMESTAMP(3) WHERE "
                        f"tenant_id=%s AND task_id=%s AND {column}=%s",
                        (state, tenant, attempt.task_id, attempt.node_id),
                    )
            if lease_future:
                execute(
                    "UPDATE orbit_execution_command_runtime SET revision=revision+1,"
                    "lease_expires_at=UTC_TIMESTAMP(3)+INTERVAL 1 HOUR,"
                    "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                    (tenant, attempt.task_id, attempt.node_id),
                )
            if unknown_age is not None:
                now = query_no_commit("SELECT UTC_TIMESTAMP(3)")[0][0]
                since = now - timedelta(minutes=unknown_age)
                execute(
                    "UPDATE orbit_execution_command_runtime SET revision=revision+1,"
                    "unknown_since=%s,next_reconcile_at=%s,needs_manual_reconciliation=%s,"
                    "updated_at=%s WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                    (
                        since,
                        since + timedelta(minutes=5),
                        manual,
                        now,
                        tenant,
                        attempt.task_id,
                        attempt.node_id,
                    ),
                )
            admin.commit()
        except BaseException:
            admin.rollback()
            raise

    def query_no_commit(sql, parameters=()):
        with admin.cursor() as cursor:
            cursor.execute(sql, parameters)
            return cursor.fetchall()

    def add(attempt, kinds):
        admin.begin()
        try:
            for sequence, kind in enumerate(kinds, 1):
                phase, source = {
                    FactKind.PROVED_NOT_SENT: (
                        SendPhase.BEFORE_DISPATCH,
                        EvidenceSource.TRANSPORT_PROVEN_NO_SEND,
                    ),
                    FactKind.WRITE_INTENT: (SendPhase.BEFORE_DISPATCH, EvidenceSource.LOCAL_INTENT),
                    FactKind.ACCEPTED: (SendPhase.ACKNOWLEDGED, EvidenceSource.PLATFORM_ACK),
                    FactKind.READBACK_SUCCEEDED: (
                        SendPhase.READBACK,
                        EvidenceSource.PLATFORM_READBACK,
                    ),
                    FactKind.READBACK_REJECTED: (
                        SendPhase.READBACK,
                        EvidenceSource.PLATFORM_READBACK,
                    ),
                    FactKind.READBACK_INCONCLUSIVE: (
                        SendPhase.READBACK,
                        EvidenceSource.PLATFORM_READBACK,
                    ),
                }[kind]
                identifier = str(uuid4())
                occurred = timestamps[attempt.node_id]
                external = "12345" if kind == FactKind.READBACK_SUCCEEDED else None
                document = canonical(
                    evidence_document(attempt, identifier, kind, phase, source, occurred, external)
                ).encode()
                evidence[identifier] = document
                execute(
                    "INSERT INTO orbit_execution_attempt_fact(tenant_id,task_id,node_id,"
                    "attempt_no,fencing_token,claim_id,worker_id,event_id,sequence_no,"
                    "fact_kind,send_phase,evidence_source,evidence_sha256,external_id,"
                    "occurred_at,recorded_at) VALUES(%s,%s,%s,1,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "%s,UTC_TIMESTAMP(6))",
                    (
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
                    ),
                )
            admin.commit()
        except BaseException:
            admin.rollback()
            raise

    def expected(attempt):
        row = query(
            "SELECT revision,active_attempt,fencing_token,claim_id,worker_id FROM "
            "orbit_execution_command_runtime WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
            (tenant, attempt.task_id, attempt.node_id),
        )[0]
        return RuntimeExpectation(*row)

    def snapshot(task_id):
        result = {}
        for table, order in [
            ("orbit_task", "id"),
            ("orbit_task_node", "ordinal"),
            ("orbit_launch_execution_command", "ordinal"),
            ("orbit_execution_command_runtime", "node_id"),
            ("orbit_execution_attempt", "node_id,attempt_no"),
            ("orbit_execution_attempt_fact", "node_id,attempt_no,sequence_no"),
            ("orbit_task_event", "sequence"),
            ("orbit_task_event_cursor", "sequence"),
            ("orbit_task_event_retention", "task_id"),
            ("orbit_task_audit", "id"),
            ("orbit_task_outbox", "audit_id"),
            ("orbit_execution_recovery_decision", "id"),
            ("orbit_execution_recovery_edge", "decision_id,ordinal"),
        ]:
            predicate = "id" if table == "orbit_task" else "task_id"
            result[table] = query(
                f"SELECT * FROM {table} WHERE tenant_id=%s AND {predicate}=%s ORDER BY {order}",
                (tenant, task_id),
            )
        result["clock"] = query(
            "SELECT revision FROM orbit_task_clock WHERE tenant_id=%s", (tenant,)
        )
        return result

    def runtime_identity(attempt):
        return query(
            "SELECT active_attempt,fencing_token,claim_id,worker_id,lease_expires_at,"
            "last_reconciled_at FROM orbit_execution_command_runtime WHERE tenant_id=%s AND "
            "task_id=%s AND node_id=%s",
            (tenant, attempt.task_id, attempt.node_id),
        )[0]

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

    async def internal():
        engine = create_async_engine(
            url, echo=False, hide_parameters=True, isolation_level="REPEATABLE READ"
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        sql_count = [0]

        def counted(*_args):
            sql_count[0] += 1

        event.listen(engine.sync_engine, "before_cursor_execute", counted)

        async def recover(attempt, guard=None):
            guard = guard or expected(attempt)
            async with sessions() as session, session.begin():
                local_store = ExecutionRecoveryStore(
                    IsolatedLeaseEvidenceAuthority(database, bindings, evidence)
                )
                return await local_store.recover_expired(session, 1, attempt, guard, str(uuid4()))

        try:
            assert_recovery_schema(query)
            task, attempts = new_task()
            attempt = attempts[0]
            async with sessions() as session, session.begin():
                before = sql_count[0]
                try:
                    await ExecutionRecoveryStore().recover_expired(
                        session, 1, attempt, expected(attempt), str(uuid4())
                    )
                except OrbitError as error:
                    assert error.code == "EXECUTION_LEASE_AUTHORITY_UNAVAILABLE"
                else:
                    raise AssertionError("DEFAULT_AUTHORITY_MUST_DENY")
                assert sql_count[0] == before
            cases.append(RECOVERY_COMMIT_CASES[0])

            add(attempt, [FactKind.PROVED_NOT_SENT])
            old = snapshot(task["id"])
            identity = runtime_identity(attempt)
            result = await recover(attempt)
            assert result.changed and result.node_state == "FAILED"
            assert runtime_identity(attempt) == identity
            assert query(
                "SELECT state,retryable,error_code,attempt FROM orbit_task_node WHERE "
                "tenant_id=%s AND task_id=%s AND id=%s",
                (tenant, task["id"], attempt.node_id),
            )[0] == ("FAILED", 1, "CONFIRMED_NOT_SENT", 1)
            assert len(snapshot(task["id"])["orbit_task_event"]) == len(old["orbit_task_event"]) + 1
            assert snapshot(task["id"])["clock"][0][0] == old["clock"][0][0] + 1
            assert query(
                "SELECT publication_phase,fact_count,fact_last_sequence,event_count FROM "
                "orbit_execution_recovery_decision WHERE tenant_id=%s AND id=%s",
                (tenant, result.decision_id),
            )[0] == ("SEALED", 1, 1, 1)
            after = snapshot(task["id"])
            for table in ("orbit_task_audit", "orbit_task_outbox", "orbit_task_event_cursor"):
                assert len(after[table]) == len(old[table]) + 1
            assert (
                len(after["orbit_execution_recovery_decision"])
                == len(old["orbit_execution_recovery_decision"]) + 1
            )
            assert (
                len(after["orbit_execution_recovery_edge"])
                == len(old["orbit_execution_recovery_edge"]) + 1
            )
            assert after["orbit_execution_attempt"] == old["orbit_execution_attempt"]
            assert after["orbit_execution_attempt_fact"] == old["orbit_execution_attempt_fact"]
            assert query(
                "SELECT t.revision,d.after_task_revision,r.revision,d.after_runtime_revision,"
                "d.after_task_clock FROM orbit_execution_recovery_decision d JOIN orbit_task t "
                "ON t.tenant_id=d.tenant_id AND t.id=d.task_id JOIN "
                "orbit_execution_command_runtime r ON r.tenant_id=d.tenant_id AND "
                "r.task_id=d.task_id AND r.node_id=d.node_id WHERE d.tenant_id=%s AND d.id=%s",
                (tenant, result.decision_id),
            )[0] == (
                result.task_revision,
                result.task_revision,
                result.runtime_revision,
                result.runtime_revision,
                after["clock"][0][0],
            )
            failed_attempt, failed_result = attempt, result
            cases.append(RECOVERY_COMMIT_CASES[1])

            task, attempts = new_task()
            attempt = attempts[0]
            add(attempt, [FactKind.ACCEPTED])
            old = snapshot(task["id"])
            result = await recover(attempt)
            events = query(
                "SELECT state,task_revision,sequence,node_id FROM orbit_task_event WHERE "
                "tenant_id=%s AND task_id=%s AND sequence>%s ORDER BY sequence",
                (
                    tenant,
                    task["id"],
                    query(
                        "SELECT before_task_sequence FROM orbit_execution_recovery_decision "
                        "WHERE tenant_id=%s AND id=%s",
                        (tenant, result.decision_id),
                    )[0][0],
                ),
            )
            assert [r[0] for r in events] == ["ACCEPTED", "VERIFYING"]
            assert all(r[3] == attempt.node_id for r in events)
            assert events[1][1] == events[0][1] + 1 and events[1][2] == events[0][2] + 1
            assert snapshot(task["id"])["clock"][0][0] == old["clock"][0][0] + 1
            detail = checked(client.get(f"/api/v1/tasks/{task['id']}", headers=headers), 200)
            page = checked(client.get(f"/api/v1/tasks/{task['id']}/nodes", headers=headers), 200)
            assert (
                detail["state"] == result.task_state and detail["revision"] == result.task_revision
            )
            assert (
                next(row for row in page["items"] if row["id"] == attempt.node_id)["state"]
                == "VERIFYING"
            )
            expected_frames = query(
                "SELECT event_id,sequence,task_revision,node_id,state FROM orbit_task_event "
                "WHERE tenant_id=%s AND task_id=%s ORDER BY sequence",
                (tenant, task["id"]),
            )
            with client.stream(
                "GET", f"/api/v1/tasks/{task['id']}/events", headers=headers
            ) as response:
                assert response.status_code == 200
                lines = response.iter_lines()
                try:
                    for expected_frame in expected_frames:
                        assert next(lines) == "id: " + expected_frame[0]
                        line = next(lines)
                        assert line.startswith("data: ")
                        frame = json.loads(line[6:])
                        assert set(frame) == {
                            "event_id",
                            "sequence",
                            "schema_version",
                            "task_id",
                            "task_revision",
                            "node_id",
                            "state",
                            "occurred_at",
                            "request_id",
                        }
                        assert (
                            frame["event_id"],
                            frame["sequence"],
                            frame["task_revision"],
                            frame["node_id"],
                            frame["state"],
                        ) == expected_frame
                        assert (
                            frame["task_id"] == task["id"]
                            and type(frame["sequence"]) is int
                            and frame["schema_version"] == 1
                        )
                        assert next(lines) == ""
                finally:
                    lines.close()
            cases.append(RECOVERY_COMMIT_CASES[2])

            task, attempts = new_task()
            attempt = attempts[0]
            change(attempt, state="ACCEPTED")
            result = await recover(attempt)
            assert result.node_state == "VERIFYING"
            assert query(
                "SELECT node_after_state,task_after_state FROM orbit_execution_recovery_edge "
                "WHERE tenant_id=%s AND decision_id=%s",
                (tenant, result.decision_id),
            )[0] == ("VERIFYING", "VERIFYING")
            cases.append(RECOVERY_COMMIT_CASES[3])

            task, attempts = new_task()
            attempt = attempts[0]
            change(attempt, state="VERIFYING")
            identity = runtime_identity(attempt)
            result = await recover(attempt)
            assert result.node_state == "UNKNOWN" and runtime_identity(attempt) == identity
            cases.append(RECOVERY_COMMIT_CASES[4])

            for kinds in (
                [FactKind.PROVED_NOT_SENT, FactKind.ACCEPTED],
                *[
                    ([FactKind.PROVED_NOT_SENT] * 288) + [kind]
                    for kind in (
                        FactKind.READBACK_SUCCEEDED,
                        FactKind.READBACK_REJECTED,
                        FactKind.READBACK_INCONCLUSIVE,
                    )
                ],
            ):
                task, attempts = new_task()
                attempt = attempts[0]
                add(attempt, kinds)
                result = await recover(attempt)
                assert result.node_state == "UNKNOWN"
                assert query(
                    "SELECT decision_code,fact_count FROM orbit_execution_recovery_decision "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, result.decision_id),
                )[0] == ("SEND_EVIDENCE_CONFLICT", len(kinds))
            cases.append(RECOVERY_COMMIT_CASES[5])

            task, attempts = new_task()
            attempt = attempts[0]
            change(attempt, lease_future=True)
            old = snapshot(task["id"])
            result = await recover(attempt)
            assert not result.changed and snapshot(task["id"]) == old
            cases.append(RECOVERY_COMMIT_CASES[6])

            task, attempts = new_task()
            attempt = attempts[0]
            change(attempt, state="UNKNOWN", unknown_age=6)
            old = snapshot(task["id"])
            identity = runtime_identity(attempt)
            result = await recover(attempt)
            assert not result.changed and snapshot(task["id"]) == old
            change(attempt, state="UNKNOWN", unknown_age=1441)
            identity = runtime_identity(attempt)
            result = await recover(attempt)
            assert result.node_state == "UNKNOWN" and runtime_identity(attempt) == identity
            assert query(
                "SELECT needs_manual_reconciliation,next_reconcile_at FROM "
                "orbit_execution_command_runtime WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                (tenant, task["id"], attempt.node_id),
            )[0] == (1, None)
            assert query(
                "SELECT edge_kind,node_before_state,node_after_state FROM "
                "orbit_execution_recovery_edge WHERE tenant_id=%s AND decision_id=%s",
                (tenant, result.decision_id),
            )[0] == ("MANUAL", "UNKNOWN", "UNKNOWN")
            cases.append(RECOVERY_COMMIT_CASES[7])

            task, attempts = new_task(count=2)
            attempt, other = attempts
            change(other, state="UNKNOWN", unknown_age=1441, manual=True)
            add(attempt, [FactKind.PROVED_NOT_SENT])
            other_before = runtime_identity(other)
            result = await recover(attempt)
            assert result.task_state == "UNKNOWN" and runtime_identity(other) == other_before
            assert (
                query(
                    "SELECT needs_manual_reconciliation FROM orbit_task WHERE tenant_id=%s AND "
                    "id=%s",
                    (tenant, task["id"]),
                )[0][0]
                == 1
            )
            cases.append(RECOVERY_COMMIT_CASES[8])

            task, attempts = new_task()
            attempt = attempts[0]
            old = snapshot(task["id"])
            guard = expected(attempt)
            for changes in (
                {"revision": 2},
                {"attempt_no": 2},
                {"fencing_token": 2},
                {"claim_id": str(uuid4())},
                {"worker_id": str(uuid4())},
            ):
                try:
                    await recover(attempt, replace(guard, **changes))
                except OrbitError as error:
                    assert error.code == "EXECUTION_LEASE_STALE"
                else:
                    raise AssertionError("EXACT_CAS_MUST_DENY")
            async with sessions() as session:
                async with session.begin():
                    captured = await ExecutionLeaseStore(
                        IsolatedLeaseEvidenceAuthority(database, bindings, evidence)
                    ).capture_recovery(session, 1, attempt, guard)
                async with session.begin():
                    try:
                        captured.decision(session)
                    except OrbitError:
                        pass
                    else:
                        raise AssertionError("CROSS_TRANSACTION_CAPTURE_MUST_DENY")
            assert snapshot(task["id"]) == old
            cases.append(RECOVERY_COMMIT_CASES[9])

            task, attempts = new_task()
            attempt = attempts[0]
            guard = expected(attempt)
            tasks = [asyncio.create_task(recover(attempt, guard)) for _ in range(2)]
            try:
                outcomes = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), 15
                )
            finally:
                for pending in tasks:
                    if not pending.done():
                        pending.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            assert sum(not isinstance(r, BaseException) for r in outcomes) == 1
            failure = next(r for r in outcomes if isinstance(r, BaseException))
            assert isinstance(failure, OrbitError) and failure.code == "EXECUTION_LEASE_STALE"
            assert (
                query(
                    "SELECT COUNT(*) FROM orbit_execution_recovery_decision WHERE tenant_id=%s "
                    "AND task_id=%s",
                    (tenant, task["id"]),
                )[0][0]
                == 1
            )
            cases.append(RECOVERY_COMMIT_CASES[10])

            task, attempts = new_task()
            attempt = attempts[0]
            guard = expected(attempt)
            old = snapshot(task["id"])
            trigger = "it_recovery_outbox_" + uuid4().hex[:12]
            execute(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON orbit_task_outbox FOR EACH ROW "
                f"BEGIN IF NEW.task_id='{task['id']}' THEN SIGNAL SQLSTATE '45000' SET "
                f"MESSAGE_TEXT='IT_RECOVERY_ROLLBACK'; END IF; END"
            )
            try:
                try:
                    await recover(attempt, guard)
                except DBAPIError as error:
                    assert error.orig.args[0] == 1644
                else:
                    raise AssertionError("OUTBOX_MUST_FAIL")
                assert snapshot(task["id"]) == old
            finally:
                execute(f"DROP TRIGGER IF EXISTS {trigger}")
            result = await recover(attempt, guard)
            assert result.changed
            cases.append(RECOVERY_COMMIT_CASES[11])

            attempt = failed_attempt
            result = failed_result
            fact_rows = query(
                "SELECT sequence_no,event_id,fact_kind,send_phase,evidence_source,"
                "evidence_sha256,external_id,occurred_at,recorded_at FROM "
                "orbit_execution_attempt_fact WHERE tenant_id=%s AND task_id=%s AND node_id=%s "
                "AND attempt_no=1 ORDER BY sequence_no",
                (tenant, attempt.task_id, attempt.node_id),
            )
            root = fact_chain_seed(attempt)
            for r in fact_rows:
                root = fact_chain_step(
                    root,
                    r[0],
                    AttemptFact(
                        attempt,
                        r[1],
                        FactKind(r[2]),
                        SendPhase(r[3]),
                        EvidenceSource(r[4]),
                        r[5],
                        r[7].replace(tzinfo=UTC),
                        r[6],
                    ),
                    r[8].replace(tzinfo=UTC),
                )
            assert (
                query(
                    "SELECT fact_root_sha256 FROM orbit_execution_recovery_decision WHERE "
                    "tenant_id=%s AND id=%s",
                    (tenant, result.decision_id),
                )[0][0]
                == root.hex()
            )
            for sql, params in [
                (
                    "UPDATE orbit_execution_recovery_decision SET decision_code=decision_code "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, result.decision_id),
                ),
                (
                    "DELETE FROM orbit_execution_recovery_decision WHERE tenant_id=%s AND id=%s",
                    (tenant, result.decision_id),
                ),
                (
                    "UPDATE orbit_execution_recovery_edge SET edge_kind=edge_kind WHERE "
                    "tenant_id=%s AND decision_id=%s",
                    (tenant, result.decision_id),
                ),
                (
                    "DELETE FROM orbit_execution_recovery_edge WHERE tenant_id=%s AND "
                    "decision_id=%s",
                    (tenant, result.decision_id),
                ),
                (
                    "INSERT INTO orbit_execution_recovery_edge SELECT tenant_id,task_id,"
                    "node_id,decision_id,3,UUID(),event_sequence+2,task_revision+2,"
                    "node_before_state,node_after_state,task_after_state,edge_kind,UUID() FROM "
                    "orbit_execution_recovery_edge WHERE tenant_id=%s AND decision_id=%s AND "
                    "ordinal=1",
                    (tenant, result.decision_id),
                ),
            ]:
                admin.begin()
                try:
                    try:
                        execute(sql, params)
                    except MySQLError as error:
                        assert error.args[0] == 1644
                    else:
                        raise AssertionError("SEALED_LEDGER_MUST_REJECT")
                finally:
                    admin.rollback()
            edge_count = query(
                "SELECT COUNT(*) FROM orbit_execution_recovery_edge WHERE tenant_id=%s AND "
                "decision_id=%s",
                (tenant, result.decision_id),
            )[0][0]
            # 明确时间故障fixture后走原内部七日purge，不直接DELETE新事件或DROP约束。
            admin.begin()
            execute(
                "UPDATE orbit_task_event SET occurred_at=UTC_TIMESTAMP(3)-INTERVAL 8 DAY WHERE "
                "tenant_id=%s AND event_id IN(SELECT event_id FROM "
                "orbit_execution_recovery_edge WHERE tenant_id=%s AND decision_id=%s)",
                (tenant, tenant, result.decision_id),
            )
            execute(
                "UPDATE orbit_task_event_cursor SET occurred_at=UTC_TIMESTAMP(3)-INTERVAL 8 "
                "DAY,expires_at=UTC_TIMESTAMP(3)-INTERVAL 1 DAY WHERE tenant_id=%s AND "
                "event_id IN(SELECT event_id FROM orbit_execution_recovery_edge WHERE "
                "tenant_id=%s AND decision_id=%s)",
                (tenant, tenant, result.decision_id),
            )
            admin.commit()
            async with sessions() as session, session.begin():
                removed = await TaskEventStore(None).purge(session, 1, attempt.task_id)
                assert removed == edge_count
            assert (
                query(
                    "SELECT COUNT(*) FROM orbit_execution_recovery_edge WHERE tenant_id=%s AND "
                    "decision_id=%s",
                    (tenant, result.decision_id),
                )[0][0]
                == edge_count
            )
            cases.append(RECOVERY_COMMIT_CASES[12])
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counted)
            await engine.dispose()

    asyncio.run(internal())
    return {"recovery_groups": len(RECOVERY_COMMIT_CASES), "platform_sends": 0, "claims": 0}
