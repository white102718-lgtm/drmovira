"""团队启停的原JWT/登录与身份版本专项；通过真实团队API，不用SQL模拟停用。"""

import uuid

from fixture_login import fixture_login

TEAM_SESSION_CASES = [
    "pythonTeamDisableRejectsOriginalJwtAndFreshNativeLogin",
    "pythonTeamReenableDoesNotResurrectOldJwtAndAllowsFreshLogin",
    "pythonTeamMemberEpochIsolationAndNameChangesKeepSessions",
    "pythonTeamAuditOutboxFailureRollsBackMemberRevocationAndCanRetry",
]


def run_team_session_checks(client, admin, headers, fixture, password, cache, cases):
    person = fixture["users"][0]
    team_id = person["team"]
    path = "/api/v1/teams/" + team_id
    caps = client.get("/api/v1/teams/capabilities", headers=headers).json()
    old_headers = fixture["manager_headers"]
    # 同一原身份保留其他租户历史成员记录，不应阻断当前有效上下文，也不能被别租户停用波及。
    with admin.cursor() as cursor:
        cursor.execute("SELECT MAX(user_id)+1 FROM sys_user")
        foreign_user = cursor.fetchone()[0]
        cursor.execute("SELECT tenant_id FROM orbit_user_scope WHERE user_id=980100")
        foreign_tenant = cursor.fetchone()[0]
        cursor.execute(
            "SELECT team_id FROM orbit_business_user WHERE user_id=980100 AND tenant_id=%s",
            (foreign_tenant,),
        )
        foreign_team = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "SELECT %s,'team_foreign_shared','跨租户历史成员夹具',"
            "'foreign-shared@fixture.example.org',password,'0','0' FROM sys_user WHERE user_id=1",
            (foreign_user,),
        )
        cursor.execute(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
            (foreign_user, str(uuid.uuid4())),
        )
        cursor.execute(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,980100)", (foreign_user,)
        )
        cursor.execute(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
            (foreign_user, foreign_tenant),
        )
        cursor.executemany(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id) VALUES(%s,%s,%s,%s)",
            [
                (foreign_tenant, str(uuid.uuid4()), foreign_user, foreign_team),
                ("00000000-0000-0000-0000-000000000001", str(uuid.uuid4()), foreign_user, team_id),
            ],
        )
    foreign_login = fixture_login(
        client, cache, {"username": "team_foreign_shared", "password": password}
    )
    assert foreign_login.status_code == 200 and foreign_login.json().get("token")
    foreign_headers = {"Authorization": "Bearer " + foreign_login.json()["token"]}

    def usable(actor):
        response = client.get("/getInfo", headers=actor)
        assert response.status_code == 200 and response.json().get("code") == 200

    def denied(actor):
        response = client.get("/getInfo", headers=actor)
        assert response.status_code == 401 or response.json().get("code") == 401

    def epochs():
        with admin.cursor() as cursor:
            cursor.execute("SELECT user_id,auth_version FROM sys_identity_subject ORDER BY user_id")
            return dict(cursor.fetchall())

    def write(current, status, key=None, name=None):
        return client.put(
            path,
            headers=headers
            | {
                "X-CSRF-Token": caps["csrf_token"],
                "Idempotency-Key": key or "team-session-" + uuid.uuid4().hex,
                "If-Match": f'"{current["revision"]}"',
            },
            json={"name": name or current["name"], "status": status},
        )

    def login():
        return fixture_login(client, cache, {"username": person["name"], "password": password})

    current = client.get(path, headers=headers).json()
    usable(old_headers)
    before_epochs = epochs()
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT b.user_id FROM orbit_business_user b JOIN orbit_user_scope s "
            "ON s.user_id=b.user_id AND s.tenant_id=b.tenant_id "
            "WHERE b.tenant_id=%s AND b.team_id=%s",
            ("00000000-0000-0000-0000-000000000001", team_id),
        )
        members = {row[0] for row in cursor.fetchall()}
    original_team = dict(current)
    disable_key = "team-disable-once-" + uuid.uuid4().hex
    changed = write(current, "DISABLED", disable_key)
    assert changed.status_code == 200
    current = changed.json()
    denied(old_headers)
    blocked = login()
    assert blocked.status_code == 401 or blocked.json().get("code") == 401
    assert not blocked.json().get("token")
    cases.append(TEAM_SESSION_CASES[0])
    disabled_epochs = epochs()
    usable(foreign_headers)
    expected = {
        identifier: version + int(identifier in members)
        for identifier, version in before_epochs.items()
    }
    assert disabled_epochs == expected
    replay = write(original_team, "DISABLED", disable_key)
    assert replay.status_code == 200 and replay.json() == current
    assert epochs() == disabled_epochs
    for label in ("停用团队改名后恢复", original_team["name"]):
        renamed_disabled = write(current, "DISABLED", name=label)
        assert renamed_disabled.status_code == 200
        current = renamed_disabled.json()
        assert epochs() == disabled_epochs
    changed = write(current, "ENABLED")
    assert changed.status_code == 200
    current = changed.json()
    denied(old_headers)
    fresh = login()
    assert fresh.status_code == 200 and fresh.json().get("token")
    member_headers = {"Authorization": "Bearer " + fresh.json()["token"]}
    usable(member_headers)
    assert epochs() == disabled_epochs
    usable(foreign_headers)
    cases.append(TEAM_SESSION_CASES[1])
    original_name = current["name"]
    renamed = write(current, "ENABLED", name="会话专项改名后恢复")
    assert renamed.status_code == 200
    current = renamed.json()
    usable(member_headers)
    assert epochs() == disabled_epochs
    renamed = write(current, "ENABLED", name=original_name)
    assert renamed.status_code == 200
    current = renamed.json()
    assert epochs() == disabled_epochs
    cases.append(TEAM_SESSION_CASES[2])
    for table in ("orbit_directory_audit", "orbit_directory_outbox"):
        baseline_epochs = epochs()
        retry = "team-session-retry-" + uuid.uuid4().hex
        with admin.cursor() as cursor:
            cursor.execute(
                "CREATE TRIGGER team_session_fail BEFORE INSERT ON "
                + table
                + " FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-session-failure'"
            )
        try:
            failed = write(current, "DISABLED", retry)
            assert failed.status_code == 503 and "fixture-session-failure" not in failed.text
            assert client.get(path, headers=headers).json() == current
            assert epochs() == baseline_epochs
            usable(member_headers)
            usable(foreign_headers)
        finally:
            with admin.cursor() as cursor:
                cursor.execute("DROP TRIGGER team_session_fail")
        retried = write(current, "DISABLED", retry)
        assert retried.status_code == 200
        current = retried.json()
        denied(member_headers)
        restored = write(current, "ENABLED")
        assert restored.status_code == 200
        current = restored.json()
        denied(member_headers)
        fresh = login()
        assert fresh.status_code == 200 and fresh.json().get("token")
        member_headers = {"Authorization": "Bearer " + fresh.json()["token"]}
        usable(member_headers)
        usable(foreign_headers)
    fixture["manager_headers"] = member_headers
    cases.append(TEAM_SESSION_CASES[3])
