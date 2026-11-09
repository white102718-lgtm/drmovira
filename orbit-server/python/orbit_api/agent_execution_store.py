"""任务绑定设备租约；默认没有生产权威来源时关闭，绝不由队列快照自证权限。"""

from abc import ABC, abstractmethod
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import text

from orbit_api import execution_agent_access as access
from orbit_api.agent_execution_contract import LEASE_SECONDS, MAX_FENCE, instruction_hash
from orbit_api.agent_monitor_store import (
    AgentMonitorStore,
    batch_binding_identities,
    one,
    stamp,
    utc,
)
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_contract import uuid_value


class ExecutionDispatchAuthority(ABC):
    """仅服务器受控注入。实现必须锁验真实权限、冻结任务、资源及共享目标锁。"""

    @abstractmethod
    async def revalidate(self, session, dispatch, *, phase):
        """每次enqueue/next/renew/command复验当前权限、预算、DAG和来源；失败抛错。"""

    @abstractmethod
    async def claim(self, session, dispatch, lease, request_id):
        """同事务持久首次attempt/runtime、任务节点RUNNING与任务审计/outbox。"""

    @abstractmethod
    async def expire(self, session, dispatch, lease, request_id):
        """同事务将真实task/node/runtime转UNKNOWN并写审计，不能仅清Profile锁。"""

    @abstractmethod
    async def record_event(self, session, dispatch, lease, event, *, historical):
        """核验证据引用/原尝试并接现有事实链；历史绝不推动状态，当前回读不可自报成功。"""


def unavailable():
    raise OrbitError(503, "EXECUTION_AUTHORITY_UNAVAILABLE", "真实执行权威来源尚未接通")


def reject(code, message, status=409):
    raise OrbitError(status, code, message)


class AgentExecutionStore:
    def __init__(self, authority=None):
        self.authority = authority
        self.monitor = AgentMonitorStore()

    def require_authority(self):
        if not isinstance(self.authority, ExecutionDispatchAuthority):
            unavailable()

    async def _command_row(self, session, dispatch):
        row = await one(
            session,
            """SELECT c.*, p.state preparation_state
            FROM orbit_launch_execution_command c JOIN orbit_launch_execution_preparation p
            ON p.tenant_id=c.tenant_id AND p.id=c.preparation_id AND p.task_id=c.task_id
            JOIN orbit_launch_execution_acceptance x ON x.tenant_id=c.tenant_id AND
            x.task_id=c.task_id
            WHERE c.tenant_id=:tenant_id AND c.task_id=:task_id AND c.node_id=:node_id
            FOR UPDATE""",
            dispatch,
        )
        if row is None or row["preparation_state"] != "ACCEPTED":
            reject("EXECUTION_SOURCE_UNAVAILABLE", "未找到完整受理的冻结任务命令")
        instruction = _decode(dispatch["instruction_json"])
        if (
            row["account_id"] != instruction["account_id"]
            or row["node_key"] != instruction["node_key"]
        ):
            reject("EXECUTION_SOURCE_MISMATCH", "冻结指令与真实命令不一致")
        return row

    async def enqueue(self, session, grant, request_id):
        """无HTTP入口；调用者来自可信服务器来源，仍逐次复验而非信任字典。"""
        self.require_authority()
        dispatch = dict(grant)
        for key in (
            "tenant_id",
            "id",
            "task_id",
            "node_id",
            "operation_id",
            "agent_id",
            "profile_binding_id",
        ):
            uuid_value(dispatch[key], "/" + key)
        instruction = dict(dispatch.pop("instruction"))
        if set(instruction) != {
            "account_id",
            "external_account_id",
            "node_key",
            "kind",
            "target",
            "plan",
            "manual",
            "policy_version",
            "submission_group_id",
            "execution_manifest_id",
            "execution_manifest_hash",
        }:
            reject("EXECUTION_INSTRUCTION_INVALID", "冻结指令字段不完整", 422)
        if instruction["kind"] == "CREATE" and (
            instruction["execution_manifest_id"] is None
            or instruction["execution_manifest_hash"] is None
        ):
            reject("EXECUTION_MANIFEST_REQUIRED", "创建必须绑定完整冻结素材清单", 422)
        dispatch["instruction_json"] = canonical(instruction)
        dispatch["versions_json"] = canonical(dispatch.pop("versions"))
        dispatch["command_hash"] = instruction_hash(instruction)
        current = SimpleNamespace(
            tenant_id=dispatch["tenant_id"],
            actor_id=dispatch["actor_id"],
            subject_id=dispatch["agent_id"],
        )
        # 与设备领取保持account→device clock→task的锁顺序，也串行内部outbox重放。
        await access.clock(session, current, write=True)
        await self.authority.revalidate(session, dispatch, phase="enqueue")
        prior = await one(
            session,
            "SELECT * FROM orbit_agent_dispatch WHERE tenant_id=:tenant_id AND "
            "(id=:id OR (task_id=:task_id AND node_id=:node_id)) FOR UPDATE",
            dispatch,
        )
        if prior is not None:
            frozen = (
                "tenant_id",
                "id",
                "task_id",
                "node_id",
                "operation_id",
                "agent_id",
                "profile_binding_id",
                "binding_revision",
                "actor_id",
                "entity_type",
                "versions_json",
                "instruction_json",
                "command_hash",
            )

            def intent(row):
                return {
                    key: _decode(row[key]) if key.endswith("_json") else row[key] for key in frozen
                }

            if canonical(intent(prior)) != canonical(intent(dispatch)):
                reject("EXECUTION_DISPATCH_CONFLICT", "同一派单或命令不能改变冻结意图")
            return {"id": prior["id"], "command_hash": prior["command_hash"]}
        source = await self._command_row(session, dispatch)
        if source["state"] != "QUEUED" or source["attempt"] != 0:
            reject("EXECUTION_ALREADY_ATTEMPTED", "命令已经领取或结果未知，禁止重派")
        await session.execute(
            text("""INSERT INTO orbit_agent_dispatch
            (tenant_id,id,task_id,node_id,operation_id,agent_id,profile_binding_id,binding_revision,
            actor_id,entity_type,versions_json,instruction_json,command_hash,state,created_at)
            VALUES(:tenant_id,:id,:task_id,:node_id,:operation_id,:agent_id,:profile_binding_id,
            :binding_revision,:actor_id,:entity_type,:versions_json,:instruction_json,:command_hash,
            'QUEUED',UTC_TIMESTAMP(6))"""),
            dispatch,
        )
        await self._event(session, dispatch, request_id, "EXECUTION_ENQUEUED")
        return {"id": dispatch["id"], "command_hash": dispatch["command_hash"]}

    async def _event(self, session, dispatch, request_id, action):
        current = SimpleNamespace(
            tenant_id=dispatch["tenant_id"],
            actor_id=dispatch["actor_id"],
            subject_id=dispatch["agent_id"],
        )
        agent = await one(
            session,
            "SELECT revision FROM orbit_execution_agent WHERE tenant_id=:tenant_id AND "
            "id=:agent_id",
            dispatch,
        )
        await access.event(
            session,
            current,
            "EXECUTION_AGENT",
            dispatch["agent_id"],
            agent["revision"],
            action,
            request_id,
            {"dispatch_id": dispatch["id"]},
        )

    async def _device(self, session, der):
        self.require_authority()
        p, now = await self.monitor.authenticate(session, der, write=True)
        head = await self.monitor.head(session, p)
        agent = await one(
            session,
            "SELECT state FROM orbit_execution_agent WHERE tenant_id=:tenant AND id=:agent "
            "FOR SHARE",
            p,
        )
        if (
            head is None
            or head["recovery_streak"] != 2
            or agent["state"] != "READY"
            or now - utc(head["received_at"]) >= timedelta(seconds=45)
        ):
            reject("AGENT_NOT_READY", "设备不在新鲜READY状态")
        return p, now, head

    async def _verify(self, session, dispatch, *, phase):
        await self.authority.revalidate(session, dispatch, phase=phase)
        source = await self._command_row(session, dispatch)
        expected = {"QUEUED"} if phase == "next" else {"RUNNING", "ACCEPTED", "VERIFYING"}
        if source["state"] not in expected:
            reject("EXECUTION_STATE_CHANGED", "命令状态不再允许发送")
        binding = await one(
            session,
            """SELECT b.*,a.external_id account_external_id FROM orbit_profile_binding b
            JOIN orbit_ad_account a ON a.tenant_id=b.tenant_id AND a.id=b.account_id
            WHERE b.tenant_id=:tenant_id AND b.id=:profile_binding_id AND b.agent_id=:agent_id
            AND b.revision=:binding_revision AND b.unbound_at IS NULL AND a.unbound_at IS NULL
            AND b.owner_user_id=a.owner_user_id AND b.owner_team_id=a.owner_team_id FOR SHARE""",
            dispatch,
        )
        instruction = _decode(dispatch["instruction_json"])
        if (
            binding is None
            or binding["account_id"] != source["account_id"]
            or instruction["external_account_id"] != binding["account_external_id"]
            or instruction_hash(instruction) != dispatch["command_hash"]
        ):
            reject("EXECUTION_BINDING_CHANGED", "关联或冻结指令已变化")
        identities = await batch_binding_identities(session, dispatch["tenant_id"], [binding])
        if identities[binding["id"]]["identity_state"] != "VALID":
            reject("IDENTITY_UNVERIFIED", "当前Profile身份未通过新鲜核验")
        from orbit_api.agent_capability_store import require_verified

        await require_verified(
            session,
            tenant_id=dispatch["tenant_id"],
            agent_id=dispatch["agent_id"],
            profile_binding_id=binding["id"],
            operation_kind=instruction["kind"],
            entity_type=dispatch["entity_type"],
            versions=_decode(dispatch["versions_json"]),
        )
        return binding

    def _public(self, dispatch, lease):
        versions = _decode(dispatch["versions_json"])
        return {k: lease[k] for k in ("id", "attempt_id", "fencing_token")} | {
            "operation_id": dispatch["operation_id"],
            "task_id": dispatch["task_id"],
            "node_id": dispatch["node_id"],
            "profile_binding_id": dispatch["profile_binding_id"],
            "expires_at": stamp(lease["expires_at"]),
            "workflow_version": versions["workflow_version"],
            "adapter_version": versions["adapter_version"],
            "command_hash": dispatch["command_hash"],
        }

    async def next(self, session, der, request_id):
        p, now, head = await self._device(session, der)
        # 设备共享clock已FOR UPDATE，所有领取串行；失效租约不可从队列再次领取。
        rows = (
            (
                await session.execute(
                    text("""SELECT l.*,d.state dispatch_state FROM orbit_agent_execution_lease l
            JOIN orbit_agent_dispatch d ON d.tenant_id=l.tenant_id AND d.id=l.dispatch_id
            WHERE l.tenant_id=:tenant AND l.agent_id=:agent AND d.state='LEASED' FOR UPDATE"""),
                    p,
                )
            )
            .mappings()
            .all()
        )
        for old in rows:
            if utc(old["expires_at"]) <= now:
                dispatch = await one(
                    session,
                    "SELECT * FROM orbit_agent_dispatch WHERE tenant_id=:tenant AND id=:id "
                    "FOR UPDATE",
                    p | {"id": old["dispatch_id"]},
                )
                await self.authority.expire(session, dispatch, old, request_id)
                source = await self._command_row(session, dispatch)
                if source["state"] != "UNKNOWN":
                    reject("EXECUTION_EXPIRY_UNCONFIRMED", "原任务过期结果尚未持久确认")
                await self._event(session, dispatch, request_id, "EXECUTION_LEASE_EXPIRED")
                await session.execute(
                    text(
                        "UPDATE orbit_agent_dispatch SET state='UNKNOWN' WHERE "
                        "tenant_id=:tenant AND id=:id"
                    ),
                    p | {"id": old["dispatch_id"]},
                )
        active = [r for r in rows if utc(r["expires_at"]) > now]
        # 丢失领取响应只能回到原租约，不创建新尝试；重启不接管旧启动。
        if active:
            same = next(
                (
                    r
                    for r in active
                    if r["boot_id"] == head["boot_id"] and r["command_received_at"] is None
                ),
                None,
            )
            if same:
                dispatch = await one(
                    session,
                    "SELECT * FROM orbit_agent_dispatch WHERE tenant_id=:tenant AND id=:id "
                    "FOR UPDATE",
                    p | {"id": same["dispatch_id"]},
                )
                await self._verify(session, dispatch, phase="command")
                return {"lease": self._public(dispatch, same), "retry_after_seconds": 20}
        if len(active) >= 2:
            return {"lease": None, "retry_after_seconds": 20}
        dispatch = await one(
            session,
            "SELECT * FROM orbit_agent_dispatch WHERE tenant_id=:tenant AND agent_id=:agent "
            "AND state='QUEUED' ORDER BY created_at,id LIMIT 1 FOR UPDATE",
            p,
        )
        if dispatch is None:
            return {"lease": None, "retry_after_seconds": 20}
        binding = await self._verify(session, dispatch, phase="next")
        profile = binding["profile_external_id"]
        # UNKNOWN保留Profile写隔离；过期不是允许另一个命令再次提交的证明。
        occupied = await one(
            session,
            """SELECT l.id FROM orbit_agent_execution_lease l JOIN orbit_agent_dispatch d
            ON d.tenant_id=l.tenant_id AND d.id=l.dispatch_id WHERE
            l.tenant_id=:tenant AND l.agent_id=:agent
            AND l.profile_external_id=:profile AND d.state IN ('LEASED','UNKNOWN')
            LIMIT 1 FOR UPDATE""",
            p | {"profile": profile},
        )
        if occupied:
            reject("PROFILE_BUSY", "Profile已有工作流或未知结果，不能强占")
        await session.execute(
            text("""INSERT INTO orbit_agent_profile_fence
            (tenant_id,agent_id,profile_external_id,fencing_token)
            VALUES(:tenant,:agent,:profile,0)
            ON DUPLICATE KEY UPDATE fencing_token=fencing_token"""),
            p | {"profile": profile},
        )
        fence = await one(
            session,
            "SELECT fencing_token FROM orbit_agent_profile_fence WHERE tenant_id=:tenant "
            "AND agent_id=:agent AND profile_external_id=:profile FOR UPDATE",
            p | {"profile": profile},
        )
        if fence["fencing_token"] >= MAX_FENCE:
            reject("FENCING_EXHAUSTED", "Profile代际计数已达上限")
        lease = {
            "id": str(uuid4()),
            "attempt_id": str(uuid4()),
            "fencing_token": fence["fencing_token"] + 1,
            "expires_at": now + timedelta(seconds=LEASE_SECONDS),
        }
        await self.authority.claim(session, dispatch, lease, request_id)
        source = await self._command_row(session, dispatch)
        if source["state"] != "RUNNING" or source["attempt"] != 1:
            reject("EXECUTION_CLAIM_UNCONFIRMED", "真实命令领取尚未确认")
        await session.execute(
            text(
                "UPDATE orbit_agent_profile_fence SET fencing_token=:fencing_token WHERE "
                "tenant_id=:tenant AND agent_id=:agent AND profile_external_id=:profile"
            ),
            p | {"profile": profile} | lease,
        )
        await session.execute(
            text("""INSERT INTO orbit_agent_execution_lease
            (tenant_id,id,dispatch_id,agent_id,boot_id,profile_external_id,attempt_id,
            fencing_token,expires_at,created_at)
            VALUES(:tenant,:id,:dispatch,:agent,:boot,:profile,:attempt_id,:fencing_token,:expires_at,:now)"""),
            p
            | lease
            | {"dispatch": dispatch["id"], "boot": head["boot_id"], "profile": profile, "now": now},
        )
        await session.execute(
            text(
                "UPDATE orbit_agent_dispatch SET state='LEASED' WHERE tenant_id=:tenant_id "
                "AND id=:id"
            ),
            dispatch,
        )
        await self._event(session, dispatch, request_id, "EXECUTION_LEASED")
        return {"lease": self._public(dispatch, lease), "retry_after_seconds": 20}

    async def _current(self, session, der, identifier, phase):
        p, now, head = await self._device(session, der)
        identifier = uuid_value(identifier, "/id")
        lease = await one(
            session,
            "SELECT * FROM orbit_agent_execution_lease WHERE tenant_id=:tenant AND "
            "agent_id=:agent AND id=:id FOR UPDATE",
            p | {"id": identifier},
        )
        if lease is None:
            reject("NOT_FOUND", "租约不存在", 404)
        if lease["boot_id"] != head["boot_id"] or utc(lease["expires_at"]) <= now:
            reject("LEASE_EXPIRED", "租约过期或设备已重新启动")
        dispatch = await one(
            session,
            "SELECT * FROM orbit_agent_dispatch WHERE tenant_id=:tenant AND id=:id FOR UPDATE",
            p | {"id": lease["dispatch_id"]},
        )
        if dispatch["state"] != "LEASED":
            reject("LEASE_INACTIVE", "租约不再允许新动作")
        await self._verify(session, dispatch, phase=phase)
        return p, now, head, dict(lease), dispatch

    async def renew(self, session, der, identifier, value, request_id):
        p, now, head, lease, dispatch = await self._current(session, der, identifier, "renew")
        if (
            value["agent_id"] != p["agent"]
            or value["boot_id"] != head["boot_id"]
            or value["fencing_token"] != lease["fencing_token"]
        ):
            reject("LEASE_FENCING_MISMATCH", "续租不属于当前设备启动和代际")
        lease["expires_at"] = now + timedelta(seconds=LEASE_SECONDS)
        await session.execute(
            text(
                "UPDATE orbit_agent_execution_lease SET expires_at=:expires_at WHERE "
                "tenant_id=:tenant AND id=:id"
            ),
            p | lease,
        )
        changed = await session.execute(
            text(
                "UPDATE orbit_execution_command_runtime SET lease_expires_at=:expires_at, "
                "revision=revision+1,updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant_id "
                "AND task_id=:task_id AND node_id=:node_id AND claim_id=:lease_id "
                "AND worker_id=:agent_id AND active_attempt=1 AND fencing_token=:fence"
            ),
            dict(dispatch)
            | {
                "lease_id": lease["id"],
                "expires_at": lease["expires_at"],
                "fence": lease["fencing_token"],
            },
        )
        if changed.rowcount != 1:
            reject("EXECUTION_RUNTIME_MISMATCH", "原命令租约关联已变化")
        await self._event(session, dispatch, request_id, "EXECUTION_LEASE_RENEWED")
        return self._public(dispatch, lease)

    async def command(self, session, der, identifier):
        _, _, _, lease, dispatch = await self._current(session, der, identifier, "command")
        await session.execute(
            text(
                "UPDATE orbit_agent_execution_lease SET "
                "command_received_at=COALESCE(command_received_at,UTC_TIMESTAMP(6)) "
                "WHERE tenant_id=:tenant_id AND id=:id"
            ),
            {"tenant_id": dispatch["tenant_id"], "id": lease["id"]},
        )
        return _decode(dispatch["instruction_json"]) | {
            "lease_id": lease["id"],
            "command_hash": dispatch["command_hash"],
            "allowed_until": stamp(lease["expires_at"]),
        }

    async def events(self, session, der, value, request_id):
        """原证书有效即可补历史；只有当前有效租约的WRITE_INTENT才允许新写。"""
        self.require_authority()
        p, now = await self.monitor.authenticate(session, der, write=True)
        head = await self.monitor.head(session, p)
        ack = {
            "accepted_event_ids": [],
            "duplicate_event_ids": [],
            "rejected_event_ids": [],
            "historical_event_ids": [],
            "request_id": request_id,
        }
        from orbit_api.agent_monitor_contract import observed_time

        for event in value["events"]:
            if event["agent_id"] != p["agent"]:
                reject("DEVICE_AGENT_MISMATCH", "事件不属于设备", 403)
            lease = await one(
                session,
                """SELECT * FROM orbit_agent_execution_lease
                WHERE tenant_id=:tenant AND agent_id=:agent AND attempt_id=:attempt FOR UPDATE""",
                p | {"attempt": event["attempt_id"]},
            )
            if lease is None:
                reject("NOT_FOUND", "原尝试不存在", 404)
            dispatch = await one(
                session,
                "SELECT * FROM orbit_agent_dispatch WHERE tenant_id=:tenant AND id=:id FOR UPDATE",
                p | {"id": lease["dispatch_id"]},
            )
            versions = _decode(dispatch["versions_json"])
            expected = {
                k: dispatch[k] for k in ("operation_id", "task_id", "node_id", "profile_binding_id")
            } | {
                "boot_id": lease["boot_id"],
                "fencing_token": lease["fencing_token"],
                "workflow_version": versions["workflow_version"],
                "adapter_version": versions["adapter_version"],
            }
            if any(event[k] != v for k, v in expected.items()):
                reject("EVENT_BINDING_MISMATCH", "事件不能混用尝试或代际")
            occurred = observed_time(event["occurred_at"])
            if not utc(lease["created_at"]) <= occurred <= now:
                reject("EVENT_TIME_INVALID", "事件时间不属于原尝试")
            historical = (
                utc(lease["expires_at"]) <= now
                or dispatch["state"] != "LEASED"
                or head is None
                or head["boot_id"] != lease["boot_id"]
            )
            if not historical:
                try:
                    await self._current(session, der, lease["id"], "command")
                except OrbitError as error:
                    # 撤权后仍保留原设备已经发生的观察，但绝不返回可发送的意图ACK。
                    if event["phase"] == "WRITE_INTENT" or error.status not in {403, 409, 422}:
                        raise
                    historical = True
            prior = await one(
                session,
                "SELECT * FROM orbit_agent_execution_event WHERE tenant_id=:tenant AND "
                "event_id=:id FOR SHARE",
                p | {"id": event["event_id"]},
            )
            if prior:
                if prior["input_hash"] != access.digest(event):
                    reject("EVENT_REPLAY_CONFLICT", "相同事件标识内容发生变化")
                ack["duplicate_event_ids"].append(event["event_id"])
                if historical or prior["historical"]:
                    ack["historical_event_ids"].append(event["event_id"])
                continue
            if event["sequence"] != lease["last_sequence"] + 1:
                reject("EVENT_SEQUENCE_CONFLICT", "事件必须按本租约连续序号补传")
            if event["phase"] == "WRITE_INTENT" and (
                event["state"] != "RUNNING" or event["retryable"]
            ):
                reject("WRITE_INTENT_INVALID", "写意图不能声称成功或允许重发")
            # 证据来源独立验证及Task状态变更必须与ACK同事务；不根据事件state直接成功。
            await self.authority.record_event(
                session, dispatch, lease, event, historical=historical
            )
            if not historical:
                source = await self._command_row(session, dispatch)
                if source["state"] in {"SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"}:
                    terminal = "UNKNOWN" if source["state"] == "UNKNOWN" else "COMPLETED"
                    await session.execute(
                        text(
                            "UPDATE orbit_agent_dispatch SET state=:state WHERE "
                            "tenant_id=:tenant_id AND id=:id"
                        ),
                        dict(dispatch) | {"state": terminal},
                    )
            await session.execute(
                text("""INSERT INTO orbit_agent_execution_event
                (tenant_id,event_id,lease_id,sequence_no,input_hash,event_json,
                historical,created_at)
                VALUES(:tenant,:event,:lease,:seq,:hash,:json,:historical,:now)"""),
                p
                | {
                    "event": event["event_id"],
                    "lease": lease["id"],
                    "seq": event["sequence"],
                    "hash": access.digest(event),
                    "json": canonical(event),
                    "historical": historical,
                    "now": now,
                },
            )
            await session.execute(
                text(
                    "UPDATE orbit_agent_execution_lease SET last_sequence=:seq WHERE "
                    "tenant_id=:tenant AND id=:id"
                ),
                p | {"seq": event["sequence"], "id": lease["id"]},
            )
            await self._event(session, dispatch, request_id, "EXECUTION_EVENT_RECORDED")
            ack["accepted_event_ids"].append(event["event_id"])
            if historical:
                ack["historical_event_ids"].append(event["event_id"])
        return ack
