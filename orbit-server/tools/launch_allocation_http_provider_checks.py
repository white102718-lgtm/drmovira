"""原Allocation HTTP成功协议专项；只由主线在固定本机UUID数据库串行执行。"""

import asyncio
import json
import re
from pathlib import Path
from uuid import uuid4

from launch_allocation_http_fixture import IsolatedHttpAllocationProvider
from material_schema_checks import validate_original_schema
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES = [
    "pythonLaunchAllocationHttpActualPost202OriginalQueuedAllocationAndSourceVersion",
    "pythonLaunchAllocationHttpActualGetQueuedSameAllocationWithoutTask",
    "pythonLaunchAllocationHttpActualClaimLoadSolvePublishAndStateHeadCas",
    "pythonLaunchAllocationHttpActualGetCompleteSucceededOriginalSchemaSlots",
    "pythonLaunchAllocationHttpOldCasReplayDifferentIntentAndNewKeyCurrentCas",
    "pythonLaunchAllocationHttpCurrentEditAndReadRevocationNeverReplayCachedSuccess",
    "pythonLaunchAllocationHttpParentBindingAndUnknownQueryCannotLeakAllocation",
    "pythonLaunchAllocationHttpActual1644AuditRollbackHasNoPartialQueueOrTask",
]


def run_launch_allocation_http_provider_checks(client, admin, headers, database, cases):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("分配HTTP成功协议只允许本轮13306 UUID库")
    from orbit_api.directory_tokens import canonical
    from orbit_api.launch_access import digest
    from orbit_api.launch_allocation_runtime import AllocationRuntime, solve_packet
    from orbit_api.launch_contract import parse_plan

    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    admin.commit()
    plan_id, account, asset = str(uuid4()), str(uuid4()), str(uuid4())
    value = parse_plan(
        canonical(
            {
                "name": "HTTP协议fixture不是平台预检",
                "ownership": {"owner_user_id": owner, "owner_team_id": team},
                "account_ids": [account],
                "asset_ids": [asset],
                "channel_id": None,
                "identity_bindings": [],
                "allow_repeat": True,
                "activate_after_create": False,
                "execution_mode": "META_API",
                "campaigns": [
                    {
                        "local_id": str(uuid4()),
                        "copies": 1,
                        "adsets": [
                            {
                                "local_id": str(uuid4()),
                                "copies": 1,
                                "ads": [{"local_id": str(uuid4()), "copies": 2}],
                            }
                        ],
                    }
                ],
            }
        ).encode()
    )
    payload = canonical(value)
    # 本轮SQL协议fixture，不伪造真实业务的预检/能力来源；head4与source1明确分离。
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbit_launch_plan(tenant_id,id,owner_user_id,owner_team_id,"
            "channel_id,name,state,revision,payload_json,payload_hash,payload_bytes,account_count,"
            "asset_count,created_at,updated_at) "
            "VALUES(%s,%s,%s,%s,NULL,%s,'VALIDATED',4,%s,%s,%s,1,1,"
            "UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (
                tenant,
                plan_id,
                owner,
                team,
                value["name"],
                payload,
                digest(value),
                len(payload.encode()),
            ),
        )
        cursor.execute(
            "INSERT INTO orbit_launch_plan_version(tenant_id,plan_id,revision,payload_json,"
            "payload_hash,dependency_json,created_at,created_by) "
            "VALUES(%s,%s,1,%s,%s,'{}',UTC_TIMESTAMP(3),1)",
            (tenant, plan_id, payload, digest(value)),
        )
    admin.commit()
    specification = json.loads(
        (
            Path(__file__).resolve().parents[2] / "data/ORBIT_Codex开发PRD/contracts/openapi.json"
        ).read_text(encoding="utf-8")
    )
    path = f"/api/v1/launch-plans/{plan_id}/allocations"
    command = {
        "asset_ids": [asset],
        "allow_repeat": True,
        "seed": 0,
        "algorithm_version": "allocation-v1",
    }

    def checked(response, status):
        assert response.status_code == status, {"actual": response.status_code, "expected": status}
        return response.json()

    capability = checked(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)
    original_key = str(uuid4())

    def write(revision=4, key=original_key):
        return headers | {
            "X-CSRF-Token": capability["csrf_token"],
            "If-Match": f'"{revision}"',
            "Idempotency-Key": key,
        }

    def schema(body):
        validate_original_schema(
            body, specification["components"]["schemas"]["Allocation"], specification
        )

    created = checked(client.post(path, headers=write(), json=command), 202)
    schema(created)
    assert created["state"] == "QUEUED" and created["plan_revision"] == 1
    assert created["plan_id"] == plan_id and created["task_id"] is None and created["items"] == []
    cases.append(LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES[0])
    detail_path = path + "/" + created["id"]
    queued = checked(client.get(detail_path, headers=headers), 200)
    schema(queued)
    assert queued == created
    cases.append(LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES[1])

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    async def consume():
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
        runtime = AllocationRuntime(IsolatedHttpAllocationProvider())
        try:
            async with sessions() as session, session.begin():
                claim = await runtime.claim(session, str(uuid4()))
                assert claim is not None and claim.allocation_id == created["id"]
            async with sessions() as session, session.begin():
                _, packet, evidence = await runtime.load(session, claim)
                assert packet["plan_revision"] == 1
            solution = solve_packet(packet, evidence)
            async with sessions() as session, session.begin():
                return await runtime.publish(session, claim, solution, str(uuid4()))
        finally:
            await engine.dispose()

    published = asyncio.run(consume())
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT revision,state FROM orbit_launch_plan WHERE tenant_id=%s AND id=%s",
            (tenant, plan_id),
        )
        assert cursor.fetchone() == (5, "DRAFT")
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_launch_plan_version WHERE tenant_id=%s AND plan_id=%s",
            (tenant, plan_id),
        )
        assert cursor.fetchone()[0] == 1
    admin.commit()
    assert published["state"] == "SUCCEEDED" and published["plan_revision"] == 1
    cases.append(LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES[2])
    final = checked(client.get(detail_path, headers=headers), 200)
    schema(final)
    assert final == published and final["task_id"] is None and len(final["items"]) == 2
    assert len({item["slot_key"] for item in final["items"]}) == 2
    assert all(
        item["account_id"] == account and item["asset_id"] == asset and item["asset_revision"] == 1
        for item in final["items"]
    )
    cases.append(LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES[3])
    assert checked(client.post(path, headers=write(), json=command), 202) == final
    rejected = checked(client.post(path, headers=write(), json=command | {"seed": 1}), 409)
    assert rejected["code"] == "IDEMPOTENCY_CONFLICT"
    rejected = checked(client.post(path, headers=write(key=str(uuid4())), json=command), 409)
    assert rejected["code"] == "REVISION_CONFLICT"
    cases.append(LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES[4])

    for menu_id, operation in (
        (31023, lambda: client.post(path, headers=write(), json=command)),
        (31021, lambda: client.get(detail_path, headers=headers)),
    ):
        with admin.cursor() as cursor:
            cursor.execute("SELECT status FROM sys_menu WHERE menu_id=%s", (menu_id,))
            original = cursor.fetchone()[0]
            cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=%s", (menu_id,))
        admin.commit()
        try:
            assert checked(operation(), 403)["code"] == "PERMISSION_DENIED"
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE sys_menu SET status=%s WHERE menu_id=%s", (original, menu_id)
                )
            admin.commit()
    cases.append(LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES[5])
    checked(
        client.get(f"/api/v1/launch-plans/{uuid4()}/allocations/{created['id']}", headers=headers),
        404,
    )
    checked(client.get(path + "/" + str(uuid4()), headers=headers), 404)
    checked(client.get(detail_path + "?actor=1", headers=headers), 400)
    cases.append(LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES[6])

    def snapshot():
        result = []
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT revision,state,payload_hash FROM orbit_launch_plan "
                "WHERE tenant_id=%s AND id=%s",
                (tenant, plan_id),
            )
            result.append(cursor.fetchone())
            # 只读计数，不复制大配置/分块或无界扫描历史响应正文。
            for table in (
                "orbit_launch_allocation",
                "orbit_launch_allocation_runtime",
                "orbit_launch_allocation_item",
                "orbit_launch_allocation_chunk",
                "orbit_launch_allocation_guard",
                "orbit_launch_idempotency",
                "orbit_launch_event",
                "orbit_launch_outbox",
                "orbit_task",
            ):
                cursor.execute("SELECT COUNT(*) FROM " + table + " WHERE tenant_id=%s", (tenant,))
                result.append(cursor.fetchone()[0])
            cursor.execute(
                "SELECT plan_revision FROM orbit_launch_clock WHERE tenant_id=%s", (tenant,)
            )
            result.append(cursor.fetchone()[0])
        admin.commit()
        return tuple(result)

    before = snapshot()
    trigger = "it_alloc_http_" + uuid4().hex[:16]
    with admin.cursor() as cursor:
        cursor.execute(
            f"CREATE TRIGGER {trigger} BEFORE INSERT ON orbit_launch_event FOR EACH ROW BEGIN "
            "IF NEW.action='allocation.queued' THEN SIGNAL SQLSTATE '45000' "
            "SET MESSAGE_TEXT='ISOLATED_HTTP_AUDIT_1644'; END IF; END"
        )
    admin.commit()
    try:
        failed = client.post(path, headers=write(5, str(uuid4())), json=command | {"seed": 1})
        checked(failed, 503)
        assert "ISOLATED_HTTP_AUDIT_1644" not in failed.text
        assert snapshot() == before
        assert checked(client.get(detail_path, headers=headers), 200) == final
    finally:
        with admin.cursor() as cursor:
            cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        admin.commit()
    cases.append(LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES[7])
    return {
        "case_count": len(LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES),
        "provider_kind": "ISOLATED_TEST",
        "real_platform_verified": False,
        "material_reference_publication_verified": False,
        "slot_count": len(final["items"]),
        "task_created": False,
    }
