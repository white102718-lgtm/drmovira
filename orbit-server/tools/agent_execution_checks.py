"""隔离真实SQL租约验收；不注册生产、不访问Meta、不证明广告写能力。"""

import asyncio
import re
from datetime import UTC
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from orbit_api.agent_execution_store import AgentExecutionStore, ExecutionDispatchAuthority
from orbit_api.agent_monitor_store import one, stamp
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.execution_agent_access import digest


class IsolatedDispatchAuthority(ExecutionDispatchAuthority):
    """仅固定UUID库和原完整accepted任务；测试权限撤销不能修改生产配置。"""

    def __init__(self, database, task_id):
        self.database = database
        self.task_id = task_id
        self.enabled = True
        self.events = {}

    async def guard(self, session, dispatch):
        url = session.get_bind().engine.url
        if (
            url.host != "127.0.0.1"
            or url.port != 13306
            or url.database != self.database
            or not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", self.database)
            or dispatch["task_id"] != self.task_id
            or (await session.execute(text("SELECT DATABASE()"))).scalar_one() != self.database
        ):
            raise OrbitError(503, "ISOLATED_DISPATCH_REJECTED", "只允许本轮隔离SQL来源")

    async def revalidate(self, session, dispatch, *, phase):
        await self.guard(session, dispatch)
        if not self.enabled:
            raise OrbitError(403, "PERMISSION_DENIED", "隔离权限已撤销")
        task = await one(
            session,
            "SELECT * FROM orbit_task WHERE tenant_id=:tenant_id AND id=:task_id FOR UPDATE",
            dispatch,
        )
        if (
            task is None
            or task["producer_kind"] != "ISOLATED_TEST"
            or task["manifest_phase"] != "COMPLETE"
        ):
            raise OrbitError(503, "ISOLATED_DISPATCH_REJECTED", "必须是真实完整受理任务")

    async def state(self, session, dispatch, state, request_id):
        values = dict(dispatch) | {"state": state, "event": str(uuid4()), "request": request_id}
        await session.execute(
            text(
                "UPDATE orbit_launch_execution_command SET "
                "state=:state,updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant_id AND "
                "task_id=:task_id AND node_id=:node_id"
            ),
            values,
        )
        await session.execute(
            text(
                "UPDATE orbit_task_node SET state=:state,updated_at=UTC_TIMESTAMP(3) WHERE "
                "tenant_id=:tenant_id AND task_id=:task_id AND id=:node_id"
            ),
            values,
        )
        await session.execute(
            text(
                "UPDATE orbit_task SET "
                "state=:state,revision=revision+1,latest_sequence=latest_sequence+1, "
                "latest_event_id=:event,updated_at=UTC_TIMESTAMP(3) "
                "WHERE tenant_id=:tenant_id AND id=:task_id"
            ),
            values,
        )
        await session.execute(
            text("""INSERT INTO orbit_task_event
            (tenant_id,task_id,event_id,sequence,task_revision,node_id,state,occurred_at,request_id)
            SELECT tenant_id,id,:event,latest_sequence,revision,:node_id,:state,
            UTC_TIMESTAMP(3),:request
            FROM orbit_task WHERE tenant_id=:tenant_id AND id=:task_id"""),
            values,
        )
        await session.execute(
            text("""INSERT INTO orbit_task_audit
            (id,tenant_id,task_id,actor_id,request_id,action,created_at)
            VALUES(:event,:tenant_id,:task_id,:actor_id,:request,'ISOLATED_AGENT_TRANSITION',UTC_TIMESTAMP(3))"""),
            values,
        )
        await session.execute(
            text("""INSERT INTO orbit_task_outbox(audit_id,tenant_id,task_id,created_at)
            VALUES(:event,:tenant_id,:task_id,UTC_TIMESTAMP(3))"""),
            values,
        )

    async def claim(self, session, dispatch, lease, request_id):
        await self.revalidate(session, dispatch, phase="claim")
        # 隔离样本真实写入原046尝试，不用新租约表代替旧运行事实。
        values = (
            dict(dispatch)
            | lease
            | {"authority": digest(["ISOLATED_SQL_NOT_SEND", dispatch["id"]])}
        )
        await session.execute(
            text("""INSERT INTO orbit_execution_attempt
            (tenant_id,task_id,node_id,preparation_id,attempt_no,fencing_token,claim_id,worker_id,
             execution_mode,command_hash,manifest_hash,source_hash,authority_hash,
             authorization_hash,
             actor_id,subject_id,owner_user_id,owner_team_id,auth_version,created_at)
            SELECT c.tenant_id,c.task_id,c.node_id,c.preparation_id,1,:fencing_token,:id,:agent_id,
            t.execution_mode,
            c.resolved_configuration_hash,p.manifest_hash,p.payload_hash,:authority,
            p.authorization_fingerprint,p.actor_id,p.subject_id,t.owner_user_id,t.owner_team_id,
            p.auth_version,UTC_TIMESTAMP(3)
            FROM orbit_launch_execution_command c JOIN orbit_launch_execution_preparation p
            ON p.tenant_id=c.tenant_id AND p.id=c.preparation_id JOIN orbit_task t
            ON t.tenant_id=c.tenant_id AND t.id=c.task_id
            WHERE c.tenant_id=:tenant_id AND c.task_id=:task_id AND c.node_id=:node_id
            AND c.attempt=0 AND c.state='QUEUED'"""),
            values,
        )
        await session.execute(
            text("""INSERT INTO orbit_execution_command_runtime
            (tenant_id,task_id,node_id,revision,active_attempt,fencing_token,claim_id,worker_id,
            lease_expires_at,created_at,updated_at)
            VALUES(:tenant_id,:task_id,:node_id,1,1,:fencing_token,:id,
            :agent_id,:expires_at,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"""),
            values,
        )
        await session.execute(
            text(
                "UPDATE orbit_launch_execution_command SET attempt=1 WHERE "
                "tenant_id=:tenant_id AND task_id=:task_id AND node_id=:node_id"
            ),
            values,
        )
        await session.execute(
            text(
                "UPDATE orbit_task_node SET attempt=1 WHERE tenant_id=:tenant_id AND "
                "task_id=:task_id AND id=:node_id"
            ),
            values,
        )
        await self.state(session, dispatch, "RUNNING", request_id)

    async def expire(self, session, dispatch, lease, request_id):
        await self.guard(session, dispatch)
        await self.state(session, dispatch, "UNKNOWN", request_id)
        await session.execute(
            text("""UPDATE orbit_execution_command_runtime SET
            revision=revision+1,unknown_since=UTC_TIMESTAMP(3),
            next_reconcile_at=UTC_TIMESTAMP(3)+INTERVAL 5 MINUTE,
            updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant_id AND task_id=:task_id
            AND node_id=:node_id
            """),
            dispatch,
        )

    async def record_event(self, session, dispatch, lease, event, *, historical):
        await self.guard(session, dispatch)
        if self.events.get(event["event_id"]) != canonical(event):
            raise OrbitError(422, "EVIDENCE_UNVERIFIED", "必须匹配本轮显式隔离观察")
        # 本专项只验证云端意图持久，不伪造平台成功/接受回执。
        if event["phase"] != "WRITE_INTENT" or event["state"] != "RUNNING":
            raise OrbitError(422, "EVIDENCE_UNVERIFIED", "本专项没有平台回读证据")
        if not historical:
            await self.revalidate(session, dispatch, phase="intent")
        from launch_execution_lease_store_checks import (
            IsolatedLeaseEvidenceAuthority,
            evidence_document,
        )

        from orbit_api.agent_monitor_contract import observed_time
        from orbit_api.launch_execution_lease_contract import (
            AttemptBinding,
            AttemptFact,
            EvidenceSource,
            FactKind,
            SendPhase,
        )
        from orbit_api.launch_execution_lease_store import ExecutionLeaseStore

        row = await one(
            session,
            "SELECT * FROM orbit_execution_attempt WHERE tenant_id=:tenant_id "
            "AND task_id=:task_id AND node_id=:node_id AND claim_id=:claim_id",
            dict(dispatch) | {"claim_id": lease["id"]},
        )
        binding = AttemptBinding(**{key: row[key] for key in AttemptBinding.__dataclass_fields__})
        occurred = observed_time(event["occurred_at"])
        proof = canonical(
            evidence_document(
                binding,
                event["event_id"],
                FactKind.WRITE_INTENT,
                SendPhase.BEFORE_DISPATCH,
                EvidenceSource.LOCAL_INTENT,
                occurred,
                None,
            )
        ).encode()
        evidence = {event["event_id"]: proof}
        authority = IsolatedLeaseEvidenceAuthority(
            self.database, {binding.node_id: binding}, evidence
        )
        import hashlib

        fact = AttemptFact(
            binding,
            event["event_id"],
            FactKind.WRITE_INTENT,
            SendPhase.BEFORE_DISPATCH,
            EvidenceSource.LOCAL_INTENT,
            hashlib.sha256(proof).hexdigest(),
            occurred,
        )
        await ExecutionLeaseStore(authority).append_verified_fact(
            session, binding.actor_id, fact, str(uuid4())
        )


def create_accepted_source(client, admin, headers):
    """运行器须先注入已有IsolatedExecutionProvider及ValidationProvider。"""
    if __package__:
        from .launch_execution_fixture import create_protocol_plan
    else:
        from launch_execution_fixture import create_protocol_plan
    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
    caps = client.get("/api/v1/launch-plans/capabilities", headers=headers).json()

    def write(rev):
        return headers | {
            "X-CSRF-Token": caps["csrf_token"],
            "If-Match": f'"{rev}"',
            "Idempotency-Key": str(uuid4()),
        }

    item = create_protocol_plan(admin, tenant, owner, team)
    result = client.post(
        f"/api/v1/launch-plans/{item['id']}/validate", headers=write(1), json=item["body"]
    )
    assert result.status_code == 200 and result.json()["valid"], "原预检未通过"
    accepted = client.post(
        f"/api/v1/launch-plans/{item['id']}/execute",
        headers=write(2),
        json={"hash": result.json()["hash"], "activate_ack": False},
    )
    assert accepted.status_code == 202, "原execute未受理"
    return accepted.json()


async def run_agent_execution_checks(sessions, database, der, grant, cases):
    """grant绑定原受理任务与本轮新鲜身份/能力；所有操作提交真实SQL事务。"""
    authority = IsolatedDispatchAuthority(database, grant["task_id"])
    store = AgentExecutionStore(authority)

    async def call(name, *args):
        async with sessions() as session, session.begin():
            return await getattr(store, name)(session, *args)

    # 故障由真实MySQL触发器产生；队列、业务审计与outbox必须整笔回滚。
    trigger = "isolated_agent_outbox_" + uuid4().hex[:16]
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON orbit_execution_agent_outbox "
                "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='ISOLATED_OUTBOX_FAILURE'"
            )
        )
    try:
        try:
            await call("enqueue", grant, str(uuid4()))
        except DBAPIError as error:
            assert error.orig.args[0] == 1644
        else:
            raise AssertionError("审计outbox故障未阻断派单")
    finally:
        async with sessions() as session, session.begin():
            await session.execute(text(f"DROP TRIGGER {trigger}"))
    async with sessions() as session:
        count = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM orbit_agent_dispatch "
                    "WHERE tenant_id=:tenant_id AND id=:id"
                ),
                grant,
            )
        ).scalar_one()
        events = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM orbit_execution_agent_event WHERE tenant_id=:tenant_id "
                    "AND resource_id=:agent_id AND action='EXECUTION_ENQUEUED'"
                ),
                grant,
            )
        ).scalar_one()
        assert count == events == 0
    cases.append("pythonAgentLeaseActualOutboxFailureRollsBackEnqueue")
    original = await call("enqueue", grant, str(uuid4()))
    assert await call("enqueue", grant, str(uuid4())) == original
    for change in (
        {"operation_id": str(uuid4())},
        {"versions": grant["versions"] | {"adapter_version": "changed-version"}},
        {"instruction": grant["instruction"] | {"policy_version": "changed-policy"}},
    ):
        try:
            await call("enqueue", grant | change, str(uuid4()))
        except OrbitError as error:
            assert error.code == "EXECUTION_DISPATCH_CONFLICT"
        else:
            raise AssertionError("同派单异内容重放未拒绝")
    async with sessions() as session:
        assert (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM orbit_execution_agent_event WHERE tenant_id=:tenant_id "
                    "AND resource_id=:agent_id AND action='EXECUTION_ENQUEUED'"
                ),
                grant,
            )
        ).scalar_one() == 1
    # 两个独立连接并发领取；真实共享clock锁让第二个请求只重放原租约。
    first, second = await asyncio.gather(
        call("next", der, str(uuid4())), call("next", der, str(uuid4()))
    )
    lease = first["lease"]
    assert second["lease"] == lease
    async with sessions() as session:
        attempts = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM orbit_execution_attempt WHERE tenant_id=:tenant_id "
                    "AND task_id=:task_id AND node_id=:node_id"
                ),
                grant,
            )
        ).scalar_one()
        leases = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM orbit_agent_execution_lease WHERE tenant_id=:tenant_id "
                    "AND dispatch_id=:id"
                ),
                grant,
            )
        ).scalar_one()
        assert attempts == leases == 1
    cases.append("pythonAgentLeaseActualConcurrentClaimHasOneAttempt")
    assert lease and lease["task_id"] == grant["task_id"]
    assert (await call("next", der, str(uuid4())))["lease"] == lease
    cases.append("pythonAgentLeaseActualAcceptedTaskClaimAndLostAckReplay")
    instruction = await call("command", der, lease["id"])
    assert instruction["command_hash"] == lease["command_hash"]
    async with sessions() as session:
        row = await one(
            session,
            "SELECT boot_id FROM orbit_agent_execution_lease WHERE tenant_id=:tenant_id AND id=:id",
            {"tenant_id": grant["tenant_id"], "id": lease["id"]},
        )
        now = (
            (await session.execute(text("SELECT UTC_TIMESTAMP(6)")))
            .scalar_one()
            .replace(tzinfo=UTC)
        )
    renew = {
        "agent_id": grant["agent_id"],
        "boot_id": row["boot_id"],
        "fencing_token": lease["fencing_token"],
    }
    renewed = await call("renew", der, lease["id"], renew, str(uuid4()))
    assert renewed["id"] == lease["id"] and renewed["fencing_token"] == lease["fencing_token"]
    try:
        await call(
            "renew",
            der,
            lease["id"],
            renew | {"fencing_token": lease["fencing_token"] + 1},
            str(uuid4()),
        )
    except OrbitError as error:
        assert error.code == "LEASE_FENCING_MISMATCH"
    else:
        raise AssertionError("旧代际未拒绝")
    cases.append("pythonAgentLeaseActualRenewAndFencingReject")
    event = {
        k: lease[k]
        for k in (
            "operation_id",
            "task_id",
            "node_id",
            "attempt_id",
            "profile_binding_id",
            "workflow_version",
            "adapter_version",
            "fencing_token",
        )
    } | {
        "event_id": str(uuid4()),
        "sequence": 1,
        "agent_id": grant["agent_id"],
        "boot_id": row["boot_id"],
        "phase": "WRITE_INTENT",
        "state": "RUNNING",
        "error_code": None,
        "retryable": False,
        "evidence_refs": [],
        "occurred_at": stamp(now),
    }
    authority.events[event["event_id"]] = canonical(event)
    ack = await call("events", der, {"events": [event]}, str(uuid4()))
    assert ack["accepted_event_ids"] == [event["event_id"]]
    replay = await call("events", der, {"events": [event]}, str(uuid4()))
    assert replay["duplicate_event_ids"] == [event["event_id"]]
    cases.append("pythonAgentLeaseActualIntentCommitAndExactReplay")
    # 已领取后内部outbox重复投递仍回原成功结果，不能建立第二次尝试。
    assert await call("enqueue", grant, str(uuid4())) == original
    authority.enabled = False
    for name, args in [
        ("enqueue", (grant, str(uuid4()))),
        ("command", (der, lease["id"])),
        ("events", (der, {"events": [event]}, str(uuid4()))),
    ]:
        try:
            await call(name, *args)
        except OrbitError as error:
            assert error.code == "PERMISSION_DENIED"
        else:
            raise AssertionError("撤权未阻断")
    cases.append("pythonAgentLeaseActualRevocationBlocksCommandAndIntentReplay")
    authority.enabled = True
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                "UPDATE orbit_agent_execution_lease "
                "SET expires_at=UTC_TIMESTAMP(6)-INTERVAL 1 MICROSECOND "
                "WHERE tenant_id=:tenant_id AND id=:lease"
            ),
            dict(grant) | {"lease": lease["id"]},
        )
    assert (await call("next", der, str(uuid4())))["lease"] is None
    historical = await call("events", der, {"events": [event]}, str(uuid4()))
    assert (
        historical["historical_event_ids"]
        == historical["duplicate_event_ids"]
        == [event["event_id"]]
    )
    assert historical["accepted_event_ids"] == []
    for name, args in [
        ("command", (der, lease["id"])),
        ("renew", (der, lease["id"], renew, str(uuid4()))),
    ]:
        try:
            await call(name, *args)
        except OrbitError as error:
            assert error.code == "LEASE_EXPIRED"
        else:
            raise AssertionError("过期租约仍能发送或续期")
    async with sessions() as session:
        row = await one(
            session,
            "SELECT d.state dispatch_state,c.state command_state,t.state task_state,"
            "r.unknown_since FROM orbit_agent_dispatch d "
            "JOIN orbit_launch_execution_command c ON c.tenant_id=d.tenant_id "
            "AND c.task_id=d.task_id AND c.node_id=d.node_id "
            "JOIN orbit_task t ON t.tenant_id=d.tenant_id AND t.id=d.task_id "
            "JOIN orbit_execution_command_runtime r ON r.tenant_id=d.tenant_id "
            "AND r.task_id=d.task_id AND r.node_id=d.node_id "
            "WHERE d.tenant_id=:tenant_id AND d.id=:id",
            grant,
        )
        assert row["dispatch_state"] == row["command_state"] == row["task_state"] == "UNKNOWN"
        assert row["unknown_since"] is not None
        assert (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM orbit_execution_attempt WHERE tenant_id=:tenant_id "
                    "AND task_id=:task_id AND node_id=:node_id"
                ),
                grant,
            )
        ).scalar_one() == 1
    cases.append("pythonAgentLeaseActualExpiryUnknownAndHistoricalReplayCannotRestore")
    return {"task_id": grant["task_id"], "lease_id": lease["id"]}
