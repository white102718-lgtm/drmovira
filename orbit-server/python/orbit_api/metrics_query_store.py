"""指标事实窄只读候选；不发行来源、不写结果、不把候选当完整Metrics。"""

import hashlib
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from weakref import WeakKeyDictionary, ref
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import bindparam, text

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.metric_profile_store import fixture_boundary
from orbit_api.metrics_contract import (
    MAX_SAFE_INTEGER,
    parse_internal_metric_query,
    validate_account_local_today,
)
from orbit_api.metrics_query_result_contract import EXPECTED_STREAM_VERSION
from orbit_api.metrics_scope_access import authorize_metric_scope

MAX_READ_BATCH = 200
DATASETS = {"ACCOUNT", "CAMPAIGN", "ADSET", "AD"}
PUBLICATION_BINDING_FIELDS = (
    "tenant_id",
    "id",
    "generation",
    "profile_id",
    "profile_version",
    "profile_hash",
    "authority_kind",
    "source_config_id",
    "source_config_revision",
    "source_proof_hash",
    "state",
    "expected_cell_count",
    "expected_cells_hash",
    "captured_cells_hash",
    "cell_count",
    "fact_count",
    "capture_sequence_max",
    "manifest_hash",
    "publisher_actor_id",
    "request_id",
    "oldest_observed_at",
    "created_at",
    "published_at",
)


def unavailable():
    raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "指标来源或冻结数据尚未完整核验") from None


def invalid_context():
    raise OrbitError(
        409, "METRICS_READ_CONTEXT_INVALID", "指标读取上下文已失效，请重新查询"
    ) from None


def safe_integer(value, *, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_SAFE_INTEGER:
        unavailable()
    return value


def uuid_text(value):
    if (
        type(value) is not str
        or re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value)
        is None
    ):
        unavailable()
    return value


def hash_text(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        unavailable()
    return value


def utc_text(value, *, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not datetime:
        unavailable()
    if value.tzinfo is not None and value.utcoffset() != timedelta(0):
        unavailable()
    return value.replace(tzinfo=UTC).isoformat(timespec="microseconds")


def publication_validation_binding(head):
    """只规范化完整头绑定，不产生权威；Provider必须先独立核来源和登记证据。"""
    try:
        source = head["source_proof_json"]
        if type(source) is str:
            source = json.loads(source)
        if type(source) is not dict:
            unavailable()
        encoded = json.dumps(
            source, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        if len(encoded) > 65536:
            unavailable()
        source_hash = hashlib.sha256(encoded).hexdigest()
        result = dict(head) | {"source_proof_hash": source_hash}
        for field in ("tenant_id", "id", "profile_id", "request_id"):
            uuid_text(result[field])
        for field in (
            "profile_hash",
            "expected_cells_hash",
            "captured_cells_hash",
            "manifest_hash",
        ):
            hash_text(result[field])
        for field in ("generation", "capture_sequence_max", "publisher_actor_id"):
            safe_integer(result[field], minimum=1)
        for field in ("expected_cell_count", "cell_count", "fact_count"):
            safe_integer(result[field])
        if (result["source_config_id"] is None) != (result["source_config_revision"] is None):
            unavailable()
        if result["source_config_id"] is not None:
            uuid_text(result["source_config_id"])
            safe_integer(result["source_config_revision"], minimum=1)
        if result["authority_kind"] not in {"TRUSTED", "ISOLATED_TEST"}:
            unavailable()
        if result["authority_kind"] == "TRUSTED" and result["source_config_id"] is None:
            from orbit_api.meta_metrics_provider import validate_meta_proof

            validate_meta_proof(source)
        if (
            result["state"] != "PUBLISHED"
            or result["cell_count"] != result["expected_cell_count"]
            or result["captured_cells_hash"] != result["expected_cells_hash"]
            or type(result["profile_version"]) is not str
            or not 1 <= len(result["profile_version"]) <= 64
        ):
            unavailable()
        for field in ("oldest_observed_at", "created_at", "published_at"):
            result[field] = utc_text(result[field], nullable=field == "oldest_observed_at")
        return tuple(result[key] for key in PUBLICATION_BINDING_FIELDS)
    except (KeyError, TypeError, ValueError, UnicodeError, OverflowError):
        unavailable()


@dataclass(frozen=True, repr=False)
class PublicationValidationReceipt:
    """来源域实际核验后返回的完整头tuple；标签、True或少量摘要不能替代。"""

    binding: tuple

    @property
    def publication_id(self):
        return self.binding[1] if type(self.binding) is tuple and len(self.binding) > 1 else None


class MetricReadSourceProvider(ABC):
    kind = "TRUSTED"

    @abstractmethod
    async def verify_publications(self, session, scope, query, heads):
        """纯DB当前来源锁/独立证据核验，禁事务中网络；返回至多200个精确receipt。"""


class MetricReadContext:
    """空的不透明服务内句柄；自行实例化不会进入Store的能力登记。"""

    __slots__ = ("__weakref__",)


class MetricCellBatch:
    __slots__ = ("_rows", "__weakref__")

    @property
    def rows(self):
        return self._rows


class MetricFactBatch:
    __slots__ = ("_rows", "__weakref__")

    @property
    def rows(self):
        return self._rows


@dataclass(frozen=True, repr=False)
class _Binding:
    session: object
    transaction: object
    actor: int
    provider: object
    query: Mapping
    scope: object
    anchor: Mapping
    profile: tuple


PROFILE_SQL = """SELECT h.id,h.current_version,h.revision,h.state,v.payload_hash
FROM orbit_metric_profile_head h JOIN orbit_metric_profile_version v
ON v.tenant_id=h.tenant_id AND v.profile_id=h.id AND v.version=h.current_version
WHERE h.tenant_id=:tenant AND h.id=:profile FOR SHARE"""

LATEST_CELLS_SQL = """
SELECT c.* FROM orbit_metric_capture_cell c
JOIN orbit_metric_publication p ON p.tenant_id=c.tenant_id AND p.id=c.publication_id
WHERE c.tenant_id=:tenant AND c.profile_id=:profile AND c.profile_version=:version
AND c.breakdown_key='TOTAL' AND c.business_date BETWEEN :date_from AND :date_to
AND p.state='PUBLISHED' AND p.generation<=:generation
AND (c.account_id>:after_account OR (c.account_id=:after_account AND c.business_date>:after_day))
{snapshot}
AND NOT EXISTS (
 SELECT 1 FROM orbit_metric_capture_cell newer
 JOIN orbit_metric_publication np ON np.tenant_id=newer.tenant_id AND np.id=newer.publication_id
 WHERE newer.tenant_id=c.tenant_id AND newer.account_id=c.account_id
 AND newer.business_date=c.business_date AND newer.profile_id=c.profile_id
 AND newer.profile_version=c.profile_version AND newer.breakdown_key=c.breakdown_key
 AND newer.capture_sequence>c.capture_sequence AND np.state='PUBLISHED'
 AND np.generation<=:generation
)
AND ({visible}) {operator}
ORDER BY c.account_id,c.business_date LIMIT :batch_size
"""


def numerator(value):
    """只规范数据库定点源值，不先round，不把未知/浮点变成零。"""
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite() or value < 0:
        unavailable()
    output = format(value, "f")
    if "." in output:
        output = output.rstrip("0").rstrip(".")
    if len(output) > 28 or re.fullmatch(r"(0|[1-9][0-9]*)(\.[0-9]{1,6})?", output) is None:
        unavailable()
    return output


def batch_size(value):
    if type(value) is not int or not 1 <= value <= MAX_READ_BATCH:
        raise ValueError("内部批量读取必须为1至200")
    return value


def literal_contains(value):
    return "%" + value.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def metric_query_hash(query):
    """完整规范条件摘要；cursor只属于页请求，不能改变冻结查询身份。"""
    return hashlib.sha256(
        canonical({key: value for key, value in query.items() if key != "cursor"}).encode()
    ).hexdigest()


def transaction(session):
    if not session.in_transaction():
        invalid_context()
    value = session.sync_session.get_transaction()
    if value is None:
        invalid_context()
    return value


async def rows(session, statement, values, *, expanding=()):
    query = text(statement)
    if expanding:
        query = query.bindparams(*(bindparam(name, expanding=True) for name in expanding))
    return [dict(row) for row in (await session.execute(query, values)).mappings().all()]


class MetricsQueryStore:
    def __init__(self, source_provider=None, *, clock=None):
        self.source_provider = source_provider
        self.clock = clock or (lambda: datetime.now(UTC))
        self._contexts = WeakKeyDictionary()
        self._cells = WeakKeyDictionary()
        self._facts = WeakKeyDictionary()

    def _provider(self):
        provider = self.source_provider
        if (
            not isinstance(provider, MetricReadSourceProvider)
            or type(provider.kind) is not str
            or provider.kind
            not in {
                "TRUSTED",
                "ISOLATED_TEST",
            }
        ):
            unavailable()
        return provider

    async def _profile(self, session, scope, query):
        if "_history_profile_version" in query:
            from orbit_api.metric_profile_query import history_source_clause

            predicate = history_source_clause(scope.current).replace(
                "hp.published_at<=:as_of", "hp.published_at<=UTC_TIMESTAMP(3)"
            )
            result = await rows(
                session,
                "SELECT v.profile_id AS id,v.version AS current_version,v.payload_hash,"
                "(SELECT MIN(ma.registry_revision) FROM orbit_metric_profile_adapter ma "
                "WHERE ma.tenant_id=v.tenant_id AND ma.profile_id=v.profile_id "
                "AND ma.profile_version=v.version AND ma.profile_hash=v.payload_hash) AS revision "
                "FROM orbit_metric_profile_version v WHERE v.tenant_id=:tenant "
                "AND v.profile_id=:profile AND v.version=:version AND " + predicate,
                {
                    "tenant": scope.current.tenant_id,
                    "profile": query["metric_profile_id"],
                    "version": query["_history_profile_version"],
                    "subject": scope.current.subject_id,
                    "actor": scope.current.actor_id,
                },
            )
            if len(result) != 1:
                unavailable()
            value = result[0]
            safe_integer(value["revision"], minimum=1)
            hash_text(value["payload_hash"])
            return (value["id"], value["current_version"], value["revision"], value["payload_hash"])
        result = await rows(
            session,
            PROFILE_SQL,
            {"tenant": scope.current.tenant_id, "profile": query["metric_profile_id"]},
        )
        if len(result) != 1 or result[0]["state"] != "ENABLED":
            unavailable()
        value = result[0]
        safe_integer(value["revision"], minimum=1)
        hash_text(value["payload_hash"])
        return (value["id"], value["current_version"], value["revision"], value["payload_hash"])

    async def _verify(self, session, scope, query, heads):
        provider = self._provider()
        if not 1 <= len(heads) <= MAX_READ_BATCH:
            unavailable()
        expected = {}
        for head in heads:
            if head["authority_kind"] == "TRUSTED" and head["source_config_id"] is None:
                from orbit_api.meta_metrics_provider import MetaMetricReadSource

                if type(provider) is not MetaMetricReadSource:
                    unavailable()
            binding = publication_validation_binding(head)
            if (
                head["tenant_id"] != scope.current.tenant_id
                or head["authority_kind"] != provider.kind
            ):
                unavailable()
            if head["id"] in expected:
                unavailable()
            expected[head["id"]] = binding
        # Provider只收到有界原头；不能省略被拒旧批次继续给部分事实。
        receipts = await provider.verify_publications(
            session,
            scope,
            MappingProxyType(dict(query)),
            tuple(MappingProxyType(dict(head)) for head in heads),
        )
        if type(receipts) is not tuple or len(receipts) != len(expected):
            unavailable()
        seen = set()
        for receipt in receipts:
            if type(receipt) is not PublicationValidationReceipt:
                unavailable()
            identifier = receipt.publication_id
            if type(identifier) is not str:
                unavailable()
            if identifier in seen or identifier not in expected:
                unavailable()
            value = receipt.binding
            actual = expected[identifier]
            if type(value) is not tuple or len(value) != len(actual):
                unavailable()
            if any(
                type(left) is not type(right) or left != right
                for left, right in zip(value, actual, strict=True)
            ):
                unavailable()
            seen.add(identifier)
        if seen != set(expected):
            unavailable()

    async def select_source_anchor(self, session, actor, query):
        provider = self._provider()  # 默认缺来源时0SQL，不先查询账户/权限或创建空结果。
        current_transaction = transaction(session)
        safe_integer(actor, minimum=1)
        parsed = parse_internal_metric_query(canonical(query).encode())
        if parsed["dataset"] not in DATASETS:
            unavailable()
        if parsed["cursor"] is not None:
            raise OrbitError(409, "METRICS_READ_CONTEXT_INVALID", "结果游标需由完整查询快照层处理")
        scope = await authorize_metric_scope(session, actor, parsed["scope_snapshot_id"])
        if provider.kind == "ISOLATED_TEST":
            await fixture_boundary(session)
        profile = await self._profile(session, scope, parsed)
        candidates = await rows(
            session,
            "SELECT p.* FROM orbit_metric_publication p WHERE p.tenant_id=:tenant "
            "AND p.profile_id=:profile AND p.profile_version=:version AND p.profile_hash=:hash "
            "AND p.state='PUBLISHED' ORDER BY p.generation DESC LIMIT 1",
            {
                "tenant": scope.current.tenant_id,
                "profile": profile[0],
                "version": profile[1],
                "hash": profile[3],
            },
        )
        if len(candidates) != 1:
            unavailable()
        anchor = candidates[0]
        if (anchor["profile_id"], anchor["profile_version"], anchor["profile_hash"]) != (
            profile[0],
            profile[1],
            profile[3],
        ):
            unavailable()
        await self._verify(session, scope, parsed, candidates)
        if transaction(session) is not current_transaction:
            invalid_context()
        context = MetricReadContext()
        self._contexts[context] = _Binding(
            ref(session),
            current_transaction,
            actor,
            provider,
            MappingProxyType(parsed),
            scope,
            MappingProxyType(candidates[0]),
            profile,
        )
        return context

    async def _binding(self, session, context):
        self._provider()
        if type(context) is not MetricReadContext:
            invalid_context()
        binding = self._contexts.get(context)
        if (
            binding is None
            or binding.session() is not session
            or self._provider() is not binding.provider
            or transaction(session) is not binding.transaction
        ):
            invalid_context()
        scope = await authorize_metric_scope(
            session, binding.actor, binding.query["scope_snapshot_id"]
        )
        if (
            scope.current != binding.scope.current
            or scope.auth_version != binding.scope.auth_version
            or scope.auth_fingerprint != binding.scope.auth_fingerprint
            or scope.snapshot_id != binding.scope.snapshot_id
            or scope.snapshot_hash != binding.scope.snapshot_hash
            or scope.member_count != binding.scope.member_count
            or scope.managed_team_ids != binding.scope.managed_team_ids
        ):
            invalid_context()
        if await self._profile(session, scope, binding.query) != binding.profile:
            raise OrbitError(409, "METRICS_SOURCE_CHANGED", "指标口径已变化，请重新查询")
        await self._verify(session, scope, binding.query, [dict(binding.anchor)])
        if transaction(session) is not binding.transaction:
            invalid_context()
        return binding

    async def describe_context(self, session, context):
        """仅从真实同事务票据导出有界只读资料；资料不能被导回当作授信票据。"""
        binding = await self._binding(session, context)
        scope = binding.scope
        return MappingProxyType(
            {
                "actor_id": binding.actor,
                "tenant_id": scope.current.tenant_id,
                "subject_id": scope.current.subject_id,
                "auth_version": scope.auth_version,
                "auth_fingerprint": scope.auth_fingerprint,
                "scope_snapshot_id": scope.snapshot_id,
                "scope_hash": scope.snapshot_hash,
                "scope_count": scope.member_count,
                "query": MappingProxyType(dict(binding.query)),
                "query_hash": metric_query_hash(binding.query),
                "source_publication_id": binding.anchor["id"],
                "source_generation": binding.anchor["generation"],
                "authority_kind": binding.anchor["authority_kind"],
                "profile_id": binding.profile[0],
                "profile_version": binding.profile[1],
                "profile_hash": binding.profile[3],
            }
        )

    async def resume_persisted_query(self, session, actor, query_id):
        """新事务只凭049真实query UUID恢复原截止水位，绝不接受调用方descriptor。"""
        provider = self._provider()
        original_transaction = transaction(session)
        safe_integer(actor, minimum=1)
        uuid_text(query_id)
        # 先核当前monitor动作，再读本actor/tenant持久头；不能先暴露另一主体的query。
        initial = await authorize_metric_scope(session, actor, None)
        found = await rows(
            session,
            "SELECT q.* FROM orbit_metric_query_snapshot q WHERE q.tenant_id=:tenant "
            "AND q.actor_id=:actor AND q.id=:query_id FOR SHARE",
            {"tenant": initial.current.tenant_id, "actor": actor, "query_id": query_id},
        )
        if len(found) != 1 or found[0]["cleanup_requested"]:
            raise OrbitError(404, "NOT_FOUND", "指标查询不存在或不可读")
        header = found[0]
        # 056前的旧行没有独立预期根，不能借旧READY获得新构建的来源许可。
        if (
            header.get("expected_manifest_version") != EXPECTED_STREAM_VERSION
            or type(header.get("expected_membership_count")) is not int
            or not 0 <= header["expected_membership_count"] <= MAX_SAFE_INTEGER
        ):
            unavailable()
        hash_text(header.get("expected_unit_hash"))
        hash_text(header.get("expected_membership_hash"))
        if header["state"] not in {"BUILDING", "READY", "FAILED"}:
            invalid_context()
        try:
            raw = header["query_json"]
            try:
                query = parse_internal_metric_query(
                    (canonical(raw) if type(raw) is dict else raw).encode()
                )
            except OrbitError:
                unavailable()  # 持久化坏输入不是当前用户的422，不发布半包。
            if query["cursor"] is not None or query["dataset"] not in DATASETS:
                invalid_context()
            scope = await authorize_metric_scope(session, actor, query["scope_snapshot_id"])
            expected = {
                "tenant_id": scope.current.tenant_id,
                "actor_id": actor,
                "subject_id": scope.current.subject_id,
                "auth_version": scope.auth_version,
                "auth_fingerprint": scope.auth_fingerprint,
                "account_scope_snapshot_id": scope.snapshot_id,
                "account_scope_hash": scope.snapshot_hash,
                "account_scope_count": scope.member_count,
                "query_hash": metric_query_hash(query),
                "profile_id": query["metric_profile_id"],
            }
            if any(
                type(header[key]) is not type(value) or header[key] != value
                for key, value in expected.items()
            ):
                invalid_context()
            profile = await self._profile(session, scope, query)
            if (header["profile_id"], header["profile_version"], header["profile_hash"]) != (
                profile[0],
                profile[1],
                profile[3],
            ):
                raise OrbitError(409, "METRICS_SOURCE_CHANGED", "指标口径已变化，请重新查询")
            uuid_text(header["source_publication_id"])
            safe_integer(header["source_generation"], minimum=1)
            anchors = await rows(
                session,
                "SELECT p.* FROM orbit_metric_publication p WHERE p.tenant_id=:tenant "
                "AND p.id=:publication_id AND p.generation=:generation FOR SHARE",
                {
                    "tenant": scope.current.tenant_id,
                    "publication_id": header["source_publication_id"],
                    "generation": header["source_generation"],
                },
            )
            if len(anchors) != 1:
                unavailable()
            anchor = anchors[0]
            if (anchor["profile_id"], anchor["profile_version"], anchor["profile_hash"]) != (
                profile[0],
                profile[1],
                profile[3],
            ):
                unavailable()
            if provider.kind == "ISOLATED_TEST":
                await fixture_boundary(session)
            await self._verify(session, scope, query, anchors)
        except (KeyError, TypeError, ValueError, AttributeError):
            unavailable()
        if transaction(session) is not original_transaction:
            invalid_context()
        context = MetricReadContext()
        self._contexts[context] = _Binding(
            ref(session),
            original_transaction,
            actor,
            provider,
            MappingProxyType(query),
            scope,
            MappingProxyType(anchor),
            profile,
        )
        return context

    async def _publications(self, session, binding, cells):
        identifiers = sorted({row["publication_id"] for row in cells})
        if not identifiers:
            return
        if len(identifiers) > MAX_READ_BATCH:
            unavailable()
        heads = await rows(
            session,
            "SELECT p.* FROM orbit_metric_publication p WHERE p.tenant_id=:tenant AND p.id IN :ids",
            {"tenant": binding.scope.current.tenant_id, "ids": identifiers},
            expanding=("ids",),
        )
        if len(heads) != len(identifiers) or {row["id"] for row in heads} != set(identifiers):
            unavailable()
        for head in heads:
            if (
                head["profile_id"] != binding.profile[0]
                or head["profile_version"] != binding.profile[1]
                or head["profile_hash"] != binding.profile[3]
                or type(head["generation"]) is not int
                or not 1 <= head["generation"] <= binding.anchor["generation"]
            ):
                unavailable()
        await self._verify(session, binding.scope, binding.query, heads)
        if transaction(session) is not binding.transaction:
            invalid_context()

    async def iter_latest_cells(self, session, context, *, read_batch_size=200):
        self._provider()
        size = batch_size(read_batch_size)
        after_account, after_day = "", date(1000, 1, 1)
        while True:
            binding = await self._binding(session, context)
            scope, query = binding.scope, binding.query
            snapshot = ""
            values = {
                "tenant": scope.current.tenant_id,
                "profile": binding.profile[0],
                "version": binding.profile[1],
                "date_from": query["date_from"],
                "date_to": query["date_to"],
                "generation": binding.anchor["generation"],
                "after_account": after_account,
                "after_day": after_day,
                "batch_size": size,
                "subject": scope.current.subject_id,
            }
            visible = "c.owner_user_id=:subject"
            if scope.current.data_role == "SUPER_ADMIN":
                visible = "1=1"
            elif scope.current.data_role == "TEAM_ADMIN" and scope.managed_team_ids:
                visible += " OR c.owner_team_id IN :managed"
                values["managed"] = scope.managed_team_ids
            if scope.snapshot_id is not None:
                snapshot = (
                    "AND EXISTS(SELECT 1 FROM orbit_account_scope_member m WHERE "
                    "m.tenant_id=c.tenant_id AND m.snapshot_id=:snapshot "
                    "AND m.account_id=c.account_id)"
                )
                values["snapshot"] = scope.snapshot_id
            operator = ""
            if query["operator_user_id"] is not None:
                operator = "AND c.owner_user_id=:operator"
                values["operator"] = query["operator_user_id"]
            found = await rows(
                session,
                LATEST_CELLS_SQL.format(snapshot=snapshot, visible=visible, operator=operator),
                values,
                expanding=("managed",) if "managed" in values else (),
            )
            if not found:
                return
            if len(found) > size:
                unavailable()
            now = self.clock()
            if type(now) is not datetime or now.tzinfo is None:
                unavailable()
            previous = (after_account, after_day)
            for cell in found:
                key = (uuid_text(cell["account_id"]), cell["business_date"])
                if type(key[1]) is not date or key <= previous:
                    unavailable()
                previous = key
                if (
                    cell["tenant_id"] != scope.current.tenant_id
                    or cell["profile_id"] != binding.profile[0]
                    or cell["profile_version"] != binding.profile[1]
                    or cell["breakdown_key"] != "TOTAL"
                ):
                    unavailable()
                try:
                    today = now.astimezone(ZoneInfo(cell["timezone_name"])).date()
                except (ZoneInfoNotFoundError, ValueError, TypeError):
                    unavailable()
                validate_account_local_today(query, today)
            await self._publications(session, binding, found)
            batch = MetricCellBatch()
            batch._rows = tuple(MappingProxyType(dict(row)) for row in found)
            self._cells[batch] = (binding, batch.rows)
            if transaction(session) is not binding.transaction:
                invalid_context()
            yield batch
            after_account, after_day = previous
            if len(found) < size:
                return

    def _batch(self, batch, binding, *, facts=False):
        table = self._facts if facts else self._cells
        expected = MetricFactBatch if facts else MetricCellBatch
        if type(batch) is not expected:
            invalid_context()
        record = table.get(batch)
        if record is None or record[0] is not binding:
            invalid_context()
        return record[1]

    async def iter_selected_facts(self, session, context, cells, *, read_batch_size=200):
        self._provider()
        size = batch_size(read_batch_size)
        after_cell, after_id = "", ""
        while True:
            binding = await self._binding(session, context)
            selected = self._batch(cells, binding)
            await self._publications(session, binding, selected)
            ids = tuple(sorted({row["id"] for row in selected}))
            if not ids:
                return
            values = {
                "tenant": binding.scope.current.tenant_id,
                "ids": ids,
                "after_cell": after_cell,
                "after_id": after_id,
                "batch_size": size,
            }
            channel = ""
            if binding.query["channel_id"] is not None:
                channel = " AND f.channel_id=:channel"
                values["channel"] = binding.query["channel_id"]
            found = await rows(
                session,
                "SELECT f.* FROM orbit_metric_ad_fact_version f WHERE f.tenant_id=:tenant "
                "AND f.cell_id IN :ids AND f.is_deleted=0 AND "
                "(f.cell_id>:after_cell OR (f.cell_id=:after_cell AND f.id>:after_id))"
                + channel
                + " ORDER BY f.cell_id,f.id LIMIT :batch_size",
                values,
                expanding=("ids",),
            )
            if not found:
                return
            previous = (after_cell, after_id)
            cell_map = {row["id"]: row for row in selected}
            if len(found) > size:
                unavailable()
            for fact in found:
                key = (uuid_text(fact["cell_id"]), uuid_text(fact["id"]))
                if key <= previous or key[0] not in cell_map:
                    unavailable()
                previous = key
                cell = cell_map[key[0]]
                for field in (
                    "tenant_id",
                    "account_id",
                    "account_snapshot_id",
                    "business_date",
                    "profile_id",
                    "profile_version",
                    "breakdown_key",
                    "capture_sequence",
                ):
                    if type(fact[field]) is not type(cell[field]) or fact[field] != cell[field]:
                        unavailable()
            for fact in found:
                for field in (
                    "spend",
                    "impressions",
                    "clicks",
                    "registrations",
                    "purchases",
                    "purchase_value",
                ):
                    fact[field] = numerator(fact[field])
            batch = MetricFactBatch()
            batch._rows = tuple(MappingProxyType(dict(row)) for row in found)
            self._facts[batch] = (binding, batch.rows, selected)
            if transaction(session) is not binding.transaction:
                invalid_context()
            yield batch
            after_cell, after_id = previous
            if len(found) < size:
                return

    async def select_dimensions(self, session, context, batch):
        """完整有界原始维度；结果构建必须先跨全窗口选最新名，再筛实体整组。"""
        return await self._select_dimensions(session, context, batch, match_query=False)

    async def select_matching_dimensions(self, session, context, batch):
        """仅局部名称候选，不可据此裁剪聚合贡献；完整结果使用select_dimensions。"""
        return await self._select_dimensions(session, context, batch, match_query=True)

    async def _select_dimensions(self, session, context, batch, *, match_query):
        binding = await self._binding(session, context)
        if type(batch) is MetricCellBatch:
            source = self._batch(batch, binding)
            if binding.query["dataset"] != "ACCOUNT":
                invalid_context()
            await self._publications(session, binding, source)
        else:
            source = self._batch(batch, binding, facts=True)
            await self._publications(session, binding, self._facts[batch][2])
        kind = binding.query["dataset"]
        column = kind.lower() + "_snapshot_id"
        ids = tuple(sorted({row[column] for row in source}))
        if not ids:
            return ()
        if len(ids) > MAX_READ_BATCH:
            unavailable()
        values = {"tenant": binding.scope.current.tenant_id, "ids": ids, "kind": kind}
        # q先在相关维度做包含匹配，不把未命中10000码点全文传回Python。
        # 先有界核精确候选集合，防丢失/坏维度被伪装成无搜索结果。
        q = binding.query["q"] if match_query else ""
        if q:
            metadata = await rows(
                session,
                "SELECT d.id,d.tenant_id,d.account_id,d.entity_kind,"
                "CHAR_LENGTH(d.name) AS name_length FROM orbit_metric_entity_snapshot d "
                "WHERE d.tenant_id=:tenant AND d.entity_kind=:kind AND d.id IN :ids",
                values,
                expanding=("ids",),
            )
            if len(metadata) != len(ids) or {item["id"] for item in metadata} != set(ids):
                unavailable()
            expected_accounts = {row[column]: row["account_id"] for row in source}
            for item in metadata:
                if (
                    item["tenant_id"] != binding.scope.current.tenant_id
                    or item["account_id"] != expected_accounts[item["id"]]
                    or item["entity_kind"] != kind
                    or type(item["name_length"]) is not int
                    or not 0 <= item["name_length"] <= 10000
                ):
                    unavailable()
        condition = ""
        if q:
            condition = " AND (d.name LIKE :contains ESCAPE '!'"
            values["contains"] = literal_contains(q)
            # 原external_id是ASCII数字串；非数字名称不送进ASCII列比较或猜成代码。
            if re.fullmatch(r"[0-9]{1,64}", q):
                condition += " OR d.external_id=:external_id"
                values["external_id"] = q
            condition += ")"
        found = await rows(
            session,
            "SELECT d.* FROM orbit_metric_entity_snapshot d WHERE d.tenant_id=:tenant "
            "AND d.entity_kind=:kind AND d.id IN :ids" + condition + " ORDER BY d.id",
            values,
            expanding=("ids",),
        )
        returned = [item["id"] for item in found]
        if len(returned) != len(set(returned)) or not set(returned).issubset(ids):
            unavailable()
        if not q and set(returned) != set(ids):
            unavailable()
        expected = {row[column]: row["account_id"] for row in source}
        for item in found:
            if (
                item["tenant_id"] != binding.scope.current.tenant_id
                or item["account_id"] != expected[item["id"]]
                or item["entity_kind"] != kind
                or type(item["name"]) is not str
                or len(item["name"]) > 10000
                or type(item["external_id"]) is not str
                or re.fullmatch(r"[0-9]{1,64}", item["external_id"]) is None
            ):
                unavailable()
        if transaction(session) is not binding.transaction:
            invalid_context()
        return tuple(MappingProxyType(item) for item in found)
