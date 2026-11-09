"""readonly时间预览实际工具；root串队，仅UUID13306，不自行运行服务。"""

import calendar
import re
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

RULE_SCHEDULE_PREVIEW_CASES = [
    "pythonRuleSchedulePreviewCreateFirstTenantNoClockAndSqlUtcReference",
    "pythonRuleSchedulePreviewCurrentEditCasAndIndependentOriginalActions",
    "pythonRuleSchedulePreviewFutureDstGapFoldAndExpiredEmpty",
    "pythonRuleSchedulePreviewCurrentSessionCsrfAndDuplicateHeaderRejected",
    "pythonRuleSchedulePreviewStrictFourBodyKeysAndNoDualCasHeaders",
    "pythonRuleSchedulePreviewImmediateRevocationForeignAndAllRuleRowsUnchanged",
    "pythonRuleSchedulePreviewAllOriginalRowsAndClockRemainUnchanged",
]


def guard_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or type(admin.port) is not int
        or admin.port != 13306
        or type(database) is not str
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("RULE_SCHEDULE_PREVIEW_ISOLATED_UUID_REQUIRED")


def run_rule_schedule_preview_checks(client, admin, headers, password, cache, database, cases):
    guard_target(admin, database)
    if __package__:
        from .fixture_login import fixture_login
        from .metric_profile_reference_checks import seed_metric_reference_profile
        from .rule_definition_checks import TABLES, definition_body
        from .rule_editor_checks import checked
    else:
        from fixture_login import fixture_login
        from metric_profile_reference_checks import seed_metric_reference_profile
        from rule_definition_checks import TABLES, definition_body
        from rule_editor_checks import checked
    from orbit_api.directory_tokens import canonical

    def sql(statement, values=(), *, all=False):
        try:
            with admin.cursor() as cursor:
                cursor.execute(statement, values)
                result = cursor.fetchall() if all else cursor.rowcount
            admin.commit()
            return result
        except BaseException:
            admin.rollback()
            raise

    assert sql("SELECT DATABASE()", all=True)[0][0] == database
    tenant, root_owner, team = sql(
        "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1", all=True
    )[0]
    fresh_tenant, fresh_team = str(uuid4()), str(uuid4())
    sql("INSERT INTO orbit_tenant(id,name) VALUES(%s,'预览首次使用技术租户')", (fresh_tenant,))
    sql(
        "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,'预览技术团队')",
        (fresh_tenant, fresh_team),
    )
    people = []
    # 本轮原生角色严格只授指定原动作；不冒充生产租户开通/菜单发行入口。
    for native, selected_tenant, selected_team, menus in (
        (990616, fresh_tenant, fresh_team, (31000, 31040, 31042)),
        (990617, tenant, team, (31000, 31040, 31042, 31043)),
    ):
        assert sql("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,), all=True)[0][0] == 0
        assert sql("SELECT COUNT(*) FROM sys_role WHERE role_id=%s", (native,), all=True)[0][0] == 0
        username, owner = "rule_time_" + uuid4().hex[:10], str(uuid4())
        sql(
            "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "SELECT %s,%s,'时间预览',%s,password,'0','0' FROM sys_user WHERE user_id=1",
            (native, username, username + "@fixture.example.org"),
        )
        sql(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
            (native, str(uuid4())),
        )
        sql(
            "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,data_scope,status,del_flag) "
            "VALUES(%s,'时间预览',%s,1,'1','0','0')",
            (native, "preview_" + uuid4().hex),
        )
        for menu in menus:
            sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)", (native, menu))
        sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, native))
        sql(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
            (native, selected_tenant),
        )
        sql(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,display_name,invited,"
            "created_at) VALUES(%s,%s,%s,%s,'时间预览',0,UTC_TIMESTAMP(3))",
            (selected_tenant, owner, native, selected_team),
        )
        login = checked(fixture_login(client, cache, {"username": username, "password": password}))
        people.append(
            {
                "headers": {"Authorization": "Bearer " + login["token"]},
                "owner": owner,
                "native": native,
            }
        )
    first, editor = people
    path = "/api/v1/rules/editor-schedule-preview"

    def snapshot():
        return tuple(sql("SELECT * FROM " + table + " ORDER BY 1,2", all=True) for table in TABLES)

    def cap(identity, action):
        return checked(
            client.get("/api/v1/rules/capabilities", headers=identity, params={"action": action})
        )["csrf_token"]

    now = sql("SELECT UTC_TIMESTAMP(6)", all=True)[0][0]

    def schedule(**changes):
        return {
            "frequency": "INTERVAL",
            "interval_minutes": 15,
            "time_of_day": None,
            "weekday": None,
            "timezone": "UTC",
            "start_date": now.date().isoformat(),
            "end_date": (now.date() + timedelta(days=10)).isoformat(),
        } | changes

    def body(selected=None, *, rule=None):
        return {
            "action": "UPDATE" if rule else "CREATE",
            "rule_id": rule["id"] if rule else None,
            "rule_revision": rule["revision"] if rule else None,
            "schedule": selected or schedule(),
        }

    def preview(value, *, identity=None, status=200, extra=None, token=None):
        identity = identity or editor["headers"]
        csrf = token if token is not None else cap(identity, value["action"])
        before = sql("SELECT UTC_TIMESTAMP(6)", all=True)[0][0]
        response = client.post(
            path, headers=identity | {"X-CSRF-Token": csrf} | (extra or {}), json=value
        )
        result = checked(response, status)
        after = sql("SELECT UTC_TIMESTAMP(6)", all=True)[0][0]
        if status == 200:
            assert set(result) == {"reference_at", "timezone", "slots", "skipped_local_times"}
            reference = datetime.fromisoformat(result["reference_at"].replace("Z", "+00:00"))
            assert before.replace(tzinfo=UTC) <= reference <= after.replace(tzinfo=UTC)
            assert len(result["slots"]) <= 5 and result["timezone"] == value["schedule"]["timezone"]
            for slot in result["slots"]:
                assert set(slot) == {"local_time", "utc_time"}
                local = datetime.fromisoformat(slot["local_time"])
                utc = datetime.fromisoformat(slot["utc_time"].replace("Z", "+00:00"))
                assert local.tzinfo is not None and local.astimezone(UTC) == utc and utc > reference
            assert all(
                set(item) == {"local_time", "reason_code"}
                and item["reason_code"] == "DST_NONEXISTENT_LOCAL_TIME"
                for item in result["skipped_local_times"]
            )
        return result

    baseline = snapshot()
    assert (
        sql("SELECT COUNT(*) FROM orbit_rule_clock WHERE tenant_id=%s", (fresh_tenant,), all=True)[
            0
        ][0]
        == 0
    )
    first_result = preview(body(), identity=first["headers"])
    assert len(first_result["slots"]) == 5
    utc_slots = [
        datetime.fromisoformat(item["utc_time"].replace("Z", "+00:00"))
        for item in first_result["slots"]
    ]
    assert all(
        right - left == timedelta(minutes=15)
        for left, right in zip(utc_slots, utc_slots[1:], strict=False)
    )
    assert (
        sql("SELECT COUNT(*) FROM orbit_rule_clock WHERE tenant_id=%s", (fresh_tenant,), all=True)[
            0
        ][0]
        == 0
    )
    assert snapshot() == baseline
    cases.append(RULE_SCHEDULE_PREVIEW_CASES[0])

    account = str(uuid4())
    sql(
        "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
        "owner_team_id,currency,timezone_id,auth_status,account_status,value_json,details_json,"
        "bound_at,created_at) VALUES(%s,%s,%s,'时间预览账户','时间预览账户',%s,%s,'USD',"
        "'UTC','UNKNOWN','UNKNOWN','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
        (tenant, account, str(10**25 + uuid4().int % 10**25), editor["owner"], team),
    )
    sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    sc = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers))
    frozen = checked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=headers | {"X-CSRF-Token": sc["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={"mode": "IDS", "account_ids": [account], "filter": None},
        ),
        201,
    )
    profile, _ = seed_metric_reference_profile(admin, database, tenant, index=750)
    rule = checked(
        client.post(
            "/api/v1/rules",
            headers=headers
            | {"X-CSRF-Token": cap(headers, "CREATE"), "Idempotency-Key": str(uuid4())},
            json=definition_body(
                "预览只读-" + uuid4().hex[:12], editor["owner"], team, frozen["id"], profile["id"]
            ),
        ),
        201,
    )
    update = body(rule=rule)
    create_csrf, update_csrf = cap(editor["headers"], "CREATE"), cap(editor["headers"], "UPDATE")
    baseline = snapshot()
    preview(update)
    sql(
        "UPDATE orbit_metric_profile_head SET state='DISABLED' WHERE tenant_id=%s AND id=%s",
        (tenant, profile["id"]),
    )
    try:
        preview(update)
    finally:
        sql(
            "UPDATE orbit_metric_profile_head SET state='ENABLED' WHERE tenant_id=%s AND id=%s",
            (tenant, profile["id"]),
        )
    preview(update | {"rule_revision": rule["revision"] + 1}, status=409)
    checked(client.get("/api/v1/rules/" + rule["id"], headers=editor["headers"]), 403)
    sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31042", (editor["native"],))
    try:
        preview(update, token=update_csrf)
        preview(body(), status=403, token=create_csrf)
    finally:
        sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,31042)", (editor["native"],))
    assert snapshot() == baseline
    cases.append(RULE_SCHEDULE_PREVIEW_CASES[1])

    year = now.year + 1
    spring_day = date(year, 3, 1) + timedelta(
        days=(calendar.SUNDAY - date(year, 3, 1).weekday()) % 7 + 7
    )
    spring = schedule(
        frequency="DAILY",
        interval_minutes=None,
        time_of_day="02:30",
        timezone="America/New_York",
        start_date=(spring_day - timedelta(days=1)).isoformat(),
        end_date=(spring_day + timedelta(days=1)).isoformat(),
    )
    gap = preview(body(spring))
    assert len(gap["slots"]) == 2 and gap["skipped_local_times"] == [
        {
            "local_time": spring_day.isoformat() + "T02:30:00",
            "reason_code": "DST_NONEXISTENT_LOCAL_TIME",
        }
    ]
    fall_day = date(year, 11, 1) + timedelta(
        days=(calendar.SUNDAY - date(year, 11, 1).weekday()) % 7
    )
    fall = schedule(
        frequency="DAILY",
        interval_minutes=None,
        time_of_day="01:30",
        timezone="America/New_York",
        start_date=fall_day.isoformat(),
        end_date=(fall_day + timedelta(days=1)).isoformat(),
    )
    fold = preview(body(fall))
    assert (
        len(fold["slots"]) == 2
        and fold["slots"][0]["utc_time"] == fall_day.isoformat() + "T05:30:00.000000Z"
    )
    expired = preview(
        body(
            schedule(
                start_date=(now.date() - timedelta(days=2)).isoformat(),
                end_date=(now.date() - timedelta(days=1)).isoformat(),
            )
        )
    )
    assert expired["slots"] == expired["skipped_local_times"] == []
    assert snapshot() == baseline
    cases.append(RULE_SCHEDULE_PREVIEW_CASES[2])

    preview(body(), status=403, token="invalid-current-session-token")
    preview(body(), status=403, token=cap(headers, "CREATE"))
    checked(client.post(path, headers=editor["headers"], json=body()), 403)
    checked(
        client.post(
            path,
            headers=list(editor["headers"].items())
            + [("X-CSRF-Token", create_csrf), ("X-CSRF-Token", create_csrf)],
            json=body(),
        ),
        403,
    )
    assert snapshot() == baseline
    cases.append(RULE_SCHEDULE_PREVIEW_CASES[3])

    valid_headers = editor["headers"] | {"X-CSRF-Token": create_csrf}
    for extra in ({"If-Match": '"1"'}, {"Idempotency-Key": str(uuid4())}):
        preview(body(), status=400, extra=extra)
    for bad, status in (
        (body() | {"extra": 1}, 400),
        (body() | {"rule_revision": 1}, 422),
        (update | {"rule_revision": True}, 422),
    ):
        checked(client.post(path, headers=valid_headers, json=bad), status)
    raw = canonical(body()).encode()
    duplicate = raw[:-1] + b',"action":"UPDATE"}'
    checked(
        client.post(
            path, headers=valid_headers | {"Content-Type": "application/json"}, content=duplicate
        ),
        400,
    )
    checked(client.post(path + "?q=untrusted", headers=valid_headers, json=body()), 400)
    checked(
        client.post(path, headers=valid_headers | {"X-Target-Tenant": str(uuid4())}, json=body()),
        403,
    )
    checked(client.post(path, headers=valid_headers, content=b" " * (16384 + 1)), 413)
    assert snapshot() == baseline
    cases.append(RULE_SCHEDULE_PREVIEW_CASES[4])

    sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31043", (editor["native"],))
    try:
        preview(update, status=403, token=update_csrf)
        preview(body(), token=create_csrf)
    finally:
        sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,31043)", (editor["native"],))
    # 真正另一tenant已存Rule，当前create-only用户加真实edit leaf仍不能读取该对象。
    sql("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,31043)", (first["native"],))
    try:
        preview(update, identity=first["headers"], status=404)
    finally:
        sql("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31043", (first["native"],))
    preview(update)
    assert snapshot() == baseline
    cases.append(RULE_SCHEDULE_PREVIEW_CASES[5])
    preview(body())
    preview(update)
    assert snapshot() == baseline
    assert (
        sql("SELECT COUNT(*) FROM orbit_rule_clock WHERE tenant_id=%s", (fresh_tenant,), all=True)[
            0
        ][0]
        == 0
    )
    cases.append(RULE_SCHEDULE_PREVIEW_CASES[6])
    return {
        "schedule_preview_cases": len(RULE_SCHEDULE_PREVIEW_CASES),
        "preview_rule_writes": 0,
        "scheduler_started": False,
        "enabled_verified": False,
        "server_cancel_verified": False,
    }
