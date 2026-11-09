"""事件专项独占真实身份，仅UUID隔离库，不改原Task夹具。"""

from uuid import uuid4


def prepare_event_identities(client, admin, headers, password, cache):
    from fixture_login import fixture_login

    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, root_owner, team = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_id IN(990380,990381,990382)")
        assert cursor.fetchone()[0] == 0, "Task专用身份ID已占用，拒绝覆盖"
    cap = client.get("/api/v1/roles/capabilities", headers=headers)
    assert cap.status_code == 200
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": cap.json()["csrf_token"],
            "Idempotency-Key": "task-event-role-" + uuid4().hex,
        },
        json={
            "name": "Task事件专项-" + uuid4().hex[:12],
            "menu_codes": ["launch"],
            "permission_codes": ["tasks.read"],
        },
    )
    assert role.status_code == 201
    identities = {}
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role.json()["id"]),
        )
        native_role = cursor.fetchone()[0]
        for native, data_role in ((990380, "TEAM_ADMIN"), (990381, "USER"), (990382, "USER")):
            owner, name = str(uuid4()), "task_reader_" + uuid4().hex[:12]
            cursor.execute(
                "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
                "SELECT %s,%s,'任务只读夹具',%s,password,'0','0' FROM sys_user WHERE user_id=1",
                (native, name, name + "@fixture.example.org"),
            )
            cursor.execute(
                "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
                "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
                (native, str(uuid4())),
            )
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, native_role)
            )
            cursor.execute(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,%s)",
                (native, tenant, data_role),
            )
            cursor.execute(
                "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,display_name,"
                "invited,created_at) VALUES(%s,%s,%s,%s,'任务只读夹具',0,UTC_TIMESTAMP(3))",
                (tenant, owner, native, team),
            )
            if data_role == "TEAM_ADMIN":
                cursor.execute(
                    "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) "
                    "VALUES(%s,%s,%s)",
                    (tenant, native, team),
                )
            identities[native] = {"actor_id": native, "owner": owner, "username": name}
    admin.commit()
    for identity in identities.values():
        login = fixture_login(
            client, cache, {"username": identity.pop("username"), "password": password}
        )
        assert login.status_code == 200 and login.json().get("token")
        identity["headers"] = {"Authorization": "Bearer " + login.json()["token"]}
        assert client.get("/api/v1/launch-plans", headers=identity["headers"]).status_code == 403
    return tenant, root_owner, team, native_role, identities
