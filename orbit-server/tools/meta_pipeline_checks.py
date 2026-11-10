"""Meta生产读取链真实MySQL验收；网络明确为合成Graph，不声明外部Meta通过。"""

import asyncio
import hashlib
import json
import re
import secrets
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PIPELINE_CASES = (
    "metaPipelineRealOAuthImportProfilePublication",
    "metaPipelineSevenDayOriginalFactsAndQuery",
    "metaPipelineNinetyDayAsyncReportRestart",
    "metaPipelinePartialPagesNeverPublished",
    "metaPipelineOutOfOrderPreservesNewerCapture",
    "metaPipelineRevokedSourceBlocksCaptureKeepsHistory",
    "metaPipelineReauthorizationNewJobOldProfileAndOldJobBlocked",
    "metaPipelineManualSyncAtomicPolicyAndIdempotency",
    "metaPipelineAuthFailureInvalidatesOnlyMatchingSourceRevision",
    "metaPipelineDisabledProfileExplicitHistoryVersion",
    "metaPipelineOriginalImportAndMetadataSyncAuthFailureCAS",
    "two_connection_policy_independent",
    "connection_policy_idempotent_replay",
    "connection_policy_cross_target_key_rejected",
    "connection_policy_wrong_source_rejected",
    "metaPipelineTwoConnectionIndependentEnqueue",
)


def run_meta_pipeline_checks(admin, database, cases, values):
    if (
        admin.host != "127.0.0.1"
        or admin.port != 13306
        or not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database)
    ):
        raise ValueError("仅允许127.0.0.1:13306本轮隔离UUID库")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("实际库不一致")
    admin.commit()

    def decode(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decode(admin.user),
        password=decode(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )
    with tempfile.TemporaryDirectory(prefix="orbit-meta-pipeline-") as folder:
        asyncio.run(_checks(url, values, cases, folder))


class PipelineGraph:
    """受控完整Graph响应走真实adapter归一化；无网络、无广告写方法。"""

    def __init__(self, external):
        self.external = external
        self.spend = "0.123456"
        self.pending = False
        self.partial = False
        self.auth_failed = False
        self.report_starts = 0
        self.calls = 0
        self.report_window = None

    async def request(self, method, path, parameters, token, *, maximum_bytes):
        from orbit_api.meta_read_adapter import GraphResponse, validate_graph_parameters
        from orbit_api.meta_read_contract import MetaReadFailure

        self.calls += 1
        validate_graph_parameters(method, path, parameters)
        if self.auth_failed:
            raise MetaReadFailure("META_AUTH_FAILED")
        account = {
            "id": "act_" + self.external,
            "account_id": self.external,
            "name": "管线隔离账户",
            "currency": "USD",
            "timezone_name": "UTC",
            "account_status": 1,
        }
        if method == "POST":
            assert path.endswith("/act_" + self.external + "/insights")
            self.report_starts += 1
            self.report_window = json.loads(parameters["time_range"])
            payload = {"report_run_id": "98001"}
        elif path.endswith("/98001"):
            payload = {
                "id": "98001",
                "account_id": self.external,
                "async_status": "Job Running" if self.pending else "Job Completed",
                "async_percent_completion": 10 if self.pending else 100,
            }
        elif path.endswith("/me"):
            payload = {"id": self.external, "name": "管线授权主体"}
        elif path.endswith("/adaccounts"):
            payload = {"data": [account]}
        elif path.endswith("/act_" + self.external):
            payload = account
        elif path.endswith("/campaigns"):
            payload = {"data": [{"id": "8101", "account_id": self.external, "name": "系列"}]}
        elif path.endswith("/adsets"):
            payload = {
                "data": [
                    {"id": "8102", "account_id": self.external, "campaign_id": "8101", "name": "组"}
                ]
            }
        elif path.endswith("/ads"):
            payload = {
                "data": [
                    {
                        "id": "8103",
                        "account_id": self.external,
                        "campaign_id": "8101",
                        "adset_id": "8102",
                        "name": "广告",
                    }
                ]
            }
        elif path.endswith("/insights"):
            if self.partial and parameters.get("after"):
                raise MetaReadFailure("META_READ_FORBIDDEN")
            window = (
                self.report_window if "/98001/" in path else json.loads(parameters["time_range"])
            )
            first, last = date.fromisoformat(window["since"]), date.fromisoformat(window["until"])
            payload = {
                "data": [
                    {
                        "account_id": self.external,
                        "campaign_id": "8101",
                        "adset_id": "8102",
                        "ad_id": "8103",
                        "date_start": (first + timedelta(days=i)).isoformat(),
                        "date_stop": (first + timedelta(days=i)).isoformat(),
                        "account_currency": "USD",
                        "spend": self.spend,
                        "impressions": "3",
                        "clicks": "0",
                    }
                    for i in range((last - first).days + 1)
                ]
            }
            if self.partial:
                payload["paging"] = {
                    "cursors": {"after": "partial"},
                    "next": "https://graph.facebook.com" + path + "?after=partial",
                }
        else:
            raise AssertionError("未知Graph读取路径")
        return GraphResponse(200, json.dumps(payload).encode())


async def _checks(url, values, cases, folder):
    from config.orbit_runtime import configure_isolated_fixture

    from orbit_api.account_access import context as account_context
    from orbit_api.account_actions_store import AccountActionsStore
    from orbit_api.account_contract import AccountImport
    from orbit_api.account_import_store import AccountImportStore
    from orbit_api.account_objects import AccountImportObjects
    from orbit_api.account_worker import AccountImportWorker
    from orbit_api.browser_session_store import BrowserSessionStore
    from orbit_api.configuration import ConfigurationWrite
    from orbit_api.configuration_store import ConfigurationStore
    from orbit_api.cookie_identity import bind_verified_cookie
    from orbit_api.credentials import CredentialCipher
    from orbit_api.directory_tokens import DirectoryTokens
    from orbit_api.errors import OrbitError
    from orbit_api.meta_connection_contract import MetaApplication, ValidatedGrant
    from orbit_api.meta_connection_service import MetaConnectionService
    from orbit_api.meta_metric_collection import MetaMetricCollectionStore, one
    from orbit_api.meta_metric_profile_source import (
        ADAPTER_VERSION,
        MetaMetricProfileService,
    )
    from orbit_api.meta_metric_worker import MetaMetricWorker
    from orbit_api.meta_metrics_provider import MetaMetricReadSource
    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import MetaReadFailure
    from orbit_api.meta_sync_runtime import MetaSyncRuntime, business_window
    from orbit_api.meta_sync_store import policy_access, save_policy
    from orbit_api.metric_profile_query import MetricProfileQuery
    from orbit_api.metric_profile_store import MetricProfileStore
    from orbit_api.metrics_contract import parse_history_metric_query
    from orbit_api.metrics_query_store import MetricsQueryStore
    from orbit_api.reference_contract import ReferenceImport
    from orbit_api.reference_store import ReferenceStore

    configure_isolated_fixture(values | {"ORBIT_META_GRAPH_VERSION": "v24.0"})
    engine = create_async_engine(url, echo=False, isolation_level="READ COMMITTED")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cipher = CredentialCipher(
        values["ORBIT_PYTHON_SECRETS_ACTIVE_KEY_ID"], values["ORBIT_PYTHON_SECRETS_KEYS"]
    )
    tenant = "00000000-0000-0000-0000-000000000001"
    provider, identity_id = str(uuid4()), str(uuid4())
    external = str(uuid4().int % (10**24))
    graph = PipelineGraph(external)

    def adapter(configuration):
        return MetaReadAdapter(configuration, transport=graph)

    issuer = "https://meta-pipeline.fixture.example/" + provider
    try:
        async with sessions() as s, s.begin():
            existing = await one(
                s,
                "SELECT i.provider_id,c.revision FROM orbit_external_identity i "
                "JOIN orbit_system_configuration c ON c.tenant_id=i.tenant_id "
                "AND c.id=i.provider_id "
                "WHERE i.tenant_id=:tenant AND i.user_id=1 AND c.enabled=1 AND c.section='OIDC' "
                "FOR SHARE",
                {"tenant": tenant},
            )
            revision = 1
            if existing:
                provider, revision = existing["provider_id"], existing["revision"]
            else:
                await s.execute(
                    text(
                        "INSERT INTO orbit_system_configuration "
                        "(id,tenant_id,section,name,enabled,revision,settings_json,"
                        "secrets_json,verification_status,updated_at) VALUES(:id,:tenant,"
                        "'OIDC',:id,1,1,:settings,'{}','UNTESTED',UTC_TIMESTAMP(3))"
                    ),
                    {"id": provider, "tenant": tenant, "settings": json.dumps({"issuer": issuer})},
                )
                await s.execute(
                    text(
                        "INSERT INTO orbit_external_identity "
                        "(id,tenant_id,user_id,issuer,issuer_digest,subject,subject_digest,"
                        "provider_id,verified_email,verified_at) VALUES(:id,:tenant,1,:issuer,"
                        ":digest,'pipeline',:subject,:provider,'pipeline@fixture.example',"
                        "UTC_TIMESTAMP(3))"
                    ),
                    {
                        "id": identity_id,
                        "tenant": tenant,
                        "issuer": issuer,
                        "digest": hashlib.sha256(issuer.encode()).digest(),
                        "subject": hashlib.sha256(b"pipeline").digest(),
                        "provider": provider,
                    },
                )
            _, identity = await BrowserSessionStore(cipher).issue(
                s, tenant, 1, provider, revision, secrets.token_urlsafe(32), str(uuid4())
            )
        bind_verified_cookie(identity)

        class OAuth:
            async def exchange(self, code):
                assert code == "isolated-code"
                return "pipeline-isolated-token", ValidatedGrant(
                    external,
                    ("ads_read",),
                    datetime.now(UTC) + timedelta(hours=2),
                    datetime.now(UTC) + timedelta(days=1),
                )

        service = MetaConnectionService(
            sessions, cipher, MetaApplication("123", "isolated-secret", "v24.0", "456"), OAuth()
        )
        start = await service.start(1, "/orbit/accounts", str(uuid4()), str(uuid4()))
        state = parse_qs(urlsplit(start["authorize_url"]).query)["state"][0]
        await service.callback(1, state, "isolated-code", str(uuid4()))
        async with sessions() as s, s.begin():
            connection = await one(
                s,
                "SELECT * FROM orbit_meta_connection WHERE tenant_id=:tenant AND "
                "principal_id=:principal",
                {"tenant": tenant, "principal": external},
            )
            owner, _ = await account_context(s, 1, "accounts.import")
            vendor_id = str(uuid4())
            vendor = dict(
                id=vendor_id,
                kind="VENDOR",
                name="管线隔离户商",
                availability="AVAILABLE",
                owner_team_id=owner.team_id,
                data_owner_user_ids=[owner.subject_id],
                source_key="pipeline:" + vendor_id,
            )
            references = ReferenceStore(DirectoryTokens(cipher))
            reference_caps = await references.capabilities(s, 1, "")
            preview = await references.preview(
                s,
                1,
                "",
                reference_caps["csrf_token"],
                str(uuid4()),
                ReferenceImport(
                    kind="VENDOR",
                    source="isolated-meta-pipeline",
                    reason="隔离管线验收",
                    base_catalog_revision=reference_caps["catalog_revision"],
                    items=[vendor],
                ),
                str(uuid4()),
            )
            assert preview["state"] == "VALIDATED", "户商生产预检失败"
            await references.commit(
                s,
                1,
                "",
                reference_caps["csrf_token"],
                str(uuid4()),
                preview["id"],
                preview["revision"],
                str(uuid4()),
            )
            imports = AccountImportStore(
                DirectoryTokens(cipher), AccountImportObjects(str(Path(folder).resolve()))
            )
            caps = await imports.capabilities(s, 1, "")
            batch = await imports.create(
                s,
                1,
                "",
                caps["csrf_token"],
                str(uuid4()),
                AccountImport(
                    vendor_id,
                    external,
                    vendor["data_owner_user_ids"][0],
                    vendor["owner_team_id"],
                ),
                str(uuid4()),
            )
            await s.execute(
                text(
                    "INSERT INTO orbit_meta_import_source "
                    "(tenant_id,batch_id,connection_id,connection_revision,channel_id,"
                    "revision) VALUES(:tenant,:batch,:connection,1,NULL,1)"
                ),
                {"tenant": tenant, "batch": batch["id"], "connection": connection["id"]},
            )
        await AccountImportWorker(
            sessions,
            cipher,
            {"USD"},
            target=(tenant, batch["id"]),
            meta_graph_version="v24.0",
            meta_adapter_factory=adapter,
        ).run_once()
        async with sessions() as s, s.begin():
            account = await one(
                s,
                "SELECT * FROM orbit_ad_account WHERE tenant_id=:tenant AND external_id=:external",
                {"tenant": tenant, "external": external},
            )
            if account is None:
                diagnostics = (
                    (
                        await s.execute(
                            text(
                                "SELECT state,attempts,JSON_UNQUOTE("
                                "JSON_EXTRACT(value_json,'$.error_code')) code "
                                "FROM orbit_account_import_row WHERE tenant_id=:tenant "
                                "AND batch_id=:batch "
                                "ORDER BY token_index"
                            ),
                            {"tenant": tenant, "batch": batch["id"]},
                        )
                    )
                    .mappings()
                    .all()
                )
                safe = [
                    {"state": r["state"], "attempts": r["attempts"], "code": r["code"]}
                    for r in diagnostics
                ]
                raise AssertionError("META_PIPELINE_IMPORT: " + json.dumps(safe))
            settings = dict(
                intervalMinutes=15,
                lookbackDays=7,
                profileVersion="pipeline-v1",
                registerActionType="complete_registration",
                purchaseActionType="purchase",
                valueActionType="purchase",
            )
            config = await ConfigurationStore(cipher).save(
                s,
                1,
                str(uuid4()),
                ConfigurationWrite(
                    section="METRICS",
                    name="管线指标" + external,
                    enabled=True,
                    settings=settings,
                    secrets={},
                    reason="隔离管线验收",
                ),
                request_id=str(uuid4()),
            )
        selection = dict(
            configuration_id=config["id"],
            configuration_revision=config["revision"],
            connection_id=connection["id"],
            connection_revision=1,
            account_id=external,
            attribution_windows=["7d_click", "1d_view"],
            action_report_time="conversion",
            maturity_days=28,
        )
        profile_service = MetaMetricProfileService(
            sessions, cipher, "v24.0", adapter_factory=adapter
        )
        selection["expected_revision"] = 0
        profile_key = str(uuid4())
        published = await profile_service.publish(1, selection, profile_key, str(uuid4()))
        assert await profile_service.publish(1, selection, profile_key, str(uuid4())) == published
        cases.append(PIPELINE_CASES[0])
        from meta_connection_policy_checks import check_connection_policies
        from meta_second_connection_fixture import prepare_second_connection

        second_connection, second_config, second_account = await prepare_second_connection(
            sessions, cipher, tenant, graph, adapter, imports, vendor_id, vendor
        )
        cases.extend(
            await check_connection_policies(
                sessions,
                1,
                (
                    (connection["id"], config["id"], ADAPTER_VERSION),
                    (second_connection["id"], second_config["id"], ADAPTER_VERSION),
                ),
            )
        )
        from orbit_api.meta_sync_runtime import enqueue_metrics

        async with sessions() as s, s.begin():
            current, _ = await account_context(s, 1, "accounts.sync")
            queued_second = await enqueue_metrics(s, current, second_account, str(uuid4()), days=7)
            assert queued_second["connection_id"] == second_connection["id"]
            assert queued_second["profile_id"] == second_config["id"]
        cases.append(PIPELINE_CASES[15])

        async with sessions() as s, s.begin():
            await save_policy(
                s,
                await policy_access(s, 1),
                dict(
                    profile_id=config["id"],
                    adapter_version=ADAPTER_VERSION,
                    scheduler_enabled=False,
                    revision=0,
                ),
                str(uuid4()),
                str(uuid4()),
            )
        assert await MetaSyncRuntime(sessions, cipher, "v24.0").schedule() == 0
        actions = AccountActionsStore(DirectoryTokens(cipher))
        async with sessions() as s, s.begin():
            sync_caps = await actions.capabilities(s, 1, "", account["id"], "SYNC")

        async def manual_sync(key, request, csrf=None, revision=None):
            async with sessions() as s, s.begin():
                return await actions.sync(
                    s,
                    1,
                    account["id"],
                    sync_caps["revision"] if revision is None else revision,
                    key,
                    "",
                    sync_caps["csrf_token"] if csrf is None else csrf,
                    "隔离手动同步",
                    request,
                )

        for csrf, revision, error_code in (
            ("invalid", None, "CSRF_INVALID"),
            (None, sync_caps["revision"] + 1, "REVISION_CONFLICT"),
        ):
            try:
                await manual_sync(str(uuid4()), str(uuid4()), csrf, revision)
            except OrbitError as error:
                assert error.code == error_code
            else:
                raise AssertionError("原同步会话或版本校验被绕过")
        async with sessions() as s, s.begin():
            await s.execute(
                text(
                    "CREATE TRIGGER meta_pipeline_command_reject BEFORE INSERT ON "
                    "orbit_account_command FOR EACH ROW SIGNAL SQLSTATE '45000' "
                    "SET MESSAGE_TEXT='ISOLATED_META_PIPELINE_ROLLBACK'"
                )
            )
        try:
            try:
                await manual_sync(str(uuid4()), str(uuid4()))
            except Exception as error:
                from sqlalchemy.exc import DBAPIError

                assert isinstance(error, DBAPIError), "应由隔离命令审计故障触发回滚"
            else:
                raise AssertionError("命令失败未回滚采集任务")
        finally:
            async with sessions() as s, s.begin():
                await s.execute(text("DROP TRIGGER meta_pipeline_command_reject"))
        async with sessions() as s:
            assert (
                await s.execute(
                    text(
                        "SELECT COUNT(*) FROM orbit_meta_metric_job WHERE "
                        "tenant_id=:tenant AND account_id=:account"
                    ),
                    {"tenant": tenant, "account": account["id"]},
                )
            ).scalar_one() == 0
        manual_key, manual_request = str(uuid4()), str(uuid4())
        manual_ack = await manual_sync(manual_key, manual_request)
        assert await manual_sync(manual_key, str(uuid4())) == manual_ack
        async with sessions() as s:
            params = {"tenant": tenant, "account": account["id"]}
            assert (
                await s.execute(
                    text(
                        "SELECT COUNT(*) FROM orbit_meta_metric_job WHERE "
                        "tenant_id=:tenant AND account_id=:account"
                    ),
                    params,
                )
            ).scalar_one() == 1
            assert (
                await s.execute(
                    text(
                        "SELECT COUNT(*) FROM orbit_account_command WHERE "
                        "tenant_id=:tenant AND account_id=:account AND kind='SYNC'"
                    ),
                    params,
                )
            ).scalar_one() == 1
        async with sessions() as s:
            selected_job = await one(
                s,
                "SELECT profile_id,connection_id FROM orbit_meta_metric_job "
                "WHERE tenant_id=:tenant AND account_id=:account",
                {"tenant": tenant, "account": account["id"]},
            )
            assert selected_job["profile_id"] == config["id"]
            assert selected_job["connection_id"] == connection["id"]
        cases.append(PIPELINE_CASES[7])
        store = MetaMetricCollectionStore()

        async def new_job(days):
            first, last = business_window("UTC", datetime.now(UTC), days)
            async with sessions() as s, s.begin():
                return await store.begin(
                    s,
                    1,
                    account["id"],
                    config["id"],
                    ADAPTER_VERSION,
                    first,
                    last,
                    "v24.0",
                    str(uuid4()),
                )

        async def factory(job):
            from orbit_api.meta_account_sources import load_connection

            async with sessions() as s, s.begin():
                source = await load_connection(
                    s, cipher, tenant, job["connection_id"], job["connection_revision"], "v24.0"
                )
            return adapter(source.configuration)

        worker = MetaMetricWorker(sessions, factory)
        seven = await new_job(7)
        assert (seven["date_to"] - seven["date_from"]).days == 6
        result = await worker.run(1, seven["id"])
        assert result["cell_count"] == result["fact_count"] == 7

        async def latest(job, history_version=None):
            query = dict(
                date_from=job["date_from"].isoformat(),
                date_to=job["date_to"].isoformat(),
                dataset="AD",
                metric_profile_id=config["id"],
                scope_snapshot_id=None,
                channel_id=None,
                operator_user_id=None,
                q="",
                sort="spend",
                direction="DESC",
                cursor=None,
                page_size=20,
                granularity="SUMMARY",
            )
            if history_version is not None:
                query = parse_history_metric_query(
                    json.dumps({"query": query, "metric_profile_version": history_version}).encode()
                )
            source = MetricsQueryStore(MetaMetricReadSource())
            async with sessions() as s, s.begin():
                context = await source.select_source_anchor(s, 1, query)
                found = []
                async for batch in source.iter_latest_cells(s, context):
                    found.extend(batch.rows)
                return found

        assert len(await latest(seven)) == 7
        cases.append(PIPELINE_CASES[1])
        ninety = await new_job(90)
        assert (ninety["date_to"] - ninety["date_from"]).days == 89
        graph.pending = True
        first = await worker.run(1, ninety["id"])
        assert first["state"] == "WAIT_REPORT" and graph.report_starts == 1
        async with sessions() as s, s.begin():
            await s.execute(
                text(
                    "UPDATE orbit_meta_metric_job SET next_run_at=UTC_TIMESTAMP(6) WHERE "
                    "tenant_id=:tenant AND id=:id"
                ),
                {"tenant": tenant, "id": ninety["id"]},
            )
        graph.pending = False
        result = await MetaMetricWorker(sessions, factory).run(1, ninety["id"])
        assert result["cell_count"] == 90 and graph.report_starts == 1
        assert len(await latest(ninety)) == 90
        cases.append(PIPELINE_CASES[2])
        partial = await new_job(7)
        graph.partial = True
        try:
            await worker.run(1, partial["id"])
        except MetaReadFailure as error:
            assert error.code == "META_READ_FORBIDDEN"
        else:
            raise AssertionError("不完整分页被发布")
        graph.partial = False
        async with sessions() as s:
            assert (
                await s.execute(
                    text(
                        "SELECT COUNT(*) FROM orbit_metric_publication WHERE "
                        "tenant_id=:tenant AND id=:id"
                    ),
                    {"tenant": tenant, "id": partial["publication_id"]},
                )
            ).scalar_one() == 0
            assert (
                await s.execute(
                    text(
                        "SELECT COUNT(*) FROM orbit_meta_metric_capture_page WHERE "
                        "tenant_id=:tenant AND job_id=:id AND stream_key='insights'"
                    ),
                    {"tenant": tenant, "id": partial["id"]},
                )
            ).scalar_one() == 1
        cases.append(PIPELINE_CASES[3])
        older, newer = await new_job(7), await new_job(7)
        graph.spend = "2"
        await worker.run(1, newer["id"])
        graph.spend = "1"
        await worker.run(1, older["id"])
        current = await latest(older)
        assert {r["capture_sequence"] for r in current} == {newer["capture_sequence"]}
        cases.append(PIPELINE_CASES[4])
        blocked = await new_job(7)
        late_auth = await new_job(7)
        late_worker = str(uuid4())
        async with sessions() as s, s.begin():
            late_claim = await store.claim(s, 1, late_auth["id"], late_worker)

        await service.disconnect(1, connection["id"], 1, "隔离撤权验收", str(uuid4()), str(uuid4()))
        try:
            await worker.run(1, blocked["id"])
        except OrbitError:
            pass
        else:
            raise AssertionError("撤权后仍可采集")
        assert len(await latest(older)) == 7
        async with sessions() as s:
            historical = await MetricProfileQuery(DirectoryTokens(cipher), historical=True).page(
                s, 1, "", {"metric_profile_id": config["id"]}
            )
        assert [item["id"] for item in historical["items"]] == [config["id"]]
        cases.append(PIPELINE_CASES[5])
        reauth = await service.start(
            1, "/orbit/accounts", str(uuid4()), str(uuid4()), connection["id"]
        )
        reauth_state = parse_qs(urlsplit(reauth["authorize_url"]).query)["state"][0]
        await service.callback(1, reauth_state, "isolated-code", str(uuid4()))
        resumed = await new_job(7)
        assert resumed["profile_id"] == config["id"] and resumed["profile_version"] == "pipeline-v1"
        assert resumed["connection_revision"] > blocked["connection_revision"]
        try:
            await worker.run(1, blocked["id"])
        except OrbitError as error:
            assert error.code == "META_SOURCE_CHANGED"
        else:
            raise AssertionError("旧检查点不能借重新授权复活")
        result = await worker.run(1, resumed["id"])
        assert result["cell_count"] == 7
        assert len(await latest(older)) == 7
        cases.append(PIPELINE_CASES[6])
        async with sessions() as s, s.begin():
            assert not await store.invalidate_source(
                s, 1, late_auth["id"], late_worker, late_claim["fencing_token"]
            )
            active = await one(
                s,
                "SELECT status,revision FROM orbit_meta_connection WHERE "
                "tenant_id=:tenant AND id=:id",
                {"tenant": tenant, "id": connection["id"]},
            )
            assert (
                active["status"] == "ACTIVE"
                and active["revision"] == resumed["connection_revision"]
            )
        failure, queued = await new_job(7), await new_job(7)
        graph.auth_failed = True
        try:
            await worker.run(1, failure["id"])
        except MetaReadFailure as error:
            assert error.code == "META_AUTH_FAILED"
        else:
            raise AssertionError("认证失败未停止采集")
        graph.auth_failed = False
        async with sessions() as s, s.begin():
            invalid = await one(
                s,
                "SELECT status,revision,(token_envelope IS NULL) token_cleared "
                "FROM orbit_meta_connection WHERE tenant_id=:tenant AND id=:id",
                {"tenant": tenant, "id": connection["id"]},
            )
            assert invalid["status"] == "REAUTH_REQUIRED" and invalid["token_cleared"]
            assert invalid["revision"] == resumed["connection_revision"] + 1
        try:
            await worker.run(1, queued["id"])
        except OrbitError:
            pass
        else:
            raise AssertionError("同来源已排队任务在Token失效后仍可领取")
        cases.append(PIPELINE_CASES[8])
        from meta_metadata_auth_checks import check_metadata_auth

        await check_metadata_auth(
            sessions,
            cipher,
            tenant,
            service,
            connection,
            graph,
            adapter,
            account,
            imports,
            vendor_id,
            vendor,
        )
        cases.append(PIPELINE_CASES[10])

        from orbit_api.meta_metric_profile_source import publisher

        async with sessions() as s, s.begin():
            await MetricProfileStore().revoke(
                s, await publisher(s, 1), config["id"], 1, str(uuid4())
            )
        assert len(await latest(older, "pipeline-v1")) == 7
        for version in (None, "does-not-exist"):
            try:
                await latest(older, version)
            except OrbitError as error:
                assert error.status == 503
            else:
                raise AssertionError("未明确或不存在的历史版本不可回退当前版本")
        cases.append(PIPELINE_CASES[9])

    finally:
        await engine.dispose()
