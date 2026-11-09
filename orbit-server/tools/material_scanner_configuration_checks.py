"""034正式配置实际HTTP/SQL/Worker专项；由主线独占本机数据库及对象根运行。"""

import asyncio
import hashlib
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image
from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_SCANNER_CONFIGURATION_CASES = [
    "pythonMaterialScannerCandidatesExposeOnlyControlledPublicFields",
    "pythonMaterialScannerConfigurationRejectsUnknownProfileAndTransportFields",
    "pythonMaterialScannerConfigurationSingletonIncludesDisabledRows",
    "pythonMaterialScannerConfigurationReadTestActuallyScansSafePngAndAdvancesRevision",
    "pythonMaterialScannerConfiguredWorkerBindsExactTenantConfigurationToProof",
    "pythonMaterialScannerConfigurationChangesAfterScanFailClosedWithoutCleanProof",
    "pythonMaterialScannerConfigurationChangesBeforeRecordCannotPersistProof",
    "pythonMaterialScannerConfigurationChangesDuringProcessingCannotPublishReady",
    "pythonMaterialScannerConfigurationSourceForeignKeyAndNullPairRejectInvalidBinding",
    "pythonMaterialScannerConfigurationStateAuditRollbackIncludesSourceThenRetryIsExact",
]


def run_material_scanner_configuration_checks(
    client, admin, headers, database, object_root, cases, *, registry
):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host not in {"127.0.0.1", "localhost"}
        or admin.port != 13306
    ):
        raise ValueError("正式配置专项仅允许主线本机UUID隔离库")
    from orbit_api.authorization import require_business_access
    from orbit_api.material_contract import CompletedPart
    from orbit_api.material_job_policy import actor_auth_version, material_job_scope
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_processing import process_material
    from orbit_api.material_scanner_selection import ConfiguredMaterialWorker

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    admin.commit()
    profiles = client.get(
        "/api/v1/system-configurations/material-scanner-profiles", headers=headers
    )
    assert profiles.status_code == 200
    assert set(profiles.json()) == {"items"}
    options = profiles.json()["items"]
    assert options and all(set(row) == {"id", "label", "availability"} for row in options)
    profile_id = next(row["id"] for row in options if row["availability"] == "READY")
    bound_scanner = registry.resolve(profile_id).scanner
    invalid = client.get(
        "/api/v1/system-configurations/material-scanner-profiles?tenant=x", headers=headers
    )
    assert invalid.status_code == 400
    cases.append(MATERIAL_SCANNER_CONFIGURATION_CASES[0])
    capabilities = client.get("/api/v1/assets/capabilities", headers=headers)
    assert capabilities.status_code == 200
    csrf = capabilities.json()["csrf_token"]
    category = capabilities.json()["default_category_id"]
    payload = {
        "section": "MATERIAL_SCANNER",
        "name": "正式扫描专项",
        "enabled": True,
        "settings": {"profileId": profile_id},
        "secrets": {},
        "reason": "实际安全配置专项",
    }

    def send(value, *, path="", revision=None):
        extra = {"Idempotency-Key": str(uuid4()), "X-CSRF-Token": csrf}
        if revision is not None:
            extra["If-Match"] = f'"{revision}"'
        return client.post(
            "/api/v1/system-configurations" + path, headers=headers | extra, json=value
        )

    assert send({**payload, "settings": {"profileId": "missing-profile"}}).status_code == 422
    assert (
        send({**payload, "settings": {"profileId": profile_id, "port": 19310}}).status_code == 400
    )
    cases.append(MATERIAL_SCANNER_CONFIGURATION_CASES[1])
    created = send(payload)
    assert created.status_code == 200, (created.status_code, created.json().get("code"))
    config = created.json()
    duplicate = send({**payload, "name": "另一个名称", "enabled": False})
    assert (
        duplicate.status_code == 409 and duplicate.json()["code"] == "SCANNER_CONFIGURATION_EXISTS"
    )
    cases.append(MATERIAL_SCANNER_CONFIGURATION_CASES[2])
    probed = send(
        {"reason": "实际安全PNG只读扫描"}, path=f"/{config['id']}/test", revision=config["revision"]
    )
    assert probed.status_code == 200
    assert probed.json()["result"]["status"] == "READ_VERIFIED"
    tested_config = probed.json()["configuration"]
    assert tested_config["revision"] == config["revision"] + 1
    config = tested_config
    cases.append(MATERIAL_SCANNER_CONFIGURATION_CASES[3])
    objects = LocalMaterialObjects(Path(object_root))

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

        async def bump():
            async with sessions() as session, session.begin():
                await session.execute(
                    text(
                        "UPDATE orbit_system_configuration SET revision=revision+1 "
                        "WHERE tenant_id=:tenant AND id=:id"
                    ),
                    {"tenant": tenant, "id": config["id"]},
                )

        async def fixture():
            identifier, upload = str(uuid4()), str(uuid4())
            output = BytesIO()
            Image.new("RGB", (24, 24), "green").save(output, "PNG")
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
                  (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,sha256,byte_size,object_upload_id)
                  VALUES(:tenant,:id,:owner,:team,'正式配置实际PNG',:category,'IMAGE','image/png','SCANNING',:sha,:size,:upload)"""),
                    {
                        "tenant": tenant,
                        "id": identifier,
                        "owner": owner,
                        "team": team,
                        "category": category,
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

        async def state(identifier):
            async with sessions() as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT state,preview_ready FROM orbit_material_asset "
                            "WHERE tenant_id=:tenant AND id=:id"
                        ),
                        {"tenant": tenant, "id": identifier},
                    )
                ).one()
                proofs = (
                    await session.execute(
                        text(
                            "SELECT configuration_id,configuration_revision FROM "
                            "orbit_material_scan_runtime_proof "
                            "WHERE tenant_id=:tenant AND asset_id=:id"
                        ),
                        {"tenant": tenant, "id": identifier},
                    )
                ).all()
                return tuple(row), proofs

        try:
            identifier = await fixture()
            worker = ConfiguredMaterialWorker(sessions, objects, registry=registry)
            assert await worker.run_once(1) == [{"asset_id": identifier, "state": "READY"}]
            current_state, proofs = await state(identifier)
            assert current_state == ("READY", 1) and [tuple(row) for row in proofs] == [
                (config["id"], config["revision"])
            ]
            cases.append(MATERIAL_SCANNER_CONFIGURATION_CASES[4])

            class AfterScanChange(ConfiguredMaterialWorker):
                seen = 0

                async def current_runtime_profile(self, claim):
                    self.seen += 1
                    if self.seen == 2:
                        await bump()
                    return await super().current_runtime_profile(claim)

            identifier = await fixture()
            worker = AfterScanChange(sessions, objects, registry=registry)
            assert await worker.run_once(1) == [
                {"asset_id": identifier, "state": "PROCESSING_FAILED"}
            ]
            assert await state(identifier) == (("PROCESSING_FAILED", 0), [])
            cases.append(MATERIAL_SCANNER_CONFIGURATION_CASES[5])

            class BeforeRecordChange(ConfiguredMaterialWorker):
                async def record_runtime_scan(self, claim, result, profile):
                    await bump()
                    return await super().record_runtime_scan(claim, result, profile)

            identifier = await fixture()
            worker = BeforeRecordChange(sessions, objects, registry=registry)
            assert await worker.run_once(1) == [
                {"asset_id": identifier, "state": "PROCESSING_FAILED"}
            ]
            assert await state(identifier) == (("PROCESSING_FAILED", 0), [])
            cases.append(MATERIAL_SCANNER_CONFIGURATION_CASES[6])

            class DuringProcessingChange(ConfiguredMaterialWorker):
                async def finish(self, claim, state, error, result):
                    await bump()
                    return await super().finish(claim, state, error, result)

            identifier = await fixture()
            worker = DuringProcessingChange(sessions, objects, registry=registry)
            assert await worker.run_once(1) == [
                {"asset_id": identifier, "state": "PROCESSING_FAILED"}
            ]
            current_state, proofs = await state(identifier)
            assert current_state == ("PROCESSING_FAILED", 0) and len(proofs) == 1
            assert proofs[0][0] == config["id"] and proofs[0][1] > config["revision"]
            cases.append(MATERIAL_SCANNER_CONFIGURATION_CASES[7])
            before_source = await state(identifier)
            for fragment, parameters, error_number in (
                ("configuration_id=:missing", {"missing": str(uuid4())}, 1452),
                ("configuration_revision=NULL", {}, 3819),
            ):
                try:
                    async with sessions() as session, session.begin():
                        await session.execute(
                            text(
                                "UPDATE orbit_material_scan_runtime_proof SET "
                                + fragment
                                + " WHERE tenant_id=:tenant AND asset_id=:id"
                            ),
                            {"tenant": tenant, "id": identifier, **parameters},
                        )
                except DBAPIError as error:
                    assert error.orig.args[0] == error_number
                else:
                    raise AssertionError("正式配置来源FK/成对NULL约束必须生效")
                assert await state(identifier) == before_source
            cases.append(MATERIAL_SCANNER_CONFIGURATION_CASES[8])

            identifier = await fixture()
            worker = ConfiguredMaterialWorker(sessions, objects, registry=registry)
            claim = await worker.claim()
            assert claim["asset_id"] == identifier
            profile = await worker.current_runtime_profile(claim)
            actual = await asyncio.to_thread(
                worker.scanner.scan,
                objects,
                tenant,
                claim["object_upload_id"],
                claim["sha256"],
                claim["byte_size"],
            )
            assert actual.receipt.result == "CLEAN" and actual.proof is not None
            assert await worker.current_runtime_profile(claim) == profile

            async def counts():
                async with sessions() as session:
                    result = []
                    for table, column in (
                        ("orbit_material_scan_receipt", "asset_id"),
                        ("orbit_material_scan_runtime_proof", "asset_id"),
                        ("orbit_material_audit", "resource_id"),
                        ("orbit_material_outbox", "resource_id"),
                    ):
                        result.append(
                            (
                                await session.execute(
                                    text(
                                        f"SELECT COUNT(*) FROM {table} "
                                        f"WHERE tenant_id=:tenant AND {column}=:id"
                                    ),
                                    {"tenant": tenant, "id": identifier},
                                )
                            ).scalar_one()
                        )
                    clock = (
                        await session.execute(
                            text(
                                "SELECT revision FROM orbit_material_clock WHERE tenant_id=:tenant"
                            ),
                            {"tenant": tenant},
                        )
                    ).scalar_one()
                    return tuple(result), clock

            before_counts, before_state = await counts(), await state(identifier)
            trigger = "orbit_it_config_source_" + uuid4().hex[:12]
            try:
                with admin.cursor() as cursor:
                    cursor.execute(f"""CREATE TRIGGER {trigger}
                    BEFORE INSERT ON orbit_material_audit FOR EACH ROW BEGIN
                    IF NEW.resource_id='{identifier}' AND NEW.action='MATERIAL_PROCESSING' THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='source state audit'; END IF; END""")
                admin.commit()
                try:
                    await worker.record_scan(claim, actual, profile=profile)
                except DBAPIError as error:
                    assert error.orig.args[0] == 1644
                else:
                    raise AssertionError("状态审计失败必须回滚配置来源/收据/证明/事件")
                assert await counts() == before_counts and await state(identifier) == before_state
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")
                admin.commit()
            original_provider = bound_scanner.values_provider

            def forbidden_provider():
                raise AssertionError("登记或媒体完成事务内不得读取私有配置")

            bound_scanner.values_provider = forbidden_provider
            try:
                advanced, scan_state = await worker.record_scan(claim, actual, profile=profile)
            finally:
                bound_scanner.values_provider = original_provider
            assert scan_state == "PROCESSING" and advanced is not None
            committed = await counts()
            assert committed[0] == (1, 1, 2, 2)
            assert await worker.record_scan(claim, actual, profile=profile) == (None, "STALE")
            assert await counts() == committed
            processed = await asyncio.to_thread(
                process_material, objects, tenant, claim["object_upload_id"], claim["mime"]
            )
            bound_scanner.values_provider = forbidden_provider
            try:
                assert await worker.finish(advanced, "READY", None, processed) == (True, "READY")
            finally:
                bound_scanner.values_provider = original_provider
            assert (await state(identifier))[0] == ("READY", 1)
            cases.append(MATERIAL_SCANNER_CONFIGURATION_CASES[9])
        finally:
            await engine.dispose()

    asyncio.run(run())
    return {
        "configuration_cases": len(MATERIAL_SCANNER_CONFIGURATION_CASES),
        "registry_scope": "explicit_fixture",
        "proof_source": "tenant_configuration_full_revision",
        "production_launcher_verified": False,
    }
