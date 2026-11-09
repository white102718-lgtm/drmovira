"""原技术用户导入/删除保留，业务人员不得绕过独立目录状态与版本流程。"""

import io
import uuid

from openpyxl import Workbook

NATIVE_BULK_LIFECYCLE_CASES = [
    "pythonNativeDeleteBusinessAndMixedBatchPreservesDirectory",
    "pythonNativeExcelMixedBusinessUpdateRejectsBeforeAnyTechnicalInsert",
    "pythonNativeTechnicalExcelCreateUpdateAndDeleteRemainUsable",
    "pythonNativeOrphanedBusinessHistoryCannotBecomeTechnicalWriteTarget",
]


def user_import_workbook(rows):
    """生成原技术用户模板的真实Excel，不替代业务HTTP成功响应。"""
    book = Workbook()
    sheet = book.active
    sheet.append(
        ["部门编号", "登录名称", "用户名称", "用户邮箱", "手机号码", "用户性别", "帐号状态"]
    )
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def write_native_browser_import_fixtures(output, admin, fixture):
    with admin.cursor() as cursor:
        cursor.execute("SELECT dept_id FROM sys_user WHERE user_id=1")
        department = cursor.fetchone()[0]
    for project in ("desktop-1440", "wide-1920", "mobile-390"):
        for kind, name in (
            ("technical", "ui_import_" + project.replace("-", "_")),
            ("business", fixture["users"][22]["name"]),
        ):
            content = user_import_workbook(
                [
                    [
                        department,
                        name,
                        "浏览器导入专项",
                        name + "@fixture.example.org",
                        "+44 020 1000",
                        "未知",
                        "停用",
                    ]
                ]
            )
            (output / f"native-{kind}-import-{project}.xlsx").write_bytes(content)


def run_native_bulk_lifecycle_checks(client, admin, headers, fixture, cases):
    target = fixture["users"][22]
    tenant = "00000000-0000-0000-0000-000000000001"
    public_url = "/api/v1/users/" + target["id"]
    original = client.get(public_url, headers=headers).json()
    technical_name = "bulk_technical_" + uuid.uuid4().hex[:10]
    with admin.cursor() as cursor:
        cursor.execute("SELECT dept_id FROM sys_user WHERE user_id=1")
        department = cursor.fetchone()[0]

    def state():
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT u.del_flag,u.status,u.nick_name,u.email,u.phonenumber,u.dept_id,"
                "SHA2(COALESCE(u.password,''),256),"
                "b.revision,b.updated_at,i.auth_version FROM sys_user u "
                "JOIN orbit_business_user b ON b.user_id=u.user_id "
                "JOIN sys_identity_subject i ON i.user_id=u.user_id "
                "WHERE b.tenant_id=%s AND u.user_id=%s",
                (tenant, target["native"]),
            )
            person = cursor.fetchone()
            cursor.execute(
                "SELECT role_id FROM sys_user_role WHERE user_id=%s ORDER BY role_id",
                (target["native"],),
            )
            grants = cursor.fetchall()
            cursor.execute(
                "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
            )
            clock = cursor.fetchone()[0]
            counts = []
            for table in ("orbit_directory_audit", "orbit_directory_outbox"):
                cursor.execute("SELECT COUNT(*) FROM " + table)
                counts.append(cursor.fetchone()[0])
            return person, grants, clock, counts

    def row(name, nickname):
        return [
            department,
            name,
            nickname,
            name + "@fixture.example.org",
            "+44 020 1000",
            "未知",
            "停用",
        ]

    def upload(rows, update_support=True):
        return client.post(
            "/system/user/importData",
            headers=headers,
            params={"updateSupport": str(update_support).lower()},
            files={
                "file": (
                    "users.xlsx",
                    user_import_workbook(rows),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    def denied(response):
        assert response.status_code < 500
        assert response.status_code != 200 or response.json().get("code") != 200

    # 先建一个无业务映射的真实技术用户，用它证明混批在第一笔写入前检查全部目标。
    created = upload([row(technical_name, "技术导入")])
    assert created.status_code == 200 and created.json().get("code") == 200
    with admin.cursor() as cursor:
        cursor.execute("SELECT user_id FROM sys_user WHERE user_name=%s", (technical_name,))
        technical_id = cursor.fetchone()[0]
    for identifiers in (str(target["native"]), f"{technical_id},{target['native']}"):
        before = state()
        denied(client.delete("/system/user/" + identifiers, headers=headers))
        assert state() == before
        assert client.get(public_url, headers=headers).json() == original
        with admin.cursor() as cursor:
            cursor.execute("SELECT del_flag FROM sys_user WHERE user_id=%s", (technical_id,))
            assert cursor.fetchone()[0] == "0"
    cases.append(NATIVE_BULK_LIFECYCLE_CASES[0])
    pending_name = "bulk_pending_" + uuid.uuid4().hex[:10]
    before = state()
    denied(upload([row(pending_name, "不应部分新增"), row(target["name"], "不应覆盖业务人员")]))
    assert state() == before
    assert client.get(public_url, headers=headers).json() == original
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM sys_user WHERE user_name=%s", (pending_name,))
        assert cursor.fetchone()[0] == 0
    cases.append(NATIVE_BULK_LIFECYCLE_CASES[1])
    updated = upload([row(technical_name, "技术更新")])
    assert updated.status_code == 200 and updated.json().get("code") == 200
    with admin.cursor() as cursor:
        cursor.execute("SELECT nick_name FROM sys_user WHERE user_id=%s", (technical_id,))
        assert cursor.fetchone()[0] == "技术更新"
    deleted = client.delete("/system/user/" + str(technical_id), headers=headers)
    assert deleted.status_code == 200 and deleted.json().get("code") == 200
    with admin.cursor() as cursor:
        cursor.execute("SELECT del_flag FROM sys_user WHERE user_id=%s", (technical_id,))
        assert cursor.fetchone()[0] == "2"
    assert state() == before
    skipped = upload(
        [row(pending_name, "跳过已有业务人员仍可新增技术用户"), row(target["name"], "不得覆盖")],
        update_support=False,
    )
    assert skipped.status_code == 200 and skipped.json().get("code") == 200
    assert "已存在" in skipped.json()["msg"]
    assert state() == before
    with admin.cursor() as cursor:
        cursor.execute("SELECT user_id FROM sys_user WHERE user_name=%s", (pending_name,))
        pending_id = cursor.fetchone()[0]
    removed = client.delete("/system/user/" + str(pending_id), headers=headers)
    assert removed.status_code == 200 and removed.json().get("code") == 200
    cases.append(NATIVE_BULK_LIFECYCLE_CASES[2])
    # 人工历史数据可能保留业务行但缺当前scope；不能因此退回原技术用户写权限。
    detail = client.get("/system/user/" + str(target["native"]), headers=headers).json()
    full = detail["data"] | {"roleIds": detail["roleIds"], "postIds": detail["postIds"]}
    full.pop("password", None)
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT tenant_id,data_role,enabled,revision FROM orbit_user_scope WHERE user_id=%s",
            (target["native"],),
        )
        membership = cursor.fetchone()
        cursor.execute("DELETE FROM orbit_user_scope WHERE user_id=%s", (target["native"],))
    try:
        before = state()
        assert client.get(public_url, headers=headers).status_code == 404
        assert (
            client.get("/system/user/" + str(target["native"]), headers=headers).status_code == 404
        )
        operations = [
            ("/system/user", full | {"nickName": "不应变成技术用户"}),
            ("/system/user/changeStatus", {"userId": target["native"], "status": "1"}),
            ("/system/user/resetPwd", {"userId": target["native"], "password": "FixtureOrphan1!"}),
        ]
        for url, value in operations:
            denied(client.put(url, headers=headers, json=value))
            assert state() == before
        denied(
            client.put(
                "/system/user/authRole",
                headers=headers,
                params={
                    "userId": target["native"],
                    "roleIds": ",".join(map(str, detail["roleIds"])),
                },
            )
        )
        assert state() == before
        denied(client.delete("/system/user/" + str(target["native"]), headers=headers))
        denied(upload([row(target["name"], "历史人员不能走技术导入")]))
        assert state() == before
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role,enabled,revision) "
                "VALUES(%s,%s,%s,%s,%s)",
                (target["native"], *membership),
            )
    assert client.get(public_url, headers=headers).json() == original
    cases.append(NATIVE_BULK_LIFECYCLE_CASES[3])
