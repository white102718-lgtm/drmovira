"""036真实SQL/HTTP/SSE专项；受控ISOLATED_TEST状态不计平台真实执行。"""

import asyncio
import json
import re
import time
from contextlib import contextmanager
from uuid import uuid4

from sqlalchemy import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TASK_EVENT_STREAM_CASES = [
    "pythonTaskEventActualInitialCursorDirectoryAndStrictSseFrame",
    "pythonTaskEventProductionPublisherUnavailableWithoutWrites",
    "pythonTaskEventCheckpointAcceptsOlderSnapshotAfterActualNewRevision",
    "pythonTaskEventUnknownAndOtherTaskCursorUniformAuthorized400",
    "pythonTaskEventLogicalSevenDaysExpiredBeforePhysicalCleanup",
    "pythonTaskEventFreshSnapshotResumesFromExpiredLatestWithoutLoop",
    "pythonTaskEventUnreadExpiredAfterCheckpointStill410",
    "pythonTaskEventPhysicalPurgeKeepsCursorIdentityAnd410",
    "pythonTaskEventAtomicNodeTaskDirectoryAuditOutboxRollback",
    "pythonTaskEventThreeRoleAndForeignScopeAuthorization",
    "pythonTaskEventIdleRevocationActualControlFrameAndMeasuredDelay",
    "pythonTaskEventPerActorQuotaAndDisconnectRelease",
    "pythonTaskEventActualReconnectDoesNotRepeatLastSequence",
    "pythonTaskEventUnexpiredPayloadGapFailsClosed",
]


@contextmanager
def hold_idle_streams(client, url, headers):
    """同时持有4条响应及迭代器；临时iter_lines回收会使httpcore关闭真实连接。"""
    held = []
    try:
        for _ in range(4):
            manager = client.stream("GET", url, headers=headers)
            response = manager.__enter__()
            entry = [manager, response, None]
            held.append(entry)  # 状态/首帧断言失败时也必须回收已打开响应。
            assert response.status_code == 200, {"actual": response.status_code, "expected": 200}
            lines = response.iter_lines()
            entry[2] = lines
            assert next(lines) == ": keepalive"
        yield held
    finally:
        for manager, _response, lines in reversed(held):
            try:
                if lines is not None:
                    lines.close()
            finally:
                manager.__exit__(None, None, None)


def run_task_event_stream_checks(client, admin, headers, password, cache, database, cases):
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database) or (
        admin.host != "127.0.0.1" or admin.port != 13306
    ):
        raise ValueError("事件专项仅允许13306当前UUID库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
    from task_event_fixture import prepare_event_identities

    tenant, _, team, role, identities = prepare_event_identities(
        client, admin, headers, password, cache
    )
    own = identities[990381]["headers"]
    owner = identities[990381]["owner"]

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decoded(admin.user),
        password=decoded(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )

    async def main():
        from task_core_fixture import compile_dag, insert_plan, plan

        from orbit_api.errors import OrbitError
        from orbit_api.task_contract import node_id, validate_dag
        from orbit_api.task_event_publisher import publish_fixture_running
        from orbit_api.task_event_store import TaskEventStore
        from orbit_api.task_manifest import TaskManifestStore

        engine = create_async_engine(url, echo=False)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        manifest = TaskManifestStore()

        async def call(operation):
            async with sessions() as session, session.begin():
                return await operation(session)

        async def new(target=owner):
            value = plan(target, team, copies=1)
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
            return task, records

        def detail(task, identity=own):
            response = client.get(
                "/api/v1/tasks/" + task,
                headers=identity
                | {
                    "Origin": "https://app.fixture.example",
                },
            )
            assert response.status_code == 200
            assert response.headers.get("x-task-event-checkpoint")
            exposed = {
                name.strip().lower()
                for name in response.headers.get("access-control-expose-headers", "").split(",")
            }
            assert "x-task-event-checkpoint" in exposed
            return response

        def event_headers(event=None, checkpoint=None, identity=own):
            return (
                identity
                | ({"Last-Event-ID": event} if event else {})
                | ({"X-Task-Event-Checkpoint": checkpoint} if checkpoint else {})
            )

        def rejection(task, expected, event=None, checkpoint=None, identity=own):
            # 非200响应有限立即结束，不用client.get读取成功的长流。
            with client.stream(
                "GET",
                f"/api/v1/tasks/{task}/events",
                headers=event_headers(event, checkpoint, identity),
            ) as response:
                assert response.status_code == expected, {
                    "actual": response.status_code,
                    "expected": expected,
                }
                response.read()
                return response.json()

        def age(task, event):
            # 明确故障/时间夹具；不改生产publisher时间或假称等候七天实测。
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_task_event SET occurred_at=UTC_TIMESTAMP(3)-INTERVAL 8 DAY "
                    "WHERE tenant_id=%s AND task_id=%s AND event_id=%s",
                    (tenant, task, event),
                )
                cursor.execute(
                    "UPDATE orbit_task_event_cursor SET "
                    "occurred_at=UTC_TIMESTAMP(3)-INTERVAL 8 DAY,"
                    "expires_at=UTC_TIMESTAMP(3)-INTERVAL 1 DAY "
                    "WHERE tenant_id=%s AND task_id=%s AND event_id=%s",
                    (tenant, task, event),
                )
            admin.commit()

        async def publish(task, records, index=0):
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

        try:
            task, records = await new()
            first = detail(task)
            initial = first.json()["latest_event_id"]
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_task_event_cursor WHERE tenant_id=%s "
                    "AND task_id=%s AND event_id=%s AND sequence=1",
                    (tenant, task, initial),
                )
                assert cursor.fetchone()[0] == 1
            with client.stream("GET", f"/api/v1/tasks/{task}/events", headers=own) as response:
                assert response.status_code == 200
                assert response.headers["cache-control"] == "no-store"
                lines = response.iter_lines()
                assert next(lines) == "id: " + initial
                payload = json.loads(next(lines).removeprefix("data: "))
                assert set(payload) == {
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
                assert payload["sequence"] == payload["task_revision"] == 1
                assert payload["state"] == "QUEUED" and payload["node_id"] is None
            cases.append(TASK_EVENT_STREAM_CASES[0])
            try:
                await call(
                    lambda s: publish_fixture_running(
                        s, 1, task, node_id(task, records[0]["node_key"]), str(uuid4())
                    )
                )
            except OrbitError as error:
                assert error.status == 503 and error.code == "TASK_AUTHORITY_PROVIDER_UNAVAILABLE"
            else:
                raise AssertionError("生产来源缺失未拒绝")
            cases.append(TASK_EVENT_STREAM_CASES[1])
            checkpoint = first.headers["x-task-event-checkpoint"]
            second = await publish(task, records)
            with client.stream(
                "GET", f"/api/v1/tasks/{task}/events", headers=event_headers(initial, checkpoint)
            ) as response:
                assert response.status_code == 200
                assert next(response.iter_lines()) == "id: " + second
            cases.append(TASK_EVENT_STREAM_CASES[2])
            other_task, _ = await new()
            other_event = detail(other_task).json()["latest_event_id"]
            for unknown in (str(uuid4()), other_event):
                assert rejection(task, 400, unknown)["code"] == "EVENT_CURSOR_INVALID"
            cases.append(TASK_EVENT_STREAM_CASES[3])
            aged, aged_records = await new()
            old = detail(aged).json()["latest_event_id"]
            age(aged, old)
            assert rejection(aged, 410, old)["code"] == "EVENT_CURSOR_EXPIRED"
            cases.append(TASK_EVENT_STREAM_CASES[4])
            fresh = detail(aged)
            cp = fresh.headers["x-task-event-checkpoint"]
            with client.stream(
                "GET", f"/api/v1/tasks/{aged}/events", headers=event_headers(old, cp)
            ) as response:
                assert response.status_code == 200
                assert next(response.iter_lines()) == ": keepalive"
            cases.append(TASK_EVENT_STREAM_CASES[5])
            unread = await publish(aged, aged_records)
            age(aged, unread)
            assert rejection(aged, 410, old, cp)["code"] == "EVENT_CURSOR_EXPIRED"
            cases.append(TASK_EVENT_STREAM_CASES[6])
            assert await call(lambda s: TaskEventStore(None).purge(s, 1, aged)) == 2
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_task_event WHERE tenant_id=%s AND task_id=%s",
                    (tenant, aged),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_task_event_cursor "
                    "WHERE tenant_id=%s AND task_id=%s",
                    (tenant, aged),
                )
                assert cursor.fetchone()[0] == 2
            assert rejection(aged, 410, old)["code"] == "EVENT_CURSOR_EXPIRED"
            cases.append(TASK_EVENT_STREAM_CASES[7])
            before = detail(task).json()
            with admin.cursor() as cursor:
                cursor.execute(
                    "CREATE TRIGGER task_event_fixture_fail BEFORE INSERT ON orbit_task_outbox "
                    "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-event-rollback'"
                )
            try:
                try:
                    await publish(task, records, 1)
                except DBAPIError as error:
                    assert error.orig.args[0] == 1644
                else:
                    raise AssertionError("事件outbox未回滚")
            finally:
                with admin.cursor() as cursor:
                    cursor.execute("DROP TRIGGER task_event_fixture_fail")
            assert detail(task).json() == before
            cases.append(TASK_EVENT_STREAM_CASES[8])
            assert detail(task, identities[990380]["headers"]).status_code == 200
            assert (
                rejection(task, 404, identity=identities[990382]["headers"])["code"] == "NOT_FOUND"
            )
            assert detail(task, headers).status_code == 200
            cases.append(TASK_EVENT_STREAM_CASES[9])
            current = detail(task).json()["latest_event_id"]
            with client.stream(
                "GET", f"/api/v1/tasks/{task}/events", headers=event_headers(current)
            ) as response:
                lines = response.iter_lines()
                assert response.status_code == 200 and next(lines) == ": keepalive"
                started = time.monotonic()
                with admin.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=310206", (role,)
                    )
                admin.commit()
                try:
                    observed = []
                    for line in lines:
                        if line:
                            observed.append(line)
                        if line.startswith("data:"):
                            break
                    elapsed = time.monotonic() - started
                    assert observed == ["event: SCOPE_REVOKED", 'data: {"code":"SCOPE_REVOKED"}']
                    assert elapsed < 2, {"revocation_seconds": elapsed}
                finally:
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,310206)", (role,)
                        )
                    admin.commit()
            cases.append(TASK_EVENT_STREAM_CASES[10])
            with hold_idle_streams(client, f"/api/v1/tasks/{task}/events", event_headers(current)):
                assert rejection(task, 429, current)["code"] == "TASK_STREAM_LIMIT"
            # disconnect处理有调度延迟；有界真实重连确认quota回收，不假设close即同步释放。
            release_deadline = time.monotonic() + 2
            while True:
                with client.stream(
                    "GET", f"/api/v1/tasks/{task}/events", headers=event_headers(current)
                ) as response:
                    if response.status_code == 200:
                        assert next(response.iter_lines()) == ": keepalive"
                        break
                    assert response.status_code == 429
                assert time.monotonic() < release_deadline, "断连未及时回收事件流名额"
                await asyncio.sleep(0.02)
            cases.append(TASK_EVENT_STREAM_CASES[11])
            third = await publish(task, records, 1)
            with client.stream(
                "GET", f"/api/v1/tasks/{task}/events", headers=event_headers(current)
            ) as response:
                assert response.status_code == 200
                lines = response.iter_lines()
                assert next(lines) == "id: " + third
                assert json.loads(next(lines).removeprefix("data: "))["sequence"] == 3
            cases.append(TASK_EVENT_STREAM_CASES[12])
            with admin.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM orbit_task_event WHERE tenant_id=%s "
                    "AND task_id=%s AND event_id=%s",
                    (tenant, task, third),
                )
            admin.commit()
            # 初始握手必须在200之前发现真实未过期缺口；不将无payload当无新事件。
            assert rejection(task, 503, current)["code"] == "TASK_EVENT_SEQUENCE_UNAVAILABLE"
            cases.append(TASK_EVENT_STREAM_CASES[13])
        finally:
            await engine.dispose()

    asyncio.run(main())
