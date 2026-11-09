"""真实C文件/扫描/范围→原execute引用桥；Meta来源仍为显式隔离协议。"""

import asyncio
import hashlib
import json
from io import BytesIO
from uuid import uuid4

from PIL import Image
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest
from orbit_api.launch_allocation import build_compatibility_evidence, solve_allocation
from orbit_api.launch_execution_contract import prepare_execution
from orbit_api.launch_execution_material_bridge import ExecutionMaterialBridge
from orbit_api.launch_execution_store import (
    ExecutionAuthorityProvider,
    ExecutionEvidence,
    database_now,
)
from orbit_api.launch_expansion import ad_slots
from orbit_api.launch_validation_store import ObservationReference, ValidationInput

if __package__:
    from .launch_allocation_reference_checks import validate_target
    from .launch_execution_fixture import (
        IsolatedExecutionValidationProvider,
        create_protocol_plan,
        profile,
    )
    from .launch_validation_fixture import first, guard
else:
    from launch_allocation_reference_checks import validate_target
    from launch_execution_fixture import (
        IsolatedExecutionValidationProvider,
        create_protocol_plan,
        profile,
    )
    from launch_validation_fixture import first, guard

EXECUTION_MATERIAL_BRIDGE_CASES = [
    "pythonExecutionMaterialActualConfiguredPng030034Proof",
    "pythonExecutionMaterialHttp202ActualCReferencesAndSourceAnchor",
    "pythonExecutionMaterialOwnerScopeIntersectionDenied",
    "pythonExecutionMaterialOwnerReadRevocationDenied",
    "pythonExecutionMaterialActualRuntimeProofMismatchDenied",
    "pythonExecutionMaterialActual1644WholeAcceptanceRollback",
]


class IsolatedMaterialExecutionProvider(ExecutionAuthorityProvider):
    """只C证据真实；账户/Meta能力/身份/归因均非生产Authority，禁止普通数据库。"""

    kind = "ISOLATED_TEST"

    def __init__(self, session_factory, control_dir=None):
        self.session_factory, self.control_dir = session_factory, control_dir
        self.bridge = ExecutionMaterialBridge()
        self.captures = {}
        self.ticket_key = "isolated_material_execution_ticket_" + uuid4().hex

    async def capture(self, value):
        async with self.session_factory() as session, session.begin():
            await guard(session)
            row = await first(
                session,
                "SELECT allocation_id,name_reservation_id FROM orbit_launch_validation "
                "WHERE tenant_id=:tenant AND id=:id",
                {"tenant": value.current.tenant_id, "id": value.validation_id},
            )
            if row is None:
                raise OrbitError(409, "STALE_PREVIEW", "实际预检来源不存在")
            materials = await self.bridge.capture_materials(session, value.current, value.source)
            now = await database_now(session)
        observed = await IsolatedExecutionValidationProvider(
            self.session_factory, self.control_dir
        ).capture(ValidationInput(value.current, value.source, canonical(dict(row)).encode()))
        arguments = json.loads(observed.freeze_arguments_json)
        arguments.pop("total_dag_node_count")
        plan = value.source.payload()
        metadata = json.loads(materials.metadata_json)
        revisions = {key: row["revision"] for key, row in metadata.items()}
        compatibility = build_compatibility_evidence(
            ad_slots(plan),
            plan["asset_ids"],
            capability_version=arguments["capability_version"],
            source_hash=digest([value.source.payload_hash, "ISOLATED_COMPATIBILITY"]),
            verified=True,
            complete=True,
            evaluate=lambda _slot, _asset: True,
            material_revisions=revisions,
        )
        profiles = {
            group["metric_profile_id"]
            for campaign in plan["campaigns"]
            for group in campaign["adsets"]
        }
        from uuid import UUID

        refs = tuple(observed.observations) + (
            ObservationReference("CAPABILITY", str(UUID(int=93901)), 1),
            ObservationReference("POLICY", str(UUID(int=93902)), 1),
        )
        refs += tuple(ObservationReference("ACCOUNT", key, 1) for key in plan["account_ids"])
        refs += tuple(
            ObservationReference("MATERIAL", key, revision) for key, revision in revisions.items()
        )
        refs += tuple(ObservationReference("CONFIGURATION", key, 1) for key in profiles)
        prepared = prepare_execution(
            value.source,
            value.validation,
            validated_head_revision=value.source.head_revision,
            **arguments,
            compatibility=compatibility,
            material_revisions=revisions,
            material_metadata=metadata,
            resolved_metric_profiles={key: profile(key) for key in profiles},
            observation_refs=refs,
            request=json.loads(value.request_json),
            now=now,
        )
        if len(self.captures) >= 64:
            raise OrbitError(
                503, "LAUNCH_EXECUTION_AUTHORITY_UNAVAILABLE", "隔离工具有界捕获已达上限"
            )
        self.captures[prepared.manifest_hash] = materials
        return ExecutionEvidence(
            value.current,
            value.validation_id,
            digest([prepared.manifest_hash, materials.metadata_json.decode()]),
            prepared,
        )

    async def revalidate(self, session, current, source, evidence):
        await guard(session)
        capture = self.captures.get(evidence.prepared.manifest_hash)
        if capture is None:
            raise OrbitError(409, "STALE_PREVIEW", "缺同源真实C捕获")
        ticket = await self.bridge.lock_for_accept(
            session, current, source, capture, evidence.prepared
        )
        session.info[self.ticket_key] = ticket
        return evidence

    async def publish_references(self, session, current, evidence, task_id, request_id):
        await self.bridge.publish(
            session,
            current,
            evidence.prepared.source,
            evidence.prepared,
            session.info.get(self.ticket_key),
            task_id,
            request_id,
        )


def run_launch_execution_material_bridge_checks(
    client, admin, headers, database, cases, *, object_root, registry, user_fixture
):
    root = validate_target(admin, database, object_root)
    from orbit_api.authorization import require_business_access
    from orbit_api.material_contract import CompletedPart
    from orbit_api.material_job_policy import actor_auth_version, material_job_scope
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_scanner_selection import ConfiguredMaterialWorker
    from orbit_api.material_security import clean_scan_ids

    def checked(response, expected):
        assert response.status_code == expected, {
            "actual": response.status_code,
            "expected": expected,
            "code": response.json().get("code"),
        }
        return response.json()

    def one(sql, params=()):
        with admin.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        admin.commit()
        return row

    assert one("SELECT DATABASE()")[0] == database, "真实选中数据库必须精确等于本轮UUID库"

    owner, peer = user_fixture["users"][1], user_fixture["users"][3]
    assert owner["team"] == peer["team"] and owner["id"] != peer["id"]
    tenant = one("SELECT tenant_id FROM orbit_business_user WHERE user_id=1")[0]
    role_caps = checked(client.get("/api/v1/roles/capabilities", headers=headers), 200)
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": role_caps["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "执行C桥fixture-" + uuid4().hex[:8],
                "menu_codes": ["assets", "launch"],
                "permission_codes": ["assets.read", "assets.upload", "launch.execute"],
            },
        ),
        201,
    )
    native = one(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
    )[0]
    with admin.cursor() as cursor:
        for user in (owner, peer):
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (user["native"], native)
            )
    admin.commit()
    profiles = checked(
        client.get("/api/v1/system-configurations/material-scanner-profiles", headers=headers), 200
    )
    profile_id = next(row["id"] for row in profiles["items"] if row["availability"] == "READY")
    assert registry.resolve(profile_id).profile.profile_id == profile_id
    caps = checked(client.get("/api/v1/assets/capabilities", headers=headers), 200)
    config_body = {
        "section": "MATERIAL_SCANNER",
        "name": "真实执行C桥扫描fixture",
        "enabled": True,
        "settings": {"profileId": profile_id},
        "secrets": {},
        "reason": "真实执行引用链验收",
    }
    existing = one(
        "SELECT id,revision FROM orbit_system_configuration WHERE tenant_id=%s "
        "AND section='MATERIAL_SCANNER' LIMIT 1",
        (tenant,),
    )
    config_headers = headers | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": str(uuid4())}
    if existing:
        checked(
            client.put(
                "/api/v1/system-configurations/" + existing[0],
                headers=config_headers | {"If-Match": f'"{existing[1]}"'},
                json=config_body,
            ),
            200,
        )
    else:
        checked(
            client.post("/api/v1/system-configurations", headers=config_headers, json=config_body),
            200,
        )
    objects = LocalMaterialObjects(root)

    def decode(value):
        return value.decode() if isinstance(value, bytes) else value

    async def setup():
        engine = create_async_engine(
            URL.create(
                "mysql+asyncmy",
                username=decode(admin.user),
                password=decode(admin.password),
                host=admin.host,
                port=admin.port,
                database=database,
            ),
            echo=False,
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            identifier, upload = str(uuid4()), str(uuid4())
            buffer = BytesIO()
            Image.new("RGB", (28, 24), (20, 60, 90)).save(buffer, "PNG")
            content = buffer.getvalue()
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
                params = {
                    "tenant": tenant,
                    "id": identifier,
                    "owner": owner["id"],
                    "team": owner["team"],
                    "sha": sha,
                    "size": len(content),
                    "upload": upload,
                    "category": caps["default_category_id"],
                }
                await session.execute(
                    text(
                        "INSERT INTO orbit_material_asset(tenant_id,id,owner_user_id,owner_team_id,"
                        "name,category_id,kind,mime,state,sha256,byte_size,object_upload_id) "
                        "VALUES(:tenant,:id,:owner,:team,"
                        "'真实执行PNGfixture',:category,'IMAGE','image/png','SCANNING',:sha,:size"
                        ",:upload)"
                    ),
                    params,
                )
                material = {
                    "id": identifier,
                    "owner_user_id": owner["id"],
                    "owner_team_id": owner["team"],
                    "sha256": sha,
                    "mime": "image/png",
                }
                await session.execute(
                    text(
                        "INSERT INTO "
                        "orbit_material_job(tenant_id,asset_id,actor_id,actor_auth_version,"
                        "scope_digest,state,created_at) "
                        "VALUES(:tenant,:id,:actor,:version,:scope,'PENDING','1800-01-01')"
                    ),
                    params
                    | {
                        "actor": owner["native"],
                        "version": await actor_auth_version(session, owner["native"]),
                        "scope": material_job_scope(current, material),
                    },
                )
            own_processed = False
            for _ in range(20):
                result = await ConfiguredMaterialWorker(
                    sessions, objects, registry=registry
                ).run_once(1)
                own = [row for row in result if row["asset_id"] == identifier]
                if own:
                    assert len(own) == 1 and own[0]["state"] == "READY"
                    own_processed = True
                    break
                if not result:
                    break
            assert own_processed, "有界Worker必须实际处理本组对象，不假设租户队列为空"
            async with sessions() as session, session.begin():
                assert identifier in await clean_scan_ids(session, tenant, [identifier])
                row = (
                    await session.execute(
                        text(
                            "SELECT revision,sha256 FROM orbit_material_asset "
                            "WHERE tenant_id=:tenant AND id=:id"
                        ),
                        {"tenant": tenant, "id": identifier},
                    )
                ).one()
            return identifier, row[0], row[1]
        finally:
            await engine.dispose()

    asset, asset_revision, sha = asyncio.run(setup())
    cases.append(EXECUTION_MATERIAL_BRIDGE_CASES[0])

    def write(revision):
        cap = checked(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)
        return headers | {
            "X-CSRF-Token": cap["csrf_token"],
            "Idempotency-Key": str(uuid4()),
            "If-Match": f'"{revision}"',
        }

    def new(plan_owner=owner["id"]):
        item = create_protocol_plan(admin, tenant, plan_owner, owner["team"], mode="REAL_C_BRIDGE")
        plan = item["value"]
        plan["asset_ids"] = [asset]
        versions = {asset: asset_revision}
        evidence = build_compatibility_evidence(
            ad_slots(plan),
            [asset],
            capability_version="ISOLATED_PROTOCOL_NOT_PLATFORM",
            source_hash=digest([digest(plan), "ISOLATED_COMPATIBILITY"]),
            verified=True,
            complete=True,
            evaluate=lambda _slot, _asset: True,
            material_revisions=versions,
        )
        solution = solve_allocation(
            ad_slots(plan),
            [asset],
            evidence,
            allow_repeat=True,
            seed=0,
            material_revisions=versions,
        )
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_launch_plan SET "
                "payload_json=%s,payload_hash=%s,payload_bytes=%s WHERE id=%s",
                (canonical(plan), digest(plan), len(canonical(plan).encode()), item["id"]),
            )
            cursor.execute(
                "UPDATE orbit_launch_plan_version SET payload_json=%s,payload_hash=%s WHERE "
                "plan_id=%s",
                (canonical(plan), digest(plan), item["id"]),
            )
            cursor.execute(
                "UPDATE orbit_launch_allocation_item SET "
                "asset_id=%s,asset_revision=%s,asset_sha256=%s "
                "WHERE tenant_id=%s AND allocation_id=%s",
                (asset, asset_revision, sha, tenant, item["body"]["allocation_id"]),
            )
            cursor.execute(
                "UPDATE orbit_launch_allocation SET input_hash=%s WHERE tenant_id=%s AND id=%s",
                (solution.input_hash, tenant, item["body"]["allocation_id"]),
            )
        admin.commit()
        validation = checked(
            client.post(
                f"/api/v1/launch-plans/{item['id']}/validate", headers=write(1), json=item["body"]
            ),
            200,
        )
        assert validation["valid"]
        item.update(execute={"hash": validation["hash"], "activate_ack": False}, head=write(2))
        return item

    def execute(item):
        return client.post(
            f"/api/v1/launch-plans/{item['id']}/execute", headers=item["head"], json=item["execute"]
        )

    first_item = new()
    task = checked(execute(first_item), 202)
    assert task["node_count"] > 0
    assert one(
        "SELECT source_revision,validated_head_revision,submitted_head_revision FROM "
        "orbit_launch_execution_acceptance WHERE task_id=%s",
        (task["id"],),
    ) == (1, 2, 3)
    assert (
        one(
            "SELECT COUNT(*) FROM orbit_material_reference WHERE tenant_id=%s AND asset_id=%s "
            "AND kind='EXECUTION' AND resource_id=%s AND active=1",
            (tenant, asset, task["id"]),
        )[0]
        == 1
    )
    cases.append(EXECUTION_MATERIAL_BRIDGE_CASES[1])
    wrong_owner = new(peer["id"])
    checked(execute(wrong_owner), 404)
    cases.append(EXECUTION_MATERIAL_BRIDGE_CASES[2])
    revoked = new()
    caller_headers = user_fixture["actor_headers"]
    caller_caps = checked(client.get("/api/v1/assets/capabilities", headers=caller_headers), 200)
    caller_write = caller_headers | {
        "X-CSRF-Token": caller_caps["csrf_token"],
        "Idempotency-Key": str(uuid4()),
        "If-Match": '"2"',
    }
    # 移除owner的全部assets.read原生映射并精确恢复，不借root可读绕过owner交集。
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT rm.role_id,rm.menu_id FROM sys_role_menu rm JOIN sys_user_role ur "
            "ON ur.role_id=rm.role_id JOIN sys_menu m ON m.menu_id=rm.menu_id "
            "WHERE ur.user_id=%s AND m.perms='assets.read'",
            (owner["native"],),
        )
        saved = cursor.fetchall()
        assert saved
        cursor.executemany("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=%s", saved)
    admin.commit()
    try:
        # 原caller仍有launch.execute，只有素材read被即时撤销；不得借root代读。
        checked(
            client.post(
                f"/api/v1/launch-plans/{revoked['id']}/execute",
                headers=caller_write,
                json=revoked["execute"],
            ),
            403,
        )
        assert (
            one("SELECT COUNT(*) FROM orbit_task WHERE source_plan_id=%s", (revoked["id"],))[0] == 0
        )
        checked(execute(revoked), 404)
        assert (
            one("SELECT COUNT(*) FROM orbit_task WHERE source_plan_id=%s", (revoked["id"],))[0] == 0
        )
    finally:
        with admin.cursor() as cursor:
            cursor.executemany("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)", saved)
        admin.commit()
    cases.append(EXECUTION_MATERIAL_BRIDGE_CASES[3])
    corrupted = new()
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT receipt_id,config_sha256 FROM orbit_material_scan_runtime_proof "
            "WHERE tenant_id=%s AND asset_id=%s",
            (tenant, asset),
        )
        receipt, config_hash = cursor.fetchone()
        cursor.execute(
            "UPDATE orbit_material_scan_runtime_proof SET config_sha256=%s "
            "WHERE tenant_id=%s AND asset_id=%s AND receipt_id=%s",
            ("0" * 64, tenant, asset, receipt),
        )
    admin.commit()
    try:
        checked(execute(corrupted), 409)
        assert (
            one("SELECT COUNT(*) FROM orbit_task WHERE source_plan_id=%s", (corrupted["id"],))[0]
            == 0
        )
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_material_scan_runtime_proof SET config_sha256=%s "
                "WHERE tenant_id=%s AND asset_id=%s AND receipt_id=%s",
                (config_hash, tenant, asset, receipt),
            )
        admin.commit()
    cases.append(EXECUTION_MATERIAL_BRIDGE_CASES[4])
    rollback = new()
    trigger = "execution_material_outbox_" + uuid4().hex[:10]
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "CREATE TRIGGER " + trigger + " BEFORE INSERT ON orbit_material_outbox "
                "FOR EACH ROW SIGNAL SQLSTATE '45000' SET "
                "MESSAGE_TEXT='ISOLATED_MATERIAL_ACCEPT_FAILURE'"
            )
        admin.commit()
        checked(execute(rollback), 503)
        assert (
            one(
                "SELECT COUNT(*) FROM orbit_launch_execution_acceptance WHERE plan_id=%s",
                (rollback["id"],),
            )[0]
            == 0
        )
        assert one(
            "SELECT state,revision FROM orbit_launch_plan WHERE id=%s", (rollback["id"],)
        ) == ("VALIDATED", 2)
        assert (
            one(
                "SELECT COUNT(*) FROM orbit_material_reference r JOIN orbit_task t ON "
                "t.tenant_id=r.tenant_id AND t.id=r.resource_id WHERE t.source_plan_id=%s",
                (rollback["id"],),
            )[0]
            == 0
        )
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS " + trigger)
        admin.commit()
    cases.append(EXECUTION_MATERIAL_BRIDGE_CASES[5])
