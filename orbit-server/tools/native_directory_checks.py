"""原人员读取真实反例：原超级权限不能扩大业务租户。"""

NATIVE_DIRECTORY_CASES = [
    "pythonNativeUserListFiltersTenantBeforeCountAndPagination",
    "pythonNativeUserDetailAndRoleSelectionHideForeignObjects",
    "pythonNativeDirectoryCacheTracksScopeAndDirectoryClock",
    "pythonNativeUserExplicitManagedTeamScopeAndRevocation",
]


def run_native_directory_checks(client, admin, headers, fixture, cases):
    response = client.get(
        "/system/user/list", headers=headers, params={"userId": 980100, "pageSize": 1}
    )
    assert response.status_code == 200 and response.json().get("code") == 200
    assert response.json()["rows"] == [] and response.json()["total"] == 0, (
        "原人员列表泄露其他租户账号，必须在SQL分页和COUNT前限制"
    )
    own = fixture["users"][1]
    response = client.get(
        "/system/user/list", headers=headers, params={"userId": own["native"], "pageSize": 1}
    )
    assert response.status_code == 200 and response.json()["total"] == 1
    assert response.json()["rows"][0]["userId"] == own["native"]
    cases.append(NATIVE_DIRECTORY_CASES[0])
    for url in ("/system/user/980100", "/system/user/authRole/980100"):
        hidden = client.get(url, headers=headers)
        assert hidden.status_code == 404 and hidden.json().get("code") == 404, url
        assert "fixture.example.org" not in hidden.text
    own_detail = client.get("/system/user/" + str(own["native"]), headers=headers)
    assert own_detail.status_code == 200
    assert 980100 not in {role["roleId"] for role in own_detail.json()["roles"]}
    cases.append(NATIVE_DIRECTORY_CASES[1])
    query = {"userId": own["native"], "pageSize": 1}
    before = client.get("/system/user/list", headers=headers, params=query)
    cached = client.get("/system/user/list", headers=headers, params=query)
    assert cached.headers.get("x-api-cache") == "HIT"
    original = before.json()["rows"][0]["nickName"]
    tenant = "00000000-0000-0000-0000-000000000001"
    try:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1")
        limited = client.get("/system/user/list", headers=headers, params=query)
        assert limited.status_code == 200 and limited.json()["rows"] == []
        assert limited.json()["total"] == 0 and limited.headers.get("x-api-cache") == "MISS"
        assert client.get("/system/user/" + str(own["native"]), headers=headers).status_code == 404
        own_profile = client.get("/system/user/1", headers=headers)
        assert own_profile.status_code == 200 and own_profile.json()["data"]["userId"] == 1
        assert {role["roleId"] for role in own_profile.json()["roles"]} <= {1}
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=1")
    try:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31082")
        assert client.get("/system/user/list", headers=headers, params=query).status_code == 403
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status='0' WHERE menu_id=31082")
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE sys_user SET nick_name='缓存目录版本专项' WHERE user_id=%s",
                (own["native"],),
            )
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
        fresh = client.get("/system/user/list", headers=headers, params=query)
        assert fresh.json()["rows"][0]["nickName"] == "缓存目录版本专项"
        assert fresh.headers.get("x-api-cache") == "MISS"
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE sys_user SET nick_name=%s WHERE user_id=%s", (original, own["native"])
            )
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
    cases.append(NATIVE_DIRECTORY_CASES[2])
    # 专属夹具改变真实范围并推进同一目录时钟，不通过换查询参数躲开缓存。
    team = own["team"]
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT enabled FROM orbit_business_team_manager "
            "WHERE tenant_id=%s AND manager_user_id=1 AND team_id=%s",
            (tenant, team),
        )
        previous_link = cursor.fetchone()
    scope_query = {"userName": "user_directory_", "pageSize": 200}
    try:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='TEAM_ADMIN' WHERE user_id=1")
            cursor.execute(
                "INSERT INTO orbit_business_team_manager"
                "(tenant_id,manager_user_id,team_id,enabled) "
                "VALUES(%s,1,%s,1) ON DUPLICATE KEY UPDATE enabled=1",
                (tenant, team),
            )
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
            cursor.execute(
                "SELECT u.user_id FROM sys_user u "
                "JOIN orbit_business_user b ON b.user_id=u.user_id "
                "JOIN orbit_user_scope s ON s.user_id=b.user_id AND s.tenant_id=b.tenant_id "
                "WHERE b.tenant_id=%s AND u.user_name LIKE 'user_directory_%%' "
                "AND EXISTS(SELECT 1 FROM orbit_business_team_manager m "
                "WHERE m.tenant_id=b.tenant_id "
                "AND m.team_id=b.team_id AND m.manager_user_id=1 AND m.enabled=1)",
                (tenant,),
            )
            expected = {row[0] for row in cursor.fetchall()}
        limited = client.get("/system/user/list", headers=headers, params=scope_query)
        assert limited.status_code == 200 and limited.json()["total"] == len(expected)
        assert {row["userId"] for row in limited.json()["rows"]} == expected
        assert own["native"] in expected
        assert (
            client.get("/system/user/list", headers=headers, params=scope_query).headers.get(
                "x-api-cache"
            )
            == "HIT"
        )
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE tenant_id=%s "
                "AND manager_user_id=1 AND team_id=%s",
                (tenant, team),
            )
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
        revoked = client.get("/system/user/list", headers=headers, params=scope_query)
        assert revoked.status_code == 200 and revoked.headers.get("x-api-cache") == "MISS"
        assert own["native"] not in {row["userId"] for row in revoked.json()["rows"]}
        assert client.get("/system/user/" + str(own["native"]), headers=headers).status_code == 404
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=1")
            if previous_link is None:
                cursor.execute(
                    "DELETE FROM orbit_business_team_manager "
                    "WHERE tenant_id=%s AND manager_user_id=1 AND team_id=%s",
                    (tenant, team),
                )
            else:
                cursor.execute(
                    "UPDATE orbit_business_team_manager SET enabled=%s "
                    "WHERE tenant_id=%s AND manager_user_id=1 AND team_id=%s",
                    (previous_link[0], tenant, team),
                )
            cursor.execute(
                "UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
            )
    cases.append(NATIVE_DIRECTORY_CASES[3])
