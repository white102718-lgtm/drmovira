"""完整原Metrics的纯结果投影；不发行、不授予来源权威、不加载全量排序集。"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal, localcontext

from pydantic import ValidationError

from orbit_api.directory_tokens import canonical
from orbit_api.metrics_aggregation import (
    CRITICAL_NAMES,
    MetricAccumulator,
    MetricGroup,
    decimal_text,
)
from orbit_api.metrics_contract import MAX_COUNT, MetricRow, MetricTotal, parse_metrics
from orbit_api.metrics_query_result_contract import (
    RESULT_DATASETS,
    QuerySourceIdentity,
    strict_day,
    strict_integer,
    strict_uuid,
    strict_version,
    unverified,
)

RESULT_ALGORITHM_VERSION = "orbit-metric-result-v1-coverage6-down-ratios6-half-up-stale-null"
SORT_FIELDS = ("spend", "impressions", "clicks", "purchases", "roas", "cpm", "name")
DISPLAY_NULLABLE = ("owner_team_id", "operator_user_id", "channel_id", "product_name_snapshot")


def utc(value):
    """SQL列声明UTC；naive仅在此显式附UTC，不以系统本地时区猜日期。"""
    if type(value) is not datetime:
        unverified()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    if value.utcoffset() is None:
        unverified()
    return value.astimezone(UTC)


@dataclass(frozen=True, repr=False)
class ResultGroupKey:
    tenant_id: str
    dataset: str
    entity_id: str
    currency: str
    profile_id: str
    profile_version: str
    business_date: date | None

    def __post_init__(self):
        for value in (self.tenant_id, self.entity_id, self.profile_id):
            strict_uuid(value)
        if type(self.dataset) is not str or self.dataset not in RESULT_DATASETS:
            unverified()
        if type(self.currency) is not str or len(self.currency) != 3:
            unverified()
        strict_version(self.profile_version)
        if self.business_date is not None:
            strict_day(self.business_date)

    def metric_group(self):
        return MetricGroup(self.tenant_id, self.currency, self.profile_id, self.profile_version)

    def stable_key(self):
        return (
            self.entity_id,
            self.currency,
            self.business_date.isoformat() if self.business_date else "",
        )


@dataclass(frozen=True, repr=False)
class DisplayContribution:
    """来自本组真实历史快照，不从当前目录补名或把snapshot ID当entity ID。"""

    entity_id: str
    name: str
    business_date: date
    capture_sequence: int
    observed_at: datetime
    snapshot_id: str
    owner_team_id: str | None
    operator_user_id: str | None
    channel_id: str | None
    product_name_snapshot: str | None

    def __post_init__(self):
        strict_uuid(self.entity_id)
        strict_uuid(self.snapshot_id)
        strict_day(self.business_date)
        strict_integer(self.capture_sequence, minimum=1)
        utc(self.observed_at)
        if type(self.name) is not str or len(self.name) > 10000:
            unverified()
        for value in (self.owner_team_id, self.operator_user_id, self.channel_id):
            if value is not None:
                strict_uuid(value)
        if self.product_name_snapshot is not None and (
            type(self.product_name_snapshot) is not str
            or not 1 <= len(self.product_name_snapshot) <= 100
        ):
            unverified()
        try:
            self.name.encode("utf-8")
            if self.product_name_snapshot is not None:
                self.product_name_snapshot.encode("utf-8")
        except UnicodeError:
            unverified()

    def rank(self):
        return (self.business_date, self.capture_sequence, utc(self.observed_at), self.snapshot_id)


class DisplayReducer:
    """常量内存元数据投影；nullable冲突变NULL，名称按真实版本排序。"""

    def __init__(self, group):
        if type(group) is not ResultGroupKey:
            unverified()
        self.group = group
        self._seen = False
        self._values = {}
        self._mixed = set()
        self._latest = None

    def add(self, item):
        if type(item) is not DisplayContribution or item.entity_id != self.group.entity_id:
            unverified()
        if self.group.business_date is not None and item.business_date != self.group.business_date:
            unverified()
        if (
            self._latest is not None
            and item.rank() == self._latest.rank()
            and item.name != self._latest.name
        ):
            unverified()
        if not self._seen:
            self._values = {name: getattr(item, name) for name in DISPLAY_NULLABLE}
        else:
            for name in DISPLAY_NULLABLE:
                if self._values[name] != getattr(item, name):
                    self._mixed.add(name)
        if self._latest is None or item.rank() > self._latest.rank():
            self._latest = item
        self._seen = True

    def finish(self):
        if not self._seen or len(self._latest.name) > 255:
            unverified()
        return {
            name: None if name in self._mixed else self._values[name] for name in DISPLAY_NULLABLE
        } | {"name": self._latest.name}


@dataclass(frozen=True)
class QualityDecision:
    quality: str
    coverage: str
    missing_count: int
    ratios_allowed: bool
    oldest_observed_at: datetime | None


def coverage_text(complete, expected):
    strict_integer(complete)
    strict_integer(expected)
    if complete > expected:
        unverified()
    if expected == 0:
        return "0"
    with localcontext() as context:
        context.prec = 80
        ratio = (Decimal(complete) / Decimal(expected)).quantize(
            Decimal("0.000001"), rounding=ROUND_DOWN
        )
        return decimal_text(ratio)


class CoverageAccumulator:
    """计数来自独立完整预期流/SQL去重；不能用事实行数调用此方法猜分母。"""

    def __init__(self):
        self.expected = 0
        self.complete = 0
        self._critical_missing = False
        self._oldest = None

    def add_unit(self, *, complete, critical_complete, observed_at):
        if type(complete) is not bool or type(critical_complete) is not bool:
            unverified()
        if complete and critical_complete and observed_at is None:
            unverified()
        observed = utc(observed_at) if observed_at is not None else None
        strict_integer(self.expected + 1)
        self.expected += 1
        if complete:
            self.complete += 1
        if not complete or not critical_complete:
            self._critical_missing = True
        if observed is not None and (self._oldest is None or observed < self._oldest):
            self._oldest = observed

    def finish(self, now):
        now = utc(now)
        if self._oldest is not None and self._oldest > now:
            unverified()
        missing = strict_integer(self.expected - self.complete, maximum=MAX_COUNT)
        coverage = coverage_text(self.complete, self.expected)
        if self.expected == 0 or self.complete == 0:
            quality = "UNKNOWN"
        elif missing or self._critical_missing:
            quality = "PARTIAL"
        elif self._oldest is None:
            unverified()
        elif now - self._oldest > timedelta(minutes=30):
            quality = "STALE"
        else:
            quality = "COMPLETE"
        return QualityDecision(quality, coverage, missing, quality == "COMPLETE", self._oldest)


def validate_outbound(model, value):
    try:
        result = model.model_validate(value).model_dump()
        for field in ("tenant_id", "metric_profile_id"):
            strict_uuid(result[field])
        if model is MetricRow:
            for field in ("owner_team_id", "operator_user_id", "channel_id"):
                if result[field] is not None:
                    strict_uuid(result[field])
            day = result["business_date"]
            if day is not None:
                parsed = date.fromisoformat(day)
                if parsed.isoformat() != day:
                    unverified()
        return result
    except (ValidationError, ValueError, TypeError):
        unverified()


class MetricResultRow:
    """单已排序组的常量内存投影；全量排序/去重由SQL staging负责。"""

    def __init__(self, group):
        if type(group) is not ResultGroupKey:
            unverified()
        self.group = group
        self.display = DisplayReducer(group)
        self.coverage = CoverageAccumulator()
        self._values = MetricAccumulator(group.metric_group())
        self._value_rows = 0

    def add_values(self, source_group, values):
        self._values.add(source_group, values)
        self._value_rows += 1

    def finish(self, *, now, account_count, ad_count):
        strict_integer(account_count, maximum=MAX_COUNT)
        strict_integer(ad_count, maximum=MAX_COUNT)
        decision = self.coverage.finish(now)
        if self.coverage.expected == 0 and self._value_rows:
            unverified()
        values = self._values.finish(ratios_allowed=False)
        quality = decision.quality
        if quality in {"COMPLETE", "STALE"} and any(
            values[name] is None for name in CRITICAL_NAMES
        ):
            quality = "PARTIAL"
        values = self._values.finish(ratios_allowed=quality == "COMPLETE")
        group = self.group
        result = {
            "tenant_id": group.tenant_id,
            **self.display.finish(),
            "entity_id": group.entity_id,
            "currency": group.currency,
            "metric_profile_id": group.profile_id,
            "business_date": group.business_date.isoformat() if group.business_date else None,
            "account_count": account_count,
            "ad_count": ad_count,
            "values": values,
            "quality": quality,
            "coverage": decision.coverage,
        }
        return validate_outbound(MetricRow, result)


class MetricResultTotal:
    """完整筛选范围的独立currency/profile总计，不累加页面或重复元数据组。"""

    def __init__(self, group):
        if type(group) is not MetricGroup:
            unverified()
        self.group = group
        self.coverage = CoverageAccumulator()
        self._values = MetricAccumulator(group)
        self._value_rows = 0

    def add_values(self, source_group, values):
        self._values.add(source_group, values)
        self._value_rows += 1

    def finish(self, *, now, account_count, ad_count):
        strict_integer(account_count, maximum=MAX_COUNT)
        strict_integer(ad_count, maximum=MAX_COUNT)
        decision = self.coverage.finish(now)
        if self.coverage.expected == 0 and self._value_rows:
            unverified()
        values = self._values.finish(ratios_allowed=decision.ratios_allowed)
        return validate_outbound(
            MetricTotal,
            {
                "tenant_id": self.group.tenant_id,
                "currency": self.group.currency,
                "metric_profile_id": self.group.profile_id,
                "values": values,
                "account_count": account_count,
                "ad_count": ad_count,
                "missing_count": decision.missing_count,
                "coverage": decision.coverage,
            },
        )


def compare_metric_rows(left, right, *, sort, direction):
    """全局SQL排序的纯参考比较器；不加载/排序无限结果集。"""
    if (
        type(sort) is not str
        or sort not in SORT_FIELDS
        or type(direction) is not str
        or direction not in {"ASC", "DESC"}
    ):
        unverified()
    left = validate_outbound(MetricRow, left)
    right = validate_outbound(MetricRow, right)
    a = left["name"] if sort == "name" else left["values"][sort]
    b = right["name"] if sort == "name" else right["values"][sort]
    if (a is None) != (b is None):
        return 1 if a is None else -1
    if a is not None:
        try:
            a = a.encode("utf-8") if sort == "name" else Decimal(a)
            b = b.encode("utf-8") if sort == "name" else Decimal(b)
        except (ValueError, TypeError, UnicodeError):
            unverified()
        if a != b:
            result = -1 if a < b else 1
            return result if direction == "ASC" else -result

    def key(item):
        return (item["entity_id"], item["currency"], item["business_date"] or "")

    return (key(left) > key(right)) - (key(left) < key(right))


def metrics_page(
    *,
    source,
    query_snapshot_id,
    scope_version,
    data_as_of,
    missing_count,
    items,
    totals,
    next_cursor,
    page_size,
):
    if type(source) is not QuerySourceIdentity:
        unverified()
    strict_uuid(query_snapshot_id)
    strict_integer(scope_version, minimum=1)
    strict_integer(missing_count, maximum=MAX_COUNT)
    if type(page_size) is not int or page_size not in (20, 50, 100, 200):
        unverified()
    if type(items) not in (tuple, list) or len(items) > page_size:
        unverified()
    if type(totals) not in (tuple, list) or len(totals) > 1000:
        unverified()
    seen_totals = set()
    total_missing = 0
    rows = [validate_outbound(MetricRow, item) for item in items]
    summaries = [validate_outbound(MetricTotal, total) for total in totals]
    for item in rows + summaries:
        if item["tenant_id"] != source.tenant_id or item["metric_profile_id"] != source.profile_id:
            unverified()
    seen_rows = set()
    for item in rows:
        key = (item["entity_id"], item["currency"], item["business_date"])
        if key in seen_rows:
            unverified()
        seen_rows.add(key)
    for total in summaries:
        key = (total["currency"], total["metric_profile_id"])
        if key in seen_totals:
            unverified()
        seen_totals.add(key)
        total_missing += total["missing_count"]
    if total_missing != missing_count or any(
        (item["currency"], item["metric_profile_id"]) not in seen_totals for item in rows
    ):
        unverified()
    payload = {
        "items": rows,
        "next_cursor": next_cursor,
        "scope_version": scope_version,
        "snapshot_id": source.publication_id,
        "data_as_of": utc(data_as_of).isoformat(),
        "missing_count": missing_count,
        "query_snapshot_id": query_snapshot_id,
        "totals": summaries,
    }
    try:
        return parse_metrics(canonical(payload).encode())
    except (UnicodeError, ValueError, TypeError):
        unverified()
