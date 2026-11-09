"""原角色列表、详情、授权树、成员选择与原完整资料表单的真实边界。"""

NATIVE_ROLE_READ_CASES = [
    "pythonNativeRoleListFiltersForeignTenantBeforeCount",
    "pythonNativeRoleDetailsAndAuthorizationTreesHideForeignObjects",
    "pythonNativeRoleMemberSelectorsIntersectRoleAndUserAuthority",
    "pythonNativeRoleCacheRechecksActionScopeAndDirectoryClock",
    "pythonNativeForeignLegacyRoleRelationshipIsExplicitWithoutDisclosure",
    "pythonNativeFullReadonlyDtoCanEditUnicodeContactsWithoutPassword",
    "pythonNativeUserAndMemberListsNeverSerializePasswordFields",
]


def run_native_role_read_checks(client, admin, headers, fixture, cases):
    tenant = "00000000-0000-0000-0000-000000000001"
    role = fixture["native_role"]
    query = {"roleId": role, "pageSize": 1}
    foreign = client.get(
        "/system/role/list", headers=headers, params={"roleId": 980100, "pageSize": 1}
    )
    assert foreign.status_code == 200
    assert foreign.json()["rows"] == [] and foreign.json()["total"] == 0, (
        "原角色列表泄露其他租户功能角色"
    )
    own = client.get("/system/role/list", headers=headers, params=query)
    assert own.status_code == 200 and own.json()["total"] == 1
    assert own.json()["rows"][0]["roleId"] == role
    cases.append(NATIVE_ROLE_READ_CASES[0])
    urls = [
        "/system/role/{id}",
        "/system/role/deptTree/{id}",
        "/system/menu/roleMenuTreeselect/{id}",
    ]
    for pattern in urls:
        hidden = client.get(pattern.format(id=980100), headers=headers)
        assert hidden.status_code == 404 and hidden.json().get("code") == 404, pattern
        visible = client.get(pattern.format(id=role), headers=headers)
        assert visible.status_code == 200 and visible.json().get("code") == 200, pattern
    cases.append(NATIVE_ROLE_READ_CASES[1])
    for selection in ("allocatedList", "unallocatedList"):
        url = "/system/role/authUser/" + selection
        hidden = client.get(url, headers=headers, params={"roleId": 980100})
        assert hidden.status_code == 404
        scoped = client.get(
            url,
            headers=headers,
            params={"roleId": role, "userName": "foreign_user_directory", "pageSize": 1},
        )
        assert scoped.status_code == 200 and scoped.json()["total"] == 0
        assert scoped.json()["rows"] == []
    member_query = {"roleId": role, "userName": fixture["users"][1]["name"], "pageSize": 1}
    member_url = "/system/role/authUser/allocatedList"
    member = client.get(member_url, headers=headers, params=member_query)
    assert member.status_code == 200 and member.json()["total"] == 1
    assert (
        client.get(member_url, headers=headers, params=member_query).headers.get("x-api-cache")
        == "HIT"
    )
    try:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31082")
        assert client.get(member_url, headers=headers, params=member_query).status_code == 403
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status='0' WHERE menu_id=31082")
    cases.append(NATIVE_ROLE_READ_CASES[2])
    client.get("/system/role/list", headers=headers, params=query)
    assert (
        client.get("/system/role/list", headers=headers, params=query).headers.get("x-api-cache")
        == "HIT"
    )
    try:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1")
        assert client.get("/system/role/list", headers=headers, params=query).status_code == 403
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=1")
    try:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31084")
        assert client.get("/system/role/list", headers=headers, params=query).status_code == 403
        assert client.get(urls[2].format(id=role), headers=headers).status_code == 403
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status='0' WHERE menu_id=31084")
    original = own.json()["rows"][0]["roleName"]
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE sys_role SET role_name='原角色缓存版本专项' WHERE role_id=%s", (role,)
            )
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
        fresh = client.get("/system/role/list", headers=headers, params=query)
        assert (
            fresh.status_code == 200 and fresh.json()["rows"][0]["roleName"] == "原角色缓存版本专项"
        )
        assert fresh.headers.get("x-api-cache") == "MISS"
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_role SET role_name=%s WHERE role_id=%s", (original, role))
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
    cases.append(NATIVE_ROLE_READ_CASES[3])
    target = fixture["users"][1]["native"]
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,980100)", (target,)
            )
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
        for url in (f"/system/user/{target}", f"/system/user/authRole/{target}"):
            broken = client.get(url, headers=headers)
            assert broken.status_code == 409 and broken.json().get("code") == 409
            assert "人员隔离专项角色" not in broken.text
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=980100", (target,)
            )
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
    restored = client.get(f"/system/user/{target}", headers=headers)
    assert restored.status_code == 200
    assert 980100 not in {role["roleId"] for role in restored.json()["roles"]}
    cases.append(NATIVE_ROLE_READ_CASES[4])
    # 与原Vue表单相同：详情只读DTO回填，再覆盖关联数组；不能只测手写最小JSON。
    original = restored.json()
    body = original["data"] | {"roleIds": original["roleIds"], "postIds": original["postIds"]}
    body.pop("password", None)
    changed = body | {
        "nickName": "😀" * 50,
        "email": "p" * 64 + "@" + "q" * 63 + "." + "r" * 63 + "." + "s" * 57 + ".com",
        "phonenumber": "+86 " + "7" * 28,
    }
    import uuid

    caps = client.get("/api/v1/users/capabilities", headers=headers).json()
    duplicate = client.post(
        "/api/v1/users",
        headers=headers
        | {
            "X-CSRF-Token": caps["csrf_token"],
            "Idempotency-Key": "native-contact-" + uuid.uuid4().hex,
        },
        json={
            "display_name": "原资料重复联系方式专项",
            "nickname": "另一个稳定身份",
            "email": changed["email"],
            "phone": changed["phonenumber"],
            "team_id": fixture["users"][1]["team"],
            "role_ids": [fixture["role_id"]],
            "data_role": "USER",
            "managed_team_ids": [],
            "status": "INVITED",
        },
    )
    assert duplicate.status_code == 201
    duplicate_person = duplicate.json()
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT u.password,i.subject_id,i.auth_version FROM sys_user u "
            "JOIN sys_identity_subject i ON i.user_id=u.user_id WHERE u.user_id=%s",
            (target,),
        )
        original_identity = cursor.fetchone()
    for value in (changed, body):
        saved = client.put("/system/user", headers=headers, json=value)
        if saved.status_code != 200 or saved.json().get("code") != 200:
            # 仅独立夹具公开错误消息用于定位，不打印请求、令牌、密码、连接串。
            print({"native_edit_fixture_error": str(saved.json().get("msg", ""))[:160]})
        assert saved.status_code == 200 and saved.json().get("code") == 200
        reread = client.get(f"/system/user/{target}", headers=headers).json()
        assert all(
            reread["data"][key] == value[key] for key in ("nickName", "email", "phonenumber")
        )
        assert reread["roleIds"] == original["roleIds"]
        other = client.get("/api/v1/users/" + duplicate_person["id"], headers=headers)
        assert other.status_code == 200 and other.json() == duplicate_person
    for value in (changed, body):
        profile = client.put(
            "/system/user/profile",
            headers=fixture["actor_headers"],
            json={key: value[key] for key in ("nickName", "email", "phonenumber")},
        )
        assert profile.status_code == 200 and profile.json().get("code") == 200
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT u.password,i.subject_id,i.auth_version FROM sys_user u "
                "JOIN sys_identity_subject i ON i.user_id=u.user_id WHERE u.user_id=%s",
                (target,),
            )
            assert cursor.fetchone() == original_identity
        other = client.get("/api/v1/users/" + duplicate_person["id"], headers=headers)
        assert other.status_code == 200 and other.json() == duplicate_person
    cases.append(NATIVE_ROLE_READ_CASES[5])
    user_query = {"userId": target, "pageSize": 1}
    for _ in range(2):
        listing = client.get("/system/user/list", headers=headers, params=user_query)
        assert listing.status_code == 200 and listing.json()["total"] == 1
        assert "password" not in listing.json()["rows"][0], "原人员列表不能返回密码字段或哈希"
        members = client.get(
            "/system/role/authUser/allocatedList",
            headers=headers,
            params={"roleId": role, "userName": fixture["users"][1]["name"]},
        )
        assert members.status_code == 200 and members.json()["total"] == 1
        assert "password" not in members.json()["rows"][0]
    cases.append(NATIVE_ROLE_READ_CASES[6])
