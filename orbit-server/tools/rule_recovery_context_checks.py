"""规则再认证上下文真实HTTP专项；仅主线UUID隔离库，无平台写入。"""

import asyncio
import hashlib
import json
from uuid import UUID, uuid4

if __package__:
    from .rule_editor_scope_checks import guard_target
else:
    from rule_editor_scope_checks import guard_target

ACTIONS = {
    "CREATE": "rules.create",
    "UPDATE": "rules.edit",
    "ENABLE": "rules.enable",
    "PAUSE": "rules.pause",
    "ARCHIVE": "rules.archive",
    "SIMULATE": "rules.read",
}
NATIVE_ACTORS = tuple(range(990690, 990696))
RULE_RECOVERY_CONTEXT_CASES = (
    "pythonRuleRecoveryRootSixExactActorTenantAndOriginalCsrf",
    "pythonRuleRecoverySingleActionWithoutReadOrDirectoryAndReadOnlySimulate",
    "pythonRuleRecoveryJwtContextActuallyCreatesOriginalDraft",
    "pythonRuleRecoveryStrictGetRejectsUnknownDuplicateBodyAndTargetTenant",
    "pythonRuleRecoveryRevocationRejectsOldJwtWithoutPartialContext",
    "pythonRuleRecoveryRealForeignTenantReturnsOnlyCurrentIdentity",
    "pythonRuleRecoveryCookieNewSessionCsrfCreatesOriginalDraft",
    "pythonRuleRecoveryCookieRejectsMalformedDuplicateAndRevokedNoBearerFallback",
)
PATH = "/api/v1/rules/recovery-context"


def assert_context(value, actor, tenant):
    """绝不在失败信息中输出真实CSRF、Token或业务标识。"""
    assert type(value) is dict and set(value) == {"actor_id", "tenant_id", "csrf_token"}
    assert type(value["actor_id"]) is int and value["actor_id"] == actor
    assert type(value["tenant_id"]) is str and value["tenant_id"] == tenant
    assert str(UUID(value["tenant_id"])) == value["tenant_id"]
    assert type(value["csrf_token"]) is str and 16 <= len(value["csrf_token"]) <= 255
    return value


def assert_no_context(value):
    assert type(value) is dict
    assert not {"actor_id", "tenant_id", "csrf_token"} & value.keys()


def native_response(response, *, actor=None):
    """原native协议没有ORBIT no-store约定；仍严格核HTTP、code与所需字段。"""
    assert response.status_code == 200
    value = response.json()
    assert type(value) is dict and type(value.get("code")) is int and value["code"] == 200
    if actor is None:
        assert type(value.get("token")) is str and len(value["token"]) > 16
    else:
        assert type(value.get("user")) is dict
        assert type(value["user"].get("userId")) is int and value["user"]["userId"] == actor
        assert type(value.get("permissions")) is list
        assert all(type(item) is str for item in value["permissions"])
    return value


def run_rule_recovery_context_checks(
    client, admin, headers, password, cache, database, cases, *, keys
):
    guard_target(admin, database)
    if __package__:
        from .fixture_login import fixture_login
        from .metric_fact_schema_checks import MetricFactSqlFixture
        from .metric_profile_reference_checks import seed_metric_reference_profile
        from .rule_definition_checks import definition_body
        from .rule_editor_checks import checked
        from .rule_simulation_access_checks import engine_url
    else:
        from fixture_login import fixture_login
        from metric_fact_schema_checks import MetricFactSqlFixture
        from metric_profile_reference_checks import seed_metric_reference_profile
        from rule_definition_checks import definition_body
        from rule_editor_checks import checked
        from rule_simulation_access_checks import engine_url
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from orbit_api.browser_session_store import BrowserSessionStore
    from orbit_api.credentials import CredentialCipher
    from orbit_api.directory_tokens import DirectoryTokens
    from orbit_api.oidc_contract import opaque_token

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

    assert sql("SELECT DATABASE()", rows=True) == ((database,),)
    fixture = MetricFactSqlFixture(admin, database)
    tenant, team = fixture.tenant, fixture.team
    cipher = CredentialCipher("fixture", keys)
    tokens = DirectoryTokens(cipher)

    def get_context(identity, action, actor, expected_tenant, status=200):
        value = checked(client.get(PATH, headers=identity, params={"action": action}), status)
        if status == 200:
            return assert_context(value, actor, expected_tenant)
        assert_no_context(value)
        return value

    for action in ACTIONS:
        value = get_context(headers, action, 1, tenant)
        caps = checked(
            client.get("/api/v1/rules/capabilities", headers=headers, params={"action": action})
        )
        assert set(caps) == {"csrf_token"}
        expected_binding = tokens.session_binding(headers["Authorization"], 1, tenant)
        # JWT签名令牌包含秒级有效期；跨秒请求不要求字节相同，核同原用途/会话绑定。
        for csrf in (value["csrf_token"], caps["csrf_token"]):
            assert tokens.verify("DIRECTORY_CSRF_V1", csrf)["binding"] == expected_binding
    cases.append(RULE_RECOVERY_CONTEXT_CASES[0])
    role_cap = checked(client.get("/api/v1/roles/capabilities", headers=headers))
    people = {}
    for native, (action, permission) in zip(NATIVE_ACTORS, ACTIONS.items(), strict=True):
        role = checked(
            client.post(
                "/api/v1/roles",
                headers=headers
                | {"X-CSRF-Token": role_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
                json={
                    "name": "规则恢复单动作-" + uuid4().hex[:10],
                    "menu_codes": ["rules"],
                    "permission_codes": [permission],
                },
            ),
            201,
        )
        role_id = sql(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role["id"]),
            rows=True,
        )[0][0]
        assert (
            sql("SELECT COUNT(*) FROM sys_user WHERE user_id=%s", (native,), rows=True)[0][0] == 0
        )
        owner, username = str(uuid4()), "recovery_" + uuid4().hex[:12]
        sql(
            "INSERT INTO sys_user(user_id,user_name,nick_name,email,password,status,del_flag) "
            "SELECT %s,%s,'规则恢复技术用户',%s,password,'0','0' FROM sys_user WHERE user_id=1",
            (native, username, username + "@fixture.example.org"),
        )
        sql(
            "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
            "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
            (native, str(uuid4())),
        )
        sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (native, role_id))
        sql(
            "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
            (native, tenant),
        )
        sql(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,display_name,"
            "invited,created_at) VALUES(%s,%s,%s,%s,'规则恢复技术用户',0,UTC_TIMESTAMP(3))",
            (tenant, owner, native, team),
        )
        login = native_response(
            fixture_login(client, cache, {"username": username, "password": password})
        )
        own = {"Authorization": "Bearer " + login["token"]}
        info = native_response(client.get("/getInfo", headers=own), actor=native)
        assert set(info["permissions"]) - {""} == {permission}
        for requested in ACTIONS:
            get_context(own, requested, native, tenant, 200 if requested == action else 403)
        people[action] = {
            "native": native,
            "owner": owner,
            "headers": own,
            "role": role_id,
            "username": username,
        }
    sql("UPDATE orbit_directory_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    cases.append(RULE_RECOVERY_CONTEXT_CASES[1])

    creator = people["CREATE"]
    account = fixture.account()
    sql(
        "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
        (creator["owner"], tenant, account),
    )
    sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    profile, _ = seed_metric_reference_profile(admin, database, tenant, index=969)

    def create_draft(identity, csrf):
        write = identity | {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())}
        snapshot = checked(
            client.post(
                "/api/v1/rules/editor-scope-snapshots",
                headers=write,
                json={
                    "action": "CREATE",
                    "rule_id": None,
                    "ownership": {"owner_user_id": creator["owner"], "owner_team_id": team},
                    "selection": {"mode": "IDS", "account_ids": [account], "filter": None},
                },
            ),
            201,
        )
        body = definition_body(
            "恢复上下文真实草稿-" + uuid4().hex[:10],
            creator["owner"],
            team,
            snapshot["id"],
            profile["id"],
        )
        created = checked(
            client.post(
                "/api/v1/rules", headers=write | {"Idempotency-Key": str(uuid4())}, json=body
            ),
            201,
        )
        assert created["state"] == "DRAFT" and created["revision"] == 1
        assert created["ownership"] == body["ownership"]
        # CREATE-only没有读权限；真实root回读核验，不能以POST返回代替持久化。
        assert checked(client.get("/api/v1/rules/" + created["id"], headers=headers)) == created
        checked(client.get("/api/v1/rules/" + created["id"], headers=identity), 403)

    current = get_context(creator["headers"], "CREATE", creator["native"], tenant)
    create_draft(creator["headers"], current["csrf_token"])
    cases.append(RULE_RECOVERY_CONTEXT_CASES[2])
    bad_queries = (
        ({}, 422),
        ({"action": "UNKNOWN"}, 422),
        ({"action": "CREATE", "actor_id": "1"}, 400),
        ({"action": "CREATE", "tenant_id": str(uuid4())}, 400),
        ([("action", "CREATE"), ("action", "UPDATE")], 400),
    )
    for params, status in bad_queries:
        assert_no_context(checked(client.get(PATH, headers=headers, params=params), status))
    assert_no_context(
        checked(client.request("GET", PATH + "?action=CREATE", headers=headers, content=b"{}"), 400)
    )
    assert_no_context(
        checked(
            client.get(
                PATH,
                headers=headers | {"X-Target-Tenant": str(uuid4())},
                params={"action": "CREATE"},
            ),
            403,
        )
    )
    cases.append(RULE_RECOVERY_CONTEXT_CASES[3])
    target = people["UPDATE"]
    sql(
        "DELETE a FROM orbit_business_role_action a JOIN orbit_business_role r "
        "ON r.tenant_id=a.tenant_id AND r.id=a.role_id WHERE r.native_role_id=%s "
        "AND a.permission_code='rules.edit'",
        (target["role"],),
    )
    try:
        get_context(target["headers"], "UPDATE", target["native"], tenant, 403)
    finally:
        sql(
            "INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) "
            "SELECT tenant_id,id,'rules.edit' FROM orbit_business_role WHERE native_role_id=%s",
            (target["role"],),
        )
    get_context(target["headers"], "UPDATE", target["native"], tenant)
    cases.append(RULE_RECOVERY_CONTEXT_CASES[4])

    # 真实外租户：仅SIMULATE主体搬到专属租户，原角色不跨租户借用。
    foreign, foreign_team = str(uuid4()), str(uuid4())
    sql("INSERT INTO orbit_tenant(id,name) VALUES(%s,'恢复上下文外租户')", (foreign,))
    sql(
        "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,'恢复外团队')",
        (foreign, foreign_team),
    )
    reader = people["SIMULATE"]
    # 外租户尚无完整身份时原JWT已失效401；不能把认证失效降为业务403。
    # 补齐明确外租户身份及本租户角色后，必须真实重新登录，不复用旧claim。
    sql("UPDATE orbit_user_scope SET tenant_id=%s WHERE user_id=%s", (foreign, reader["native"]))
    foreign_role = 990696
    assert (
        sql("SELECT COUNT(*) FROM sys_role WHERE role_id=%s", (foreign_role,), rows=True)[0][0] == 0
    )
    try:
        get_context(reader["headers"], "SIMULATE", reader["native"], foreign, 401)
        assert sql(
            "SELECT tenant_id FROM orbit_user_scope WHERE user_id=%s",
            (reader["native"],),
            rows=True,
        ) == ((foreign,),)
        sql(
            "INSERT INTO orbit_business_user(tenant_id,id,user_id,team_id,display_name,"
            "invited,created_at) VALUES(%s,%s,%s,%s,'恢复外租户本人',0,UTC_TIMESTAMP(3))",
            (foreign, str(uuid4()), reader["native"], foreign_team),
        )
        sql(
            "INSERT INTO sys_role(role_id,role_name,role_key,role_sort,data_scope,status,del_flag) "
            "VALUES(%s,'恢复外租户只读',%s,1,'1','0','0')",
            (foreign_role, "recovery_" + uuid4().hex),
        )
        business_role = str(uuid4())
        sql(
            "INSERT INTO orbit_business_role(tenant_id,id,native_role_id,built_in,created_at,"
            "updated_at) VALUES(%s,%s,%s,0,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (foreign, business_role, foreign_role),
        )
        sql(
            "INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) "
            "VALUES(%s,%s,'rules')",
            (foreign, business_role),
        )
        sql(
            "INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) "
            "VALUES(%s,%s,'rules.read')",
            (foreign, business_role),
        )
        sql(
            "INSERT INTO sys_role_menu(role_id,menu_id) SELECT %s,menu_id FROM sys_menu "
            "WHERE menu_id IN(31000,31040) OR (perms='rules.read' AND menu_type='F')",
            (foreign_role,),
        )
        sql(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
            (reader["native"], foreign_role),
        )
        login = native_response(
            fixture_login(client, cache, {"username": reader["username"], "password": password})
        )
        foreign_headers = {"Authorization": "Bearer " + login["token"]}
        native_response(client.get("/getInfo", headers=foreign_headers), actor=reader["native"])
        get_context(foreign_headers, "SIMULATE", reader["native"], foreign)
        get_context(foreign_headers, "CREATE", reader["native"], foreign, 403)
        assert_no_context(
            checked(
                client.get(
                    PATH,
                    headers=foreign_headers | {"X-Target-Tenant": tenant},
                    params={"action": "SIMULATE"},
                ),
                403,
            )
        )
        get_context(headers, "SIMULATE", 1, tenant)
    finally:
        sql(
            "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
            (reader["native"], foreign_role),
        )
        sql("UPDATE orbit_user_scope SET tenant_id=%s WHERE user_id=%s", (tenant, reader["native"]))
    cases.append(RULE_RECOVERY_CONTEXT_CASES[5])

    provider, identity_id = str(uuid4()), str(uuid4())
    issuer, subject = "https://recovery.fixture.example", uuid4().hex
    sql(
        "INSERT INTO orbit_system_configuration(id,tenant_id,section,name,enabled,revision,"
        "settings_json,secrets_json,verification_status,updated_at) "
        "VALUES(%s,%s,'OIDC',%s,1,1,%s,%s,'UNTESTED',UTC_TIMESTAMP(3))",
        (
            provider,
            tenant,
            "恢复Cookie技术夹具-" + uuid4().hex[:8],
            json.dumps(
                {
                    "issuer": issuer,
                    "clientId": "recovery-fixture",
                    "redirectUri": "https://app.fixture.example/auth/callback",
                }
            ),
            json.dumps(
                {
                    "clientSecret": cipher.encrypt(
                        "fixture-only-secret", tenant, provider, "clientSecret"
                    )
                }
            ),
        ),
    )
    sql(
        "INSERT INTO orbit_external_identity(id,tenant_id,user_id,issuer,issuer_digest,subject,"
        "subject_digest,provider_id,verified_email,verified_at) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(3))",
        (
            identity_id,
            tenant,
            creator["native"],
            issuer,
            hashlib.sha256(issuer.encode()).digest(),
            subject,
            hashlib.sha256(subject.encode()).digest(),
            provider,
            "recovery@fixture.example.org",
        ),
    )

    async def cookie_checks():
        engine = create_async_engine(engine_url(admin, database), echo=False, pool_pre_ping=True)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        store, binding = BrowserSessionStore(cipher), opaque_token()

        async def issue():
            async with sessions() as db, db.begin():
                return await store.issue(
                    db, tenant, creator["native"], provider, 1, binding, str(uuid4())
                )

        try:
            old, before = await issue()
            cookie, principal = await issue()
            assert before.csrf_token != principal.csrf_token and old != cookie
            pair = f"adpilot_session={cookie}; __Host-orbit_browser={binding}"
            own = {"Cookie": pair}
            value = get_context(own, "CREATE", creator["native"], tenant)
            assert value["csrf_token"] == principal.csrf_token
            assert get_context(own | headers, "CREATE", creator["native"], tenant) == value
            create_draft(own | {"Origin": "https://app.fixture.example"}, value["csrf_token"])
            cases.append(RULE_RECOVERY_CONTEXT_CASES[6])
            for malformed in ("adpilot_session=malformed", pair + "; adpilot_session=" + cookie):
                assert_no_context(
                    checked(
                        client.get(
                            PATH,
                            headers=headers | {"Cookie": malformed},
                            params={"action": "CREATE"},
                        ),
                        401,
                    )
                )
            async with sessions() as db, db.begin():
                await store.logout(
                    db,
                    cookie,
                    binding,
                    principal.csrf_token,
                    "recovery-" + uuid4().hex,
                    str(uuid4()),
                )
            get_context(own | headers, "CREATE", creator["native"], tenant, 401)
            cases.append(RULE_RECOVERY_CONTEXT_CASES[7])
        finally:
            await engine.dispose()

    asyncio.run(cookie_checks())
