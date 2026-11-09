"""仅隔离协议夹具的状态事件发布器；没有生产权威结果来源时明确503。"""

from uuid import uuid4

from sqlalchemy import text

from orbit_api import task_access
from orbit_api.authorization import require_business_access
from orbit_api.errors import OrbitError
from orbit_api.task_contract import identifier
from orbit_api.task_manifest import isolated


async def publish_fixture_running(
    session, actor, task_id, node_id, request_id, *, producer="TRUSTED"
):
    """只证明事务协议，不开放任意状态或时间字段，也不证明平台已接收。"""
    await isolated(session, producer)
    current = await require_business_access(session, actor, "launch", "launch.execute")
    await task_access.clock(session, current, write=True)
    params = {
        "tenant": current.tenant_id,
        "task": identifier(task_id),
        "node": identifier(node_id),
        "request": identifier(request_id),
        "actor": actor,
    }
    row = (
        (
            await session.execute(
                text(
                    "SELECT revision,latest_sequence,manifest_phase,state FROM orbit_task "
                    "WHERE tenant_id=:tenant AND id=:task FOR UPDATE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    if row is None or row["manifest_phase"] != "COMPLETE":
        raise OrbitError(404, "NOT_FOUND", "完整任务不存在")
    node = (
        await session.execute(
            text(
                "SELECT state FROM orbit_task_node WHERE tenant_id=:tenant AND task_id=:task "
                "AND id=:node FOR UPDATE"
            ),
            params,
        )
    ).scalar_one_or_none()
    if node != "QUEUED" or row["state"] not in {"QUEUED", "RUNNING"}:
        raise OrbitError(409, "TASK_FIXTURE_STATE_CONFLICT", "受控夹具只允许未发送节点进入运行状态")
    if row["revision"] >= 9007199254740991 or row["latest_sequence"] >= 9007199254740991:
        raise OrbitError(409, "REVISION_EXHAUSTED", "任务事件版本不可继续增加")
    params |= {
        "revision": row["revision"] + 1,
        "sequence": row["latest_sequence"] + 1,
        "event": str(uuid4()),
        "audit": str(uuid4()),
    }
    await session.execute(
        text(
            "UPDATE orbit_task_node SET state='RUNNING',updated_at=UTC_TIMESTAMP(3) "
            "WHERE tenant_id=:tenant AND task_id=:task AND id=:node"
        ),
        params,
    )
    await session.execute(
        text(
            "INSERT INTO "
            "orbit_task_event(tenant_id,task_id,event_id,sequence,task_revision,node_id,"
            "state,occurred_at,request_id) VALUES(:tenant,:task,:event,:sequence,:revision,:node,"
            "'RUNNING',UTC_TIMESTAMP(3),:request)"
        ),
        params,
    )
    await session.execute(
        text(
            "UPDATE orbit_task SET state='RUNNING',revision=:revision,latest_sequence=:sequence,"
            "latest_event_id=:event,updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant "
            "AND id=:task"
        ),
        params,
    )
    await session.execute(
        text("UPDATE orbit_task_clock SET revision=revision+1 WHERE tenant_id=:tenant"), params
    )
    await session.execute(
        text(
            "INSERT INTO "
            "orbit_task_audit(id,tenant_id,task_id,actor_id,request_id,action,created_at) "
            "VALUES(:audit,:tenant,:task,:actor,:request,'ISOLATED_EVENT_PROTOCOL',UTC_TIMESTAMP(3))"
        ),
        params,
    )
    await session.execute(
        text(
            "INSERT INTO orbit_task_outbox(audit_id,tenant_id,task_id,created_at) "
            "VALUES(:audit,:tenant,:task,UTC_TIMESTAMP(3))"
        ),
        params,
    )
    return params["event"]
