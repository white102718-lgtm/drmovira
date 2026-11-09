"""019待排队的真实租约/提交失败恢复专项；仅本轮UUID库和独占对象。"""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_LIFECYCLE_RECOVERY_CASES = [
    "pythonMaterialLifecycleExpiredLeaseChangesFenceAndRejectsActualOldClaim",
    "pythonMaterialLifecycleRecoveredClaimActuallyPurgesAndCommitsOnce",
    "pythonMaterialLifecycleCleaningAssetRejectsNewReferenceGate",
    "pythonMaterialLifecyclePurgeThenAuditFailureRollsBackMetadata",
    "pythonMaterialLifecycleRetryAfterPurgeAndDatabaseFailureRecoversMissingFiles",
]


def run_material_lifecycle_recovery_checks(admin, database, object_root, cases):
    if not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database):
        raise ValueError("生命周期恢复专项只能使用当前隔离库")
    if admin.host not in {"127.0.0.1", "localhost"} or admin.port != 13306:
        raise ValueError("生命周期恢复专项只能使用本机隔离MySQL")
    from orbit_api.errors import OrbitError
    from orbit_api.material_lifecycle import MaterialLifecycleWorker, require_referenceable
    from orbit_api.material_lifecycle_objects import LifecycleObjectFence
    from orbit_api.material_objects import LocalMaterialObjects

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    current = [datetime.now(UTC).replace(tzinfo=None)]
    current[0] = current[0].replace(microsecond=current[0].microsecond // 1000 * 1000)
    root = Path(object_root)
    objects = LocalMaterialObjects(root)
    fence = LifecycleObjectFence(root, writers_fenced=True)

    def fixture():
        asset, upload, job = str(uuid4()), str(uuid4()), str(uuid4())
        with admin.cursor() as cursor:
            cursor.execute(
                """INSERT INTO orbit_material_asset
                (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
                 sha256,byte_size,object_upload_id,archived_at)
                VALUES(%s,%s,%s,%s,'生命周期恢复元数据夹具',%s,'IMAGE','image/png','ARCHIVED',%s,4,%s,%s)""",
                (
                    tenant,
                    asset,
                    owner,
                    team,
                    "00000000-0000-4000-8000-000000000001",
                    "b" * 64,
                    upload,
                    current[0] - timedelta(days=31),
                ),
            )
            cursor.execute(
                """INSERT INTO orbit_material_lifecycle_job
                (tenant_id,id,asset_id,upload_id,kind,due_at)
                VALUES(%s,%s,%s,%s,'ARCHIVE_RETENTION',%s)""",
                (tenant, job, asset, upload, current[0]),
            )
        admin.commit()
        objects.put_part(tenant, upload, 1, b"data", 4)
        return asset, upload, job

    def metadata(asset):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT physical_cleanup_state,physical_deleted_at FROM orbit_material_asset "
                "WHERE tenant_id=%s AND id=%s",
                (tenant, asset),
            )
            return cursor.fetchone()

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    async def run():
        engine = create_async_engine(
            URL.create(
                "mysql+asyncmy",
                username=decoded(admin.user),
                password=decoded(admin.password),
                host=admin.host,
                port=admin.port,
                database=database,
            ),
            echo=False,
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        worker = MaterialLifecycleWorker(sessions, fence, clock=lambda: current[0])
        try:
            asset, upload, job = fixture()
            first = await worker.claim()
            assert first and first["id"] == job
            current[0] += timedelta(minutes=3)
            assert await worker.recover() >= 1
            assert await worker.finish(first) == "STALE"
            cases.append(MATERIAL_LIFECYCLE_RECOVERY_CASES[0])
            second = await worker.claim()
            assert second and second["id"] == job and second["generation"] > first["generation"]
            assert second["claim_token"] != first["claim_token"]
            async with sessions() as session, session.begin():
                try:
                    await require_referenceable(session, tenant, asset)
                except OrbitError as error:
                    assert error.code == "ASSET_PHYSICALLY_UNAVAILABLE"
                else:
                    raise AssertionError("CLEANING不能新增历史或执行引用")
            # 先真实验证门禁，计入注册顺序后统一append。
            fence.purge(tenant, upload, job)
            assert await worker.finish(second) == "DONE"
            assert metadata(asset)[0] == "PURGED" and not (root / tenant / upload).exists()
            assert await worker.finish(second) == "STALE"
            cases.append(MATERIAL_LIFECYCLE_RECOVERY_CASES[1])
            cases.append(MATERIAL_LIFECYCLE_RECOVERY_CASES[2])

            asset, upload, job = fixture()
            claim = await worker.claim()
            assert claim and claim["id"] == job
            fence.purge(tenant, upload, job)
            trigger = "material_lifecycle_reject_" + uuid4().hex[:16]
            with admin.cursor() as cursor:
                cursor.execute(f"""CREATE TRIGGER `{trigger}` BEFORE INSERT ON orbit_material_audit
                    FOR EACH ROW BEGIN
                    IF NEW.resource_id='{asset}' AND NEW.action='MATERIAL_OBJECT_PURGED' THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture lifecycle audit rejection';
                    END IF; END""")
            try:
                try:
                    await worker.finish(claim)
                except DBAPIError as error:
                    assert getattr(error.orig, "args", (None,))[0] == 1644
                else:
                    raise AssertionError("真实审计触发器失败不能提交DONE")
                assert metadata(asset) == ("CLEANING", None)
                assert not (root / tenant / upload).exists()
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT state FROM orbit_material_lifecycle_job "
                        "WHERE tenant_id=%s AND id=%s",
                        (tenant, job),
                    )
                    assert cursor.fetchone()[0] == "RUNNING"
                cases.append(MATERIAL_LIFECYCLE_RECOVERY_CASES[3])
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(f"DROP TRIGGER `{trigger}`")
            current[0] += timedelta(minutes=3)
            assert await worker.recover() >= 1
            retried = await worker.claim()
            assert retried and retried["id"] == job
            assert fence.purge(tenant, upload, job) == 0
            assert await worker.finish(retried) == "DONE"
            assert metadata(asset)[0] == "PURGED"
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_material_audit "
                    "WHERE tenant_id=%s AND resource_id=%s AND action='MATERIAL_OBJECT_PURGED'",
                    (tenant, asset),
                )
                assert cursor.fetchone()[0] == 1
            cases.append(MATERIAL_LIFECYCLE_RECOVERY_CASES[4])
        finally:
            await engine.dispose()

    asyncio.run(run())
