"""039真实SQL护栏专项：仅DDL协议夹具，无Authority/execute/平台调用。

数据为显式GUARD_FIXTURE，直接SQL的ACCEPTED状态仅验证约束/运行字段，
不代表原202已实现。接受历史不能绕护栏清理，由主线finally DROP本轮UUID库。
"""

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import timedelta
from uuid import uuid4

import pymysql

LAUNCH_EXECUTION_GUARD_CASES = [
    "pythonExecutionGuardTrustedInitialHiddenTaskAndTypedHeaders",
    "pythonExecutionGuardTrustedDirectCompleteAndUnboundUpdateRejected",
    "pythonExecutionGuardPreparationExactValidationBindingEveryField",
    "pythonExecutionGuardPreparationAndCommandHashChecks",
    "pythonExecutionGuardActualByteShaAndLengthCheck",
    "pythonExecutionGuardSealingCurrentReadIgnoresOldRepeatableReadSnapshot",
    "pythonExecutionGuardSealedIntentSourceNodeEdgeByteCommandImmutable",
    "pythonExecutionGuardAcceptedRuntimeAllowedButIntentStillImmutable",
    "pythonExecutionGuardAbortedCannotReviveAndBoundedCleanup",
    "pythonExecutionGuardLegalTaskPreparationOrderAndSealSynchronization",
    "pythonExecutionGuardIllegalReverseOrderDeadlockWholeTransactionRollback",
]


def guard_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("执行护栏专项仅允许主线本轮13306/UUID库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("实际数据库与本轮UUID不一致")


def error_number(error):
    """仅保留实际数字errno，不回传SQL/参数/错误正文。"""
    return (
        error.args[0]
        if isinstance(error, pymysql.err.MySQLError) and error.args and type(error.args[0]) is int
        else None
    )


def _insert(cursor, table, value):
    # table/列完全来自本工具常量，业务值全部绑定，不接HTTP输入。
    cursor.execute(
        "INSERT INTO "
        + table
        + "("
        + ",".join(value)
        + ") VALUES("
        + ",".join(["%s"] * len(value))
        + ")",
        tuple(value.values()),
    )


def _connect(admin, database):
    def decode(value):
        return value.decode() if isinstance(value, bytes) else value

    result = pymysql.connect(
        host=admin.host,
        port=admin.port,
        user=decode(admin.user),
        password=decode(admin.password),
        database=database,
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=5,
        read_timeout=7,
        write_timeout=7,
    )
    with result.cursor() as cursor:
        cursor.execute("SET SESSION innodb_lock_wait_timeout=5")
    return result


def _locked_wait(observer, connection_id, *, pending=None, seconds=2):
    # INNODB_TRX监控buffer需距上次read>0.1s才刷新，10ms自旋可能饿死刷新。
    # 独立autocommit观察连接不继承业务RR事务，总预算仍严格2秒。
    until = time.monotonic() + seconds
    samples, last_state = 0, None

    def fail(phase, errno=None):
        diagnostic = {
            "phase": phase,
            "actual_errno": errno,
            "samples": samples,
            "last_trx_state": last_state,
        }
        print(json.dumps({"execution_guard_wait_diagnostic": diagnostic}), flush=True)
        raise AssertionError(diagnostic)

    while time.monotonic() < until:
        if pending is not None and pending.done():
            try:
                outcome = pending.result()
            except pymysql.err.MySQLError as error:
                fail("waiter_finished_error", error_number(error))
            fail("waiter_finished_without_observed_lock", outcome if type(outcome) is int else None)
        with observer.cursor() as cursor:
            cursor.execute(
                "SELECT trx_state FROM information_schema.innodb_trx WHERE trx_mysql_thread_id=%s",
                (connection_id,),
            )
            row = cursor.fetchone()
        samples += 1
        last_state = (
            row[0]
            if row and row[0] in {"RUNNING", "LOCK WAIT", "ROLLING BACK", "COMMITTING"}
            else None
        )
        if last_state == "LOCK WAIT":
            return
        time.sleep(min(0.12, max(0, until - time.monotonic())))
    fail("lock_wait_not_observed")


def run_launch_execution_guard_checks(client, admin, headers, password, cache, database, cases):
    guard_target(admin, database)
    from task_core_fixture import compile_dag, plan

    from orbit_api.directory_tokens import canonical
    from orbit_api.launch_access import digest
    from orbit_api.task_contract import chunk_manifest, node_id

    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()

    def fixture(*, with_commands=True, unbound=False, task_kind="TRUSTED"):
        value = plan(owner, team, copies=1)
        value["name"] = "ORBIT_EXECUTION_GUARD_FIXTURE_" + uuid4().hex[:12]
        dag = compile_dag(value)
        records = [asdict(row) for row in dag.nodes]
        payload = canonical(value)
        ids = {
            key: str(uuid4())
            for key in ("plan", "allocation", "names", "validation", "task", "prep", "request")
        }
        document = canonical({"schema": "SQL_GUARD_FIXTURE_NOT_EXECUTE", "nodes": records}).encode()
        chunks = chunk_manifest(records)
        admin.begin()
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT UTC_TIMESTAMP(3),DATE(UTC_TIMESTAMP(3)+INTERVAL 8 "
                "HOUR),CAST(DATE(UTC_TIMESTAMP(3)+INTERVAL 8 HOUR)+INTERVAL 1 DAY AS "
                "DATETIME)-INTERVAL 8 HOUR"
            )
            now, day, midnight = cursor.fetchone()
            expiry = now + timedelta(minutes=15)
            _insert(
                cursor,
                "orbit_launch_plan",
                dict(
                    tenant_id=tenant,
                    id=ids["plan"],
                    owner_user_id=owner,
                    owner_team_id=team,
                    name=value["name"],
                    state="VALIDATED",
                    revision=2,
                    payload_json=payload,
                    payload_hash=digest(value),
                    payload_bytes=len(payload.encode()),
                    account_count=1,
                    asset_count=1,
                    created_at=now,
                    updated_at=now,
                ),
            )
            _insert(
                cursor,
                "orbit_launch_plan_version",
                dict(
                    tenant_id=tenant,
                    plan_id=ids["plan"],
                    revision=1,
                    payload_json=payload,
                    payload_hash=digest(value),
                    dependency_json="{}",
                    created_at=now,
                    created_by=1,
                ),
            )
            _insert(
                cursor,
                "orbit_launch_allocation",
                dict(
                    tenant_id=tenant,
                    id=ids["allocation"],
                    plan_id=ids["plan"],
                    plan_revision=1,
                    state="SUCCEEDED",
                    task_id=None,
                    algorithm_version="allocation-v1",
                    seed=0,
                    input_hash=dag.allocation_input_hash,
                    warnings_json="[]",
                    active=1,
                    created_at=now,
                    updated_at=now,
                ),
            )
            _insert(
                cursor,
                "orbit_launch_name_reservation",
                dict(
                    tenant_id=tenant,
                    id=ids["names"],
                    plan_id=ids["plan"],
                    plan_revision=1,
                    naming_date=day,
                    source_hash=digest([ids["plan"], "guard-names"]),
                    created_at=now,
                ),
            )
            validation_hash = digest([ids["plan"], "SQL_GUARD_FIXTURE_NOT_AUTHORITY"])
            summary = dict(
                valid=True,
                hash=validation_hash,
                expires_at=expiry.isoformat(timespec="milliseconds") + "Z",
                errors=[],
                campaign_count=dag.campaign_count,
                adset_count=dag.adset_count,
                ad_count=dag.ad_count,
                budget_totals=[],
                scope_version=1,
                total_dag_node_count=dag.total_dag_node_count,
            )
            _insert(
                cursor,
                "orbit_launch_validation",
                dict(
                    tenant_id=tenant,
                    id=ids["validation"],
                    plan_id=ids["plan"],
                    source_revision=1,
                    validated_head_revision=2,
                    payload_hash=digest(value),
                    validation_hash=validation_hash,
                    validated_at=now,
                    expires_at=expiry,
                    naming_date=day,
                    scope_version=1,
                    allocation_id=ids["allocation"],
                    name_reservation_id=ids["names"],
                    provider_kind="ISOLATED_TEST",
                    provider_fingerprint=digest(["guard"]),
                    summary_json=canonical(summary),
                    observation_refs_json="[]",
                    created_by=1,
                    created_at=now,
                ),
            )
            task = dict(
                tenant_id=tenant,
                id=ids["task"],
                owner_user_id=owner,
                owner_team_id=team,
                source_plan_id=ids["plan"],
                source_revision=1,
                source_hash=digest(value),
                execution_mode="META_API",
                producer_kind=task_kind,
                graph_hash=dag.graph_hash,
                manifest_hash=digest(chunks),
                expected_node_count=len(records),
                expected_chunk_count=len(chunks),
                accepted_request_id=ids["request"],
                created_by=1,
                created_at=now,
                updated_at=now,
                dag_schema_version=1,
                plan_input_hash=dag.plan_input_hash,
                allocation_input_hash=dag.allocation_input_hash,
            )
            _insert(cursor, "orbit_task", task)
            prep = dict(
                tenant_id=tenant,
                id=ids["prep"],
                task_id=ids["task"],
                plan_id=ids["plan"],
                source_revision=1,
                payload_hash=digest(value),
                validation_id=ids["validation"],
                validated_head_revision=2,
                validation_hash=validation_hash,
                validation_expires_at=expiry,
                naming_date=day,
                actor_id=1,
                subject_id=owner,
                owner_user_id=owner,
                owner_team_id=team,
                auth_version=1,
                authorization_fingerprint=digest(["guard-auth"]),
                intent_hash=digest(["guard-intent"]),
                idempotency_key_hash=digest(["guard-key"]),
                provider_kind="TRUSTED",
                provider_fingerprint=digest(["guard-provider"]),
                manifest_schema_version=1,
                manifest_hash=hashlib.sha256(document).hexdigest(),
                task_chunk_hash=digest(chunks),
                graph_hash=dag.graph_hash,
                plan_input_hash=dag.plan_input_hash,
                allocation_input_hash=dag.allocation_input_hash,
                expected_bytes=len(document),
                expected_byte_chunks=1,
                expected_node_count=len(records),
                expected_node_chunks=len(chunks),
                expected_command_count=len(records),
                expected_edge_count=sum(len(row["parent_keys"]) for row in records),
                created_at=now,
                updated_at=now,
                expires_at=min(expiry, midnight),
            )
            result = dict(
                ids=ids,
                task=task,
                prep=prep,
                records=records,
                document=document,
                chunks=chunks,
                now=now,
            )
            if not unbound:
                _insert(cursor, "orbit_launch_execution_preparation", prep)
                for ordinal, row in enumerate(records):
                    identifier = node_id(ids["task"], row["node_key"])
                    _insert(
                        cursor,
                        "orbit_task_node",
                        dict(
                            tenant_id=tenant,
                            task_id=ids["task"],
                            id=identifier,
                            ordinal=ordinal,
                            node_key=row["node_key"],
                            kind=row["kind"],
                            initial_json=canonical(row),
                            updated_at=now,
                        ),
                    )
                    for parent in row["parent_keys"]:
                        _insert(
                            cursor,
                            "orbit_task_edge",
                            dict(
                                tenant_id=tenant,
                                task_id=ids["task"],
                                child_id=identifier,
                                parent_id=node_id(ids["task"], parent),
                            ),
                        )
                    if with_commands:
                        _insert(cursor, "orbit_launch_execution_command", command(result, ordinal))
                for ordinal, count, fingerprint in chunks:
                    _insert(
                        cursor,
                        "orbit_task_chunk",
                        dict(
                            tenant_id=tenant,
                            task_id=ids["task"],
                            ordinal=ordinal,
                            expected_count=count,
                            expected_hash=fingerprint,
                            persisted=1,
                        ),
                    )
                _insert(
                    cursor,
                    "orbit_launch_execution_byte_chunk",
                    dict(
                        tenant_id=tenant,
                        preparation_id=ids["prep"],
                        ordinal=0,
                        byte_length=len(document),
                        chunk_hash=prep["manifest_hash"],
                        payload=document,
                        created_at=now,
                    ),
                )
                cursor.execute(
                    "UPDATE orbit_task SET node_count=%s,edge_count=%s WHERE tenant_id=%s AND "
                    "id=%s",
                    (len(records), prep["expected_edge_count"], tenant, ids["task"]),
                )
                cursor.execute(
                    "UPDATE orbit_launch_execution_preparation SET persisted_bytes=expected_bytes,"
                    "persisted_byte_chunks=expected_byte_chunks,persisted_node_count=expected_n"
                    "ode_count,"
                    "persisted_node_chunks=expected_node_chunks,persisted_command_count=%s,"
                    "persisted_edge_count=expected_edge_count,mutation_revision=mutation_revisi"
                    "on+1 "
                    "WHERE tenant_id=%s AND id=%s",
                    (len(records) if with_commands else 0, tenant, ids["prep"]),
                )
        admin.commit()
        return result

    def command(item, ordinal):
        row = item["records"][ordinal]
        resolved = canonical(
            {
                "schema": "SQL_GUARD_FIXTURE_NOT_EXECUTE",
                "kind": row["kind"],
                "target": row["target_key"],
            }
        )
        return dict(
            tenant_id=tenant,
            preparation_id=item["ids"]["prep"],
            task_id=item["ids"]["task"],
            node_id=node_id(item["ids"]["task"], row["node_key"]),
            ordinal=ordinal,
            node_key=row["node_key"],
            kind=row["kind"],
            purpose=row["purpose"],
            account_id=row["account_id"],
            target_key=row["target_key"],
            resolved_configuration_json=resolved,
            resolved_configuration_hash=hashlib.sha256(resolved.encode()).hexdigest(),
            observation_binding_hash=digest(["guard-observation"]),
            created_at=item["now"],
            updated_at=item["now"],
        )

    def reject(action, *, errno=1644):
        admin.begin()
        try:
            with admin.cursor() as cursor:
                action(cursor)
        except pymysql.err.MySQLError as error:
            assert error_number(error) == errno, {
                "actual_errno": error_number(error),
                "expected_errno": errno,
            }
        else:
            raise AssertionError("应拒绝的真实SQL意外成功")
        finally:
            admin.rollback()

    def update(table, values, where, params):
        def action(cursor):
            cursor.execute(
                "UPDATE "
                + table
                + " SET "
                + ",".join(key + "=%s" for key in values)
                + " WHERE "
                + where,
                tuple(values.values()) + tuple(params),
            )

        return action

    def seal(item, *, already_sealing=False, complete=True):
        admin.begin()
        with admin.cursor() as cursor:
            if not already_sealing:
                cursor.execute(
                    "UPDATE orbit_launch_execution_preparation SET state='SEALING',"
                    "mutation_revision=mutation_revision+1 WHERE tenant_id=%s AND id=%s",
                    (tenant, item["ids"]["prep"]),
                )
            if complete:
                cursor.execute(
                    "UPDATE orbit_launch_execution_preparation SET state='SEALED',"
                    "sealed_revision=mutation_revision+1,mutation_revision=mutation_revision+1,seal"
                    "ed_at=UTC_TIMESTAMP(3) "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, item["ids"]["prep"]),
                )
        admin.commit()

    # 所有正向均为显式DDL fixture；没有production Provider或原execute调用。
    base = fixture()
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT manifest_phase,node_count FROM orbit_task WHERE tenant_id=%s AND id=%s",
            (tenant, base["ids"]["task"]),
        )
        assert cursor.fetchone() == ("BUILDING", len(base["records"]))
    cases.append(LAUNCH_EXECUTION_GUARD_CASES[0])

    unbound = fixture(unbound=True)
    for values in ({"manifest_phase": "COMPLETE"}, {"state": "RUNNING"}):
        reject(
            update("orbit_task", values, "tenant_id=%s AND id=%s", (tenant, unbound["ids"]["task"]))
        )
    for changes in (
        {"manifest_phase": "COMPLETE"},
        {"node_count": 1},
        {"dag_schema_version": None},
        {"plan_input_hash": None},
        {"allocation_input_hash": None},
        {"plan_input_hash": "g" * 64},
    ):
        row = unbound["task"] | changes | {"id": str(uuid4())}
        reject(lambda cursor, row=row: _insert(cursor, "orbit_task", row))
    isolated = fixture(unbound=True, task_kind="ISOLATED_TEST")
    reject(
        update(
            "orbit_task",
            {"producer_kind": "TRUSTED"},
            "tenant_id=%s AND id=%s",
            (tenant, isolated["ids"]["task"]),
        )
    )
    cases.append(LAUNCH_EXECUTION_GUARD_CASES[1])

    # NEW prep及Task保持完全匹配，只篡改实际038行，确保触达038关联防线。
    for field in (
        "plan_id",
        "source_revision",
        "payload_hash",
        "validated_head_revision",
        "validation_hash",
        "expires_at",
        "naming_date",
    ):

        def mismatched_validation(cursor, field=field):
            validation = unbound["ids"]["validation"]
            if field == "plan_id":
                cursor.execute(
                    "UPDATE orbit_launch_validation SET plan_id=%s,validated_head_revision=99 "
                    "WHERE tenant_id=%s AND id=%s",
                    (base["ids"]["plan"], tenant, validation),
                )
            elif field == "source_revision":
                cursor.execute(
                    "INSERT INTO orbit_launch_plan_version(tenant_id,plan_id,revision,payload_json,"
                    "payload_hash,dependency_json,created_at,created_by) SELECT "
                    "tenant_id,plan_id,2,"
                    "payload_json,payload_hash,dependency_json,created_at,created_by FROM "
                    "orbit_launch_plan_version WHERE tenant_id=%s AND plan_id=%s AND revision=1",
                    (tenant, unbound["ids"]["plan"]),
                )
                cursor.execute(
                    "UPDATE orbit_launch_validation SET "
                    "source_revision=2,validated_head_revision=3 "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, validation),
                )
            elif field == "validation_hash":
                cursor.execute(
                    "UPDATE orbit_launch_validation SET validation_hash=%s,"
                    "summary_json=JSON_SET(summary_json,'$.hash',%s) WHERE tenant_id=%s AND id=%s",
                    ("b" * 64, "b" * 64, tenant, validation),
                )
            elif field == "expires_at":
                cursor.execute(
                    "UPDATE orbit_launch_validation SET validated_at=validated_at+INTERVAL "
                    "1000 MICROSECOND,"
                    "expires_at=expires_at+INTERVAL 1000 "
                    "MICROSECOND,naming_date=DATE(validated_at+INTERVAL 8 HOUR) "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, validation),
                )
            elif field == "naming_date":
                cursor.execute(
                    "UPDATE orbit_launch_validation SET validated_at=validated_at-INTERVAL 1 DAY,"
                    "expires_at=expires_at-INTERVAL 1 "
                    "DAY,naming_date=DATE(validated_at+INTERVAL 8 HOUR) "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, validation),
                )
            else:
                cursor.execute(
                    "UPDATE orbit_launch_validation SET "
                    + field
                    + "=%s WHERE tenant_id=%s AND id=%s",
                    (3 if field == "validated_head_revision" else "b" * 64, tenant, validation),
                )
            assert cursor.rowcount == 1
            _insert(cursor, "orbit_launch_execution_preparation", unbound["prep"])

        reject(mismatched_validation)
    reject(
        lambda cursor: _insert(
            cursor,
            "orbit_launch_execution_preparation",
            unbound["prep"] | {"validation_id": base["ids"]["validation"]},
        )
    )
    cases.append(LAUNCH_EXECUTION_GUARD_CASES[2])

    for field in (
        "intent_hash",
        "idempotency_key_hash",
        "provider_fingerprint",
        "authorization_fingerprint",
        "manifest_hash",
    ):
        row = unbound["prep"] | {field: "g" * 64}
        reject(
            lambda cursor, row=row: _insert(cursor, "orbit_launch_execution_preparation", row),
            errno=3819,
        )
    command_base = fixture(with_commands=False)
    for field in ("resolved_configuration_hash", "observation_binding_hash"):
        row = command(command_base, 0) | {field: "g" * 64}
        reject(
            lambda cursor, row=row: _insert(cursor, "orbit_launch_execution_command", row),
            errno=3819,
        )
    cases.append(LAUNCH_EXECUTION_GUARD_CASES[3])

    for changes in ({"chunk_hash": "g" * 64}, {"chunk_hash": "0" * 64}, {"byte_length": 1}):
        row = (
            dict(
                tenant_id=tenant,
                preparation_id=base["ids"]["prep"],
                ordinal=1,
                byte_length=3,
                chunk_hash=hashlib.sha256(b"abc").hexdigest(),
                payload=b"abc",
                created_at=base["now"],
            )
            | changes
        )
        reject(
            lambda cursor, row=row: _insert(cursor, "orbit_launch_execution_byte_chunk", row),
            errno=3819,
        )
    cases.append(LAUNCH_EXECUTION_GUARD_CASES[4])

    # 当前FOR SHARE必须越过RR旧快照，不能把SEALING看成旧BUILDING。
    rr = _connect(admin, database)
    try:
        rr.begin()
        with rr.cursor() as cursor:
            cursor.execute(
                "SELECT state FROM orbit_launch_execution_preparation WHERE tenant_id=%s AND id=%s",
                (tenant, base["ids"]["prep"]),
            )
            assert cursor.fetchone()[0] == "BUILDING"
        seal(base, complete=False)
        try:
            with rr.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_task_node SET updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=%s "
                    "AND task_id=%s AND ordinal=0",
                    (tenant, base["ids"]["task"]),
                )
        except pymysql.err.MySQLError as error:
            assert error_number(error) == 1644, {"actual_errno": error_number(error)}
        else:
            raise AssertionError("RR旧快照绕过了真实seal当前锁读")
        rr.rollback()
    finally:
        rr.close()
    seal(base, already_sealing=True)
    cases.append(LAUNCH_EXECUTION_GUARD_CASES[5])

    for action in (
        update(
            "orbit_launch_execution_byte_chunk",
            {"payload": b"tampered"},
            "tenant_id=%s AND preparation_id=%s",
            (tenant, base["ids"]["prep"]),
        ),
        update(
            "orbit_launch_execution_command",
            {"resolved_configuration_json": "{}"},
            "tenant_id=%s AND task_id=%s",
            (tenant, base["ids"]["task"]),
        ),
        update(
            "orbit_task_node",
            {"initial_json": "{}"},
            "tenant_id=%s AND task_id=%s",
            (tenant, base["ids"]["task"]),
        ),
        update(
            "orbit_task",
            {"graph_hash": "b" * 64},
            "tenant_id=%s AND id=%s",
            (tenant, base["ids"]["task"]),
        ),
        update(
            "orbit_task",
            {"manifest_phase": "COMPLETE"},
            "tenant_id=%s AND id=%s",
            (tenant, base["ids"]["task"]),
        ),
        lambda cursor: cursor.execute(
            "DELETE FROM orbit_task_edge WHERE tenant_id=%s AND task_id=%s",
            (tenant, base["ids"]["task"]),
        ),
    ):
        reject(action)
    cases.append(LAUNCH_EXECUTION_GUARD_CASES[6])

    # 仅直接SQL护栏fixture发布，决不称原execute 202或生产authority。
    admin.begin()
    with admin.cursor() as cursor:
        cursor.execute("SELECT UTC_TIMESTAMP(3)")
        accepted_at = cursor.fetchone()[0]
        request, event = str(uuid4()), str(uuid4())
        prep = base["prep"]
        _insert(
            cursor,
            "orbit_launch_execution_acceptance",
            dict(
                tenant_id=tenant,
                plan_id=base["ids"]["plan"],
                source_revision=1,
                task_id=base["ids"]["task"],
                preparation_id=base["ids"]["prep"],
                validation_id=base["ids"]["validation"],
                validated_head_revision=2,
                submitted_head_revision=3,
                validation_hash=prep["validation_hash"],
                manifest_hash=prep["manifest_hash"],
                intent_hash=prep["intent_hash"],
                accepted_request_id=request,
                accepted_by=1,
                accepted_at=accepted_at,
            ),
        )
        cursor.execute(
            "UPDATE orbit_launch_execution_preparation SET "
            "state='ACCEPTED',mutation_revision=mutation_revision+1,"
            "accepted_at=%s,accepted_head_revision=3,accepted_request_id=%s WHERE tenant_id=%s "
            "AND id=%s",
            (accepted_at, request, tenant, base["ids"]["prep"]),
        )
        _insert(
            cursor,
            "orbit_task_event",
            dict(
                tenant_id=tenant,
                task_id=base["ids"]["task"],
                event_id=event,
                sequence=1,
                task_revision=1,
                node_id=None,
                state="QUEUED",
                occurred_at=accepted_at,
                request_id=request,
            ),
        )
        cursor.execute(
            "UPDATE orbit_task SET manifest_phase='COMPLETE',created_at=%s,accepted_request_id=%s,"
            "latest_sequence=1,latest_event_id=%s WHERE tenant_id=%s AND id=%s",
            (accepted_at, request, event, tenant, base["ids"]["task"]),
        )
        cursor.execute(
            "UPDATE orbit_task_node SET state='RUNNING',attempt=1 WHERE tenant_id=%s AND "
            "task_id=%s AND ordinal=0",
            (tenant, base["ids"]["task"]),
        )
        cursor.execute(
            "UPDATE orbit_launch_execution_command SET state='RUNNING',attempt=1 WHERE "
            "tenant_id=%s AND task_id=%s AND ordinal=0",
            (tenant, base["ids"]["task"]),
        )
        running_event = str(uuid4())
        _insert(
            cursor,
            "orbit_task_event",
            dict(
                tenant_id=tenant,
                task_id=base["ids"]["task"],
                event_id=running_event,
                sequence=2,
                task_revision=2,
                node_id=node_id(base["ids"]["task"], base["records"][0]["node_key"]),
                state="RUNNING",
                occurred_at=accepted_at,
                request_id=request,
            ),
        )
        cursor.execute(
            "UPDATE orbit_task SET state='RUNNING',revision=2,latest_sequence=2,"
            "latest_event_id=%s WHERE tenant_id=%s AND id=%s",
            (running_event, tenant, base["ids"]["task"]),
        )
    admin.commit()
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT state,revision,latest_sequence FROM orbit_task WHERE tenant_id=%s AND id=%s",
            (tenant, base["ids"]["task"]),
        )
        assert cursor.fetchone() == ("RUNNING", 2, 2)
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_task_event_cursor WHERE tenant_id=%s AND task_id=%s",
            (tenant, base["ids"]["task"]),
        )
        assert cursor.fetchone()[0] == 2
    reject(
        update(
            "orbit_task_node",
            {"initial_json": "{}"},
            "tenant_id=%s AND task_id=%s",
            (tenant, base["ids"]["task"]),
        )
    )
    cases.append(LAUNCH_EXECUTION_GUARD_CASES[7])

    aborted = fixture()
    admin.begin()
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_launch_execution_preparation SET "
            "state='ABORTED',mutation_revision=mutation_revision+1 WHERE tenant_id=%s AND id=%s",
            (tenant, aborted["ids"]["prep"]),
        )
    admin.commit()
    reject(
        update(
            "orbit_launch_execution_preparation",
            {"state": "BUILDING", "mutation_revision": 99},
            "tenant_id=%s AND id=%s",
            (tenant, aborted["ids"]["prep"]),
        )
    )
    admin.begin()
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM orbit_task WHERE tenant_id=%s AND id=%s FOR UPDATE",
            (tenant, aborted["ids"]["task"]),
        )
        cursor.fetchone()
        cursor.execute(
            "SELECT id FROM orbit_launch_execution_preparation WHERE tenant_id=%s AND id=%s "
            "FOR UPDATE",
            (tenant, aborted["ids"]["prep"]),
        )
        cursor.fetchone()
        for table in (
            "orbit_launch_execution_command",
            "orbit_task_edge",
            "orbit_task_node",
            "orbit_task_chunk",
        ):
            # 小fixture，仍显式有界；生产清理每批需按稳定主键续页。
            cursor.execute(
                "DELETE FROM " + table + " WHERE tenant_id=%s AND task_id=%s LIMIT 500",
                (tenant, aborted["ids"]["task"]),
            )
        cursor.execute(
            "DELETE FROM orbit_launch_execution_byte_chunk WHERE tenant_id=%s AND "
            "preparation_id=%s LIMIT 500",
            (tenant, aborted["ids"]["prep"]),
        )
        cursor.execute(
            "DELETE FROM orbit_launch_execution_preparation WHERE tenant_id=%s AND id=%s",
            (tenant, aborted["ids"]["prep"]),
        )
        cursor.execute(
            "DELETE FROM orbit_task WHERE tenant_id=%s AND id=%s", (tenant, aborted["ids"]["task"])
        )
    admin.commit()
    cases.append(LAUNCH_EXECUTION_GUARD_CASES[8])

    # 并发工具在下方独立连接运行，真实观测INNODB_TRX，不用Sleep连接数冒充锁证据。
    concurrency = fixture()
    _concurrency_checks(admin, database, tenant, concurrency, fixture(), cases)
    return {"fixture_only": True, "platform_requests": 0, "accepted_via_execute": False}


def _concurrency_checks(admin, database, tenant, item, control, cases):
    """两个实际连接受控制造同步与非法锁环；仅1213视为预期死锁。"""
    connections = [_connect(admin, database) for _ in range(2)]
    first, second = connections
    observer = _connect(admin, database)
    observer.autocommit(True)
    task, prep = item["ids"]["task"], item["ids"]["prep"]
    try:
        first.begin()
        with first.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM orbit_task WHERE tenant_id=%s AND id=%s FOR UPDATE", (tenant, task)
            )
            cursor.fetchone()
            cursor.execute(
                "SELECT id FROM orbit_launch_execution_preparation WHERE tenant_id=%s AND "
                "id=%s FOR UPDATE",
                (tenant, prep),
            )
            cursor.fetchone()

        def sealing():
            second.begin()
            with second.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_launch_execution_preparation SET "
                    "state='SEALING',mutation_revision=mutation_revision+1 WHERE tenant_id=%s "
                    "AND id=%s",
                    (tenant, prep),
                )
            second.commit()

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(sealing)
            _locked_wait(observer, second.thread_id(), pending=pending)
            first.commit()
            pending.result(timeout=7)
        cases.append(LAUNCH_EXECUTION_GUARD_CASES[9])
        # 另一个BUILDING对象可做非法锁环，不动刚进入SEALING的对象。
        task, prep = control["ids"]["task"], control["ids"]["prep"]
        markers = [str(uuid4()), str(uuid4())]
        for connection, marker in zip(connections, markers, strict=True):
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO "
                    "orbit_task_audit(id,tenant_id,task_id,actor_id,request_id,action,created_a"
                    "t) VALUES(%s,%s,%s,1,%s,'GUARD_ROLLBACK_MARKER',UTC_TIMESTAMP(3))",
                    (marker, tenant, item["ids"]["task"], str(uuid4())),
                )
        with first.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM orbit_task WHERE tenant_id=%s AND id=%s FOR UPDATE", (tenant, task)
            )
            cursor.fetchone()
        with second.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM orbit_launch_execution_preparation WHERE tenant_id=%s AND "
                "id=%s FOR UPDATE",
                (tenant, prep),
            )
            cursor.fetchone()

        def task_then_prep():
            try:
                with first.cursor() as cursor:
                    cursor.execute(
                        "UPDATE orbit_task_node SET updated_at=UTC_TIMESTAMP(3) WHERE "
                        "tenant_id=%s AND task_id=%s AND ordinal=0",
                        (tenant, task),
                    )
                return None
            except pymysql.err.MySQLError as error:
                return error_number(error)

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(task_then_prep)
            _locked_wait(observer, first.thread_id(), pending=pending)
            try:
                with second.cursor() as cursor:
                    cursor.execute(
                        "UPDATE orbit_task SET updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=%s "
                        "AND id=%s",
                        (tenant, task),
                    )
                second_error = None
            except pymysql.err.MySQLError as error:
                second_error = error_number(error)
            # 必须先释放幸存者锁，另一连接才能结束；先记录1213受害者的自动整笔回滚。
            if second_error == 1213:
                with second.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_task_audit WHERE id=%s", (markers[1],)
                    )
                    assert cursor.fetchone()[0] == 0
            second.rollback()
            first_error = pending.result(timeout=7)
            if first_error == 1213:
                with first.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM orbit_task_audit WHERE id=%s", (markers[0],)
                    )
                    assert cursor.fetchone()[0] == 0
            assert sorted([code or 0 for code in (first_error, second_error)]) == [0, 1213], {
                "actual_errnos": [first_error, second_error]
            }
            first.rollback()
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_task_audit WHERE id IN(%s,%s)", tuple(markers)
            )
            assert cursor.fetchone()[0] == 0
        cases.append(LAUNCH_EXECUTION_GUARD_CASES[10])
    finally:
        observer.close()
        for connection in connections:
            connection.rollback()
            connection.close()
