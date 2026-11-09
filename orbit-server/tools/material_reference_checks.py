"""素材内部引用真实SQL/对象/扫描Worker专项；不代替HTTP上传或任务发布验收。"""

import asyncio
import hashlib
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_REFERENCE_CASES = [
    "pythonMaterialReferenceSafeMetadataHasExplicitUnverifiedScanGate",
    "pythonMaterialReferenceCompleteBatchRejectsMissingAndChangedRevisionHash",
    "pythonMaterialReferenceCleaningAndArchivedNeverBecomeNewAllocation",
    "pythonMaterialReferenceActualRegistrationIsIdempotentAndAudited",
    "pythonMaterialReferenceReplacementLocksUnionAndReleasesOnlyExactOwnKind",
    "pythonMaterialReferenceFailedOuterPlanCasRollsBackReferenceAuditAndOutbox",
    "pythonMaterialReferenceCancellationPreservesHistoricalEvidence",
    "pythonMaterialReferenceResourceLookupUsesActualCompositeIndex",
]


def run_material_reference_checks(admin, database, cases, *, scanner, object_root):
    if not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database):
        raise ValueError("内部素材专项只使用当前UUID隔离库")
    if admin.host not in {"localhost", "127.0.0.1"} or admin.port != 13306:
        raise ValueError("内部素材专项禁止连接共享或远程MySQL")
    from orbit_api.authorization import require_business_access
    from orbit_api.errors import OrbitError
    from orbit_api.material_contract import CompletedPart
    from orbit_api.material_job_policy import actor_auth_version, material_job_scope
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_references import (
        deactivate_locked_material_references,
        lock_active_material_reference_set,
        register_active_material_references,
        require_allocation_assets,
    )
    from orbit_api.material_worker import MaterialWorker

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    first, second, missing, resource, historical, legacy = [str(uuid4()) for _ in range(6)]
    objects = LocalMaterialObjects(Path(object_root))
    uploads = {}
    with admin.cursor() as cursor:
        for identifier in (first, second, legacy):
            output = BytesIO()
            Image.new("RGB", (16, 16), "orange" if identifier == first else "blue").save(
                output, "PNG"
            )
            content, upload = output.getvalue(), str(uuid4())
            digest = hashlib.sha256(content).hexdigest()
            uploads[identifier] = {
                "id": identifier,
                "owner_user_id": owner,
                "owner_team_id": team,
                "sha256": digest,
                "mime": "image/png",
            }
            if identifier != legacy:
                objects.put_part(tenant, upload, 1, content, len(content))
                objects.assemble(
                    tenant,
                    upload,
                    [CompletedPart(part_number=1, etag=digest)],
                    len(content),
                    digest,
                    "image/png",
                )
            cursor.execute(
                """INSERT INTO orbit_material_asset
                (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,
                 sha256,byte_size,object_upload_id,width_px,height_px,duration_seconds)
                VALUES(%s,%s,%s,%s,'内部引用真实安全PNG',%s,'IMAGE','image/png',%s,
                %s,%s,%s,NULL,NULL,NULL)""",
                (
                    tenant,
                    identifier,
                    owner,
                    team,
                    "00000000-0000-4000-8000-000000000001",
                    "READY" if identifier == legacy else "SCANNING",
                    digest,
                    len(content),
                    upload,
                ),
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

        async def context(session):
            return await require_business_access(session, 1, "assets", "assets.read")

        async def rejected(code, identifiers, **kwargs):
            async with sessions() as session, session.begin():
                ctx = await context(session)
                try:
                    await require_allocation_assets(
                        session, ctx, owner, team, identifiers, **kwargs
                    )
                except OrbitError as error:
                    assert error.code == code, (error.status, error.code)
                else:
                    raise AssertionError("素材冻结条件失效却成功")

        try:
            async with sessions() as session, session.begin():
                ctx = await require_business_access(session, 1, "assets", "assets.upload")
                version = await actor_auth_version(session, 1)
                for identifier in (first, second):
                    await session.execute(
                        text("""INSERT INTO orbit_material_job
                        (tenant_id,asset_id,actor_id,actor_auth_version,scope_digest,state,created_at)
                        VALUES(:tenant,:asset,1,:version,:scope,'PENDING',
                        '2000-01-01 00:00:00')"""),
                        {
                            "tenant": tenant,
                            "asset": identifier,
                            "version": version,
                            "scope": material_job_scope(ctx, uploads[identifier]),
                        },
                    )
            processed = await MaterialWorker(
                sessions,
                objects,
                scanner=scanner,
                runtime_profile_provider=lambda claim: scanner.profile,
            ).run_once(2)
            assert len(processed) == 2 and all(item["state"] == "READY" for item in processed)
            async with sessions() as session, session.begin():
                ctx = await context(session)
                combined = await require_allocation_assets(
                    session, ctx, owner, team, [first, legacy]
                )
                metadata = combined[first]
                assert metadata["width"] == 16 and metadata["height"] == 16
                assert metadata["duration"] is None
                assert metadata["antivirus_status"] == "CLEAN"
                assert metadata["execution_eligible"] is True
                assert not {"object_upload_id", "path", "original_url"} & set(metadata)
                legacy_read = {legacy: combined[legacy]}
                assert legacy_read[legacy]["antivirus_status"] == "UNVERIFIED"
                assert legacy_read[legacy]["execution_eligible"] is False
                try:
                    await register_active_material_references(
                        session, ctx, owner, team, legacy_read, "ALLOCATION", resource, str(uuid4())
                    )
                except OrbitError as error:
                    assert error.code == "ANTIVIRUS_UNVERIFIED"
                else:
                    raise AssertionError("旧READY不得继承为扫描通过")
            cases.append(MATERIAL_REFERENCE_CASES[0])
            await rejected("MATERIAL_REFERENCE_UNAVAILABLE", [first, missing])
            await rejected("REVISION_CONFLICT", [first], expected_revisions={first: 999})
            await rejected("MATERIAL_HASH_CONFLICT", [first], expected_sha256={first: "b" * 64})
            cases.append(MATERIAL_REFERENCE_CASES[1])
            for column, value in (("state", "ARCHIVED"), ("physical_cleanup_state", "CLEANING")):
                with admin.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE orbit_material_asset SET {column}=%s WHERE tenant_id=%s AND id=%s",
                        (value, tenant, first),
                    )
                admin.commit()
                await rejected("MATERIAL_NOT_READY", [first])
                with admin.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE orbit_material_asset SET {column}=%s WHERE tenant_id=%s AND id=%s",
                        ("READY" if column == "state" else "LIVE", tenant, first),
                    )
                admin.commit()
            cases.append(MATERIAL_REFERENCE_CASES[2])
            async with sessions() as session, session.begin():
                ctx = await context(session)
                await lock_active_material_reference_set(
                    session, ctx, "ALLOCATION", resource, additional_asset_ids=[first]
                )
                frozen = await require_allocation_assets(session, ctx, owner, team, [first])
                refs = await register_active_material_references(
                    session, ctx, owner, team, frozen, "ALLOCATION", resource, str(uuid4())
                )
                assert refs == await register_active_material_references(
                    session, ctx, owner, team, frozen, "ALLOCATION", resource, str(uuid4())
                )
                count = (
                    await session.execute(
                        text("""SELECT COUNT(*) FROM orbit_material_audit
                    WHERE tenant_id=:tenant AND resource_id=:asset
                    AND action='MATERIAL_REFERENCE_ADDED'"""),
                        {"tenant": tenant, "asset": first},
                    )
                ).scalar_one()
                assert count == 1
            cases.append(MATERIAL_REFERENCE_CASES[3])
            with admin.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO orbit_material_reference
                    (tenant_id,asset_id,id,kind,resource_id,active)
                    VALUES(%s,%s,%s,'HISTORICAL_EVIDENCE',%s,0)""",
                    (tenant, first, str(uuid4()), historical),
                )
            admin.commit()
            async with sessions() as session, session.begin():
                ctx = await context(session)
                ticket = await lock_active_material_reference_set(
                    session, ctx, "ALLOCATION", resource, additional_asset_ids=[second]
                )
                frozen = await require_allocation_assets(session, ctx, owner, team, [second])
                assert (
                    await deactivate_locked_material_references(session, ctx, ticket, str(uuid4()))
                    == 1
                )
                await register_active_material_references(
                    session, ctx, owner, team, frozen, "ALLOCATION", resource, str(uuid4())
                )
            cases.append(MATERIAL_REFERENCE_CASES[4])
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_material_outbox "
                    "WHERE tenant_id=%s AND resource_id=%s",
                    (tenant, second),
                )
                before_outbox = cursor.fetchone()[0]
                # 真runtime绑定、SCANNING→PROCESSING、媒体READY及引用登记各一条。
                assert before_outbox == 4
                cursor.execute(
                    "SELECT action,COUNT(*) FROM orbit_material_audit "
                    "WHERE tenant_id=%s AND resource_id=%s GROUP BY action",
                    (tenant, second),
                )
                assert dict(cursor.fetchall()) == {
                    "MATERIAL_SCAN_RUNTIME_BOUND": 1,
                    "MATERIAL_PROCESSING": 1,
                    "MATERIAL_READY": 1,
                    "MATERIAL_REFERENCE_ADDED": 1,
                }
            admin.commit()
            try:
                async with sessions() as session, session.begin():
                    ctx = await context(session)
                    ticket = await lock_active_material_reference_set(
                        session, ctx, "ALLOCATION", resource
                    )
                    await deactivate_locked_material_references(session, ctx, ticket, str(uuid4()))
                    raise RuntimeError("fixture-plan-cas-failed")
            except RuntimeError as error:
                assert str(error) == "fixture-plan-cas-failed"
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT active FROM orbit_material_reference WHERE tenant_id=%s "
                    "AND asset_id=%s AND kind='ALLOCATION' AND resource_id=%s",
                    (tenant, second, resource),
                )
                assert cursor.fetchone()[0] == 1
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_material_audit WHERE tenant_id=%s "
                    "AND resource_id=%s AND action='MATERIAL_REFERENCE_RELEASED'",
                    (tenant, second),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_material_outbox "
                    "WHERE tenant_id=%s AND resource_id=%s",
                    (tenant, second),
                )
                assert cursor.fetchone()[0] == before_outbox
            admin.commit()
            cases.append(MATERIAL_REFERENCE_CASES[5])
            # 合法取消允许旧素材已经归档，历史种类始终保留。
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_material_asset SET state='ARCHIVED' WHERE tenant_id=%s AND id=%s",
                    (tenant, second),
                )
            admin.commit()
            async with sessions() as session, session.begin():
                ctx = await context(session)
                ticket = await lock_active_material_reference_set(
                    session, ctx, "ALLOCATION", resource
                )
                assert (
                    await deactivate_locked_material_references(session, ctx, ticket, str(uuid4()))
                    == 1
                )
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_material_reference WHERE tenant_id=%s "
                    "AND asset_id=%s AND kind='HISTORICAL_EVIDENCE' AND resource_id=%s",
                    (tenant, first, historical),
                )
                assert cursor.fetchone()[0] == 1
            admin.commit()
            cases.append(MATERIAL_REFERENCE_CASES[6])
            with admin.cursor() as cursor:
                cursor.execute(
                    "EXPLAIN SELECT id,asset_id FROM orbit_material_reference "
                    "WHERE tenant_id=%s AND kind='ALLOCATION' AND resource_id=%s AND active=1 "
                    "ORDER BY asset_id,id LIMIT 501",
                    (tenant, resource),
                )
                names = [column[0] for column in cursor.description]
                plan = dict(zip(names, cursor.fetchone(), strict=True))
                assert plan["key"] == "idx_material_reference_resource", plan["key"]
                assert plan["type"] == "ref" and "filesort" not in (plan["Extra"] or "").lower()
            admin.commit()
            cases.append(MATERIAL_REFERENCE_CASES[7])
        finally:
            await engine.dispose()

    asyncio.run(run())
