"""仅当前临时库创建三视口邀请，凭据只经子进程内存环境传递，不写文件或日志。"""

import json
import re
from uuid import uuid4


def prepare_authentication_browser(client, admin, headers, fixture, cipher, idp, database):
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database):
        raise ValueError("浏览器认证只能使用当前隔离测试库")
    caps = client.get("/api/v1/users/capabilities", headers=headers)
    assert caps.status_code == 200
    values = {}
    for project in ["desktop-1440", "wide-1920", "mobile-390"]:
        email = "browser-oidc-" + uuid4().hex + "@example.org"
        response = client.post(
            "/api/v1/users",
            headers=headers
            | {
                "X-CSRF-Token": caps.json()["csrf_token"],
                "Idempotency-Key": "browser-user-" + uuid4().hex,
            },
            json={
                "display_name": "浏览器OIDC-" + project,
                "nickname": "浏览器OIDC-" + project,
                "email": email,
                "phone": "",
                "team_id": fixture["users"][0]["team"],
                "role_ids": [fixture["role_id"]],
                "data_role": "USER",
                "managed_team_ids": [],
                "status": "INVITED",
            },
        )
        assert response.status_code == 201
        user = response.json()
        sent = client.post(
            "/api/v1/users/" + user["id"] + "/invitation",
            headers=headers
            | {
                "X-CSRF-Token": caps.json()["csrf_token"],
                "Idempotency-Key": "browser-invite-" + uuid4().hex,
                "If-Match": '"' + str(user["revision"]) + '"',
            },
        )
        assert sent.status_code == 200
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT d.id,d.protected_json FROM orbit_invitation_delivery d "
                "JOIN orbit_user_invitation i ON i.id=d.invitation_id "
                "JOIN orbit_business_user b ON b.user_id=i.user_id AND b.tenant_id=i.tenant_id "
                "WHERE b.id=%s AND i.status='ACTIVE'",
                (user["id"],),
            )
            delivery, encrypted = cursor.fetchone()
        payload = json.loads(
            cipher.decrypt_internal(
                json.loads(encrypted)["envelope"],
                "00000000-0000-0000-0000-000000000001",
                delivery,
                "invitation_delivery",
            )
        )
        idp.browser_accounts[project] = {"subject": "Browser-OIDC-" + uuid4().hex, "email": email}
        values[project] = {"invitation": payload["invitation_token"], "user_id": user["id"]}
    return values
