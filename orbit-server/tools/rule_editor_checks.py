"""规则编辑辅助真实HTTP专项；仅本轮SQL FIXTURE资料，不授Meta/模拟资格。"""

import json
import re
from uuid import UUID, uuid4

RULE_EDITOR_CASES = [
    "pythonRuleEditorCreateEditOnlyNativeContextWithoutBorrowedMenus",
    "pythonRuleEditorOwnerTrueLabelsSelfAndRootKeysetNoUserDirectoryPermission",
    "pythonRuleEditorProfileOriginalTwelveFieldsAndTwentyPlusKeyset",
    "pythonRuleEditorSignedCursorSessionKindSizeFilterAndClockBinding",
    "pythonRuleEditorUpdateOwnRuleKeepsValidOwnerAndDisplaysFrozenVersusCurrentProfile",
    "pythonRuleEditorDisabledProfileUnavailableAndBadProofRejectsWholePage",
    "pythonRuleEditorCurrentActionRevocationAndForeignRuleHidden",
    "pythonRuleEditorStrictGetBoundaryAndReadonlyBusinessTables",
]


def guard_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or type(admin.port) is not int
        or admin.port != 13306
        or not isinstance(database, str)
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("RULE_EDITOR_ISOLATED_UUID_REQUIRED")


def checked(response, status=200):
    value = response.json()
    if response.status_code != status:
        code = value.get("code") if isinstance(value, dict) else None
        # 不输出错误正文/msg、Token、账号或任何未知字符串。
        safe_code = (
            code
            if (type(code) is int and 100 <= code <= 599)
            or (type(code) is str and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code))
            else None
        )
        diagnostic = {
            "scope": "rule-editor-fixture",
            "phase": "http-status",
            "expected": status,
            "actual": response.status_code,
            "code": safe_code,
        }
        print(json.dumps(diagnostic), flush=True)
        raise AssertionError("RULE_EDITOR_HTTP_STATUS_MISMATCH")
    assert response.headers.get("cache-control") == "no-store"
    return value


def assert_foreign_rule(rule, expected_owner, actor_owner, team):
    assert expected_owner != actor_owner
    assert rule["ownership"] == {"owner_user_id": expected_owner, "owner_team_id": team}
    assert type(rule["id"]) is str and str(UUID(rule["id"])) == rule["id"]
    assert rule["revision"] == 1 and rule["state"] == "DRAFT"


def run_rule_editor_checks(client, admin, headers, password, cache, database, cases):
    guard_target(admin, database)
    if __package__:
        from .fixture_login import fixture_login
        from .metric_profile_query_checks import query_profile_sql_sample
        from .metric_profile_reference_checks import seed_metric_reference_profile
        from .rule_definition_checks import TABLES, definition_body
    else:
        from fixture_login import fixture_login
        from metric_profile_query_checks import query_profile_sql_sample
        from metric_profile_reference_checks import seed_metric_reference_profile
        from rule_definition_checks import TABLES, definition_body
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

    def get(path, params, *, identity=None, status=200):
        return checked(
            client.get("/api/v1/rules/" + path, headers=identity or user_headers, params=params),
            status,
        )

    def counts():
        return tuple(sql("SELECT COUNT(*) FROM " + table, all=True)[0][0] for table in TABLES)

    assert sql("SELECT DATABASE()", all=True)[0][0] == database
    tenant, root_owner, team = sql(
        "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1", all=True
    )[0]
    role_cap = checked(client.get("/api/v1/roles/capabilities", headers=headers))
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": role_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "规则辅助-" + uuid4().hex[:10],
                "menu_codes": ["rules"],
                "permission_codes": ["rules.create", "rules.edit"],
            },
        ),
        201,
    )
    native_role = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
        all=True,
    )[0][0]
    native, owner, username = 990601, str(uuid4()), "rule_editor_" + uuid4().hex[:10]
    assert sql("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,), all=True)[0][0] == 0
    sql(
        "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
        "SELECT %s,%s,'规则候选本人',%s,password,'0','0' FROM sys_user WHERE user_id=1",
        (native, username, username + "@fixture.example.org"),
    )
    sql(
        "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
        "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
        (native, str(uuid4())),
    )
    sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, native_role))
    sql(
        "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
        (native, tenant),
    )
    sql(
        "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,"
        "display_name,invited,created_at) "
        "VALUES(%s,%s,%s,%s,'规则候选本人',0,UTC_TIMESTAMP(3))",
        (tenant, owner, native, team),
    )
    sql("UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    login = checked(fixture_login(client, cache, {"username": username, "password": password}))
    user_headers = {"Authorization": "Bearer " + login["token"]}
    before = counts()
    create = {"action": "CREATE"}
    context = get("edit-context", create)
    assert set(context) == {
        "action",
        "rule_id",
        "rule_revision",
        "editable",
        "csrf_token",
        "default_ownership",
        "selected_owner",
        "selected_profile",
    }
    assert context["default_ownership"] == {"owner_user_id": owner, "owner_team_id": team}
    assert context["selected_owner"]["can_keep"] is True and context["selected_profile"] is None
    for path in (
        "/api/v1/scope-snapshots/capabilities",
        "/api/v1/metrics/capabilities",
        "/api/v1/users/capabilities",
    ):
        checked(client.get(path, headers=user_headers), 403)
    assert counts() == before
    cases.append(RULE_EDITOR_CASES[0])
    owner_query = create | {"kind": "OWNER", "page_size": "20"}
    owners = get("editor-options", owner_query)
    assert len(owners["items"]) == 1
    assert owners["items"][0]["id"] == owner and owners["items"][0]["name"] == "规则候选本人"
    assert set(owners["items"][0]) == {"id", "team_id", "name", "team_name"}
    root_owners = get("editor-options", owner_query, identity=headers)
    assert (
        any(item["id"] == root_owner for item in root_owners["items"]) or root_owners["next_cursor"]
    )
    # 技术当前scope样本；证明TEAM_ADMIN无显式managed不扩到团队，加入后才出现目标。
    sql("UPDATE orbit_user_scope SET data_role='TEAM_ADMIN' WHERE user_id=%s", (native,))
    try:
        restricted = get("editor-options", owner_query)
        assert [item["id"] for item in restricted["items"]] == [owner]
        sql(
            "INSERT INTO orbit_business_team_manager(tenant_id,team_id,manager_user_id,enabled) "
            "VALUES(%s,%s,%s,1)",
            (tenant, team, native),
        )
        managed, continuation = [], None
        while True:
            page = get(
                "editor-options", owner_query | ({"cursor": continuation} if continuation else {})
            )
            managed.extend(item["id"] for item in page["items"])
            continuation = page["next_cursor"]
            if continuation is None:
                break
        assert root_owner in managed and owner in managed and managed == sorted(set(managed))
    finally:
        sql(
            "DELETE FROM orbit_business_team_manager WHERE tenant_id=%s AND team_id=%s "
            "AND manager_user_id=%s",
            (tenant, team, native),
        )
        sql("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=%s", (native,))
    cases.append(RULE_EDITOR_CASES[1])
    profiles = []
    for index in range(21):
        profile, _ = seed_metric_reference_profile(admin, database, tenant, index=601 + index)
        profiles.append(profile)
    profile_query = create | {
        "kind": "PROFILE",
        "owner_user_id": owner,
        "owner_team_id": team,
        "page_size": "20",
    }
    first = get("editor-options", profile_query)
    assert len(first["items"]) == 20 and first["next_cursor"]
    all_profiles, seen_cursor, current = first["items"][:], set(), first
    while current["next_cursor"]:
        cursor = current["next_cursor"]
        assert cursor not in seen_cursor
        seen_cursor.add(cursor)
        current = get("editor-options", profile_query | {"cursor": cursor})
        all_profiles.extend(current["items"])
    ids = [item["id"] for item in all_profiles]
    assert ids == sorted(set(ids)) and {item["id"] for item in profiles}.issubset(ids)
    assert all(len(item) == 12 and "name" not in item for item in all_profiles)
    cases.append(RULE_EDITOR_CASES[2])
    for changes in ({"page_size": "50"}, {"q": profiles[0]["id"]}):
        get(
            "editor-options", profile_query | changes | {"cursor": first["next_cursor"]}, status=409
        )
    get("editor-options", owner_query | {"cursor": first["next_cursor"]}, status=409)
    get(
        "editor-options",
        profile_query | {"cursor": first["next_cursor"]},
        identity=headers,
        status=409,
    )
    sql("UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    get("editor-options", profile_query | {"cursor": first["next_cursor"]}, status=409)
    cases.append(RULE_EDITOR_CASES[3])

    def seed_rule(rule_owner):
        account = str(uuid4())
        sql(
            "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
            "owner_user_id,owner_team_id,currency,timezone_id,auth_status,account_status,"
            "value_json,details_json,bound_at,created_at) "
            "VALUES(%s,%s,%s,'规则辅助账户','规则辅助账户',%s,%s,'USD','Asia/Shanghai','UNKNOWN','UNKNOWN','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (tenant, account, str(10**25 + uuid4().int % 10**25), rule_owner, team),
        )
        sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
        scope_cap = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers))
        frozen = checked(
            client.post(
                "/api/v1/scope-snapshots",
                headers=headers
                | {"X-CSRF-Token": scope_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
                json={"mode": "IDS", "account_ids": [account], "filter": None},
            ),
            201,
        )
        cap = checked(
            client.get("/api/v1/rules/capabilities", headers=headers, params={"action": "CREATE"})
        )
        body = definition_body(
            "规则辅助引用-" + uuid4().hex[:10], rule_owner, team, frozen["id"], profiles[0]["id"]
        )
        result = checked(
            client.post(
                "/api/v1/rules",
                headers=headers
                | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
                json=body,
            ),
            201,
        )
        return result

    rule = seed_rule(owner)
    foreign_rule = seed_rule(root_owner)
    assert_foreign_rule(foreign_rule, root_owner, owner, team)
    update = {"action": "UPDATE", "rule_id": rule["id"]}
    selected = get("edit-context", update)
    assert selected["selected_owner"]["can_keep"] is True and selected["rule_revision"] == 1
    assert (
        selected["selected_profile"]["status"] == "CURRENT"
        and selected["selected_profile"]["current"] == profiles[0]
    )
    replacement, _ = seed_metric_reference_profile(
        admin, database, tenant, index=630, identifier=profiles[0]["id"]
    )
    selected = get("edit-context", update)
    assert selected["selected_profile"]["status"] == "CHANGED"
    assert selected["selected_profile"]["bound_version"] == profiles[0]["version"]
    assert selected["selected_profile"]["current"] == replacement
    get(
        "editor-options",
        update | {"kind": "PROFILE", "owner_user_id": root_owner, "owner_team_id": team},
        status=403,
    )
    cases.append(RULE_EDITOR_CASES[4])
    sql(
        "UPDATE orbit_metric_profile_head SET state='DISABLED' WHERE tenant_id=%s AND id=%s",
        (tenant, profiles[0]["id"]),
    )
    try:
        selected = get("edit-context", update)
        assert (
            selected["selected_profile"]["status"] == "UNAVAILABLE"
            and selected["selected_profile"]["current"] is None
        )
    finally:
        sql(
            "UPDATE orbit_metric_profile_head SET state='ENABLED' WHERE tenant_id=%s AND id=%s",
            (tenant, profiles[0]["id"]),
        )
    bad, bad_hash, proof = query_profile_sql_sample(650)
    proof_doc = json.loads(proof)
    proof_doc["source_sha256"] = "b" * 64  # 明确技术坏来源INSERT，不是正常Authority发行。
    sql(
        "INSERT INTO orbit_metric_profile_version(tenant_id,profile_id,version,"
        "payload_json,payload_hash,source,authority_kind,observed_at,evidence_ref,"
        "source_sha256,source_proof_json,created_by) "
        "VALUES(%s,%s,%s,%s,%s,'FIXTURE','ISOLATED_TEST',UTC_TIMESTAMP(3),'isolated-query:SQL_ONLY_NOT_META',%s,%s,1)",
        (
            tenant,
            bad["id"],
            bad["version"],
            canonical(bad),
            bad_hash,
            "a" * 64,
            canonical(proof_doc),
        ),
    )
    sql(
        "INSERT INTO orbit_metric_profile_head(tenant_id,id,current_version,revision,state) "
        "VALUES(%s,%s,%s,1,'ENABLED')",
        (tenant, bad["id"], bad["version"]),
    )
    try:
        get("editor-options", profile_query | {"page_size": "200"}, status=503)
    finally:
        sql(
            "UPDATE orbit_metric_profile_head SET state='DISABLED' WHERE tenant_id=%s AND id=%s",
            (tenant, bad["id"]),
        )
    cases.append(RULE_EDITOR_CASES[5])
    sql(
        "DELETE FROM orbit_business_role_action WHERE tenant_id=%s AND role_id=%s "
        "AND permission_code='rules.create'",
        (tenant, role["id"]),
    )
    try:
        get("edit-context", create, status=403)
        get("edit-context", update)  # edit独立仍有效，不自动要求create/read。
    finally:
        sql(
            "INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) "
            "VALUES(%s,%s,'rules.create')",
            (tenant, role["id"]),
        )
    foreign_baseline = counts()
    # 本工具自己经原scope/Rule HTTP创建，不能假定其他专项存在root归属规则。
    assert sql(
        "SELECT owner_user_id,owner_team_id FROM orbit_rule_head WHERE tenant_id=%s AND id=%s",
        (tenant, foreign_rule["id"]),
        all=True,
    ) == ((root_owner, team),)
    get("edit-context", {"action": "UPDATE", "rule_id": foreign_rule["id"]}, status=404)
    assert counts() == foreign_baseline
    cases.append(RULE_EDITOR_CASES[6])
    baseline = counts()
    get("editor-options", owner_query | {"previous": "arbitrary"}, status=400)
    get("edit-context", {"action": "CREATE", "rule_id": rule["id"]}, status=422)
    checked(
        client.get(
            "/api/v1/rules/edit-context",
            headers=user_headers | {"X-Target-Tenant": str(uuid4())},
            params=create,
        ),
        403,
    )
    checked(
        client.request(
            "GET", "/api/v1/rules/edit-context", headers=user_headers, params=create, content=b"{}"
        ),
        400,
    )
    get("editor-options", owner_query)
    get("editor-options", profile_query)
    assert counts() == baseline
    cases.append(RULE_EDITOR_CASES[7])
    return {
        "editor_cases": len(RULE_EDITOR_CASES),
        "technical_fixture_profiles": 21,
        "platform_writes": 0,
        "scope_engine_implemented": False,
        "production_authority_verified": False,
    }
