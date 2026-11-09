"""投放D1真实MySQL/HTTP专项，仅主线孤立UUID数据库串行调用。"""

import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor

from fixture_login import fixture_login

LAUNCH_DRAFT_TEMPLATE_CASES = [
    "pythonLaunchDraftOriginalCreatePersistsImmutableVersion",
    "pythonLaunchDraftNestedTreeRoundtripNeverMeansValidated",
    "pythonLaunchDraftCasReplayNoopAndStaleVersion",
    "pythonLaunchStrictStructureFieldPayloadAndUnknownDependenciesAtomic",
    "pythonLaunchConcurrentCasOnlyOneWriteCommits",
    "pythonLaunchAuditFailureRollsBackPlanVersionClockKeyOutbox",
    "pythonTemplateNfcOwnerUniqueNameConflictWithoutOverwrite",
    "pythonTemplateDefaultTeamRecipientsFrozenAndNotEditableByRecipient",
    "pythonTemplateApplyNewDraftStripsReferencesAndClonesWholeTree",
    "pythonTemplateArchiveCasAndImmutableAppliedPlan",
    "pythonLaunchUserPeerManagerAndForeignTenantScope",
    "pythonLaunchSuccessfulKeyReplayRechecksCurrentReadAndNewWritesOriginalAction",
    "pythonTemplateForeignOrMixedRecipientsRejectWholeTransaction",
    "pythonLaunchOwnerOptionsOwnOrExplicitManagedNeverWholeHomeTeam",
    "pythonLaunchOwnerOptionsRevocationAndActorTeamChangeAreCurrent",
    "pythonLaunchCursorFilterWatermarkAndFullOriginalPage",
]

TABLES = (
    "orbit_launch_clock",
    "orbit_launch_plan",
    "orbit_launch_plan_version",
    "orbit_launch_plan_reference",
    "orbit_launch_template",
    "orbit_launch_template_recipient",
    "orbit_launch_template_version",
    "orbit_launch_idempotency",
    "orbit_launch_event",
    "orbit_launch_outbox",
    "orbit_launch_name_sequence",
    "orbit_launch_name_reservation",
    "orbit_launch_name_item",
    "orbit_launch_allocation",
    "orbit_launch_allocation_item",
)


def snapshot(admin):
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", cursor.fetchone()[0])
        result = []
        for table in TABLES:
            cursor.execute("SELECT * FROM " + table)
            result.append(tuple(sorted(cursor.fetchall(), key=repr)))
        return tuple(result)


def assert_status(response, expected):
    if response.status_code != expected:
        print(
            f"LAUNCH_D1 expected_status={expected} actual_status={response.status_code}", flush=True
        )
    assert response.status_code == expected
    return response.json()


def draft(owner):
    return {
        "name": "草稿" + uuid.uuid4().hex,
        "ownership": {"owner_user_id": owner["id"], "owner_team_id": owner["team"]},
        "account_ids": [],
        "channel_id": None,
        "campaigns": [],
        "identity_bindings": [],
        "asset_ids": [],
        "allow_repeat": False,
        "activate_after_create": False,
        "execution_mode": "META_API",
    }


def tree():
    return [
        {
            "local_id": str(uuid.uuid4()),
            "copies": 2,
            "objective": "OUTCOME_SALES",
            "buying_type": "AUCTION",
            "special_ad_categories": [],
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "budget": {
                "owner": "CAMPAIGN",
                "type": "DAILY",
                "amount": "12.340000",
                "currency": "USD",
                "spend_cap": None,
            },
            "adsets": [
                {
                    "local_id": str(uuid.uuid4()),
                    "copies": 3,
                    "name": "组",
                    "budget": None,
                    "country_codes": ["US", "CN"],
                    "age_min": 18,
                    "age_max": 65,
                    "locales": ["6"],
                    "placements": "AUTO",
                    "optimization_goal": "OFFSITE_CONVERSIONS",
                    "billing_event": "IMPRESSIONS",
                    "start_time": "2027-01-01T00:00:00+08:00",
                    "end_time": None,
                    "ads": [
                        {
                            "local_id": str(uuid.uuid4()),
                            "copies": 4,
                            "name": "广告",
                            "title": "标题",
                            "body": "第一行\n第二行",
                            "description": "",
                            "url": "https://example.com/landing",
                            "url_tags": "source=orbit&campaign=test",
                            "cta": "LEARN_MORE",
                            "asset_type": "IMAGE",
                        }
                    ],
                }
            ],
        }
    ]


def run_launch_draft_template_checks(client, admin, headers, fixture, password, cache, cases):
    snapshot(admin)
    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, root_id, root_team = cursor.fetchone()
        cursor.execute(
            "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE tenant_id<>%s LIMIT 1",
            (tenant,),
        )
        foreign_tenant, foreign_owner, foreign_team = cursor.fetchone()
    root = {"id": root_id, "team": root_team}
    manager, user, unmanaged, peer = fixture["users"][:4]

    def head(identity=headers, revision=None, key=None, templates=False):
        caps = assert_status(
            client.get(
                "/api/v1/templates/capabilities"
                if templates
                else "/api/v1/launch-plans/capabilities",
                headers=identity,
            ),
            200,
        )
        assert str(uuid.UUID(caps["actor_user_id"])) == caps["actor_user_id"]
        assert str(uuid.UUID(caps["actor_team_id"])) == caps["actor_team_id"]
        assert isinstance(caps["actor_label"], str) and caps["actor_label"].strip()
        assert not {"email", "phone", "password"} & set(caps)
        return (
            identity
            | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": key or str(uuid.uuid4())}
            | ({"If-Match": f'"{revision}"'} if revision else {})
        )

    def create(body, identity=headers, write=None):
        return client.post("/api/v1/launch-plans", json=body, headers=write or head(identity))

    def template(body, identity=headers):
        return client.post("/api/v1/templates", json=body, headers=head(identity, templates=True))

    original = draft(root)
    create_head = head()
    first = assert_status(create(original, write=create_head), 201)
    assert first["state"] == "DRAFT" and first["revision"] == 1
    assert set(first) == set(original) | {"id", "revision", "state", "created_at", "updated_at"}
    assert (
        assert_status(client.get("/api/v1/launch-plans/" + first["id"], headers=headers), 200)
        == first
    )
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT revision,payload_json FROM orbit_launch_plan_version "
            "WHERE tenant_id=%s AND plan_id=%s",
            (tenant, first["id"]),
        )
        version, payload = cursor.fetchone()
        assert version == 1 and json.loads(payload) == original
    cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[0])

    nested = draft(root) | {
        "campaigns": tree(),
        "workflow_version": "draft-only",
        "adapter_version": "draft-only",
        "profile_binding_ids": [],
    }
    saved = assert_status(create(nested), 201)
    assert saved["campaigns"] == nested["campaigns"] and saved["state"] == "DRAFT"
    assert not any(field in saved for field in ("valid", "hash", "task_id"))
    cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[1])

    updated_body = original | {"name": "实际修改" + uuid.uuid4().hex}
    update_head = head(revision=1)
    path = "/api/v1/launch-plans/" + first["id"]
    updated = assert_status(client.put(path, headers=update_head, json=updated_body), 200)
    assert updated["revision"] == 2 and updated["updated_at"] >= first["updated_at"]
    assert assert_status(client.put(path, headers=update_head, json=updated_body), 200) == updated
    nochange = assert_status(client.put(path, headers=head(revision=2), json=updated_body), 200)
    assert nochange == updated
    before = snapshot(admin)
    assert_status(client.put(path, headers=head(revision=1), json=original), 409)
    assert snapshot(admin) == before
    assert assert_status(create(original, write=create_head), 201) == first
    cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[2])

    invalids = [
        (original | {"unknown": True}, 400),
        (original | {"allow_repeat": "false"}, 400),
        (original | {"name": "😀" * 101}, 422),
        (original | {"account_scope_snapshot_id": str(uuid.uuid4())}, 404),
    ]
    invalids.extend(
        (
            original | {"ownership": original["ownership"] | {"owner_user_id": identifier}},
            422,
        )
        for identifier in (
            root_id.replace("-", ""),
            "{" + root_id + "}",
            "urn:uuid:" + root_id,
        )
    )
    for body, status in invalids:
        before = snapshot(admin)
        assert_status(create(body), status)
        assert snapshot(admin) == before
    oversized = json.dumps(original | {"name": "x" * (5 * 1024 * 1024)}).encode()
    before = snapshot(admin)
    assert_status(
        client.post(
            "/api/v1/launch-plans",
            headers=head() | {"Content-Type": "application/json"},
            content=oversized,
        ),
        413,
    )
    assert snapshot(admin) == before
    cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[3])

    parallel = assert_status(create(draft(root)), 201)
    parallel_path = "/api/v1/launch-plans/" + parallel["id"]
    requests = [(head(revision=1), draft(root)) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda item: client.put(parallel_path, headers=item[0], json=item[1]), requests
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 409]
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM orbit_launch_plan_version WHERE tenant_id=%s AND plan_id=%s",
            (tenant, parallel["id"]),
        )
        assert cursor.fetchone()[0] == 2
    cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[4])

    failure_head, failure_body = head(), draft(root)
    with admin.cursor() as cursor:
        cursor.execute(
            "CREATE TRIGGER fixture_launch_failure BEFORE INSERT ON orbit_launch_event "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture rejection'"
        )
    try:
        before = snapshot(admin)
        failed = create(failure_body, write=failure_head)
        assert_status(failed, 503)
        assert "fixture rejection" not in failed.text and snapshot(admin) == before
    finally:
        with admin.cursor() as cursor:
            cursor.execute("DROP TRIGGER fixture_launch_failure")
    assert_status(create(failure_body, write=failure_head), 201)
    cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[5])

    template_body = {
        "name": "e\u0301" + uuid.uuid4().hex,
        "description": "原配置模板",
        "visibility": "PRIVATE",
        "recipient_user_ids": [],
        "campaigns": tree(),
    }
    saved_template = assert_status(template(template_body), 201)
    assert saved_template["name"].startswith("é")
    before = snapshot(admin)
    assert_status(template(template_body | {"name": saved_template["name"]}), 409)
    assert snapshot(admin) == before
    cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[6])

    # 专项人员只挂当前新角色，结束恢复原角色行，避免旧功能角色并集掩盖撤权检查。
    role_caps = assert_status(client.get("/api/v1/roles/capabilities", headers=headers), 200)
    permissions = [
        "launch." + action for action in ("read", "create", "edit", "execute", "publish")
    ] + ["templates." + action for action in ("read", "create", "edit", "share", "archive")]
    role = assert_status(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": role_caps["csrf_token"], "Idempotency-Key": str(uuid.uuid4())},
            json={
                "name": "投放D1" + uuid.uuid4().hex[:10],
                "menu_codes": ["launch"],
                "permission_codes": permissions,
            },
        ),
        201,
    )
    old_roles = {}
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role["id"]),
        )
        native_role = cursor.fetchone()[0]
        for actor in (manager, user, peer, unmanaged):
            cursor.execute("SELECT role_id FROM sys_user_role WHERE user_id=%s", (actor["native"],))
            old_roles[actor["native"]] = [row[0] for row in cursor.fetchall()]
            cursor.execute("DELETE FROM sys_user_role WHERE user_id=%s", (actor["native"],))
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (actor["native"], native_role),
            )
    try:
        identities = {}
        for actor in (manager, user, peer):
            logged = fixture_login(client, cache, {"username": actor["name"], "password": password})
            token = assert_status(logged, 200)["token"]
            identities[actor["id"]] = {"Authorization": "Bearer " + token}
        user_headers, manager_headers, peer_headers = [
            identities[actor["id"]] for actor in (user, manager, peer)
        ]
        team_body = template_body | {
            "name": "TEAM冻结" + uuid.uuid4().hex,
            "visibility": "TEAM",
            "recipient_user_ids": [],
        }
        team_template = assert_status(template(team_body, user_headers), 201)
        assert (
            user["id"] in team_template["recipient_user_ids"]
            and peer["id"] in team_template["recipient_user_ids"]
        )
        shared_path = "/api/v1/templates/" + team_template["id"]
        assert_status(client.get(shared_path, headers=peer_headers), 200)
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                (user["team"], tenant, unmanaged["id"]),
            )
        try:
            new_member = assert_status(
                fixture_login(client, cache, {"username": unmanaged["name"], "password": password}),
                200,
            )
            assert_status(
                client.get(
                    shared_path,
                    headers={"Authorization": "Bearer " + new_member["token"]},
                ),
                404,
            )
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                    (unmanaged["team"], tenant, unmanaged["id"]),
                )
        before = snapshot(admin)
        assert_status(
            client.put(
                shared_path, headers=head(peer_headers, revision=1, templates=True), json=team_body
            ),
            403,
        )
        assert snapshot(admin) == before
        cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[7])

        apply_value = {
            "ownership": {"owner_user_id": peer["id"], "owner_team_id": peer["team"]},
            "reason": "共享模板生成真实草稿",
        }
        apply_head = head(peer_headers, revision=1, templates=True)
        applied = assert_status(
            client.post(shared_path + "/apply", headers=apply_head, json=apply_value), 201
        )
        assert (
            applied["account_ids"] == applied["asset_ids"] == applied["identity_bindings"] == []
            and applied["channel_id"] is None
        )
        assert applied["state"] == "DRAFT" and applied["activate_after_create"] is False
        old_ids = [
            team_template["campaigns"][0]["local_id"],
            team_template["campaigns"][0]["adsets"][0]["local_id"],
            team_template["campaigns"][0]["adsets"][0]["ads"][0]["local_id"],
        ]
        new_ids = [
            applied["campaigns"][0]["local_id"],
            applied["campaigns"][0]["adsets"][0]["local_id"],
            applied["campaigns"][0]["adsets"][0]["ads"][0]["local_id"],
        ]
        assert not set(old_ids) & set(new_ids) and len(set(new_ids)) == 3
        assert (
            assert_status(
                client.post(shared_path + "/apply", headers=apply_head, json=apply_value), 201
            )
            == applied
        )
        cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[8])

        archived = assert_status(
            client.post(
                shared_path + "/archive",
                headers=head(user_headers, revision=1, templates=True),
                json={"reason": "模板已停用"},
            ),
            200,
        )
        assert archived["state"] == "ARCHIVED" and archived["revision"] == 2
        assert_status(
            client.post(
                shared_path + "/apply",
                headers=head(peer_headers, revision=2, templates=True),
                json=apply_value,
            ),
            409,
        )
        assert (
            assert_status(
                client.get("/api/v1/launch-plans/" + applied["id"], headers=peer_headers), 200
            )
            == applied
        )
        cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[9])

        personal_body = draft(user)
        personal_head = head(user_headers)
        personal = assert_status(create(personal_body, user_headers, personal_head), 201)
        assert_status(
            client.get("/api/v1/launch-plans/" + personal["id"], headers=peer_headers), 404
        )
        assert_status(
            client.get("/api/v1/launch-plans/" + personal["id"], headers=manager_headers), 200
        )
        before = snapshot(admin)
        assert_status(create(draft(peer), user_headers), 403)
        assert_status(create(draft({"id": foreign_owner, "team": foreign_team}), headers), 422)
        assert snapshot(admin) == before
        # 真正存在的另一租户对象，不能用随机不存在UUID冒充跨租户验证。
        foreign_id = str(uuid.uuid4())
        foreign_body = draft({"id": foreign_owner, "team": foreign_team})
        with admin.cursor() as cursor:
            cursor.execute(
                """INSERT INTO orbit_launch_plan(tenant_id,id,owner_user_id,owner_team_id,
                channel_id,name,state,revision,payload_json,payload_hash,payload_bytes,
                account_count,asset_count,created_at,updated_at)
                VALUES(%s,%s,%s,%s,NULL,%s,'DRAFT',1,%s,%s,%s,0,0,
                UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))""",
                (
                    foreign_tenant,
                    foreign_id,
                    foreign_owner,
                    foreign_team,
                    foreign_body["name"],
                    json.dumps(foreign_body),
                    "f" * 64,
                    len(json.dumps(foreign_body).encode()),
                ),
            )
        assert_status(client.get("/api/v1/launch-plans/" + foreign_id, headers=user_headers), 404)
        assert_status(client.get("/api/v1/launch-plans/" + foreign_id, headers=headers), 404)
        assert_status(
            client.put(
                "/api/v1/launch-plans/" + foreign_id,
                headers=head(user_headers, revision=1),
                json=personal_body,
            ),
            404,
        )
        cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[10])

        with admin.cursor() as cursor:
            cursor.execute("SELECT menu_id FROM sys_menu WHERE perms='launch.create'")
            create_menu = cursor.fetchone()[0]
            cursor.execute(
                "DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=%s",
                (native_role, create_menu),
            )
        try:
            before = snapshot(admin)
            # 原API语义：旧成功键是当前可读结果；撤创建动作只阻断新的业务意图。
            replay = assert_status(create(personal_body, user_headers, personal_head), 201)
            assert replay["id"] == personal["id"]
            assert snapshot(admin) == before
            assert_status(create(personal_body, user_headers), 403)
            assert snapshot(admin) == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)",
                    (native_role, create_menu),
                )
        cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[11])

        mixed = template_body | {
            "name": "不能部分共享" + uuid.uuid4().hex,
            "visibility": "TEAM",
            "recipient_user_ids": [user["id"], foreign_owner],
        }
        before = snapshot(admin)
        assert_status(template(mixed, user_headers), 422)
        assert snapshot(admin) == before
        cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[12])

        def owners(identity):
            items, after = [], None
            while True:
                result = assert_status(
                    client.get(
                        "/api/v1/launch-plans/ownership-options",
                        headers=identity,
                        params={"page_size": 20} | ({"cursor": after} if after else {}),
                    ),
                    200,
                )
                items.extend(result["items"])
                after = result["next_cursor"]
                if not after:
                    return items

        assert {row["id"] for row in owners(user_headers)} == {user["id"]}
        manager_candidates = owners(manager_headers)
        manager_ids = {row["id"] for row in manager_candidates}
        assert {manager["id"], user["id"], peer["id"]} <= manager_ids
        assert unmanaged["id"] not in manager_ids
        assert all(set(row) == {"id", "name", "team_id", "team_name"} for row in manager_candidates)
        cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[13])

        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT menu_id FROM sys_menu WHERE perms IN ('launch.create','launch.edit')"
            )
            owner_actions = [row[0] for row in cursor.fetchall()]
            assert len(owner_actions) == 2
            for action in owner_actions:
                cursor.execute(
                    "DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=%s",
                    (native_role, action),
                )
        try:
            before = snapshot(admin)
            assert_status(
                client.get("/api/v1/launch-plans/ownership-options", headers=user_headers), 403
            )
            assert snapshot(admin) == before
        finally:
            with admin.cursor() as cursor:
                for action in owner_actions:
                    cursor.execute(
                        "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)",
                        (native_role, action),
                    )
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                (user["team"], tenant, manager["id"]),
            )
        try:
            current_caps = assert_status(
                client.get("/api/v1/launch-plans/capabilities", headers=manager_headers), 200
            )
            assert current_caps["actor_team_id"] == user["team"]
            assert (
                next(row for row in owners(manager_headers) if row["id"] == manager["id"])[
                    "team_id"
                ]
                == user["team"]
            )
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                    (manager["team"], tenant, manager["id"]),
                )
        cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[14])
    finally:
        with admin.cursor() as cursor:
            for native, roles in old_roles.items():
                cursor.execute("DELETE FROM sys_user_role WHERE user_id=%s", (native,))
                for existing in roles:
                    cursor.execute(
                        "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                        (native, existing),
                    )

    prefix = "投放分页" + uuid.uuid4().hex
    for index in range(21):
        assert_status(create(draft(root) | {"name": prefix + str(index)}), 201)
    page = assert_status(
        client.get("/api/v1/launch-plans", headers=headers, params={"q": prefix, "page_size": 20}),
        200,
    )
    assert (
        len(page["items"]) == 20
        and page["next_cursor"]
        and all("campaigns" in row for row in page["items"])
    )
    next_page = assert_status(
        client.get(
            "/api/v1/launch-plans",
            headers=headers,
            params={"q": prefix, "page_size": 20, "cursor": page["next_cursor"]},
        ),
        200,
    )
    assert len(next_page["items"]) == 1 and next_page["next_cursor"] is None
    assert not {row["id"] for row in page["items"]} & {row["id"] for row in next_page["items"]}
    assert_status(
        client.get(
            "/api/v1/launch-plans",
            headers=headers,
            params={"q": prefix + "changed", "page_size": 20, "cursor": page["next_cursor"]},
        ),
        409,
    )
    assert_status(create(draft(root)), 201)
    assert_status(
        client.get(
            "/api/v1/launch-plans",
            headers=headers,
            params={"q": prefix, "page_size": 20, "cursor": page["next_cursor"]},
        ),
        409,
    )
    cases.append(LAUNCH_DRAFT_TEMPLATE_CASES[15])
