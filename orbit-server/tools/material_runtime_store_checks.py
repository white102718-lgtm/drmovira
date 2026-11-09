"""030实际SQL原子绑定专项；主线独立库排队，不启动服务/篡改共享引擎。"""

import asyncio
import hashlib
import json
import re
from contextlib import nullcontext
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from uuid import uuid4

from PIL import Image
from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_RUNTIME_STORE_CASES = [
    "pythonMaterialRuntimeStoreActualReceiptProofAuditOutboxAtomicNoReadyPromotion",
    "pythonMaterialRuntimeStoreExactReplayDoesNotDuplicateEventOrClock",
    "pythonMaterialRuntimeStoreDifferentResultCannotOverwriteImmutableBinding",
    "pythonMaterialRuntimeStoreClaimAndGenerationMismatchCannotBorrowProof",
    "pythonMaterialRuntimeStoreExpiredLeaseDoesNotPersistAnyProof",
    "pythonMaterialRuntimeStoreAudit1644RollsBackReceiptProofEventAndClock",
    "pythonMaterialRuntimeStoreAuditRollbackRetryCommitsExactlyOneEvent",
    "pythonMaterialRuntimeStoreLegacyReceiptWithoutProofCannotBeUpgraded",
    "pythonMaterialRuntimeStoreFourColumnForeignKeyRejectsWrongReceiptClaim",
    "pythonMaterialRuntimeStoreExpiredProofRejectedUsingActualDatabaseUtc",
    "pythonMaterialRuntimeStoreConcurrentDuplicateCommitsOneProofAndEvent",
]


def run_material_runtime_store_checks(admin, database, cases):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host
        not in {
            "127.0.0.1",
            "localhost",
        }
        or admin.port != 13306
    ):
        raise ValueError("030专项仅允许主线本机UUID隔离库")
    from clamd_fixture_attestation import attest_fixture
    from material_runtime_fixture import material_runtime_fixture_scanner

    from orbit_api.authorization import require_business_access
    from orbit_api.errors import OrbitError
    from orbit_api.material_job_policy import actor_auth_version, material_job_scope
    from orbit_api.material_runtime_store import append_runtime_scan
    from orbit_api.material_worker import MaterialWorker

    scanner, process_before = material_runtime_fixture_scanner()
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    admin.commit()

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    def counts(identifier):
        result = []
        with admin.cursor() as cursor:
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
                result.append(cursor.fetchone()[0])
            cursor.execute(
                "SELECT revision FROM orbit_material_clock WHERE tenant_id=%s", (tenant,)
            )
            clock = cursor.fetchone()[0]
        admin.commit()
        return tuple(result), clock

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
        worker = MaterialWorker(sessions, None)

        async def fixture():
            identifier, upload = str(uuid4()), str(uuid4())
            buffer = BytesIO()
            Image.new("RGB", (24, 24), "purple").save(buffer, "PNG")
            content = buffer.getvalue()
            digest = hashlib.sha256(content).hexdigest()
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
                    VALUES(:tenant,:id,:owner,:team,'030实际SQL隔离夹具',:category,
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
                    VALUES(:tenant,:id,1,:version,:scope,'PENDING','1900-01-01')"""),
                    {
                        "tenant": tenant,
                        "id": identifier,
                        "version": version,
                        "scope": material_job_scope(context, item),
                    },
                )
            claim = await worker.claim()
            assert claim["asset_id"] == identifier and "cancelled" not in claim

            class Source:
                def open(self, mode):
                    assert mode == "rb"
                    return BytesIO(content)

            class Objects:
                def original(self, current_tenant, current_upload):
                    assert (current_tenant, current_upload) == (tenant, upload)
                    return Source()

                def mutation_guard(self, *args):
                    return nullcontext()

            result = await asyncio.to_thread(
                scanner.scan, Objects(), tenant, upload, digest, len(content)
            )
            assert result.receipt.result == "CLEAN" and result.proof is not None
            return claim, result

        async def append(claim, result, profile=None):
            async with sessions() as session, session.begin():
                return await append_runtime_scan(session, claim, result, profile or scanner.profile)

        async def rejects(claim, result, code):
            before = counts(claim["asset_id"])
            try:
                await append(claim, result)
            except OrbitError as error:
                assert error.status == 409 and error.code == code, (error.status, error.code)
            else:
                raise AssertionError("无效运行证明必须拒绝")
            assert counts(claim["asset_id"]) == before

        try:
            claim, result = await fixture()
            initial, clock = counts(claim["asset_id"])
            assert initial == (0, 0, 0, 0)
            stored = await append(claim, result)
            assert not stored.replayed
            assert counts(claim["asset_id"]) == ((1, 1, 1, 1), clock + 1)
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT state,preview_ready,revision FROM orbit_material_asset "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, claim["asset_id"]),
                )
                assert cursor.fetchone() == ("SCANNING", 0, claim["revision"])
                cursor.execute(
                    "SELECT policy_sha256 FROM orbit_material_scan_receipt "
                    "WHERE tenant_id=%s AND asset_id=%s",
                    (tenant, claim["asset_id"]),
                )
                assert cursor.fetchone()[0] == scanner.profile.policy.config_sha256
                cursor.execute(
                    "SELECT change_json FROM orbit_material_audit WHERE id=%s", (stored.event_id,)
                )
                change = json.loads(cursor.fetchone()[0])
                assert change == {
                    "reason": "可信扫描收据与当前运行实例证明原子绑定",
                    "before": None,
                    "after": {
                        "receipt_id": stored.receipt_id,
                        "claim_id": claim["claim_id"],
                        "profile_id": scanner.profile.profile_id,
                        "profile_revision": scanner.profile.revision,
                        "instance_id": scanner.profile.instance_id,
                        "result": "CLEAN",
                    },
                }
            admin.commit()
            cases.append(MATERIAL_RUNTIME_STORE_CASES[0])
            replay = await append(claim, result)
            assert (
                replay.replayed
                and replay.receipt_id == stored.receipt_id
                and replay.event_id == stored.event_id
            )
            assert counts(claim["asset_id"]) == ((1, 1, 1, 1), clock + 1)
            cases.append(MATERIAL_RUNTIME_STORE_CASES[1])
            changed = replace(
                result,
                receipt=replace(
                    result.receipt, result="UNVERIFIED", error_code="ANTIVIRUS_UNAVAILABLE"
                ),
            )
            await rejects(claim, changed, "MATERIAL_RUNTIME_SCAN_CONFLICT")
            cases.append(MATERIAL_RUNTIME_STORE_CASES[2])
            await rejects({**claim, "claim_id": str(uuid4())}, result, "MATERIAL_SCAN_STALE")
            await rejects(
                claim,
                replace(result, proof=replace(result.proof, instance_id=str(uuid4()))),
                "MATERIAL_RUNTIME_PROOF_INVALID",
            )
            cases.append(MATERIAL_RUNTIME_STORE_CASES[3])
            stale_claim, stale_result = await fixture()
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_material_job SET claimed_at=UTC_TIMESTAMP(3)-INTERVAL 6 MINUTE "
                    "WHERE tenant_id=%s AND asset_id=%s",
                    (tenant, stale_claim["asset_id"]),
                )
            admin.commit()
            await rejects(stale_claim, stale_result, "MATERIAL_SCAN_STALE")
            cases.append(MATERIAL_RUNTIME_STORE_CASES[4])
            rollback_claim, rollback_result = await fixture()
            snapshot = counts(rollback_claim["asset_id"])
            trigger = "orbit_it_runtime_audit_" + uuid4().hex[:12]
            try:
                with admin.cursor() as cursor:
                    cursor.execute(f"""CREATE TRIGGER {trigger}
                    BEFORE INSERT ON orbit_material_audit
                    FOR EACH ROW BEGIN IF NEW.resource_id='{rollback_claim["asset_id"]}'
                    AND NEW.action='MATERIAL_SCAN_RUNTIME_BOUND' THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='runtime audit fixture';
                    END IF; END""")
                admin.commit()
                try:
                    await append(rollback_claim, rollback_result)
                except DBAPIError as error:
                    assert error.orig.args[0] == 1644
                else:
                    raise AssertionError("审计拒绝必须回滚实例证明")
                assert counts(rollback_claim["asset_id"]) == snapshot
                cases.append(MATERIAL_RUNTIME_STORE_CASES[5])
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")
                admin.commit()
            await append(rollback_claim, rollback_result)
            assert counts(rollback_claim["asset_id"]) == ((1, 1, 1, 1), snapshot[1] + 1)
            cases.append(MATERIAL_RUNTIME_STORE_CASES[6])
            legacy_claim, legacy_result = await fixture()
            # 显式保留旧026反例；新Worker不再允许raw CLEAN进入PROCESSING。
            # 原文件已真实扫描，以下只模拟历史缺030元数据，不声称有完整运行资格。
            async with sessions() as session, session.begin():
                await session.execute(
                    text("""INSERT INTO orbit_material_scan_receipt
                (tenant_id,asset_id,claim_id,id,result,sha256,byte_size,engine_version,
                 database_version,database_built_at,policy_sha256,started_at,completed_at)
                VALUES(:tenant_id,:asset_id,:claim_id,:id,'CLEAN',:sha256,:byte_size,
                 :engine,:database,:built,:policy,:started,:completed)"""),
                    {
                        **legacy_claim,
                        "id": str(uuid4()),
                        "engine": legacy_result.receipt.engine_version,
                        "database": legacy_result.receipt.database_version,
                        "built": legacy_result.receipt.database_built_at.replace(tzinfo=None),
                        "policy": legacy_result.receipt.policy_sha256,
                        "started": legacy_result.receipt.started_at.replace(tzinfo=None),
                        "completed": legacy_result.receipt.completed_at.replace(tzinfo=None),
                    },
                )
                await session.execute(
                    text("""UPDATE orbit_material_asset
                    SET state='PROCESSING',revision=revision+1
                    WHERE tenant_id=:tenant_id AND id=:asset_id"""),
                    legacy_claim,
                )
            await rejects(legacy_claim, legacy_result, "MATERIAL_RUNTIME_PROOF_REQUIRED")
            cases.append(MATERIAL_RUNTIME_STORE_CASES[7])
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM orbit_material_scan_receipt "
                    "WHERE tenant_id=%s AND asset_id=%s AND claim_id=%s",
                    (tenant, legacy_claim["asset_id"], legacy_claim["claim_id"]),
                )
                legacy_id = cursor.fetchone()[0]
                # 第二条仅为FK反例的UNVERIFIED元数据，不伪称实际扫描或赋予CLEAN资格。
                other_claim, other_receipt = str(uuid4()), str(uuid4())
                cursor.execute(
                    """INSERT INTO orbit_material_scan_receipt
                (tenant_id,asset_id,claim_id,id,result,sha256,byte_size,started_at,completed_at,error_code)
                SELECT tenant_id,asset_id,%s,%s,'UNVERIFIED',sha256,byte_size,
                started_at,completed_at,'ANTIVIRUS_UNAVAILABLE'
                FROM orbit_material_scan_receipt WHERE tenant_id=%s AND asset_id=%s AND id=%s""",
                    (other_claim, other_receipt, tenant, legacy_claim["asset_id"], legacy_id),
                )
            admin.commit()
            try:
                with admin.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO orbit_material_scan_runtime_proof
                    (tenant_id,asset_id,receipt_id,claim_id,profile_id,profile_revision,instance_id,
                     profile_sha256,source_sha256,executable_sha256,config_sha256,process_created_at_us,
                     issued_at,expires_at,verified_before,verified_after)
                    SELECT tenant_id,%s,%s,%s,profile_id,profile_revision,instance_id,
                     profile_sha256,source_sha256,executable_sha256,config_sha256,process_created_at_us,
                     issued_at,expires_at,verified_before,verified_after
                    FROM orbit_material_scan_runtime_proof WHERE tenant_id=%s AND asset_id=%s""",
                        (
                            legacy_claim["asset_id"],
                            legacy_id,
                            other_claim,
                            tenant,
                            claim["asset_id"],
                        ),
                    )
            except Exception as error:
                assert error.args[0] == 1452
                admin.rollback()
            else:
                admin.rollback()
                raise AssertionError("四列外键必须拒绝同收据借用其他claim")
            assert counts(legacy_claim["asset_id"])[0][1] == 0
            cases.append(MATERIAL_RUNTIME_STORE_CASES[8])
            # 有效扫描窗口之后、真实SQL当前时间之前到期；不sleep或改共享时钟。
            expiration = result.proof.verified_after + timedelta(microseconds=1)
            expired_profile = replace(scanner.profile, expires_at=expiration)
            expired_result = replace(result, proof=replace(result.proof, expires_at=expiration))
            snapshot = counts(claim["asset_id"])
            try:
                await append(claim, expired_result, expired_profile)
            except OrbitError as error:
                assert error.status == 409 and error.code == "MATERIAL_RUNTIME_PROOF_INVALID"
            else:
                raise AssertionError("真实数据库时间已过期不能重放证明")
            assert counts(claim["asset_id"]) == snapshot
            cases.append(MATERIAL_RUNTIME_STORE_CASES[9])
            concurrent_claim, concurrent_result = await fixture()
            snapshot = counts(concurrent_claim["asset_id"])
            first, second = await asyncio.gather(
                append(concurrent_claim, concurrent_result),
                append(concurrent_claim, concurrent_result),
            )
            assert sorted([first.replayed, second.replayed]) == [False, True]
            assert first.receipt_id == second.receipt_id and first.event_id == second.event_id
            assert counts(concurrent_claim["asset_id"]) == ((1, 1, 1, 1), snapshot[1] + 1)
            cases.append(MATERIAL_RUNTIME_STORE_CASES[10])
        finally:
            await engine.dispose()
        assert attest_fixture() == process_before

    asyncio.run(run())
