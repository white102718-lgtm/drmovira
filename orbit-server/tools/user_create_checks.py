"""人员创建真实HTTP专项；只在运行器专属临时数据库执行。"""

import uuid

USER_CREATE_CASES = [
    "pythonUserCreateAllFieldsNoPasswordAndIdempotentReplay",
    "pythonUserCreateStrictStatusReferencesAndReadonlyFields",
    "pythonUserCreateActionDataRoleAndCsrfIntersection",
    "pythonUserCreateAuditOutboxAtomicRollbackAndRetry",
    "pythonUserCreateContactsDoNotMergeIdentities",
    "pythonUserCreateFiveHundredManagedTeamsFitBodyAndBatchPersist",
    "pythonUserReferenceOptionsBoundedKeysetAndPermissionBoundary",
]


def run_user_create_checks(client, admin, headers, fixture, cases):
    base = "/api/v1/users"
    tenant = "00000000-0000-0000-0000-000000000001"
    caps_response = client.get(base + "/capabilities", headers=headers)
    assert caps_response.status_code == 200
    caps = caps_response.json()
    assert set(caps) == {
        "data_role",
        "managed_team_ids",
        "can_create",
        "actor_user_id",
        "protected_user_ids",
        "csrf_token",
    }
    assert caps["can_create"] and caps["data_role"] == "SUPER_ADMIN"
    assert str(uuid.UUID(caps["actor_user_id"])) == caps["actor_user_id"]
    assert caps["protected_user_ids"] == [caps["actor_user_id"]]
    body = {
        "display_name": "😀" * 50,
        "nickname": "e\u0301" * 50,
        "email": "new-user@fixture.example.org",
        "phone": "+86 " + "7" * 28,
        "team_id": fixture["users"][1]["team"],
        "role_ids": [fixture["role_id"]],
        "data_role": "USER",
        "managed_team_ids": [],
        "status": "INVITED",
    }

    def post(value, key=None, csrf=None):
        return client.post(
            base,
            headers=headers
            | {
                "X-CSRF-Token": csrf or caps["csrf_token"],
                "Idempotency-Key": key or "user-create-" + uuid.uuid4().hex,
            },
            json=value,
        )

    key = "user-create-" + uuid.uuid4().hex
    response = post(body, key)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created == {
        **body,
        "nickname": "é" * 50,
        "id": created["id"],
        "revision": 1,
        "identity_status": "UNVERIFIED",
    }
    assert client.get(base + "/" + created["id"], headers=headers).json() == created
    assert post(body, key).json() == created
    assert post(body | {"nickname": "不同请求"}, key).status_code == 409
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT u.password,u.status,b.invited,s.auth_version,u.user_name "
            "FROM orbit_business_user b JOIN sys_user u ON u.user_id=b.user_id "
            "JOIN sys_identity_subject s ON s.user_id=u.user_id WHERE b.id=%s",
            (created["id"],),
        )
        row = cursor.fetchone()
        assert row[:4] == (None, "1", 1, 1) and len(row[4]) == 28
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_directory_audit WHERE resource_id=%s",
            (created["id"],),
        )
        assert cursor.fetchone()[0] == 1
    cases.append(USER_CREATE_CASES[0])
    for change, status in (
        ({"status": "ENABLED"}, 422),
        ({"team_id": str(uuid.uuid4())}, 422),
        ({"managed_team_ids": [str(uuid.uuid4())], "data_role": "TEAM_ADMIN"}, 422),
        ({"role_ids": [str(uuid.uuid4())]}, 422),
        ({"identity_status": "LOCAL_ACCOUNT"}, 400),
        ({"tenant_id": tenant}, 400),
        ({"phone": "1" * 33}, 422),
    ):
        denied = post(body | change)
        assert denied.status_code == status, denied.text
    cases.append(USER_CREATE_CASES[1])
    assert (
        client.post(base, headers=headers | {"Idempotency-Key": key}, json=body).status_code == 403
    )
    assert (
        client.post(
            base,
            headers=headers
            | {
                "X-CSRF-Token": caps["csrf_token"],
                "Idempotency-Key": "short",
            },
            json=body,
        ).status_code
        == 400
    )
    with admin.cursor() as cursor:
        cursor.execute("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1")
    try:
        assert client.get(base + "/capabilities", headers=headers).json()["can_create"] is False
        assert post(body).status_code == 403
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=1")
    manager = fixture["manager_headers"]
    assert client.get(base + "/capabilities", headers=manager).json()["can_create"] is False
    assert (
        client.post(
            base,
            headers=manager
            | {
                "X-CSRF-Token": caps["csrf_token"],
                "Idempotency-Key": "foreign-csrf-" + uuid.uuid4().hex,
            },
            json=body,
        ).status_code
        == 403
    )
    # 暂借独立fixture身份验证CSRF确实绑定会话，而非只因数据角色不足拒绝。
    with admin.cursor() as cursor:
        cursor.execute("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=980000")
    try:
        assert client.get(base + "/capabilities", headers=manager).json()["can_create"] is True
        cross = client.post(
            base,
            headers=manager
            | {
                "X-CSRF-Token": caps["csrf_token"],
                "Idempotency-Key": "foreign-csrf-" + uuid.uuid4().hex,
            },
            json=body,
        )
        assert cross.status_code == 403 and cross.json()["code"] == "CSRF_INVALID"
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_user_scope SET data_role='TEAM_ADMIN' WHERE user_id=980000"
            )
    cases.append(USER_CREATE_CASES[2])

    tables = (
        "sys_user",
        "sys_identity_subject",
        "sys_user_role",
        "orbit_user_scope",
        "orbit_business_user",
        "orbit_business_team_manager",
        "orbit_directory_audit",
        "orbit_directory_outbox",
        "orbit_directory_idempotency",
    )

    def counts():
        with admin.cursor() as cursor:
            result = []
            for table in tables:
                cursor.execute("SELECT COUNT(*) FROM " + table)
                result.append(cursor.fetchone()[0])
            return result

    for table in ("orbit_directory_audit", "orbit_directory_outbox"):
        before = counts()
        retry_key = "user-rollback-" + uuid.uuid4().hex
        with admin.cursor() as cursor:
            cursor.execute(
                "CREATE TRIGGER user_create_fail BEFORE INSERT ON "
                + table
                + " FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture failure'"
            )
        try:
            failed = post(body | {"display_name": "失败不得留半个人员"}, retry_key)
            assert failed.status_code == 503 and "fixture failure" not in failed.text
            assert counts() == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute("DROP TRIGGER user_create_fail")
        assert post(body | {"display_name": "失败不得留半个人员"}, retry_key).status_code == 201
    cases.append(USER_CREATE_CASES[3])
    duplicate = post(body | {"display_name": "相同联系方式不合并主体"})
    assert duplicate.status_code == 201 and duplicate.json()["id"] != created["id"]
    cases.append(USER_CREATE_CASES[4])
    teams = sorted(str(uuid.uuid4()) for _ in range(500))
    with admin.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,%s)",
            [
                (tenant, identifier, "批量管理团队" + str(index))
                for index, identifier in enumerate(teams)
            ],
        )
    large = post(
        body
        | {
            "display_name": "人员创建大范围",
            "data_role": "TEAM_ADMIN",
            "managed_team_ids": teams,
        }
    )
    assert large.status_code == 201, large.text
    assert (
        client.get(base + "/" + large.json()["id"], headers=headers).json()["managed_team_ids"]
        == teams
    )
    disabled = post(body | {"display_name": "未验证的停用人员", "status": "DISABLED"})
    assert disabled.status_code == 201 and disabled.json()["identity_status"] == "UNVERIFIED"
    assert (
        client.get(base + "/" + disabled.json()["id"], headers=headers).json()["status"]
        == "DISABLED"
    )
    cases.append(USER_CREATE_CASES[5])
    options = base + "/reference-options"
    params = {"kind": "TEAM", "q": "批量管理团队", "page_size": 20}
    page = client.get(options, headers=headers, params=params)
    assert page.status_code == 200 and len(page.json()["items"]) == 20
    assert set(page.json()) == {"items", "next_cursor"}
    assert all(set(item) == {"id", "name"} for item in page.json()["items"])
    continuation = page.json()["next_cursor"]
    second = client.get(options, headers=headers, params=params | {"cursor": continuation})
    assert second.status_code == 200 and len(second.json()["items"]) == 20
    assert not ({i["id"] for i in page.json()["items"]} & {i["id"] for i in second.json()["items"]})
    assert client.get(options, headers=manager, params=params).status_code == 403
    assert client.get(options, headers=headers, params=params | {"kind": "USER"}).status_code == 422
    assert client.get(options + "?kind=TEAM&kind=ROLE", headers=headers).status_code == 400
    assert (
        client.get(options, headers=headers, params=params | {"tenant_id": tenant}).status_code
        == 400
    )
    roles = client.get(options, headers=headers, params={"kind": "ROLE", "page_size": 200})
    assert roles.status_code == 200 and fixture["role_id"] in {
        i["id"] for i in roles.json()["items"]
    }
    with admin.cursor() as cursor:
        cursor.execute("SELECT id FROM orbit_business_role WHERE built_in=1")
        protected = {row[0] for row in cursor.fetchall()}
    assert not protected & {i["id"] for i in roles.json()["items"]}
    # 真实目录写入后旧选项游标拒绝，不能混用不同目录版本。
    assert post(body | {"display_name": "选项游标水位变更"}).status_code == 201
    stale = client.get(options, headers=headers, params=params | {"cursor": continuation})
    assert stale.status_code == 409 and stale.json()["code"] == "CURSOR_STALE"
    cases.append(USER_CREATE_CASES[6])
