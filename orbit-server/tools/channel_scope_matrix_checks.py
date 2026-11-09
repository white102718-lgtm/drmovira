"""渠道真实租户/归属/撤权矩阵，仅由主线隔离MySQL运行器串行调用。"""

import json
import re
import uuid
from copy import deepcopy

from fixture_login import fixture_login

CHANNEL_SCOPE_MATRIX_CASES = [
    "pythonChannelUserOwnLifecycleAndPeerIsolation",
    "pythonChannelManagerExplicitTeamNeverWholeHomeTeam",
    "pythonChannelForeignTenantReadAndWriteAlwaysInvisible",
    "pythonChannelForeignReferenceAndOwnerRejectedAtomically",
    "pythonChannelActionRevocationBlocksSuccessfulKeyReplay",
    "pythonChannelScopeRevocationBlocksEverySuccessfulKeyReplay",
    "pythonChannelMixedOwnerAssignmentHasNoPartialMutation",
    "pythonChannelReferenceMixedScopeBatchNeverPartiallyCreates",
]

SNAPSHOT_TABLES = (
    "orbit_channel",
    "orbit_channel_owner",
    "orbit_reference_clock",
    "orbit_reference_record",
    "orbit_reference_owner",
    "orbit_reference_product_agent",
    "orbit_reference_import",
    "orbit_reference_event",
    "orbit_reference_idempotency",
)


def request_revision(method, path, revision):
    """创建合同禁止If-Match；停用POST仍必须携带现有业务版本。"""
    return None if method == "POST" and path == "/api/v1/channels" else revision


def assert_denial_status(method, expected, actual):
    """失败只输出固定方法/状态数字，严禁输出URL、正文、响应或认证头。"""
    assert method in {"POST", "PUT"}
    assert type(expected) is int and type(actual) is int
    if actual != expected:
        print(
            f"CHANNEL_SCOPE_DENIAL method={method} "
            f"expected_status={expected} actual_status={actual}",
            flush=True,
        )
    assert actual == expected


def own(actor, owners=None):
    """始终复制拥有者集合，避免对照正文被后续变更污染。"""
    return {
        "owner_team_id": actor["team"],
        "data_owner_user_ids": list(owners if owners is not None else [actor["id"]]),
    }


def write_body(actor, product, agent, **changes):
    return {
        "ownership": own(actor),
        "code": "matrix_" + uuid.uuid4().hex,
        "name": "渠道范围矩阵",
        "product_id": product,
        "agent_id": agent,
        "type": "APP",
        "media": "META",
        "url": "https://example.com/scope#retained",
        "status": "ENABLED",
        **deepcopy(changes),
    }


def snapshot(admin):
    """小型隔离夹具全行快照，拒绝时连正文、关系、时钟、事件与幂等都不得变化。"""
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", cursor.fetchone()[0])
        result = []
        for table in SNAPSHOT_TABLES:
            # 表名是固定代码白名单，不能来自请求。
            cursor.execute("SELECT * FROM " + table)
            result.append(tuple(sorted(cursor.fetchall(), key=repr)))
        return tuple(result)


def run_channel_scope_matrix_checks(client, admin, headers, fixture, password, cache, cases):
    snapshot(admin)  # 任何夹具写入前先校验专属临时数据库。
    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id FROM orbit_user_scope WHERE user_id=1")
        tenant = cursor.fetchone()[0]
        cursor.execute(
            "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE tenant_id<>%s LIMIT 1",
            (tenant,),
        )
        foreign_tenant, foreign_user, foreign_team = cursor.fetchone()
    manager, user, unmanaged, peer = fixture["users"][:4]
    capabilities = client.get("/api/v1/roles/capabilities", headers=headers).json()
    permissions = ["system.read", "system.dictionaries.manage"] + [
        "channels." + action for action in ("read", "create", "edit", "assign", "archive")
    ]
    response = client.post(
        "/api/v1/roles",
        headers=headers
        | {
            "X-CSRF-Token": capabilities["csrf_token"],
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={
            "name": "渠道完整范围" + uuid.uuid4().hex[:8],
            "menu_codes": ["system", "channels"],
            "permission_codes": permissions,
        },
    )
    assert response.status_code == 201
    role_id = response.json()["id"]
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
        result = fixture_login(client, cache, {"username": actor["name"], "password": password})
        assert result.status_code == 200 and result.json().get("token")
        return {"Authorization": "Bearer " + result.json()["token"]}

    def head(identity, *, revision=None, key=None):
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

    def reference(actor, kind="BUSINESS_AGENT", **changes):
        identifier = str(uuid.uuid4())
        return {
            "id": identifier,
            "kind": kind,
            "name": "渠道关联" + identifier[-8:],
            "source_key": "channel-matrix-" + identifier,
            "availability": "AVAILABLE",
            **own(actor),
            **changes,
        }

    def preview(identity, rows):
        caps = client.get("/api/v1/reference-catalog-imports/capabilities", headers=identity)
        assert caps.status_code == 200
        return client.post(
            "/api/v1/reference-catalog-imports",
            headers=identity
            | {
                "X-CSRF-Token": caps.json()["csrf_token"],
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={
                "kind": rows[0]["kind"],
                "source": "渠道多身份验收",
                "reason": "真实权限与原子性",
                "base_catalog_revision": caps.json()["catalog_revision"],
                "items": rows,
            },
        )

    def add_references(actor, owners=None):
        pair = []
        agent = reference(actor, data_owner_user_ids=own(actor, owners)["data_owner_user_ids"])
        product = reference(
            actor,
            "PRODUCT",
            data_owner_user_ids=own(actor, owners)["data_owner_user_ids"],
            allowed_agent_ids=[agent["id"]],
        )
        for row in (agent, product):
            result = preview(headers, [row])
            assert result.status_code == 201 and result.json()["state"] == "VALIDATED"
            result = result.json()
            committed = client.post(
                "/api/v1/reference-catalog-imports/" + result["id"] + "/commit",
                headers=head(headers, revision=result["revision"]),
            )
            assert committed.status_code == 200
            pair.append(row)
        return product["id"], agent["id"]

    def create(identity, body):
        write = head(identity)
        response = client.post("/api/v1/channels", headers=write, json=body)
        assert response.status_code == 201
        return response.json(), write

    def deny(method, path, identity, body, expected, revision=1, write=None):
        before = snapshot(admin)
        response = client.request(
            method,
            path,
            headers=write or head(identity, revision=request_revision(method, path, revision)),
            json=body,
        )
        assert_denial_status(method, expected, response.status_code)
        assert snapshot(admin) == before, "拒绝请求产生了部分业务/审计/幂等写入"

    def invisible(identity, channel, body):
        path = "/api/v1/channels/" + channel["id"]
        assert client.get(path, headers=identity).status_code == 404
        assert client.get(path + "/edit-context", headers=identity).status_code == 404
        labels = client.get(
            "/api/v1/channels/display-labels", headers=identity, params={"ids": channel["id"]}
        )
        assert labels.status_code == 200 and channel["id"] not in labels.text
        listed = client.get("/api/v1/channels", headers=identity, params={"q": body["code"]})
        assert listed.status_code == 200 and not listed.json()["items"]
        deny("PUT", path, identity, body, 404)
        deny(
            "PUT",
            path + "/owners",
            identity,
            {"ownership": body["ownership"], "reason": "不可越权"},
            404,
        )
        deny("POST", path + "/archive", identity, {"reason": "不可越权"}, 404)

    try:
        manager_headers, user_headers = login(manager), login(user)
        product, agent = add_references(user, [user["id"], peer["id"]])
        personal_product, personal_agent = add_references(manager)
        other_product, other_agent = add_references(unmanaged)
        own_body = write_body(user, product, agent)
        mine, _ = create(user_headers, own_body)
        peer_body = write_body(peer, product, agent)
        peer_channel, _ = create(manager_headers, peer_body)
        invisible(user_headers, peer_channel, peer_body)
        expanded = deepcopy(own_body)
        expanded["ownership"] = own(user, [user["id"], peer["id"]])
        deny("POST", "/api/v1/channels", user_headers, expanded, 403)
        deny("PUT", "/api/v1/channels/" + mine["id"], user_headers, expanded, 403)
        path = "/api/v1/channels/" + mine["id"]
        edited = client.put(
            path, headers=head(user_headers, revision=1), json=own_body | {"name": "本人可编辑"}
        )
        assert edited.status_code == 200 and edited.json()["revision"] == 2
        assigned = client.put(
            path + "/owners",
            headers=head(user_headers, revision=2),
            json={"ownership": own(user), "reason": "保留本人"},
        )
        assert assigned.status_code == 200 and assigned.json()["revision"] == 3
        archived = client.post(
            path + "/archive", headers=head(user_headers, revision=3), json={"reason": "本人停用"}
        )
        assert archived.status_code == 200 and archived.json()["url"] == own_body["url"]
        cases.append(CHANNEL_SCOPE_MATRIX_CASES[0])

        create(manager_headers, write_body(manager, personal_product, personal_agent))
        outsider_body = write_body(unmanaged, other_product, other_agent)
        outsider, _ = create(headers, outsider_body)
        invisible(manager_headers, outsider, outsider_body)
        deny("POST", "/api/v1/channels", manager_headers, outsider_body, 403)
        assert (
            client.get(
                "/api/v1/channels/" + peer_channel["id"], headers=manager_headers
            ).status_code
            == 200
        )
        cases.append(CHANNEL_SCOPE_MATRIX_CASES[1])

        # 另一租户夹具由固定SQL建立；被测读写全部经过真实HTTP，不为其伪造登录。
        foreign_actor = {"id": foreign_user, "team": foreign_team}
        foreign_agent = reference(foreign_actor)
        foreign_product = reference(
            foreign_actor, "PRODUCT", allowed_agent_ids=[foreign_agent["id"]]
        )
        foreign_body = write_body(foreign_actor, foreign_product["id"], foreign_agent["id"])
        foreign_channel = {"id": str(uuid.uuid4())}
        with admin.cursor() as cursor:
            for row in (foreign_agent, foreign_product):
                cursor.execute(
                    """INSERT INTO orbit_reference_record
                    (tenant_id,id,kind,source_key,name,availability,owner_team_id,
                    value_json,revision,catalog_revision,updated_at)
                    VALUES(%s,%s,%s,%s,%s,'AVAILABLE',%s,%s,1,1,UTC_TIMESTAMP(3))""",
                    (
                        foreign_tenant,
                        row["id"],
                        row["kind"],
                        row["source_key"],
                        row["name"],
                        foreign_team,
                        json.dumps(row),
                    ),
                )
                cursor.execute(
                    "INSERT INTO orbit_reference_owner VALUES(%s,%s,%s)",
                    (foreign_tenant, row["id"], foreign_user),
                )
            cursor.execute(
                "INSERT INTO orbit_reference_product_agent VALUES(%s,%s,%s)",
                (foreign_tenant, foreign_product["id"], foreign_agent["id"]),
            )
            cursor.execute(
                """INSERT INTO orbit_channel
                (tenant_id,id,code,name,owner_team_id,product_id,agent_id,status,
                value_json,revision,created_at,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,'ENABLED',%s,1,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))""",
                (
                    foreign_tenant,
                    foreign_channel["id"],
                    foreign_body["code"],
                    foreign_body["name"],
                    foreign_team,
                    foreign_product["id"],
                    foreign_agent["id"],
                    json.dumps(foreign_body),
                ),
            )
            cursor.execute(
                "INSERT INTO orbit_channel_owner VALUES(%s,%s,%s)",
                (foreign_tenant, foreign_channel["id"], foreign_user),
            )
        for identity in (headers, manager_headers, user_headers):
            invisible(identity, foreign_channel, foreign_body)
        cases.append(CHANNEL_SCOPE_MATRIX_CASES[2])

        for changes in (
            {"product_id": foreign_product["id"]},
            {"agent_id": foreign_agent["id"]},
            {"ownership": own(foreign_actor)},
        ):
            invalid = write_body(user, product, agent, **changes)
            deny("POST", "/api/v1/channels", headers, invalid, 422)
            deny("PUT", "/api/v1/channels/" + peer_channel["id"], headers, invalid, 422)
        cases.append(CHANNEL_SCOPE_MATRIX_CASES[3])

        replay_body = write_body(peer, product, agent)
        replay_channel, create_head = create(manager_headers, replay_body)
        path = "/api/v1/channels/" + replay_channel["id"]
        intents = [("create", "POST", "/api/v1/channels", replay_body, create_head)]
        for action, method, suffix, body, revision in (
            ("edit", "PUT", "", replay_body | {"name": "重放编辑"}, 1),
            ("assign", "PUT", "/owners", {"ownership": own(peer), "reason": "重放分配"}, 2),
            ("archive", "POST", "/archive", {"reason": "重放停用"}, 3),
        ):
            write = head(manager_headers, revision=revision)
            assert (
                client.request(method, path + suffix, headers=write, json=body).status_code == 200
            )
            intents.append((action, method, path + suffix, body, write))
        for action, method, endpoint, body, write in intents:
            with admin.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM orbit_business_role_action WHERE tenant_id=%s "
                    "AND role_id=%s AND permission_code=%s",
                    (tenant, role_id, "channels." + action),
                )
            try:
                deny(method, endpoint, manager_headers, body, 403, write=write)
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO orbit_business_role_action VALUES(%s,%s,%s)",
                        (tenant, role_id, "channels." + action),
                    )
        cases.append(CHANNEL_SCOPE_MATRIX_CASES[4])

        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_business_team_manager SET enabled=0 WHERE tenant_id=%s "
                "AND manager_user_id=%s AND team_id=%s",
                (tenant, manager["native"], user["team"]),
            )
        try:
            for _, method, endpoint, body, write in intents:
                deny(method, endpoint, manager_headers, body, 404, write=write)
            invisible(manager_headers, peer_channel, peer_body)
        finally:
            with admin.cursor() as cursor:
                cursor.execute(
                    "UPDATE orbit_business_team_manager SET enabled=1 WHERE tenant_id=%s "
                    "AND manager_user_id=%s AND team_id=%s",
                    (tenant, manager["native"], user["team"]),
                )
        cases.append(CHANNEL_SCOPE_MATRIX_CASES[5])

        mixed = {"ownership": own(user, [user["id"], foreign_user]), "reason": "有效与外租户混合"}
        deny("PUT", "/api/v1/channels/" + peer_channel["id"] + "/owners", headers, mixed, 422)
        mixed["ownership"] = own(user, [user["id"], unmanaged["id"]])
        deny(
            "PUT", "/api/v1/channels/" + peer_channel["id"] + "/owners", manager_headers, mixed, 422
        )
        cases.append(CHANNEL_SCOPE_MATRIX_CASES[6])

        # 渠道无批量创建合同；这里验证其依赖的引用导入混合范围整批拒绝。
        for identity, actors in (
            (user_headers, (user, peer)),
            (manager_headers, (peer, unmanaged)),
        ):
            rows = [reference(actor) for actor in actors]
            before = snapshot(admin)
            rejected = preview(identity, rows)
            assert rejected.status_code == 403
            assert snapshot(admin) == before
        cases.append(CHANNEL_SCOPE_MATRIX_CASES[7])
    finally:
        with admin.cursor() as cursor:
            for actor in (manager, user):
                cursor.execute(
                    "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                    (actor["native"], native_role),
                )
