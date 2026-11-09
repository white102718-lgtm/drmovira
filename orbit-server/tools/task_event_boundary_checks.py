"""T2边界真实MySQL/SSE工具；不改生产时钟、不执行平台请求。"""

import asyncio
import re
import time
from contextlib import contextmanager
from datetime import UTC, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TASK_EVENT_BOUNDARY_CASES = [
    "pythonTaskEventIdleStreamNoSameTransactionBeyondOneSecond",
    "pythonTaskEventExactDatabaseUtcSevenDayMinusEqualPlusMillisecond",
    "pythonTaskEventDeleteFailureRollsBackPayloadAndRetentionWatermark",
    "pythonTaskEventReaderAndPurgeSerializeWithoutSilentGap",
    "pythonTaskEventConcurrentPublishersKeepTaskNodeSequenceDirectoryAndAuditConsistent",
    "pythonTaskEventActuallySignedExpiredCheckpointRejected",
    "pythonTaskEventReadableCrossActorCannotBorrowSnapshotCheckpoint",
]

TRANSACTION_SQL = """
 SELECT t.trx_id,t.trx_mysql_thread_id,t.trx_state,t.trx_query IS NULL,
        t.trx_rows_locked,t.trx_lock_structs
 FROM information_schema.innodb_trx t
 JOIN information_schema.processlist p ON p.ID=t.trx_mysql_thread_id
 WHERE p.DB=%s AND p.ID<>CONNECTION_ID()
"""


@contextmanager
def hold_idle_stream(client, url, headers):
    """采样期间强持响应及iterator，不能让GeneratorExit先关闭底层HTTP1流。"""
    with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200, {"actual": response.status_code, "expected": 200}
        lines = response.iter_lines()
        try:
            assert next(lines) == ": keepalive"
            yield lines
        finally:
            lines.close()


def confirm_keepalive(lines):
    """采样结束真实继续读取，跳过前一帧空行但不接受撤权或业务data。"""
    for _ in range(3):
        line = next(lines)
        if line:
            assert line == ": keepalive"
            return
    raise AssertionError("采样后未读到真实keepalive")


def epoch_seconds(value):
    """以整数毫秒避免float舍入，输入为数据库UTC DATETIME(3)。"""
    aware = value.replace(tzinfo=UTC)
    return Decimal(int(aware.timestamp()) * 1000 + aware.microsecond // 1000) / Decimal(1000)


class TransactionObservation:
    """按连续trx_id寿命判断，连接Sleep或不同短事务不能冒充长事务。"""

    def __init__(self):
        self.first_seen, self.longest = {}, 0.0
        self.samples, self.maximum_rows_locked = 0, 0

    def add(self, rows, now):
        self.samples += 1
        active = {str(row[0]) for row in rows}
        self.first_seen = {key: value for key, value in self.first_seen.items() if key in active}
        for row in rows:
            key = str(row[0])
            first = self.first_seen.setdefault(key, now)
            self.longest = max(self.longest, now - first)
            self.maximum_rows_locked = max(self.maximum_rows_locked, int(row[4]))
        assert self.longest <= 1.0, {"same_trx_observed_seconds": self.longest}


def run_task_event_boundary_checks(
    client, admin, headers, password, cache, database, cases, *, cipher
):
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database) or (
        admin.host != "127.0.0.1" or admin.port != 13306
    ):
        raise ValueError("事件边界专项仅允许当前13306/UUID库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_id=990384")
        assert cursor.fetchone()[0] == 0, "事件边界身份ID已占用，拒绝覆盖"
    cap = client.get("/api/v1/roles/capabilities", headers=headers)
    assert cap.status_code == 200
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": cap.json()["csrf_token"],
            "Idempotency-Key": "event-boundary-" + uuid4().hex,
        },
        json={
            "name": "事件边界只读-" + uuid4().hex[:12],
            "menu_codes": ["launch"],
            "permission_codes": ["tasks.read"],
        },
    )
    assert role.status_code == 201
    username = "event_boundary_" + uuid4().hex[:12]
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role.json()["id"]),
        )
        role_id = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "SELECT 990384,%s,'事件边界夹具',%s,password,'0','0' FROM sys_user WHERE user_id=1",
            (username, username + "@fixture.example.org"),
        )
        cursor.execute(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(990384,%s,1,UTC_TIMESTAMP(3))",
            (str(uuid4()),),
        )
        cursor.execute("INSERT INTO sys_user_role(user_id,role_id) VALUES(990384,%s)", (role_id,))
        cursor.execute(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) "
            "VALUES(990384,%s,'TEAM_ADMIN')",
            (tenant,),
        )
        cursor.execute(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,display_name,"
            "invited,created_at) VALUES(%s,%s,990384,%s,'事件边界夹具',0,UTC_TIMESTAMP(3))",
            (tenant, str(uuid4()), team),
        )
        cursor.execute(
            "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) "
            "VALUES(%s,990384,%s)",
            (tenant, team),
        )
    admin.commit()
    from fixture_login import fixture_login

    login = fixture_login(client, cache, {"username": username, "password": password})
    assert login.status_code == 200
    team_headers = {"Authorization": "Bearer " + login.json()["token"]}

    def decode(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decode(admin.user),
        password=decode(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )
    metrics = {"blocked_cases": []}

    async def main():
        from pymysql.err import MySQLError
        from task_core_fixture import compile_dag, insert_plan, plan

        from orbit_api.directory_tokens import DirectoryTokens
        from orbit_api.errors import OrbitError
        from orbit_api.task_contract import node_id, validate_dag
        from orbit_api.task_event_contract import PURPOSE
        from orbit_api.task_event_publisher import publish_fixture_running
        from orbit_api.task_event_store import TaskEventStore
        from orbit_api.task_manifest import TaskManifestStore

        engine = create_async_engine(url, echo=False)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        manifest, events = TaskManifestStore(), TaskEventStore(DirectoryTokens(cipher))

        async def call(operation):
            async with sessions() as session, session.begin():
                return await operation(session)

        async def new():
            value = plan(owner, team, copies=1)
            graph = compile_dag(value)
            source = await call(lambda s: insert_plan(s, tenant, value))
            task = await call(
                lambda s: manifest.begin(
                    s, 1, source, 1, graph, str(uuid4()), producer="ISOLATED_TEST"
                )
            )
            records = validate_dag(graph)
            await call(lambda s: manifest.append(s, 1, task, 0, records))
            await call(lambda s: manifest.finalize(s, 1, task))
            detail = client.get("/api/v1/tasks/" + task, headers=headers)
            assert detail.status_code == 200
            return task, records, detail

        def rejected(task, event, token, identity=headers):
            with client.stream(
                "GET",
                f"/api/v1/tasks/{task}/events",
                headers=identity
                | {
                    "Last-Event-ID": event,
                    "X-Task-Event-Checkpoint": token,
                },
            ) as response:
                assert response.status_code == 400
                response.read()
                assert response.json()["code"] == "EVENT_CURSOR_INVALID"

        def age(task):
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_task_event SET occurred_at=UTC_TIMESTAMP(3)-INTERVAL 8 DAY "
                    "WHERE tenant_id=%s AND task_id=%s",
                    (tenant, task),
                )
                cursor.execute(
                    "UPDATE orbit_task_event_cursor "
                    "SET occurred_at=UTC_TIMESTAMP(3)-INTERVAL 8 DAY,"
                    "expires_at=UTC_TIMESTAMP(3)-INTERVAL 1 DAY WHERE tenant_id=%s AND task_id=%s",
                    (tenant, task),
                )
            admin.commit()

        try:
            task, records, detail = await new()
            event_id = detail.json()["latest_event_id"]
            with hold_idle_stream(
                client, f"/api/v1/tasks/{task}/events", headers | {"Last-Event-ID": event_id}
            ) as idle_lines:
                observation = TransactionObservation()
                deadline = time.monotonic() + 2.2
                denied_errno = None
                while time.monotonic() < deadline:
                    try:
                        with admin.cursor() as cursor:
                            cursor.execute(TRANSACTION_SQL, (database,))
                            rows = cursor.fetchall()
                    except MySQLError as error:
                        if error.args[0] not in {1142, 1227}:
                            raise
                        denied_errno = error.args[0]
                        break
                    observation.add(rows, time.monotonic())
                    await asyncio.sleep(0.1)
                if denied_errno is None:
                    assert observation.samples >= 10
                    metrics["idle_transaction_observation"] = {
                        "samples": observation.samples,
                        "same_trx_max_seconds": observation.longest,
                        "maximum_rows_locked_at_sample": observation.maximum_rows_locked,
                    }
                else:
                    metrics["blocked_cases"].append(
                        {
                            "case": TASK_EVENT_BOUNDARY_CASES[0],
                            "reason": "MYSQL_OBSERVATION_PERMISSION",
                            "errno": denied_errno,
                        }
                    )
                confirm_keepalive(idle_lines)
                if denied_errno is None:
                    cases.append(TASK_EVENT_BOUNDARY_CASES[0])

            # 只固定独立工具连接；先证明UTC_TIMESTAMP实际固定，再测试原store，不能假精确。
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT expires_at FROM orbit_task_event_cursor WHERE tenant_id=%s "
                    "AND task_id=%s AND event_id=%s",
                    (tenant, task, event_id),
                )
                expiry = cursor.fetchone()[0]
            boundary_engine = create_async_engine(url, echo=False)
            boundary_sessions = async_sessionmaker(boundary_engine, expire_on_commit=False)
            boundary_results = []
            try:
                for offset in (-1, 0, 1):
                    reference = expiry + timedelta(milliseconds=offset)
                    async with boundary_sessions() as session:
                        try:
                            async with session.begin():
                                await session.execute(text("SET time_zone = '+00:00'"))
                                await session.execute(
                                    text("SET timestamp = :value"),
                                    {"value": epoch_seconds(reference)},
                                )
                                actual = (
                                    await session.execute(text("SELECT UTC_TIMESTAMP(3)"))
                                ).scalar_one()
                                assert actual == reference, (
                                    "隔离连接UTC时钟未按毫秒固定，不能声称精确边界"
                                )
                                try:
                                    after = await events.start(session, 1, task, event_id)
                                except OrbitError as error:
                                    assert (
                                        offset >= 0
                                        and error.status == 410
                                        and error.code == "EVENT_CURSOR_EXPIRED"
                                    )
                                    boundary_results.append({"offset_ms": offset, "status": 410})
                                else:
                                    assert offset == -1 and after == 1
                                    boundary_results.append({"offset_ms": offset, "status": 200})
                        finally:
                            await session.execute(text("SET timestamp = 0"))
                            await session.rollback()
            finally:
                await boundary_engine.dispose()
            metrics["exact_sql_utc_boundary"] = boundary_results
            cases.append(TASK_EVENT_BOUNDARY_CASES[1])

            rollback_task, _, _ = await new()
            age(rollback_task)
            with admin.cursor() as cursor:
                cursor.execute(
                    "CREATE TRIGGER task_event_boundary_delete_fail "
                    "BEFORE DELETE ON orbit_task_event FOR EACH ROW "
                    "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-cleanup-rollback'"
                )
            try:
                try:
                    await call(lambda s: events.purge(s, 1, rollback_task))
                except DBAPIError as error:
                    assert error.orig.args[0] == 1644
                else:
                    raise AssertionError("清理故障未回滚")
            finally:
                with admin.cursor() as cursor:
                    cursor.execute("DROP TRIGGER task_event_boundary_delete_fail")
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_task_event WHERE tenant_id=%s AND task_id=%s",
                    (tenant, rollback_task),
                )
                assert cursor.fetchone()[0] == 1
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_task_event_cursor "
                    "WHERE tenant_id=%s AND task_id=%s",
                    (tenant, rollback_task),
                )
                assert cursor.fetchone()[0] == 1
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_task_event_retention "
                    "WHERE tenant_id=%s AND task_id=%s",
                    (tenant, rollback_task),
                )
                assert cursor.fetchone()[0] == 0
            cases.append(TASK_EVENT_BOUNDARY_CASES[2])
            metrics["cleanup_rollback"] = {
                "injected_errno": 1644,
                "payload": 1,
                "directory": 1,
                "retention_rows": 0,
            }

            # after=1快照已经读过老事件，批读合法空；读事务SHARE锁阻止同Task清理X锁。
            async with sessions() as reader:
                async with reader.begin():
                    assert await events.batch(reader, 1, rollback_task, 1) == []

                    async def waiting_purge():
                        async with sessions() as writer, writer.begin():
                            await writer.execute(text("SET innodb_lock_wait_timeout=1"))
                            return await events.purge(writer, 1, rollback_task)

                    try:
                        wait_started = time.monotonic()
                        await asyncio.wait_for(waiting_purge(), 3)
                    except DBAPIError as error:
                        assert error.orig.args[0] == 1205
                        metrics["reader_purge_lock_wait"] = {
                            "errno": 1205,
                            "seconds": time.monotonic() - wait_started,
                        }
                    else:
                        raise AssertionError("清理应真实等待尚未结束的Task读锁")
            # 读锁释放后重试真实清理，不将锁等待超时冒充清理成功。
            assert await call(lambda s: events.purge(s, 1, rollback_task)) == 1
            assert await call(lambda s: events.batch(s, 1, rollback_task, 1)) == []
            try:
                await call(lambda s: events.start(s, 1, rollback_task, None))
            except OrbitError as error:
                assert error.status == 410
            else:
                raise AssertionError("已裁剪未读事件被当成空闲")
            cases.append(TASK_EVENT_BOUNDARY_CASES[3])

            async def publish(index):
                return await call(
                    lambda s: publish_fixture_running(
                        s,
                        1,
                        task,
                        node_id(task, records[index]["node_key"]),
                        str(uuid4()),
                        producer="ISOLATED_TEST",
                    )
                )

            concurrent_started = time.monotonic()
            emitted = await asyncio.wait_for(asyncio.gather(publish(0), publish(1)), 5)
            assert len(set(emitted)) == 2
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT revision,latest_sequence,state FROM orbit_task "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, task),
                )
                assert cursor.fetchone() == (3, 3, "RUNNING")
                for table in (
                    "orbit_task_event",
                    "orbit_task_event_cursor",
                    "orbit_task_audit",
                    "orbit_task_outbox",
                ):
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE tenant_id=%s AND task_id=%s",
                        (tenant, task),
                    )
                    assert cursor.fetchone()[0] == 3
                cursor.execute(
                    "SELECT sequence,task_revision,state FROM orbit_task_event "
                    "WHERE tenant_id=%s AND task_id=%s ORDER BY sequence",
                    (tenant, task),
                )
                assert cursor.fetchall() == ((1, 1, "QUEUED"), (2, 2, "RUNNING"), (3, 3, "RUNNING"))
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_task_node WHERE tenant_id=%s AND task_id=%s "
                    "AND state='RUNNING' AND external_id IS NULL AND attempt=0",
                    (tenant, task),
                )
                assert cursor.fetchone()[0] == 2
            cases.append(TASK_EVENT_BOUNDARY_CASES[4])
            metrics["two_publisher_protocol"] = {
                "seconds": time.monotonic() - concurrent_started,
                "revision": 3,
                "sequence": 3,
                "running_nodes": 2,
            }
            current = client.get("/api/v1/tasks/" + task, headers=headers)
            assert current.status_code == 200
            token = current.headers["x-task-event-checkpoint"]
            claims = DirectoryTokens(cipher).verify(PURPOSE, token)
            expired_token = DirectoryTokens(cipher).issue(
                PURPOSE,
                {key: value for key, value in claims.items() if key not in {"exp", "kid"}},
                ttl=-1,
            )
            rejected(task, current.json()["latest_event_id"], expired_token)
            cases.append(TASK_EVENT_BOUNDARY_CASES[5])
            metrics["expired_checkpoint_status"] = 400
            readable = client.get("/api/v1/tasks/" + task, headers=team_headers)
            assert readable.status_code == 200  # 明确已过对象范围授权，不用先404掩盖token绑定错误。
            rejected(task, current.json()["latest_event_id"], token, team_headers)
            cases.append(TASK_EVENT_BOUNDARY_CASES[6])
            metrics["readable_cross_actor_checkpoint_status"] = 400
            return metrics
        finally:
            await engine.dispose()

    return asyncio.run(main())
