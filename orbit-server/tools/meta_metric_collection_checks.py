"""真实MySQL采集发布验收；Graph合成transport不冒充真实Meta外测。"""

import json
import re
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from orbit_api.meta_metric_collection import MetaMetricCollectionStore, one
from orbit_api.meta_metric_worker import MetaMetricWorker
from orbit_api.meta_metrics_provider import MetaExpectedUnitProvider, MetaMetricReadSource
from orbit_api.meta_read_adapter import GraphResponse, MetaReadAdapter, validate_graph_parameters
from orbit_api.meta_read_contract import MetaReadConfiguration
from orbit_api.metrics_query_result_contract import QuerySourceIdentity
from orbit_api.metrics_scope_access import authorize_metric_scope

META_METRIC_COLLECTION_CASES = (
    "pythonMetaMetricOriginalFactsPublishedFromIndependentInventory",
    "pythonMetaMetricMissingActionsRemainUnknownAndExactDecimals",
    "pythonMetaMetricSealedHistorySurvivesDisconnect",
)


async def run_meta_metric_collection_checks(
    sessions, database, *, actor, account_id, profile_id, adapter_version, cases
):
    """调用方先通过真实注册接口准备当前连接/账户/verified profile；仅隔离UUID库。"""
    if not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database):
        raise ValueError("仅允许本轮隔离验收库")
    async with sessions() as session:
        actual = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
        if actual != database:
            raise ValueError("实际数据库不一致")
    store = MetaMetricCollectionStore()
    day = date(2026, 10, 1)
    async with sessions() as session, session.begin():
        job = await store.begin(
            session, actor, account_id, profile_id, adapter_version, day, day, "v24.0", str(uuid4())
        )
        account = await one(
            session,
            "SELECT * FROM orbit_ad_account WHERE id=:id AND tenant_id=:tenant",
            {"id": account_id, "tenant": job["tenant_id"]},
        )

    class Transport:
        async def request(self, method, path, parameters, token, *, maximum_bytes):
            validate_graph_parameters(method, path, parameters)
            assert method == "GET", "短窗口不得触发广告或报表写请求"
            external = account["external_id"]
            if path.endswith("/act_" + external):
                payload = {
                    "id": "act_" + external,
                    "account_id": external,
                    "name": "验收账户",
                    "currency": account["currency"],
                    "timezone_name": account["timezone_id"],
                }
            elif path.endswith("/campaigns"):
                payload = {"data": [{"id": "7101", "account_id": external, "name": "系列"}]}
            elif path.endswith("/adsets"):
                payload = {
                    "data": [
                        {"id": "7102", "account_id": external, "campaign_id": "7101", "name": "组"}
                    ]
                }
            elif path.endswith("/ads"):
                payload = {
                    "data": [
                        {
                            "id": "7103",
                            "account_id": external,
                            "campaign_id": "7101",
                            "adset_id": "7102",
                            "name": "广告",
                        }
                    ]
                }
            elif path.endswith("/insights"):
                payload = {
                    "data": [
                        {
                            "account_id": external,
                            "campaign_id": "7101",
                            "adset_id": "7102",
                            "ad_id": "7103",
                            "date_start": day.isoformat(),
                            "date_stop": day.isoformat(),
                            "account_currency": account["currency"],
                            "spend": "0.123456",
                            "impressions": "3",
                            "clicks": "0",
                        }
                    ]
                }
            else:
                raise AssertionError("未知读取路径")
            return GraphResponse(200, json.dumps(payload).encode())

    async def factory(current):
        return MetaReadAdapter(
            MetaReadConfiguration(
                current["connection_id"],
                current["connection_revision"],
                current["api_version"],
                "isolated-metric-read-token",
            ),
            transport=Transport(),
        )

    result = await MetaMetricWorker(sessions, factory).run(actor, job["id"])
    assert result["cell_count"] == result["fact_count"] == 1
    async with sessions() as session, session.begin():
        head = await one(
            session,
            "SELECT * FROM orbit_metric_publication WHERE tenant_id=:tenant AND id=:id",
            {"tenant": job["tenant_id"], "id": result["publication_id"]},
        )
        scope = await authorize_metric_scope(session, actor, None)
        query = {
            "date_from": day.isoformat(),
            "date_to": day.isoformat(),
            "dataset": "AD",
            "metric_profile_id": profile_id,
            "scope_snapshot_id": None,
            "channel_id": None,
            "operator_user_id": None,
            "q": "",
            "sort": "spend",
            "direction": "DESC",
            "cursor": None,
            "page_size": 20,
            "granularity": "SUMMARY",
        }
        source = MetaMetricReadSource()
        assert len(await source.verify_publications(session, scope, query, [head])) == 1
        identity = QuerySourceIdentity(
            job["tenant_id"],
            head["id"],
            head["generation"],
            profile_id,
            head["profile_version"],
            head["profile_hash"],
            "TRUSTED",
        )
        manifest = await MetaExpectedUnitProvider(source).prepare_manifest(
            session, scope, query, identity
        )
        assert manifest.unit_count == manifest.membership_count == 1
        fact = await one(
            session,
            "SELECT f.* FROM orbit_metric_ad_fact_version f JOIN orbit_metric_capture_cell c "
            "ON c.tenant_id=f.tenant_id AND c.id=f.cell_id "
            "WHERE c.tenant_id=:tenant AND c.publication_id=:id",
            {"tenant": job["tenant_id"], "id": head["id"]},
        )
        assert fact["spend"] == Decimal("0.123456") and fact["clicks"] == 0
        assert fact["purchases"] is None and fact["purchase_value"] is None
    cases.extend(META_METRIC_COLLECTION_CASES[:2])
    # 断开仅在回滚事务内验证；不会给后续验收留下连接变化。
    async with sessions() as session:
        async with session.begin():
            await session.execute(
                text(
                    "UPDATE orbit_meta_connection SET status='DISCONNECTED' "
                    "WHERE tenant_id=:tenant AND id=:id"
                ),
                {"tenant": job["tenant_id"], "id": job["connection_id"]},
            )
            scope = await authorize_metric_scope(session, actor, None)
            assert len(await source.verify_publications(session, scope, query, [head])) == 1
            await session.rollback()
    cases.append(META_METRIC_COLLECTION_CASES[2])
    return result
