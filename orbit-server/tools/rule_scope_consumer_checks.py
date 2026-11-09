"""061新RULE来源实际消费专项；只定义由root串队，不启动服务/平台。"""

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

RULE_SCOPE_CONSUMER_CASES = [
    "pythonRuleScopeConsumerCreateOriginalFifteenAndExactRuleManifest",
    "pythonRuleScopeConsumerUpdateExactTargetCurrentCasAndFrozenSource",
    "pythonRuleScopeConsumerFirstUpdateWrongTargetOrOldRevisionNoPartialWrites",
    "pythonRuleScopeConsumerCreateCannotMoveAndOutboxRollbackReleasesFirstBinding",
    "pythonRuleScopeConsumerConcurrentDifferentRulesOneCompleteFirstBinding",
    "pythonRuleScopeConsumerOldSuccessfulIntentCurrentAuthorizationBeforeSource",
    "pythonRuleScopeConsumerCollaboratorPublicManifestWithoutPrivateScopeRead",
    "pythonRuleScopeConsumerTechnicalCompleteAccountCloneUuidCollision409",
]


def guard_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or type(admin.port) is not int
        or admin.port != 13306
        or type(database) is not str
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("RULE_CONSUMER_ISOLATED_UUID_REQUIRED")


def run_rule_scope_consumer_checks(client, admin, headers, password, cache, database, cases):
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
                "name": "规则消费-" + uuid4().hex[:10],
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
    identities = []
    for native, data_role in ((990612, "USER"), (990613, "TEAM_ADMIN")):
        assert sql("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,), all=True)[0][0] == 0
        owner, username = str(uuid4()), "rule_cons_" + uuid4().hex[:12]
        sql(
            "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "SELECT %s,%s,'规则真实消费',%s,password,'0','0' FROM sys_user WHERE user_id=1",
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
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,"
            "display_name,invited,created_at) "
            "VALUES(%s,%s,%s,%s,'规则真实消费',0,UTC_TIMESTAMP(3))",
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
        identities.append(
            {"owner": owner, "headers": {"Authorization": "Bearer " + login["token"]}}
        )
    creator, collaborator = identities
    owner = creator["owner"]
    sql("UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    ids = sorted(str(uuid4()) for _ in range(4))
    for index, account in enumerate(ids):
        label = "规则消费账户-" + uuid4().hex[:10]
        sql(
            "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
            "owner_team_id,currency,timezone_id,auth_status,account_status,value_json,details_json,"
            "bound_at,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'Asia/Shanghai','UNKNOWN',"
            "'UNKNOWN','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (
                tenant,
                account,
                "00" + str(10**24 + uuid4().int % 10**24),
                label,
                label,
                owner,
                team,
                "USD" if index % 2 == 0 else "EUR",
            ),
        )
    sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    profile, _ = seed_metric_reference_profile(admin, database, tenant, index=710)
    scope_base = "/api/v1/rules/editor-scope-snapshots"
    rule_base = "/api/v1/rules"

    def counts():
        return tuple(sql("SELECT COUNT(*) FROM " + table, all=True)[0][0] for table in TABLES)

    def revision():
        return sql("SELECT revision FROM orbit_rule_clock WHERE tenant_id=%s", (tenant,), all=True)[
            0
        ][0]

    def cap(identity, action):
        return checked(
            client.get(rule_base + "/capabilities", headers=identity, params={"action": action})
        )["csrf_token"]

    def scope(*, rule=None, selected=None):
        action = "UPDATE" if rule else "CREATE"
        extra = {"If-Match": '"' + str(rule["revision"]) + '"'} if rule else {}
        return checked(
            client.post(
                scope_base,
                headers=creator["headers"]
                | extra
                | {
                    "X-CSRF-Token": cap(creator["headers"], action),
                    "Idempotency-Key": str(uuid4()),
                },
                json={
                    "action": action,
                    "rule_id": rule["id"] if rule else None,
                    "ownership": {"owner_user_id": owner, "owner_team_id": team},
                    "selection": {
                        "mode": "IDS",
                        "account_ids": selected or ids[:2],
                        "filter": None,
                    },
                },
            ),
            201,
        )

    def body(snapshot, label):
        return definition_body(
            label + "-" + uuid4().hex[:10], owner, team, snapshot["id"], profile["id"]
        )

    def mutate(value, *, rule=None, key=None, identity=None, status=None):
        identity = identity or creator["headers"]
        action = "UPDATE" if rule else "CREATE"
        request_headers = identity | {
            "X-CSRF-Token": cap(identity, action),
            "Idempotency-Key": key or str(uuid4()),
        }
        if rule:
            request_headers |= {"If-Match": '"' + str(rule["revision"]) + '"'}
        response = (
            client.put(rule_base + "/" + rule["id"], headers=request_headers, json=value)
            if rule
            else client.post(rule_base, headers=request_headers, json=value)
        )
        return checked(response, status if status is not None else (200 if rule else 201))

    def verify(rule, snapshot, expected_body):
        assert parse_rule_response(Rule, rule).model_dump() == rule and len(rule) == 15
        assert "source_kind" not in rule
        assert checked(client.get(rule_base + "/" + rule["id"], headers=headers)) == rule
        header = sql(
            "SELECT m.source_kind,m.source_snapshot_id,m.rule_id,m.sealed,m.member_count,"
            "m.source_snapshot_hash,m.member_ids_hash,v.payload_json FROM orbit_rule_head h "
            "JOIN orbit_rule_scope_manifest m ON m.tenant_id=h.tenant_id AND m.id=h.manifest_id "
            "JOIN orbit_rule_version v ON v.tenant_id=h.tenant_id AND "
            "v.rule_id=h.id AND v.revision=h.revision "
            "WHERE h.tenant_id=%s AND h.id=%s",
            (tenant, rule["id"]),
            all=True,
        )
        assert len(header) == 1
        row = header[0]
        assert row[:6] == (
            "RULE",
            snapshot["id"],
            rule["id"],
            1,
            snapshot["count"],
            snapshot["hash"],
        )
        payload = json.loads(row[7]) if isinstance(row[7], str) else row[7]
        assert payload == expected_body
        selected = sql(
            "SELECT account_id FROM orbit_rule_scope_member WHERE tenant_id=%s "
            "AND manifest_id=(SELECT manifest_id FROM orbit_rule_head WHERE "
            "tenant_id=%s AND id=%s) "
            "ORDER BY account_id",
            (tenant, tenant, rule["id"]),
            all=True,
        )
        actual = [r[0] for r in selected]
        assert len(actual) == snapshot["count"]
        assert hashlib.sha256(canonical(actual).encode()).hexdigest() == row[6]
        assert (
            sql(
                "SELECT COUNT(*) FROM orbit_rule_scope_manifest WHERE tenant_id=%s "
                "AND source_kind='RULE' AND rule_source_snapshot_id=%s AND rule_id<>%s",
                (tenant, snapshot["id"], rule["id"]),
                all=True,
            )[0][0]
            == 0
        )

    created_scope = scope()
    original_body = body(created_scope, "新RULE消费")
    original_key = str(uuid4())
    original = mutate(original_body, key=original_key)
    verify(original, created_scope, original_body)
    cases.append(RULE_SCOPE_CONSUMER_CASES[0])
    update_scope = scope(rule=original, selected=ids[1:])
    update_body = original_body | {
        "scope_snapshot_id": update_scope["id"],
        "name": original_body["name"] + "-更新",
    }
    current = mutate(update_body, rule=original)
    assert current["revision"] == 2
    verify(current, update_scope, update_body)
    assert (
        sql(
            "SELECT rule_revision FROM orbit_rule_editor_scope_snapshot WHERE "
            "tenant_id=%s AND id=%s",
            (tenant, update_scope["id"]),
            all=True,
        )[0][0]
        == 1
    )
    cases.append(RULE_SCOPE_CONSUMER_CASES[1])
    second_scope = scope()
    second_body = body(second_scope, "不同目标")
    second = mutate(second_body)
    wrong_target = scope(rule=current)
    baseline, clock_before = counts(), revision()
    error = mutate(second_body | {"scope_snapshot_id": wrong_target["id"]}, rule=second, status=409)
    assert error["code"] == "RULE_ACCOUNT_SCOPE_CHANGED"
    assert counts() == baseline and revision() == clock_before
    stale = scope(rule=current)
    advanced_body = update_body | {"name": update_body["name"] + "-继续"}
    advanced = mutate(advanced_body, rule=current)
    baseline, clock_before = counts(), revision()
    error = mutate(advanced_body | {"scope_snapshot_id": stale["id"]}, rule=advanced, status=409)
    assert error["code"] == "RULE_ACCOUNT_SCOPE_CHANGED"
    assert counts() == baseline and revision() == clock_before
    current = advanced
    cases.append(RULE_SCOPE_CONSUMER_CASES[2])
    baseline, clock_before = counts(), revision()
    error = mutate(original_body | {"name": original_body["name"] + "-挪用"}, status=409)
    assert error["code"] == "RULE_SCOPE_ALREADY_BOUND"
    assert counts() == baseline and revision() == clock_before
    rollback_scope = scope()
    rollback_body = body(rollback_scope, "回滚可重试")
    rollback_key = str(uuid4())
    trigger = "rule_consumer_fail_" + uuid4().hex[:12]
    baseline, clock_before = counts(), revision()
    try:
        sql(
            "CREATE TRIGGER " + trigger + " BEFORE INSERT ON orbit_rule_outbox FOR EACH ROW "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='ISOLATED_RULE_CONSUMER_OUTBOX_1644'"
        )
        mutate(rollback_body, key=rollback_key, status=503)
        assert counts() == baseline and revision() == clock_before
        assert (
            sql(
                "SELECT COUNT(*) FROM orbit_rule_scope_manifest WHERE tenant_id=%s "
                "AND source_kind='RULE' AND rule_source_snapshot_id=%s",
                (tenant, rollback_scope["id"]),
                all=True,
            )[0][0]
            == 0
        )
    finally:
        sql("DROP TRIGGER IF EXISTS " + trigger)
    recovered = mutate(rollback_body, key=rollback_key)
    verify(recovered, rollback_scope, rollback_body)
    cases.append(RULE_SCOPE_CONSUMER_CASES[3])
    racing_scope = scope()
    racing_bodies = [body(racing_scope, "并发首领A"), body(racing_scope, "并发首领B")]
    racing_csrf = cap(creator["headers"], "CREATE")
    racing_keys = [str(uuid4()), str(uuid4())]
    barrier = Barrier(2)
    baseline, clock_before = counts(), revision()

    def race(index):
        barrier.wait(timeout=5)
        return client.post(
            rule_base,
            headers=creator["headers"]
            | {"X-CSRF-Token": racing_csrf, "Idempotency-Key": racing_keys[index]},
            json=racing_bodies[index],
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(race, (0, 1)))
    assert sorted(response.status_code for response in responses) == [201, 409]
    winner_index = next(i for i, response in enumerate(responses) if response.status_code == 201)
    winner = checked(responses[winner_index], 201)
    loser = checked(responses[1 - winner_index], 409)
    assert loser["code"] == "RULE_SCOPE_ALREADY_BOUND"
    verify(winner, racing_scope, racing_bodies[winner_index])
    assert [after - before for before, after in zip(baseline, counts(), strict=True)] == [
        0,
        1,
        2,
        1,
        1,
        1,
        1,
        1,
    ]
    assert revision() == clock_before + 1
    cases.append(RULE_SCOPE_CONSUMER_CASES[4])
    baseline, clock_before = counts(), revision()
    sql(
        "UPDATE orbit_metric_profile_head SET state='DISABLED' WHERE tenant_id=%s AND id=%s",
        (tenant, profile["id"]),
    )
    try:
        assert mutate(original_body, key=original_key) == original
        error = mutate(original_body | {"name": "不同正文"}, key=original_key, status=409)
        assert error["code"] == "IDEMPOTENCY_CONFLICT"
    finally:
        sql(
            "UPDATE orbit_metric_profile_head SET state='ENABLED' WHERE tenant_id=%s AND id=%s",
            (tenant, profile["id"]),
        )
    assert counts() == baseline and revision() == clock_before
    sql(
        "DELETE FROM orbit_business_role_action WHERE tenant_id=%s AND role_id=%s "
        "AND permission_code='rules.create'",
        (tenant, role["id"]),
    )
    try:
        checked(
            client.post(
                rule_base,
                headers=creator["headers"]
                | {"X-CSRF-Token": racing_csrf, "Idempotency-Key": original_key},
                json=original_body,
            ),
            403,
        )
    finally:
        sql(
            "INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) "
            "VALUES(%s,%s,'rules.create')",
            (tenant, role["id"]),
        )
    cases.append(RULE_SCOPE_CONSUMER_CASES[5])
    for identity in (creator["headers"], collaborator["headers"]):
        checked(client.get("/api/v1/scope-snapshots/capabilities", headers=identity), 403)
        checked(client.get("/api/v1/users/capabilities", headers=identity), 403)
    checked(
        client.get(
            scope_base + "/" + update_scope["id"] + "/members", headers=collaborator["headers"]
        ),
        404,
    )
    before_manifest = sql(
        "SELECT manifest_id FROM orbit_rule_head WHERE tenant_id=%s AND id=%s",
        (tenant, current["id"]),
        all=True,
    )[0][0]
    reused_body = advanced_body | {"name": advanced_body["name"] + "-协作"}
    reused = mutate(reused_body, rule=current, identity=collaborator["headers"])
    assert reused["revision"] == current["revision"] + 1
    assert (
        sql(
            "SELECT manifest_id FROM orbit_rule_head WHERE tenant_id=%s AND id=%s",
            (tenant, current["id"]),
            all=True,
        )[0][0]
        == before_manifest
    )
    verify(reused, update_scope, reused_body)
    cases.append(RULE_SCOPE_CONSUMER_CASES[6])
    collision_scope = scope()
    root_cap = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers))
    account_scope = checked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=headers
            | {"X-CSRF-Token": root_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={"mode": "IDS", "account_ids": ids[:2], "filter": None},
        ),
        201,
    )
    assert (
        sql(
            "SELECT COUNT(*) FROM orbit_account_scope_snapshot WHERE tenant_id=%s AND id=%s",
            (tenant, collision_scope["id"]),
            all=True,
        )[0][0]
        == 0
    )
    # 技术碰撞注入：从原API真实完整scope派生，完整构建→成员→ready→审计/outbox。
    # 不关闭FK/trigger，不改原源，不把该UUID克隆称正常HTTP可达或平台证明。
    admin.begin()
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO orbit_account_scope_snapshot(tenant_id,id,actor_id,scope_version,"
                "auth_fingerprint,request_key,request_hash,request_json,"
                "member_count,members_hash,ready,created_at) "
                "SELECT tenant_id,%s,actor_id,scope_version,auth_fingerprint,"
                "%s,request_hash,request_json,0,NULL,0,"
                "UTC_TIMESTAMP(3) FROM orbit_account_scope_snapshot WHERE tenant_id=%s AND id=%s",
                (collision_scope["id"], str(uuid4()), tenant, account_scope["id"]),
            )
            assert cursor.rowcount == 1
            cursor.execute(
                "INSERT INTO orbit_account_scope_member(tenant_id,snapshot_id,"
                "account_id,external_id,"
                "name,name_prefix,account_revision,owner_user_id,owner_team_id,currency) "
                "SELECT tenant_id,%s,account_id,external_id,name,name_prefix,"
                "account_revision,owner_user_id,"
                "owner_team_id,currency FROM orbit_account_scope_member WHERE "
                "tenant_id=%s AND snapshot_id=%s",
                (collision_scope["id"], tenant, account_scope["id"]),
            )
            assert cursor.rowcount == 2
            cursor.execute(
                "UPDATE orbit_account_scope_snapshot SET ready=1,member_count=%s,members_hash=%s "
                "WHERE tenant_id=%s AND id=%s",
                (account_scope["count"], account_scope["hash"], tenant, collision_scope["id"]),
            )
            event = str(uuid4())
            cursor.execute(
                "INSERT INTO orbit_account_scope_event(id,tenant_id,"
                "snapshot_id,actor_id,request_id,"
                "member_count,members_hash,created_at) VALUES(%s,%s,%s,1,%s,%s,"
                "%s,UTC_TIMESTAMP(3))",
                (
                    event,
                    tenant,
                    collision_scope["id"],
                    str(uuid4()),
                    account_scope["count"],
                    account_scope["hash"],
                ),
            )
            cursor.execute(
                "INSERT INTO orbit_account_scope_outbox(event_id,tenant_id,snapshot_id,created_at) "
                "VALUES(%s,%s,%s,UTC_TIMESTAMP(3))",
                (event, tenant, collision_scope["id"]),
            )
        admin.commit()
    except BaseException:
        admin.rollback()
        raise
    baseline, clock_before = counts(), revision()
    collision = mutate(body(collision_scope, "两源碰撞"), status=409)
    assert collision["code"] == "RULE_SCOPE_SOURCE_AMBIGUOUS"
    assert counts() == baseline and revision() == clock_before
    cases.append(RULE_SCOPE_CONSUMER_CASES[7])
    return {
        "consumer_cases": 8,
        "new_rule_source_consumed": True,
        "http_concurrent_requests": 2,
        "technical_collision_clone": True,
        "platform_writes": 0,
        "production_authority_verified": False,
    }
