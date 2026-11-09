"""独立户商代称真实HTTP/MySQL专项，主线注册017后统一串行调用。"""

import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor

from fixture_login import fixture_login

VENDOR_ALIAS_CASES = [
    "pythonVendorAliasUnknownGetAndNullNoopNeverInventMaintenance",
    "pythonVendorAliasNfcCasReplayAndCatalogWatermark",
    "pythonVendorAliasSameValueNoopClearAndDuplicateAliasesAllowed",
    "pythonVendorAliasStrictStructureBoundariesAndBatchLimit",
    "pythonVendorAliasAuditFailureRollsBackAliasClockAndKey",
    "pythonVendorAliasConcurrentFirstWriteOnlyOneSucceeds",
    "pythonVendorAliasUserSharedReadAndExplicitManagerWriteScope",
    "pythonVendorAliasRevokedActionScopeReplayAndForeignTenantInvisible",
]


def run_vendor_alias_checks(client, admin, headers, fixture, password, cache, cases):
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", cursor.fetchone()[0])
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, root_user, root_team = cursor.fetchone()

    def state():
        with admin.cursor() as cursor:
            result = []
            for table in (
                "orbit_vendor_alias",
                "orbit_reference_clock",
                "orbit_reference_event",
                "orbit_reference_idempotency",
            ):
                cursor.execute("SELECT * FROM " + table)
                result.append(tuple(sorted(cursor.fetchall(), key=repr)))
            return tuple(result)

    def head(identity, revision=1, key=None):
        caps = client.get("/api/v1/vendor-aliases/capabilities", headers=identity)
        assert caps.status_code == 200
        return identity | {
            "X-CSRF-Token": caps.json()["csrf_token"],
            "Idempotency-Key": key or str(uuid.uuid4()),
            "If-Match": f'"{revision}"',
        }

    def read(identifier, identity=headers):
        return client.get("/api/v1/vendor-aliases/" + identifier, headers=identity)

    def put(identifier, alias, revision=1, identity=headers, write=None):
        return client.put(
            "/api/v1/vendor-aliases/" + identifier,
            headers=write or head(identity, revision),
            json={"alias": alias, "reason": "真实代称维护验收"},
        )

    def vendor(actor=None, owners=None):
        actor = actor or {"id": root_user, "team": root_team}
        identifier = str(uuid.uuid4())
        row = {
            "id": identifier,
            "kind": "VENDOR",
            "name": "完整名称不能截断为代称" + identifier,
            "availability": "AVAILABLE",
            "source_key": "alias-fixture-" + identifier,
            "owner_team_id": actor["team"],
            "data_owner_user_ids": owners or [actor["id"]],
        }
        caps = client.get("/api/v1/reference-catalog-imports/capabilities", headers=headers).json()
        write = headers | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": str(uuid.uuid4())}
        preview = client.post(
            "/api/v1/reference-catalog-imports",
            headers=write,
            json={
                "kind": "VENDOR",
                "source": "代称专项",
                "reason": "真实目录",
                "base_catalog_revision": caps["catalog_revision"],
                "items": [row],
            },
        )
        assert preview.status_code == 201 and preview.json()["state"] == "VALIDATED"
        frozen = preview.json()
        response = client.post(
            "/api/v1/reference-catalog-imports/" + frozen["id"] + "/commit",
            headers=write
            | {"Idempotency-Key": str(uuid.uuid4()), "If-Match": f'"{frozen["revision"]}"'},
        )
        assert response.status_code == 200
        return identifier

    identifier = vendor()
    before = state()
    unknown = read(identifier)
    assert unknown.status_code == 200
    assert (
        unknown.json()["alias"] is None
        and unknown.json()["revision"] == 1
        and unknown.json()["updated_at"] is None
    )
    assert state() == before, "GET不得初始化代称行或修改任何状态"
    noop = put(identifier, None)
    assert noop.status_code == 200 and noop.json() == unknown.json()
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_vendor_alias WHERE tenant_id=%s AND vendor_id=%s",
            (tenant, identifier),
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_reference_event WHERE "
            "resource_type='VENDOR_ALIAS' AND resource_id=%s",
            (identifier,),
        )
        assert cursor.fetchone()[0] == 0
    cases.append(VENDOR_ALIAS_CASES[0])

    saved_head = head(headers)
    saved = put(identifier, " e\u0301 ", write=saved_head)
    assert saved.status_code == 200
    saved = saved.json()
    assert saved["alias"] == "é" and saved["revision"] == 2 and saved["updated_at"].endswith("Z")
    assert saved["catalog_revision"] == unknown.json()["catalog_revision"] + 1
    before = state()
    assert put(identifier, " e\u0301 ", write=saved_head).json() == saved
    assert state() == before
    assert put(identifier, "旧版本", 1).status_code == 409
    assert put(identifier, "不同意图", write=saved_head).status_code == 409
    assert state() == before
    cases.append(VENDOR_ALIAS_CASES[1])

    before = read(identifier).json()
    assert put(identifier, "é", 2).json() == before
    cleared = put(identifier, None, 2)
    assert (
        cleared.status_code == 200
        and cleared.json()["revision"] == 3
        and cleared.json()["alias"] is None
    )
    assert cleared.json()["catalog_revision"] == before["catalog_revision"] + 1
    assert put(identifier, None, 3).json() == cleared.json()
    another = vendor()
    assert put(identifier, "共同代称", 3).status_code == 200
    assert put(another, "共同代称").status_code == 200
    cases.append(VENDOR_ALIAS_CASES[2])

    for body, expected in (
        ({"alias": 3, "reason": "类型"}, 400),
        ({"alias": "户" * 31, "reason": "边界"}, 422),
        ({"alias": "", "reason": "空值"}, 422),
        ({"alias": None, "reason": "未知", "name": "禁止"}, 400),
    ):
        before = state()
        response = client.put(
            "/api/v1/vendor-aliases/" + identifier, headers=head(headers, 4), json=body
        )
        assert response.status_code == expected
        assert state() == before
    assert (
        client.get(
            "/api/v1/vendor-aliases", headers=headers, params={"ids": identifier + "," + identifier}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/vendor-aliases",
            headers=headers,
            params={"ids": ",".join(str(uuid.uuid4()) for _ in range(201))},
        ).status_code
        == 422
    )
    cases.append(VENDOR_ALIAS_CASES[3])

    before = state()
    retry_head = head(headers, 4)
    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TRIGGER fixture_alias_failure BEFORE INSERT ON orbit_reference_event "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture rejection'"
        )
    try:
        assert put(identifier, "必须原子回滚", write=retry_head).status_code == 503
        assert state() == before
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER fixture_alias_failure")
    assert put(identifier, "必须原子回滚", write=retry_head).status_code == 200
    cases.append(VENDOR_ALIAS_CASES[4])

    racing = vendor()
    race_heads = [head(headers), head(headers)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda pair: put(racing, pair[1], write=pair[0]),
                zip(race_heads, ("竞态甲", "竞态乙"), strict=True),
            )
        )
    assert sorted(response.status_code for response in results) == [200, 409]
    assert read(racing).json()["revision"] == 2
    cases.append(VENDOR_ALIAS_CASES[5])

    manager, user, _, peer = fixture["users"][:4]
    role_caps = client.get("/api/v1/roles/capabilities", headers=headers).json()
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {"X-CSRF-Token": role_caps["csrf_token"], "Idempotency-Key": str(uuid.uuid4())},
        json={
            "name": "代称范围" + uuid.uuid4().hex[:8],
            "menu_codes": ["system", "accounts"],
            "permission_codes": ["system.read", "system.dictionaries.manage", "accounts.read"],
        },
    )
    assert role.status_code == 201
    role_id = role.json()["id"]
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role_id),
        )
        native_role = cursor.fetchone()[0]
        for actor in (manager, user):
            cursor.execute(
                "INSERT INTO sys_user_role VALUES(%s,%s)", (actor["native"], native_role)
            )
    try:
        identities = []
        for actor in (manager, user):
            login = fixture_login(client, cache, {"username": actor["name"], "password": password})
            assert login.status_code == 200 and login.json().get("token")
            identities.append({"Authorization": "Bearer " + login.json()["token"]})
        manager_headers, user_headers = identities
        personal = vendor(user)
        shared = vendor(user, [user["id"], peer["id"]])
        assert put(personal, "本人代称", identity=user_headers).status_code == 200
        assert read(shared, user_headers).status_code == 200
        before = state()
        assert put(shared, "共享不能个人改", identity=user_headers).status_code == 403
        assert state() == before
        successful_head = head(manager_headers)
        assert (
            put(shared, "管理团队代称", identity=manager_headers, write=successful_head).status_code
            == 200
        )
        cases.append(VENDOR_ALIAS_CASES[6])

        with admin.cursor() as cursor:
            cursor.execute(
                "DELETE FROM orbit_business_role_action WHERE tenant_id=%s AND role_id=%s "
                "AND permission_code='system.dictionaries.manage'",
                (tenant, role_id),
            )
        try:
            before = state()
            assert (
                put(
                    shared, "管理团队代称", identity=manager_headers, write=successful_head
                ).status_code
                == 403
            )
            assert read(shared, manager_headers).status_code == 200
            assert state() == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO orbit_business_role_action "
                    "VALUES(%s,%s,'system.dictionaries.manage')",
                    (tenant, role_id),
                )
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE tenant_id=%s "
                "AND manager_user_id=%s AND team_id=%s",
                (tenant, manager["native"], user["team"]),
            )
        try:
            before = state()
            assert read(shared, manager_headers).status_code == 404
            assert (
                put(
                    shared, "管理团队代称", identity=manager_headers, write=successful_head
                ).status_code
                == 404
            )
            assert state() == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_business_team_manager SET enabled=1 WHERE tenant_id=%s "
                    "AND manager_user_id=%s AND team_id=%s",
                    (tenant, manager["native"], user["team"]),
                )
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE tenant_id<>%s LIMIT 1",
                (tenant,),
            )
            foreign_tenant, foreign_user, foreign_team = cursor.fetchone()
            foreign = str(uuid.uuid4())
            foreign_value = {
                "id": foreign,
                "kind": "VENDOR",
                "name": "另一租户真实户商",
                "availability": "AVAILABLE",
                "source_key": "alias-foreign-" + foreign,
                "owner_team_id": foreign_team,
                "data_owner_user_ids": [foreign_user],
            }
            cursor.execute(
                """INSERT INTO orbit_reference_record
                (tenant_id,id,kind,source_key,name,availability,owner_team_id,value_json,
                revision,catalog_revision,updated_at)
                VALUES(%s,%s,'VENDOR',%s,%s,'AVAILABLE',%s,%s,1,1,UTC_TIMESTAMP(3))""",
                (
                    foreign_tenant,
                    foreign,
                    foreign_value["source_key"],
                    foreign_value["name"],
                    foreign_team,
                    json.dumps(foreign_value),
                ),
            )
            cursor.execute(
                "INSERT INTO orbit_reference_owner VALUES(%s,%s,%s)",
                (foreign_tenant, foreign, foreign_user),
            )
        for identity in (headers, manager_headers, user_headers):
            before = state()
            assert read(foreign, identity).status_code == 404
            assert put(foreign, "不能跨租户", identity=identity).status_code == 404
            batch = client.get("/api/v1/vendor-aliases", headers=identity, params={"ids": foreign})
            assert batch.status_code == 200 and not batch.json()["items"]
            assert state() == before
        cases.append(VENDOR_ALIAS_CASES[7])
    finally:
        with admin.cursor() as cursor:
            for actor in (manager, user):
                cursor.execute(
                    "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                    (actor["native"], native_role),
                )
