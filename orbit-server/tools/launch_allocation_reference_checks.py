"""真实C扫描/权限/引用桥专项；平台能力仅隔离SQL夹具，主线串行执行。"""

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

LAUNCH_ALLOCATION_REFERENCE_CASES = [
    "pythonAllocationReferenceBridgeActualConfiguredPngHas034CleanRuntimeProof",
    "pythonAllocationReferenceBridgeSafeMetadataBindsRealMediaVersionNotPlatformProof",
    "pythonAllocationReferenceBridgeCurrentUserIntersectionAndActionRevocationReject",
    "pythonAllocationReferenceBridgeRealReceiptAssetMismatchCannotBecomeClean",
    "pythonAllocationReferenceBridgeActualRuntimeSourceBeforeHeadPublishesReferences",
    "pythonAllocationReferenceBridgeActual1644ReplacementRollsBackAllReferencesAndItems",
    "pythonAllocationReferenceBridgeReplacementReleasesExactOldAllocationAndPreservesHistory",
    "pythonAllocationReferenceBridgeReplayAndStaleClaimCannotRepeatReferenceAudit",
]


def validate_target(admin, database, object_root):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("素材桥专项只允许本机13306 UUID数据库")
    root = Path(object_root)
    base = Path(__file__).resolve().parents[1] / ".runtime/integration-objects"
    if (
        not root.is_absolute()
        or root.name != "materials"
        or not re.fullmatch(r"run-[A-Za-z0-9_-]{8,64}", root.parent.name)
        or root.resolve(strict=True).parent.parent != base.resolve(strict=True)
    ):
        raise ValueError("素材桥必须复用主线本轮对象根")
    for entry in (root, *root.parents):
        info = entry.lstat()
        if entry.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("素材桥对象根拒绝链接或reparse")
    return root


def run_launch_allocation_reference_checks(
    client, admin, headers, database, cases, *, object_root, registry, user_fixture
):
    root = validate_target(admin, database, object_root)
    from orbit_api.authorization import require_business_access
    from orbit_api.directory_tokens import canonical
    from orbit_api.errors import OrbitError
    from orbit_api.launch_access import digest
    from orbit_api.launch_allocation import build_compatibility_evidence
    from orbit_api.launch_allocation_reference_provider import (
        AllocationReferenceAuthority,
        LockedAllocationAuthority,
        ReferenceBackedAllocationProvider,
    )
    from orbit_api.launch_allocation_runtime import AllocationRuntime, solve_packet
    from orbit_api.launch_contract import parse_plan
    from orbit_api.launch_expansion import ad_slots
    from orbit_api.material_contract import CompletedPart
    from orbit_api.material_job_policy import actor_auth_version, material_job_scope
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_scanner_selection import ConfiguredMaterialWorker
    from orbit_api.material_security import clean_scan_ids

    def checked(response, status):
        assert response.status_code == status, {"actual": response.status_code, "expected": status}
        return response.json()

    users = user_fixture["users"]
    owner, peer = users[1], users[3]
    assert owner["team"] == peer["team"] and owner["id"] != peer["id"]
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE user_id=1")
        tenant = cursor.fetchone()[0]
    admin.commit()
    role_caps = checked(client.get("/api/v1/roles/capabilities", headers=headers), 200)
    granted = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": role_caps["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "素材桥权限fixture" + uuid4().hex[:8],
                "menu_codes": ["assets", "launch"],
                "permission_codes": ["assets.read", "assets.upload", "launch.read", "launch.edit"],
            },
        ),
        201,
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, granted["id"]),
        )
        native_role = cursor.fetchone()[0]
        for user in (owner, peer):
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (user["native"], native_role),
            )
    admin.commit()
    candidates = checked(
        client.get("/api/v1/system-configurations/material-scanner-profiles", headers=headers), 200
    )
    profile_id = next(row["id"] for row in candidates["items"] if row["availability"] == "READY")
    assert registry.resolve(profile_id).profile.profile_id == profile_id
    asset_caps = checked(client.get("/api/v1/assets/capabilities", headers=headers), 200)
    config_headers = headers | {
        "X-CSRF-Token": asset_caps["csrf_token"],
        "Idempotency-Key": str(uuid4()),
    }
    configuration_value = {
        "section": "MATERIAL_SCANNER",
        "name": "素材桥真实扫描fixture",
        "enabled": True,
        "settings": {"profileId": profile_id},
        "secrets": {},
        "reason": "真实CLEAN引用链专项",
    }
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT id,revision FROM orbit_system_configuration "
            "WHERE tenant_id=%s AND section='MATERIAL_SCANNER' LIMIT 2",
            (tenant,),
        )
        configured = cursor.fetchall()
    admin.commit()
    assert len(configured) <= 1
    if configured:
        config_id, config_revision = configured[0]
        config = checked(
            client.put(
                "/api/v1/system-configurations/" + config_id,
                headers=config_headers | {"If-Match": f'"{config_revision}"'},
                json=configuration_value,
            ),
            200,
        )
    else:
        config = checked(
            client.post(
                "/api/v1/system-configurations", headers=config_headers, json=configuration_value
            ),
            200,
        )
    objects = LocalMaterialObjects(root)
    trigger = "it_bridge_" + uuid4().hex[:16]

    class IsolatedSqlAuthority(AllocationReferenceAuthority):
        """只验真实C/队列/引用，非真实Meta账户或身份能力来源。"""

        async def lock_sources(self, session, current, plan, request):
            url = session.bind.url
            if url.host != "127.0.0.1" or url.port != 13306:
                raise ValueError("隔离能力不可用于业务数据源")
            actual = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
            if actual != database or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", actual):
                raise ValueError("隔离能力只允许本轮UUID库")
            return LockedAllocationAuthority(
                session.sync_session.get_transaction(),
                current,
                digest(plan),
                digest(["ISOLATED-SQL", current.actor_id, current.subject_id]),
                "ISOLATED-SQL-CAPABILITY-NOT-META",
                "a" * 64,
            )

        def compatibility(self, locked, plan, request, materials):
            return build_compatibility_evidence(
                ad_slots(plan),
                plan["asset_ids"],
                capability_version=locked.capability_version,
                source_hash=locked.source_hash,
                verified=True,
                complete=True,
                evaluate=lambda _slot, _asset: True,
                material_revisions={key: row["revision"] for key, row in materials.items()},
            )

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    async def run():
        engine = create_async_engine(
            URL.create(
                "mysql+asyncmy",
                username=decoded(admin.user),
                password=decoded(admin.password),
                host="127.0.0.1",
                port=13306,
                database=database,
            ),
            echo=False,
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        provider = ReferenceBackedAllocationProvider(IsolatedSqlAuthority())
        runtime = AllocationRuntime(provider)

        async def call(method, *args):
            async with sessions() as session, session.begin():
                return await method(session, *args)

        async def execute(sql, params):
            async with sessions() as session, session.begin():
                return await session.execute(text(sql), params)

        async def context(session, actor=owner["native"]):
            return await require_business_access(session, actor, "launch", "launch.edit")

        assets = []

        async def png(index):
            identifier, upload = str(uuid4()), str(uuid4())
            data = BytesIO()
            Image.new("RGB", (24 + index, 24), (20 + index, 50, 90)).save(data, "PNG")
            content = data.getvalue()
            sha = hashlib.sha256(content).hexdigest()
            objects.put_part(tenant, upload, 1, content, len(content))
            objects.assemble(
                tenant,
                upload,
                [CompletedPart(part_number=1, etag=sha)],
                len(content),
                sha,
                "image/png",
            )
            async with sessions() as session, session.begin():
                current = await require_business_access(
                    session, owner["native"], "assets", "assets.upload"
                )
                auth_version = await actor_auth_version(session, owner["native"])
                material = {
                    "id": identifier,
                    "owner_user_id": owner["id"],
                    "owner_team_id": owner["team"],
                    "sha256": sha,
                    "mime": "image/png",
                }
                params = {
                    "tenant": tenant,
                    "id": identifier,
                    "owner": owner["id"],
                    "team": owner["team"],
                    "sha": sha,
                    "size": len(content),
                    "upload": upload,
                    "category": asset_caps["default_category_id"],
                }
                await session.execute(
                    text(
                        "INSERT INTO orbit_material_asset(tenant_id,id,owner_user_id,"
                        "owner_team_id,name,category_id,kind,mime,state,sha256,"
                        "byte_size,object_upload_id) "
                        "VALUES(:tenant,:id,:owner,:team,'真实PNG素材桥fixture',:category,'IMAGE','image/png',"
                        "'SCANNING',:sha,:size,:upload)"
                    ),
                    params,
                )
                await session.execute(
                    text(
                        "INSERT INTO orbit_material_job(tenant_id,asset_id,actor_id,"
                        "actor_auth_version,scope_digest,state,created_at) "
                        "VALUES(:tenant,:id,:actor,:version,:scope,'PENDING','1800-01-01')"
                    ),
                    params
                    | {
                        "actor": owner["native"],
                        "version": auth_version,
                        "scope": material_job_scope(current, material),
                    },
                )
            return identifier

        async def plan_fixture(pool, *, identifier=None, revision=1, head=3):
            identifier = identifier or str(uuid4())
            value = parse_plan(
                canonical(
                    {
                        "name": "真实引用桥非Metafixture",
                        "ownership": {"owner_user_id": owner["id"], "owner_team_id": owner["team"]},
                        "account_ids": [account_id],
                        "asset_ids": pool,
                        "channel_id": None,
                        "identity_bindings": [],
                        "allow_repeat": True,
                        "activate_after_create": False,
                        "execution_mode": "META_API",
                        "campaigns": [
                            {
                                "local_id": campaign_id,
                                "copies": 1,
                                "adsets": [
                                    {
                                        "local_id": adset_id,
                                        "copies": 1,
                                        "ads": [{"local_id": ad_id, "copies": 2}],
                                    }
                                ],
                            }
                        ],
                    }
                ).encode()
            )
            payload = canonical(value)
            params = {
                "tenant": tenant,
                "id": identifier,
                "owner": owner["id"],
                "team": owner["team"],
                "head": head,
                "revision": revision,
                "payload": payload,
                "hash": digest(value),
                "bytes": len(payload.encode()),
                "actor": owner["native"],
            }
            async with sessions() as session, session.begin():
                if revision == 1:
                    await session.execute(
                        text(
                            "INSERT INTO orbit_launch_plan(tenant_id,id,owner_user_id,"
                            "owner_team_id,channel_id,name,state,revision,payload_json,payload_hash,payload_bytes,"
                            "account_count,asset_count,created_at,updated_at) "
                            "VALUES(:tenant,:id,:owner,:team,NULL,"
                            "'真实引用桥非Metafixture','VALIDATED',:head,:payload,:hash,:bytes,1,2,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"
                        ),
                        params,
                    )
                else:
                    await session.execute(
                        text(
                            "UPDATE orbit_launch_plan SET revision=:head,state='DRAFT',"
                            "payload_json=:payload,payload_hash=:hash,payload_bytes=:bytes,"
                            "updated_at=UTC_TIMESTAMP(3) "
                            "WHERE tenant_id=:tenant AND id=:id"
                        ),
                        params,
                    )
                await session.execute(
                    text(
                        "INSERT INTO orbit_launch_plan_version(tenant_id,plan_id,revision,"
                        "payload_json,payload_hash,dependency_json,created_at,created_by) "
                        "VALUES(:tenant,:id,:revision,:payload,:hash,'{}',UTC_TIMESTAMP(3),:actor)"
                    ),
                    params,
                )
            return identifier, value

        async def rejected(operation, code):
            try:
                await operation()
            except OrbitError as error:
                assert error.code == code, {"code": error.code, "expected": code}
            else:
                raise AssertionError("真实来源或权限失败不得成功")

        async def snapshot(plan_id):
            async with sessions() as session, session.begin():
                params = {"tenant": tenant, "plan": plan_id}
                allocation = (
                    await session.execute(
                        text(
                            "SELECT id,state,active,input_hash FROM orbit_launch_allocation "
                            "WHERE tenant_id=:tenant AND plan_id=:plan ORDER BY id LIMIT 4"
                        ),
                        params,
                    )
                ).all()
                assert len(allocation) <= 2
                refs = (
                    await session.execute(
                        text(
                            "SELECT r.asset_id,r.kind,r.resource_id,r.active FROM "
                            "orbit_material_reference r "
                            "WHERE r.tenant_id=:tenant AND (r.resource_id IN (SELECT id FROM "
                            "orbit_launch_allocation "
                            "WHERE tenant_id=:tenant AND plan_id=:plan) OR "
                            "r.resource_id=:historical) "
                            "ORDER BY r.asset_id,r.kind,r.resource_id LIMIT 10"
                        ),
                        params | {"historical": historical},
                    )
                ).all()
                assert len(refs) <= 5
                counts = []
                for table in (
                    "orbit_material_audit",
                    "orbit_material_outbox",
                    "orbit_launch_event",
                    "orbit_launch_outbox",
                    "orbit_launch_allocation_item",
                    "orbit_launch_allocation_guard",
                ):
                    counts.append(
                        (
                            await session.execute(
                                text("SELECT COUNT(*) FROM " + table + " WHERE tenant_id=:tenant"),
                                params,
                            )
                        ).scalar_one()
                    )
                head = (
                    await session.execute(
                        text(
                            "SELECT revision,state FROM orbit_launch_plan WHERE "
                            "tenant_id=:tenant AND id=:plan"
                        ),
                        params,
                    )
                ).one()
                material_clock = (
                    await session.execute(
                        text("SELECT revision FROM orbit_material_clock WHERE tenant_id=:tenant"),
                        params,
                    )
                ).scalar_one()
                launch_clock = (
                    await session.execute(
                        text(
                            "SELECT plan_revision FROM orbit_launch_clock WHERE tenant_id=:tenant"
                        ),
                        params,
                    )
                ).scalar_one()
                return (
                    tuple(allocation),
                    tuple(refs),
                    tuple(counts),
                    tuple(head),
                    material_clock,
                    launch_clock,
                )

        account_id, campaign_id, adset_id, ad_id, historical = [str(uuid4()) for _ in range(5)]
        try:
            for index in range(3):
                assets.append(await png(index))
            completed = await ConfiguredMaterialWorker(
                sessions, objects, registry=registry
            ).run_once(3)
            assert {row["asset_id"] for row in completed if row["state"] == "READY"} == set(assets)
            async with sessions() as session, session.begin():
                assert await clean_scan_ids(session, tenant, assets) == set(assets)
                proofs = (
                    await session.execute(
                        text(
                            "SELECT "
                            "p.asset_id,s.result,p.configuration_id,p.configuration_revision "
                            "FROM orbit_material_scan_runtime_proof p JOIN "
                            "orbit_material_scan_receipt s "
                            "ON s.tenant_id=p.tenant_id AND s.asset_id=p.asset_id AND "
                            "s.id=p.receipt_id "
                            "WHERE p.tenant_id=:tenant AND p.configuration_id=:config "
                            "AND p.asset_id IN (:asset0,:asset1,:asset2) "
                            "ORDER BY p.asset_id LIMIT 4"
                        ),
                        {
                            "tenant": tenant,
                            "config": config["id"],
                            "asset0": assets[0],
                            "asset1": assets[1],
                            "asset2": assets[2],
                        },
                    )
                ).all()
                selected = [tuple(row) for row in proofs if row[0] in assets]
                assert len(selected) == 3 and all(
                    row[1:] == ("CLEAN", config["id"], config["revision"]) for row in selected
                )
            cases.append(LAUNCH_ALLOCATION_REFERENCE_CASES[0])
            plan_id, plan = await plan_fixture(assets[:2])
            command = {
                "asset_ids": assets[:2],
                "allow_repeat": True,
                "seed": 0,
                "algorithm_version": "allocation-v1",
            }
            async with sessions() as session, session.begin():
                capture = await provider.capture(session, await context(session), plan, command)
                assert set(capture.material_metadata) == set(assets[:2])
                assert all(
                    row["mime"] == "image/png" and row["width_px"] >= 24
                    for row in capture.material_metadata.values()
                )
                assert capture.evidence.capability_version == "ISOLATED-SQL-CAPABILITY-NOT-META"
            cases.append(LAUNCH_ALLOCATION_REFERENCE_CASES[1])

            async def peer_capture():
                async with sessions() as session, session.begin():
                    return await provider.capture(
                        session, await context(session, peer["native"]), plan, command
                    )

            await rejected(peer_capture, "MATERIAL_REFERENCE_UNAVAILABLE")
            with admin.cursor() as cursor:
                cursor.execute("SELECT status FROM sys_menu WHERE menu_id=31051")
                menu_status = cursor.fetchone()[0]
                cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31051")
            admin.commit()
            try:

                async def revoked_capture():
                    async with sessions() as session, session.begin():
                        return await provider.capture(
                            session, await context(session), plan, command
                        )

                await rejected(revoked_capture, "PERMISSION_DENIED")
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE sys_menu SET status=%s WHERE menu_id=31051", (menu_status,)
                    )
                admin.commit()
            cases.append(LAUNCH_ALLOCATION_REFERENCE_CASES[2])

            try:
                async with sessions() as session, session.begin():
                    await session.execute(
                        text(
                            "UPDATE orbit_material_asset SET sha256=:sha WHERE "
                            "tenant_id=:tenant AND id=:id"
                        ),
                        {"tenant": tenant, "id": assets[0], "sha": "f" * 64},
                    )
                    try:
                        await provider.capture(session, await context(session), plan, command)
                    except OrbitError as error:
                        assert error.code == "ANTIVIRUS_UNVERIFIED"
                        raise
                    raise AssertionError("真实收据不符不得通过")
            except OrbitError as error:
                assert error.code == "ANTIVIRUS_UNVERIFIED"
            async with sessions() as session, session.begin():
                assert await clean_scan_ids(session, tenant, assets) == set(assets)
            cases.append(LAUNCH_ALLOCATION_REFERENCE_CASES[3])

            key = str(uuid4())
            first = await call(
                runtime.enqueue, owner["native"], plan_id, command, 3, key, str(uuid4())
            )
            assert first["plan_revision"] == 1 and first["task_id"] is None
            claim = await call(runtime.claim, str(uuid4()))
            assert claim.allocation_id == first["id"]
            _, packet, evidence = await call(runtime.load, claim)
            first_result = await call(
                runtime.publish, claim, solve_packet(packet, evidence), str(uuid4())
            )
            assert first_result["state"] == "SUCCEEDED" and len(first_result["items"]) == 2
            initial = await snapshot(plan_id)
            assert initial[3] == (4, "DRAFT")
            assert {row[0] for row in initial[1] if row[3] == 1} == set(assets[:2])
            cases.append(LAUNCH_ALLOCATION_REFERENCE_CASES[4])

            await execute(
                "INSERT INTO "
                "orbit_material_reference(tenant_id,asset_id,id,kind,resource_id,active) "
                "VALUES(:tenant,:asset,:id,'HISTORICAL_EVIDENCE',:resource,1)",
                {"tenant": tenant, "asset": assets[0], "id": str(uuid4()), "resource": historical},
            )
            _, revised = await plan_fixture(assets[1:], identifier=plan_id, revision=5, head=5)
            next_command = command | {"asset_ids": assets[1:], "seed": 1}
            next_key = str(uuid4())
            second = await call(
                runtime.enqueue, owner["native"], plan_id, next_command, 5, next_key, str(uuid4())
            )
            next_claim = await call(runtime.claim, str(uuid4()))
            assert next_claim.allocation_id == second["id"]
            _, next_packet, next_evidence = await call(runtime.load, next_claim)
            solution = solve_packet(next_packet, next_evidence)
            before = await snapshot(plan_id)
            with admin.cursor() as cursor:
                cursor.execute(
                    f"CREATE TRIGGER {trigger} BEFORE INSERT ON orbit_material_audit FOR EACH "
                    "ROW BEGIN "
                    "IF NEW.action='MATERIAL_REFERENCE_ADDED' THEN SIGNAL SQLSTATE '45000' "
                    "SET MESSAGE_TEXT='ISOLATED_BRIDGE_AUDIT_1644'; END IF; END"
                )
            admin.commit()
            try:
                try:
                    await call(runtime.publish, next_claim, solution, str(uuid4()))
                except DBAPIError as error:
                    assert error.orig.args[0] == 1644
                else:
                    raise AssertionError("引用审计拒绝必须使整个发布回滚")
                assert await snapshot(plan_id) == before
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")
                admin.commit()
            cases.append(LAUNCH_ALLOCATION_REFERENCE_CASES[5])

            replacement = await call(runtime.publish, next_claim, solution, str(uuid4()))
            assert replacement["state"] == "SUCCEEDED" and replacement["plan_revision"] == 5
            after = await snapshot(plan_id)
            old_refs = [row for row in after[1] if row[2] == first["id"]]
            new_refs = [row for row in after[1] if row[2] == second["id"]]
            historical_refs = [row for row in after[1] if row[2] == historical]
            assert len(old_refs) == 2 and all(row[3] == 0 for row in old_refs)
            assert (
                len(new_refs) == 2
                and {row[0] for row in new_refs} == set(assets[1:])
                and all(row[3] == 1 for row in new_refs)
            )
            assert (
                len(historical_refs) == 1
                and historical_refs[0][1] == "HISTORICAL_EVIDENCE"
                and historical_refs[0][3] == 1
            )
            assert after[3] == (5, "DRAFT")
            cases.append(LAUNCH_ALLOCATION_REFERENCE_CASES[6])

            replay = await call(
                runtime.enqueue, owner["native"], plan_id, next_command, 5, next_key, str(uuid4())
            )
            assert replay == replacement
            assert await snapshot(plan_id) == after

            async def stale():
                return await call(runtime.publish, next_claim, solution, str(uuid4()))

            await rejected(stale, "ALLOCATION_CLAIM_LOST")
            assert await snapshot(plan_id) == after
            cases.append(LAUNCH_ALLOCATION_REFERENCE_CASES[7])
            return {
                "case_count": 8,
                "actual_configured_scanned_png": 3,
                "platform_authority": "ISOLATED_SQL_ONLY",
                "real_platform_verified": False,
                "actual_reference_replacement": True,
                "real_scan_receipt_inserted_by_worker": True,
            }
        finally:
            with admin.cursor() as cursor:
                cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            admin.commit()
            await engine.dispose()

    try:
        return asyncio.run(run())
    finally:
        with admin.cursor() as cursor:
            for user in (owner, peer):
                cursor.execute(
                    "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                    (user["native"], native_role),
                )
        admin.commit()
