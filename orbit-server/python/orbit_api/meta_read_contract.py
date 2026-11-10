"""Meta只读采集合同：来源版本、业务日窗口及未发布分页检查点，不产生写权限。"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from orbit_api.directory_tokens import canonical

ERRORS = frozenset(
    {
        "META_CONFIG_INVALID",
        "META_API_VERSION_UNSUPPORTED",
        "META_REQUEST_INVALID",
        "META_RESPONSE_INVALID",
        "META_AUTH_FAILED",
        "META_READ_FORBIDDEN",
        "META_RATE_LIMITED",
        "META_TRANSIENT_FAILURE",
        "META_READ_REJECTED",
        "META_REDIRECT_REJECTED",
        "META_RESPONSE_TOO_LARGE",
        "META_CHECKPOINT_MISMATCH",
        "META_PAGINATION_INVALID",
        "META_PAGE_LIMIT",
        "META_RECORD_LIMIT",
        "META_REPORT_START_UNKNOWN",
        "META_REPORT_NOT_READY",
        "META_REPORT_FAILED",
        "META_ACCOUNT_MISMATCH",
    }
)


class MetaReadFailure(Exception):
    """只暴露固定码；平台错误正文和Token从不进入异常或日志。"""

    def __init__(self, code, *, retryable=False):
        self.code = code if code in ERRORS else "META_RESPONSE_INVALID"
        self.retryable = retryable is True
        super().__init__(self.code)


def fail(code="META_RESPONSE_INVALID", *, retryable=False):
    raise MetaReadFailure(code, retryable=retryable) from None


# 固定官方SDK tag 24.0.0 的字段/参数合同，不代表最新版本或当前凭据已获授权。
# https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/24.0.0/facebook_business/apiconfig.py
SUPPORTED_API_VERSIONS = frozenset({"v24.0"})


def validate_api_version(value):
    """显式必填；未知版本须先核对合同再加入，不能静默沿用当前字段。"""
    if not isinstance(value, str) or re.fullmatch(r"v[0-9]{1,3}\.[0-9]{1,2}", value) is None:
        fail("META_CONFIG_INVALID")
    if value not in SUPPORTED_API_VERSIONS:
        fail("META_API_VERSION_UNSUPPORTED")
    return value


def external_id(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,64}", value) is None:
        fail("META_REQUEST_INVALID")
    return value


def decimal_value(value, *, integer=False):
    """未知保持null；不经float，不把账户次要货币单位自动转换成主单位。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        fail()
    raw = str(value)
    if len(raw) > 80 or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw) is None:
        fail()
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        fail()
    if not amount.is_finite() or (integer and amount != amount.to_integral_value()):
        fail()
    return format(amount, "f")


@dataclass(frozen=True, repr=False)
class MetaReadConfiguration:
    source_config_id: str
    source_config_revision: int
    api_version: str
    token: str = field(repr=False)

    def __post_init__(self):
        validate_api_version(self.api_version)
        try:
            valid = str(UUID(self.source_config_id)) == self.source_config_id
        except (ValueError, TypeError, AttributeError):
            valid = False
        if (
            not valid
            or type(self.source_config_revision) is not int
            or not 1 <= self.source_config_revision <= 9007199254740991
            or not isinstance(self.api_version, str)
            or re.fullmatch(r"v[0-9]{1,3}\.[0-9]{1,2}", self.api_version) is None
            or not isinstance(self.token, str)
            or not 1 <= len(self.token) <= 8192
            or not self.token.isascii()
            or any(not 33 <= ord(c) <= 126 for c in self.token)
        ):
            fail("META_CONFIG_INVALID")

    @property
    def fingerprint(self):
        return hashlib.sha256(
            canonical(
                [self.source_config_id, self.source_config_revision, self.api_version]
            ).encode()
        ).hexdigest()


@dataclass(frozen=True)
class InsightWindow:
    since: date
    until: date
    timezone_name: str

    def __post_init__(self):
        if (
            type(self.since) is not date
            or type(self.until) is not date
            or not 0 <= (self.until - self.since).days <= 92
        ):
            fail("META_REQUEST_INVALID")
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, TypeError, ValueError):
            fail("META_REQUEST_INVALID")

    def parameters(self):
        return {
            "time_range": canonical(
                {"since": self.since.isoformat(), "until": self.until.isoformat()}
            ),
            "time_increment": "1",
        }

    def utc_bounds(self):
        """Graph采用账户本地业务日，数据库窗口为半开UTC区间，保留DST长短日。"""
        zone = ZoneInfo(self.timezone_name)
        return (
            datetime.combine(self.since, time.min, zone).astimezone(UTC),
            datetime.combine(self.until + timedelta(days=1), time.min, zone).astimezone(UTC),
        )


@dataclass(frozen=True, repr=False)
class ReadCheckpoint:
    """只保存于受控采集任务，不接受浏览器提供；页内容与检查点同事务暂存。"""

    source_fingerprint: str
    request_fingerprint: str
    after: str
    page_number: int
    record_count: int
    seen_cursors: tuple[str, ...] = ()
    seen_keys: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            not isinstance(self.source_fingerprint, str)
            or not re.fullmatch("[a-f0-9]{64}", self.source_fingerprint)
            or not isinstance(self.request_fingerprint, str)
            or not re.fullmatch("[a-f0-9]{64}", self.request_fingerprint)
            or not isinstance(self.after, str)
            or not 1 <= len(self.after) <= 2048
            or type(self.page_number) is not int
            or not 1 <= self.page_number < 250
            or type(self.record_count) is not int
            or not 0 <= self.record_count <= 50000
            or not isinstance(self.seen_cursors, (list, tuple))
            or len(self.seen_cursors) != self.page_number
            or not isinstance(self.seen_keys, (list, tuple))
            or len(self.seen_keys) != self.record_count
            or any(not isinstance(v, str) or not 1 <= len(v) <= 2048 for v in self.seen_cursors)
            or any(not isinstance(v, str) or not 1 <= len(v) <= 1024 for v in self.seen_keys)
            or len(set(self.seen_cursors)) != len(self.seen_cursors)
            or len(set(self.seen_keys)) != len(self.seen_keys)
            or self.seen_cursors[-1] != self.after
        ):
            fail("META_CHECKPOINT_MISMATCH")
        object.__setattr__(self, "seen_cursors", tuple(self.seen_cursors))
        object.__setattr__(self, "seen_keys", tuple(self.seen_keys))


@dataclass(frozen=True, repr=False)
class ReadPage:
    items: tuple[dict, ...]
    checkpoint: ReadCheckpoint | None
    complete: bool
    source_fingerprint: str
    request_fingerprint: str
    evidence_sha256: str
    observed_at: datetime


@dataclass(frozen=True, repr=False)
class AsyncReport:
    report_run_id: str
    account_id: str
    source_fingerprint: str
    request_fingerprint: str
    window: InsightWindow
    level: str
    attribution: "MetaAttribution"


@dataclass(frozen=True)
class ReportStatus:
    state: str
    percent: int
    complete: bool


@dataclass(frozen=True, repr=False)
class MetaAttribution:
    """已由MetricProfileStore.resolve核验的明确归因；本类型不自行发行verified。"""

    profile_id: str
    profile_version: str
    registry_revision: int
    profile_source_hash: str
    adapter_version: str
    mapping_hash: str
    windows: tuple[str, ...]
    report_time: str

    def __post_init__(self):
        try:
            valid = str(UUID(self.profile_id)) == self.profile_id
        except (TypeError, ValueError, AttributeError):
            valid = False
        # 首期只映射已支持的明确组合；不能以default或窗口显示文案回退。
        if (
            not valid
            or not isinstance(self.profile_version, str)
            or not 1 <= len(self.profile_version) <= 64
            or type(self.registry_revision) is not int
            or not 1 <= self.registry_revision <= 9007199254740991
            or not isinstance(self.profile_source_hash, str)
            or not re.fullmatch("[a-f0-9]{64}", self.profile_source_hash)
            or not isinstance(self.adapter_version, str)
            or not 1 <= len(self.adapter_version) <= 64
            or not isinstance(self.mapping_hash, str)
            or not re.fullmatch("[a-f0-9]{64}", self.mapping_hash)
            or type(self.windows) is not tuple
            or not 1 <= len(self.windows) <= 3
            or len(set(self.windows)) != len(self.windows)
            or not set(self.windows) <= {"1d_click", "7d_click", "1d_view"}
            or self.report_time not in {"impression", "conversion", "mixed"}
        ):
            fail("META_REQUEST_INVALID")

    def parameters(self):
        return {
            "action_attribution_windows": canonical(list(self.windows)),
            "action_report_time": self.report_time,
        }

    @property
    def fingerprint(self):
        return hashlib.sha256(
            canonical(
                [
                    self.profile_id,
                    self.profile_version,
                    self.registry_revision,
                    self.profile_source_hash,
                    self.adapter_version,
                    self.mapping_hash,
                    self.windows,
                    self.report_time,
                ]
            ).encode()
        ).hexdigest()

    @classmethod
    def from_resolved(cls, resolved):
        """仅供持久worker传入服务器resolve结果；禁止HTTP接受此字典作为验收。"""
        try:
            profile = resolved["profile"]
            if (
                profile["verified"] is not True
                or profile["source"] != "META"
                or profile["timezone_policy"] != "ACCOUNT_LOCAL"
                or profile["breakdown"] != "TOTAL"
                or resolved["bound_profile_version"] != profile["version"]
            ):
                fail("META_REQUEST_INVALID")
            mapping = {
                ("CLICK_THROUGH", 1): "1d_click",
                ("CLICK_THROUGH", 7): "7d_click",
                ("VIEW_THROUGH", 1): "1d_view",
            }
            spec = resolved["attribution_spec"]
            if not isinstance(spec, list) or not 1 <= len(spec) <= 3:
                fail("META_REQUEST_INVALID")
            windows = []
            for item in spec:
                if (
                    set(item) != {"event_type", "window_days"}
                    or type(item["window_days"]) is not int
                ):
                    fail("META_REQUEST_INVALID")
                windows.append(mapping[(item["event_type"], item["window_days"])])
            if len(set(windows)) != len(windows) or set(windows) != set(
                profile["attribution_windows"]
            ):
                fail("META_REQUEST_INVALID")
            if (
                hashlib.sha256(canonical(profile).encode()).hexdigest()
                != resolved["profile_source_hash"]
            ):
                fail("META_REQUEST_INVALID")
            return cls(
                profile["id"],
                profile["version"],
                resolved["registry_revision"],
                resolved["profile_source_hash"],
                resolved["adapter_version"],
                hashlib.sha256(canonical(spec).encode()).hexdigest(),
                tuple(sorted(windows)),
                profile["action_report_time"],
            )
        except (KeyError, TypeError, ValueError):
            fail("META_REQUEST_INVALID")
