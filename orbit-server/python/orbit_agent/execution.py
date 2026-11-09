"""明确注入已验收Adapter的单次广告执行消费者；默认关闭，无隐式真实平台写入。"""

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from orbit_agent.adspower_status import ProbeError
from orbit_agent.execution_spool import ExecutionSpool as ExecutionSpool
from orbit_agent.protocol import exact, integer, timestamp, uuid

LEASE_KEYS = {
    "id",
    "operation_id",
    "task_id",
    "node_id",
    "attempt_id",
    "profile_binding_id",
    "expires_at",
    "fencing_token",
    "workflow_version",
    "adapter_version",
    "command_hash",
}
INSTRUCTION_KEYS = {
    "lease_id",
    "command_hash",
    "account_id",
    "external_account_id",
    "node_key",
    "kind",
    "target",
    "plan",
    "manual",
    "policy_version",
    "submission_group_id",
    "allowed_until",
    "execution_manifest_id",
    "execution_manifest_hash",
}


def instruction_hash(value):
    """稳定命令摘要排除租约ID和时限；续租不能改变冻结业务输入。"""
    stable = {
        k: v for k, v in value.items() if k not in {"lease_id", "command_hash", "allowed_until"}
    }
    return hashlib.sha256(
        json.dumps(
            stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def instant(value):
    timestamp(value)
    return datetime.fromisoformat(value).astimezone(UTC)


def validate_lease(lease):
    exact(lease, LEASE_KEYS)
    for key in ("id", "operation_id", "task_id", "node_id", "attempt_id", "profile_binding_id"):
        uuid(lease[key])
    integer(lease["fencing_token"])
    instant(lease["expires_at"])
    for key in ("workflow_version", "adapter_version"):
        if type(lease[key]) is not str or not 1 <= len(lease[key]) <= 64:
            raise ProbeError("EXECUTION_LEASE_INVALID")
    if type(lease["command_hash"]) is not str or not re.fullmatch(
        "[a-f0-9]{64}", lease["command_hash"]
    ):
        raise ProbeError("EXECUTION_LEASE_INVALID")


def validate_instruction(value, lease):
    exact(value, INSTRUCTION_KEYS)
    if (
        value["lease_id"] != lease["id"]
        or value["command_hash"] != lease["command_hash"]
        or instruction_hash(value) != lease["command_hash"]
    ):
        raise ProbeError("EXECUTION_COMMAND_INVALID")
    uuid(value["account_id"])
    instant(value["allowed_until"])
    if value["kind"] not in {
        "CREATE",
        "BUDGET_SET",
        "PAUSE",
        "ENABLE",
        "DELETE",
        "ARCHIVE",
        "VERIFY",
    }:
        raise ProbeError("EXECUTION_COMMAND_INVALID")
    if type(value["external_account_id"]) is not str or not re.fullmatch(
        "[0-9]{1,64}", value["external_account_id"]
    ):
        raise ProbeError("EXECUTION_COMMAND_INVALID")
    for key, limit in (("node_key", 512), ("policy_version", 64)):
        if type(value[key]) is not str or not 1 <= len(value[key]) <= limit:
            raise ProbeError("EXECUTION_COMMAND_INVALID")
    for key in ("target", "plan", "manual"):
        if value[key] is not None and type(value[key]) is not dict:
            raise ProbeError("EXECUTION_COMMAND_INVALID")
    for key in ("submission_group_id", "execution_manifest_id"):
        if value[key] is not None:
            uuid(value[key])
    digest = value["execution_manifest_hash"]
    if digest is not None and (type(digest) is not str or not re.fullmatch("[a-f0-9]{64}", digest)):
        raise ProbeError("EXECUTION_COMMAND_INVALID")
    if value["kind"] == "CREATE" and (not value["execution_manifest_id"] or not digest):
        raise ProbeError("EXECUTION_MANIFEST_REQUIRED")


@dataclass(frozen=True)
class PreparedProfile:
    """受控Adapter返回的独占使用句柄；人工已打开的窗口不属于本流程。"""

    opened_by_workflow: bool
    exclusive: bool

    def __post_init__(self):
        if type(self.opened_by_workflow) is not bool or type(self.exclusive) is not bool:
            raise ProbeError("PROFILE_OWNERSHIP_INVALID")


class ExecutionConsumer:
    """Adapter须实现prepare/validate/submit/close；validate核身份、能力、页面和冻结素材。"""

    def __init__(self, device, spool, boot_id, *, adapter=None):
        self.device, self.spool, self.boot_id = device, spool, uuid(boot_id)
        self.adapter = adapter

    async def _ack(self, event, *, historical=False):
        ack = await self.device.report_events([event])
        names = {
            "accepted_event_ids",
            "duplicate_event_ids",
            "rejected_event_ids",
            "historical_event_ids",
        }
        exact(ack, names | {"request_id"})
        uuid(ack["request_id"])
        all_ids = []
        for name in names:
            if type(ack[name]) is not list or len(ack[name]) > 100:
                raise ProbeError("EXECUTION_ACK_INVALID")
            for identifier in ack[name]:
                uuid(identifier)
            if len(set(ack[name])) != len(ack[name]):
                raise ProbeError("EXECUTION_ACK_INVALID")
            if name != "historical_event_ids":
                all_ids.extend(ack[name])
        if len(all_ids) != len(set(all_ids)) or set(all_ids) != {event["event_id"]}:
            raise ProbeError("EXECUTION_ACK_INVALID")
        eligible = ack["accepted_event_ids"] + ack["duplicate_event_ids"]
        if not set(ack["historical_event_ids"]) <= set(eligible):
            raise ProbeError("EXECUTION_ACK_INVALID")
        if event["event_id"] not in eligible or (
            not historical and event["event_id"] in ack["historical_event_ids"]
        ):
            raise ProbeError("EXECUTION_INTENT_UNCONFIRMED")
        self.spool.acknowledge(event)

    async def flush_history(self):
        """只补传已落盘原事件，原boot/attempt/fence不变；历史ACK绝不恢复发送权。"""
        count = 0
        for event in self.spool.pending():
            try:
                await self._ack(event, historical=True)
                count += 1
            except Exception:
                break
        return count

    def _event(self, lease, sequence, phase, state, *, evidence=None, error=None):
        return {
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
            "sequence": sequence,
            "agent_id": self.spool.agent_id,
            "boot_id": self.boot_id,
            "phase": phase,
            "state": state,
            "error_code": error,
            "retryable": False,
            "evidence_refs": evidence or [],
            "occurred_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

    async def run_once(self):
        """未配置可信执行器时不领取；网络/进程异常从未承诺安全自动重试。"""
        if self.adapter is None:
            return {"state": "BLOCKED_AUTH", "error_code": "EXECUTION_ADAPTER_UNVERIFIED"}
        profile = None
        keeper = None
        lease = None
        instruction = None
        started = False
        intent = None
        lost = False
        deadline = None

        def guard():
            if instruction is not None:
                validate_instruction(instruction, lease)
            if (
                lost
                or datetime.now(UTC) >= instant(lease["expires_at"])
                or (deadline is not None and asyncio.get_running_loop().time() >= deadline)
                or (instruction and datetime.now(UTC) >= instant(instruction["allowed_until"]))
            ):
                raise ProbeError("EXECUTION_LEASE_EXPIRED")

        async def renew():
            nonlocal lease, instruction, lost, deadline
            try:
                while True:
                    await asyncio.sleep(20)
                    renewed = await self.device.renew_lease(
                        lease["id"], self.boot_id, lease["fencing_token"]
                    )
                    validate_lease(renewed)
                    if {k: v for k, v in renewed.items() if k != "expires_at"} != {
                        k: v for k, v in lease.items() if k != "expires_at"
                    }:
                        raise ProbeError("EXECUTION_LEASE_INVALID")
                    refreshed = await self.device.execution_command(renewed["id"])
                    validate_instruction(refreshed, renewed)
                    # 发送时限只能从服务端重新获取，不能因本地续租自行延长。
                    lease, instruction = renewed, refreshed
                    deadline = asyncio.get_running_loop().time() + min(
                        120, (instant(lease["expires_at"]) - datetime.now(UTC)).total_seconds()
                    )
            except Exception:
                lost = True

        try:
            reply = await self.device.next_lease()
            exact(reply, {"lease", "retry_after_seconds"})
            lease = reply["lease"]
            if lease is None:
                return {"state": "IDLE", "error_code": None}
            validate_lease(lease)
            deadline = asyncio.get_running_loop().time() + min(
                120, (instant(lease["expires_at"]) - datetime.now(UTC)).total_seconds()
            )
            guard()
            instruction = await self.device.execution_command(lease["id"])
            validate_instruction(instruction, lease)
            guard()
            if not self.spool.begin(lease):
                prior = self.spool.attempt(lease["attempt_id"])
                state = (
                    prior["state"]
                    if prior["state"] in {"NEEDS_HUMAN", "BLOCKED_AUTH"}
                    else "UNKNOWN"
                )
                return {"state": state, "error_code": "EXECUTION_RECOVERY_REQUIRED"}
            started = True
            keeper = asyncio.create_task(renew())
            profile = await self.adapter.prepare(lease, instruction)
            if not isinstance(profile, PreparedProfile) or not profile.exclusive:
                raise ProbeError("PROFILE_BUSY")
            await self.adapter.validate(profile, lease, instruction)
            guard()
            intent = self._event(lease, 1, "WRITE_INTENT", "RUNNING")
            self.spool.record(lease["attempt_id"], intent, "WRITE_INTENT")
            await self._ack(intent)
            # 云确认期间可能撤权/续租失败；发送前重新验证，不把旧确认作为永久授权。
            await self.adapter.validate(profile, lease, instruction)
            guard()
            self.spool.dispatch(lease["attempt_id"], intent)
            evidence = await self.adapter.submit(profile, lease, instruction)
            if (
                type(evidence) is not list
                or not 1 <= len(evidence) <= 20
                or any(type(item) is not str or not 1 <= len(item) <= 255 for item in evidence)
            ):
                raise ProbeError("EXECUTION_EVIDENCE_INVALID")
            event = self._event(lease, 2, "SUBMITTED", "VERIFYING", evidence=evidence)
            self.spool.record(lease["attempt_id"], event, "VERIFYING")
            await self._ack(event)
            return {"state": "VERIFYING", "error_code": None}
        except Exception as error:
            # 不回显平台响应/任意异常文本；只返回本模块已知拒绝码。
            code = error.code if isinstance(error, ProbeError) else "EXECUTION_CONNECTION_FAILED"
            state = "UNKNOWN" if intent is not None else "BLOCKED_AUTH"
            if intent is None and code in {
                "LOGIN_REQUIRED",
                "CHALLENGE",
                "IDENTITY_MISMATCH",
                "PROFILE_BUSY",
            }:
                state = "NEEDS_HUMAN"
            if started:
                self.spool.state(lease["attempt_id"], state)
                if intent is not None:
                    event = self._event(
                        lease,
                        self.spool.next_sequence(lease["attempt_id"]),
                        "RECOVERY",
                        "UNKNOWN",
                        error="EXECUTION_OUTCOME_UNKNOWN",
                    )
                    self.spool.record(lease["attempt_id"], event, "UNKNOWN")
                    try:
                        await self._ack(event, historical=True)
                    except Exception:
                        pass  # 未ACK的原事件保留，后续只允许历史重传。
                elif state == "NEEDS_HUMAN" or code == "CAPABILITY_UNVERIFIED":
                    event = self._event(
                        lease,
                        self.spool.next_sequence(lease["attempt_id"]),
                        "PREFLIGHT",
                        state,
                        error=code,
                    )
                    self.spool.record(lease["attempt_id"], event, state)
                    try:
                        await self._ack(event, historical=True)
                    except Exception:
                        pass
            return {"state": state, "error_code": code}
        finally:
            if keeper is not None:
                keeper.cancel()
                await asyncio.gather(keeper, return_exceptions=True)
            if (
                isinstance(profile, PreparedProfile)
                and profile.opened_by_workflow
                and profile.exclusive
            ):
                try:
                    await self.adapter.close(profile)
                except Exception:
                    pass
