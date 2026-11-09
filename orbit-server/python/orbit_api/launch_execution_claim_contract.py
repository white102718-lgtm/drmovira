"""首次claim纯建议；无SQL/issuer/领取/发送，不改变原恢复或公开状态枚举。"""

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_lease_contract import (
    MAX_REVISION,
    AttemptBinding,
    _hash,
    _integer,
    _utc,
    _uuid,
    aggregate_task_state,
)
from orbit_api.task_contract import KINDS, MAX_NODES, NODE_STATES, TASK_STATES


def _nonnegative(value, maximum=MAX_REVISION):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("NONNEGATIVE_COUNTER_REQUIRED")


def _text(value, maximum):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        raise ValueError("BOUNDED_TEXT_REQUIRED")


@dataclass(frozen=True, repr=False)
class ClaimTarget:
    tenant_id: str
    task_id: str
    node_id: str
    preparation_id: str
    plan_id: str
    source_revision: int
    source_hash: str
    manifest_hash: str
    command_hash: str
    intent_hash: str
    execution_mode: str
    actor_id: int
    subject_id: str
    owner_user_id: str
    owner_team_id: str
    account_id: str
    target_key: str
    kind: str
    purpose: str

    def __post_init__(self):
        for key in (
            "tenant_id",
            "task_id",
            "node_id",
            "preparation_id",
            "plan_id",
            "subject_id",
            "owner_user_id",
            "owner_team_id",
            "account_id",
        ):
            _uuid(getattr(self, key))
        _integer(self.source_revision, MAX_REVISION)
        _integer(self.actor_id, MAX_REVISION)
        for value in (self.source_hash, self.manifest_hash, self.command_hash, self.intent_hash):
            _hash(value)
        if self.execution_mode not in {"META_API", "ADSPOWER_UI"} or self.kind not in KINDS:
            raise ValueError("FROZEN_MODE_AND_KIND_REQUIRED")
        _text(self.target_key, 512)
        _text(self.purpose, 32)


@dataclass(frozen=True)
class ExpectedClaimHead:
    task_revision: int
    node_state: str
    command_state: str
    node_attempt: int
    command_attempt: int
    runtime_revision: int | None

    def __post_init__(self):
        _integer(self.task_revision, MAX_REVISION)
        if self.node_state not in NODE_STATES or self.command_state not in NODE_STATES:
            raise ValueError("ORIGINAL_NODE_STATE_REQUIRED")
        _nonnegative(self.node_attempt, 4294967295)
        _nonnegative(self.command_attempt, 4294967295)
        if self.runtime_revision is not None:
            _integer(self.runtime_revision, MAX_REVISION)


@dataclass(frozen=True, repr=False)
class ClaimRequest:
    target: ClaimTarget
    worker_id: str
    request_id: str
    expected: ExpectedClaimHead

    def __post_init__(self):
        if not isinstance(self.target, ClaimTarget) or not isinstance(
            self.expected, ExpectedClaimHead
        ):
            raise ValueError("TYPED_CLAIM_REQUEST_REQUIRED")
        _uuid(self.worker_id)
        _uuid(self.request_id)


def request_hash(request):
    if not isinstance(request, ClaimRequest):
        raise ValueError("TYPED_CLAIM_REQUEST_REQUIRED")
    # 不混入每次捕获的时间/nonce/临时观察版本，不把读epoch当业务键。
    return hashlib.sha256(
        canonical({"domain": "ORBIT_FIRST_CLAIM_V1", "request": asdict(request)}).encode()
    ).hexdigest()


def logical_command_hash(target):
    if not isinstance(target, ClaimTarget):
        raise ValueError("TYPED_CLAIM_TARGET_REQUIRED")
    return hashlib.sha256(
        canonical(
            {"domain": "ORBIT_LOGICAL_EXECUTION_COMMAND_V1", "target": asdict(target)}
        ).encode()
    ).hexdigest()


@dataclass(frozen=True, repr=False)
class ClaimRuntimeSnapshot:
    revision: int
    active_attempt: int | None
    fencing_token: int
    claim_id: str | None
    worker_id: str | None
    lease_expires_at: datetime | None
    unknown_since: datetime | None
    last_reconciled_at: datetime | None
    next_reconcile_at: datetime | None
    needs_manual_reconciliation: bool

    def __post_init__(self):
        _integer(self.revision, MAX_REVISION)
        _nonnegative(self.fencing_token)
        if type(self.needs_manual_reconciliation) is not bool:
            raise ValueError("STRICT_BOOLEAN_REQUIRED")
        for value in (
            self.lease_expires_at,
            self.unknown_since,
            self.last_reconciled_at,
            self.next_reconcile_at,
        ):
            if value is not None:
                _utc(value)
        if self.active_attempt is None:
            if (
                self.fencing_token != 0
                or any(
                    value is not None
                    for value in (
                        self.claim_id,
                        self.worker_id,
                        self.lease_expires_at,
                        self.unknown_since,
                        self.last_reconciled_at,
                        self.next_reconcile_at,
                    )
                )
                or self.needs_manual_reconciliation
            ):
                raise ValueError("INITIAL_RUNTIME_MUST_BE_EMPTY")
        else:
            _integer(self.active_attempt, 4294967295)
            _integer(self.fencing_token, MAX_REVISION)
            _uuid(self.claim_id)
            _uuid(self.worker_id)


@dataclass(frozen=True)
class ParentClaimState:
    tenant_id: str
    task_id: str
    node_id: str
    state: str

    def __post_init__(self):
        for value in (self.tenant_id, self.task_id, self.node_id):
            _uuid(value)
        if self.state not in NODE_STATES:
            raise ValueError("ORIGINAL_PARENT_STATE_REQUIRED")


@dataclass(frozen=True, repr=False)
class LockedClaimSnapshot:
    target: ClaimTarget
    task_revision: int
    task_sequence: int
    task_state: str
    node_state: str
    command_state: str
    node_attempt: int
    command_attempt: int
    runtime: ClaimRuntimeSnapshot | None
    parents: tuple[ParentClaimState, ...]
    node_state_counts: tuple[tuple[str, int], ...]
    manifest_phase: str
    preparation_state: str
    cancel_requested: bool
    _transaction: object = field(repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.target, ClaimTarget):
            raise ValueError("TYPED_TARGET_REQUIRED")
        _integer(self.task_revision, MAX_REVISION)
        _nonnegative(self.task_sequence)
        if (
            self.task_state not in TASK_STATES
            or self.node_state not in NODE_STATES
            or self.command_state not in NODE_STATES
        ):
            raise ValueError("ORIGINAL_STATE_REQUIRED")
        _nonnegative(self.node_attempt, 4294967295)
        _nonnegative(self.command_attempt, 4294967295)
        if self.runtime is not None and not isinstance(self.runtime, ClaimRuntimeSnapshot):
            raise ValueError("TYPED_RUNTIME_REQUIRED")
        if (
            not isinstance(self.parents, tuple)
            or len(self.parents) > 100
            or any(not isinstance(row, ParentClaimState) for row in self.parents)
        ):
            raise ValueError("BOUNDED_TYPED_PARENTS_REQUIRED")
        if type(self.cancel_requested) is not bool:
            raise ValueError("STRICT_CANCELLATION_INTENT_REQUIRED")
        _counts(self.node_state_counts)
        if self.manifest_phase not in {"BUILDING", "COMPLETE"} or self.preparation_state not in {
            "BUILDING",
            "SEALING",
            "SEALED",
            "ACCEPTED",
            "ABORTED",
        }:
            raise ValueError("ORIGINAL_MANIFEST_PHASE_REQUIRED")


def _counts(counts):
    if not isinstance(counts, tuple) or not counts or len(counts) > len(NODE_STATES):
        raise ValueError("BOUNDED_COMPLETE_STATE_COUNTS_REQUIRED")
    states, total = [], 0
    for row in counts:
        if not isinstance(row, tuple) or len(row) != 2 or row[0] not in NODE_STATES:
            raise ValueError("STATE_COUNT_INVALID")
        _integer(row[1], MAX_NODES)
        states.append(row[0])
        total += row[1]
    if states != sorted(set(states)) or total > MAX_NODES:
        raise ValueError("STATE_COUNTS_MUST_BE_UNIQUE_COMPLETE_AND_BOUNDED")
    return dict(counts)


@dataclass(frozen=True, repr=False)
class ClaimSourceFacts:
    """未来真实issuer的已锁数据投影；此结构/哈希本身不证明其真实性。"""

    target: ClaimTarget
    worker_id: str
    worker_principal_id: str
    worker_grant_revision: int
    auth_revision: int
    scope_revision: int
    authorized_actions: tuple[str, ...]
    captured_at: datetime
    expires_at: datetime
    lease_expires_at: datetime
    worker_enabled: bool
    manifest_proof_hash: str
    expected_node_count: int
    parent_ids: tuple[str, ...]
    _transaction: object = field(repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.target, ClaimTarget):
            raise ValueError("TYPED_SOURCE_TARGET_REQUIRED")
        _uuid(self.worker_id)
        _uuid(self.worker_principal_id)
        for value in (self.worker_grant_revision, self.auth_revision, self.scope_revision):
            _integer(value, MAX_REVISION)
        if (
            not isinstance(self.authorized_actions, tuple)
            or self.authorized_actions != tuple(sorted(set(self.authorized_actions)))
            or any(
                value not in {"launch.execute", "launch.publish"}
                for value in self.authorized_actions
            )
        ):
            raise ValueError("EXPLICIT_ORIGINAL_EXECUTION_ACTIONS_REQUIRED")
        for value in (self.captured_at, self.expires_at, self.lease_expires_at):
            _utc(value)
        if (
            not self.captured_at < self.lease_expires_at <= self.expires_at
            or type(self.worker_enabled) is not bool
        ):
            raise ValueError("EXPLICIT_WORKER_AND_SOURCE_LIFETIME_REQUIRED")
        _hash(self.manifest_proof_hash)
        _integer(self.expected_node_count, MAX_NODES)
        if (
            not isinstance(self.parent_ids, tuple)
            or len(self.parent_ids) > 100
            or self.parent_ids != tuple(sorted(set(self.parent_ids)))
        ):
            raise ValueError("EXACT_FROZEN_PARENT_IDS_REQUIRED")
        for value in self.parent_ids:
            _uuid(value)


class SwitchScope(StrEnum):
    GLOBAL = "GLOBAL"
    TENANT = "TENANT"
    ACCOUNT = "ACCOUNT"


@dataclass(frozen=True)
class ClaimSwitchFact:
    scope: SwitchScope
    scope_id: str | None
    revision: int
    blocked: bool

    def __post_init__(self):
        if not isinstance(self.scope, SwitchScope) or type(self.blocked) is not bool:
            raise ValueError("TYPED_SWITCH_SOURCE_REQUIRED")
        _integer(self.revision, MAX_REVISION)
        if self.scope is SwitchScope.GLOBAL:
            if self.scope_id is not None:
                raise ValueError("GLOBAL_SWITCH_HAS_NO_REQUEST_SCOPE")
        else:
            _uuid(self.scope_id)


class ReservationKind(StrEnum):
    RESERVED = "RESERVED"
    NO_BUDGET_EFFECT = "NO_BUDGET_EFFECT"


@dataclass(frozen=True, repr=False)
class ClaimResourceFacts:
    """共享coordinator事实投影；不计算预算、不生成锁、不含默认通过分支。"""

    target: ClaimTarget
    logical_command_hash: str
    switches: tuple[ClaimSwitchFact, ...]
    policy_version: str
    policy_proof_hash: str
    target_lock_id: str
    reservation_kind: ReservationKind
    reservation_id: str | None
    budget_owner_lock_id: str | None
    budget_baseline_hash: str | None
    captured_at: datetime
    expires_at: datetime
    _transaction: object = field(repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.target, ClaimTarget) or not isinstance(
            self.reservation_kind, ReservationKind
        ):
            raise ValueError("TYPED_RESOURCE_FACTS_REQUIRED")
        _hash(self.logical_command_hash)
        _hash(self.policy_proof_hash)
        _text(self.policy_version, 64)
        _uuid(self.target_lock_id)
        if (
            not isinstance(self.switches, tuple)
            or len(self.switches) != 3
            or any(not isinstance(row, ClaimSwitchFact) for row in self.switches)
            or tuple(row.scope for row in self.switches)
            != (SwitchScope.GLOBAL, SwitchScope.TENANT, SwitchScope.ACCOUNT)
        ):
            raise ValueError("ALL_THREE_EXPLICIT_SWITCHES_REQUIRED")
        for value in (self.captured_at, self.expires_at):
            _utc(value)
        if self.captured_at >= self.expires_at:
            raise ValueError("RESOURCE_LIFETIME_INVALID")
        if self.reservation_kind is ReservationKind.RESERVED:
            _uuid(self.reservation_id)
            _uuid(self.budget_owner_lock_id)
            _hash(self.budget_baseline_hash)
        elif any(
            value is not None
            for value in (self.reservation_id, self.budget_owner_lock_id, self.budget_baseline_hash)
        ):
            raise ValueError("EXPLICIT_NO_BUDGET_EFFECT_CANNOT_HIDE_RESERVATION")


@dataclass(frozen=True, repr=False)
class FirstClaimProposal:
    target: ClaimTarget
    worker_id: str
    request_hash: str
    next_attempt: int
    next_fencing_token: int
    next_runtime_revision: int
    next_task_revision: int
    next_task_sequence: int
    node_path: tuple[str, str]
    task_state: str
    lease_expires_at: datetime
    transport_eligible: bool = field(default=False, init=False)
    claimed: bool = field(default=False, init=False)
    writes_intent: bool = field(default=False, init=False)
    releases_resources: bool = field(default=False, init=False)
    _transaction: object = field(default=None, repr=False, compare=False)

    def require_same_transaction(self, transaction):
        if transaction is None or transaction is not self._transaction:
            raise ValueError("PROPOSAL_CANNOT_CROSS_TRANSACTION")


@dataclass(frozen=True)
class ClaimDecision:
    code: str
    proposal: FirstClaimProposal | None = field(default=None, repr=False)
    claimed: bool = field(default=False, init=False)
    transport_eligible: bool = field(default=False, init=False)


def propose_first_claim(
    request, snapshot, *, database_now, transaction=None, source_facts=None, resource_facts=None
):
    """仅纯建议；未来真实Store必须另核issuer/proof/锁与当前源，再同事务写入。"""
    if not isinstance(source_facts, ClaimSourceFacts):
        raise OrbitError(503, "EXECUTION_CLAIM_SOURCE_UNAVAILABLE", "真实执行来源尚未就绪")
    if not isinstance(resource_facts, ClaimResourceFacts):
        raise OrbitError(503, "EXECUTION_CLAIM_RESOURCES_UNAVAILABLE", "真实执行资源证明尚未就绪")
    if not isinstance(request, ClaimRequest) or not isinstance(snapshot, LockedClaimSnapshot):
        raise ValueError("TYPED_LOCKED_CLAIM_INPUT_REQUIRED")
    _utc(database_now)
    if transaction is None or any(
        value is not transaction
        for value in (snapshot._transaction, source_facts._transaction, resource_facts._transaction)
    ):
        raise ValueError("CLAIM_FACTS_REQUIRE_SAME_TRANSACTION")
    target = request.target
    if (
        snapshot.target != target
        or source_facts.target != target
        or resource_facts.target != target
        or source_facts.worker_id != request.worker_id
    ):
        return ClaimDecision("CLAIM_BINDING_MISMATCH")
    if not source_facts.worker_enabled:
        return ClaimDecision("CLAIM_WORKER_DISABLED")
    if "launch.execute" not in source_facts.authorized_actions or (
        (target.kind == "ENABLE" or target.purpose == "ENABLE")
        and "launch.publish" not in source_facts.authorized_actions
    ):
        return ClaimDecision("CLAIM_ACTION_DENIED")
    if (
        source_facts.captured_at > database_now
        or source_facts.expires_at <= database_now
        or source_facts.lease_expires_at <= database_now
    ):
        return ClaimDecision("CLAIM_SOURCE_EXPIRED")
    if (
        resource_facts.captured_at > database_now
        or resource_facts.expires_at <= database_now
        or source_facts.lease_expires_at > resource_facts.expires_at
    ):
        return ClaimDecision("CLAIM_RESOURCES_EXPIRED")
    if resource_facts.logical_command_hash != logical_command_hash(target) or tuple(
        row.scope_id for row in resource_facts.switches
    ) != (None, target.tenant_id, target.account_id):
        return ClaimDecision("CLAIM_RESOURCE_BINDING_MISMATCH")
    if any(row.blocked for row in resource_facts.switches):
        return ClaimDecision("CLAIM_KILL_SWITCH_ACTIVE")
    if snapshot.manifest_phase != "COMPLETE" or snapshot.preparation_state != "ACCEPTED":
        return ClaimDecision("CLAIM_MANIFEST_INCOMPLETE")
    counts = _counts(snapshot.node_state_counts)
    if (
        sum(counts.values()) != source_facts.expected_node_count
        or counts.get(snapshot.node_state, 0) < 1
        or aggregate_task_state(tuple(counts)) != snapshot.task_state
    ):
        return ClaimDecision("CLAIM_TASK_AGGREGATE_UNVERIFIED")
    runtime = snapshot.runtime
    current = ExpectedClaimHead(
        snapshot.task_revision,
        snapshot.node_state,
        snapshot.command_state,
        snapshot.node_attempt,
        snapshot.command_attempt,
        runtime.revision if runtime else None,
    )
    if current != request.expected:
        return ClaimDecision("CLAIM_STALE")
    if snapshot.cancel_requested:
        return ClaimDecision("CLAIM_CANCEL_REQUESTED")
    if (
        snapshot.task_state not in {"QUEUED", "RUNNING"}
        or snapshot.node_state != "QUEUED"
        or snapshot.command_state != "QUEUED"
        or snapshot.node_attempt != 0
        or snapshot.command_attempt != 0
    ):
        return ClaimDecision("CLAIM_NOT_FIRST_QUEUED")
    if runtime is not None and runtime.active_attempt is not None:
        return ClaimDecision("CLAIM_ALREADY_ACTIVE")
    parents = snapshot.parents
    if tuple(row.node_id for row in parents) != source_facts.parent_ids or any(
        row.tenant_id != target.tenant_id
        or row.task_id != target.task_id
        or row.node_id == target.node_id
        for row in parents
    ):
        return ClaimDecision("CLAIM_PARENT_BINDING_UNVERIFIED")
    if any(row.state != "SUCCEEDED" for row in parents):
        return ClaimDecision("CLAIM_PARENTS_NOT_SUCCEEDED")
    if (
        snapshot.task_revision == MAX_REVISION
        or snapshot.task_sequence == MAX_REVISION
        or (runtime is not None and runtime.revision == MAX_REVISION)
    ):
        return ClaimDecision("CLAIM_COUNTER_EXHAUSTED")
    after = counts.copy()
    after["QUEUED"] -= 1
    if after["QUEUED"] == 0:
        del after["QUEUED"]
    after["RUNNING"] = after.get("RUNNING", 0) + 1
    proposal = FirstClaimProposal(
        target,
        request.worker_id,
        request_hash(request),
        1,
        1,
        runtime.revision + 1 if runtime else 1,
        snapshot.task_revision + 1,
        snapshot.task_sequence + 1,
        ("QUEUED", "RUNNING"),
        aggregate_task_state(tuple(after)),
        source_facts.lease_expires_at,
        _transaction=transaction,
    )
    return ClaimDecision("CLAIM_FIRST_PROPOSAL_ONLY", proposal)


@dataclass(frozen=True, repr=False)
class ClaimReceipt:
    """未来持久Store的读回DTO；本模块不从proposal制造已提交回执。"""

    receipt_id: str
    request_id: str
    request_hash: str
    binding: AttemptBinding
    runtime_revision: int
    task_revision: int
    task_sequence: int
    lease_expires_at: datetime
    recorded_at: datetime
    transport_eligible: bool = field(default=False, init=False)
    renews_lease: bool = field(default=False, init=False)
    reserves_resources: bool = field(default=False, init=False)

    def __post_init__(self):
        _uuid(self.receipt_id)
        _uuid(self.request_id)
        _hash(self.request_hash)
        if (
            not isinstance(self.binding, AttemptBinding)
            or self.binding.attempt_no != 1
            or self.binding.fencing_token != 1
        ):
            raise ValueError("EXACT_FIRST_ATTEMPT_RECEIPT_REQUIRED")
        for value in (self.runtime_revision, self.task_revision, self.task_sequence):
            _integer(value, MAX_REVISION)
        _utc(self.lease_expires_at)
        _utc(self.recorded_at)
        if self.recorded_at >= self.lease_expires_at:
            raise ValueError("ORIGINAL_RECEIPT_LIFETIME_INVALID")


def match_original_receipt(request, receipt):
    """纯内容匹配，不执行当前读授权；调用者必须另核原回执读取范围。"""
    if not isinstance(request, ClaimRequest) or not isinstance(receipt, ClaimReceipt):
        raise ValueError("TYPED_REQUEST_AND_RECEIPT_REQUIRED")
    binding, target = receipt.binding, request.target
    fields = (
        "tenant_id",
        "task_id",
        "node_id",
        "preparation_id",
        "source_hash",
        "manifest_hash",
        "command_hash",
        "execution_mode",
        "actor_id",
        "subject_id",
        "owner_user_id",
        "owner_team_id",
    )
    if (
        request.request_id != receipt.request_id
        or request.worker_id != binding.worker_id
        or request_hash(request) != receipt.request_hash
        or any(getattr(binding, key) != getattr(target, key) for key in fields)
    ):
        raise OrbitError(409, "EXECUTION_CLAIM_IDEMPOTENCY_CONFLICT", "领取请求与原持久回执不一致")
    return receipt  # 即使租约后来到期，也只是原读回，不续租、不创建attempt、不授发送权。
