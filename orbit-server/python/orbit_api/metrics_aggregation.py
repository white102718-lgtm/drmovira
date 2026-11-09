"""同租户/币种/口径的流式分子汇总；不证明来源、归属或数据质量。"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

from orbit_api.errors import OrbitError
from orbit_api.metrics_contract import DECIMAL_PATTERN, METRIC_NAMES

ALGORITHM_VERSION = "orbit-metric-sum-purchases-ratio6-half-up-v1"
ADDITIVE_NAMES = ("spend", "impressions", "clicks", "registrations", "purchases", "purchase_value")
CRITICAL_NAMES = ("spend", "impressions", "clicks", "purchases", "purchase_value")


def unverified():
    raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "指标汇总数据尚未完整核验") from None


def decimal_text(value: Decimal) -> str:
    # 不用normalize()，避免受进程全局Decimal精度影响而在输出阶段舍入大金额。
    output = format(value, "f")
    if "." in output:
        output = output.rstrip("0").rstrip(".")
    if len(output) > 28 or re.fullmatch(DECIMAL_PATTERN, output) is None:
        unverified()
    return output


def read_numerator(value):
    if value is None:
        return None
    if type(value) is not str or len(value) > 28 or re.fullmatch(DECIMAL_PATTERN, value) is None:
        unverified()
    return Decimal(value)


@dataclass(frozen=True)
class MetricGroup:
    tenant_id: str
    currency: str
    profile_id: str
    profile_version: str

    def __post_init__(self):
        if any(type(value) is not str or not value for value in vars(self).values()):
            unverified()


class MetricAccumulator:
    """仅接收已完成权限/完整cell选择后的分子；各实例必须对应一个精确分组。

    不接收已有比率，避免错误地平均ROAS。缺失任意参与行会污染该列，不能把
    缺失当零；全部无行仍是未知。合法完整空单元的零须由可信发行领域明确提供。
    内存只保留六个Decimal和缺失位，不缓存完整事实行。
    """

    def __init__(self, group: MetricGroup):
        if type(group) is not MetricGroup:
            unverified()
        self.group = group
        self._sums = {name: Decimal(0) for name in ADDITIVE_NAMES}
        self._missing = set()
        self._seen = False

    def add(self, group: MetricGroup, values: Mapping):
        if type(group) is not MetricGroup or group != self.group:
            unverified()
        if not isinstance(values, Mapping) or set(values) != set(ADDITIVE_NAMES):
            unverified()
        parsed = {name: read_numerator(values[name]) for name in ADDITIVE_NAMES}
        # 先验证整行再赋值；坏分子或溢出不能留下半行已累加的中间状态。
        sums = dict(self._sums)
        missing = set(self._missing)
        with localcontext() as context:
            context.prec = 80
            for name, value in parsed.items():
                if value is None:
                    missing.add(name)
                else:
                    sums[name] += value
                    # 原DTO长度是硬边界；非负总和只会增长，超界立即明确失败。
                    decimal_text(sums[name])
        self._sums, self._missing, self._seen = sums, missing, True

    def finish(self, *, ratios_allowed: bool) -> dict:
        """质量许可必须显式提供；它不是本函数推断出的权威质量证明。"""
        if type(ratios_allowed) is not bool:
            unverified()
        result = dict.fromkeys(METRIC_NAMES)
        if not self._seen:
            return result
        for name in ADDITIVE_NAMES:
            if name not in self._missing:
                result[name] = decimal_text(self._sums[name])
        if not ratios_allowed or any(result[name] is None for name in CRITICAL_NAMES):
            return result
        # 原合同：先聚合分子分母，CPA首期指定转化为purchases；分母0返回null。
        formulas = {
            "roas": ("purchase_value", "spend", 1),
            "cpm": ("spend", "impressions", 1000),
            "ctr": ("clicks", "impressions", 100),
            "cpc": ("spend", "clicks", 1),
            "cpa": ("spend", "purchases", 1),
        }
        with localcontext() as context:
            context.prec = 80
            for name, (numerator, denominator, multiplier) in formulas.items():
                if self._sums[denominator] == 0:
                    continue
                value = self._sums[numerator] * multiplier / self._sums[denominator]
                result[name] = decimal_text(
                    value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                )
        # usage需要已核验的ad→creative→asset跨日去重映射，不由广告数/行数猜测。
        return result
