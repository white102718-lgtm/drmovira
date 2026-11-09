"""投放/模板独立实时权限、事务水位、单拥有者与审计幂等基础。"""

import hashlib
from uuid import uuid4

from sqlalchemy import text

from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import managed_teams, validate_ownership


async def context(session, actor, permission):
    # 模板是launch菜单内二级页，不创设templates一级菜单，也不隐含launch.read。
    return await require_business_access(session, actor, "launch", permission)


def readable(current, teams, row):
    return (
        current.data_role == "SUPER_ADMIN"
        or row["owner_user_id"] == current.subject_id
        or (current.data_role == "TEAM_ADMIN" and row["owner_team_id"] in teams)
    )


def scope_clause(current, alias, *, current_managers=False):
    if current.data_role == "SUPER_ADMIN":
        return "1=1"
    own = f"{alias}.owner_user_id=:subject"
    if current.data_role == "TEAM_ADMIN":
        return (
            own
            + " OR EXISTS(SELECT 1 FROM orbit_business_team_manager tm "
            + f"WHERE tm.tenant_id={alias}.tenant_id AND tm.team_id={alias}.owner_team_id "
            + "AND tm.manager_user_id=:actor AND tm.enabled=1"
            + (" FOR SHARE)" if current_managers else ")")
        )
    return own


def parameters(current):
    return {"tenant": current.tenant_id, "actor": current.actor_id, "subject": current.subject_id}


async def owner(session, current, ownership):
    await validate_ownership(
        session,
        current,
        {
            "owner_team_id": ownership["owner_team_id"],
            "data_owner_user_ids": [ownership["owner_user_id"]],
        },
    )
    return (
        await session.execute(
            text(
                "SELECT user_id FROM orbit_business_user WHERE tenant_id=:tenant AND "
                "id=:owner FOR SHARE"
            ),
            {"tenant": current.tenant_id, "owner": ownership["owner_user_id"]},
        )
    ).scalar_one()


async def clock(session, current, *, write=False):
    row = (
        (
            await session.execute(
                text(
                    "SELECT plan_revision,template_revision FROM orbit_launch_clock WHERE "
                    "tenant_id=:tenant " + ("FOR UPDATE" if write else "FOR SHARE")
                ),
                parameters(current),
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise OrbitError(503, "LAUNCH_INITIALIZATION_REQUIRED", "投放业务迁移尚未完成")
    if max(row["plan_revision"], row["template_revision"]) >= MAX_REVISION:
        raise OrbitError(409, "REVISION_EXHAUSTED", "投放目录版本已达上限")
    return row


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


async def successful_replay(session, actor, read_permission, operation, key, payload_hash):
    """只读探测成功键，先当前读授权再解释原结果；不锁空键、不重取变化后的来源。

    未命中继续原动作授权和最终写锁幂等复核；并发首写不会因探测绕过业务校验。
    """
    row = (
        (
            await session.execute(
                text(
                    "SELECT i.tenant_id,i.input_hash,i.result_json FROM orbit_launch_idempotency i "
                    "JOIN orbit_user_scope s ON s.user_id=i.actor_id AND s.tenant_id=i.tenant_id "
                    "AND s.enabled=1 WHERE i.actor_id=:actor "
                    "AND i.operation=:op AND i.key_hash=:key"
                ),
                {"actor": actor, "op": operation, "key": hashlib.sha256(key.encode()).hexdigest()},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    current = await context(session, actor, read_permission)
    if row["tenant_id"] != current.tenant_id:
        raise OrbitError(403, "PERMISSION_DENIED", "当前读取范围已变化")
    if row["input_hash"] != payload_hash:
        raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不得改变业务意图")
    return current, _decode(row["result_json"])


async def replay(session, current, operation, key, payload_hash):
    row = (
        (
            await session.execute(
                text(
                    "SELECT input_hash,result_json FROM orbit_launch_idempotency WHERE "
                    "tenant_id=:tenant AND actor_id=:actor AND operation=:op AND key_hash=:key "
                    "FOR UPDATE"
                ),
                parameters(current)
                | {"op": operation, "key": hashlib.sha256(key.encode()).hexdigest()},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    if row["input_hash"] != payload_hash:
        raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不得改变业务意图")
    return _decode(row["result_json"])


async def remember(session, current, operation, key, payload_hash, result):
    await session.execute(
        text(
            """INSERT INTO orbit_launch_idempotency
            (tenant_id,actor_id,operation,key_hash,input_hash,result_json,created_at)
            VALUES(:tenant,:actor,:op,:key,:hash,:result,UTC_TIMESTAMP(3))"""
        ),
        parameters(current)
        | {
            "op": operation,
            "key": hashlib.sha256(key.encode()).hexdigest(),
            "hash": payload_hash,
            "result": canonical(result),
        },
    )


async def event(
    session, current, resource_kind, resource_id, revision, action, request_id, details
):
    event_id = str(uuid4())
    values = parameters(current) | {
        "event": event_id,
        "kind": resource_kind,
        "id": resource_id,
        "revision": revision,
        "action": action,
        "request": request_id,
        "details": canonical(details),
    }
    await session.execute(
        text(
            """INSERT INTO orbit_launch_event(tenant_id,id,actor_id,resource_kind,
            resource_id,revision,action,request_id,details_json,created_at)
            VALUES(:tenant,:event,:actor,:kind,:id,:revision,:action,:request,:details,
            UTC_TIMESTAMP(3))"""
        ),
        values,
    )
    await session.execute(
        text(
            "INSERT INTO orbit_launch_outbox(tenant_id,event_id,state,created_at) "
            "VALUES(:tenant,:event,'PENDING',UTC_TIMESTAMP(3))"
        ),
        values,
    )
    field = "template_revision" if resource_kind == "TEMPLATE" else "plan_revision"
    await session.execute(
        text(f"UPDATE orbit_launch_clock SET {field}={field}+1 WHERE tenant_id=:tenant"), values
    )


async def teams(session, current):
    return await managed_teams(session, current)
