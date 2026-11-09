"""主线串行的045真实SQL协议；受控httpx响应不是实际Meta权限或真实导入。

真实角色/配置API；账户归属与READ_VERIFIED为本轮显式SQL技术fixture。
只由主线连接已有13306/UUID库执行，不启动数据库/定时器或发送平台写入。
"""

import asyncio
import hashlib
import json
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

META_OBSERVATION_REGISTRY_CASES = [
    "pythonMetaRawRealEncryptedConfigurationAndBoundSqlCapture",
    "pythonMetaRawCompleteHeaderAccountResourceAuditOutbox",
    "pythonMetaRawSuccessfulReplayAfterSourceRevisionClockAndAuthChange",
    "pythonMetaRawNewKeySourceAccountAndClockCasRollback",
    "pythonMetaRawCurrentPermissionAndScopeStopHistoricalReplay",
    "pythonMetaRawSameKeyChangedObservationConflictsWithoutNewEvidence",
    "pythonMetaRawActualAudit1644RollsBackAllSixTables",
    "pythonMetaRawActualOutbox1644RollsBackAllSixTables",
    "pythonMetaRawTwoFirstProbeMissesSameKeyHaveOneCompleteResult",
    "pythonMetaRawOriginalMicrosecondsExactSqlRoundTrip",
    "pythonMetaRawDatabaseImmutabilityAndOutboxAllowedAck",
    "pythonMetaRawCurrentManagedCaptureRejectsOldRepeatableReadView",
    "pythonMetaRawProtectedDetailsFailClosedUnderControlledCorruption",
    "pythonMetaRawRegistrationNeverWritesAccountClockOrIdentityEvidence",
]

IDENTITY_FACT_OBSERVATION_CASES = [
    "pythonMetaIdentityFactsRealSqlBoundWhitelistedValuesAndUnboundPrincipal",
    "pythonMetaIdentityFactsExactRawSelectionRejectsForeignAndUnexpectedResources",
    "pythonMetaIdentityFactsCompleteAssignmentPagingAndIncompleteRejection",
    "pythonMetaIdentityFactsPermissionAndMissingFieldsStayUnknown",
    "pythonMetaIdentityFactsNetworkOutsideSqlAndNoAdditionalPersistentWrites",
]

IDENTITY_PRINCIPAL_BINDING_CASES = [
    "pythonMetaPrincipalMissingConfiguredUserIdFixed503",
    "pythonMetaPrincipalRealConfigurationCaptureAndExactMeMatch",
    "pythonMetaPrincipalWrongMeRejectedWithoutUnsafeEvidence",
    "pythonMetaPrincipalSourceAccountClockAndAuthGenerationChangesReject",
    "pythonMetaPrincipalCurrentActionAndOldRepeatableReadManagedScopeReject",
    "pythonMetaPrincipalNetworkOutsideSqlAndNoAdditionalPersistentFacts",
]


def identity_fact_protocol_response(request, token, mode):
    """只用于本工具的固定HTTP协议；响应不是Meta权限或能力证明。"""
    assert request.method == "GET" and request.url.scheme == "https"
    assert request.url.host == "graph.facebook.com"
    assert request.headers.get("Authorization") == "Bearer " + token
    assert token not in str(request.url) and "access_token" not in request.url.params
    assert request.url.path.startswith("/v25.0/")
    path = request.url.path.removeprefix("/v25.0/")
    if mode == "permission":
        # 正式采集器不能把异常正文或该回显带入输出/异常。
        return 403, {"error": {"code": 200, "message": token}}
    if path == "me":
        assert dict(request.url.params) == {"fields": "id"}
        # 故意不同于配置systemUserId=7；M1未绑定此配置字段，不能声称匹配。
        return 200, {"id": "7" if mode == "principal_match" else "17"}
    if path in {"009", "008", "007"}:
        if mode == "missing":
            return 200, {"id": path}
        return 200, {
            "009": {"id": "009", "name": "页" * 4096, "business": {"id": "42"}, "can_post": False},
            "008": {
                "id": "008",
                "name": None,
                "owner_business": {"id": "42"},
                "owner_ad_account": None,
                "is_unavailable": False,
                "is_restricted_use": True,
                "user_access_expire_time": None,
            },
            "007": {
                "id": "007",
                "name": "",
                "business": {"id": "42"},
                "ios_bundle_id": ["com.fixture.one", "com.fixture.two"],
                "iphone_app_store_id": "001234",
                "ipad_app_store_id": None,
            },
        }[path]
    if path in {"009/assigned_users", "008/assigned_users"}:
        assert request.url.params["fields"] == "id,business,user_type"
        assert request.url.params["business"] == "42"
        assert request.url.params["limit"] == "200"
        if mode == "missing":
            return 200, {"data": [{"id": "17"}]}
        if mode in {"pagination", "incomplete"} and "after" not in request.url.params:
            paging = {
                "next": "https://graph.facebook.com/v25.0/" + path + "?access_token=DO_NOT_FORWARD",
            }
            if mode == "pagination":
                paging["cursors"] = {"after": "opaque-fixture-next"}
            return 200, {"data": [{"id": "17"}], "paging": paging}
        if "after" in request.url.params:
            assert request.url.params["after"] == "opaque-fixture-next"
            return 200, {
                "data": [{"id": "18", "business": {"id": "42"}, "user_type": "FUTURE_TYPE"}]
            }
        return 200, {"data": [{"id": "17", "business": {"id": "42"}, "user_type": "SYSTEM_USER"}]}
    raise AssertionError("身份协议只允许本专项已声明Graph只读路径")


def guard_meta_registry_target(admin, database):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not isinstance(database, str)
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("原始观察专项仅允许13306本轮UUID隔离库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("实际数据库不是主线本轮UUID库")
    admin.commit()


def run_meta_observation_registry_checks(
    client,
    admin,
    headers,
    password,
    cache,
    database,
    cases,
    *,
    cipher=None,
    include_identity_facts=False,
):
    guard_meta_registry_target(admin, database)
    if cipher is None or not cipher.ready:
        raise ValueError("需要主线本轮实际CredentialCipher，不读取私密环境或自造密钥")
    import httpx
    import pymysql
    from sqlalchemy import URL, text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    try:
        from account_scope_visibility_plan_checks import prepare_plan_identities
    except ImportError:
        from tools.account_scope_visibility_plan_checks import prepare_plan_identities

    import orbit_api.meta_bound_observation as bound_module
    import orbit_api.meta_launch_observation as observer_module
    from orbit_api.errors import OrbitError
    from orbit_api.meta_observation_registry import MetaObservationRegistry

    identities = prepare_plan_identities(client, admin, headers, password, cache)
    user, manager = identities["USER"], identities["TEAM_ADMIN"]
    actor, subject, team = user["actor_id"], user["owner_user_id"], user["owner_team_id"]

    def sql(statement, values=(), *, fetch=False):
        try:
            with admin.cursor() as cursor:
                cursor.execute(statement, values)
                value = cursor.fetchall() if fetch else cursor.rowcount
            admin.commit()
            return value
        except BaseException:
            admin.rollback()
            raise

    tenant = sql("SELECT tenant_id FROM orbit_business_user WHERE user_id=1", fetch=True)[0][0]

    def checked(response, expected):
        assert response.status_code == expected, {
            "actual": response.status_code,
            "expected": expected,
            "code": response.json().get("code"),
        }
        return response.json()

    cap = checked(client.get("/api/v1/roles/capabilities", headers=headers), 200)
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers | {"X-CSRF-Token": cap["csrf_token"], "Idempotency-Key": str(uuid4())},
            json={
                "name": "原始观察同步动作" + uuid4().hex[:12],
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
    for identity in (user, manager):
        sql(
            "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)",
            (identity["actor_id"], native_role),
        )
    sync_menu = sql("SELECT menu_id FROM sys_menu WHERE perms='accounts.sync'", fetch=True)[0][0]
    original_sources = sql(
        "SELECT id,enabled FROM orbit_system_configuration "
        "WHERE tenant_id=%s AND section='META_BM' ORDER BY id",
        (tenant,),
        fetch=True,
    )
    sql(
        "UPDATE orbit_system_configuration SET enabled=0 WHERE tenant_id=%s AND section='META_BM'",
        (tenant,),
    )
    technical_token = "isolated-meta-raw-token-" + uuid4().hex
    configuration = checked(
        client.post(
            "/api/v1/system-configurations",
            headers=headers | {"Idempotency-Key": "meta-raw-config-" + uuid4().hex},
            json={
                "section": "META_BM",
                "name": "原始观察隔离协议" + uuid4().hex[:12],
                "enabled": True,
                "settings": {"businessId": "42", "systemUserId": "7", "graphVersion": "v25.0"},
                "secrets": {"accessToken": {"operation": "REPLACE", "value": technical_token}},
                "reason": "仅本轮技术来源，不声明真实Meta核验",
            },
        ),
        200,
    )
    source_id = configuration["id"]
    sql(
        "UPDATE orbit_system_configuration SET verification_status='READ_VERIFIED' "
        "WHERE tenant_id=%s AND id=%s",
        (tenant, source_id),
    )
    encrypted = sql(
        "SELECT secrets_json FROM orbit_system_configuration WHERE tenant_id=%s AND id=%s",
        (tenant, source_id),
        fetch=True,
    )[0][0]
    encrypted = json.loads(encrypted) if isinstance(encrypted, (str, bytes)) else encrypted
    assert encrypted["accessToken"] != technical_token
    assert (
        cipher.decrypt_internal(encrypted["accessToken"], tenant, source_id, "accessToken")
        == technical_token
    )

    accounts = [str(uuid4()), str(uuid4())]
    external = [
        "00" + str(10**20 + uuid4().int % 10**20),
        "00" + str(10**20 + uuid4().int % 10**20),
    ]
    for identifier, platform_id in zip(accounts, external, strict=True):
        sql(
            "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
            "owner_team_id,currency,timezone_id,auth_status,account_status,value_json,details_json,"
            "bound_at,created_at) VALUES(%s,%s,%s,'原始观察SQL夹具','原始观察SQL夹具',%s,%s,"
            "'USD','UTC','AUTHORIZED','ACTIVE','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (tenant, identifier, platform_id, subject, team),
        )
    checked(
        client.get(
            f"/api/v1/accounts/{accounts[0]}/actions/capabilities",
            headers=user["headers"],
            params={"action": "SYNC"},
        ),
        200,
    )

    tables = (
        "orbit_meta_raw_head",
        "orbit_meta_raw_account",
        "orbit_meta_raw_resource",
        "orbit_meta_raw_idempotency",
        "orbit_meta_raw_audit",
        "orbit_meta_raw_outbox",
    )

    def raw_counts():
        return tuple(sql("SELECT COUNT(*) FROM " + table, fetch=True)[0][0] for table in tables)

    def unrelated():
        return (
            sql(
                "SELECT revision FROM orbit_account_clock WHERE tenant_id=%s", (tenant,), fetch=True
            )[0][0],
            sql(
                "SELECT id,revision,value_json,details_json FROM orbit_ad_account WHERE "
                "tenant_id=%s "
                "AND id IN(%s,%s) ORDER BY id",
                (tenant, *accounts),
                fetch=True,
            ),
            sql("SELECT COUNT(*) FROM orbit_account_identity_evidence", fetch=True)[0][0],
            sql("SELECT COUNT(*) FROM orbit_account_identity_head", fetch=True)[0][0],
        )

    initial_unrelated = unrelated()
    graph_requests = 0
    identity_graph_requests = 0
    identity_network_checks = 0
    principal_graph_requests = 0
    protocol_state = {"name_suffix": ""}

    def handler(request):
        nonlocal graph_requests
        assert request.method == "GET" and request.url.scheme == "https"
        assert request.url.host == "graph.facebook.com"
        assert request.headers["Authorization"] == "Bearer " + technical_token
        assert technical_token not in str(request.url)
        graph_requests += 1
        path = request.url.path.removeprefix("/v25.0/")
        if path == "42/owned_ad_accounts":
            body = {
                "data": [
                    {"id": "act_" + identifier, "account_id": identifier} for identifier in external
                ]
            }
        elif path == "42/client_ad_accounts":
            body = {"data": []}
        elif path.endswith("/promote_pages"):
            body = {"data": [{"id": "009", "name": "页" * 4096}]}
        elif path.endswith("/adspixels"):
            body = {"data": [{"id": "008", "name": None}]}
        elif path.endswith("/advertisable_applications"):
            body = {
                "data": [{"id": "007", "name": ""}]
                if protocol_state.get("identity_application")
                else [],
            }
        elif path.startswith("act_") and "/" not in path:
            body = {
                "id": path,
                "account_id": path[4:],
                "name": "账户名" * 1000 + protocol_state["name_suffix"],
                "currency": "USD",
                "timezone_name": "UTC",
                "account_status": 0,
                "capabilities": ["RAW_READ_ONLY"],
                "user_tasks": [],
            }
        else:
            raise AssertionError("受控来源只允许本专项固定Graph读取路径")
        return httpx.Response(200, json=body)

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
        nonlocal principal_graph_requests
        engine = create_async_engine(
            url, echo=False, hide_parameters=True, isolation_level="REPEATABLE READ"
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        registry = MetaObservationRegistry()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=False
        ) as graph:

            class ProtocolTransport:
                async def get(self, target, headers, *, maximum_bytes):
                    response = await graph.get(target, headers=headers)
                    assert len(response.content) <= maximum_bytes
                    return observer_module.GraphReadResponse(response.status_code, response.content)

            async def capture(*, selected_actor=actor, factory=sessions):
                source = await bound_module.capture_meta_source(
                    factory, selected_actor, accounts, cipher=cipher
                )
                bound = await bound_module.observe_meta_source(
                    source, transport=ProtocolTransport()
                )
                return registry.prepare(bound)

            async def persist(prepared, key=None, *, factory=sessions):
                async with factory() as session, session.begin():
                    return await registry.register(
                        session,
                        actor,
                        prepared,
                        key=key or "meta-raw-" + uuid4().hex,
                        request_id=str(uuid4()),
                    )

            async def denied(operation, status, code):
                before = raw_counts()
                try:
                    await operation()
                except OrbitError as error:
                    assert (error.status, error.code) == (status, code), {
                        "actual_status": error.status,
                        "actual_code": error.code,
                    }
                else:
                    raise AssertionError("预期明确拒绝，不得用原始回执冒充当前授权")
                assert raw_counts() == before

            try:
                prepared = await capture()
                assert prepared.bound.source.configuration.source_config_id == source_id
                assert {row.external_id for row in prepared.accounts} == set(external)
                assert prepared.bound.observation.request_count == 10
                assert all(
                    len(row.name) == 4096 for row in prepared.resources if row.kind == "PAGE"
                )
                assert all(row.name is None for row in prepared.resources if row.kind == "PIXEL")
                cases.append(META_OBSERVATION_REGISTRY_CASES[0])
                key = "meta-raw-first-" + uuid4().hex
                before = raw_counts()
                receipt = await persist(prepared, key)
                assert tuple(
                    after - old for after, old in zip(raw_counts(), before, strict=True)
                ) == (1, 2, 4, 1, 1, 1)
                assert receipt["execution_authorized"] is False
                assert (
                    sql(
                        "SELECT COUNT(*) FROM orbit_meta_raw_resource WHERE tenant_id=%s AND "
                        "registry_id=%s "
                        "AND name IS NULL",
                        (tenant, receipt["registry_id"]),
                        fetch=True,
                    )[0][0]
                    == 2
                )
                cases.append(META_OBSERVATION_REGISTRY_CASES[1])

                sql(
                    "UPDATE orbit_system_configuration SET enabled=0,revision=revision+1 WHERE "
                    "tenant_id=%s AND id=%s",
                    (tenant, source_id),
                )
                sql(
                    "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s",
                    (tenant,),
                )
                sql(
                    "UPDATE sys_identity_subject SET auth_version=auth_version+1 WHERE user_id=%s",
                    (actor,),
                )
                try:
                    assert await persist(prepared, key) == receipt
                finally:
                    sql(
                        "UPDATE sys_identity_subject SET auth_version=auth_version-1 WHERE "
                        "user_id=%s",
                        (actor,),
                    )
                    sql(
                        "UPDATE orbit_account_clock SET revision=revision-1 WHERE tenant_id=%s",
                        (tenant,),
                    )
                    sql(
                        "UPDATE orbit_system_configuration SET enabled=1,revision=revision-1 "
                        "WHERE tenant_id=%s AND id=%s",
                        (tenant, source_id),
                    )
                cases.append(META_OBSERVATION_REGISTRY_CASES[2])

                for mutate, restore, values in (
                    (
                        "UPDATE orbit_system_configuration SET revision=revision+1 WHERE "
                        "tenant_id=%s AND id=%s",
                        "UPDATE orbit_system_configuration SET revision=revision-1 WHERE "
                        "tenant_id=%s AND id=%s",
                        (tenant, source_id),
                    ),
                    (
                        "UPDATE orbit_ad_account SET revision=revision+1 WHERE tenant_id=%s "
                        "AND id=%s",
                        "UPDATE orbit_ad_account SET revision=revision-1 WHERE tenant_id=%s "
                        "AND id=%s",
                        (tenant, accounts[0]),
                    ),
                    (
                        "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s",
                        "UPDATE orbit_account_clock SET revision=revision-1 WHERE tenant_id=%s",
                        (tenant,),
                    ),
                ):
                    sql(mutate, values)
                    try:
                        await denied(lambda: persist(prepared), 409, "META_RAW_SOURCE_CHANGED")
                    finally:
                        sql(restore, values)
                cases.append(META_OBSERVATION_REGISTRY_CASES[3])

                sql(
                    "DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=%s",
                    (native_role, sync_menu),
                )
                try:
                    await denied(lambda: persist(prepared, key), 403, "PERMISSION_DENIED")
                finally:
                    sql(
                        "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)",
                        (native_role, sync_menu),
                    )
                sql(
                    "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
                    (manager["owner_user_id"], tenant, accounts[0]),
                )
                try:
                    await denied(lambda: persist(prepared, key), 404, "NOT_FOUND")
                finally:
                    sql(
                        "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
                        (subject, tenant, accounts[0]),
                    )
                cases.append(META_OBSERVATION_REGISTRY_CASES[4])
                protocol_state["name_suffix"] = "受控不同观察正文"
                try:
                    changed = await capture()
                finally:
                    protocol_state["name_suffix"] = ""
                await denied(lambda: persist(changed, key), 409, "IDEMPOTENCY_CONFLICT")
                cases.append(META_OBSERVATION_REGISTRY_CASES[5])

                for table, case_index in (
                    ("orbit_meta_raw_audit", 6),
                    ("orbit_meta_raw_outbox", 7),
                ):
                    name = "meta_raw_failure_" + uuid4().hex[:12]
                    sql(
                        "CREATE TRIGGER "
                        + name
                        + " BEFORE INSERT ON "
                        + table
                        + " FOR EACH ROW SIGNAL SQLSTATE '45000' "
                        "SET MESSAGE_TEXT='controlled rejection'"
                    )
                    before = raw_counts()
                    try:
                        try:
                            await persist(prepared)
                        except DBAPIError as error:
                            assert error.orig.args and error.orig.args[0] == 1644
                        else:
                            raise AssertionError("1644必须让整个登记事务回滚")
                        assert raw_counts() == before
                    finally:
                        sql("DROP TRIGGER " + name)
                    cases.append(META_OBSERVATION_REGISTRY_CASES[case_index])

                concurrent_key = "meta-raw-concurrent-" + uuid4().hex
                key_hash = hashlib.sha256(concurrent_key.encode()).hexdigest()
                entered, release = 0, asyncio.Event()

                class ProbeBarrierSession(AsyncSession):
                    async def execute(self, statement, params=None, **kwargs):
                        nonlocal entered
                        result = await super().execute(statement, params, **kwargs)
                        value = str(statement)
                        if (
                            "FROM orbit_meta_raw_idempotency" in value
                            and "FOR UPDATE" not in value
                            and params
                            and params.get("key") == key_hash
                        ):
                            entered += 1
                            if entered == 2:
                                release.set()
                            await asyncio.wait_for(release.wait(), 5)
                        return result

                barrier_sessions = async_sessionmaker(
                    engine, class_=ProbeBarrierSession, expire_on_commit=False
                )
                before = raw_counts()
                first, second = await asyncio.wait_for(
                    asyncio.gather(
                        persist(prepared, concurrent_key, factory=barrier_sessions),
                        persist(prepared, concurrent_key, factory=barrier_sessions),
                    ),
                    12,
                )
                assert entered == 2 and first == second
                assert tuple(
                    after - old for after, old in zip(raw_counts(), before, strict=True)
                ) == (1, 2, 4, 1, 1, 1)
                cases.append(META_OBSERVATION_REGISTRY_CASES[8])

                # 仅测试进程注入观察时钟，真实SQL捕获与完整hash仍实际执行；非自然平台时间。
                for microseconds in (123499, 123500, 999999):
                    at = (datetime.now(UTC) - timedelta(minutes=2)).replace(
                        microsecond=microseconds
                    )
                    old_capture_clock, old_observer_clock = (
                        bound_module.utc_now,
                        observer_module.utc_now,
                    )
                    try:
                        bound_module.utc_now = lambda at=at: at
                        observer_module.utc_now = lambda at=at: at
                        timed = await capture()
                    finally:
                        bound_module.utc_now, observer_module.utc_now = (
                            old_capture_clock,
                            old_observer_clock,
                        )
                    timed_key = "meta-raw-micro-" + uuid4().hex
                    actual = await persist(timed, timed_key)
                    saved = sql(
                        "SELECT captured_at,started_at,observed_at FROM orbit_meta_raw_head "
                        "WHERE tenant_id=%s AND id=%s",
                        (tenant, actual["registry_id"]),
                        fetch=True,
                    )[0]
                    assert saved == (at.replace(tzinfo=None),) * 3
                    assert actual["observed_at"] == at.isoformat().replace("+00:00", "Z")
                    assert await persist(timed, timed_key) == actual
                cases.append(META_OBSERVATION_REGISTRY_CASES[9])

                for table in (
                    "orbit_meta_raw_head",
                    "orbit_meta_raw_account",
                    "orbit_meta_raw_resource",
                    "orbit_meta_raw_audit",
                    "orbit_meta_raw_idempotency",
                ):
                    for command in (
                        "UPDATE " + table + " SET tenant_id=tenant_id LIMIT 1",
                        "DELETE FROM " + table + " LIMIT 1",
                    ):
                        if table == "orbit_meta_raw_idempotency" and command.startswith("UPDATE"):
                            sql(command)
                            continue
                        try:
                            sql(command)
                        except pymysql.err.MySQLError as error:
                            assert error.args and error.args[0] == 1644
                        else:
                            raise AssertionError("原始证据不可变DML护栏没有拒绝")
                event = sql(
                    "SELECT event_id FROM orbit_meta_raw_outbox WHERE tenant_id=%s ORDER BY "
                    "event_id LIMIT 1",
                    (tenant,),
                    fetch=True,
                )[0][0]
                sql(
                    "UPDATE orbit_meta_raw_outbox SET state='DONE' WHERE tenant_id=%s AND "
                    "event_id=%s",
                    (tenant, event),
                )
                try:
                    sql(
                        "UPDATE orbit_meta_raw_outbox SET state='PENDING' WHERE tenant_id=%s "
                        "AND event_id=%s",
                        (tenant, event),
                    )
                except pymysql.err.MySQLError as error:
                    assert error.args[0] == 1644
                else:
                    raise AssertionError("DONE不能反向变PENDING")
                cases.append(META_OBSERVATION_REGISTRY_CASES[10])

                class OldViewSession:
                    def __init__(self):
                        self.session = sessions()

                    def __getattr__(self, name):
                        return getattr(self.session, name)

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *args):
                        await self.session.close()

                    @asynccontextmanager
                    async def begin(self):
                        async with self.session.begin():
                            await self.session.execute(
                                text(
                                    "SELECT team_id FROM orbit_business_team_manager "
                                    "WHERE tenant_id=:tenant AND manager_user_id=:actor"
                                ),
                                {"tenant": tenant, "actor": manager["actor_id"]},
                            )
                            sql(
                                "DELETE FROM orbit_business_team_manager WHERE tenant_id=%s "
                                "AND manager_user_id=%s AND team_id=%s",
                                (tenant, manager["actor_id"], team),
                            )
                            yield

                try:
                    await denied(
                        lambda: capture(selected_actor=manager["actor_id"], factory=OldViewSession),
                        404,
                        "NOT_FOUND",
                    )
                finally:
                    sql(
                        "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,"
                        "team_id,enabled) VALUES(%s,%s,%s,1)",
                        (tenant, manager["actor_id"], team),
                    )
                cases.append(META_OBSERVATION_REGISTRY_CASES[11])

                trigger = "guard_meta_raw_resource_update"
                create_trigger = sql("SHOW CREATE TRIGGER " + trigger, fetch=True)[0][2]
                stored_name = sql(
                    "SELECT name FROM orbit_meta_raw_resource WHERE tenant_id=%s AND "
                    "registry_id=%s "
                    "AND account_id=%s AND kind='PAGE'",
                    (tenant, receipt["registry_id"], sorted(accounts)[0]),
                    fetch=True,
                )[0][0]
                sql("DROP TRIGGER " + trigger)
                try:
                    sql(
                        "UPDATE orbit_meta_raw_resource SET name='controlled corruption' WHERE "
                        "tenant_id=%s "
                        "AND registry_id=%s AND account_id=%s AND kind='PAGE'",
                        (tenant, receipt["registry_id"], sorted(accounts)[0]),
                    )
                    await denied(
                        lambda: persist(prepared, key), 503, "META_RAW_OBSERVATION_INVALID"
                    )
                finally:
                    sql(
                        "UPDATE orbit_meta_raw_resource SET name=%s WHERE tenant_id=%s AND "
                        "registry_id=%s "
                        "AND account_id=%s AND kind='PAGE'",
                        (stored_name, tenant, receipt["registry_id"], sorted(accounts)[0]),
                    )
                    sql(create_trigger)
                assert await persist(prepared, key) == receipt
                cases.append(META_OBSERVATION_REGISTRY_CASES[12])
                assert unrelated() == initial_unrelated
                cases.append(META_OBSERVATION_REGISTRY_CASES[13])

                if include_identity_facts:
                    from sqlalchemy import event

                    import orbit_api.meta_identity_facts_observation as facts_module

                    stage = {"in_get": False, "sql_count": 0}

                    def observe_sql(_connection, _cursor, _statement, _params, _context, _many):
                        assert stage["in_get"] is False, "身份网络调用期间不得执行SQL"
                        stage["sql_count"] += 1

                    event.listen(engine.sync_engine, "before_cursor_execute", observe_sql)
                    protocol_state["identity_application"] = True
                    # 此新包不register，旧14组的原4资源及所有原断言不变。
                    enriched = await capture()
                    assert stage["sql_count"] > 0
                    assert {row.kind for row in enriched.resources} == {
                        "PAGE",
                        "PIXEL",
                        "APPLICATION",
                    }
                    assert engine.pool.checkedout() == 0
                    before_identity = (raw_counts(), unrelated())
                    selections = [
                        facts_module.IdentityFactSelection(
                            row.account_id,
                            row.kind,
                            row.external_id,
                        )
                        for row in enriched.resources
                    ]
                    identity_mode = {"value": "normal"}

                    def identity_handler(request):
                        nonlocal identity_graph_requests
                        identity_graph_requests += 1
                        status, body = identity_fact_protocol_response(
                            request,
                            technical_token,
                            identity_mode["value"],
                        )
                        return httpx.Response(status, json=body)

                    async with httpx.AsyncClient(
                        transport=httpx.MockTransport(identity_handler),
                        follow_redirects=False,
                    ) as identity_graph:

                        class IdentityProtocolTransport:
                            async def get(self, target, get_headers, *, maximum_bytes):
                                nonlocal identity_network_checks
                                assert engine.pool.checkedout() == 0
                                before_sql = stage["sql_count"]
                                assert stage["in_get"] is False
                                stage["in_get"] = True
                                try:
                                    response = await identity_graph.get(target, headers=get_headers)
                                finally:
                                    stage["in_get"] = False
                                assert stage["sql_count"] == before_sql
                                assert engine.pool.checkedout() == 0
                                assert len(response.content) <= maximum_bytes
                                identity_network_checks += 1
                                return observer_module.GraphReadResponse(
                                    response.status_code,
                                    response.content,
                                )

                        async def facts(wanted):
                            return await facts_module.observe_identity_facts(
                                enriched.bound,
                                wanted,
                                transport=IdentityProtocolTransport(),
                            )

                        result = await facts(selections)
                        assert result.principal_id == "17"
                        assert result.principal_binding == "CONFIG_PRINCIPAL_NOT_BOUND"
                        assert result.source_binding_sha256 == enriched.bound.binding_sha256
                        assert result.source_config_id == source_id
                        assert result.execution_authorized is result.durable is False
                        assert result.capability_version is result.policy_version is None
                        assert result.api_version_compatibility_verified is False
                        assert len(result.resources) == 6
                        assert result.request_count == 11
                        for row in result.resources:
                            values = json.loads(row.object_facts_json)
                            if row.kind == "PAGE":
                                assert values["name"] == "页" * 4096
                                assert values["can_post"] is False
                            elif row.kind == "PIXEL":
                                assert values["name"] is None
                                assert values["is_restricted_use"] is True
                                assert "owner_ad_account" in row.unknown_fields
                            else:
                                assert values["name"] == ""
                                assert values["ios_bundle_id"] == [
                                    "com.fixture.one",
                                    "com.fixture.two",
                                ]
                                assert values["iphone_app_store_id"] == "001234"
                                assert values["ipad_app_store_id"] is None
                                assert row.assignment_reason == "NOT_REQUESTED_FOR_APPLICATION"
                        assert technical_token not in repr(result)
                        assert (raw_counts(), unrelated()) == before_identity
                        cases.append(IDENTITY_FACT_OBSERVATION_CASES[0])

                        first = selections[0]
                        before_network = identity_graph_requests
                        for bad in (
                            facts_module.IdentityFactSelection(
                                str(uuid4()), first.kind, first.external_id
                            ),
                            facts_module.IdentityFactSelection(
                                first.account_id, first.kind, "999999"
                            ),
                        ):
                            try:
                                await facts([bad])
                            except observer_module.MetaObservationFailure as error:
                                assert error.code == "META_ACCOUNT_SELECTION_INVALID"
                            else:
                                raise AssertionError("原始账户资源交集外不能发起查询")
                        assert identity_graph_requests == before_network
                        assert (raw_counts(), unrelated()) == before_identity
                        cases.append(IDENTITY_FACT_OBSERVATION_CASES[1])

                        page = next(row for row in selections if row.kind == "PAGE")
                        identity_mode["value"] = "pagination"
                        paged = await facts([page])
                        assigned = json.loads(paged.resources[0].assignment_facts_json)
                        assert [row["id"] for row in assigned] == ["17", "18"]
                        assert paged.request_count == 4
                        identity_mode["value"] = "incomplete"
                        try:
                            await facts([page])
                        except observer_module.MetaObservationFailure as error:
                            assert error.code == "META_OBSERVATION_INCOMPLETE"
                        else:
                            raise AssertionError("分页缺游标不能作为完整身份观察")
                        assert (raw_counts(), unrelated()) == before_identity
                        cases.append(IDENTITY_FACT_OBSERVATION_CASES[2])

                        identity_mode["value"] = "permission"
                        denied_facts = await facts([page])
                        assert denied_facts.principal_id is None
                        assert denied_facts.principal_reason == "META_READ_FORBIDDEN"
                        denied_row = denied_facts.resources[0]
                        assert (
                            denied_row.object_facts_json is denied_row.assignment_facts_json is None
                        )
                        assert (
                            denied_row.object_reason
                            == denied_row.assignment_reason
                            == "META_READ_FORBIDDEN"
                        )
                        assert technical_token not in repr(denied_facts)
                        identity_mode["value"] = "missing"
                        missing = await facts([page])
                        missing_row = missing.resources[0]
                        assert json.loads(missing_row.object_facts_json) == {
                            "id": "009",
                            "name": None,
                            "business": None,
                            "can_post": None,
                        }
                        assert missing_row.unknown_fields == ("name", "business", "can_post")
                        assert json.loads(missing_row.assignment_facts_json) == [
                            {"id": "17", "business": None, "user_type": None},
                        ]
                        assert missing.execution_authorized is False
                        assert (raw_counts(), unrelated()) == before_identity
                        cases.append(IDENTITY_FACT_OBSERVATION_CASES[3])

                    assert stage["in_get"] is False and engine.pool.checkedout() == 0
                    assert identity_network_checks == identity_graph_requests == 24
                    assert (raw_counts(), unrelated()) == before_identity
                    cases.append(IDENTITY_FACT_OBSERVATION_CASES[4])

                    import orbit_api.meta_identity_principal_binding as principal_module

                    principal_before = (raw_counts(), unrelated())
                    principal_gets_before = identity_graph_requests
                    configured_principal = sql(
                        "SELECT JSON_UNQUOTE(JSON_EXTRACT(settings_json,'$.systemUserId')) "
                        "FROM orbit_system_configuration WHERE tenant_id=%s AND id=%s",
                        (tenant, source_id),
                        fetch=True,
                    )[0][0]
                    assert configured_principal == "7"

                    async def principal_capture(*, selected_bound=enriched.bound, factory=sessions):
                        return await principal_module.capture_identity_principal(
                            factory,
                            selected_bound.source.actor_id,
                            selected_bound,
                        )

                    sql(
                        "UPDATE orbit_system_configuration SET settings_json="
                        "JSON_REMOVE(settings_json,'$.systemUserId') WHERE tenant_id=%s AND id=%s",
                        (tenant, source_id),
                    )
                    try:
                        await denied(principal_capture, 503, "META_PRINCIPAL_SOURCE_UNAVAILABLE")
                    finally:
                        sql(
                            "UPDATE orbit_system_configuration SET settings_json="
                            "JSON_SET(settings_json,'$.systemUserId',%s) "
                            "WHERE tenant_id=%s AND id=%s",
                            (configured_principal, tenant, source_id),
                        )
                    assert identity_graph_requests == principal_gets_before
                    assert (raw_counts(), unrelated()) == principal_before
                    cases.append(IDENTITY_PRINCIPAL_BINDING_CASES[0])

                    principal_source = await principal_capture()
                    assert principal_source.system_user_id == configured_principal
                    assert principal_source.source_sha256 == principal_module.source_hash(
                        principal_source
                    )
                    assert principal_source.bound.binding_sha256 == enriched.bound.binding_sha256
                    assert engine.pool.checkedout() == 0
                    identity_mode["value"] = "principal_match"
                    async with httpx.AsyncClient(
                        transport=httpx.MockTransport(identity_handler),
                        follow_redirects=False,
                    ) as identity_graph:
                        matched = await principal_module.observe_identity_principal(
                            principal_source,
                            [page],
                            transport=IdentityProtocolTransport(),
                        )
                        assert matched.principal_id == configured_principal
                        assert matched.principal_matches is True
                        assert (
                            matched.principal_type_verified
                            is matched.publication_revalidated
                            is False
                        )
                        assert matched.durable is matched.execution_authorized is False
                        assert matched.capability_version is matched.policy_version is None
                        assert matched.facts.source_binding_sha256 == enriched.bound.binding_sha256
                        assert matched.facts.principal_binding == "CONFIG_PRINCIPAL_NOT_BOUND"
                        assert matched.facts.request_count == 3
                        assert technical_token not in repr(matched)
                        assert (raw_counts(), unrelated()) == principal_before
                        cases.append(IDENTITY_PRINCIPAL_BINDING_CASES[1])

                        # 错配仍使用实际HTTP GET响应；不替换match对象/不自填expected。
                        identity_mode["value"] = "normal"
                        await denied(
                            lambda: principal_module.observe_identity_principal(
                                principal_source,
                                [page],
                                transport=IdentityProtocolTransport(),
                            ),
                            503,
                            "META_PRINCIPAL_MISMATCH",
                        )
                        assert (raw_counts(), unrelated()) == principal_before
                        cases.append(IDENTITY_PRINCIPAL_BINDING_CASES[2])

                    for mutate, restore, values in (
                        (
                            "UPDATE orbit_system_configuration SET revision=revision+1 "
                            "WHERE tenant_id=%s AND id=%s",
                            "UPDATE orbit_system_configuration SET revision=revision-1 "
                            "WHERE tenant_id=%s AND id=%s",
                            (tenant, source_id),
                        ),
                        (
                            "UPDATE orbit_ad_account SET revision=revision+1 "
                            "WHERE tenant_id=%s AND id=%s",
                            "UPDATE orbit_ad_account SET revision=revision-1 "
                            "WHERE tenant_id=%s AND id=%s",
                            (tenant, accounts[0]),
                        ),
                        (
                            "UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=%s",
                            "UPDATE orbit_account_clock SET revision=revision-1 WHERE tenant_id=%s",
                            (tenant,),
                        ),
                        (
                            "UPDATE sys_identity_subject SET auth_version=auth_version+1 "
                            "WHERE user_id=%s",
                            "UPDATE sys_identity_subject SET auth_version=auth_version-1 "
                            "WHERE user_id=%s",
                            (actor,),
                        ),
                    ):
                        sql(mutate, values)
                        try:
                            await denied(principal_capture, 409, "META_PRINCIPAL_SOURCE_CHANGED")
                        finally:
                            sql(restore, values)
                    assert (raw_counts(), unrelated()) == principal_before
                    cases.append(IDENTITY_PRINCIPAL_BINDING_CASES[3])

                    sql(
                        "DELETE FROM sys_role_menu WHERE role_id=%s AND menu_id=%s",
                        (native_role, sync_menu),
                    )
                    try:
                        await denied(principal_capture, 403, "PERMISSION_DENIED")
                    finally:
                        sql(
                            "INSERT INTO sys_role_menu(role_id,menu_id) VALUES(%s,%s)",
                            (native_role, sync_menu),
                        )
                    sql(
                        "UPDATE orbit_ad_account SET owner_user_id=%s WHERE tenant_id=%s AND id=%s",
                        (manager["owner_user_id"], tenant, accounts[0]),
                    )
                    try:
                        await denied(principal_capture, 404, "NOT_FOUND")
                    finally:
                        sql(
                            "UPDATE orbit_ad_account SET owner_user_id=%s "
                            "WHERE tenant_id=%s AND id=%s",
                            (subject, tenant, accounts[0]),
                        )
                    manager_prepared = await capture(selected_actor=manager["actor_id"])
                    try:
                        await denied(
                            lambda: principal_capture(
                                selected_bound=manager_prepared.bound,
                                factory=OldViewSession,
                            ),
                            404,
                            "NOT_FOUND",
                        )
                    finally:
                        sql(
                            "INSERT INTO orbit_business_team_manager(tenant_id,manager_user_id,"
                            "team_id,enabled) VALUES(%s,%s,%s,1)",
                            (tenant, manager["actor_id"], team),
                        )
                    assert (raw_counts(), unrelated()) == principal_before
                    cases.append(IDENTITY_PRINCIPAL_BINDING_CASES[4])

                    assert stage["in_get"] is False and engine.pool.checkedout() == 0
                    principal_graph_requests = identity_graph_requests - principal_gets_before
                    assert principal_graph_requests == 6
                    assert identity_network_checks == identity_graph_requests == 30
                    assert (raw_counts(), unrelated()) == principal_before
                    cases.append(IDENTITY_PRINCIPAL_BINDING_CASES[5])
                    event.remove(engine.sync_engine, "before_cursor_execute", observe_sql)
            finally:
                await engine.dispose()

    try:
        asyncio.run(run())
    finally:
        sql(
            "UPDATE orbit_system_configuration SET enabled=0 WHERE tenant_id=%s AND id=%s",
            (tenant, source_id),
        )
        for identifier, enabled in original_sources:
            sql(
                "UPDATE orbit_system_configuration SET enabled=%s WHERE tenant_id=%s AND id=%s",
                (enabled, tenant, identifier),
            )
    metrics = {
        "blocked_cases": [],
        "platform_requests": 0,
        "controlled_graph_gets": graph_requests + identity_graph_requests,
        "source_scope": "REAL_ROLE_CONFIGURATION_API_SQL_ACCOUNTS_HTTPX_MOCK_NOT_META_AUTHORITY",
        "clock_scope": "CONTROLLED_OBSERVATION_CLOCK_SQL_DATETIME6_NOT_NATURAL_PLATFORM_TIME",
    }
    if include_identity_facts:
        metrics.update(
            identity_controlled_graph_gets=identity_graph_requests,
            identity_network_outside_sql_checks=identity_network_checks,
            identity_scope="M1_REAL_SQL_CAPTURE_MOCK_GRAPH_FACTS_NO_023_OR_CAPABILITY_AUTHORITY",
            principal_controlled_graph_gets=principal_graph_requests,
            principal_scope="REAL_SQL_SYSTEM_USER_ID_CAS_AND_MOCK_ME_ID_MATCH_NOT_TYPE_OR_AUTHORITY",
        )
    return metrics
