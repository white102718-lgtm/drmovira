"""只读候选目录真实SQL；明确技术authority/DB损坏注入，零claim/send/平台写。"""

import asyncio
import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, timedelta
from unittest.mock import Mock
from uuid import uuid4

from pymysql import MySQLError
from sqlalchemy import URL, event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from orbit_api.authorization import require_business_access
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_candidates import (
    CandidateGrant,
    ExecutionCandidateAuthority,
    ExecutionCandidateDirectory,
)

if __package__:
    from .launch_execution_fixture import create_protocol_plan
    from .launch_execution_lease_checks import guard_execution_lease_target
else:
    from launch_execution_fixture import create_protocol_plan
    from launch_execution_lease_checks import guard_execution_lease_target

EXECUTION_CANDIDATE_CASES = [
    "pythonExecutionCandidateDefaultUnavailableBeforeDatabaseInitialization",
    "pythonExecutionCandidateReal202CompleteManifestReadonly",
    "pythonExecutionCandidateFourPageSizesExactRawKeysetAndFullCoverage",
    "pythonExecutionCandidateAllParentsSucceededAndCancelledTerminalNotRevived",
    "pythonExecutionCandidateCurrentAttemptFenceBindingNeverReclaimed",
    "pythonExecutionCandidateCurrentOwnerSourceAndExpiryFailClosed",
    "pythonExecutionCandidateActualCurrentScopeRevocationFailsClosed",
    "pythonExecutionCandidateFinalGrantDriftDiscardsSameTransactionPage",
    "pythonExecutionCandidateOriginalImmutableTriggersRejectMutation",
    "pythonExecutionCandidateTechnicalDatabaseByteCorruptionRejectedAndRestored",
    "pythonExecutionCandidateTechnicalCommandConfigurationCorruptionRejectedAndRestored",
    "pythonExecutionCandidateTechnicalGraphEdgeCorruptionRejectedAndRestored",
]

TRIGGER_TABLES = {
    "guard_execution_byte_update": "orbit_launch_execution_byte_chunk",
    "guard_execution_command_update": "orbit_launch_execution_command",
    "guard_execution_task_update": "orbit_task",
    "guard_execution_edge_update": "orbit_task_edge",
}


def candidate_directory(authority, sessions):
    """传递会创建AsyncSession的工厂本身，不能再包成返回工厂的lambda。"""
    if not isinstance(sessions, async_sessionmaker):
        raise TypeError("ASYNC_SESSIONMAKER_REQUIRED")
    return ExecutionCandidateDirectory(authority, sessions)


class CandidateFixtureCleanupError(RuntimeError):
    """仅内部清理失败信号；主线必须保留本轮UUID库，不接收外部开关。"""

    preserve_fixture_database = True

    def __init__(self, trigger, phase):
        if trigger not in TRIGGER_TABLES or phase not in {
            "row-restore",
            "trigger-restore",
            "snapshot-restore",
        }:
            raise ValueError("清理诊断只允许精确护栏与固定阶段")
        self.trigger, self.phase = trigger, phase
        super().__init__("CANDIDATE_FIXTURE_CLEANUP_UNVERIFIED:" + trigger + ":" + phase)


def _admin_rows(admin, sql, params=()):
    with admin.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    admin.commit()
    return rows


def trigger_definition(admin, database, name):
    """只读精确原定义到内存，不输出含DEFINER的DDL。"""
    guard_execution_lease_target(admin, database)
    if name not in TRIGGER_TABLES:
        raise ValueError("仅允许本工具四个精确UPDATE护栏")
    if _admin_rows(admin, "SELECT DATABASE()")[0][0] != database:
        raise ValueError("实际数据库与本轮UUID不符")
    rows = _admin_rows(
        admin,
        "SELECT EVENT_OBJECT_TABLE,ACTION_TIMING,EVENT_MANIPULATION,ACTION_STATEMENT "
        "FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND TRIGGER_NAME=%s",
        (database, name),
    )
    if len(rows) != 1 or rows[0][:3] != (TRIGGER_TABLES[name], "BEFORE", "UPDATE"):
        raise ValueError("原触发器定义不符合本轮精确白名单")
    with admin.cursor() as cursor:
        cursor.execute("SHOW CREATE TRIGGER `" + name + "`")
        columns = [column[0] for column in cursor.description]
        values = cursor.fetchone()
    admin.commit()
    row = dict(zip(columns, values, strict=True))
    ddl = row.get("SQL Original Statement")
    if (
        not isinstance(ddl, str)
        or not re.search(r"\bTRIGGER\s+`?" + re.escape(name) + r"`?\s+BEFORE\s+UPDATE\b", ddl, re.I)
        or not rows[0][3]
    ):
        raise ValueError("SHOW CREATE必须为同名真实UPDATE定义")
    return ddl, rows[0][3]


@contextmanager
def technical_corruption_trigger(admin, database, name):
    """仅独占disposable UUID数据库技术损坏阶段；finally恢复同名原DDL。"""
    original = trigger_definition(admin, database, name)
    dropped = False
    try:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER `" + name + "`")
            dropped = True
        admin.commit()
        yield
    finally:
        if dropped:
            try:
                with admin.cursor() as cursor:
                    cursor.execute(original[0])
                admin.commit()
                current = trigger_definition(admin, database, name)
                if (
                    current != original
                    or hashlib.sha256(canonical(current).encode()).hexdigest()
                    != hashlib.sha256(canonical(original).encode()).hexdigest()
                ):
                    raise ValueError("原护栏恢复定义未一致")
            except BaseException:
                print(
                    json.dumps(
                        {
                            "scope": "execution-candidate-fixture",
                            "phase": "trigger-cleanup-unverified",
                            "cleanup_complete": False,
                        }
                    ),
                    flush=True,
                )
                raise CandidateFixtureCleanupError(name, "trigger-restore") from None


class IsolatedCandidateAuthority(ExecutionCandidateAuthority):
    """固定原SQL受理来源+真实当前原动作；不证明Meta/设备/预算/transport。"""

    def __init__(self, database, grant):
        self.database, self.grant = database, grant
        self.calls = 0
        self.final_drift = False

    async def capture(self, task_id):
        if task_id != self.grant.task_id:
            raise OrbitError(503, "ISOLATED_CANDIDATE_SOURCE_REJECTED", "仅允许本轮完整Task")
        self.calls = 0
        return self.grant

    async def revalidate(self, session, grant):
        url = session.get_bind().engine.url
        guard_execution_lease_target(url, self.database)
        if (await session.execute(text("SELECT DATABASE()"))).scalar_one() != self.database:
            raise ValueError("隔离数据库不一致")
        current = await require_business_access(
            session, grant.actor_id, "launch", "launch.execute", acting_subject=False
        )
        row = (
            await session.execute(
                text(
                    "SELECT b.tenant_id,b.id,b.team_id,i.auth_version FROM orbit_business_user b "
                    "JOIN sys_identity_subject i ON i.user_id=b.user_id "
                    "WHERE b.user_id=:actor AND b.enabled=1 AND b.invited=0 FOR SHARE"
                ),
                {"actor": grant.actor_id},
            )
        ).one()
        if (current.tenant_id, current.subject_id, row[0], row[1], row[2], row[3]) != (
            grant.tenant_id,
            grant.subject_id,
            grant.tenant_id,
            grant.subject_id,
            grant.owner_team_id,
            grant.auth_revision,
        ) or current.subject_id != grant.owner_user_id:
            raise OrbitError(503, "ISOLATED_CANDIDATE_IDENTITY_CHANGED", "当前隔离来源身份已变化")
        self.calls += 1
        if self.final_drift and self.calls == 2:
            return replace(grant, auth_revision=grant.auth_revision + 1)
        return grant


def run_execution_candidate_checks(client, admin, headers, password, cache, database, cases):
    guard_execution_lease_target(admin, database)
    if _admin_rows(admin, "SELECT DATABASE()")[0][0] != database:
        raise ValueError("必须本轮实际UUID数据库")

    def query(sql, params=()):
        return _admin_rows(admin, sql, params)

    def write(sql, params=()):
        assert sql.count("%s") == len(params), "FIXTURE_PARAMETER_BINDING_MUST_BE_EXACT"
        with admin.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount

    def transaction(statements):
        admin.begin()
        try:
            for sql, params in statements:
                assert write(sql, params) >= 0
            admin.commit()
        except BaseException:
            admin.rollback()
            raise

    def checked(response, status):
        assert response.status_code == status, {
            "expected_status": status,
            "actual_status": response.status_code,
        }
        return response.json()

    tenant, owner, team, auth_version = query(
        "SELECT b.tenant_id,b.id,b.team_id,i.auth_version FROM orbit_business_user b "
        "JOIN sys_identity_subject i ON i.user_id=b.user_id WHERE b.user_id=1"
    )[0]
    csrf = checked(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)[
        "csrf_token"
    ]
    item = create_protocol_plan(admin, tenant, owner, team, copies=70)

    def action(revision):
        return headers | {
            "X-CSRF-Token": csrf,
            "If-Match": f'"{revision}"',
            "Idempotency-Key": str(uuid4()),
        }

    validation = checked(
        client.post(
            f"/api/v1/launch-plans/{item['id']}/validate", headers=action(1), json=item["body"]
        ),
        200,
    )
    assert validation["valid"] is True
    task = checked(
        client.post(
            f"/api/v1/launch-plans/{item['id']}/execute",
            headers=action(2),
            json={"hash": validation["hash"], "activate_ack": False},
        ),
        202,
    )
    task_id = task["id"]
    assert task["state"] == "QUEUED" and 200 < task["node_count"] <= 1000
    prep = query(
        "SELECT p.id,p.source_revision,p.payload_hash,p.manifest_hash,p.intent_hash,p.subject_id,"
        "p.actor_id, p.authorization_fingerprint, t.execution_mode FROM "
        "orbit_launch_execution_preparation "
        "p JOIN orbit_task t ON t.tenant_id=p.tenant_id AND t.id=p.task_id "
        "WHERE p.tenant_id=%s AND p.task_id=%s",
        (tenant, task_id),
    )
    # 显式列消除JOIN同名；mode取原Task，非猜测默认。
    if len(prep) != 1:
        raise AssertionError("COMPLETE_PREPARATION_REQUIRED")
    prep = prep[0]
    now = query("SELECT UTC_TIMESTAMP(6)")[0][0].replace(tzinfo=UTC)
    grant = CandidateGrant(
        tenant,
        task_id,
        1,
        prep[5],
        owner,
        team,
        auth_version,
        prep[1],
        prep[2],
        prep[3],
        prep[4],
        now + timedelta(minutes=5),
    )
    nodes = query(
        "SELECT id, ordinal, state, attempt FROM orbit_task_node WHERE tenant_id=%s AND "
        "task_id=%s ORDER BY ordinal",
        (tenant, task_id),
    )
    assert len(nodes) == task["node_count"] and [row[1] for row in nodes] == list(range(len(nodes)))

    def snapshot():
        result = {}
        for table, predicate, order in [
            ("orbit_task", "id", "id"),
            ("orbit_task_node", "task_id", "ordinal"),
            ("orbit_task_chunk", "task_id", "ordinal"),
            ("orbit_task_edge", "task_id", "child_id,parent_id"),
            ("orbit_launch_execution_preparation", "task_id", "id"),
            ("orbit_launch_execution_command", "task_id", "ordinal"),
            ("orbit_launch_execution_acceptance", "task_id", "task_id"),
            ("orbit_execution_command_runtime", "task_id", "node_id"),
            ("orbit_execution_attempt", "task_id", "node_id,attempt_no"),
            ("orbit_execution_attempt_fact", "task_id", "node_id,attempt_no,sequence_no"),
            ("orbit_task_event", "task_id", "sequence"),
            ("orbit_task_audit", "task_id", "id"),
            ("orbit_task_outbox", "task_id", "audit_id"),
        ]:
            result[table] = query(
                "SELECT * FROM "
                + table
                + " WHERE tenant_id=%s AND "
                + predicate
                + "=%s ORDER BY "
                + order,
                (tenant, task_id),
            )
        result["bytes"] = query(
            "SELECT * FROM orbit_launch_execution_byte_chunk WHERE tenant_id=%s AND "
            "preparation_id=%s ORDER BY ordinal",
            (tenant, prep[0]),
        )
        result["clock"] = query("SELECT * FROM orbit_task_clock WHERE tenant_id=%s", (tenant,))
        return result

    def expected_candidates(after, limit):
        raw = query(
            "SELECT id, ordinal FROM orbit_task_node WHERE tenant_id=%s AND task_id=%s AND "
            "ordinal>%s ORDER BY ordinal LIMIT %s",
            (tenant, task_id, -1 if after is None else after, limit),
        )
        expected = query(
            "SELECT n.id,n.ordinal FROM orbit_task_node n JOIN orbit_launch_execution_command c "
            "ON c.tenant_id=n.tenant_id AND c.task_id=n.task_id AND c.node_id=n.id "
            "JOIN orbit_task t ON t.tenant_id=n.tenant_id AND t.id=n.task_id "
            "WHERE n.tenant_id=%s AND n.task_id=%s AND n.ordinal>%s AND n.ordinal<=%s "
            "AND n.state='QUEUED' AND c.state='QUEUED' AND n.attempt=0 AND c.attempt=0 "
            "AND t.state IN('QUEUED','RUNNING') AND NOT EXISTS(SELECT 1 FROM orbit_task_edge e "
            "JOIN orbit_task_node p ON p.tenant_id=e.tenant_id AND p.task_id=e.task_id "
            "AND p.id=e.parent_id "
            "WHERE e.tenant_id=n.tenant_id AND e.task_id=n.task_id AND e.child_id=n.id "
            "AND p.state<>'SUCCEEDED') ORDER BY n.ordinal",
            (tenant, task_id, -1 if after is None else after, raw[-1][1] if raw else -1),
        )
        return raw, list(expected)

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
        sql_reads, directory_calls, restored = [0], [0], [0]

        def readonly(connection, cursor, statement, parameters, context, many):
            keyword = statement.lstrip().split(None, 1)[0].upper()
            assert keyword in {"SELECT", "SET"}, "DIRECTORY_MUST_NOT_WRITE"
            if keyword == "SELECT":
                sql_reads[0] += 1

        event.listen(engine.sync_engine, "before_cursor_execute", readonly)

        async def page(*, value=grant, after=None, limit=200, authority=None):
            before = snapshot()
            directory_calls[0] += 1
            try:
                return await candidate_directory(
                    authority or IsolatedCandidateAuthority(database, value), sessions
                ).page(task_id, after_ordinal=after, limit=limit)
            finally:
                assert snapshot() == before, "DIRECTORY_CHANGED_DURABLE_TABLES"

        async def denied(**kwargs):
            try:
                await page(**kwargs)
            except OrbitError as error:
                assert error.status in {403, 503}
                return error.code
            raise AssertionError("DIRECTORY_MUST_FAIL_CLOSED")

        async def corrupt(name, mutate, restore):
            baseline = snapshot()
            with technical_corruption_trigger(admin, database, name):
                try:
                    transaction([mutate])
                    assert await denied() == "EXECUTION_DIRECTORY_UNVERIFIED"
                finally:
                    try:
                        transaction([restore])
                    except BaseException:
                        print(
                            json.dumps(
                                {
                                    "scope": "execution-candidate-fixture",
                                    "phase": "row-cleanup-unverified",
                                    "cleanup_complete": False,
                                }
                            ),
                            flush=True,
                        )
                        raise CandidateFixtureCleanupError(name, "row-restore") from None
            try:
                if snapshot() != baseline:
                    raise CandidateFixtureCleanupError(name, "snapshot-restore")
            except BaseException:
                raise CandidateFixtureCleanupError(name, "snapshot-restore") from None
            restored[0] += 1

        try:
            factory = Mock(return_value=sessions)
            before = sql_reads[0]
            try:
                await ExecutionCandidateDirectory(sessions_factory=factory).page(task_id)
            except OrbitError as error:
                assert error.code == "EXECUTION_DIRECTORY_AUTHORITY_UNAVAILABLE"
            else:
                raise AssertionError("DEFAULT_AUTHORITY_MUST_DENY")
            factory.assert_not_called()
            assert sql_reads[0] == before
            cases.append(EXECUTION_CANDIDATE_CASES[0])
            first = await page()
            assert first.execution_authorized is False and first.raw_rows == 200
            assert first.next_ordinal == 199
            assert [(row.node_id, row.ordinal) for row in first.items] == expected_candidates(
                None, 200
            )[1]
            cases.append(EXECUTION_CANDIDATE_CASES[1])
            page_counts = {}
            for limit in (20, 50, 100, 200):
                after, raw_total, ordinals, candidates = None, 0, [], []
                count = 0
                while True:
                    raw, expected = expected_candidates(after, limit)
                    current = await page(after=after, limit=limit)
                    assert current.raw_rows == len(raw)
                    assert [(row.node_id, row.ordinal) for row in current.items] == expected
                    raw_total += current.raw_rows
                    ordinals.extend(row[1] for row in raw)
                    candidates.extend(row.node_id for row in current.items)
                    count += 1
                    if current.next_ordinal is None:
                        break
                    assert current.next_ordinal == raw[-1][1] and (
                        after is None or current.next_ordinal > after
                    )
                    after = current.next_ordinal
                    assert count <= len(nodes)
                assert raw_total == len(nodes) and ordinals == list(range(len(nodes)))
                assert len(candidates) == len(set(candidates))
                page_counts[str(limit)] = count
            assert all(count > 1 for count in page_counts.values())
            cases.append(EXECUTION_CANDIDATE_CASES[2])

            target = nodes[-1][0]

            def runtime_statements(state):
                return [
                    (
                        "UPDATE orbit_task_node SET state=%s WHERE tenant_id=%s AND task_id=%s",
                        (state, tenant, task_id),
                    ),
                    (
                        "UPDATE orbit_launch_execution_command SET state=%s WHERE tenant_id=%s AND "
                        "task_id=%s",
                        (state, tenant, task_id),
                    ),
                ]

            baseline = snapshot()
            try:
                # 明确技术SQL父状态，不冒充真实平台执行成功或claim。
                transaction(
                    runtime_statements("SUCCEEDED")
                    + [
                        (
                            "UPDATE orbit_task_node SET state='QUEUED' WHERE tenant_id=%s AND "
                            "task_id=%s AND id=%s",
                            (tenant, task_id, target),
                        ),
                        (
                            "UPDATE orbit_launch_execution_command SET state='QUEUED' WHERE "
                            "tenant_id=%s AND task_id=%s AND node_id=%s",
                            (tenant, task_id, target),
                        ),
                    ]
                )
                current = await page(after=len(nodes) - 2)
                assert [row.node_id for row in current.items] == [target]
                for terminal in ("CANCELLED", "FAILED", "UNKNOWN", "RETRY_WAIT", "SUCCEEDED"):
                    transaction(
                        [
                            (
                                "UPDATE orbit_task_node SET state=%s WHERE tenant_id=%s AND "
                                "task_id=%s AND id=%s",
                                (terminal, tenant, task_id, target),
                            ),
                            (
                                "UPDATE orbit_launch_execution_command SET state=%s WHERE "
                                "tenant_id=%s AND task_id=%s AND node_id=%s",
                                (terminal, tenant, task_id, target),
                            ),
                        ]
                    )
                    assert (await page(after=len(nodes) - 2)).items == ()
                transaction(
                    [
                        (
                            "UPDATE orbit_task_node SET state='QUEUED' "
                            "WHERE tenant_id=%s AND task_id=%s AND id=%s",
                            (tenant, task_id, target),
                        ),
                        (
                            "UPDATE orbit_launch_execution_command SET state='QUEUED' "
                            "WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                            (tenant, task_id, target),
                        ),
                    ]
                )
                for terminal_task in (
                    "CANCELLED",
                    "UNKNOWN",
                    "FAILED",
                    "SUCCEEDED",
                    "PARTIAL_SUCCESS",
                ):
                    transaction(
                        [
                            (
                                "UPDATE orbit_task SET state=%s WHERE tenant_id=%s AND id=%s",
                                (terminal_task, tenant, task_id),
                            )
                        ]
                    )
                    assert (await page(after=len(nodes) - 2)).items == ()
            finally:
                transaction(
                    runtime_statements("QUEUED")
                    + [
                        (
                            "UPDATE orbit_task SET state=%s WHERE tenant_id=%s AND id=%s",
                            (task["state"], tenant, task_id),
                        ),
                    ]
                )
            assert snapshot() == baseline
            cases.append(EXECUTION_CANDIDATE_CASES[3])

            current_node = nodes[0][0]
            command = query(
                "SELECT resolved_configuration_hash FROM orbit_launch_execution_command WHERE "
                "tenant_id=%s AND task_id=%s AND node_id=%s",
                (tenant, task_id, current_node),
            )[0][0]
            claim_id, worker_id = str(uuid4()), str(uuid4())
            # 显式SQL技术运行头，不调用产品claim或transport；历史不可变，留在自有UUID库。
            transaction(
                [
                    (
                        "INSERT INTO orbit_execution_attempt(tenant_id, task_id, node_id, "
                        "preparation_id, attempt_no, fencing_token, claim_id, worker_id, "
                        "execution_mode, command_hash, manifest_hash, source_hash, "
                        "authority_hash, authorization_hash, actor_id, subject_id, "
                        "owner_user_id, owner_team_id, auth_version, created_at) VALUES(%s, %s, "
                        "%s, %s, 1, 1, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, "
                        "UTC_TIMESTAMP(3))",
                        (
                            tenant,
                            task_id,
                            current_node,
                            prep[0],
                            claim_id,
                            worker_id,
                            prep[8],
                            command,
                            prep[3],
                            prep[2],
                            hashlib.sha256(b"ISOLATED_SQL_NOT_PLATFORM_OR_CLAIM").hexdigest(),
                            prep[7],
                            prep[5],
                            owner,
                            team,
                            auth_version,
                        ),
                    ),
                    (
                        "INSERT INTO orbit_execution_command_runtime(tenant_id, task_id, "
                        "node_id, revision, active_attempt, fencing_token, claim_id, worker_id, "
                        "lease_expires_at, created_at, updated_at) VALUES(%s, %s, %s, 1, 1, 1, "
                        "%s, %s, UTC_TIMESTAMP(3)+INTERVAL 1 MINUTE, UTC_TIMESTAMP(3), "
                        "UTC_TIMESTAMP(3))",
                        (tenant, task_id, current_node, claim_id, worker_id),
                    ),
                    (
                        "UPDATE orbit_task_node SET state='RUNNING', attempt=1 WHERE "
                        "tenant_id=%s AND task_id=%s AND id=%s",
                        (tenant, task_id, current_node),
                    ),
                    (
                        "UPDATE orbit_launch_execution_command SET state='RUNNING', attempt=1 "
                        "WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                        (tenant, task_id, current_node),
                    ),
                ]
            )
            assert current_node not in {row.node_id for row in (await page()).items}
            try:
                transaction(
                    [
                        (
                            "UPDATE orbit_task_node SET attempt=2 WHERE tenant_id=%s AND "
                            "task_id=%s AND id=%s",
                            (tenant, task_id, current_node),
                        ),
                        (
                            "UPDATE orbit_launch_execution_command SET attempt=2 WHERE "
                            "tenant_id=%s AND task_id=%s AND node_id=%s",
                            (tenant, task_id, current_node),
                        ),
                    ]
                )
                assert await denied() == "EXECUTION_DIRECTORY_UNVERIFIED"
            finally:
                transaction(
                    [
                        (
                            "UPDATE orbit_task_node SET attempt=1 WHERE tenant_id=%s AND "
                            "task_id=%s AND id=%s",
                            (tenant, task_id, current_node),
                        ),
                        (
                            "UPDATE orbit_launch_execution_command SET attempt=1 WHERE "
                            "tenant_id=%s AND task_id=%s AND node_id=%s",
                            (tenant, task_id, current_node),
                        ),
                    ]
                )
            cases.append(EXECUTION_CANDIDATE_CASES[4])

            for invalid in (
                replace(grant, owner_user_id=str(uuid4())),
                replace(grant, owner_team_id=str(uuid4())),
                replace(grant, source_revision=grant.source_revision + 1),
                replace(grant, source_hash="f" * 64),
                replace(grant, manifest_hash="f" * 64),
                replace(grant, expires_at=now - timedelta(seconds=1)),
            ):
                assert await denied(value=invalid) in {
                    "ISOLATED_CANDIDATE_IDENTITY_CHANGED",
                    "EXECUTION_DIRECTORY_UNVERIFIED",
                }
            cases.append(EXECUTION_CANDIDATE_CASES[5])

            scope_enabled = query("SELECT enabled FROM orbit_user_scope WHERE user_id=1")[0][0]
            try:
                transaction([("UPDATE orbit_user_scope SET enabled=0 WHERE user_id=1", ())])
                assert await denied() == "PERMISSION_DENIED"
            finally:
                transaction(
                    [("UPDATE orbit_user_scope SET enabled=%s WHERE user_id=1", (scope_enabled,))]
                )
            assert current_node not in {row.node_id for row in (await page()).items}
            cases.append(EXECUTION_CANDIDATE_CASES[6])

            drift = IsolatedCandidateAuthority(database, grant)
            drift.final_drift = True
            assert await denied(authority=drift) == "EXECUTION_DIRECTORY_AUTHORITY_CHANGED"
            assert drift.calls == 2
            cases.append(EXECUTION_CANDIDATE_CASES[7])

            byte = query(
                "SELECT ordinal, payload, byte_length, chunk_hash FROM "
                "orbit_launch_execution_byte_chunk WHERE tenant_id=%s AND preparation_id=%s "
                "ORDER BY ordinal LIMIT 1",
                (tenant, prep[0]),
            )[0]
            original_payload = bytes(byte[1])
            bad_payload = original_payload + b" "
            byte_mutation = (
                "UPDATE orbit_launch_execution_byte_chunk SET payload=%s, byte_length=%s, "
                "chunk_hash=%s WHERE tenant_id=%s AND preparation_id=%s AND ordinal=%s",
                (
                    bad_payload,
                    len(bad_payload),
                    hashlib.sha256(bad_payload).hexdigest(),
                    tenant,
                    prep[0],
                    byte[0],
                ),
            )
            byte_restore = (
                byte_mutation[0],
                (original_payload, byte[2], byte[3], tenant, prep[0], byte[0]),
            )
            command_row = query(
                "SELECT node_id, target_key, resolved_configuration_json FROM "
                "orbit_launch_execution_command WHERE tenant_id=%s AND task_id=%s ORDER BY "
                "ordinal LIMIT 1",
                (tenant, task_id),
            )[0]
            target_mutation = (
                "UPDATE orbit_launch_execution_command SET target_key=%s WHERE tenant_id=%s AND "
                "task_id=%s AND node_id=%s",
                ("ISOLATED_TECHNICAL_CORRUPTION", tenant, task_id, command_row[0]),
            )
            target_restore = (target_mutation[0], (command_row[1], tenant, task_id, command_row[0]))
            configuration = (
                json.loads(command_row[2])
                if isinstance(command_row[2], (str, bytes))
                else command_row[2]
            )
            config_mutation = (
                "UPDATE orbit_launch_execution_command SET resolved_configuration_json=%s WHERE "
                "tenant_id=%s AND task_id=%s AND node_id=%s",
                (
                    canonical(configuration | {"isolated_technical_corruption": True}),
                    tenant,
                    task_id,
                    command_row[0],
                ),
            )
            config_restore = (
                config_mutation[0],
                (canonical(configuration), tenant, task_id, command_row[0]),
            )
            graph = query(
                "SELECT graph_hash FROM orbit_task WHERE tenant_id=%s AND id=%s", (tenant, task_id)
            )[0][0]
            graph_mutation = (
                "UPDATE orbit_task SET graph_hash=%s WHERE tenant_id=%s AND id=%s",
                ("f" * 64, tenant, task_id),
            )
            graph_restore = (graph_mutation[0], (graph, tenant, task_id))
            edge = query(
                "SELECT child_id, parent_id FROM orbit_task_edge WHERE tenant_id=%s AND "
                "task_id=%s ORDER BY child_id, parent_id LIMIT 1",
                (tenant, task_id),
            )[0]
            assert edge[0] != edge[1]
            edge_mutation = (
                "UPDATE orbit_task_edge SET parent_id=%s WHERE tenant_id=%s AND task_id=%s AND "
                "child_id=%s AND parent_id=%s",
                (edge[0], tenant, task_id, edge[0], edge[1]),
            )
            edge_restore = (edge_mutation[0], (edge[1], tenant, task_id, edge[0], edge[0]))
            baseline = snapshot()
            for mutation, code in (
                (byte_mutation, "EXECUTION_IMMUTABLE_PAYLOAD"),
                (target_mutation, "EXECUTION_IMMUTABLE_INTENT"),
                (config_mutation, "EXECUTION_IMMUTABLE_INTENT"),
                (graph_mutation, "EXECUTION_IMMUTABLE_TASK_SOURCE"),
                (edge_mutation, "EXECUTION_IMMUTABLE_PAYLOAD"),
            ):
                try:
                    transaction([mutation])
                except MySQLError as error:
                    assert error.args == (1644, code)
                else:
                    raise AssertionError("ORIGINAL_IMMUTABLE_GUARD_MUST_REJECT")
                assert snapshot() == baseline
            await page()
            cases.append(EXECUTION_CANDIDATE_CASES[8])

            print("execution-candidate-fixture phase=technical-database-corruption", flush=True)
            await corrupt("guard_execution_byte_update", byte_mutation, byte_restore)
            cases.append(EXECUTION_CANDIDATE_CASES[9])
            await corrupt("guard_execution_command_update", target_mutation, target_restore)
            await corrupt("guard_execution_command_update", config_mutation, config_restore)
            cases.append(EXECUTION_CANDIDATE_CASES[10])
            await corrupt("guard_execution_task_update", graph_mutation, graph_restore)
            await corrupt("guard_execution_edge_update", edge_mutation, edge_restore)
            cases.append(EXECUTION_CANDIDATE_CASES[11])
            await page()
            return {
                "candidate_groups": len(EXECUTION_CANDIDATE_CASES),
                "actual_manifest_nodes": len(nodes),
                "page_counts": page_counts,
                "directory_calls": directory_calls[0],
                "directory_durable_writes": 0,
                "sql_reads": sql_reads[0],
                "claims": 0,
                "transport_calls": 0,
                "platform_writes": 0,
                "production_issuer": False,
                "technical_corruption_restored": restored[0],
                "cleanup_complete": True,
            }
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", readonly)
            await engine.dispose()

    return asyncio.run(internal())
