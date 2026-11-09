"""账户实时动作授权、范围交集与只追加事务事件；独立于系统人员管理权限。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import MAX_REVISION
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import managed_teams


async def context(session, actor, permission):
    current = await require_business_access(session, actor, "accounts", permission)
    return current, await managed_teams(session, current)


def visible_clause(current, alias):
    # alias仅由本模块固定调用点传入，不接收请求中的SQL片段。
    if current.data_role == "SUPER_ADMIN":
        return "1=1"
    own = f"{alias}.owner_user_id=:subject"
    if current.data_role == "TEAM_ADMIN":
        return (
            own
            + " OR EXISTS(SELECT 1 FROM orbit_business_team_manager tm "
            + f"WHERE tm.tenant_id={alias}.tenant_id AND tm.team_id={alias}.owner_team_id "
            + "AND tm.manager_user_id=:actor AND tm.enabled=1)"
        )
    return own


def parameters(current):
    return {"tenant": current.tenant_id, "actor": current.actor_id, "subject": current.subject_id}


async def clock(session, current, *, write=False):
    value = (
        await session.execute(
            text(
                "SELECT revision FROM orbit_account_clock WHERE tenant_id=:tenant "
                + ("FOR UPDATE" if write else "FOR SHARE")
            ),
            parameters(current),
        )
    ).scalar_one_or_none()
    if value is None:
        raise OrbitError(503, "ACCOUNT_INITIALIZATION_REQUIRED", "账户业务迁移尚未完成")
    if value >= MAX_REVISION:
        raise OrbitError(409, "REVISION_EXHAUSTED", "账户目录版本已达上限")
    # 时钟锁先于命令/账户锁；共享读不升级为写锁。独立分配Worker用自身锁序追平。
    # 到期投影未生效时整租户范围查询失败关闭，不能继续以旧拥有者授予访问。
    from orbit_api.account_actions_store import require_tenant_projections_current

    await require_tenant_projections_current(session, current.tenant_id, datetime.now(UTC))
    return value


async def event(session, current, resource_type, identifier, revision, action, request_id, details):
    identifier_event = str(uuid4())
    values = parameters(current) | {
        "event": identifier_event,
        "type": resource_type,
        "id": identifier,
        "revision": revision,
        "action": action,
        "request": request_id,
        "details": canonical(details),
    }
    await session.execute(
        text("""INSERT INTO orbit_account_event
        (id,tenant_id,resource_type,resource_id,revision,actor_id,request_id,action,details_json,created_at)
        VALUES(:event,:tenant,:type,:id,:revision,:actor,:request,:action,:details,UTC_TIMESTAMP(3))"""),
        values,
    )
    await session.execute(
        text("""INSERT INTO orbit_account_outbox
        (event_id,tenant_id,resource_type,resource_id,created_at)
        VALUES(:event,:tenant,:type,:id,UTC_TIMESTAMP(3))"""),
        values,
    )
    await session.execute(
        text("UPDATE orbit_account_clock SET revision=revision+1 WHERE tenant_id=:tenant"), values
    )
