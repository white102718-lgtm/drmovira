"""原角色分配入口真实专项：不继承原菜单通配权限为业务租户权限。"""

import time
import uuid

NATIVE_USER_ROLE_CASES = [
    "pythonNativeRoleAssignmentAdvancesUserRevisionAndStalesCas",
    "pythonNativeRoleBatchAddCancelAndNoopHaveExactChanges",
    "pythonNativeRoleBatchAuditOutboxRollbackAllUsersAndEpochs",
    "pythonNativeRoleAssignmentCannotIntroduceBuiltinUnmappedOrEmptyRoles",
    "pythonNativeRoleAssignmentNoopTenantAndActionAreStillChecked",
    "pythonNativeRoleBatchRejectsMixedTenantAndOversizeBeforeWrites",
    "pythonNativeRoleBatchAcceptsTwoHundredTargetsAndTracksEveryRevision",
]


def run_native_user_role_checks(client, admin, headers, fixture, cases):
    tenant = "00000000-0000-0000-0000-000000000001"
    targets = [fixture["users"][index] for index in (20, 21, 23)]
    tracked = [target["native"] for target in targets] + [980100]
    api = "/api/v1/users/"
    caps = client.get("/api/v1/roles/capabilities", headers=headers).json()
    created = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": caps["csrf_token"],
            "Idempotency-Key": "native-assignment-" + uuid.uuid4().hex,
        },
        json={
            "name": "原角色分配衔接专项",
            "menu_codes": ["system"],
            "permission_codes": ["system.read", "system.users.manage"],
        },
    )
    assert created.status_code == 201
    role_id = created.json()["id"]
    with admin.cursor() as cursor:
        cursor.execute("SELECT native_role_id FROM orbit_business_role WHERE id=%s", (role_id,))
        native_role = cursor.fetchone()[0]

    def get(target):
        response = client.get(api + target["id"], headers=headers)
        assert response.status_code == 200
        return response.json()

    def snapshot():
        with admin.cursor() as cursor:
            slots = ",".join(["%s"] * len(tracked))
            cursor.execute(
                "SELECT b.user_id,b.revision,b.updated_at,i.auth_version "
                "FROM orbit_business_user b "
                "JOIN sys_identity_subject i ON i.user_id=b.user_id "
                "WHERE b.user_id IN (" + slots + ") ORDER BY b.user_id",
                tracked,
            )
            people = cursor.fetchall()
            cursor.execute(
                "SELECT user_id,role_id FROM sys_user_role WHERE user_id IN ("
                + slots
                + ") ORDER BY user_id,role_id",
                tracked,
            )
            associations = cursor.fetchall()
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
            return people, associations, clock, counts

    def ok(response):
        assert response.status_code == 200 and response.json().get("code") == 200

    def rejected(response, message):
        assert response.status_code != 200 or response.json().get("code") != 200
        assert message in response.json().get("msg", response.json().get("message", ""))

    def assign(target, roles):
        return client.put(
            "/system/user/authRole",
            headers=headers,
            params={"userId": target["native"], "roleIds": roles},
        )

    def batch(action, people):
        return client.put(
            "/system/role/authUser/" + action,
            headers=headers,
            params={"roleId": native_role, "userIds": ",".join(str(person) for person in people)},
        )

    target = targets[2]
    before = get(target)
    previous = snapshot()
    ok(assign(target, str(native_role)))
    after = get(target)
    assert after["revision"] == before["revision"] + 1 and after["role_ids"] == [role_id]
    changed = snapshot()
    assert changed[2] == previous[2] + 2
    assert changed[3] == [previous[3][0] + 1, previous[3][1] + 1, previous[3][2]]
    user_caps = client.get(api + "capabilities", headers=headers).json()
    stale = client.put(
        api + target["id"],
        headers=headers
        | {
            "X-CSRF-Token": user_caps["csrf_token"],
            "Idempotency-Key": "native-cas-" + uuid.uuid4().hex,
            "If-Match": f'"{before["revision"]}"',
        },
        json={
            key: value
            for key, value in before.items()
            if key not in {"id", "revision", "identity_status"}
        },
    )
    assert stale.status_code == 409
    ok(assign(target, str(native_role)))
    assert snapshot() == changed
    ok(assign(target, str(fixture["native_role"])))
    cases.append(NATIVE_USER_ROLE_CASES[0])
    pair = targets[:2]
    before = [get(person) for person in pair]
    previous = snapshot()
    ok(batch("selectAll", [person["native"] for person in pair]))
    for person, old in zip(pair, before, strict=True):
        current = get(person)
        assert current["revision"] == old["revision"] + 1
        assert set(current["role_ids"]) == {fixture["role_id"], role_id}
    assert snapshot()[2] == previous[2] + 3
    ok(
        client.put(
            "/system/role/authUser/cancel",
            headers=headers,
            json={"userId": pair[0]["native"], "roleId": native_role},
        )
    )
    ok(batch("cancelAll", [person["native"] for person in pair]))
    for person, old in zip(pair, before, strict=True):
        assert get(person)["revision"] == old["revision"] + 2
        assert get(person)["role_ids"] == old["role_ids"]
    assert snapshot()[2] == previous[2] + 7
    stable = snapshot()
    ok(batch("cancelAll", [person["native"] for person in pair]))
    assert snapshot() == stable
    cases.append(NATIVE_USER_ROLE_CASES[1])
    for table in ("orbit_directory_audit", "orbit_directory_outbox"):
        stable = snapshot()
        before = [get(person) for person in pair]
        with admin.cursor() as cursor:
            cursor.execute(
                "CREATE TRIGGER native_role_fail BEFORE INSERT ON "
                + table
                + " FOR EACH ROW SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT='fixture-native-role-failure'"
            )
        try:
            failed = batch("selectAll", [person["native"] for person in pair])
            assert failed.status_code != 200 or failed.json().get("code") != 200
            assert "fixture-native-role-failure" not in failed.text
            assert snapshot() == stable
            assert [get(person) for person in pair] == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute("DROP TRIGGER native_role_fail")
        ok(batch("selectAll", [person["native"] for person in pair]))
        ok(batch("cancelAll", [person["native"] for person in pair]))
    cases.append(NATIVE_USER_ROLE_CASES[2])
    for roles, message in (("1", "基础管理员角色只读"), ("2", "已登记"), ("", "至少保留")):
        stable = snapshot()
        rejected(assign(target, roles), message)
        assert snapshot() == stable
    cases.append(NATIVE_USER_ROLE_CASES[3])
    stable = snapshot()
    rejected(assign({"native": 980100}, "980100"), "不能跨业务租户")
    assert snapshot() == stable
    with admin.cursor() as cursor:
        cursor.execute("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1")
    try:
        rejected(assign(target, str(fixture["native_role"])), "授权")
        assert snapshot() == stable
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=1")
    with admin.cursor() as cursor:
        cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31082")
    try:
        rejected(assign(target, str(fixture["native_role"])), "权限")
        assert snapshot() == stable
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status='0' WHERE menu_id=31082")
    cases.append(NATIVE_USER_ROLE_CASES[4])
    rejected(batch("selectAll", [pair[0]["native"], 980100]), "不能跨业务租户")
    assert snapshot() == stable
    rejected(batch("selectAll", [pair[0]["native"]] * 201), "最多200")
    assert snapshot() == stable
    cases.append(NATIVE_USER_ROLE_CASES[5])
    with admin.cursor() as cursor:
        cursor.execute("SELECT COALESCE(MAX(user_id),0)+1 FROM sys_user")
        start = cursor.fetchone()[0]
        identifiers = list(range(start, start + 200))
        business_ids = [str(uuid.uuid4()) for _ in identifiers]
        cursor.executemany(
            "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "VALUES(%s,%s,%s,%s,NULL,'1','0')",
            [
                (
                    identifier,
                    "role_boundary_" + str(identifier),
                    "原角色边界" + str(index),
                    "role-boundary-" + str(identifier) + "@fixture.example.org",
                )
                for index, identifier in enumerate(identifiers)
            ],
        )
        cursor.executemany(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
            [(identifier, str(uuid.uuid4())) for identifier in identifiers],
        )
        cursor.executemany(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
            [(identifier, tenant) for identifier in identifiers],
        )
        cursor.executemany(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,invited) "
            "VALUES(%s,%s,%s,%s,1)",
            [
                (tenant, business_id, identifier, fixture["users"][1]["team"])
                for identifier, business_id in zip(identifiers, business_ids, strict=True)
            ],
        )
        cursor.executemany(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
            [(identifier, fixture["native_role"]) for identifier in identifiers],
        )
    clock_before = snapshot()[2]
    started = time.monotonic()
    ok(batch("selectAll", identifiers))
    added_seconds = time.monotonic() - started
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*),MIN(b.revision),MAX(b.revision),"
            "MIN(i.auth_version),MAX(i.auth_version) "
            "FROM orbit_business_user b JOIN sys_identity_subject i ON i.user_id=b.user_id "
            "WHERE b.user_id BETWEEN %s AND %s",
            (identifiers[0], identifiers[-1]),
        )
        assert cursor.fetchone() == (200, 2, 2, 2, 2)
        cursor.execute(
            "SELECT COUNT(*) FROM sys_user_role WHERE user_id BETWEEN %s AND %s AND role_id=%s",
            (identifiers[0], identifiers[-1], native_role),
        )
        assert cursor.fetchone()[0] == 200
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_directory_audit a JOIN orbit_business_user b "
            "ON b.id=a.resource_id AND b.tenant_id=a.tenant_id "
            "WHERE b.user_id BETWEEN %s AND %s AND a.resource_type='USER' "
            "AND a.revision=2 AND a.before_revision=1 AND JSON_LENGTH(a.changed_fields_json)=1 "
            "AND JSON_CONTAINS(a.changed_fields_json,'\"role_ids\"')",
            (identifiers[0], identifiers[-1]),
        )
        assert cursor.fetchone()[0] == 200
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_directory_outbox o JOIN orbit_business_user b "
            "ON b.id=o.resource_id AND b.tenant_id=o.tenant_id "
            "WHERE b.user_id BETWEEN %s AND %s AND o.resource_type='USER' AND o.revision=2",
            (identifiers[0], identifiers[-1]),
        )
        assert cursor.fetchone()[0] == 200
    assert snapshot()[2] == clock_before + 201
    started = time.monotonic()
    ok(batch("cancelAll", identifiers))
    removed_seconds = time.monotonic() - started
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*),MIN(b.revision),MAX(b.revision),"
            "MIN(i.auth_version),MAX(i.auth_version) "
            "FROM orbit_business_user b JOIN sys_identity_subject i ON i.user_id=b.user_id "
            "WHERE b.user_id BETWEEN %s AND %s",
            (identifiers[0], identifiers[-1]),
        )
        assert cursor.fetchone() == (200, 3, 3, 3, 3)
        cursor.execute(
            "SELECT COUNT(*) FROM sys_user_role WHERE user_id BETWEEN %s AND %s AND role_id=%s",
            (identifiers[0], identifiers[-1], native_role),
        )
        assert cursor.fetchone()[0] == 0
        for table, event_column in (
            ("orbit_directory_audit", "revision"),
            ("orbit_directory_outbox", "revision"),
        ):
            cursor.execute(
                "SELECT COUNT(*) FROM " + table + " e JOIN orbit_business_user b "
                "ON b.id=e.resource_id AND b.tenant_id=e.tenant_id "
                "WHERE b.user_id BETWEEN %s AND %s AND e.resource_type='USER' "
                "AND e." + event_column + "=3",
                (identifiers[0], identifiers[-1]),
            )
            assert cursor.fetchone()[0] == 200
    assert snapshot()[2] == clock_before + 402
    cases.append(NATIVE_USER_ROLE_CASES[6])
    return {
        "targets": 200,
        "add_seconds": round(added_seconds, 3),
        "remove_seconds": round(removed_seconds, 3),
    }
