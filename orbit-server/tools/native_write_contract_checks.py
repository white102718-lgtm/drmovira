"""原资料写入不能破坏业务人员字段合同；在独立数据库验证实际回滚。"""

NATIVE_WRITE_CONTRACT_CASES = [
    "pythonNativeProfileAndFullEditCannotClearBusinessEmailOrPersistControls",
    "pythonNativeContactNormalizationMatchesBusinessDtoAndNoop",
    "pythonNativeUserExportHandlesNoDepartmentAndHasNoCredentialColumns",
]


def run_native_write_contract_checks(client, admin, headers, fixture, cases):
    target = fixture["users"][1]
    own = fixture["actor_headers"]
    native_url = "/system/user/" + str(target["native"])
    public_url = "/api/v1/users/" + target["id"]
    detail = client.get(native_url, headers=headers).json()
    assert detail["businessManaged"] is True
    assert client.get("/system/user/", headers=headers).json()["businessManaged"] is False
    body = detail["data"] | {"roleIds": detail["roleIds"], "postIds": detail["postIds"]}
    body.pop("password", None)
    original = client.get(public_url, headers=headers).json()
    tenant = "00000000-0000-0000-0000-000000000001"

    def state():
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT u.nick_name,u.email,u.phonenumber,b.revision,i.auth_version "
                "FROM sys_user u JOIN orbit_business_user b ON b.user_id=u.user_id "
                "JOIN sys_identity_subject i ON i.user_id=u.user_id "
                "WHERE u.user_id=%s AND b.tenant_id=%s",
                (target["native"], tenant),
            )
            person = cursor.fetchone()
            cursor.execute(
                "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
            )
            clock = cursor.fetchone()[0]
            counters = []
            for table in ("orbit_directory_audit", "orbit_directory_outbox"):
                cursor.execute("SELECT COUNT(*) FROM " + table)
                counters.append(cursor.fetchone()[0])
            return person, clock, counters

    for field, invalid in (
        ("email", ""),
        ("email", None),
        ("nickName", "昵称\u202e伪装"),
        ("phonenumber", "12\u000034"),
    ):
        for url, caller, value in (
            ("/system/user/profile", own, {field: invalid}),
            ("/system/user", headers, body | {field: invalid}),
        ):
            before = state()
            response = client.put(url, headers=caller, json=value)
            assert response.status_code != 200 or response.json().get("code") != 200, (
                "原资料入口接受违反业务字段合同的值"
            )
            assert state() == before
            assert client.get(public_url, headers=headers).json() == original
    cases.append(NATIVE_WRITE_CONTRACT_CASES[0])
    for url, caller in (("/system/user/profile", own), ("/system/user", headers)):
        value = {
            "nickName": "e\u0301" * 50,
            "email": " User@EXAMPLE.ORG ",
            "phonenumber": " +44 020 0000 ",
        }
        before = state()
        response = client.put(
            url, headers=caller, json=(body | value) if url == "/system/user" else value
        )
        assert response.status_code == 200 and response.json().get("code") == 200
        normalized = client.get(public_url, headers=headers).json()
        assert normalized["nickname"] == "é" * 50 and normalized["email"] == "User@example.org"
        assert normalized["phone"] == "+44 020 0000" and normalized["revision"] == before[0][3] + 1
        stable = state()
        replay = client.put(
            url, headers=caller, json=(body | value) if url == "/system/user" else value
        )
        assert replay.status_code == 200 and replay.json().get("code") == 200
        assert state() == stable
        restored = client.put("/system/user", headers=headers, json=body)
        assert restored.status_code == 200 and restored.json().get("code") == 200
    cases.append(NATIVE_WRITE_CONTRACT_CASES[1])
    import io

    from openpyxl import load_workbook

    exported = client.post(
        "/system/user/export", headers=headers, data={"userName": target["name"]}
    )
    assert exported.status_code == 200 and exported.headers.get("content-type", "").startswith(
        "application/"
    )
    sheet = load_workbook(io.BytesIO(exported.content), read_only=True).active
    rows = list(sheet.values)
    assert rows and "用户名称" in rows[0] and "password" not in str(rows[0]).lower()
    assert any(target["name"] in row for row in rows[1:])
    assert not any("foreign_user_directory" in row for row in rows[1:])
    cases.append(NATIVE_WRITE_CONTRACT_CASES[2])
