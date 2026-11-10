"""Meta只读采集设置及状态；配置保存不启动后台进程，不改变原Metrics查询合同。"""

import hashlib
from datetime import UTC

from sqlalchemy import text

from orbit_api.account_access import event
from orbit_api.authorization import require_business_access
from orbit_api.configuration import _parse_json
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid
from orbit_api.meta_connection_service import access, lock_account_clock
from orbit_api.meta_metric_collection import resolved_profile

MAX_REVISION = 9007199254740991
ERRORS = {
    "META_RATE_LIMITED",
    "META_TRANSIENT_FAILURE",
    "META_AUTH_FAILED",
    "META_READ_FORBIDDEN",
    "META_RESPONSE_INVALID",
    "META_COLLECTION_UNVERIFIED",
}


def parse_policy(raw):
    value = _parse_json(raw)
    if not isinstance(value, dict) or set(value) != {
        "profile_id",
        "adapter_version",
        "scheduler_enabled",
        "revision",
    }:
        raise OrbitError(422, "FIELD_INVALID", "采集设置字段不完整或含未知字段")
    if not isinstance(value["profile_id"], str):
        raise OrbitError(422, "FIELD_INVALID", "请选择已验证指标口径", "/profile_id")
    _uuid(value["profile_id"], "/profile_id")
    if (
        type(value["scheduler_enabled"]) is not bool
        or type(value["revision"]) is not int
        or not 0 <= value["revision"] <= MAX_REVISION
        or not isinstance(value["adapter_version"], str)
        or not 1 <= len(value["adapter_version"]) <= 64
        or any(ord(c) < 33 or ord(c) > 126 for c in value["adapter_version"])
    ):
        raise OrbitError(422, "FIELD_INVALID", "请选择指标口径、有效版本和明确调度状态")
    return value


def public_policy(row):
    return {
        "profile_id": row["profile_id"] if row else None,
        "adapter_version": row["adapter_version"] if row else None,
        "scheduler_enabled": bool(row["scheduler_enabled"]) if row else False,
        "revision": row["revision"] if row else 0,
    }


def stamp(value):
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def public_job(row):
    if row["job_id"] is None:
        return None
    error = _decode(row["checkpoint_json"]).get("last_error")
    return {
        "id": row["job_id"],
        "state": row["state"],
        "updated_at": stamp(row["updated_at"]),
        "last_error": error if error in ERRORS else "META_COLLECTION_UNVERIFIED" if error else None,
        "attempts": row["attempts"],
        "next_run_at": stamp(row["next_run_at"]),
        "page_number": row["page_number"],
        "date_from": row["date_from"].isoformat(),
        "date_to": row["date_to"].isoformat(),
        "profile_id": row["profile_id"],
        "profile_version": row["profile_version"],
        "adapter_version": row["adapter_version"],
    }


async def policy_access(session, actor):
    current = await access(session, actor)
    account = await require_business_access(session, actor, "accounts", "accounts.sync")
    if current.tenant_id != account.tenant_id or current.subject_id != account.subject_id:
        raise OrbitError(403, "PERMISSION_DENIED", "集成与账户同步权限已变化")
    return current


async def read_policy(session, current, *, write=False, connection_id=None):
    if connection_id is not None:
        await policy_connection(session, current, connection_id)
    table = "orbit_meta_connection_sync_policy" if connection_id else "orbit_meta_sync_policy"
    extra = " AND connection_id=:connection " if connection_id else " "

    return (
        (
            await session.execute(
                text(
                    f"SELECT * FROM {table} WHERE tenant_id=:tenant "
                    + extra
                    + ("FOR UPDATE" if write else "FOR SHARE")
                ),
                {"tenant": current.tenant_id, "connection": connection_id},
            )
        )
        .mappings()
        .first()
    )


async def resolve_policy_profile(session, tenant, identifier, adapter, *, connection_id=None):
    """仅采集设置采用原连接ID的当前版本；映射、主体连续性由采集解析器复核。"""
    row = (
        (
            await session.execute(
                text(
                    "SELECT v.source_connection_id,c.revision FROM orbit_metric_profile_head h "
                    "JOIN orbit_metric_profile_version v ON v.tenant_id=h.tenant_id "
                    "AND v.profile_id=h.id AND v.version=h.current_version "
                    "LEFT JOIN orbit_meta_connection c ON c.tenant_id=v.tenant_id "
                    "AND c.id=v.source_connection_id WHERE h.tenant_id=:tenant "
                    "AND h.id=:id FOR SHARE"
                ),
                {"tenant": tenant, "id": identifier},
            )
        )
        .mappings()
        .first()
    )
    if row is None or (row["source_connection_id"] is not None and row["revision"] is None):
        raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "采集口径来源不可用")
    if connection_id is not None and row["source_connection_id"] != connection_id:
        raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "指标口径不属于当前连接")
    return await resolved_profile(
        session, tenant, identifier, adapter, row["source_connection_id"], row["revision"]
    )


async def policy_choices(session, current, *, connection_id=None):
    if connection_id is not None:
        await policy_connection(session, current, connection_id)

    rows = (
        (
            await session.execute(
                text(
                    "SELECT h.id profile_id,h.current_version profile_version,m.adapter_version "
                    "FROM orbit_metric_profile_head h JOIN orbit_metric_profile_version v ON "
                    "v.tenant_id=h.tenant_id AND v.profile_id=h.id AND v.version=h.current_version "
                    "JOIN orbit_metric_profile_adapter m ON m.tenant_id=v.tenant_id AND m.pro"
                    "file_id=v.profile_id "
                    "AND m.profile_version=v.version WHERE h.tenant_id=:tenant AND h.state='E"
                    "NABLED' "
                    "AND v.source='META' AND v.authority_kind='TRUSTED' AND m.revoked_at IS NULL "
                    "AND (:connection IS NULL OR v.source_connection_id=:connection) "
                    "ORDER BY h.id,m.adapter_version LIMIT 201"
                ),
                {"tenant": current.tenant_id, "connection": connection_id},
            )
        )
        .mappings()
        .all()
    )
    if len(rows) > 200:
        raise OrbitError(
            503, "META_PROFILE_CHOICE_LIMIT", "可选指标口径较多，请联系管理员整理后重试"
        )
    choices = []
    for row in rows:
        try:
            await resolve_policy_profile(
                session,
                current.tenant_id,
                row["profile_id"],
                row["adapter_version"],
                **({"connection_id": connection_id} if connection_id else {}),
            )
        except OrbitError as error:
            if error.code not in {
                "METRIC_PROFILE_SOURCE_CHANGED",
                "METRIC_PROFILE_AUTHORITY_UNAVAILABLE",
            }:
                raise
            continue
        choices.append(dict(row))
    return choices


async def save_policy(session, current, value, key, request_id, *, connection_id=None):
    """权限和CSRF由入口实时验证；时钟→策略→口径，幂等与审计均在同事务。"""
    await lock_account_clock(session, current.tenant_id)
    if connection_id is not None:
        await policy_connection(session, current, connection_id)
    table = "orbit_meta_connection_sync_policy" if connection_id else "orbit_meta_sync_policy"
    prior = (
        (
            await session.execute(
                text(
                    "SELECT input_hash,result_json FROM orbit_meta_request_receipt "
                    "WHERE tenant_id=:tenant AND actor_id=:actor AND request_key=:key FOR UPDATE"
                ),
                {"tenant": current.tenant_id, "actor": current.actor_id, "key": key},
            )
        )
        .mappings()
        .first()
    )
    digest = hashlib.sha256(
        canonical(
            {
                "operation": "META_SYNC_POLICY",
                "value": value,
                **({"connection_id": connection_id} if connection_id else {}),
            }
        ).encode()
    ).hexdigest()
    if prior is not None:
        if prior["input_hash"] != digest:
            raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "此幂等键已用于其他设置")
        return _decode(prior["result_json"])
    old = await read_policy(
        session, current, write=True, **({"connection_id": connection_id} if connection_id else {})
    )
    if value["revision"] != (old["revision"] if old else 0):
        raise OrbitError(409, "REVISION_CONFLICT", "采集设置已被其他人修改，请刷新")
    if value["revision"] >= MAX_REVISION:
        raise OrbitError(409, "REVISION_EXHAUSTED", "采集设置版本已达上限")
    # 关闭当前调度不需要过期口径重新有效，避免用户无法停止失效来源的自动任务。
    disabling = (
        old is not None
        and not value["scheduler_enabled"]
        and all(old[k] == value[k] for k in ("profile_id", "adapter_version"))
    )
    if not disabling:
        await resolve_policy_profile(
            session,
            current.tenant_id,
            value["profile_id"],
            value["adapter_version"],
            **({"connection_id": connection_id} if connection_id else {}),
        )
    result = {**value, "revision": value["revision"] + 1}
    params = {
        "tenant": current.tenant_id,
        "actor": current.actor_id,
        "connection": connection_id,
        "profile": value["profile_id"],
        "adapter": value["adapter_version"],
        "enabled": value["scheduler_enabled"],
        "revision": result["revision"],
    }
    if old is None:
        columns = (
            "tenant_id,"
            + ("connection_id," if connection_id else "")
            + "profile_id,adapter_version,scheduler_enabled,actor_id,revision,updated_at"
        )
        values = (
            ":tenant,"
            + (":connection," if connection_id else "")
            + ":profile,:adapter,:enabled,:actor,:revision,UTC_TIMESTAMP(6)"
        )
        await session.execute(text(f"INSERT INTO {table} ({columns}) VALUES({values})"), params)
    else:
        await session.execute(
            text(
                f"UPDATE {table} SET profile_id=:profile,adapter_version=:adapter,"
                "scheduler_enabled=:enabled,actor_id=:actor,revision=:revision,"
                "last_fast_slot=NULL,last_daily_date=NULL,updated_at=UTC_TIMESTAMP(6) "
                "WHERE tenant_id=:tenant"
                + (" AND connection_id=:connection" if connection_id else "")
            ),
            params,
        )
    await event(
        session,
        current,
        "META_SYNC_POLICY",
        connection_id or current.tenant_id,
        result["revision"],
        "META_SYNC_POLICY_CHANGED",
        request_id,
        {
            **({"connection_id": connection_id} if connection_id else {}),
            "profile_id": value["profile_id"],
            "adapter_version": value["adapter_version"],
            "scheduler_enabled": value["scheduler_enabled"],
        },
    )
    await session.execute(
        text(
            "INSERT INTO orbit_meta_request_receipt "
            "(tenant_id,actor_id,request_key,input_hash,result_json,created_at) "
            "VALUES(:tenant,:actor,:key,:digest,:result,UTC_TIMESTAMP(3))"
        ),
        {
            "tenant": current.tenant_id,
            "actor": current.actor_id,
            "key": key,
            "digest": digest,
            "result": canonical(result),
        },
    )
    return result


async def policy_connection(session, current, identifier):
    """连接专属设置仍核本人连接/租户超级管理员，停用连接可读取并关闭原策略。"""
    identifier = _uuid(identifier, "/connection_id")
    row = (
        (
            await session.execute(
                text(
                    "SELECT id,actor_id,kind,status,revision FROM orbit_meta_connection "
                    "WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                ),
                {"tenant": current.tenant_id, "id": identifier},
            )
        )
        .mappings()
        .first()
    )
    if row is None or (current.data_role != "SUPER_ADMIN" and row["actor_id"] != current.actor_id):
        raise OrbitError(404, "NOT_FOUND", "Meta连接不存在或不可见")
    return row
