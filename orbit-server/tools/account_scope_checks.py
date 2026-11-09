"""025真实MySQL/HTTP范围协议专项；521受控账户不声称5万容量或真实平台采集。"""

import asyncio
import re
from uuid import uuid4

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

CASES = [
    "pythonAccountScopeFilterFreezesAllMembersWithStrictOriginalResponse",
    "pythonAccountScopeIdsReplayIsSetCanonicalAndHashStable",
    "pythonAccountScopeUnknownInvisibleAndInvalidSelectionsFailWithoutPartialCommit",
    "pythonAccountScopeKeysetMembersStayFrozenAcrossOrdinaryRename",
    "pythonAccountScopePlanLimitRejects521WithoutTruncation",
    "pythonAccountScopePlanRechecksOwnerTeamCurrencyButNotNameRevision",
    "pythonAccountScopeIdempotencyRejectsDifferentSelection",
    "pythonAccountScopeMemberAndAuditFailuresRollBackWholeCommand",
    "pythonAccountScopeReadOnlyWithoutImportCanGetCsrfAndFreeze",
    "pythonAccountScopeForeignSnapshotsAndRevokedReadOrMemberScopeFailClosed",
]


def run_account_scope_checks(
    client,
    admin,
    headers,
    actor_id,
    owner_user_id,
    owner_team_id,
    database,
    cases,
    cipher,
    readonly_identity,
):
    """readonly_identity需独占单角色USER，含headers/actor_id/owner_user_id/owner_team_id。"""
    if (
        not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database)
        or admin.host != "127.0.0.1"
        or admin.port != 13306
    ):
        raise ValueError("范围专项只允许本轮UUID独立MySQL库")
    from orbit_api.account_access import context
    from orbit_api.account_scope_store import AccountScopeStore
    from orbit_api.directory_tokens import DirectoryTokens
    from orbit_api.errors import OrbitError

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decoded(admin.user),
        password=decoded(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )
    marker = "范围受控-" + uuid4().hex
    ids = sorted(str(uuid4()) for _ in range(521))
    read_account = str(uuid4())
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        assert cursor.fetchone()[0] == database
        cursor.execute("SELECT tenant_id FROM orbit_business_user WHERE id=%s", (owner_user_id,))
        tenant = cursor.fetchone()[0]
        insert = (
            "INSERT INTO orbit_ad_account "
            "(tenant_id,id,external_id,name,name_prefix,owner_user_id,owner_team_id,currency,"
            "timezone_id,auth_status,account_status,value_json,details_json,bound_at,created_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,'USD','Asia/Shanghai','UNKNOWN','UNKNOWN','{}','{}',"
            "UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"
        )
        cursor.executemany(
            insert,
            [
                (
                    tenant,
                    identifier,
                    "00" + str(10**22 + uuid4().int % 10**22),
                    marker + "-" + str(index),
                    marker + "-" + str(index),
                    owner_user_id,
                    owner_team_id,
                )
                for index, identifier in enumerate(ids)
            ]
            + [
                (
                    tenant,
                    read_account,
                    "00" + str(10**22 + uuid4().int % 10**22),
                    "范围只读角色受控",
                    "范围只读角色受控",
                    readonly_identity["owner_user_id"],
                    readonly_identity["owner_team_id"],
                )
            ],
        )
    root = "/api/v1/scope-snapshots"
    caps = client.get(root + "/capabilities", headers=headers)
    assert caps.status_code == 200 and caps.headers["cache-control"] == "no-store"
    assert caps.headers.get("x-request-id")
    assert set(caps.json()) == {"csrf_token", "max_members", "max_plan_accounts"}
    assert caps.json()["max_members"] == 50000 and caps.json()["max_plan_accounts"] == 500

    def create(body, key=None, identity=headers, csrf=None):
        return client.post(
            root,
            headers=identity
            | {
                "X-CSRF-Token": csrf or caps.json()["csrf_token"],
                "Idempotency-Key": key or "account-scope-" + uuid4().hex,
            },
            json=body,
        )

    def selected(chosen):
        return {"mode": "IDS", "account_ids": chosen, "filter": None}

    body = {
        "mode": "FILTER",
        "account_ids": [],
        "filter": {
            "q": marker,
            "status": "UNKNOWN",
            "auth_status": "UNKNOWN",
            "operator_user_id": owner_user_id,
            "vendor_id": None,
        },
    }
    frozen = create(body)
    assert frozen.status_code == 201
    frozen = frozen.json()
    assert set(frozen) == {"id", "count", "scope_version", "hash", "created_at"}
    assert frozen["count"] == 521 and re.fullmatch(r"[0-9a-f]{64}", frozen["hash"])
    cases.append(CASES[0])
    key = "scope-replay-" + uuid4().hex
    two = create(selected(ids[:2]), key)
    assert two.status_code == 201
    replay = create(selected(list(reversed(ids[:2]))), key)
    assert replay.status_code == 201 and replay.json() == two.json()
    cases.append(CASES[1])
    assert create(selected([str(uuid4())])).status_code == 404
    assert create(selected([ids[0], ids[0]])).status_code == 422
    assert create({"mode": "IDS", "account_ids": [], "filter": None}).status_code == 422
    assert create(body, csrf="invalid-session-csrf").status_code == 403
    assert client.get(root + "/capabilities?token=fixture", headers=headers).status_code == 400
    cases.append(CASES[2])
    members = root + "/" + frozen["id"] + "/members"
    first = client.get(members, headers=headers, params={"page_size": "20"})
    assert first.status_code == 200 and len(first.json()["items"]) == 20
    assert set(first.json()) == {"items", "next_cursor", "data_as_of", "scope_version"}
    assert all(set(item) == {"account_id", "external_id", "name"} for item in first.json()["items"])
    assert first.json()["items"][0]["external_id"].startswith("00")
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_ad_account SET name=%s,name_prefix=%s,"
            "revision=revision+1 WHERE tenant_id=%s AND id=%s",
            (marker + "-当前已改名", marker + "-当前已改名", tenant, ids[0]),
        )
        cursor.execute(
            "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s", (tenant,)
        )
    again = client.get(members, headers=headers, params={"page_size": "20"})
    assert again.status_code == 200 and again.json()["items"] == first.json()["items"]
    following = client.get(
        members, headers=headers, params={"page_size": "20", "cursor": first.json()["next_cursor"]}
    )
    assert following.status_code == 200 and len(following.json()["items"]) == 20
    assert not {item["account_id"] for item in first.json()["items"]}.intersection(
        item["account_id"] for item in following.json()["items"]
    )
    assert (
        client.get(
            members, headers=headers, params={"cursor": first.json()["next_cursor"], "q": "x"}
        ).status_code
        == 409
    )
    cases.append(CASES[3])

    def resolve(identifier):
        async def execute():
            engine = create_async_engine(url, echo=False)
            try:
                sessions = async_sessionmaker(engine, expire_on_commit=False)
                async with sessions() as session, session.begin():
                    current, _ = await context(session, actor_id, "accounts.read")
                    return await AccountScopeStore(DirectoryTokens(cipher)).resolve_for_plan(
                        session,
                        current,
                        identifier,
                        owner_user_id=owner_user_id,
                        owner_team_id=owner_team_id,
                    )
            finally:
                await engine.dispose()

        return asyncio.run(execute())

    try:
        resolve(frozen["id"])
    except OrbitError as error:
        assert error.status == 422 and error.code == "PLAN_ACCOUNT_LIMIT"
    else:
        raise AssertionError("521账户范围不能静默截为计划500账户")
    cases.append(CASES[4])
    assert resolve(two.json()["id"]) == ids[:2]
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_ad_account SET currency='EUR' WHERE tenant_id=%s AND id=%s",
            (tenant, ids[0]),
        )
    try:
        try:
            resolve(two.json()["id"])
        except OrbitError as error:
            assert error.code == "ACCOUNT_OWNERSHIP_CHANGED"
        else:
            raise AssertionError("不能沿用币种变化前的冻结业务选择")
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "UPDATE orbit_ad_account SET currency='USD' WHERE tenant_id=%s AND id=%s",
                (tenant, ids[0]),
            )
    assert resolve(two.json()["id"]) == ids[:2]
    cases.append(CASES[5])
    assert create(selected(ids[2:4]), key).status_code == 409
    cases.append(CASES[6])

    def state():
        values = []
        with admin.cursor() as cursor:
            for table in (
                "orbit_account_scope_snapshot",
                "orbit_account_scope_member",
                "orbit_account_scope_event",
                "orbit_account_scope_outbox",
            ):
                cursor.execute("SELECT COUNT(*) FROM " + table)
                values.append(cursor.fetchone()[0])
        return values

    for target in ("orbit_account_scope_member", "orbit_account_scope_event"):
        before = state()
        key_fault = "scope-rollback-" + uuid4().hex
        with admin.cursor() as cursor:
            cursor.execute(
                "CREATE TRIGGER account_scope_fixture_fail BEFORE INSERT ON "
                + target
                + " FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture-only'"
            )
        try:
            assert create(selected(ids[:3]), key_fault).status_code == 503
            assert state() == before
        finally:
            with admin.cursor() as cursor:
                cursor.execute("DROP TRIGGER IF EXISTS account_scope_fixture_fail")
        assert create(selected(ids[:3]), key_fault).status_code == 201
    cases.append(CASES[7])
    read_headers = readonly_identity["headers"]
    assert (
        client.get("/api/v1/account-imports/capabilities", headers=read_headers).status_code == 403
    )
    read_caps = client.get(root + "/capabilities", headers=read_headers)
    assert read_caps.status_code == 200
    own = create(
        selected([read_account]), identity=read_headers, csrf=read_caps.json()["csrf_token"]
    )
    assert own.status_code == 201 and own.json()["count"] == 1
    cases.append(CASES[8])
    assert client.get(members, headers=read_headers).status_code == 404
    own_path = root + "/" + own.json()["id"] + "/members"
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_ad_account SET owner_user_id=%s,owner_team_id=%s "
            "WHERE tenant_id=%s AND id=%s",
            (owner_user_id, owner_team_id, tenant, read_account),
        )
    assert client.get(own_path, headers=read_headers).status_code == 409
    with admin.cursor() as cursor:
        cursor.execute(
            "UPDATE orbit_ad_account SET owner_user_id=%s,owner_team_id=%s "
            "WHERE tenant_id=%s AND id=%s",
            (
                readonly_identity["owner_user_id"],
                readonly_identity["owner_team_id"],
                tenant,
                read_account,
            ),
        )
        cursor.execute(
            "SELECT role_id FROM sys_user_role WHERE user_id=%s", (readonly_identity["actor_id"],)
        )
        roles = cursor.fetchall()
        assert len(roles) == 1, "须使用本轮独占且仅单角色的只读人员"
        role = roles[0][0]
        cursor.execute("DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=31011", (role,))
        assert cursor.rowcount == 1
    try:
        assert client.get(root + "/capabilities", headers=read_headers).status_code == 403
        assert client.get(own_path, headers=read_headers).status_code == 403
    finally:
        with admin.cursor() as cursor:
            cursor.execute("INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,31011)", (role,))
    cases.append(CASES[9])
