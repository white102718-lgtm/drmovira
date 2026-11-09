"""规则原合同纯DTO；结构合法不代表范围、指标来源或模拟资格已经核验。"""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationError

from orbit_api.configuration import _parse_json
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput, pointer

MAX_SAFE = 9007199254740991
Metric = Literal[
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
]
Logic = Literal["AND", "OR"]
COUNTS = frozenset({"impressions", "clicks", "registrations", "purchases"})
MONEY_METRICS = frozenset({"spend", "purchase_value", "cpm", "cpc", "cpa"})
DECIMAL_TEXT = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]{1,6})?", re.ASCII)


def invalid(path, message="规则字段值不符合原合同"):
    raise OrbitError(422, "FIELD_VALIDATION_FAILED", message, path)


class RuleOwnership(StrictInput):
    owner_user_id: str
    owner_team_id: str


class Condition(StrictInput):
    metric: Metric
    operator: Literal["GT", "GTE", "LT", "LTE", "EQ", "NEQ"]
    threshold: str = Field(min_length=1, max_length=28)


class ConditionGroup(StrictInput):
    logic: Logic
    conditions: list[Condition] = Field(min_length=1, max_length=10)


class Schedule(StrictInput):
    frequency: Literal["INTERVAL", "DAILY", "WEEKLY"]
    interval_minutes: int | None = Field(ge=15, le=1440)
    time_of_day: str | None
    weekday: int | None = Field(ge=1, le=7)
    timezone: str = Field(min_length=1, max_length=64)
    start_date: str
    end_date: str


class RuleWrite(StrictInput):
    name: str
    ownership: RuleOwnership
    target_level: Literal["CAMPAIGN", "ADSET", "AD"]
    scope_snapshot_id: str
    logic: Logic
    groups: list[ConditionGroup] = Field(min_length=1, max_length=5)
    window: Literal["TODAY", "YESTERDAY", "LAST_3D", "LAST_7D"]
    metric_profile_id: str
    schedule: Schedule
    cooldown_minutes: int = Field(ge=0, le=10080)
    max_daily: int = Field(ge=1, le=1000)


class Rule(RuleWrite):
    id: str
    revision: int = Field(ge=1, le=MAX_SAFE)
    state: Literal["DRAFT", "ENABLED", "PAUSED", "ARCHIVED"]
    next_run_at: str | None


class ConditionResult(StrictInput):
    entity_id: str
    condition_index: int = Field(ge=0, le=2147483647)
    value: str | None
    result: Literal["TRUE", "FALSE", "UNKNOWN"]
    reason_code: str | None = Field(min_length=1, max_length=64)


class Simulation(StrictInput):
    id: str
    rule_id: str
    revision: int = Field(ge=1, le=MAX_SAFE)
    snapshot_id: str
    hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    account_count: int = Field(ge=0, le=2147483647)
    scanned_count: int = Field(ge=0, le=2147483647)
    hit_count: int = Field(ge=0, le=2147483647)
    unknown_count: int = Field(ge=0, le=2147483647)
    false_count: int = Field(ge=0, le=2147483647)
    conditions: list[ConditionResult] = Field(max_length=10000)
    expires_at: str
    next_cursor: str | None = Field(min_length=1, max_length=2048)


class RuleRun(StrictInput):
    id: str
    rule_id: str
    rule_revision: int = Field(ge=1, le=MAX_SAFE)
    schedule_slot: str
    snapshot_id: str
    state: Literal["RUNNING", "SUCCEEDED", "SKIPPED", "UNKNOWN", "FAILED"]
    hit_count: int = Field(ge=0, le=2147483647)
    reason_code: str | None = Field(min_length=1, max_length=64)


class RulePage(StrictInput):
    items: list[Rule] = Field(max_length=200)
    next_cursor: str | None = Field(min_length=1, max_length=2048)
    data_as_of: str
    scope_version: int = Field(ge=1, le=MAX_SAFE)


class RuleRunPage(StrictInput):
    items: list[RuleRun] = Field(max_length=200)
    next_cursor: str | None = Field(min_length=1, max_length=2048)
    data_as_of: str
    scope_version: int = Field(ge=1, le=MAX_SAFE)


class EnableRule(StrictInput):
    simulation_id: str


class RuleReason(StrictInput):
    reason: str = Field(min_length=1, max_length=1000)


def _schema(model, value, base=""):
    try:
        return model.model_validate(value)
    except ValidationError as error:
        item = error.errors(include_input=False, include_context=False)[0]
        path = base + pointer(item["loc"])
        if item["type"] == "extra_forbidden":
            raise OrbitError(400, "UNKNOWN_FIELD", "请求包含未知字段", path) from None
        structural = item["type"] in {
            "missing",
            "string_type",
            "int_type",
            "list_type",
            "model_type",
            "bool_type",
        }
        if item["type"] == "literal_error":
            supplied = value
            for key in item["loc"]:
                supplied = supplied[key]
            structural = not isinstance(supplied, str)
        raise OrbitError(
            400 if structural else 422,
            "INVALID_STRUCTURE" if structural else "FIELD_VALIDATION_FAILED",
            "字段缺失或类型无效" if structural else "字段值或数量超出范围",
            path,
        ) from None


def identifier(value, path):
    try:
        if str(UUID(value)) != value.lower():
            raise ValueError
        return value.lower()
    except (ValueError, TypeError, AttributeError):
        invalid(path, "请输入完整业务UUID")


def _text(value, path, maximum, *, trim=False):
    # 先拒控制字符再trim，不能把末尾换行吞掉放行。
    if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} or c in "\u2028\u2029" for c in value):
        invalid(path)
    value = unicodedata.normalize("NFC", value.strip() if trim else value)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        invalid(path)
    if not 1 <= len(value) <= maximum or any(unicodedata.category(c) == "Cc" for c in value):
        invalid(path)
    return value


def threshold_value(condition, path):
    text = condition.threshold
    if len(text) > 28 or DECIMAL_TEXT.fullmatch(text) is None:
        invalid(path)
    value = Decimal(text)
    if condition.metric in COUNTS and value != value.to_integral_value():
        invalid(path, "计数阈值必须是整数")
    maximum = (
        Decimal("1000000000")
        if condition.metric in MONEY_METRICS
        else Decimal("1000000")
        if condition.metric == "roas"
        else Decimal("100")
        if condition.metric == "ctr"
        else None
    )
    if maximum is not None and value > maximum:
        invalid(path, "指标阈值超出范围")
    return value


def parse_schedule(value, path="/schedule"):
    schedule = _schema(Schedule, value, path)
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", schedule.start_date):
            invalid(path + "/start_date")
        start = date.fromisoformat(schedule.start_date)
    except ValueError:
        invalid(path + "/start_date")
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", schedule.end_date):
            invalid(path + "/end_date")
        end = date.fromisoformat(schedule.end_date)
    except ValueError:
        invalid(path + "/end_date")
    if not 0 <= (end - start).days < 366:
        invalid(path + "/end_date", "含首尾日期最多366天")
    try:
        if schedule.timezone.startswith(("/", ".")):
            raise ValueError
        ZoneInfo(schedule.timezone)
    except (ZoneInfoNotFoundError, ValueError, UnicodeError):
        invalid(path + "/timezone", "请选择有效IANA时区")
    interval = schedule.frequency == "INTERVAL"
    if interval != (schedule.interval_minutes is not None):
        invalid(path + "/interval_minutes")
    if interval:
        if schedule.time_of_day is not None:
            invalid(path + "/time_of_day")
    elif schedule.time_of_day is None or not re.fullmatch(
        r"([01][0-9]|2[0-3]):[0-5][0-9]", schedule.time_of_day
    ):
        invalid(path + "/time_of_day")
    if (schedule.frequency == "WEEKLY") != (schedule.weekday is not None):
        invalid(path + "/weekday")
    return schedule


def _write(value, path=""):
    value.name = _text(value.name, path + "/name", 80, trim=True)
    for field in ("owner_user_id", "owner_team_id"):
        setattr(
            value.ownership,
            field,
            identifier(getattr(value.ownership, field), path + "/ownership/" + field),
        )
    for field in ("scope_snapshot_id", "metric_profile_id"):
        setattr(value, field, identifier(getattr(value, field), path + "/" + field))
    if sum(len(group.conditions) for group in value.groups) > 20:
        invalid(path + "/groups", "全部条件不得超过20条")
    for gi, group in enumerate(value.groups):
        for ci, condition in enumerate(group.conditions):
            threshold_value(condition, f"{path}/groups/{gi}/conditions/{ci}/threshold")
    value.schedule = parse_schedule(value.schedule.model_dump(), path + "/schedule")
    return value


def parse_rule_write(raw: bytes):
    return _write(_schema(RuleWrite, _parse_json(raw)))


def parse_rule_action(kind, raw: bytes):
    if kind not in {"ENABLE", "PAUSE", "ARCHIVE"}:
        raise ValueError("未定义的规则动作")
    value = _schema(EnableRule if kind == "ENABLE" else RuleReason, _parse_json(raw))
    if kind == "ENABLE":
        value.simulation_id = identifier(value.simulation_id, "/simulation_id")
    else:
        value.reason = _text(value.reason, "/reason", 1000, trim=True)
    return value


def _utc(value, path):
    try:
        if not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]+)?(?:Z|\+00:00)",
            value,
        ):
            raise ValueError
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError
    except (ValueError, OverflowError):
        invalid(path, "时间必须是UTC date-time")


def parse_rule_response(model, value, *, path=""):
    """边界适配器核完整原DTO；不生成成功对象、不从缺失事实补零。"""
    if model not in {Rule, Simulation, ConditionResult, RuleRun, RulePage, RuleRunPage}:
        raise ValueError("未定义的规则响应")
    result = _schema(model, value, path)
    if hasattr(result, "next_cursor") and result.next_cursor is not None:
        # 不静默trim不透明游标。
        _text(result.next_cursor, path + "/next_cursor", 2048)
    if isinstance(result, (RulePage, RuleRunPage)):
        _utc(result.data_as_of, path + "/data_as_of")
        for index, row in enumerate(result.items):
            result.items[index] = parse_rule_response(
                Rule if isinstance(row, Rule) else RuleRun,
                row.model_dump(),
                path=f"{path}/items/{index}",
            )
        return result
    for field in ("id", "rule_id", "snapshot_id", "entity_id"):
        if hasattr(result, field):
            setattr(result, field, identifier(getattr(result, field), path + "/" + field))
    if isinstance(result, Rule):
        _write(result, path)
        if result.next_run_at is not None:
            _utc(result.next_run_at, path + "/next_run_at")
    if isinstance(result, Simulation):
        if result.hit_count + result.false_count + result.unknown_count != result.scanned_count:
            invalid(path + "/scanned_count")
        _utc(result.expires_at, path + "/expires_at")
        for index, row in enumerate(result.conditions):
            result.conditions[index] = parse_rule_response(
                ConditionResult,
                row.model_dump(),
                path=f"{path}/conditions/{index}",
            )
    if isinstance(result, ConditionResult) and result.value is not None:
        if len(result.value) > 28 or DECIMAL_TEXT.fullmatch(result.value) is None:
            invalid(path + "/value")
    if isinstance(result, RuleRun):
        _utc(result.schedule_slot, path + "/schedule_slot")
    if hasattr(result, "reason_code") and result.reason_code is not None:
        result.reason_code = _text(result.reason_code, path + "/reason_code", 64)
    return result
