"""只读采集持久化：分页先暂存、独立库存先封存，最后发布原048事实。"""

import hashlib
import re
from dataclasses import asdict
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from orbit_api import account_access
from orbit_api.agent_monitor_store import now_utc, utc
from orbit_api.authorization import require_business_access
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_metrics_provider import decoded, meta_source_proof, rows
from orbit_api.meta_read_contract import (
    AsyncReport,
    MetaAttribution,
    ReadPage,
    validate_api_version,
)
from orbit_api.metric_profile_contract import parse_source_proof, publication
from orbit_api.metric_profile_store import validate_collection_source, validate_current_source
from orbit_api.metrics_query_result_contract import ExpectedEntityMembership, ExpectedUnitReceipt
from orbit_api.metrics_query_store import (
    hash_text,
    publication_validation_binding,
    unavailable,
    uuid_text,
)

DIMENSION_FIELDS = (
    "tenant_id id account_id entity_kind entity_id external_id name "
    "parent_snapshot_id parent_kind content_hash"
).split()
CELL_FIELDS = (
    "tenant_id id publication_id account_id account_snapshot_id business_date profile_id "
    "profile_version capture_sequence timezone_name currency owner_user_id owner_team_id "
    "attribution_version expected_page_count received_page_count expected_entity_count fact_count "
    "empty_result empty_field_mask critical_complete inventory_hash source_hash oldest_observed_at"
).split()
FACT_FIELDS = (
    "tenant_id id cell_id account_id business_date profile_id profile_version capture_sequence "
    "ad_id adset_id campaign_id account_snapshot_id campaign_snapshot_id adset_snapshot_id "
    "ad_snapshot_id "
    "channel_id product_name_snapshot parent_mapping_hash asset_mapping_state asset_mapping_hash "
    "launch_mapping_hash is_deleted spend impressions clicks registrations purchases "
    "purchase_value "
    "observed_at fact_hash"
).split()


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def reject(code="META_COLLECTION_UNVERIFIED", message="采集来源或完整性尚未核验", status=409):
    raise OrbitError(status, code, message)


def source_revision_matches(job, connection):
    return (
        connection is not None
        and connection["status"] == "ACTIVE"
        and all(
            connection[key] == job[target]
            for key, target in (
                ("tenant_id", "tenant_id"),
                ("id", "connection_id"),
                ("revision", "connection_revision"),
            )
        )
    )


async def one(session, sql, params):
    found = await rows(session, sql, params)
    return found[0] if found else None


async def insert(session, table, value, fields):
    if set(value) != set(fields):
        reject("META_MATERIALIZATION_INVALID", "原事实字段不完整", 422)
    await session.execute(
        text(
            "INSERT INTO "
            + table
            + " ("
            + ",".join(fields)
            + ") VALUES ("
            + ",".join(":" + k for k in fields)
            + ")"
        ),
        value,
    )


async def resolved_profile(
    session, tenant, identifier, adapter, connection_id, connection_revision
):
    row = await one(
        session,
        """SELECT h.current_version,h.state,v.*,m.mapping_json,m.mapping_hash,
        m.profile_hash,m.registry_revision,m.revoked_at,m.source_proof_json adapter_proof
        FROM orbit_metric_profile_head h JOIN orbit_metric_profile_version v
        ON v.tenant_id=h.tenant_id AND v.profile_id=h.id AND v.version=h.current_version
        JOIN orbit_metric_profile_adapter m ON m.tenant_id=v.tenant_id AND m.profile_id=v.profile_id
        AND m.profile_version=v.version AND m.adapter_version=:adapter
        WHERE h.tenant_id=:tenant AND h.id=:id FOR SHARE""",
        {"tenant": tenant, "id": identifier, "adapter": adapter},
    )
    if (
        row is None
        or row["state"] != "ENABLED"
        or row["source"] != "META"
        or row["authority_kind"] != "TRUSTED"
        or row["revoked_at"] is not None
    ):
        unavailable()
    payload = decoded(row["payload_json"])
    mapping = decoded(row["mapping_json"])
    proof = decoded(row["source_proof_json"])
    if (
        digest(payload) != row["payload_hash"]
        or digest(mapping) != row["mapping_hash"]
        or row["profile_hash"] != row["payload_hash"]
        or decoded(row["adapter_proof"]) != proof
    ):
        unavailable()
    try:
        parsed = parse_source_proof(proof, row["source"])
        publication(payload, adapter, mapping, parsed)
    except (ValueError, KeyError, TypeError):
        unavailable()
    for field in (
        "source_config_id",
        "source_config_revision",
        "source_connection_id",
        "source_connection_revision",
    ):
        if getattr(parsed, field) != row.get(field):
            unavailable()
    if connection_id is None and connection_revision is None:
        await validate_current_source(session, tenant, parsed)
    else:
        await validate_collection_source(
            session, tenant, parsed, connection_id, connection_revision
        )
    result = dict(
        profile=payload,
        profile_source_hash=row["payload_hash"],
        adapter_version=adapter,
        bound_profile_version=row["current_version"],
        registry_revision=row["registry_revision"],
        attribution_spec=mapping,
    )
    MetaAttribution.from_resolved(result)
    return result


class MetaMetricCollectionStore:
    async def _event(self, session, job, action):
        value = dict(
            id=str(uuid4()),
            tenant_id=job["tenant_id"],
            job_id=job["id"],
            actor_id=job["actor_id"],
            action=action,
            created_at=await now_utc(session),
        )
        await insert(session, "orbit_meta_metric_event", value, tuple(value))
        out = dict(event_id=value["id"], tenant_id=job["tenant_id"], created_at=value["created_at"])
        await insert(session, "orbit_meta_metric_outbox", out, tuple(out))

    async def _source(self, session, actor, account):
        current = await require_business_access(session, actor, "accounts", "accounts.sync")
        await account_access.clock(session, current)
        row = await one(
            session,
            """SELECT a.*,s.connection_id,s.connection_revision,
            s.revision account_source_revision,c.status connection_status,c.revision
            actual_revision,
            (c.token_envelope IS NOT NULL) has_token,c.expires_at,c.data_access_expires_at
            FROM orbit_ad_account a JOIN orbit_meta_account_source s
            ON s.tenant_id=a.tenant_id AND s.account_id=a.id JOIN orbit_meta_connection c
            ON c.tenant_id=s.tenant_id AND c.id=s.connection_id
            WHERE a.tenant_id=:tenant AND a.id=:id AND a.unbound_at IS NULL AND ("""
            + account_access.visible_clause(current, "a")
            + ") FOR SHARE",
            account_access.parameters(current) | {"id": account},
        )
        now = await now_utc(session)
        if row is None:
            reject("NOT_FOUND", "账户或读取来源不可见", 404)
        if (
            row["connection_status"] != "ACTIVE"
            or row["connection_revision"] != row["actual_revision"]
            or not row["has_token"]
            or any(
                row[k] is not None and utc(row[k]) <= now
                for k in ("expires_at", "data_access_expires_at")
            )
        ):
            reject("META_REAUTH_REQUIRED", "账户读取连接已失效", 403)
        return current, row, now

    async def begin(
        self,
        session,
        actor,
        account_id,
        profile_id,
        adapter_version,
        date_from,
        date_to,
        api_version,
        request_id,
    ):
        for value in (account_id, profile_id, request_id):
            uuid_text(value)
        if (
            type(date_from) is not date
            or type(date_to) is not date
            or not 0 <= (date_to - date_from).days <= 92
        ):
            reject("FIELD_INVALID", "采集业务日最长93日", 422)
        validate_api_version(api_version)
        current, source, now = await self._source(session, actor, account_id)
        resolved = await resolved_profile(
            session,
            current.tenant_id,
            profile_id,
            adapter_version,
            source["connection_id"],
            source["connection_revision"],
        )
        profile = resolved["profile"]
        from zoneinfo import ZoneInfo

        if date_to > now.astimezone(ZoneInfo(source["timezone_id"])).date():
            reject("FIELD_INVALID", "不能采集账户未来业务日", 422)
        request_hash = digest(
            [
                request_id,
                account_id,
                profile_id,
                profile["version"],
                date_from.isoformat(),
                date_to.isoformat(),
                source["connection_id"],
                source["connection_revision"],
                adapter_version,
                api_version,
            ]
        )
        params = {"tenant": current.tenant_id, "actor": actor, "request": request_hash}
        await session.execute(
            text(
                "SELECT capture_sequence FROM orbit_metric_fact_clock WHERE "
                "tenant_id=:tenant FOR UPDATE"
            ),
            params,
        )
        prior = await one(
            session,
            "SELECT * FROM orbit_meta_metric_job WHERE tenant_id=:tenant AND "
            "actor_id=:actor AND request_hash=:request FOR UPDATE",
            params,
        )
        if prior:
            return dict(prior)
        await session.execute(
            text(
                "UPDATE orbit_metric_fact_clock SET capture_sequence=capture_sequence+1 "
                "WHERE tenant_id=:tenant"
            ),
            params,
        )
        sequence = (
            await session.execute(
                text(
                    "SELECT capture_sequence FROM orbit_metric_fact_clock WHERE tenant_id=:tenant"
                ),
                params,
            )
        ).scalar_one()
        value = dict(
            tenant_id=current.tenant_id,
            id=str(uuid4()),
            publication_id=str(uuid4()),
            account_id=account_id,
            connection_id=source["connection_id"],
            connection_revision=source["connection_revision"],
            account_source_revision=source["account_source_revision"],
            actor_id=actor,
            profile_id=profile_id,
            profile_version=profile["version"],
            profile_hash=resolved["profile_source_hash"],
            adapter_version=adapter_version,
            api_version=api_version,
            source_fingerprint=digest(
                [source["connection_id"], source["connection_revision"], api_version]
            ),
            date_from=date_from,
            date_to=date_to,
            capture_sequence=sequence,
            state="INVENTORY",
            next_run_at=now,
            checkpoint_json="{}",
            request_hash=request_hash,
            created_at=now,
            updated_at=now,
        )
        await insert(session, "orbit_meta_metric_job", value, tuple(value))
        await self._event(session, value, "META_COLLECTION_STARTED")
        return dict(
            await one(
                session,
                "SELECT * FROM orbit_meta_metric_job WHERE tenant_id=:tenant AND id=:id",
                {"tenant": current.tenant_id, "id": value["id"]},
            )
        )

    async def _job(self, session, actor, job_id, worker=None, fence=None):
        current = await require_business_access(session, actor, "accounts", "accounts.sync")
        job = await one(
            session,
            "SELECT * FROM orbit_meta_metric_job WHERE tenant_id=:tenant AND id=:id FOR UPDATE",
            {"tenant": current.tenant_id, "id": uuid_text(job_id)},
        )
        if job is None or job["actor_id"] != actor:
            reject("NOT_FOUND", "采集任务不可见", 404)
        _, source, now = await self._source(session, actor, job["account_id"])
        if any(
            source[k] != job[k]
            for k in ("connection_id", "connection_revision", "account_source_revision")
        ):
            reject("META_SOURCE_CHANGED", "账户采集来源已变化")
        resolved = await resolved_profile(
            session,
            job["tenant_id"],
            job["profile_id"],
            job["adapter_version"],
            source["connection_id"],
            source["connection_revision"],
        )
        if (
            resolved["profile"]["version"] != job["profile_version"]
            or resolved["profile_source_hash"] != job["profile_hash"]
        ):
            reject("META_PROFILE_CHANGED", "归因配置已变化")
        if worker is not None and (
            job["lease_owner"] != worker
            or job["fencing_token"] != fence
            or job["lease_expires_at"] is None
            or utc(job["lease_expires_at"]) <= now
        ):
            reject("META_COLLECTION_LEASE_EXPIRED", "采集租约或代际已失效")
        return dict(job), source, resolved, now

    async def claim(self, session, actor, job_id, worker_id):
        uuid_text(worker_id)
        job, _, _, now = await self._job(session, actor, job_id)
        if job["state"] in {"PUBLISHED", "FAILED"} or utc(job["next_run_at"]) > now:
            reject("META_JOB_NOT_DUE", "任务无需执行")
        if job["lease_expires_at"] is not None and utc(job["lease_expires_at"]) > now:
            reject("META_JOB_BUSY", "任务已被Worker领取")
        if job["attempts"] >= 3 and job["state"] != "WAIT_REPORT":
            reject("META_RETRY_EXHAUSTED", "任务已达到三次尝试上限")
        state = (
            decoded(job["checkpoint_json"]).get("resume_state", "INVENTORY")
            if job["state"] in {"RETRY_WAIT", "WAIT_REPORT"}
            else job["state"]
        )
        await session.execute(
            text("""UPDATE orbit_meta_metric_job SET attempts=attempts+:increment,
            fencing_token=fencing_token+1,lease_owner=:worker,lease_expires_at=:expires,state=:state,
            updated_at=:now WHERE tenant_id=:tenant AND id=:id"""),
            {
                "tenant": job["tenant_id"],
                "id": job_id,
                "worker": worker_id,
                "increment": 0 if job["state"] == "WAIT_REPORT" else 1,
                "expires": now + timedelta(seconds=120),
                "now": now,
                "state": state,
            },
        )
        return dict(
            await one(
                session,
                "SELECT * FROM orbit_meta_metric_job WHERE tenant_id=:tenant AND id=:id",
                {"tenant": job["tenant_id"], "id": job_id},
            )
        )

    async def renew(self, session, actor, job_id, worker, fence):
        job, _, _, now = await self._job(session, actor, job_id, worker, fence)
        await session.execute(
            text(
                "UPDATE orbit_meta_metric_job SET "
                "lease_expires_at=:expires,updated_at=:now WHERE tenant_id=:tenant AND id=:id"
            ),
            {
                "tenant": job["tenant_id"],
                "id": job_id,
                "expires": now + timedelta(seconds=120),
                "now": now,
            },
        )

    async def report_start(self, session, actor, job_id, worker, fence):
        job, _, _, now = await self._job(session, actor, job_id, worker, fence)
        if job["state"] != "CAPTURING":
            reject()
        checkpoint = decoded(job["checkpoint_json"])
        prior = checkpoint.get("async_report")
        if prior:
            if prior.get("state") == "STARTING":
                reject("META_REPORT_START_UNKNOWN", "报表建立结果未知，禁止自动重复建立")
            return prior
        checkpoint["async_report"] = {"state": "STARTING"}
        await session.execute(
            text(
                "UPDATE orbit_meta_metric_job SET checkpoint_json=:value, "
                "updated_at=:now WHERE tenant_id=:tenant AND id=:id"
            ),
            {"value": canonical(checkpoint), "now": now, "tenant": job["tenant_id"], "id": job_id},
        )
        return None

    async def report_bind(self, session, actor, job_id, worker, fence, report):
        job, source, resolved, now = await self._job(session, actor, job_id, worker, fence)
        if (
            type(report) is not AsyncReport
            or report.source_fingerprint != job["source_fingerprint"]
            or report.account_id != source["external_id"]
            or report.level != "ad"
            or report.window.since != job["date_from"]
            or report.window.until != job["date_to"]
            or report.attribution != MetaAttribution.from_resolved(resolved)
        ):
            reject()
        checkpoint = decoded(job["checkpoint_json"])
        if checkpoint.get("async_report") != {"state": "STARTING"}:
            reject("META_REPORT_START_UNKNOWN", "报表绑定前缺少唯一持久意图")
        value = asdict(report)
        value["window"] = {
            **value["window"],
            "since": report.window.since.isoformat(),
            "until": report.window.until.isoformat(),
        }
        checkpoint["async_report"] = {"state": "BOUND", "report": value}
        await session.execute(
            text(
                "UPDATE orbit_meta_metric_job SET checkpoint_json=:value, "
                "report_id=:report,updated_at=:now WHERE tenant_id=:tenant AND id=:id"
            ),
            {
                "value": canonical(checkpoint),
                "report": report.report_run_id,
                "now": now,
                "tenant": job["tenant_id"],
                "id": job_id,
            },
        )

    async def report_wait(self, session, actor, job_id, worker, fence):
        job, _, _, now = await self._job(session, actor, job_id, worker, fence)
        checkpoint = decoded(job["checkpoint_json"])
        if (
            job["state"] != "CAPTURING"
            or checkpoint.get("async_report", {}).get("state") != "BOUND"
        ):
            reject()
        checkpoint["resume_state"] = "CAPTURING"
        await session.execute(
            text(
                "UPDATE orbit_meta_metric_job SET state='WAIT_REPORT', "
                "lease_owner=NULL,lease_expires_at=NULL,next_run_at=:next,checkpoint_json=:value, "
                "updated_at=:now WHERE tenant_id=:tenant AND id=:id"
            ),
            {
                "value": canonical(checkpoint),
                "now": now,
                "next": now + timedelta(seconds=30),
                "tenant": job["tenant_id"],
                "id": job_id,
            },
        )
        return {"job_id": job_id, "state": "WAIT_REPORT"}

    async def append_capture(self, session, actor, job_id, worker, fence, stream_key, page):
        job, source, _, now = await self._job(session, actor, job_id, worker, fence)
        if (
            type(page) is not ReadPage
            or type(page.items) is not tuple
            or len(page.items) > 200
            or type(page.complete) is not bool
            or page.complete != (page.checkpoint is None)
            or page.source_fingerprint != job["source_fingerprint"]
            or not re.fullmatch(r"(inventory_(?:ACCOUNT|CAMPAIGN|ADSET|AD)|insights)", stream_key)
            or (stream_key.startswith("inventory_") and job["state"] != "INVENTORY")
            or (stream_key == "insights" and job["state"] != "CAPTURING")
        ):
            reject()
        hash_text(page.evidence_sha256)
        hash_text(page.request_fingerprint)
        if page.observed_at.tzinfo is None or page.observed_at > now + timedelta(seconds=5):
            reject()
        prior = await one(
            session,
            """SELECT * FROM orbit_meta_metric_capture_page WHERE tenant_id=:tenant
            AND job_id=:id AND stream_key=:stream ORDER BY page_number DESC LIMIT 1 FOR UPDATE""",
            {"tenant": job["tenant_id"], "id": job_id, "stream": stream_key},
        )
        number = 1 if prior is None else prior["page_number"] + 1
        if prior and (
            prior["complete"] or prior["request_fingerprint"] != page.request_fingerprint
        ):
            reject("META_CHECKPOINT_MISMATCH", "分页已结束或请求已变化")
        if page.checkpoint is not None and (
            page.checkpoint.page_number != number
            or page.checkpoint.source_fingerprint != page.source_fingerprint
            or page.checkpoint.request_fingerprint != page.request_fingerprint
        ):
            reject("META_CHECKPOINT_MISMATCH", "分页检查点不连续")
        value = dict(
            tenant_id=job["tenant_id"],
            job_id=job_id,
            page_number=number,
            stream_key=stream_key,
            request_fingerprint=page.request_fingerprint,
            evidence_sha256=page.evidence_sha256,
            items_json=canonical(list(page.items)),
            checkpoint_json=canonical(asdict(page.checkpoint)) if page.checkpoint else None,
            complete=page.complete,
            observed_at=page.observed_at,
        )
        await insert(session, "orbit_meta_metric_capture_page", value, tuple(value))
        if stream_key == "insights":
            for index, item in enumerate(page.items):
                day = date.fromisoformat(item["date_start"])
                if (
                    item["account_id"] != source["external_id"]
                    or item["level"] != "ad"
                    or item["date_start"] != item["date_stop"]
                    or not job["date_from"] <= day <= job["date_to"]
                ):
                    reject()
                entry = dict(
                    tenant_id=job["tenant_id"],
                    job_id=job_id,
                    external_ad_id=item["ad_id"],
                    business_date=day,
                    stream_key=stream_key,
                    page_number=number,
                    item_index=index,
                )
                await insert(session, "orbit_meta_metric_insight_index", entry, tuple(entry))
        checkpoint = decoded(job["checkpoint_json"]) | {
            stream_key: asdict(page.checkpoint) if page.checkpoint else {"complete": True}
        }
        await session.execute(
            text("""UPDATE orbit_meta_metric_job SET checkpoint_json=:checkpoint,
            page_number=page_number+1,after_cursor=:after,updated_at=:now
            WHERE tenant_id=:tenant AND id=:id"""),
            {
                "tenant": job["tenant_id"],
                "id": job_id,
                "checkpoint": canonical(checkpoint),
                "after": page.checkpoint.after if page.checkpoint else None,
                "now": now,
            },
        )
        return number

    async def append_inventory(
        self, session, actor, job_id, worker, fence, *, units=(), members=(), dimensions=()
    ):
        job, _, _, _ = await self._job(session, actor, job_id, worker, fence)
        if job["state"] != "INVENTORY" or any(
            type(x) not in (tuple, list) or len(x) > 200 for x in (units, members, dimensions)
        ):
            reject()
        for original in dimensions:
            dimension = dict(original)
            observed = dimension.pop("_observed_at")
            if (
                dimension["tenant_id"] != job["tenant_id"]
                or dimension["account_id"] != job["account_id"]
            ):
                reject()
            prior = await one(
                session,
                "SELECT * FROM orbit_metric_entity_snapshot WHERE tenant_id=:tenant AND "
                "id=:id FOR SHARE",
                {"tenant": job["tenant_id"], "id": dimension["id"]},
            )
            if prior:
                if any(prior[k] != dimension[k] for k in DIMENSION_FIELDS):
                    reject("META_DIMENSION_CONFLICT", "相同快照不能变更")
            else:
                await insert(session, "orbit_metric_entity_snapshot", dimension, DIMENSION_FIELDS)
            value = dict(
                tenant_id=job["tenant_id"],
                job_id=job_id,
                account_id=job["account_id"],
                entity_kind=dimension["entity_kind"],
                entity_id=dimension["entity_id"],
                entity_snapshot_id=dimension["id"],
                observed_at=observed,
            )
            await self._expected_insert(
                session,
                "orbit_meta_metric_job_dimension",
                value,
                ("tenant_id", "job_id", "entity_kind", "entity_id"),
            )
        for dataset, unit in units:
            if type(unit) is not ExpectedUnitReceipt or dataset not in {
                "ACCOUNT",
                "CAMPAIGN",
                "ADSET",
                "AD",
            }:
                reject()
            self._inventory_binding(job, unit)
            value = asdict(unit) | {"job_id": job_id, "dataset": dataset}
            await self._expected_insert(
                session,
                "orbit_meta_metric_expected_unit",
                value,
                ("tenant_id", "job_id", "dataset", "account_id", "business_date"),
            )
        for member in members:
            if type(member) is not ExpectedEntityMembership:
                reject()
            self._inventory_binding(job, member)
            value = asdict(member) | {"job_id": job_id}
            await self._expected_insert(
                session,
                "orbit_meta_metric_expected_member",
                value,
                ("tenant_id", "job_id", "dataset", "account_id", "business_date", "entity_id"),
            )

    def _inventory_binding(self, job, item):
        if (
            item.tenant_id != job["tenant_id"]
            or item.account_id != job["account_id"]
            or item.profile_id != job["profile_id"]
            or item.profile_version != job["profile_version"]
            or not job["date_from"] <= item.business_date <= job["date_to"]
        ):
            reject()

    async def _expected_insert(self, session, table, value, keys):
        prior = await one(
            session,
            "SELECT * FROM "
            + table
            + " WHERE "
            + " AND ".join(k + "=:" + k for k in keys)
            + " FOR SHARE",
            value,
        )
        if prior:
            for key, val in value.items():
                old = prior[key]
                if isinstance(val, datetime):
                    old = utc(old)
                    val = utc(val)
                if old != val:
                    reject("META_INVENTORY_CONFLICT", "库存重放不能改变预期成员")
            return
        await insert(session, table, value, tuple(value))

    async def freeze_inventory(self, session, actor, job_id, worker, fence):
        job, _, _, now = await self._job(session, actor, job_id, worker, fence)
        if job["state"] != "INVENTORY":
            reject()
        params = {"tenant": job["tenant_id"], "id": job_id}
        streams = await rows(
            session,
            """SELECT stream_key,MAX(page_number) pages,SUM(complete) completed
            FROM orbit_meta_metric_capture_page WHERE tenant_id=:tenant AND job_id=:id
            AND stream_key LIKE 'inventory_%' GROUP BY stream_key""",
            params,
        )
        if {r["stream_key"] for r in streams} != {
            "inventory_" + k for k in ("ACCOUNT", "CAMPAIGN", "ADSET", "AD")
        } or any(r["completed"] != 1 for r in streams):
            reject("META_INVENTORY_INCOMPLETE", "库存分页未完整结束")
        units = await rows(
            session,
            """SELECT * FROM orbit_meta_metric_expected_unit WHERE tenant_id=:tenant
            AND job_id=:id ORDER BY dataset,account_id,business_date FOR SHARE""",
            params,
        )
        if len(units) != 4 * ((job["date_to"] - job["date_from"]).days + 1):
            reject("META_INVENTORY_INCOMPLETE", "库存必须覆盖四层全部业务日")
        root = hashlib.sha256()
        total_members = 0
        for row in units:
            expected = ExpectedUnitReceipt(
                **{k: row[k] for k in ExpectedUnitReceipt.__dataclass_fields__}
            )
            self._inventory_binding(job, expected)
            inventory = await one(
                session,
                "SELECT COUNT(*) total FROM orbit_meta_metric_job_dimension "
                "WHERE tenant_id=:tenant AND job_id=:id AND entity_kind=:kind",
                params | {"kind": row["dataset"]},
            )
            mismatch = await rows(
                session,
                """SELECT m.entity_id FROM orbit_meta_metric_expected_member m
                LEFT JOIN orbit_meta_metric_job_dimension d ON d.tenant_id=m.tenant_id
                  AND d.job_id=m.job_id AND d.entity_kind=m.dataset AND d.entity_id=m.entity_id
                WHERE m.tenant_id=:tenant AND m.job_id=:id AND m.dataset=:kind
                  AND m.business_date=:day AND (d.entity_id IS NULL
                    OR d.entity_snapshot_id<>m.entity_snapshot_id
                    OR d.observed_at<>m.name_observed_at
                    OR m.name_capture_sequence<>:sequence) LIMIT 1""",
                params
                | {
                    "kind": row["dataset"],
                    "day": row["business_date"],
                    "sequence": job["capture_sequence"],
                },
            )
            if inventory["total"] != expected.entity_count or mismatch:
                reject("META_INVENTORY_INCOMPLETE", "冻结成员必须精确覆盖本次独立结构库存")
            member_hash = hashlib.sha256()
            count = 0
            after = ""
            while True:
                batch = await rows(
                    session,
                    """SELECT * FROM orbit_meta_metric_expected_member
                    WHERE tenant_id=:tenant AND job_id=:id AND dataset=:dataset
                    AND account_id=:account AND business_date=:day AND entity_id>:after
                    ORDER BY entity_id LIMIT 200 FOR SHARE""",
                    params
                    | {
                        "dataset": row["dataset"],
                        "account": row["account_id"],
                        "day": row["business_date"],
                        "after": after,
                    },
                )
                if not batch:
                    break
                for item in batch:
                    values = {k: item[k] for k in ExpectedEntityMembership.__dataclass_fields__}
                    values["name_observed_at"] = utc(values["name_observed_at"])
                    member = ExpectedEntityMembership(**values)
                    self._inventory_binding(job, member)
                    member_hash.update(canonical(member.record()).encode() + b"\n")
                    count += 1
                after = batch[-1]["entity_id"]
            if count != expected.entity_count or member_hash.hexdigest() != expected.entity_hash:
                reject("META_INVENTORY_INCOMPLETE", "库存成员数量或完整根不一致")
            total_members += count
            root.update(canonical([row["dataset"], expected.record()]).encode() + b"\n")
        await session.execute(
            text("""UPDATE orbit_meta_metric_job SET state='CAPTURING',inventory_hash=:hash,
            expected_unit_count=:units,expected_member_count=:members,updated_at=:now
            WHERE tenant_id=:tenant AND id=:id"""),
            params
            | {"hash": root.hexdigest(), "units": len(units), "members": total_members, "now": now},
        )
        await self._event(session, job, "META_INVENTORY_FROZEN")
        return root.hexdigest()

    async def _prepare_publication(self, session, job, now):
        params = {"tenant": job["tenant_id"], "id": job["id"]}
        pages = await rows(
            session,
            """SELECT page_number,complete,evidence_sha256,observed_at
            FROM orbit_meta_metric_capture_page WHERE tenant_id=:tenant AND job_id=:id
            AND stream_key='insights' ORDER BY page_number FOR SHARE""",
            params,
        )
        if (
            not pages
            or not pages[-1]["complete"]
            or any(r["complete"] for r in pages[:-1])
            or [r["page_number"] for r in pages] != list(range(1, len(pages) + 1))
        ):
            reject("META_CAPTURE_INCOMPLETE", "指标分页尚未完整结束")
        head = await one(
            session,
            "SELECT * FROM orbit_metric_publication WHERE tenant_id=:tenant AND "
            "id=:publication FOR UPDATE",
            params | {"publication": job["publication_id"]},
        )
        if head:
            return head
        units = await rows(
            session,
            "SELECT * FROM orbit_meta_metric_expected_unit WHERE tenant_id=:tenant AND "
            "job_id=:id AND dataset='AD' ORDER BY account_id,business_date FOR SHARE",
            params,
        )
        unit_hash = hashlib.sha256()
        for unit in units:
            unit_hash.update(
                canonical(
                    [
                        unit["account_id"],
                        unit["business_date"].isoformat(),
                        job["profile_id"],
                        job["profile_version"],
                        "TOTAL",
                    ]
                ).encode()
                + b"\n"
            )
        value = dict(
            tenant_id=job["tenant_id"],
            id=job["publication_id"],
            profile_id=job["profile_id"],
            profile_version=job["profile_version"],
            profile_hash=job["profile_hash"],
            authority_kind="TRUSTED",
            source_config_id=None,
            source_config_revision=None,
            source_proof_json=canonical(meta_source_proof(job)),
            state="BUILDING",
            expected_cell_count=len(units),
            expected_cells_hash=unit_hash.hexdigest(),
            capture_sequence_max=job["capture_sequence"],
            publisher_actor_id=job["actor_id"],
            request_id=job["id"],
            created_at=now,
        )
        await insert(session, "orbit_metric_publication", value, tuple(value))
        return value

    async def append_materialized(
        self, session, actor, job_id, worker, fence, *, cells=(), facts=()
    ):
        job, _, _, now = await self._job(session, actor, job_id, worker, fence)
        if job["state"] != "CAPTURING" or any(
            type(x) not in (tuple, list) or len(x) > 200 for x in (cells, facts)
        ):
            reject()
        await self._prepare_publication(session, job, now)
        for table, items, fields in (
            ("orbit_metric_capture_cell", cells, CELL_FIELDS),
            ("orbit_metric_ad_fact_version", facts, FACT_FIELDS),
        ):
            for item in items:
                if (
                    item["tenant_id"] != job["tenant_id"]
                    or item["account_id"] != job["account_id"]
                    or item["profile_id"] != job["profile_id"]
                    or item["profile_version"] != job["profile_version"]
                    or item["capture_sequence"] != job["capture_sequence"]
                    or not job["date_from"] <= item["business_date"] <= job["date_to"]
                ):
                    reject()
                if table.endswith("cell") and item["publication_id"] != job["publication_id"]:
                    reject()
                prior = await one(
                    session,
                    "SELECT * FROM " + table + " WHERE tenant_id=:tenant AND id=:id FOR SHARE",
                    {"tenant": job["tenant_id"], "id": item["id"]},
                )
                if prior:
                    for key in fields:
                        old, new = prior[key], item[key]
                        if isinstance(new, datetime):
                            old = utc(old)
                            new = utc(new)
                        if (
                            key
                            in {
                                "spend",
                                "impressions",
                                "clicks",
                                "registrations",
                                "purchases",
                                "purchase_value",
                            }
                            and new is not None
                        ):
                            from decimal import Decimal

                            new = Decimal(new)
                        if old != new:
                            reject("META_MATERIALIZATION_CONFLICT", "重放不能修改已暂存事实")
                else:
                    await insert(session, table, item, fields)

    async def publish(self, session, actor, job_id, worker, fence):
        job, _, _, now = await self._job(session, actor, job_id, worker, fence)
        if job["state"] == "PUBLISHED":
            return {"publication_id": job["publication_id"]}
        if job["state"] != "CAPTURING":
            reject()
        head = await self._prepare_publication(session, job, now)
        params = {"tenant": job["tenant_id"], "publication": job["publication_id"], "job": job_id}
        unexpected = await rows(
            session,
            """SELECT i.external_ad_id FROM orbit_meta_metric_insight_index i
            WHERE i.tenant_id=:tenant AND i.job_id=:job AND NOT EXISTS (
              SELECT 1 FROM orbit_meta_metric_job_dimension d
              JOIN orbit_metric_entity_snapshot s ON s.tenant_id=d.tenant_id
                AND s.id=d.entity_snapshot_id
              WHERE d.tenant_id=i.tenant_id AND d.job_id=i.job_id
                AND d.entity_kind='AD' AND s.external_id=i.external_ad_id) LIMIT 1""",
            params,
        )
        if unexpected:
            reject("META_INVENTORY_CHANGED", "指标含未冻结广告，须重新采集独立库存")
        cells = await rows(
            session,
            """SELECT c.*,u.entity_count,u.entity_hash FROM orbit_metric_capture_cell c
            JOIN orbit_meta_metric_expected_unit u ON u.tenant_id=c.tenant_id AND u.job_id=:job
            AND u.dataset='AD' AND u.account_id=c.account_id AND u.business_date=c.business_date
            WHERE c.tenant_id=:tenant AND c.publication_id=:publication
            ORDER BY c.account_id,c.business_date FOR SHARE""",
            params,
        )
        if len(cells) != head["expected_cell_count"]:
            reject("META_CAPTURE_INCOMPLETE", "事实单元不等于冻结预期")
        root = hashlib.sha256()
        keys = hashlib.sha256()
        fact_count = 0
        oldest = None
        for cell in cells:
            if (
                cell["expected_entity_count"] != cell["entity_count"]
                or cell["fact_count"] != cell["entity_count"]
            ):
                reject("META_CAPTURE_INCOMPLETE", "广告事实不能遗漏独立库存对象")
            keys.update(
                canonical(
                    [
                        cell["account_id"],
                        cell["business_date"].isoformat(),
                        job["profile_id"],
                        job["profile_version"],
                        "TOTAL",
                    ]
                ).encode()
                + b"\n"
            )
            count = 0
            after = ""
            facts_root = hashlib.sha256()
            while True:
                batch = await rows(
                    session,
                    """SELECT f.id,f.fact_hash,f.ad_id,m.entity_id FROM
                    orbit_metric_ad_fact_version f
                    LEFT JOIN orbit_meta_metric_expected_member m ON m.tenant_id=f.tenant_id
                    AND m.job_id=:job
                    AND m.dataset='AD' AND m.account_id=f.account_id AND
                    m.business_date=f.business_date
                    AND m.entity_id=f.ad_id WHERE f.tenant_id=:tenant AND f.cell_id=:cell AND
                    f.id>:after
                    ORDER BY f.id LIMIT 200 FOR SHARE""",
                    params | {"cell": cell["id"], "after": after},
                )
                if not batch:
                    break
                for fact in batch:
                    if fact["entity_id"] is None:
                        reject("META_CAPTURE_INCOMPLETE", "指标广告不属于独立库存")
                    facts_root.update(canonical([fact["id"], fact["fact_hash"]]).encode() + b"\n")
                    count += 1
                after = batch[-1]["id"]
            if count != cell["fact_count"]:
                reject("META_CAPTURE_INCOMPLETE", "广告事实数量不完整")
            fact_count += count
            oldest = (
                min(oldest, cell["oldest_observed_at"]) if oldest else cell["oldest_observed_at"]
            )
            root.update(
                canonical([cell["id"], cell["source_hash"], facts_root.hexdigest()]).encode()
                + b"\n"
            )
        if keys.hexdigest() != head["expected_cells_hash"]:
            reject()
        await session.execute(
            text(
                "SELECT published_generation FROM orbit_metric_fact_clock WHERE "
                "tenant_id=:tenant FOR UPDATE"
            ),
            params,
        )
        await session.execute(
            text(
                "UPDATE orbit_metric_fact_clock SET "
                "published_generation=published_generation+1 WHERE tenant_id=:tenant"
            ),
            params,
        )
        generation = (
            await session.execute(
                text(
                    "SELECT published_generation FROM orbit_metric_fact_clock WHERE "
                    "tenant_id=:tenant"
                ),
                params,
            )
        ).scalar_one()
        await session.execute(
            text(
                "UPDATE orbit_metric_publication SET state='SEALED' WHERE "
                "tenant_id=:tenant AND id=:publication"
            ),
            params,
        )
        await session.execute(
            text("""UPDATE orbit_metric_publication SET state='PUBLISHED',generation=:generation,
            cell_count=:cells,fact_count=:facts,captured_cells_hash=:keys,manifest_hash=:root,
            oldest_observed_at=:oldest,published_at=:now WHERE tenant_id=:tenant AND
            id=:publication"""),
            params
            | {
                "generation": generation,
                "cells": len(cells),
                "facts": fact_count,
                "keys": keys.hexdigest(),
                "root": root.hexdigest(),
                "oldest": oldest,
                "now": now,
            },
        )
        saved = await one(
            session,
            "SELECT * FROM orbit_metric_publication WHERE tenant_id=:tenant AND "
            "id=:publication FOR SHARE",
            params,
        )
        binding = publication_validation_binding(saved)
        receipt = dict(
            tenant_id=job["tenant_id"],
            publication_id=job["publication_id"],
            job_id=job_id,
            binding_json=canonical(binding),
            binding_hash=digest(binding),
            inventory_hash=job["inventory_hash"],
            created_at=now,
        )
        await insert(session, "orbit_meta_metric_publication_receipt", receipt, tuple(receipt))
        await session.execute(
            text(
                "UPDATE orbit_meta_metric_job SET state='PUBLISHED',updated_at=:now WHERE "
                "tenant_id=:tenant AND id=:job"
            ),
            params | {"now": now},
        )
        await self._event(session, job, "META_METRICS_PUBLISHED")
        return {
            "publication_id": job["publication_id"],
            "generation": generation,
            "cell_count": len(cells),
            "fact_count": fact_count,
        }

    async def invalidate_source(self, session, actor, job_id, worker, fence):
        """实际认证失败只撤销其冻结来源；旧响应绝不撤销已重新授权的新版本。"""
        from orbit_api.meta_connection_service import lock_account_clock

        current = await require_business_access(session, actor, "accounts", "accounts.sync")
        await lock_account_clock(session, current.tenant_id)
        params = {"tenant": current.tenant_id, "id": uuid_text(job_id)}
        job = await one(
            session,
            "SELECT * FROM orbit_meta_metric_job WHERE tenant_id=:tenant AND id=:id FOR UPDATE",
            params,
        )
        now = await now_utc(session)
        if (
            job is None
            or job["actor_id"] != actor
            or job["lease_owner"] != worker
            or job["fencing_token"] != fence
            or job["lease_expires_at"] is None
            or utc(job["lease_expires_at"]) <= now
            or job["state"] not in {"INVENTORY", "CAPTURING"}
        ):
            reject("META_COLLECTION_LEASE_EXPIRED", "认证失败回执不属于当前领取")
        visible = await one(
            session,
            "SELECT a.id,s.connection_id,s.connection_revision,s.revision source_revision "
            "FROM orbit_ad_account a LEFT JOIN orbit_meta_account_source s "
            "ON s.tenant_id=a.tenant_id AND s.account_id=a.id WHERE "
            "a.tenant_id=:tenant AND a.id=:id AND a.unbound_at IS NULL AND ("
            + account_access.visible_clause(current, "a")
            + ") FOR SHARE",
            account_access.parameters(current) | {"id": job["account_id"]},
        )
        if visible is None:
            reject("NOT_FOUND", "账户已不可见", 404)
        connection = await one(
            session,
            "SELECT id,tenant_id,revision,status FROM "
            "orbit_meta_connection WHERE tenant_id=:tenant AND id=:id FOR UPDATE",
            {"tenant": current.tenant_id, "id": job["connection_id"]},
        )
        expired = source_revision_matches(job, connection) and all(
            visible[field] == job[target]
            for field, target in (
                ("connection_id", "connection_id"),
                ("connection_revision", "connection_revision"),
                ("source_revision", "account_source_revision"),
            )
        )
        if expired:
            await session.execute(
                text(
                    "UPDATE orbit_meta_connection SET status='REAUTH_REQUIRED', "
                    "token_envelope=NULL,revision=revision+1,updated_at=:now "
                    "WHERE tenant_id=:tenant "
                    "AND id=:id AND revision=:revision"
                ),
                {
                    "tenant": current.tenant_id,
                    "id": job["connection_id"],
                    "revision": job["connection_revision"],
                    "now": now,
                },
            )
            await account_access.event(
                session,
                current,
                "META_CONNECTION",
                job["connection_id"],
                job["connection_revision"] + 1,
                "META_AUTHORIZATION_EXPIRED",
                str(uuid4()),
                {},
            )
        checkpoint = decoded(job["checkpoint_json"]) | {"last_error": "META_AUTH_FAILED"}
        await session.execute(
            text(
                "UPDATE orbit_meta_metric_job SET state='FAILED', "
                "lease_owner=NULL,lease_expires_at=NULL,checkpoint_json=:checkpoint,"
                "updated_at=:now "
                "WHERE tenant_id=:tenant AND id=:id"
            ),
            params | {"checkpoint": canonical(checkpoint), "now": now},
        )
        await self._event(session, job, "META_AUTHORIZATION_FAILED")
        return expired

    async def fail(self, session, actor, job_id, worker, fence, *, retryable, code):
        job, _, _, now = await self._job(session, actor, job_id, worker, fence)
        if code not in {
            "META_RATE_LIMITED",
            "META_TRANSIENT_FAILURE",
            "META_AUTH_FAILED",
            "META_READ_FORBIDDEN",
            "META_RESPONSE_INVALID",
            "META_COLLECTION_UNVERIFIED",
        }:
            code = "META_COLLECTION_UNVERIFIED"
        retry = retryable is True and job["attempts"] < 3
        checkpoint = decoded(job["checkpoint_json"]) | {
            "resume_state": job["state"],
            "last_error": code,
        }
        await session.execute(
            text("""UPDATE orbit_meta_metric_job SET state=:state,next_run_at=:next,
            lease_expires_at=NULL,checkpoint_json=:checkpoint,updated_at=:now
            WHERE tenant_id=:tenant AND id=:id"""),
            {
                "tenant": job["tenant_id"],
                "id": job_id,
                "state": "RETRY_WAIT" if retry else "FAILED",
                "next": now + timedelta(seconds=30 * 2 ** job["attempts"]),
                "checkpoint": canonical(checkpoint),
                "now": now,
            },
        )
