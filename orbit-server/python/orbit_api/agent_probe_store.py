"""主动只读探测请求；控制面永不访问用户localhost，也不发广告执行命令。"""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

from orbit_api import execution_agent_access as access
from orbit_api.agent_monitor_contract import observed_time
from orbit_api.agent_monitor_store import AgentMonitorStore, now_utc, one, stamp, utc
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.execution_agent_store import ExecutionAgentStore
from orbit_api.reference_contract import uuid_value

COLUMNS = (
    "id,tenant_id,agent_id,actor_id,agent_revision,state,created_at,expires_at,"
    "completed_at,error_code,completion_hash,completion_ack"
)


def public_request(row, now):
    """排队到期直接按服务端时间展示，不依赖定时任务，不改写已完成回执。"""
    expired = row["state"] == "QUEUED" and utc(row["expires_at"]) <= now
    return {
        "id": row["id"],
        "agent_id": row["agent_id"],
        "state": "EXPIRED" if expired else row["state"],
        "created_at": stamp(row["created_at"]),
        "expires_at": stamp(row["expires_at"]),
        "completed_at": stamp(row["completed_at"]),
        "error_code": "PROBE_EXPIRED" if expired else row["error_code"],
    }


def completion_state(row, head, value, now):
    """完成只证明一次新观察已送达；API故障和Meta未知绝不能当作身份有效。"""
    if utc(row["expires_at"]) <= now:
        raise OrbitError(410, "PROBE_EXPIRED", "探测请求已过期，请重新发起")
    if row["state"] != "QUEUED":
        raise OrbitError(409, "PROBE_NOT_PENDING", "探测请求已终结")
    AgentMonitorStore().current_report(head, value, now)
    observed = observed_time(value["observed_at"])
    if observed < utc(row["created_at"]) or observed > utc(head["received_at"]) + timedelta(
        seconds=5
    ):
        raise OrbitError(409, "PROBE_OBSERVATION_STALE", "必须使用本次请求发起后的新观察")
    if (
        head["diagnostic_seq"] != value["seq"]
        or head["diagnostic_received_at"] is None
        or utc(head["diagnostic_received_at"]) < utc(row["created_at"])
    ):
        raise OrbitError(409, "PROBE_DIAGNOSTICS_REQUIRED", "当前心跳的诊断尚未确认")
    diagnostic = _decode(head["diagnostic_json"])
    if diagnostic["api_status"] != "READY":
        return "FAILED", "LOCAL_API_UNAVAILABLE"
    return "COMPLETED", None


class AgentProbeStore:
    def __init__(self, tokens=None):
        self.tokens = tokens
        self.monitor = AgentMonitorStore()

    async def enqueue(
        self, session, actor, agent_id, authorization, csrf, key, expected, request_id
    ):
        """当前授权先于回放；同设备时钟写锁串行化幂等键和唯一有效待办。"""
        current = await access.context(session, actor, "environments.probe", write=True)
        access.verify_csrf(self.tokens, current, authorization, csrf)
        await access.clock(session, current, write=True)
        agent = await ExecutionAgentStore(self.tokens).row(session, current, agent_id, write=True)
        if agent["state"] == "REVOKED":
            raise OrbitError(409, "AGENT_REVOKED", "已撤销设备不能发起探测")
        intent = access.digest({"agent_id": agent["id"], "revision": expected})
        replay = await access.replay(session, current, "PROBE", key, intent)
        if replay is not None:
            return replay
        if agent["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "设备已被修改，请刷新后发起")
        now = await now_utc(session)
        p = access.parameters(current) | {"agent": agent["id"], "now": now.replace(tzinfo=None)}
        existing = await one(
            session,
            "SELECT id FROM orbit_agent_probe_request WHERE tenant_id=:tenant AND "
            "agent_id=:agent AND state='QUEUED' AND expires_at>:now "
            "ORDER BY created_at,id LIMIT 1 FOR UPDATE",
            p,
        )
        if existing:
            raise OrbitError(409, "PROBE_ALREADY_PENDING", "已有待完成探测，请等待或查询原请求")
        identifier = str(uuid4())
        expires = now + timedelta(seconds=120)
        await session.execute(
            text(
                "INSERT INTO orbit_agent_probe_request "
                "(tenant_id,id,agent_id,actor_id,agent_revision,state,created_at,expires_at) "
                "VALUES(:tenant,:id,:agent,:actor,:revision,'QUEUED',:now,:expires)"
            ),
            p | {"id": identifier, "revision": expected, "expires": expires.replace(tzinfo=None)},
        )
        ack = {"id": identifier, "revision": 1, "state": "QUEUED", "request_id": request_id}
        await access.event(
            session,
            current,
            "EXECUTION_AGENT",
            agent["id"],
            expected,
            "PROBE_REQUESTED",
            request_id,
            {"probe_request_id": identifier},
        )
        await access.remember(session, current, "PROBE", key, intent, ack)
        return ack

    async def request_row(self, session, tenant, agent, identifier, *, write=False):
        identifier = uuid_value(identifier, "/request_id")
        row = await one(
            session,
            f"SELECT {COLUMNS} FROM orbit_agent_probe_request "
            "WHERE tenant_id=:tenant AND agent_id=:agent AND id=:id "
            + ("FOR UPDATE" if write else "FOR SHARE"),
            {"tenant": tenant, "agent": agent, "id": identifier},
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "探测请求不存在或当前不可见")
        return row

    async def get(self, session, actor, agent_id, identifier):
        current = await access.context(session, actor, "environments.read", write=True)
        await access.clock(session, current)
        agent = await ExecutionAgentStore(self.tokens).row(session, current, agent_id)
        row = await self.request_row(session, current.tenant_id, agent["id"], identifier)
        return public_request(row, await now_utc(session))

    async def initiator(self, session, row):
        """原操作者的当前权限和租户仍必须有效；设备证书不替代业务授权。"""
        current = await access.context(session, row["actor_id"], "environments.probe", write=True)
        if current.tenant_id != row["tenant_id"]:
            raise OrbitError(403, "PROBE_AUTHORIZATION_REVOKED", "原探测授权已失效")
        return current

    async def agent_revision(self, session, row):
        agent = await one(
            session,
            "SELECT revision FROM orbit_execution_agent "
            "WHERE tenant_id=:tenant AND id=:agent FOR SHARE",
            {"tenant": row["tenant_id"], "agent": row["agent_id"]},
        )
        if agent is None or agent["revision"] != row["agent_revision"]:
            raise OrbitError(409, "PROBE_DEVICE_CHANGED", "设备配置已变化，请重新发起探测")

    async def pending(self, session, der):
        p, now = await self.monitor.authenticate(session, der, write=True)
        row = await one(
            session,
            f"SELECT {COLUMNS} FROM orbit_agent_probe_request "
            "WHERE tenant_id=:tenant AND agent_id=:agent AND state='QUEUED' "
            "AND expires_at>:now ORDER BY created_at,id LIMIT 1 FOR UPDATE",
            p | {"now": now.replace(tzinfo=None)},
        )
        result = {"agent_id": p["agent"], "request": None}
        if row is None:
            return result
        try:
            await self.initiator(session, row)
            await self.agent_revision(session, row)
        except OrbitError as error:
            if error.status not in {401, 403, 404, 409}:
                raise
            code = (
                "PROBE_DEVICE_CHANGED"
                if error.code == "PROBE_DEVICE_CHANGED"
                else "PROBE_AUTHORIZATION_REVOKED"
            )
            await session.execute(
                text(
                    "UPDATE orbit_agent_probe_request SET state='FAILED',"
                    "completed_at=:now,error_code=:error WHERE tenant_id=:tenant AND id=:id"
                ),
                p | {"id": row["id"], "now": now.replace(tzinfo=None), "error": code},
            )
            return result
        result["request"] = {
            "id": row["id"],
            "created_at": stamp(row["created_at"]),
            "expires_at": stamp(row["expires_at"]),
        }
        return result

    async def complete(self, session, der, identifier, value, request_id):
        p, now = await self.monitor.authenticate(session, der, write=True)
        self.monitor.match(p, value)
        row = await self.request_row(session, p["tenant"], p["agent"], identifier, write=True)
        current = await self.initiator(session, row)
        await self.agent_revision(session, row)
        intent = access.digest(value)
        # 已确认回执重放可以晚于TTL或新seq，但设备/用户当前授权始终在前。
        if row["completion_hash"] is not None:
            if row["completion_hash"] != intent:
                raise OrbitError(409, "PROBE_COMPLETION_CONFLICT", "完成请求已用于不同观察")
            return _decode(row["completion_ack"])
        head = await self.monitor.head(session, p)
        state, error_code = completion_state(row, head, value, now)
        ack = {"id": row["id"], "revision": 1, "state": state, "request_id": request_id}
        await session.execute(
            text(
                "UPDATE orbit_agent_probe_request SET state=:state,completed_at=:now,"
                "error_code=:error,completion_hash=:hash,completion_ack=:ack "
                "WHERE tenant_id=:tenant AND id=:id"
            ),
            p
            | {
                "id": row["id"],
                "state": state,
                "now": now.replace(tzinfo=None),
                "error": error_code,
                "hash": intent,
                "ack": canonical(ack),
            },
        )
        await access.event(
            session,
            current,
            "EXECUTION_AGENT",
            p["agent"],
            row["agent_revision"],
            "PROBE_FINISHED",
            request_id,
            {"probe_request_id": row["id"], "state": state},
        )
        return ack
