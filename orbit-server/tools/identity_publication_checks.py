"""053专项：真实SQL/原GET，Graph与独立能力发行均明确为隔离协议fixture。

不启动服务、不调用真实Meta、不新增HTTP发布backdoor。主线串行执行并销毁UUID库。
"""

import asyncio
import hashlib
import json
import re
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

IDENTITY_PUBLICATION_CASES = [
    "pythonIdentityPublicationNoAuthority503ZeroWrites",
    "pythonIdentityPublicationCompleteOriginalGetAndAtomicProvenance",
    "pythonIdentityPublicationFloorMicrosecondsExactRoundTrip",
    "pythonIdentityPublicationHistoricalReplayCurrentScopeBeforeSourceCas",
    "pythonIdentityPublicationNewKeyStaleSourceRollsBack",
    "pythonIdentityPublicationCurrentActionAndForeignScope404",
    "pythonIdentityPublicationAuditAndOutbox1644WholeRollback",
    "pythonIdentityPublicationTwoFirstProbeMissesOneCompleteVersion",
    "pythonIdentityPublicationUnknownForeignAndUnsyncedObjects",
    "pythonIdentityPublicationOldRrManagedRevocationCurrentGet",
    "pythonIdentityPublicationImmutableProvenanceAndCorruptRowsFailClosed",
    "pythonIdentityPublicationReleaseRevocationCurrentGetRejects",
]

IDENTITY_INVENTORY_BOUNDARY_CASES = [
    "pythonIdentityPublicationCompleteEmptyInventoryOriginalHttp",
    "pythonIdentityPublicationFiveThousandExactInventoryAndFiveThousandOneRejected",
]


def inventory_protocol_page(total, after):
    """独占受控GET页；0/5000/5001均明确夹具，最多200行且不猜平台游标。"""
    if type(total) is not int or total not in (0, 5000, 5001):
        raise ValueError("只允许本专项三个明确库存边界")
    if after is None:
        start = 0
    elif isinstance(after, str) and re.fullmatch(r"inventory-[0-9]{1,5}", after):
        start = int(after.removeprefix("inventory-"))
        if start < 200 or start % 200 or start >= total:
            raise ValueError("不接受未由本夹具发行的分页游标")
    else:
        raise ValueError("不接受未由本夹具发行的分页游标")
    end = min(start + 200, total)
    records = [
        {"id": "000000" + str(index).zfill(5), "name": "完整库存主页" + str(index)}
        for index in range(start, end)
    ]
    return records, "inventory-" + str(end) if end < total else None


def run_identity_publication_checks(
    client,
    admin,
    headers,
    password,
    cache,
    database,
    cases,
    *,
    cipher=None,
    prepare_browser_fixture=False,
    include_inventory_boundaries=False,
):
    try:
        from account_scope_visibility_plan_checks import prepare_plan_identities
        from fixture_login import fixture_login
        from meta_observation_registry_checks import guard_meta_registry_target
    except ImportError:
        from tools.account_scope_visibility_plan_checks import prepare_plan_identities
        from tools.fixture_login import fixture_login
        from tools.meta_observation_registry_checks import guard_meta_registry_target

    guard_meta_registry_target(admin, database)
    if type(prepare_browser_fixture) is not bool:
        raise ValueError("浏览器fixture开关必须显式布尔值")
    if type(include_inventory_boundaries) is not bool:
        raise ValueError("库存边界开关必须显式布尔值")
    if cipher is None or not cipher.ready:
        raise ValueError("053需要主线内存CredentialCipher，不加载其他环境或输出凭据")

    import httpx
    from sqlalchemy import URL, text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    import orbit_api.meta_bound_observation as bound_module
    import orbit_api.meta_identity_facts_observation as facts_module
    import orbit_api.meta_launch_observation as observer_module
    from orbit_api.errors import OrbitError
    from orbit_api.identity_publication_readmodel import IdentityPublicationReadmodel
    from orbit_api.identity_publication_store import (
        IdentityCapabilityAuthority,
        IdentityDecision,
        IdentityPublicationStore,
        IdentityQualification,
    )
    from orbit_api.meta_identity_principal_binding import (
        capture_identity_principal,
        observe_identity_principal,
    )
    from orbit_api.meta_observation_registry import MetaObservationRegistry

    identities = prepare_plan_identities(client, admin, headers, password, cache)
    user, manager = identities["USER"], identities["TEAM_ADMIN"]
    actor, owner, team = user["actor_id"], user["owner_user_id"], user["owner_team_id"]

    def sql(statement, values=(), *, fetch=False):
        try:
            with admin.cursor() as cursor:
                cursor.execute(statement, values)
                result = cursor.fetchall() if fetch else cursor.rowcount
            admin.commit()
            return result
        except BaseException:
            admin.rollback()
            raise

    def checked(response, expected):
        assert response.status_code == expected, {
            "actual": response.status_code,
            "expected": expected,
            "code": response.json().get("code"),
        }
        return response.json()

    tenant = sql("SELECT tenant_id FROM orbit_business_user WHERE user_id=1", fetch=True)[0][0]
    capabilities = checked(client.get("/api/v1/roles/capabilities", headers=headers), 200)
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {"X-CSRF-Token": capabilities["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "身份发布同步隔离" + uuid4().hex[:12],
                "menu_codes": ["accounts"],
                "permission_codes": ["accounts.sync"],
            },
        ),
        201,
    )
    native_role = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
        fetch=True,
    )[0][0]
    sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (actor, native_role))
    original_sources = sql(
        "SELECT id,enabled FROM orbit_system_configuration WHERE tenant_id=%s "
        "AND section='META_BM' ORDER BY id",
        (tenant,),
        fetch=True,
    )
    sql(
        "UPDATE orbit_system_configuration SET enabled=0 WHERE tenant_id=%s AND section='META_BM'",
        (tenant,),
    )
    token = "isolated-identity-source-" + uuid4().hex
    configuration = checked(
        client.post(
            "/api/v1/system-configurations",
            headers=headers | {"Idempotency-Key": "identity-config-" + uuid4().hex},
            json={
                "section": "META_BM",
                "name": "身份发布SQL协议" + uuid4().hex[:12],
                "enabled": True,
                "settings": {"businessId": "42", "systemUserId": "7", "graphVersion": "v25.0"},
                "secrets": {"accessToken": {"operation": "REPLACE", "value": token}},
                "reason": "仅SQL技术fixture，不表示Meta生产核验",
            },
        ),
        200,
    )
    config_id = configuration["id"]
    sql(
        "UPDATE orbit_system_configuration SET verification_status='READ_VERIFIED' "
        "WHERE tenant_id=%s AND id=%s",
        (tenant, config_id),
    )
    config_revision = sql(
        "SELECT revision FROM orbit_system_configuration WHERE tenant_id=%s AND id=%s",
        (tenant, config_id),
        fetch=True,
    )[0][0]
    account_id, external = str(uuid4()), "00" + str(10**20 + uuid4().int % 10**20)

    def add_account(identifier, selected_owner):
        platform_id = external if identifier == account_id else "00" + str(uuid4().int)
        sql(
            "INSERT INTO "
            "orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
            "owner_team_id,"
            "currency,timezone_id,auth_status,account_status,value_json,details_json,"
            "bound_at,created_at) "
            "VALUES(%s,%s,%s,'身份发布SQL夹具','身份发布SQL夹具',%s,%s,'USD','UTC','AUTHORIZED','ACTIVE',"
            "'{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (
                tenant,
                identifier,
                platform_id,
                selected_owner,
                team,
            ),
        )
        return platform_id

    add_account(account_id, owner)
    release_id, release_hash = str(uuid4()), hashlib.sha256(b"ISOLATED_PROTOCOL_ONLY").hexdigest()
    release_version = "isolated-identity-v1"
    sql(
        "INSERT INTO "
        "orbit_identity_capability_release(tenant_id,id,revision,capability_version,"
        "issuer,source_kind,"
        "source_hash,source_config_id,source_config_revision,business_id,"
        "graph_version,action_scope) "
        "VALUES(%s,%s,1,'isolated-identity-v1','isolated-protocol-issuer',"
        "'ISOLATED_PROTOCOL',%s,%s,%s,"
        "'42','v25.0','ACCOUNT_IDENTITIES_READ')",
        (tenant, release_id, release_hash, config_id, config_revision),
    )
    tables = (
        "orbit_account_identity_evidence",
        "orbit_account_identity_history",
        "orbit_account_identity_head",
        "orbit_account_identity_resource",
        "orbit_identity_publication_provenance",
        "orbit_identity_publication_ledger",
        "orbit_account_event",
        "orbit_account_outbox",
    )

    def counts():
        return tuple(sql("SELECT COUNT(*) FROM " + table, fetch=True)[0][0] for table in tables)

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

    async def run():
        nonlocal release_id, release_version
        engine = create_async_engine(
            url, echo=False, hide_parameters=True, isolation_level="REPEATABLE READ"
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        graph_count, network_checks = 0, 0
        scope_externals = {external}
        source_accounts, principal_account = [account_id], account_id
        inventory_total, target_page_calls = None, 0

        def handler(request):
            nonlocal graph_count, network_checks, target_page_calls
            assert engine.pool.checkedout() == 0, "网络期间不得持有SQL连接或事务"
            network_checks += 1
            assert request.method == "GET" and request.url.host == "graph.facebook.com"
            assert request.headers["Authorization"] == "Bearer " + token
            assert token not in str(request.url)
            graph_count += 1
            path = request.url.path.removeprefix("/v25.0/")
            if path == "42/owned_ad_accounts":
                body = {
                    "data": [
                        {"id": "act_" + value, "account_id": value}
                        for value in sorted(scope_externals)
                    ]
                }
            elif path == "42/client_ad_accounts":
                body = {"data": []}
            elif path.endswith("/promote_pages"):
                if inventory_total is not None and path.startswith("act_" + external + "/"):
                    records, after = inventory_protocol_page(
                        inventory_total, request.url.params.get("after")
                    )
                    target_page_calls += 1
                    body = {"data": records}
                    if after:
                        body["paging"] = {
                            "next": "https://graph.facebook.com/v25.0/" + path,
                            "cursors": {"after": after},
                        }
                else:
                    body = {"data": [{"id": "009", "name": "实际页名"}]}
            elif path.endswith("/adspixels"):
                body = {"data": [] if inventory_total is not None else [{"id": "008", "name": ""}]}
            elif path.endswith("/advertisable_applications"):
                body = {
                    "data": [] if inventory_total is not None else [{"id": "007", "name": "应用名"}]
                }
            elif path.startswith("act_") and path[4:] in scope_externals:
                body = {
                    "id": path,
                    "account_id": path[4:],
                    "name": "账户",
                    "currency": "USD",
                    "timezone_name": "UTC",
                    "account_status": 1,
                    "capabilities": [],
                    "user_tasks": [],
                }
            elif path == "me":
                body = {"id": "7"}
            elif path == "009":
                body = {
                    "id": "009",
                    "name": "实际页名",
                    "business": {"id": "42"},
                    "can_post": False,
                }
            elif path == "009/assigned_users":
                body = {"data": []}  # 空assignment不发行任何可投资格。
            else:
                raise AssertionError("未声明Graph路径")
            return httpx.Response(200, json=body)

        class Authority(IdentityCapabilityAuthority):
            kind = "ISOLATED_TEST"

            async def capture(self, match, selected):
                binding = next(
                    row for row in match.source.bound.source.accounts if row.account_id == selected
                )
                observed = next(
                    row
                    for row in match.source.bound.observation.accounts
                    if row.external_id == binding.external_id
                )
                return IdentityQualification(
                    release_id,
                    1,
                    release_hash,
                    release_version,
                    match.source.bound.binding_sha256,
                    match.evidence_sha256,
                    selected,
                    tuple(
                        IdentityDecision(
                            r.kind,
                            r.external_id,
                            r.kind == "PAGE",
                            None if r.kind == "PAGE" else "ISOLATED_UNAVAILABLE",
                        )
                        for r in observed.resources
                    ),
                    match.facts.observed_at,
                )

            async def revalidate(self, session, current, prepared):
                # 明确为SQL协议来源；真实发行/权限producer不在此fixture内。
                result = (
                    await session.execute(
                        text(
                            "SELECT source_kind FROM orbit_identity_capability_release "
                            "WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                        ),
                        {"tenant": tenant, "id": release_id},
                    )
                ).scalar_one()
                assert result == "ISOLATED_PROTOCOL"

        store, readmodel, registry = (
            IdentityPublicationStore(Authority()),
            IdentityPublicationReadmodel(),
            MetaObservationRegistry(),
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as graph:

            class Transport:
                async def get(self, target, headers, *, maximum_bytes):
                    response = await graph.get(target, headers=headers)
                    assert len(response.content) <= maximum_bytes
                    return observer_module.GraphReadResponse(response.status_code, response.content)

            async def prepare(expected=0, *, at=None):
                old = bound_module.utc_now, observer_module.utc_now, facts_module.utc_now
                try:
                    if at is not None:
                        bound_module.utc_now = observer_module.utc_now = facts_module.utc_now = (
                            lambda: at
                        )
                    source = await bound_module.capture_meta_source(
                        sessions, actor, source_accounts, cipher=cipher
                    )
                    bound = await bound_module.observe_meta_source(source, transport=Transport())
                    async with sessions() as session, session.begin():
                        raw_receipt = await registry.register(
                            session,
                            actor,
                            registry.prepare(bound),
                            key="identity-raw-" + uuid4().hex,
                            request_id=str(uuid4()),
                        )
                    principal = await capture_identity_principal(sessions, actor, bound)
                    match = await observe_identity_principal(
                        principal,
                        [facts_module.IdentityFactSelection(principal_account, "PAGE", "009")],
                        transport=Transport(),
                    )
                    return await store.prepare(
                        match,
                        account_id,
                        registry_id=raw_receipt["registry_id"],
                        expected_revision=expected,
                    )
                finally:
                    bound_module.utc_now, observer_module.utc_now, facts_module.utc_now = old

            async def persist(prepared, key=None, factory=sessions):
                async with factory() as session, session.begin():
                    return await store.register(
                        session,
                        actor,
                        prepared,
                        key=key or "identity-publish-" + uuid4().hex,
                        request_id=str(uuid4()),
                    )

            async def denied(operation, status, code):
                before = counts()
                try:
                    await operation()
                except OrbitError as error:
                    assert (error.status, error.code) == (status, code), {
                        "status": error.status,
                        "code": error.code,
                    }
                else:
                    raise AssertionError("必须明确失败关闭")
                assert counts() == before

            async def read(selected_actor=actor, selected_account=account_id):
                async with sessions() as session, session.begin():
                    return await readmodel.get(session, selected_actor, selected_account)

            try:
                before = counts()
                await denied(
                    lambda: IdentityPublicationStore().prepare(
                        None, account_id, registry_id=str(uuid4()), expected_revision=0
                    ),
                    503,
                    "IDENTITY_PUBLICATION_AUTHORITY_UNAVAILABLE",
                )
                cases.append(IDENTITY_PUBLICATION_CASES[0])
                first = await prepare(at=datetime.now(UTC) - timedelta(minutes=3))
                key = "identity-first-" + uuid4().hex
                receipt = await persist(first, key)
                assert tuple(a - b for a, b in zip(counts(), before, strict=True)) == (
                    1,
                    1,
                    1,
                    3,
                    1,
                    1,
                    1,
                    1,
                )
                value = await read()
                expected = json.loads(first.payload_json)
                assert value == expected
                actual = checked(
                    client.get(
                        f"/api/v1/accounts/{account_id}/identities", headers=user["headers"]
                    ),
                    200,
                )
                assert actual == expected
                assert receipt["execution_authorized"] is False
                cases.append(IDENTITY_PUBLICATION_CASES[1])
                latest, latest_receipt = first, receipt
                base = datetime.now(UTC) - timedelta(minutes=2)
                for index, microsecond in enumerate((123499, 123500, 999999), 1):
                    at = (base + timedelta(seconds=index)).replace(microsecond=microsecond)
                    latest = await prepare(index, at=at)
                    latest_receipt = await persist(latest)
                    raw, projected = sql(
                        "SELECT p.raw_observed_at,e.observed_at FROM "
                        "orbit_identity_publication_provenance p "
                        "JOIN orbit_account_identity_evidence e ON e.tenant_id=p.tenant_id "
                        "AND e.id=p.evidence_id "
                        "WHERE p.tenant_id=%s AND p.evidence_id=%s",
                        (tenant, latest_receipt["evidence_id"]),
                        fetch=True,
                    )[0]
                    assert raw == at.replace(tzinfo=None)
                    assert projected == at.replace(
                        tzinfo=None, microsecond=microsecond // 1000 * 1000
                    )
                    assert await read() == json.loads(latest.payload_json)
                cases.append(IDENTITY_PUBLICATION_CASES[2])
                sql(
                    "UPDATE orbit_system_configuration SET enabled=0,"
                    "revision=revision+1 WHERE tenant_id=%s AND id=%s",
                    (tenant, config_id),
                )
                sql(
                    "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s",
                    (tenant,),
                )
                sql(
                    "UPDATE sys_identity_subject SET auth_version=auth_version+1 WHERE user_id=%s",
                    (actor,),
                )
                assert await persist(first, key) == receipt
                # 进程重启/来源换版后，默认None Authority仍可恢复旧metadata；不重抓网络。
                async with sessions() as session, session.begin():
                    recovered = await IdentityPublicationStore().successful_replay(
                        session, actor, key=key, intent_hash=first.intent_hash
                    )
                assert recovered == receipt
                username = sql(
                    "SELECT user_name FROM sys_user WHERE user_id=%s", (actor,), fetch=True
                )[0][0]
                login = checked(
                    fixture_login(client, cache, {"username": username, "password": password}), 200
                )
                user["headers"] = {"Authorization": "Bearer " + login["token"]}
                cases.append(IDENTITY_PUBLICATION_CASES[3])
                await denied(lambda: persist(first), 409, "IDENTITY_PUBLICATION_SOURCE_CHANGED")
                cases.append(IDENTITY_PUBLICATION_CASES[4])
                sql(
                    "UPDATE orbit_system_configuration SET enabled=1,revision=%s "
                    "WHERE tenant_id=%s AND id=%s",
                    (config_revision, tenant, config_id),
                )
                sql(
                    "DELETE FROM sys_user_role WHERE user_id=%s AND role_id=%s",
                    (actor, native_role),
                )
                await denied(lambda: persist(first, key), 403, "PERMISSION_DENIED")
                sql(
                    "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (actor, native_role)
                )
                sql(
                    "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
                    (manager["owner_user_id"], tenant, account_id),
                )
                await denied(lambda: persist(first, key), 404, "NOT_FOUND")
                sql(
                    "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
                    (owner, tenant, account_id),
                )
                cases.append(IDENTITY_PUBLICATION_CASES[5])
                next_packet = await prepare(4)
                for table in ("orbit_account_event", "orbit_account_outbox"):
                    trigger = "identity_failure_" + uuid4().hex[:12]
                    sql(
                        "CREATE TRIGGER "
                        + trigger
                        + " BEFORE INSERT ON "
                        + table
                        + " FOR EACH ROW SIGNAL SQLSTATE '45000' SET "
                        "MESSAGE_TEXT='controlled rejection'"
                    )
                    before = counts()
                    try:
                        try:
                            await persist(next_packet)
                        except DBAPIError as error:
                            assert error.orig.args[0] == 1644
                        else:
                            raise AssertionError("实际1644必须整体回滚")
                        assert counts() == before
                    finally:
                        sql("DROP TRIGGER " + trigger)
                cases.append(IDENTITY_PUBLICATION_CASES[6])
                entered, gate = 0, asyncio.Event()
                concurrent_key = "identity-concurrent-" + uuid4().hex
                key_hash = hashlib.sha256(concurrent_key.encode()).hexdigest()

                class BarrierSession(AsyncSession):
                    async def execute(self, statement, params=None, **kwargs):
                        nonlocal entered
                        result = await super().execute(statement, params, **kwargs)
                        if (
                            "FROM orbit_identity_publication_ledger" in str(statement)
                            and "FOR UPDATE" not in str(statement)
                            and params
                            and params.get("key") == key_hash
                        ):
                            entered += 1
                            if entered == 2:
                                gate.set()
                            await asyncio.wait_for(gate.wait(), 5)
                        return result

                factories = async_sessionmaker(
                    engine, class_=BarrierSession, expire_on_commit=False
                )
                before = counts()
                a, b = await asyncio.wait_for(
                    asyncio.gather(
                        persist(next_packet, concurrent_key, factories),
                        persist(next_packet, concurrent_key, factories),
                    ),
                    12,
                )
                assert entered == 2 and a == b
                assert tuple(x - y for x, y in zip(counts(), before, strict=True)) == (
                    1,
                    1,
                    0,
                    3,
                    1,
                    1,
                    1,
                    1,
                )
                cases.append(IDENTITY_PUBLICATION_CASES[7])
                foreign, unsynced = str(uuid4()), str(uuid4())
                add_account(foreign, manager["owner_user_id"])
                add_account(unsynced, owner)
                await denied(lambda: read(selected_account=str(uuid4())), 404, "NOT_FOUND")
                await denied(lambda: read(selected_account=foreign), 404, "NOT_FOUND")
                await denied(
                    lambda: read(selected_account=unsynced), 503, "ACCOUNT_IDENTITIES_UNSYNCED"
                )
                malformed = checked(
                    client.get("/api/v1/accounts/not-uuid/identities", headers=user["headers"]), 422
                )
                assert malformed["code"] == "FIELD_INVALID"
                assert malformed["field_errors"][0]["path"] == "/id"
                for identifier, status in ((str(uuid4()), 404), (foreign, 404), (unsynced, 503)):
                    checked(
                        client.get(
                            f"/api/v1/accounts/{identifier}/identities", headers=user["headers"]
                        ),
                        status,
                    )
                cases.append(IDENTITY_PUBLICATION_CASES[8])
                async with sessions() as session:
                    try:
                        await session.execute(
                            text("SELECT COUNT(*) FROM orbit_business_team_manager")
                        )
                        sql(
                            "DELETE FROM orbit_business_team_manager WHERE "
                            "tenant_id=%s AND manager_user_id=%s AND team_id=%s",
                            (tenant, manager["actor_id"], team),
                        )
                        try:
                            await readmodel.get(session, manager["actor_id"], account_id)
                        except OrbitError as error:
                            assert (error.status, error.code) == (404, "NOT_FOUND")
                        else:
                            raise AssertionError("旧RR不可保留已撤管理范围")
                    finally:
                        await session.rollback()
                        sql(
                            "INSERT INTO orbit_business_team_manager(tenant_id,"
                            "manager_user_id,team_id,enabled) VALUES(%s,%s,%s,1)",
                            (tenant, manager["actor_id"], team),
                        )
                cases.append(IDENTITY_PUBLICATION_CASES[9])
                for table in (
                    "orbit_identity_publication_provenance",
                    "orbit_identity_publication_ledger",
                ):
                    try:
                        with admin.cursor() as cursor:
                            cursor.execute(
                                "DELETE FROM " + table + " WHERE tenant_id=%s", (tenant,)
                            )
                    except Exception as error:
                        assert error.args[0] == 1644
                    else:
                        raise AssertionError("不可变表DELETE必须1644")
                    finally:
                        admin.rollback()
                async with sessions() as session, session.begin():
                    await session.execute(
                        text(
                            "UPDATE orbit_account_identity_resource SET usable=2 WHERE "
                            "tenant_id=:tenant AND account_id=:id AND revision=5 AND kind='PAGE'"
                        ),
                        {"tenant": tenant, "id": account_id},
                    )
                    try:
                        await readmodel.get(session, actor, account_id)
                    except OrbitError as error:
                        assert (error.status, error.code) == (
                            503,
                            "IDENTITY_PUBLICATION_HISTORY_INVALID",
                        )
                    else:
                        raise AssertionError("损坏Boolean必须在bool转换前拒绝")
                    await session.rollback()
                cases.append(IDENTITY_PUBLICATION_CASES[10])
                sql(
                    "UPDATE orbit_identity_capability_release SET "
                    "revoked_at=UTC_TIMESTAMP(6) WHERE tenant_id=%s AND id=%s",
                    (tenant, release_id),
                )
                await denied(lambda: read(), 503, "IDENTITY_PUBLICATION_RELEASE_UNAVAILABLE")
                checked(
                    client.get(
                        f"/api/v1/accounts/{account_id}/identities", headers=user["headers"]
                    ),
                    503,
                )
                assert await persist(first, key) == receipt
                cases.append(IDENTITY_PUBLICATION_CASES[11])
                head_revision, inventory_metrics = 5, {}

                def issue_release(version, issuer):
                    nonlocal release_id, release_version
                    release_id, release_version = str(uuid4()), version
                    sql(
                        "INSERT INTO orbit_identity_capability_release(tenant_id,id,revision,"
                        "capability_version,issuer,source_kind,source_hash,source_config_id,"
                        "source_config_revision,business_id,graph_version,action_scope) "
                        "VALUES(%s,%s,1,%s,%s,'ISOLATED_PROTOCOL',%s,%s,%s,"
                        "'42','v25.0','ACCOUNT_IDENTITIES_READ')",
                        (
                            tenant,
                            release_id,
                            release_version,
                            issuer,
                            release_hash,
                            config_id,
                            config_revision,
                        ),
                    )

                if include_inventory_boundaries:
                    # 同来源anchor只作/me主体核对。目标实际0/5000资源由独立资格完整覆盖。
                    anchor_account = str(uuid4())
                    anchor_external = add_account(anchor_account, owner)
                    scope_externals.add(anchor_external)
                    source_accounts[:] = sorted([account_id, anchor_account])
                    principal_account = anchor_account
                    issue_release("isolated-inventory-boundary-v2", "isolated-inventory-issuer")
                    for total, case_index in ((0, 0), (5000, 1)):
                        inventory_total, target_page_calls = total, 0
                        start = time.perf_counter()
                        boundary = await prepare(head_revision)
                        capture_seconds = time.perf_counter() - start
                        assert target_page_calls == (1 if total == 0 else 25)
                        target_raw = [
                            r for r in boundary.raw.resources if r.account_id == account_id
                        ]
                        anchor_raw = [
                            r for r in boundary.raw.resources if r.account_id == anchor_account
                        ]
                        assert len(target_raw) == total and len(anchor_raw) == 1
                        assert len(boundary.match.facts.resources) == 1
                        assert boundary.match.facts.resources[0].account_id == anchor_account
                        payload = json.loads(boundary.payload_json)
                        expected_ids = {"000000" + str(i).zfill(5) for i in range(total)}
                        assert len(payload["resources"]) == total
                        assert {r["external_id"] for r in payload["resources"]} == expected_ids
                        assert all(r["kind"] == "PAGE" for r in payload["resources"])
                        assert "009" not in {r["external_id"] for r in payload["resources"]}
                        start = time.perf_counter()
                        published = await persist(boundary)
                        publish_seconds = time.perf_counter() - start
                        head_revision += 1
                        assert published["revision"] == head_revision
                        actual_resources = sql(
                            "SELECT external_id FROM orbit_account_identity_resource "
                            "WHERE tenant_id=%s AND account_id=%s AND revision=%s "
                            "ORDER BY external_id",
                            (tenant, account_id, head_revision),
                            fetch=True,
                        )
                        assert (
                            len(actual_resources) == total
                            and {r[0] for r in actual_resources} == expected_ids
                        )
                        start = time.perf_counter()
                        response = client.get(
                            f"/api/v1/accounts/{account_id}/identities", headers=user["headers"]
                        )
                        actual = checked(response, 200)
                        read_seconds = time.perf_counter() - start
                        assert actual == payload and await read() == payload
                        inventory_metrics[str(total)] = {
                            "target_resources": total,
                            "anchor_resources": 1,
                            "target_inventory_graph_pages": target_page_calls,
                            "source_accounts": 2,
                            "principal_selected_resources": 1,
                            "capture_and_raw_registration_seconds": round(capture_seconds, 6),
                            "publication_seconds": round(publish_seconds, 6),
                            "http_read_seconds": round(read_seconds, 6),
                            "http_response_bytes": len(response.content),
                            "exact_full_original_dto": True,
                        }
                        if total == 0:
                            cases.append(IDENTITY_INVENTORY_BOUNDARY_CASES[case_index])
                        else:
                            # 5001确实经过26个受控Graph页，在任何raw登记/发布前限额拒绝。
                            inventory_total, target_page_calls = 5001, 0
                            protected = tables + (
                                "orbit_meta_raw_head",
                                "orbit_meta_raw_account",
                                "orbit_meta_raw_resource",
                                "orbit_meta_raw_idempotency",
                                "orbit_meta_raw_audit",
                                "orbit_meta_raw_outbox",
                                "orbit_identity_capability_release",
                            )

                            def state(protected=protected):
                                return tuple(
                                    sql("SELECT COUNT(*) FROM " + name, fetch=True)[0][0]
                                    for name in protected
                                ) + tuple(
                                    sql(
                                        "SELECT revision FROM orbit_account_clock "
                                        "WHERE tenant_id=%s",
                                        (tenant,),
                                        fetch=True,
                                    )[0]
                                )

                            before = state()
                            try:
                                await prepare(head_revision)
                            except observer_module.MetaObservationFailure as error:
                                assert error.code == "META_RECORD_BUDGET_EXCEEDED"
                            else:
                                raise AssertionError("5001真实读取不得生成完整库存或部分写入")
                            assert target_page_calls == 26 and state() == before
                            assert await read() == payload
                            inventory_metrics["5001"] = {
                                "target_inventory_graph_pages": target_page_calls,
                                "error_code": "META_RECORD_BUDGET_EXCEEDED",
                                "partial_writes": 0,
                            }
                            cases.append(IDENTITY_INVENTORY_BOUNDARY_CASES[case_index])
                browser_fixture = None
                if prepare_browser_fixture:
                    # 已撤销负例保持原样；新增独立有效发行与真实新版本供只读页面消费。
                    inventory_total, principal_account = None, account_id
                    source_accounts[:] = [account_id]
                    scope_externals.clear()
                    scope_externals.add(external)
                    issue_release("isolated-identity-browser-v2", "isolated-browser-issuer")
                    browser_prepared = await prepare(head_revision)
                    browser_receipt = await persist(browser_prepared)
                    expected = json.loads(browser_prepared.payload_json)
                    assert (
                        browser_receipt["revision"] == head_revision + 1
                        and await read() == expected
                    )
                    checked(
                        client.get(
                            f"/api/v1/accounts/{account_id}/identities", headers=user["headers"]
                        ),
                        200,
                    )
                    browser_fixture = {
                        "account_id": account_id,
                        "external_id": external,
                        "expected": expected,
                    }
                return {
                    "controlled_graph_gets": graph_count,
                    "network_without_sql_checks": network_checks,
                    "real_meta_requests": 0,
                    "execution_authorized": False,
                    "sql_account_fixture": True,
                    "release_source": "ISOLATED_PROTOCOL",
                    "original_get_checked": True,
                    **({"browser_fixture": browser_fixture} if prepare_browser_fixture else {}),
                    **(
                        {"inventory_boundaries": inventory_metrics}
                        if include_inventory_boundaries
                        else {}
                    ),
                }
            finally:
                await engine.dispose()
                # 仅主线本轮UUID库浏览器窗口保留有效来源；最终由主线销毁整个隔离库。
                if not prepare_browser_fixture:
                    sql(
                        "UPDATE orbit_system_configuration SET enabled=0 "
                        "WHERE tenant_id=%s AND id=%s",
                        (tenant, config_id),
                    )
                    for identifier, enabled in original_sources:
                        sql(
                            "UPDATE orbit_system_configuration SET enabled=%s WHERE "
                            "tenant_id=%s AND id=%s",
                            (enabled, tenant, identifier),
                        )

    return asyncio.run(run())
