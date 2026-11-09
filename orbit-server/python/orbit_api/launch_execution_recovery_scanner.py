"""显式注入的原代际恢复扫描器；默认无authority，零claim/send/平台请求。"""

import asyncio
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from orbit_api.errors import OrbitError
from orbit_api.launch_execution_lease_contract import (
    MAX_REVISION,
    AttemptBinding,
    _integer,
    _utc,
    _uuid,
)
from orbit_api.launch_execution_lease_store import (
    ExecutionLeaseAuthority,
    LeaseOperation,
    RuntimeExpectation,
    _database_time,
    _stored_binding,
    unverified,
)
from orbit_api.launch_execution_recovery_store import ExecutionRecoveryStore
from orbit_api.task_contract import NODE_STATES

PAGE_SIZE = 200
MAX_TENANTS = 64  # 内部维护配置的有界批次，不是业务租户数量上限。
RECOVERY_LOCK_WAIT_SECONDS = 1
CONNECTION_CLEANUP_SECONDS = 2
BLOCKED_CODES = frozenset(
    {
        "EXECUTION_LEASE_SOURCE_UNVERIFIED",
        "EXECUTION_LEASE_AUTHORITY_UNAVAILABLE",
        "EXECUTION_FACT_READ_TIMEOUT",
    }
)


class RecoveryBucket(StrEnum):
    EXPIRED = "EXPIRED"
    ACCEPTED = "ACCEPTED"
    MANUAL_DUE = "MANUAL_DUE"


@dataclass(frozen=True, repr=False)
class MaintenanceScanGrant:
    """仅受控服务器provider签发；类型本身不是生产issuer证明。"""

    grant_id: str
    principal_id: str
    actor_id: int
    tenants: tuple[str, ...]
    action: LeaseOperation
    revision: int
    expires_at: datetime

    def __post_init__(self):
        _uuid(self.grant_id)
        _uuid(self.principal_id)
        _integer(self.actor_id, MAX_REVISION)
        _integer(self.revision, MAX_REVISION)
        _utc(self.expires_at)
        if self.action is not LeaseOperation.RECOVER_EXPIRED:
            raise ValueError("需要原恢复动作授权")
        if not isinstance(self.tenants, tuple) or not 1 <= len(self.tenants) <= MAX_TENANTS:
            raise ValueError("维护租户范围必须有界")
        for tenant in self.tenants:
            _uuid(tenant)
        if tuple(sorted(set(self.tenants))) != self.tenants:
            raise ValueError("维护租户必须唯一并有序")


class RecoveryScanAuthorityProvider(ABC):
    """没有生产默认实现，不接受HTTP/SQL任意字符串构造维护权限。"""

    @abstractmethod
    async def capture(self) -> MaintenanceScanGrant:
        """事务外捕获真实维护主体、issuer及当前授权范围；无来源应拒绝。"""

    @abstractmethod
    async def current(self, grant: MaintenanceScanGrant) -> MaintenanceScanGrant:
        """事务外复验相同主体/范围/action/版本/期限，不能返回布尔模拟成功。"""

    @abstractmethod
    async def authority(self, grant: MaintenanceScanGrant) -> ExecutionLeaseAuthority:
        """返回绑定该主体范围的真实事实authority，authorize仍须事务内当前复验。"""


@dataclass(frozen=True, repr=False)
class RecoveryCandidate:
    binding: AttemptBinding
    expected: RuntimeExpectation


@dataclass(frozen=True, repr=False)
class RawRecoveryHint:
    key: tuple
    candidate: RecoveryCandidate | None
    blocked: bool = True


@dataclass
class _Position:
    cutoff: datetime | None = None
    key: tuple | None = None


@dataclass(frozen=True)
class RecoveryScanReport:
    pages: int
    raw_rows: int
    attempted: int
    recovered: int
    noop: int
    stale: int
    blocked: int
    filtered: int
    budget_exhausted: bool
    stopped: bool


def _authority_error(code="RECOVERY_SCAN_AUTHORITY_UNAVAILABLE"):
    raise OrbitError(503, code, "恢复扫描维护主体及可信来源尚未就绪")


def _validate_grant(grant, now):
    if not isinstance(grant, MaintenanceScanGrant):
        _authority_error()
    _utc(now)
    if now >= grant.expires_at:
        _authority_error("RECOVERY_SCAN_AUTHORITY_EXPIRED")


async def _connection_settings(connection):
    row = (
        (
            await connection.execute(
                text(
                    "SELECT CONNECTION_ID() AS connection_id,"
                    "@@SESSION.innodb_lock_wait_timeout AS lock_wait_timeout"
                )
            )
        )
        .mappings()
        .one()
    )
    identifier, original = row["connection_id"], row["lock_wait_timeout"]
    if (
        type(identifier) is not int
        or identifier < 1
        or type(original) is not int
        or not 1 <= original <= 1073741824
    ):
        _authority_error("RECOVERY_SCAN_CONNECTION_UNVERIFIED")
    return identifier, original


async def _restore_owned_connection(connection, identifier, original):
    # invalidated连接的下一次execute可能自动重连；不能用新物理会话假装恢复旧设置。
    if connection.invalidated:
        return
    if connection.closed or identifier is None or original is None:
        _authority_error("RECOVERY_SCAN_CONNECTION_UNVERIFIED")
    if connection.in_transaction():
        await connection.rollback()
    current, _ = await _connection_settings(connection)
    if current != identifier:
        _authority_error("RECOVERY_SCAN_CONNECTION_CHANGED")
    await connection.execute(
        text("SET SESSION innodb_lock_wait_timeout=:original"), {"original": original}
    )
    restored_id, restored = await _connection_settings(connection)
    if restored_id != identifier or restored != original:
        _authority_error("RECOVERY_SCAN_CONNECTION_RESTORE_FAILED")
    await connection.commit()  # 关闭复位查询的autobegin后才可返回连接池。


@asynccontextmanager
async def _recovery_transaction(sessions):
    """逐条独占同物理连接；只限定本scanner，不改变旧Store/其他API或全局设置。"""
    settings = getattr(sessions, "kw", None)
    engine = settings.get("bind") if isinstance(settings, dict) else None
    if not isinstance(engine, AsyncEngine):
        _authority_error("RECOVERY_SCAN_DATABASE_UNVERIFIED")
    connection = await engine.connect()
    identifier = original = None
    try:
        identifier, original = await _connection_settings(connection)
        await connection.execute(
            text("SET SESSION innodb_lock_wait_timeout=:seconds"),
            {"seconds": RECOVERY_LOCK_WAIT_SECONDS},
        )
        configured_id, configured_timeout = await _connection_settings(connection)
        if configured_id != identifier or configured_timeout != RECOVERY_LOCK_WAIT_SECONDS:
            _authority_error("RECOVERY_SCAN_CONNECTION_UNVERIFIED")
        await connection.commit()  # 设置/读取的autobegin必须先闭合，业务txn随后开始。
        if connection.invalidated or connection.closed:
            _authority_error("RECOVERY_SCAN_CONNECTION_UNVERIFIED")
        async with sessions(bind=connection) as session, session.begin():
            yield session
    finally:
        # 不创建shield后台Task；取消后的清理仍完整await且有独立上界。
        try:
            async with asyncio.timeout(CONNECTION_CLEANUP_SECONDS):
                await _restore_owned_connection(connection, identifier, original)
                await connection.close()
        except BaseException:
            async with asyncio.timeout(CONNECTION_CLEANUP_SECONDS):
                await connection.invalidate()
                await connection.close()
            raise


async def _candidate_page(session, tenant, bucket, position, limit):
    """有界原始页后集合绑定；此事务只生成提示，不授予恢复权限。"""
    now = _database_time((await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one())
    cutoff = position.cutoff or now
    if cutoff > now:
        # SQL UTC回退时不继续使用未来扫描水位，保留进度并由运维处理。
        unverified()
    params = {"tenant": tenant, "limit": limit, "cutoff": cutoff.replace(tzinfo=None)}
    if bucket is RecoveryBucket.EXPIRED:
        sql = (
            "SELECT task_id,node_id,lease_expires_at AS due FROM orbit_execution_command_runtime "
            "WHERE tenant_id=:tenant AND active_attempt IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND lease_expires_at<=:cutoff "
        )
        if position.key:
            sql += "AND (lease_expires_at,task_id,node_id)>(:due,:task,:node) "
        sql += "ORDER BY lease_expires_at,task_id,node_id LIMIT :limit"
    elif bucket is RecoveryBucket.ACCEPTED:
        sql = (
            "SELECT task_id,node_id FROM orbit_launch_execution_command "
            "WHERE tenant_id=:tenant AND state='ACCEPTED' "
        )
        if position.key:
            sql += "AND (task_id,node_id)>(:task,:node) "
        sql += "ORDER BY task_id,node_id LIMIT :limit"
    else:
        params["manual_cutoff"] = (cutoff - timedelta(hours=24)).replace(tzinfo=None)
        sql = (
            "SELECT task_id,node_id,unknown_since AS due FROM orbit_execution_command_runtime "
            "WHERE tenant_id=:tenant AND needs_manual_reconciliation=FALSE "
            "AND unknown_since IS NOT NULL AND unknown_since<=:manual_cutoff "
        )
        if position.key:
            sql += "AND (unknown_since,task_id,node_id)>(:due,:task,:node) "
        sql += "ORDER BY unknown_since,task_id,node_id LIMIT :limit"
    if position.key:
        if bucket is RecoveryBucket.ACCEPTED:
            params["task"], params["node"] = position.key
        else:
            params["due"], params["task"], params["node"] = position.key
    rows = (await session.execute(text(sql), params)).mappings().all()
    if len(rows) > limit:
        unverified()
    if not rows:
        return now, cutoff, []
    pairs = []
    for i, row in enumerate(rows):
        _uuid(row["task_id"])
        _uuid(row["node_id"])
        pairs.append(f"(:task_{i},:node_{i})")
        params[f"task_{i}"] = row["task_id"]
        params[f"node_{i}"] = row["node_id"]
    joined = (
        (
            await session.execute(
                text(
                    "SELECT a.*,r.revision AS runtime_revision,c.state AS command_state,"
                    "n.state AS node_state "
                    "FROM orbit_execution_attempt a JOIN orbit_execution_command_runtime r "
                    "ON r.tenant_id=a.tenant_id AND r.task_id=a.task_id AND r.node_id=a.node_id "
                    "AND r.active_attempt=a.attempt_no AND r.fencing_token=a.fencing_token "
                    "AND r.claim_id=a.claim_id AND r.worker_id=a.worker_id "
                    "JOIN orbit_launch_execution_command c ON c.tenant_id=a.tenant_id "
                    "AND c.task_id=a.task_id AND c.node_id=a.node_id "
                    "JOIN orbit_task_node n ON n.tenant_id=a.tenant_id AND n.task_id=a.task_id "
                    "AND n.id=a.node_id "
                    "WHERE a.tenant_id=:tenant AND (a.task_id,a.node_id) IN("
                    + ",".join(pairs)
                    + ")"
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    indexed = {}
    requested = {(row["task_id"], row["node_id"]) for row in rows}
    if len(joined) > len(rows):
        unverified()
    for row in joined:
        key = (row["task_id"], row["node_id"])
        if key in indexed or key not in requested:
            unverified()
        indexed[key] = row
    hints = []
    last_key = position.key
    for row in rows:
        key = (row["task_id"], row["node_id"])
        if bucket is not RecoveryBucket.ACCEPTED:
            key = (_database_time(row["due"]).replace(tzinfo=None),) + key
        if last_key is not None and key <= last_key:
            unverified()
        last_key = key
        full = indexed.get((row["task_id"], row["node_id"]))
        candidate = None
        blocked = True
        allowed = {
            RecoveryBucket.EXPIRED: {"RUNNING", "VERIFYING"},
            RecoveryBucket.ACCEPTED: {"ACCEPTED"},
            RecoveryBucket.MANUAL_DUE: {"UNKNOWN"},
        }[bucket]
        if (
            full is not None
            and full["command_state"] == full["node_state"]
            and full["command_state"] in NODE_STATES
            and full["command_state"] not in allowed
        ):
            blocked = False
        if (
            full is not None
            and full["command_state"] == full["node_state"]
            and full["command_state"] in allowed
        ):
            try:
                binding = _stored_binding(full)
                if binding.tenant_id != tenant:
                    unverified()
                candidate = RecoveryCandidate(
                    binding,
                    RuntimeExpectation(
                        full["runtime_revision"],
                        binding.attempt_no,
                        binding.fencing_token,
                        binding.claim_id,
                        binding.worker_id,
                    ),
                )
            except OrbitError as error:
                if error.code != "EXECUTION_LEASE_SOURCE_UNVERIFIED":
                    raise
            except (ValueError, KeyError, TypeError):
                candidate = None
        hints.append(RawRecoveryHint(key, candidate, blocked))
    return now, cutoff, hints


class ExecutionRecoveryScanner:
    """单进程单次在途；进度仅优化扫描，原恢复CAS才是持久去重边界。"""

    def __init__(
        self, authority_provider=None, sessions_factory=None, *, clock=None, monotonic=None
    ):
        self.provider = authority_provider
        self.sessions_factory = sessions_factory
        self.clock = clock or (lambda: datetime.now(UTC))
        self.monotonic = monotonic or time.monotonic
        self._running = False
        self._stopped = False
        self._grant = None
        self._positions = {}
        self._rotation = 0

    def request_stop(self):
        self._stopped = True

    async def _current(self, grant):
        _validate_grant(grant, self.clock())
        current = await self.provider.current(grant)
        _validate_grant(current, self.clock())
        if current != grant:
            _authority_error("RECOVERY_SCAN_AUTHORITY_CHANGED")

    async def scan_once(self, *, max_candidates=100, max_raw_rows=1000, time_budget_seconds=10):
        if not isinstance(self.provider, RecoveryScanAuthorityProvider):
            _authority_error()
        if self._running:
            raise OrbitError(409, "RECOVERY_SCAN_ALREADY_RUNNING", "恢复扫描已有在途批次")
        _integer(max_candidates, 200)
        _integer(max_raw_rows, 10000)
        if type(time_budget_seconds) not in (int, float) or not 0 < time_budget_seconds <= 60:
            raise ValueError("恢复扫描耗时预算必须在零至六十秒之间")
        self._running = True
        try:
            async with asyncio.timeout(time_budget_seconds):
                return await self._scan(max_candidates, max_raw_rows, time_budget_seconds)
        finally:
            self._running = False

    async def _scan(self, max_candidates, max_raw_rows, seconds):
        started = self.monotonic()
        grant = await self.provider.capture()
        _validate_grant(grant, self.clock())
        await self._current(grant)
        if self._grant != grant:
            self._positions = {}
            self._rotation = 0
            self._grant = grant
        if self.sessions_factory is None:
            _authority_error()
        if self._stopped:
            return RecoveryScanReport(0, 0, 0, 0, 0, 0, 0, 0, False, True)
        sessions = self.sessions_factory()
        ring = [(tenant, bucket) for bucket in RecoveryBucket for tenant in grant.tenants]
        metrics = dict(
            pages=0, raw_rows=0, attempted=0, recovered=0, noop=0, stale=0, blocked=0, filtered=0
        )
        complete = set()
        exhausted = False
        while len(complete) < len(ring):
            if self._stopped:
                break
            if (
                metrics["attempted"] >= max_candidates
                or metrics["raw_rows"] >= max_raw_rows
                or self.monotonic() - started >= seconds
            ):
                exhausted = True
                break
            entry = ring[self._rotation % len(ring)]
            self._rotation = (self._rotation + 1) % len(ring)
            if entry in complete:
                continue
            tenant, bucket = entry
            position = self._positions.setdefault(entry, _Position())
            await self._current(grant)
            limit = min(PAGE_SIZE, max_raw_rows - metrics["raw_rows"])
            async with sessions() as session, session.begin():
                now, cutoff, hints = await _candidate_page(session, tenant, bucket, position, limit)
                _validate_grant(grant, now)
            metrics["pages"] += 1
            metrics["raw_rows"] += len(hints)
            position.cutoff = cutoff
            consumed = 0
            for hint in hints:
                if self._stopped:
                    break
                if metrics["attempted"] >= max_candidates or self.monotonic() - started >= seconds:
                    exhausted = True
                    break
                await self._current(grant)
                candidate = hint.candidate
                if candidate is None:
                    metrics["blocked" if hint.blocked else "filtered"] += 1
                else:
                    if candidate.binding.tenant_id != tenant or tenant not in grant.tenants:
                        unverified()
                    authority = await self.provider.authority(grant)
                    _validate_grant(grant, self.clock())
                    if not isinstance(authority, ExecutionLeaseAuthority):
                        _authority_error()
                    metrics["attempted"] += 1
                    try:
                        async with _recovery_transaction(sessions) as session:
                            result = await ExecutionRecoveryStore(authority).recover_expired(
                                session,
                                grant.actor_id,
                                candidate.binding,
                                candidate.expected,
                                str(uuid4()),
                            )
                        metrics["recovered" if result.changed else "noop"] += 1
                    except OrbitError as error:
                        if error.status == 409 and error.code == "EXECUTION_LEASE_STALE":
                            metrics["stale"] += 1
                        elif error.status == 503 and error.code in BLOCKED_CODES:
                            metrics["blocked"] += 1
                        else:
                            raise
                # 只有已分类/已提交/明确stale才推进，未处理余页下次重读而非丢弃。
                position.key = hint.key
                consumed += 1
            if consumed == len(hints) and len(hints) < limit:
                position.key = None
                position.cutoff = None
                complete.add(entry)
            if exhausted:
                break
        return RecoveryScanReport(**metrics, budget_exhausted=exhausted, stopped=self._stopped)
