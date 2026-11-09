"""账户命令本人诊断技术补充；保持原Ack与Task合同不变。"""

from datetime import UTC, datetime

from orbit_api.account_actions_store import PERMISSIONS
from orbit_api.account_identities_store import identifier
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.errors import OrbitError

STATES = frozenset(
    {"SCHEDULED", "WAITING_EXECUTOR", "WAITING_RETRY", "RUNNING", "BLOCKED", "SUCCEEDED", "FAILED"}
)
# 只发布已知的业务分类，不透传来源或数据库异常文本；未知分类明确null。
PUBLIC_ERRORS = frozenset(
    {
        "ACCOUNT_SYNC_EXECUTOR_UNCONFIGURED",
        "ACCOUNT_SYNC_SOURCE_UNAVAILABLE",
        "ACCOUNT_SYNC_SOURCE_CHANGED",
        "ACCOUNT_SYNC_AUTHORIZATION_CHANGED",
        "ACCOUNT_SYNC_ACCOUNT_CHANGED",
        "ACCOUNT_SYNC_OWNERSHIP_CHANGED",
        "ACCOUNT_SYNC_SCOPE_CHANGED",
        "ACCOUNT_SYNC_READ_LEASE_EXPIRED",
        "ACCOUNT_SYNC_OBSERVATION_STALE",
        "ACCOUNT_SYNC_CLAIM_LOST",
        "ACCOUNT_SYNC_REVISION_EXHAUSTED",
        "ACCOUNT_ASSIGNMENT_PROJECTION_LAG",
        "ACCOUNT_METADATA_RECONCILIATION_REQUIRED",
        "ACCOUNT_METADATA_INVALID",
        "ACCOUNT_LOCALLY_UNBOUND",
        "ACCOUNT_READ_ATTEMPTS_EXHAUSTED",
        "ACCOUNT_PLATFORM_FORBIDDEN",
        "ACCOUNT_PLATFORM_RATE_LIMITED",
        "ACCOUNT_PLATFORM_READ_UNCERTAIN",
        "ACCOUNT_PLATFORM_REDIRECT_REJECTED",
        "ACCOUNT_PLATFORM_REQUEST_REJECTED",
        "ACCOUNT_PLATFORM_RESPONSE_INVALID",
        "ACCOUNT_PLATFORM_SCOPE_INVALID",
        "ACCOUNT_PLATFORM_SCOPE_LIMIT",
        "ACCOUNT_PLATFORM_UNAVAILABLE",
        "ACCOUNT_OWNERSHIP_CHANGED",
        "ASSIGNMENT_ACCOUNT_METADATA_CHANGED",
        "ASSIGNMENT_ACTOR_CHANGED",
        "ASSIGNMENT_HISTORY_CHANGED",
        "ASSIGNMENT_SCOPE_CHANGED",
    }
)


def parse_diagnostic(account_id, query):
    if set(query) - {"kind", "request_id"}:
        raise OrbitError(400, "UNKNOWN_FIELD", "命令状态不接受该查询参数")
    kind = query.get("kind")
    if kind not in PERMISSIONS:
        raise OrbitError(422, "FIELD_INVALID", "请选择明确的账户动作", "/kind")
    return (
        identifier(account_id, "/account_id"),
        kind,
        identifier(query.get("request_id"), "/request_id"),
    )


def unavailable():
    raise OrbitError(503, "ACCOUNT_COMMAND_DIAGNOSTIC_UNAVAILABLE", "账户命令状态暂不可核验")


def database_time(value, *, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, datetime) or value.microsecond % 1000:
        unavailable()
    # MySQL DATETIME(3)以UTC存储且驱动返回naive，不使用本机时区推断。
    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def diagnostic(row):
    if (
        row["kind"] not in PERMISSIONS
        or row["state"] not in STATES
        or type(row["revision"]) is not int
        or not 1 <= row["revision"] <= MAX_REVISION
        or type(row["attempt_count"]) is not int
        or not 0 <= row["attempt_count"] <= 4
    ):
        unavailable()
    return {
        "command_id": row["id"],
        "account_id": row["account_id"],
        "kind": row["kind"],
        "accepted_request_id": row["request_id"],
        "revision": row["revision"],
        "state": row["state"],
        "attempt_count": row["attempt_count"],
        "last_error_code": row["last_error_code"]
        if row["last_error_code"] in PUBLIC_ERRORS
        else None,
        **{
            key: database_time(row[key], optional=key not in {"created_at", "updated_at"})
            for key in (
                "effective_from",
                "next_attempt_at",
                "created_at",
                "updated_at",
                "completed_at",
            )
        },
    }
