"""034配置权限/真实异租户/注册代际负例；不重启或接管引擎，不提供HTTP测试端点。"""

import asyncio
import hashlib
import json
import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fixture_login import fixture_login
from PIL import Image
from sqlalchemy import URL, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES = [
    "pythonScannerConfigurationTeamAdminCannotUseGrantedIntegrationAction",
    "pythonScannerConfigurationSuperAdminRequiresCurrentActionAndSameTokenRevocation",
    "pythonScannerConfigurationForeignSuperAdminCannotReadOrTargetOtherTenant",
    "pythonScannerConfigurationForeignTenantWithoutConfigurationWorkerFailsClosed",
    "pythonScannerConfigurationDisabledTenantSelectionDoesNotReviveFailedJob",
    "pythonScannerConfigurationEmptyServerRegistryNeverProducesCleanProof",
    "pythonScannerConfigurationWithdrawAfterRealScanRejectsOldSelection",
    "pythonScannerConfigurationRepublishAfterRealScanRejectsOldRegistryGeneration",
    "pythonScannerConfigurationProfileAToBToAReturnCannotReuseOldRevision",
    "pythonScannerConfigurationRealForeignConfigurationIdFailsCompositeTenantForeignKey",
    "pythonScannerConfigurationDisabledBusinessIdentityIsRejectedWithExistingToken",
    "pythonScannerConfigurationHistoricalProofSourceRemainsUnchangedAfterConfigurationUpdates",
]


def validate_scope_fixture(admin, database, fixture):
    if (
        not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
        or admin.host not in {"127.0.0.1", "localhost"}
        or admin.port != 13306
        or not isinstance(fixture, dict)
        or len(fixture.get("users", [])) < 4
        or not fixture.get("actor_headers")
        or not fixture.get("manager_headers")
    ):
        raise ValueError("扫描配置scope专项仅允许主线本机UUID库与真实USER夹具")


def assert_disabled_identity_response(response):
    """原登录身份校验先拒绝停用scope；与仍有效身份的功能动作403严格区分。"""
    try:
        body = response.json()
    except ValueError:
        body = None
    code = body.get("code") if isinstance(body, dict) else None
    diagnostic = (response.status_code, code)
    assert diagnostic == (401, "SESSION_REQUIRED"), diagnostic
    # 只允许认证错误三字段，不能将实际配置、候选或原异常装进错误体。
    assert set(body) == {"code", "message", "request_id"}, diagnostic


def run_material_scanner_configuration_scope_checks(
    client, admin, headers, user_fixture, password, cache, database, object_root, cases, *, registry
):
    validate_scope_fixture(admin, database, user_fixture)
    from orbit_api.authorization import require_business_access
    from orbit_api.material_antivirus_runtime import PROFILE_KEY, ProcessBoundMaterialScanner
    from orbit_api.material_contract import CompletedPart
    from orbit_api.material_job_policy import actor_auth_version, material_job_scope
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_scanner_registry import MaterialScannerRegistry
    from orbit_api.material_scanner_selection import ConfiguredMaterialWorker

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
        cursor.execute(
            "SELECT id,revision,settings_json FROM orbit_system_configuration "
            "WHERE tenant_id=%s AND section='MATERIAL_SCANNER'",
            (tenant,),
        )
        configuration = cursor.fetchone()
        assert configuration is not None
        config_id = configuration[0]
        settings = (
            json.loads(configuration[2]) if isinstance(configuration[2], str) else configuration[2]
        )
        original = registry.resolve(settings["profileId"])
        cursor.execute(
            "SELECT s.tenant_id,b.id,b.team_id FROM orbit_user_scope s "
            "JOIN orbit_business_user b ON b.user_id=s.user_id AND b.tenant_id=s.tenant_id "
            "WHERE s.user_id=980100"
        )
        foreign_tenant, foreign_owner, foreign_team = cursor.fetchone()
        assert foreign_tenant != tenant
        cursor.execute(
            "SELECT data_role FROM orbit_user_scope WHERE user_id=%s",
            (user_fixture["users"][1]["native"],),
        )
        old_actor_data_role = cursor.fetchone()[0]
        cursor.execute(
            "SELECT u.status,b.invited,s.data_role FROM sys_user u "
            "JOIN orbit_user_scope s ON s.user_id=u.user_id JOIN orbit_business_user b "
            "ON b.user_id=u.user_id AND b.tenant_id=s.tenant_id WHERE u.user_id=980100"
        )
        foreign_original = cursor.fetchone()
        cursor.execute(
            "SELECT id,native_role_id FROM orbit_business_role WHERE tenant_id=%s",
            (foreign_tenant,),
        )
        foreign_role, foreign_native_role = cursor.fetchone()
        cursor.execute("SELECT menu_id FROM sys_role_menu WHERE role_id=%s", (foreign_native_role,))
        foreign_native_menus = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            "SELECT menu_code FROM orbit_business_role_menu WHERE tenant_id=%s AND role_id=%s",
            (foreign_tenant, foreign_role),
        )
        foreign_business_menus = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            "SELECT permission_code FROM orbit_business_role_action "
            "WHERE tenant_id=%s AND role_id=%s",
            (foreign_tenant, foreign_role),
        )
        foreign_actions = [row[0] for row in cursor.fetchall()]
    admin.commit()
    candidates = "/api/v1/system-configurations/material-scanner-profiles"
    base = "/api/v1/system-configurations"
    manager, actor = user_fixture["users"][:2]
    actor_headers = user_fixture["actor_headers"]
    manager_headers = user_fixture["manager_headers"]
    role_caps = client.get("/api/v1/roles/capabilities", headers=headers)
    assert role_caps.status_code == 200
    created_role = client.post(
        "/api/v1/roles",
        headers=headers
        | {"X-CSRF-Token": role_caps.json()["csrf_token"], "Idempotency-Key": str(uuid4())},
        json={
            "name": "扫描配置范围" + uuid4().hex[:8],
            "menu_codes": ["system"],
            "permission_codes": ["system.read", "system.integrations.manage"],
        },
    )
    assert created_role.status_code == 201
    role_id = created_role.json()["id"]
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role_id),
        )
        native_role = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
            (manager["native"], native_role),
        )
    admin.commit()
    try:
        assert client.get(candidates, headers=manager_headers).status_code == 403
        cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[0])
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=%s",
                (actor["native"],),
            )
        admin.commit()
        assert client.get(candidates, headers=actor_headers).status_code == 403
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (actor["native"], native_role),
            )
        admin.commit()
        assert client.get(candidates, headers=actor_headers).status_code == 200
        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM orbit_business_role_action WHERE tenant_id=%s AND role_id=%s "
                "AND permission_code='system.integrations.manage'",
                (tenant, role_id),
            )
        admin.commit()
        assert client.get(candidates, headers=actor_headers).status_code == 403
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) "
                "VALUES(%s,%s,'system.integrations.manage')",
                (tenant, role_id),
            )
            # 仅激活USER夹具已存在的异租户身份与角色，不另造人员或借默认租户角色。
            cursor.execute("UPDATE sys_user SET status='0' WHERE user_id=980100")
            cursor.execute("UPDATE orbit_business_user SET invited=0 WHERE user_id=980100")
            cursor.execute(
                "UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=980100"
            )
            cursor.execute(
                "SELECT id,native_role_id FROM orbit_business_role WHERE tenant_id=%s",
                (foreign_tenant,),
            )
            foreign_role, foreign_native_role = cursor.fetchone()
            for menu in (31000, 31080, 31081, 31090, 31050, 31051, 31052):
                cursor.execute(
                    "INSERT IGNORE INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)",
                    (foreign_native_role, menu),
                )
            for menu in ("system", "assets"):
                cursor.execute(
                    "INSERT IGNORE INTO orbit_business_role_menu(tenant_id,role_id,menu_code) "
                    "VALUES(%s,%s,%s)",
                    (foreign_tenant, foreign_role, menu),
                )
            for permission in (
                "system.read",
                "system.integrations.manage",
                "assets.read",
                "assets.upload",
            ):
                cursor.execute(
                    "INSERT IGNORE INTO orbit_business_role_action"
                    "(tenant_id,role_id,permission_code) VALUES(%s,%s,%s)",
                    (foreign_tenant, foreign_role, permission),
                )
            cursor.execute(
                "INSERT IGNORE INTO orbit_material_clock(tenant_id) VALUES(%s)", (foreign_tenant,)
            )
        admin.commit()
        assert client.get(candidates, headers=actor_headers).status_code == 200
        cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[1])
        login = fixture_login(
            client, cache, {"username": "foreign_user_directory", "password": password}
        )
        assert login.status_code == 200 and login.json().get("token")
        foreign_headers = {"Authorization": "Bearer " + login.json()["token"]}
        assert client.get(candidates, headers=foreign_headers).status_code == 200
        assert client.get(base + "/" + config_id, headers=foreign_headers).status_code == 404
        assert client.get(base, headers=foreign_headers).json() == []
        assert (
            client.get(
                candidates, headers=foreign_headers | {"X-Target-Tenant": tenant}
            ).status_code
            == 403
        )
        cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[2])

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
            objects = LocalMaterialObjects(Path(object_root))
            processor_calls = []

            def forbidden_processor(*args):
                processor_calls.append(True)
                raise AssertionError("负例不得进入媒体处理器")

            async def fixture(*, foreign=False):
                actor_id, current_tenant, current_owner, current_team = (
                    (980100, foreign_tenant, foreign_owner, foreign_team)
                    if foreign
                    else (1, tenant, owner, team)
                )
                identifier, upload = str(uuid4()), str(uuid4())
                output = BytesIO()
                Image.new("RGB", (16, 16), "blue").save(output, "PNG")
                content = output.getvalue()
                digest = hashlib.sha256(content).hexdigest()
                objects.put_part(current_tenant, upload, 1, content, len(content))
                objects.assemble(
                    current_tenant,
                    upload,
                    [CompletedPart(part_number=1, etag=digest)],
                    len(content),
                    digest,
                    "image/png",
                )
                async with sessions() as session, session.begin():
                    context = await require_business_access(
                        session, actor_id, "assets", "assets.upload", acting_subject=False
                    )
                    version = await actor_auth_version(session, actor_id)
                    item = {
                        "id": identifier,
                        "owner_user_id": current_owner,
                        "owner_team_id": current_team,
                        "sha256": digest,
                        "mime": "image/png",
                    }
                    await session.execute(
                        text("""INSERT INTO orbit_material_asset
                      (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,sha256,byte_size,object_upload_id)
                      VALUES(:tenant,:id,:owner,:team,'扫描scope安全PNG',:category,'IMAGE','image/png','SCANNING',:sha,:size,:upload)"""),
                        {
                            "tenant": current_tenant,
                            "id": identifier,
                            "owner": current_owner,
                            "team": current_team,
                            "category": "00000000-0000-4000-8000-000000000001",
                            "sha": digest,
                            "size": len(content),
                            "upload": upload,
                        },
                    )
                    await session.execute(
                        text("""INSERT INTO orbit_material_job
                      (tenant_id,asset_id,actor_id,actor_auth_version,scope_digest,state,created_at)
                      VALUES(:tenant,:id,:actor,:version,:scope,'PENDING','1700-01-01')"""),
                        {
                            "tenant": current_tenant,
                            "id": identifier,
                            "actor": actor_id,
                            "version": version,
                            "scope": material_job_scope(context, item),
                        },
                    )
                return current_tenant, identifier

            async def snapshot(current_tenant, identifier):
                async with sessions() as session:
                    state = (
                        await session.execute(
                            text(
                                "SELECT state,preview_ready FROM orbit_material_asset "
                                "WHERE tenant_id=:tenant AND id=:id"
                            ),
                            {"tenant": current_tenant, "id": identifier},
                        )
                    ).one()
                    receipts = (
                        (
                            await session.execute(
                                text(
                                    "SELECT result FROM orbit_material_scan_receipt "
                                    "WHERE tenant_id=:tenant AND asset_id=:id"
                                ),
                                {"tenant": current_tenant, "id": identifier},
                            )
                        )
                        .scalars()
                        .all()
                    )
                    proofs = (
                        await session.execute(
                            text(
                                "SELECT COUNT(*) FROM orbit_material_scan_runtime_proof "
                                "WHERE tenant_id=:tenant AND asset_id=:id"
                            ),
                            {"tenant": current_tenant, "id": identifier},
                        )
                    ).scalar_one()
                    return tuple(state), receipts, proofs

            def worker(selected_registry=None, cls=ConfiguredMaterialWorker):
                return cls(
                    sessions,
                    objects,
                    registry=selected_registry if selected_registry is not None else registry,
                    processor=forbidden_processor,
                )

            async def must_fail(current_worker, *, foreign=False):
                current_tenant, identifier = await fixture(foreign=foreign)
                assert await current_worker.run_once(1) == [
                    {"asset_id": identifier, "state": "PROCESSING_FAILED"}
                ]
                assert await snapshot(current_tenant, identifier) == (
                    ("PROCESSING_FAILED", 0),
                    ["UNVERIFIED"],
                    0,
                )
                assert processor_calls == []
                return current_tenant, identifier

            async def update_configuration(*, enabled=None, profile_id=None):
                async with sessions() as session, session.begin():
                    fields, values = (
                        [
                            "revision=revision+1",
                            "verification_status='UNTESTED'",
                            "verified_at=NULL",
                        ],
                        {"tenant": tenant, "id": config_id},
                    )
                    if enabled is not None:
                        fields.append("enabled=:enabled")
                        values["enabled"] = enabled
                    if profile_id is not None:
                        fields.append("settings_json=:settings")
                        values["settings"] = json.dumps({"profileId": profile_id})
                    await session.execute(
                        text(
                            "UPDATE orbit_system_configuration SET "
                            + ",".join(fields)
                            + " WHERE tenant_id=:tenant AND id=:id"
                        ),
                        values,
                    )

            try:
                # 真实另一租户，没有扫描配置且有合法assets.upload身份，不能借用默认租户选择。
                await must_fail(worker(), foreign=True)
                cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[3])
                await update_configuration(enabled=False)
                failed_tenant, failed_id = await must_fail(worker())
                await update_configuration(enabled=True)
                assert await worker().run_once(1) == []
                assert (await snapshot(failed_tenant, failed_id))[0] == ("PROCESSING_FAILED", 0)
                cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[4])
                await must_fail(worker(MaterialScannerRegistry()))
                cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[5])

                class WithdrawBeforeRecord(ConfiguredMaterialWorker):
                    async def record_runtime_scan(self, claim, result, profile):
                        assert result.receipt.result == "CLEAN" and result.proof is not None
                        registry.withdraw(profile.profile_id)
                        return await super().record_runtime_scan(claim, result, profile)

                await must_fail(worker(cls=WithdrawBeforeRecord))
                registry.publish(original.scanner, original.label)
                cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[6])

                class RepublishBeforeRecord(ConfiguredMaterialWorker):
                    async def record_runtime_scan(self, claim, result, profile):
                        assert result.receipt.result == "CLEAN" and result.proof is not None
                        registry.publish(original.scanner, original.label)
                        return await super().record_runtime_scan(claim, result, profile)

                await must_fail(worker(cls=RepublishBeforeRecord))
                cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[7])
                # 第二别名只指向同一个实际固定引擎，明确不是另一个daemon/生产启动器证明。
                private = original.scanner.values_provider()
                profiles = private[PROFILE_KEY]
                profiles = json.loads(profiles) if isinstance(profiles, str) else profiles
                alias_id = "scope-secondary"
                alias_values = {
                    PROFILE_KEY: json.dumps({alias_id: profiles[original.profile.profile_id]})
                }
                alias = ProcessBoundMaterialScanner(alias_id, values_provider=lambda: alias_values)
                registry.publish(alias, "隔离scope第二受控候选")

                class ReturnToOriginal(ConfiguredMaterialWorker):
                    async def record_runtime_scan(self, claim, result, profile):
                        assert result.receipt.result == "CLEAN" and result.proof is not None
                        await update_configuration(profile_id=alias_id)
                        await update_configuration(profile_id=original.profile.profile_id)
                        return await super().record_runtime_scan(claim, result, profile)

                await must_fail(worker(cls=ReturnToOriginal))
                registry.withdraw(alias_id)
                cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[8])
                # 创建另一真实租户的正式配置行，再直接验证复合tenant/config FK，非随机不存在ID。
                foreign_config = str(uuid4())
                async with sessions() as session, session.begin():
                    await session.execute(
                        text("""INSERT INTO orbit_system_configuration
                    (id,tenant_id,section,name,enabled,revision,settings_json,secrets_json)
                    VALUES(:id,:tenant,'MATERIAL_SCANNER','异租户实际配置',1,1,:settings,'{}')"""),
                        {
                            "id": foreign_config,
                            "tenant": foreign_tenant,
                            "settings": json.dumps(settings),
                        },
                    )
                    own_proof = (
                        (
                            await session.execute(
                                text(
                                    """SELECT p.asset_id,p.receipt_id,p.configuration_id,
                                p.configuration_revision FROM orbit_material_scan_runtime_proof p
                                JOIN orbit_material_asset a ON a.tenant_id=p.tenant_id
                                AND a.id=p.asset_id WHERE p.tenant_id=:tenant
                                AND p.configuration_id=:id AND a.state='READY' LIMIT 1"""
                                ),
                                {"tenant": tenant, "id": config_id},
                            )
                        )
                        .mappings()
                        .one()
                    )
                try:
                    async with sessions() as session, session.begin():
                        await session.execute(
                            text(
                                "UPDATE orbit_material_scan_runtime_proof "
                                "SET configuration_id=:foreign WHERE tenant_id=:tenant "
                                "AND asset_id=:asset AND receipt_id=:receipt"
                            ),
                            {
                                "foreign": foreign_config,
                                "tenant": tenant,
                                "asset": own_proof["asset_id"],
                                "receipt": own_proof["receipt_id"],
                            },
                        )
                except DBAPIError as error:
                    assert error.orig.args[0] == 1452
                else:
                    raise AssertionError("真实异租户配置不得绑定本租户扫描证明")
                cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[9])
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE orbit_user_scope SET enabled=0 WHERE user_id=%s", (actor["native"],)
                    )
                admin.commit()
                try:
                    assert_disabled_identity_response(client.get(candidates, headers=actor_headers))
                finally:
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "UPDATE orbit_user_scope SET enabled=1 WHERE user_id=%s",
                            (actor["native"],),
                        )
                    admin.commit()
                assert client.get(candidates, headers=actor_headers).status_code == 200
                cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[10])
                await update_configuration(enabled=False)
                historical = client.get(
                    "/api/v1/assets/" + own_proof["asset_id"] + "/security", headers=headers
                )
                assert historical.status_code == 200 and historical.json()["scan_status"] == "CLEAN"
                await update_configuration(enabled=True)
                async with sessions() as session:
                    final = (
                        await session.execute(
                            text(
                                "SELECT configuration_id,configuration_revision "
                                "FROM orbit_material_scan_runtime_proof "
                                "WHERE tenant_id=:tenant "
                                "AND asset_id=:asset AND receipt_id=:receipt"
                            ),
                            {
                                "tenant": tenant,
                                "asset": own_proof["asset_id"],
                                "receipt": own_proof["receipt_id"],
                            },
                        )
                    ).one()
                    assert tuple(final) == (
                        own_proof["configuration_id"],
                        own_proof["configuration_revision"],
                    )
                assert processor_calls == []
                cases.append(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES[11])
            finally:
                registry.withdraw("scope-secondary")
                registry.publish(original.scanner, original.label)
                await update_configuration(enabled=True, profile_id=original.profile.profile_id)
                await engine.dispose()

        asyncio.run(run())
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sys_user_role WHERE role_id=%s AND user_id IN(%s,%s)",
                (native_role, manager["native"], actor["native"]),
            )
            cursor.execute(
                "UPDATE orbit_user_scope SET data_role=%s,enabled=1 WHERE user_id=%s",
                (old_actor_data_role, actor["native"]),
            )
            cursor.execute(
                "UPDATE sys_user SET status=%s WHERE user_id=980100", (foreign_original[0],)
            )
            cursor.execute(
                "UPDATE orbit_business_user SET invited=%s WHERE user_id=980100",
                (foreign_original[1],),
            )
            cursor.execute(
                "UPDATE orbit_user_scope SET data_role=%s WHERE user_id=980100",
                (foreign_original[2],),
            )
            cursor.execute("DELETE FROM sys_role_menu WHERE role_id=%s", (foreign_native_role,))
            for menu in foreign_native_menus:
                cursor.execute(
                    "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)",
                    (foreign_native_role, menu),
                )
            cursor.execute(
                "DELETE FROM orbit_business_role_menu WHERE tenant_id=%s AND role_id=%s",
                (foreign_tenant, foreign_role),
            )
            for menu in foreign_business_menus:
                cursor.execute(
                    "INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) "
                    "VALUES(%s,%s,%s)",
                    (foreign_tenant, foreign_role, menu),
                )
            cursor.execute(
                "DELETE FROM orbit_business_role_action WHERE tenant_id=%s AND role_id=%s",
                (foreign_tenant, foreign_role),
            )
            for permission in foreign_actions:
                cursor.execute(
                    "INSERT INTO orbit_business_role_action"
                    "(tenant_id,role_id,permission_code) VALUES(%s,%s,%s)",
                    (foreign_tenant, foreign_role, permission),
                )
        admin.commit()
    return {
        "scope_cases": len(MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES),
        "registry_transition": "same_fixed_engine_memory_publication_only",
        "production_daemon_replacement_verified": False,
    }
