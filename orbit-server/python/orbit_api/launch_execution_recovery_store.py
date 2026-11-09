"""既有广告尝试的窄恢复提交；默认无权威，不领取、不发送、不释放任何资源锁。"""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

from orbit_api.launch_execution_lease_contract import MAX_REVISION, _uuid, aggregate_task_state
from orbit_api.launch_execution_lease_store import (
    ExecutionLeaseAuthority,
    ExecutionLeaseStore,
    _database_time,
    _one,
    stale,
    unavailable,
    unverified,
)
from orbit_api.task_contract import MAX_NODES


@dataclass(frozen=True, repr=False)
class RecoveryReceipt:
    changed: bool
    decision_id: str | None
    runtime_revision: int
    task_revision: int
    task_sequence: int
    node_state: str
    task_state: str


async def _write(session, sql, values):
    if (await session.execute(text(sql), values)).rowcount != 1:
        stale()


async def _insert(session, table, values):
    # 仅模块内固定表/列；所有业务值均绑定参数，不能把请求字段作为标识符。
    columns = ",".join(values)
    await _write(
        session,
        f"INSERT INTO {table}({columns}) VALUES(" + ",".join(":" + key for key in values) + ")",
        values,
    )


async def _current_task_counts(session, values, expected_count, now):
    """Task锁内当前键集读取，常数状态计数，不能依赖已有RR快照。"""
    counts, after, manual = Counter(), -1, False
    while True:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT id,ordinal,state FROM orbit_task_node WHERE "
                        "tenant_id=:tenant AND task_id=:task "
                        "AND ordinal>:after ORDER BY ordinal LIMIT 500 FOR SHARE"
                    ),
                    values | {"after": after},
                )
            )
            .mappings()
            .all()
        )
        if len(rows) > 500:
            unverified()
        if not rows:
            break
        for row in rows:
            if type(row["ordinal"]) is not int or row["ordinal"] != after + 1:
                unverified()
            # 原聚合函数也验证枚举；未知状态不能作为FAILED吞掉。
            try:
                aggregate_task_state((row["state"],))
            except ValueError:
                unverified()
            counts[row["state"]] += 1
            after = row["ordinal"]
        unknown_ids = sorted(row["id"] for row in rows if row["state"] == "UNKNOWN")
        if unknown_ids:
            parameters = values | {
                f"unknown_{i}": identifier for i, identifier in enumerate(unknown_ids)
            }
            placeholders = ",".join(f":unknown_{i}" for i in range(len(unknown_ids)))
            runtime_rows = (
                (
                    await session.execute(
                        text(
                            "SELECT node_id,unknown_since,needs_manual_reconciliation "
                            "FROM orbit_execution_command_runtime WHERE tenant_id=:tenant "
                            "AND task_id=:task "
                            f"AND node_id IN({placeholders}) ORDER BY node_id FOR SHARE"
                        ),
                        parameters,
                    )
                )
                .mappings()
                .all()
            )
            if [row["node_id"] for row in runtime_rows] != unknown_ids:
                unverified()
            for runtime in runtime_rows:
                if runtime["unknown_since"] is None:
                    unverified()
                since = _database_time(runtime["unknown_since"])
                if since > now or runtime["needs_manual_reconciliation"] not in (0, 1):
                    unverified()
                manual |= bool(runtime["needs_manual_reconciliation"]) or now >= since + timedelta(
                    hours=24
                )
        if after + 1 > MAX_NODES:
            unverified()
    if after + 1 != expected_count or sum(counts.values()) != expected_count:
        unverified()
    return counts, manual


async def _verify_edge_links(session, values, identifier, request_id, actor_id, now, count):
    """封存前读取实际事件/审计/outbox；七日清理不受永久FK阻碍。"""
    rows = (
        (
            await session.execute(
                text(
                    "SELECT e.ordinal FROM orbit_execution_recovery_edge e "
                    "JOIN orbit_task_event v ON v.tenant_id=e.tenant_id AND v.task_id=e.task_id "
                    "AND v.event_id=e.event_id AND v.sequence=e.event_sequence "
                    "AND v.task_revision=e.task_revision AND v.node_id=e.node_id "
                    "AND v.state=e.node_after_state "
                    "JOIN orbit_task_audit a ON a.tenant_id=e.tenant_id AND a.task_id=e.task_id "
                    "AND a.id=e.audit_id JOIN orbit_task_outbox o ON o.tenant_id=a.tenant_id "
                    "AND o.task_id=a.task_id AND o.audit_id=a.id "
                    "WHERE e.tenant_id=:tenant AND e.task_id=:task AND e.node_id=:node "
                    "AND e.decision_id=:decision AND v.request_id=:request "
                    "AND a.request_id=:request "
                    "AND a.actor_id=:actor AND v.occurred_at=:now AND a.created_at=:now "
                    "AND o.created_at=:now ORDER BY e.ordinal LIMIT 4 FOR SHARE"
                ),
                values
                | {"decision": identifier, "request": request_id, "actor": actor_id, "now": now},
            )
        )
        .mappings()
        .all()
    )
    if [row["ordinal"] for row in rows] != list(range(1, count + 1)):
        unverified()


class ExecutionRecoveryStore:
    """只消费受控原恢复authority；外层事务负责提交和任何失败整笔回滚。"""

    def __init__(self, authority=None):
        self.authority = authority

    async def recover_expired(self, session, actor_id, binding, expected, request_id):
        if not isinstance(self.authority, ExecutionLeaseAuthority):
            unavailable()
        _uuid(request_id)
        captured = await ExecutionLeaseStore(self.authority).capture_recovery(
            session, actor_id, binding, expected
        )
        decision = captured.decision(session)
        values = {"tenant": binding.tenant_id, "task": binding.task_id, "node": binding.node_id}
        task = await _one(
            session,
            "SELECT * FROM orbit_task WHERE tenant_id=:tenant AND id=:task FOR UPDATE",
            values,
        )
        runtime = await _one(
            session,
            "SELECT * FROM orbit_execution_command_runtime WHERE tenant_id=:tenant AND "
            "task_id=:task AND node_id=:node FOR UPDATE",
            values,
        )
        clock = await _one(
            session,
            "SELECT revision FROM orbit_task_clock WHERE tenant_id=:tenant FOR UPDATE",
            values,
        )
        stamp = await _one(session, "SELECT UTC_TIMESTAMP(3) AS now", {})
        if task is None or runtime is None or clock is None or stamp is None:
            unverified()
        now3 = _database_time(stamp["now"])
        counts, others_manual = await _current_task_counts(
            session, values, task["node_count"], captured.database_now
        )
        initial = captured.snapshot.state
        if counts[initial] < 1:
            unverified()
        new_manual = (
            bool(runtime["needs_manual_reconciliation"]) or decision.needs_manual_reconciliation
        )
        task_manual = bool(task["needs_manual_reconciliation"]) or others_manual or new_manual
        edges = [
            (before, after, "STATE")
            for before, after in zip(decision.state_path, decision.state_path[1:], strict=False)
        ]
        if decision.needs_manual_reconciliation and (
            not runtime["needs_manual_reconciliation"] or not task["needs_manual_reconciliation"]
        ):
            edges.append(("UNKNOWN", "UNKNOWN", "MANUAL"))
        if not edges:
            return RecoveryReceipt(
                False,
                None,
                expected.revision,
                task["revision"],
                task["latest_sequence"],
                initial,
                task["state"],
            )
        if not 1 <= len(edges) <= 3:
            unverified()
        for key, addition in [("revision", len(edges)), ("latest_sequence", len(edges))]:
            if type(task[key]) is not int or not 0 <= task[key] <= MAX_REVISION - addition:
                unverified()
        if expected.revision >= MAX_REVISION or clock["revision"] >= MAX_REVISION:
            stale()
        captured.decision(session)  # 精确封印及外层事务仍有效，不接调用者决策。
        identifier = str(uuid4())
        head = {
            "tenant_id": binding.tenant_id,
            "id": identifier,
            "task_id": binding.task_id,
            "node_id": binding.node_id,
            "attempt_no": binding.attempt_no,
            "fencing_token": binding.fencing_token,
            "claim_id": binding.claim_id,
            "worker_id": binding.worker_id,
            "before_runtime_revision": expected.revision,
            "after_runtime_revision": expected.revision + 1,
            "before_task_revision": task["revision"],
            "after_task_revision": task["revision"] + len(edges),
            "before_task_sequence": task["latest_sequence"],
            "after_task_sequence": task["latest_sequence"] + len(edges),
            "before_task_clock": clock["revision"],
            "after_task_clock": clock["revision"] + 1,
            "fact_count": captured.summary.total_count,
            "fact_last_sequence": captured.summary.last_sequence,
            "fact_root_sha256": captured.summary.root_sha256,
            "hash_schema_version": 1,
            "publication_phase": "BUILDING",
            "decision_code": decision.code,
            "state_path_json": json.dumps(decision.state_path),
            "event_count": len(edges),
            "actor_id": actor_id,
            "request_id": request_id,
            "decided_at": captured.database_now.replace(tzinfo=None),
        }
        await _insert(session, "orbit_execution_recovery_decision", head)
        final = decision.state_path[-1]
        unknown = (
            runtime["unknown_since"]
            if initial == "UNKNOWN"
            else (now3.replace(tzinfo=None) if final == "UNKNOWN" else None)
        )
        next_read = runtime["next_reconcile_at"]
        if final == "UNKNOWN" and initial != "UNKNOWN":
            next_read = now3.replace(tzinfo=None) + timedelta(minutes=5)
        if new_manual:
            next_read = None
        await _write(
            session,
            "UPDATE orbit_execution_command_runtime SET revision=revision+1,unknown_since=:unknown,"
            "next_reconcile_at=:next_read,needs_manual_reconciliation=:manual,updated_at=:now "
            "WHERE tenant_id=:tenant AND task_id=:task AND node_id=:node AND "
            "revision=:old_revision "
            "AND active_attempt=:attempt AND fencing_token=:fence AND claim_id=:claim AND "
            "worker_id=:worker",
            values
            | {
                "unknown": unknown,
                "next_read": next_read,
                "manual": new_manual,
                "now": now3.replace(tzinfo=None),
                "old_revision": expected.revision,
                "attempt": expected.attempt_no,
                "fence": expected.fencing_token,
                "claim": expected.claim_id,
                "worker": expected.worker_id,
            },
        )
        revision, sequence = task["revision"], task["latest_sequence"]
        latest_event = task["latest_event_id"]
        current_task_state = task["state"]
        for ordinal, (before, after, kind) in enumerate(edges, 1):
            if kind == "STATE":
                node_values = values | {
                    "before": before,
                    "after": after,
                    "attempt": binding.attempt_no,
                    "now": now3.replace(tzinfo=None),
                    "retryable": decision.retryable if after == "FAILED" else False,
                    "error": "CONFIRMED_NOT_SENT"
                    if after == "FAILED"
                    else (decision.code if after == "UNKNOWN" else None),
                }
                await _write(
                    session,
                    "UPDATE orbit_launch_execution_command SET state=:after,updated_at=:now "
                    "WHERE tenant_id=:tenant AND task_id=:task AND node_id=:node AND "
                    "state=:before AND attempt=:attempt",
                    node_values,
                )
                await _write(
                    session,
                    "UPDATE orbit_task_node SET "
                    "state=:after,retryable=:retryable,error_code=:error,"
                    "error_message=NULL,updated_at=:now WHERE tenant_id=:tenant AND task_id=:task "
                    "AND id=:node AND state=:before AND attempt=:attempt",
                    node_values,
                )
                counts[before] -= 1
                counts[after] += 1
            if any(count < 0 for count in counts.values()):
                unverified()
            current_task_state = aggregate_task_state(
                tuple(state for state, count in counts.items() if count)
            )
            revision += 1
            sequence += 1
            latest_event, audit_id = str(uuid4()), str(uuid4())
            await _insert(
                session,
                "orbit_task_event",
                {
                    "tenant_id": binding.tenant_id,
                    "task_id": binding.task_id,
                    "event_id": latest_event,
                    "sequence": sequence,
                    "schema_version": 1,
                    "task_revision": revision,
                    "node_id": binding.node_id,
                    "state": after,
                    "occurred_at": now3.replace(tzinfo=None),
                    "request_id": request_id,
                },
            )
            await _insert(
                session,
                "orbit_task_audit",
                {
                    "id": audit_id,
                    "tenant_id": binding.tenant_id,
                    "task_id": binding.task_id,
                    "actor_id": actor_id,
                    "request_id": request_id,
                    "action": "RECOVERY_MANUAL" if kind == "MANUAL" else "RECOVERY_" + after,
                    "created_at": now3.replace(tzinfo=None),
                },
            )
            await _insert(
                session,
                "orbit_task_outbox",
                {
                    "audit_id": audit_id,
                    "tenant_id": binding.tenant_id,
                    "task_id": binding.task_id,
                    "created_at": now3.replace(tzinfo=None),
                },
            )
            await _insert(
                session,
                "orbit_execution_recovery_edge",
                {
                    "tenant_id": binding.tenant_id,
                    "task_id": binding.task_id,
                    "node_id": binding.node_id,
                    "decision_id": identifier,
                    "ordinal": ordinal,
                    "event_id": latest_event,
                    "event_sequence": sequence,
                    "task_revision": revision,
                    "node_before_state": before,
                    "node_after_state": after,
                    "task_after_state": current_task_state,
                    "edge_kind": kind,
                    "audit_id": audit_id,
                },
            )
        await _write(
            session,
            "UPDATE orbit_task SET "
            "revision=:revision,state=:state,needs_manual_reconciliation=:manual,"
            "latest_event_id=:event,latest_sequence=:sequence,updated_at=:now "
            "WHERE tenant_id=:tenant AND id=:task AND revision=:old_revision "
            "AND latest_sequence=:old_sequence",
            values
            | {
                "revision": revision,
                "state": current_task_state,
                "manual": task_manual,
                "event": latest_event,
                "sequence": sequence,
                "now": now3.replace(tzinfo=None),
                "old_revision": task["revision"],
                "old_sequence": task["latest_sequence"],
            },
        )
        await _write(
            session,
            "UPDATE orbit_task_clock SET revision=revision+1 WHERE tenant_id=:tenant AND "
            "revision=:clock",
            values | {"clock": clock["revision"]},
        )
        await _verify_edge_links(
            session, values, identifier, request_id, actor_id, now3.replace(tzinfo=None), len(edges)
        )
        await _write(
            session,
            "UPDATE orbit_execution_recovery_decision SET publication_phase='SEALED' WHERE "
            "tenant_id=:tenant AND id=:id AND publication_phase='BUILDING'",
            {"tenant": binding.tenant_id, "id": identifier},
        )
        return RecoveryReceipt(
            True, identifier, expected.revision + 1, revision, sequence, final, current_task_state
        )
