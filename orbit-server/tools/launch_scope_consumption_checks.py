"""A025→投放真实范围消费；仅主线孤立UUID库串行，不外发广告。"""

import json
import re
from uuid import uuid4

from launch_draft_template_checks import assert_status, draft, snapshot, tree

LAUNCH_SCOPE_CONSUMPTION_CASES = [
    "pythonLaunchScopePersistsActualIdsAndImmutableProvenanceWithEditableOriginalPlan",
    "pythonLaunchScopeOriginalIntentReplayDistinguishesDifferentSnapshotsSameIds",
    "pythonLaunchScopeFiveHundredAcceptedFiveHundredOneAndExpandedOverflowAtomic",
    "pythonLaunchScopeOrdinaryRenameKeepsFrozenSelectionAndReadsCurrentRevision",
    "pythonLaunchScopeOwnerTeamCurrencyAndUnbindDriftRejectWholePlan",
    "pythonLaunchScopeForeignCreatorTenantAndListCursorCannotBeConsumed",
    "pythonLaunchScopeSuccessfulReplayRequiresCurrentPlanReadAndNewWritesRecheckSources",
    "pythonLaunchScopeAuditRollbackAndUnknownIdentityRemainFailClosed",
    "pythonLaunchScopeActualDeadlockRetryRetainsOriginalRequestAndFrozenSelection",
    "pythonLaunchScopeActualTargetOwnerMustAlsoHaveCurrentAccountsRead",
]


def run_launch_scope_consumption_checks(client, admin, headers, fixture, cases):
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", cursor.fetchone()[0])
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    accounts = sorted(str(uuid4()) for _ in range(501))
    with admin.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO orbit_ad_account
        (tenant_id,id,external_id,name,name_prefix,owner_user_id,owner_team_id,currency,
        timezone_id,auth_status,account_status,value_json,details_json,bound_at,created_at)
        VALUES(%s,%s,%s,'范围消费账户','范围消费账户',%s,%s,'USD','Asia/Shanghai',
        'AUTHORIZED','ACTIVE','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))""",
            [
                (tenant, identifier, str(10**25 + uuid4().int % 10**25), owner, team)
                for identifier in accounts
            ],
        )

    def head(revision=None, key=None):
        caps = assert_status(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)
        return (
            headers
            | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": key or str(uuid4())}
            | ({"If-Match": f'"{revision}"'} if revision is not None else {})
        )

    def scope(ids):
        caps = assert_status(
            client.get("/api/v1/scope-snapshots/capabilities", headers=headers), 200
        )
        return assert_status(
            client.post(
                "/api/v1/scope-snapshots",
                headers=headers
                | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": str(uuid4())},
                json={"mode": "IDS", "account_ids": ids, "filter": None},
            ),
            201,
        )

    def body(frozen, **changes):
        return (
            draft({"id": owner, "team": team})
            | {"account_scope_snapshot_id": frozen["id"], "campaigns": tree()}
            | changes
        )

    def create(value, write=None):
        return client.post("/api/v1/launch-plans", headers=write or head(), json=value)

    def denied(value, status, write=None, code=None):
        before = snapshot(admin)
        response = create(value, write)
        assert response.status_code == status
        if code:
            assert response.json()["code"] == code
        assert snapshot(admin) == before

    two = scope(accounts[:2])
    command = body(two)
    original_key = head()
    first = assert_status(create(command, original_key), 201)
    assert first["account_ids"] == accounts[:2] and first["account_scope_snapshot_id"] is None
    assert first["state"] == "DRAFT"
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT dependency_json FROM orbit_launch_plan_version "
            "WHERE tenant_id=%s AND plan_id=%s AND revision=1",
            (tenant, first["id"]),
        )
        dependencies = cursor.fetchone()[0]
        dependencies = json.loads(dependencies) if isinstance(dependencies, str) else dependencies
        provenance = dependencies["account_scope_snapshot"]
        assert provenance["scope_id"] == two["id"] and provenance["members_hash"] == two["hash"]
        assert provenance["scope_version"] == two["scope_version"] and provenance["count"] == 2
        assert re.fullmatch(r"[0-9a-f]{64}", provenance["auth_fingerprint"])
        assert set(dependencies["accounts"]) == set(accounts[:2])
    loaded = assert_status(client.get(f"/api/v1/launch-plans/{first['id']}", headers=headers), 200)
    metadata = {"id", "revision", "state", "created_at", "updated_at"}
    editing = {key: value for key, value in loaded.items() if key not in metadata} | {
        "name": "范围消费后可继续编辑"
    }
    edited = assert_status(
        client.put(f"/api/v1/launch-plans/{first['id']}", headers=head(1), json=editing), 200
    )
    assert edited["revision"] == 2 and edited["account_ids"] == accounts[:2]
    cases.append(LAUNCH_SCOPE_CONSUMPTION_CASES[0])

    assert assert_status(create(command, original_key), 201) == first
    same_members = scope(accounts[:2])
    denied(
        command | {"account_scope_snapshot_id": same_members["id"]},
        409,
        original_key,
        "IDEMPOTENCY_CONFLICT",
    )
    denied(
        command | {"account_scope_snapshot_id": None, "account_ids": accounts[:2]},
        409,
        original_key,
        "IDEMPOTENCY_CONFLICT",
    )
    cases.append(LAUNCH_SCOPE_CONSUMPTION_CASES[1])

    five_hundred, too_many = scope(accounts[:500]), scope(accounts)
    small_tree = tree()
    small_tree[0]["copies"] = 1
    small_tree[0]["adsets"][0]["copies"] = 1
    small_tree[0]["adsets"][0]["ads"][0]["copies"] = 1
    large = assert_status(create(body(five_hundred, campaigns=small_tree)), 201)
    assert large["account_ids"] == accounts[:500] and len(large["account_ids"]) == 500
    denied(body(too_many, campaigns=small_tree), 422, code="PLAN_ACCOUNT_LIMIT")
    denied(body(five_hundred), 422, code="PLAN_NODE_LIMIT")
    denied(command | {"account_ids": accounts[:2]}, 422, code="FIELD_VALIDATION_FAILED")
    cases.append(LAUNCH_SCOPE_CONSUMPTION_CASES[2])

    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_ad_account SET name='当前改名',name_prefix='当前改名',"
            "revision=revision+1 "
            "WHERE tenant_id=%s AND id=%s",
            (tenant, accounts[0]),
        )
    renamed = assert_status(create(body(two)), 201)
    assert renamed["account_ids"] == accounts[:2]
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT dependency_json FROM orbit_launch_plan_version "
            "WHERE tenant_id=%s AND plan_id=%s",
            (tenant, renamed["id"]),
        )
        saved = cursor.fetchone()[0]
        saved = json.loads(saved) if isinstance(saved, str) else saved
        assert saved["accounts"][accounts[0]]["revision"] == 2
        cursor.execute(
            "SELECT name,account_revision FROM orbit_account_scope_member "
            "WHERE tenant_id=%s AND snapshot_id=%s AND account_id=%s",
            (tenant, two["id"], accounts[0]),
        )
        assert cursor.fetchone() == ("范围消费账户", 1)
    cases.append(LAUNCH_SCOPE_CONSUMPTION_CASES[3])

    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM orbit_business_user WHERE tenant_id=%s AND id<>%s LIMIT 1",
            (tenant, owner),
        )
        other_owner = cursor.fetchone()[0]
        cursor.execute(
            "SELECT id FROM orbit_business_team WHERE tenant_id=%s AND id<>%s LIMIT 1",
            (tenant, team),
        )
        other_team = cursor.fetchone()[0]
    for column, changed, original, status, code in (
        ("owner_user_id", other_owner, owner, 409, "ACCOUNT_OWNERSHIP_CHANGED"),
        ("owner_team_id", other_team, team, 409, "ACCOUNT_OWNERSHIP_CHANGED"),
        ("currency", "EUR", "USD", 409, "ACCOUNT_OWNERSHIP_CHANGED"),
        ("unbound_at", "2026-01-01 00:00:00", None, 422, "ACCOUNT_SCOPE_MISMATCH"),
    ):
        with admin.cursor() as cursor:
            cursor.execute(
                f"UPDATE orbit_ad_account SET {column}=%s WHERE tenant_id=%s AND id=%s",
                (changed, tenant, accounts[0]),
            )
        try:
            denied(body(two), status, code=code)
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    f"UPDATE orbit_ad_account SET {column}=%s WHERE tenant_id=%s AND id=%s",
                    (original, tenant, accounts[0]),
                )
    wrong_currency = body(two)
    wrong_currency["campaigns"][0]["budget"]["currency"] = "EUR"
    denied(wrong_currency, 422, code="ACCOUNT_CURRENCY_MISMATCH")
    cases.append(LAUNCH_SCOPE_CONSUMPTION_CASES[4])

    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT tenant_id FROM orbit_business_user WHERE tenant_id<>%s LIMIT 1", (tenant,)
        )
        foreign_tenant = cursor.fetchone()[0]
        cursor.execute(
            "SELECT user_id FROM orbit_business_user WHERE tenant_id=%s AND user_id<>1 LIMIT 1",
            (tenant,),
        )
        other_actor = cursor.fetchone()[0]
        foreign_ids = []
        for target_tenant, target_actor in ((foreign_tenant, 1), (tenant, other_actor)):
            identifier = str(uuid4())
            cursor.execute(
                """INSERT INTO orbit_account_scope_snapshot
            (tenant_id,id,actor_id,scope_version,auth_fingerprint,request_key,request_hash,
            request_json,member_count,members_hash,ready,created_at)
            SELECT %s,%s,%s,scope_version,auth_fingerprint,%s,request_hash,request_json,
            member_count,members_hash,0,created_at FROM orbit_account_scope_snapshot
            WHERE tenant_id=%s AND id=%s""",
                (target_tenant, identifier, target_actor, str(uuid4()), tenant, two["id"]),
            )
            cursor.execute(
                "INSERT INTO orbit_account_scope_member "
                "(tenant_id,snapshot_id,account_id,external_id,name,name_prefix,account_revision,"
                "owner_user_id,owner_team_id,currency) "
                "SELECT %s,%s,account_id,external_id,name,name_prefix,account_revision,"
                "owner_user_id,owner_team_id,currency FROM orbit_account_scope_member "
                "WHERE tenant_id=%s AND snapshot_id=%s",
                (target_tenant, identifier, tenant, two["id"]),
            )
            cursor.execute(
                "UPDATE orbit_account_scope_snapshot SET ready=1 WHERE tenant_id=%s AND id=%s",
                (target_tenant, identifier),
            )
            foreign_ids.append(identifier)
    for identifier in foreign_ids + [str(uuid4())]:
        denied(command | {"account_scope_snapshot_id": identifier}, 404)
    members = assert_status(
        client.get(
            f"/api/v1/scope-snapshots/{five_hundred['id']}/members",
            headers=headers,
            params={"page_size": "200"},
        ),
        200,
    )
    assert members["next_cursor"]
    denied(command | {"account_scope_snapshot_id": members["next_cursor"]}, 422)
    cases.append(LAUNCH_SCOPE_CONSUMPTION_CASES[5])

    for menu in (31011, 31022):
        with admin.cursor() as cursor:
            cursor.execute("SELECT status FROM sys_menu WHERE menu_id=%s", (menu,))
            previous_status = cursor.fetchone()[0]
            cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=%s", (menu,))
        try:
            # 已成功的原键不再消费快照或执行创建；新意图仍逐次核验原来源和创建动作。
            before = snapshot(admin)
            assert assert_status(create(command, original_key), 201) == first
            assert snapshot(admin) == before
            denied(command, 403)
            if menu == 31011:
                empty = assert_status(create(draft({"id": owner, "team": team})), 201)
                assert empty["account_ids"] == [] and empty["state"] == "DRAFT"
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE sys_menu SET status=%s WHERE menu_id=%s", (previous_status, menu)
                )
    with admin.cursor() as cursor:
        cursor.execute("SELECT status FROM sys_menu WHERE menu_id=31021")
        read_status = cursor.fetchone()[0]
        cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31021")
    try:
        denied(command, 403, original_key)
    finally:
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_menu SET status=%s WHERE menu_id=31021", (read_status,))
    assert assert_status(create(command, original_key), 201) == first
    cases.append(LAUNCH_SCOPE_CONSUMPTION_CASES[6])

    denied(
        body(two, profile_binding_ids=[str(uuid4())]),
        503,
        code="LAUNCH_IDENTITY_DEPENDENCY_UNAVAILABLE",
    )
    atomic_body, atomic_key = body(two), head()
    before = snapshot(admin)
    with admin.cursor() as cursor:
        cursor.execute("""CREATE TRIGGER fixture_launch_scope_failure
        BEFORE INSERT ON orbit_launch_event
        FOR EACH ROW BEGIN IF NEW.action='plan.create' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='isolated launch scope audit fixture';
        END IF; END""")
    try:
        assert create(atomic_body, atomic_key).status_code == 503
        assert snapshot(admin) == before
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER fixture_launch_scope_failure")
    assert_status(create(atomic_body, atomic_key), 201)
    cases.append(LAUNCH_SCOPE_CONSUMPTION_CASES[7])

    # MEMORY夹具只记录失败次数，不属于业务；首次触发真实1213，外层transaction必须重试原请求。
    retry_body, retry_key = body(two), head()
    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE fixture_launch_scope_retry(id INT PRIMARY KEY,n INT NOT NULL) "
            "ENGINE=MEMORY"
        )
        cursor.execute("INSERT INTO fixture_launch_scope_retry VALUES(1,0)")
        cursor.execute("""CREATE TRIGGER fixture_launch_scope_deadlock
        BEFORE INSERT ON orbit_launch_event
        FOR EACH ROW BEGIN IF NEW.action='plan.create' THEN
        UPDATE fixture_launch_scope_retry SET n=n+1 WHERE id=1;
        IF (SELECT n FROM fixture_launch_scope_retry WHERE id=1)=1 THEN
        SIGNAL SQLSTATE '40001' SET MYSQL_ERRNO=1213,MESSAGE_TEXT='isolated scope retry';
        END IF; END IF; END""")
    try:
        retried = assert_status(create(retry_body, retry_key), 201)
        assert retried["account_ids"] == accounts[:2]
        assert (
            retry_body["account_ids"] == [] and retry_body["account_scope_snapshot_id"] == two["id"]
        )
        with admin.cursor() as cursor:
            cursor.execute("SELECT n FROM fixture_launch_scope_retry WHERE id=1")
            assert cursor.fetchone()[0] == 2
            cursor.execute(
                "SELECT COUNT(*) FROM orbit_launch_plan_version WHERE tenant_id=%s AND plan_id=%s",
                (tenant, retried["id"]),
            )
            assert cursor.fetchone()[0] == 1
        assert assert_status(create(retry_body, retry_key), 201) == retried
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER fixture_launch_scope_deadlock")
            cursor.execute("DROP TABLE fixture_launch_scope_retry")
    cases.append(LAUNCH_SCOPE_CONSUMPTION_CASES[8])
    # 调用者SUPER可读不能替代实际负责人来源读权，仅本隔离库临时角色调整并完整恢复。
    with admin.cursor() as cursor:
        cursor.execute(
            """SELECT b.id,b.user_id,b.team_id FROM orbit_business_user b
        JOIN sys_user u ON u.user_id=b.user_id AND u.status='0' AND u.del_flag='0'
        JOIN orbit_user_scope s ON s.user_id=b.user_id AND s.tenant_id=b.tenant_id AND s.enabled=1
        WHERE b.tenant_id=%s AND b.user_id<>1 AND b.enabled=1 AND b.invited=0
        ORDER BY b.id LIMIT 1""",
            (tenant,),
        )
        target_owner, target_actor, target_team = cursor.fetchone()
        cursor.execute(
            "UPDATE orbit_ad_account SET owner_user_id=%s,owner_team_id=%s "
            "WHERE tenant_id=%s AND id=%s",
            (target_owner, target_team, tenant, accounts[-1]),
        )
        cursor.execute("SELECT role_id FROM sys_user_role WHERE user_id=%s", (target_actor,))
        original_roles = cursor.fetchall()
    target_scope = scope(accounts[-1:])
    try:
        with admin.cursor() as cursor:
            cursor.execute("DELETE FROM sys_user_role WHERE user_id=%s", (target_actor,))
        denied(
            body(
                target_scope,
                ownership={"owner_user_id": target_owner, "owner_team_id": target_team},
            ),
            404,
        )
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DELETE FROM sys_user_role WHERE user_id=%s", (target_actor,))
            if original_roles:
                cursor.executemany(
                    "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                    [(target_actor, row[0]) for row in original_roles],
                )
            cursor.execute(
                "UPDATE orbit_ad_account SET owner_user_id=%s,owner_team_id=%s "
                "WHERE tenant_id=%s AND id=%s",
                (owner, team, tenant, accounts[-1]),
            )
    cases.append(LAUNCH_SCOPE_CONSUMPTION_CASES[9])
    return {"plan_id": first["id"], "scope_id": two["id"], "accepted_500_plan_id": large["id"]}
