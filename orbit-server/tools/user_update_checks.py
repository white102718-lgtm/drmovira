"""人员编辑真实HTTP专项：版本、权限、撤销、回滚与管理员存续。"""

import time
import uuid

USER_UPDATE_CASES = [
    "pythonUserUpdateAllFieldsCasIdempotencyAndSessionRevocation",
    "pythonUserUpdateNoopPreservesVersionAuditAndClock",
    "pythonUserUpdateStateReferencesSelfAndBuiltinBoundary",
    "pythonUserUpdateAuditOutboxAndIdentityRollback",
    "pythonUserUpdateRetainsDisabledAssignedReferences",
    "pythonUserUpdateLastRecoverableAdministratorRollback",
    "pythonUserUpdateConcurrentRevisionAndSameKeyHaveSingleCommit",
]


def run_user_update_checks(client, admin, headers, fixture, password, cache, cases):
    base = "/api/v1/users/"
    tenant = "00000000-0000-0000-0000-000000000001"
    target = fixture["users"][0]
    path = base + target["id"]
    csrf = client.get(base + "capabilities", headers=headers).json()["csrf_token"]
    initial = client.get(path, headers=headers).json()

    def body(value):
        return {k: v for k, v in value.items() if k not in {"id", "revision", "identity_status"}}

    def put(value, revision, key=None, url=path, actor=headers):
        return client.put(
            url,
            headers=actor
            | {
                "X-CSRF-Token": csrf,
                "Idempotency-Key": key or "user-update-" + uuid.uuid4().hex,
                "If-Match": f'"{revision}"',
            },
            json=value,
        )

    def state():
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT auth_version FROM sys_identity_subject WHERE user_id=%s",
                (target["native"],),
            )
            version = cursor.fetchone()[0]
            cursor.execute(
                "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
            )
            clock = cursor.fetchone()[0]
            counts = []
            for table in (
                "orbit_directory_audit",
                "orbit_directory_outbox",
                "orbit_directory_idempotency",
            ):
                cursor.execute("SELECT COUNT(*) FROM " + table)
                counts.append(cursor.fetchone()[0])
        return [version, clock, *counts]

    role_caps = client.get("/api/v1/roles/capabilities", headers=headers).json()
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": role_caps["csrf_token"],
            "Idempotency-Key": "user-update-role-" + uuid.uuid4().hex,
        },
        json={
            "name": "人员编辑专项可恢复角色",
            "menu_codes": ["system"],
            "permission_codes": ["system.read", "system.users.manage", "system.teams.manage"],
        },
    )
    assert role.status_code == 201
    role_id = role.json()["id"]
    usable = client.get("/getInfo", headers=fixture["manager_headers"])
    assert usable.status_code == 200 and usable.json()["code"] == 200
    changed = body(initial) | {
        "display_name": "人员目录专项编辑姓名0",
        "nickname": "😀" * 50,
        "email": "w" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 61,
        "phone": "+86 " + "5" * 28,
        "team_id": fixture["users"][1]["team"],
        "role_ids": [role_id],
        "data_role": "USER",
        "managed_team_ids": [],
    }
    before = state()
    key = "user-update-" + uuid.uuid4().hex
    saved = put(changed, initial["revision"], key)
    assert saved.status_code == 200, saved.text
    current = saved.json()
    assert current == {
        **changed,
        "id": target["id"],
        "revision": initial["revision"] + 1,
        "identity_status": "LOCAL_ACCOUNT",
    }
    assert client.get(path, headers=headers).json() == current
    after = state()
    assert after == [before[0] + 1, before[1] + 2, before[2] + 1, before[3] + 1, before[4] + 1]
    revoked = client.get("/getInfo", headers=fixture["manager_headers"])
    assert revoked.status_code == 401 or revoked.json().get("code") == 401
    assert put(changed, initial["revision"], key).json() == current
    assert put(changed | {"nickname": "不同请求"}, initial["revision"], key).status_code == 409
    assert put(changed, initial["revision"]).status_code == 409
    cases.append(USER_UPDATE_CASES[0])
    before = state()
    key = "user-noop-" + uuid.uuid4().hex
    assert put(changed, current["revision"], key).json() == current
    assert put(changed, current["revision"], key).json() == current
    assert state() == [*before[:4], before[4] + 1]
    cases.append(USER_UPDATE_CASES[1])
    root = client.get(base + "capabilities", headers=headers).json()["actor_user_id"]
    own = client.get(base + root, headers=headers).json()
    assert (
        put(body(own) | {"data_role": "USER"}, own["revision"], url=base + root).status_code == 403
    )
    assert (
        put(body(own) | {"status": "DISABLED"}, own["revision"], url=base + root).status_code == 403
    )
    assert put(changed | {"status": "INVITED"}, current["revision"]).status_code == 422
    pending_path = base + fixture["users"][26]["id"]
    pending = client.get(pending_path, headers=headers).json()
    assert (
        put(
            body(pending) | {"status": "ENABLED"}, pending["revision"], url=pending_path
        ).status_code
        == 422
    )
    assert put(changed | {"role_ids": [str(uuid.uuid4())]}, current["revision"]).status_code == 422
    assert (
        put(changed | {"identity_status": "LOCAL_ACCOUNT"}, current["revision"]).status_code == 400
    )
    assert put(changed, current["revision"], url=base + str(uuid.uuid4())).status_code == 404
    with admin.cursor() as cursor:
        cursor.execute("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1")
    try:
        assert put(changed, current["revision"]).status_code == 403
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=1")
    cases.append(USER_UPDATE_CASES[2])
    for index, table in enumerate(("orbit_directory_audit", "orbit_directory_outbox")):
        before = state()
        next_body = body(current) | {"role_ids": [fixture["role_id"] if index == 0 else role_id]}
        retry = "user-update-rollback-" + uuid.uuid4().hex
        with admin.cursor() as cursor:
            cursor.execute(
                "CREATE TRIGGER user_update_fail BEFORE INSERT ON "
                + table
                + " FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture failure'"
            )
        try:
            failed = put(next_body, current["revision"], retry)
            assert failed.status_code == 503 and "fixture failure" not in failed.text
            assert client.get(path, headers=headers).json() == current
            assert state() == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute("DROP TRIGGER user_update_fail")
        success = put(next_body, current["revision"], retry)
        assert success.status_code == 200
        current = success.json()
    cases.append(USER_UPDATE_CASES[3])
    with admin.cursor() as cursor:
        cursor.execute("SELECT native_role_id FROM orbit_business_role WHERE id=%s", (role_id,))
        new_native_role = cursor.fetchone()[0]
        cursor.execute("UPDATE sys_role SET status='1' WHERE role_id=%s", (new_native_role,))
    try:
        labels = client.get(
            base + "reference-options",
            headers=headers,
            params={"kind": "ROLE", "ids": role_id, "page_size": 200},
        )
        assert labels.status_code == 200 and labels.json()["items"] == [
            {"id": role_id, "name": "人员编辑专项可恢复角色"}
        ]
        retained = put(body(current) | {"nickname": "保留既有停用角色"}, current["revision"])
        assert retained.status_code == 200 and retained.json()["role_ids"] == [role_id]
        current = retained.json()
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_role SET status='0' WHERE role_id=%s", (new_native_role,))
    restored = put(body(initial), current["revision"])
    assert restored.status_code == 200
    cases.append(USER_UPDATE_CASES[4])
    for ids in (
        "",
        role_id + "," + role_id,
        "not-a-uuid",
        ",".join(str(uuid.uuid4()) for _ in range(101)),
    ):
        assert (
            client.get(
                base + "reference-options", headers=headers, params={"kind": "ROLE", "ids": ids}
            ).status_code
            == 422
        )
    with admin.cursor() as cursor:
        cursor.execute("SELECT id FROM orbit_business_role WHERE tenant_id<>%s LIMIT 1", (tenant,))
        foreign_role = cursor.fetchone()[0]
    invisible = client.get(
        base + "reference-options", headers=headers, params={"kind": "ROLE", "ids": foreign_role}
    )
    assert invisible.status_code == 200 and invisible.json()["items"] == []
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM orbit_business_team WHERE tenant_id=%s ORDER BY id LIMIT 100", (tenant,)
        )
        selected_teams = [row[0] for row in cursor.fetchall()]
    labels = client.get(
        base + "reference-options",
        headers=headers,
        params={"kind": "TEAM", "ids": ",".join(selected_teams), "page_size": 200},
    )
    assert (
        labels.status_code == 200
        and [item["id"] for item in labels.json()["items"]] == selected_teams
    )
    login = client.post("/login", json={"username": target["name"], "password": password})
    cooldown = time.monotonic()
    if login.status_code == 429:
        # 仅等待专属DB15的原12次/分钟登录窗口自然结束，不删键、不修改生产限流。
        print({"user_update_fixture_login_throttled": True})
        while list(cache.scan_iter(match="api_rate_limit:login:sliding_window:*")):
            assert time.monotonic() - cooldown < 65
            time.sleep(0.5)
        login = client.post("/login", json={"username": target["name"], "password": password})
    if login.status_code != 200 or not login.json().get("token"):
        print(
            {
                "user_update_fixture_login_http_status": login.status_code,
                "business_code": login.json().get("code"),
                "message": login.json().get("msg"),
            }
        )
    cooldown_seconds = round(time.monotonic() - cooldown, 3)
    assert login.status_code == 200 and login.json().get("token")
    manager = {"Authorization": "Bearer " + login.json()["token"]}
    last = fixture["users"][24]
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id IN(980000,980024)"
        )
        cursor.execute("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1")
        cursor.execute(
            "UPDATE sys_user_role SET role_id=%s WHERE user_id=980024", (new_native_role,)
        )
        cursor.execute("SELECT auth_version FROM sys_identity_subject WHERE user_id=980024")
        last_version = cursor.fetchone()[0]
    try:
        last_path = base + last["id"]
        last_before = client.get(last_path, headers=manager).json()
        manager_csrf = client.get(base + "capabilities", headers=manager).json()["csrf_token"]
        rejected = client.put(
            last_path,
            headers=manager
            | {
                "X-CSRF-Token": manager_csrf,
                "Idempotency-Key": "last-user-" + uuid.uuid4().hex,
                "If-Match": f'"{last_before["revision"]}"',
            },
            json=body(last_before) | {"status": "DISABLED"},
        )
        assert rejected.status_code == 409 and rejected.json()["code"] == "LAST_ADMIN_REQUIRED"
        assert client.get(last_path, headers=manager).json() == last_before
        with admin.cursor() as cursor:
            cursor.execute("SELECT auth_version FROM sys_identity_subject WHERE user_id=980024")
            assert cursor.fetchone()[0] == last_version
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=1")
            cursor.execute(
                "UPDATE orbit_user_scope SET data_role='TEAM_ADMIN' WHERE user_id=980000"
            )
            cursor.execute("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=980024")
            cursor.execute(
                "UPDATE sys_user_role SET role_id=%s WHERE user_id=980024",
                (fixture["native_role"],),
            )
    cases.append(USER_UPDATE_CASES[5])
    from concurrent.futures import ThreadPoolExecutor

    parallel_path = base + fixture["users"][22]["id"]
    original = client.get(parallel_path, headers=headers).json()
    for shared_key in (None, "same-user-key-" + uuid.uuid4().hex):
        before_parallel = client.get(parallel_path, headers=headers).json()
        change = body(before_parallel) | {"nickname": "同键并发" if shared_key else "版本并发"}
        before_state = state()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    put, change, before_parallel["revision"], shared_key, url=parallel_path
                )
                for _ in range(2)
            ]
            results = [future.result() for future in futures]
        assert sorted(r.status_code for r in results) == ([200, 200] if shared_key else [200, 409])
        latest = client.get(parallel_path, headers=headers).json()
        assert latest["revision"] == before_parallel["revision"] + 1
        if shared_key:
            assert results[0].json() == results[1].json() == latest
        assert state() == [before_state[0], *[number + 1 for number in before_state[1:]]]
    assert put(body(original), latest["revision"], url=parallel_path).status_code == 200
    cases.append(USER_UPDATE_CASES[6])
    fixture["manager_headers"] = manager
    return cooldown_seconds
