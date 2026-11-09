"""原分配、同步、本地解绑写入合同；不把排队回执冒充已执行。"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from orbit_api.account_details_contract import timestamp
from orbit_api.account_identities_store import identifier
from orbit_api.configuration import _parse_json, short_text
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.errors import OrbitError

MAX_BODY = 16384


@dataclass(frozen=True)
class Assignment:
    operator_user_id: str
    owner_team_id: str
    vendor_id: str | None
    effective_from: str
    reason: str


def invalid(pointer):
    raise OrbitError(422, "FIELD_INVALID", "账户动作字段不符合原合同", pointer)


def body(raw):
    if len(raw) > MAX_BODY:
        raise OrbitError(413, "BODY_TOO_LARGE", "账户动作请求超过正文上限")
    value = _parse_json(raw)
    if not isinstance(value, dict):
        invalid("/")
    return value


def reason(value):
    if not isinstance(value, str):
        invalid("/reason")
    return short_text(value, 1000, "/reason")


def parse_reason(raw):
    value = body(raw)
    if set(value) != {"reason"}:
        invalid("/")
    return reason(value["reason"])


def parse_assignment(raw):
    value = body(raw)
    if set(value) != {
        "operator_user_id",
        "owner_team_id",
        "vendor_id",
        "effective_from",
        "reason",
    }:
        invalid("/")
    effective = timestamp(value["effective_from"], "/effective_from")
    raw_effective = datetime.fromisoformat(value["effective_from"].replace("Z", "+00:00"))
    if raw_effective.microsecond % 1000:
        # 精确零点不能把额外微秒截断后“修成”合法输入。
        effective = (
            raw_effective.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        )
    return Assignment(
        identifier(value["operator_user_id"], "/operator_user_id"),
        identifier(value["owner_team_id"], "/owner_team_id"),
        identifier(value["vendor_id"], "/vendor_id") if value["vendor_id"] is not None else None,
        effective,
        reason(value["reason"]),
    )


def next_business_midnight(timezone_id, now):
    """下一账户当地日零点；遇不存在的墙钟时刻明确拒绝，不猜固定UTC偏移。"""
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("当地日边界必须使用带时区的可信参考时刻")
    try:
        zone = ZoneInfo(timezone_id)
        local = now.astimezone(zone)
        desired = datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=zone)
        instant = desired.astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) != desired.replace(tzinfo=None):
            raise OrbitError(
                422, "BUSINESS_MIDNIGHT_UNAVAILABLE", "下一当地日零点不存在，需核验账户时区边界"
            )
        return instant
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise OrbitError(422, "ACCOUNT_TIMEZONE_INVALID", "账户时区未验证") from None


def validate_effective(value, timezone_id, now):
    expected = next_business_midnight(timezone_id, now)
    instant = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    if instant != expected:
        raise OrbitError(
            422,
            "ASSIGNMENT_EFFECTIVE_INVALID",
            "分配必须在账户当地下一业务日零点生效",
            "/effective_from",
        )
    return expected


def write_headers(headers):
    tokens, keys, revisions = (
        headers.getlist("x-csrf-token"),
        headers.getlist("idempotency-key"),
        headers.getlist("if-match"),
    )
    if len(tokens) != 1 or not 16 <= len(tokens[0]) <= 255:
        raise OrbitError(403, "CSRF_INVALID", "账户动作需要唯一有效会话校验")
    if (
        len(keys) != 1
        or not 16 <= len(keys[0]) <= 128
        or not all(" " <= char <= "~" for char in keys[0])
    ):
        raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "账户动作需要16至128位ASCII幂等键")
    if len(revisions) != 1 or not re.fullmatch(r'"[1-9][0-9]{0,15}"', revisions[0]):
        raise OrbitError(400, "REVISION_REQUIRED", "账户动作需要带双引号的If-Match版本")
    revision = int(revisions[0][1:-1])
    if revision > MAX_REVISION:
        invalid("/revision")
    return tokens[0], keys[0], revision
