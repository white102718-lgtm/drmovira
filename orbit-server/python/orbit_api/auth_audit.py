"""认证最小审计与状态在同一事务，不把认证凭据或提供者响应写进事件。"""

from uuid import uuid4

from sqlalchemy import text


async def append_auth_audit(
    session, tenant, actor, kind, resource_id, action, revision, request_id
):
    if kind not in {"AUTHORIZATION", "SESSION", "INVITATION", "DELIVERY"}:
        raise ValueError("未知认证资源类型")
    if action not in {
        "STARTED",
        "CLAIMED",
        "VERIFIED",
        "FAILED",
        "SESSION_CREATED",
        "SIGNED_OUT",
        "INVITATION_QUEUED",
        "INVITATION_REVOKED",
        "INVITATION_CONSUMED",
        "DELIVERY_CLAIMED",
        "DELIVERY_ACCEPTED",
        "DELIVERY_FAILED",
        "DELIVERY_UNKNOWN",
    }:
        raise ValueError("未知认证审计动作")
    await session.execute(
        text("""INSERT INTO orbit_auth_audit
            (id,tenant_id,user_id,resource_type,resource_id,action,revision,request_id,created_at)
            VALUES(:event,:tenant,:actor,:kind,:resource,:action,:revision,:request,UTC_TIMESTAMP(3))"""),
        {
            "event": str(uuid4()),
            "tenant": tenant,
            "actor": actor,
            "kind": kind,
            "resource": resource_id,
            "action": action,
            "revision": revision,
            "request": request_id,
        },
    )
