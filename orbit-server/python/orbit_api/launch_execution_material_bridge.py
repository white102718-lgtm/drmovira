"""原execute的C素材证据/引用内部桥；不提供平台Authority或公开HTTP入口。"""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from orbit_api.authorization import BusinessContext, require_business_access
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_contract import DESCRIPTOR_FIELDS, PreparedExecution
from orbit_api.launch_plan_source import PlanSource
from orbit_api.material_references import (
    register_active_material_references,
    require_allocation_assets,
)

TICKET_KEY = "orbit_execution_material_publication_tickets"
FIELDS = (
    "id",
    "revision",
    "sha256",
    "mime",
    "size",
    "width",
    "height",
    "duration",
    "owner_user_id",
    "owner_team_id",
    "state",
    "physical_cleanup_state",
    "antivirus_status",
    "execution_eligible",
)


def unavailable():
    raise OrbitError(503, "EXECUTION_MATERIAL_SOURCE_UNAVAILABLE", "真实素材证据不完整")


def stale():
    raise OrbitError(409, "STALE_PREVIEW", "冻结素材来源或当前双方授权已变化")


def transaction(session):
    if not session.in_transaction():
        raise ValueError("执行素材桥必须处于调用者外层短事务")
    return session.sync_session.get_transaction()


@dataclass(frozen=True, repr=False)
class ExecutionMaterialCapture:
    current: BusinessContext
    source_hash: str
    source_revision: int
    owner_user_id: str
    owner_team_id: str
    pool: tuple[str, ...]
    metadata_json: bytes


@dataclass(frozen=True, repr=False)
class ExecutionMaterialTicket:
    owner: object
    transaction: object
    capture: ExecutionMaterialCapture
    current: BusinessContext
    manifest_hash: str
    used: tuple[str, ...]


class ExecutionMaterialBridge:
    """由Provider.capture/revalidate/publish钩子调用；不授予生产写权限。

    revalidate须在来源锁之后、launch clock/head之前调用lock_for_accept。
    本桥不伪造跨事务锁证明；publish只消费在本事务已登记的完整票据。
    """

    def __init__(self):
        self._owner = object()

    async def _read(self, session, current, source):
        transaction(session)
        if not isinstance(current, BusinessContext) or not isinstance(source, PlanSource):
            raise ValueError("须使用当前服务端上下文与真实配置源")
        if hashlib.sha256(source.canonical_payload).hexdigest() != source.payload_hash:
            unavailable()
        actual = await require_business_access(
            session, current.actor_id, "launch", "launch.execute"
        )
        if actual != current or source.tenant_id != current.tenant_id:
            stale()
        plan = source.payload()
        ownership = plan["ownership"]
        identifiers = tuple(sorted(plan["asset_ids"]))
        if len(identifiers) > 500 or len(set(identifiers)) != len(identifiers):
            unavailable()
        metadata = {}
        # 空池不调用C上下文，不额外强制assets.read。非空由C核caller与owner双方交集。
        for offset in range(0, len(identifiers), 200):
            batch = identifiers[offset : offset + 200]
            rows = await require_allocation_assets(
                session, current, ownership["owner_user_id"], ownership["owner_team_id"], batch
            )
            if set(rows) != set(batch):
                unavailable()
            for identifier in batch:
                row = rows[identifier]
                if (
                    row.get("id") != identifier
                    or row.get("state") != "READY"
                    or row.get("physical_cleanup_state") != "LIVE"
                    or row.get("antivirus_status") != "CLEAN"
                    or row.get("execution_eligible") is not True
                    or any(field not in row for field in FIELDS)
                ):
                    raise OrbitError(409, "ANTIVIRUS_UNVERIFIED", "素材缺当前030/034完整扫描证明")
                metadata[identifier] = {field: row[field] for field in FIELDS}
                if row["duration"] is not None:
                    metadata[identifier]["duration"] = format(
                        Decimal(row["duration"]).normalize(), "f"
                    )
        return ExecutionMaterialCapture(
            current,
            source.payload_hash,
            source.source_revision,
            ownership["owner_user_id"],
            ownership["owner_team_id"],
            identifiers,
            canonical(metadata).encode(),
        )

    async def capture_materials(self, session, current, source):
        """capture自有短事务内完整观察；关闭此事务后再做外部网络与完整编译。"""
        return await self._read(session, current, source)

    async def lock_for_accept(self, session, current, source, capture, prepared):
        """final来源阶段取同事务全部C锁；不能在launch head之后第一次调用。"""
        identity = transaction(session)
        if not isinstance(capture, ExecutionMaterialCapture) or not isinstance(
            prepared, PreparedExecution
        ):
            unavailable()
        if source != prepared.source or capture.current != current:
            stale()
        observed = await self._read(session, current, source)
        if observed != capture:
            stale()
        metadata = json.loads(capture.metadata_json)
        used_metadata = json.loads(prepared.materials_json)
        used = tuple(sorted(used_metadata))
        actual_used = {node.asset_id for node in prepared.dag.nodes if node.asset_id is not None}
        if set(used) != actual_used or not set(used) <= set(capture.pool):
            stale()
        # pure的执行描述不含安全资格字段；逐个原字段对应实际C值，未知不得补零。
        for identifier in used:
            row = used_metadata[identifier]
            if (
                not isinstance(row, dict)
                or set(row) != set(DESCRIPTOR_FIELDS)
                or any(metadata[identifier].get(field) != value for field, value in row.items())
            ):
                stale()
        ticket = ExecutionMaterialTicket(
            self._owner, identity, capture, current, prepared.manifest_hash, used
        )
        # 每个完整manifest只保存本事务一张票；旧事务遗留不成为新授权。
        tickets = session.info.get(TICKET_KEY, [])
        session.info[TICKET_KEY] = [
            value
            for value in tickets
            if value.transaction is identity and value.manifest_hash != ticket.manifest_hash
        ] + [ticket]
        return ticket

    async def publish(self, session, current, source, prepared, ticket, task_id, request_id):
        """accept外层事务只重入既有C锁，实际EXECUTION引用/审计/outbox同笔提交。"""
        identity = transaction(session)
        tickets = session.info.get(TICKET_KEY, [])
        if (
            not isinstance(prepared, PreparedExecution)
            or not isinstance(ticket, ExecutionMaterialTicket)
            or ticket.owner is not self._owner
            or not any(value is ticket for value in tickets)
            or ticket.transaction is not identity
            or ticket.current != current
            or source != prepared.source
            or ticket.capture.current != current
            or ticket.capture.source_hash != source.payload_hash
            or ticket.capture.source_revision != source.source_revision
            or ticket.manifest_hash != prepared.manifest_hash
            or ticket.used != tuple(sorted(json.loads(prepared.materials_json)))
            or ticket.capture.owner_user_id != source.payload()["ownership"]["owner_user_id"]
            or ticket.capture.owner_team_id != source.payload()["ownership"]["owner_team_id"]
        ):
            raise ValueError("执行引用必须消费本Bridge同事务精确来源票据")
        metadata = json.loads(ticket.capture.metadata_json)
        result = {}
        for offset in range(0, len(ticket.used), 200):
            batch = ticket.used[offset : offset + 200]
            result.update(
                await register_active_material_references(
                    session,
                    current,
                    ticket.capture.owner_user_id,
                    ticket.capture.owner_team_id,
                    {identifier: metadata[identifier] for identifier in batch},
                    "EXECUTION",
                    task_id,
                    request_id,
                )
            )
        if set(result) != set(ticket.used):
            unavailable()
        session.info[TICKET_KEY] = [value for value in tickets if value is not ticket]
        return result
