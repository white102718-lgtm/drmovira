"""真实扫描Worker/SQL租约与证据回滚；不写标准测试签名或恶意样本。"""

import asyncio
import hashlib
import re
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image
from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_ANTIVIRUS_WORKER_CASES = [
    "pythonMaterialAntivirusActualWorkerKeepsScanningUntilCleanAndPublishesVerifiedPreview",
    "pythonMaterialAntivirusMissingScannerFailsWithoutPreviewOrReady",
    "pythonMaterialAntivirusStaleDatabaseFailsClosedWithPersistentUnverifiedReceipt",
    "pythonMaterialAntivirusExpiredScanLeaseRejectsOldResultAndRecoversNewClaim",
    "pythonMaterialAntivirusExpiredProcessingLeaseCannotPublishReady",
    "pythonMaterialAntivirusReceiptAuditFailureRollsBackStateAndProofAtomically",
]


def run_material_antivirus_worker_checks(admin, database, object_root, scanner, cases):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host not in {"localhost", "127.0.0.1"}
        or admin.port != 13306
    ):
        raise ValueError("扫描Worker专项仅使用主线本机UUID隔离库")
    from orbit_api.authorization import require_business_access
    from orbit_api.material_antivirus import ClamdMaterialScanner
    from orbit_api.material_contract import CompletedPart
    from orbit_api.material_job_policy import actor_auth_version, material_job_scope
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_processing import process_material
    from orbit_api.material_worker import MaterialWorker

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    objects = LocalMaterialObjects(Path(object_root))

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    def asset_state(identifier):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,error_code,preview_ready FROM orbit_material_asset "
                "WHERE tenant_id=%s AND id=%s",
                (tenant, identifier),
            )
            result = cursor.fetchone()
        admin.commit()
        return result

    def expire(claim):
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_material_job SET claimed_at=UTC_TIMESTAMP(3)-INTERVAL 6 MINUTE "
                "WHERE tenant_id=%s AND asset_id=%s",
                (tenant, claim["asset_id"]),
            )
        admin.commit()

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
        worker = MaterialWorker(
            sessions,
            objects,
            scanner=scanner,
            runtime_profile_provider=lambda claim: scanner.profile,
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
                ctx = await require_business_access(session, 1, "assets", "assets.upload")
                version = await actor_auth_version(session, 1)
                await session.execute(
                    text("""INSERT INTO orbit_material_asset
                    (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
                    sha256,byte_size,object_upload_id)
                    VALUES(:tenant,:id,:owner,:team,'真实扫描Worker安全PNG',:category,
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
                scope = material_job_scope(
                    ctx,
                    {
                        "id": identifier,
                        "owner_user_id": owner,
                        "owner_team_id": team,
                        "sha256": digest,
                        "mime": "image/png",
                    },
                )
                await session.execute(
                    text("""INSERT INTO orbit_material_job
                    (tenant_id,asset_id,actor_id,actor_auth_version,scope_digest,state,created_at)
                    VALUES(:tenant,:id,1,:version,:scope,'PENDING','2000-01-01 00:00:00')"""),
                    {"tenant": tenant, "id": identifier, "version": version, "scope": scope},
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

        async def process(claim):
            result = await asyncio.to_thread(
                process_material, objects, tenant, claim["object_upload_id"], claim["mime"]
            )
            return await worker.finish(claim, "READY", None, result)

        try:
            identifier = await fixture()
            claim = await worker.claim()
            assert claim["asset_id"] == identifier and asset_state(identifier) == (
                "SCANNING",
                None,
                0,
            )
            proof = await scan(claim)
            assert proof.receipt.result == "CLEAN"
            claimed, phase = await worker.record_scan(claim, proof, profile=scanner.profile)
            assert phase == "PROCESSING" and asset_state(identifier) == ("PROCESSING", None, 0)
            assert await process(claimed) == (True, "READY")
            assert asset_state(identifier) == ("READY", None, 1)
            cases.append(MATERIAL_ANTIVIRUS_WORKER_CASES[0])
            identifier = await fixture()
            assert (await MaterialWorker(sessions, objects).run_once(1))[0][
                "state"
            ] == "PROCESSING_FAILED"
            assert asset_state(identifier) == ("PROCESSING_FAILED", "ANTIVIRUS_UNAVAILABLE", 0)
            cases.append(MATERIAL_ANTIVIRUS_WORKER_CASES[1])
            identifier = await fixture()
            stale = ClamdMaterialScanner(
                replace(
                    scanner.profile.policy,
                    daily_db_built_at=scanner.profile.policy.daily_db_built_at - timedelta(days=3),
                )
            )
            assert (await MaterialWorker(sessions, objects, scanner=stale).run_once(1))[0][
                "state"
            ] == "PROCESSING_FAILED"
            assert asset_state(identifier) == ("PROCESSING_FAILED", "ANTIVIRUS_DATABASE_STALE", 0)
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT result,error_code FROM orbit_material_scan_receipt "
                    "WHERE tenant_id=%s AND asset_id=%s",
                    (tenant, identifier),
                )
                assert cursor.fetchone() == ("UNVERIFIED", "ANTIVIRUS_DATABASE_STALE")
            admin.commit()
            cases.append(MATERIAL_ANTIVIRUS_WORKER_CASES[2])
            identifier = await fixture()
            old = await worker.claim()
            proof = await scan(old)
            expire(old)
            assert await worker.record_scan(old, proof, profile=scanner.profile) == (None, "STALE")
            assert await worker.recover() == 1
            fresh = await worker.claim()
            assert fresh["claim_id"] != old["claim_id"]
            assert await worker.record_scan(old, proof, profile=scanner.profile) == (None, "STALE")
            fresh, phase = await worker.record_scan(
                fresh, await scan(fresh), profile=scanner.profile
            )
            assert phase == "PROCESSING" and await process(fresh) == (True, "READY")
            cases.append(MATERIAL_ANTIVIRUS_WORKER_CASES[3])
            identifier = await fixture()
            claim = await worker.claim()
            claim, phase = await worker.record_scan(
                claim, await scan(claim), profile=scanner.profile
            )
            expire(claim)
            assert await process(claim) == (False, "STALE")
            assert asset_state(identifier)[0] == "PROCESSING"
            assert await worker.recover() == 1
            assert (await worker.run_once(1))[0]["state"] == "READY"
            cases.append(MATERIAL_ANTIVIRUS_WORKER_CASES[4])
            identifier = await fixture()
            claim = await worker.claim()
            proof = await scan(claim)
            trigger = "it_av_audit_" + uuid4().hex
            with admin.cursor() as cursor:
                cursor.execute(
                    f"CREATE TRIGGER {trigger} BEFORE INSERT ON orbit_material_audit "
                    f"FOR EACH ROW BEGIN IF NEW.resource_id='{identifier}' THEN "
                    "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture audit reject'; END IF; END"
                )
            admin.commit()
            try:
                try:
                    await worker.record_scan(claim, proof, profile=scanner.profile)
                except DBAPIError as error:
                    assert error.orig.args[0] == 1644
                else:
                    raise AssertionError("扫描审计拒绝未回滚")
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(f"DROP TRIGGER {trigger}")
                admin.commit()
            assert asset_state(identifier)[0] == "SCANNING"
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_material_scan_receipt "
                    "WHERE tenant_id=%s AND asset_id=%s",
                    (tenant, identifier),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_material_scan_runtime_proof "
                    "WHERE tenant_id=%s AND asset_id=%s",
                    (tenant, identifier),
                )
                assert cursor.fetchone()[0] == 0
            admin.commit()
            claimed, phase = await worker.record_scan(claim, proof, profile=scanner.profile)
            assert phase == "PROCESSING" and await process(claimed) == (True, "READY")
            cases.append(MATERIAL_ANTIVIRUS_WORKER_CASES[5])
        finally:
            await engine.dispose()

    asyncio.run(run())
