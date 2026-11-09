"""到期未追平真实保护链；隔离库预置合法历史时刻，不伪装真实日历跨日。"""

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from launch_draft_template_checks import draft
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

CASES = [
    "pythonAccountProjectionDueBlocksAllCurrentAccountReadShapes",
    "pythonAccountProjectionDueBlocksScopeFreezeAndFrozenMemberRead",
    "pythonAccountProjectionDueBlocksLaunchSourceAndObservationPublication",
    "pythonAccountProjectionDueBlocksImportAcceptanceAndWorkerBeforeHttp",
    "pythonAccountProjectionRecoveryUsesIndependentWorkerWithoutSelfDeadlock",
    "pythonAccountProjectionAfterRecoveryOldOwnerCannotReadOrKeepScope",
]


def run_account_projection_checks(
    client,
    admin,
    headers,
    owner_user_id,
    owner_team_id,
    vendor_id,
    target_identity,
    readonly_identity,
    database,
    cases,
    cipher,
):
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("到期投影专项只允许主线当前独立MySQL库")
    from orbit_api.account_actions_worker import AccountActionsWorker
    from orbit_api.account_details_store import AccountDetailsStore
    from orbit_api.account_worker import AccountImportWorker
    from orbit_api.directory_tokens import DirectoryTokens, canonical
    from orbit_api.errors import OrbitError

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decoded(admin.user),
        password=decoded(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )
    account, old_interval, future_interval, command, request_id = (str(uuid4()) for _ in range(5))
    zone = ZoneInfo("America/New_York")
    effective = (
        datetime.now(UTC).astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
    )
    start = (effective - timedelta(days=1)).astimezone(UTC)
    effective = effective.astimezone(UTC)
    old_owner = readonly_identity["owner_user_id"]
    assert readonly_identity["owner_team_id"] == owner_team_id == target_identity["owner_team_id"]
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE id=%s", (owner_user_id,))
        tenant = cursor.fetchone()[0]
        cursor.execute(
            "SELECT id FROM orbit_business_user WHERE user_id=1 AND tenant_id=%s", (tenant,)
        )
        actor_subject = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO orbit_ad_account "
            "(tenant_id,id,external_id,name,name_prefix,owner_user_id,owner_team_id,currency,"
            "timezone_id,auth_status,account_status,value_json,details_json,bound_at,created_at) "
            "VALUES(%s,%s,%s,'到期保护受控','到期保护受控',%s,%s,'USD','America/New_York',"
            "'AUTHORIZED','ACTIVE','{}','{}',%s,%s)",
            (
                tenant,
                account,
                str(10**24 + uuid4().int % 10**24),
                old_owner,
                owner_team_id,
                start.replace(tzinfo=None),
                start.replace(tzinfo=None),
            ),
        )
    root_scope_cap = client.get("/api/v1/scope-snapshots/capabilities", headers=headers)
    old_scope_cap = client.get(
        "/api/v1/scope-snapshots/capabilities", headers=readonly_identity["headers"]
    )
    launch_cap = client.get("/api/v1/launch-plans/capabilities", headers=headers)
    import_cap = client.get("/api/v1/account-imports/capabilities", headers=headers)
    assert all(
        response.status_code == 200
        for response in (root_scope_cap, old_scope_cap, launch_cap, import_cap)
    )
    old_scope = client.post(
        "/api/v1/scope-snapshots",
        headers=readonly_identity["headers"]
        | {
            "X-CSRF-Token": old_scope_cap.json()["csrf_token"],
            "Idempotency-Key": "projection-scope-" + uuid4().hex,
        },
        json={"mode": "IDS", "account_ids": [account], "filter": None},
    )
    assert old_scope.status_code == 201
    accepted_import = client.post(
        "/api/v1/account-imports",
        headers=headers
        | {
            "X-CSRF-Token": import_cap.json()["csrf_token"],
            "Idempotency-Key": "projection-import-" + uuid4().hex,
        },
        json={
            "vendor_id": vendor_id,
            "owner_user_id": owner_user_id,
            "owner_team_id": owner_team_id,
            "account_ids_text": str(10**25 + uuid4().int % 10**25),
        },
    )
    assert accepted_import.status_code == 202
    with admin.cursor() as cursor:
        for identifier, owner, begin, end, reason in (
            (old_interval, old_owner, start, effective, "受控历史原归属"),
            (future_interval, target_identity["owner_user_id"], effective, None, "受控已到期归属"),
        ):
            cursor.execute(
                "INSERT INTO orbit_account_assignment "
                "(tenant_id,id,account_id,owner_user_id,owner_team_id,starts_at,ends_at,reason) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    tenant,
                    identifier,
                    account,
                    owner,
                    owner_team_id,
                    begin.replace(tzinfo=None),
                    end.replace(tzinfo=None) if end else None,
                    reason,
                ),
            )
        payload = {
            "operator_user_id": target_identity["owner_user_id"],
            "owner_team_id": owner_team_id,
            "vendor_id": None,
            "effective_from": effective.isoformat().replace("+00:00", "Z"),
            "reason": "受控历史已受理任务，验证当前到期保护",
        }
        source = {
            "owner_user_id": old_owner,
            "owner_team_id": owner_team_id,
            "vendor_id": None,
            "currency": "USD",
            "timezone_id": "America/New_York",
            "target_alias_at_accept": {
                "alias": None,
                "alias_revision": None,
                "source": "NO_VENDOR",
            },
        }
        ack = {"id": account, "revision": 2, "state": "SCHEDULED", "request_id": request_id}
        cursor.execute(
            "UPDATE orbit_ad_account SET revision=2 WHERE tenant_id=%s AND id=%s", (tenant, account)
        )
        cursor.execute(
            "INSERT INTO orbit_account_command "
            "(tenant_id,id,account_id,kind,state,actor_id,actor_subject_id,request_key,request_hash,"
            "request_id,accepted_account_revision,source_json,payload_json,response_json,assignment_id,"
            "effective_from,active_kind,created_at,updated_at) "
            "VALUES(%s,%s,%s,'ASSIGNMENT','SCHEDULED',1,%s,%s,%s,%s,2,%s,%s,%s,%s,%s,"
            "'ASSIGNMENT',%s,%s)",
            (
                tenant,
                command,
                account,
                actor_subject,
                "projection-history-" + uuid4().hex,
                hashlib.sha256(canonical(["ASSIGNMENT", account, 1, payload]).encode()).hexdigest(),
                request_id,
                json.dumps(source),
                json.dumps(payload),
                json.dumps(ack),
                future_interval,
                effective.replace(tzinfo=None),
                start.replace(tzinfo=None),
                start.replace(tzinfo=None),
            ),
        )
        cursor.execute(
            "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
        )

    def blocked(response):
        assert (
            response.status_code == 503
            and response.json()["code"] == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"
        )
        assert response.headers.get("Cache-Control") == "no-store"

    for path in (
        "/api/v1/accounts/extended",
        f"/api/v1/accounts/{account}",
        f"/api/v1/accounts/{account}/details",
        "/api/v1/accounts/owner-options",
        f"/api/v1/accounts/{account}/identities",
    ):
        blocked(client.get(path, headers=readonly_identity["headers"]))
    cases.append(CASES[0])
    blocked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers))
    blocked(
        client.get(
            f"/api/v1/scope-snapshots/{old_scope.json()['id']}/members",
            headers=readonly_identity["headers"],
        )
    )
    blocked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=headers
            | {
                "X-CSRF-Token": root_scope_cap.json()["csrf_token"],
                "Idempotency-Key": "projection-block-scope-" + uuid4().hex,
            },
            json={"mode": "IDS", "account_ids": [account], "filter": None},
        )
    )
    cases.append(CASES[1])
    body = draft({"id": old_owner, "team": owner_team_id})
    body["account_ids"] = [account]
    blocked(
        client.post(
            "/api/v1/launch-plans",
            headers=headers
            | {
                "X-CSRF-Token": launch_cap.json()["csrf_token"],
                "Idempotency-Key": "projection-block-plan-" + uuid4().hex,
            },
            json=body,
        )
    )

    async def internal_checks():
        engine = create_async_engine(url, echo=False)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            try:
                async with sessions() as session, session.begin():
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "SELECT revision FROM orbit_account_details_clock WHERE tenant_id=%s",
                            (tenant,),
                        )
                        saved_watermark = cursor.fetchone()
                    await AccountDetailsStore(DirectoryTokens(cipher)).publish(
                        session,
                        1,
                        saved_watermark[0] if saved_watermark else 0,
                        observations=[
                            {
                                "account_id": account,
                                "observations": {
                                    "balance": {
                                        "amount": None,
                                        "currency": "USD",
                                        "kind": "UNKNOWN",
                                        "status": "UNSYNCED",
                                        "source": "VERIFIED_INGESTION",
                                        "business_date": None,
                                        "observed_at": None,
                                    }
                                },
                            }
                        ],
                    )
            except OrbitError as error:
                assert error.status == 503 and error.code == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"
            else:
                raise AssertionError("到期前不能发布观测")
            cases.append(CASES[2])
            blocked(
                client.post(
                    "/api/v1/account-imports",
                    headers=headers
                    | {
                        "X-CSRF-Token": import_cap.json()["csrf_token"],
                        "Idempotency-Key": "projection-block-import-" + uuid4().hex,
                    },
                    json={
                        "vendor_id": vendor_id,
                        "owner_user_id": owner_user_id,
                        "owner_team_id": owner_team_id,
                        "account_ids_text": "123456789",
                    },
                )
            )
            calls = []

            def forbidden_platform(configuration):
                calls.append(True)
                raise AssertionError("到期未追平不能创建平台读取器")

            worker = AccountImportWorker(
                sessions,
                cipher,
                {"USD"},
                platform_factory=forbidden_platform,
                target=(tenant, accepted_import.json()["id"]),
            )
            try:
                await worker.run_once(1)
            except OrbitError as error:
                assert error.code == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"
            else:
                raise AssertionError("旧导入Worker必须暂停，不能沿旧投影前进")
            assert calls == []
            cases.append(CASES[3])
            async with sessions() as session, session.begin():
                result = await AccountActionsWorker().advance_due(session, tenant)
            assert result["activated"] == 1 and result["blocked"] == 0
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT owner_user_id FROM orbit_ad_account WHERE tenant_id=%s AND id=%s",
                    (tenant, account),
                )
                assert cursor.fetchone()[0] == target_identity["owner_user_id"]
                cursor.execute(
                    "SELECT state,active_kind FROM orbit_account_command "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, command),
                )
                assert cursor.fetchone() == ("SUCCEEDED", None)
            cases.append(CASES[4])
        finally:
            await engine.dispose()

    asyncio.run(internal_checks())
    assert client.get(f"/api/v1/accounts/{account}", headers=headers).status_code == 200
    assert (
        client.get(f"/api/v1/accounts/{account}", headers=readonly_identity["headers"]).status_code
        == 404
    )
    invalid_scope = client.get(
        f"/api/v1/scope-snapshots/{old_scope.json()['id']}/members",
        headers=readonly_identity["headers"],
    )
    assert invalid_scope.status_code == 409 and invalid_scope.json()["code"] == "SCOPE_CHANGED"
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_account_spend_day WHERE tenant_id=%s AND account_id=%s",
            (tenant, account),
        )
        assert cursor.fetchone()[0] == 0
    cases.append(CASES[5])
