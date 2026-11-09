"""028原动作真实本地协议：受控时钟推进不等于真实日历跨日，不访问Graph或广告写入。"""

import asyncio
import json
import re
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

CASES = [
    "pythonAccountActionsCapabilitiesExactAndOriginalWriteHeadersGuarded",
    "pythonAccountAssignmentAcceptsFutureIntervalAndLeavesCurrentOwnerUnchanged",
    "pythonAccountAssignmentReplayAndPendingOrStaleRequestsDoNotRewriteHistory",
    "pythonAccountAssignmentRejectsNonBoundaryWithoutPartialChanges",
    "pythonAccountAssignmentDueGuardAndControlledActivationFreezeAliasTwice",
    "pythonAccountActionsOnlyRoleNeedsNoReadOrImportForOriginalAction",
    "pythonAccountAssignmentRevokedActorBlocksAndExplicitRecoveryRechecks",
    "pythonAccountAssignmentAcceptAuditFailureRollsBackIntervalAliasAndCommand",
    "pythonAccountAssignmentActivationAuditFailureRollsBackProjectionAndState",
    "pythonAccountSyncMissingOrAmbiguousSourceCannotGuessToken",
    "pythonAccountSyncPersistsWaitingExecutorWithoutFakeObservedSuccess",
    "pythonAccountLocalUnbindPreservesPlatformAndHistoryAndStopsQueuedRead",
]


def run_account_actions_checks(
    client,
    admin,
    headers,
    owner_user_id,
    owner_team_id,
    vendor_id,
    target_identity,
    action_identity,
    database,
    cases,
    cipher,
):
    """action_identity为actions-only TEAM_ADMIN且显式管理本轮团队，人员/来源由主线真实准备。"""
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("账户动作专项只允许本轮独立MySQL夹具")
    from orbit_api.account_actions_store import require_projection_current
    from orbit_api.account_actions_worker import AccountActionsWorker
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
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE id=%s", (owner_user_id,))
        tenant = cursor.fetchone()[0]
    accounts = [str(uuid4()) for _ in range(5)]
    for index, account in enumerate(accounts):
        zone = "America/New_York" if index == 0 else "Asia/Shanghai"
        start = (
            datetime.now(UTC)
            .astimezone(ZoneInfo(zone))
            .replace(hour=0, minute=0, second=0, microsecond=0)
        )
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_ad_account "
                "(tenant_id,id,external_id,name,name_prefix,owner_user_id,owner_team_id,vendor_id,"
                "currency,timezone_id,auth_status,account_status,value_json,details_json,"
                "bound_at,created_at) "
                "VALUES(%s,%s,%s,'动作受控','动作受控',%s,%s,%s,'USD',%s,'AUTHORIZED','ACTIVE',"
                "'{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
                (
                    tenant,
                    account,
                    str(10**22 + uuid4().int % 10**22),
                    owner_user_id,
                    owner_team_id,
                    vendor_id,
                    zone,
                ),
            )
            cursor.execute(
                "INSERT INTO orbit_account_assignment "
                "(tenant_id,id,account_id,owner_user_id,owner_team_id,vendor_id,starts_at,reason) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,'本轮受控初始绑定')",
                (
                    tenant,
                    str(uuid4()),
                    account,
                    owner_user_id,
                    owner_team_id,
                    vendor_id,
                    start.astimezone(UTC).replace(tzinfo=None),
                ),
            )

    def caps(account, kind, identity=headers):
        result = client.get(
            f"/api/v1/accounts/{account}/actions/capabilities",
            headers=identity,
            params={"action": kind},
        )
        assert result.status_code == 200, (result.status_code, result.json().get("code"))
        assert set(result.json()) == {"csrf_token", "revision", "next_effective_from"}
        assert result.headers["cache-control"] == "no-store" and result.headers.get("x-request-id")
        return result.json()

    def send(account, kind, value, *, key=None, capability=None, identity=headers):
        capability = capability or caps(account, kind, identity)
        path = {"ASSIGNMENT": "assignment", "SYNC": "sync", "UNBIND": "unbind"}[kind]
        method = client.put if kind == "ASSIGNMENT" else client.post
        return method(
            f"/api/v1/accounts/{account}/{path}",
            headers=identity
            | {
                "X-CSRF-Token": capability["csrf_token"],
                "If-Match": f'"{capability["revision"]}"',
                "Idempotency-Key": key or "account-action-" + uuid4().hex,
            },
            json=value,
        )

    def assignment(capability):
        return {
            "operator_user_id": target_identity["owner_user_id"],
            "owner_team_id": target_identity["owner_team_id"],
            "vendor_id": vendor_id,
            "effective_from": capability["next_effective_from"],
            "reason": "本轮受控分配",
        }

    def state(account):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT owner_user_id,owner_team_id,vendor_id,revision,unbound_at,synced_at "
                "FROM orbit_ad_account WHERE tenant_id=%s AND id=%s",
                (tenant, account),
            )
            return cursor.fetchone()

    def totals():
        result = []
        with admin.cursor() as cursor:
            for table in (
                "orbit_account_command",
                "orbit_account_assignment",
                "orbit_account_event",
                "orbit_account_outbox",
                "orbit_account_vendor_alias_snapshot",
            ):
                cursor.execute("SELECT COUNT(*) FROM " + table)
                result.append(cursor.fetchone()[0])
            cursor.execute("SELECT revision FROM orbit_account_clock WHERE tenant_id=%s", (tenant,))
            result.append(cursor.fetchone()[0])
        return result

    async def advance(now, *, blocked=False, guard=None):
        engine = create_async_engine(url, echo=False)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session, session.begin():
                if guard:
                    return await require_projection_current(session, tenant, guard, now)
                return await AccountActionsWorker().advance_due(
                    session, tenant, now=now, include_blocked=blocked
                )
        finally:
            await engine.dispose()

    cap = caps(accounts[0], "ASSIGNMENT")
    assert cap["next_effective_from"]
    assert caps(accounts[0], "SYNC")["next_effective_from"] is None
    assert (
        client.get(
            f"/api/v1/accounts/{accounts[0]}/actions/capabilities",
            headers=headers,
            params={"action": "unknown"},
        ).status_code
        == 422
    )
    invalid = client.post(
        f"/api/v1/accounts/{accounts[0]}/unbind", headers=headers, json={"reason": "控"}
    )
    assert invalid.status_code == 403
    cases.append(CASES[0])
    alias_caps = client.get("/api/v1/vendor-aliases/capabilities", headers=headers)
    assert alias_caps.status_code == 200
    alias_path = "/api/v1/vendor-aliases/" + vendor_id
    old_alias = client.get(alias_path, headers=headers).json()["alias"]

    def alias(value):
        original = client.get(alias_path, headers=headers)
        result = client.put(
            alias_path,
            headers=headers
            | {
                "X-CSRF-Token": alias_caps.json()["csrf_token"],
                "Idempotency-Key": str(uuid4()),
                "If-Match": f'"{original.json()["revision"]}"',
            },
            json={"alias": value, "reason": "本轮账户动作快照验收"},
        )
        assert result.status_code == 200

    try:
        alias("受理时真实代称")
        key = "assignment-replay-" + uuid4().hex
        body = assignment(cap)
        accepted = send(accounts[0], "ASSIGNMENT", body, key=key, capability=cap)
        assert accepted.status_code == 200 and accepted.json()["state"] == "SCHEDULED"
        assert set(accepted.json()) == {"id", "revision", "state", "request_id"}
        assert state(accounts[0])[0] == owner_user_id
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT id,owner_user_id,starts_at,ends_at FROM orbit_account_assignment "
                "WHERE tenant_id=%s AND account_id=%s ORDER BY starts_at",
                (tenant, accounts[0]),
            )
            intervals = cursor.fetchall()
        assert len(intervals) == 2 and intervals[0][3] == intervals[1][2]
        assert intervals[1][1] == target_identity["owner_user_id"]
        cases.append(CASES[1])
        assert (
            send(accounts[0], "ASSIGNMENT", body, key=key, capability=cap).json() == accepted.json()
        )
        assert (
            send(
                accounts[0], "ASSIGNMENT", body | {"reason": "不同"}, key=key, capability=cap
            ).status_code
            == 409
        )
        assert send(accounts[0], "UNBIND", {"reason": "不能覆盖未来分配"}).status_code == 409
        cases.append(CASES[2])
        wrong = caps(accounts[1], "ASSIGNMENT")
        before = totals()
        from datetime import timedelta

        wrong_body = assignment(wrong)
        wrong_body["effective_from"] = (
            datetime.fromisoformat(wrong_body["effective_from"].replace("Z", "+00:00"))
            + timedelta(seconds=1)
        ).isoformat()
        assert send(accounts[1], "ASSIGNMENT", wrong_body, capability=wrong).status_code == 422
        assert totals() == before
        cases.append(CASES[3])
        due = datetime.fromisoformat(body["effective_from"].replace("Z", "+00:00"))
        try:
            asyncio.run(advance(due, guard=accounts[0]))
        except OrbitError as error:
            assert error.code == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG" and error.status == 503
        else:
            raise AssertionError("到期未追平必须失败关闭")
        alias("激活时真实代称")
        assert asyncio.run(advance(due))["activated"] == 1
        assert state(accounts[0])[0] == target_identity["owner_user_id"]
        assert asyncio.run(advance(due))["activated"] == 0
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT resource_revision,alias FROM orbit_account_vendor_alias_snapshot "
                "WHERE tenant_id=%s AND resource_type='ASSIGNMENT' AND resource_id=%s "
                "ORDER BY resource_revision",
                (tenant, intervals[1][0]),
            )
            assert list(cursor.fetchall()) == [(1, "受理时真实代称"), (2, "激活时真实代称")]
        cases.append(CASES[4])
        action_headers = action_identity["headers"]
        assert client.get("/api/v1/accounts/extended", headers=action_headers).status_code == 403
        assert (
            client.get("/api/v1/account-imports/capabilities", headers=action_headers).status_code
            == 403
        )
        action_cap = caps(accounts[1], "ASSIGNMENT", action_headers)
        only = send(
            accounts[1],
            "ASSIGNMENT",
            assignment(action_cap),
            identity=action_headers,
            capability=action_cap,
        )
        assert only.status_code == 200 and only.json()["state"] == "SCHEDULED"
        cases.append(CASES[5])
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE sys_user SET status='1' WHERE user_id=%s", (action_identity["actor_id"],)
            )
        action_due = datetime.fromisoformat(
            action_cap["next_effective_from"].replace("Z", "+00:00")
        )
        try:
            assert asyncio.run(advance(action_due))["blocked"] == 1
            assert state(accounts[1])[0] == owner_user_id
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE sys_user SET status='0' WHERE user_id=%s",
                    (action_identity["actor_id"],),
                )
        assert asyncio.run(advance(action_due))["activated"] == 0
        assert asyncio.run(advance(action_due, blocked=True))["activated"] == 1
        cases.append(CASES[6])
        for phase, account in (("SCHEDULED", accounts[2]), ("ACTIVATED", accounts[3])):
            current_cap = caps(account, "ASSIGNMENT")
            current_body = assignment(current_cap)
            if phase == "ACTIVATED":
                assert (
                    send(account, "ASSIGNMENT", current_body, capability=current_cap).status_code
                    == 200
                )
            before, old_state = totals(), state(account)
            with admin.cursor() as cursor:
                cursor.execute(
                    "CREATE TRIGGER account_action_audit_fail BEFORE INSERT ON orbit_account_event "
                    "FOR EACH ROW BEGIN IF NEW.action=%s THEN "
                    "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-only'; END IF; END",
                    ("ACCOUNT_ASSIGNMENT_" + phase,),
                )
            try:
                if phase == "SCHEDULED":
                    assert (
                        send(
                            account, "ASSIGNMENT", current_body, capability=current_cap
                        ).status_code
                        == 503
                    )
                else:
                    from sqlalchemy.exc import SQLAlchemyError

                    try:
                        asyncio.run(
                            advance(
                                datetime.fromisoformat(
                                    current_body["effective_from"].replace("Z", "+00:00")
                                )
                            )
                        )
                    except SQLAlchemyError:
                        pass
                    else:
                        raise AssertionError("激活审计失败必须向外回滚")
                assert state(account) == old_state and totals() == before
            finally:
                with admin.cursor() as cursor:
                    cursor.execute("DROP TRIGGER IF EXISTS account_action_audit_fail")
            if phase == "ACTIVATED":
                assert (
                    asyncio.run(
                        advance(
                            datetime.fromisoformat(
                                current_body["effective_from"].replace("Z", "+00:00")
                            )
                        )
                    )["activated"]
                    == 1
                )
            cases.append(CASES[7 if phase == "SCHEDULED" else 8])
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS account_action_audit_fail")
        alias(old_alias)

    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM orbit_system_configuration WHERE tenant_id=%s "
            "AND section='META_BM' AND enabled=1",
            (tenant,),
        )
        original_sources = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            "UPDATE orbit_system_configuration SET enabled=0 "
            "WHERE tenant_id=%s AND section='META_BM'",
            (tenant,),
        )
    sources = [str(uuid4()), str(uuid4())]
    try:
        assert send(accounts[4], "SYNC", {"reason": "来源缺失"}).status_code == 503
        with admin.cursor() as cursor:
            for source in sources:
                cursor.execute(
                    "INSERT INTO orbit_system_configuration "
                    "(id,tenant_id,section,name,enabled,revision,settings_json,"
                    "secrets_json,verification_status) "
                    "VALUES(%s,%s,'META_BM',%s,1,1,%s,%s,'READ_VERIFIED')",
                    (
                        source,
                        tenant,
                        "只读任务受控来源-" + source,
                        json.dumps({"businessId": "42", "graphVersion": "v25.0"}),
                        json.dumps(
                            {
                                "accessToken": cipher.encrypt(
                                    "fixture-token-not-real", tenant, source, "accessToken"
                                )
                            }
                        ),
                    ),
                )
        assert send(accounts[4], "SYNC", {"reason": "来源歧义"}).status_code == 503
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_system_configuration SET enabled=0 WHERE id=%s", (sources[1],)
            )
        cases.append(CASES[9])
        previous = state(accounts[4])
        queued = send(accounts[4], "SYNC", {"reason": "真实持久只读排队"})
        assert queued.status_code == 202 and queued.json()["state"] == "WAITING_EXECUTOR"
        assert state(accounts[4])[5] == previous[5]
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,last_error_code FROM orbit_account_command WHERE tenant_id=%s "
                "AND account_id=%s AND kind='SYNC'",
                (tenant, accounts[4]),
            )
            assert cursor.fetchone() == ("WAITING_EXECUTOR", "ACCOUNT_SYNC_EXECUTOR_UNCONFIGURED")
        cases.append(CASES[10])
        unbound = send(accounts[4], "UNBIND", {"reason": "本地解绑不删除平台广告"})
        assert unbound.status_code == 200 and unbound.json()["state"] == "SUCCEEDED"
        assert state(accounts[4])[4] is not None
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT state,active_kind,last_error_code FROM orbit_account_command "
                "WHERE tenant_id=%s AND account_id=%s AND kind='SYNC'",
                (tenant, accounts[4]),
            )
            assert cursor.fetchone() == ("FAILED", None, "ACCOUNT_LOCALLY_UNBOUND")
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_account_assignment "
                "WHERE tenant_id=%s AND account_id=%s",
                (tenant, accounts[4]),
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT auth_status,account_status FROM orbit_ad_account "
                "WHERE tenant_id=%s AND id=%s",
                (tenant, accounts[4]),
            )
            assert cursor.fetchone() == ("AUTHORIZED", "ACTIVE")
        cases.append(CASES[11])
    finally:
        with admin.cursor() as cursor:
            for source in sources:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET enabled=0 WHERE id=%s", (source,)
                )
            for source in original_sources:
                cursor.execute(
                    "UPDATE orbit_system_configuration SET enabled=1 WHERE id=%s", (source,)
                )
