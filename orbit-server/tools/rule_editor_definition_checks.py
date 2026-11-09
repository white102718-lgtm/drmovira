"""编辑定义真实只读专项；仅声明由root在13306本轮UUID库串行运行。

ENABLED/坏来源版本是明确SQL技术样本，完整事件→版本→head/outbox，
保留全部FK/immutable trigger；不证明模拟、正式启用或平台执行资格。
"""

import re
from uuid import uuid4

RULE_EDITOR_DEFINITION_CASES = [
    "pythonRuleEditDefinitionEditOnlyOriginalFifteenAndStoredScopeFour",
    "pythonRuleEditDefinitionManagedCollaboratorWithoutPrivateScopeOrOtherActions",
    "pythonRuleEditDefinitionFourStatesAndUnavailableProfileRemainReadable",
    "pythonRuleEditDefinitionCurrentOwnerNotHistoricalManifestOwner",
    "pythonRuleEditDefinitionCurrentActionRevokedAndForeignHidden",
    "pythonRuleEditDefinitionTechnicalBrokenPayloadOrSourceExact503",
    "pythonRuleEditDefinitionStrictGetAndAllPersistentRowsUnchanged",
]


def guard_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or type(admin.port) is not int
        or admin.port != 13306
        or type(database) is not str
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("RULE_EDIT_DEFINITION_ISOLATED_UUID_REQUIRED")


def has_rule_page(nodes):
    if type(nodes) is not list:
        raise AssertionError("RULE_ROUTERS_LIST_REQUIRED")
    for node in nodes:
        if type(node) is not dict:
            raise AssertionError("RULE_ROUTER_OBJECT_REQUIRED")
        if node.get("component") == "orbit/rules/index":
            return True
        if "children" in node and has_rule_page(node["children"]):
            return True
    return False


def run_rule_editor_definition_checks(client, admin, headers, password, cache, database, cases):
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
    from orbit_api.rule_contract import Rule, parse_rule_response
    from orbit_api.rule_store import digest

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
    role_cap = checked(client.get("/api/v1/roles/capabilities", headers=headers))
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": role_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "定义编辑-" + uuid4().hex[:10],
                "menu_codes": ["rules"],
                "permission_codes": ["rules.edit"],
            },
        ),
        201,
    )
    native_role = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
        all=True,
    )[0][0]
    people = []
    for native, data_role in ((990614, "USER"), (990615, "TEAM_ADMIN")):
        assert sql("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,), all=True)[0][0] == 0
        owner, username = str(uuid4()), "rule_def_" + uuid4().hex[:10]
        sql(
            "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "SELECT %s,%s,'规则编辑定义',%s,password,'0','0' FROM sys_user WHERE user_id=1",
            (native, username, username + "@fixture.example.org"),
        )
        sql(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
            (native, str(uuid4())),
        )
        sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, native_role))
        sql(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,%s)",
            (native, tenant, data_role),
        )
        sql(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,display_name,"
            "invited,created_at) VALUES(%s,%s,%s,%s,'规则编辑定义',0,UTC_TIMESTAMP(3))",
            (tenant, owner, native, team),
        )
        if data_role == "TEAM_ADMIN":
            sql(
                "INSERT INTO orbit_business_team_manager(tenant_id,team_id,"
                "manager_user_id,enabled) "
                "VALUES(%s,%s,%s,1)",
                (tenant, team, native),
            )
        login = checked(fixture_login(client, cache, {"username": username, "password": password}))
        people.append({"owner": owner, "headers": {"Authorization": "Bearer " + login["token"]}})
    editor, collaborator = people
    sql("UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    profile, _ = seed_metric_reference_profile(admin, database, tenant, index=740)

    def cap(action):
        return checked(
            client.get("/api/v1/rules/capabilities", headers=headers, params={"action": action})
        )["csrf_token"]

    def seed_rule(owner):
        account = str(uuid4())
        sql(
            "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
            "owner_team_id,currency,timezone_id,auth_status,account_status,value_json,details_json,"
            "bound_at,created_at) VALUES(%s,%s,%s,'定义账户','定义账户',%s,%s,'USD',"
            "'Asia/Shanghai','UNKNOWN','UNKNOWN','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (tenant, account, str(10**25 + uuid4().int % 10**25), owner, team),
        )
        sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
        source_cap = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers))
        source = checked(
            client.post(
                "/api/v1/scope-snapshots",
                headers=headers
                | {"X-CSRF-Token": source_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
                json={"mode": "IDS", "account_ids": [account], "filter": None},
            ),
            201,
        )
        body = definition_body(
            "定义只读-" + uuid4().hex[:12], owner, team, source["id"], profile["id"]
        )
        rule = checked(
            client.post(
                "/api/v1/rules",
                headers=headers | {"X-CSRF-Token": cap("CREATE"), "Idempotency-Key": str(uuid4())},
                json=body,
            ),
            201,
        )
        return rule, source

    own, source = seed_rule(editor["owner"])
    foreign, _ = seed_rule(root_owner)
    moved, _ = seed_rule(editor["owner"])
    bad_rules = [seed_rule(editor["owner"])[0] for _ in range(3)]

    def snapshot():
        # 全部原规则表原列/值逐行对账，含clock/所有状态；不只COUNT忽略UPDATE。
        return tuple(sql("SELECT * FROM " + table + " ORDER BY 1,2", all=True) for table in TABLES)

    def get(rule, *, identity=None, status=200):
        response = client.get(
            "/api/v1/rules/" + rule["id"] + "/edit-definition",
            headers=identity or editor["headers"],
        )
        value = checked(response, status)
        if status == 200:
            assert set(value) == {"rule", "stored_scope"}
            assert len(value["rule"]) == 15
            assert parse_rule_response(Rule, value["rule"]).model_dump() == value["rule"]
            assert value["rule"] == rule
            count, original_id = sql(
                "SELECT m.member_count,m.source_snapshot_id FROM orbit_rule_head h "
                "JOIN orbit_rule_scope_manifest m ON m.tenant_id=h.tenant_id AND m.rule_id=h.id "
                "AND m.id=h.manifest_id WHERE h.tenant_id=%s AND h.id=%s AND m.sealed=1",
                (tenant, rule["id"]),
                all=True,
            )[0]
            assert value["stored_scope"] == {
                "id": original_id,
                "count": count,
                **rule["ownership"],
            }
            assert original_id == rule["scope_snapshot_id"] and 1 <= count <= 50000
        return value

    before = snapshot()
    get(own)
    for path in (
        "/api/v1/rules/" + own["id"],
        "/api/v1/accounts/extended",
        "/api/v1/users/capabilities",
        "/api/v1/metric-profiles",
    ):
        checked(client.get(path, headers=editor["headers"]), 403)
    if sql("SELECT COUNT(*) FROM sys_menu WHERE menu_id=31047", all=True)[0][0] == 1:
        routers = client.get("/getRouters", headers=editor["headers"])
        assert routers.status_code == 200 and routers.json()["code"] == 200
        assert has_rule_page(routers.json()["data"])
        info = client.get("/getInfo", headers=editor["headers"])
        assert info.status_code == 200 and info.json()["code"] == 200
        permissions = info.json()["permissions"]
        assert type(permissions) is list and "rules.edit" in permissions
        assert "rules.read" not in permissions and "*:*:*" not in permissions
    assert snapshot() == before
    cases.append(RULE_EDITOR_DEFINITION_CASES[0])

    before = snapshot()
    get(own, identity=collaborator["headers"])
    checked(
        client.get(
            "/api/v1/scope-snapshots/" + source["id"] + "/members",
            headers=collaborator["headers"],
        ),
        403,
    )
    assert snapshot() == before
    cases.append(RULE_EDITOR_DEFINITION_CASES[1])

    def publish_technical(rule, *, state=None, owner=None, corruption=None):
        """本轮SQL技术版本，不调用/伪造正式enable或模拟资格，无关闭护栏。"""
        event, request = str(uuid4()), str(uuid4())
        state = state or rule["state"]
        action = "ENABLE" if state == "ENABLED" else "UPDATE"
        body = {
            key: value
            for key, value in rule.items()
            if key not in {"id", "revision", "state", "next_run_at"}
        }
        if owner:
            body["ownership"] = {"owner_user_id": owner, "owner_team_id": team}
        if corruption == "source":
            body["scope_snapshot_id"] = str(uuid4())
        if corruption == "nullable_number":
            body["cooldown_minutes"] = None
        hash_value = "0" * 64 if corruption == "hash" else digest(body)
        admin.begin()
        try:
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT revision FROM orbit_rule_clock WHERE tenant_id=%s FOR UPDATE", (tenant,)
                )
                cursor.fetchone()
                cursor.execute(
                    "INSERT INTO orbit_rule_event(tenant_id,id,rule_id,revision,actor_id,"
                    "request_id,"
                    "action,reason,details_json) VALUES(%s,%s,%s,%s,1,%s,%s,NULL,%s)",
                    (
                        tenant,
                        event,
                        rule["id"],
                        rule["revision"] + 1,
                        request,
                        action,
                        canonical(
                            {
                                "source": "ISOLATED_SQL_ONLY_NOT_ENABLE_AUTHORITY",
                                "kind": corruption or state,
                            }
                        ),
                    ),
                )
                cursor.execute(
                    "INSERT INTO orbit_rule_version(tenant_id,rule_id,revision,payload_json,"
                    "payload_hash,name,owner_user_id,owner_team_id,target_level,state,manifest_id,"
                    "metric_profile_id,metric_profile_version,metric_profile_hash,profile_proof_hash,"
                    "event_id,created_at) SELECT tenant_id,rule_id,revision+1,%s,%s,name,%s,"
                    "owner_team_id,target_level,%s,manifest_id,metric_profile_id,metric_profile_version,"
                    "metric_profile_hash,profile_proof_hash,%s,UTC_TIMESTAMP(3) "
                    "FROM orbit_rule_version "
                    "WHERE tenant_id=%s AND rule_id=%s AND revision=%s",
                    (
                        canonical(body),
                        hash_value,
                        owner or rule["ownership"]["owner_user_id"],
                        state,
                        event,
                        tenant,
                        rule["id"],
                        rule["revision"],
                    ),
                )
                assert cursor.rowcount == 1
                cursor.execute(
                    "UPDATE orbit_rule_head SET revision=revision+1,owner_user_id=%s,state=%s,"
                    "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=%s AND id=%s AND revision=%s",
                    (
                        owner or rule["ownership"]["owner_user_id"],
                        state,
                        tenant,
                        rule["id"],
                        rule["revision"],
                    ),
                )
                assert cursor.rowcount == 1
                cursor.execute(
                    "INSERT INTO orbit_rule_outbox(tenant_id,event_id) VALUES(%s,%s)",
                    (tenant, event),
                )
                cursor.execute(
                    "UPDATE orbit_rule_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
                )
            admin.commit()
        except BaseException:
            admin.rollback()
            raise
        return body | {
            "id": rule["id"],
            "revision": rule["revision"] + 1,
            "state": state,
            "next_run_at": None,
        }

    current = publish_technical(own, state="ENABLED")
    sql(
        "UPDATE orbit_metric_profile_head SET state='DISABLED' WHERE tenant_id=%s AND id=%s",
        (tenant, profile["id"]),
    )
    try:
        before = snapshot()
        get(current)
        assert snapshot() == before
    finally:
        sql(
            "UPDATE orbit_metric_profile_head SET state='ENABLED' WHERE tenant_id=%s AND id=%s",
            (tenant, profile["id"]),
        )
    for operation, expected_state in (("pause", "PAUSED"), ("archive", "ARCHIVED")):
        current = checked(
            client.post(
                "/api/v1/rules/" + current["id"] + "/" + operation,
                headers=headers
                | {
                    "X-CSRF-Token": cap(operation.upper()),
                    "Idempotency-Key": str(uuid4()),
                    "If-Match": '"' + str(current["revision"]) + '"',
                },
                json={"reason": "只读定义技术状态样本后原动作"},
            )
        )
        assert current["state"] == expected_state
        before = snapshot()
        get(current)
        assert snapshot() == before
    cases.append(RULE_EDITOR_DEFINITION_CASES[2])

    moved = publish_technical(moved, owner=root_owner)
    before = snapshot()
    get(moved, identity=collaborator["headers"])
    historical = sql(
        "SELECT m.owner_user_id FROM orbit_rule_scope_manifest m JOIN orbit_rule_head h "
        "ON h.tenant_id=m.tenant_id AND h.manifest_id=m.id WHERE h.tenant_id=%s AND h.id=%s",
        (tenant, moved["id"]),
        all=True,
    )[0][0]
    assert historical == editor["owner"] and historical != moved["ownership"]["owner_user_id"]
    assert snapshot() == before
    cases.append(RULE_EDITOR_DEFINITION_CASES[3])

    before = snapshot()
    get(foreign, status=404)
    checked(
        client.get("/api/v1/rules/" + str(uuid4()) + "/edit-definition", headers=editor["headers"]),
        404,
    )
    sql(
        "DELETE FROM orbit_business_role_action WHERE tenant_id=%s AND role_id=%s "
        "AND permission_code='rules.edit'",
        (tenant, role["id"]),
    )
    try:
        get(current, status=403)
    finally:
        sql(
            "INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) "
            "VALUES(%s,%s,'rules.edit')",
            (tenant, role["id"]),
        )
    assert snapshot() == before
    cases.append(RULE_EDITOR_DEFINITION_CASES[4])

    for rule, corruption in zip(bad_rules, ("source", "hash", "nullable_number"), strict=True):
        bad = publish_technical(rule, corruption=corruption)
        before = snapshot()
        error = get(bad, status=503)
        assert error["code"] == "RULE_DEFINITION_UNAVAILABLE"
        assert snapshot() == before
    cases.append(RULE_EDITOR_DEFINITION_CASES[5])

    before = snapshot()
    path = "/api/v1/rules/" + current["id"] + "/edit-definition"
    for parameters in ({"unknown": "1"}, [("q", "1"), ("q", "2")]):
        checked(client.get(path, headers=editor["headers"], params=parameters), 400)
    checked(client.request("GET", path, headers=editor["headers"], content=b"{}"), 400)
    checked(client.get(path, headers=editor["headers"] | {"X-Target-Tenant": str(uuid4())}), 403)
    checked(client.get("/api/v1/rules/not-a-uuid/edit-definition", headers=editor["headers"]), 422)
    get(current)
    assert snapshot() == before
    cases.append(RULE_EDITOR_DEFINITION_CASES[6])
    return {
        "definition_cases": len(RULE_EDITOR_DEFINITION_CASES),
        "platform_writes": 0,
        "readonly_full_rule_tables_verified": True,
        "enabled_sample": "SQL_TECHNICAL_NOT_ENABLE_AUTHORITY",
        "full_current_member_scope_verified": False,
    }
