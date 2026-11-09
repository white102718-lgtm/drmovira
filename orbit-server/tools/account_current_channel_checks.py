"""064账户渠道真实HTTP/MySQL专项；仅13306 UUID库，账户/profile为技术夹具，无平台写入。"""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

CASES = [
    "currentChannelEmptyAndStrictWriteBoundaries",
    "currentChannelBindReplayCasAndAtomicAudit",
    "ruleChannelCandidatesReadOnlyBoundedPaging",
    "ruleChannelEffectiveDateAndSecondPage",
    "currentChannelRebindInvalidatesCandidateAndRuleCursor",
    "currentChannelClearAndDisabledOrInvisibleTarget",
    "currentChannelConcurrentCasSingleWinner",
    "currentChannelOutboxFailureRollsBackAllWrites",
    "currentChannelPermissionRevokedRejectsReplay",
    "ruleFilterCandidatesReadOnlyActorWithoutChannelOrAccountPermissions",
    "currentChannelOwnReadOnlyReturnsNoCsrf",
    "currentChannelReadOnlyCannotWriteAndLeavesStateUnchanged",
    "currentChannelRealForeignTenantWhole404AndNoRuleCandidates",
]


def run_checks(client, admin, headers, database, cases, fixture_info, password, cache):
    from metric_fact_schema_checks import MetricFactSqlFixture
    from rule_definition_checks import checked, definition_body, guard_rule_target

    guard_rule_target(admin, database)
    fixture = MetricFactSqlFixture(admin, database)
    tenant, owner, team = fixture.tenant, fixture.owner, fixture.team

    def sql(statement, params=(), rows=False):
        with admin.cursor() as cursor:
            cursor.execute(statement, params)
            result = cursor.fetchall() if rows else cursor.rowcount
        admin.commit()
        return result

    def cap(path, **params):
        return checked(client.get(path, headers=headers, params=params), 200)

    def write_headers(csrf, revision=None, key=None):
        return (
            headers
            | {"X-CSRF-Token": csrf, "Idempotency-Key": key or str(uuid4())}
            | ({"If-Match": f'"{revision}"'} if revision else {})
        )

    def import_reference(kind, **extra):
        current = cap("/api/v1/reference-catalog-imports/capabilities")
        identifier = str(uuid4())
        value = {
            "kind": kind,
            "id": identifier,
            "name": "渠道关联验收引用",
            "availability": "AVAILABLE",
            "owner_team_id": team,
            "data_owner_user_ids": [owner],
            "source_key": "channel-it-" + identifier,
            **extra,
        }
        preview = checked(
            client.post(
                "/api/v1/reference-catalog-imports",
                headers=write_headers(current["csrf_token"]),
                json={
                    "kind": kind,
                    "source": "真实HTTP隔离验收",
                    "reason": "当前账户渠道",
                    "base_catalog_revision": current["catalog_revision"],
                    "items": [value],
                },
            ),
            201,
        )
        assert preview["state"] == "VALIDATED"
        checked(
            client.post(
                "/api/v1/reference-catalog-imports/" + preview["id"] + "/commit",
                headers=write_headers(current["csrf_token"], preview["revision"]),
            ),
            200,
        )
        return identifier

    agent = import_reference("BUSINESS_AGENT")
    product = import_reference("PRODUCT", allowed_agent_ids=[agent])
    channel_cap = cap("/api/v1/reference-catalog-imports/capabilities")
    channels = []
    for index in range(21):
        value = {
            "ownership": {"owner_team_id": team, "data_owner_user_ids": [owner]},
            "code": "CURRENT_" + uuid4().hex,
            "name": f"当前渠道验收{index:02d}",
            "product_id": product,
            "agent_id": agent,
            "type": "WEBSITE",
            "media": "META",
            "url": "https://example.com/channel-test",
            "status": "ENABLED",
        }
        channels.append(
            checked(
                client.post(
                    "/api/v1/channels", headers=write_headers(channel_cap["csrf_token"]), json=value
                ),
                201,
            )
        )
    accounts = [fixture.account() for _ in range(21)]
    # 原账户、指标只用隔离技术来源；渠道、规则、范围、关联均通过真实业务API。
    scope_cap = cap("/api/v1/scope-snapshots/capabilities")
    scope = checked(
        client.post(
            "/api/v1/scope-snapshots",
            headers=write_headers(scope_cap["csrf_token"]),
            json={"mode": "IDS", "account_ids": accounts, "filter": None},
        ),
        201,
    )
    rule_cap = cap("/api/v1/rules/capabilities", action="CREATE")
    marker = "当前渠道闭环-" + uuid4().hex[:8]
    rules = []
    for index in range(21):
        body = definition_body(
            marker + f"-{index:02d}", owner, team, scope["id"], fixture_info["profile_id"]
        )
        rules.append(
            checked(
                client.post(
                    "/api/v1/rules", headers=write_headers(rule_cap["csrf_token"]), json=body
                ),
                201,
            )
        )

    def path(account=accounts[0]):
        return "/api/v1/accounts/" + account + "/current-channel"

    empty = cap(path())
    assert empty["channel_id"] is None and empty["csrf_token"]
    for body in [
        {},
        {"channel_id": None, "reason": ""},
        {"channel_id": "bad", "reason": "test"},
        {"channel_id": None, "reason": "ok", "tenant_id": tenant},
    ]:
        assert (
            client.put(
                path(), headers=write_headers(empty["csrf_token"], empty["revision"]), json=body
            ).status_code
            == 422
        )
    assert cap(path())["revision"] == empty["revision"]
    cases.append(CASES[0])

    def save(account, channel, *, expected=None, key=None, status=200):
        current = cap(path(account))
        h = write_headers(current["csrf_token"], expected or current["revision"], key)
        body = {"channel_id": channel, "reason": "隔离验收当前渠道关联"}
        return checked(client.put(path(account), headers=h, json=body), status), h, body

    first, h, body = save(accounts[0], channels[0]["id"])
    assert checked(client.put(path(), headers=h, json=body), 200) == first
    assert (
        client.put(
            path(), headers=write_headers(empty["csrf_token"], empty["revision"]), json=body
        ).status_code
        == 409
    )
    assert (
        sql(
            "SELECT COUNT(*) FROM orbit_account_event "
            "WHERE tenant_id=%s AND resource_id=%s AND action=%s",
            (tenant, accounts[0], "CURRENT_CHANNEL_CHANGED"),
            True,
        )[0][0]
        == 1
    )
    for account, channel in zip(accounts[1:], channels[1:], strict=True):
        save(account, channel["id"])
    cases.append(CASES[1])
    candidates = cap("/api/v1/rules/list-filter-options", kind="CHANNEL", page_size=20)
    assert len(candidates["items"]) == 20 and candidates["next_cursor"]
    next_candidates = cap(
        "/api/v1/rules/list-filter-options",
        kind="CHANNEL",
        page_size=20,
        cursor=candidates["next_cursor"],
    )
    assert len(next_candidates["items"]) == 1 and next_candidates["next_cursor"] is None
    assert {x["id"] for x in candidates["items"] + next_candidates["items"]} == {
        c["id"] for c in channels
    }
    assert all(x["label"].startswith("当前渠道验收") for x in candidates["items"])
    cases.append(CASES[2])
    query = {
        "channel_id": channels[0]["id"],
        "date_from": "2026-01-01",
        "date_to": "2026-01-01",
        "page_size": 20,
        "q": marker,
    }
    page = cap("/api/v1/rules", **query)
    assert len(page["items"]) == 20 and page["next_cursor"]
    second = cap("/api/v1/rules", **query, cursor=page["next_cursor"])
    assert len(second["items"]) == 1
    assert {x["id"] for x in page["items"] + second["items"]} == {r["id"] for r in rules}
    assert not cap("/api/v1/rules", channel_id=channels[0]["id"], date_from="2026-01-02")["items"]
    cases.append(CASES[3])
    save(accounts[0], channels[1]["id"])
    assert (
        client.get(
            "/api/v1/rules", headers=headers, params=query | {"cursor": page["next_cursor"]}
        ).status_code
        == 409
    )
    assert (
        client.get(
            "/api/v1/rules/list-filter-options",
            headers=headers,
            params={"kind": "CHANNEL", "page_size": 20, "cursor": candidates["next_cursor"]},
        ).status_code
        == 409
    )
    assert not cap("/api/v1/rules", **query)["items"]
    assert len(cap("/api/v1/rules", channel_id=channels[1]["id"], q=marker)["items"]) == 21
    cases.append(CASES[4])
    save(accounts[0], None)
    assert cap(path())["channel_id"] is None
    save(accounts[0], str(uuid4()), status=404)
    disabled = channels[0]
    # 通过真实渠道编辑停用，不能直接改DB伪造业务结果。
    channel_edit = cap("/api/v1/channels/capabilities")
    disabled_body = {
        k: disabled[k]
        for k in (
            "ownership",
            "code",
            "name",
            "product_id",
            "agent_id",
            "type",
            "media",
            "url",
            "status",
        )
    }
    disabled_body["status"] = "DISABLED"
    checked(
        client.put(
            "/api/v1/channels/" + disabled["id"],
            headers=write_headers(channel_edit["csrf_token"], disabled["revision"]),
            json=disabled_body,
        ),
        200,
    )
    save(accounts[0], disabled["id"], status=422)
    # 已成功原键仍可恢复；停用仅禁止新的关联意图。
    assert checked(client.put(path(), headers=h, json=body), 200) == first
    cases.append(CASES[5])
    before = cap(path())
    payload = {"channel_id": channels[2]["id"], "reason": "并发CAS"}

    def race(_):
        return client.put(
            path(), headers=write_headers(before["csrf_token"], before["revision"]), json=payload
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(race, range(2))) == [200, 409]
    cases.append(CASES[6])
    before = cap(path())
    table_names = [
        "orbit_account_current_channel",
        "orbit_account_channel_idempotency",
        "orbit_account_event",
        "orbit_account_outbox",
    ]
    counts = [sql("SELECT COUNT(*) FROM " + t, rows=True)[0][0] for t in table_names]
    sql(
        "CREATE TRIGGER fixture_channel_outbox BEFORE INSERT ON orbit_account_outbox "
        "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='CHANNEL_FIXTURE_ROLLBACK'"
    )
    try:
        save(accounts[0], channels[3]["id"], status=503)
    finally:
        sql("DROP TRIGGER fixture_channel_outbox")
    after = cap(path())
    assert {k: after[k] for k in ("revision", "channel_id")} == {
        k: before[k] for k in ("revision", "channel_id")
    }
    assert counts == [sql("SELECT COUNT(*) FROM " + t, rows=True)[0][0] for t in table_names]
    cases.append(CASES[7])
    sql("UPDATE sys_menu SET status='1' WHERE perms='accounts.assign'")
    try:
        assert client.put(path(), headers=h, json=body).status_code == 403
        assert cap(path())["csrf_token"] is None
    finally:
        sql("UPDATE sys_menu SET status='0' WHERE perms='accounts.assign'")
    cases.append(CASES[8])
    # 使用父档已真实登录过的本人/外租户主体；只补精确账户读取授权，不借管理员Token。
    from fixture_login import fixture_login
    from rules_definition_flow_checks import NATIVE_ACTORS, assert_read_only_info

    identities = []
    for native in NATIVE_ACTORS:
        actor = sql(
            "SELECT u.user_name,b.id,b.tenant_id,b.team_id FROM sys_user u "
            "JOIN orbit_business_user b ON b.user_id=u.user_id WHERE u.user_id=%s",
            (native,),
            True,
        )
        assert len(actor) == 1
        username, subject, actor_tenant, actor_team = actor[0]
        login = checked(
            fixture_login(client, cache, {"username": username, "password": password}), 200
        )
        actor_headers = {"Authorization": "Bearer " + login["token"]}
        assert_read_only_info(client.get("/getInfo", headers=actor_headers))
        identities.append((native, username, subject, actor_tenant, actor_team, actor_headers))
    own, foreign = identities
    own_accounts = sql(
        "SELECT id FROM orbit_ad_account WHERE tenant_id=%s AND owner_user_id=%s ORDER BY id",
        (tenant, own[2]),
        True,
    )
    assert len(own_accounts) == 2
    own_account = own_accounts[0][0]
    own_agent = import_reference("BUSINESS_AGENT", data_owner_user_ids=[owner, own[2]])
    own_product = import_reference(
        "PRODUCT", allowed_agent_ids=[own_agent], data_owner_user_ids=[owner, own[2]]
    )
    channel_cap = cap("/api/v1/channels/capabilities")
    own_channel = checked(
        client.post(
            "/api/v1/channels",
            headers=write_headers(channel_cap["csrf_token"]),
            json={
                "ownership": {"owner_team_id": team, "data_owner_user_ids": [owner, own[2]]},
                "code": "READ_ONLY_" + uuid4().hex,
                "name": "仅规则读取可见的当前渠道",
                "product_id": own_product,
                "agent_id": own_agent,
                "type": "WEBSITE",
                "media": "META",
                "url": "https://example.com/channel-read-only-test",
                "status": "ENABLED",
            },
        ),
        201,
    )
    save(own_account, own_channel["id"])
    # 尚未授予accounts.read；三类候选只凭rules.read，且必须返回本人规则实际引用。
    assert (
        checked(client.get("/api/v1/channels", headers=own[5]), 403)["code"] == "PERMISSION_DENIED"
    )
    assert (
        checked(client.get(path(own_account), headers=own[5]), 403)["code"] == "PERMISSION_DENIED"
    )
    own_rules = checked(client.get("/api/v1/rules", headers=own[5]), 200)["items"]
    assert own_rules and all(rule["ownership"]["owner_user_id"] == own[2] for rule in own_rules)
    expected = {
        "OPERATOR": {own[2]},
        "METRIC_PROFILE": {rule["metric_profile_id"] for rule in own_rules},
        "CHANNEL": {own_channel["id"]},
    }
    for kind, ids in expected.items():
        result = checked(
            client.get("/api/v1/rules/list-filter-options", headers=own[5], params={"kind": kind}),
            200,
        )
        assert {item["id"] for item in result["items"]} == ids and result["next_cursor"] is None
    cases.append(CASES[9])

    role_cap = cap("/api/v1/roles/capabilities")
    read_role = checked(
        client.post(
            "/api/v1/roles",
            headers=write_headers(role_cap["csrf_token"]),
            json={
                "name": "渠道关联账户只读-" + uuid4().hex[:8],
                "menu_codes": ["accounts"],
                "permission_codes": ["accounts.read"],
            },
        ),
        201,
    )
    native_role = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, read_role["id"]),
        True,
    )[0][0]
    sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (own[0], native_role))
    # 外租户身份必须有其自身租户的读取角色及完整业务初始化，避免用403/503冒充跨租户404。
    foreign_role = sql(
        "SELECT r.id,r.native_role_id FROM orbit_business_role r JOIN sys_user_role ur "
        "ON ur.role_id=r.native_role_id WHERE r.tenant_id=%s AND ur.user_id=%s",
        (foreign[3], foreign[0]),
        True,
    )[0]
    sql(
        "INSERT INTO orbit_business_role_menu(tenant_id,role_id,menu_code) "
        "VALUES(%s,%s,'accounts')",
        (foreign[3], foreign_role[0]),
    )
    sql(
        "INSERT INTO orbit_business_role_action(tenant_id,role_id,permission_code) "
        "VALUES(%s,%s,'accounts.read')",
        (foreign[3], foreign_role[0]),
    )
    sql(
        "INSERT INTO sys_role_menu(role_id,menu_id) SELECT %s,menu_id "
        "FROM sys_menu WHERE menu_id IN(31010,31011)",
        (foreign_role[1],),
    )
    sql("INSERT INTO orbit_account_clock(tenant_id) VALUES(%s)", (foreign[3],))
    sql("INSERT INTO orbit_reference_clock(tenant_id) VALUES(%s)", (foreign[3],))
    current_headers = []
    for identity in identities:
        login = checked(
            fixture_login(client, cache, {"username": identity[1], "password": password}), 200
        )
        h_read = {"Authorization": "Bearer " + login["token"]}
        info = checked(client.get("/getInfo", headers=h_read), 200)
        assert (
            "accounts.read" in info["permissions"] and "accounts.assign" not in info["permissions"]
        )
        current_headers.append(h_read)
    own_headers, foreign_headers = current_headers
    own_read = checked(client.get(path(own_account), headers=own_headers), 200)
    assert own_read == {
        "account_id": own_account,
        "channel_id": own_channel["id"],
        "revision": cap(path(own_account))["revision"],
        "csrf_token": None,
    }
    cases.append(CASES[10])
    counts = [sql("SELECT COUNT(*) FROM " + t, rows=True)[0][0] for t in table_names]
    root_cap = cap(path(own_account))
    denied = checked(
        client.put(
            path(own_account),
            headers=own_headers
            | {
                "X-CSRF-Token": root_cap["csrf_token"],
                "Idempotency-Key": str(uuid4()),
                "If-Match": f'"{own_read["revision"]}"',
            },
            json={"channel_id": None, "reason": "只读身份必须拒绝写入"},
        ),
        403,
    )
    assert denied["code"] == "PERMISSION_DENIED"
    assert checked(client.get(path(own_account), headers=own_headers), 200) == own_read
    assert counts == [sql("SELECT COUNT(*) FROM " + t, rows=True)[0][0] for t in table_names]
    cases.append(CASES[11])
    alien = checked(client.get(path(own_account), headers=foreign_headers), 404)
    assert alien["code"] == "NOT_FOUND" and "channel_id" not in alien
    # 本租户外人同样不可读；外租户规则候选不能泄漏本租户真实名称或ID。
    assert checked(client.get(path(accounts[0]), headers=own_headers), 404)["code"] == "NOT_FOUND"
    for kind in expected:
        result = checked(
            client.get(
                "/api/v1/rules/list-filter-options", headers=foreign_headers, params={"kind": kind}
            ),
            200,
        )
        assert result["items"] == [] and result["next_cursor"] is None
    cases.append(CASES[12])
    return {
        "marker": marker,
        "account_id": accounts[0],
        "channels": [{"id": c["id"], "name": c["name"]} for c in channels[:4]],
        "rule_count": 21,
        "checks_executed": len(CASES),
        "real_platform_calls": False,
    }
