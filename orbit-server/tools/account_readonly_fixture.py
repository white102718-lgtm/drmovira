"""025专属只读账户身份夹具；仅主线UUID数据库，不写真实平台。"""

import re
from uuid import uuid4

from fixture_login import fixture_login


def prepare_account_readonly_fixture(client, admin, headers, password, cache):
    """角色走真实API；只读身份没有import动作，Token仅返回内存。"""
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        database = cursor.fetchone()[0]
        if (
            not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
            or admin.host != "127.0.0.1"
            or admin.port != 13306
        ):
            raise ValueError("范围只读夹具只允许主线当前隔离MySQL")
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, _root_owner, root_team = cursor.fetchone()
    role_caps = client.get("/api/v1/roles/capabilities", headers=headers)
    assert role_caps.status_code == 200
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": role_caps.json()["csrf_token"],
            "Idempotency-Key": "scope-read-role-" + uuid4().hex,
        },
        json={
            "name": "范围只读专项-" + uuid4().hex[:12],
            "menu_codes": ["accounts"],
            "permission_codes": ["accounts.read"],
        },
    )
    assert role.status_code == 201
    native, owner = 990101, str(uuid4())
    name = "scope_read_only_" + uuid4().hex[:12]
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,))
        assert cursor.fetchone()[0] == 0, "夹具技术ID已占用，拒绝覆盖"
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role.json()["id"]),
        )
        native_role = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "SELECT %s,%s,%s,%s,password,'0','0' FROM sys_user WHERE user_id=1",
            (native, name, "范围只读夹具", name + "@fixture.example.org"),
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
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
            (native, tenant),
        )
        cursor.execute(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,"
            "display_name,invited,created_at) "
            "VALUES(%s,%s,%s,%s,%s,0,UTC_TIMESTAMP(3))",
            (tenant, owner, native, root_team, "范围只读夹具"),
        )
    login = fixture_login(client, cache, {"username": name, "password": password})
    assert login.status_code == 200 and login.json().get("token")
    identity = {"Authorization": "Bearer " + login.json()["token"]}
    assert client.get("/api/v1/accounts/extended", headers=identity).status_code == 200
    assert client.get("/api/v1/account-imports/capabilities", headers=identity).status_code == 403
    return {
        "headers": identity,
        "actor_id": native,
        "owner_user_id": owner,
        "owner_team_id": root_team,
    }
