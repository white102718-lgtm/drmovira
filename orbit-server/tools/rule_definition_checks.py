"""057规则定义真实专项；仅主线UUID库，账户/profile为SQL技术夹具，零平台调用。

真实角色、私有scope与规则均走原API。不构造ENABLED/Simulation成功，不启动服务。
每组完整成功后才append；失败保留前面真实通过组，外层主线销毁本轮数据库。
"""

import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

RULE_DEFINITION_CASES = [
    "pythonRuleOriginalCreateDetailAndFifteenFields",
    "pythonRuleOriginalWriteBoundaryAndHeadersHaveNoPartialWrites",
    "pythonRuleNoopAndRealEditReuseImmutableManifest",
    "pythonRuleSuccessfulKeysPrecedeOldCasButRejectDifferentIntent",
    "pythonRuleActiveNameUniqueContainsAndArchiveReleasesName",
    "pythonRuleComplete521MixedCurrencyMembersAndOwnerIntersection",
    "pythonRuleRulesOnlyEditorUsesOwnManifestWithoutOtherModules",
    "pythonRuleForeignOwnerHiddenAndOriginalListFilters",
    "pythonRuleUnavailableProfileDoesNotBlockReadOrArchive",
    "pythonRuleMissingSimulationAndRunSourcesNeverFakeSuccess",
    "pythonRuleLiteralContainsEscapingAndSignedCursorChanges",
    "pythonRuleOriginalActionRevocationRejectsSuccessfulReplay",
    "pythonRuleCurrentMemberScopeRejectsTransferWithoutClockBump",
    "pythonRuleDatabaseImmutableGuardsReturnExact1644",
    "pythonRuleOutbox1644RollsBackAllEightTables",
    "pythonRuleConcurrentSameCasHasExactlyOneAtomicWinner",
]

TABLES = (
    "orbit_rule_clock",
    "orbit_rule_scope_manifest",
    "orbit_rule_scope_member",
    "orbit_rule_event",
    "orbit_rule_version",
    "orbit_rule_head",
    "orbit_rule_idempotency",
    "orbit_rule_outbox",
)
SCOPE_MEMBERS_PATH = "/api/v1/scope-snapshots/{id}/members"


def guard_rule_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not isinstance(database, str)
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("规则专项仅允许13306本轮UUID隔离库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("实际库不是本轮UUID库")
    admin.commit()


def checked(response, status, *, code=None):
    body = response.json()
    if response.status_code != status:
        # 仅输出固定HTTP状态与安全错误码，不打印正文、头、业务ID或秘密。
        print(
            json.dumps(
                {
                    "rule_check_http_status": response.status_code,
                    "expected_status": status,
                    "safe_code": body.get("code") if isinstance(body, dict) else None,
                }
            ),
            flush=True,
        )
    assert response.status_code == status, {
        "actual": response.status_code,
        "expected": status,
        "code": body.get("code") if isinstance(body, dict) else None,
    }
    if code is not None:
        assert body.get("code") == code, {"actual_code": body.get("code"), "expected_code": code}
    return body


def definition_body(name, owner, team, snapshot, profile):
    return {
        "name": name,
        "ownership": {"owner_user_id": owner, "owner_team_id": team},
        "target_level": "AD",
        "scope_snapshot_id": snapshot,
        "logic": "AND",
        "groups": [
            {
                "logic": "AND",
                "conditions": [{"metric": "spend", "operator": "GTE", "threshold": "12.500000"}],
            }
        ],
        "window": "LAST_3D",
        "metric_profile_id": profile,
        "schedule": {
            "frequency": "INTERVAL",
            "interval_minutes": 30,
            "time_of_day": None,
            "weekday": None,
            "timezone": "Asia/Shanghai",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
        "cooldown_minutes": 60,
        "max_daily": 5,
    }


def run_rule_definition_checks(client, admin, headers, password, cache, database, cases):
    guard_rule_target(admin, database)
    try:
        from fixture_login import fixture_login
        from metric_profile_query_checks import query_profile_sql_sample
    except ImportError:
        from tools.fixture_login import fixture_login
        from tools.metric_profile_query_checks import query_profile_sql_sample
    from pymysql.err import MySQLError

    from orbit_api.rule_contract import Rule, RulePage, parse_rule_response

    def sql(statement, values=(), *, rows=False):
        try:
            with admin.cursor() as cursor:
                cursor.execute(statement, values)
                result = cursor.fetchall() if rows else cursor.rowcount
            admin.commit()
            return result
        except BaseException:
            admin.rollback()
            raise

    def counts():
        with admin.cursor() as cursor:
            values = []
            for table in TABLES:
                cursor.execute("SELECT COUNT(*) FROM " + table)
                values.append(cursor.fetchone()[0])
            cursor.execute("SELECT revision FROM orbit_rule_clock WHERE tenant_id=%s", (tenant,))
            values.append(cursor.fetchone()[0])
        admin.commit()
        return tuple(values)

    tenant, root_owner, team = sql(
        "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1", rows=True
    )[0]
    assert (
        sql("SELECT COUNT(*) FROM sys_user WHERE user_id IN(990570,990571)", rows=True)[0][0] == 0
    )
    role_caps = checked(client.get("/api/v1/roles/capabilities", headers=headers), 200)
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": role_caps["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "规则专属" + uuid4().hex[:12],
                "menu_codes": ["rules"],
                "permission_codes": [
                    "rules.read",
                    "rules.create",
                    "rules.edit",
                    "rules.enable",
                    "rules.pause",
                    "rules.archive",
                ],
            },
        ),
        201,
    )
    native_role = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
        rows=True,
    )[0][0]
    identities = []
    for native in (990570, 990571):
        owner, username = str(uuid4()), "rule_fixture_" + uuid4().hex[:12]
        with admin.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
                "SELECT %s,%s,'规则夹具',%s,password,'0','0' FROM sys_user WHERE user_id=1",
                (native, username, username + "@fixture.example.org"),
            )
            cursor.execute(
                "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
                "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
                (native, str(uuid4())),
            )
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, native_role)
            )
            cursor.execute(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
                (native, tenant),
            )
            cursor.execute(
                "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,"
                "display_name,invited,created_at) "
                "VALUES(%s,%s,%s,%s,'规则夹具',0,UTC_TIMESTAMP(3))",
                (tenant, owner, native, team),
            )
        admin.commit()
        login = checked(
            fixture_login(client, cache, {"username": username, "password": password}), 200
        )
        identities.append(
            {
                "owner": owner,
                "actor": native,
                "headers": {"Authorization": "Bearer " + login["token"]},
            }
        )
    editor, foreign = identities
    account_ids = sorted(str(uuid4()) for _ in range(521))
    other_account = str(uuid4())
    marker = "规则定义-" + uuid4().hex[:12]
    with admin.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,"
            "owner_user_id,owner_team_id,currency,timezone_id,auth_status,account_status,"
            "value_json,details_json,bound_at,created_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'Asia/Shanghai','UNKNOWN','UNKNOWN','{}','{}',"
            "UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            [
                (
                    tenant,
                    identifier,
                    "00" + str(10**22 + uuid4().int % 10**22),
                    marker,
                    marker,
                    editor["owner"] if identifier != other_account else foreign["owner"],
                    team,
                    "USD" if index % 2 else "EUR",
                )
                for index, identifier in enumerate(account_ids + [other_account])
            ],
        )
    admin.commit()
    profile, profile_hash, proof = query_profile_sql_sample(570)
    with admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO orbit_metric_profile_version(tenant_id,profile_id,version,"
            "payload_json,payload_hash,source,authority_kind,observed_at,evidence_ref,"
            "source_sha256,source_proof_json,created_by) "
            "VALUES(%s,%s,%s,%s,%s,'FIXTURE','ISOLATED_TEST',%s,'isolated-query:SQL_ONLY_NOT_META',%s,%s,1)",
            (
                tenant,
                profile["id"],
                profile["version"],
                json.dumps(profile),
                profile_hash,
                datetime.fromisoformat(json.loads(proof)["observed_at"]).replace(tzinfo=None),
                "a" * 64,
                proof,
            ),
        )
        cursor.execute(
            "INSERT INTO orbit_metric_profile_head(tenant_id,id,current_version,revision,state) "
            "VALUES(%s,%s,%s,1,'ENABLED')",
            (tenant, profile["id"], profile["version"]),
        )
        cursor.execute(
            "UPDATE orbit_metric_profile_clock SET revision=revision+1 WHERE tenant_id=%s",
            (tenant,),
        )
    admin.commit()

    def snapshot(ids):
        cap = checked(client.get("/api/v1/scope-snapshots/capabilities", headers=headers), 200)
        return checked(
            client.post(
                "/api/v1/scope-snapshots",
                headers=headers
                | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
                json={"mode": "IDS", "account_ids": ids, "filter": None},
            ),
            201,
        )["id"]

    scope = snapshot(account_ids)
    base = "/api/v1/rules"

    def body(suffix, *, selected=scope, owner=None):
        return definition_body(
            marker + suffix, owner or editor["owner"], team, selected, profile["id"]
        )

    def mutate(
        method, url, value, *, actor=headers, action="CREATE", revision=None, key=None, status=200
    ):
        cap = checked(
            client.get(base + "/capabilities", headers=actor, params={"action": action}), 200
        )
        extra = {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": key or str(uuid4())}
        if revision is not None:
            extra["If-Match"] = '"' + str(revision) + '"'
        response = client.request(method, url, headers=actor | extra, json=value)
        return checked(response, status)

    def create(suffix, *, value=None, key=None):
        return mutate("POST", base, value or body(suffix), key=key, status=201)

    def get(identifier, *, actor=headers, status=200):
        return checked(client.get(base + "/" + identifier, headers=actor), status)

    def update(rule, value, *, key=None, actor=headers, status=200, revision=None):
        return mutate(
            "PUT",
            base + "/" + rule["id"],
            value,
            actor=actor,
            action="UPDATE",
            revision=rule["revision"] if revision is None else revision,
            key=key,
            status=status,
        )

    def archive(rule, *, actor=headers):
        return mutate(
            "POST",
            base + "/" + rule["id"] + "/archive",
            {"reason": "真实定义归档"},
            actor=actor,
            action="ARCHIVE",
            revision=rule["revision"],
        )

    def done(index):
        cases.append(RULE_DEFINITION_CASES[index])

    created_key = str(uuid4())
    initial_body = body("-首项")
    first = create("", value=initial_body, key=created_key)
    parse_rule_response(Rule, first)
    assert len(first) == 15 and first["state"] == "DRAFT" and first["next_run_at"] is None
    assert get(first["id"]) == first
    page = checked(client.get(base, headers=headers), 200)
    parse_rule_response(RulePage, page)
    assert any(row["id"] == first["id"] for row in page["items"])
    done(0)

    before = counts()
    for bad in (
        dict(initial_body, unknown=True),
        {k: v for k, v in initial_body.items() if k != "schedule"},
    ):
        mutate("POST", base, bad, status=400)
    bad = copy.deepcopy(initial_body)
    del bad["schedule"]["weekday"]
    mutate("POST", base, bad, status=400)
    mutate("POST", base, dict(initial_body, cooldown_minutes=-1), status=422)
    cap = checked(
        client.get(base + "/capabilities", headers=headers, params={"action": "CREATE"}), 200
    )
    checked(
        client.post(base, headers=headers | {"X-CSRF-Token": cap["csrf_token"]}, json=initial_body),
        400,
        code="IDEMPOTENCY_KEY_INVALID",
    )
    checked(
        client.post(
            base,
            headers=headers
            | {"Idempotency-Key": str(uuid4()), "X-CSRF-Token": "not-a-session-token"},
            json=initial_body,
        ),
        403,
        code="CSRF_INVALID",
    )
    assert counts() == before
    done(1)

    original_manifest = sql(
        "SELECT manifest_id FROM orbit_rule_head WHERE tenant_id=%s AND id=%s",
        (tenant, first["id"]),
        rows=True,
    )[0][0]
    noop = update(first, initial_body)
    assert noop == first
    changed_body = dict(initial_body, cooldown_minutes=61)
    edit_key = str(uuid4())
    edited = update(first, changed_body, key=edit_key)
    assert edited["revision"] == 2 and edited["cooldown_minutes"] == 61
    assert (
        sql(
            "SELECT manifest_id FROM orbit_rule_head WHERE tenant_id=%s AND id=%s",
            (tenant, first["id"]),
            rows=True,
        )[0][0]
        == original_manifest
    )
    assert (
        sql(
            "SELECT COUNT(*) FROM orbit_rule_version WHERE tenant_id=%s AND rule_id=%s",
            (tenant, first["id"]),
            rows=True,
        )[0][0]
        == 2
    )
    done(2)

    assert update(first, changed_body, key=edit_key) == edited
    before = counts()
    update(first, dict(changed_body, max_daily=6), key=edit_key, status=409)
    assert create("", value=initial_body, key=created_key) == first
    assert counts() == before
    done(3)

    before = counts()
    mutate("POST", base, initial_body, status=409)
    assert counts() == before
    disposable = create("-回收名称")
    archived = archive(disposable)
    assert archived["state"] == "ARCHIVED"
    reused = create("-回收名称")
    assert reused["id"] != disposable["id"]
    done(4)

    assert sql(
        "SELECT COUNT(*),COUNT(DISTINCT frozen_currency) FROM orbit_rule_scope_member "
        "WHERE tenant_id=%s AND manifest_id=%s",
        (tenant, original_manifest),
        rows=True,
    )[0] == (521, 2)
    mixed = snapshot([account_ids[0], other_account])
    before = counts()
    mutate("POST", base, body("-越交集", selected=mixed), status=409)
    assert counts() == before
    done(5)

    rules_only = editor["headers"]
    for endpoint in ("/api/v1/accounts/extended", "/api/v1/launch-plans/capabilities"):
        checked(client.get(endpoint, headers=rules_only), 403)
    editor_body = dict(changed_body, max_daily=7)
    edited = update(edited, editor_body, actor=rules_only)
    assert edited["revision"] == 3
    assert (
        sql(
            "SELECT COUNT(*) FROM orbit_rule_scope_manifest WHERE tenant_id=%s AND rule_id=%s",
            (tenant, edited["id"]),
            rows=True,
        )[0][0]
        == 1
    )
    checked(client.get(SCOPE_MEMBERS_PATH.format(id=scope), headers=rules_only), 403)
    done(6)

    get(first["id"], actor=foreign["headers"], status=404)
    filtered = checked(
        client.get(base, headers=foreign["headers"], params={"operator_user_id": editor["owner"]}),
        200,
    )
    assert filtered["items"] == []
    mine = checked(
        client.get(
            base,
            headers=rules_only,
            params={
                "operator_user_id": editor["owner"],
                "metric_profile_id": profile["id"],
                "entity_type": "AD",
                "status": "DRAFT",
            },
        ),
        200,
    )
    assert any(row["id"] == edited["id"] for row in mine["items"])
    done(7)

    safe = create("-无来源仍可读归档")
    sql(
        "UPDATE orbit_metric_profile_head SET state='DISABLED' WHERE tenant_id=%s AND id=%s",
        (tenant, profile["id"]),
    )
    try:
        assert get(safe["id"]) == safe
        assert create("", value=initial_body, key=created_key) == first
        mutate(
            "POST",
            base + "/" + safe["id"] + "/pause",
            {"reason": "当前非启用"},
            action="PAUSE",
            revision=safe["revision"],
            status=409,
        )
        assert archive(safe)["state"] == "ARCHIVED"
    finally:
        sql(
            "UPDATE orbit_metric_profile_head SET state='ENABLED' WHERE tenant_id=%s AND id=%s",
            (tenant, profile["id"]),
        )
    done(8)

    before = counts()
    mutate(
        "POST",
        base + "/" + edited["id"] + "/enable",
        {"simulation_id": str(uuid4())},
        action="ENABLE",
        revision=edited["revision"],
        status=503,
    )
    cap = checked(
        client.get(base + "/capabilities", headers=headers, params={"action": "SIMULATE"}), 200
    )
    checked(
        client.post(
            base + "/" + edited["id"] + "/simulate",
            headers=headers
            | {
                "X-CSRF-Token": cap["csrf_token"],
                "Idempotency-Key": str(uuid4()),
                "If-Match": '"' + str(edited["revision"]) + '"',
            },
        ),
        503,
    )
    checked(client.get(base + "/" + edited["id"] + "/runs", headers=headers), 503)
    assert counts() == before
    done(9)

    literal = create("-字面%_\\尾")
    result = checked(client.get(base, headers=headers, params={"q": "%_\\"}), 200)
    assert [row["id"] for row in result["items"]] == [literal["id"]]
    for index in range(21):
        create("-分页" + str(index))
    page = checked(client.get(base, headers=headers, params={"page_size": 20}), 200)
    assert len(page["items"]) == 20 and page["next_cursor"]
    next_page = checked(
        client.get(base, headers=headers, params={"page_size": 20, "cursor": page["next_cursor"]}),
        200,
    )
    assert not ({r["id"] for r in page["items"]} & {r["id"] for r in next_page["items"]})
    checked(
        client.get(base, headers=headers, params={"page_size": 50, "cursor": page["next_cursor"]}),
        409,
    )
    create("-游标失效")
    checked(
        client.get(base, headers=headers, params={"page_size": 20, "cursor": page["next_cursor"]}),
        409,
    )
    done(10)

    revocation_key = str(uuid4())
    revocation_body = dict(editor_body, max_daily=8)
    edited = update(edited, revocation_body, key=revocation_key, actor=rules_only)
    cap = checked(
        client.get(base + "/capabilities", headers=rules_only, params={"action": "UPDATE"}), 200
    )
    sql(
        "DELETE FROM orbit_business_role_action WHERE tenant_id=%s AND role_id=%s "
        "AND permission_code='rules.edit'",
        (tenant, role["id"]),
    )
    try:
        checked(
            client.put(
                base + "/" + edited["id"],
                headers=rules_only
                | {
                    "X-CSRF-Token": cap["csrf_token"],
                    "Idempotency-Key": revocation_key,
                    "If-Match": '"3"',
                },
                json=revocation_body,
            ),
            403,
        )
    finally:
        sql(
            "INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) "
            "VALUES(%s,%s,'rules.edit')",
            (tenant, role["id"]),
        )
    done(11)

    before = counts()
    sql(
        "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
        (foreign["owner"], tenant, account_ids[0]),
    )
    try:
        update(edited, dict(revocation_body, max_daily=9), actor=rules_only, status=409)
        assert get(edited["id"], actor=rules_only) == edited
        assert counts() == before
    finally:
        sql(
            "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
            (editor["owner"], tenant, account_ids[0]),
        )
    done(12)

    # 每条真实失败均精确1644；不把FK/CHECK/重复键等其它SQL错误计作护栏通过。
    before = counts()

    # 使用实际列清单构造INSERT反例；从未更改生产trigger或绕过缺省值。
    def clone_insert(table, changes, where, arguments):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                "AND EXTRA NOT LIKE '%%GENERATED%%' ORDER BY ORDINAL_POSITION",
                (database, table),
            )
            columns = [row[0] for row in cursor.fetchall()]
        admin.commit()
        assert set(changes) <= set(columns)
        expressions = ["%s" if column in changes else "`" + column + "`" for column in columns]
        return (
            "INSERT INTO "
            + table
            + "("
            + ",".join("`" + column + "`" for column in columns)
            + ") SELECT "
            + ",".join(expressions)
            + " FROM "
            + table
            + " WHERE "
            + where
            + " LIMIT 1",
            tuple(changes[column] for column in columns if column in changes) + arguments,
        )

    rejects = [
        clone_insert(
            "orbit_rule_scope_manifest",
            {"id": str(uuid4()), "sealed": 1},
            "tenant_id=%s AND id=%s",
            (tenant, original_manifest),
        ),
        (
            "UPDATE orbit_rule_scope_manifest SET sealed=0 WHERE tenant_id=%s AND id=%s",
            (tenant, original_manifest),
        ),
        (
            "DELETE FROM orbit_rule_scope_manifest WHERE tenant_id=%s AND id=%s",
            (tenant, original_manifest),
        ),
        clone_insert(
            "orbit_rule_scope_member",
            {"account_id": other_account},
            "tenant_id=%s AND manifest_id=%s",
            (tenant, original_manifest),
        ),
        (
            "UPDATE orbit_rule_scope_member SET frozen_revision=frozen_revision+1 "
            "WHERE tenant_id=%s AND manifest_id=%s LIMIT 1",
            (tenant, original_manifest),
        ),
        (
            "DELETE FROM orbit_rule_scope_member WHERE tenant_id=%s AND manifest_id=%s LIMIT 1",
            (tenant, original_manifest),
        ),
        clone_insert(
            "orbit_rule_version",
            {"rule_id": str(uuid4())},
            "tenant_id=%s AND rule_id=%s",
            (tenant, first["id"]),
        ),
        (
            "UPDATE orbit_rule_version SET payload_hash=REPEAT('a',64) "
            "WHERE tenant_id=%s AND rule_id=%s LIMIT 1",
            (tenant, first["id"]),
        ),
        (
            "DELETE FROM orbit_rule_version WHERE tenant_id=%s AND rule_id=%s LIMIT 1",
            (tenant, first["id"]),
        ),
        clone_insert(
            "orbit_rule_head", {"id": str(uuid4())}, "tenant_id=%s AND id=%s", (tenant, first["id"])
        ),
        (
            "UPDATE orbit_rule_head SET revision=revision+2 WHERE tenant_id=%s AND id=%s",
            (tenant, first["id"]),
        ),
        ("DELETE FROM orbit_rule_head WHERE tenant_id=%s AND id=%s", (tenant, first["id"])),
        (
            "UPDATE orbit_rule_event SET reason='篡改' WHERE tenant_id=%s AND rule_id=%s LIMIT 1",
            (tenant, first["id"]),
        ),
        (
            "DELETE FROM orbit_rule_event WHERE tenant_id=%s AND rule_id=%s LIMIT 1",
            (tenant, first["id"]),
        ),
        (
            "UPDATE orbit_rule_idempotency SET intent_hash=REPEAT('a',64) "
            "WHERE tenant_id=%s AND rule_id=%s LIMIT 1",
            (tenant, first["id"]),
        ),
        (
            "DELETE FROM orbit_rule_idempotency WHERE tenant_id=%s AND rule_id=%s LIMIT 1",
            (tenant, first["id"]),
        ),
        (
            "UPDATE orbit_rule_outbox SET created_at=created_at+INTERVAL 1 SECOND "
            "WHERE tenant_id=%s LIMIT 1",
            (tenant,),
        ),
        ("DELETE FROM orbit_rule_outbox WHERE tenant_id=%s LIMIT 1", (tenant,)),
    ]
    assert len(rejects) == 18
    for statement, values in rejects:
        try:
            with admin.cursor() as cursor:
                cursor.execute(statement, values)
        except MySQLError as error:
            assert error.args[0] == 1644, {"errno": error.args[0]}
        else:
            raise AssertionError("规则不可变DML意外成功")
        finally:
            admin.rollback()
    assert counts() == before
    done(13)

    trigger = "rule_fixture_fail_" + uuid4().hex[:12]
    before = counts()
    try:
        sql(
            "CREATE TRIGGER " + trigger + " BEFORE INSERT ON orbit_rule_outbox FOR EACH ROW "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='ISOLATED_RULE_OUTBOX_1644'"
        )
        mutate("POST", base, body("-原子回滚"), status=503)
        assert counts() == before
    finally:
        sql("DROP TRIGGER IF EXISTS " + trigger)
    done(14)

    concurrent = create("-双CAS")
    a, b = body("-双CAS-A"), body("-双CAS-B")
    before = counts()
    cap = checked(
        client.get(base + "/capabilities", headers=headers, params={"action": "UPDATE"}), 200
    )

    def race(value):
        return client.put(
            base + "/" + concurrent["id"],
            headers=headers
            | {
                "X-CSRF-Token": cap["csrf_token"],
                "Idempotency-Key": str(uuid4()),
                "If-Match": '"1"',
            },
            json=value,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(race, (a, b)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response.json() for response in responses if response.status_code == 200)
    assert get(concurrent["id"]) == winner and winner["revision"] == 2
    after = counts()
    # 目录+版本+事件+ledger+outbox各增一次；成员及manifest不重复复制。
    assert [y - x for x, y in zip(before, after, strict=True)] == [0, 0, 0, 1, 1, 0, 1, 1, 1]
    done(15)
