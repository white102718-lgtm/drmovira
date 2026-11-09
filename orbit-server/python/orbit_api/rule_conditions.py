"""每对象的Decimal三值条件纯核心；不读取事实、不授予模拟或执行资格。"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from orbit_api.rule_contract import (
    COUNTS,
    DECIMAL_TEXT,
    RuleWrite,
    parse_rule_write,
    threshold_value,
)

Truth = Literal["TRUE", "FALSE", "UNKNOWN"]


@dataclass(frozen=True)
class Leaf:
    condition_index: int
    metric: str
    operator: str
    threshold: Decimal


@dataclass(frozen=True)
class Group:
    logic: str
    conditions: tuple[Leaf, ...]


@dataclass(frozen=True)
class ConditionTree:
    logic: str
    groups: tuple[Group, ...]


@dataclass(frozen=True)
class LeafResult:
    condition_index: int
    value: Decimal | None
    result: Truth
    reason_code: str | None


@dataclass(frozen=True)
class Evaluation:
    result: Truth
    groups: tuple[Truth, ...]
    conditions: tuple[LeafResult, ...]


def compile_conditions(rule: RuleWrite) -> ConditionTree:
    # 经严格入口重新核验，冻结为tuple/Decimal，不保留调用方可变列表引用。
    rule = parse_rule_write(
        json.dumps(rule.model_dump(include=set(RuleWrite.model_fields)), ensure_ascii=True).encode()
    )
    index = 0
    groups = []
    for gi, group in enumerate(rule.groups):
        leaves = []
        for ci, condition in enumerate(group.conditions):
            leaves.append(
                Leaf(
                    index,
                    condition.metric,
                    condition.operator,
                    threshold_value(condition, f"/groups/{gi}/conditions/{ci}/threshold"),
                )
            )
            index += 1
        groups.append(Group(group.logic, tuple(leaves)))
    return ConditionTree(rule.logic, tuple(groups))


def combine(logic: str, values: tuple[Truth, ...]) -> Truth:
    if (
        logic not in {"AND", "OR"}
        or not values
        or any(value not in {"TRUE", "FALSE", "UNKNOWN"} for value in values)
    ):
        raise ValueError("三值逻辑输入无效")
    decisive = "FALSE" if logic == "AND" else "TRUE"
    if decisive in values:
        return decisive
    if "UNKNOWN" in values:
        return "UNKNOWN"
    return "TRUE" if logic == "AND" else "FALSE"


def _observed(metric: str, value):
    if value is None:
        return None, "METRIC_MISSING"
    if isinstance(value, str):
        if len(value) > 28 or DECIMAL_TEXT.fullmatch(value) is None:
            return None, "METRIC_INVALID"
        value = Decimal(value)
    # 严格拒float/bool/int；指标适配器须保持Decimal或原Decimal字符串精度。
    if not isinstance(value, Decimal) or not value.is_finite() or value.is_signed():
        return None, "METRIC_INVALID"
    # 在任何定点字符串展开之前界定大小，避免1E+巨量指数产生巨型输出。
    _, digits, exponent = value.as_tuple()
    if exponent < -6 or max(1, len(digits) + exponent) + (1 - exponent if exponent < 0 else 0) > 28:
        return None, "METRIC_INVALID"
    if metric in COUNTS and value != value.to_integral_value():
        return None, "METRIC_INVALID"
    return value, None


def evaluate_conditions(tree: ConditionTree, observations: Mapping[str, Decimal | str | None]):
    """不短路：即使根已确定，仍保留每条叶子的稳定全树索引及未知原因。

    调用者每次仅传同一个对象自身账户币种的数据；本函数没有跨币求和或汇率。
    """
    leaves = []
    groups = []
    for group in tree.groups:
        current = []
        for leaf in group.conditions:
            value, reason = _observed(leaf.metric, observations.get(leaf.metric))
            result: Truth = "UNKNOWN"
            if reason is None:
                try:
                    result = (
                        "TRUE"
                        if {
                            "GT": value > leaf.threshold,
                            "GTE": value >= leaf.threshold,
                            "LT": value < leaf.threshold,
                            "LTE": value <= leaf.threshold,
                            "EQ": value == leaf.threshold,
                            "NEQ": value != leaf.threshold,
                        }[leaf.operator]
                        else "FALSE"
                    )
                except (InvalidOperation, KeyError):
                    raise ValueError("条件树不是已编译合同") from None
            leaves.append(LeafResult(leaf.condition_index, value, result, reason))
            current.append(result)
        groups.append(combine(group.logic, tuple(current)))
    return Evaluation(combine(tree.logic, tuple(groups)), tuple(groups), tuple(leaves))
