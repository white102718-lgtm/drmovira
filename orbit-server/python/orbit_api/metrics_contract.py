"""原监测查询与四种响应的严格合同；不把结构合法当作指标来源或覆盖证明。"""

import json
import re
import unicodedata
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError

from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput, pointer, schema_error

MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_COUNT = 2_147_483_647
MAX_BUSINESS_DAYS = 93
DECIMAL_PATTERN = r"^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$"
DecimalText = Annotated[str, Field(max_length=28, pattern=DECIMAL_PATTERN)]
MetricDataset = Literal[
    "ACCOUNT", "CAMPAIGN", "ADSET", "AD", "OPERATOR", "CHANNEL", "ASSET", "LAUNCH"
]
METRIC_NAMES = (
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
    "usage",
)


def invalid(parts, message="指标字段值不符合原合同"):
    raise OrbitError(422, "FIELD_VALIDATION_FAILED", message, pointer(parts))


class MetricQuery(StrictInput):
    date_from: str
    date_to: str
    dataset: MetricDataset
    metric_profile_id: str
    scope_snapshot_id: str | None
    channel_id: str | None = Field(min_length=1, max_length=64)
    operator_user_id: str | None
    q: str = Field(min_length=0, max_length=100)
    sort: Literal["spend", "impressions", "clicks", "purchases", "roas", "cpm", "name"]
    direction: Literal["ASC", "DESC"]
    cursor: str | None = Field(min_length=1, max_length=2048)
    page_size: Literal[20, 50, 100, 200]
    granularity: Literal["SUMMARY", "DAY"]

    @field_validator("page_size", mode="before")
    @classmethod
    def strict_page_size(cls, value):
        if type(value) is not int:
            raise PydanticCustomError("int_type", "分页数量必须为整数")
        return value

    @field_validator("dataset", "sort", "direction", "granularity", mode="before")
    @classmethod
    def strict_enumeration(cls, value):
        if not isinstance(value, str):
            raise PydanticCustomError("string_type", "枚举必须为字符串")
        return value

    @field_validator("q", mode="before")
    @classmethod
    def normalize_query(cls, value):
        # 用户短文本先NFC再计码点，不回显非法输入或把控制字符当搜索条件。
        if isinstance(value, str):
            value = unicodedata.normalize("NFC", value).strip()
            if any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value):
                invalid(("q",), "搜索条件不能包含换行或控制字符")
        return value

    @field_validator("channel_id", mode="before")
    @classmethod
    def normalize_channel(cls, value):
        if isinstance(value, str):
            value = unicodedata.normalize("NFC", value).strip()
            if any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value):
                invalid(("channel_id",), "渠道条件不能包含换行或控制字符")
        return value


class MetricValues(StrictInput):
    spend: DecimalText | None
    impressions: DecimalText | None
    clicks: DecimalText | None
    registrations: DecimalText | None
    purchases: DecimalText | None
    purchase_value: DecimalText | None
    roas: DecimalText | None
    cpm: DecimalText | None
    ctr: DecimalText | None
    cpc: DecimalText | None
    cpa: DecimalText | None
    usage: DecimalText | None


class MetricRow(StrictInput):
    tenant_id: str
    owner_team_id: str | None
    operator_user_id: str | None
    entity_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=0, max_length=255)
    channel_id: str | None
    product_name_snapshot: str | None = Field(min_length=1, max_length=100)
    currency: str = Field(min_length=3, max_length=3)
    metric_profile_id: str
    business_date: str | None
    account_count: int = Field(ge=0, le=MAX_COUNT)
    ad_count: int = Field(ge=0, le=MAX_COUNT)
    values: MetricValues
    quality: Literal["COMPLETE", "PARTIAL", "STALE", "UNKNOWN"]
    coverage: DecimalText

    @field_validator("quality", mode="before")
    @classmethod
    def strict_quality(cls, value):
        if not isinstance(value, str):
            raise PydanticCustomError("string_type", "质量必须为字符串枚举")
        return value


class MetricTotal(StrictInput):
    tenant_id: str
    currency: str = Field(min_length=3, max_length=3)
    metric_profile_id: str
    values: MetricValues
    account_count: int = Field(ge=0, le=MAX_COUNT)
    ad_count: int = Field(ge=0, le=MAX_COUNT)
    missing_count: int = Field(ge=0, le=MAX_COUNT)
    coverage: DecimalText


class Metrics(StrictInput):
    items: list[MetricRow] = Field(max_length=200)
    next_cursor: str | None = Field(min_length=1, max_length=2048)
    scope_version: int = Field(ge=1, le=MAX_SAFE_INTEGER)
    snapshot_id: str
    data_as_of: str
    missing_count: int = Field(ge=0, le=MAX_COUNT)
    query_snapshot_id: str
    totals: list[MetricTotal] = Field(max_length=1000)


def _uuid(value, parts):
    try:
        if str(UUID(value)) != value.lower():
            raise ValueError
        return value.lower()
    except (ValueError, AttributeError):
        invalid(parts, "需要带连字符的完整UUID")


def _day(value, parts):
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        invalid(parts, "日期必须为有效YYYY-MM-DD业务日")


def _timestamp(value, parts):
    try:
        if (
            re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})",
                value,
            )
            is None
        ):
            raise ValueError
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
    except ValueError:
        invalid(parts, "数据时刻必须为带时区的有效ISO时间")


def _parse(raw, model):
    """JSON重复键及NaN不被覆盖/转换；错误只携带固定说明和JSON Pointer。"""
    if not isinstance(raw, bytes):
        raise OrbitError(400, "INVALID_STRUCTURE", "指标正文必须为JSON字节", "/")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    def non_finite(_):
        raise ValueError

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=non_finite)
    except (ValueError, UnicodeError, RecursionError):
        raise OrbitError(400, "INVALID_STRUCTURE", "指标JSON结构无效", "/") from None
    try:
        return model.model_validate(value).model_dump()
    except ValidationError as error:
        failure = schema_error(error)
        # 规范Decimal的正则失败是值边界，不是JSON类型错误；不修改公共错误映射。
        if (
            error.errors(include_input=False, include_context=False)[0]["type"]
            == "string_pattern_mismatch"
        ):
            failure.status = 422
            failure.message = "指标数值必须为非负规范十进制字符串"
        if failure.status == 422:
            failure.code = "FIELD_VALIDATION_FAILED"
        raise failure from None


def validate_account_local_today(query, account_local_today):
    """只接受调用方提供的可信账户当地日；Store需对每个预期账户重验。"""
    if type(account_local_today) is not date:
        raise ValueError("account_local_today必须来自可信账户时区的date")
    if _day(query["date_to"], ("date_to",)) > account_local_today:
        invalid(("date_to",), "查询不能包含该账户当地的未来业务日")


def parse_metric_query(raw: bytes, *, account_local_today: date | None = None):
    value = _parse(raw, MetricQuery)
    start = _day(value["date_from"], ("date_from",))
    end = _day(value["date_to"], ("date_to",))
    if not 1 <= (end - start).days + 1 <= MAX_BUSINESS_DAYS:
        invalid(("date_to",), "查询必须包含1至93个业务日且结束日不早于开始日")
    for key in ("metric_profile_id", "scope_snapshot_id", "operator_user_id"):
        if value[key] is not None:
            value[key] = _uuid(value[key], (key,))
    # channel_id原输入是1—64文本，不擅自收紧成仅UUID或发明未知渠道哨兵。
    if account_local_today is not None:
        validate_account_local_today(value, account_local_today)
    return value


def _metrics(raw):
    value = _parse(raw, Metrics)
    for key in ("snapshot_id", "query_snapshot_id"):
        value[key] = _uuid(value[key], (key,))
    _timestamp(value["data_as_of"], ("data_as_of",))
    for collection in ("items", "totals"):
        for index, row in enumerate(value[collection]):
            prefix = (collection, index)
            keys = ("tenant_id", "metric_profile_id")
            if collection == "items":
                keys += ("owner_team_id", "operator_user_id", "channel_id")
                if row["business_date"] is not None:
                    _day(row["business_date"], (*prefix, "business_date"))
            for key in keys:
                if row[key] is not None:
                    row[key] = _uuid(row[key], (*prefix, key))
    # 这里只校验原DTO；覆盖率真值、totals全范围、比例/货币/来源计算仍由Store负责。
    return value


def parse_metrics(raw: bytes):
    """出站/受信持久值非法时拒绝整包发布；不把内部坏数据当作用户422。"""
    try:
        return _metrics(raw)
    except OrbitError:
        raise OrbitError(
            503, "METRICS_DATA_UNVERIFIED", "指标数据尚未完整核实，暂不可读取"
        ) from None
