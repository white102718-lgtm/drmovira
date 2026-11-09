"""窄执行恢复的可信读取与历史事实追加：精确代际及受控authority。

不更改业务状态/版本、不写TaskEvent、不领取或发送；事实及审计/outbox由外层事务提交。
生产未提供authority时，在任何SQL前失败；技术SQL hash/类型标签不能授信。
"""

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid5

from sqlalchemy import text

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_lease_contract import (
    MAX_ATTEMPT,
    MAX_REVISION,
    AttemptBinding,
    AttemptFact,
    EvidenceSource,
    FactKind,
    RuntimeSnapshot,
    SendPhase,
    _integer,
    _utc,
    _uuid,
    recover_expired,
)
from orbit_api.task_contract import MAX_NODES

FACT_PAGE_SIZE = 200
FACT_READ_SECONDS = 30
_ISSUER = object()


class LeaseOperation(StrEnum):
    """内部受控操作，不是新增公开菜单权限或广告写动作。"""

    RECOVER_EXPIRED = "RECOVER_EXPIRED"
    HISTORICAL_FACT = "HISTORICAL_FACT"


@dataclass(frozen=True, repr=False)
class LeaseAuthorityGrant:
    actor_id: int
    binding: AttemptBinding
    operation: LeaseOperation

    def __post_init__(self):
        _integer(self.actor_id, MAX_REVISION)
        if not isinstance(self.binding, AttemptBinding) or not isinstance(
            self.operation, LeaseOperation
        ):
            raise ValueError("TYPED_LEASE_GRANT_REQUIRED")


@dataclass(frozen=True, repr=False)
class FactValidationReceipt:
    """受控验证器对实际证据的确认；字符串/散列的存在不能生成本收据。"""

    fact: AttemptFact
    recorded_at: datetime

    def __post_init__(self):
        if not isinstance(self.fact, AttemptFact):
            raise ValueError("TYPED_FACT_REQUIRED")
        _utc(self.recorded_at)

    @classmethod
    def for_fact(cls, fact, *, recorded_at):
        # 仅供显式可信Authority在核验真实来源后调用，不是默认验证器。
        return cls(fact, recorded_at)


class ExecutionLeaseAuthority(ABC):
    """显式服务器依赖；无默认实现、无自动注册、无HTTP可构造入口。

    authorize须按操作分别核当前恢复权限/来源或历史设备/证据身份。
    verify_fact须验证实际不可变证据出处、内容hash、请求关联和发送阶段；
    不能仅检查本表hash或kind。两个方法只做有界SQL/已捕获来源重验，禁止网络I/O。
    """

    @abstractmethod
    async def authorize(self, session, actor_id, binding, operation):
        """成功返回精确LeaseAuthorityGrant；不足须拒绝，不能返回None当成功。"""

    @abstractmethod
    async def verify_fact(self, session, fact, *, recorded_at):
        """真实核验后返回精确FactValidationReceipt；不确定必须拒绝。"""


@dataclass(frozen=True, repr=False)
class RuntimeExpectation:
    revision: int
    attempt_no: int
    fencing_token: int
    claim_id: str
    worker_id: str

    def __post_init__(self):
        _integer(self.revision, MAX_REVISION)
        _integer(self.attempt_no, MAX_ATTEMPT)
        _integer(self.fencing_token, MAX_REVISION)
        _uuid(self.claim_id)
        _uuid(self.worker_id)


@dataclass(frozen=True, repr=False)
class FactAppendReceipt:
    event_id: str
    sequence_no: int
    recorded_at: datetime


@dataclass(frozen=True, repr=False)
class VerifiedFactSummary:
    """只由本模块完整遍历后签发；每类保留一份代表，内存不随事实总数增长。"""

    binding: AttemptBinding
    total_count: int
    last_sequence: int
    counts: tuple[tuple[FactKind, int], ...]
    representatives: tuple[AttemptFact, ...]
    root_sha256: str
    _issuer: object = field(repr=False, compare=False)


@dataclass(frozen=True, repr=False)
class VerifiedRecoveryInput:
    snapshot: RuntimeSnapshot
    summary: VerifiedFactSummary
    database_now: datetime
    _transaction: object = field(repr=False, compare=False)
    _issuer: object = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def decision(self, session):
        """同一外层事务仍持锁才可计算；返回纯建议，绝不冒充状态已提交。"""
        if (
            self._issuer is not _ISSUER
            or self.summary._issuer is not _ISSUER
            or self.snapshot.binding != self.summary.binding
            or not isinstance(self._seal, _RecoverySeal)
            or self._seal.value is not self
            or self._seal.summary is not self.summary
            or not session.in_transaction()
            or session.get_transaction() is not self._transaction
        ):
            unverified()
        return recover_expired(
            self.snapshot,
            self.summary.representatives,
            now=self.database_now,
            facts_complete=True,
        )


class _RecoverySeal:
    """进程内精确实例凭证；复制已签发DTO也不能替换其事实/时钟后继续使用。"""

    __slots__ = ("value", "summary")

    def __init__(self, summary):
        self.value = None
        self.summary = summary


def _issue_recovery(snapshot, summary, now, transaction):
    seal = _RecoverySeal(summary)
    value = VerifiedRecoveryInput(snapshot, summary, now, transaction, _ISSUER, seal)
    seal.value = value
    return value


def unavailable():
    raise OrbitError(503, "EXECUTION_LEASE_AUTHORITY_UNAVAILABLE", "执行恢复可信来源尚未就绪")


def unverified():
    raise OrbitError(503, "EXECUTION_LEASE_SOURCE_UNVERIFIED", "执行尝试或完整事实尚未核实")


def stale():
    raise OrbitError(409, "EXECUTION_LEASE_STALE", "执行恢复代际或版本已变化")


def fact_conflict():
    raise OrbitError(409, "EXECUTION_FACT_CONFLICT", "同一事实事件不得改变原内容")


def _database_time(value):
    if not isinstance(value, datetime):
        unverified()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    try:
        _utc(value)
    except ValueError:
        unverified()
    return value


async def _one(session, sql, values):
    return (await session.execute(text(sql), values)).mappings().first()


def _stored_binding(row):
    try:
        return AttemptBinding(
            **{
                name: row[name]
                for name in AttemptBinding.__dataclass_fields__
                if name not in {"attempt_no"}
            },
            attempt_no=row["attempt_no"],
        )
    except (KeyError, TypeError, ValueError):
        unverified()


def fact_chain_seed(binding):
    """固定域隔离、完整不可变尝试绑定；摘要本身不授予证据真实性。"""
    if not isinstance(binding, AttemptBinding):
        raise ValueError("需要精确尝试绑定")
    return hashlib.sha256(
        canonical({"domain": "ORBIT_EXECUTION_FACT_CHAIN_V1", "binding": asdict(binding)}).encode()
    ).digest()


def fact_chain_step(previous, sequence, fact, recorded_at):
    """仅对已逐项验证事实调用，完整六位UTC参与有序链，不持有整包。"""
    if not isinstance(previous, bytes) or len(previous) != 32 or not isinstance(fact, AttemptFact):
        raise ValueError("需要前序摘要及精确事实")
    _integer(sequence, MAX_ATTEMPT)
    _utc(recorded_at)
    document = asdict(fact)
    document["occurred_at"] = fact.occurred_at.isoformat(timespec="microseconds")
    document["recorded_at"] = recorded_at.isoformat(timespec="microseconds")
    document["sequence"] = sequence
    return hashlib.sha256(previous + canonical(document).encode()).digest()


async def _stream_verified_facts(session, authority, binding, database_now):
    """调用方必须已锁command/runtime；所有Store追加者也须同序锁command。

    按sequence连续键集读到空页，不设200总数上限，不接受调用方complete标记。
    无整包/无限event_id集合：最多200行页、6个计数及6份代表。
    """
    after = 0
    counts, representatives = {}, {}
    root = fact_chain_seed(binding)
    values = {
        "tenant": binding.tenant_id,
        "task": binding.task_id,
        "node": binding.node_id,
        "attempt": binding.attempt_no,
    }
    async with asyncio.timeout(FACT_READ_SECONDS):
        while True:
            rows = list(
                (
                    await session.execute(
                        text(
                            "SELECT attempt_no,fencing_token,claim_id,worker_id,"
                            "event_id,sequence_no,"
                            "fact_kind,send_phase,evidence_source,evidence_sha256,external_id,"
                            "occurred_at,recorded_at FROM orbit_execution_attempt_fact "
                            "WHERE tenant_id=:tenant AND task_id=:task AND node_id=:node "
                            "AND attempt_no=:attempt AND sequence_no>:after "
                            "ORDER BY sequence_no LIMIT 200 FOR SHARE"
                        ),
                        values | {"after": after},
                    )
                )
                .mappings()
                .all()
            )
            if len(rows) > FACT_PAGE_SIZE:
                unverified()
            if not rows:
                break
            for row in rows:
                try:
                    sequence = row["sequence_no"]
                    if type(sequence) is not int or sequence != after + 1:
                        unverified()
                    _integer(sequence, MAX_ATTEMPT)
                    if (
                        row["attempt_no"] != binding.attempt_no
                        or row["fencing_token"] != binding.fencing_token
                        or row["claim_id"] != binding.claim_id
                        or row["worker_id"] != binding.worker_id
                    ):
                        unverified()
                    occurred = _database_time(row["occurred_at"])
                    recorded = _database_time(row["recorded_at"])
                    if occurred > recorded or recorded > database_now:
                        unverified()
                    fact = AttemptFact(
                        binding,
                        row["event_id"],
                        FactKind(row["fact_kind"]),
                        SendPhase(row["send_phase"]),
                        EvidenceSource(row["evidence_source"]),
                        row["evidence_sha256"],
                        occurred,
                        row["external_id"],
                    )
                except (KeyError, TypeError, ValueError):
                    unverified()
                receipt = await authority.verify_fact(session, fact, recorded_at=recorded)
                if not isinstance(
                    receipt, FactValidationReceipt
                ) or receipt != FactValidationReceipt.for_fact(fact, recorded_at=recorded):
                    unverified()
                counts[fact.kind] = counts.get(fact.kind, 0) + 1
                representatives.setdefault(fact.kind, fact)
                root = fact_chain_step(root, sequence, fact, recorded)
                after = sequence
    return VerifiedFactSummary(
        binding,
        after,
        after,
        tuple(sorted(counts.items())),
        tuple(representatives[kind] for kind in sorted(representatives)),
        root.hex(),
        _ISSUER,
    )


class ExecutionLeaseStore:
    def __init__(self, authority=None):
        self.authority = authority

    async def append_verified_fact(self, session, actor_id, fact, request_id):
        """仅留原尝试事实；同event精确幂等，绝不变更当前状态、版本或执行次数。"""
        if not isinstance(self.authority, ExecutionLeaseAuthority):
            unavailable()
        if not session.in_transaction():
            raise ValueError("事实追加需要调用方外层事务")
        if not isinstance(fact, AttemptFact):
            raise ValueError("需要完整精确事实")
        _integer(actor_id, MAX_REVISION)
        _uuid(request_id)
        binding = fact.binding
        grant = await self.authority.authorize(
            session, actor_id, binding, LeaseOperation.HISTORICAL_FACT
        )
        if not isinstance(grant, LeaseAuthorityGrant) or grant != LeaseAuthorityGrant(
            actor_id, binding, LeaseOperation.HISTORICAL_FACT
        ):
            unavailable()
        values = {"tenant": binding.tenant_id, "task": binding.task_id, "node": binding.node_id}
        await self._lock_fact_target(session, binding, values)
        precision = list(
            (
                await session.execute(
                    text(
                        "SELECT COLUMN_NAME AS name,DATETIME_PRECISION AS precision_value "
                        "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                        "AND TABLE_NAME='orbit_execution_attempt_fact' "
                        "AND COLUMN_NAME IN('occurred_at','recorded_at')"
                    )
                )
            )
            .mappings()
            .all()
        )
        if {row["name"]: row["precision_value"] for row in precision} != {
            "occurred_at": 6,
            "recorded_at": 6,
        }:
            raise OrbitError(503, "EXECUTION_FACT_PRECISION_UNVERIFIED", "事实微秒精度迁移尚未就绪")
        old = await _one(
            session,
            "SELECT task_id,node_id,attempt_no,fencing_token,claim_id,worker_id,event_id,"
            "sequence_no,fact_kind,send_phase,evidence_source,evidence_sha256,external_id,"
            "occurred_at,recorded_at FROM orbit_execution_attempt_fact "
            "WHERE tenant_id=:tenant AND event_id=:event FOR UPDATE",
            values | {"event": fact.event_id},
        )
        now = await _one(session, "SELECT UTC_TIMESTAMP(6) AS now", {})
        if now is None:
            unverified()
        recorded_now = _database_time(now["now"])
        audit_id = str(uuid5(UUID(binding.tenant_id), "execution-fact:" + fact.event_id))
        if old is not None:
            if (
                old["task_id"] != binding.task_id
                or old["node_id"] != binding.node_id
                or old["attempt_no"] != binding.attempt_no
                or old["fencing_token"] != binding.fencing_token
                or old["claim_id"] != binding.claim_id
                or old["worker_id"] != binding.worker_id
            ):
                fact_conflict()
            try:
                stored = AttemptFact(
                    binding,
                    old["event_id"],
                    FactKind(old["fact_kind"]),
                    SendPhase(old["send_phase"]),
                    EvidenceSource(old["evidence_source"]),
                    old["evidence_sha256"],
                    _database_time(old["occurred_at"]),
                    old["external_id"],
                )
            except (KeyError, TypeError, ValueError):
                unverified()
            if stored != fact:
                fact_conflict()
            recorded = _database_time(old["recorded_at"])
            if recorded > recorded_now:
                unverified()
            await self._verify_append_fact(session, stored, recorded)
            audit = await _one(
                session,
                "SELECT a.id FROM orbit_task_audit a JOIN orbit_task_outbox o "
                "ON o.tenant_id=a.tenant_id AND o.task_id=a.task_id AND o.audit_id=a.id "
                "WHERE a.tenant_id=:tenant AND a.task_id=:task AND a.id=:audit "
                "AND a.action='EXECUTION_FACT_APPEND' FOR SHARE",
                values | {"audit": audit_id},
            )
            if audit is None:
                unverified()
            return FactAppendReceipt(fact.event_id, old["sequence_no"], recorded)
        recorded = recorded_now
        await self._verify_append_fact(session, fact, recorded)
        tail = await _one(
            session,
            "SELECT sequence_no FROM orbit_execution_attempt_fact WHERE tenant_id=:tenant "
            "AND task_id=:task AND node_id=:node AND attempt_no=:attempt "
            "ORDER BY sequence_no DESC LIMIT 1 FOR UPDATE",
            values | {"attempt": binding.attempt_no},
        )
        previous = tail["sequence_no"] if tail else 0
        if type(previous) is not int or not 0 <= previous < MAX_ATTEMPT:
            raise OrbitError(409, "EXECUTION_FACT_SEQUENCE_EXHAUSTED", "事实序号已达上限")
        sequence = previous + 1
        parameters = values | {
            "attempt": binding.attempt_no,
            "fence": binding.fencing_token,
            "claim": binding.claim_id,
            "worker": binding.worker_id,
            "event": fact.event_id,
            "sequence": sequence,
            "kind": fact.kind.value,
            "phase": fact.phase.value,
            "source": fact.source.value,
            "hash": fact.evidence_sha256,
            "external": fact.external_id,
            "occurred": fact.occurred_at.replace(tzinfo=None),
            "recorded": recorded.replace(tzinfo=None),
            "audit": audit_id,
            "actor": actor_id,
            "request": request_id,
        }
        for sql in (
            "INSERT INTO orbit_execution_attempt_fact(tenant_id,task_id,node_id,attempt_no,"
            "fencing_token,claim_id,worker_id,event_id,sequence_no,fact_kind,send_phase,"
            "evidence_source,evidence_sha256,external_id,occurred_at,recorded_at) VALUES("
            ":tenant,:task,:node,:attempt,:fence,:claim,:worker,:event,:sequence,:kind,:phase,"
            ":source,:hash,:external,:occurred,:recorded)",
            "INSERT INTO orbit_task_audit(id,tenant_id,task_id,actor_id,request_id,"
            "action,created_at) "
            "VALUES(:audit,:tenant,:task,:actor,:request,'EXECUTION_FACT_APPEND',:recorded)",
            "INSERT INTO orbit_task_outbox(audit_id,tenant_id,task_id,created_at) "
            "VALUES(:audit,:tenant,:task,:recorded)",
        ):
            result = await session.execute(text(sql), parameters)
            if result.rowcount != 1:
                unverified()
        return FactAppendReceipt(fact.event_id, sequence, recorded)

    async def _verify_append_fact(self, session, fact, recorded):
        if fact.occurred_at > recorded:
            unverified()
        receipt = await self.authority.verify_fact(session, fact, recorded_at=recorded)
        if not isinstance(
            receipt, FactValidationReceipt
        ) or receipt != FactValidationReceipt.for_fact(fact, recorded_at=recorded):
            unverified()

    async def _lock_fact_target(self, session, binding, values):
        """晚到可留原尝试；不要求其仍是当前运行头，但拒绝未来/孤立尝试。"""
        clock = await _one(
            session,
            "SELECT revision FROM orbit_task_clock WHERE tenant_id=:tenant FOR UPDATE",
            values,
        )
        if (
            clock is None
            or type(clock["revision"]) is not int
            or not 1 <= clock["revision"] <= MAX_REVISION
        ):
            unverified()
        task = await _one(
            session,
            "SELECT owner_user_id,owner_team_id,source_hash,execution_mode,manifest_phase,"
            "node_count,expected_node_count FROM orbit_task "
            "WHERE tenant_id=:tenant AND id=:task FOR UPDATE",
            values,
        )
        if (
            task is None
            or task["manifest_phase"] != "COMPLETE"
            or not 1 <= task["node_count"] <= MAX_NODES
            or task["node_count"] != task["expected_node_count"]
            or task["source_hash"] != binding.source_hash
            or task["owner_user_id"] != binding.owner_user_id
            or task["owner_team_id"] != binding.owner_team_id
            or task["execution_mode"] != binding.execution_mode
        ):
            unverified()
        preparation = await _one(
            session,
            "SELECT state,manifest_hash,payload_hash,expected_command_count,"
            "persisted_command_count "
            "FROM orbit_launch_execution_preparation WHERE tenant_id=:tenant AND task_id=:task "
            "AND id=:preparation FOR SHARE",
            values | {"preparation": binding.preparation_id},
        )
        command = await _one(
            session,
            "SELECT c.preparation_id,c.resolved_configuration_json,c.resolved_configuration_hash "
            "FROM orbit_launch_execution_command c WHERE c.tenant_id=:tenant AND c.task_id=:task "
            "AND c.node_id=:node FOR UPDATE",
            values,
        )
        node = await _one(
            session,
            "SELECT state,attempt FROM orbit_task_node WHERE tenant_id=:tenant "
            "AND task_id=:task AND id=:node FOR UPDATE",
            values,
        )
        runtime = await _one(
            session,
            "SELECT active_attempt,fencing_token FROM orbit_execution_command_runtime "
            "WHERE tenant_id=:tenant AND task_id=:task AND node_id=:node FOR UPDATE",
            values,
        )
        if (
            preparation is None
            or command is None
            or node is None
            or runtime is None
            or preparation["state"] != "ACCEPTED"
            or preparation["manifest_hash"] != binding.manifest_hash
            or preparation["payload_hash"] != binding.source_hash
            or preparation["expected_command_count"] != task["node_count"]
            or preparation["persisted_command_count"] != task["node_count"]
            or command["preparation_id"] != binding.preparation_id
            or command["resolved_configuration_hash"] != binding.command_hash
            or runtime["active_attempt"] is None
            or runtime["active_attempt"] < binding.attempt_no
            or runtime["fencing_token"] < binding.fencing_token
        ):
            unverified()
        try:
            payload = command["resolved_configuration_json"]
            if isinstance(payload, (str, bytes)):
                payload = json.loads(payload)
            if (
                not isinstance(payload, dict)
                or hashlib.sha256(canonical(payload).encode()).hexdigest() != binding.command_hash
            ):
                unverified()
        except (TypeError, ValueError, UnicodeError):
            unverified()
        original = await _one(
            session,
            "SELECT * FROM orbit_execution_attempt WHERE tenant_id=:tenant AND task_id=:task "
            "AND node_id=:node AND attempt_no=:attempt FOR SHARE",
            values | {"attempt": binding.attempt_no},
        )
        if original is None or _stored_binding(original) != binding:
            unverified()

    async def capture_recovery(self, session, actor_id, binding, expected):
        """只读且持锁的恢复输入；不会claim、增attempt或持久状态/事件。"""
        if not isinstance(self.authority, ExecutionLeaseAuthority):
            unavailable()
        if not session.in_transaction():
            raise ValueError("执行恢复读取需要调用方外层事务")
        if not isinstance(binding, AttemptBinding) or not isinstance(expected, RuntimeExpectation):
            raise ValueError("需要精确尝试及运行头预期")
        _integer(actor_id, MAX_REVISION)
        grant = await self.authority.authorize(
            session, actor_id, binding, LeaseOperation.RECOVER_EXPIRED
        )
        if not isinstance(grant, LeaseAuthorityGrant) or grant != LeaseAuthorityGrant(
            actor_id, binding, LeaseOperation.RECOVER_EXPIRED
        ):
            unavailable()
        values = {"tenant": binding.tenant_id, "task": binding.task_id, "node": binding.node_id}
        clock = await _one(
            session,
            "SELECT revision FROM orbit_task_clock WHERE tenant_id=:tenant FOR UPDATE",
            values,
        )
        if (
            clock is None
            or type(clock["revision"]) is not int
            or not 1 <= clock["revision"] < MAX_REVISION
        ):
            unverified()
        task = await _one(
            session,
            "SELECT owner_user_id,owner_team_id,source_hash,execution_mode,manifest_phase,"
            "node_count,expected_node_count FROM orbit_task "
            "WHERE tenant_id=:tenant AND id=:task FOR UPDATE",
            values,
        )
        if (
            task is None
            or task["manifest_phase"] != "COMPLETE"
            or not 1 <= task["node_count"] <= MAX_NODES
            or task["node_count"] != task["expected_node_count"]
            or task["owner_user_id"] != binding.owner_user_id
            or task["owner_team_id"] != binding.owner_team_id
            or task["execution_mode"] != binding.execution_mode
            or task["source_hash"] != binding.source_hash
        ):
            unverified()
        preparation = await _one(
            session,
            "SELECT id,task_id,state,manifest_hash,payload_hash,expected_command_count,"
            "persisted_command_count FROM orbit_launch_execution_preparation "
            "WHERE tenant_id=:tenant AND task_id=:task AND id=:preparation FOR SHARE",
            values | {"preparation": binding.preparation_id},
        )
        command = await _one(
            session,
            "SELECT c.state,c.attempt,c.preparation_id,c.resolved_configuration_json,"
            "c.resolved_configuration_hash FROM orbit_launch_execution_command c "
            "WHERE c.tenant_id=:tenant AND c.task_id=:task AND c.node_id=:node FOR UPDATE",
            values,
        )
        node = await _one(
            session,
            "SELECT state,attempt FROM orbit_task_node "
            "WHERE tenant_id=:tenant AND task_id=:task AND id=:node FOR UPDATE",
            values,
        )
        runtime = await _one(
            session,
            "SELECT revision,active_attempt,fencing_token,claim_id,worker_id,lease_expires_at,"
            "unknown_since,last_reconciled_at FROM orbit_execution_command_runtime "
            "WHERE tenant_id=:tenant AND task_id=:task AND node_id=:node FOR UPDATE",
            values,
        )
        if runtime is None:
            stale()
        try:
            actual_expectation = RuntimeExpectation(
                runtime["revision"],
                runtime["active_attempt"],
                runtime["fencing_token"],
                runtime["claim_id"],
                runtime["worker_id"],
            )
        except (KeyError, TypeError, ValueError):
            unverified()
        if actual_expectation != expected:
            stale()
        if (
            expected.attempt_no != binding.attempt_no
            or expected.fencing_token != binding.fencing_token
            or expected.claim_id != binding.claim_id
            or expected.worker_id != binding.worker_id
        ):
            stale()
        if (
            command is None
            or preparation is None
            or node is None
            or command["state"] != node["state"]
            or command["state"] not in {"RUNNING", "ACCEPTED", "VERIFYING", "UNKNOWN"}
            or command["attempt"] != binding.attempt_no
            or node["attempt"] != binding.attempt_no
            or preparation["state"] != "ACCEPTED"
            or command["preparation_id"] != binding.preparation_id
            or preparation["id"] != binding.preparation_id
            or preparation["task_id"] != binding.task_id
            or preparation["manifest_hash"] != binding.manifest_hash
            or preparation["payload_hash"] != binding.source_hash
            or command["resolved_configuration_hash"] != binding.command_hash
            or preparation["expected_command_count"] != task["node_count"]
            or preparation["persisted_command_count"] != task["node_count"]
        ):
            unverified()
        try:
            configuration = command["resolved_configuration_json"]
            if isinstance(configuration, (str, bytes)):
                configuration = json.loads(configuration)
            if (
                not isinstance(configuration, dict)
                or hashlib.sha256(canonical(configuration).encode()).hexdigest()
                != binding.command_hash
            ):
                unverified()
        except (TypeError, ValueError, UnicodeError):
            unverified()
        attempt = await _one(
            session,
            "SELECT * FROM orbit_execution_attempt WHERE tenant_id=:tenant AND task_id=:task "
            "AND node_id=:node AND attempt_no=:attempt FOR SHARE",
            values | {"attempt": binding.attempt_no},
        )
        if attempt is None or _stored_binding(attempt) != binding:
            unverified()
        now_row = await _one(session, "SELECT UTC_TIMESTAMP(6) AS now", {})
        if now_row is None:
            unverified()
        now = _database_time(now_row["now"])
        try:
            snapshot = RuntimeSnapshot(
                binding,
                runtime["revision"],
                command["state"],
                _database_time(runtime["lease_expires_at"])
                if runtime["lease_expires_at"]
                else None,
                _database_time(runtime["unknown_since"]) if runtime["unknown_since"] else None,
                _database_time(runtime["last_reconciled_at"])
                if runtime["last_reconciled_at"]
                else None,
            )
            summary = await _stream_verified_facts(session, self.authority, binding, now)
        except TimeoutError:
            raise OrbitError(
                503, "EXECUTION_FACT_READ_TIMEOUT", "完整事实读取超时，不能推断执行结果"
            ) from None
        except (KeyError, TypeError, ValueError):
            unverified()
        return _issue_recovery(snapshot, summary, now, session.get_transaction())
