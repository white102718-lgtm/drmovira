"""当前runtime→Worker→030→READY实际链；由主线独占对象根/数据库串行执行。"""

import asyncio
import hashlib
import re
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image
from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_RUNTIME_WORKER_CASES = [
    "pythonMaterialRuntimeWorkerActualBoundScanAndProcessingPublishesWithProof",
    "pythonMaterialRuntimeWorkerRawCleanWithoutRuntimeNeverCallsProcessorOrReady",
    "pythonMaterialRuntimeWorkerMissingCurrentProfileProviderFailsClosed",
    "pythonMaterialRuntimeWorkerProfileChangesAfterScanCannotPublish",
    "pythonMaterialRuntimeWorkerStateAuditRollbackIncludesBothProofTables",
    "pythonMaterialRuntimeWorkerRetryAndDuplicateCannotRepeatStateEvent",
    "pythonMaterialRuntimeWorkerLegacyCleanWithout030CannotFinishReady",
]


def run_material_runtime_worker_checks(admin, database, object_root, cases):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host
        not in {
            "localhost",
            "127.0.0.1",
        }
        or admin.port != 13306
    ):
        raise ValueError("runtime Worker专项只允许主线本机UUID独立库")
    from clamd_fixture_attestation import attest_fixture
    from material_runtime_fixture import material_runtime_fixture_scanner

    from orbit_api.authorization import require_business_access
    from orbit_api.material_antivirus import ClamdMaterialScanner
    from orbit_api.material_contract import CompletedPart
    from orbit_api.material_job_policy import actor_auth_version, material_job_scope
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_processing import process_material
    from orbit_api.material_security import clean_scan_ids
    from orbit_api.material_worker import MaterialWorker

    scanner, process_before = material_runtime_fixture_scanner()
    objects = LocalMaterialObjects(Path(object_root))
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    admin.commit()

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    def snapshot(identifier):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,error_code,preview_ready,revision FROM orbit_material_asset "
                "WHERE tenant_id=%s AND id=%s",
                (tenant, identifier),
            )
            state = cursor.fetchone()
            counts = []
            for table, column in (
                ("orbit_material_scan_receipt", "asset_id"),
                ("orbit_material_scan_runtime_proof", "asset_id"),
                ("orbit_material_audit", "resource_id"),
                ("orbit_material_outbox", "resource_id"),
            ):
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE tenant_id=%s AND {column}=%s",
                    (tenant, identifier),
                )
                counts.append(cursor.fetchone()[0])
            cursor.execute(
                "SELECT revision FROM orbit_material_clock WHERE tenant_id=%s", (tenant,)
            )
            clock = cursor.fetchone()[0]
        admin.commit()
        return state, tuple(counts), clock

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
        calls = []

        def processor(*args):
            calls.append(True)
            return process_material(*args)

        def worker(*, current=True, selected=None, provider=None):
            return MaterialWorker(
                sessions,
                objects,
                processor=processor,
                scanner=selected or scanner,
                runtime_profile_provider=(provider or (lambda claim: scanner.profile))
                if current
                else None,
            )

        async def fixture():
            identifier, upload = str(uuid4()), str(uuid4())
            output = BytesIO()
            Image.new("RGB", (24, 24), "purple").save(output, "PNG")
            content = output.getvalue()
            digest = hashlib.sha256(content).hexdigest()
            objects.put_part(tenant, upload, 1, content, len(content))
            objects.assemble(
                tenant,
                upload,
                [CompletedPart(part_number=1, etag=digest)],
                len(content),
                digest,
                "image/png",
            )
            async with sessions() as session, session.begin():
                context = await require_business_access(session, 1, "assets", "assets.upload")
                version = await actor_auth_version(session, 1)
                item = {
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
                    VALUES(:tenant,:id,:owner,:team,'runtime Worker真实PNG',:category,
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
                    VALUES(:tenant,:id,1,:version,:scope,'PENDING','1800-01-01')"""),
                    {
                        "tenant": tenant,
                        "id": identifier,
                        "version": version,
                        "scope": material_job_scope(context, item),
                    },
                )
            return identifier

        async def scan(claim):
            return await asyncio.to_thread(
                scanner.scan,
                objects,
                tenant,
                claim["object_upload_id"],
                claim["sha256"],
                claim["byte_size"],
            )

        try:
            current = worker()
            identifier = await fixture()
            assert await current.run_once(1) == [{"asset_id": identifier, "state": "READY"}]
            assert len(calls) == 1 and snapshot(identifier)[0][0:3] == ("READY", None, 1)
            assert snapshot(identifier)[1] == (1, 1, 3, 3)
            async with sessions() as session:
                assert identifier in await clean_scan_ids(session, tenant, [identifier])
            cases.append(MATERIAL_RUNTIME_WORKER_CASES[0])
            identifier = await fixture()
            before_calls = len(calls)
            assert await worker(
                current=False, selected=ClamdMaterialScanner(scanner.profile.policy)
            ).run_once(1) == [{"asset_id": identifier, "state": "PROCESSING_FAILED"}]
            assert len(calls) == before_calls and snapshot(identifier)[1][1] == 0
            assert snapshot(identifier)[0][1:3] == ("ANTIVIRUS_RUNTIME_UNVERIFIED", 0)
            cases.append(MATERIAL_RUNTIME_WORKER_CASES[1])
            identifier = await fixture()
            assert await worker(current=False).run_once(1) == [
                {"asset_id": identifier, "state": "PROCESSING_FAILED"}
            ]
            assert len(calls) == before_calls and snapshot(identifier)[1][1] == 0
            cases.append(MATERIAL_RUNTIME_WORKER_CASES[2])
            identifier = await fixture()
            selected = []

            def changed_profile(claim):
                selected.append(True)
                return (
                    scanner.profile
                    if len(selected) == 1
                    else replace(scanner.profile, revision=scanner.profile.revision + 1)
                )

            assert await worker(provider=changed_profile).run_once(1) == [
                {"asset_id": identifier, "state": "PROCESSING_FAILED"}
            ]
            assert len(calls) == before_calls and snapshot(identifier)[1][1] == 0
            cases.append(MATERIAL_RUNTIME_WORKER_CASES[3])
            identifier = await fixture()
            claim = await current.claim()
            assert claim["asset_id"] == identifier
            result = await scan(claim)
            before = snapshot(identifier)
            trigger = "orbit_it_runtime_state_" + uuid4().hex[:12]
            try:
                with admin.cursor() as cursor:
                    cursor.execute(f"""CREATE TRIGGER {trigger}
                    BEFORE INSERT ON orbit_material_audit FOR EACH ROW BEGIN
                    IF NEW.resource_id='{identifier}' AND NEW.action='MATERIAL_PROCESSING' THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='runtime state audit'; END IF; END""")
                admin.commit()
                try:
                    await current.record_scan(claim, result, profile=scanner.profile)
                except DBAPIError as error:
                    assert error.orig.args[0] == 1644
                else:
                    raise AssertionError("状态审计失败必须回滚全部扫描证据")
                assert snapshot(identifier) == before
                cases.append(MATERIAL_RUNTIME_WORKER_CASES[4])
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")
                admin.commit()
            advanced, state = await current.record_scan(claim, result, profile=scanner.profile)
            assert state == "PROCESSING" and advanced["revision"] == claim["revision"] + 1
            committed = snapshot(identifier)
            assert await current.record_scan(claim, result, profile=scanner.profile) == (
                None,
                "STALE",
            )
            assert snapshot(identifier) == committed and committed[1] == (1, 1, 2, 2)
            cases.append(MATERIAL_RUNTIME_WORKER_CASES[5])
            # 当前原文件真实扫描过，人工只放旧026无030反例，不冒充完整可用证明。
            identifier = await fixture()
            legacy = await current.claim()
            real = await scan(legacy)
            assert real.receipt.result == "CLEAN"
            async with sessions() as session, session.begin():
                await session.execute(
                    text("""INSERT INTO orbit_material_scan_receipt
                (tenant_id,asset_id,claim_id,id,result,sha256,byte_size,engine_version,
                 database_version,database_built_at,policy_sha256,started_at,completed_at)
                VALUES(:tenant_id,:asset_id,:claim_id,:id,'CLEAN',:sha256,:byte_size,
                 :engine,:database,:built,:policy,:started,:completed)"""),
                    {
                        **legacy,
                        "id": str(uuid4()),
                        "engine": real.receipt.engine_version,
                        "database": real.receipt.database_version,
                        "built": real.receipt.database_built_at.replace(tzinfo=None),
                        "policy": real.receipt.policy_sha256,
                        "started": real.receipt.started_at.replace(tzinfo=None),
                        "completed": real.receipt.completed_at.replace(tzinfo=None),
                    },
                )
                await session.execute(
                    text(
                        "UPDATE orbit_material_asset SET state='PROCESSING' "
                        "WHERE tenant_id=:tenant_id AND id=:asset_id"
                    ),
                    legacy,
                )
            media = await asyncio.to_thread(
                process_material, objects, tenant, legacy["object_upload_id"], legacy["mime"]
            )
            assert await current.finish(legacy, "READY", None, media) == (True, "PROCESSING_FAILED")
            assert snapshot(identifier)[0][2] == 0 and snapshot(identifier)[1][1] == 0
            async with sessions() as session:
                assert identifier not in await clean_scan_ids(session, tenant, [identifier])
            cases.append(MATERIAL_RUNTIME_WORKER_CASES[6])
        finally:
            await engine.dispose()
        assert attest_fixture() == process_before

    asyncio.run(run())
