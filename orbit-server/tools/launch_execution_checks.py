"""原execute隔离SQL/HTTP验收工具；不发送平台请求、不证明生产authority。"""

import asyncio
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

if __package__:
    from .launch_execution_fixture import create_protocol_plan
else:
    from launch_execution_fixture import create_protocol_plan

EXECUTION_CASES = [
    "pythonExecutionOriginal202TaskCompleteManifestAndCommands",
    "pythonExecutionOriginalTaskReadAndFirstNodesConsistent",
    "pythonExecutionAcceptedExactOldKeyReplayBeforeCAS",
    "pythonExecutionSameKeyDifferentBodyRejected",
    "pythonExecutionDifferentKeySameConfigurationReusesActualTask",
    "pythonExecutionStrictOriginalFieldsHeadersAndCsrfNoTask",
    "pythonExecutionCurrentActionDeniedWithoutBorrowingEdit",
    "pythonExecutionFinalOutbox1644WholeAcceptanceRollback",
    "pythonExecutionActualAllocationItemsRevalidatedAtFinal",
    "pythonExecutionActualNameItemsRevalidatedAtFinal",
    "pythonExecutionUnsealedPreparationCannotBeAccepted",
    "pythonExecutionSameKeyLiveBuilderBusyDoesNotAbortOriginal",
    "pythonExecutionExpiredPreparationDbClockBoundedCleanup",
    "pythonExecutionCleanupNeverDeletesAcceptedHistory",
    "pythonExecutionActualSqlFinalTtlBeforeEqualAfter",
    "pythonExecutionActualSqlShanghaiMidnightBeforeEqual",
]


def epoch_seconds(value):
    """精确会话时钟，不以float丢毫秒，也不更改系统/应用全局时间。"""
    delta = value.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000


def clocked_sessions(sessions, value):
    @asynccontextmanager
    async def factory():
        from sqlalchemy import text

        async with sessions() as session:
            # SET会开始SQLAlchemy autobegin；先提交只包含SET的短事务，让Store自有begin可用。
            await session.execute(
                text("SET SESSION timestamp=:value"), {"value": epoch_seconds(value)}
            )
            await session.commit()
            try:
                yield session
            finally:
                if session.in_transaction():
                    await session.rollback()
                await session.execute(text("SET SESSION timestamp=0"))
                await session.commit()

    return factory


def run_launch_execution_checks(
    client, admin, headers, password, cache, database, cases, *, control_dir, cipher=None
):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or cipher is None
    ):
        raise ValueError("执行协议必须本轮13306/UUID库及内存Cipher")
    from orbit_api.directory_tokens import canonical

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()

    def checked(response, expected):
        assert response.status_code == expected, {
            "actual": response.status_code,
            "expected": expected,
            "code": response.json().get("code"),
        }
        return response.json()

    def write(revision, key=None):
        cap = checked(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)
        return headers | {
            "X-CSRF-Token": cap["csrf_token"],
            "If-Match": f'"{revision}"',
            "Idempotency-Key": key or str(uuid4()),
        }

    def new(mode="SUCCESS"):
        item = create_protocol_plan(admin, tenant, owner, team, mode=mode)
        result = checked(
            client.post(
                f"/api/v1/launch-plans/{item['id']}/validate", headers=write(1), json=item["body"]
            ),
            200,
        )
        assert result["valid"] is True and result["hash"] is not None
        item.update(
            validation=result,
            execute={"hash": result["hash"], "activate_ack": False},
            head=write(2),
        )
        return item

    def execute(item, *, head=None, body=None):
        return client.post(
            f"/api/v1/launch-plans/{item['id']}/execute",
            headers=head or item["head"],
            json=body or item["execute"],
        )

    def one(sql, params=()):
        with admin.cursor() as cursor:
            cursor.execute(sql, params)
            result = cursor.fetchone()
        # 每次只读观察立即结束RR快照；不能把上一次HTTP前的快照当最新受理状态。
        admin.commit()
        return result

    def scalar(sql, params=()):
        return one(sql, params)[0]

    def accepted_count(item):
        return scalar(
            "SELECT COUNT(*) FROM orbit_launch_execution_acceptance WHERE "
            "tenant_id=%s AND plan_id=%s",
            (tenant, item["id"]),
        )

    first = new()
    task = checked(execute(first), 202)
    assert task["state"] == "QUEUED" and task["revision"] == 1
    assert task["node_count"] > 0 and len(task["nodes"]) == min(200, task["node_count"])
    assert task["ownership"] == first["value"]["ownership"]
    assert (
        scalar(
            "SELECT COUNT(*) FROM orbit_launch_execution_command WHERE tenant_id=%s AND task_id=%s",
            (tenant, task["id"]),
        )
        == task["node_count"]
    )
    assert (
        scalar(
            "SELECT COUNT(*) FROM orbit_task_node WHERE tenant_id=%s AND task_id=%s",
            (tenant, task["id"]),
        )
        == task["node_count"]
    )
    assert (
        scalar(
            "SELECT COUNT(*) FROM orbit_task_audit WHERE tenant_id=%s AND task_id=%s",
            (tenant, task["id"]),
        )
        == 1
    )
    assert (
        scalar(
            "SELECT COUNT(*) FROM orbit_task_outbox WHERE tenant_id=%s AND task_id=%s",
            (tenant, task["id"]),
        )
        == 1
    )
    assert scalar(
        "SELECT COUNT(*) FROM orbit_material_reference WHERE tenant_id=%s "
        "AND resource_id=%s AND kind='EXECUTION' AND active=1",
        (tenant, task["id"]),
    ) == len(first["value"]["asset_ids"])
    assert one(
        "SELECT state,revision FROM orbit_launch_plan WHERE tenant_id=%s AND id=%s",
        (tenant, first["id"]),
    ) == ("SUBMITTED", 3)
    cases.append(EXECUTION_CASES[0])

    detail = checked(client.get(f"/api/v1/tasks/{task['id']}", headers=headers), 200)
    for field in ("id", "state", "revision", "node_count", "ownership", "nodes"):
        assert detail[field] == task[field]
    cases.append(EXECUTION_CASES[1])
    assert checked(execute(first), 202) == task
    assert accepted_count(first) == 1
    cases.append(EXECUTION_CASES[2])
    mismatch = checked(execute(first, body=first["execute"] | {"activate_ack": True}), 409)
    assert mismatch["code"] == "IDEMPOTENCY_CONFLICT"
    cases.append(EXECUTION_CASES[3])
    repeated = checked(execute(first, head=write(2)), 202)
    assert repeated["id"] == task["id"] and accepted_count(first) == 1
    before_conflict = (
        scalar("SELECT COUNT(*) FROM orbit_launch_idempotency"),
        scalar("SELECT COUNT(*) FROM orbit_task_audit"),
        scalar("SELECT COUNT(*) FROM orbit_task"),
    )
    for revision, body in ((2, first["execute"] | {"activate_ack": True}), (3, first["execute"])):
        rejected = checked(execute(first, head=write(revision), body=body), 409)
        assert rejected["code"] == "IDEMPOTENCY_CONFLICT"
    assert before_conflict == (
        scalar("SELECT COUNT(*) FROM orbit_launch_idempotency"),
        scalar("SELECT COUNT(*) FROM orbit_task_audit"),
        scalar("SELECT COUNT(*) FROM orbit_task"),
    )
    cases.append(EXECUTION_CASES[4])

    strict = new("STRICT")
    checked(execute(strict, body=strict["execute"] | {"verified": True}), 400)
    checked(
        execute(
            strict, head={key: value for key, value in strict["head"].items() if key != "If-Match"}
        ),
        400,
    )
    checked(execute(strict, head=strict["head"] | {"X-CSRF-Token": "invalid"}), 403)
    assert accepted_count(strict) == 0
    assert scalar("SELECT COUNT(*) FROM orbit_task WHERE source_plan_id=%s", (strict["id"],)) == 0
    cases.append(EXECUTION_CASES[5])

    # 复用本轮真实角色API创建的预检only身份，不给它附加execute/read授权。
    if __package__:
        from .fixture_login import fixture_login
    else:
        from fixture_login import fixture_login

    username = one("SELECT user_name FROM sys_user WHERE user_id=990462")[0]
    login = checked(fixture_login(client, cache, {"username": username, "password": password}), 200)
    denied = checked(
        execute(strict, head=strict["head"] | {"Authorization": "Bearer " + login["token"]}), 403
    )
    assert denied["code"] and accepted_count(strict) == 0
    cases.append(EXECUTION_CASES[6])

    rollback = new("ROLLBACK")
    trigger = "execution_outbox_fixture_" + uuid4().hex[:12]
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "CREATE TRIGGER " + trigger + " BEFORE INSERT ON orbit_task_outbox "
                "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='ISOLATED_EXECUTION_FAILURE'"
            )
        admin.commit()
        checked(execute(rollback), 503)
        assert accepted_count(rollback) == 0
        assert one(
            "SELECT state,revision FROM orbit_launch_plan WHERE id=%s", (rollback["id"],)
        ) == ("VALIDATED", 2)
        assert (
            scalar(
                "SELECT COUNT(*) FROM orbit_task WHERE source_plan_id=%s AND "
                "manifest_phase='COMPLETE'",
                (rollback["id"],),
            )
            == 0
        )
        assert (
            scalar(
                "SELECT COUNT(*) FROM orbit_material_reference r JOIN orbit_task t "
                "ON t.tenant_id=r.tenant_id AND t.id=r.resource_id WHERE t.source_plan_id=%s",
                (rollback["id"],),
            )
            == 0
        )
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS " + trigger)
        admin.commit()
    cases.append(EXECUTION_CASES[7])

    # 以下真实SQL Store协议另起独立engine；精确时钟仅该会话，不改应用/系统时间。
    from sqlalchemy import URL, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    if __package__:
        from .launch_execution_fixture import IsolatedExecutionProvider
    else:
        from launch_execution_fixture import IsolatedExecutionProvider

    from orbit_api import launch_access
    from orbit_api.directory_tokens import DirectoryTokens
    from orbit_api.errors import OrbitError
    from orbit_api.launch_execution_store import (
        ExecutionInput,
        LaunchExecutionStore,
        SealedExecution,
        execution_build_spec,
        frozen_validation_row,
        iter_byte_packets,
    )
    from orbit_api.launch_plan_source import capture_plan_source
    from orbit_api.launch_store import LaunchStore

    def decode(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decode(admin.user),
        password=decode(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
        query={"charset": "utf8mb4"},
    )

    async def sql_checks():
        engine = create_async_engine(url, echo=False)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        provider = IsolatedExecutionProvider(sessions, control_dir)
        store = LaunchExecutionStore(DirectoryTokens(cipher), provider)
        authorization = headers["Authorization"]
        try:

            async def private(item):
                async with sessions() as session, session.begin():
                    current = await launch_access.context(session, 1, "launch.execute")
                    await launch_access.clock(session, current, write=True)
                    head = await LaunchStore(store.tokens).row(
                        session, current, item["id"], write=True
                    )
                    source = await capture_plan_source(session, current, head)
                    row = (
                        (
                            await session.execute(
                                text(
                                    "SELECT * FROM orbit_launch_validation "
                                    "WHERE tenant_id=:tenant AND plan_id=:plan "
                                    "AND validated_head_revision=2"
                                ),
                                {"tenant": tenant, "plan": item["id"]},
                            )
                        )
                        .mappings()
                        .one()
                    )
                    request = ExecutionInput(
                        current,
                        source,
                        row["id"],
                        frozen_validation_row(row),
                        canonical(item["execute"]).encode(),
                    )
                evidence = await provider.capture(request)
                async with sessions() as session, session.begin():
                    handle = await store.stage_begin(
                        session,
                        1,
                        authorization,
                        item["head"]["X-CSRF-Token"],
                        item["head"]["Idempotency-Key"],
                        str(uuid4()),
                        evidence,
                        execution_build_spec(evidence.prepared),
                    )
                return handle

            async def prepared(item):
                return await store.prepare(
                    sessions,
                    1,
                    authorization,
                    item["head"]["X-CSRF-Token"],
                    item["head"]["Idempotency-Key"],
                    item["execute"],
                    item["id"],
                    2,
                    str(uuid4()),
                )

            async def accept(item, flow):
                async with sessions() as session, session.begin():
                    return await store.accept(
                        session,
                        1,
                        authorization,
                        item["head"]["X-CSRF-Token"],
                        item["head"]["Idempotency-Key"],
                        item["execute"],
                        item["id"],
                        2,
                        str(uuid4()),
                        flow,
                    )

            for which in ("allocation", "names"):
                item = new("FINAL_" + which.upper())
                flow = await prepared(item)
                with admin.cursor() as cursor:
                    if which == "allocation":
                        cursor.execute(
                            "UPDATE orbit_launch_allocation_item SET asset_revision=2 "
                            "WHERE tenant_id=%s AND allocation_id=%s AND ordinal=0",
                            (tenant, item["body"]["allocation_id"]),
                        )
                    else:
                        cursor.execute(
                            "UPDATE orbit_launch_name_item SET name=CONCAT(name,'tamper') "
                            "WHERE tenant_id=%s AND reservation_id=%s AND ordinal=0",
                            (tenant, item["body"]["name_reservation_id"]),
                        )
                admin.commit()
                try:
                    try:
                        await accept(item, flow)
                        raise AssertionError("完整items变化不应被接受")
                    except OrbitError as failure:
                        assert failure.status == 409
                    assert accepted_count(item) == 0
                finally:
                    with admin.cursor() as cursor:
                        if which == "allocation":
                            cursor.execute(
                                "UPDATE orbit_launch_allocation_item SET asset_revision=1 "
                                "WHERE tenant_id=%s AND allocation_id=%s AND ordinal=0",
                                (tenant, item["body"]["allocation_id"]),
                            )
                        else:
                            cursor.execute(
                                "UPDATE orbit_launch_name_item SET "
                                "name=LEFT(name,CHAR_LENGTH(name)-6) "
                                "WHERE tenant_id=%s AND reservation_id=%s AND ordinal=0",
                                (tenant, item["body"]["name_reservation_id"]),
                            )
                    admin.commit()
                cases.append(EXECUTION_CASES[8 if which == "allocation" else 9])

            unfinished = new("UNSEALED")
            handle = await private(unfinished)
            try:
                await accept(
                    unfinished,
                    SealedExecution(handle, 1, handle.evidence.prepared.validation_expires_at),
                )
                raise AssertionError("未seal不应受理")
            except OrbitError as failure:
                assert failure.status == 409
            assert accepted_count(unfinished) == 0
            cases.append(EXECUTION_CASES[10])
            # 真正已存在的原builder仍持有服务器handle；第二个HTTP不得共享/ABORT它。
            second_request = asyncio.create_task(asyncio.to_thread(execute, unfinished))
            async with sessions() as session, session.begin():
                await store.append_bytes(
                    session,
                    1,
                    authorization,
                    unfinished["head"]["X-CSRF-Token"],
                    handle,
                    next(iter_byte_packets(handle.evidence.prepared)),
                )
            failure = checked(await second_request, 409)
            assert failure["code"] == "EXECUTION_PREPARATION_IN_PROGRESS"
            assert one(
                "SELECT state FROM orbit_launch_execution_preparation WHERE id=%s", (handle.id,)
            ) == ("BUILDING",)
            assert (
                scalar(
                    "SELECT persisted_byte_chunks FROM orbit_launch_execution_preparation "
                    "WHERE id=%s",
                    (handle.id,),
                )
                == 1
            )
            cases.append(EXECUTION_CASES[11])

            # 到期真实SQL时钟注入：不声称自然等待十五分钟或HTTP跨日。
            expiry = handle.evidence.prepared.validation_expires_at
            timestamp = epoch_seconds(expiry)
            for _ in range(100):
                async with sessions() as session, session.begin():
                    try:
                        await session.execute(
                            text("SET SESSION timestamp=:value"), {"value": timestamp}
                        )
                        await store.cleanup_expired(session, limit=500)
                    finally:
                        await session.execute(text("SET SESSION timestamp=0"))
                if (
                    scalar(
                        "SELECT COUNT(*) FROM orbit_launch_execution_preparation WHERE id=%s",
                        (handle.id,),
                    )
                    == 0
                ):
                    break
            assert scalar("SELECT COUNT(*) FROM orbit_task WHERE id=%s", (handle.task_id,)) == 0
            cases.append(EXECUTION_CASES[12])
            assert one("SELECT manifest_phase FROM orbit_task WHERE id=%s", (task["id"],)) == (
                "COMPLETE",
            )
            assert accepted_count(first) == 1
            cases.append(EXECUTION_CASES[13])

            # 真实Store最终事务精确TTL三边界；不声称自然十五分钟等待。
            for offset, expected_success in ((-1, True), (0, False), (1, False)):
                item = new("TTL")
                flow = await prepared(item)
                point = flow.sealed.handle.evidence.prepared.validation_expires_at + timedelta(
                    milliseconds=offset
                )
                async with sessions() as session, session.begin():
                    try:
                        await session.execute(
                            text("SET SESSION timestamp=:value"),
                            {"value": epoch_seconds(point)},
                        )
                        try:
                            result = await store.accept(
                                session,
                                1,
                                authorization,
                                item["head"]["X-CSRF-Token"],
                                item["head"]["Idempotency-Key"],
                                item["execute"],
                                item["id"],
                                2,
                                str(uuid4()),
                                flow,
                            )
                        except OrbitError as failure:
                            assert not expected_success and failure.code == "STALE_PREVIEW"
                        else:
                            assert expected_success and result["node_count"] > 0
                    finally:
                        await session.execute(text("SET SESSION timestamp=0"))
                assert accepted_count(item) == int(expected_success)
            cases.append(EXECUTION_CASES[14])

            for offset, expected_success in ((-1, True), (0, False)):
                item = new("MIDNIGHT")
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT naming_date,summary_json FROM orbit_launch_validation "
                        "WHERE tenant_id=%s AND plan_id=%s",
                        (tenant, item["id"]),
                    )
                    day, summary = cursor.fetchone()
                import json

                summary = json.loads(summary) if isinstance(summary, str) else summary
                midnight = datetime.combine(
                    day + timedelta(days=1), datetime.min.time(), tzinfo=UTC
                ) - timedelta(hours=8)
                started = midnight - timedelta(seconds=1)
                expires = started + timedelta(minutes=15)
                summary["expires_at"] = expires.isoformat(timespec="milliseconds").replace(
                    "+00:00", "Z"
                )
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE orbit_launch_validation SET validated_at=%s,expires_at=%s,"
                        "summary_json=%s WHERE tenant_id=%s AND plan_id=%s",
                        (
                            started.replace(tzinfo=None),
                            expires.replace(tzinfo=None),
                            canonical(summary),
                            tenant,
                            item["id"],
                        ),
                    )
                admin.commit()
                frozen_sessions = clocked_sessions(sessions, started)
                frozen_provider = IsolatedExecutionProvider(frozen_sessions, control_dir)
                frozen_store = LaunchExecutionStore(DirectoryTokens(cipher), frozen_provider)
                flow = await frozen_store.prepare(
                    frozen_sessions,
                    1,
                    authorization,
                    item["head"]["X-CSRF-Token"],
                    item["head"]["Idempotency-Key"],
                    item["execute"],
                    item["id"],
                    2,
                    str(uuid4()),
                )
                point = midnight + timedelta(milliseconds=offset)
                async with sessions() as session, session.begin():
                    try:
                        await session.execute(
                            text("SET SESSION timestamp=:value"),
                            {"value": epoch_seconds(point)},
                        )
                        try:
                            await frozen_store.accept(
                                session,
                                1,
                                authorization,
                                item["head"]["X-CSRF-Token"],
                                item["head"]["Idempotency-Key"],
                                item["execute"],
                                item["id"],
                                2,
                                str(uuid4()),
                                flow,
                            )
                        except OrbitError as failure:
                            assert not expected_success and failure.code == "STALE_PREVIEW"
                        else:
                            assert expected_success
                    finally:
                        await session.execute(text("SET SESSION timestamp=0"))
                assert accepted_count(item) == int(expected_success)
            cases.append(EXECUTION_CASES[15])
        finally:
            await engine.dispose()

    asyncio.run(sql_checks())
