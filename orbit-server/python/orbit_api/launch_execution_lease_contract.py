"""执行租约恢复的纯协议；不领取、不发送、不持久化，不创造公开业务状态。

Fact只能由未来Store核验真实来源后构造。结构校验/摘要绝不等于平台证据或发送授权。
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from orbit_api.task_contract import MAX_NODES, NODE_STATES, TASK_STATES

MAX_REVISION = 9007199254740991
MAX_ATTEMPT = 4294967295
RECONCILE_INTERVAL = timedelta(minutes=5)
MANUAL_AFTER = timedelta(hours=24)


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("UUID_INVALID")


def _integer(value, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError("COUNTER_INVALID")


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("HASH_INVALID")


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError("UTC_REQUIRED")


class FactKind(StrEnum):
    """私有观察事实，不能写入TaskNode.state或命令state。"""

    WRITE_INTENT = "WRITE_INTENT"
    PROVED_NOT_SENT = "PROVED_NOT_SENT"
    ACCEPTED = "ACCEPTED"
    READBACK_SUCCEEDED = "READBACK_SUCCEEDED"
    READBACK_REJECTED = "READBACK_REJECTED"
    READBACK_INCONCLUSIVE = "READBACK_INCONCLUSIVE"


class SendPhase(StrEnum):
    BEFORE_DISPATCH = "BEFORE_DISPATCH"
    DISPATCH_STARTED = "DISPATCH_STARTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    READBACK = "READBACK"


class EvidenceSource(StrEnum):
    LOCAL_INTENT = "LOCAL_INTENT"
    TRANSPORT_PROVEN_NO_SEND = "TRANSPORT_PROVEN_NO_SEND"
    PLATFORM_ACK = "PLATFORM_ACK"
    PLATFORM_READBACK = "PLATFORM_READBACK"


@dataclass(frozen=True, repr=False)
class AttemptBinding:
    """冻结来源与确切执行代际；每次重试新attempt/fence，不能更换通道。"""

    tenant_id: str
    task_id: str
    node_id: str
    preparation_id: str
    claim_id: str
    worker_id: str
    attempt_no: int
    fencing_token: int
    command_hash: str
    manifest_hash: str
    source_hash: str
    authority_hash: str
    authorization_hash: str
    execution_mode: str
    actor_id: int
    subject_id: str
    owner_user_id: str
    owner_team_id: str
    auth_version: int

    def __post_init__(self):
        for value in (
            self.tenant_id,
            self.task_id,
            self.node_id,
            self.preparation_id,
            self.claim_id,
            self.worker_id,
            self.subject_id,
            self.owner_user_id,
            self.owner_team_id,
        ):
            _uuid(value)
        _integer(self.actor_id, MAX_REVISION)
        _integer(self.auth_version, MAX_REVISION)
        _integer(self.attempt_no, MAX_ATTEMPT)
        _integer(self.fencing_token, MAX_REVISION)
        for value in (
            self.command_hash,
            self.manifest_hash,
            self.source_hash,
            self.authority_hash,
            self.authorization_hash,
        ):
            _hash(value)
        if self.execution_mode not in {"META_API", "ADSPOWER_UI"}:
            raise ValueError("EXECUTION_MODE_INVALID")


@dataclass(frozen=True, repr=False)
class AttemptFact:
    binding: AttemptBinding
    event_id: str
    kind: FactKind
    phase: SendPhase
    source: EvidenceSource
    evidence_sha256: str
    occurred_at: datetime
    external_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.binding, AttemptBinding):
            raise ValueError("ATTEMPT_REQUIRED")
        _uuid(self.event_id)
        _hash(self.evidence_sha256)
        _utc(self.occurred_at)
        if not (
            isinstance(self.kind, FactKind)
            and isinstance(self.phase, SendPhase)
            and isinstance(self.source, EvidenceSource)
        ):
            raise ValueError("TYPED_FACT_REQUIRED")
        required = {
            FactKind.WRITE_INTENT: (SendPhase.BEFORE_DISPATCH, EvidenceSource.LOCAL_INTENT),
            FactKind.PROVED_NOT_SENT: (
                SendPhase.BEFORE_DISPATCH,
                EvidenceSource.TRANSPORT_PROVEN_NO_SEND,
            ),
            FactKind.ACCEPTED: (SendPhase.ACKNOWLEDGED, EvidenceSource.PLATFORM_ACK),
            FactKind.READBACK_SUCCEEDED: (
                SendPhase.READBACK,
                EvidenceSource.PLATFORM_READBACK,
            ),
            FactKind.READBACK_REJECTED: (SendPhase.READBACK, EvidenceSource.PLATFORM_READBACK),
            FactKind.READBACK_INCONCLUSIVE: (
                SendPhase.READBACK,
                EvidenceSource.PLATFORM_READBACK,
            ),
        }
        if (self.phase, self.source) != required[self.kind]:
            raise ValueError("FACT_SOURCE_PHASE_MISMATCH")
        if self.external_id is not None and (
            not isinstance(self.external_id, str)
            or not re.fullmatch(r"[0-9]{1,64}", self.external_id)
        ):
            raise ValueError("EXTERNAL_ID_INVALID")
        if self.kind == FactKind.READBACK_SUCCEEDED and self.external_id is None:
            raise ValueError("EXTERNAL_ID_REQUIRED")


@dataclass(frozen=True, repr=False)
class RuntimeSnapshot:
    binding: AttemptBinding
    revision: int
    state: str
    lease_expires_at: datetime | None
    unknown_since: datetime | None = None
    last_reconciled_at: datetime | None = None

    def __post_init__(self):
        if not isinstance(self.binding, AttemptBinding):
            raise ValueError("ATTEMPT_REQUIRED")
        _integer(self.revision, MAX_REVISION)
        if self.state not in NODE_STATES:
            raise ValueError("NODE_STATE_INVALID")
        for value in (self.lease_expires_at, self.unknown_since, self.last_reconciled_at):
            if value is not None:
                _utc(value)
        if (self.state == "UNKNOWN") != (self.unknown_since is not None):
            raise ValueError("UNKNOWN_TIME_MISMATCH")
        if self.last_reconciled_at is not None and (
            self.unknown_since is None or self.last_reconciled_at < self.unknown_since
        ):
            raise ValueError("RECONCILE_TIME_INVALID")


@dataclass(frozen=True)
class RecoveryDecision:
    """未来Store仍须CAS/revision+1并同事务审计/outbox；本对象不是写入结果。"""

    state_path: tuple[str, ...]
    code: str
    retryable: bool = False
    readonly_reconcile_due: bool = False
    needs_manual_reconciliation: bool = False
    next_reconcile_at: datetime | None = None


def recover_expired(snapshot, facts, *, now, facts_complete=False):
    """只判断租约恢复；无事实不推断未发送，旧fence不能推动当前状态。"""
    if not isinstance(snapshot, RuntimeSnapshot):
        raise ValueError("RUNTIME_REQUIRED")
    _utc(now)
    if not isinstance(facts, tuple) or len(facts) > 200:
        raise ValueError("BOUNDED_FACTS_REQUIRED")
    if type(facts_complete) is not bool:
        raise ValueError("FACT_COMPLETENESS_REQUIRED")
    current = []
    seen = set()
    for fact in facts:
        if not isinstance(fact, AttemptFact) or fact.occurred_at > now:
            raise ValueError("FACT_INVALID_OR_FUTURE")
        if fact.event_id in seen:
            raise ValueError("DUPLICATE_FACT")
        seen.add(fact.event_id)
        if fact.binding == snapshot.binding:
            current.append(fact)
    state = snapshot.state
    if state == "UNKNOWN":
        if snapshot.unknown_since > now or (
            snapshot.last_reconciled_at is not None and snapshot.last_reconciled_at > now
        ):
            raise ValueError("UNKNOWN_TIME_FUTURE")
        manual = now >= snapshot.unknown_since + MANUAL_AFTER
        due_at = (snapshot.last_reconciled_at or snapshot.unknown_since) + RECONCILE_INTERVAL
        return RecoveryDecision(
            (state,),
            "UNKNOWN_MANUAL_REQUIRED" if manual else "UNKNOWN_READ_ONLY",
            readonly_reconcile_due=not manual and now >= due_at,
            needs_manual_reconciliation=manual,
            next_reconcile_at=None if manual else due_at,
        )
    if state == "ACCEPTED":
        if any(f.kind == FactKind.PROVED_NOT_SENT for f in current) and any(
            f.kind == FactKind.ACCEPTED for f in current
        ):
            return RecoveryDecision(
                (state, "VERIFYING", "UNKNOWN"),
                "SEND_EVIDENCE_CONFLICT",
                next_reconcile_at=now + RECONCILE_INTERVAL,
            )
        return RecoveryDecision((state, "VERIFYING"), "ACCEPTED_REQUIRES_READBACK")
    if state not in {"RUNNING", "VERIFYING"}:
        return RecoveryDecision((state,), "NO_LEASE_RECOVERY")
    if snapshot.lease_expires_at is None:
        raise ValueError("ACTIVE_LEASE_REQUIRED")
    if now < snapshot.lease_expires_at:
        return RecoveryDecision((state,), "LEASE_STILL_VALID")
    positive_no_send = any(f.kind == FactKind.PROVED_NOT_SENT for f in current)
    readback = any(
        f.kind
        in {
            FactKind.READBACK_SUCCEEDED,
            FactKind.READBACK_REJECTED,
            FactKind.READBACK_INCONCLUSIVE,
        }
        for f in current
    )
    # 读回事实与“发送前确定未发送”不能合成安全重试；连不确定读回也须核验。
    # 只看精确当前代际，旧尝试事实仍只留历史，不能污染或推动当前决策。
    if positive_no_send and (readback or any(f.kind == FactKind.ACCEPTED for f in current)):
        return RecoveryDecision(
            (state, "UNKNOWN"),
            "SEND_EVIDENCE_CONFLICT",
            next_reconcile_at=now + RECONCILE_INTERVAL,
        )
    if state == "RUNNING" and any(f.kind == FactKind.ACCEPTED for f in current):
        return RecoveryDecision((state, "ACCEPTED", "VERIFYING"), "ACK_REQUIRES_READBACK")
    intent = any(f.kind == FactKind.WRITE_INTENT for f in current)
    if state == "RUNNING" and positive_no_send and not intent and facts_complete:
        return RecoveryDecision((state, "FAILED"), "PROVED_NOT_SENT", retryable=True)
    return RecoveryDecision(
        (state, "UNKNOWN"),
        "LEASE_OUTCOME_UNKNOWN",
        next_reconcile_at=now + RECONCILE_INTERVAL,
    )


def aggregate_task_state(node_states):
    """WORKFLOWS第5节及第11节的汇总，不以配置成功推断正在投放。"""
    if not isinstance(node_states, (tuple, list)) or not 1 <= len(node_states) <= MAX_NODES:
        raise ValueError("BOUNDED_NODES_REQUIRED")
    states = set(node_states)
    if not states <= NODE_STATES:
        raise ValueError("NODE_STATE_INVALID")
    for nodes, result in (
        ({"UNKNOWN"}, "UNKNOWN"),
        ({"NEEDS_HUMAN"}, "NEEDS_HUMAN"),
        ({"RUNNING", "ACCEPTED"}, "RUNNING"),
        ({"VERIFYING"}, "VERIFYING"),
        ({"RETRY_WAIT"}, "RETRY_WAIT"),
        ({"DRAFT", "VALIDATED", "QUEUED"}, "QUEUED"),
    ):
        if states & nodes:
            return result
    if states == {"SUCCEEDED"}:
        result = "SUCCEEDED"
    elif "SUCCEEDED" in states:
        result = "PARTIAL_SUCCESS"
    elif states == {"CANCELLED"}:
        result = "CANCELLED"
    else:
        result = "FAILED"
    assert result in TASK_STATES
    return result
