"""原若依真实接口验证字段容量；不创建ORBIT身份或冒充邀请验证。"""

import secrets
import uuid

IDENTITY_CAPACITY_CASES = [
    "pythonNativeUserUnicodeAndInternationalContactCapacity",
    "pythonNativeRoleUnicodeCapacityAndOverflowRejection",
]


def run_identity_capacity_checks(client, admin, headers, cases):
    suffix = uuid.uuid4().hex[:12]
    name = "capacity_" + suffix
    # RFC语法合法的254字符邮箱，最长标签不超过63字符；不进行外部邮件投递。
    email = "a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 61
    phone = "+86 " + "1" * 28
    assert len(email) == 254 and len(phone) == 32
    value = {
        "userName": name,
        "nickName": "😀" * 50,
        "email": email,
        "phonenumber": phone,
        "password": secrets.token_urlsafe(9) + "Aa1!",
        "status": "1",
        "sex": "2",
        "deptId": 100,
        "roleIds": [2],
        "postIds": [],
    }
    created = client.post("/system/user", headers=headers, json=value)
    assert created.status_code == 200 and created.json().get("code") == 200
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT user_id,nick_name,email,phonenumber FROM sys_user WHERE user_name=%s", (name,)
        )
        row = cursor.fetchone()
        assert row and row[1:] == (value["nickName"], email, phone)
        cursor.execute("SELECT COUNT(*) FROM orbit_user_scope WHERE user_id=%s", (row[0],))
        assert cursor.fetchone()[0] == 0
    for field, invalid in (
        ("nickName", "😀" * 51),
        ("phonenumber", phone + "1"),
        ("email", email + "a"),
    ):
        bad = client.post(
            "/system/user", headers=headers, json=value | {"userName": name + "x", field: invalid}
        )
        assert bad.status_code != 200 or bad.json().get("code") != 200
    cases.append(IDENTITY_CAPACITY_CASES[0])
    role_key = "capacity_role_" + suffix
    role = {
        "roleName": "😀" * 50,
        "roleKey": role_key,
        "roleSort": 30,
        "status": "0",
        "dataScope": "5",
        "menuIds": [],
        "deptIds": [],
        "menuCheckStrictly": True,
        "deptCheckStrictly": True,
    }
    created = client.post("/system/role", headers=headers, json=role)
    assert created.status_code == 200 and created.json().get("code") == 200
    with admin.cursor() as cursor:
        cursor.execute("SELECT role_name FROM sys_role WHERE role_key=%s", (role_key,))
        assert cursor.fetchone()[0] == role["roleName"]
    bad = client.post(
        "/system/role",
        headers=headers,
        json=role | {"roleKey": role_key + "x", "roleName": "😀" * 51},
    )
    assert bad.status_code != 200 or bad.json().get("code") != 200
    cases.append(IDENTITY_CAPACITY_CASES[1])
