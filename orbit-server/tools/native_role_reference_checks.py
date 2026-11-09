"""原完整人员编辑和角色分配必须与业务角色引用合同一致。"""

import uuid

NATIVE_ROLE_REFERENCE_CASES = [
    "pythonNativeRoleReferencesRejectMissingAndDeletedWithoutPartialWrites",
    "pythonNativeRoleReferencesRejectNewDisabledButRetainAssignedDisabled",
    "pythonNativeRoleReferencesEnforceTwentyUniqueRolesBeforeWrites",
    "pythonNativeRoleReferenceBatchFailureRollsBackEveryMember",
]


def run_native_role_reference_checks(client, admin, headers, fixture, cases):
    tenant = "00000000-0000-0000-0000-000000000001"
    # 使用独立目标，角色改动不能使后续本人资料专项的登录凭据提前失效。
    target = fixture["users"][22]
    native = target["native"]
    base = fixture["native_role"]
    public_url = "/api/v1/users/" + target["id"]
    detail = client.get("/system/user/" + str(native), headers=headers).json()
    body = detail["data"] | {"roleIds": detail["roleIds"], "postIds": detail["postIds"]}
    body.pop("password", None)
    with admin.cursor() as cursor:
        cursor.execute("SELECT COALESCE(MAX(role_id),0)+1 FROM sys_role")
        first = cursor.fetchone()[0]
        roles = list(range(first, first + 21))
        cursor.executemany(
            "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,status,del_flag) "
            "VALUES(%s,%s,%s,1,'0','0')",
            [(role, "引用边界" + str(role), "reference_boundary_" + str(role)) for role in roles],
        )
        cursor.executemany(
            "INSERT INTO orbit_business_role(tenant_id,id,native_role_id,created_at,updated_at) "
            "VALUES(%s,%s,%s,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            [(tenant, str(uuid.uuid4()), role) for role in roles],
        )

    def state(user_id=native):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT user_name,nick_name,email,phonenumber,dept_id,status,del_flag "
                "FROM sys_user WHERE user_id=%s",
                (user_id,),
            )
            user = cursor.fetchone()
            cursor.execute(
                "SELECT role_id FROM sys_user_role WHERE user_id=%s ORDER BY role_id", (user_id,)
            )
            grants = cursor.fetchall()
            cursor.execute(
                "SELECT b.revision,b.updated_at,i.auth_version FROM orbit_business_user b "
                "JOIN sys_identity_subject i ON i.user_id=b.user_id "
                "WHERE b.tenant_id=%s AND b.user_id=%s",
                (tenant, user_id),
            )
            identity = cursor.fetchone()
            cursor.execute(
                "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
            )
            clock = cursor.fetchone()[0]
            counts = []
            for table in ("orbit_directory_audit", "orbit_directory_outbox"):
                cursor.execute("SELECT COUNT(*) FROM " + table)
                counts.append(cursor.fetchone()[0])
            return user, grants, identity, clock, counts

    def write(entry, role_ids):
        if entry == "form":
            return client.put("/system/user", headers=headers, json=body | {"roleIds": role_ids})
        return client.put(
            "/system/user/authRole",
            headers=headers,
            params={"userId": native, "roleIds": ",".join(map(str, role_ids))},
        )

    def reject(role_ids):
        original = client.get(public_url, headers=headers).json()
        for entry in ("form", "assignment"):
            before = state()
            response = write(entry, role_ids)
            assert response.status_code < 500
            assert response.status_code != 200 or response.json().get("code") != 200, (
                "原入口接受不符合业务合同的角色引用"
            )
            assert state() == before
            assert client.get(public_url, headers=headers).json() == original

    with admin.cursor() as cursor:
        cursor.execute("UPDATE sys_role SET del_flag='2' WHERE role_id=%s", (roles[-1],))
    reject([base, roles[-1] + 1000000])
    reject([base, roles[-1]])
    # 历史损坏关系不能在新人员DTO中被JOIN静默丢掉；只在独立fixture注入并清理。
    for dangling in (roles[-1], roles[-1] + 1000000):
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, dangling)
            )
        try:
            unreadable = client.get(public_url, headers=headers)
            assert unreadable.status_code == 409
            assert unreadable.json()["code"] == "DIRECTORY_MAPPING_REQUIRED"
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s", (native, dangling)
                )
    cases.append(NATIVE_ROLE_REFERENCE_CASES[0])
    with admin.cursor() as cursor:
        cursor.execute("UPDATE sys_role SET status='1' WHERE role_id=%s", (roles[0],))
    reject([base, roles[0]])
    with admin.cursor() as cursor:
        cursor.execute("UPDATE sys_role SET status='1' WHERE role_id=%s", (base,))
    try:
        for entry in ("form", "assignment"):
            response = write(entry, [base])
            assert response.status_code == 200 and response.json().get("code") == 200
            assert client.get(public_url, headers=headers).status_code == 200
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_role SET status='0' WHERE role_id=%s", (base,))
    cases.append(NATIVE_ROLE_REFERENCE_CASES[1])
    with admin.cursor() as cursor:
        cursor.execute("UPDATE sys_role SET status='0' WHERE role_id=%s", (roles[0],))
    reject([base] + roles[:20])
    reject([base, base])
    for entry in ("form", "assignment"):
        maximum = [base] + roles[:19]
        response = write(entry, maximum)
        assert response.status_code == 200 and response.json().get("code") == 200
        assert len(client.get(public_url, headers=headers).json()["role_ids"]) == 20
        stable = state()
        replay = write(entry, maximum)
        assert replay.status_code == 200 and replay.json().get("code") == 200
        assert state() == stable
        restored = write(entry, [base])
        assert restored.status_code == 200 and restored.json().get("code") == 200
    cases.append(NATIVE_ROLE_REFERENCE_CASES[2])
    good = fixture["users"][21]["native"]

    def reject_batch(role):
        before = state(good), state()
        response = client.put(
            "/system/role/authUser/selectAll",
            headers=headers,
            params={"roleId": role, "userIds": f"{good},{native}"},
        )
        assert response.status_code < 500
        assert response.status_code != 200 or response.json().get("code") != 200
        assert (state(good), state()) == before

    # 第一人新增可成功，第二人已达20项；前者的版本/审计也必须随整笔事务撤销。
    response = write("form", [base] + roles[:19])
    assert response.status_code == 200 and response.json().get("code") == 200
    reject_batch(roles[19])
    restored = write("form", [base])
    assert restored.status_code == 200 and restored.json().get("code") == 200
    with admin.cursor() as cursor:
        cursor.execute("UPDATE sys_role SET status='1' WHERE role_id=%s", (roles[0],))
        cursor.execute("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (good, roles[0]))
    try:
        reject_batch(roles[0])
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s", (good, roles[0])
            )
            cursor.execute("UPDATE sys_role SET status='0' WHERE role_id=%s", (roles[0],))
    reject_batch(roles[-1] + 1000000)
    cases.append(NATIVE_ROLE_REFERENCE_CASES[3])
