"""持久Meta只读Worker；网络在事务外，原048为唯一数值事实，调度默认关闭。"""

import hashlib
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4, uuid5

from orbit_api.account_details_contract import fact_interval, freeze_attribution
from orbit_api.agent_monitor_store import utc
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_metric_collection import (
    MetaMetricCollectionStore,
    digest,
    one,
    reject,
)
from orbit_api.meta_metrics_provider import decoded, rows
from orbit_api.meta_read_contract import (
    AsyncReport,
    InsightWindow,
    MetaAttribution,
    MetaReadFailure,
    ReadCheckpoint,
)
from orbit_api.metric_profile_query import mysql_millisecond_instant
from orbit_api.metrics_query_result_contract import ExpectedEntityMembership, ExpectedUnitReceipt


def action_value(items, action):
    """精确归因动作值；没有明确value就是未知，不将窗口分列相加。"""
    if action is None or items is None:
        return None
    found = [row.get("value") for row in items if row.get("action_type") == action]
    if len(found) > 1:
        reject("META_RESPONSE_INVALID", "重复归因动作", 422)
    return found[0] if found else None


def metric_values(item, profile):
    if item is None:
        return dict.fromkeys(
            ("spend", "impressions", "clicks", "registrations", "purchases", "purchase_value")
        )
    values = {key: item.get(key) for key in ("spend", "impressions", "clicks")} | {
        "registrations": action_value(item.get("actions"), profile["register_action_type"]),
        "purchases": action_value(item.get("actions"), profile["purchase_action_type"]),
        "purchase_value": action_value(item.get("action_values"), profile["value_action_type"]),
    }

    return {key: exact_numeric(value) for key, value in values.items()}


def exact_numeric(value):
    if value is None:
        return None
    if type(value) is not str:
        reject("META_RESPONSE_INVALID", "指标必须为精确定点字符串", 422)
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        reject("META_RESPONSE_INVALID", "指标数值无效", 422)
    if not parsed.is_finite():
        reject("META_RESPONSE_INVALID", "指标数值无效", 422)
    result = format(parsed, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    if len(result) > 28 or not re.fullmatch(r"(0|[1-9][0-9]*)(\.[0-9]{1,6})?", result):
        reject("META_RESPONSE_INVALID", "指标超出原事实精度，禁止隐式舍入", 422)
    return result


def normalized_hash(value):
    return digest(
        {
            key: item.isoformat() if isinstance(item, (date, datetime)) else item
            for key, item in value.items()
        }
    )


def dimension(account, tenant, kind, row, parents, observed):
    external = row["account_id"] if kind == "ACCOUNT" else row["id"]
    entity = account if kind == "ACCOUNT" else str(uuid5(UUID(account), kind + ":" + external))
    parent_kind = {"ACCOUNT": None, "CAMPAIGN": "ACCOUNT", "ADSET": "CAMPAIGN", "AD": "ADSET"}[kind]
    parent_external = (
        None
        if kind == "ACCOUNT"
        else row["account_id"]
        if kind == "CAMPAIGN"
        else row["campaign_id"]
        if kind == "ADSET"
        else row["adset_id"]
    )
    parent = None if kind == "ACCOUNT" else parents.get((parent_kind, parent_external))
    if parent_kind is not None and parent is None:
        reject("META_PARENT_UNVERIFIED", "独立库存缺少原父对象")
    if type(row.get("name")) is not str:
        reject("META_RESPONSE_INVALID", "独立名称来源缺失", 422)
    value = dict(
        tenant_id=tenant,
        account_id=account,
        entity_kind=kind,
        entity_id=entity,
        external_id=external,
        name=row["name"],
        parent_snapshot_id=parent,
        parent_kind=parent_kind,
    )
    hashed = digest(value)
    return value | {
        "id": str(uuid5(UUID(account), kind + ":snapshot:" + hashed)),
        "content_hash": hashed,
        "_observed_at": observed,
    }


class MetaMetricWorker:
    """adapter_factory(job)必须从当前受控连接解密构造MetaReadAdapter，绝不接浏览器Token。"""

    def __init__(self, sessions, adapter_factory, *, store=None, worker_id=None):
        self.sessions = sessions
        self.adapter_factory = adapter_factory
        self.store = store or MetaMetricCollectionStore()
        self.worker_id = worker_id or str(uuid4())

    async def _tx(self, actor, job_id, fence, method, *args, **kwargs):
        async with self.sessions() as session, session.begin():
            await self.store.renew(session, actor, job_id, self.worker_id, fence)
            return await getattr(self.store, method)(
                session, actor, job_id, self.worker_id, fence, *args, **kwargs
            )

    async def run(self, actor, job_id):
        async with self.sessions() as session, session.begin():
            job = await self.store.claim(session, actor, job_id, self.worker_id)
        fence = job["fencing_token"]
        try:
            adapter = await self.adapter_factory(job)
            if adapter.configuration.fingerprint != job["source_fingerprint"]:
                reject("META_SOURCE_CHANGED", "实际读取适配器来源不一致")
            async with self.sessions() as session, session.begin():
                job, source, resolved, _ = await self.store._job(
                    session, actor, job_id, self.worker_id, fence
                )
            attribution = MetaAttribution.from_resolved(resolved)
            if job["state"] == "INVENTORY":
                for kind in ("ACCOUNT", "CAMPAIGN", "ADSET", "AD"):
                    await self._inventory_stream(
                        actor, job, fence, adapter, source["external_id"], kind
                    )
                await self._expectations(actor, job, fence)
                await self._tx(actor, job_id, fence, "freeze_inventory")
            account = await self._account(job)
            if not account.get("currency") or not account.get("timezone_name"):
                reject("META_ACCOUNT_METADATA_MISSING", "账户币种或时区缺失")
            window = InsightWindow(job["date_from"], job["date_to"], account["timezone_name"])
            complete = await self._insights(
                actor, job, fence, adapter, source["external_id"], window, attribution
            )
            if not complete:
                return {"job_id": job_id, "state": "WAIT_REPORT"}
            await self._materialize(actor, job, fence, resolved["profile"], account)
            return await self._tx(actor, job_id, fence, "publish")
        except (MetaReadFailure, OrbitError) as error:
            code = error.code
            retryable = isinstance(error, MetaReadFailure) and error.retryable
            try:
                if isinstance(error, MetaReadFailure) and code == "META_AUTH_FAILED":
                    async with self.sessions() as session, session.begin():
                        await self.store.invalidate_source(
                            session, actor, job_id, self.worker_id, fence
                        )
                else:
                    await self._tx(actor, job_id, fence, "fail", retryable=retryable, code=code)
            except OrbitError:
                pass  # 撤权/失效不借错误处理重新获得来源权限。
            raise

    async def _checkpoint(self, job, key):
        async with self.sessions() as session:
            row = await one(
                session,
                "SELECT checkpoint_json FROM orbit_meta_metric_job WHERE tenant_id=:tenant "
                "AND id=:id",
                {"tenant": job["tenant_id"], "id": job["id"]},
            )
        value = decoded(row["checkpoint_json"]).get(key)
        if value and value.get("complete") is True:
            return True
        if value:
            value = dict(value)
            for field in ("seen_cursors", "seen_keys"):
                value[field] = tuple(value.get(field, ()))
            return ReadCheckpoint(**value)
        return None

    async def _inventory_stream(self, actor, job, fence, adapter, external, kind):
        stream = "inventory_" + kind
        checkpoint = await self._checkpoint(job, stream)
        if checkpoint is True:
            return
        while True:
            await self._renew(actor, job, fence)
            page = (
                await adapter.account_page(external)
                if kind == "ACCOUNT"
                else await adapter.structure_page(external, kind, checkpoint=checkpoint)
            )
            async with self.sessions() as session, session.begin():
                await self.store.renew(session, actor, job["id"], self.worker_id, fence)
                await self.store.append_capture(
                    session, actor, job["id"], self.worker_id, fence, stream, page
                )
                parents = {}
                if kind != "ACCOUNT":
                    parent_kind = {"CAMPAIGN": "ACCOUNT", "ADSET": "CAMPAIGN", "AD": "ADSET"}[kind]
                    ids = sorted(
                        {
                            r["account_id"]
                            if kind == "CAMPAIGN"
                            else r["campaign_id"]
                            if kind == "ADSET"
                            else r["adset_id"]
                            for r in page.items
                        }
                    )
                    if ids:
                        found = await rows(
                            session,
                            """SELECT d.external_id,d.id FROM orbit_meta_metric_job_dimension j
                            JOIN orbit_metric_entity_snapshot d ON d.tenant_id=j.tenant_id AND
                            d.id=j.entity_snapshot_id
                            WHERE j.tenant_id=:tenant AND j.job_id=:job AND j.entity_kind=:kind
                            AND d.external_id IN :ids FOR SHARE""",
                            {
                                "tenant": job["tenant_id"],
                                "job": job["id"],
                                "kind": parent_kind,
                                "ids": ids,
                            },
                        )
                        parents = {(parent_kind, r["external_id"]): r["id"] for r in found}
                dims = [
                    dimension(
                        job["account_id"], job["tenant_id"], kind, row, parents, page.observed_at
                    )
                    for row in page.items
                ]
                await self.store.append_inventory(
                    session, actor, job["id"], self.worker_id, fence, dimensions=dims
                )
            if page.complete:
                break
            checkpoint = page.checkpoint

    async def _renew(self, actor, job, fence):
        async with self.sessions() as session, session.begin():
            await self.store.renew(session, actor, job["id"], self.worker_id, fence)

    async def _account(self, job):
        async with self.sessions() as session:
            row = await one(
                session,
                "SELECT items_json FROM orbit_meta_metric_capture_page WHERE "
                "tenant_id=:tenant AND job_id=:id AND stream_key='inventory_ACCOUNT' AND "
                "page_number=1",
                {"tenant": job["tenant_id"], "id": job["id"]},
            )
        values = decoded(row["items_json"]) if row else []
        if len(values) != 1:
            reject("META_INVENTORY_INCOMPLETE", "账户库存必须唯一")
        return values[0]

    async def _dimensions(self, job, kind):
        after = ""
        while True:
            async with self.sessions() as session:
                batch = await rows(
                    session,
                    """SELECT j.*,d.external_id,d.parent_snapshot_id
                    FROM orbit_meta_metric_job_dimension j JOIN orbit_metric_entity_snapshot d
                    ON d.tenant_id=j.tenant_id AND d.id=j.entity_snapshot_id
                    WHERE j.tenant_id=:tenant AND j.job_id=:id AND j.entity_kind=:kind
                    AND j.entity_id>:after ORDER BY j.entity_id LIMIT 200""",
                    {"tenant": job["tenant_id"], "id": job["id"], "kind": kind, "after": after},
                )
            if not batch:
                break
            yield batch
            after = batch[-1]["entity_id"]

    def _member(self, job, kind, day, row):
        return ExpectedEntityMembership(
            job["tenant_id"],
            job["account_id"],
            day,
            job["profile_id"],
            job["profile_version"],
            kind,
            row["entity_id"],
            row["entity_snapshot_id"],
            job["capture_sequence"],
            utc(row["observed_at"]),
        )

    async def _attribution(self, job, day, timezone, observed):
        start, end = fact_interval(day, timezone, observed.replace(tzinfo=None))
        async with self.sessions() as session, session.begin():
            previous = await one(
                session,
                """SELECT c.owner_user_id,c.owner_team_id,c.attribution_version
                FROM orbit_metric_capture_cell c JOIN orbit_metric_publication p
                ON p.tenant_id=c.tenant_id AND p.id=c.publication_id
                WHERE c.tenant_id=:tenant AND c.account_id=:account AND c.business_date=:day
                AND p.state='PUBLISHED' AND p.authority_kind='TRUSTED'
                ORDER BY c.capture_sequence DESC LIMIT 1 FOR SHARE""",
                {"tenant": job["tenant_id"], "account": job["account_id"], "day": day},
            )
            if previous:
                previous = dict(previous) | {"attribution_reason": "PRIOR_FROZEN"}
            assignments = await rows(
                session,
                """SELECT owner_user_id,owner_team_id,starts_at,ends_at
                FROM orbit_account_assignment WHERE tenant_id=:tenant AND account_id=:account
                AND starts_at<:end AND (ends_at IS NULL OR ends_at>:start)
                ORDER BY starts_at LIMIT 2001 FOR SHARE""",
                {
                    "tenant": job["tenant_id"],
                    "account": job["account_id"],
                    "start": start,
                    "end": end,
                },
            )
            if len(assignments) > 2000:
                reject("META_ATTRIBUTION_UNVERIFIED", "历史归属区间异常")
        return freeze_attribution(start, end, assignments, previous)

    async def _expectations(self, actor, job, fence):
        account = await self._account(job)
        if not account.get("currency") or not account.get("timezone_name"):
            reject("META_ACCOUNT_METADATA_MISSING", "账户币种或时区缺失")
        async with self.sessions() as session:
            snapshot = await one(
                session,
                "SELECT entity_snapshot_id,observed_at FROM "
                "orbit_meta_metric_job_dimension WHERE tenant_id=:tenant AND job_id=:id "
                "AND entity_kind='ACCOUNT'",
                {"tenant": job["tenant_id"], "id": job["id"]},
            )
        day = job["date_from"]
        while day <= job["date_to"]:
            attribution = await self._attribution(
                job, day, account["timezone_name"], utc(snapshot["observed_at"])
            )
            for kind in ("ACCOUNT", "CAMPAIGN", "ADSET", "AD"):
                root = hashlib.sha256()
                count = 0
                async for batch in self._dimensions(job, kind):
                    for row in batch:
                        root.update(
                            canonical(self._member(job, kind, day, row).record()).encode() + b"\n"
                        )
                        count += 1
                unit = ExpectedUnitReceipt(
                    job["tenant_id"],
                    job["account_id"],
                    day,
                    job["profile_id"],
                    job["profile_version"],
                    attribution["owner_user_id"],
                    attribution["owner_team_id"],
                    account["currency"],
                    account["timezone_name"],
                    snapshot["entity_snapshot_id"],
                    attribution["attribution_version"],
                    count,
                    root.hexdigest(),
                )
                await self._tx(actor, job["id"], fence, "append_inventory", units=[(kind, unit)])
                async for batch in self._dimensions(job, kind):
                    await self._tx(
                        actor,
                        job["id"],
                        fence,
                        "append_inventory",
                        members=[self._member(job, kind, day, row) for row in batch],
                    )
            day += timedelta(days=1)

    async def _insights(self, actor, job, fence, adapter, external, window, attribution):
        checkpoint = await self._checkpoint(job, "insights")
        if checkpoint is True:
            return True
        report = None
        if (window.until - window.since).days > 7:
            prior = await self._tx(actor, job["id"], fence, "report_start")
            if prior:
                value = dict(prior["report"])
                saved_window = dict(value["window"])
                for key in ("since", "until"):
                    saved_window[key] = date.fromisoformat(saved_window[key])
                value["window"] = InsightWindow(**saved_window)
                saved_attribution = dict(value["attribution"])
                saved_attribution["windows"] = tuple(saved_attribution["windows"])
                value["attribution"] = MetaAttribution(**saved_attribution)
                report = AsyncReport(**value)
            else:
                report = await adapter.start_report(external, window, attribution=attribution)
                await self._tx(actor, job["id"], fence, "report_bind", report)
            status = await adapter.report_status(report)
            if not status.complete:
                await self._tx(actor, job["id"], fence, "report_wait")
                return False
        while True:
            await self._renew(actor, job, fence)
            page = (
                await adapter.report_page(report, checkpoint=checkpoint)
                if report
                else await adapter.insights_page(
                    external, window, attribution=attribution, level="ad", checkpoint=checkpoint
                )
            )
            await self._tx(actor, job["id"], fence, "append_capture", "insights", page)
            if page.complete:
                return True
            checkpoint = page.checkpoint

    async def _fact_batch(self, job, day, unit, adrows, profile):
        ids = [row["external_id"] for row in adrows]
        async with self.sessions() as session:
            source = await rows(
                session,
                """SELECT i.external_ad_id,
                JSON_EXTRACT(p.items_json,CONCAT('$[',i.item_index,']')) item_json,p.observed_at
                FROM orbit_meta_metric_insight_index i JOIN orbit_meta_metric_capture_page p
                ON p.tenant_id=i.tenant_id AND p.job_id=i.job_id AND p.stream_key=i.stream_key
                AND p.page_number=i.page_number WHERE i.tenant_id=:tenant AND i.job_id=:job
                AND i.business_date=:day AND i.external_ad_id IN :ids""",
                {"tenant": job["tenant_id"], "job": job["id"], "day": day, "ids": ids},
            )
            tree = await rows(
                session,
                """SELECT ad.id ad_snapshot,ad.external_id ad_external,ad.entity_id ad_id,
                aset.id adset_snapshot,aset.entity_id adset_id,aset.external_id adset_external,
                camp.id campaign_snapshot,camp.entity_id campaign_id,camp.external_id
                campaign_external
                FROM orbit_meta_metric_job_dimension j JOIN orbit_metric_entity_snapshot ad
                ON ad.tenant_id=j.tenant_id AND ad.id=j.entity_snapshot_id
                JOIN orbit_metric_entity_snapshot aset ON aset.tenant_id=ad.tenant_id AND
                aset.id=ad.parent_snapshot_id
                JOIN orbit_metric_entity_snapshot camp ON camp.tenant_id=aset.tenant_id AND
                camp.id=aset.parent_snapshot_id
                WHERE j.tenant_id=:tenant AND j.job_id=:job AND j.entity_kind='AD' AND
                ad.external_id IN :ids""",
                {"tenant": job["tenant_id"], "job": job["id"], "ids": ids},
            )
        by_source = {r["external_ad_id"]: r for r in source}
        by_tree = {r["ad_external"]: r for r in tree}
        facts = []
        complete = True
        for row in adrows:
            parent = by_tree.get(row["external_id"])
            saved = by_source.get(row["external_id"])
            if parent is None:
                reject("META_PARENT_UNVERIFIED", "广告父链缺失")
            item = decoded(saved["item_json"]) if saved else None
            if item and (
                item["campaign_id"] != parent["campaign_external"]
                or item["adset_id"] != parent["adset_external"]
                or item["timezone_name"] != unit["timezone_name"]
                or item["currency"] not in (None, unit["currency"])
            ):
                reject("META_PARENT_UNVERIFIED", "指标身份、层级、币种或时区与库存不符")
            metrics = metric_values(item, profile)
            complete = complete and all(
                metrics[k] is not None
                for k in ("spend", "impressions", "clicks", "purchases", "purchase_value")
            )
            observed = utc(saved["observed_at"]) if saved else utc(unit["oldest_observed_at"])
            # 原048未知渠道/素材/计划映射保持NULL，不借当前目录推断历史。
            fact = dict(
                tenant_id=job["tenant_id"],
                id=str(
                    uuid5(UUID(job["publication_id"]), day.isoformat() + ":AD:" + row["entity_id"])
                ),
                cell_id=unit["id"],
                account_id=job["account_id"],
                business_date=day,
                profile_id=job["profile_id"],
                profile_version=job["profile_version"],
                capture_sequence=job["capture_sequence"],
                ad_id=parent["ad_id"],
                adset_id=parent["adset_id"],
                campaign_id=parent["campaign_id"],
                account_snapshot_id=unit["account_snapshot_id"],
                campaign_snapshot_id=parent["campaign_snapshot"],
                adset_snapshot_id=parent["adset_snapshot"],
                ad_snapshot_id=parent["ad_snapshot"],
                channel_id=None,
                product_name_snapshot=None,
                parent_mapping_hash=digest(dict(parent)),
                asset_mapping_state="UNKNOWN",
                asset_mapping_hash=None,
                launch_mapping_hash=None,
                is_deleted=False,
                observed_at=mysql_millisecond_instant(observed),
                **metrics,
            )
            fact["fact_hash"] = normalized_hash(fact)
            facts.append(fact)
        return facts, complete

    async def _materialize(self, actor, job, fence, profile, account):
        async with self.sessions() as session:
            units = await rows(
                session,
                "SELECT * FROM orbit_meta_metric_expected_unit WHERE tenant_id=:tenant AND "
                "job_id=:job AND dataset='AD' ORDER BY business_date",
                {"tenant": job["tenant_id"], "job": job["id"]},
            )
            pages = await rows(
                session,
                "SELECT page_number,evidence_sha256,observed_at FROM "
                "orbit_meta_metric_capture_page WHERE tenant_id=:tenant AND job_id=:job "
                "AND stream_key='insights' ORDER BY page_number",
                {"tenant": job["tenant_id"], "job": job["id"]},
            )
        if not pages:
            reject("META_CAPTURE_INCOMPLETE", "缺少明确指标末页")
        source_hash = digest([[r["page_number"], r["evidence_sha256"]] for r in pages])
        oldest = min(r["observed_at"] for r in pages)
        for expected in units:
            day = expected["business_date"]
            count = expected["entity_count"]
            cell = {
                k: expected[k]
                for k in (
                    "tenant_id",
                    "account_id",
                    "account_snapshot_id",
                    "business_date",
                    "profile_id",
                    "profile_version",
                    "timezone_name",
                    "currency",
                    "owner_user_id",
                    "owner_team_id",
                    "attribution_version",
                )
            }
            cell.update(
                id=str(uuid5(UUID(job["publication_id"]), day.isoformat() + ":cell")),
                publication_id=job["publication_id"],
                capture_sequence=job["capture_sequence"],
                expected_page_count=len(pages),
                received_page_count=len(pages),
                expected_entity_count=count,
                fact_count=count,
                empty_result=count == 0,
                empty_field_mask=0,
                critical_complete=False,
                inventory_hash=expected["entity_hash"],
                source_hash=source_hash,
                oldest_observed_at=mysql_millisecond_instant(utc(oldest)),
            )
            # 先算完整性再插入cell，避免部分物化改变已冻结字段；两次扫描均走页索引。
            complete = count > 0
            async for batch in self._dimensions(job, "AD"):
                _, batch_complete = await self._fact_batch(job, day, cell, batch, profile)
                complete = complete and batch_complete
            cell["critical_complete"] = complete
            await self._tx(actor, job["id"], fence, "append_materialized", cells=[cell])
            async for batch in self._dimensions(job, "AD"):
                facts, _ = await self._fact_batch(job, day, cell, batch, profile)
                await self._tx(actor, job["id"], fence, "append_materialized", facts=facts)
