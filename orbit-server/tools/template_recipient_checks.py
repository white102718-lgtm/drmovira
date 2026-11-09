"""模板share-only最小权限与真实成员漂移专项；只在主线UUID孤立库执行。"""

import uuid

from fixture_login import fixture_login
from launch_draft_template_checks import assert_status, snapshot

TEMPLATE_RECIPIENT_CASES = [
    "pythonTemplateShareOnlyCandidateNeedsNoLaunchReadOrSystemUserAction",
    "pythonTemplateRecipientForeignMovedDisabledRejectsAtomicShare",
    "pythonTemplateRecipientCursorBindsTemplateVersionAndTargetTeam",
    "pythonTemplateShareOnlyRevocationRejectsCandidateAndSuccessfulKeyReplay",
]


def fixture_username():
    """原若依sys_user.user_name为VARCHAR(30)，控制身份账号不可越过真实表约束。"""
    return "tplr_" + uuid.uuid4().hex[:24]


def run_template_recipient_checks(client, admin, headers, fixture, password, cache, cases):
    snapshot(admin)
    user, other_team = fixture["users"][1], fixture["users"][2]["team"]
    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id FROM orbit_user_scope WHERE user_id=1")
        tenant = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM orbit_business_user WHERE tenant_id<>%s LIMIT 1", (tenant,))
        foreign_owner = cursor.fetchone()[0]
        cursor.execute("SELECT role_id FROM sys_user_role WHERE user_id=%s", (user["native"],))
        original_roles = [row[0] for row in cursor.fetchall()]

    def role(permissions):
        caps = assert_status(client.get("/api/v1/roles/capabilities", headers=headers), 200)
        result = assert_status(
            client.post(
                "/api/v1/roles",
                headers=headers
                | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": str(uuid.uuid4())},
                json={
                    "name": "模板最小动作" + uuid.uuid4().hex[:10],
                    "menu_codes": ["launch"],
                    "permission_codes": permissions,
                },
            ),
            201,
        )
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
                (tenant, result["id"]),
            )
            return cursor.fetchone()[0]

    def login_with(native_role):
        with admin.cursor() as cursor:
            cursor.execute("DELETE FROM sys_user_role WHERE user_id=%s", (user["native"],))
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (user["native"], native_role),
            )
        logged = assert_status(
            fixture_login(client, cache, {"username": user["name"], "password": password}), 200
        )
        return {"Authorization": "Bearer " + logged["token"]}

    def members(identity, template_id=None, after=None, size=200):
        return client.get(
            "/api/v1/templates/recipient-options",
            headers=identity,
            params={"page_size": size}
            | ({"template_id": template_id} if template_id else {})
            | ({"cursor": after} if after else {}),
        )

    def write(identity, candidates, revision, key=None):
        return identity | {
            "X-CSRF-Token": candidates["csrf_token"],
            "Idempotency-Key": key or str(uuid.uuid4()),
            "If-Match": f'"{revision}"',
        }

    setup_role = role(["templates.read", "templates.create"])
    share_role = role(["templates.share"])
    try:
        setup_identity = login_with(setup_role)
        caps = assert_status(
            client.get("/api/v1/templates/capabilities", headers=setup_identity), 200
        )
        body = {
            "name": "仅共享动作" + uuid.uuid4().hex,
            "description": "",
            "visibility": "PRIVATE",
            "recipient_user_ids": [],
            "campaigns": [{"local_id": str(uuid.uuid4()), "copies": 1, "adsets": []}],
        }
        template = assert_status(
            client.post(
                "/api/v1/templates",
                headers=setup_identity
                | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": str(uuid.uuid4())},
                json=body,
            ),
            201,
        )
        template_id = template["id"]
        # 21名独立激活身份产生真实两页，不复用一个UUID或放宽最小page_size。
        controls = []
        for index in range(21):
            identifier, native = str(uuid.uuid4()), 50000000 + int(uuid.uuid4().hex[:6], 16)
            with admin.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,))
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    """INSERT INTO sys_user(user_id,user_name,nick_name,password,status,del_flag)
                SELECT %s,%s,%s,password,'0','0' FROM sys_user WHERE user_id=1""",
                    (native, fixture_username(), "共享候选控制" + str(index)),
                )
                cursor.execute(
                    "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
                    "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
                    (native, str(uuid.uuid4())),
                )
                cursor.execute(
                    "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) "
                    "VALUES(%s,%s,'USER')",
                    (native, tenant),
                )
                cursor.execute(
                    """INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,
                display_name,enabled,invited,created_at)
                VALUES(%s,%s,%s,%s,%s,1,0,UTC_TIMESTAMP(3))""",
                    (tenant, identifier, native, user["team"], "共享候选控制" + str(index)),
                )
            controls.append({"id": identifier, "native": native})
        identity = login_with(share_role)
        assert_status(client.get("/api/v1/templates", headers=identity), 403)
        assert_status(client.get("/api/v1/launch-plans/ownership-options", headers=identity), 403)
        assert_status(client.get("/api/v1/users", headers=identity), 403)
        first = assert_status(members(identity, template_id, size=20), 200)
        assert len(first["items"]) == 20 and first["next_cursor"]
        all_ids, after = {row["id"] for row in first["items"]}, first["next_cursor"]
        while after:
            page = assert_status(members(identity, template_id, after, 20), 200)
            ids = {row["id"] for row in page["items"]}
            assert not all_ids & ids
            all_ids |= ids
            after = page["next_cursor"]
        assert {person["id"] for person in controls} | {user["id"]} <= all_ids
        assert foreign_owner not in all_ids
        assert all(
            row["team_id"] == user["team"] and set(row) == {"id", "name", "team_id", "team_name"}
            for row in first["items"]
        )
        assert first["owner_team_id"] == user["team"] and first["csrf_token"]
        assert_status(members(identity, template_id, size=201), 422)
        assert_status(
            client.get(
                "/api/v1/templates/recipient-options",
                headers=identity,
                params={"team_id": other_team},
            ),
            400,
        )
        cases.append(TEMPLATE_RECIPIENT_CASES[0])

        path = "/api/v1/templates/" + template_id + "/share"
        control = controls[0]
        for state in ("FOREIGN", "DISABLED", "MOVED"):
            with admin.cursor() as cursor:
                if state == "DISABLED":
                    cursor.execute(
                        "UPDATE sys_user SET status='1' WHERE user_id=%s", (control["native"],)
                    )
                if state == "MOVED":
                    cursor.execute(
                        "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                        (other_team, tenant, control["id"]),
                    )
            try:
                current = assert_status(members(identity, template_id), 200)
                denied = foreign_owner if state == "FOREIGN" else control["id"]
                if state != "FOREIGN":
                    assert denied not in {row["id"] for row in current["items"]}
                before = snapshot(admin)
                assert_status(
                    client.post(
                        path,
                        headers=write(identity, current, 1),
                        json={
                            "recipient_user_ids": [controls[1]["id"], denied],
                            "reason": "必须整批拒绝",
                        },
                    ),
                    422,
                )
                assert snapshot(admin) == before
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE sys_user SET status='0' WHERE user_id=%s", (control["native"],)
                    )
                    cursor.execute(
                        "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                        (user["team"], tenant, control["id"]),
                    )
        candidates = assert_status(members(identity, template_id), 200)
        share_value = {
            "recipient_user_ids": [control["id"]],
            "reason": "只有共享动作也能维护真实冻结集合",
        }
        success_head = write(identity, candidates, 1)
        shared = assert_status(client.post(path, headers=success_head, json=share_value), 200)
        assert shared["revision"] == 2 and shared["recipient_user_ids"] == [control["id"]]
        cases.append(TEMPLATE_RECIPIENT_CASES[1])

        previous = assert_status(members(identity, template_id, size=20), 200)
        assert previous["next_cursor"]
        before = snapshot(admin)
        assert_status(members(identity, None, previous["next_cursor"], 20), 409)
        assert snapshot(admin) == before
        next_value = {
            "recipient_user_ids": [controls[1]["id"]],
            "reason": "新共享版本废弃旧候选游标",
        }
        changed = assert_status(
            client.post(path, headers=write(identity, previous, 2), json=next_value), 200
        )
        assert changed["revision"] == 3
        assert_status(members(identity, template_id, previous["next_cursor"], 20), 409)
        cases.append(TEMPLATE_RECIPIENT_CASES[2])

        with admin.cursor() as cursor:
            cursor.execute("SELECT menu_id FROM sys_menu WHERE perms='templates.share'")
            share_menu = cursor.fetchone()[0]
            cursor.execute(
                "DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=%s",
                (share_role, share_menu),
            )
        try:
            before = snapshot(admin)
            assert_status(members(identity, template_id), 403)
            assert_status(client.post(path, headers=success_head, json=share_value), 403)
            assert snapshot(admin) == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)",
                    (share_role, share_menu),
                )
        cases.append(TEMPLATE_RECIPIENT_CASES[3])
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DELETE FROM sys_user_role WHERE user_id=%s", (user["native"],))
            for original in original_roles:
                cursor.execute(
                    "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                    (user["native"], original),
                )
