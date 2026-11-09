"""066关联登记真实HTTP专项；无Profile探测/登录/广告执行声明。"""

from uuid import uuid4

from fixture_login import fixture_login
from rule_definition_checks import guard_rule_target

PROFILE_BINDING_CASES = [
    "pythonProfileBindingOriginalFieldsUnknownAndCurrentAccountOwner",
    "pythonProfileBindingSameKeyReplayAndCasAtomicity",
    "pythonProfileBindingNonAdminReadWithoutAccountsReadAndNoWrite",
    "pythonProfileBindingCurrentOwnerChangeHidesOldAndAdminRepairs",
    "pythonProfileBindingRevokedAgentHiddenAndAdminCanMove",
    "pythonProfileBindingUnbindCurrent404AndOriginalReceiptReplay",
    "pythonProfileBindingMultipleProfilesAndCursorBoundedCurrentScope",
    "pythonProfileBindingOutboxFailureRollsBackAllChanges",
    "pythonProfileBindingCurrentRevocationRejectsReadsAndWrites",
]


def run_profile_binding_checks(client, admin, headers, database, password, cache, cases):
    guard_rule_target(admin, database)

    def sql(statement, values=(), fetch=False):
        with admin.cursor() as cursor:
            cursor.execute(statement, values)
            result = cursor.fetchall() if fetch else cursor.rowcount
        admin.commit()
        return result

    def checked(response, status=200):
        assert response.status_code == status, (
            response.request.url.path,
            response.status_code,
            response.text[:400],
        )
        return response.json()

    tenant, root_owner, team = sql(
        "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1", fetch=True
    )[0]
    cap = checked(client.get("/api/v1/roles/capabilities", headers=headers))
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "环境关联只读" + uuid4().hex[:8],
                "menu_codes": ["environments"],
                "permission_codes": ["environments.read", "environments.enroll"],
            },
        ),
        201,
    )
    native_role = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
        True,
    )[0][0]
    native, owner, name = 990790, str(uuid4()), "profile_" + uuid4().hex[:12]
    sql(
        "INSERT INTO sys_user(user_id,user_name,nick_name,password,status,del_flag) "
        "SELECT %s,%s,%s,password,'0','0' FROM sys_user WHERE user_id=1",
        (native, name, name),
    )
    sql(
        "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
        "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
        (native, str(uuid4())),
    )
    sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, native_role))
    sql(
        "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
        (native, tenant),
    )
    sql(
        "INSERT INTO orbit_business_user"
        "(tenant_id,id,user_id,team_id,display_name,invited,created_at) "
        "VALUES(%s,%s,%s,%s,%s,0,UTC_TIMESTAMP(3))",
        (tenant, owner, native, team, name),
    )
    login = checked(fixture_login(client, cache, {"username": name, "password": password}))
    user = {"Authorization": "Bearer " + login["token"]}
    capabilities = checked(
        client.get(
            "/api/v1/execution-agents/capabilities", headers=headers, params={"operation": "ENROLL"}
        )
    )

    def write(revision=None, key=None):
        return (
            headers
            | {"X-CSRF-Token": capabilities["csrf_token"], "Idempotency-Key": key or str(uuid4())}
            | ({"If-Match": f'"{revision}"'} if revision else {})
        )

    def agent():
        return checked(
            client.post(
                "/api/v1/execution-agents",
                headers=write(),
                json={
                    "name": "关联专项设备" + uuid4().hex[:8],
                    "endpoint": "http://127.0.0.1:50325",
                    "probe_interval": 15,
                },
            ),
            201,
        )

    first_agent, second_agent = agent(), agent()
    account = str(uuid4())
    sql(
        "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
        "owner_team_id,currency,timezone_id,auth_status,account_status,value_json,details_json,"
        "bound_at,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'USD','UTC','AUTHORIZED',"
        "'ACTIVE','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
        (tenant, account, str(10**25 + uuid4().int % 10**24), name, name, owner, team),
    )
    body = {
        "account_id": account,
        "agent_id": first_agent["id"],
        "profile_external_id": "登记非探测",
        "ownership": {"owner_user_id": owner, "owner_team_id": team},
    }
    base = "/api/v1/profile-bindings"
    original_headers = write()
    created = checked(client.post(base, headers=original_headers, json=body), 201)
    assert created == body | {
        "id": created["id"],
        "revision": 1,
        "identity_state": "UNKNOWN",
        "verified_at": None,
    }
    path = base + "/" + created["id"]
    assert checked(client.get(path, headers=headers)) == created
    invalid = body | {"identity_state": "VALID"}
    checked(client.post(base, headers=write(), json=invalid), 400)
    checked(
        client.post(
            base,
            headers=write(),
            json=body | {"ownership": {"owner_user_id": root_owner, "owner_team_id": team}},
        ),
        422,
    )
    cases.append(PROFILE_BINDING_CASES[0])

    def snapshot():
        values = []
        for table in (
            "orbit_profile_binding",
            "orbit_execution_agent_idempotency",
            "orbit_execution_agent_event",
            "orbit_execution_agent_outbox",
        ):
            values.append(
                sql(f"SELECT COUNT(*) FROM {table} WHERE tenant_id=%s", (tenant,), True)[0][0]
            )
        values.append(
            sql(
                "SELECT revision FROM orbit_execution_agent_clock WHERE tenant_id=%s",
                (tenant,),
                True,
            )[0][0]
        )
        return values

    before = snapshot()
    assert checked(client.post(base, headers=original_headers, json=body), 201) == created
    assert snapshot() == before
    checked(client.post(base, headers=write(), json=body), 409)
    updated_body = body | {"profile_external_id": "登记修改"}
    updated_headers = write(1)
    updated = checked(client.put(path, headers=updated_headers, json=updated_body))
    assert updated["revision"] == 2
    before = snapshot()
    assert checked(client.put(path, headers=updated_headers, json=updated_body)) == updated
    checked(client.put(path, headers=write(1), json=body), 409)
    assert snapshot() == before
    cases.append(PROFILE_BINDING_CASES[1])
    assert checked(client.get(path, headers=user)) == updated
    checked(client.get("/api/v1/accounts", headers=user), 403)
    checked(
        client.get(
            "/api/v1/execution-agents/capabilities", headers=user, params={"operation": "ENROLL"}
        ),
        403,
    )
    checked(
        client.post(
            base,
            headers=user
            | {"X-CSRF-Token": capabilities["csrf_token"], "Idempotency-Key": str(uuid4())},
            json=body,
        ),
        403,
    )
    assert snapshot() == before
    cases.append(PROFILE_BINDING_CASES[2])

    sql(
        "UPDATE orbit_ad_account SET owner_user_id=%s,revision=revision+1 "
        "WHERE tenant_id=%s AND id=%s",
        (root_owner, tenant, account),
    )
    sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    checked(client.get(path, headers=user), 404)
    checked(client.get(path, headers=headers))
    repair_body = updated_body | {"ownership": {"owner_user_id": root_owner, "owner_team_id": team}}
    updated = checked(client.put(path, headers=write(2), json=repair_body))
    assert updated["revision"] == 3 and updated["identity_state"] == "UNKNOWN"
    cases.append(PROFILE_BINDING_CASES[3])
    revoke_caps = checked(
        client.get(
            "/api/v1/execution-agents/capabilities", headers=headers, params={"operation": "REVOKE"}
        )
    )
    checked(
        client.post(
            "/api/v1/execution-agents/" + first_agent["id"] + "/revoke",
            headers=write(first_agent["revision"]) | {"X-CSRF-Token": revoke_caps["csrf_token"]},
            json={"reason": "专项撤销"},
        )
    )
    checked(client.get(path, headers=headers))
    checked(client.put(path, headers=write(3), json=repair_body), 409)
    repair_body |= {"agent_id": second_agent["id"]}
    moved = checked(client.put(path, headers=write(3), json=repair_body))
    assert moved["revision"] == 4
    cases.append(PROFILE_BINDING_CASES[4])
    unbind_headers, reason = write(4), {"reason": "专项解绑"}
    receipt = checked(client.post(path + "/unbind", headers=unbind_headers, json=reason))
    assert set(receipt) == {"id", "revision", "unbound_at"} and receipt["revision"] == 5
    checked(client.get(path, headers=headers), 404)
    before = snapshot()
    assert checked(client.post(path + "/unbind", headers=unbind_headers, json=reason)) == receipt
    assert snapshot() == before
    cases.append(PROFILE_BINDING_CASES[5])
    for i in range(21):
        checked(
            client.post(
                base,
                headers=write(),
                json=repair_body | {"profile_external_id": "分页Profile" + str(i)},
            ),
            201,
        )
    page = checked(client.get(base, headers=headers, params={"page_size": 20}))
    assert len(page["items"]) == 20 and page["next_cursor"]
    second = checked(
        client.get(base, headers=headers, params={"page_size": 20, "cursor": page["next_cursor"]})
    )
    assert not ({r["id"] for r in page["items"]} & {r["id"] for r in second["items"]})
    checked(
        client.get(base, headers=user, params={"page_size": 20, "cursor": page["next_cursor"]}), 409
    )
    assert checked(client.get(base, headers=user))["items"] == []
    cases.append(PROFILE_BINDING_CASES[6])
    trigger = "profile_binding_outbox_fault_" + uuid4().hex
    before = snapshot()
    try:
        sql(
            f"CREATE TRIGGER {trigger} BEFORE INSERT ON orbit_execution_agent_outbox "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROFILE_BINDING_FIXTURE_OUTBOX'"
        )
        checked(
            client.post(
                base, headers=write(), json=repair_body | {"profile_external_id": "回滚Profile"}
            ),
            503,
        )
    finally:
        sql(f"DROP TRIGGER IF EXISTS {trigger}")
    assert snapshot() == before
    cases.append(PROFILE_BINDING_CASES[7])
    sql("DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s", (native, native_role))
    checked(client.get(base, headers=user), 403)
    checked(client.get(path, headers=user), 403)
    checked(
        client.post(
            base,
            headers=user
            | {"X-CSRF-Token": capabilities["csrf_token"], "Idempotency-Key": str(uuid4())},
            json=body,
        ),
        403,
    )
    cases.append(PROFILE_BINDING_CASES[8])
