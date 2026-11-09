"""实际引擎+MySQL感染控制流；无害标准串只在内存，不证明HTTP或磁盘感染验收。"""

import asyncio
import base64
import hashlib
import re
from contextlib import nullcontext
from io import BytesIO
from uuid import uuid4

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_ANTIVIRUS_MEMORY_WORKER_CASES = [
    "pythonMaterialActualEngineMemoryWorkerInfectedQuarantinesWithoutCallingProcessor",
    "pythonMaterialActualEngineMemoryWorkerReceiptCannotBeReplayedOrBecomeReferenceable",
]


def run_material_antivirus_memory_worker_checks(admin, database, scanner, cases):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host not in {"127.0.0.1", "localhost"}
        or admin.port != 13306
    ):
        raise ValueError("内存感染控制流仅允许主线本机UUID数据库")
    from orbit_api.authorization import require_business_access
    from orbit_api.errors import OrbitError
    from orbit_api.material_job_policy import actor_auth_version, material_job_scope
    from orbit_api.material_references import require_allocation_assets
    from orbit_api.material_worker import MaterialWorker

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    identifier, upload = str(uuid4()), str(uuid4())
    content = base64.b64decode(
        "WDVPIVAlQEFQWzRcUFpYNTQoUF4pN0NDKTd9JEVJQ0FSLVNUQU5EQVJELUFOVElWSVJVUy1URVNULUZJTEUhJEgrSCo="
    )
    digest = hashlib.sha256(content).hexdigest()
    processor_calls = []

    class MemorySource:
        def open(self, mode):
            assert mode == "rb"
            return BytesIO(content)

    class MemoryObjects:
        # 唯一服务内部虚拟对象；不接受文件路径或对任意对象返回测试字节。
        def original(self, current_tenant, current_upload):
            assert (current_tenant, current_upload) == (tenant, upload)
            return MemorySource()

        def mutation_guard(self, current_tenant, current_upload):
            assert (current_tenant, current_upload) == (tenant, upload)
            return nullcontext()

    def processor(*args):
        processor_calls.append(True)
        raise AssertionError("受感染对象不得进入媒体处理器")

    class ObservedWorker(MaterialWorker):
        async def claim(self):
            value = await super().claim()
            self.observed_claim = value
            return value

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    def receipts():
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT claim_id,id,result,sha256,byte_size,engine_version,database_version,"
                "database_built_at,policy_sha256,started_at,completed_at,error_code,created_at "
                "FROM orbit_material_scan_receipt WHERE tenant_id=%s AND asset_id=%s ORDER BY id",
                (tenant, identifier),
            )
            rows = cursor.fetchall()
        admin.commit()
        return rows

    def runtime_proofs():
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM orbit_material_scan_runtime_proof "
                "WHERE tenant_id=%s AND asset_id=%s ORDER BY receipt_id",
                (tenant, identifier),
            )
            rows = cursor.fetchall()
        admin.commit()
        return rows

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
        objects = MemoryObjects()
        worker = ObservedWorker(
            sessions,
            objects,
            processor=processor,
            scanner=scanner,
            runtime_profile_provider=lambda claim: scanner.profile,
        )
        try:
            async with sessions() as session, session.begin():
                context = await require_business_access(session, 1, "assets", "assets.upload")
                version = await actor_auth_version(session, 1)
                asset = {
                    "id": identifier,
                    "owner_user_id": owner,
                    "owner_team_id": team,
                    "sha256": digest,
                    "mime": "image/png",
                }
                await session.execute(
                    text("""INSERT INTO orbit_material_asset
                    (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
                     sha256,byte_size,object_upload_id)
                    VALUES(:tenant,:id,:owner,:team,'内存感染控制流隔离夹具',:category,
                    'IMAGE','image/png','SCANNING',:sha,:size,:upload)"""),
                    {
                        "tenant": tenant,
                        "id": identifier,
                        "owner": owner,
                        "team": team,
                        "category": "00000000-0000-4000-8000-000000000001",
                        "sha": digest,
                        "size": len(content),
                        "upload": upload,
                    },
                )
                await session.execute(
                    text("""INSERT INTO orbit_material_job
                    (tenant_id,asset_id,actor_id,actor_auth_version,scope_digest,state,created_at)
                    VALUES(:tenant,:id,1,:version,:scope,'PENDING','2000-01-01')"""),
                    {
                        "tenant": tenant,
                        "id": identifier,
                        "version": version,
                        "scope": material_job_scope(context, asset),
                    },
                )
            assert await worker.run_once(1) == [{"asset_id": identifier, "state": "QUARANTINED"}]
            assert processor_calls == []
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT state,error_code,preview_ready FROM orbit_material_asset "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, identifier),
                )
                assert cursor.fetchone() == ("QUARANTINED", "ANTIVIRUS_INFECTED", 0)
                cursor.execute(
                    "SELECT state FROM orbit_material_job WHERE tenant_id=%s AND asset_id=%s",
                    (tenant, identifier),
                )
                assert cursor.fetchone()[0] == "FAILED"
            admin.commit()
            before = receipts()
            assert len(before) == 1 and before[0][2:5] == ("INFECTED", digest, len(content))
            before_runtime = runtime_proofs()
            assert len(before_runtime) == 1
            cases.append(MATERIAL_ANTIVIRUS_MEMORY_WORKER_CASES[0])
            proof = await asyncio.to_thread(
                scanner.scan, objects, tenant, upload, digest, len(content)
            )
            assert proof.receipt.result == "INFECTED"
            assert await worker.record_scan(
                worker.observed_claim, proof, profile=scanner.profile
            ) == (None, "STALE")
            assert receipts() == before
            assert runtime_proofs() == before_runtime
            async with sessions() as session, session.begin():
                context = await require_business_access(session, 1, "assets", "assets.read")
                try:
                    await require_allocation_assets(session, context, owner, team, [identifier])
                except OrbitError as error:
                    assert error.status == 409 and error.code == "MATERIAL_NOT_READY"
                else:
                    raise AssertionError("受感染内存对象不得成为可分配素材")
            assert processor_calls == []
            cases.append(MATERIAL_ANTIVIRUS_MEMORY_WORKER_CASES[1])
        finally:
            await engine.dispose()

    asyncio.run(run())
