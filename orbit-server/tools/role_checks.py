"""角色CRUD、桥接与权限并集的真实HTTP/MySQL专项；不调用外部身份服务。"""

import uuid

ROLE_CASES = [
    "pythonBusinessRoleBuiltInReadOnlyAndSafeCopy",
    "pythonBusinessRoleCreateIdempotencyCasAndWhitelist",
    "pythonBusinessRoleMenuActionUnionAndSelfEditDenied",
    "pythonBusinessRoleNativeDefinitionAndForeignAssignmentGuard",
    "pythonBusinessRolePermissionChangeRevokesLiveSession",
    "pythonBusinessRoleAtomicAuditAndOutboxRollback",
    "pythonBusinessRoleKeysetAndTenantIsolation",
]


def run_role_checks(client, admin, headers, password, cases):
    base = "/api/v1/roles"
    tenant = "00000000-0000-0000-0000-000000000001"
    cap = client.get(base + "/capabilities", headers=headers)
    assert cap.status_code == 200
    caps = cap.json()
    assert set(caps) == {"menus", "permissions", "built_in_role_ids", "csrf_token"}
    assert len(caps["menus"]) == 8 and all("*" not in code for code in caps["permissions"])
    writes = headers | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": str(uuid.uuid4())}
    builtin_id = caps["built_in_role_ids"][0]
    builtin = client.get(base + "/" + builtin_id, headers=headers).json()
    assert set(builtin) == {"id", "name", "revision", "menu_codes", "permission_codes"}
    copy = {key: builtin[key] for key in ("name", "menu_codes", "permission_codes")}
    copy["name"] = "安全复制内置角色"
    assert (
        client.put(
            base + "/" + builtin_id, headers=writes | {"If-Match": '"1"'}, json=copy
        ).status_code
        == 403
    )
    copied = client.post(base, headers=writes, json=copy)
    assert copied.status_code == 201 and copied.json()["id"] != builtin_id
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT r.data_scope,r.role_key,r.role_id FROM orbit_business_role b "
            "JOIN sys_role r ON r.role_id=b.native_role_id WHERE b.id=%s",
            (copied.json()["id"],),
        )
        scope, key, native = cursor.fetchone()
        assert scope == "5" and key.startswith("orbit:") and native != 1
        cursor.execute(
            "SELECT m.perms FROM sys_role_menu rm JOIN sys_menu m ON m.menu_id=rm.menu_id "
            "WHERE rm.role_id=%s",
            (native,),
        )
        assert all(
            not str(row[0]).startswith("system:") and "*" not in str(row[0])
            for row in cursor.fetchall()
        )
    cases.append(ROLE_CASES[0])

    def create(value):
        response = client.post(
            base, headers=writes | {"Idempotency-Key": str(uuid.uuid4())}, json=value
        )
        assert response.status_code == 201
        return response.json()

    menu = create({"name": "仅菜单角色", "menu_codes": ["system"], "permission_codes": []})
    action_value = {
        "name": "😀" * 50,
        "menu_codes": [],
        "permission_codes": ["system.roles.manage", "system.teams.manage"],
    }
    action_headers = writes | {"Idempotency-Key": str(uuid.uuid4())}
    action_response = client.post(base, headers=action_headers, json=action_value)
    assert action_response.status_code == 201
    action = action_response.json()
    assert client.post(base, headers=action_headers, json=action_value).json() == action
    assert (
        client.post(
            base, headers=action_headers, json=action_value | {"name": "异意图"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            base,
            headers=writes | {"Idempotency-Key": str(uuid.uuid4())},
            json=action_value | {"permission_codes": ["*:*:*"]},
        ).status_code
        == 422
    )
    updated_value = action_value | {"name": "动作角色"}
    updated_headers = writes | {"Idempotency-Key": str(uuid.uuid4()), "If-Match": '"1"'}
    updated = client.put(base + "/" + action["id"], headers=updated_headers, json=updated_value)
    assert updated.status_code == 200 and updated.json()["revision"] == 2
    assert (
        client.put(base + "/" + action["id"], headers=updated_headers, json=updated_value).json()
        == updated.json()
    )
    assert (
        client.put(
            base + "/" + action["id"],
            headers=updated_headers | {"Idempotency-Key": str(uuid.uuid4())},
            json=updated_value,
        ).status_code
        == 409
    )
    action = updated.json()
    cases.append(ROLE_CASES[1])
    user_id = 999021
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT id,native_role_id FROM orbit_business_role WHERE id IN(%s,%s)",
            (menu["id"], action["id"]),
        )
        native_ids = dict(cursor.fetchall())
        cursor.execute(
            "INSERT INTO sys_user(user_id,user_name,nick_name,password,status,dept_id) "
            "SELECT %s,'fixture_business_roles','业务角色并集',password,'0',dept_id "
            "FROM sys_user WHERE user_id=1",
            (user_id,),
        )
        cursor.execute(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
            (user_id, str(uuid.uuid4())),
        )
        cursor.execute(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'SUPER_ADMIN')",
            (user_id, tenant),
        )
        cursor.execute(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id) VALUES(%s,%s,%s,%s)",
            (tenant, str(uuid.uuid4()), user_id, tenant),
        )
        for native_id in native_ids.values():
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (user_id, native_id)
            )

    def login():
        response = client.post(
            "/login",
            json={
                "username": "fixture_business_roles",
                "password": password,
                "code": "",
                "uuid": "",
            },
        )
        assert response.status_code == 200 and response.json().get("token")
        return {"Authorization": "Bearer " + response.json()["token"]}

    member = login()
    try:
        member_caps = client.get(base + "/capabilities", headers=member)
        assert member_caps.status_code == 200
        assert client.get("/api/v1/teams", headers=member).status_code == 200
        self_edit = client.put(
            base + "/" + action["id"],
            headers=member
            | {
                "X-CSRF-Token": member_caps.json()["csrf_token"],
                "Idempotency-Key": str(uuid.uuid4()),
                "If-Match": '"2"',
            },
            json=updated_value,
        )
        assert self_edit.status_code == 403 and self_edit.json()["code"] == "SELF_ROLE_CHANGE"
        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                (user_id, native_ids[menu["id"]]),
            )
        assert client.get(base, headers=member).status_code == 403
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (user_id, native_ids[menu["id"]]),
            )
        cases.append(ROLE_CASES[2])
        native_edit = client.put(
            "/system/role",
            headers=headers,
            json={
                "roleId": native_ids[action["id"]],
                "roleName": "旁路改写",
                "roleKey": "bypass",
                "roleSort": 10,
                "status": "0",
                "menuIds": [1],
                "menuCheckStrictly": True,
                "deptCheckStrictly": True,
            },
        )
        assert native_edit.status_code == 200 and native_edit.json().get("code") != 200
        assert "ORBIT" in native_edit.json().get("msg", "")
        foreign = str(uuid.uuid4())
        foreign_role = str(uuid.uuid4())
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_tenant(id,name) VALUES(%s,'角色隔离夹具')", (foreign,)
            )
            cursor.execute(
                "INSERT INTO sys_role(role_name,role_key,role_sort,status) "
                "VALUES('隔离功能角色',%s,20,'0')",
                ("orbit:" + foreign_role,),
            )
            foreign_native = cursor.lastrowid
            cursor.execute(
                "INSERT INTO orbit_business_role "
                "(tenant_id,id,native_role_id,created_at,updated_at) "
                "VALUES(%s,%s,%s,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
                (foreign, foreign_role, foreign_native),
            )
        rejected = client.put(
            "/system/user/authRole",
            headers=headers,
            params={"userId": str(user_id), "roleIds": str(foreign_native)},
        )
        assert rejected.status_code == 200 and rejected.json().get("code") != 200
        assert "其他业务租户" in rejected.json().get("msg", "")
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT role_id FROM sys_user_role WHERE user_id=%s ORDER BY role_id", (user_id,)
            )
            assert sorted(row[0] for row in cursor.fetchall()) == sorted(native_ids.values())
        assert client.get(base + "/" + foreign_role, headers=headers).status_code == 404
        cases.append(ROLE_CASES[3])
        changed_value = updated_value | {"permission_codes": ["system.roles.manage"]}
        changed = client.put(
            base + "/" + action["id"],
            headers=writes | {"If-Match": '"2"', "Idempotency-Key": str(uuid.uuid4())},
            json=changed_value,
        )
        assert changed.status_code == 200 and changed.json()["revision"] == 3
        assert client.get("/api/v1/teams", headers=member).status_code in {401, 403}
        member = login()
        assert client.get(base, headers=member).status_code == 200
        assert client.get("/api/v1/teams", headers=member).status_code == 403
        cases.append(ROLE_CASES[4])
        for table in ("orbit_directory_audit", "orbit_directory_outbox"):
            with admin.cursor() as cursor:
                cursor.execute(
                    f"CREATE TRIGGER fixture_role_failure BEFORE INSERT ON {table} "
                    "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='role fixture rejection'"
                )
            try:
                failed = client.put(
                    base + "/" + action["id"],
                    headers=writes | {"If-Match": '"3"', "Idempotency-Key": str(uuid.uuid4())},
                    json=changed_value | {"permission_codes": []},
                )
                assert failed.status_code == 503 and "role fixture rejection" not in failed.text
                assert (
                    client.get(base + "/" + action["id"], headers=headers).json() == changed.json()
                )
                assert client.get(base, headers=member).status_code == 200
            finally:
                with admin.cursor() as cursor:
                    cursor.execute("DROP TRIGGER fixture_role_failure")
        cases.append(ROLE_CASES[5])
        for index in range(23):
            create({"name": f"角色分页夹具{index:02}", "menu_codes": [], "permission_codes": []})
        first = client.get(
            base, params={"q": "角色分页夹具", "page_size": 20}, headers=headers
        ).json()
        second = client.get(
            base,
            params={"q": "角色分页夹具", "page_size": 20, "cursor": first["next_cursor"]},
            headers=headers,
        ).json()
        assert (
            len(first["items"]) == 20
            and len(second["items"]) == 3
            and second["next_cursor"] is None
        )
        assert len({item["id"] for item in first["items"] + second["items"]}) == 23
        assert first["data_as_of"] == second["data_as_of"]
        create({"name": "使角色旧游标失效", "menu_codes": [], "permission_codes": []})
        assert (
            client.get(
                base,
                params={"q": "角色分页夹具", "page_size": 20, "cursor": first["next_cursor"]},
                headers=headers,
            ).status_code
            == 409
        )
        cases.append(ROLE_CASES[6])
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET enabled=0 WHERE user_id=%s", (user_id,))
