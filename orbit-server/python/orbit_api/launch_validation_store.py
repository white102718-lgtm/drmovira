"""原validate持久协议；无真实权威Provider时503，不建Task或执行广告。

prepare独占短事务，结束后才调用外部只读capture；validate使用调用者外层
事务完成来源重验、Plan状态CAS、不可变预检、审计/outbox和幂等回执。
"""

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from orbit_api import launch_access as access
from orbit_api.authorization import BusinessContext
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import parse_plan_action, uuid_field
from orbit_api.launch_expansion import SHANGHAI, budget_totals, expanded_counts
from orbit_api.launch_plan_source import PlanSource, capture_plan_source
from orbit_api.launch_store import LaunchStore
from orbit_api.launch_validation_contract import (
    SAFE_INTEGER,
    TTL,
    FrozenValidation,
    freeze_validation,
    is_current,
    validation_response,
)
from orbit_api.reference_access import verify_csrf

OPERATION = "plan.validate"
FINGERPRINT = re.compile(r"[a-f0-9]{64}")
OBSERVATION_KINDS = frozenset(
    {
        "ACCOUNT",
        "IDENTITY",
        "MATERIAL",
        "CAPABILITY",
        "POLICY",
        "CHANNEL",
        "PRODUCT",
        "SCOPE",
        "ALLOCATION",
        "NAME_RESERVATION",
        "PROFILE_BINDING",
        "ENVIRONMENT",
        "CONFIGURATION",
    }
)
FREEZE_FIELDS = frozenset(
    {
        "allocation",
        "name_reservation",
        "capability_version",
        "policy_version",
        "scope_version",
        "channel_snapshot",
        "product_snapshot",
        "currency",
        "total_dag_node_count",
    }
)


def unavailable():
    raise OrbitError(503, "LAUNCH_VALIDATION_AUTHORITY_UNAVAILABLE", "生产预检权威来源尚未就绪")


def changed():
    raise OrbitError(409, "STALE_PREVIEW", "预检来源或权限已变化，请重新预检")


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    code: str
    message: str
    constraint: str = ""


@dataclass(frozen=True)
class ObservationReference:
    kind: str
    id: str
    revision: int


@dataclass(frozen=True, repr=False)
class ValidationInput:
    """仅内部短事务捕获；没有Cookie、API Key或浏览器verified字段。"""

    current: BusinessContext
    source: PlanSource
    request_json: bytes

    def request(self):
        return json.loads(self.request_json)


@dataclass(frozen=True, repr=False)
class ValidationEvidence:
    """由受控Provider产生的不可变采集包，自身不等于外部核验成功。"""

    fingerprint: str
    scope_version: int
    total_dag_node_count: int
    errors: tuple[ValidationIssue, ...]
    observations: tuple[ObservationReference, ...]
    # 成功时为FREEZE_FIELDS完整JSON；业务invalid可以为None。
    freeze_arguments_json: bytes | None = None


class ValidationAuthorityProvider(ABC):
    """服务端显式注入的适配器，不从HTTP请求或verified布尔构造。"""

    kind = "TRUSTED"

    @abstractmethod
    async def capture(self, value: ValidationInput) -> ValidationEvidence:
        """无session；所有DB短事务结束后才执行外部只读访问。

        无法取得真实能力/身份/策略时必须503，不能用空错误和零计数代替。
        """

    @abstractmethod
    async def revalidate(self, session, current, source, evidence) -> ValidationEvidence:
        """仅数据库来源clock/排序资源锁，不进行网络请求或任何持久写。

        必须重核caller及实际投手交集、来源revision与观察证据；返回相同包
        才能接力。锁顺序在launch clock/head之前；来源变化不可静默刷新输入。
        此处不得锁launch所属allocation/name头，交Store在launch clock/head后
        按既有发布/命名锁序处理，避免反向等待已有发布事务。
        """


@dataclass(frozen=True, repr=False)
class ValidationPreparation:
    current: BusinessContext
    plan_id: str
    expected: int
    input_hash: str
    source: PlanSource | None
    evidence: ValidationEvidence | None
    provider: ValidationAuthorityProvider | None
    capture_started_at: datetime | None = None
    frozen: FrozenValidation | None = None
    summary_json: bytes | None = None


def _csrf(tokens, current, authorization, csrf):
    try:
        verify_csrf(tokens, current, authorization, csrf)
    except OrbitError as error:
        if error.status == 400:
            raise OrbitError(403, "CSRF_INVALID", "会话校验已失效，请刷新") from None
        raise


async def _database_time(session):
    value = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
    if not isinstance(value, datetime):
        unavailable()
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _request(value, identifier, expected):
    identifier = uuid_field(identifier, ("id",))
    if type(expected) is not int or not 1 <= expected <= SAFE_INTEGER:
        raise OrbitError(400, "REVISION_REQUIRED", "须提供有效If-Match版本")
    value = parse_plan_action(canonical(value).encode(), "validate")
    return identifier, value, access.digest([identifier, expected, value])


def _arguments(raw):
    """受信协议也不接受重复键或NaN；错误只返回固定503，不透包内值。"""

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                unavailable()
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: unavailable())
    except (ValueError, UnicodeError, RecursionError):
        unavailable()


def _checked_evidence(evidence):
    if (
        not isinstance(evidence, ValidationEvidence)
        or not isinstance(evidence.fingerprint, str)
        or not FINGERPRINT.fullmatch(evidence.fingerprint)
    ):
        unavailable()
    if (
        type(evidence.scope_version) is not int
        or not 1 <= evidence.scope_version <= SAFE_INTEGER
        or type(evidence.total_dag_node_count) is not int
        or not 0 <= evidence.total_dag_node_count <= 100000
    ):
        unavailable()
    if (
        not isinstance(evidence.errors, tuple)
        or len(evidence.errors) > 1000
        or any(not isinstance(item, ValidationIssue) for item in evidence.errors)
    ):
        unavailable()
    if not isinstance(evidence.observations, tuple) or len(evidence.observations) > 4000:
        unavailable()
    refs, seen = [], set()
    for item in evidence.observations:
        if (
            not isinstance(item, ObservationReference)
            or item.kind not in OBSERVATION_KINDS
            or type(item.revision) is not int
            or not 1 <= item.revision <= SAFE_INTEGER
        ):
            unavailable()
        try:
            identifier = uuid_field(item.id, ("observations", "id"))
        except OrbitError:
            unavailable()
        if (item.kind, identifier) in seen:
            unavailable()
        seen.add((item.kind, identifier))
        refs.append({"kind": item.kind, "id": identifier, "revision": item.revision})
    encoded = canonical(refs)
    if len(encoded.encode()) > 1024 * 1024:
        unavailable()
    if not evidence.errors:
        raw = evidence.freeze_arguments_json
        if not isinstance(raw, bytes) or not 0 < len(raw) <= 64 * 1024 * 1024:
            unavailable()
        try:
            arguments = _arguments(raw)
            if (
                not isinstance(arguments, dict)
                or set(arguments) != FREEZE_FIELDS
                or not isinstance(arguments["allocation"], dict)
                or not isinstance(arguments["name_reservation"], dict)
                or arguments["scope_version"] != evidence.scope_version
                or arguments["total_dag_node_count"] != evidence.total_dag_node_count
            ):
                unavailable()
        except (ValueError, UnicodeError, RecursionError):
            unavailable()
    elif evidence.freeze_arguments_json is not None:
        # 无效包不携未验证的成功冻结结果，防止调用者误用。
        unavailable()
    return encoded


def _summary(source, evidence, now, request):
    """计数/Decimal预算始终从真实配置重算，Provider不能填写伪零汇总。"""
    plan = source.payload()
    counts = expanded_counts(plan)
    totals = tuple((row["currency"], row["amount"]) for row in budget_totals(plan))
    errors = [
        {
            "path": item.path,
            "code": item.code,
            "message": item.message,
            "constraint": item.constraint,
        }
        for item in evidence.errors
    ]
    if errors:
        return None, validation_response(
            errors=errors,
            counts=counts,
            totals=totals,
            scope_version=evidence.scope_version,
            total_dag_node_count=evidence.total_dag_node_count,
        )
    arguments = _arguments(evidence.freeze_arguments_json)
    if (
        arguments["allocation"].get("id") != request["allocation_id"]
        or arguments["name_reservation"].get("id") != request["name_reservation_id"]
    ):
        unavailable()
    record = freeze_validation(
        plan,
        plan_id=source.plan_id,
        source_revision=source.source_revision,
        validated_at=now,
        **arguments,
    )
    result = validation_response(record)
    if (result["campaign_count"], result["adset_count"], result["ad_count"]) != (
        counts.campaign_count,
        counts.adset_count,
        counts.ad_count,
    ):
        unavailable()
    return record, result


class LaunchValidationStore:
    def __init__(self, tokens, provider=None):
        self.tokens, self.provider = tokens, provider

    async def require_provider(self, session):
        provider = self.provider
        if not isinstance(provider, ValidationAuthorityProvider):
            unavailable()
        if provider.kind == "ISOLATED_TEST":
            url = session.bind.url
            if url.host != "127.0.0.1" or url.port != 13306:
                unavailable()
            database = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
            if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database):
                unavailable()
        elif provider.kind != "TRUSTED":
            unavailable()
        return provider

    async def _lock_references(self, session, current, source, request, evidence):
        """launch clock/head之后核持久头；与既有发布/命名保持锁序。"""
        values = {
            "tenant": current.tenant_id,
            "allocation": request["allocation_id"],
            "names": request["name_reservation_id"],
        }
        allocation = (
            (
                await session.execute(
                    text(
                        "SELECT plan_id,plan_revision,state,algorithm_version,input_hash,active "
                        "FROM orbit_launch_allocation WHERE tenant_id=:tenant "
                        "AND id=:allocation FOR SHARE"
                    ),
                    values,
                )
            )
            .mappings()
            .first()
        )
        names = (
            (
                await session.execute(
                    text(
                        "SELECT plan_id,plan_revision,naming_date "
                        "FROM orbit_launch_name_reservation WHERE tenant_id=:tenant "
                        "AND id=:names FOR SHARE"
                    ),
                    values,
                )
            )
            .mappings()
            .first()
        )
        if (
            allocation is None
            or names is None
            or allocation["plan_id"] != source.plan_id
            or names["plan_id"] != source.plan_id
        ):
            raise OrbitError(404, "NOT_FOUND", "预检分配或名称来源不存在或不属于当前计划")
        if (
            allocation["plan_revision"] != source.source_revision
            or names["plan_revision"] != source.source_revision
        ):
            changed()
        if not evidence.errors:
            arguments = _arguments(evidence.freeze_arguments_json)
            actual_day = (
                names["naming_date"].isoformat()
                if hasattr(names["naming_date"], "isoformat")
                else names["naming_date"]
            )
            if (
                allocation["state"] != "SUCCEEDED"
                or allocation["active"] != 1
                or allocation["algorithm_version"] != arguments["allocation"]["algorithm_version"]
                or allocation["input_hash"] != arguments["allocation"]["input_hash"]
                or actual_day != arguments["name_reservation"]["naming_date"]
            ):
                changed()
            allocation_items = (
                (
                    await session.execute(
                        text(
                            "SELECT slot_key,account_id,asset_id,asset_revision "
                            "FROM orbit_launch_allocation_item WHERE tenant_id=:tenant "
                            "AND allocation_id=:allocation ORDER BY ordinal LIMIT 10001 FOR SHARE"
                        ),
                        values,
                    )
                )
                .mappings()
                .all()
            )
            name_items = (
                (
                    await session.execute(
                        text(
                            "SELECT slot_key,name,sequence FROM orbit_launch_name_item "
                            "WHERE tenant_id=:tenant AND reservation_id=:names "
                            "ORDER BY ordinal LIMIT 10001 FOR SHARE"
                        ),
                        values,
                    )
                )
                .mappings()
                .all()
            )
            # ordinal/JSON数组顺序不是集合身份；完整稳定slot和最终业务值一致才可发布。
            # 多取一项检测超限；每种表只一次集合读取，不逐广告/系列N+1。
            if not 1 <= len(allocation_items) <= 10000 or not 1 <= len(name_items) <= 10000:
                changed()
            actual_allocations = sorted(
                (row["slot_key"], row["account_id"], row["asset_id"], row["asset_revision"])
                for row in allocation_items
            )
            expected_allocations = sorted(
                (row["slot_key"], row["account_id"], row["asset_id"], row["asset_revision"])
                for row in arguments["allocation"]["items"]
            )
            try:
                actual_names = sorted(
                    (row["slot_key"], row["name"], str(int(row["sequence"]))) for row in name_items
                )
            except (ValueError, TypeError, OverflowError):
                changed()
            expected_names = sorted(
                (row["slot_key"], row["name"], str(int(row["sequence"])))
                for row in arguments["name_reservation"]["items"]
            )
            if actual_allocations != expected_allocations or actual_names != expected_names:
                changed()

    async def _known_replay(self, session, current, identifier, key, input_hash):
        """先只读探测，已提交不可变回执可免重新采集；最终仍重核对象范围。

        探测不先锁幂等行，避免与来源→launch clock→head写路径倒置。
        """
        found = (
            await session.execute(
                text(
                    "SELECT 1 FROM orbit_launch_idempotency WHERE tenant_id=:tenant "
                    "AND actor_id=:actor AND operation=:op AND key_hash=:key"
                ),
                access.parameters(current)
                | {"op": OPERATION, "key": hashlib.sha256(key.encode()).hexdigest()},
            )
        ).first()
        if found is None:
            return None
        await access.clock(session, current, write=True)
        await LaunchStore(self.tokens).row(session, current, identifier, write=True)
        return await access.replay(session, current, OPERATION, key, input_hash)

    async def prepare(
        self, session_factory, actor, authorization, csrf, key, value, identifier, expected
    ):
        identifier, value, input_hash = _request(value, identifier, expected)
        async with session_factory() as session, session.begin():
            current = await access.context(session, actor, "launch.edit")
            _csrf(self.tokens, current, authorization, csrf)
            plans = LaunchStore(self.tokens)
            await plans.row(session, current, identifier, unlocked=True)
            replayed = await self._known_replay(session, current, identifier, key, input_hash)
            if replayed is not None:
                return ValidationPreparation(
                    current, identifier, expected, input_hash, None, None, None
                )
            await access.clock(session, current, write=True)
            head = await plans.row(session, current, identifier, write=True)
            self._head(head, expected)
            source = await capture_plan_source(session, current, head)
            # 未接入的新字段先返回具体位置，不能被通用Provider缺失吞掉。
            from orbit_api.launch_meta_settings import require_meta_capabilities

            require_meta_capabilities(source.payload())
            provider = await self.require_provider(session)
            # 提前整数乘法边界，不让外部采集为非法巨大展开服务。
            expanded_counts(source.payload())
            captured = ValidationInput(current, source, canonical(value).encode())
            started = await _database_time(session)
        # 此处两个上下文均已退出，没有数据库长事务等待网络。
        evidence = await provider.capture(captured)
        _checked_evidence(evidence)
        try:
            frozen, summary = _summary(source, evidence, started, value)
        except OrbitError:
            unavailable()
        return ValidationPreparation(
            current,
            identifier,
            expected,
            input_hash,
            source,
            evidence,
            provider,
            started,
            frozen,
            canonical(summary).encode(),
        )

    @staticmethod
    def _head(head, expected):
        if head["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "计划已变化，请重新加载")
        if head["state"] not in {"DRAFT", "VALIDATED"}:
            raise OrbitError(409, "INVALID_TRANSITION", "当前计划状态不允许预检")
        if head["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "计划版本已达上限")

    async def validate(
        self,
        session,
        actor,
        authorization,
        csrf,
        key,
        value,
        identifier,
        expected,
        request_id,
        prepared,
    ):
        if not session.in_transaction():
            raise ValueError("validate必须在调用者外层事务内执行")
        identifier, value, input_hash = _request(value, identifier, expected)
        if not isinstance(prepared, ValidationPreparation) or (
            prepared.plan_id,
            prepared.expected,
            prepared.input_hash,
        ) != (identifier, expected, input_hash):
            changed()
        current = await access.context(session, actor, "launch.edit")
        _csrf(self.tokens, current, authorization, csrf)
        plans = LaunchStore(self.tokens)
        await plans.row(session, current, identifier, unlocked=True)
        replayed = await self._known_replay(session, current, identifier, key, input_hash)
        if replayed is not None:
            return replayed
        if (
            current != prepared.current
            or prepared.source is None
            or prepared.evidence is None
            or prepared.provider is not self.provider
        ):
            changed()
        provider = await self.require_provider(session)
        _checked_evidence(prepared.evidence)
        fresh = await provider.revalidate(session, current, prepared.source, prepared.evidence)
        observations = _checked_evidence(fresh)
        if fresh != prepared.evidence:
            changed()
        await access.clock(session, current, write=True)
        head = await plans.row(session, current, identifier, write=True)
        replayed = await access.replay(session, current, OPERATION, key, input_hash)
        if replayed is not None:
            return replayed
        self._head(head, expected)
        source = await capture_plan_source(session, current, head)
        if source != prepared.source:
            changed()
        await self._lock_references(session, current, source, value, fresh)
        now = await _database_time(session)
        started = prepared.capture_started_at
        if not isinstance(started, datetime) or started.tzinfo is None:
            unavailable()
        if (
            not started <= now < started + TTL
            or started.astimezone(SHANGHAI).date() != now.astimezone(SHANGHAI).date()
        ):
            changed()
        if not isinstance(prepared.summary_json, bytes):
            unavailable()
        # 完整树摘要已在capture结束后的无事务阶段计算；最终事务只移动
        # 可信完成时刻，不复制/重新散列万级执行树，不延长观察事实允许年龄。
        record = prepared.frozen
        if (record is None) != bool(fresh.errors):
            unavailable()
        if record is not None:
            now = now.replace(microsecond=now.microsecond // 1000 * 1000)
            record = replace(record, validated_at=now, expires_at=now + TTL)
            result = validation_response(record)
        else:
            result = json.loads(prepared.summary_json)
        if record is not None and not is_current(record, now):
            changed()
        revision = head["revision"] + (
            1 if record is not None or head["state"] == "VALIDATED" else 0
        )
        if revision != head["revision"]:
            updated = await session.execute(
                text(
                    "UPDATE orbit_launch_plan SET state=:state,revision=:revision,"
                    "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:plan "
                    "AND revision=:expected"
                ),
                access.parameters(current)
                | {
                    "state": "VALIDATED" if record is not None else "DRAFT",
                    "revision": revision,
                    "plan": identifier,
                    "expected": expected,
                },
            )
            if updated.rowcount != 1:
                raise OrbitError(409, "REVISION_CONFLICT", "计划已变化，请重新加载")
        if record is not None:
            await self._persist(
                session,
                current,
                source,
                record,
                revision,
                result,
                observations,
                provider.kind,
                fresh.fingerprint,
                value,
            )
        await access.event(
            session,
            current,
            "PLAN",
            identifier,
            revision,
            "plan.validate.succeeded" if record is not None else "plan.validate.invalid",
            request_id,
            {
                "source_revision": source.source_revision,
                "valid": result["valid"],
                "error_count": len(result["errors"]),
                "provider_fingerprint": fresh.fingerprint,
            },
        )
        await access.remember(session, current, OPERATION, key, input_hash, result)
        return result

    async def _persist(
        self,
        session,
        current,
        source,
        record,
        revision,
        summary,
        observations,
        kind,
        fingerprint,
        request,
    ):
        await session.execute(
            text("""INSERT INTO orbit_launch_validation
        (tenant_id,id,plan_id,source_revision,validated_head_revision,payload_hash,
         validation_hash,validated_at,expires_at,naming_date,scope_version,allocation_id,
         name_reservation_id,provider_kind,provider_fingerprint,summary_json,
         observation_refs_json,created_by,created_at)
        VALUES(:tenant,:id,:plan,:source,:head,:payload,:hash,:validated,:expires,:day,
         :scope,:allocation,:names,:kind,:fingerprint,:summary,:observations,:actor,UTC_TIMESTAMP(3))"""),
            access.parameters(current)
            | {
                "id": str(uuid4()),
                "plan": source.plan_id,
                "source": source.source_revision,
                "head": revision,
                "payload": source.payload_hash,
                "hash": record.hash,
                "validated": record.validated_at.replace(tzinfo=None),
                "expires": record.expires_at.replace(tzinfo=None),
                "day": record.naming_date,
                "scope": record.scope_version,
                "allocation": request["allocation_id"],
                "names": request["name_reservation_id"],
                "kind": kind,
                "fingerprint": fingerprint,
                "summary": canonical(summary),
                "observations": observations,
            },
        )
