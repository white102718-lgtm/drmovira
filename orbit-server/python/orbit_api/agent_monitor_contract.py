"""设备独立mTLS协议，心跳不授予身份或广告执行能力。"""

import re
from datetime import datetime
from typing import Literal

from pydantic import Field, ValidationError

from orbit_api.configuration import _parse_json, short_text
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import StrictInput, schema_error, uuid_value

MAX_SEQ = 9_007_199_254_740_991
TTL_SECONDS = 90
ADAPTER_VERSION = "ADSPOWER_META_DOM_V2"
ERROR_CODES = frozenset(
    {
        "ADSPOWER_UNREACHABLE",
        "ADSPOWER_AUTH_FAILED",
        "ADSPOWER_SUBSCRIPTION_REQUIRED",
        "ADSPOWER_RESPONSE_INVALID",
        "ADSPOWER_TIMEOUT",
        "PROFILE_DISCOVERY_FAILED",
        "CDP_UNAVAILABLE",
        "IDENTITY_PROBE_FAILED",
    }
)


class ProfileInput(StrictInput):
    id: str
    agent_id: str
    external_profile_id: str = Field(min_length=1, max_length=128)
    process_state: Literal["ACTIVE", "INACTIVE", "UNKNOWN"]
    identity_state: Literal["UNKNOWN"]
    account_ids: list[str] = Field(max_length=500)
    observed_at: str


class HeartbeatInput(StrictInput):
    agent_id: str
    boot_id: str
    seq: int = Field(ge=1, le=MAX_SEQ)
    profiles: list[ProfileInput] = Field(max_length=5000)
    observed_at: str


class DiagnosticInput(StrictInput):
    agent_id: str
    boot_id: str
    seq: int = Field(ge=1, le=MAX_SEQ)
    api_status: Literal["READY", "UNREACHABLE", "AUTH_FAILED", "UNKNOWN"]
    inventory_coverage: Literal["FULL", "ACTIVE_ONLY", "UNAVAILABLE"]
    error_code: str | None
    observed_at: str


class IdentityInput(StrictInput):
    agent_id: str
    boot_id: str
    seq: int = Field(ge=1, le=MAX_SEQ)
    event_id: str
    binding_id: str
    binding_revision: int = Field(ge=1, le=MAX_SEQ)
    profile_external_id: str = Field(min_length=1, max_length=128)
    external_account_id: str | None = Field(max_length=64)
    currency: str | None = Field(max_length=3)
    identity_state: Literal["VALID", "LOGIN_REQUIRED", "CHALLENGE", "IDENTITY_MISMATCH", "UNKNOWN"]
    adapter_version: Literal["ADSPOWER_META_DOM_V1", "ADSPOWER_META_DOM_V2"]
    observed_at: str
    evidence_sha256: str


def observed_time(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)", value
        ):
            raise ValueError
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise OrbitError(
            422, "FIELD_INVALID", "观察时间必须含时区且精度不超过微秒", "/observed_at"
        ) from None


def parse(raw, model):
    try:
        value = model.model_validate(_parse_json(raw)).model_dump()
    except ValidationError as error:
        raise schema_error(error) from None
    for key in ("agent_id", "boot_id", "event_id", "binding_id"):
        if key in value:
            value[key] = uuid_value(value[key], "/" + key)
    observed_time(value["observed_at"])
    return value


def parse_heartbeat(raw):
    value = parse(raw, HeartbeatInput)
    ids, externals = set(), set()
    for index, row in enumerate(value["profiles"]):
        row["id"] = uuid_value(row["id"], f"/profiles/{index}/id")
        row["agent_id"] = uuid_value(row["agent_id"], f"/profiles/{index}/agent_id")
        row["external_profile_id"] = short_text(
            row["external_profile_id"], 128, f"/profiles/{index}/external_profile_id"
        )
        if (
            row["agent_id"] != value["agent_id"]
            or row["id"] in ids
            or row["external_profile_id"] in externals
        ):
            raise OrbitError(
                422, "PROFILE_SCOPE_INVALID", "Profile必须属于本设备且不能重复", "/profiles"
            )
        row["account_ids"] = [
            uuid_value(i, f"/profiles/{index}/account_ids") for i in row["account_ids"]
        ]
        if len(set(row["account_ids"])) != len(row["account_ids"]):
            raise OrbitError(422, "PROFILE_SCOPE_INVALID", "账户ID不能重复", "/profiles")
        observed_time(row["observed_at"])
        ids.add(row["id"])
        externals.add(row["external_profile_id"])
    return value


def parse_diagnostics(raw):
    value = parse(raw, DiagnosticInput)
    if value["error_code"] is not None and value["error_code"] not in ERROR_CODES:
        raise OrbitError(422, "FIELD_INVALID", "诊断错误码不在安全白名单", "/error_code")
    return value


def parse_identity(raw):
    value = parse(raw, IdentityInput)
    value["profile_external_id"] = short_text(
        value["profile_external_id"], 128, "/profile_external_id"
    )
    if not re.fullmatch(r"[0-9a-f]{64}", value["evidence_sha256"]):
        raise OrbitError(422, "FIELD_INVALID", "证据必须为SHA256摘要", "/evidence_sha256")
    if value["external_account_id"] is not None and not re.fullmatch(
        r"[0-9]{1,64}", value["external_account_id"]
    ):
        raise OrbitError(422, "FIELD_INVALID", "广告账户必须为平台数字ID", "/external_account_id")
    if value["currency"] is not None and not re.fullmatch(r"[A-Z]{3}", value["currency"]):
        raise OrbitError(422, "FIELD_INVALID", "币种必须为大写三位代码", "/currency")
    if value["identity_state"] == "VALID" and value["adapter_version"] != ADAPTER_VERSION:
        raise OrbitError(422, "IDENTITY_ADAPTER_UNSUPPORTED", "VALID必须来自同页账户及币种核验版本")
    if value["identity_state"] == "VALID" and (
        value["external_account_id"] is None or value["currency"] is None
    ):
        raise OrbitError(422, "IDENTITY_EVIDENCE_REQUIRED", "VALID必须有实际平台账户及币种")
    return value


def recovery_streak(previous_seq, seq, elapsed, previous_streak):
    """启动/离线恢复须两次连续新序号；重复不会调用此推进函数。"""
    return (
        min(2, previous_streak + 1)
        if previous_seq is not None and seq == previous_seq + 1 and elapsed < 45
        else 1
    )


def parse_profile_filters(values):
    from orbit_api.execution_agent_contract import parse_agent_filters

    remaining = dict(values)
    status = remaining.pop("status", None)
    filters, cursor = parse_agent_filters(remaining)
    if status is not None:
        if status not in {"ACTIVE", "INACTIVE", "UNKNOWN"}:
            raise OrbitError(422, "FIELD_INVALID", "Profile进程状态无效", "/status")
        filters["status"] = status
    return filters, cursor
