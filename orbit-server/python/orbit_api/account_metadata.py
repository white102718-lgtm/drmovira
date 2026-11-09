"""只读平台元数据适配器边界；缺失数据保持未知，不以余额或充值推算消耗。"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from orbit_api.errors import OrbitError


class AccountReadAdapter(Protocol):
    async def fetch_metadata(self, external_id: str): ...


class UnavailableAccountAdapter:
    """生产尚未配置真实只读连接器时失败关闭，绝不返回虚构平台账户。"""

    async def fetch_metadata(self, external_id):
        raise OrbitError(503, "ACCOUNT_CONNECTOR_UNVERIFIED", "账户只读连接器尚未验证")


@dataclass(frozen=True)
class AccountMetadata:
    external_id: str
    name: str
    currency: str
    timezone_id: str
    account_status: str
    auth_status: str
    observed_at: datetime


def metadata(value, expected_id, currencies):
    """currencies由服务端权威字典提供；调用者不能从平台或浏览器临时扩大币种白名单。"""
    required = {
        "external_id",
        "name",
        "currency",
        "timezone_id",
        "account_status",
        "auth_status",
        "observed_at",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise OrbitError(503, "ACCOUNT_METADATA_INVALID", "平台元数据字段缺失或未知")
    try:
        external = value["external_id"]
        name = value["name"]
        observed = value["observed_at"]
        if (
            not isinstance(external, str)
            or not re.fullmatch(r"[0-9]{1,64}", external)
            or external != expected_id
            or not isinstance(name, str)
            or not name.strip()
            or len(name) > 10000
            or not isinstance(value["currency"], str)
            or value["currency"] not in currencies
            or value["account_status"] not in {"ACTIVE", "DISABLED", "UNKNOWN"}
            or value["auth_status"] not in {"AUTHORIZED", "EXPIRED", "REVOKED", "UNKNOWN"}
            or not isinstance(observed, datetime)
            or observed.tzinfo is None
            or not isinstance(value["timezone_id"], str)
            or len(value["timezone_id"]) > 64
        ):
            raise ValueError
        ZoneInfo(value["timezone_id"])
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise OrbitError(503, "ACCOUNT_METADATA_INVALID", "平台账户身份、币种或时区无效") from None
    return AccountMetadata(
        external,
        name,
        value["currency"],
        value["timezone_id"],
        value["account_status"],
        value["auth_status"],
        observed.astimezone(UTC),
    )


def timezone_payload(identifier, reference):
    if reference.tzinfo is None:
        raise ValueError("时区显示必须有明确的参考UTC时刻")
    local = reference.astimezone(ZoneInfo(identifier))
    seconds = int(local.utcoffset().total_seconds())
    if seconds % 60:
        raise ValueError("历史时区秒级偏移不能伪装为分钟精度")
    minutes = abs(seconds) // 60
    offset = f"{'-' if seconds < 0 else '+'}{minutes // 60:02d}:{minutes % 60:02d}"
    return {
        "id": identifier,
        "display_label": "UTC" + offset + "（" + identifier + "）",
        "reference_at": reference.astimezone(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "offset_at": offset,
    }


def unknown_observation(currency, *, kind="UNKNOWN", status="UNSYNCED", source="NOT_PROVIDED"):
    return {
        "amount": None,
        "currency": currency,
        "kind": kind,
        "status": status,
        "source": source,
        "business_date": None,
        "observed_at": None,
    }
