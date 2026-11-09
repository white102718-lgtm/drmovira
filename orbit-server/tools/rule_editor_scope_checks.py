"""规则专属scope真实SQL/HTTP工具；由root串行调用，不自行启动DB或平台。"""

import hashlib
import re
from uuid import uuid4

RULE_EDITOR_SCOPE_CASES = [
    "pythonRuleScope061ExactDualGeneratedForeignKeysAndOriginalGuards",
    "pythonRuleScopeOnlyOriginalRulesActionWithoutAccountsRead",
    "pythonRuleAccountCandidatesBothCurrentScopesFourSizesKeyset",
    "pythonRuleScopeIdsFullSevenFieldsOriginalFiveResponse",
    "pythonRuleScopeFilterCompleteCreatorPrivateMemberThree",
    "pythonRuleScopeSignedCursorDomainFilterSizeAndWatermark",
    "pythonRuleScopeSameKeyOriginalReceiptDifferentBodyConflict",
    "pythonRuleScopeFullMembersLateRevocationRejectsFirstPage",
    "pythonRuleScopeCsrfMissingForeignAndOutboxAtomicRollback",
    "pythonRuleScopeCurrentCreateRevocationAndStrictBoundary",
]

TABLES = (
    "orbit_rule_editor_scope_snapshot",
    "orbit_rule_editor_scope_member",
    "orbit_rule_editor_scope_event",
    "orbit_rule_editor_scope_outbox",
)


def guard_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or type(admin.port) is not int
        or admin.port != 13306
        or type(database) is not str
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("RULE_SCOPE_ISOLATED_UUID_REQUIRED")


def run_rule_editor_scope_checks(client, admin, headers, password, cache, database, cases):
    guard_target(admin, database)
    if __package__:
        from .fixture_login import fixture_login
        from .metric_profile_reference_checks import seed_metric_reference_profile
        from .rule_definition_checks import definition_body
        from .rule_editor_checks import checked
    else:
        from fixture_login import fixture_login
        from metric_profile_reference_checks import seed_metric_reference_profile
        from rule_definition_checks import definition_body
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
    columns = sql(
        "SELECT COLUMN_NAME,EXTRA,GENERATION_EXPRESSION FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='orbit_rule_scope_manifest' "
        "AND COLUMN_NAME IN('account_source_snapshot_id',"
        "'rule_source_snapshot_id') ORDER BY COLUMN_NAME",
        (database,),
        all=True,
    )
    assert len(columns) == 2 and all("STORED GENERATED" in row[1] for row in columns)
    assert all("source_kind" in row[2] and "source_snapshot_id" in row[2] for row in columns)
    fks = sql(
        "SELECT CONSTRAINT_NAME,REFERENCED_TABLE_NAME FROM "
        "information_schema.REFERENTIAL_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA=%s AND TABLE_NAME='orbit_rule_scope_manifest' "
        "AND CONSTRAINT_NAME IN('fk_rule_manifest_account_source',"
        "'fk_rule_manifest_editor_source') "
        "ORDER BY CONSTRAINT_NAME",
        (database,),
        all=True,
    )
    assert fks == (
        ("fk_rule_manifest_account_source", "orbit_account_scope_snapshot"),
        ("fk_rule_manifest_editor_source", "orbit_rule_editor_scope_snapshot"),
    )
    old_guards = sql(
        "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s "
        "AND TRIGGER_NAME IN('rule_manifest_insert','rule_manifest_update','rule_manifest_delete',"
        "'rule_manifest_source_kind_update')",
        (database,),
        all=True,
    )
    assert len(old_guards) == 4
    cases.append(RULE_EDITOR_SCOPE_CASES[0])
    caps = checked(client.get("/api/v1/roles/capabilities", headers=headers))
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "规则账户专属-" + uuid4().hex[:10],
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
    native, owner, username = 990611, str(uuid4()), "rule_scope_" + uuid4().hex[:12]
    assert sql("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,), all=True)[0][0] == 0
    sql(
        "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
        "SELECT %s,%s,'规则账户本人',%s,password,'0','0' FROM sys_user WHERE user_id=1",
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
        "VALUES(%s,%s,%s,%s,'规则账户本人',0,UTC_TIMESTAMP(3))",
        (tenant, owner, native, team),
    )
    sql("UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    login = checked(fixture_login(client, cache, {"username": username, "password": password}))
    user_headers = {"Authorization": "Bearer " + login["token"]}
    context = checked(
        client.get("/api/v1/rules/edit-context", headers=user_headers, params={"action": "CREATE"})
    )
    csrf = context["csrf_token"]
    checked(client.get("/api/v1/scope-snapshots/capabilities", headers=user_headers), 403)
    cases.append(RULE_EDITOR_SCOPE_CASES[1])
    marker = "RuleScope" + uuid4().hex[:12]
    ids = sorted(str(uuid4()) for _ in range(205))
    foreign = str(uuid4())
    for index, identifier in enumerate(ids + [foreign]):
        sql(
            "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
            "owner_team_id,currency,timezone_id,auth_status,account_status,value_json,details_json,"
            "bound_at,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'Asia/Shanghai','UNKNOWN',"
            "'UNKNOWN','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (
                tenant,
                identifier,
                "00" + str(10**24 + uuid4().int % 10**24),
                marker + str(index),
                marker,
                owner if identifier != foreign else root_owner,
                team,
                "USD" if index % 2 == 0 else "EUR",
            ),
        )
    sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    query = {"action": "CREATE", "owner_user_id": owner, "owner_team_id": team, "q": marker}
    base = "/api/v1/rules/editor-scope-snapshots"

    def counts():
        return tuple(sql("SELECT COUNT(*) FROM " + table, all=True)[0][0] for table in TABLES)

    def create(selection, *, key=None, status=201, token=csrf):
        return checked(
            client.post(
                base,
                headers=user_headers
                | {"X-CSRF-Token": token, "Idempotency-Key": key or str(uuid4())},
                json={
                    "action": "CREATE",
                    "rule_id": None,
                    "ownership": {"owner_user_id": owner, "owner_team_id": team},
                    "selection": selection,
                },
            ),
            status,
        )

    def members(snapshot, params=None, *, identity=None, status=200):
        return checked(
            client.get(
                base + "/" + snapshot["id"] + "/members",
                headers=identity or user_headers,
                params=params or {},
            ),
            status,
        )

    for size in (20, 50, 100, 200):
        actual, cursor, seen = [], None, set()
        while True:
            page = checked(
                client.get(
                    "/api/v1/rules/editor-accounts",
                    headers=user_headers,
                    params=query
                    | {"page_size": str(size)}
                    | ({"cursor": cursor} if cursor else {}),
                )
            )
            assert set(page) == {"items", "next_cursor", "data_as_of", "scope_version"}
            assert all(set(item) == {"account_id", "external_id", "name"} for item in page["items"])
            actual.extend(item["account_id"] for item in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
            assert cursor not in seen
            seen.add(cursor)
        assert actual == ids
    cases.append(RULE_EDITOR_SCOPE_CASES[2])
    selected = {"mode": "IDS", "account_ids": ids[:201], "filter": None}
    key = str(uuid4())
    snapshot = create(selected, key=key)
    assert set(snapshot) == {"id", "count", "scope_version", "hash", "created_at"}
    assert snapshot["count"] == 201
    frozen = sql(
        "SELECT account_id,external_id,name,account_revision,owner_user_id,owner_team_id,currency "
        "FROM orbit_rule_editor_scope_member WHERE tenant_id=%s AND "
        "snapshot_id=%s ORDER BY account_id",
        (tenant, snapshot["id"]),
        all=True,
    )
    assert [row[0] for row in frozen] == ids[:201]
    assert (
        hashlib.sha256(canonical([list(row) for row in frozen]).encode()).hexdigest()
        == snapshot["hash"]
    )
    cases.append(RULE_EDITOR_SCOPE_CASES[3])
    filtered = create(
        {
            "mode": "FILTER",
            "account_ids": [],
            "filter": {
                "q": marker,
                "status": None,
                "auth_status": None,
                "operator_user_id": None,
                "vendor_id": None,
            },
        }
    )
    assert filtered["count"] == 205
    actual, cursor = [], None
    while True:
        page = members(filtered, {"page_size": "200"} | ({"cursor": cursor} if cursor else {}))
        assert all(set(item) == {"account_id", "external_id", "name"} for item in page["items"])
        actual.extend(item["account_id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert actual == ids
    members(filtered, identity=headers, status=404)  # SUPER也不冒充creator。
    cases.append(RULE_EDITOR_SCOPE_CASES[4])
    first = members(filtered, {"page_size": "20"})
    assert first["next_cursor"]
    members(filtered, {"page_size": "50", "cursor": first["next_cursor"]}, status=409)
    members(filtered, {"page_size": "20", "q": marker, "cursor": first["next_cursor"]}, status=409)
    checked(
        client.get(
            "/api/v1/rules/editor-accounts",
            headers=user_headers,
            params=query | {"page_size": "20", "cursor": first["next_cursor"]},
        ),
        409,
    )
    sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    members(filtered, {"page_size": "20", "cursor": first["next_cursor"]}, status=409)
    cases.append(RULE_EDITOR_SCOPE_CASES[5])
    baseline = counts()
    assert create(selected, key=key) == snapshot
    assert counts() == baseline
    create({"mode": "IDS", "account_ids": ids[:200], "filter": None}, key=key, status=409)
    assert counts() == baseline
    # 同一个真实actor/raw key在两个独立namespace各自发布，不改025唯一键。
    root_context = checked(
        client.get("/api/v1/rules/edit-context", headers=headers, params={"action": "CREATE"})
    )
    root_key = str(uuid4())
    one_selection = {"mode": "IDS", "account_ids": ids[:1], "filter": None}
    root_scope = checked(
        client.post(
            base,
            headers=headers
            | {"X-CSRF-Token": root_context["csrf_token"], "Idempotency-Key": root_key},
            json={
                "action": "CREATE",
                "rule_id": None,
                "ownership": {"owner_user_id": root_owner, "owner_team_id": team},
                "selection": one_selection,
            },
        ),
        201,
    )
    original = checked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=headers
            | {"X-CSRF-Token": root_context["csrf_token"], "Idempotency-Key": root_key},
            json=one_selection,
        ),
        201,
    )
    assert root_scope["id"] != original["id"] and root_scope["count"] == original["count"] == 1
    assert (
        sql(
            "SELECT COUNT(*) FROM orbit_account_scope_snapshot WHERE tenant_id=%s "
            "AND actor_id=1 AND request_key=%s",
            (tenant, root_key),
            all=True,
        )[0][0]
        == 1
    )
    assert (
        sql(
            "SELECT COUNT(*) FROM orbit_rule_editor_scope_snapshot WHERE tenant_id=%s "
            "AND actor_id=1 AND request_key=%s",
            (tenant, root_key),
            all=True,
        )[0][0]
        == 1
    )
    # UPDATE来自真实原Rule；原source仍ACCOUNT，阶段2尚未声称RuleStore接受新RULE源。
    profile, _ = seed_metric_reference_profile(admin, database, tenant, index=690)
    rule_body = definition_body(
        "规则scope历史-" + uuid4().hex[:10], owner, team, original["id"], profile["id"]
    )
    capability = checked(
        client.get("/api/v1/rules/capabilities", headers=headers, params={"action": "CREATE"})
    )
    rule = checked(
        client.post(
            "/api/v1/rules",
            headers=headers
            | {"X-CSRF-Token": capability["csrf_token"], "Idempotency-Key": str(uuid4())},
            json=rule_body,
        ),
        201,
    )
    update_key = str(uuid4())
    update_body = {
        "action": "UPDATE",
        "rule_id": rule["id"],
        "ownership": {"owner_user_id": owner, "owner_team_id": team},
        "selection": one_selection,
    }
    update_headers = user_headers | {
        "X-CSRF-Token": csrf,
        "Idempotency-Key": update_key,
        "If-Match": '"1"',
    }
    update_scope = checked(client.post(base, headers=update_headers, json=update_body), 201)
    unchanged = counts()
    conflict = checked(
        client.post(base, headers=update_headers | {"If-Match": '"2"'}, json=update_body), 409
    )
    assert conflict["code"] == "IDEMPOTENCY_CONFLICT" and counts() == unchanged
    edit_cap = checked(
        client.get("/api/v1/rules/capabilities", headers=headers, params={"action": "UPDATE"})
    )
    edited = checked(
        client.put(
            "/api/v1/rules/" + rule["id"],
            headers=headers
            | {
                "X-CSRF-Token": edit_cap["csrf_token"],
                "Idempotency-Key": str(uuid4()),
                "If-Match": '"1"',
            },
            json=rule_body | {"name": rule_body["name"] + "-改版"},
        )
    )
    assert edited["revision"] == 2
    baseline = counts()
    # 旧revision只作历史审计；成功key先读原receipt，不能因当前head已2而重新冻结。
    assert checked(client.post(base, headers=update_headers, json=update_body), 201) == update_scope
    conflict = checked(
        client.post(base, headers=update_headers | {"If-Match": '"2"'}, json=update_body), 409
    )
    assert conflict["code"] == "IDEMPOTENCY_CONFLICT" and counts() == baseline
    history = members(update_scope)
    assert [item["account_id"] for item in history["items"]] == ids[:1]
    assert counts() == baseline
    assert (
        sql(
            "SELECT rule_revision FROM orbit_rule_editor_scope_snapshot WHERE tenant_id=%s "
            "AND id=%s",
            (tenant, update_scope["id"]),
            all=True,
        )[0][0]
        == 1
    )
    cases.append(RULE_EDITOR_SCOPE_CASES[6])
    sql(
        "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
        (root_owner, tenant, ids[-1]),
    )
    sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    try:
        members(filtered, {"page_size": "20"}, status=409)  # 撤的是最后一项，仍拒绝第一页。
    finally:
        sql(
            "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
            (owner, tenant, ids[-1]),
        )
        sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    cases.append(RULE_EDITOR_SCOPE_CASES[7])
    baseline = counts()
    create(selected, token="invalid-session-token", status=403)
    create({"mode": "IDS", "account_ids": [foreign], "filter": None}, status=404)
    assert counts() == baseline
    trigger = "rule_scope_fixture_fail_" + uuid4().hex[:10]
    try:
        sql(
            "CREATE TRIGGER "
            + trigger
            + " BEFORE INSERT ON orbit_rule_editor_scope_outbox FOR EACH ROW "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='ISOLATED_RULE_SCOPE_OUTBOX_1644'"
        )
        create(selected, status=503)
        assert counts() == baseline
    finally:
        sql("DROP TRIGGER IF EXISTS " + trigger)
    cases.append(RULE_EDITOR_SCOPE_CASES[8])
    sql(
        "DELETE FROM orbit_business_role_action WHERE tenant_id=%s AND role_id=%s "
        "AND permission_code='rules.create'",
        (tenant, role["id"]),
    )
    try:
        checked(
            client.get("/api/v1/rules/editor-accounts", headers=user_headers, params=query), 403
        )
        members(filtered, status=403)
    finally:
        sql(
            "INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) "
            "VALUES(%s,%s,'rules.create')",
            (tenant, role["id"]),
        )
    checked(
        client.get(
            "/api/v1/rules/editor-accounts", headers=user_headers, params=query | {"previous": "x"}
        ),
        400,
    )
    members(filtered, {"cursor": ""}, status=422)
    cases.append(RULE_EDITOR_SCOPE_CASES[9])
    return {
        "rule_scope_cases": 10,
        "actual_accounts": 205,
        "platform_writes": 0,
        "production_authority_verified": False,
        "fifty_thousand_capacity_verified": False,
    }
