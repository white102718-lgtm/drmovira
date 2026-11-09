"""隔离UUID库规则候选真实HTTP工具；账户为SQL_ONLY UNKNOWN样本，非平台授权。"""

import re
from uuid import uuid4

RULE_SCOPE_OPTIONS_CASES = (
    "pythonRuleScopeOptionsOriginalActionOnlyWithoutBorrowedMenus",
    "pythonRuleScopeOptionsOperatorFourSizesExactBusinessUuidAndHistoricalDisabled",
    "pythonRuleScopeOptionsVendorFourFieldsAliasUnknownAndUnavailableHistory",
    "pythonRuleScopeOptionsUserAndTeamExplicitManagementDualAccountIntersection",
    "pythonRuleScopeOptionsBothReferenceScopesAndLiteralPrefix",
    "pythonRuleScopeOptionsCursorSessionKindSizeFilterAndAllSourceClocks",
    "pythonRuleScopeOptionsImmediateActionRevocationAndMissingRuleHidden",
    "pythonRuleScopeOptionsStrictGetNoBodyDuplicateUnknownAndNoBusinessWrites",
    "pythonRuleScopeOptionsExistingUpdateHeadCasAndArchivedStateInvalidatesCursor",
    "pythonRuleScopeOptionsRealForeignTenantOwnerVendorAccountIsolation",
)


def guard_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or type(admin.port) is not int
        or admin.port != 13306
        or type(database) is not str
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("RULE_SCOPE_OPTIONS_ISOLATED_UUID_REQUIRED")


def run_rule_scope_options_checks(client, admin, headers, password, cache, database, cases):
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
    tenant, root_owner, root_team = sql(
        "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1", all=True
    )[0]
    capabilities = checked(client.get("/api/v1/roles/capabilities", headers=headers))
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": capabilities["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "规则筛选-" + uuid4().hex[:10],
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
    # 专档固定技术用户范围；独立mode不与其他人员fixture混用。
    assert (
        sql("SELECT COUNT(*) FROM sys_user WHERE user_id BETWEEN 990631 AND 990653", all=True)[0][0]
        == 0
    )
    marker = "规则候选" + uuid4().hex[:8]
    other_team = str(uuid4())
    sql(
        "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,%s)",
        (tenant, other_team, marker + "团队"),
    )
    identities, vendors, accounts = [], [], []
    for index, native in enumerate(range(990631, 990654)):
        owner, vendor_id, account_id = str(uuid4()), str(uuid4()), str(uuid4())
        team = root_team if index < 2 else other_team
        username = "scope_option_" + str(native) + "_" + uuid4().hex[:6]
        label = marker + ("%_!" if index == 1 else "人员") + str(index)
        sql(
            "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "SELECT %s,%s,%s,%s,password,'0','0' FROM sys_user WHERE user_id=1",
            (native, username, label, username + "@fixture.example.org"),
        )
        sql(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
            (native, str(uuid4())),
        )
        sql(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
            (native, tenant),
        )
        sql(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,"
            "display_name,invited,created_at) "
            "VALUES(%s,%s,%s,%s,%s,0,UTC_TIMESTAMP(3))",
            (tenant, owner, native, team, label),
        )
        identities.append(
            {"native": native, "id": owner, "team": team, "username": username, "name": label}
        )
        vendor_value = {
            "id": vendor_id,
            "kind": "VENDOR",
            "name": marker + "户商" + str(index),
            "source_key": "scope-options-" + uuid4().hex,
            "availability": "UNAVAILABLE" if index == 1 else "AVAILABLE",
            "owner_team_id": team,
            "data_owner_user_ids": [owner],
        }
        sql(
            "INSERT INTO orbit_reference_record(tenant_id,id,kind,source_key,name,availability,"
            "owner_team_id,value_json,revision,catalog_revision,updated_at) "
            "VALUES(%s,%s,'VENDOR',%s,%s,%s,%s,%s,1,1,UTC_TIMESTAMP(3))",
            (
                tenant,
                vendor_id,
                vendor_value["source_key"],
                vendor_value["name"],
                vendor_value["availability"],
                team,
                canonical(vendor_value),
            ),
        )
        sql(
            "INSERT INTO orbit_reference_owner(tenant_id,reference_id,user_id) VALUES(%s,%s,%s)",
            (tenant, vendor_id, owner),
        )
        if index == 1:
            sql(
                "INSERT INTO orbit_vendor_alias(tenant_id,vendor_id,alias,revision,"
                "updated_at,updated_by) "
                "VALUES(%s,%s,%s,2,UTC_TIMESTAMP(3),1)",
                (tenant, vendor_id, marker + "%_!"),
            )
        vendors.append(vendor_value | {"alias": marker + "%_!" if index == 1 else None})
        sql(
            "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
            "owner_team_id,vendor_id,currency,timezone_id,auth_status,account_status,value_json,"
            "details_json,bound_at,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'USD','UTC',"
            "'UNKNOWN','UNKNOWN','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (tenant, account_id, "00" + str(uuid4().int), marker, marker, owner, team, vendor_id),
        )
        accounts.append(account_id)
    user = identities[0]
    sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (user["native"], native_role))
    # 历史停用主体只作为filter候选，不可作为目标owner。
    sql(
        "UPDATE orbit_business_user SET enabled=0 WHERE tenant_id=%s AND id=%s",
        (tenant, identities[-1]["id"]),
    )
    for clock in ("orbit_directory_clock", "orbit_account_clock", "orbit_reference_clock"):
        sql("UPDATE " + clock + " SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    login = checked(
        fixture_login(client, cache, {"username": user["username"], "password": password})
    )
    user_headers = {"Authorization": "Bearer " + login["token"]}
    base = "/api/v1/rules/editor-scope-options"
    root_context = {"action": "CREATE", "owner_user_id": root_owner, "owner_team_id": root_team}
    user_context = {"action": "CREATE", "owner_user_id": user["id"], "owner_team_id": user["team"]}

    def get(kind, *, context=None, identity=None, status=200, **params):
        return checked(
            client.get(
                base,
                headers=identity or headers,
                params=(context or root_context) | {"kind": kind, "q": marker} | params,
            ),
            status,
        )

    def all_items(kind, *, size=20):
        result, cursor, seen = [], None, set()
        while True:
            page = get(kind, page_size=size, **({"cursor": cursor} if cursor else {}))
            assert set(page) == {"items", "next_cursor", "data_as_of", "scope_version"}
            assert len(page["items"]) <= size
            result.extend(page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                return result
            assert cursor not in seen
            seen.add(cursor)

    own = get("OPERATOR", context=user_context, identity=user_headers)
    assert [item["id"] for item in own["items"]] == [user["id"]]
    checked(client.get("/api/v1/accounts", headers=user_headers), 403)
    cases.append(RULE_SCOPE_OPTIONS_CASES[0])
    expected_operators = sorted(item["id"] for item in identities)
    for size in (20, 50, 100, 200):
        actual = all_items("OPERATOR", size=size)
        assert [item["id"] for item in actual] == expected_operators
        assert all(set(item) == {"id", "name", "team_id", "team_name", "active"} for item in actual)
        assert (
            next(item for item in actual if item["id"] == identities[-1]["id"])["active"] is False
        )
    exact = get("OPERATOR", q=user["id"].upper())
    assert [item["id"] for item in exact["items"]] == [user["id"]]
    cases.append(RULE_SCOPE_OPTIONS_CASES[1])
    for size in (20, 50, 100, 200):
        actual = all_items("VENDOR", size=size)
        assert [item["id"] for item in actual] == sorted(item["id"] for item in vendors)
        assert all(set(item) == {"id", "name", "alias", "availability"} for item in actual)
        assert next(item for item in actual if item["id"] == vendors[0]["id"])["alias"] is None
        history = next(item for item in actual if item["id"] == vendors[1]["id"])
        assert history["alias"] == marker + "%_!" and history["availability"] == "UNAVAILABLE"
    cases.append(RULE_SCOPE_OPTIONS_CASES[2])
    sql("UPDATE orbit_user_scope SET data_role='TEAM_ADMIN' WHERE user_id=%s", (user["native"],))
    assert [
        item["id"] for item in get("OPERATOR", context=user_context, identity=user_headers)["items"]
    ] == [user["id"]]
    sql(
        "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) "
        "VALUES(%s,%s,%s)",
        (tenant, user["native"], other_team),
    )
    actual = get("OPERATOR", context=user_context, identity=user_headers, page_size=200)["items"]
    assert {item["id"] for item in actual} == {user["id"]} | {item["id"] for item in identities[2:]}
    # 管理员caller不能令USER目标获得其同team peer账户。
    sql("UPDATE orbit_user_scope SET data_role='USER' WHERE user_id=%s", (user["native"],))
    assert [item["id"] for item in get("OPERATOR", context=user_context)["items"]] == [user["id"]]
    cases.append(RULE_SCOPE_OPTIONS_CASES[3])
    assert [
        item["id"] for item in get("VENDOR", context=user_context, identity=user_headers)["items"]
    ] == [vendors[0]["id"]]
    sql(
        "DELETE FROM orbit_reference_owner WHERE tenant_id=%s AND reference_id=%s AND user_id=%s",
        (tenant, vendors[0]["id"], user["id"]),
    )
    assert get("VENDOR", context=user_context, identity=user_headers)["items"] == []
    sql(
        "INSERT INTO orbit_reference_owner(tenant_id,reference_id,user_id) VALUES(%s,%s,%s)",
        (tenant, vendors[0]["id"], user["id"]),
    )
    assert [item["id"] for item in get("OPERATOR", q=marker + "%_!")["items"]] == [
        identities[1]["id"]
    ]
    assert [item["id"] for item in get("VENDOR", q=marker + "%_!")["items"]] == [vendors[1]["id"]]
    cases.append(RULE_SCOPE_OPTIONS_CASES[4])
    first = get("OPERATOR", page_size=20)
    cursor = first["next_cursor"]
    assert cursor
    for extra in ({"kind": "VENDOR"}, {"page_size": 50}, {"q": marker + "x"}):
        kind = extra.get("kind", "OPERATOR")
        get(
            kind,
            page_size=extra.get("page_size", 20),
            cursor=cursor,
            q=extra.get("q", marker),
            status=409,
        )
    for clock in ("orbit_reference_clock", "orbit_directory_clock", "orbit_account_clock"):
        fresh = get("OPERATOR", page_size=20)["next_cursor"]
        sql("UPDATE " + clock + " SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
        get("OPERATOR", page_size=20, cursor=fresh, status=409)
    get(
        "OPERATOR",
        context=user_context,
        identity=user_headers,
        page_size=20,
        cursor=cursor,
        status=409,
    )
    cases.append(RULE_SCOPE_OPTIONS_CASES[5])
    get("OPERATOR", action="UPDATE", rule_id=str(uuid4()), status=404)
    sql("DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s", (user["native"], native_role))
    try:
        get("OPERATOR", context=user_context, identity=user_headers, status=403)
        get("VENDOR", context=user_context, identity=user_headers, status=403)
    finally:
        sql(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
            (user["native"], native_role),
        )
    cases.append(RULE_SCOPE_OPTIONS_CASES[6])
    tables = (
        "orbit_rule_head",
        "orbit_rule_version",
        "orbit_rule_scope_manifest",
        "orbit_rule_editor_scope_snapshot",
    )
    before = [sql("SELECT COUNT(*) FROM " + table, all=True)[0][0] for table in tables]
    get("OWNER", status=422)
    get("OPERATOR", page_size=500, status=422)
    get("OPERATOR", operator_user_id=user["id"], status=400)
    checked(
        client.get(
            base,
            headers=headers,
            params=list((root_context | {"kind": "OPERATOR"}).items()) + [("kind", "VENDOR")],
        ),
        400,
    )
    checked(
        client.request(
            "GET", base, headers=headers, params=root_context | {"kind": "OPERATOR"}, content=b"{}"
        ),
        400,
    )
    after = [sql("SELECT COUNT(*) FROM " + table, all=True)[0][0] for table in tables]
    assert after == before
    cases.append(RULE_SCOPE_OPTIONS_CASES[7])
    # 现存规则只通过原API创建/修改/归档，不由SQL伪造head或revision。
    profile, _ = seed_metric_reference_profile(admin, database, tenant, index=631)
    scope_cap = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers))
    frozen = checked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=headers
            | {"X-CSRF-Token": scope_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={"mode": "IDS", "account_ids": accounts[:1], "filter": None},
        ),
        201,
    )
    rule_body = definition_body(
        marker + "现存规则", root_owner, root_team, frozen["id"], profile["id"]
    )

    def write_rule(method, path, payload, *, action, revision=None, status=200):
        cap = checked(
            client.get("/api/v1/rules/capabilities", headers=headers, params={"action": action})
        )
        extra = {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())}
        if revision is not None:
            extra["If-Match"] = '"' + str(revision) + '"'
        return checked(client.request(method, path, headers=headers | extra, json=payload), status)

    rule = write_rule("POST", "/api/v1/rules", rule_body, action="CREATE", status=201)
    assert rule["revision"] == 1 and rule["state"] == "DRAFT"
    update_context = root_context | {"action": "UPDATE", "rule_id": rule["id"]}
    first = get("OPERATOR", context=update_context, page_size=20)
    assert len(first["items"]) == 20 and first["next_cursor"]
    next_page = get("OPERATOR", context=update_context, page_size=20, cursor=first["next_cursor"])
    assert len(next_page["items"]) == 3
    assert [item["id"] for item in first["items"] + next_page["items"]] == expected_operators
    rule = write_rule(
        "PUT",
        "/api/v1/rules/" + rule["id"],
        rule_body | {"name": rule_body["name"] + "改版"},
        action="UPDATE",
        revision=1,
    )
    assert rule["revision"] == 2 and rule["state"] == "DRAFT"
    get("OPERATOR", context=update_context, page_size=20, cursor=first["next_cursor"], status=409)
    current = get("OPERATOR", context=update_context, page_size=20)
    assert [item["id"] for item in current["items"]] == [item["id"] for item in first["items"]]
    assert current["next_cursor"] and current["next_cursor"] != first["next_cursor"]
    archived = write_rule(
        "POST",
        "/api/v1/rules/" + rule["id"] + "/archive",
        {"reason": "验证历史候选失效"},
        action="ARCHIVE",
        revision=2,
    )
    assert archived["state"] == "ARCHIVED" and archived["revision"] == 3
    get("OPERATOR", context=update_context, page_size=20, cursor=current["next_cursor"], status=409)
    get("OPERATOR", context=update_context, page_size=20, status=409)
    cases.append(RULE_SCOPE_OPTIONS_CASES[8])
    # 完整存在的外租户身份/资料/账户组合。不得用随机不存在对象代替此负例。
    foreign_tenant, foreign_team, foreign_owner, foreign_vendor, foreign_account = (
        str(uuid4()) for _ in range(5)
    )
    foreign_native = 990654
    assert (
        sql("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (foreign_native,), all=True)[0][0]
        == 0
    )
    sql("INSERT INTO orbit_tenant(id,name) VALUES(%s,%s)", (foreign_tenant, marker + "外租户"))
    sql(
        "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,%s)",
        (foreign_tenant, foreign_team, marker + "外团队"),
    )
    foreign_label = marker + "外域真实姓名"
    foreign_alias = marker + "外域代称"
    sql(
        "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
        "SELECT %s,%s,%s,%s,password,'0','0' FROM sys_user WHERE user_id=1",
        (
            foreign_native,
            "scope_foreign_" + uuid4().hex[:12],
            foreign_label,
            "scope-foreign-" + uuid4().hex[:12] + "@fixture.example.org",
        ),
    )
    sql(
        "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
        "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
        (foreign_native, str(uuid4())),
    )
    sql(
        "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
        (foreign_native, foreign_tenant),
    )
    sql(
        "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,"
        "display_name,invited,created_at) "
        "VALUES(%s,%s,%s,%s,%s,0,UTC_TIMESTAMP(3))",
        (foreign_tenant, foreign_owner, foreign_native, foreign_team, foreign_label),
    )
    foreign_value = {
        "id": foreign_vendor,
        "kind": "VENDOR",
        "source_key": "foreign-" + uuid4().hex,
        "name": marker + "外域户商",
        "availability": "AVAILABLE",
        "owner_team_id": foreign_team,
        "data_owner_user_ids": [foreign_owner],
    }
    sql(
        "INSERT INTO orbit_reference_record(tenant_id,id,kind,source_key,name,availability,"
        "owner_team_id,value_json,revision,catalog_revision,updated_at) "
        "VALUES(%s,%s,'VENDOR',%s,%s,'AVAILABLE',%s,%s,1,1,UTC_TIMESTAMP(3))",
        (
            foreign_tenant,
            foreign_vendor,
            foreign_value["source_key"],
            foreign_value["name"],
            foreign_team,
            canonical(foreign_value),
        ),
    )
    sql(
        "INSERT INTO orbit_reference_owner(tenant_id,reference_id,user_id) VALUES(%s,%s,%s)",
        (foreign_tenant, foreign_vendor, foreign_owner),
    )
    sql(
        "INSERT INTO orbit_vendor_alias(tenant_id,vendor_id,alias,revision,updated_at,updated_by) "
        "VALUES(%s,%s,%s,2,UTC_TIMESTAMP(3),1)",
        (foreign_tenant, foreign_vendor, foreign_alias),
    )
    sql(
        "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
        "owner_team_id,vendor_id,currency,timezone_id,auth_status,account_status,value_json,"
        "details_json,bound_at,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'USD','UTC',"
        "'UNKNOWN','UNKNOWN','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
        (
            foreign_tenant,
            foreign_account,
            "00" + str(uuid4().int),
            foreign_label,
            foreign_label,
            foreign_owner,
            foreign_team,
            foreign_vendor,
        ),
    )
    assert (
        sql(
            "SELECT COUNT(*) FROM orbit_ad_account a JOIN orbit_business_user b "
            "ON b.tenant_id=a.tenant_id AND b.id=a.owner_user_id JOIN orbit_reference_record r "
            "ON r.tenant_id=a.tenant_id AND r.id=a.vendor_id WHERE a.tenant_id=%s AND a.id=%s",
            (foreign_tenant, foreign_account),
            all=True,
        )[0][0]
        == 1
    )
    for kind, foreign_id in (("OPERATOR", foreign_owner), ("VENDOR", foreign_vendor)):
        for identity, current_context in ((headers, root_context), (user_headers, user_context)):
            assert (
                get(kind, identity=identity, context=current_context, q=foreign_id)["items"] == []
            )
            assert (
                get(kind, identity=identity, context=current_context, q=marker + "外域")["items"]
                == []
            )
    foreign_context = root_context | {"owner_user_id": foreign_owner, "owner_team_id": foreign_team}
    rejected = get("OPERATOR", context=foreign_context, status=422)
    assert rejected["code"] == "OWNER_UNAVAILABLE"
    rejected = get("VENDOR", context=foreign_context, identity=user_headers, status=403)
    assert rejected["code"] == "OWNERSHIP_DENIED"
    # 原单对象/IDS路径要求404；候选集合q空页不伪造404。
    checked(
        client.post(
            "/api/v1/rules/editor-scope-snapshots",
            headers=headers
            | {
                "X-CSRF-Token": scope_cap["csrf_token"],
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "action": "CREATE",
                "rule_id": None,
                "ownership": {"owner_user_id": root_owner, "owner_team_id": root_team},
                "selection": {"mode": "IDS", "account_ids": [foreign_account], "filter": None},
            },
        ),
        404,
    )
    cases.append(RULE_SCOPE_OPTIONS_CASES[9])
