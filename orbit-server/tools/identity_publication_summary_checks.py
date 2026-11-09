"""055真实专项入口；仅主线13306/UUID库，Graph/能力发行明确隔离协议。

不启服务、不外呼Meta。默认只两个账户及5000资源；百万容量必须主线另备独占
200个完整封印账户后显式传capacity_account_ids，本工具不默认加载百万行。
"""

import asyncio
import base64
import hashlib
import json
import math
import os
import platform
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

IDENTITY_SUMMARY_CASES = [
    "pythonIdentitySummaryCompleteEmptySealedOriginalGet",
    "pythonIdentitySummaryFiveThousandBoundedMetadata",
    "pythonIdentitySummaryThirteenCurrentDatabaseGuards",
    "pythonIdentitySummaryForgedMacCannotBecomeSynced",
    "pythonIdentitySummaryExplicitKeyRotationAndRetirement",
    "pythonIdentitySummaryCurrentSourceAndReleaseRevocation",
    "pythonIdentitySummaryUnpreparedNewHeadRemainsUnknown",
    "pythonIdentitySummaryUnpreparedSourceRemainsUnknown",
    "pythonIdentitySummaryOldRrAndOwnedRcObservationVisibility",
    "pythonIdentitySummaryCurrentManagedScopeRevocation",
    "pythonIdentitySummarySeal1644WholePublicationRollback",
    "pythonIdentitySummaryResourceWriterWaitsForHistoryFreeze",
]
IDENTITY_SUMMARY_CAPACITY_CASES = ["pythonIdentitySummaryTwoHundredByFiveThousandMetadataOnly"]
IDENTITY_SUMMARY_PUBLIC_CASES = ["pythonIdentitySummaryExtendedAndDetailsOriginalHttpConsistency"]
IDENTITY_SUMMARY_PROFILE_CASES = ["pythonIdentitySummaryDiagnosticTwoHundredSingleResourceHttp"]
SUMMARY_TRIGGER_NAMES = (
    "trg_identity_history_freeze_bu",
    "trg_identity_history_freeze_bd",
    "trg_identity_resource_freeze_bi",
    "trg_identity_resource_freeze_bu",
    "trg_identity_resource_freeze_bd",
    "trg_identity_evidence_freeze_bu",
    "trg_identity_evidence_freeze_bd",
    "trg_identity_head_freeze_bu",
    "trg_identity_head_freeze_bd",
    "trg_identity_proof_freeze_bi",
    "trg_identity_inventory_seal_bi",
    "trg_identity_inventory_seal_bu",
    "trg_identity_inventory_seal_bd",
)


def guard_summary_options(capacity_account_ids):
    if capacity_account_ids is None:
        return None
    from uuid import UUID

    if (
        not isinstance(capacity_account_ids, (list, tuple))
        or len(capacity_account_ids) != 200
        or any(not isinstance(v, str) or str(UUID(v)) != v for v in capacity_account_ids)
        or len(set(capacity_account_ids)) != 200
    ):
        raise ValueError("容量仅接受已独占准备的200个真实UUID，绝不默认装载百万资源")
    return tuple(sorted(capacity_account_ids))


def fixture_name_columns(name):
    """与真实account_worker导入一致：原名称保留，检索前缀仅[:191]，不转小写。"""
    if not isinstance(name, str):
        raise ValueError("夹具名称必须为原字符串")
    name.encode("utf-8")
    return name, name[:191]


def percentile(values, fraction):
    if not values or not 0 < fraction <= 1 or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("性能样本必须为实际非负有限时长")
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def safe_plan(value):
    """仅保留实际执行计划形状/rows/loops/耗时；不保存SQL或原绑定UUID。"""
    if not isinstance(value, str):
        raise ValueError("EXPLAIN ANALYZE必须实际返回文本")
    return re.sub(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", "<UUID>", value)


def run_identity_publication_summary_checks(
    client,
    admin,
    headers,
    password,
    cache,
    database,
    cases,
    *,
    cipher=None,
    capacity_account_ids=None,
    prepare_browser_fixture=False,
    prepare_capacity=False,
    prepare_http_profile=False,
    backend_pid=None,
):
    try:
        from account_scope_visibility_plan_checks import prepare_plan_identities
        from identity_publication_checks import inventory_protocol_page
        from launch_execution_guard_checks import _connect, _locked_wait
        from meta_observation_registry_checks import guard_meta_registry_target
    except ImportError:
        from tools.account_scope_visibility_plan_checks import prepare_plan_identities
        from tools.identity_publication_checks import inventory_protocol_page
        from tools.launch_execution_guard_checks import _connect, _locked_wait
        from tools.meta_observation_registry_checks import guard_meta_registry_target

    capacity_account_ids = guard_summary_options(capacity_account_ids)
    if (
        type(prepare_http_profile) is not bool
        or prepare_http_profile
        and (prepare_capacity or prepare_browser_fixture or capacity_account_ids is not None)
    ):
        raise ValueError("HTTP诊断必须单独显式运行，不能与容量或浏览器混计")
    if type(prepare_browser_fixture) is not bool:
        raise ValueError("浏览器fixture必须显式布尔值")
    if type(prepare_capacity) is not bool:
        raise ValueError("百万容量装载必须显式布尔值")
    if prepare_capacity and (prepare_browser_fixture or capacity_account_ids is not None):
        raise ValueError("容量装载、浏览器和外部预备账户消费必须互斥")
    if prepare_capacity and (type(backend_pid) is not int or backend_pid <= 0):
        raise ValueError("容量RSS必须传本轮实际API子进程PID")
    if prepare_browser_fixture and capacity_account_ids is not None:
        raise ValueError("浏览器夹具与预备百万容量消费须分开运行")
    guard_meta_registry_target(admin, database)
    if cipher is None or not cipher.ready:
        raise ValueError("055需要主线内存Cipher，不读取私有环境或重造生产密钥")

    import httpx
    from sqlalchemy import URL, event, text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import orbit_api.meta_bound_observation as bound_module
    import orbit_api.meta_identity_facts_observation as facts_module
    import orbit_api.meta_launch_observation as observer_module
    from orbit_api.account_details_contract import filters
    from orbit_api.account_details_store import AccountDetailsStore
    from orbit_api.credentials import CredentialCipher
    from orbit_api.directory_tokens import DirectoryTokens
    from orbit_api.errors import OrbitError
    from orbit_api.identity_publication_store import (
        IdentityCapabilityAuthority,
        IdentityDecision,
        IdentityPublicationStore,
        IdentityQualification,
    )
    from orbit_api.identity_publication_summary import (
        CLAIM_FIELDS,
        IdentityPublicationSummary,
        check_mac,
    )
    from orbit_api.meta_identity_principal_binding import (
        capture_identity_principal,
        observe_identity_principal,
    )
    from orbit_api.meta_observation_registry import MetaObservationRegistry
    from orbit_api.read_sessions import read_committed_session

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

    def checked(response, status):
        assert response.status_code == status, {
            "actual": response.status_code,
            "expected": status,
            "code": response.json().get("code"),
        }
        return response.json()

    actual_triggers = {
        row[0]
        for row in sql(
            "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s",
            (database,),
            fetch=True,
        )
    }
    assert set(SUMMARY_TRIGGER_NAMES).issubset(actual_triggers)
    identities = prepare_plan_identities(client, admin, headers, password, cache)
    user, manager = identities["USER"], identities["TEAM_ADMIN"]
    actor, owner, team = user["actor_id"], user["owner_user_id"], user["owner_team_id"]
    tenant = sql("SELECT tenant_id FROM orbit_business_user WHERE user_id=1", fetch=True)[0][0]
    cap = checked(client.get("/api/v1/roles/capabilities", headers=headers), 200)
    role = checked(
        client.post(
            "/api/v1/roles",
            headers=headers
            | {
                "X-CSRF-Token": cap["csrf_token"],
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "name": "摘要封印同步-" + uuid4().hex[:12],
                "menu_codes": ["accounts"],
                "permission_codes": ["accounts.sync"],
            },
        ),
        201,
    )
    native = sql(
        "SELECT native_role_id FROM orbit_business_role WHERE tenant_id=%s AND id=%s",
        (tenant, role["id"]),
        fetch=True,
    )[0][0]
    sql("INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)", (actor, native))
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
    token = "isolated-summary-" + uuid4().hex
    config = checked(
        client.post(
            "/api/v1/system-configurations",
            headers=headers | {"Idempotency-Key": str(uuid4())},
            json={
                "section": "META_BM",
                "name": "摘要协议-" + uuid4().hex[:12],
                "enabled": True,
                "settings": {"businessId": "42", "systemUserId": "7", "graphVersion": "v25.0"},
                "secrets": {"accessToken": {"operation": "REPLACE", "value": token}},
                "reason": "仅SQL/MockTransport协议，不证明Meta生产权限",
            },
        ),
        200,
    )
    config_id = config["id"]
    sql(
        "UPDATE orbit_system_configuration SET verification_status='READ_VERIFIED' WHERE "
        "tenant_id=%s AND id=%s",
        (tenant, config_id),
    )
    config_revision = sql(
        "SELECT revision FROM orbit_system_configuration WHERE tenant_id=%s AND id=%s",
        (tenant, config_id),
        fetch=True,
    )[0][0]
    account_id, anchor = str(uuid4()), str(uuid4())
    external, anchor_external = "00" + str(uuid4().int), "00" + str(uuid4().int)

    def add_account(identifier, ext, name="摘要SQL夹具"):
        sql(
            "INSERT INTO orbit_ad_account(tenant_id,id,external_id,name,name_prefix,owner_user_id,"
            "owner_team_id,currency,timezone_id,auth_status,account_status,value_json,details_json,"
            "bound_at,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'USD','UTC',"
            "'AUTHORIZED','ACTIVE','{}','{}',UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",
            (tenant, identifier, ext, *fixture_name_columns(name), owner, team),
        )

    for identifier, ext in ((account_id, external), (anchor, anchor_external)):
        add_account(identifier, ext)
    release_id, release_hash, release_version = None, None, None

    def issue_release():
        nonlocal release_id, release_hash, release_version
        release_id, release_hash = str(uuid4()), hashlib.sha256(os.urandom(32)).hexdigest()
        release_version = "isolated-summary-" + uuid4().hex[:12]
        sql(
            "INSERT INTO "
            "orbit_identity_capability_release(tenant_id,id,revision,capability_version,"
            "issuer,source_kind,source_hash,source_config_id,source_config_revision,business_id,"
            "graph_version,action_scope) VALUES(%s,%s,1,%s,'isolated-summary-issuer',"
            "'ISOLATED_PROTOCOL',%s,%s,%s,'42','v25.0','ACCOUNT_IDENTITIES_READ')",
            (tenant, release_id, release_version, release_hash, config_id, config_revision),
        )

    issue_release()
    tables = (
        "orbit_account_identity_evidence",
        "orbit_account_identity_history",
        "orbit_account_identity_head",
        "orbit_account_identity_resource",
        "orbit_identity_publication_provenance",
        "orbit_identity_publication_ledger",
        "orbit_identity_inventory_seal",
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
        nonlocal account_id, external, capacity_account_ids
        engine = create_async_engine(
            url,
            echo=False,
            hide_parameters=True,
            isolation_level="REPEATABLE READ",
            pool_size=1,
            max_overflow=2,
            pool_use_lifo=True,
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        class RegistryAdapter:
            """真实UUID引擎与会话类技术适配，不伪造数据库/连接配置。"""

            @staticmethod
            def session(*, log_sql):
                assert log_sql is False
                return sessions()

        def rc_sessions():
            return read_committed_session(RegistryAdapter)

        graph_count, network_checks, inventory_total = 0, 0, 0
        browser_mode, browser_fixture = False, None
        summary_queries, sample_metrics = [], {}
        capacity_report = None

        def save_capacity():
            if capacity_report is not None:
                output = (
                    Path(__file__).resolve().parents[1]
                    / ".runtime/identity-summary-capacity-current.json"
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps(capacity_report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

        def record_query(connection, cursor, statement, parameters, context, executemany):
            summary_queries.append(statement)

        def handler(request):
            nonlocal graph_count, network_checks
            assert engine.pool.checkedout() == 0
            network_checks += 1
            assert request.method == "GET" and request.url.host == "graph.facebook.com"
            assert request.headers["Authorization"] == "Bearer " + token
            assert token not in str(request.url)
            graph_count += 1
            path = request.url.path.removeprefix("/v25.0/")
            if path == "42/owned_ad_accounts":
                body = {
                    "data": [
                        {"id": "act_" + ext, "account_id": ext}
                        for ext in (external, anchor_external)
                    ]
                }
            elif path == "42/client_ad_accounts":
                body = {"data": []}
            elif path == "act_" + external + "/promote_pages":
                if browser_mode:
                    assert "after" not in request.url.params
                    records, after = [{"id": "001", "name": "真实隔离主页"}], None
                elif prepare_http_profile and inventory_total == 1:
                    assert "after" not in request.url.params
                    records, after = [{"id": "00000000000", "name": "单资源CPU诊断主页"}], None
                else:
                    records, after = inventory_protocol_page(
                        inventory_total, request.url.params.get("after")
                    )
                body = {"data": records}
                if after:
                    body["paging"] = {
                        "next": "https://graph.facebook.com/v25.0/" + path,
                        "cursors": {"after": after},
                    }
            elif path == "act_" + anchor_external + "/promote_pages":
                body = {"data": [{"id": "009", "name": "主体锚，不污染目标库存"}]}
            elif path.endswith(("/adspixels", "/advertisable_applications")):
                if browser_mode and path == "act_" + external + "/adspixels":
                    body = {"data": [{"id": "002", "name": "已明确不可用像素"}]}
                elif browser_mode and path == "act_" + external + "/advertisable_applications":
                    body = {"data": [{"id": "003", "name": "已明确不可用应用"}]}
                else:
                    body = {"data": []}
            elif path in {"act_" + external, "act_" + anchor_external}:
                body = {
                    "id": path,
                    "account_id": path[4:],
                    "name": "摘要夹具",
                    "currency": "USD",
                    "timezone_name": "UTC",
                    "account_status": 1,
                    "capabilities": [],
                    "user_tasks": [],
                }
            elif path == "me":
                body = {"id": "7"}
            elif path == "009":
                body = {"id": "009", "name": "主体锚", "business": {"id": "42"}, "can_post": False}
            elif path == "009/assigned_users":
                body = {"data": []}
            else:
                raise AssertionError("未声明Graph只读路径")
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
                actual = (
                    await session.execute(
                        text(
                            "SELECT source_kind FROM orbit_identity_capability_release "
                            "WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                        ),
                        {"tenant": tenant, "id": prepared.qualification.release_id},
                    )
                ).scalar_one()
                assert actual == "ISOLATED_PROTOCOL"

        store, registry = (
            IdentityPublicationStore(Authority()),
            MetaObservationRegistry(),
        )
        summary = IdentityPublicationSummary(cipher)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as graph:

            class Transport:
                async def get(self, target, headers, *, maximum_bytes):
                    response = await graph.get(target, headers=headers)
                    assert len(response.content) <= maximum_bytes
                    return observer_module.GraphReadResponse(response.status_code, response.content)

            async def prepare(expected):
                source = await bound_module.capture_meta_source(
                    sessions, actor, [account_id, anchor], cipher=cipher
                )
                bound = await bound_module.observe_meta_source(source, transport=Transport())
                async with sessions() as session, session.begin():
                    raw = await registry.register(
                        session,
                        actor,
                        registry.prepare(bound),
                        key="summary-raw-" + uuid4().hex,
                        request_id=str(uuid4()),
                    )
                principal = await capture_identity_principal(sessions, actor, bound)
                match = await observe_identity_principal(
                    principal,
                    [facts_module.IdentityFactSelection(anchor, "PAGE", "009")],
                    transport=Transport(),
                )
                return await store.prepare(
                    match, account_id, registry_id=raw["registry_id"], expected_revision=expected
                )

            async def persist(prepared, *, sealer=summary):
                async with sessions() as session, session.begin():
                    ticket = await sealer.prepare_publication(session, actor, prepared)
                    receipt = await store.register(
                        session,
                        actor,
                        prepared,
                        key="summary-publish-" + uuid4().hex,
                        request_id=str(uuid4()),
                    )
                    assert await sealer.seal_published(session, actor, prepared, receipt, ticket)
                    return receipt

            async def read_summary(*, model=summary, factory=rc_sessions, selected_actor=actor):
                async with factory() as session, session.begin():
                    page = await AccountDetailsStore(
                        DirectoryTokens(cipher), identity_summary=model
                    ).list(session, selected_actor, filters({"q": external}), identifier=account_id)
                    assert len(page["items"]) == 1
                    assert page["items"][0]["account"]["id"] == account_id
                    return {
                        key: page["items"][0]["details"][key]
                        for key in ("identity_status", "identity_count", "identity_observed_at")
                    }

            def state():
                return counts(), sql(
                    "SELECT h.revision,v.resource_count,v.evidence_id FROM "
                    "orbit_account_identity_head h "
                    "JOIN orbit_account_identity_history v ON v.tenant_id=h.tenant_id AND "
                    "v.account_id=h.account_id "
                    "AND v.revision=h.revision WHERE h.tenant_id=%s AND h.account_id=%s",
                    (tenant, account_id),
                    fetch=True,
                )

            def rejected(statement, values):
                before = state()
                try:
                    with admin.cursor() as cursor:
                        cursor.execute(statement, values)
                except Exception as error:
                    assert error.args[0] == 1644, {"errno": error.args[0], "expected": 1644}
                else:
                    raise AssertionError("冻结后修改必须精确1644")
                finally:
                    admin.rollback()
                assert state() == before

            try:
                first = await prepare(0)
                first_receipt = await persist(first)
                value = await read_summary()
                assert value["identity_status"] == "SYNCED" and value["identity_count"] == 0
                assert value["identity_observed_at"] == first_receipt["observed_at"]
                response = checked(
                    client.get(
                        f"/api/v1/accounts/{account_id}/identities", headers=user["headers"]
                    ),
                    200,
                )
                assert response == json.loads(first.payload_json) and response["resources"] == []
                cases.append(IDENTITY_SUMMARY_CASES[0])

                inventory_total = 5000
                second = await prepare(1)
                second_receipt = await persist(second)
                event.listen(engine.sync_engine, "before_cursor_execute", record_query)
                started = time.perf_counter()
                try:
                    value = await read_summary()
                finally:
                    event.remove(engine.sync_engine, "before_cursor_execute", record_query)
                sample_metrics["single_5000_summary_seconds"] = time.perf_counter() - started
                assert value["identity_status"] == "SYNCED" and value["identity_count"] == 5000
                assert not any(
                    "orbit_account_identity_resource" in statement for statement in summary_queries
                )
                assert checked(
                    client.get(
                        f"/api/v1/accounts/{account_id}/identities", headers=user["headers"]
                    ),
                    200,
                ) == json.loads(second.payload_json)
                cases.append(IDENTITY_SUMMARY_CASES[1])
                # 原HTTP当前admin范围，逐项比较同一完整库存与观察时刻，不自造公开DTO。
                original = checked(
                    client.get(f"/api/v1/accounts/{account_id}/identities", headers=headers), 200
                )
                expected_summary = {
                    "identity_status": "SYNCED",
                    "identity_count": len(original["resources"]),
                    "identity_observed_at": original["observed_at"],
                }
                extended = checked(
                    client.get(
                        "/api/v1/accounts/extended", params={"q": external}, headers=headers
                    ),
                    200,
                )
                assert len(extended["items"]) == 1
                detailed = checked(
                    client.get(f"/api/v1/accounts/{account_id}/details", headers=headers), 200
                )
                for item in (extended["items"][0], detailed):
                    assert item["account"]["id"] == account_id
                    for field, expected in expected_summary.items():
                        assert item["details"][field] == expected, {"field": field}
                assert expected_summary["identity_count"] == 5000
                cases.append(IDENTITY_SUMMARY_PUBLIC_CASES[0])
                # 归还后取回同一物理连接检查恢复RR，不用新连接假称池恢复。
                async with rc_sessions() as session, session.begin():
                    rc_id = (await session.execute(text("SELECT CONNECTION_ID()"))).scalar_one()
                    level = (
                        await session.execute(text("SELECT @@transaction_isolation"))
                    ).scalar_one()
                    assert level == "READ-COMMITTED"
                async with sessions() as session, session.begin():
                    restored = (await session.execute(text("SELECT CONNECTION_ID()"))).scalar_one()
                    level = (
                        await session.execute(text("SELECT @@transaction_isolation"))
                    ).scalar_one()
                    assert restored == rc_id and level == "REPEATABLE-READ"

                common = (tenant, account_id)
                eid = second_receipt["evidence_id"]
                attacks = [
                    (
                        "UPDATE orbit_account_identity_history SET resource_count=4999 WHERE "
                        "tenant_id=%s AND account_id=%s AND revision=2",
                        common,
                    ),
                    (
                        "DELETE FROM orbit_account_identity_history WHERE tenant_id=%s AND "
                        "account_id=%s AND revision=2",
                        common,
                    ),
                    (
                        "INSERT INTO "
                        "orbit_account_identity_resource(tenant_id,account_id,revision,kind,"
                        "external_id,name,usable) "
                        "VALUES(%s,%s,2,'PAGE','987654321','禁止后插',1)",
                        common,
                    ),
                    (
                        "UPDATE orbit_account_identity_resource SET usable=2 WHERE "
                        "tenant_id=%s AND account_id=%s AND revision=2 LIMIT 1",
                        common,
                    ),
                    (
                        "DELETE FROM orbit_account_identity_resource WHERE tenant_id=%s AND "
                        "account_id=%s AND revision=2 LIMIT 1",
                        common,
                    ),
                    (
                        "UPDATE orbit_account_identity_evidence SET complete=0 WHERE "
                        "tenant_id=%s AND id=%s",
                        (tenant, eid),
                    ),
                    (
                        "DELETE FROM orbit_account_identity_evidence WHERE tenant_id=%s AND id=%s",
                        (tenant, eid),
                    ),
                    (
                        "UPDATE orbit_account_identity_head SET revision=1 WHERE tenant_id=%s "
                        "AND account_id=%s",
                        common,
                    ),
                    (
                        "DELETE FROM orbit_account_identity_head WHERE tenant_id=%s AND "
                        "account_id=%s",
                        common,
                    ),
                ]
                for statement, values in attacks:
                    rejected(statement, values)
                for table, altered, changed in (
                    ("orbit_identity_publication_provenance", "payload_hash", "b" * 64),
                    ("orbit_identity_inventory_seal", "resource_count", 4999),
                ):
                    columns = [r[0] for r in sql("SHOW COLUMNS FROM " + table, fetch=True)]
                    select = ["%s" if c == altered else c for c in columns]
                    rejected(
                        "INSERT INTO "
                        + table
                        + "("
                        + ",".join(columns)
                        + ") SELECT "
                        + ",".join(select)
                        + " FROM "
                        + table
                        + " WHERE tenant_id=%s AND evidence_id=%s",
                        (changed, tenant, eid),
                    )
                rejected(
                    "UPDATE orbit_identity_inventory_seal SET mac=%s WHERE tenant_id=%s AND "
                    "evidence_id=%s",
                    ("B" * 43, tenant, eid),
                )
                rejected(
                    "DELETE FROM orbit_identity_inventory_seal WHERE tenant_id=%s AND "
                    "evidence_id=%s",
                    (tenant, eid),
                )
                cases.append(IDENTITY_SUMMARY_CASES[2])

                # 真SQL插入结构合法但无有效MAC的seal，证明DB绑定/COUNT不能替代签名。
                inventory_total = 0
                third = await prepare(2)
                async with sessions() as session, session.begin():
                    ticket = await summary.prepare_publication(session, actor, third)
                    bad_receipt = await store.register(
                        session, actor, third, key="bad-mac-" + uuid4().hex, request_id=str(uuid4())
                    )
                    heads, evidence, proofs, _, _ = await summary._metadata(
                        session, ticket.current, [account_id]
                    )
                    proof = proofs[bad_receipt["evidence_id"]]
                    from orbit_api.identity_publication_store import current_accounts

                    account = (
                        await current_accounts(session, ticket.current, [account_id], write=True)
                    )[0]
                    values = summary._expected(
                        ticket.current,
                        account,
                        heads[account_id],
                        evidence[bad_receipt["evidence_id"]],
                        proof,
                        cipher.active_key_id,
                    )
                    values["mac"] = "A" * 43
                    assert not check_mac(cipher, values)
                    await session.execute(
                        text(
                            "INSERT INTO orbit_identity_inventory_seal("
                            + ",".join(CLAIM_FIELDS)
                            + ",mac) VALUES("
                            + ",".join(":" + k for k in CLAIM_FIELDS)
                            + ",:mac)"
                        ),
                        values,
                    )
                assert (await read_summary())["identity_status"] == "UNKNOWN"
                cases.append(IDENTITY_SUMMARY_CASES[3])

                keys = {name: base64.b64encode(os.urandom(32)).decode() for name in ("old", "new")}
                old, rotated, retired = (
                    CredentialCipher("old", keys),
                    CredentialCipher("new", keys),
                    CredentialCipher("new", {"new": keys["new"]}),
                )
                fourth = await prepare(3)
                await persist(fourth, sealer=IdentityPublicationSummary(old))
                assert (await read_summary(model=IdentityPublicationSummary(rotated)))[
                    "identity_status"
                ] == "SYNCED"
                assert (await read_summary(model=IdentityPublicationSummary(retired)))[
                    "identity_status"
                ] == "UNKNOWN"
                assert (await read_summary())[
                    "identity_status"
                ] == "UNKNOWN"  # 生产keyring未持fixture old。
                fifth = await prepare(4)
                await persist(fifth)
                cases.append(IDENTITY_SUMMARY_CASES[4])

                sql(
                    "UPDATE orbit_system_configuration SET enabled=0 WHERE tenant_id=%s AND id=%s",
                    (tenant, config_id),
                )
                assert (await read_summary())["identity_status"] == "UNKNOWN"
                sql(
                    "UPDATE orbit_system_configuration SET enabled=1 WHERE tenant_id=%s AND id=%s",
                    (tenant, config_id),
                )
                sql(
                    "UPDATE orbit_identity_capability_release SET revoked_at=UTC_TIMESTAMP(6) "
                    "WHERE tenant_id=%s AND id=%s",
                    (tenant, release_id),
                )
                assert (await read_summary())["identity_status"] == "UNKNOWN"
                issue_release()
                sixth = await prepare(5)
                await persist(sixth)
                cases.append(IDENTITY_SUMMARY_CASES[5])

                seventh = await prepare(6)
                # prepare前已有RR view；并发发布完成后RC普通probe必须读到新头。
                async with sessions() as old_rr, rc_sessions() as current_rc:
                    await old_rr.execute(text("SELECT COUNT(*) FROM orbit_account_identity_head"))
                    await current_rc.execute(
                        text("SELECT COUNT(*) FROM orbit_account_identity_head")
                    )
                    await persist(seventh)
                    old_ticket = await summary.prepare(old_rr, actor, [account_id])
                    old_result = await summary.resolve(
                        old_rr, actor, [{"id": account_id}], old_ticket
                    )
                    assert old_result[account_id]["identity_status"] == "UNKNOWN"
                    cases.append(IDENTITY_SUMMARY_CASES[6])
                    rc_ticket = await summary.prepare(current_rc, actor, [account_id])
                    rc_result = await summary.resolve(
                        current_rc, actor, [{"id": account_id}], rc_ticket
                    )
                    isolation = (
                        await current_rc.execute(text("SELECT @@transaction_isolation"))
                    ).scalar_one()
                    assert (
                        isolation == "READ-COMMITTED"
                        and rc_result[account_id]["identity_status"] == "SYNCED"
                    )
                    await old_rr.rollback()
                    await current_rc.rollback()
                cases.append(IDENTITY_SUMMARY_CASES[8])

                # 已持clock后不补首次来源锁；空来源票据遇当前头只能UNKNOWN。
                from dataclasses import replace
                from types import MappingProxyType

                async with rc_sessions() as session, session.begin():
                    ticket = await summary.prepare(session, actor, [])
                    ticket = replace(ticket, configurations=(), releases=MappingProxyType({}))
                    result = await summary.resolve(session, actor, [{"id": account_id}], ticket)
                    assert result[account_id]["identity_status"] == "UNKNOWN"
                marker = "摘要候选-" + uuid4().hex[:8]
                sql(
                    "UPDATE orbit_ad_account SET name=%s,name_prefix=%s "
                    "WHERE tenant_id=%s AND id=%s",
                    (*fixture_name_columns(marker), tenant, anchor),
                )

                class PageChangedSummary(IdentityPublicationSummary):
                    async def prepare(self, session, selected_actor, candidates):
                        assert anchor in candidates and account_id not in candidates
                        ticket = await super().prepare(session, selected_actor, candidates)
                        # 明确SQL并发夹具，不给原写方补clock掩盖反例。
                        sql(
                            "UPDATE orbit_ad_account SET name=%s,name_prefix=%s "
                            "WHERE tenant_id=%s AND id=%s",
                            (*fixture_name_columns(marker), tenant, account_id),
                        )
                        return ticket

                try:
                    async with rc_sessions() as session, session.begin():
                        page = await AccountDetailsStore(
                            DirectoryTokens(cipher), identity_summary=PageChangedSummary(cipher)
                        ).list(session, actor, filters({"q": marker}))
                        current_items = {item["account"]["id"]: item for item in page["items"]}
                        assert set(current_items) == {account_id, anchor}
                        assert current_items[account_id]["details"]["identity_status"] == "UNKNOWN"
                        assert current_items[account_id]["details"]["identity_count"] is None
                        assert current_items[anchor]["details"]["identity_status"] == "UNSYNCED"
                finally:
                    sql(
                        "UPDATE orbit_ad_account SET name=%s,name_prefix=%s WHERE tenant_id=%s "
                        "AND id IN (%s,%s)",
                        (*fixture_name_columns("摘要SQL夹具"), tenant, account_id, anchor),
                    )
                cases.append(IDENTITY_SUMMARY_CASES[7])

                async with sessions() as session:
                    try:
                        await session.execute(
                            text("SELECT COUNT(*) FROM orbit_business_team_manager")
                        )
                        sql(
                            "DELETE FROM orbit_business_team_manager WHERE tenant_id=%s AND "
                            "manager_user_id=%s AND team_id=%s",
                            (tenant, manager["actor_id"], team),
                        )
                        try:
                            ticket = await summary.prepare(
                                session, manager["actor_id"], [account_id]
                            )
                            await summary.resolve(
                                session, manager["actor_id"], [{"id": account_id}], ticket
                            )
                        except OrbitError as error:
                            assert (error.status, error.code) == (404, "NOT_FOUND")
                        else:
                            raise AssertionError("旧RR不得保留已撤销管理范围")
                    finally:
                        await session.rollback()
                        sql(
                            "INSERT INTO "
                            "orbit_business_team_manager(tenant_id,manager_user_id,team_id,enabled)"
                            " "
                            "VALUES(%s,%s,%s,1)",
                            (tenant, manager["actor_id"], team),
                        )
                cases.append(IDENTITY_SUMMARY_CASES[9])

                eighth = await prepare(7)
                before = state()
                temporary = "trg_fixture_summary_abort_" + uuid4().hex[:10]
                sql(
                    "CREATE TRIGGER "
                    + temporary
                    + " BEFORE INSERT ON orbit_identity_inventory_seal FOR EACH ROW "
                    "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='ISOLATED_SEAL_ROLLBACK'"
                )
                try:
                    try:
                        await persist(eighth)
                    except DBAPIError as error:
                        assert error.orig.args[0] == 1644
                    else:
                        raise AssertionError("seal失败必须整笔发布回滚")
                    assert state() == before
                finally:
                    sql("DROP TRIGGER " + temporary)
                cases.append(IDENTITY_SUMMARY_CASES[10])

                with ThreadPoolExecutor(max_workers=1) as pool:
                    holder, writer = _connect(admin, database), _connect(admin, database)
                    observer = _connect(admin, database)
                    observer.autocommit(True)
                    try:
                        with holder.cursor() as cursor:
                            cursor.execute(
                                "SELECT revision FROM orbit_account_identity_history WHERE "
                                "tenant_id=%s AND account_id=%s AND revision=7 FOR UPDATE",
                                (tenant, account_id),
                            )
                        with writer.cursor() as cursor:
                            cursor.execute("SELECT CONNECTION_ID()")
                            writer_id = cursor.fetchone()[0]

                        # 当前7是完整空库存，先验证禁止后插；INSERT触发H SHARE与holder同步。
                        def insert_attempt():
                            try:
                                with writer.cursor() as cursor:
                                    cursor.execute(
                                        "INSERT INTO "
                                        "orbit_account_identity_resource(tenant_id,account_id,"
                                        "revision,kind,external_id,name,usable) "
                                        "VALUES(%s,%s,7,'PAGE','111111','禁止并发后插',1)",
                                        (tenant, account_id),
                                    )
                                writer.commit()
                                return 0
                            except Exception as error:
                                writer.rollback()
                                return error.args[0]

                        future = pool.submit(insert_attempt)
                        _locked_wait(observer, writer_id, pending=future)
                        holder.rollback()
                        assert future.result(timeout=5) == 1644
                    finally:
                        holder.rollback()
                        holder.close()
                        writer.close()
                        observer.close()
                cases.append(IDENTITY_SUMMARY_CASES[11])

                if prepare_browser_fixture:
                    # 保留原revoked发行负例，另建独立有效发行及完整3项库存供真实UI。
                    browser_mode = True
                    issue_release()
                    browser_prepared = await prepare(7)
                    await persist(browser_prepared)
                    expected = json.loads(browser_prepared.payload_json)
                    expected_summary = {
                        "identity_status": "SYNCED",
                        "identity_count": 3,
                        "identity_observed_at": expected["observed_at"],
                    }
                    assert len(expected["resources"]) == 3
                    assert {r["usable"] for r in expected["resources"]} == {True, False}
                    assert any(r["reason_code"] is not None for r in expected["resources"])
                    assert await read_summary() == expected_summary
                    assert (
                        checked(
                            client.get(
                                f"/api/v1/accounts/{account_id}/identities", headers=headers
                            ),
                            200,
                        )
                        == expected
                    )
                    browser_fixture = {
                        "account_id": account_id,
                        "external_id": external,
                        "expected": expected,
                        "expected_summary": expected_summary,
                    }

                profile_diagnostic = None
                if prepare_http_profile:
                    # 只定位200行HTTP的CPU，完整来源链保留；200资源绝不标百万容量通过。
                    profile_prefix = "summary-profile-" + uuid4().hex[:10] + "-"
                    inventory_total, browser_mode = 1, False
                    profile_expected = {}
                    for index in range(200):
                        account_id, external = str(uuid4()), "00" + str(uuid4().int)
                        add_account(account_id, external, profile_prefix + str(index).zfill(3))
                        prepared = await prepare(0)
                        assert len(json.loads(prepared.payload_json)["resources"]) == 1
                        receipt = await persist(prepared)
                        profile_expected[account_id] = {
                            "identity_status": "SYNCED",
                            "identity_count": 1,
                            "identity_observed_at": receipt["observed_at"],
                        }

                    def profile_http_read():
                        began = time.perf_counter()
                        response = client.get(
                            "/api/v1/accounts/extended",
                            headers=headers,
                            params={"q": profile_prefix, "page_size": "200"},
                        )
                        elapsed = time.perf_counter() - began
                        page = checked(response, 200)
                        assert page["next_cursor"] is None and len(page["items"]) == 200
                        assert {item["account"]["id"] for item in page["items"]} == set(
                            profile_expected
                        )
                        for item in page["items"]:
                            for key, expected in profile_expected[item["account"]["id"]].items():
                                assert item["details"][key] == expected
                        return elapsed

                    elapsed_samples = [profile_http_read() for _ in range(2)]
                    profile_barrier = threading.Barrier(20)

                    def profile_worker(_):
                        profile_barrier.wait(timeout=10)
                        return [profile_http_read() for _ in range(10)]

                    with ThreadPoolExecutor(max_workers=20) as workers:
                        concurrent = [
                            v for batch in workers.map(profile_worker, range(20)) for v in batch
                        ]
                    profile_diagnostic = {
                        "scope": "200账户各1资源的完整链路HTTP CPU诊断，非容量验收",
                        "accounts": 200,
                        "resources": 200,
                        "http_seconds": elapsed_samples,
                        "capacity_passed": False,
                        "unprofiled_concurrent": {
                            "samples": len(concurrent),
                            "concurrency": 20,
                            "p50_seconds": percentile(concurrent, 0.50),
                            "p95_seconds": percentile(concurrent, 0.95),
                            "p99_seconds": percentile(concurrent, 0.99),
                        },
                    }
                    cases.append(IDENTITY_SUMMARY_PROFILE_CASES[0])
                capacity_expected, capacity_prefix = {}, None
                if prepare_capacity:
                    import psutil

                    process = psutil.Process(backend_pid)
                    capacity_report = {
                        "status": "RUNNING",
                        "phase": "loading",
                        "scope": "200账户×5000完整身份库存；非Meta或全部项目容量",
                        "cache_note": "首读/暖读，装载及Store检查已可暖缓存；不是冷缓存",
                        "machine": {
                            "os": platform.platform(),
                            "logical_cpus": os.cpu_count(),
                            "memory_bytes": psutil.virtual_memory().total,
                        },
                        "backend_rss_before_bytes": process.memory_info().rss,
                        "rss_note": "前后采样RSS，不是峰值/独立Worker峰值/泄漏证明",
                        "mysql_version": sql("SELECT VERSION()", fetch=True)[0][0],
                        "mysql_settings": dict(
                            zip(
                                (
                                    "buffer_pool_bytes",
                                    "redo_capacity_bytes",
                                    "flush_log_at_trx_commit",
                                ),
                                sql(
                                    "SELECT @@global.innodb_buffer_pool_size,"
                                    "@@global.innodb_redo_log_capacity,"
                                    "@@global.innodb_flush_log_at_trx_commit",
                                    fetch=True,
                                )[0],
                                strict=True,
                            )
                        ),
                        "metrics": sample_metrics,
                        "target_p95_seconds": 1.0,
                    }
                    save_capacity()
                    # 每户都走完整M1/M2/M3→Qualification→C1→full hash→MAC，不复制SQL seal。
                    capacity_prefix = "摘要容量-" + uuid4().hex[:12] + "-"
                    inventory_total, browser_mode = 5000, False
                    identifiers = []
                    started = time.perf_counter()
                    initial_graph = graph_count
                    for index in range(200):
                        account_id, external = str(uuid4()), "00" + str(uuid4().int)
                        add_account(account_id, external, capacity_prefix + str(index).zfill(3))
                        prepared = await prepare(0)
                        assert len(json.loads(prepared.payload_json)["resources"]) == 5000
                        receipt = await persist(prepared)
                        identifiers.append(account_id)
                        capacity_expected[account_id] = {
                            "identity_status": "SYNCED",
                            "identity_count": 5000,
                            "identity_observed_at": receipt["observed_at"],
                        }
                        if (index + 1) % 20 == 0:
                            print(
                                json.dumps(
                                    {
                                        "identity_summary_capacity_progress": {
                                            "phase": "full_protocol_loading",
                                            "accounts_completed": index + 1,
                                            "resources_published": (index + 1) * 5000,
                                            "elapsed_seconds": round(
                                                time.perf_counter() - started, 3
                                            ),
                                        }
                                    }
                                ),
                                flush=True,
                            )
                            capacity_report["accounts_completed"] = index + 1
                            capacity_report["resources_published"] = (index + 1) * 5000
                            save_capacity()
                    capacity_account_ids = tuple(sorted(identifiers))
                    sample_metrics["capacity_load_seconds"] = time.perf_counter() - started
                    sample_metrics["capacity_load_controlled_graph_gets"] = (
                        graph_count - initial_graph
                    )

                if capacity_account_ids is not None:
                    # 仅消费主线明确预备的独占完整fixture；本入口不会隐式加载百万行。
                    # 容量来源属于主线预备fixture，先恢复其原配置，不让本窄档来源抢唯一位。
                    if not prepare_capacity:
                        sql(
                            "UPDATE orbit_system_configuration SET enabled=0 "
                            "WHERE tenant_id=%s AND id=%s",
                            (tenant, config_id),
                        )
                        for identifier, enabled in original_sources:
                            sql(
                                "UPDATE orbit_system_configuration SET enabled=%s "
                                "WHERE tenant_id=%s AND id=%s",
                                (enabled, tenant, identifier),
                            )
                    placeholders = ",".join(["%s"] * 200)
                    loaded = sql(
                        "SELECT h.account_id,COUNT(*) FROM orbit_account_identity_head h "
                        "JOIN orbit_account_identity_resource r ON r.tenant_id=h.tenant_id "
                        "AND r.account_id=h.account_id AND r.revision=h.revision "
                        "WHERE h.tenant_id=%s AND h.account_id IN (" + placeholders + ") "
                        "GROUP BY h.account_id",
                        (tenant, *capacity_account_ids),
                        fetch=True,
                    )
                    assert {row[0]: row[1] for row in loaded} == {
                        identifier: 5000 for identifier in capacity_account_ids
                    }
                    sample_metrics["capacity_actual_accounts"] = len(loaded)
                    sample_metrics["capacity_actual_resources"] = sum(row[1] for row in loaded)
                    capacity_queries = []
                    captured_reads = {}

                    def capacity_query(*args):
                        capacity_queries.append(args[2])
                        statement, parameters = args[2], args[3]
                        if not statement.lstrip().upper().startswith("SELECT"):
                            return
                        for table, label in (
                            ("orbit_account_identity_head h", "head"),
                            ("orbit_identity_publication_provenance", "proof"),
                            ("orbit_identity_inventory_seal", "seal"),
                            ("orbit_meta_raw_head", "raw"),
                            ("orbit_system_configuration", "config"),
                        ):
                            if "FROM " + table in statement:
                                if label == "head" and "FOR SHARE OF h,v" not in statement:
                                    continue
                                captured_reads[label] = (statement, parameters)

                    event.listen(engine.sync_engine, "before_cursor_execute", capacity_query)
                    try:
                        started = time.perf_counter()
                        async with rc_sessions() as session, session.begin():
                            ticket = await summary.prepare(session, 1, capacity_account_ids)
                            result = await summary.resolve(
                                session,
                                1,
                                [{"id": identifier} for identifier in capacity_account_ids],
                                ticket,
                            )
                        sample_metrics["capacity_summary_seconds"] = time.perf_counter() - started
                        if prepare_capacity:
                            started = time.perf_counter()
                            async with rc_sessions() as session, session.begin():
                                actual_page = await AccountDetailsStore(
                                    DirectoryTokens(cipher), identity_summary=summary
                                ).list(
                                    session, 1, filters({"q": capacity_prefix, "page_size": "200"})
                                )
                            sample_metrics["capacity_store_seconds"] = time.perf_counter() - started
                            assert actual_page["next_cursor"] is None
                            assert {item["account"]["id"] for item in actual_page["items"]} == set(
                                capacity_account_ids
                            )
                            for item in actual_page["items"]:
                                for field, expected in capacity_expected[
                                    item["account"]["id"]
                                ].items():
                                    assert item["details"][field] == expected
                    finally:
                        event.remove(engine.sync_engine, "before_cursor_execute", capacity_query)
                    assert len(result) == 200 and all(
                        value["identity_status"] == "SYNCED" and value["identity_count"] == 5000
                        for value in result.values()
                    )
                    assert not any(
                        "orbit_account_identity_resource" in statement
                        for statement in capacity_queries
                    )
                    if prepare_capacity:
                        capacity_report["phase"] = "http_first_warm_and_concurrent"

                        def http_read():
                            started = time.perf_counter()
                            response = client.get(
                                "/api/v1/accounts/extended",
                                headers=headers,
                                params={"q": capacity_prefix, "page_size": "200"},
                            )
                            elapsed = time.perf_counter() - started
                            page = checked(response, 200)
                            assert page["next_cursor"] is None
                            assert len(page["items"]) == 200
                            assert {item["account"]["id"] for item in page["items"]} == set(
                                capacity_account_ids
                            )
                            for item in page["items"]:
                                for field, expected in capacity_expected[
                                    item["account"]["id"]
                                ].items():
                                    assert item["details"][field] == expected
                            return elapsed, len(response.content)

                        first, size = http_read()
                        warm, _ = http_read()
                        sample_metrics.update(
                            capacity_http_seconds=first,
                            capacity_warm_http_seconds=warm,
                            capacity_http_bytes=size,
                        )
                        barrier = threading.Barrier(20)

                        def http_worker(_):
                            barrier.wait(timeout=10)
                            return [http_read()[0] for _ in range(10)]

                        started = time.perf_counter()
                        with ThreadPoolExecutor(max_workers=20) as workers:
                            samples = [
                                v for batch in workers.map(http_worker, range(20)) for v in batch
                            ]
                        elapsed = time.perf_counter() - started
                        measurement = {
                            "concurrency": 20,
                            "samples": len(samples),
                            "p50_seconds": percentile(samples, 0.50),
                            "p95_seconds": percentile(samples, 0.95),
                            "p99_seconds": percentile(samples, 0.99),
                            "throughput_per_second": len(samples) / elapsed,
                            "elapsed_seconds": elapsed,
                            "error_samples": 0,
                        }
                        capacity_report["http_warm_concurrent"] = measurement
                        capacity_report["backend_rss_after_bytes"] = process.memory_info().rss
                        assert set(captured_reads) == {"head", "proof", "seal", "raw", "config"}
                        plans = {}
                        for label, (statement, parameters) in captured_reads.items():
                            assert "orbit_account_identity_resource" not in statement
                            natural = re.sub(
                                r"\s+FORCE\s+INDEX\s*\([^)]*\)", "", statement, flags=re.I
                            )
                            with admin.cursor() as cursor:
                                cursor.execute("EXPLAIN ANALYZE " + statement, parameters)
                                actual = [safe_plan(row[0]) for row in cursor.fetchall()]
                                admin.rollback()
                                cursor.execute("EXPLAIN ANALYZE " + natural, parameters)
                                without_force = [safe_plan(row[0]) for row in cursor.fetchall()]
                                admin.rollback()
                            assert not any(
                                "orbit_account_identity_resource" in row
                                for row in actual + without_force
                            )
                            plans[label] = {
                                "actual_statement": actual,
                                "natural_without_force_index": without_force,
                                "actual_had_force_index": "FORCE INDEX" in statement.upper(),
                            }
                        capacity_report["actual_explain_analyze"] = plans
                        capacity_report["store_resource_queries"] = 0
                        save_capacity()
                        assert len(samples) == 200 and measurement["p95_seconds"] <= 1.0
                        capacity_report.update(status="PASS", phase="complete")
                        save_capacity()
                    cases.append(IDENTITY_SUMMARY_CAPACITY_CASES[0])
                return {
                    "controlled_graph_gets": graph_count,
                    "network_without_sql_checks": network_checks,
                    "real_meta_requests": 0,
                    "execution_authorized": False,
                    "release_source": "ISOLATED_PROTOCOL",
                    "summary_batch_sql": len(summary_queries),
                    "default_capacity_loaded": False,
                    "explicit_capacity_prepared": prepare_capacity,
                    "capacity_accounts": 200 if capacity_account_ids is not None else 0,
                    "metrics": sample_metrics,
                    **(
                        {"http_profile_diagnostic": profile_diagnostic}
                        if prepare_http_profile
                        else {}
                    ),
                    **({"capacity_report": capacity_report} if prepare_capacity else {}),
                    **({"browser_fixture": browser_fixture} if prepare_browser_fixture else {}),
                }
            except BaseException:
                if capacity_report is not None:
                    capacity_report["status"] = "FAIL"
                    save_capacity()
                raise
            finally:
                await engine.dispose()
                if not prepare_browser_fixture or browser_fixture is None:
                    sql(
                        "UPDATE orbit_system_configuration SET enabled=0 "
                        "WHERE tenant_id=%s AND id=%s",
                        (tenant, config_id),
                    )
                    for identifier, enabled in original_sources:
                        sql(
                            "UPDATE orbit_system_configuration SET enabled=%s WHERE tenant_id=%s "
                            "AND id=%s",
                            (enabled, tenant, identifier),
                        )

    return asyncio.run(run())
