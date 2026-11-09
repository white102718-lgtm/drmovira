"""054恢复扫描普通混合真实SQL专项；技术维护provider不是生产issuer或平台证明。"""

import asyncio
import hashlib
import json
import time
from dataclasses import replace
from datetime import UTC, timedelta
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy import URL, event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_lease_contract import (
    AttemptBinding,
    EvidenceSource,
    FactKind,
    SendPhase,
)
from orbit_api.launch_execution_lease_store import (
    ExecutionLeaseAuthority,
    LeaseOperation,
    RuntimeExpectation,
)
from orbit_api.launch_execution_recovery_scanner import (
    ExecutionRecoveryScanner,
    MaintenanceScanGrant,
    RecoveryBucket,
    RecoveryScanAuthorityProvider,
)
from orbit_api.launch_execution_recovery_service import ExecutionRecoveryService

if __package__:
    from .launch_execution_fixture import create_protocol_plan
    from .launch_execution_lease_checks import guard_execution_lease_target
    from .launch_execution_lease_store_checks import (
        IsolatedLeaseEvidenceAuthority,
        evidence_document,
    )
else:
    from launch_execution_fixture import create_protocol_plan
    from launch_execution_lease_checks import guard_execution_lease_target
    from launch_execution_lease_store_checks import (
        IsolatedLeaseEvidenceAuthority,
        evidence_document,
    )

SCANNER_CASES = [
    "pythonRecoveryScanner054DefaultUnavailableBeforeDatabaseInitialization",
    "pythonRecoveryScanner054Original202CompleteTaskTechnicalRuntimeSource",
    "pythonRecoveryScanner054MoreThan400OldUnknownRawRowsReachLaterCandidate",
    "pythonRecoveryScanner054ThreeBucketsAndTrustedCurrentScope",
    "pythonRecoveryScanner054CandidateBudgetDoesNotLoseRemainingPage",
    "pythonRecoveryScanner054TwoRealScannersCommitOneExactCas",
    "pythonRecoveryScanner054Outbox1644LeavesDataAndFailedCandidateCursorUnadvanced",
    "pythonRecoveryScanner054RevokedMaintenanceGrantStopsNextCandidate",
    "pythonRecoveryScanner054ActualClockLockCancelTimeoutDrainsTransactions",
    "pythonRecoveryScanner054ThreeIndexDefinitionsAndRealExplainPlans",
]

SERVICE_CASES = [
    "pythonRecoveryService054RealOnceCommitsOriginalRecovery",
    "pythonRecoveryService054RealInflightServeStopDrainsExactTransaction",
    "pythonRecoveryService054OriginalGrantDriftStopsWithoutRenewal",
    "pythonRecoveryService054RealServer1205TerminatesWithoutAutomaticRetry",
]


def assert_service_cleanup(service, outcome, scanners):
    """精确任务退出只证明当前服务清理；SQL/P_S与池复位另行实际核对。"""
    assert outcome["cleanup_complete"] is True and service.state == "STOPPED"
    assert len(scanners) == 1 and service.scanner is scanners[0]
    assert service.retained_tasks == ()
    assert service.active_task is not None and service.active_task.done()
    assert not service.active_task.cancelled() and service.active_task.exception() is None
    assert scanners[0]._running is False


def three_bucket_diagnostic(before_accepted, before_manual, after_accepted, after_manual, report):
    """仅白名单状态/整数水位/计数，不含UUID、SQL、原响应、来源对象或凭据。"""
    allowed = {
        "DRAFT",
        "VALIDATED",
        "QUEUED",
        "RUNNING",
        "ACCEPTED",
        "VERIFYING",
        "SUCCEEDED",
        "FAILED",
        "UNKNOWN",
        "RETRY_WAIT",
        "CANCELLED",
        "EXPIRED",
        "BLOCKED_AUTH",
        "BLOCKED_DEPENDENCY",
        "NEEDS_HUMAN",
    }

    def snapshot(before, after):
        if not isinstance(after, tuple) or len(after) != 3 or after[0] not in allowed:
            raise ValueError("诊断状态必须为受控原枚举")
        numbers = (before.revision, before.attempt_no, after[1], after[2])
        if any(type(value) is not int or value < 1 for value in numbers):
            raise ValueError("诊断水位必须为正整数")
        return {
            "before_runtime_revision": before.revision,
            "before_attempt": before.attempt_no,
            "after_state": after[0],
            "after_attempt": after[1],
            "after_runtime_revision": after[2],
        }

    counts = {
        key: getattr(report, key)
        for key in (
            "pages",
            "raw_rows",
            "attempted",
            "recovered",
            "noop",
            "stale",
            "blocked",
            "filtered",
        )
    }
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError("诊断计数必须为非负整数")
    return {
        "scope": "recovery-scanner-fixture",
        "phase": "three-buckets-state",
        "accepted": snapshot(before_accepted, after_accepted),
        "manual": snapshot(before_manual, after_manual),
        "counts": counts,
    }


def safe_lock_wait_diagnostic(rows):
    """只输出自有等待连接数值身份与状态分类，不接收SQL文本或对象ID。"""
    result = []
    for row in rows:
        if len(row) != 8:
            raise ValueError("锁等待诊断必须固定八字段")
        requesting, blocking, connection, command, state, seconds, status, timeout = row

        def number(value):
            if value is None:
                return None
            if type(value) is not int or value < 0:
                raise ValueError("诊断身份必须为非负整数")
            return value

        commands = {
            "Query": "QUERY",
            "Sleep": "SLEEP",
            "Killed": "KILLED",
            "Connect": "CONNECT",
            "Daemon": "DAEMON",
        }
        state_class = (
            "GONE"
            if connection is None
            else (
                "NO_STATE"
                if state is None
                else (
                    "LOCK_WAIT"
                    if "lock" in str(state).lower()
                    else (
                        "EXECUTING"
                        if state in ("executing", "Sending data", "updating")
                        else "OTHER"
                    )
                )
            )
        )
        if status not in ("WAITING", "GRANTED"):
            raise ValueError("诊断锁状态非法")
        if timeout is not None:
            if not isinstance(timeout, str) or not timeout.isascii() or not timeout.isdecimal():
                raise ValueError("诊断等待期限必须为十进制整数")
            timeout = int(timeout)
        result.append(
            {
                "requesting_thread": number(requesting),
                "blocking_thread": number(blocking),
                "connection_id": number(connection),
                "command_class": commands.get(command, "OTHER"),
                "state_class": state_class,
                "process_seconds": number(seconds),
                "lock_status": status,
                "server_lock_wait_timeout": timeout,
            }
        )
    return {
        "scope": "recovery-scanner-fixture",
        "phase": "owned-lock-wait-diagnostic",
        "waits": result,
    }


def assert_expired_accepted_recovery(query, tenant, attempt, before):
    """同轮两次原恢复均须精确落库，不以多个允许终态放宽。"""
    heads = query(
        "SELECT before_runtime_revision,after_runtime_revision,decision_code,event_count,"
        "publication_phase,before_task_revision,after_task_revision,before_task_sequence,"
        "after_task_sequence FROM orbit_execution_recovery_decision "
        "WHERE tenant_id=%s AND task_id=%s AND node_id=%s ORDER BY after_runtime_revision",
        (tenant, attempt.task_id, attempt.node_id),
    )
    assert len(heads) == 2
    assert heads[0][:5] == (
        before.revision,
        before.revision + 1,
        "ACCEPTED_REQUIRES_READBACK",
        1,
        "SEALED",
    )
    assert heads[1][:5] == (
        before.revision + 1,
        before.revision + 2,
        "LEASE_OUTCOME_UNKNOWN",
        1,
        "SEALED",
    )
    assert all(row[6] == row[5] + 1 and row[8] == row[7] + 1 for row in heads)
    assert heads[1][5] == heads[0][6] and heads[1][7] == heads[0][8]
    edges = query(
        "SELECT e.node_before_state,e.node_after_state,v.state,"
        "v.task_revision,v.sequence,v.node_id "
        "FROM orbit_execution_recovery_decision d JOIN orbit_execution_recovery_edge e "
        "ON e.tenant_id=d.tenant_id AND e.decision_id=d.id "
        "JOIN orbit_task_event v ON v.tenant_id=e.tenant_id AND v.task_id=e.task_id "
        "AND v.event_id=e.event_id WHERE d.tenant_id=%s AND d.task_id=%s "
        "AND d.node_id=%s ORDER BY d.after_runtime_revision,e.ordinal",
        (tenant, attempt.task_id, attempt.node_id),
    )
    assert edges == (
        ("ACCEPTED", "VERIFYING", "VERIFYING", heads[0][6], heads[0][8], attempt.node_id),
        ("VERIFYING", "UNKNOWN", "UNKNOWN", heads[1][6], heads[1][8], attempt.node_id),
    )
    assert query(
        "SELECT c.state,n.state,n.attempt,r.active_attempt,r.fencing_token,r.claim_id,r.worker_id,"
        "r.revision FROM orbit_launch_execution_command c JOIN orbit_task_node n "
        "ON n.tenant_id=c.tenant_id AND n.task_id=c.task_id AND n.id=c.node_id "
        "JOIN orbit_execution_command_runtime r ON r.tenant_id=c.tenant_id AND r.task_id=c.task_id "
        "AND r.node_id=c.node_id WHERE c.tenant_id=%s AND c.task_id=%s AND c.node_id=%s",
        (tenant, attempt.task_id, attempt.node_id),
    )[0] == (
        "UNKNOWN",
        "UNKNOWN",
        attempt.attempt_no,
        attempt.attempt_no,
        attempt.fencing_token,
        attempt.claim_id,
        attempt.worker_id,
        before.revision + 2,
    )
    assert query(
        "SELECT state,revision,latest_sequence FROM orbit_task WHERE tenant_id=%s AND id=%s",
        (tenant, attempt.task_id),
    )[0] == ("UNKNOWN", heads[1][6], heads[1][8])


class _TechnicalAuthority(ExecutionLeaseAuthority):
    def __init__(self, provider):
        self.provider = provider

    async def authorize(self, session, actor, binding, operation):
        provider = self.provider
        current = await provider.current(provider.grant)
        if current != provider.grant:
            raise OrbitError(503, "RECOVERY_SCAN_AUTHORITY_CHANGED", "仅本轮技术维护来源已变化")
        result = await IsolatedLeaseEvidenceAuthority(
            provider.database, provider.bindings, provider.evidence
        ).authorize(session, actor, binding, operation)
        if binding.node_id == provider.barrier_target:
            # 仅并发测试屏障，尚未取得Task锁；不构成生产来源实现。
            provider.arrivals += 1
            if provider.arrivals == 2:
                provider.release.set()
            await asyncio.wait_for(provider.release.wait(), 5)
        if binding.node_id == provider.revoke_target:
            provider.revoked = True
        return result

    async def verify_fact(self, session, fact, *, recorded_at):
        return await IsolatedLeaseEvidenceAuthority(
            self.provider.database, self.provider.bindings, self.provider.evidence
        ).verify_fact(session, fact, recorded_at=recorded_at)


class TechnicalScannerProvider(RecoveryScanAuthorityProvider):
    """仅显式工具使用；actual UUID/13306 guard在factory和每次事实authority中执行。"""

    def __init__(self, admin, database, tenant, bindings, evidence, now):
        guard_execution_lease_target(admin, database)
        self.database, self.bindings, self.evidence = database, bindings, evidence
        self.grant = MaintenanceScanGrant(
            str(uuid4()),
            str(uuid4()),
            1,
            (tenant,),
            LeaseOperation.RECOVER_EXPIRED,
            1,
            now + timedelta(hours=1),
        )
        self.revoked = False
        self.revoke_target = None
        self.barrier_target = None
        self.arrivals = 0
        self.release = asyncio.Event()

    async def capture(self):
        return self.grant

    async def current(self, grant):
        return replace(self.grant, revision=self.grant.revision + 1) if self.revoked else self.grant

    async def authority(self, grant):
        return _TechnicalAuthority(self)


def run_execution_recovery_scanner_checks(
    client, admin, headers, password, cache, database, cases, *, include_service=False
):
    if type(include_service) is not bool:
        raise ValueError("服务专项必须显式布尔开关")
    guard_execution_lease_target(admin, database)

    def query(sql, values=()):
        with admin.cursor() as cursor:
            cursor.execute(sql, values)
            result = cursor.fetchall()
        admin.commit()
        return result

    def execute(sql, values=()):
        with admin.cursor() as cursor:
            cursor.execute(sql, values)
            return cursor.rowcount

    def checked(response, status):
        assert response.status_code == status, {
            "expected_status": status,
            "actual_status": response.status_code,
        }
        return response.json()

    assert query("SELECT DATABASE()")[0][0] == database
    tenant, owner, team = query(
        "SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1"
    )[0]
    capabilities = checked(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)

    def write(revision):
        return headers | {
            "X-CSRF-Token": capabilities["csrf_token"],
            "If-Match": f'"{revision}"',
            "Idempotency-Key": str(uuid4()),
        }

    def validated_plan():
        item = create_protocol_plan(admin, tenant, owner, team)
        result = checked(
            client.post(
                f"/api/v1/launch-plans/{item['id']}/validate", headers=write(1), json=item["body"]
            ),
            200,
        )
        assert result["valid"] and result["hash"]
        return item, result

    bindings, evidence, timestamps = {}, {}, {}

    def accept_and_seed(item, validation, *, count=1):
        task = checked(
            client.post(
                f"/api/v1/launch-plans/{item['id']}/execute",
                headers=write(2),
                json={"hash": validation["hash"], "activate_ack": False},
            ),
            202,
        )
        assert task["state"] == "QUEUED" and task["revision"] == 1
        if count is None:
            count = task["node_count"]
        prep = query(
            "SELECT id,manifest_hash,payload_hash,authorization_fingerprint,actor_id,subject_id,"
            "auth_version FROM orbit_launch_execution_preparation WHERE tenant_id=%s "
            "AND task_id=%s AND state='ACCEPTED'",
            (tenant, task["id"]),
        )[0]
        commands = query(
            "SELECT node_id,resolved_configuration_hash FROM orbit_launch_execution_command "
            "WHERE tenant_id=%s AND task_id=%s ORDER BY ordinal LIMIT %s",
            (tenant, task["id"], count),
        )
        assert len(commands) == count
        assert query(
            "SELECT manifest_phase,node_count,expected_node_count FROM orbit_task WHERE "
            "tenant_id=%s AND id=%s",
            (tenant, task["id"]),
        )[0] == ("COMPLETE", task["node_count"], task["node_count"])
        now = query("SELECT UTC_TIMESTAMP(3)")[0][0].replace(tzinfo=UTC)
        chosen = []
        admin.begin()
        try:
            # 只为读取协议构造运行技术样本；不是Worker领取或实际发出命令。
            for node, command_hash in commands:
                attempt = AttemptBinding(
                    tenant,
                    task["id"],
                    node,
                    prep[0],
                    str(uuid4()),
                    str(uuid4()),
                    1,
                    1,
                    command_hash,
                    prep[1],
                    prep[2],
                    hashlib.sha256(canonical(["ISOLATED_SQL_NOT_SEND", node]).encode()).hexdigest(),
                    prep[3],
                    task["execution_mode"],
                    prep[4],
                    prep[5],
                    owner,
                    team,
                    prep[6],
                )
                execute(
                    "INSERT INTO orbit_execution_attempt(tenant_id,task_id,node_id,preparation_id,"
                    "attempt_no,fencing_token,claim_id,worker_id,execution_mode,command_hash,"
                    "manifest_hash,source_hash,authority_hash,authorization_hash,actor_id,"
                    "subject_id,"
                    "owner_user_id,owner_team_id,auth_version,created_at) VALUES("
                    "%s,%s,%s,%s,1,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        tenant,
                        task["id"],
                        node,
                        prep[0],
                        attempt.claim_id,
                        attempt.worker_id,
                        attempt.execution_mode,
                        command_hash,
                        prep[1],
                        prep[2],
                        attempt.authority_hash,
                        prep[3],
                        prep[4],
                        prep[5],
                        owner,
                        team,
                        prep[6],
                        (now - timedelta(days=2)).replace(tzinfo=None),
                    ),
                )
                execute(
                    "INSERT INTO orbit_execution_command_runtime(tenant_id,task_id,node_id,"
                    "revision,"
                    "active_attempt,fencing_token,claim_id,worker_id,lease_expires_at,created_at,"
                    "updated_at) VALUES(%s,%s,%s,1,1,1,%s,%s,%s,%s,%s)",
                    (
                        tenant,
                        task["id"],
                        node,
                        attempt.claim_id,
                        attempt.worker_id,
                        (now - timedelta(seconds=1)).replace(tzinfo=None),
                        (now - timedelta(days=2)).replace(tzinfo=None),
                        now.replace(tzinfo=None),
                    ),
                )
                execute(
                    "UPDATE orbit_launch_execution_command SET state='RUNNING',attempt=1,"
                    "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                    (tenant, task["id"], node),
                )
                execute(
                    "UPDATE orbit_task_node SET state='RUNNING',attempt=1,"
                    "updated_at=UTC_TIMESTAMP(3) "
                    "WHERE tenant_id=%s AND task_id=%s AND id=%s",
                    (tenant, task["id"], node),
                )
                bindings[node] = attempt
                timestamps[node] = now - timedelta(seconds=1)
                chosen.append(attempt)
            admin.commit()
        except BaseException:
            admin.rollback()
            raise
        return task, chosen

    def new_task(*, count=1):
        item, validation = validated_plan()
        task, attempts = accept_and_seed(item, validation, count=count)
        return task, attempts

    def change(attempt, *, state=None, lease_future=False, unknown_age=None, manual=False):
        admin.begin()
        try:
            if state:
                for table, column in [
                    ("orbit_launch_execution_command", "node_id"),
                    ("orbit_task_node", "id"),
                ]:
                    execute(
                        f"UPDATE {table} SET state=%s,updated_at=UTC_TIMESTAMP(3) WHERE "
                        f"tenant_id=%s AND task_id=%s AND {column}=%s",
                        (state, tenant, attempt.task_id, attempt.node_id),
                    )
            if lease_future:
                execute(
                    "UPDATE orbit_execution_command_runtime SET revision=revision+1,"
                    "lease_expires_at=UTC_TIMESTAMP(3)+INTERVAL 1 HOUR,"
                    "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                    (tenant, attempt.task_id, attempt.node_id),
                )
            if unknown_age is not None:
                now = query_no_commit("SELECT UTC_TIMESTAMP(3)")[0][0]
                since = now - timedelta(minutes=unknown_age)
                execute(
                    "UPDATE orbit_execution_command_runtime SET revision=revision+1,"
                    "unknown_since=%s,next_reconcile_at=%s,needs_manual_reconciliation=%s,"
                    "updated_at=%s WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                    (
                        since,
                        since + timedelta(minutes=5),
                        manual,
                        now,
                        tenant,
                        attempt.task_id,
                        attempt.node_id,
                    ),
                )
            admin.commit()
        except BaseException:
            admin.rollback()
            raise

    def query_no_commit(sql, parameters=()):
        with admin.cursor() as cursor:
            cursor.execute(sql, parameters)
            return cursor.fetchall()

    def add(attempt, kinds):
        admin.begin()
        try:
            for sequence, kind in enumerate(kinds, 1):
                phase, source = {
                    FactKind.PROVED_NOT_SENT: (
                        SendPhase.BEFORE_DISPATCH,
                        EvidenceSource.TRANSPORT_PROVEN_NO_SEND,
                    ),
                    FactKind.WRITE_INTENT: (SendPhase.BEFORE_DISPATCH, EvidenceSource.LOCAL_INTENT),
                    FactKind.ACCEPTED: (SendPhase.ACKNOWLEDGED, EvidenceSource.PLATFORM_ACK),
                    FactKind.READBACK_SUCCEEDED: (
                        SendPhase.READBACK,
                        EvidenceSource.PLATFORM_READBACK,
                    ),
                    FactKind.READBACK_REJECTED: (
                        SendPhase.READBACK,
                        EvidenceSource.PLATFORM_READBACK,
                    ),
                    FactKind.READBACK_INCONCLUSIVE: (
                        SendPhase.READBACK,
                        EvidenceSource.PLATFORM_READBACK,
                    ),
                }[kind]
                identifier = str(uuid4())
                occurred = timestamps[attempt.node_id]
                external = "12345" if kind == FactKind.READBACK_SUCCEEDED else None
                document = canonical(
                    evidence_document(attempt, identifier, kind, phase, source, occurred, external)
                ).encode()
                evidence[identifier] = document
                execute(
                    "INSERT INTO orbit_execution_attempt_fact(tenant_id,task_id,node_id,"
                    "attempt_no,fencing_token,claim_id,worker_id,event_id,sequence_no,"
                    "fact_kind,send_phase,evidence_source,evidence_sha256,external_id,"
                    "occurred_at,recorded_at) VALUES(%s,%s,%s,1,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "%s,UTC_TIMESTAMP(6))",
                    (
                        tenant,
                        attempt.task_id,
                        attempt.node_id,
                        attempt.claim_id,
                        attempt.worker_id,
                        identifier,
                        sequence,
                        kind.value,
                        phase.value,
                        source.value,
                        hashlib.sha256(document).hexdigest(),
                        external,
                        occurred.replace(tzinfo=None),
                    ),
                )
            admin.commit()
        except BaseException:
            admin.rollback()
            raise

    def expected(attempt):
        row = query(
            "SELECT revision,active_attempt,fencing_token,claim_id,worker_id FROM "
            "orbit_execution_command_runtime WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
            (tenant, attempt.task_id, attempt.node_id),
        )[0]
        return RuntimeExpectation(*row)

    def snapshot(task_id):
        result = {}
        for table, order in [
            ("orbit_task", "id"),
            ("orbit_task_node", "ordinal"),
            ("orbit_launch_execution_command", "ordinal"),
            ("orbit_execution_command_runtime", "node_id"),
            ("orbit_execution_attempt", "node_id,attempt_no"),
            ("orbit_execution_attempt_fact", "node_id,attempt_no,sequence_no"),
            ("orbit_task_event", "sequence"),
            ("orbit_task_event_cursor", "sequence"),
            ("orbit_task_event_retention", "task_id"),
            ("orbit_task_audit", "id"),
            ("orbit_task_outbox", "audit_id"),
            ("orbit_execution_recovery_decision", "id"),
            ("orbit_execution_recovery_edge", "decision_id,ordinal"),
        ]:
            predicate = "id" if table == "orbit_task" else "task_id"
            result[table] = query(
                f"SELECT * FROM {table} WHERE tenant_id=%s AND {predicate}=%s ORDER BY {order}",
                (tenant, task_id),
            )
        result["clock"] = query(
            "SELECT revision FROM orbit_task_clock WHERE tenant_id=%s", (tenant,)
        )
        return result

    def runtime_identity(attempt):
        return query(
            "SELECT active_attempt,fencing_token,claim_id,worker_id,lease_expires_at,"
            "last_reconciled_at FROM orbit_execution_command_runtime WHERE tenant_id=%s AND "
            "task_id=%s AND node_id=%s",
            (tenant, attempt.task_id, attempt.node_id),
        )[0]

    def credential(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=credential(admin.user),
        password=credential(admin.password),
        host="127.0.0.1",
        port=13306,
        database=database,
    )

    def phase(value):
        print("recovery-scanner-fixture phase=" + value, flush=True)

    def old_unknown(attempts):
        admin.begin()
        try:
            for attempt in attempts:
                for table, column in [
                    ("orbit_launch_execution_command", "node_id"),
                    ("orbit_task_node", "id"),
                ]:
                    execute(
                        f"UPDATE {table} SET state='UNKNOWN',updated_at=UTC_TIMESTAMP(3) WHERE "
                        f"tenant_id=%s AND task_id=%s AND {column}=%s",
                        (tenant, attempt.task_id, attempt.node_id),
                    )
                execute(
                    "UPDATE orbit_execution_command_runtime SET revision=revision+1,"
                    "unknown_since=UTC_TIMESTAMP(3)-INTERVAL 6 MINUTE,"
                    "next_reconcile_at=UTC_TIMESTAMP(3)-INTERVAL 1 MINUTE,"
                    "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                    (tenant, attempt.task_id, attempt.node_id),
                )
            admin.commit()
        except BaseException:
            admin.rollback()
            raise

    def targets(count=1):
        return new_task(count=count)

    def state(attempt):
        return query(
            "SELECT c.state,n.attempt,r.revision FROM orbit_launch_execution_command c JOIN "
            "orbit_task_node n ON n.tenant_id=c.tenant_id AND n.task_id=c.task_id AND "
            "n.id=c.node_id JOIN orbit_execution_command_runtime r ON r.tenant_id=c.tenant_id "
            "AND r.task_id=c.task_id AND r.node_id=c.node_id WHERE c.tenant_id=%s AND "
            "c.task_id=%s AND c.node_id=%s",
            (tenant, attempt.task_id, attempt.node_id),
        )[0]

    async def internal():
        engine = create_async_engine(
            url, echo=False, hide_parameters=True, isolation_level="REPEATABLE READ"
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        count = [0]
        invalidations = [0]
        pool_original = [None]
        pool_connections = set()
        pool_probe_count = [0]

        def pool_checkout(dbapi_connection, record, proxy):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("SELECT CONNECTION_ID(),@@SESSION.innodb_lock_wait_timeout")
                identifier, timeout = cursor.fetchone()
            finally:
                cursor.close()
            assert type(identifier) is int and type(timeout) is int
            if pool_original[0] is None:
                pool_original[0] = timeout
            assert timeout == pool_original[0]
            pool_connections.add(identifier)

        def invalidated(*args):
            invalidations[0] += 1

        async def pool_probe():
            async with engine.connect() as owned:
                row = (
                    await owned.execute(
                        text("SELECT CONNECTION_ID(),@@SESSION.innodb_lock_wait_timeout")
                    )
                ).one()
                assert row[1] == pool_original[0]
                pool_probe_count[0] += 1
                return row[0]

        def counted(*args):
            count[0] += 1

        event.listen(engine.sync_engine, "before_cursor_execute", counted)
        event.listen(engine.sync_engine, "checkout", pool_checkout)
        event.listen(engine.sync_engine, "invalidate", invalidated)
        now = query("SELECT UTC_TIMESTAMP(6)")[0][0].replace(tzinfo=UTC)
        provider = TechnicalScannerProvider(admin, database, tenant, bindings, evidence, now)

        def scanner():
            return ExecutionRecoveryScanner(provider, lambda: sessions)

        async def sweep(value=None, **kwargs):
            return await (value or scanner()).scan_once(
                max_raw_rows=10000, time_budget_seconds=60, **kwargs
            )

        async def settle():
            for _ in range(3):
                await sweep()

        async def wait_for_clock_wait(thread):
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                rows = query(
                    "SELECT t.PROCESSLIST_ID FROM performance_schema.data_lock_waits w "
                    "JOIN performance_schema.data_locks b "
                    "ON b.ENGINE_LOCK_ID=w.BLOCKING_ENGINE_LOCK_ID "
                    "JOIN performance_schema.data_locks r "
                    "ON r.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID "
                    "JOIN performance_schema.threads t ON t.THREAD_ID=w.REQUESTING_THREAD_ID "
                    "WHERE b.THREAD_ID=%s AND r.OBJECT_SCHEMA=%s AND "
                    "r.OBJECT_NAME='orbit_task_clock'",
                    (thread, database),
                )
                if rows:
                    identifier = rows[0][0]
                    assert type(identifier) is int and identifier in pool_connections
                    return identifier
                await asyncio.sleep(0.01)
            raise AssertionError("ACTUAL_SCANNER_CLOCK_LOCK_WAIT_NOT_OBSERVED")

        def actual_wait_count(thread):
            return query(
                "SELECT COUNT(*) FROM performance_schema.data_lock_waits w JOIN "
                "performance_schema.data_locks b ON b.ENGINE_LOCK_ID=w.BLOCKING_ENGINE_LOCK_ID "
                "WHERE b.THREAD_ID=%s",
                (thread,),
            )[0][0]

        def owned_trx_count(identifier):
            return query(
                "SELECT COUNT(*) FROM information_schema.innodb_trx WHERE trx_mysql_thread_id=%s",
                (identifier,),
            )[0][0]

        def owned_server_timeout(identifier):
            rows = query(
                "SELECT v.VARIABLE_VALUE FROM performance_schema.variables_by_thread v JOIN "
                "performance_schema.threads t ON t.THREAD_ID=v.THREAD_ID WHERE "
                "t.PROCESSLIST_ID=%s AND v.VARIABLE_NAME=%s",
                (identifier, "innodb_lock_wait_timeout"),
            )
            return int(rows[0][0]) if rows else None

        async def no_clock_wait(thread, identifier):
            deadline = time.monotonic() + 2
            while actual_wait_count(thread) or owned_trx_count(identifier):
                if time.monotonic() >= deadline:
                    rows = query(
                        "SELECT w.REQUESTING_THREAD_ID,w.BLOCKING_THREAD_ID,t.PROCESSLIST_ID,"
                        "t.PROCESSLIST_COMMAND,t.PROCESSLIST_STATE,t.PROCESSLIST_TIME,"
                        "r.LOCK_STATUS,"
                        "v.VARIABLE_VALUE FROM performance_schema.data_lock_waits w "
                        "JOIN performance_schema.data_locks r "
                        "ON r.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID "
                        "LEFT JOIN performance_schema.threads t "
                        "ON t.THREAD_ID=w.REQUESTING_THREAD_ID "
                        "LEFT JOIN performance_schema.variables_by_thread v "
                        "ON v.THREAD_ID=w.REQUESTING_THREAD_ID "
                        "AND v.VARIABLE_NAME='innodb_lock_wait_timeout' "
                        "WHERE w.BLOCKING_THREAD_ID=%s AND r.OBJECT_SCHEMA=%s "
                        "AND r.OBJECT_NAME='orbit_task_clock'",
                        (thread, database),
                    )
                    diagnostic = safe_lock_wait_diagnostic(rows)
                    diagnostic["remaining_owned_transactions"] = owned_trx_count(identifier)
                    diagnostic["owned_connection_id"] = identifier
                    print(json.dumps(diagnostic), flush=True)
                    raise AssertionError("SCANNER_LOCK_WAIT_DID_NOT_END")
                await asyncio.sleep(0.01)

        try:
            phase("default-and-source")
            factory = Mock(return_value=sessions)
            before = count[0]
            try:
                await ExecutionRecoveryScanner(None, factory).scan_once()
            except OrbitError as error:
                assert error.code == "RECOVERY_SCAN_AUTHORITY_UNAVAILABLE"
            else:
                raise AssertionError("DEFAULT_MUST_DENY")
            factory.assert_not_called()
            assert count[0] == before
            cases.append(SCANNER_CASES[0])

            task, attempts = targets()
            detail = checked(client.get(f"/api/v1/tasks/{task['id']}", headers=headers), 200)
            assert detail["id"] == task["id"] and detail["node_count"] > 0
            assert query(
                "SELECT p.state,p.expected_command_count,p.persisted_command_count,"
                "t.manifest_phase FROM orbit_launch_execution_preparation p JOIN orbit_task t "
                "ON t.tenant_id=p.tenant_id AND t.id=p.task_id WHERE p.tenant_id=%s AND "
                "p.task_id=%s",
                (tenant, task["id"]),
            )[0] == ("ACCEPTED", detail["node_count"], detail["node_count"], "COMPLETE")
            assert (
                query(
                    "SELECT COUNT(*) FROM orbit_launch_execution_command WHERE tenant_id=%s "
                    "AND task_id=%s",
                    (tenant, task["id"]),
                )[0][0]
                == detail["node_count"]
            )
            cases.append(SCANNER_CASES[1])
            await settle()

            phase("ordinary-more-than-400")
            old = []
            old_tasks = 0
            while len(old) < 401:
                _, batch = targets(count=None)
                old_unknown(batch)
                old.extend(batch)
                old_tasks += 1
                if old_tasks % 10 == 0:
                    phase("ordinary-seed-progress")
            task, attempts = targets()
            late = attempts[0]
            old_max = max(
                query(
                    "SELECT lease_expires_at FROM orbit_execution_command_runtime WHERE "
                    "tenant_id=%s AND task_id=%s AND node_id=%s",
                    (tenant, a.task_id, a.node_id),
                )[0][0]
                for a in old
            )
            late_due = query(
                "SELECT lease_expires_at FROM orbit_execution_command_runtime WHERE "
                "tenant_id=%s AND task_id=%s AND node_id=%s",
                (tenant, late.task_id, late.node_id),
            )[0][0]
            assert late_due > old_max
            result = await sweep()
            assert (
                result.raw_rows > 400
                and result.filtered >= len(old)
                and state(late)[0] == "UNKNOWN"
            )
            assert state(late)[1] == 1
            cases.append(SCANNER_CASES[2])

            phase("three-buckets")
            _, attempts = targets()
            accepted = attempts[0]
            change(accepted, state="ACCEPTED", lease_future=True)
            _, attempts = targets()
            expired_accepted = attempts[0]
            change(expired_accepted, state="ACCEPTED")
            before_expired = expected(expired_accepted)
            expired_identity = runtime_identity(expired_accepted)
            _, attempts = targets()
            manual = attempts[0]
            change(manual, state="UNKNOWN", unknown_age=1441)
            before_accepted = expected(accepted)
            before_manual = expected(manual)
            result = await sweep()
            after_accepted, after_manual = state(accepted), state(manual)
            if after_accepted != ("VERIFYING", 1, before_accepted.revision + 1) or after_manual != (
                "UNKNOWN",
                1,
                before_manual.revision + 1,
            ):
                print(
                    json.dumps(
                        three_bucket_diagnostic(
                            before_accepted, before_manual, after_accepted, after_manual, result
                        )
                    ),
                    flush=True,
                )
            assert after_accepted == ("VERIFYING", 1, before_accepted.revision + 1)
            assert after_manual == ("UNKNOWN", 1, before_manual.revision + 1)
            assert (
                query(
                    "SELECT needs_manual_reconciliation FROM orbit_execution_command_runtime "
                    "WHERE tenant_id=%s AND task_id=%s AND node_id=%s",
                    (tenant, manual.task_id, manual.node_id),
                )[0][0]
                == 1
            )
            assert_expired_accepted_recovery(query, tenant, expired_accepted, before_expired)
            assert runtime_identity(expired_accepted) == expired_identity
            provider.revoked = True
            before = count[0]
            try:
                await sweep()
            except OrbitError as error:
                assert error.code == "RECOVERY_SCAN_AUTHORITY_CHANGED"
            else:
                raise AssertionError("CURRENT_SCOPE_MUST_DENY")
            assert count[0] == before
            provider.revoked = False
            cases.append(SCANNER_CASES[3])
            await settle()

            phase("partial-budget")
            _, attempts = targets(count=2)
            limited = scanner()
            for _ in range(64):
                report = await sweep(limited, max_candidates=1)
                assert report.budget_exhausted
                if sum(state(a)[0] == "UNKNOWN" for a in attempts) == 1:
                    break
            assert sum(state(a)[0] == "UNKNOWN" for a in attempts) == 1
            for _ in range(64):
                await sweep(limited, max_candidates=1)
                if all(state(a)[0] == "UNKNOWN" for a in attempts):
                    break
            assert all(state(a)[0] == "UNKNOWN" for a in attempts)
            assert all(state(a)[1] == 1 for a in attempts)
            cases.append(SCANNER_CASES[4])

            phase("two-scanner-cas")
            _, attempts = targets()
            race = attempts[0]
            provider.barrier_target = race.node_id
            provider.arrivals = 0
            provider.release = asyncio.Event()
            running = [asyncio.create_task(sweep(scanner())) for _ in range(2)]
            try:
                reports = await asyncio.wait_for(asyncio.gather(*running), 20)
            finally:
                for pending in running:
                    if not pending.done():
                        pending.cancel()
                await asyncio.gather(*running, return_exceptions=True)
                provider.barrier_target = None
            assert provider.arrivals == 2 and sum(r.stale for r in reports) >= 1
            assert (
                query(
                    "SELECT COUNT(*) FROM orbit_execution_recovery_decision WHERE tenant_id=%s "
                    "AND task_id=%s AND node_id=%s",
                    (tenant, race.task_id, race.node_id),
                )[0][0]
                == 1
            )
            assert state(race) == ("UNKNOWN", 1, 2)
            cases.append(SCANNER_CASES[5])

            phase("rollback-watermark")
            task, attempts = targets()
            failed = attempts[0]
            before = snapshot(task["id"])
            value = scanner()
            trigger = "it_scanner_outbox_" + uuid4().hex[:12]
            execute(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON orbit_task_outbox FOR EACH ROW "
                f"BEGIN IF NEW.task_id='{task['id']}' THEN SIGNAL SQLSTATE '45000' SET "
                f"MESSAGE_TEXT='IT_SCANNER_ROLLBACK'; END IF; END"
            )
            try:
                try:
                    await sweep(value)
                except DBAPIError as error:
                    assert error.orig.args[0] == 1644
                else:
                    raise AssertionError("OUTBOX_FAILURE_MUST_PROPAGATE")
                assert snapshot(task["id"]) == before
                due = query(
                    "SELECT lease_expires_at FROM orbit_execution_command_runtime WHERE "
                    "tenant_id=%s AND task_id=%s AND node_id=%s",
                    (tenant, failed.task_id, failed.node_id),
                )[0][0]
                position = value._positions[(tenant, RecoveryBucket.EXPIRED)]
                assert position.key is None or position.key < (due, failed.task_id, failed.node_id)
            finally:
                execute(f"DROP TRIGGER IF EXISTS {trigger}")
            await sweep(value)
            assert state(failed) == ("UNKNOWN", 1, 2)
            cases.append(SCANNER_CASES[6])

            phase("revocation")
            _, attempts = targets(count=2)
            first = min(attempts, key=lambda a: a.node_id)
            second = next(a for a in attempts if a != first)
            provider.revoke_target = first.node_id
            provider.revoked = False
            try:
                try:
                    await sweep()
                except OrbitError as error:
                    assert error.code == "RECOVERY_SCAN_AUTHORITY_CHANGED"
                else:
                    raise AssertionError("REVOCATION_MUST_STOP")
                assert state(first)[0] == "UNKNOWN" and state(second)[0] == "RUNNING"
            finally:
                provider.revoke_target = None
                provider.revoked = False
            cases.append(SCANNER_CASES[7])
            await settle()

            phase("actual-cancel-timeout")
            task, attempts = targets()
            blocked = attempts[0]
            before = snapshot(task["id"])
            async with sessions() as holder, holder.begin():
                connection = (await holder.execute(text("SELECT CONNECTION_ID()"))).scalar_one()
                thread = query(
                    "SELECT THREAD_ID FROM performance_schema.threads WHERE PROCESSLIST_ID=%s",
                    (connection,),
                )[0][0]
                await holder.execute(
                    text(
                        "SELECT revision FROM orbit_task_clock WHERE tenant_id=:tenant FOR UPDATE"
                    ),
                    {"tenant": tenant},
                )
                value = scanner()
                running = asyncio.create_task(sweep(value))
                prior_invalidations = invalidations[0]
                try:
                    waiting_id = await wait_for_clock_wait(thread)
                    assert owned_server_timeout(waiting_id) == 1
                    running.cancel()
                    try:
                        await running
                    except asyncio.CancelledError:
                        pass
                    else:
                        raise AssertionError("CANCEL_MUST_PROPAGATE")
                    await no_clock_wait(thread, waiting_id)
                    assert not value._running and actual_wait_count(thread) == 0
                    assert (
                        owned_trx_count(waiting_id) == 0 and invalidations[0] > prior_invalidations
                    )
                    assert await pool_probe() != waiting_id
                finally:
                    if not running.done():
                        running.cancel()
                    await asyncio.gather(running, return_exceptions=True)
                value = scanner()
                running = asyncio.create_task(
                    value.scan_once(max_raw_rows=10000, time_budget_seconds=0.5)
                )
                prior_invalidations = invalidations[0]
                try:
                    waiting_id = await wait_for_clock_wait(thread)
                    assert owned_server_timeout(waiting_id) == 1
                    try:
                        await running
                    except TimeoutError:
                        pass
                    else:
                        raise AssertionError("TIMEOUT_MUST_PROPAGATE")
                    await no_clock_wait(thread, waiting_id)
                    assert not value._running and actual_wait_count(thread) == 0
                    assert (
                        owned_trx_count(waiting_id) == 0 and invalidations[0] > prior_invalidations
                    )
                    assert await pool_probe() != waiting_id
                finally:
                    if not running.done():
                        running.cancel()
                    await asyncio.gather(running, return_exceptions=True)
                # 独立server1205：外层5秒不抢先超时，不吞成Timeout/成功。
                value = scanner()
                prior_invalidations = invalidations[0]
                running = asyncio.create_task(
                    value.scan_once(max_raw_rows=10000, time_budget_seconds=5)
                )
                try:
                    waiting_id = await wait_for_clock_wait(thread)
                    assert owned_server_timeout(waiting_id) == 1
                    try:
                        await running
                    except DBAPIError as error:
                        assert error.orig.args[0] == 1205
                    else:
                        raise AssertionError("ACTUAL_1205_MUST_PROPAGATE")
                    await no_clock_wait(thread, waiting_id)
                    assert not value._running and invalidations[0] == prior_invalidations
                    assert owned_server_timeout(waiting_id) == pool_original[0]
                    due = query(
                        "SELECT lease_expires_at FROM orbit_execution_command_runtime WHERE "
                        "tenant_id=%s AND task_id=%s AND node_id=%s",
                        (tenant, blocked.task_id, blocked.node_id),
                    )[0][0]
                    position = value._positions[(tenant, RecoveryBucket.EXPIRED)]
                    assert position.key is None or position.key < (
                        due,
                        blocked.task_id,
                        blocked.node_id,
                    )
                    await pool_probe()
                finally:
                    if not running.done():
                        running.cancel()
                    await asyncio.gather(running, return_exceptions=True)
            assert snapshot(task["id"]) == before and state(blocked)[0] == "RUNNING"
            cases.append(SCANNER_CASES[8])
            await settle()

            phase("index-explain")
            names = (
                "idx_exec_runtime_tenant_expiry",
                "idx_exec_command_tenant_recovery",
                "idx_exec_runtime_tenant_manual",
            )
            index_rows = query(
                "SELECT INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME,INDEX_COMMENT FROM "
                "information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND INDEX_NAME "
                "IN(%s,%s,%s) ORDER BY INDEX_NAME,SEQ_IN_INDEX",
                names,
            )
            expected_columns = {
                names[0]: ["tenant_id", "lease_expires_at", "task_id", "node_id"],
                names[1]: ["tenant_id", "state", "task_id", "node_id"],
                names[2]: [
                    "tenant_id",
                    "needs_manual_reconciliation",
                    "unknown_since",
                    "task_id",
                    "node_id",
                ],
            }
            for name, columns in expected_columns.items():
                found = [row for row in index_rows if row[0] == name]
                assert [row[2] for row in found] == columns and all(row[3] for row in found)
            _, attempts = targets()
            change(attempts[0], state="ACCEPTED")
            _, attempts = targets()
            change(attempts[0], state="UNKNOWN", unknown_age=1441)
            statements = [
                (
                    "orbit_execution_command_runtime",
                    names[0],
                    "active_attempt IS NOT NULL AND lease_expires_at<=UTC_TIMESTAMP(3)",
                    "lease_expires_at,task_id,node_id",
                    "task_id,node_id,lease_expires_at",
                ),
                (
                    "orbit_launch_execution_command",
                    names[1],
                    "state='ACCEPTED'",
                    "task_id,node_id",
                    "task_id,node_id",
                ),
                (
                    "orbit_execution_command_runtime",
                    names[2],
                    "needs_manual_reconciliation=FALSE AND "
                    "unknown_since<=UTC_TIMESTAMP(3)-INTERVAL 24 HOUR",
                    "unknown_since,task_id,node_id",
                    "task_id,node_id,unknown_since",
                ),
            ]
            plans = []
            for table, index, predicate, ordering, columns in statements:
                for forced in (False, True):
                    with admin.cursor() as cursor:
                        cursor.execute(
                            f"EXPLAIN SELECT {columns} FROM {table} "
                            + (f"FORCE INDEX ({index}) " if forced else "")
                            + f"WHERE tenant_id=%s AND {predicate} ORDER BY {ordering} LIMIT 200",
                            (tenant,),
                        )
                        columns_meta = [item[0] for item in cursor.description]
                        plan = dict(zip(columns_meta, cursor.fetchone(), strict=True))
                    assert plan["key"] is not None and plan["type"] != "ALL"
                    if forced:
                        assert plan["key"] == index
                    plans.append(
                        {
                            "index": index,
                            "forced": forced,
                            "chosen_key": plan["key"],
                            "access": plan["type"],
                            "rows": plan["rows"],
                        }
                    )
            cases.append(SCANNER_CASES[9])
            if include_service:
                phase("service-real-once")
                await settle()

                def service_instance():
                    created = []

                    def make(fixed):
                        value = ExecutionRecoveryScanner(fixed, lambda: sessions)
                        created.append(value)
                        return value

                    return ExecutionRecoveryService(provider, make), created

                task, attempts = targets()
                target = attempts[0]
                original = expected(target)
                value, created = service_instance()
                outcome = await value.run(
                    mode="once",
                    stop=asyncio.Event(),
                    max_candidates=1,
                    max_raw_rows=10000,
                    time_budget_seconds=10,
                )
                assert_service_cleanup(value, outcome, created)
                assert outcome["cycles"] == 1 and outcome["recovered"] == 1
                assert state(target) == ("UNKNOWN", original.attempt_no, original.revision + 1)
                assert (
                    query(
                        "SELECT COUNT(*) FROM orbit_execution_recovery_decision WHERE tenant_id=%s "
                        "AND task_id=%s AND node_id=%s AND publication_phase='SEALED'",
                        (tenant, target.task_id, target.node_id),
                    )[0][0]
                    == 1
                )
                await pool_probe()
                cases.append(SERVICE_CASES[0])
                await settle()

                phase("service-real-inflight-stop")
                task, attempts = targets(count=2)
                first, second = sorted(attempts, key=lambda row: row.node_id)
                original_first, original_second = expected(first), expected(second)
                value, created = service_instance()
                stop = asyncio.Event()
                running = None
                async with sessions() as holder, holder.begin():
                    connection = (await holder.execute(text("SELECT CONNECTION_ID()"))).scalar_one()
                    thread = query(
                        "SELECT THREAD_ID FROM performance_schema.threads WHERE PROCESSLIST_ID=%s",
                        (connection,),
                    )[0][0]
                    await holder.execute(
                        text(
                            "SELECT revision FROM orbit_task_clock "
                            "WHERE tenant_id=:tenant FOR UPDATE"
                        ),
                        {"tenant": tenant},
                    )
                    running = asyncio.create_task(
                        value.run(
                            mode="serve",
                            stop=stop,
                            interval_seconds=1,
                            max_candidates=1,
                            max_raw_rows=10000,
                            time_budget_seconds=10,
                        )
                    )
                    try:
                        waiting_id = await wait_for_clock_wait(thread)
                        assert owned_server_timeout(waiting_id) == 1
                        stop.set()
                        # 等服务自身确实先停领；不是只设stop便假定当前Task已退出。
                        deadline = time.monotonic() + 0.5
                        while not created[0]._stopped:
                            assert time.monotonic() < deadline
                            await asyncio.sleep(0)
                        await holder.rollback()  # 只释放本轮精确holder，让已开始恢复完整提交。
                        outcome = await running
                        assert_service_cleanup(value, outcome, created)
                        assert outcome["result"] == "STOPPED"
                        await no_clock_wait(thread, waiting_id)
                        assert owned_server_timeout(waiting_id) == pool_original[0]
                    finally:
                        stop.set()
                        if running is not None:
                            if not running.done():
                                running.cancel()
                            await asyncio.gather(running, return_exceptions=True)
                assert state(first) == (
                    "UNKNOWN",
                    original_first.attempt_no,
                    original_first.revision + 1,
                )
                assert state(second) == (
                    "RUNNING",
                    original_second.attempt_no,
                    original_second.revision,
                )
                await pool_probe()
                cases.append(SERVICE_CASES[1])
                await settle()

                phase("service-original-grant-drift")
                task, attempts = targets(count=2)
                first, second = sorted(attempts, key=lambda row: row.node_id)
                original_first, original_second = expected(first), expected(second)
                value, created = service_instance()
                original_grant = provider.grant
                reports = []

                def revoke_after_commit(report):
                    reports.append(report)
                    provider.revoked = True

                try:
                    try:
                        await value.run(
                            mode="serve",
                            stop=asyncio.Event(),
                            interval_seconds=1,
                            max_candidates=1,
                            max_raw_rows=10000,
                            time_budget_seconds=10,
                            report=revoke_after_commit,
                        )
                    except OrbitError as error:
                        assert error.code == "RECOVERY_SERVICE_AUTHORITY_CHANGED"
                    else:
                        raise AssertionError("SERVICE_GRANT_DRIFT_MUST_STOP")
                    assert value.state == "FAILED" and value.retained_tasks == ()
                    assert len(reports) == len(created) == 1 and reports[0]["recovered"] == 1
                    assert value.active_task.done() and value.active_task.exception() is None
                    assert not created[0]._running
                    assert provider.grant == original_grant
                    assert state(first) == (
                        "UNKNOWN",
                        original_first.attempt_no,
                        original_first.revision + 1,
                    )
                    assert state(second) == (
                        "RUNNING",
                        original_second.attempt_no,
                        original_second.revision,
                    )
                finally:
                    provider.revoked = False
                await pool_probe()
                cases.append(SERVICE_CASES[2])
                await settle()

                phase("service-actual-1205-no-retry")
                task, attempts = targets()
                target = attempts[0]
                before = snapshot(task["id"])
                value, created = service_instance()
                reports = []
                async with sessions() as holder, holder.begin():
                    connection = (await holder.execute(text("SELECT CONNECTION_ID()"))).scalar_one()
                    thread = query(
                        "SELECT THREAD_ID FROM performance_schema.threads WHERE PROCESSLIST_ID=%s",
                        (connection,),
                    )[0][0]
                    await holder.execute(
                        text(
                            "SELECT revision FROM orbit_task_clock "
                            "WHERE tenant_id=:tenant FOR UPDATE"
                        ),
                        {"tenant": tenant},
                    )
                    prior_invalidations = invalidations[0]
                    running = asyncio.create_task(
                        value.run(
                            mode="serve",
                            stop=asyncio.Event(),
                            interval_seconds=1,
                            max_candidates=1,
                            max_raw_rows=10000,
                            time_budget_seconds=10,
                            report=reports.append,
                        )
                    )
                    try:
                        waiting_id = await wait_for_clock_wait(thread)
                        assert owned_server_timeout(waiting_id) == 1
                        try:
                            await running
                        except DBAPIError as error:
                            assert error.orig.args[0] == 1205
                        else:
                            raise AssertionError("SERVICE_1205_MUST_TERMINATE")
                        assert value.state == "FAILED" and len(created) == 1 and reports == []
                        assert value.active_task.done() and isinstance(
                            value.active_task.exception(), DBAPIError
                        )
                        assert not created[0]._running and value.retained_tasks == ()
                        await no_clock_wait(thread, waiting_id)
                        assert invalidations[0] == prior_invalidations
                        assert owned_server_timeout(waiting_id) == pool_original[0]
                        due = query(
                            "SELECT lease_expires_at FROM orbit_execution_command_runtime WHERE "
                            "tenant_id=%s AND task_id=%s AND node_id=%s",
                            (tenant, target.task_id, target.node_id),
                        )[0][0]
                        position = created[0]._positions[(tenant, RecoveryBucket.EXPIRED)]
                        assert position.key is None or position.key < (
                            due,
                            target.task_id,
                            target.node_id,
                        )
                    finally:
                        if not running.done():
                            running.cancel()
                        await asyncio.gather(running, return_exceptions=True)
                assert snapshot(task["id"]) == before and state(target)[0] == "RUNNING"
                await pool_probe()
                cases.append(SERVICE_CASES[3])
            return {
                "scanner_groups": len(SCANNER_CASES),
                "ordinary_old_unknown_rows": len(old),
                "ordinary_source_tasks": old_tasks,
                "index_plans": plans,
                "platform_sends": 0,
                "claims": 0,
                "production_issuer": False,
                "pool_restore_probes": pool_probe_count[0],
                "original_session_lock_timeout": pool_original[0],
                "cancelled_connection_invalidations": invalidations[0],
                "service_groups": len(SERVICE_CASES) if include_service else 0,
            }
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counted)
            event.remove(engine.sync_engine, "checkout", pool_checkout)
            event.remove(engine.sync_engine, "invalidate", invalidated)
            await engine.dispose()

    return asyncio.run(internal())
