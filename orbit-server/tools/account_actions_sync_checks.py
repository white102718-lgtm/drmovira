"""029真实MySQL/HTTP/本机TLS专项；网络夹具不是生产Meta验收，不写广告。"""

import asyncio
import json
import re
import tempfile
from datetime import UTC, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from account_platform_checks import local_graph
from sqlalchemy import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

CASES = [
    "pythonAccountSyncActualTlsMetadataAtomicAndUnknownMoneyPreserved",
    "pythonAccountSyncInitialPlusThreeRetriesRespectThirtySixtyOneTwenty",
    "pythonAccountSyncSourceChangedBeforeHttpOrWriteNeverCommitsObservation",
    "pythonAccountSyncAccountVersionFenceRejectsLateObservation",
    "pythonAccountSyncReadLeaseRecoveryCannotReviveOldClaim",
    "pythonAccountSyncCurrentActorRevocationStopsPlatformHttp",
    "pythonAccountSyncLocalUnbindCannotBeReversedByInflightRead",
    "pythonAccountSyncMetadataAuditFailureRollsBackThenControlledRecovery",
    "pythonAccountSyncTimezoneChangeRequiresExplicitReconciliation",
]


def run_account_sync_checks(
    client,
    admin,
    headers,
    cipher,
    owner_user_id,
    owner_team_id,
    action_identity,
    database,
    cases,
):
    """action_identity为028已有唯一actions-only TEAM_ADMIN，不扩大到accounts.read。"""
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("账户同步专项只允许本轮独立MySQL夹具")
    from orbit_api.account_actions_sync import AccountSyncWorker
    from orbit_api.account_platform import AccountReadFailure

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
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE id=%s", (owner_user_id,))
        tenant = cursor.fetchone()[0]
        cursor.execute(
            "SELECT id FROM orbit_system_configuration "
            "WHERE tenant_id=%s AND section='META_BM' AND enabled=1",
            (tenant,),
        )
        prior_sources = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            "UPDATE orbit_system_configuration SET enabled=0 "
            "WHERE tenant_id=%s AND section='META_BM'",
            (tenant,),
        )
    source = str(uuid4())
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbit_system_configuration "
            "(id,tenant_id,section,name,enabled,revision,"
            "settings_json,secrets_json,verification_status) "
            "VALUES(%s,%s,'META_BM','同步独占受控来源',1,1,%s,%s,'READ_VERIFIED')",
            (
                source,
                tenant,
                json.dumps({"businessId": "42", "graphVersion": "v25.0"}),
                json.dumps(
                    {
                        "accessToken": cipher.encrypt(
                            "fixture-secret-token", tenant, source, "accessToken"
                        )
                    }
                ),
            ),
        )

    def seed():
        account, external = str(uuid4()), str(10**22 + uuid4().int % 10**22)
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_ad_account "
                "(tenant_id,id,external_id,name,name_prefix,owner_user_id,owner_team_id,currency,"
                "timezone_id,auth_status,account_status,value_json,"
                "details_json,bound_at,created_at) "
                "VALUES(%s,%s,%s,'同步之前','同步之前',%s,%s,'USD','America/New_York',"
                "'UNKNOWN','UNKNOWN','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
                (tenant, account, external, owner_user_id, owner_team_id),
            )
        return account, external

    def enqueue(account, identity=headers):
        cap = client.get(
            f"/api/v1/accounts/{account}/actions/capabilities",
            headers=identity,
            params={"action": "SYNC"},
        )
        assert cap.status_code == 200
        result = client.post(
            f"/api/v1/accounts/{account}/sync",
            headers=identity
            | {
                "X-CSRF-Token": cap.json()["csrf_token"],
                "If-Match": f'"{cap.json()["revision"]}"',
                "Idempotency-Key": "account-sync-" + uuid4().hex,
            },
            json={"reason": "真实本机TLS同步协议专项"},
        )
        assert result.status_code == 202 and result.json()["state"] == "WAITING_EXECUTOR"
        return result.json()

    def row(account):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT id,state,attempt_count,last_error_code,next_attempt_at,claimed_at "
                "FROM orbit_account_command WHERE tenant_id=%s AND account_id=%s AND kind='SYNC' "
                "ORDER BY created_at DESC,id DESC LIMIT 1",
                (tenant, account),
            )
            command = cursor.fetchone()
            cursor.execute(
                "SELECT name,synced_at,revision,unbound_at,value_json "
                "FROM orbit_ad_account WHERE tenant_id=%s AND id=%s",
                (tenant, account),
            )
            value = cursor.fetchone()
        return command, value

    def force_due(account):
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_account_command "
                "SET next_attempt_at=UTC_TIMESTAMP(3)-INTERVAL 1 SECOND "
                "WHERE tenant_id=%s AND account_id=%s AND active_kind='SYNC'",
                (tenant, account),
            )

    async def checks(graph):
        engine = create_async_engine(url, echo=False)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        worker = AccountSyncWorker(
            sessions, cipher, {"USD"}, tenant, platform_factory=graph.factory
        )

        async def read(claim):
            reader = graph.factory(claim.configuration)
            reader.preflight = lambda: worker.preflight(claim)
            await reader.prepare((claim.external_id,))
            return await reader.fetch_metadata(claim.external_id)

        try:
            # 同一真实租户先前的动作专项可能留下等待任务；不能把processed=1当成本任务成功。
            # 旧来源已在工具开始明确停用。保留真实队列顺序，用同一Worker有界处理原有到期项，
            # 并核实其失败关闭而非跳队列/任意换Token；不强行提前尚未到期的重试。
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT id,state FROM orbit_account_command WHERE tenant_id=%s "
                    "AND kind='SYNC' AND active_kind='SYNC' "
                    "AND state IN ('WAITING_EXECUTOR','WAITING_RETRY') "
                    "AND (next_attempt_at IS NULL OR next_attempt_at<=UTC_TIMESTAMP(3)) "
                    "ORDER BY created_at,id",
                    (tenant,),
                )
                earlier = list(cursor.fetchall())
            print(f"ACCOUNT_SYNC_EXISTING_DUE_QUEUE_COUNT={len(earlier)}", flush=True)
            for _ in range((len(earlier) + 99) // 100 + 1):
                progress = await worker.run_once(limit=100)
                if not progress["processed"] and not progress["recovered"]:
                    break
            assert not graph.requests, "旧冻结来源不可用，处理历史等待任务不得发送HTTP"
            with admin.cursor() as cursor:
                for identifier, _state in earlier:
                    cursor.execute(
                        "SELECT state,active_kind,last_error_code FROM orbit_account_command "
                        "WHERE tenant_id=%s AND id=%s",
                        (tenant, identifier),
                    )
                    previous = cursor.fetchone()
                    assert previous[0] == "FAILED" and previous[1] is None and previous[2], (
                        "旧队列应真实失败关闭",
                        previous[0],
                        previous[1],
                        previous[2],
                    )
            account, graph.external_id = seed()
            enqueue(account)
            progress = await worker.run_once(limit=1)
            command, value = row(account)
            print(
                "ACCOUNT_SYNC_FIRST_SAFE="
                + json.dumps(
                    {
                        "processed": progress["processed"],
                        "initial_pending_count": len(earlier),
                        "target_state": command[1],
                        "attempt_count": command[2],
                        "last_error_code": command[3],
                        "graph_request_count": len(graph.requests),
                    }
                ),
                flush=True,
            )
            assert progress["processed"] == 1
            assert command[1:4] == ("SUCCEEDED", 1, None), (
                "目标同步命令安全状态",
                command[1],
                command[2],
                command[3],
                "原有可执行队列数量",
                len(earlier),
            )
            assert value[0] == "平台账户原名" and value[1] is not None and value[3] is None
            with admin.cursor() as cursor:
                cursor.execute("SELECT UTC_TIMESTAMP(6)")
                read_start = cursor.fetchone()[0].replace(tzinfo=UTC)
            public = client.get(f"/api/v1/accounts/{account}", headers=headers)
            extended = client.get(f"/api/v1/accounts/{account}/details", headers=headers)
            with admin.cursor() as cursor:
                cursor.execute("SELECT UTC_TIMESTAMP(6)")
                read_end = cursor.fetchone()[0].replace(tzinfo=UTC)

            def safe_code(response):
                try:
                    body = response.json()
                except ValueError:
                    return None
                code = body.get("code") if isinstance(body, dict) else None
                return (
                    code
                    if (
                        type(code) is int
                        or isinstance(code, str)
                        and re.fullmatch(r"[A-Z0-9_]{1,64}", code)
                    )
                    else None
                )

            print(
                "ACCOUNT_SYNC_READ_SAFE="
                + json.dumps(
                    {
                        "core_status": public.status_code,
                        "details_status": extended.status_code,
                        "core_error_code": safe_code(public),
                        "details_error_code": safe_code(extended),
                    }
                ),
                flush=True,
            )
            assert public.status_code == extended.status_code == 200
            core, enriched = public.json(), extended.json()["account"]
            keys = {
                "id",
                "external_id",
                "name",
                "ownership",
                "vendor_id",
                "vendor_alias",
                "currency",
                "timezone",
                "auth_status",
                "account_status",
                "spend",
                "balance",
                "revision",
                "synced_at",
            }
            assert set(core) == set(enriched) == keys
            timezone_keys = {"id", "display_label", "reference_at", "offset_at"}
            assert set(core["timezone"]) == set(enriched["timezone"]) == timezone_keys
            differences = sorted(
                [key for key in keys - {"timezone"} if core[key] != enriched[key]]
                + [
                    "timezone." + key
                    for key in timezone_keys
                    if core["timezone"][key] != enriched["timezone"][key]
                ]
            )
            print(
                "ACCOUNT_SYNC_CORE_DIFFERENCES=" + json.dumps({"differing_keys": differences}),
                flush=True,
            )
            assert set(differences) <= {"timezone.reference_at"}
            from datetime import datetime

            references = []
            for payload in (core, enriched):
                timezone = payload["timezone"]
                reference = datetime.fromisoformat(timezone["reference_at"].replace("Z", "+00:00"))
                assert reference.tzinfo is not None and timezone["reference_at"].endswith("Z")
                assert (
                    read_start - timedelta(milliseconds=1)
                    <= reference
                    <= read_end + timedelta(milliseconds=1)
                )
                assert timezone["id"] == "America/New_York"
                offset_seconds = int(
                    reference.astimezone(ZoneInfo(timezone["id"])).utcoffset().total_seconds()
                )
                assert offset_seconds % 60 == 0
                minutes = abs(offset_seconds) // 60
                offset = (
                    f"{'-' if offset_seconds < 0 else '+'}{minutes // 60:02d}:{minutes % 60:02d}"
                )
                assert timezone["offset_at"] == offset
                assert timezone["display_label"] == f"UTC{offset}（{timezone['id']}）"
                references.append(reference)
            spend_window = extended.json()["details"]["spend_window"]
            assert spend_window["reference_at"] == enriched["timezone"]["reference_at"]
            business_day = references[1].astimezone(ZoneInfo("America/New_York")).date().isoformat()
            assert spend_window["mode"] == "TODAY"
            assert spend_window["date_from"] == spend_window["date_to"] == business_day
            assert (
                public.json()["balance"]["amount"] is None
                and public.json()["spend"]["amount"] is None
            )
            assert all(
                method == "GET" and "access_token" not in path for method, path, _ in graph.requests
            )
            cases.append(CASES[0])

            account, graph.external_id = seed()
            enqueue(account)
            graph.mode, before = "rate", len(graph.requests)
            for attempt, seconds in ((1, 30), (2, 60), (3, 120), (4, None)):
                assert (await worker.run_once(limit=1))["processed"] == 1
                command, value = row(account)
                assert command[2] == attempt and value[1] is None
                assert command[1] == ("WAITING_RETRY" if seconds else "FAILED")
                if seconds:
                    with admin.cursor() as cursor:
                        cursor.execute(
                            "SELECT TIMESTAMPDIFF(SECOND,UTC_TIMESTAMP(3),next_attempt_at) "
                            "FROM orbit_account_command WHERE tenant_id=%s AND id=%s",
                            (tenant, command[0]),
                        )
                        remaining = cursor.fetchone()[0]
                    assert seconds - 5 <= remaining <= seconds
                    current_requests = len(graph.requests)
                    assert (await worker.run_once(limit=1))["processed"] == 0
                    assert len(graph.requests) == current_requests
                    force_due(account)
            assert len(graph.requests) == before + 4
            assert (await worker.run_once(limit=1))["processed"] == 0
            graph.mode = "normal"
            cases.append(CASES[1])

            account, graph.external_id = seed()
            enqueue(account)
            claim, consumed = await worker.claim()
            assert consumed and claim is not None
            result = await read(claim)
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET revision=revision+1 WHERE id=%s",
                    (source,),
                )
            assert await worker.complete(claim, result=result)
            assert row(account)[0][1:4] == ("FAILED", 1, "ACCOUNT_SYNC_SOURCE_CHANGED")
            assert row(account)[1][1] is None
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET revision=1 WHERE id=%s", (source,)
                )
            account, graph.external_id = seed()
            enqueue(account)
            claim, _ = await worker.claim()
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET enabled=0 WHERE id=%s", (source,)
                )
            before = len(graph.requests)
            try:
                await read(claim)
            except AccountReadFailure as failure:
                assert failure.code == "ACCOUNT_SYNC_SOURCE_CHANGED"
                await worker.complete(claim, failure=failure)
            else:
                raise AssertionError("失效冻结来源不能发送HTTP")
            assert len(graph.requests) == before and row(account)[1][1] is None
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET enabled=1 WHERE id=%s", (source,)
                )
            cases.append(CASES[2])

            account, graph.external_id = seed()
            enqueue(account)
            claim, _ = await worker.claim()
            result = await read(claim)
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_ad_account SET revision=revision+1,name='并发更新名' "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, account),
                )
            assert await worker.complete(claim, result=result)
            assert row(account)[0][3] == "ACCOUNT_SYNC_ACCOUNT_CHANGED"
            assert row(account)[1][0:2] == ("并发更新名", None)
            cases.append(CASES[3])

            account, graph.external_id = seed()
            enqueue(account)
            claim, _ = await worker.claim()
            result = await read(claim)
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_account_command "
                    "SET claimed_at=UTC_TIMESTAMP(3)-INTERVAL 121 SECOND "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, claim.command),
                )
            assert not await worker.complete(claim, result=result)
            before = len(graph.requests)
            assert (await worker.run_once(limit=1))["recovered"] == 1
            assert len(graph.requests) == before and row(account)[0][1] == "WAITING_RETRY"
            assert not await worker.complete(claim, result=result)
            force_due(account)
            await worker.run_once(limit=1)
            assert row(account)[0][1:3] == ("SUCCEEDED", 2)
            cases.append(CASES[4])

            account, graph.external_id = seed()
            enqueue(account, action_identity["headers"])
            claim, _ = await worker.claim()
            before = len(graph.requests)
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE sys_user SET status='1' WHERE user_id=%s",
                    (action_identity["actor_id"],),
                )
            try:
                try:
                    await read(claim)
                except AccountReadFailure as failure:
                    assert failure.code == "ACCOUNT_SYNC_AUTHORIZATION_CHANGED"
                    await worker.complete(claim, failure=failure)
                else:
                    raise AssertionError("已停用发起人员不能发送平台HTTP")
                assert len(graph.requests) == before and row(account)[1][1] is None
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE sys_user SET status='0' WHERE user_id=%s",
                        (action_identity["actor_id"],),
                    )
            cases.append(CASES[5])

            account, graph.external_id = seed()
            enqueue(account)
            claim, _ = await worker.claim()
            result = await read(claim)
            caps = client.get(
                f"/api/v1/accounts/{account}/actions/capabilities",
                headers=headers,
                params={"action": "UNBIND"},
            )
            unbound = client.post(
                f"/api/v1/accounts/{account}/unbind",
                headers=headers
                | {
                    "X-CSRF-Token": caps.json()["csrf_token"],
                    "If-Match": f'"{caps.json()["revision"]}"',
                    "Idempotency-Key": "sync-unbind-" + uuid4().hex,
                },
                json={"reason": "在途只读不能复活本地解绑"},
            )
            assert unbound.status_code == 200 and not await worker.complete(claim, result=result)
            assert row(account)[0][3] == "ACCOUNT_LOCALLY_UNBOUND"
            assert row(account)[1][1] is None and row(account)[1][3] is not None
            cases.append(CASES[6])

            account, graph.external_id = seed()
            enqueue(account)
            with admin.cursor() as cursor:
                cursor.execute(
                    "CREATE TRIGGER account_sync_audit_fail BEFORE INSERT ON orbit_account_event "
                    "FOR EACH ROW BEGIN IF NEW.action='ACCOUNT_METADATA_SYNCHRONIZED' THEN "
                    "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-only'; END IF; END"
                )
            try:
                try:
                    await worker.run_once(limit=1)
                except SQLAlchemyError:
                    pass
                else:
                    raise AssertionError("真实审计故障必须回滚元数据和终态")
            finally:
                with admin.cursor() as cursor:
                    cursor.execute("DROP TRIGGER IF EXISTS account_sync_audit_fail")
            command, value = row(account)
            assert command[1] == "RUNNING" and value[0:2] == ("同步之前", None)
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_account_event "
                    "WHERE tenant_id=%s AND resource_id=%s "
                    "AND action='ACCOUNT_METADATA_SYNCHRONIZED'",
                    (tenant, account),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "UPDATE orbit_account_command "
                    "SET claimed_at=UTC_TIMESTAMP(3)-INTERVAL 121 SECOND "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, command[0]),
                )
            await worker.run_once(limit=1)
            force_due(account)
            await worker.run_once(limit=1)
            assert row(account)[0][1] == "SUCCEEDED"
            cases.append(CASES[7])

            account, graph.external_id = seed()
            enqueue(account)
            claim, _ = await worker.claim()
            result = await read(claim)
            assert await worker.complete(claim, result=result | {"timezone_id": "UTC"})
            assert row(account)[0][3] == "ACCOUNT_METADATA_RECONCILIATION_REQUIRED"
            assert row(account)[1][1] is None
            cases.append(CASES[8])
        finally:
            await engine.dispose()

    try:
        with (
            tempfile.TemporaryDirectory(prefix="orbit-sync-graph-") as directory,
            local_graph(Path(directory)) as graph,
        ):
            asyncio.run(checks(graph))
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS account_sync_audit_fail")
            cursor.execute("UPDATE orbit_system_configuration SET enabled=0 WHERE id=%s", (source,))
            for previous in prior_sources:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET enabled=1 WHERE id=%s", (previous,)
                )
