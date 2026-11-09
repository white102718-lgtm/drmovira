"""原角色入口必须用写入后的状态判定保护；仅运行于已核验的独立临时库。"""

import time
import uuid

ROLE_GUARD_CASES = [
    "pythonNativeLastAdminRoleDisableRollsBackNewState",
    "pythonNativeRoleMenuRemovalRevokesAndCommitsDirectoryVersion",
    "pythonTeamDisableRequiresActuallyUsableRecoveryAdministrator",
    "pythonNativeRoleCannotRemoveLastRecoveryActionAndTeamCanBeRestored",
]


def _fixture_login(client, cache, name, password):
    payload = {"username": name, "password": password, "code": "", "uuid": ""}
    response = client.post("/login", json=payload)
    if response.status_code == 429:
        started = time.monotonic()
        print({"role_guard_fixture_login_throttled": True})
        while list(cache.scan_iter(match="api_rate_limit:login:sliding_window:*")):
            assert time.monotonic() - started < 65
            time.sleep(0.5)
        response = client.post("/login", json=payload)
    assert response.status_code == 200 and response.json().get("token")
    return {"Authorization": "Bearer " + response.json()["token"]}


def _guard_operator(client, admin, headers, password, tenant, cache):
    """有效SUPER_ADMIN具备原/业务角色动作，但没有团队恢复动作，不冒用失效Root会话。"""
    caps = client.get("/api/v1/roles/capabilities", headers=headers).json()
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": caps["csrf_token"],
            "Idempotency-Key": "guard-operator-" + uuid.uuid4().hex,
        },
        json={
            "name": "角色保护有效操作者",
            "menu_codes": ["system"],
            "permission_codes": ["system.read", "system.roles.manage"],
        },
    )
    assert role.status_code == 201
    team_id = str(uuid.uuid4())
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE id=%s", (role.json()["id"],)
        )
        native_role = cursor.fetchone()[0]
        cursor.execute("UPDATE sys_role SET data_scope='1' WHERE role_id=%s", (native_role,))
        cursor.execute(
            "INSERT INTO sys_role_menu(role_id,menu_id) SELECT %s,menu_id FROM sys_menu "
            "WHERE perms LIKE 'system:role:%%' OR menu_id IN(1,100,101)",
            (native_role,),
        )
        cursor.execute(
            "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,'保护操作者团队')",
            (tenant, team_id),
        )
        cursor.execute(
            "INSERT INTO sys_user"
            "(user_id,user_name,nick_name,email,password,status,del_flag,dept_id) "
            "SELECT 2000020,'role_guard_operator','角色保护有效操作者',"
            "'role-guard-operator@fixture.example.org',password,'0','0',dept_id "
            "FROM sys_user WHERE user_id=1"
        )
        cursor.execute(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(2000020,%s,1,UTC_TIMESTAMP(3))",
            (str(uuid.uuid4()),),
        )
        cursor.execute(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(2000020,%s)", (native_role,)
        )
        cursor.execute(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) "
            "VALUES(2000020,%s,'SUPER_ADMIN')",
            (tenant,),
        )
        cursor.execute(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id) "
            "VALUES(%s,%s,2000020,%s)",
            (tenant, str(uuid.uuid4()), team_id),
        )
    return _fixture_login(client, cache, "role_guard_operator", password)


def run_role_guard_checks(client, admin, headers, password, tenant, cases, cache):
    operator = _guard_operator(client, admin, headers, password, tenant, cache)
    role_id = 998010
    with admin.cursor() as cursor:
        cursor.execute("SELECT role_id FROM sys_user_role WHERE user_id=2 ORDER BY role_id")
        original_roles = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT user_name FROM sys_user WHERE user_id=2")
        user_name = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,status,del_flag) "
            "VALUES(%s,'写后保护夹具','fixture-post-state',10,'0','0')",
            (role_id,),
        )
        cursor.execute(
            "INSERT INTO sys_role_menu(role_id,menu_id) "
            "VALUES(%s,31000),(%s,31080),(%s,31081),(%s,31083)",
            (role_id, role_id, role_id, role_id),
        )
        cursor.execute("DELETE FROM sys_user_role WHERE user_id=2")
        cursor.execute("INSERT INTO sys_user_role(user_id,role_id) VALUES(2,%s)", (role_id,))
        cursor.execute(
            "UPDATE orbit_business_team SET enabled=0 WHERE tenant_id=%s AND id=%s",
            (tenant, tenant),
        )
        cursor.execute("SELECT auth_version FROM sys_identity_subject WHERE user_id=2")
        before_auth = cursor.fetchone()[0]
        cursor.execute("SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,))
        before_directory = cursor.fetchone()[0]
    try:
        refused = client.put(
            "/system/role/changeStatus", headers=operator, json={"roleId": role_id, "status": "1"}
        )
        assert refused.status_code == 200 and refused.json().get("code") != 200
        assert "至少一名" in refused.json().get("msg", "")
        with admin.cursor() as cursor:
            cursor.execute("SELECT status FROM sys_role WHERE role_id=%s", (role_id,))
            assert cursor.fetchone()[0] == "0"
            cursor.execute("SELECT auth_version FROM sys_identity_subject WHERE user_id=2")
            assert cursor.fetchone()[0] == before_auth
            cursor.execute(
                "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
            )
            assert cursor.fetchone()[0] == before_directory
            cursor.execute(
                "UPDATE orbit_business_team SET enabled=1 WHERE tenant_id=%s AND id=%s",
                (tenant, tenant),
            )
        cases.append(ROLE_GUARD_CASES[0])
        target_headers = _fixture_login(client, cache, user_name, password)
        path = "/api/v1/system-configurations/metadata"
        assert client.get(path, headers=target_headers).status_code == 200
        changed = client.put(
            "/system/role",
            headers=headers,
            json={
                "roleId": role_id,
                "roleName": "写后保护夹具",
                "roleKey": "fixture-post-state",
                "roleSort": 10,
                "status": "0",
                "menuIds": [31000, 31080],
                "menuCheckStrictly": True,
                "deptCheckStrictly": True,
            },
        )
        assert changed.status_code == 200 and changed.json().get("code") == 200
        assert client.get(path, headers=target_headers).status_code == 401
        with admin.cursor() as cursor:
            cursor.execute("SELECT auth_version FROM sys_identity_subject WHERE user_id=2")
            assert cursor.fetchone()[0] == before_auth + 1
            cursor.execute(
                "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
            )
            assert cursor.fetchone()[0] == before_directory + 1
            cursor.execute(
                "SELECT menu_id FROM sys_role_menu WHERE role_id=%s ORDER BY menu_id", (role_id,)
            )
            assert cursor.fetchall() == ((31000,), (31080,))
        cases.append(ROLE_GUARD_CASES[1])
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_team SET enabled=1 WHERE tenant_id=%s AND id=%s",
                (tenant, tenant),
            )
            cursor.execute("DELETE FROM sys_user_role WHERE user_id=2")
            for original in original_roles:
                cursor.execute(
                    "INSERT INTO sys_user_role(user_id,role_id) VALUES(2,%s)", (original,)
                )
    _check_recovery_action(
        client, admin, headers, password, user_name, tenant, cases, cache, operator
    )


def _check_recovery_action(
    client, admin, headers, password, user_name, tenant, cases, cache, operator
):
    base = "/api/v1/teams"
    team_path = base + "/" + tenant
    team = client.get(team_path, headers=headers).json()
    csrf = client.get(base + "/capabilities", headers=headers).json()["csrf_token"]
    disabled = {"name": team["name"], "status": "DISABLED"}
    write_headers = headers | {
        "X-CSRF-Token": csrf,
        "If-Match": f'"{team["revision"]}"',
        "Idempotency-Key": str(uuid.uuid4()),
    }
    refused = client.put(team_path, headers=write_headers, json=disabled)
    assert refused.status_code == 409 and refused.json()["code"] == "LAST_ADMIN_REQUIRED"
    assert client.get(team_path, headers=headers).json() == team
    cases.append(ROLE_GUARD_CASES[2])
    with admin.cursor() as cursor:
        cursor.execute("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(990003,31083)")
    try:
        allowed = client.put(
            team_path, headers=write_headers | {"Idempotency-Key": str(uuid.uuid4())}, json=disabled
        )
        assert allowed.status_code == 200 and allowed.json()["status"] == "DISABLED"
        # 主管理员会话失效，由另一有效团队的管理员恢复，不能借原菜单绕开禁用。
        assert client.get(team_path, headers=headers).status_code == 401
        recovery_headers = _fixture_login(client, cache, user_name, password)
        with admin.cursor() as cursor:
            cursor.execute("SELECT auth_version FROM sys_identity_subject WHERE user_id=2")
            before_auth = cursor.fetchone()[0]
            cursor.execute(
                "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
            )
            before_directory = cursor.fetchone()[0]
        refused = client.put(
            "/system/role",
            headers=operator,
            json={
                "roleId": 990003,
                "roleName": "fixture split",
                "roleKey": "fixture-split",
                "roleSort": 3,
                "status": "0",
                "menuIds": [31081],
                "menuCheckStrictly": True,
                "deptCheckStrictly": True,
            },
        )
        assert refused.status_code == 200 and refused.json().get("code") != 200
        assert "至少一名" in refused.json().get("msg", "")
        with admin.cursor() as cursor:
            cursor.execute("SELECT auth_version FROM sys_identity_subject WHERE user_id=2")
            assert cursor.fetchone()[0] == before_auth
            cursor.execute(
                "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
            )
            assert cursor.fetchone()[0] == before_directory
            cursor.execute(
                "SELECT menu_id FROM sys_role_menu WHERE role_id=990003 ORDER BY menu_id"
            )
            assert cursor.fetchall() == ((31081,), (31083,))
        csrf = client.get(base + "/capabilities", headers=recovery_headers).json()["csrf_token"]
        restored = client.put(
            team_path,
            headers=recovery_headers
            | {
                "X-CSRF-Token": csrf,
                "If-Match": f'"{allowed.json()["revision"]}"',
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={"name": team["name"], "status": "ENABLED"},
        )
        assert restored.status_code == 200 and restored.json()["status"] == "ENABLED"
        assert client.get(team_path, headers=headers).status_code == 401
        with admin.cursor() as cursor:
            cursor.execute("SELECT user_name FROM sys_user WHERE user_id=1")
            root_name = cursor.fetchone()[0]
        headers.update(_fixture_login(client, cache, root_name, password))
        assert client.get(team_path, headers=headers).status_code == 200
        cases.append(ROLE_GUARD_CASES[3])
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_team SET enabled=1 WHERE tenant_id=%s AND id=%s",
                (tenant, tenant),
            )
            cursor.execute("DELETE FROM sys_role_menu WHERE role_id=990003 AND menu_id=31083")
