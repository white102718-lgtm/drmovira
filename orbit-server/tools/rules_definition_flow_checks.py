"""规则定义+真实展示元数据闭环，零simulate/enable/广告写；仅root隔离队列调用。"""

import json
from uuid import uuid4

if __package__:
    from .rule_simulation_access_checks import guard_target
else:
    from rule_simulation_access_checks import guard_target

RULES_DEFINITION_FLOW_CASES = (
    "pythonRulesDefinitionOriginalCreateGetListPreservesFifteenAndPageFour",
    "pythonRulesDefinitionBatchDisplayMetadataTrueNamesCreatorAndUtcMilliseconds",
    "pythonRulesDefinitionOrGroupsDecimalZeroCooldownEditAndSuccessfulKeyReplay",
    "pythonRulesDefinitionDraftPauseRejectedArchiveAndCreationMetadataStable",
    "pythonRulesDefinitionMetadataReadOnlyActorNeedsNoDirectoryOrWriteActions",
    "pythonRulesDefinitionMixedInvisibleAndRealForeignTenantWhole404",
    "pythonRulesDefinitionCurrentReadRevokedAndStrictMetadataGet",
    "pythonRulesDefinitionMetadataReadsAllEightPersistentTablesUnchanged",
)
NATIVE_ACTORS = (990680, 990681)


def assert_read_only_info(response):
    value = response.json()
    permissions = value.get("permissions") if type(value) is dict else None
    valid_list = type(permissions) is list and all(type(item) is str for item in permissions)
    actual = set(permissions) if valid_list else set()
    expected = {"rules.read"}
    if response.status_code != 200 or not valid_list or actual - {""} != expected:
        fixed = frozenset(
            {
                "rules.read",
                "rules.create",
                "rules.edit",
                "rules.enable",
                "rules.pause",
                "rules.archive",
                "accounts.read",
                "monitor.read",
                "system.users.read",
                "*:*:*",
            }
        )
        print(
            json.dumps(
                {
                    "scope": "rules-definition-flow",
                    "phase": "native-info",
                    "status": response.status_code,
                    "permissions_type_valid": valid_list,
                    "known_permissions": sorted(actual & fixed),
                    "empty_permission_count": sum(item == "" for item in permissions)
                    if valid_list
                    else 0,
                    "other_permission_count": len(actual - fixed - {""}),
                }
            ),
            flush=True,
        )
        raise AssertionError("RULE_FLOW_READ_ONLY_INFO_MISMATCH")


def run_rules_definition_flow_checks(client, admin, headers, password, cache, database, cases):
    guard_target(admin, database)
    if __package__:
        from .fixture_login import fixture_login
        from .metric_fact_schema_checks import MetricFactSqlFixture
        from .metric_profile_reference_checks import seed_metric_reference_profile
        from .rule_definition_checks import TABLES, definition_body
        from .rule_editor_checks import checked
    else:
        from fixture_login import fixture_login
        from metric_fact_schema_checks import MetricFactSqlFixture
        from metric_profile_reference_checks import seed_metric_reference_profile
        from rule_definition_checks import TABLES, definition_body
        from rule_editor_checks import checked
    from orbit_api.rule_contract import Rule, RulePage, parse_rule_response
    from orbit_api.rule_display_metadata_contract import RuleDisplayMetadataPage, created_at_text

    def sql(statement, values=(), *, rows=False):
        try:
            with admin.cursor() as cursor:
                cursor.execute(statement, values)
                value = cursor.fetchall() if rows else cursor.rowcount
            admin.commit()
            return value
        except BaseException:
            admin.rollback()
            raise

    if sql("SELECT DATABASE()", rows=True) != ((database,),):
        raise ValueError("RULE_FLOW_ACTUAL_DATABASE_REQUIRED")
    fixture = MetricFactSqlFixture(admin, database)
    tenant, root_owner, team = fixture.tenant, fixture.owner, fixture.team
    role_cap = checked(client.get("/api/v1/roles/capabilities", headers=headers))
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": role_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "规则闭环只读-" + uuid4().hex[:8],
                "menu_codes": ["rules"],
                "permission_codes": ["rules.read"],
            },
        ),
        201,
    )
    read_role = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
        rows=True,
    )[0][0]
    foreign_tenant, foreign_team = str(uuid4()), str(uuid4())
    sql("INSERT INTO orbit_tenant(id,name) VALUES(%s,'规则闭环外租户')", (foreign_tenant,))
    sql(
        "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,'规则闭环外团队')",
        (foreign_tenant, foreign_team),
    )
    sql("INSERT INTO orbit_rule_clock(tenant_id) VALUES(%s)", (foreign_tenant,))
    foreign_role = NATIVE_ACTORS[1]
    assert (
        sql("SELECT COUNT(*) FROM sys_role WHERE role_id=%s", (foreign_role,), rows=True)[0][0] == 0
    )
    sql(
        "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,data_scope,status,del_flag) "
        "VALUES(%s,'规则闭环外租户只读',%s,1,'1','0','0')",
        (foreign_role, "rule_flow_" + uuid4().hex),
    )
    business_role = str(uuid4())
    sql(
        "INSERT INTO "
        "orbit_business_role(tenant_id,id,native_role_id,built_in,created_at,updated_at) "
        "VALUES(%s,%s,%s,0,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
        (foreign_tenant, business_role, foreign_role),
    )
    sql(
        "INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) VALUES(%s,%s,'rules')",
        (foreign_tenant, business_role),
    )
    sql(
        "INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) "
        "VALUES(%s,%s,'rules.read')",
        (foreign_tenant, business_role),
    )
    sql(
        "INSERT INTO sys_role_menu(role_id,menu_id) SELECT %s,menu_id FROM sys_menu "
        "WHERE menu_id IN(31000,31040,31047) OR (perms='rules.read' AND menu_type='F')",
        (foreign_role,),
    )
    people = []
    for native, selected_tenant, selected_team, native_role in (
        (NATIVE_ACTORS[0], tenant, team, read_role),
        (NATIVE_ACTORS[1], foreign_tenant, foreign_team, foreign_role),
    ):
        assert (
            sql("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,), rows=True)[0][0] == 0
        )
        username, owner = "ruleflow_" + uuid4().hex[:10], str(uuid4())
        sql(
            "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "SELECT %s,%s,'规则只读验收',%s,password,'0','0' FROM sys_user WHERE user_id=1",
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
            (native, selected_tenant),
        )
        sql(
            "INSERT INTO "
            "orbit_business_user(tenant_id,id,user_id,team_id,display_name,invited,created_at) "
            "VALUES(%s,%s,%s,%s,'规则流程投手',0,UTC_TIMESTAMP(3))",
            (selected_tenant, owner, native, selected_team),
        )
        login = checked(fixture_login(client, cache, {"username": username, "password": password}))
        identity = {
            "headers": {"Authorization": "Bearer " + login["token"]},
            "owner": owner,
            "native": native,
        }
        info = client.get("/getInfo", headers=identity["headers"])
        assert_read_only_info(info)
        people.append(identity)
    own, foreign_user = people
    accounts = [fixture.account() for _ in range(2)]
    for index, account in enumerate(accounts):
        sql(
            "UPDATE orbit_ad_account SET owner_user_id=%s,currency=%s,timezone_id=%s "
            "WHERE tenant_id=%s AND id=%s",
            (
                own["owner"],
                ("USD", "EUR")[index],
                ("Asia/Shanghai", "America/Los_Angeles")[index],
                tenant,
                account,
            ),
        )
    sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    profile, _ = seed_metric_reference_profile(admin, database, tenant, index=967)
    cap = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers))
    scope = checked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={"mode": "IDS", "account_ids": accounts, "filter": None},
        ),
        201,
    )
    marker = "定义闭环-" + uuid4().hex[:12]
    body = definition_body(marker, own["owner"], team, scope["id"], profile["id"])
    base = "/api/v1/rules"

    def mutate(method, path, value, action, *, revision=None, key=None, status=200):
        cap = checked(
            client.get(base + "/capabilities", headers=headers, params={"action": action})
        )
        extra = {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": key or str(uuid4())}
        if revision is not None:
            extra["If-Match"] = '"' + str(revision) + '"'
        return checked(client.request(method, path, headers=headers | extra, json=value), status)

    created = mutate("POST", base, body, "CREATE", status=201)
    assert len(created) == 15 and parse_rule_response(Rule, created).model_dump() == created
    assert created["revision"] == 1 and created["state"] == "DRAFT"
    assert checked(client.get(base + "/" + created["id"], headers=headers)) == created
    page = checked(client.get(base, headers=headers, params={"q": marker, "page_size": "20"}))
    assert len(page) == 4 and parse_rule_response(RulePage, page).model_dump() == page
    assert page["items"] == [created]
    # 原GET q上限按Unicode字符计数，HTTP层与Store同时守住100/101边界。
    for unit in ("中", "😀"):
        empty_page = checked(client.get(base, headers=headers, params={"q": unit * 100}))
        assert parse_rule_response(RulePage, empty_page).model_dump() == empty_page
        rejected = checked(client.get(base, headers=headers, params={"q": unit * 101}), 422)
        assert len(rejected["field_errors"]) == 1
        assert rejected["field_errors"][0]["path"] == "/q"
    cases.append(RULES_DEFINITION_FLOW_CASES[0])

    other_body = definition_body(
        "其他归属-" + uuid4().hex[:10], root_owner, team, scope["id"], profile["id"]
    )
    other = mutate("POST", base, other_body, "CREATE", status=201)

    def metadata(ids, *, identity=headers, status=200):
        value = checked(
            client.get(
                base + "/display-metadata", headers=identity, params={"rule_ids": ",".join(ids)}
            ),
            status,
        )
        if status == 200:
            assert RuleDisplayMetadataPage.model_validate(value).model_dump() == value
            assert [row["rule_id"] for row in value["items"]] == ids
        else:
            assert "items" not in value
        return value

    def expected_item(rule):
        creator, when, owner_name, team_name, creator_name = sql(
            "SELECT h.created_by,h.created_at,u.display_name,t.name,c.display_name FROM "
            "orbit_rule_head h "
            "LEFT JOIN orbit_business_user u ON u.tenant_id=h.tenant_id AND u.id=h.owner_user_id "
            "LEFT JOIN orbit_business_team t ON t.tenant_id=h.tenant_id AND t.id=h.owner_team_id "
            "LEFT JOIN orbit_business_user c ON c.tenant_id=h.tenant_id AND c.user_id=h.created_by "
            "WHERE h.tenant_id=%s AND h.id=%s",
            (tenant, rule["id"]),
            rows=True,
        )[0]
        return {
            "rule_id": rule["id"],
            "revision": rule["revision"],
            "owner_user_name": owner_name,
            "owner_team_name": team_name,
            "created_by": creator,
            "created_by_name": creator_name,
            "created_at": created_at_text(when),
        }

    first = metadata([other["id"], created["id"]])
    assert first["items"] == [expected_item(other), expected_item(created)]
    original_metadata = first["items"][1]
    assert (
        original_metadata["created_by"] == 1
        and original_metadata["owner_user_name"] == "规则流程投手"
    )
    cases.append(RULES_DEFINITION_FLOW_CASES[1])

    edited_body = body | {
        "logic": "OR",
        "groups": [
            {
                "logic": "AND",
                "conditions": [{"metric": "spend", "operator": "GTE", "threshold": "12.5"}],
            },
            {
                "logic": "OR",
                "conditions": [{"metric": "clicks", "operator": "GT", "threshold": "0"}],
            },
        ],
        "cooldown_minutes": 0,
        "max_daily": 8,
    }
    key = str(uuid4())
    edited = mutate("PUT", base + "/" + created["id"], edited_body, "UPDATE", revision=1, key=key)
    assert (
        edited["revision"] == 2
        and edited["logic"] == "OR"
        and edited["groups"] == edited_body["groups"]
    )
    assert edited["cooldown_minutes"] == 0 and edited["max_daily"] == 8 and len(edited) == 15
    assert (
        mutate("PUT", base + "/" + created["id"], edited_body, "UPDATE", revision=1, key=key)
        == edited
    )
    assert checked(client.get(base + "/" + created["id"], headers=headers)) == edited
    after = metadata([created["id"]])["items"][0]
    assert after == expected_item(edited) and after == original_metadata | {"revision": 2}
    cases.append(RULES_DEFINITION_FLOW_CASES[2])

    rejected = mutate(
        "POST",
        base + "/" + edited["id"] + "/pause",
        {"reason": "草稿不能暂停"},
        "PAUSE",
        revision=2,
        status=409,
    )
    assert rejected["code"] == "RULE_STATE_CONFLICT"
    assert checked(client.get(base + "/" + edited["id"], headers=headers)) == edited
    archived = mutate(
        "POST",
        base + "/" + edited["id"] + "/archive",
        {"reason": "定义闭环归档验收"},
        "ARCHIVE",
        revision=2,
    )
    assert archived["revision"] == 3 and archived["state"] == "ARCHIVED" and len(archived) == 15
    assert checked(client.get(base + "/" + archived["id"], headers=headers)) == archived
    assert metadata([archived["id"]])["items"][0] == original_metadata | {"revision": 3}
    archive_page = checked(
        client.get(
            base, headers=headers, params={"q": marker, "status": "ARCHIVED", "page_size": "20"}
        )
    )
    assert len(archive_page) == 4 and archive_page["items"] == [archived]
    cases.append(RULES_DEFINITION_FLOW_CASES[3])

    read_only = metadata([archived["id"]], identity=own["headers"])
    assert read_only["items"] == [expected_item(archived)]
    assert checked(client.get(base + "/" + archived["id"], headers=own["headers"])) == archived
    denied = checked(
        client.get(base + "/capabilities", headers=own["headers"], params={"action": "CREATE"}), 403
    )
    assert denied["code"] == "PERMISSION_DENIED"
    cases.append(RULES_DEFINITION_FLOW_CASES[4])

    mixed = metadata([archived["id"], other["id"]], identity=own["headers"], status=404)
    assert mixed["code"] == "NOT_FOUND"
    alien = metadata([archived["id"]], identity=foreign_user["headers"], status=404)
    assert alien["code"] == "NOT_FOUND"
    cases.append(RULES_DEFINITION_FLOW_CASES[5])

    def all_rows():
        return tuple(sql("SELECT * FROM " + table + " ORDER BY 1,2", rows=True) for table in TABLES)

    before = all_rows()
    sql("DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s", (own["native"], read_role))
    try:
        denied = metadata([archived["id"]], identity=own["headers"], status=403)
        assert denied["code"] == "PERMISSION_DENIED"
    finally:
        sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (own["native"], read_role))
    invalid_requests = [
        ({"params": {"rule_ids": ""}}, 422, "FIELD_INVALID"),
        ({"params": {"rule_ids": archived["id"] + "," + archived["id"]}}, 422, "FIELD_INVALID"),
        (
            {"params": [("rule_ids", archived["id"]), ("rule_ids", other["id"])]},
            400,
            "INVALID_STRUCTURE",
        ),
        ({"params": {"rule_ids": archived["id"], "unknown": "x"}}, 400, "UNKNOWN_FIELD"),
        ({"params": {"rule_ids": archived["id"]}, "content": b"{}"}, 400, "INVALID_STRUCTURE"),
        (
            {
                "params": {"rule_ids": archived["id"]},
                "headers": headers | {"X-Target-Tenant": foreign_tenant},
            },
            403,
            "PERMISSION_DENIED",
        ),
    ]
    for options, status, code in invalid_requests:
        options = {"headers": headers} | options
        error = checked(client.request("GET", base + "/display-metadata", **options), status)
        assert error["code"] == code and "items" not in error
    cases.append(RULES_DEFINITION_FLOW_CASES[6])
    assert metadata([archived["id"], other["id"]])["items"] == [
        expected_item(archived),
        expected_item(other),
    ]
    assert all_rows() == before
    assert len(checked(client.get(base + "/" + archived["id"], headers=headers))) == 15
    cases.append(RULES_DEFINITION_FLOW_CASES[7])
    return {
        "account_count": 2,
        "created_by_native": 1,
        "rule_revisions": [1, 2, 3],
        "mixed_unreadable_whole_404": True,
        "real_foreign_tenant_404": True,
        "simulation_called": False,
        "enable_called": False,
        "draft_pause_positive": False,
        "enabled_pause_positive_tested": False,
    }
