"""Meta独立封存来源接原指标读取管线；本模块不网络采集、不另建统计值。"""

import hashlib
import json
import re
from datetime import UTC, date

from sqlalchemy import bindparam, text

from orbit_api.directory_tokens import canonical
from orbit_api.metrics_query_result_contract import (
    ExpectedEntityMembership,
    ExpectedUnitManifest,
    ExpectedUnitProvider,
    ExpectedUnitReceipt,
)
from orbit_api.metrics_query_store import (
    MetricReadSourceProvider,
    PublicationValidationReceipt,
    hash_text,
    metric_query_hash,
    publication_validation_binding,
    safe_integer,
    unavailable,
    uuid_text,
)
from orbit_api.metrics_scope_access import authorize_metric_scope

PROOF_KIND = "META_METRICS_COLLECTION_V1"
PROOF_KEYS = {
    "kind",
    "checkpoint_id",
    "connection_id",
    "connection_revision",
    "account_source_revision",
    "inventory_hash",
    "api_version",
}


def meta_source_proof(job):
    """只生成绑定形状；真实授信仍须独立发布时receipt核验。"""
    value = dict(
        kind=PROOF_KIND,
        checkpoint_id=job["id"],
        connection_id=job["connection_id"],
        connection_revision=job["connection_revision"],
        account_source_revision=job["account_source_revision"],
        inventory_hash=job["inventory_hash"],
        api_version=job["api_version"],
    )
    validate_meta_proof(value)
    return value


def validate_meta_proof(value):
    if type(value) is not dict or set(value) != PROOF_KEYS or value["kind"] != PROOF_KIND:
        unavailable()
    for key in ("checkpoint_id", "connection_id"):
        uuid_text(value[key])
    for key in ("connection_revision", "account_source_revision"):
        safe_integer(value[key], minimum=1)
    hash_text(value["inventory_hash"])
    if type(value["api_version"]) is not str or not re.fullmatch(
        r"v[0-9]{1,3}\.[0-9]{1,2}", value["api_version"]
    ):
        unavailable()
    return value


def decoded(value):
    try:
        return json.loads(value) if type(value) is str else value
    except (ValueError, TypeError):
        unavailable()


async def rows(session, sql, params):
    statement = text(sql)
    for key in ("ids", "managed"):
        if key in params:
            statement = statement.bindparams(bindparam(key, expanding=True))
    return (await session.execute(statement, params)).mappings().all()


async def current_scope(session, scope):
    if not session.in_transaction():
        unavailable()
    fresh = await authorize_metric_scope(session, scope.current.actor_id, scope.snapshot_id)
    if fresh != scope:
        unavailable()


class MetaMetricReadSource(MetricReadSourceProvider):
    """可信来源是持久采集封存，不是Token存在、state标签或当前查询头自我声明。"""

    async def verify_publications(self, session, scope, query, heads):
        await current_scope(session, scope)
        if not 1 <= len(heads) <= 200 or len({h["id"] for h in heads}) != len(heads):
            unavailable()
        incoming = {h["id"]: h for h in heads}
        saved = await rows(
            session,
            """SELECT r.*,j.id checkpoint_id,j.connection_id,
            j.connection_revision,j.account_source_revision,j.inventory_hash checkpoint_inventory,
            j.state checkpoint_state,j.publication_id checkpoint_publication,j.api_version,
            j.capture_sequence,j.profile_hash checkpoint_profile_hash,
            v.source profile_source,v.authority_kind profile_authority,v.payload_hash,
            m.revoked_at adapter_revoked,m.profile_hash adapter_profile_hash
            FROM orbit_meta_metric_publication_receipt r
            JOIN orbit_meta_metric_job j ON j.tenant_id=r.tenant_id AND j.id=r.job_id
            JOIN orbit_metric_profile_version v ON v.tenant_id=j.tenant_id
              AND v.profile_id=j.profile_id AND v.version=j.profile_version
            JOIN orbit_metric_profile_adapter m ON m.tenant_id=j.tenant_id
              AND m.profile_id=j.profile_id AND m.profile_version=j.profile_version
              AND m.adapter_version=j.adapter_version
            WHERE r.tenant_id=:tenant AND r.publication_id IN :ids
            ORDER BY r.publication_id FOR SHARE""",
            {"tenant": scope.current.tenant_id, "ids": sorted(incoming)},
        )
        if len(saved) != len(heads):
            unavailable()
        receipts = []
        for row in saved:
            head = incoming.get(row["publication_id"])
            if (
                head is None
                or head["tenant_id"] != scope.current.tenant_id
                or head["authority_kind"] != "TRUSTED"
            ):
                unavailable()
            actual = publication_validation_binding(head)
            binding = decoded(row["binding_json"])
            proof = decoded(head["source_proof_json"])
            if (
                type(binding) is not list
                or canonical(binding) != canonical(actual)
                or hashlib.sha256(canonical(binding).encode()).hexdigest() != row["binding_hash"]
                or row["revoked_at"] is not None
                or row["checkpoint_state"] != "PUBLISHED"
                or row["checkpoint_publication"] != head["id"]
                or row["profile_source"] != "META"
                or row["profile_authority"] != "TRUSTED"
                or row["payload_hash"] != head["profile_hash"]
                or row["checkpoint_profile_hash"] != head["profile_hash"]
                or row["adapter_profile_hash"] != head["profile_hash"]
                or (
                    row["adapter_revoked"] is not None
                    and query.get("_history_profile_version") != head["profile_version"]
                )
                or row["inventory_hash"] != row["checkpoint_inventory"]
                or row["capture_sequence"] != head["capture_sequence_max"]
            ):
                unavailable()
            expected = meta_source_proof(
                dict(
                    id=row["checkpoint_id"],
                    connection_id=row["connection_id"],
                    connection_revision=row["connection_revision"],
                    account_source_revision=row["account_source_revision"],
                    inventory_hash=row["inventory_hash"],
                    api_version=row["api_version"],
                )
            )
            if canonical(proof) != canonical(expected):
                unavailable()
            receipts.append(PublicationValidationReceipt(tuple(binding)))
        return tuple(receipts)


class MetaExpectedUnitProvider(ExpectedUnitProvider):
    """预期集合只来自采集前冻结库存；按原权限求交，不从cell/fact补分母。"""

    def __init__(self, source_provider=None):
        self.source = source_provider or MetaMetricReadSource()

    async def _source(self, session, scope, query, source):
        if source.authority_kind != "TRUSTED" or source.tenant_id != scope.current.tenant_id:
            unavailable()
        found = await rows(
            session,
            "SELECT * FROM orbit_metric_publication WHERE tenant_id=:tenant AND id=:id FOR SHARE",
            {"tenant": source.tenant_id, "id": source.publication_id},
        )
        if len(found) != 1:
            unavailable()
        head = found[0]
        if (
            head["generation"],
            head["profile_id"],
            head["profile_version"],
            head["profile_hash"],
        ) != (source.generation, source.profile_id, source.profile_version, source.profile_hash):
            unavailable()
        await self.source.verify_publications(session, scope, query, found)

    async def _stream(self, session, scope, query, source, *, members=False):
        await self._source(session, scope, query, source)
        alias = "m" if members else "u"
        params = dict(
            tenant=source.tenant_id,
            profile=source.profile_id,
            version=source.profile_version,
            generation=source.generation,
            dataset=query["dataset"],
            date_from=query["date_from"],
            date_to=query["date_to"],
            subject=scope.current.subject_id,
            after_account="",
            after_day=date(1000, 1, 1),
            after_entity="",
            limit=200,
        )
        visible = "u.owner_user_id=:subject"
        if scope.current.data_role == "SUPER_ADMIN":
            visible = "1=1"
        elif scope.current.data_role == "TEAM_ADMIN" and scope.managed_team_ids:
            visible += " OR u.owner_team_id IN :managed"
            params["managed"] = scope.managed_team_ids
        filters = ""
        if query["operator_user_id"] is not None:
            filters += " AND u.owner_user_id=:operator"
            params["operator"] = query["operator_user_id"]
        if scope.snapshot_id:
            filters += """ AND EXISTS(SELECT 1 FROM orbit_account_scope_member sm
                WHERE sm.tenant_id=u.tenant_id AND sm.snapshot_id=:snapshot AND
                sm.account_id=u.account_id)"""
            params["snapshot"] = scope.snapshot_id
        join = ""
        if members:
            join = """ JOIN orbit_meta_metric_expected_member m ON m.tenant_id=u.tenant_id
            AND m.job_id=u.job_id AND m.dataset=u.dataset AND m.account_id=u.account_id
            AND m.business_date=u.business_date"""
        tail = ",m.entity_id" if members else ""
        after = (
            "(u.account_id,u.business_date,m.entity_id)>(:after_account,:after_day,:after_entity)"
            if members
            else "(u.account_id,u.business_date)>(:after_account,:after_day)"
        )
        sql = f"""SELECT {alias}.*,j.publication_id FROM orbit_meta_metric_expected_unit u
            JOIN orbit_meta_metric_job j ON j.tenant_id=u.tenant_id AND j.id=u.job_id
            JOIN orbit_metric_publication p ON p.tenant_id=j.tenant_id AND
            p.id=j.publication_id {join}
            WHERE u.tenant_id=:tenant AND u.profile_id=:profile AND u.profile_version=:version
            AND u.dataset=:dataset AND u.business_date BETWEEN :date_from AND :date_to
            AND p.state='PUBLISHED' AND p.generation<=:generation AND ({visible}) {filters}
            AND {after}
            AND NOT EXISTS(SELECT 1 FROM orbit_meta_metric_expected_unit nu
                JOIN orbit_meta_metric_job nj ON nj.tenant_id=nu.tenant_id AND nj.id=nu.job_id
                JOIN orbit_metric_publication np ON np.tenant_id=nj.tenant_id AND
                np.id=nj.publication_id
                WHERE nu.tenant_id=u.tenant_id AND nu.account_id=u.account_id
                AND nu.business_date=u.business_date AND nu.profile_id=u.profile_id
                AND nu.profile_version=u.profile_version AND nu.dataset=u.dataset
                AND nj.capture_sequence>j.capture_sequence AND np.state='PUBLISHED'
                AND np.generation<=:generation)
            ORDER BY u.account_id,u.business_date{tail} LIMIT :limit FOR SHARE"""
        while True:
            batch = await rows(session, sql, params)
            if not batch:
                break
            heads = await rows(
                session,
                "SELECT * FROM orbit_metric_publication WHERE tenant_id=:tenant AND id IN "
                ":ids FOR SHARE",
                {"tenant": source.tenant_id, "ids": sorted({r["publication_id"] for r in batch})},
            )
            await self.source.verify_publications(session, scope, query, heads)
            receipts = []
            model = ExpectedEntityMembership if members else ExpectedUnitReceipt
            for row in batch:
                values = {key: row[key] for key in model.__dataclass_fields__}
                if members:
                    values["name_observed_at"] = values["name_observed_at"].replace(tzinfo=UTC)
                receipts.append(model(**values))
            yield tuple(receipts)
            last = batch[-1]
            params.update(after_account=last["account_id"], after_day=last["business_date"])
            if members:
                params["after_entity"] = last["entity_id"]

    async def prepare_manifest(self, session, scope, query, source):
        roots = []
        for members in (False, True):
            count = 0
            root = hashlib.sha256()
            async for batch in self._stream(session, scope, query, source, members=members):
                for item in batch:
                    root.update(canonical(item.record()).encode() + b"\n")
                    count += 1
            roots.append((count, root.hexdigest()))
        return ExpectedUnitManifest(
            source,
            scope.current.actor_id,
            scope.current.subject_id,
            scope.auth_version,
            scope.auth_fingerprint,
            metric_query_hash(query),
            query["dataset"],
            date.fromisoformat(query["date_from"]),
            date.fromisoformat(query["date_to"]),
            scope.snapshot_id,
            scope.snapshot_hash,
            scope.member_count,
            roots[0][0],
            roots[0][1],
            roots[1][0],
            roots[1][1],
        )

    async def revalidate_manifest(self, session, scope, query, manifest):
        actual = await self.prepare_manifest(session, scope, query, manifest.source)
        if actual != manifest:
            unavailable()
        return actual

    async def iter_unit_batches(self, session, scope, query, manifest):
        async for batch in self._stream(session, scope, query, manifest.source):
            yield batch

    async def iter_membership_batches(self, session, scope, query, manifest):
        async for batch in self._stream(session, scope, query, manifest.source, members=True):
            yield batch
