"""真实素材读/引用桥；平台权威接口未注入时关闭，不注册路由或伪造能力。"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from orbit_api.authorization import BusinessContext, require_business_access
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest
from orbit_api.launch_allocation import AllocationSolution, inputs, verify_evidence
from orbit_api.launch_allocation_runtime import AllocationProvider, CapturedAllocation
from orbit_api.launch_contract import parse_plan, parse_plan_action
from orbit_api.launch_expansion import ad_slots
from orbit_api.material_references import (
    deactivate_locked_material_references,
    lock_active_material_reference_set,
    register_active_material_references,
    require_allocation_assets,
)

TICKET_KEY = "orbit_allocation_reference_provider_tickets"


@dataclass(frozen=True, repr=False)
class LockedAllocationAuthority:
    """仅受控适配器返回；必须持同事务来源锁，摘要不能来自浏览器verified字段。"""

    transaction: object
    context: BusinessContext
    plan_hash: str
    authority_fingerprint: str
    capability_version: str
    source_hash: str


class AllocationReferenceAuthority(ABC):
    """缺真实账户/身份/平台能力来源时保持未实现，不以完整兼容fixture代替。"""

    @abstractmethod
    async def lock_sources(self, session, current, plan, request):
        """来源clock及账户/身份等排序锁先于material；禁止网络I/O或先锁launch。

        必须核真实平台能力/策略、caller与owner交集、相关账户/身份/素材授权范围
        版本。返回摘要涵盖这些来源；不存在可信生产包时明确503而非猜兼容。
        """

    @abstractmethod
    def compatibility(self, locked, plan, request, materials):
        """同步、无SQL/网络：用已锁真实能力与媒体尺寸/格式构完整兼容证据。"""


@dataclass(frozen=True, repr=False)
class MaterialPublicationTicket:
    owner: object
    transaction: object
    context: BusinessContext
    plan_hash: str
    previous_id: str | None
    old_references: object
    metadata_json: bytes


def unavailable():
    raise OrbitError(503, "ALLOCATION_AUTHORITY_UNAVAILABLE", "真实分配权威来源尚未接入")


def transaction_identity(session):
    if not session.in_transaction():
        raise ValueError("素材分配桥必须复用调用者同一外层事务")
    return session.sync_session.get_transaction()


def material_metadata(records, expected_ids):
    if not isinstance(records, dict) or set(records) != set(expected_ids):
        raise OrbitError(503, "ALLOCATION_MATERIAL_PROOF_UNAVAILABLE", "素材读取必须完整无缺项")
    result = {}
    for identifier in sorted(expected_ids):
        row = records[identifier]
        if (
            row.get("state") != "READY"
            or row.get("physical_cleanup_state") != "LIVE"
            or row.get("antivirus_status") != "CLEAN"
            or row.get("execution_eligible") is not True
        ):
            raise OrbitError(409, "ANTIVIRUS_UNVERIFIED", "素材缺完整可用态和扫描来源证明")
        try:
            result[identifier] = {
                "revision": row["revision"],
                "sha256": row["sha256"],
                "kind": row["kind"],
                "mime": row["mime"],
                "byte_size": row["size"],
                "width_px": row["width"],
                "height_px": row["height"],
                "duration_seconds": row["duration"],
            }
        except KeyError:
            raise OrbitError(
                503, "ALLOCATION_MATERIAL_PROOF_UNAVAILABLE", "素材安全元数据不完整"
            ) from None
    return result


class ReferenceBackedAllocationProvider(AllocationProvider):
    """TRUSTED表示代码路径，不表示已有生产能力适配器或验收通过；不自动注入app。"""

    kind = "TRUSTED"

    def __init__(self, authority=None):
        self.authority = authority
        self._ticket_owner = object()

    async def _capture(
        self, session, current, plan, request, *, previous_id=None, publication=False
    ):
        transaction = transaction_identity(session)
        if not isinstance(self.authority, AllocationReferenceAuthority):
            unavailable()
        if not isinstance(current, BusinessContext):
            raise ValueError("需要实时授权业务上下文")
        fresh = await require_business_access(session, current.actor_id, "launch", "launch.edit")
        if fresh != current:
            raise OrbitError(403, "PERMISSION_DENIED", "当前投放授权范围已变化")
        plan = parse_plan(canonical(plan).encode())
        request = parse_plan_action(canonical(request).encode(), "allocation")
        if (
            set(plan["asset_ids"]) != set(request["asset_ids"])
            or plan["allow_repeat"] != request["allow_repeat"]
        ):
            raise OrbitError(409, "ALLOCATION_INPUT_CHANGED", "素材池或重复开关与计划不一致")
        identifiers = sorted(plan["asset_ids"])
        if not 1 <= len(identifiers) <= 500:
            raise OrbitError(422, "FIELD_INVALID", "素材池必须1至500项", "/asset_ids")
        locked = await self.authority.lock_sources(session, current, plan, request)
        if (
            not isinstance(locked, LockedAllocationAuthority)
            or locked.transaction is not transaction
            or locked.context != current
            or locked.plan_hash != digest(plan)
            or any(
                not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None
                for value in (locked.authority_fingerprint, locked.source_hash)
            )
            or not isinstance(locked.capability_version, str)
            or not 1 <= len(locked.capability_version) <= 64
        ):
            unavailable()
        old = None
        if publication and previous_id is not None:
            # 旧清单从服务端精确allocation键逆查；旧新union先全局排序锁，不能分批逆锁。
            old = await lock_active_material_reference_set(
                session, current, "ALLOCATION", previous_id, additional_asset_ids=identifiers
            )
        ownership = plan["ownership"]
        records = {}
        for start in range(0, len(identifiers), 200):
            batch = identifiers[start : start + 200]
            records.update(
                await require_allocation_assets(
                    session, current, ownership["owner_user_id"], ownership["owner_team_id"], batch
                )
            )
        metadata = material_metadata(records, identifiers)
        evidence = self.authority.compatibility(
            locked, plan, request, json.loads(canonical(metadata))
        )
        slots, assets = inputs(ad_slots(plan), identifiers)
        verify_evidence(slots, assets, evidence)
        if (
            evidence.capability_version != locked.capability_version
            or evidence.source_hash != locked.source_hash
        ):
            unavailable()
        if dict(evidence.material_revisions) != {
            key: row["revision"] for key, row in metadata.items()
        }:
            raise OrbitError(409, "MATERIAL_VERSION_CONFLICT", "兼容图必须绑定实际素材版本")
        captured = CapturedAllocation(
            evidence, metadata, locked.authority_fingerprint, digest(plan)
        )
        ticket = None
        if publication:
            ticket = MaterialPublicationTicket(
                self._ticket_owner,
                transaction,
                current,
                digest(plan),
                previous_id,
                old,
                canonical(metadata).encode(),
            )
            session.info.setdefault(TICKET_KEY, []).append(ticket)
        return captured, ticket

    async def capture(self, session, current, plan, request):
        captured, _ = await self._capture(session, current, plan, request)
        return captured

    async def prepare_publication(self, session, current, packet, previous_id):
        return await self._capture(
            session,
            current,
            packet["plan"],
            packet["request"],
            previous_id=previous_id,
            publication=True,
        )

    async def publish_references(
        self, session, current, packet, solution, allocation_id, previous_id, ticket, request_id
    ):
        transaction = transaction_identity(session)
        tickets = session.info.get(TICKET_KEY, [])
        if (
            not isinstance(ticket, MaterialPublicationTicket)
            or ticket.owner is not self._ticket_owner
            or not any(item is ticket for item in tickets)
            or ticket.transaction is not transaction
            or ticket.context != current
            or ticket.previous_id != previous_id
            or ticket.plan_hash != digest(packet["plan"])
            or ticket.metadata_json != canonical(packet["material_metadata"]).encode()
        ):
            raise ValueError("素材引用发布必须使用本Provider同事务精确来源票据")
        # runtime应已完成计划/guard/旧active(input_hash)CAS；本方法不接受HTTP或plan_id授权。
        expected_slots = {row.key for row in ad_slots(packet["plan"])}
        if (
            not isinstance(solution, AllocationSolution)
            or solution.input_hash != packet["input_hash"]
            or solution.algorithm_version != "allocation-v1"
            or solution.seed != packet["request"]["seed"]
            or solution.capability_version != packet["capability_version"]
            or len(solution.assignments) != len(expected_slots)
            or {slot for slot, _ in solution.assignments} != expected_slots
            or allocation_id == previous_id
        ):
            raise OrbitError(409, "ALLOCATION_INPUT_CHANGED", "只能发布完整原冻结结果")
        used = sorted({asset for _, asset in solution.assignments})
        metadata = json.loads(ticket.metadata_json)
        if not used or not set(used) <= set(metadata):
            raise OrbitError(409, "ALLOCATION_INPUT_CHANGED", "结果含未冻结素材")
        if ticket.old_references is not None:
            await deactivate_locked_material_references(
                session, current, ticket.old_references, request_id
            )
        ownership = packet["plan"]["ownership"]
        for start in range(0, len(used), 200):
            await register_active_material_references(
                session,
                current,
                ownership["owner_user_id"],
                ownership["owner_team_id"],
                {key: metadata[key] for key in used[start : start + 200]},
                "ALLOCATION",
                allocation_id,
                request_id,
            )
        session.info[TICKET_KEY] = [item for item in tickets if item is not ticket]
