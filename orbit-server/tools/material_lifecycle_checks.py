"""019待排队的真实MySQL/独占文件生命周期专项；不证明旧HTTP写方已接入fence。"""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_LIFECYCLE_CASES = [
    "pythonMaterialLifecycleExactUploadExpiryPreservesIncompleteBeforeBoundary",
    "pythonMaterialLifecycleNeverExpiresCompletedReadyUpload",
    "pythonMaterialLifecycleUnintegratedWritersNeverEnablePhysicalDelete",
    "pythonMaterialLifecycleExpiredObjectActuallyPurgesWithDurableTombstone",
    "pythonMaterialLifecycleArchiveThirtyDayBoundaryAndHistoricalEvidenceBlock",
    "pythonMaterialLifecycleActualArchivePurgePreservesMetadataAuditAndFencesOldClaims",
]


def run_material_lifecycle_checks(admin, database, object_root, cases):
    if not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database):
        raise ValueError("生命周期专项只能使用主线当前UUID测试库")
    if admin.host not in {"localhost", "127.0.0.1"} or admin.port != 13306:
        raise ValueError("生命周期专项只能使用本机隔离MySQL")
    from orbit_api.material_lifecycle import MaterialLifecycleWorker
    from orbit_api.material_lifecycle_objects import LifecycleObjectFence
    from orbit_api.material_objects import LocalMaterialObjects

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    now = datetime.now(UTC).replace(tzinfo=None)
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)
    objects = LocalMaterialObjects(Path(object_root))

    def fixture(state, expires, archived=None):
        asset, upload = str(uuid4()), str(uuid4())
        with admin.cursor() as cursor:
            cursor.execute(
                """INSERT INTO orbit_material_asset
                (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
                 sha256,byte_size,object_upload_id,archived_at)
                VALUES(%s,%s,%s,%s,'生命周期独占元数据夹具',%s,'IMAGE','image/png',%s,%s,4,%s,%s)""",
                (
                    tenant,
                    asset,
                    owner,
                    team,
                    "00000000-0000-4000-8000-000000000001",
                    state,
                    "a" * 64,
                    upload,
                    archived,
                ),
            )
            cursor.execute(
                """INSERT INTO orbit_material_upload
                (tenant_id,id,asset_id,owner_user_id,expires_at,state)
                VALUES(%s,%s,%s,%s,%s,%s)""",
                (
                    tenant,
                    upload,
                    asset,
                    owner,
                    expires,
                    "COMPLETE" if state in {"READY", "ARCHIVED"} else "UPLOADING",
                ),
            )
        admin.commit()
        objects.put_part(tenant, upload, 1, b"data", 4)
        return asset, upload

    expired = fixture("UPLOADING", now)
    early = fixture("UPLOADING", now + timedelta(milliseconds=1))
    ready = fixture("READY", now - timedelta(days=1))
    old = fixture("ARCHIVED", now - timedelta(days=31), now - timedelta(days=30))
    young = fixture(
        "ARCHIVED", now - timedelta(days=31), now - timedelta(days=30) + timedelta(milliseconds=1)
    )
    historical = fixture("ARCHIVED", now - timedelta(days=40), now - timedelta(days=31))
    with admin.cursor() as cursor:
        cursor.execute(
            """INSERT INTO orbit_material_reference
            (tenant_id,asset_id,id,kind,resource_id,active)
            VALUES(%s,%s,%s,'HISTORICAL_EVIDENCE',%s,0)""",
            (tenant, historical[0], str(uuid4()), str(uuid4())),
        )
    admin.commit()

    def state(asset):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,physical_cleanup_state,physical_deleted_at FROM orbit_material_asset "
                "WHERE tenant_id=%s AND id=%s",
                (tenant, asset),
            )
            return cursor.fetchone()

    def due_now():
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_material_lifecycle_job SET due_at=%s "
                "WHERE tenant_id=%s AND asset_id IN (%s,%s)",
                (now, tenant, expired[0], old[0]),
            )
        admin.commit()

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
        try:
            disabled = MaterialLifecycleWorker(
                sessions, LifecycleObjectFence(Path(object_root)), clock=lambda: now
            )
            assert await disabled.enqueue() == 2
            assert state(expired[0])[0] == "UPLOAD_FAILED"
            assert state(early[0])[0] == "UPLOADING"
            cases.append(MATERIAL_LIFECYCLE_CASES[0])
            assert state(ready[0])[0] == "READY"
            assert objects.part_path(tenant, ready[1], 1).read_bytes() == b"data"
            cases.append(MATERIAL_LIFECYCLE_CASES[1])
            await disabled.run_once(10)
            assert state(expired[0])[1] == "LIVE"
            assert objects.part_path(tenant, expired[1], 1).is_file()
            cases.append(MATERIAL_LIFECYCLE_CASES[2])
            due_now()
            # 仅这批独占fixture对象由本工具写入；不声称现HTTP对象写方已接入协议。
            fence = LifecycleObjectFence(Path(object_root), writers_fenced=True)
            claims = []

            class CapturingWorker(MaterialLifecycleWorker):
                async def claim(self):
                    actual = await super().claim()
                    if actual and not actual.get("skipped"):
                        claims.append(actual)
                    return actual

            enabled = CapturingWorker(sessions, fence, clock=lambda: now)
            results = await enabled.run_once(10)
            assert len(results) == 2 and all(item["state"] == "DONE" for item in results)
            assert state(expired[0])[0:2] == ("UPLOAD_FAILED", "PURGED")
            assert not (Path(object_root) / tenant / expired[1]).exists()
            assert (
                Path(object_root) / ".lifecycle" / tenant / (expired[1] + ".tombstone")
            ).is_file()
            cases.append(MATERIAL_LIFECYCLE_CASES[3])
            assert state(young[0])[1] == state(historical[0])[1] == "LIVE"
            assert objects.part_path(tenant, historical[1], 1).is_file()
            cases.append(MATERIAL_LIFECYCLE_CASES[4])
            assert state(old[0])[0:2] == ("ARCHIVED", "PURGED") and state(old[0])[2] == now
            assert not (Path(object_root) / tenant / old[1]).exists()
            completed_claim = next(claim for claim in claims if claim["asset_id"] == old[0])
            assert await enabled.finish(completed_claim) == "STALE"
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_material_audit "
                    "WHERE tenant_id=%s AND resource_id=%s "
                    "AND action='MATERIAL_OBJECT_PURGED'",
                    (tenant, old[0]),
                )
                assert cursor.fetchone()[0] == 1
            cases.append(MATERIAL_LIFECYCLE_CASES[5])
        finally:
            await engine.dispose()

    asyncio.run(run())
