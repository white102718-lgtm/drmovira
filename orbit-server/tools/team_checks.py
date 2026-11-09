"""真实团队HTTP专项；数据只写调用方已核验的专属MySQL临时库。"""

import uuid
from concurrent.futures import ThreadPoolExecutor

TEAM_CASES = [
    "pythonTeamCreateCsrfAndIdempotentReplay",
    "pythonTeamUpdateCasAndAtomicAudit",
    "pythonTeamKeysetFiltersAndStaleCursor",
    "pythonTeamLastAdministratorRollback",
    "pythonTeamAuditAndOutboxFailureRollback",
    "pythonTeamExplicitManagerScopeAndRevocation",
    "pythonTeamConcurrentOwnTeamCasHasOneCommit",
    "pythonTeamCsrfBoundToOriginalSession",
]


def run_team_checks(client, admin, headers, password, cases):
    base = "/api/v1/teams"
    tenant = "00000000-0000-0000-0000-000000000001"
    caps = client.get(base + "/capabilities", headers=headers)
    assert caps.status_code == 200 and caps.json()["can_create"] is True
    csrf = caps.json()["csrf_token"]
    assert 16 <= len(csrf) <= 255
    key = "team-create-" + uuid.uuid4().hex
    writes = headers | {"X-CSRF-Token": csrf, "Idempotency-Key": key}
    value = {"name": "😀" * 100, "status": "ENABLED"}
    denied = client.post(base, headers=headers | {"Idempotency-Key": key}, json=value)
    assert denied.status_code == 403
    assert set(denied.json()) == {"code", "message", "request_id", "retryable", "field_errors"}
    created = client.post(base, headers=writes, json=value)
    assert created.status_code == 201, "团队真实创建失败"
    item = created.json()
    assert set(item) == {"id", "name", "status", "revision"} and item["revision"] == 1
    assert client.post(base, headers=writes, json=value).json() == item
    assert client.post(base, headers=writes, json=value | {"name": "另一意图"}).status_code == 409
    assert client.get(base + "/" + item["id"], headers=headers).json() == item
    assert (
        client.get(base, headers=headers | {"X-Target-Tenant": str(uuid.uuid4())}).status_code
        == 403
    )
    cases.append(TEAM_CASES[0])
    path = base + "/" + item["id"]
    update_headers = writes | {"If-Match": '"1"', "Idempotency-Key": str(uuid.uuid4())}
    update = {"name": "团队新名称", "status": "ENABLED"}
    response = client.put(path, headers=update_headers, json=update)
    assert response.status_code == 200 and response.json()["revision"] == 2
    assert client.put(path, headers=update_headers, json=update).json() == response.json()
    assert (
        client.put(
            path, headers=update_headers | {"Idempotency-Key": str(uuid.uuid4())}, json=update
        ).status_code
        == 409
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_directory_audit WHERE resource_id=%s", (item["id"],)
        )
        assert cursor.fetchone()[0] == 2
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_directory_outbox WHERE resource_id=%s", (item["id"],)
        )
        assert cursor.fetchone()[0] == 2
        cursor.execute(
            "SELECT actor_subject_id,actor_team_id,request_id FROM orbit_directory_audit "
            "WHERE resource_id=%s LIMIT 1",
            (item["id"],),
        )
        frozen = cursor.fetchone()
        assert frozen[:2] == (tenant, tenant) and str(uuid.UUID(frozen[2])) == frozen[2]
    cases.append(TEAM_CASES[1])
    with admin.cursor() as cursor:
        for index in range(24):
            cursor.execute(
                "INSERT INTO orbit_business_team(tenant_id,id,name,created_at) "
                "VALUES(%s,%s,%s,UTC_TIMESTAMP(3))",
                (tenant, str(uuid.uuid4()), f"分页夹具{index:02}"),
            )
    first = client.get(base, params={"q": "分页夹具", "page_size": 20}, headers=headers).json()
    assert len(first["items"]) == 20 and first["next_cursor"]
    second = client.get(
        base,
        params={"q": "分页夹具", "page_size": 20, "cursor": first["next_cursor"]},
        headers=headers,
    ).json()
    assert len(second["items"]) == 4 and second["next_cursor"] is None
    assert len({row["id"] for row in first["items"] + second["items"]}) == 24
    assert first["data_as_of"] == second["data_as_of"]
    assert (
        client.get(
            base,
            params={"q": "改筛选", "page_size": 20, "cursor": first["next_cursor"]},
            headers=headers,
        ).status_code
        == 409
    )
    assert client.get(base + "?q=a&q=b", headers=headers).status_code == 400
    assert (
        client.get(base + "?operator_user_id=" + str(uuid.uuid4()), headers=headers).status_code
        == 422
    )
    assert (
        client.get(base + "?date_from=2026-11-08&date_to=2026-11-07", headers=headers).status_code
        == 422
    )
    new = client.post(base, headers=writes | {"Idempotency-Key": str(uuid.uuid4())}, json=update)
    assert new.status_code == 201
    assert (
        client.get(
            base,
            params={"q": "分页夹具", "page_size": 20, "cursor": first["next_cursor"]},
            headers=headers,
        ).status_code
        == 409
    )
    cases.append(TEAM_CASES[2])
    root_path = base + "/" + tenant
    protected = client.put(
        root_path,
        headers=update_headers | {"Idempotency-Key": str(uuid.uuid4())},
        json={"name": "不能停用最后管理员团队", "status": "DISABLED"},
    )
    assert protected.status_code == 409 and protected.json()["code"] == "LAST_ADMIN_REQUIRED"
    assert client.get(root_path, headers=headers).json()["status"] == "ENABLED"
    cases.append(TEAM_CASES[3])
    for table in ("orbit_directory_audit", "orbit_directory_outbox"):
        with admin.cursor() as cursor:
            cursor.execute(
                f"CREATE TRIGGER fixture_team_failure BEFORE INSERT ON {table} "
                "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture rejection'"
            )
            cursor.execute(
                "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
            )
            revision = cursor.fetchone()[0]
        try:
            failed_key = str(uuid.uuid4())
            failed = client.put(
                path,
                headers=writes | {"If-Match": '"2"', "Idempotency-Key": failed_key},
                json=update | {"name": "必须回滚"},
            )
            assert failed.status_code == 503 and "fixture rejection" not in failed.text
            assert client.get(path, headers=headers).json()["revision"] == 2
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT revision FROM orbit_directory_clock WHERE tenant_id=%s", (tenant,)
                )
                assert cursor.fetchone()[0] == revision
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_directory_idempotency WHERE request_key=%s",
                    (failed_key,),
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_directory_audit WHERE resource_id=%s", (item["id"],)
                )
                assert cursor.fetchone()[0] == 2
        finally:
            with admin.cursor() as cursor:
                cursor.execute("DROP TRIGGER fixture_team_failure")
    cases.append(TEAM_CASES[4])
    try:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=1")
        assert client.get(base + "/capabilities", headers=headers).json()["can_create"] is False
        assert client.get(path, headers=headers).status_code == 404
        assert client.post(base, headers=writes, json=value).status_code == 403
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='TEAM_ADMIN' WHERE user_id=1")
        assert client.put(root_path, headers=update_headers, json=update).status_code == 403
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) "
                "VALUES(%s,1,%s)",
                (tenant, item["id"]),
            )
        assert client.get(path, headers=headers).status_code == 200
        manager_headers = writes | {"If-Match": '"2"', "Idempotency-Key": str(uuid.uuid4())}
        assert client.put(path, headers=manager_headers, json=update).status_code == 200
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE manager_user_id=1"
            )
        assert client.put(path, headers=manager_headers, json=update).status_code == 404
        cases.append(TEAM_CASES[5])
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE orbit_user_scope SET data_role='SUPER_ADMIN' WHERE user_id=1")
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(
                lambda _: client.put(
                    root_path,
                    headers=writes | {"If-Match": '"1"', "Idempotency-Key": str(uuid.uuid4())},
                    json={"name": "并发维护默认团队", "status": "ENABLED"},
                ),
                range(4),
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 409, 409, 409]
    with admin.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM orbit_directory_audit WHERE resource_id=%s", (tenant,))
        assert cursor.fetchone()[0] == 1
    cases.append(TEAM_CASES[6])
    login = client.post(
        "/login", json={"username": "admin", "password": password, "code": "", "uuid": ""}
    )
    assert login.status_code == 200 and login.json().get("token")
    new_headers = writes | {
        "Authorization": "Bearer " + login.json()["token"],
        "Idempotency-Key": str(uuid.uuid4()),
    }
    assert client.post(base, headers=new_headers, json=value).status_code == 403
    cases.append(TEAM_CASES[7])
