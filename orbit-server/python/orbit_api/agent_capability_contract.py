"""动作验证的原响应及内部受控验收凭证；身份探测不能签发写能力。"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

from orbit_api.errors import OrbitError

OPERATIONS = frozenset({"CREATE", "BUDGET_SET", "PAUSE", "DELETE", "ENABLE", "ARCHIVE"})
ENTITIES = frozenset({"CAMPAIGN", "ADSET", "AD"})
VERSIONS = (
    "workflow_version",
    "adapter_version",
    "client_version",
    "browser_version",
    "page_language",
)
FIELDS = (
    "id",
    "agent_id",
    "profile_binding_id",
    "operation_kind",
    "entity_type",
    *VERSIONS,
    "state",
    "evidence_ref",
    "verified_at",
)


def parse_filters(query):
    if set(query) - {"cursor", "page_size"}:
        raise OrbitError(400, "UNKNOWN_FIELD", "能力列表仅接受游标和页大小")
    size = query.get("page_size", "50")
    if str(size) not in {"20", "50", "100", "200"} or isinstance(size, bool):
        raise OrbitError(422, "FIELD_INVALID", "页大小无效", "/page_size")
    cursor = query.get("cursor")
    if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048):
        raise OrbitError(422, "FIELD_INVALID", "游标无效", "/cursor")
    return int(size), cursor


def validate_target(operation_kind, entity_type, versions):
    if (
        operation_kind not in OPERATIONS
        or entity_type not in ENTITIES
        or set(versions) != set(VERSIONS)
    ):
        raise ValueError("CAPABILITY_TARGET_INVALID")
    if operation_kind == "BUDGET_SET" and entity_type == "AD":
        raise ValueError("AD_HAS_NO_BUDGET")
    if any(
        not isinstance(v, str)
        or not 1 <= len(v) <= 64
        or v != v.strip()
        or any(ord(c) < 32 for c in v)
        for v in versions.values()
    ):
        raise ValueError("CAPABILITY_VERSION_INVALID")


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def effective_state(row, now):
    if row["state"] == "REVOKED" or row["agent_state"] == "REVOKED":
        return "REVOKED"
    if (
        row["state"] != "VERIFIED"
        or not row["evidence_ref"]
        or not row["verified_at"]
        or not row["expires_at"]
        or utc(row["expires_at"]) <= utc(now)
        or utc(row["verified_at"]) > utc(now)
        or row["binding_revision"] != row["current_binding_revision"]
        or row["agent_revision"] != row["current_agent_revision"]
        or row["unbound_at"] is not None
        or row["account_unbound_at"] is not None
        or not row["ownership_matches"]
    ):
        return "UNVERIFIED"
    return "VERIFIED"


def public_capability(row, now):
    result = {k: row[k] for k in FIELDS}
    result["state"] = effective_state(row, now)
    result["verified_at"] = (
        utc(row["verified_at"]).isoformat().replace("+00:00", "Z") if row["verified_at"] else None
    )
    return result


@dataclass(frozen=True)
class AcceptanceEvidence:
    """只能由受控验收程序在核验实际证据后构造，不提供HTTP签发入口。

    四种回执分别覆盖真实成功回读、明确失败、未知结果和挑战；摘要本身不
    自动证明成功，发行者负责检查其受控证据文件，不能从Agent报告直接构造。
    """

    source_sha256: str
    cases: dict
    verified_at: datetime
    expires_at: datetime

    def __post_init__(self):
        keys = {"success_readback", "explicit_failure", "unknown", "challenge"}
        if (
            set(self.cases) != keys
            or not re.fullmatch("[a-f0-9]{64}", self.source_sha256)
            or any(
                not isinstance(v, str) or not re.fullmatch("[a-f0-9]{64}", v)
                for v in self.cases.values()
            )
            or self.verified_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or self.expires_at <= self.verified_at
        ):
            raise ValueError("ACCEPTANCE_EVIDENCE_REQUIRED")
        object.__setattr__(self, "cases", MappingProxyType(dict(self.cases)))
