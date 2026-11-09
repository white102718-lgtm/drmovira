"""维护动作与数据范围的真实多身份矩阵；只修改运行器专属数据库夹具。"""

import json
import re
import uuid

from fixture_login import fixture_login

REFERENCE_CHANNEL_SCOPE_CASES = [
    "pythonReferenceUserMaintenanceOwnScopeNeverWholeTeam",
    "pythonReferenceManagerOwnAndExplicitTeamScopes",
    "pythonReferenceOwnerTargetIntersectsProductAndAgent",
    "pythonReferencePreviewDetailsDifferencesCommitHideRevokedTeam",
    "pythonReferenceIdempotentReplayRechecksCurrentScope",
    "pythonReferenceMaintenanceActionRevocationIsImmediate",
    "pythonReferenceOwnerTransferAndCasLeaveNoPartialWrites",
    "pythonReferenceActualForeignTenantObjectsRemainInvisible",
]


def run_reference_channel_scope_checks(client, admin, headers, fixture, password, cache, cases):
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", cursor.fetchone()[0])
        cursor.execute("SELECT tenant_id FROM orbit_user_scope WHERE user_id=1")
        tenant = cursor.fetchone()[0]
    root_caps = client.get("/api/v1/roles/capabilities", headers=headers).json()
    role_response = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": root_caps["csrf_token"],
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={
            "name": "引用目录范围验收" + uuid.uuid4().hex[:6],
            "menu_codes": ["system", "channels"],
            "permission_codes": [
                "system.read",
                "system.dictionaries.manage",
                "channels.read",
                "channels.create",
                "channels.edit",
                "channels.assign",
                "channels.archive",
            ],
        },
    )
    assert role_response.status_code == 201, "范围矩阵角色创建失败"
    role_id = role_response.json()["id"]
    manager, user, unmanaged, peer = fixture["users"][:4]
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
            (tenant, role_id),
        )
        native_role = cursor.fetchone()[0]
        for actor in (manager, user):
            cursor.execute(
                "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
                (actor["native"], native_role),
            )

    def login(actor):
        response = fixture_login(client, cache, {"username": actor["name"], "password": password})
        assert response.status_code == 200 and response.json().get("token"), "范围矩阵真实登录失败"
        return {"Authorization": "Bearer " + response.json()["token"]}

    def capabilities(actor_headers):
        response = client.get(
            "/api/v1/reference-catalog-imports/capabilities", headers=actor_headers
        )
        assert response.status_code == 200, "字典维护不能额外要求SUPER_ADMIN"
        return response.json()

    def body(actor, *, kind="BUSINESS_AGENT", owners=None, **changes):
        identifier = str(uuid.uuid4())
        return {
            "id": identifier,
            "kind": kind,
            "name": "范围资料" + identifier[-6:],
            "source_key": "scope-" + identifier,
            "availability": "AVAILABLE",
            "owner_team_id": actor["team"],
            "data_owner_user_ids": owners or [actor["id"]],
            **changes,
        }

    def precheck(actor_headers, rows, *, key=None):
        caps = capabilities(actor_headers)
        payload = {
            "kind": rows[0]["kind"],
            "source": "真实权限矩阵",
            "reason": "验证当前范围交集",
            "base_catalog_revision": caps["catalog_revision"],
            "items": rows,
        }
        write = actor_headers | {
            "X-CSRF-Token": caps["csrf_token"],
            "Idempotency-Key": key or str(uuid.uuid4()),
        }
        return (
            client.post("/api/v1/reference-catalog-imports", headers=write, json=payload),
            payload,
            write,
        )

    def commit(actor_headers, result, *, key=None, revision=None):
        caps = capabilities(actor_headers)
        return client.post(
            f"/api/v1/reference-catalog-imports/{result['id']}/commit",
            headers=actor_headers
            | {
                "X-CSRF-Token": caps["csrf_token"],
                "Idempotency-Key": key or str(uuid.uuid4()),
                "If-Match": f'"{revision or result["revision"]}"',
            },
        )

    def add(actor_headers, rows):
        response, _, _ = precheck(actor_headers, rows)
        assert response.status_code == 201 and response.json()["state"] == "VALIDATED"
        response = commit(actor_headers, response.json())
        assert response.status_code == 200, "合法范围原子提交失败"

    try:
        manager_headers, user_headers = login(manager), login(user)
        own = body(user)
        add(user_headers, [own])
        visible = client.get("/api/v1/reference-catalogs/PRODUCT", headers=user_headers)
        assert visible.status_code == 200
        # 同团队的另一个人不自动属于普通用户的范围。
        denied, _, _ = precheck(user_headers, [body(peer)])
        assert denied.status_code == 403
        denied, _, _ = precheck(user_headers, [body(user, owners=[user["id"], peer["id"]])])
        assert denied.status_code == 403
        denied, _, _ = precheck(user_headers, [body(unmanaged)])
        assert denied.status_code == 403
        cases.append(REFERENCE_CHANNEL_SCOPE_CASES[0])

        managed_agent = body(user, owners=[user["id"], peer["id"]])
        add(manager_headers, [managed_agent])
        personal_agent = body(manager)
        add(manager_headers, [personal_agent])
        denied, _, _ = precheck(manager_headers, [body(unmanaged)])
        assert denied.status_code == 403
        personal_product = body(manager, kind="PRODUCT", allowed_agent_ids=[personal_agent["id"]])
        add(manager_headers, [personal_product])
        own_candidates = client.get(
            "/api/v1/reference-catalogs/PRODUCT",
            headers=manager_headers,
            params={"owner_user_id": manager["id"]},
        )
        assert own_candidates.status_code == 200 and personal_product["id"] in {
            row["value"]["id"] for row in own_candidates.json()["items"]
        }
        cases.append(REFERENCE_CHANNEL_SCOPE_CASES[1])

        peer_product = body(peer, kind="PRODUCT", allowed_agent_ids=[managed_agent["id"]])
        add(manager_headers, [peer_product])
        rejected = client.get(
            "/api/v1/reference-catalogs/BUSINESS_AGENT",
            headers=manager_headers,
            params={"product_id": peer_product["id"], "owner_user_id": user["id"]},
        )
        assert rejected.status_code == 404  # agent对目标可用不等于product对目标可用。
        accepted = client.get(
            "/api/v1/reference-catalogs/BUSINESS_AGENT",
            headers=manager_headers,
            params={"product_id": peer_product["id"], "owner_user_id": peer["id"]},
        )
        assert accepted.status_code == 200 and {
            row["value"]["id"] for row in accepted.json()["items"]
        } == {managed_agent["id"]}
        assert (
            client.get(
                "/api/v1/reference-catalogs/PRODUCT",
                headers=user_headers,
                params={"owner_user_id": peer["id"]},
            ).status_code
            == 403
        )
        # USER能读自己的关联，不能通过无权product得到其他人的总代名称。
        assert (
            client.get(
                "/api/v1/reference-catalogs/BUSINESS_AGENT",
                headers=user_headers,
                params={"product_id": peer_product["id"]},
            ).status_code
            == 404
        )
        cases.append(REFERENCE_CHANNEL_SCOPE_CASES[2])

        pending, _, _ = precheck(manager_headers, [body(peer)])
        assert pending.status_code == 201
        pending = pending.json()
        pending_path = "/api/v1/reference-catalog-imports/" + pending["id"]
        assert client.get(pending_path, headers=user_headers).status_code == 404
        assert client.get(pending_path + "/differences", headers=user_headers).status_code == 404
        assert commit(user_headers, pending).status_code == 404
        with admin.cursor() as cursor:
            cursor.execute(
                """
                UPDATE orbit_business_team_manager SET enabled=0 WHERE
                tenant_id=%s AND manager_user_id=%s AND team_id=%s
                """,
                (tenant, manager["native"], user["team"]),
            )
        try:
            assert client.get(pending_path, headers=manager_headers).status_code == 404
            assert (
                client.get(pending_path + "/differences", headers=manager_headers).status_code
                == 404
            )
            assert commit(manager_headers, pending).status_code == 404
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    """
                UPDATE orbit_business_team_manager SET enabled=1 WHERE
                tenant_id=%s AND manager_user_id=%s AND team_id=%s
                """,
                    (tenant, manager["native"], user["team"]),
                )
        cases.append(REFERENCE_CHANNEL_SCOPE_CASES[3])

        response, payload, write = precheck(manager_headers, [body(peer)])
        assert response.status_code == 201
        result = response.json()
        commit_key = str(uuid.uuid4())
        assert commit(manager_headers, result, key=commit_key).status_code == 200
        with admin.cursor() as cursor:
            cursor.execute(
                """
                UPDATE orbit_business_team_manager SET enabled=0 WHERE
                tenant_id=%s AND manager_user_id=%s AND team_id=%s
                """,
                (tenant, manager["native"], user["team"]),
            )
        try:
            assert (
                client.post(
                    "/api/v1/reference-catalog-imports", headers=write, json=payload
                ).status_code
                == 404
            )
            assert commit(manager_headers, result, key=commit_key).status_code == 404
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    """
                UPDATE orbit_business_team_manager SET enabled=1 WHERE
                tenant_id=%s AND manager_user_id=%s AND team_id=%s
                """,
                    (tenant, manager["native"], user["team"]),
                )
        cases.append(REFERENCE_CHANNEL_SCOPE_CASES[4])

        response, payload, write = precheck(user_headers, [body(user)])
        assert response.status_code == 201
        with admin.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM orbit_business_role_action WHERE tenant_id=%s
                AND role_id=%s AND
                permission_code='system.dictionaries.manage'
                """,
                (tenant, role_id),
            )
        try:
            path = "/api/v1/reference-catalog-imports/" + response.json()["id"]
            assert client.get(path, headers=user_headers).status_code == 403
            assert (
                client.post(
                    "/api/v1/reference-catalog-imports", headers=write, json=payload
                ).status_code
                == 403
            )
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    """
                INSERT INTO
                orbit_business_role_action(tenant_id,role_id,permission_code)
                VALUES(%s,%s,'system.dictionaries.manage')
                """,
                    (tenant, role_id),
                )
        cases.append(REFERENCE_CHANNEL_SCOPE_CASES[5])

        response, _, _ = precheck(manager_headers, [body(peer)])
        result = response.json()
        path = "/api/v1/reference-catalog-imports/" + result["id"]
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                (unmanaged["team"], tenant, peer["id"]),
            )
        try:
            assert client.get(path, headers=manager_headers).status_code == 404
            assert commit(manager_headers, result).status_code == 422
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_business_user SET team_id=%s WHERE tenant_id=%s AND id=%s",
                    (peer["team"], tenant, peer["id"]),
                )
        assert commit(manager_headers, result, revision=99).status_code == 409
        assert commit(manager_headers, result).status_code == 200
        cases.append(REFERENCE_CHANNEL_SCOPE_CASES[6])

        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE tenant_id<>%s LIMIT 1",
                (tenant,),
            )
            foreign_tenant, foreign_user, foreign_team = cursor.fetchone()
            foreign_id = str(uuid.uuid4())
            foreign_item = body({"team": foreign_team, "id": foreign_user})
            foreign_payload = {
                "kind": "BUSINESS_AGENT",
                "source": "另一租户隔离夹具",
                "reason": "不得可见",
                "base_catalog_revision": 0,
                "items": [foreign_item],
            }
            foreign_result = {
                "id": foreign_id,
                "revision": 1,
                "state": "VALIDATED",
                "base_catalog_revision": 0,
                "expires_at": "2099-01-01T00:00:00.000Z",
                "issues": [],
                "created_count": 1,
                "updated_count": 0,
            }
            cursor.execute(
                """
                INSERT INTO
                orbit_reference_import(tenant_id,id,actor_id,team_ids_json,input_json,result_json,state,revision,base_revision,expires_at,created_at)
                VALUES(%s,%s,1,%s,%s,%s,'VALIDATED',1,0,'2099-01-01',UTC_TIMESTAMP(3))
                """,
                (
                    foreign_tenant,
                    foreign_id,
                    json.dumps([foreign_team]),
                    json.dumps(foreign_payload),
                    json.dumps(foreign_result),
                ),
            )
        foreign_path = "/api/v1/reference-catalog-imports/" + foreign_id
        for identity in (headers, manager_headers, user_headers):
            assert client.get(foreign_path, headers=identity).status_code == 404
            assert client.get(foreign_path + "/differences", headers=identity).status_code == 404
            assert commit(identity, foreign_result).status_code == 404
            assert client.get(
                "/api/v1/reference-catalogs/PRODUCT",
                headers=identity,
                params={"owner_user_id": foreign_user},
            ).status_code in {403, 404}
        cases.append(REFERENCE_CHANNEL_SCOPE_CASES[7])
    finally:
        with admin.cursor() as cursor:
            for actor in (manager, user):
                cursor.execute(
                    "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                    (actor["native"], native_role),
                )
