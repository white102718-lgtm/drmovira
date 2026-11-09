"""设备与绑定共享授权、水位、幂等和事务事件；不持有平台凭据或连接执行机。"""

import hashlib
from uuid import uuid4

from sqlalchemy import text

from orbit_api import account_access
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import verify_csrf  # noqa: F401


def parameters(current):
    return {"tenant": current.tenant_id, "actor": current.actor_id, "subject": current.subject_id}


async def context(session, actor, permission, *, write=False):
    current = await require_business_access(session, actor, "environments", permission)
    if write and current.data_role != "SUPER_ADMIN":
        raise OrbitError(403, "PERMISSION_DENIED", "仅超级管理员可管理执行设备及绑定")
    return current


def visibility_clause(current, alias="g"):
    """非超管仅经有效关联和当前账户范围读取；失配归属不沿旧binding授予权限。"""
    if current.data_role == "SUPER_ADMIN":
        return "1=1"
    return (
        f"{alias}.state<>'REVOKED' AND EXISTS(SELECT 1 FROM orbit_profile_binding b "
        "JOIN orbit_ad_account a ON a.tenant_id=b.tenant_id AND a.id=b.account_id "
        f"WHERE b.tenant_id={alias}.tenant_id AND b.agent_id={alias}.id "
        "AND b.unbound_at IS NULL AND a.unbound_at IS NULL "
        "AND a.owner_user_id=b.owner_user_id AND a.owner_team_id=b.owner_team_id AND ("
        + account_access.visible_clause(current, "a").replace(
            "AND tm.enabled=1)", "AND tm.enabled=1 FOR SHARE)"
        )
        + ") FOR SHARE)"
    )


async def clock(session, current, *, write=False):
    # 所有读写统一账户clock在先，以便转户/解绑与设备关联变更保持同一锁序。
    await account_access.clock(session, current)
    revision = (
        await session.execute(
            text(
                "SELECT revision FROM orbit_execution_agent_clock WHERE tenant_id=:tenant "
                + ("FOR UPDATE" if write else "FOR SHARE")
            ),
            parameters(current),
        )
    ).scalar_one_or_none()
    if revision is None:
        raise OrbitError(503, "ENVIRONMENT_INITIALIZATION_REQUIRED", "执行机登记迁移尚未完成")
    if revision >= MAX_REVISION:
        raise OrbitError(409, "REVISION_EXHAUSTED", "执行机目录版本已达上限")
    return revision


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


async def replay(session, current, operation, key, input_hash):
    row = (
        (
            await session.execute(
                text(
                    "SELECT input_hash,result_json FROM orbit_execution_agent_idempotency "
                    "WHERE tenant_id=:tenant AND actor_id=:actor AND operation=:operat"
                    "ion AND key_hash=:key "
                    "FOR SHARE"
                ),
                parameters(current) | {"operation": operation, "key": digest(key)},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    if row["input_hash"] != input_hash:
        raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于不同请求")
    return _decode(row["result_json"])


async def remember(session, current, operation, key, input_hash, result):
    await session.execute(
        text(
            "INSERT INTO orbit_execution_agent_idempotency "
            "(tenant_id,actor_id,operation,key_hash,input_hash,result_json,created_at) "
            "VALUES(:tenant,:actor,:operation,:key,:hash,:result,UTC_TIMESTAMP(6))"
        ),
        parameters(current)
        | {
            "operation": operation,
            "key": digest(key),
            "hash": input_hash,
            "result": canonical(result),
        },
    )


async def event(session, current, resource_type, identifier, revision, action, request_id, details):
    values = parameters(current) | {
        "event": str(uuid4()),
        "type": resource_type,
        "id": identifier,
        "revision": revision,
        "action": action,
        "request": request_id,
        "details": canonical(details),
    }
    await session.execute(
        text(
            "INSERT INTO orbit_execution_agent_event "
            "(id,tenant_id,resource_type,resource_id,revision,actor_id,request"
            "_id,action,details_json,created_at) "
            "VALUES(:event,:tenant,:type,:id,:revision,:actor,:request,:action"
            ",:details,UTC_TIMESTAMP(6))"
        ),
        values,
    )
    await session.execute(
        text(
            "INSERT INTO orbit_execution_agent_outbox(event_id,tenant_id,resou"
            "rce_type,resource_id,created_at) "
            "VALUES(:event,:tenant,:type,:id,UTC_TIMESTAMP(6))"
        ),
        values,
    )
    await session.execute(
        text("UPDATE orbit_execution_agent_clock SET revision=revision+1 WHERE tenant_id=:tenant"),
        parameters(current),
    )
