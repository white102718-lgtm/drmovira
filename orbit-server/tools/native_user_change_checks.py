"""原人员资料编辑同事务版本/审计专项；沿用真实登录，不绕过原接口认证。"""

import uuid

NATIVE_USER_CHANGE_CASES = [
    "pythonNativeProfileAdvancesBusinessVersionAuditAndCursor",
    "pythonNativeProfileNoopDoesNotCreateFakeBusinessChange",
    "pythonNativeProfileAuditAndOutboxFailuresRollbackEverything",
    "pythonNativeFullFormRoleChangeTracksBusinessRevisionAndRevocation",
]


def run_native_user_change_checks(client, admin, headers, fixture, cases):
    target = fixture["users"][1]
    path = "/api/v1/users/" + target["id"]
    before = client.get(path, headers=headers).json()
    own_headers = fixture["actor_headers"]

    def counters():
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT revision FROM orbit_directory_clock WHERE tenant_id="
                "'00000000-0000-0000-0000-000000000001'"
            )
            clock = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_directory_audit WHERE resource_type='USER' "
                "AND resource_id=%s",
                (target["id"],),
            )
            audit = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_directory_outbox WHERE resource_type='USER' "
                "AND resource_id=%s",
                (target["id"],),
            )
            outbox = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM orbit_directory_idempotency")
            return clock, audit, outbox, cursor.fetchone()[0]

    old_counts = counters()
    page = client.get(
        "/api/v1/users", headers=headers, params={"q": "人员目录专项", "page_size": 20}
    ).json()
    changed = {
        "nickName": "😀" * 50,
        "email": "a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 61,
        "phonenumber": "+86 " + "9" * 28,
    }
    saved = client.put("/system/user/profile", headers=own_headers, json=changed)
    assert saved.status_code == 200 and saved.json()["code"] == 200
    after = client.get(path, headers=headers).json()
    assert after["revision"] == before["revision"] + 1
    assert after["nickname"] == changed["nickName"] and after["phone"] == changed["phonenumber"]
    assert after["email"] == changed["email"] and after["display_name"] == before["display_name"]
    for field, invalid in (
        ("nickName", "😀" * 51),
        ("email", changed["email"] + "a"),
        ("phonenumber", changed["phonenumber"] + "1"),
    ):
        bad = client.put("/system/user/profile", headers=own_headers, json={field: invalid})
        assert bad.status_code != 200 or bad.json().get("code") != 200
        assert client.get(path, headers=headers).json() == after
    assert counters() == (old_counts[0] + 1, old_counts[1] + 1, old_counts[2] + 1, old_counts[3])
    assert (
        client.get(
            "/api/v1/users",
            headers=headers,
            params={"q": "人员目录专项", "page_size": 20, "cursor": page["next_cursor"]},
        ).status_code
        == 409
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT changed_fields_json,actor_id,actor_subject_id,actor_team_id "
            "FROM orbit_directory_audit WHERE resource_type='USER' AND resource_id=%s "
            "AND revision=%s",
            (target["id"], after["revision"]),
        )
        import json

        row = cursor.fetchone()
        assert set(json.loads(row[0])) == {"nickname", "email", "phone"}
        assert row[1:] == (980001, target["id"], target["team"])
    restored = client.put(
        "/system/user/profile",
        headers=own_headers,
        json={
            "nickName": before["nickname"],
            "email": before["email"],
            "phonenumber": before["phone"],
        },
    )
    assert restored.status_code == 200 and restored.json()["code"] == 200
    cases.append(NATIVE_USER_CHANGE_CASES[0])
    stable = client.get(path, headers=headers).json()
    stable_counts = counters()
    noop = client.put(
        "/system/user/profile", headers=own_headers, json={"nickName": before["nickname"]}
    )
    assert noop.status_code == 200 and noop.json()["code"] == 200
    assert client.get(path, headers=headers).json() == stable and counters() == stable_counts
    cases.append(NATIVE_USER_CHANGE_CASES[1])
    for table in ("orbit_directory_audit", "orbit_directory_outbox"):
        with admin.cursor() as cursor:
            cursor.execute(
                "CREATE TRIGGER it_native_profile_failure BEFORE INSERT ON "
                + table
                + " FOR EACH ROW SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT='fixture-native-profile-failure'"
            )
        try:
            failed = client.put(
                "/system/user/profile", headers=own_headers, json={"nickName": "必须原子回滚"}
            )
            assert failed.status_code != 200 or failed.json().get("code") != 200
            assert client.get(path, headers=headers).json() == stable
            assert counters() == stable_counts
        finally:
            with admin.cursor() as cursor:
                cursor.execute("DROP TRIGGER it_native_profile_failure")
    cases.append(NATIVE_USER_CHANGE_CASES[2])
    caps = client.get("/api/v1/roles/capabilities", headers=headers).json()
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "Idempotency-Key": "native-user-role-" + uuid.uuid4().hex,
            "X-CSRF-Token": caps["csrf_token"],
        },
        json={
            "name": "原人员入口版本专项角色",
            "menu_codes": ["system"],
            "permission_codes": ["system.users.manage", "system.read"],
        },
    )
    assert role.status_code == 201
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE id=%s", (role.json()["id"],)
        )
        native_role = cursor.fetchone()[0]
    revision = stable["revision"]
    for assigned, expected_roles in (
        (native_role, [role.json()["id"]]),
        (fixture["native_role"], [fixture["role_id"]]),
    ):
        full = client.put(
            "/system/user",
            headers=headers,
            json={
                "userId": 980001,
                "userName": target["name"],
                "nickName": before["nickname"],
                "email": before["email"],
                "phonenumber": before["phone"],
                "roleIds": [assigned],
                "postIds": [],
            },
        )
        assert full.status_code == 200 and full.json()["code"] == 200
        revision += 1
        actual = client.get(path, headers=headers).json()
        assert actual["revision"] == revision and actual["role_ids"] == expected_roles
    revoked = client.get("/getInfo", headers=own_headers)
    assert revoked.status_code == 401 or revoked.json().get("code") == 401
    cases.append(NATIVE_USER_CHANGE_CASES[3])
