"""真实配置源/CAS头读取专项；状态写入仅隔离夹具，不冒充预检/execute接口。"""

import asyncio
import re

from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

LAUNCH_PLAN_SOURCE_CASES = [
    "pythonLaunchPlanSourceActualStateHeadsRetainImmutableConfiguration",
    "pythonLaunchPlanSourceActualConfigurationSaveCreatesNewAnchor",
    "pythonLaunchPlanSourceCorruptLatestBodyFailsClosedAndRestores",
    "pythonLaunchPlanSourceFutureVersionNeverFallsBackToOlderMatch",
    "pythonLaunchPlanSourceMissingHistoryNeverInventsAnchor",
    "pythonLaunchPlanSourceActualPrimaryBackwardPlanAndVersionShareLock",
]


def run_launch_plan_source_checks(admin, database, cases):
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database) or (
        admin.host != "127.0.0.1" or admin.port != 13306
    ):
        raise ValueError("配置源专项仅允许当前13306/UUID隔离库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database

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
        from task_core_fixture import insert_plan, plan

        from orbit_api import launch_access
        from orbit_api.directory_tokens import canonical
        from orbit_api.errors import OrbitError
        from orbit_api.launch_plan_source import capture_plan_source
        from orbit_api.launch_store import LaunchStore

        engine = create_async_engine(url, echo=False)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def call(operation):
            async with sessions() as session, session.begin():
                return await operation(session)

        async def read(session):
            context = await launch_access.context(session, 1, "launch.edit")
            await launch_access.clock(session, context)
            head = await LaunchStore(None).row(session, context, identifier)
            return await capture_plan_source(session, context, head)

        async def rejected():
            try:
                await call(read)
            except OrbitError as error:
                assert (error.status, error.code) == (503, "LAUNCH_SOURCE_STATE_UNAVAILABLE")
            else:
                raise AssertionError("损坏配置源未拒绝")

        try:
            async with sessions() as session, session.begin():
                context = await launch_access.context(session, 1, "launch.edit")
                original = plan(context.subject_id, context.team_id, copies=1)
                identifier = await insert_plan(session, context.tenant_id, original)
                tenant = context.tenant_id
            params = {"tenant": tenant, "plan": identifier}
            first = await call(read)
            assert (first.source_revision, first.head_revision) == (1, 1)
            for state, revision in (("VALIDATED", 2), ("SUBMITTED", 3)):
                async with sessions() as session, session.begin():
                    await session.execute(
                        text(
                            "UPDATE orbit_launch_plan SET state=:state,revision=:revision "
                            "WHERE tenant_id=:tenant AND id=:plan"
                        ),
                        params | {"state": state, "revision": revision},
                    )
                current = await call(read)
                assert (current.source_revision, current.head_revision) == (1, revision)
                assert current.canonical_payload == first.canonical_payload
            cases.append(LAUNCH_PLAN_SOURCE_CASES[0])

            changed = original | {"name": "新配置仍以真实版本保存"}
            changed_hash = launch_access.digest(changed)
            async with sessions() as session, session.begin():
                await session.execute(
                    text(
                        "UPDATE orbit_launch_plan SET state='DRAFT',revision=4,name=:name,"
                        "payload_json=:payload,payload_hash=:hash,payload_bytes=:bytes "
                        "WHERE tenant_id=:tenant AND id=:plan"
                    ),
                    params
                    | {
                        "name": changed["name"],
                        "payload": canonical(changed),
                        "hash": changed_hash,
                        "bytes": len(canonical(changed).encode()),
                    },
                )
                await session.execute(
                    text(
                        "INSERT INTO orbit_launch_plan_version"
                        "(tenant_id,plan_id,revision,payload_json,"
                        "payload_hash,dependency_json,created_at,created_by) "
                        "VALUES(:tenant,:plan,4,:payload,:hash,'{}',UTC_TIMESTAMP(3),1)"
                    ),
                    params | {"payload": canonical(changed), "hash": changed_hash},
                )
            current = await call(read)
            assert (current.source_revision, current.head_revision) == (4, 4)
            assert current.payload_hash != first.payload_hash
            assert first.payload()["name"] == original["name"]
            cases.append(LAUNCH_PLAN_SOURCE_CASES[1])

            async with sessions() as session, session.begin():
                await session.execute(
                    text(
                        "UPDATE orbit_launch_plan_version SET payload_json=:payload WHERE "
                        "tenant_id=:tenant AND plan_id=:plan AND revision=4"
                    ),
                    params | {"payload": canonical(changed | {"name": "损坏夹具"})},
                )
            try:
                await rejected()
            finally:
                async with sessions() as session, session.begin():
                    await session.execute(
                        text(
                            "UPDATE orbit_launch_plan_version SET payload_json=:payload WHERE "
                            "tenant_id=:tenant AND plan_id=:plan AND revision=4"
                        ),
                        params | {"payload": canonical(changed)},
                    )
                assert (await call(read)).canonical_payload == current.canonical_payload
            cases.append(LAUNCH_PLAN_SOURCE_CASES[2])

            async with sessions() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO orbit_launch_plan_version"
                        "(tenant_id,plan_id,revision,payload_json,"
                        "payload_hash,dependency_json,created_at,created_by) "
                        "VALUES(:tenant,:plan,5,:payload,:hash,'{}',UTC_TIMESTAMP(3),1)"
                    ),
                    params | {"payload": canonical(changed), "hash": changed_hash},
                )
            try:
                await rejected()
            finally:
                async with sessions() as session, session.begin():
                    await session.execute(
                        text(
                            "DELETE FROM orbit_launch_plan_version WHERE "
                            "tenant_id=:tenant AND plan_id=:plan AND revision=5"
                        ),
                        params,
                    )
            cases.append(LAUNCH_PLAN_SOURCE_CASES[3])

            async with sessions() as session, session.begin():
                savepoint = await session.begin_nested()
                await session.execute(
                    text(
                        "DELETE FROM orbit_launch_plan_version WHERE "
                        "tenant_id=:tenant AND plan_id=:plan"
                    ),
                    params,
                )
                try:
                    await read(session)
                except OrbitError as error:
                    assert error.code == "LAUNCH_SOURCE_STATE_UNAVAILABLE"
                else:
                    raise AssertionError("无历史时虚构配置源")
                finally:
                    await savepoint.rollback()
            assert (await call(read)).source_revision == 4
            cases.append(LAUNCH_PLAN_SOURCE_CASES[4])

            async with sessions() as holder, holder.begin():
                await read(holder)
                # 只关闭本测试连接的EXPLAIN重写SQL说明，避免驱动把夹具参数打印到日志。
                # 错误、锁等待和执行计划断言均保留；finally恢复连接原值。
                notes = (await holder.execute(text("SELECT @@SESSION.sql_notes"))).scalar_one()
                assert notes in {0, 1}
                await holder.execute(text("SET SESSION sql_notes=0"))
                try:
                    explained = (
                        (
                            await holder.execute(
                                text(
                                    "EXPLAIN SELECT revision,payload_hash,"
                                    "OCTET_LENGTH(payload_json) AS storage_bytes "
                                    "FROM orbit_launch_plan_version "
                                    "WHERE tenant_id=:tenant AND plan_id=:plan "
                                    "ORDER BY revision DESC LIMIT 1 FOR SHARE"
                                ),
                                params,
                            )
                        )
                        .mappings()
                        .all()
                    )
                finally:
                    await holder.execute(
                        text("SET SESSION sql_notes=1" if notes else "SET SESSION sql_notes=0")
                    )
                assert len(explained) == 1 and explained[0]["key"] == "PRIMARY"
                assert explained[0]["type"] != "ALL"
                async with sessions() as contender, contender.begin():
                    await contender.execute(text("SET SESSION innodb_lock_wait_timeout=1"))
                    try:
                        await contender.execute(
                            text(
                                "UPDATE orbit_launch_plan_version SET "
                                "payload_hash=:hash WHERE tenant_id=:tenant AND plan_id=:plan "
                                "AND revision=4"
                            ),
                            params | {"hash": "0" * 64},
                        )
                    except DBAPIError as error:
                        assert error.orig.args[0] == 1205
                    else:
                        raise AssertionError("真实来源共享锁未阻止配置改写")
            assert (await call(read)).payload_hash == changed_hash
            cases.append(LAUNCH_PLAN_SOURCE_CASES[5])
            return {
                "case_count": len(LAUNCH_PLAN_SOURCE_CASES),
                "primary_index": True,
                "actual_lock_wait_code": 1205,
                "scope": "仅配置源读取及SQL夹具状态接力；非validate/execute业务受理",
            }
        finally:
            await engine.dispose()

    return asyncio.run(main())
