"""命令状态真实HTTP/MySQL专项；仅主线隔离库串行调用，不访问平台。"""

import json
import re
from uuid import uuid4

CASES = [
    "pythonAccountCommandOwnActualUnbindAckAndStrictDiagnostic",
    "pythonAccountCommandOriginalIdempotentAckUnchanged",
    "pythonAccountCommandOtherActorWrongAccountKindRequestHidden",
    "pythonAccountCommandStrictQueryAndNoTargetTenant",
    "pythonAccountCommandCurrentOwnerTransferAndImmediateRevocation",
    "pythonAccountCommandUnknownErrorNullAndRealUtcState",
    "pythonAccountCommandDuplicateCorrelationFailsClosed",
    "pythonAccountCommandCompositeIndexExplain",
    "pythonAccountCommandActionPermissionRevokedImmediately",
    "pythonAccountCommandDueProjectionGuardNotBypassed",
]


def run_account_command_checks(
    client, admin, headers, owner_user_id, owner_team_id, action_identity, database, cases
):
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("命令诊断只允许本轮独占MySQL夹具")
    account, key = str(uuid4()), "diagnostic-" + uuid4().hex
    actor = action_identity["actor_id"]
    action_headers = action_identity["headers"]
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE id=%s", (owner_user_id,))
        tenant = cursor.fetchone()[0]
        cursor.execute(
            "SELECT id,team_id FROM orbit_business_user WHERE tenant_id=%s AND user_id=%s",
            (tenant, actor),
        )
        subject, team = cursor.fetchone()
        assert team == owner_team_id and subject != owner_user_id
        cursor.execute(
            "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
            "owner_user_id,owner_team_id,currency,timezone_id,auth_status,account_status,"
            "value_json,details_json,bound_at,created_at) "
            "VALUES(%s,%s,%s,'命令本人诊断','命令本人诊断',%s,%s,'USD','Asia/Shanghai',"
            "'AUTHORIZED','ACTIVE','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (tenant, account, str(10**24 + uuid4().int % 10**24), subject, team),
        )
    admin.commit()
    base = f"/api/v1/accounts/{account}"
    cap = client.get(base + "/actions/capabilities?action=UNBIND", headers=action_headers)
    assert cap.status_code == 200
    write_headers = action_headers | {
        "X-CSRF-Token": cap.json()["csrf_token"],
        "If-Match": f'"{cap.json()["revision"]}"',
        "Idempotency-Key": key,
    }
    accepted = client.post(
        base + "/unbind", headers=write_headers, json={"reason": "隔离库命令诊断受理"}
    )
    assert accepted.status_code == 200
    ack = accepted.json()
    query = {"kind": "UNBIND", "request_id": ack["request_id"]}

    def get(*, identity=action_headers, params=None, path=base):
        return client.get(
            path + "/actions/status", params=query if params is None else params, headers=identity
        )

    response = get()
    assert response.status_code == 200
    value = response.json()
    assert set(value) == {
        "command_id",
        "account_id",
        "kind",
        "accepted_request_id",
        "revision",
        "state",
        "attempt_count",
        "last_error_code",
        "effective_from",
        "next_attempt_at",
        "created_at",
        "updated_at",
        "completed_at",
    }
    assert value["account_id"] == account and value["accepted_request_id"] == ack["request_id"]
    assert value["kind"] == "UNBIND" and value["state"] == "SUCCEEDED"
    assert value["attempt_count"] == 0 and value["completed_at"] is not None
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get("x-request-id")
    cases.append(CASES[0])

    replay = client.post(
        base + "/unbind", headers=write_headers, json={"reason": "隔离库命令诊断受理"}
    )
    assert replay.status_code == 200 and replay.json() == ack
    assert get().json() == value
    cases.append(CASES[1])

    assert get(identity=headers).status_code == 404  # SUPER可见账户也不能读他人命令。
    assert get(params=query | {"kind": "SYNC"}).status_code == 404
    assert get(params=query | {"request_id": str(uuid4())}).status_code == 404
    assert get(path=f"/api/v1/accounts/{uuid4()}").status_code == 404
    cases.append(CASES[2])

    for params, code in [
        ({"kind": "UNBIND"}, 422),
        (query | {"kind": "QUEUED"}, 422),
        (query | {"owner_user_id": subject}, 400),
        (query | {"request_id": "invalid"}, 422),
    ]:
        assert get(params=params).status_code == code
    assert (
        get(
            params=[("kind", "UNBIND"), ("kind", "SYNC"), ("request_id", ack["request_id"])]
        ).status_code
        == 400
    )
    assert get(identity=action_headers | {"X-Target-Tenant": str(uuid4())}).status_code == 403
    cases.append(CASES[3])

    # 仅隔离夹具暂改实时角色/当前owner；结束恢复，绝不创建历史读权限例外。
    with admin.cursor() as cursor:
        cursor.execute("SELECT data_role FROM orbit_user_scope WHERE user_id=%s", (actor,))
        original_role = cursor.fetchone()[0]
        cursor.execute("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=%s", (actor,))
        cursor.execute(
            "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
            (owner_user_id, tenant, account),
        )
    admin.commit()
    try:
        assert get().status_code == 404
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
                (subject, tenant, account),
            )
            cursor.execute("UPDATE sys_user SET status='1' WHERE user_id=%s", (actor,))
        admin.commit()
        assert get().status_code in {401, 403}
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_user_scope SET data_role=%s WHERE user_id=%s", (original_role, actor)
            )
            cursor.execute("UPDATE sys_user SET status='0' WHERE user_id=%s", (actor,))
            cursor.execute(
                "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
                (subject, tenant, account),
            )
        admin.commit()
    assert get().status_code == 200
    cases.append(CASES[4])

    command = value["command_id"]
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_account_command SET last_error_code=%s WHERE tenant_id=%s AND id=%s",
            ("UNRECOGNIZED_PRIVATE_DIAGNOSTIC", tenant, command),
        )
    admin.commit()
    assert get().json()["last_error_code"] is None
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT created_at,updated_at,completed_at FROM orbit_account_command "
            "WHERE tenant_id=%s AND id=%s",
            (tenant, command),
        )
        times = cursor.fetchone()
        cursor.execute(
            "UPDATE orbit_account_command SET last_error_code=NULL WHERE tenant_id=%s AND id=%s",
            (tenant, command),
        )
    admin.commit()
    for field, instant in zip(("created_at", "updated_at", "completed_at"), times, strict=True):
        assert value[field] == instant.isoformat(timespec="milliseconds") + "Z"
    cases.append(CASES[5])

    duplicate = str(uuid4())
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbit_account_command(tenant_id,id,account_id,kind,state,revision,"
            "actor_id,actor_subject_id,request_key,request_hash,request_id,accepted_account_revision,"
            "source_json,payload_json,response_json,created_at,updated_at,completed_at) "
            "SELECT tenant_id,%s,account_id,kind,state,revision,actor_id,actor_subject_id,%s,"
            "request_hash,request_id,accepted_account_revision,source_json,payload_json,response_json,"
            "created_at,updated_at,completed_at FROM orbit_account_command "
            "WHERE tenant_id=%s AND id=%s",
            (duplicate, "diagnostic-duplicate-" + uuid4().hex, tenant, command),
        )
    admin.commit()
    try:
        result = get()
        assert result.status_code == 503
        assert result.json()["code"] == "ACCOUNT_COMMAND_DIAGNOSTIC_UNAVAILABLE"
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM orbit_account_command WHERE tenant_id=%s AND id=%s",
                (tenant, duplicate),
            )
        admin.commit()
    assert get().json() == value
    cases.append(CASES[6])

    with admin.cursor() as cursor:
        cursor.execute(
            "EXPLAIN FORMAT=JSON SELECT id FROM orbit_account_command WHERE "
            "tenant_id=%s AND actor_id=%s AND actor_subject_id=%s AND account_id=%s "
            "AND kind=%s AND request_id=%s LIMIT 2",
            (tenant, actor, subject, account, "UNBIND", ack["request_id"]),
        )
        plan = json.loads(cursor.fetchone()[0])
    assert "idx_account_command_diagnostic" in json.dumps(plan)
    cases.append(CASES[7])

    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT rm.role_id FROM sys_role_menu rm JOIN sys_user_role ur "
            "ON ur.role_id=rm.role_id WHERE ur.user_id=%s AND rm.menu_id=31015",
            (actor,),
        )
        native_roles = [record[0] for record in cursor.fetchall()]
        assert native_roles
        for role in native_roles:
            cursor.execute("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31015", (role,))
    admin.commit()
    try:
        assert get().status_code == 403
    finally:
        with admin.cursor() as cursor:
            for role in native_roles:
                cursor.execute(
                    "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,31015)", (role,)
                )
        admin.commit()
    assert get().status_code == 200
    cases.append(CASES[8])

    # 仅受控持久状态故障注入，证明诊断沿现有guard；不冒充实际分配受理/跨日。
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_account_command SET kind='ASSIGNMENT',active_kind='ASSIGNMENT',"
            "state='BLOCKED',effective_from=UTC_TIMESTAMP(3)-INTERVAL 1 SECOND "
            "WHERE tenant_id=%s AND id=%s",
            (tenant, command),
        )
    admin.commit()
    try:
        result = get(params=query | {"kind": "ASSIGNMENT"})
        assert result.status_code == 503
        assert result.json()["code"] == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_account_command SET kind='UNBIND',active_kind=NULL,"
                "state='SUCCEEDED',effective_from=NULL WHERE tenant_id=%s AND id=%s",
                (tenant, command),
            )
        admin.commit()
    assert get().json() == value
    cases.append(CASES[9])
