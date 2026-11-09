"""执行机和绑定真实HTTP验收；只允许主运行器的随机隔离库，不连接真实设备。"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

from fixture_login import fixture_login
from metric_fact_schema_checks import MetricFactSqlFixture

ENVIRONMENT_REGISTRY_CASES = [
    "environmentSuperadminRegisterReadAndReplayOfflineUnknown",
    "environmentStrictLocalEndpointAndNoSecretInput",
    "environmentOrdinaryAndTeamAdminCannotManageDespiteGrantedActions",
    "environmentUnboundDeviceInvisibleToOrdinaryUser",
    "environmentBindingCurrentAccountVisibilityWithoutAccountsRead",
    "environmentSharedDeviceDoesNotExposePeerBinding",
    "environmentBindingOwnershipMismatchAndForeignReferencesRejected",
    "environmentAgentUpdateCasReplayAndConcurrentSingleWinner",
    "environmentBoundedPagingFiltersAndWatermarkInvalidation",
    "environmentRegistrationDateUsesShanghaiDayBoundary",
    "environmentBindingTransferHidesOldOwnerUntilAdminRepairs",
    "environmentBindingUnbindReplayAndNoDuplicateAssociation",
    "environmentDeviceRevocationHidesFromUsersAndKeepsAdminRead",
    "environmentAuditOutboxFailureRollsBackEveryWrite",
    "environmentCurrentActionRevocationRejectsSuccessfulReplay",
    "environmentForeignTenantAndUnsupportedProbeRemainClosed",
]


def run_environment_registry_checks(
    client, admin, headers, fixture, password, cache, database, cases
):
    assert admin.host in {"127.0.0.1", "localhost"} and admin.port == 13306
    assert re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    sql_fixture = MetricFactSqlFixture(admin, database)
    tenant = sql_fixture.tenant
    marker = "env_it_" + uuid4().hex[:8]
    root = "/api/v1/execution-agents"
    bindings = "/api/v1/profile-bindings"

    def sql(statement, values=(), fetch=False):
        with admin.cursor() as cursor:
            cursor.execute(statement, values)
            result = cursor.fetchall() if fetch else cursor.rowcount
        admin.commit()
        return result

    def checked(response, status=200):
        if response.status_code != status:
            print(
                {
                    "environment_expected": status,
                    "actual": response.status_code,
                    "path": response.request.url.path,
                    "error_code": response.json().get("code"),
                },
                flush=True,
            )
        assert response.status_code == status, (
            response.request.method,
            response.request.url.path,
            response.status_code,
            response.text[:500],
        )
        return response.json()

    def caps(identity=headers, operation="ENROLL"):
        return checked(
            client.get(root + "/capabilities", headers=identity, params={"operation": operation})
        )

    def wh(revision=None, operation="ENROLL"):
        result = headers | {
            "X-CSRF-Token": caps(operation=operation)["csrf_token"],
            "Idempotency-Key": str(uuid4()),
        }
        return result | ({"If-Match": f'"{revision}"'} if revision is not None else {})

    tables = (
        "orbit_execution_agent",
        "orbit_profile_binding",
        "orbit_execution_agent_idempotency",
        "orbit_execution_agent_event",
        "orbit_execution_agent_outbox",
    )

    def counts():
        return [sql("SELECT COUNT(*) FROM " + table, fetch=True)[0][0] for table in tables] + [
            sql(
                "SELECT revision FROM orbit_execution_agent_clock WHERE tenant_id=%s",
                (tenant,),
                True,
            )[0][0]
        ]

    def agent_body(name):
        return {"name": name, "endpoint": "http://localhost:50325", "probe_interval": 30}

    body, create_headers = agent_body(marker + "_first"), wh()
    agent = checked(client.post(root, headers=create_headers, json=body), 201)
    assert set(agent) == {
        "id",
        "name",
        "endpoint",
        "probe_interval",
        "revision",
        "state",
        "last_heartbeat",
    }
    assert agent["state"] == "OFFLINE" and agent["last_heartbeat"] is None
    assert checked(client.get(root + "/" + agent["id"], headers=headers)) == agent
    before = counts()
    assert checked(client.post(root, headers=create_headers, json=body), 201) == agent
    assert counts() == before
    cases.append(ENVIRONMENT_REGISTRY_CASES[0])

    for wrong in [
        body | {"endpoint": "http://example.com:50325"},
        body | {"api_key": "isolated-forbidden-value"},
        body | {"state": "READY"},
        body | {"probe_interval": True},
        body | {"endpoint": "http://localhost:50325/path"},
    ]:
        before = counts()
        checked(
            client.post(root, headers=wh(), json=wrong),
            400 if {"api_key", "state"} & wrong.keys() or wrong["probe_interval"] is True else 422,
        )
        assert counts() == before
    cases.append(ENVIRONMENT_REGISTRY_CASES[1])

    role_cap = checked(client.get("/api/v1/roles/capabilities", headers=headers))
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": role_cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": marker,
                "menu_codes": ["environments"],
                "permission_codes": [
                    "environments." + x for x in ("read", "enroll", "revoke", "probe")
                ],
            },
        ),
        201,
    )
    native_role = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
        True,
    )[0][0]
    manager, user, peer = fixture["users"][0], fixture["users"][1], fixture["users"][3]
    actors = []
    for actor in (manager, user, peer):
        sql(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
            (actor["native"], native_role),
        )
        login = checked(
            fixture_login(client, cache, {"username": actor["name"], "password": password})
        )
        identity = {"Authorization": "Bearer " + login["token"]}
        assert caps(identity, "READ")["csrf_token"] is None
        info = checked(client.get("/getInfo", headers=identity))
        assert (
            "accounts.read" not in info["permissions"]
            and "environments.enroll" in info["permissions"]
        )
        before = counts()
        for operation in ("ENROLL", "REVOKE", "PROBE"):
            checked(
                client.get(
                    root + "/capabilities", headers=identity, params={"operation": operation}
                ),
                403,
            )
        checked(
            client.post(
                root,
                headers=identity
                | {k: v for k, v in create_headers.items() if k != "Authorization"},
                json=body,
            ),
            403,
        )
        assert counts() == before
        actors.append(identity)
    manager_headers, user_headers, peer_headers = actors
    cases.append(ENVIRONMENT_REGISTRY_CASES[2])
    assert checked(client.get(root, headers=user_headers))["items"] == []
    checked(client.get(root + "/" + agent["id"], headers=user_headers), 404)
    cases.append(ENVIRONMENT_REGISTRY_CASES[3])

    account = sql_fixture.account()
    peer_account = sql_fixture.account()
    for identifier, actor in [(account, user), (peer_account, peer)]:
        sql(
            "UPDATE orbit_ad_account SET owner_user_id=%s,owner_team_id=%s "
            "WHERE tenant_id=%s AND id=%s",
            (actor["id"], actor["team"], tenant, identifier),
        )
    sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))

    def binding_body(identifier, actor, profile):
        return {
            "account_id": identifier,
            "agent_id": agent["id"],
            "profile_external_id": profile,
            "ownership": {"owner_user_id": actor["id"], "owner_team_id": actor["team"]},
        }

    binding_value = binding_body(account, user, "profile-own")
    binding = checked(client.post(bindings, headers=wh(), json=binding_value), 201)
    assert binding["identity_state"] == "UNKNOWN" and binding["verified_at"] is None
    assert checked(client.get(root, headers=user_headers))["items"] == [agent]
    assert checked(client.get(bindings + "/" + binding["id"], headers=user_headers)) == binding
    cases.append(ENVIRONMENT_REGISTRY_CASES[4])
    peer_binding = checked(
        client.post(bindings, headers=wh(), json=binding_body(peer_account, peer, "profile-peer")),
        201,
    )
    assert {x["id"] for x in checked(client.get(bindings, headers=user_headers))["items"]} == {
        binding["id"]
    }
    checked(client.get(bindings + "/" + peer_binding["id"], headers=user_headers), 404)
    assert checked(client.get(root, headers=peer_headers))["items"] == [agent]
    cases.append(ENVIRONMENT_REGISTRY_CASES[5])
    for wrong, status in [
        (
            binding_value
            | {"ownership": {"owner_user_id": peer["id"], "owner_team_id": peer["team"]}},
            422,
        ),
        (binding_value | {"account_id": str(uuid4())}, 404),
        (binding_value | {"agent_id": str(uuid4())}, 404),
    ]:
        before = counts()
        checked(client.post(bindings, headers=wh(), json=wrong), status)
        assert counts() == before
    cases.append(ENVIRONMENT_REGISTRY_CASES[6])

    update_headers = wh(agent["revision"])
    update_body = body | {"name": marker + "_updated"}
    agent = checked(client.put(root + "/" + agent["id"], headers=update_headers, json=update_body))
    before = counts()
    assert (
        checked(client.put(root + "/" + agent["id"], headers=update_headers, json=update_body))
        == agent
    )
    assert counts() == before
    checked(client.put(root + "/" + agent["id"], headers=wh(1), json=body), 409)
    race_headers = [wh(agent["revision"]), wh(agent["revision"])]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda pair: client.put(
                    root + "/" + agent["id"],
                    headers=pair[1],
                    json=body | {"name": marker + "_race" + str(pair[0])},
                ),
                enumerate(race_headers),
            )
        )
    assert sorted(r.status_code for r in outcomes) == [200, 409]
    agent = checked(client.get(root + "/" + agent["id"], headers=headers))
    cases.append(ENVIRONMENT_REGISTRY_CASES[7])
    for index in range(20):
        checked(client.post(root, headers=wh(), json=agent_body(marker + f"_{index:02}")), 201)
    filters = {"q": marker, "page_size": 20, "status": "OFFLINE"}
    first = checked(client.get(root, headers=headers, params=filters))
    assert len(first["items"]) == 20 and first["next_cursor"]
    second = checked(
        client.get(root, headers=headers, params=filters | {"cursor": first["next_cursor"]})
    )
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    assert len({x["id"] for x in first["items"] + second["items"]}) == 21
    agent = checked(client.put(root + "/" + agent["id"], headers=wh(agent["revision"]), json=body))
    checked(
        client.get(root, headers=headers, params=filters | {"cursor": first["next_cursor"]}), 409
    )
    cases.append(ENVIRONMENT_REGISTRY_CASES[8])
    sql(
        "UPDATE orbit_execution_agent SET created_at=%s WHERE tenant_id=%s AND id=%s",
        (datetime(2026, 1, 1, 16, 30), tenant, agent["id"]),
    )
    visible = checked(
        client.get(
            root,
            headers=headers,
            params={"q": marker + "_first", "date_from": "2026-01-02", "date_to": "2026-01-02"},
        )
    )
    assert [x["id"] for x in visible["items"]] == [agent["id"]]
    assert not checked(
        client.get(root, headers=headers, params={"q": marker + "_first", "date_to": "2026-01-01"})
    )["items"]
    cases.append(ENVIRONMENT_REGISTRY_CASES[9])

    sql(
        "UPDATE orbit_ad_account SET owner_user_id=%s,owner_team_id=%s "
        "WHERE tenant_id=%s AND id=%s",
        (peer["id"], peer["team"], tenant, account),
    )
    sql("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,))
    checked(client.get(bindings + "/" + binding["id"], headers=user_headers), 404)
    checked(client.get(root + "/" + agent["id"], headers=user_headers), 404)
    assert (
        checked(client.get(bindings + "/" + binding["id"], headers=headers))["id"] == binding["id"]
    )
    binding = checked(
        client.put(
            bindings + "/" + binding["id"],
            headers=wh(binding["revision"]),
            json=binding_body(account, peer, "profile-own"),
        )
    )
    assert (
        checked(client.get(bindings + "/" + binding["id"], headers=peer_headers))["ownership"][
            "owner_user_id"
        ]
        == peer["id"]
    )
    cases.append(ENVIRONMENT_REGISTRY_CASES[10])
    unbind_headers = wh(binding["revision"])
    unbind_path = bindings + "/" + binding["id"] + "/unbind"
    unbound = checked(
        client.post(unbind_path, headers=unbind_headers, json={"reason": "isolated acceptance"})
    )
    assert unbound["id"] == binding["id"] and unbound["unbound_at"]
    before = counts()
    assert (
        checked(
            client.post(unbind_path, headers=unbind_headers, json={"reason": "isolated acceptance"})
        )
        == unbound
    )
    assert counts() == before
    checked(client.get(bindings + "/" + binding["id"], headers=peer_headers), 404)
    replacement = checked(
        client.post(bindings, headers=wh(), json=binding_body(account, peer, "profile-own")), 201
    )
    assert replacement["id"] != binding["id"]
    cases.append(ENVIRONMENT_REGISTRY_CASES[11])
    revoke_headers = wh(agent["revision"], "REVOKE")
    revoked = checked(
        client.post(
            root + "/" + agent["id"] + "/revoke",
            headers=revoke_headers,
            json={"reason": "isolated acceptance"},
        )
    )
    assert revoked["state"] == "REVOKED"
    checked(client.get(root + "/" + agent["id"], headers=peer_headers), 404)
    assert checked(client.get(root + "/" + agent["id"], headers=headers))["state"] == "REVOKED"
    before = counts()
    assert (
        checked(
            client.post(
                root + "/" + agent["id"] + "/revoke",
                headers=revoke_headers,
                json={"reason": "isolated acceptance"},
            )
        )
        == revoked
    )
    assert counts() == before
    cases.append(ENVIRONMENT_REGISTRY_CASES[12])
    before = counts()
    sql(
        "CREATE TRIGGER environment_fixture_outbox BEFORE INSERT ON orbit_execution_agent_outbox "
        "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='ENVIRONMENT_FIXTURE_ROLLBACK'"
    )
    try:
        checked(client.post(root, headers=wh(), json=agent_body(marker + "_rollback")), 503)
    finally:
        sql("DROP TRIGGER environment_fixture_outbox")
    assert counts() == before
    cases.append(ENVIRONMENT_REGISTRY_CASES[13])
    sql("UPDATE sys_menu SET status='1' WHERE menu_id=31062")
    try:
        checked(client.post(root, headers=create_headers, json=body), 403)
    finally:
        sql("UPDATE sys_menu SET status='0' WHERE menu_id=31062")
    cases.append(ENVIRONMENT_REGISTRY_CASES[14])
    foreign_tenant = sql("SELECT id FROM orbit_tenant WHERE id<>%s LIMIT 1", (tenant,), True)[0][0]
    foreign_id = str(uuid4())
    sql(
        "INSERT INTO orbit_execution_agent(tenant_id,id,name,endpoint,"
        "probe_interval,created_at,updated_at) "
        "VALUES(%s,%s,'foreign','http://127.0.0.1:50325',30,NOW(6),NOW(6))",
        (foreign_tenant, foreign_id),
    )
    checked(client.get(root + "/" + foreign_id, headers=headers), 404)
    checked(client.get(root + "/" + str(uuid4()), headers=headers), 404)
    alive = first["items"][0]
    if alive["id"] == agent["id"]:
        alive = first["items"][1]
    checked(
        client.post(root + "/" + alive["id"] + "/probe", headers=wh(alive["revision"], "PROBE")),
        503,
    )
    cases.append(ENVIRONMENT_REGISTRY_CASES[15])
    return {
        "scope": "isolated device registry and unverified profile associations",
        "marker": marker,
        "device_id": alive["id"],
        "account_id": account,
        "owner_user_id": peer["id"],
        "owner_team_id": peer["team"],
        "real_advertising_writes": False,
    }
