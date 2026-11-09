"""账户18列技术补充合同；日期是账户当地消耗窗口，未知观测保持null。"""

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from orbit_api.configuration import short_text
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid

MODES = {
    "TODAY",
    "YESTERDAY",
    "LAST7",
    "LAST14",
    "LAST30",
    "THISWEEK",
    "LASTWEEK",
    "THISMONTH",
    "LASTMONTH",
    "MAX",
    "CUSTOM",
}
TEXT_FIELDS = {
    "personal_profile",
    "business_entity",
    "payment_type",
    "payment_method",
    "blocked_reason",
}
MONEY_FIELDS = {"balance", "payable", "lifetime_spend"}
SOURCES = {"META_GRAPH_METADATA", "AUTHORIZED_VENDOR", "LOCAL_AUDIT", "VERIFIED_INGESTION"}
STATUSES = {"SYNCED", "UNSYNCED", "FAILED", "UNKNOWN"}
REASONS = {"NOT_PROVIDED", "NOT_AUTHORIZED", "READ_FAILED", "STALE", "SOURCE_UNAVAILABLE"}


def invalid(pointer, message="账户补充字段无效"):
    raise OrbitError(422, "FIELD_INVALID", message, pointer)


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def day(value, pointer):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        invalid(pointer)
    try:
        return date.fromisoformat(value)
    except ValueError:
        invalid(pointer)


def timestamp(value, pointer):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})",
        value,
    ):
        invalid(pointer)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return iso(parsed)
    except (ValueError, OverflowError):
        invalid(pointer)


def amount(value, pointer):
    if (
        not isinstance(value, str)
        or len(value) > 28
        or not re.fullmatch(r"(0|[1-9][0-9]*)(\.[0-9]{1,6})?", value)
    ):
        invalid(pointer)
    try:
        parsed = Decimal(value)
        if parsed >= Decimal("1000000000000000000000"):
            invalid(pointer)
        return value
    except InvalidOperation:
        invalid(pointer)


def filters(params):
    result = {"page_size": 50, "q": "", "mode": params.get("mode", "TODAY")}
    if result["mode"] not in MODES:
        invalid("/mode")
    if params.get("page_size", "50") not in {"20", "50", "100", "200"}:
        invalid("/page_size")
    result["page_size"] = int(params.get("page_size", "50"))
    result["q"] = short_text(params.get("q", ""), 100, "/q", required=False)
    for key, target in (("operator_user_id", "owner_user_id"), ("vendor_id", "vendor_id")):
        if key in params:
            result[target] = _uuid(params[key], "/" + key)
    for key, accepted in (
        ("status", {"ACTIVE", "DISABLED", "UNKNOWN"}),
        ("auth_status", {"AUTHORIZED", "EXPIRED", "REVOKED", "UNKNOWN"}),
    ):
        if key in params:
            if params[key] not in accepted:
                invalid("/" + key)
            result["account_status" if key == "status" else key] = params[key]
    has_dates = "date_from" in params or "date_to" in params
    if has_dates and "mode" not in params:
        result["mode"] = "CUSTOM"
    if result["mode"] == "CUSTOM":
        start, end = (
            day(params.get("date_from"), "/date_from"),
            day(params.get("date_to"), "/date_to"),
        )
        if start > end or (end - start).days >= 3660:
            invalid("/date_to", "消耗日期范围须按顺序且不超过3660日")
        result.update(date_from=start.isoformat(), date_to=end.isoformat())
    elif has_dates:
        invalid("/mode", "快捷日期与自定义起止不能同时提交")
    return result


def window(query, timezone, reference, earliest=None):
    today = reference.astimezone(ZoneInfo(timezone)).date()
    mode = query["mode"]
    end = today
    if mode == "CUSTOM":
        return date.fromisoformat(query["date_from"]), date.fromisoformat(query["date_to"])
    if mode == "MAX":
        return earliest, today if earliest is not None else None
    if mode == "TODAY":
        start = today
    elif mode == "YESTERDAY":
        start = end = today - timedelta(days=1)
    elif mode.startswith("LAST") and mode[4:].isdigit():
        start = today - timedelta(days=int(mode[4:]) - 1)
    elif mode == "THISWEEK":
        start = today - timedelta(days=today.weekday())
    elif mode == "LASTWEEK":
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
    elif mode == "THISMONTH":
        start = today.replace(day=1)
    else:
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    return start, end


def text_observation(value, pointer):
    keys = {"value", "code", "status", "reason_code", "source", "observed_at"}
    if not isinstance(value, dict) or set(value) != keys:
        invalid(pointer)
    if (
        not isinstance(value["status"], str)
        or value["status"] not in STATUSES
        or not isinstance(value["source"], str)
        or value["source"] not in SOURCES
    ):
        invalid(pointer)
    for key, maximum in (("value", 2000), ("code", 64), ("reason_code", 64)):
        if value[key] is not None:
            if not isinstance(value[key], str):
                invalid(pointer + "/" + key)
            short_text(value[key], maximum, pointer + "/" + key, required=False)
    if value["reason_code"] is not None and value["reason_code"] not in REASONS:
        invalid(pointer + "/reason_code")
    result = dict(value)
    result["observed_at"] = (
        timestamp(value["observed_at"], pointer + "/observed_at")
        if value["observed_at"] is not None
        else None
    )
    if result["status"] == "SYNCED" and result["observed_at"] is None:
        invalid(pointer + "/observed_at")
    if result["status"] != "SYNCED" and result["value"] is not None:
        invalid(pointer + "/value")
    return result


def observed_fields(value, currency):
    """受控采集器写入白名单；不允许原始响应、Token和任意字段混入展示JSON。"""
    if not isinstance(value, dict) or not value or not set(value) <= TEXT_FIELDS | MONEY_FIELDS:
        invalid("/observations")
    result = {}
    for key, item in value.items():
        pointer = "/observations/" + key
        if key in TEXT_FIELDS:
            result[key] = text_observation(item, pointer)
            continue
        keys = {"amount", "currency", "kind", "status", "source", "business_date", "observed_at"}
        if not isinstance(item, dict) or set(item) != keys or item["currency"] != currency:
            invalid(pointer)
        allowed_kind = (
            {"UNKNOWN"} if key == "balance" else {"BILL"} if key == "payable" else {"SPEND"}
        )
        if (
            not isinstance(item["kind"], str)
            or item["kind"] not in allowed_kind
            or not isinstance(item["status"], str)
            or item["status"] not in STATUSES
            or not isinstance(item["source"], str)
            or item["source"] not in SOURCES
        ):
            invalid(pointer)
        result[key] = dict(item)
        if item["amount"] is not None:
            amount(item["amount"], pointer + "/amount")
            if item["status"] != "SYNCED":
                invalid(pointer + "/status")
        if item["business_date"] is not None:
            day(item["business_date"], pointer + "/business_date")
        result[key]["observed_at"] = (
            timestamp(item["observed_at"], pointer + "/observed_at")
            if item["observed_at"] is not None
            else None
        )
        if item["status"] == "SYNCED" and result[key]["observed_at"] is None:
            invalid(pointer + "/observed_at")
    return result


def fact_input(item, currency, timezone):
    """日事实只接受规范十进制与明确覆盖，不接受浏览器提供归属/租户/发布版本。"""
    keys = {
        "account_id",
        "business_date",
        "amount",
        "coverage",
        "currency",
        "source",
        "observed_at",
    }
    if not isinstance(item, dict) or set(item) != keys:
        invalid("/facts")
    identifier = _uuid(item["account_id"], "/facts/account_id")
    business_day = day(item["business_date"], "/facts/business_date")
    if (
        item["currency"] != currency
        or not isinstance(item["source"], str)
        or item["source"] not in {"META_INSIGHTS", "VERIFIED_INGESTION"}
    ):
        invalid("/facts/source")
    if not isinstance(item["coverage"], str) or item["coverage"] not in {"COMPLETE", "PARTIAL"}:
        invalid("/facts/coverage")
    if item["amount"] is not None:
        amount(item["amount"], "/facts/amount")
    if (item["coverage"] == "COMPLETE") != (item["amount"] is not None):
        invalid("/facts/amount")
    observed = datetime.fromisoformat(
        timestamp(item["observed_at"], "/facts/observed_at").replace("Z", "+00:00")
    )
    if observed > datetime.now(UTC) + timedelta(minutes=5):
        invalid("/facts/observed_at", "未来观测时刻不能发布为已取得事实")
    if business_day > observed.astimezone(ZoneInfo(timezone)).date():
        invalid("/facts/business_date", "不能将观测时刻之后的账户业务日标为已观测")
    return item | {
        "account_id": identifier,
        "business_date": business_day,
        "observed_at": observed.replace(tzinfo=None),
    }


def fact_interval(business_day, timezone, observed_at):
    """日粒度观测只覆盖本地零点至观测时刻/次日零点；DST日不可固定加24小时UTC。"""
    local_start = datetime.combine(business_day, datetime.min.time(), ZoneInfo(timezone))
    local_end = datetime.combine(
        business_day + timedelta(days=1), datetime.min.time(), ZoneInfo(timezone)
    )
    start = local_start.astimezone(UTC).replace(tzinfo=None)
    end = min(local_end.astimezone(UTC).replace(tzinfo=None), observed_at)
    return start, end


def freeze_attribution(start, end, assignments, previous=None):
    """普通补采只复制首次冻结归属；改归属须独立双人历史更正，不能借采集器实施。"""
    fields = ("owner_user_id", "owner_team_id", "attribution_version", "attribution_reason")
    if previous is not None:
        return {key: previous[key] for key in fields}
    unknown = {
        "owner_user_id": None,
        "owner_team_id": None,
        "attribution_version": 1,
        "attribution_reason": "UNASSIGNED_NO_COVERAGE",
    }
    if end <= start:
        return unknown | {"attribution_reason": "UNASSIGNED_EMPTY_WINDOW"}
    overlapping = [
        a
        for a in assignments
        if a["starts_at"] < end and (a["ends_at"] is None or a["ends_at"] > start)
    ]
    if len(overlapping) != 1:
        return unknown | {
            "attribution_reason": "UNASSIGNED_AMBIGUOUS"
            if overlapping
            else "UNASSIGNED_NO_COVERAGE"
        }
    assignment = overlapping[0]
    if assignment["starts_at"] > start or (
        assignment["ends_at"] is not None and assignment["ends_at"] < end
    ):
        return unknown | {"attribution_reason": "UNASSIGNED_PARTIAL_WINDOW"}
    return {
        "owner_user_id": assignment["owner_user_id"],
        "owner_team_id": assignment["owner_team_id"],
        "attribution_version": 1,
        "attribution_reason": "COVERED",
    }
