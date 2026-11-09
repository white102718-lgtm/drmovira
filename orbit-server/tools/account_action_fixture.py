"""028独占动作身份：真实角色API和原生映射，绝不附送read/import权限。"""

import re
from uuid import UUID, uuid4

from fixture_login import fixture_login


def prepare_account_action_fixture(client, admin, headers, password, cache, owner_team_id):
    """仅供主线本轮UUID库；固定技术ID占用即失败，不覆盖任何已有用户。"""
    if not isinstance(owner_team_id, str) or str(UUID(owner_team_id)) != owner_team_id:
        raise ValueError("动作身份团队必须为规范业务UUID")
    native = 990102
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        database = cursor.fetchone()[0]
        if (
            not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
            or admin.host != "127.0.0.1"
            or admin.port != 13306
        ):
            raise ValueError("动作专属身份只允许当前独立MySQL夹具")
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE user_id=1")
        tenant = cursor.fetchone()[0]
        cursor.execute(
            "SELECT 1 FROM orbit_business_team WHERE tenant_id=%s AND id=%s AND enabled=1",
            (tenant, owner_team_id),
        )
        assert cursor.fetchone() is not None, "动作身份必须使用本轮真实启用团队"
        cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,))
        assert cursor.fetchone()[0] == 0, "动作夹具技术ID已占用，拒绝覆盖"
    caps = client.get("/api/v1/roles/capabilities", headers=headers)
    assert caps.status_code == 200
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": caps.json()["csrf_token"],
            "Idempotency-Key": "account-actions-role-" + uuid4().hex,
        },
        json={
            "name": "账户动作独占-" + uuid4().hex[:12],
            "menu_codes": ["accounts"],
            "permission_codes": ["accounts.assign", "accounts.sync", "accounts.unbind"],
        },
    )
    assert role.status_code == 201
    owner, name = str(uuid4()), "account_actions_" + uuid4().hex[:12]
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role.json()["id"]),
        )
        native_role = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "SELECT %s,%s,%s,%s,password,'0','0' FROM sys_user WHERE user_id=1",
            (native, name, "账户动作夹具", name + "@fixture.example.org"),
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
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'TEAM_ADMIN')",
            (native, tenant),
        )
        cursor.execute(
            "INSERT INTO orbit_business_user"
            "(tenant_id,id,user_id,team_id,display_name,invited,created_at) "
            "VALUES(%s,%s,%s,%s,'账户动作夹具',0,UTC_TIMESTAMP(3))",
            (tenant, owner, native, owner_team_id),
        )
        cursor.execute(
            "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) "
            "VALUES(%s,%s,%s)",
            (tenant, native, owner_team_id),
        )
    login = fixture_login(client, cache, {"username": name, "password": password})
    assert login.status_code == 200 and login.json().get("token")
    identity = {"Authorization": "Bearer " + login.json()["token"]}
    assert client.get("/api/v1/accounts/extended", headers=identity).status_code == 403
    assert client.get("/api/v1/account-imports/capabilities", headers=identity).status_code == 403
    return {
        "headers": identity,
        "actor_id": native,
        "owner_user_id": owner,
        "owner_team_id": owner_team_id,
    }
