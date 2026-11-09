"""TaskEvent存量防线真实负例；故障行逐项精确恢复，不改变原Schema/迁移。"""

import asyncio
import re
import time
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TASK_EVENT_INTEGRITY_CASES = [
    "pythonTaskEventValidFutureStateStringRemainsOriginalSchemaCompatible",
    "pythonTaskEventStoredSchemaVersionCorruptionRejectedBeforeHttp200",
    "pythonTaskEventStoredRevisionSequenceAndUuidCorruptionRejectedBeforeHttp200",
    "pythonTaskEventStoredEmptyStateRejectedWithoutInventingEnum",
    "pythonTaskEventCursorDirectoryIdentitySequenceAndTimeDivergenceRejected",
    "pythonTaskEventSecondRowCorruptionRejectsWholeBatchBeforeHeaders",
    "pythonTaskEventInFlightCorruptNextRowClosesWithoutInvalidDataAndReconnect503",
]
TABLES = {"orbit_task_event", "orbit_task_event_cursor"}


def read_row(admin, table, tenant, task, sequence):
    assert table in TABLES
    with admin.cursor() as cursor:
        cursor.execute(
            f"SELECT * FROM {table} WHERE tenant_id=%s AND task_id=%s AND sequence=%s",
            (tenant, task, sequence),
        )
        row = cursor.fetchone()
        assert row is not None
        return dict(zip([column[0] for column in cursor.description], row, strict=True))


@contextmanager
def inject_row(admin, table, tenant, task, sequence, changes):
    """仅一行、稳定另一唯一键定位恢复；错误状态断言抛出时也复原并核逐字段相等。"""
    original = read_row(admin, table, tenant, task, sequence)
    assert changes and set(changes) <= set(original)
    assert not set(changes) & {"tenant_id", "task_id"}
    assert not {"event_id", "sequence"} <= set(changes)
    stable = "event_id" if "event_id" not in changes else "sequence"

    def update(values, *, restoring=False):
        with admin.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET "
                + ",".join(f"{key}=%s" for key in values)
                + f" WHERE tenant_id=%s AND task_id=%s AND {stable}=%s",
                (*values.values(), tenant, task, original[stable]),
            )
            assert cursor.rowcount in ({0, 1} if restoring else {1})
        admin.commit()

    try:
        update(changes)
        yield
    finally:
        update(original, restoring=True)
        assert read_row(admin, table, tenant, task, sequence) == original


def run_task_event_integrity_checks(client, admin, headers, database, cases):
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database) or (
        admin.host != "127.0.0.1" or admin.port != 13306
    ):
        raise ValueError("事件存量完整性专项仅允许13306当前UUID库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()

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

    async def main():
        from task_core_fixture import compile_dag, insert_plan, plan

        from orbit_api.task_contract import node_id, validate_dag
        from orbit_api.task_event_publisher import publish_fixture_running
        from orbit_api.task_manifest import TaskManifestStore

        engine = create_async_engine(url, echo=False)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        manifest = TaskManifestStore()

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
            return task, records

        def rejects_before_start(task, last_event=None, code="TASK_EVENT_STATE_UNAVAILABLE"):
            request_headers = headers | ({"Last-Event-ID": last_event} if last_event else {})
            with client.stream(
                "GET", f"/api/v1/tasks/{task}/events", headers=request_headers
            ) as response:
                assert response.status_code == 503, {
                    "actual": response.status_code,
                    "expected": 503,
                }
                response.read()
                assert response.json()["code"] == code

        async def publish(task, records):
            return await call(
                lambda s: publish_fixture_running(
                    s,
                    1,
                    task,
                    node_id(task, records[0]["node_key"]),
                    str(uuid4()),
                    producer="ISOLATED_TEST",
                )
            )

        try:
            task, _ = await new()
            with inject_row(
                admin, "orbit_task_event", tenant, task, 1, {"state": "FUTURE_STATE_V2"}
            ):
                with client.stream(
                    "GET", f"/api/v1/tasks/{task}/events", headers=headers
                ) as response:
                    assert response.status_code == 200
                    lines = response.iter_lines()
                    assert next(lines).startswith("id: ")
                    import json

                    assert (
                        json.loads(next(lines).removeprefix("data: "))["state"] == "FUTURE_STATE_V2"
                    )
            cases.append(TASK_EVENT_INTEGRITY_CASES[0])

            with inject_row(admin, "orbit_task_event", tenant, task, 1, {"schema_version": 2}):
                rejects_before_start(task)
            cases.append(TASK_EVENT_INTEGRITY_CASES[1])
            for changes in (
                {"task_revision": 0},
                {"task_revision": 2},
                {"task_revision": 9007199254740992},
                {"sequence": 0},
                {"sequence": 2},
                {"sequence": 9007199254740992},
                {"event_id": "invalid-fixture"},
                {"request_id": "invalid-fixture"},
            ):
                with inject_row(admin, "orbit_task_event", tenant, task, 1, changes):
                    rejects_before_start(
                        task,
                        code=(
                            "TASK_EVENT_SEQUENCE_UNAVAILABLE"
                            if "sequence" in changes
                            else "TASK_EVENT_STATE_UNAVAILABLE"
                        ),
                    )
            cases.append(TASK_EVENT_INTEGRITY_CASES[2])
            with inject_row(admin, "orbit_task_event", tenant, task, 1, {"state": ""}):
                rejects_before_start(task)
            cases.append(TASK_EVENT_INTEGRITY_CASES[3])
            directory = read_row(admin, "orbit_task_event_cursor", tenant, task, 1)
            for changes in (
                {"sequence": 2},
                {"event_id": str(uuid4())},
                {"occurred_at": directory["occurred_at"] + timedelta(milliseconds=1)},
                {"expires_at": directory["expires_at"] + timedelta(days=1)},
            ):
                with inject_row(admin, "orbit_task_event_cursor", tenant, task, 1, changes):
                    rejects_before_start(task)
            cases.append(TASK_EVENT_INTEGRITY_CASES[4])

            batch_task, batch_records = await new()
            await publish(batch_task, batch_records)
            with inject_row(
                admin, "orbit_task_event", tenant, batch_task, 2, {"schema_version": 2}
            ):
                rejects_before_start(batch_task)
            cases.append(TASK_EVENT_INTEGRITY_CASES[5])
            live_task, live_records = await new()
            original = read_row(admin, "orbit_task_event", tenant, live_task, 1)
            second = None
            clean_second = None
            try:
                with client.stream(
                    "GET",
                    f"/api/v1/tasks/{live_task}/events",
                    headers=headers
                    | {
                        "Last-Event-ID": original["event_id"],
                    },
                ) as response:
                    assert response.status_code == 200
                    lines = response.iter_lines()
                    assert next(lines) == ": keepalive"

                    async def publish_corrupt(session):
                        event = await publish_fixture_running(
                            session,
                            1,
                            live_task,
                            node_id(live_task, live_records[0]["node_key"]),
                            str(uuid4()),
                            producer="ISOLATED_TEST",
                        )
                        clean = dict(
                            (
                                await session.execute(
                                    text(
                                        "SELECT * FROM orbit_task_event WHERE tenant_id=:tenant "
                                        "AND task_id=:task AND event_id=:event"
                                    ),
                                    {"tenant": tenant, "task": live_task, "event": event},
                                )
                            )
                            .mappings()
                            .one()
                        )
                        # 同事务故障注入，避免合法event2先提交被observer抢读而制造不稳定断言。
                        await session.execute(
                            text(
                                "UPDATE orbit_task_event SET schema_version=2 "
                                "WHERE tenant_id=:tenant AND task_id=:task AND event_id=:event"
                            ),
                            {"tenant": tenant, "task": live_task, "event": event},
                        )
                        return event, clean

                    second, clean_second = await call(publish_corrupt)
                    deadline = time.monotonic() + 2
                    for line in lines:
                        assert not line or line == ": keepalive", "损坏事件不得进入任何业务或控制帧"
                        assert time.monotonic() < deadline, "损坏事件提交后observer未有界关闭"
                rejects_before_start(live_task, original["event_id"])
            finally:
                if second is not None:
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "UPDATE orbit_task_event SET schema_version=1 WHERE tenant_id=%s "
                            "AND task_id=%s AND event_id=%s",
                            (tenant, live_task, second),
                        )
                    admin.commit()
                    restored = read_row(admin, "orbit_task_event", tenant, live_task, 2)
                    assert restored == clean_second
            cases.append(TASK_EVENT_INTEGRITY_CASES[6])
        finally:
            await engine.dispose()

    asyncio.run(main())
