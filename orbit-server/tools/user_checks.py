"""人员只读专项：显式临时身份fixture，不发送邀请、不伪造OIDC身份已验证。"""

import uuid

USER_CASES = [
    "pythonUserDirectoryExactFieldsAndLocalIdentityIsNotOidc",
    "pythonUserDirectoryKeysetAndFilters",
    "pythonUserDirectoryOwnAndExplicitManagedScope",
    "pythonUnverifiedBusinessIdentityCannotUseNativeEnabledSession",
    "pythonUserDirectoryMappingAndContactFailuresAreExplicit",
    "pythonUserDirectoryPreservesDisabledAssignedRoleReferences",
    "pythonUserDirectoryActualForeignObjectIsInvisible",
    "pythonUserDirectoryTenantAndRevokedActionBoundary",
]


def run_user_checks(client, admin, headers, password, cases):
    tenant = "00000000-0000-0000-0000-000000000001"
    role_caps = client.get("/api/v1/roles/capabilities", headers=headers).json()
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": role_caps["csrf_token"],
            "Idempotency-Key": "user-fixture-role-" + uuid.uuid4().hex,
        },
        json={
            "name": "人员目录专项权限",
            "menu_codes": ["system"],
            "permission_codes": ["system.read", "system.users.manage"],
        },
    )
    assert role.status_code == 201
    role_id = role.json()["id"]
    teams = [str(uuid.uuid4()), str(uuid.uuid4())]
    users = []
    with admin.cursor() as cursor:
        cursor.execute("SELECT native_role_id FROM orbit_business_role WHERE id=%s", (role_id,))
        native_role = cursor.fetchone()[0]
        for index, team in enumerate(teams):
            cursor.execute(
                "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,%s)",
                (tenant, team, "人员目录专项团队" + str(index)),
            )
        for index in range(28):
            identifier = str(uuid.uuid4())
            native = 980000 + index
            status = "1" if index in (26, 27) else "0"
            team = teams[0 if index % 2 else 1]
            data_role = "TEAM_ADMIN" if index == 0 else "USER"
            name = "user_directory_" + str(index)
            cursor.execute(
                """
                INSERT INTO sys_user
                (user_id,user_name,nick_name,email,phonenumber,password,status,del_flag)
                SELECT %s,%s,%s,%s,%s,password,%s,'0' FROM sys_user WHERE user_id=1
            """,
                (
                    native,
                    name,
                    "人员目录专项昵称" + str(index),
                    name + "@fixture.example.org",
                    "+86 123456789" if index == 1 else "+86 1234567" + f"{index:03d}",
                    status,
                ),
            )
            cursor.execute(
                "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
                "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
                (native, str(uuid.uuid4())),
            )
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, native_role)
            )
            cursor.execute(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,%s)",
                (native, tenant, data_role),
            )
            cursor.execute(
                """
                INSERT INTO orbit_business_user
                (tenant_id,id,user_id,team_id,display_name,invited,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(3))
            """,
                (
                    tenant,
                    identifier,
                    native,
                    team,
                    "人员目录专项姓名" + str(index),
                    int(index == 26),
                ),
            )
            users.append({"id": identifier, "native": native, "name": name, "team": team})
        cursor.execute(
            "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) "
            "VALUES(%s,980000,%s)",
            (tenant, teams[0]),
        )
    base = "/api/v1/users"
    initial = client.get(base, headers=headers)
    assert initial.status_code == 200 and len(initial.json()["items"]) == 29
    detail = client.get(base + "/" + users[1]["id"], headers=headers)
    assert detail.status_code == 200
    item = detail.json()
    assert set(item) == {
        "id",
        "revision",
        "display_name",
        "nickname",
        "email",
        "phone",
        "team_id",
        "role_ids",
        "data_role",
        "managed_team_ids",
        "status",
        "identity_status",
    }
    assert item["display_name"] != item["nickname"] and item["role_ids"] == [role_id]
    assert item["phone"] == "+86 123456789" and item["identity_status"] == "LOCAL_ACCOUNT"
    assert detail.headers["cache-control"] == "no-store"
    with admin.cursor() as cursor:
        cursor.execute("UPDATE orbit_business_user SET display_name=NULL WHERE user_id=980027")
        cursor.execute(
            "UPDATE sys_user SET nick_name='',email='legacy-fallback@fixture.example.org' "
            "WHERE user_id=980027"
        )
    try:
        legacy = client.get(base, headers=headers, params={"q": users[27]["name"]})
        assert legacy.status_code == 200 and len(legacy.json()["items"]) == 1
        assert legacy.json()["items"][0]["display_name"] == users[27]["name"]
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_user SET display_name='人员目录专项姓名27' "
                "WHERE user_id=980027"
            )
            cursor.execute(
                "UPDATE sys_user SET nick_name='人员目录专项昵称27',email=%s WHERE user_id=980027",
                (users[27]["name"] + "@fixture.example.org",),
            )
    denied_activation = client.put(
        "/system/user/changeStatus", headers=headers, json={"userId": 980026, "status": "0"}
    )
    assert denied_activation.status_code != 200 or denied_activation.json().get("code") != 200
    with admin.cursor() as cursor:
        cursor.execute("SELECT status FROM sys_user WHERE user_id=980026")
        assert cursor.fetchone()[0] == "1"
    assert client.get(base + "/" + users[26]["id"], headers=headers).json()["status"] == "INVITED"
    assert (
        client.get(base + "/" + users[26]["id"], headers=headers).json()["identity_status"]
        == "UNVERIFIED"
    )
    cases.append(USER_CASES[0])
    query = {"q": "人员目录专项", "page_size": 20}
    first = client.get(base, headers=headers, params=query).json()
    assert len(first["items"]) == 20 and first["next_cursor"]
    second = client.get(
        base, headers=headers, params=query | {"cursor": first["next_cursor"]}
    ).json()
    assert len(second["items"]) == 8 and second["next_cursor"] is None
    assert len({x["id"] for x in first["items"] + second["items"]}) == 28
    for status, count in (("ENABLED", 26), ("DISABLED", 1), ("INVITED", 1)):
        response = client.get(
            base, headers=headers, params=query | {"status": status, "page_size": 50}
        )
        assert response.status_code == 200 and len(response.json()["items"]) == count
    assert client.get(base, headers=headers, params={"q": "+86 123456789"}).json()["items"]
    assert client.get(base, headers=headers, params={"q": "%"}).json()["items"] == []
    assert (
        client.get(
            base,
            headers=headers,
            params=query | {"cursor": first["next_cursor"], "status": "ENABLED"},
        ).status_code
        == 409
    )
    assert (
        client.get(base, headers=headers, params={"date_from": "2999-01-01"}).json()["items"] == []
    )
    cases.append(USER_CASES[1])
    actors = {}
    for index in (0, 1):
        login = client.post("/login", json={"username": users[index]["name"], "password": password})
        assert login.status_code == 200 and login.json().get("token")
        actor_headers = {"Authorization": "Bearer " + login.json()["token"]}
        actors[index] = actor_headers
        visible = client.get(base, headers=actor_headers)
        assert visible.status_code == 200
        ids = {x["id"] for x in visible.json()["items"]}
        expected = (
            {u["id"] for u in users if u["team"] == teams[0]} | {users[0]["id"]}
            if index == 0
            else {users[1]["id"]}
        )
        assert ids == expected
        assert client.get(base + "/" + users[2]["id"], headers=actor_headers).status_code == 404
        assert client.get(base + "/" + users[index]["id"], headers=actor_headers).status_code == 200
    cases.append(USER_CASES[2])
    with admin.cursor() as cursor:
        cursor.execute("UPDATE orbit_business_user SET invited=1 WHERE user_id=980001")
    try:
        for endpoint in (base, "/getInfo"):
            invalid = client.get(endpoint, headers=actor_headers)
            assert invalid.status_code == 401 or invalid.json().get("code") == 401
        pending = client.get(base + "/" + users[1]["id"], headers=headers)
        assert pending.json()["status"] == "INVITED"
        assert pending.json()["identity_status"] == "UNVERIFIED"
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_business_user SET invited=0 WHERE user_id=980001")
    cases.append(USER_CASES[3])
    with admin.cursor() as cursor:
        cursor.execute("INSERT INTO sys_user_role(user_id,role_id) VALUES(980001,2)")
    try:
        assert client.get(base + "/" + users[1]["id"], headers=headers).status_code == 409
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DELETE FROM sys_user_role WHERE user_id=980001 AND role_id=2")
            cursor.execute("UPDATE sys_user SET email='' WHERE user_id=980001")
    try:
        assert client.get(base + "/" + users[1]["id"], headers=headers).status_code == 409
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE sys_user SET email=%s WHERE user_id=980001",
                (users[1]["name"] + "@fixture.example.org",),
            )
    cases.append(USER_CASES[4])
    with admin.cursor() as cursor:
        cursor.execute("UPDATE sys_role SET status='1' WHERE role_id=%s", (native_role,))
        cursor.execute(
            "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
        )
    try:
        disabled_role = client.get(base + "/" + users[1]["id"], headers=headers)
        assert disabled_role.status_code == 200 and disabled_role.json()["role_ids"] == [role_id]
        native_detail = client.get("/system/user/980001", headers=headers)
        assert native_detail.status_code == 200 and native_detail.json()["roleIds"] == [native_role]
        assert any(
            role["roleId"] == native_role and role["status"] == "1"
            for role in native_detail.json()["roles"]
        )
        native_selection = client.get("/system/user/authRole/980001", headers=headers)
        assert native_selection.status_code == 200 and any(
            role["roleId"] == native_role and role["status"] == "1" and role["flag"]
            for role in native_selection.json()["roles"]
        )
        # 只读资料保留历史授权，不意味着认证把停用角色重新计入权限。
        authenticated = client.get("/getInfo", headers=actor_headers)
        assert authenticated.status_code == 200 and authenticated.json().get("code") == 200
        assert native_role not in {
            role["roleId"] for role in authenticated.json()["user"].get("role", [])
        }
        original = native_detail.json()["data"]
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT u.password,i.auth_version FROM sys_user u "
                "JOIN sys_identity_subject i ON i.user_id=u.user_id WHERE u.user_id=980001"
            )
            security = cursor.fetchone()
        form = {
            "userId": 980001,
            "userName": original["userName"],
            "nickName": original["nickName"],
            "email": original["email"],
            "phonenumber": original["phonenumber"],
            "status": original["status"],
            "roleIds": [native_role],
            "postIds": [],
        }
        for nickname in (original["nickName"] + "修复", original["nickName"]):
            changed = client.put(
                "/system/user", headers=headers, json=form | {"nickName": nickname}
            )
            assert changed.status_code == 200 and changed.json().get("code") == 200
            with admin.cursor() as cursor:
                cursor.execute("SELECT role_id FROM sys_user_role WHERE user_id=980001")
                assert cursor.fetchall() == ((native_role,),)
                cursor.execute(
                    "SELECT u.password,i.auth_version FROM sys_user u "
                    "JOIN sys_identity_subject i ON i.user_id=u.user_id WHERE u.user_id=980001"
                )
                assert cursor.fetchone() == security
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_role SET status='0' WHERE role_id=%s", (native_role,))
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
    cases.append(USER_CASES[5])
    foreign_tenant, foreign_user, foreign_role = [str(uuid.uuid4()) for _ in range(3)]
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbit_tenant(id,name) VALUES(%s,'人员隔离专项租户')", (foreign_tenant,)
        )
        cursor.execute("INSERT INTO orbit_directory_clock(tenant_id) VALUES(%s)", (foreign_tenant,))
        cursor.execute(
            "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,'人员隔离专项团队')",
            (foreign_tenant, foreign_tenant),
        )
        cursor.execute(
            "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,data_scope,status,del_flag) "
            "VALUES(980100,'人员隔离专项角色','fixture-foreign-user-directory',100,'5','0','0')"
        )
        cursor.execute(
            "INSERT INTO orbit_business_role(tenant_id,id,native_role_id,created_at,updated_at) "
            "VALUES(%s,%s,980100,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (foreign_tenant, foreign_role),
        )
        cursor.execute("""
            INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag)
            SELECT 980100,'foreign_user_directory','另一租户不得泄露',
                'foreign_user_directory@fixture.example.org',password,'0','0'
            FROM sys_user WHERE user_id=1
        """)
        cursor.execute(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(980100,%s,1,UTC_TIMESTAMP(3))",
            (str(uuid.uuid4()),),
        )
        cursor.execute("INSERT INTO sys_user_role(user_id,role_id) VALUES(980100,980100)")
        cursor.execute(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(980100,%s,'USER')",
            (foreign_tenant,),
        )
        cursor.execute(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,created_at) "
            "VALUES(%s,%s,980100,%s,UTC_TIMESTAMP(3))",
            (foreign_tenant, foreign_user, foreign_tenant),
        )
    for requester in (headers, actor_headers):
        foreign = client.get(base + "/" + foreign_user, headers=requester)
        assert foreign.status_code == 404 and "另一租户不得泄露" not in foreign.text
        page = client.get(base, headers=requester, params={"q": "另一租户不得泄露"})
        assert page.status_code == 200 and page.json()["items"] == []
    with admin.cursor() as cursor:
        cursor.execute("UPDATE orbit_business_user SET invited=1 WHERE user_id=980100")
        cursor.execute("UPDATE sys_user SET status='1' WHERE user_id=980100")
    foreign_activation = client.put(
        "/system/user/changeStatus", headers=headers, json={"userId": 980100, "status": "0"}
    )
    assert foreign_activation.json().get("code") != 200
    assert "不能跨业务租户" in foreign_activation.json().get("msg", "")
    assert "待邀请验证" not in foreign_activation.text
    with admin.cursor() as cursor:
        cursor.execute("SELECT status FROM sys_user WHERE user_id=980100")
        assert cursor.fetchone()[0] == "1"
    cases.append(USER_CASES[6])
    assert (
        client.get(base, headers=headers | {"X-Target-Tenant": str(uuid.uuid4())}).status_code
        == 403
    )
    assert client.get(base + "/" + str(uuid.uuid4()), headers=headers).status_code == 404
    assert client.get(base + "?q=a&q=b", headers=headers).status_code == 400
    assert client.get(base + "?tenant_id=" + tenant, headers=headers).status_code == 400
    with admin.cursor() as cursor:
        cursor.execute(
            "DELETE FROM orbit_business_role_action WHERE role_id=%s "
            "AND permission_code='system.users.manage'",
            (role_id,),
        )
    try:
        assert client.get(base, headers=actor_headers).status_code == 403
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) "
                "VALUES(%s,%s,'system.users.manage')",
                (tenant, role_id),
            )
    cases.append(USER_CASES[7])
    return {
        "users": users,
        "actor_headers": actor_headers,
        "manager_headers": actors[0],
        "native_role": native_role,
        "role_id": role_id,
    }
