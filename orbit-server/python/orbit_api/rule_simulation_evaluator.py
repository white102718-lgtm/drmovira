"""有界纯模拟计算；无权限/来源发行、SQL、Simulation响应或启用资格。

只有真实EOF、预期身份根/数量相符及所有sink成功后返回完整内部summary。
sink已消费前缀不会被本模块回滚；未来Store必须以BUILDING暂存并独立发布。
"""

import asyncio
import hashlib
import re
from collections.abc import AsyncIterable, Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID

from orbit_api.directory_tokens import canonical
from orbit_api.metrics_aggregation import decimal_text
from orbit_api.rule_conditions import Truth, compile_conditions, evaluate_conditions
from orbit_api.rule_contract import MONEY_METRICS, RuleWrite, parse_rule_write

ALGORITHM_VERSION = "orbit-rule-simulation-evaluator-v1"
IDENTITY_DOMAIN = "ORBIT_RULE_SIMULATION_ENTITY_IDS_V1"
RESULT_DOMAIN = "ORBIT_RULE_SIMULATION_RESULTS_V1"
MAX_SCANNED = 2147483647  # 原Simulation.scanned_count范围，不是新增业务上限。
MAX_BATCH = 200  # 仅本内部流式协议内存预算，不限制完整模拟实体总量。
METRICS = frozenset(
    {
        "spend",
        "impressions",
        "clicks",
        "registrations",
        "purchases",
        "purchase_value",
        "roas",
        "cpm",
        "ctr",
        "cpc",
        "cpa",
    }
)


def _uuid(value):
    if type(value) is not str:
        raise ValueError("SIMULATION_ENTITY_UUID_INVALID")
    try:
        valid = str(UUID(value)) == value
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("SIMULATION_ENTITY_UUID_INVALID")


def _frame(value):
    payload = canonical(value).encode("utf-8")
    return len(payload).to_bytes(8, "big") + payload


def _hasher(domain):
    value = hashlib.sha256()
    value.update(_frame({"domain": domain, "version": 1}))
    return value


def _identity_finish(hasher, count):
    hasher.update(_frame({"count": count}))
    return hasher.hexdigest()


def entity_ids_root(ids: Iterable[str]) -> str:
    """未来adapter可复用的纯身份根格式；不是可信预期集合issuer。"""
    hasher, after, count = _hasher(IDENTITY_DOMAIN), "", 0
    for entity_id in ids:
        _uuid(entity_id)
        if entity_id <= after or count == MAX_SCANNED:
            raise ValueError("SIMULATION_ENTITY_ORDER_OR_COUNT_INVALID")
        hasher.update(_frame(entity_id))
        after, count = entity_id, count + 1
    return _identity_finish(hasher, count)


@dataclass(frozen=True, slots=True)
class ExpectedEntityStream:
    entity_count: int
    entity_ids_root: str

    def __post_init__(self):
        if type(self.entity_count) is not int or not 0 <= self.entity_count <= MAX_SCANNED:
            raise ValueError("SIMULATION_EXPECTED_COUNT_INVALID")
        if (
            type(self.entity_ids_root) is not str
            or re.fullmatch(r"[a-f0-9]{64}", self.entity_ids_root) is None
        ):
            raise ValueError("SIMULATION_EXPECTED_ROOT_INVALID")


@dataclass(frozen=True, slots=True)
class EntityObservation:
    entity_id: str
    account_id: str
    currency: str | None
    observations: Mapping[str, Decimal | str | None]

    def __post_init__(self):
        _uuid(self.entity_id)
        _uuid(self.account_id)
        if self.currency is not None and (
            type(self.currency) is not str or re.fullmatch(r"[A-Z]{3}", self.currency) is None
        ):
            raise ValueError("SIMULATION_CURRENCY_INVALID")
        if not isinstance(self.observations, Mapping):
            raise ValueError("SIMULATION_OBSERVATIONS_INVALID")
        copied = dict(self.observations)
        if (
            any(type(key) is not str for key in copied)
            or set(copied) - METRICS
            or any(
                value is not None and type(value) not in {str, Decimal} for value in copied.values()
            )
        ):
            raise ValueError("SIMULATION_OBSERVATIONS_INVALID")
        # Key/value均不可变，复制后再只读包装，不能仅依赖浅frozen dataclass。
        object.__setattr__(self, "observations", MappingProxyType(copied))


@dataclass(frozen=True, slots=True)
class EvaluatedCondition:
    entity_id: str
    condition_index: int
    value: str | None
    result: Truth
    reason_code: str | None

    def public(self):
        return {
            "entity_id": self.entity_id,
            "condition_index": self.condition_index,
            "value": self.value,
            "result": self.result,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class EntityEvaluation:
    entity_id: str
    account_id: str
    currency: str | None
    result: Truth
    conditions: tuple[EvaluatedCondition, ...]

    def _root_value(self):
        return {
            "entity_id": self.entity_id,
            "account_id": self.account_id,
            "currency": self.currency,
            "result": self.result,
            "conditions": [value.public() for value in self.conditions],
        }


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    algorithm: str
    rule_hash: str
    scanned_count: int
    hit_count: int
    unknown_count: int
    false_count: int
    condition_count: int
    entity_ids_root: str
    results_root: str


ResultSink = Callable[[tuple[EntityEvaluation, ...]], Awaitable[None]]


async def evaluate_simulation_entities(
    rule: RuleWrite,
    expected: ExpectedEntityStream,
    batches: AsyncIterable[tuple[EntityObservation, ...]],
    sink: ResultSink,
) -> EvaluationSummary:
    if not isinstance(rule, RuleWrite) or type(expected) is not ExpectedEntityStream:
        raise ValueError("SIMULATION_INPUT_CONTRACT_REQUIRED")
    if not callable(sink):
        raise ValueError("SIMULATION_ASYNC_SINK_REQUIRED")
    frozen_rule = parse_rule_write(
        canonical(rule.model_dump(include=set(RuleWrite.model_fields))).encode()
    )
    tree = compile_conditions(frozen_rule)
    rule_hash = hashlib.sha256(canonical(frozen_rule.model_dump()).encode()).hexdigest()
    identity, results = _hasher(IDENTITY_DOMAIN), _hasher(RESULT_DOMAIN)
    results.update(
        _frame(
            {
                "algorithm": ALGORITHM_VERSION,
                "rule_hash": rule_hash,
                "expected_count": expected.entity_count,
                "entity_ids_root": expected.entity_ids_root,
            }
        )
    )
    scanned, hit, unknown, false, condition_count, after = 0, 0, 0, 0, 0, ""
    async for batch in batches:
        if type(batch) is not tuple or not 1 <= len(batch) <= MAX_BATCH:
            raise ValueError("SIMULATION_BATCH_INVALID")
        output = []
        for entity in batch:
            if type(entity) is not EntityObservation:
                raise ValueError("SIMULATION_ENTITY_CONTRACT_REQUIRED")
            if entity.entity_id <= after:
                raise ValueError("SIMULATION_ENTITY_ORDER_INVALID")
            if scanned >= expected.entity_count or scanned >= MAX_SCANNED:
                raise ValueError("SIMULATION_STREAM_EXCEEDS_EXPECTED")
            observed = entity.observations
            if entity.currency is None:
                # 不猜USD；仅原金额单位指标未知，不污染独立计数/比例。
                observed = {
                    key: None if key in MONEY_METRICS else value for key, value in observed.items()
                }
            evaluation = evaluate_conditions(tree, observed)
            leaves = tuple(
                EvaluatedCondition(
                    entity.entity_id,
                    leaf.condition_index,
                    decimal_text(leaf.value) if leaf.value is not None else None,
                    leaf.result,
                    leaf.reason_code,
                )
                for leaf in evaluation.conditions
            )
            value = EntityEvaluation(
                entity.entity_id, entity.account_id, entity.currency, evaluation.result, leaves
            )
            identity.update(_frame(entity.entity_id))
            results.update(_frame(value._root_value()))
            output.append(value)
            after, scanned = entity.entity_id, scanned + 1
            hit += evaluation.result == "TRUE"
            unknown += evaluation.result == "UNKNOWN"
            false += evaluation.result == "FALSE"
            condition_count += len(leaves)
        if await sink(tuple(output)) is not None:
            raise ValueError("SIMULATION_SINK_ACK_INVALID")
        # 即使adapter/sink自身从不挂起，也在每个有界批次响应取消。
        await asyncio.sleep(0)
    await asyncio.sleep(0)
    actual_root = _identity_finish(identity, scanned)
    if scanned != expected.entity_count or actual_root != expected.entity_ids_root:
        raise ValueError("SIMULATION_STREAM_INCOMPLETE_OR_ROOT_MISMATCH")
    statistics = {
        "scanned_count": scanned,
        "hit_count": hit,
        "unknown_count": unknown,
        "false_count": false,
        "condition_count": condition_count,
    }
    results.update(_frame({"summary": statistics}))
    return EvaluationSummary(
        ALGORITHM_VERSION,
        rule_hash,
        scanned,
        hit,
        unknown,
        false,
        condition_count,
        actual_root,
        results.hexdigest(),
    )
