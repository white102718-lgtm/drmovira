"""500个不同有效拥有者真实闭环；只供主线专属临时MySQL串行调用。"""

import hashlib
import json
import uuid

from channel_scope_matrix_checks import snapshot
from fixture_login import fixture_login

CHANNEL_OWNERS_500_CASES = [
    "pythonChannel500ActualIdentitiesAndThreePageCandidateScopes",
    "pythonChannel500ReferencePrecheckAndAtomicCommit",
    "pythonChannel500CreateDetailListAndReadableLabels",
    "pythonChannel500ManagerAssignmentAndUserOwnershipIntersection",
    "pythonChannel501AndForeignMixedOwnersRejectWithoutPartialWrites",
    "pythonChannel500DisabledOrMovedMemberRejectsWholeAssignment",
    "pythonChannel500ManagerScopeRevocationBlocksReadAndReplay",
    "pythonChannel500AuditFailureRollsBackOwnersVersionClockAndKey",
    "pythonChannelTeamManagerPersonalCandidateNeverIncludesHomePeers",
]


def assert_exact_owners(actual, expected):
    """不能用相同人数替代精确UUID集合，且不能允许重复抵消遗漏。"""
    assert len(actual) == len(expected) and len(set(actual)) == len(actual)
    assert set(actual) == set(expected)


def owner_fixtures(namespace, team, native_start):
    """500目标成员加1个上限反例控制成员，UUID不同且可追溯到本轮隔离命名空间。"""
    return [
        {
            "id": str(uuid.uuid5(namespace, "owner-" + str(index))),
            "subject": str(uuid.uuid5(namespace, "subject-" + str(index))),
            "team": team,
            "native": native_start + index,
            "name": "owner500_" + namespace.hex[:10] + "_" + str(index),
            "display": f"五百成员{index:03d}",
        }
        for index in range(501)
    ]


def run_channel_owners_500_checks(client, admin, headers, fixture, password, cache, cases):
    snapshot(admin)
    namespace = uuid.uuid4()
    native_start = 2_000_000 + (int(namespace.hex[:6], 16) % 1_000_000) * 1000
    team, team_name = str(uuid.uuid4()), "五百成员团队" + namespace.hex[:8]
    manager = fixture["users"][0]
    members = owner_fixtures(namespace, team, native_start)
    target, control = members[:500], members[500]
    identifiers = [member["id"] for member in target]
    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, _, root_team = cursor.fetchone()
        cursor.execute(
            "SELECT COUNT(*) FROM sys_user WHERE user_id BETWEEN %s AND %s",
            (native_start, native_start + 500),
        )
        assert cursor.fetchone()[0] == 0, "隔离身份native ID区间已有占用，不得覆盖"
        cursor.execute(
            "INSERT INTO orbit_business_team(tenant_id,id,name) VALUES(%s,%s,%s)",
            (tenant, team, team_name),
        )
        for member in members:
            # 只在临时库复制已有夹具密码hash，不读取明文/环境变量，不发送邀请。
            cursor.execute(
                """INSERT INTO sys_user(user_id,user_name,nick_name,password,status,del_flag)
                SELECT %s,%s,%s,password,'0','0' FROM sys_user WHERE user_id=1""",
                (member["native"], member["name"], member["display"]),
            )
            cursor.execute(
                "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time) "
                "VALUES(%s,%s,1,UTC_TIMESTAMP(3))",
                (member["native"], member["subject"]),
            )
            cursor.execute(
                "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role) VALUES(%s,%s,'USER')",
                (member["native"], tenant),
            )
            cursor.execute(
                "INSERT INTO orbit_business_user"
                "(tenant_id,id,user_id,team_id,display_name,invited,created_at) "
                "VALUES(%s,%s,%s,%s,%s,0,UTC_TIMESTAMP(3))",
                (tenant, member["id"], member["native"], team, member["display"]),
            )
        cursor.execute(
            "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,team_id) "
            "VALUES(%s,%s,%s)",
            (tenant, manager["native"], team),
        )
    role_caps = client.get("/api/v1/roles/capabilities", headers=headers).json()
    role = client.post(
        "/api/v1/roles",
        headers=headers
        | {"X-CSRF-Token": role_caps["csrf_token"], "Idempotency-Key": str(uuid.uuid4())},
        json={
            "name": "五百成员验收" + namespace.hex[:8],
            "menu_codes": ["channels"],
            "permission_codes": [
                "channels." + action for action in ("read", "create", "edit", "assign", "archive")
            ],
        },
    )
    assert role.status_code == 201
    role_id = role.json()["id"]
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role_id),
        )
        native_role = cursor.fetchone()[0]
        for actor in (manager, target[0]):
            cursor.execute(
                "INSERT INTO sys_user_role VALUES(%s,%s)", (actor["native"], native_role)
            )

    def login(actor):
        response = fixture_login(client, cache, {"username": actor["name"], "password": password})
        assert response.status_code == 200 and response.json().get("token")
        return {"Authorization": "Bearer " + response.json()["token"]}

    def head(identity=headers, revision=None, key=None):
        caps = client.get("/api/v1/channels/capabilities", headers=identity)
        assert caps.status_code == 200
        return (
            identity
            | {
                "X-CSRF-Token": caps.json()["csrf_token"],
                "Idempotency-Key": key or str(uuid.uuid4()),
            }
            | ({"If-Match": f'"{revision}"'} if revision is not None else {})
        )

    def candidates(identity):
        found, after, pages = [], None, 0
        while True:
            query = {"page_size": 200} | ({"after": after} if after else {})
            response = client.get(
                "/api/v1/channels/ownership-options", headers=identity, params=query
            )
            assert response.status_code == 200
            value = response.json()
            assert len(value["items"]) <= 200
            found.extend(value["items"])
            pages += 1
            after = value["next_after"]
            assert pages <= 10, "小夹具候选分页不能无界循环"
            if not after:
                break
        assert len({row["id"] for row in found}) == len(found)
        return found, pages

    def import_reference(kind, agents=None):
        identifier = str(uuid.uuid4())
        value = {
            "id": identifier,
            "kind": kind,
            "name": ("五百产品" if kind == "PRODUCT" else "五百总代") + namespace.hex[:8],
            "source_key": "owners500-" + identifier,
            "availability": "AVAILABLE",
            "owner_team_id": team,
            "data_owner_user_ids": identifiers,
        } | ({"allowed_agent_ids": agents} if agents else {})
        caps = client.get("/api/v1/reference-catalog-imports/capabilities", headers=headers).json()
        response = client.post(
            "/api/v1/reference-catalog-imports",
            headers=head(),
            json={
                "kind": kind,
                "source": "500有效成员真实专项",
                "reason": "验证原拥有者上限",
                "base_catalog_revision": caps["catalog_revision"],
                "items": [value],
            },
        )
        assert response.status_code == 201 and response.json()["state"] == "VALIDATED"
        frozen = response.json()
        committed = client.post(
            "/api/v1/reference-catalog-imports/" + frozen["id"] + "/commit",
            headers=head(revision=frozen["revision"]),
        )
        assert committed.status_code == 200 and committed.json()["created_count"] == 1
        return value

    def own(ids):
        return {"owner_team_id": team, "data_owner_user_ids": list(ids)}

    def rejected_assign(identity, ids, expected):
        before = snapshot(admin)
        current = client.get(path, headers=headers).json()
        response = client.put(
            path + "/owners",
            headers=head(identity, current["revision"]),
            json={"ownership": own(ids), "reason": "整批拒绝不能部分改分配"},
        )
        assert response.status_code == expected
        assert snapshot(admin) == before

    try:
        manager_headers, user_headers = login(manager), login(target[0])
        # 控制成员暂移到其他团队，使UI最终夹具恰好500人，后续501反例再临时移回。
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                (root_team, tenant, control["id"]),
            )
        for identity in (headers, manager_headers):
            options, pages = candidates(identity)
            assert pages >= 3
            assert_exact_owners(
                [row["id"] for row in options if row["team_id"] == team], identifiers
            )
        user_options, _ = candidates(user_headers)
        assert_exact_owners([row["id"] for row in user_options], [target[0]["id"]])
        cases.append(CHANNEL_OWNERS_500_CASES[0])

        agent = import_reference("BUSINESS_AGENT")
        product = import_reference("PRODUCT", [agent["id"]])
        with admin.cursor() as cursor:
            for identifier in (agent["id"], product["id"]):
                cursor.execute(
                    "SELECT user_id FROM orbit_reference_owner "
                    "WHERE tenant_id=%s AND reference_id=%s",
                    (tenant, identifier),
                )
                assert_exact_owners([row[0] for row in cursor.fetchall()], identifiers)
        cases.append(CHANNEL_OWNERS_500_CASES[1])

        body = {
            "ownership": own(identifiers),
            "code": "OWNERS500_" + namespace.hex[:12],
            "name": "真实500成员渠道",
            "product_id": product["id"],
            "agent_id": agent["id"],
            "type": "APP",
            "media": "META",
            "url": "https://example.com/owners500",
            "status": "ENABLED",
        }
        response = client.post("/api/v1/channels", headers=head(), json=body)
        assert response.status_code == 201
        channel = response.json()
        path = "/api/v1/channels/" + channel["id"]
        for identity in (headers, manager_headers, user_headers):
            current = client.get(path, headers=identity)
            assert current.status_code == 200
            assert_exact_owners(current.json()["ownership"]["data_owner_user_ids"], identifiers)
            listed = client.get("/api/v1/channels", headers=identity, params={"q": body["code"]})
            assert listed.status_code == 200 and len(listed.json()["items"]) == 1
            assert_exact_owners(
                listed.json()["items"][0]["ownership"]["data_owner_user_ids"], identifiers
            )
            labels = client.get(
                "/api/v1/channels/display-labels", headers=identity, params={"ids": channel["id"]}
            )
            assert labels.status_code == 200
            assert_exact_owners(
                [owner["id"] for owner in labels.json()["items"][0]["owners"]], identifiers
            )
            assert all(owner["name"] for owner in labels.json()["items"][0]["owners"])
        cases.append(CHANNEL_OWNERS_500_CASES[2])

        assigned = client.put(
            path + "/owners",
            headers=head(manager_headers, 1),
            json={"ownership": own(identifiers), "reason": "明确管理团队500人"},
        )
        assert assigned.status_code == 200 and assigned.json()["revision"] == 2
        assert_exact_owners(assigned.json()["ownership"]["data_owner_user_ids"], identifiers)
        personal_body = body | {
            "code": "SELF500_" + namespace.hex[:12],
            "ownership": own([target[0]["id"]]),
        }
        assert (
            client.post(
                "/api/v1/channels", headers=head(user_headers), json=personal_body
            ).status_code
            == 201
        )
        before = snapshot(admin)
        assert (
            client.post(
                "/api/v1/channels",
                headers=head(user_headers),
                json=body | {"code": uuid.uuid4().hex},
            ).status_code
            == 403
        )
        assert snapshot(admin) == before
        rejected_assign(user_headers, identifiers[:2], 403)
        cases.append(CHANNEL_OWNERS_500_CASES[3])

        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                (team, tenant, control["id"]),
            )
            cursor.execute(
                "SELECT id FROM orbit_business_user WHERE tenant_id<>%s LIMIT 1", (tenant,)
            )
            foreign_user = cursor.fetchone()[0]
        try:
            for identity in (headers, manager_headers):
                rejected_assign(identity, identifiers + [control["id"]], 422)
                rejected_assign(identity, identifiers[:499] + [foreign_user], 422)
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                    (root_team, tenant, control["id"]),
                )
        cases.append(CHANNEL_OWNERS_500_CASES[4])

        affected = target[-1]
        with admin.cursor() as cursor:
            cursor.execute("UPDATE sys_user SET status='1' WHERE user_id=%s", (affected["native"],))
        try:
            rejected_assign(headers, identifiers, 422)
            rejected_assign(manager_headers, identifiers, 422)
            options, _ = candidates(headers)
            assert affected["id"] not in {row["id"] for row in options}
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE sys_user SET status='0' WHERE user_id=%s", (affected["native"],)
                )
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                (root_team, tenant, affected["id"]),
            )
        try:
            rejected_assign(headers, identifiers, 422)
            rejected_assign(manager_headers, identifiers, 422)
            options, _ = candidates(headers)
            assert affected["id"] not in {row["id"] for row in options if row["team_id"] == team}
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                    (team, tenant, affected["id"]),
                )
        cases.append(CHANNEL_OWNERS_500_CASES[5])

        replay_body = body | {"code": "REPLAY500_" + namespace.hex[:12]}
        replay_head = head(manager_headers)
        replayed = client.post("/api/v1/channels", headers=replay_head, json=replay_body)
        assert replayed.status_code == 201
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE tenant_id=%s "
                "AND manager_user_id=%s AND team_id=%s",
                (tenant, manager["native"], team),
            )
        try:
            before = snapshot(admin)
            assert client.get(path, headers=manager_headers).status_code == 404
            assert (
                client.post("/api/v1/channels", headers=replay_head, json=replay_body).status_code
                == 404
            )
            assert snapshot(admin) == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_business_team_manager SET enabled=1 WHERE tenant_id=%s "
                    "AND manager_user_id=%s AND team_id=%s",
                    (tenant, manager["native"], team),
                )
        cases.append(CHANNEL_OWNERS_500_CASES[6])

        before = snapshot(admin)
        retry_head = head(revision=2)
        with admin.cursor() as cursor:
            cursor.execute(
                "CREATE TRIGGER fixture_channel500_failure BEFORE INSERT ON orbit_reference_event "
                "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture rejection'"
            )
        try:
            assert (
                client.put(
                    path + "/owners",
                    headers=retry_head,
                    json={"ownership": own(identifiers), "reason": "失败后原键500人恢复"},
                ).status_code
                == 503
            )
            assert snapshot(admin) == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute("DROP TRIGGER fixture_channel500_failure")
        restored = client.put(
            path + "/owners",
            headers=retry_head,
            json={"ownership": own(identifiers), "reason": "失败后原键500人恢复"},
        )
        assert restored.status_code == 200 and restored.json()["revision"] == 3
        assert_exact_owners(restored.json()["ownership"]["data_owner_user_ids"], identifiers)
        cases.append(CHANNEL_OWNERS_500_CASES[7])
        manager_options, _ = candidates(manager_headers)
        # TEAM本人可选，不表示其所属但未明确管理的团队全部可选。
        assert_exact_owners(
            [row["id"] for row in manager_options if row["team_id"] == manager["team"]],
            [manager["id"]],
        )
        assert fixture["users"][2]["id"] not in {row["id"] for row in manager_options}
        cases.append(CHANNEL_OWNERS_500_CASES[8])
        return {
            "team_id": team,
            "team_name": team_name,
            "owner_ids": identifiers,
            "owner_digest": hashlib.sha256(json.dumps(sorted(identifiers)).encode()).hexdigest(),
            "product_id": product["id"],
            "product_name": product["name"],
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "channel_id": channel["id"],
            "channel_code": body["code"],
        }
    finally:
        with admin.cursor() as cursor:
            for actor in (manager, target[0]):
                cursor.execute(
                    "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                    (actor["native"], native_role),
                )
            cursor.execute(
                "DELETE FROM orbit_business_team_manager WHERE tenant_id=%s "
                "AND manager_user_id=%s AND team_id=%s",
                (tenant, manager["native"], team),
            )
