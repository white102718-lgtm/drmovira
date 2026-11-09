"""执行机登记严格原合同；端点只作登记数据，控制面绝不探测用户回环地址。"""

import re
from datetime import UTC, datetime

from pydantic import Field, ValidationError

from orbit_api.configuration import _parse_json, short_text
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput, schema_error

STATES = frozenset({"READY", "SUSPECT", "OFFLINE", "REVOKED"})
DEFAULT_ALLOWED_PORTS = frozenset({50325})


class AgentWrite(StrictInput):
    name: str = Field(min_length=1, max_length=80)
    endpoint: str = Field(min_length=1, max_length=255)
    probe_interval: int = Field(ge=10, le=300)


class AgentRevoke(StrictInput):
    reason: str = Field(min_length=1, max_length=1000)


def agent_endpoint(value, *, allowed_ports=DEFAULT_ALLOWED_PORTS):
    """与本地适配器同一严格白名单；独立纯解析，不导入本地HTTP客户端到控制面。"""
    match = re.fullmatch(r"http://(?:127\.0\.0\.1|localhost):([1-9][0-9]{0,4})/?", value)
    if match is None or int(match[1]) > 65535 or int(match[1]) not in allowed_ports:
        raise OrbitError(
            422,
            "FIELD_VALIDATION_FAILED",
            "执行机地址仅允许localhost/127.0.0.1及已允许端口",
            "/endpoint",
        )
    return f"http://127.0.0.1:{int(match[1])}"


def parse_agent(raw, mode="save", *, allowed_ports=DEFAULT_ALLOWED_PORTS):
    """不接收归属扩展、密钥、证书、客户端状态或伪造心跳字段。"""
    if mode not in {"save", "revoke"}:
        raise ValueError("未知执行机写入模式")
    try:
        value = (
            (AgentWrite if mode == "save" else AgentRevoke)
            .model_validate(_parse_json(raw))
            .model_dump()
        )
    except ValidationError as error:
        raise schema_error(error) from None
    if mode == "revoke":
        value["reason"] = short_text(value["reason"], 1000, "/reason")
        return value
    value["name"] = short_text(value["name"], 80, "/name")
    value["endpoint"] = agent_endpoint(value["endpoint"], allowed_ports=allowed_ports)
    return value


def heartbeat_state(*, revoked, received_at, now):
    """只接受控制面已可信记录的接收时刻；不使用客户端observed_at或本地/status成功。"""
    if revoked:
        return "REVOKED"
    if received_at is None:
        return "OFFLINE"
    if (
        not isinstance(now, datetime)
        or not isinstance(received_at, datetime)
        or now.tzinfo is None
        or received_at.tzinfo is None
        or received_at > now
    ):
        raise ValueError("心跳状态仅由有效服务端接收时刻计算")
    elapsed = (now - received_at).total_seconds()
    return "OFFLINE" if elapsed >= 90 else "SUSPECT" if elapsed >= 45 else "READY"


def public_agent(row):
    """保持原Agent七字段；内部权限/证书元数据不能通过行合并泄露。"""
    heartbeat = row["last_heartbeat"]
    if isinstance(heartbeat, datetime):
        heartbeat = heartbeat.replace(tzinfo=UTC) if heartbeat.tzinfo is None else heartbeat
        heartbeat = heartbeat.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return {
        "name": row["name"],
        "endpoint": row["endpoint"],
        "probe_interval": row["probe_interval"],
        "id": row["id"],
        "revision": row["revision"],
        "state": row["state"],
        "last_heartbeat": heartbeat,
    }


LIST_FIELDS = frozenset(
    {
        "q",
        "cursor",
        "page_size",
        "status",
        "date_from",
        "date_to",
        "operator_user_id",
        "channel_id",
        "metric_profile_id",
        "entity_type",
    }
)


def parse_agent_filters(values):
    """登记日期按北京时间端点包含，转换为UTC半开区间；未支持关联不能静默丢弃。"""
    from datetime import date, time, timedelta
    from zoneinfo import ZoneInfo

    from orbit_api.reference_contract import uuid_value

    if set(values) - LIST_FIELDS:
        raise OrbitError(400, "UNKNOWN_FIELD", "未知设备筛选字段")
    result = {"q": short_text(values.get("q", ""), 100, "/q", required=False), "page_size": 50}
    size = values.get("page_size", "50")
    if size not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_INVALID", "每页数量必须为20/50/100/200", "/page_size")
    result["page_size"] = int(size)
    if "status" in values:
        if values["status"] not in STATES:
            raise OrbitError(422, "FIELD_INVALID", "设备状态无效", "/status")
        result["status"] = values["status"]
    dates = {}
    for field in ("date_from", "date_to"):
        if field in values:
            try:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", values[field]):
                    raise ValueError
                dates[field] = date.fromisoformat(values[field])
                boundary = dates[field] + timedelta(days=field == "date_to")
                result[field] = (
                    datetime.combine(boundary, time(), ZoneInfo("Asia/Shanghai"))
                    .astimezone(UTC)
                    .strftime("%Y-%m-%d %H:%M:%S")
                )
            except (ValueError, OverflowError):
                raise OrbitError(422, "FIELD_INVALID", "登记日期无效", "/" + field) from None
    if dates.get("date_from", date.min) > dates.get("date_to", date.max):
        raise OrbitError(422, "FIELD_INVALID", "开始日期不能晚于结束日期", "/date_from")
    for field in ("operator_user_id", "metric_profile_id"):
        if field in values:
            result[field] = uuid_value(values[field], "/" + field)
    if "channel_id" in values:
        result["channel_id"] = short_text(values["channel_id"], 64, "/channel_id")
    if "entity_type" in values:
        if values["entity_type"] not in {"CAMPAIGN", "ADSET", "AD"}:
            raise OrbitError(422, "FIELD_INVALID", "实体类型无效", "/entity_type")
        result["entity_type"] = values["entity_type"]
    cursor = values.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "游标长度无效", "/cursor")
    return result, cursor
