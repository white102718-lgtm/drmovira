"""046真实SQL护栏工具；仅原execute受理与技术SQL样本，零claim/send/Worker。

主线显式注入隔离039 Provider并串行运行；本文件导入不连接数据库。
"""

import re
from contextlib import contextmanager
from uuid import UUID, uuid4

from pymysql import MySQLError

if __package__:
    from .launch_execution_fixture import create_protocol_plan
else:
    from launch_execution_fixture import create_protocol_plan

EXECUTION_LEASE_CASES = [
    "pythonExecutionLeaseOriginal202HasComplete039SourceWithoutSending",
    "pythonExecutionLeaseActualSixTriggersAndThreeTables",
    "pythonExecutionLeaseAttemptForeignKeysBindRealCommandPreparationAndIdentity",
    "pythonExecutionLeaseAttemptHistoryIsImmutable",
    "pythonExecutionLeaseRuntimeCompositeForeignKeyRejectsPartialOrWrongBinding",
    "pythonExecutionLeaseRuntimeCasAndMonotonicFencing",
    "pythonExecutionLeaseLateFactBindsOldAttemptWithoutAdvancingCurrentHead",
    "pythonExecutionLeaseFactsImmutableAndExactEventSequenceUnique",
    "pythonExecutionLeaseActualHashPhaseUtcAndManualTimeChecks",
    "pythonExecutionLeaseActualOutbox1644RollsBackHeadFactAuditTogether",
]


def guard_execution_lease_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or type(admin.port) is not int
        or admin.port != 13306
        or not isinstance(database, str)
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("执行租约专项仅允许本机13306及本轮UUID库")


@contextmanager
def execution_lease_transaction(admin):
    """管理连接可autocommit=True；多表故障验证必须自己明确开始事务。"""
    admin.begin()
    try:
        yield
    except BaseException:
        admin.rollback()
        raise
    else:
        admin.commit()


def run_execution_lease_checks(client, admin, headers, password, cache, database, cases):
    guard_execution_lease_target(admin, database)

    def execute(sql, values=()):
        with admin.cursor() as cursor:
            cursor.execute(sql, values)
            return cursor.rowcount

    def query(sql, values=()):
        with admin.cursor() as cursor:
            cursor.execute(sql, values)
            result = cursor.fetchall()
        # 不把前一次HTTP之前的RR快照继承成“当前”观察。
        admin.commit()
        return result

    def scalar(sql, values=()):
        return query(sql, values)[0][0]

    def rejected(operation, expected):
        try:
            operation()
        except MySQLError as error:
            admin.rollback()
            assert type(error.args[0]) is int and error.args[0] in expected, {
                "expected_errno": sorted(expected),
                "actual_errno": error.args[0] if type(error.args[0]) is int else None,
            }
        else:
            admin.rollback()
            raise AssertionError("EXPECTED_SQL_REJECTION")

    def checked(response, expected):
        assert response.status_code == expected, {
            "expected_status": expected,
            "actual_status": response.status_code,
        }
        return response.json()

    assert scalar("SELECT DATABASE()") == database
    tenant, owner, team = query(
        "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1"
    )[0]
    item = create_protocol_plan(admin, tenant, owner, team)
    capabilities = checked(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)

    def write(revision):
        return headers | {
            "X-CSRF-Token": capabilities["csrf_token"],
            "If-Match": f'"{revision}"',
            "Idempotency-Key": str(uuid4()),
        }

    validation = checked(
        client.post(
            f"/api/v1/launch-plans/{item['id']}/validate", headers=write(1), json=item["body"]
        ),
        200,
    )
    assert validation["valid"] is True and validation["hash"] is not None
    task = checked(
        client.post(
            f"/api/v1/launch-plans/{item['id']}/execute",
            headers=write(2),
            json={"hash": validation["hash"], "activate_ack": False},
        ),
        202,
    )
    task_id = task["id"]
    assert str(UUID(task_id)) == task_id
    assert task["state"] == "QUEUED" and task["revision"] == 1
    preparation, manifest_hash, source_hash, auth_hash, actor, subject, auth_version = query(
        "SELECT id,manifest_hash,payload_hash,authorization_fingerprint,actor_id,"
        "subject_id,auth_version FROM orbit_launch_execution_preparation WHERE "
        "tenant_id=%s AND task_id=%s AND state='ACCEPTED'",
        (tenant, task_id),
    )[0]
    node, command_hash = query(
        "SELECT node_id,resolved_configuration_hash FROM "
        "orbit_launch_execution_command WHERE tenant_id=%s AND task_id=%s ORDER BY "
        "ordinal LIMIT 1",
        (tenant, task_id),
    )[0]
    assert (
        scalar(
            "SELECT COUNT(*) FROM orbit_launch_execution_command WHERE tenant_id=%s AND task_id=%s",
            (tenant, task_id),
        )
        == task["node_count"]
    )
    assert query(
        "SELECT DISTINCT state,attempt FROM orbit_launch_execution_command WHERE "
        "tenant_id=%s AND task_id=%s",
        (tenant, task_id),
    ) == (("QUEUED", 0),)
    assert (
        scalar(
            "SELECT COUNT(*) FROM orbit_task WHERE tenant_id=%s AND id=%s AND "
            "manifest_phase='COMPLETE'",
            (tenant, task_id),
        )
        == 1
    )
    cases.append(EXECUTION_LEASE_CASES[0])

    expected_triggers = {
        ("guard_exec_attempt_update", "orbit_execution_attempt", "UPDATE"),
        ("guard_exec_attempt_delete", "orbit_execution_attempt", "DELETE"),
        ("guard_exec_fact_update", "orbit_execution_attempt_fact", "UPDATE"),
        ("guard_exec_fact_delete", "orbit_execution_attempt_fact", "DELETE"),
        ("guard_exec_runtime_update", "orbit_execution_command_runtime", "UPDATE"),
        ("guard_exec_runtime_delete", "orbit_execution_command_runtime", "DELETE"),
    }
    actual = query(
        "SELECT TRIGGER_NAME,EVENT_OBJECT_TABLE,EVENT_MANIPULATION FROM "
        "information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND EVENT_OBJECT_TABLE "
        "IN ('orbit_execution_attempt','orbit_execution_command_runtime',"
        "'orbit_execution_attempt_fact')",
        (database,),
    )
    assert set(actual) == expected_triggers
    assert (
        scalar(
            "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND "
            "TABLE_NAME IN ('orbit_execution_attempt',"
            "'orbit_execution_command_runtime','orbit_execution_attempt_fact') AND "
            "TABLE_COLLATION='utf8mb4_0900_as_cs'",
            (database,),
        )
        == 3
    )
    cases.append(EXECUTION_LEASE_CASES[1])

    first = {
        "tenant": tenant,
        "task": task_id,
        "node": node,
        "preparation": preparation,
        "attempt": 1,
        "fence": 1,
        "claim": str(uuid4()),
        "worker": str(uuid4()),
        "mode": task["execution_mode"],
        "command": command_hash,
        "manifest": manifest_hash,
        "source": source_hash,
        "authority": "a" * 64,  # 显式SQL技术样本，不是生产发送authority。
        "authorization": auth_hash,
        "actor": actor,
        "subject": subject,
        "owner": owner,
        "team": team,
        "auth_version": auth_version,
    }
    attempt_sql = (
        "INSERT INTO orbit_execution_attempt(tenant_id,task_id,node_id,preparation_id,"
        "attempt_no,fencing_token,claim_id,worker_id,execution_mode,command_hash,"
        "manifest_hash,source_hash,authority_hash,authorization_hash,actor_id,"
        "subject_id,owner_user_id,owner_team_id,auth_version,created_at) "
        "VALUES(%(tenant)s,%(task)s,%(node)s,%(preparation)s,%(attempt)s,%(fence)s,"
        "%(claim)s,%(worker)s,%(mode)s,%(command)s,%(manifest)s,%(source)s,"
        "%(authority)s,%(authorization)s,%(actor)s,%(subject)s,%(owner)s,%(team)s,"
        "%(auth_version)s,UTC_TIMESTAMP(3))"
    )
    for column in ("tenant", "task", "node", "preparation", "subject", "owner", "team"):
        rejected(lambda column=column: execute(attempt_sql, first | {column: str(uuid4())}), {1452})
    assert execute(attempt_sql, first) == 1
    admin.commit()
    cases.append(EXECUTION_LEASE_CASES[2])

    prefix = "tenant_id=%(tenant)s AND task_id=%(task)s AND node_id=%(node)s"
    rejected(
        lambda: execute(
            "UPDATE orbit_execution_attempt SET command_hash='" + "f" * 64 + "' WHERE " + prefix,
            first,
        ),
        {1644},
    )
    rejected(lambda: execute("DELETE FROM orbit_execution_attempt WHERE " + prefix, first), {1644})
    cases.append(EXECUTION_LEASE_CASES[3])

    runtime_sql = (
        "INSERT INTO orbit_execution_command_runtime(tenant_id,task_id,node_id,"
        "revision,active_attempt,fencing_token,claim_id,worker_id,lease_expires_at,"
        "created_at,updated_at) VALUES(%(tenant)s,%(task)s,%(node)s,1,%(attempt)s,"
        "%(fence)s,%(claim)s,%(worker)s,UTC_TIMESTAMP(3)+INTERVAL 60 SECOND,"
        "UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"
    )
    for changes in (
        {"attempt": 2},
        {"fence": 2},
        {"claim": str(uuid4())},
        {"worker": str(uuid4())},
    ):
        rejected(lambda changes=changes: execute(runtime_sql, first | changes), {1452})
    rejected(lambda: execute(runtime_sql, first | {"claim": None}), {3819})
    assert execute(runtime_sql, first) == 1
    admin.commit()
    cases.append(EXECUTION_LEASE_CASES[4])

    def runtime():
        return query(
            "SELECT revision,active_attempt,fencing_token,claim_id,worker_id,"
            "lease_expires_at,unknown_since,last_reconciled_at,next_reconcile_at,"
            "needs_manual_reconciliation FROM orbit_execution_command_runtime WHERE " + prefix,
            first,
        )[0]

    for assignments in (
        "revision=revision",
        "revision=revision+2",
        "revision=revision+1,fencing_token=0",
        "revision=revision+1,claim_id='" + str(uuid4()) + "'",
        "revision=revision+1,worker_id='" + str(uuid4()) + "'",
        "revision=revision+1,created_at=created_at+INTERVAL 1 SECOND",
    ):
        rejected(
            lambda assignments=assignments: execute(
                "UPDATE orbit_execution_command_runtime SET " + assignments + " WHERE " + prefix,
                first,
            ),
            {1644},
        )
    rejected(
        lambda: execute("DELETE FROM orbit_execution_command_runtime WHERE " + prefix, first),
        {1644},
    )
    assert (
        execute(
            "UPDATE orbit_execution_command_runtime SET revision=revision+1,"
            "updated_at=UTC_TIMESTAMP(3),lease_expires_at=UTC_TIMESTAMP(3)+INTERVAL "
            "90 SECOND WHERE " + prefix + " AND revision=1",
            first,
        )
        == 1
    )
    admin.commit()
    second = first | {"attempt": 2, "fence": 2, "claim": str(uuid4()), "worker": str(uuid4())}
    assert execute(attempt_sql, second) == 1
    assert (
        execute(
            "UPDATE orbit_execution_command_runtime SET revision=revision+1,"
            "active_attempt=%(attempt)s,fencing_token=%(fence)s,claim_id=%(claim)s,"
            "worker_id=%(worker)s,updated_at=UTC_TIMESTAMP(3) WHERE " + prefix + " AND revision=2",
            second,
        )
        == 1
    )
    admin.commit()
    assert runtime()[:5] == (3, 2, 2, second["claim"], second["worker"])
    assert (
        execute(
            "UPDATE orbit_execution_command_runtime SET revision=revision+1,"
            "updated_at=UTC_TIMESTAMP(3) WHERE " + prefix + " AND revision=2",
            first,
        )
        == 0
    )  # 旧CAS精确失败，不能假称发生状态转换。
    admin.rollback()
    cases.append(EXECUTION_LEASE_CASES[5])

    fact_sql = (
        "INSERT INTO orbit_execution_attempt_fact(tenant_id,task_id,node_id,"
        "attempt_no,fencing_token,claim_id,worker_id,event_id,sequence_no,fact_kind,"
        "send_phase,evidence_source,evidence_sha256,external_id,occurred_at,"
        "recorded_at) VALUES(%(tenant)s,%(task)s,%(node)s,%(attempt)s,%(fence)s,"
        "%(claim)s,%(worker)s,%(event)s,%(sequence)s,%(kind)s,%(phase)s,"
        "%(evidence_source)s,%(evidence_hash)s,%(external)s,UTC_TIMESTAMP(3),"
        "UTC_TIMESTAMP(3))"
    )

    def event(attempt, **changes):
        return (
            attempt
            | {
                "event": str(uuid4()),
                "sequence": 1,
                "kind": "WRITE_INTENT",
                "phase": "BEFORE_DISPATCH",
                "evidence_source": "LOCAL_INTENT",
                "evidence_hash": "b" * 64,
                "external": None,
            }
            | changes
        )

    before = runtime()
    late = event(first)
    assert execute(fact_sql, late) == 1
    admin.commit()
    assert runtime() == before
    assert query(
        "SELECT attempt_no,fencing_token,claim_id FROM orbit_execution_attempt_fact "
        "WHERE tenant_id=%s AND event_id=%s",
        (tenant, late["event"]),
    )[0] == (1, 1, first["claim"])
    rejected(lambda: execute(fact_sql, event(second, claim=first["claim"])), {1452})
    cases.append(EXECUTION_LEASE_CASES[6])

    rejected(
        lambda: execute(
            "UPDATE orbit_execution_attempt_fact SET evidence_sha256='"
            + "c" * 64
            + "' WHERE tenant_id=%s AND event_id=%s",
            (tenant, late["event"]),
        ),
        {1644},
    )
    rejected(
        lambda: execute(
            "DELETE FROM orbit_execution_attempt_fact WHERE tenant_id=%s AND event_id=%s",
            (tenant, late["event"]),
        ),
        {1644},
    )
    rejected(lambda: execute(fact_sql, late | {"evidence_hash": "c" * 64}), {1062})
    rejected(lambda: execute(fact_sql, late | {"event": str(uuid4())}), {1062})
    cases.append(EXECUTION_LEASE_CASES[7])

    for changes in (
        {"command": "A" * 64},
        {"manifest": "x" * 64},
        {"auth_version": 0},
        {"fence": 0},
    ):
        rejected(
            lambda changes=changes: execute(
                attempt_sql, second | {"attempt": 3, "fence": 3, "claim": str(uuid4())} | changes
            ),
            {3819},
        )
    for changes in (
        {"evidence_hash": "G" * 64},
        {"kind": "WAITING_RETRY"},
        {
            "kind": "PROVED_NOT_SENT",
            "phase": "DISPATCH_STARTED",
            "evidence_source": "TRANSPORT_PROVEN_NO_SEND",
        },
        {"kind": "READBACK_SUCCEEDED", "phase": "READBACK", "evidence_source": "PLATFORM_READBACK"},
        {"external": "123x"},
    ):
        rejected(lambda changes=changes: execute(fact_sql, event(second, **changes)), {3819})
    rejected(
        lambda: execute(
            fact_sql.replace(
                "UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
                "UTC_TIMESTAMP(3)+INTERVAL 1 DAY,UTC_TIMESTAMP(3))",
            ),
            event(second),
        ),
        {3819},
    )
    rejected(
        lambda: execute(
            "UPDATE orbit_execution_command_runtime SET revision=revision+1,"
            "unknown_since=UTC_TIMESTAMP(3),needs_manual_reconciliation=TRUE,"
            "updated_at=UTC_TIMESTAMP(3) WHERE " + prefix,
            first,
        ),
        {3819},
    )
    assert runtime() == before
    cases.append(EXECUTION_LEASE_CASES[8])

    trigger = "it_lease_outbox_" + uuid4().hex[:12]
    baseline = (
        runtime(),
        scalar("SELECT COUNT(*) FROM orbit_execution_attempt_fact WHERE " + prefix, first),
        scalar(
            "SELECT COUNT(*) FROM orbit_task_audit WHERE tenant_id=%s AND task_id=%s",
            (tenant, task_id),
        ),
        scalar(
            "SELECT COUNT(*) FROM orbit_task_outbox WHERE tenant_id=%s AND task_id=%s",
            (tenant, task_id),
        ),
    )
    transaction_fact = event(second)
    audit_id = str(uuid4())

    def transaction():
        with execution_lease_transaction(admin):
            assert (
                execute(
                    "UPDATE orbit_execution_command_runtime SET revision=revision+1,"
                    "updated_at=UTC_TIMESTAMP(3) WHERE " + prefix + " AND revision=3",
                    first,
                )
                == 1
            )
            assert execute(fact_sql, transaction_fact) == 1
            execute(
                "INSERT INTO orbit_task_audit(id,tenant_id,task_id,actor_id,request_id,"
                "action,created_at) VALUES(%s,%s,%s,%s,%s,'ISOLATED_LEASE_SQL',"
                "UTC_TIMESTAMP(3))",
                (audit_id, tenant, task_id, actor, str(uuid4())),
            )
            execute(
                "INSERT INTO orbit_task_outbox(audit_id,tenant_id,task_id,created_at) "
                "VALUES(%s,%s,%s,UTC_TIMESTAMP(3))",
                (audit_id, tenant, task_id),
            )

    try:
        execute(
            f"CREATE TRIGGER {trigger} BEFORE INSERT ON orbit_task_outbox FOR "
            f"EACH ROW BEGIN IF NEW.task_id='{task_id}' THEN SIGNAL SQLSTATE "
            f"'45000' SET MESSAGE_TEXT='ISOLATED_LEASE_OUTBOX_REJECTED'; END IF; "
            f"END"
        )
        admin.commit()
        rejected(transaction, {1644})
        assert (
            runtime(),
            scalar("SELECT COUNT(*) FROM orbit_execution_attempt_fact WHERE " + prefix, first),
            scalar(
                "SELECT COUNT(*) FROM orbit_task_audit WHERE tenant_id=%s AND task_id=%s",
                (tenant, task_id),
            ),
            scalar(
                "SELECT COUNT(*) FROM orbit_task_outbox WHERE tenant_id=%s AND task_id=%s",
                (tenant, task_id),
            ),
        ) == baseline
    finally:
        admin.rollback()
        execute(f"DROP TRIGGER IF EXISTS {trigger}")
        admin.commit()
    transaction()
    admin.commit()
    assert runtime()[0] == baseline[0][0] + 1
    assert (
        scalar(
            "SELECT COUNT(*) FROM orbit_task_audit WHERE tenant_id=%s AND task_id=%s",
            (tenant, task_id),
        )
        == baseline[2] + 1
    )
    assert (
        scalar(
            "SELECT COUNT(*) FROM orbit_task_outbox WHERE tenant_id=%s AND task_id=%s",
            (tenant, task_id),
        )
        == baseline[3] + 1
    )
    assert scalar("SELECT COUNT(*) FROM orbit_task_outbox WHERE audit_id=%s", (audit_id,)) == 1
    assert (
        scalar(
            "SELECT COUNT(*) FROM orbit_execution_attempt_fact WHERE tenant_id=%s AND event_id=%s",
            (tenant, transaction_fact["event"]),
        )
        == 1
    )
    assert query(
        "SELECT DISTINCT state,attempt FROM orbit_launch_execution_command WHERE "
        "tenant_id=%s AND task_id=%s",
        (tenant, task_id),
    ) == (("QUEUED", 0),)
    unchanged_task = checked(client.get(f"/api/v1/tasks/{task_id}", headers=headers), 200)
    assert unchanged_task["state"] == "QUEUED" and unchanged_task["revision"] == 1
    cases.append(EXECUTION_LEASE_CASES[9])
    return {
        "lease_sql_cases": len(EXECUTION_LEASE_CASES),
        "claim_count": 0,
        "platform_send_count": 0,
    }
