"""032真实分配队列：同事务冻结、claim围栏和完整结果发布；不创建公共Task。"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import text

from orbit_api import launch_access as access
from orbit_api.authorization import BusinessContext, require_business_access
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_allocation import CompatibilityEvidence, solve_allocation
from orbit_api.launch_allocation_packet import freeze_packet, sha, thaw_packet
from orbit_api.launch_contract import parse_plan_action, uuid_field
from orbit_api.launch_dag import build_launch_dag
from orbit_api.launch_expansion import ad_slots
from orbit_api.launch_plan_source import MAX_REVISION, capture_plan_source
from orbit_api.launch_store import LaunchStore


@dataclass(frozen=True)
class CapturedAllocation:
    evidence: CompatibilityEvidence
    material_metadata: dict
    authority_fingerprint: str
    provider_plan_hash: str


class AllocationProvider(ABC):
    """仅受控服务端实现。未有生产采集/即时证据时不提供默认猜测适配器。"""

    kind = "TRUSTED"

    @abstractmethod
    async def capture(self, session, current, plan, request):
        """先来源clock/排序素材锁，再plan锁；真实caller与owner交集、能力及CLEAN证明。"""

    @abstractmethod
    async def prepare_publication(self, session, current, packet, previous_id):
        """重取全部来源/旧新素材联合锁并返回当前CapturedAllocation与同事务引用票据。"""

    @abstractmethod
    async def publish_references(
        self, session, current, packet, solution, allocation_id, previous_id, ticket, request_id
    ):
        """plan/旧active CAS成功后，同事务释放旧精确ALLOCATION引用并登记实际used素材。"""


@dataclass(frozen=True)
class AllocationClaim:
    tenant_id: str
    allocation_id: str
    worker_id: str
    token: str
    generation: int


async def one(session, sql, params=None):
    return (await session.execute(text(sql), params or {})).mappings().first()


def _transaction(session):
    if not session.in_transaction():
        raise ValueError("分配运行时必须由调用者持有外层真实事务")


def _claim_values(claim):
    if not isinstance(claim, AllocationClaim):
        raise ValueError("必须使用真实数据库领取票据")
    return {
        "tenant": claim.tenant_id,
        "id": claim.allocation_id,
        "worker": claim.worker_id,
        "token": claim.token,
        "generation": claim.generation,
    }


def _freeze(captured, plan, request, revision):
    if not isinstance(captured, CapturedAllocation):
        raise OrbitError(503, "ALLOCATION_PROVIDER_UNAVAILABLE", "缺完整受信能力提供器结果")
    return freeze_packet(
        plan,
        request,
        captured.evidence,
        captured.material_metadata,
        plan_revision=revision,
        authority_fingerprint=captured.authority_fingerprint,
        provider_plan_hash=captured.provider_plan_hash,
    )


def assert_publication_source(source, packet, state):
    """只比较真实配置来源；纯状态头变化不能重绑或复制旧分配。"""
    if (
        state not in {"DRAFT", "VALIDATED"}
        or source.source_revision != packet["plan_revision"]
        or source.payload_hash != access.digest(packet["plan"])
        or source.canonical_payload != canonical(packet["plan"]).encode()
    ):
        raise OrbitError(409, "ALLOCATION_SOURCE_CHANGED", "配置来源或可发布状态已变化")


class AllocationRuntime:
    def __init__(self, provider=None):
        self.provider = provider

    async def require_provider(self, session):
        if not isinstance(self.provider, AllocationProvider):
            raise OrbitError(
                503, "ALLOCATION_PROVIDER_UNAVAILABLE", "平台权威能力提供器尚未配置，未受理分配"
            )
        if self.provider.kind == "ISOLATED_TEST":
            url = getattr(getattr(session, "bind", None), "url", None)
            if url is None or url.host != "127.0.0.1" or url.port != 13306:
                raise OrbitError(
                    503, "ALLOCATION_PROVIDER_UNAVAILABLE", "隔离提供器只允许本机专项端口"
                )
            database = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
            if not re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database):
                raise OrbitError(
                    503, "ALLOCATION_PROVIDER_UNAVAILABLE", "隔离测试证明禁止用于业务数据库"
                )
        elif self.provider.kind != "TRUSTED":
            raise OrbitError(503, "ALLOCATION_PROVIDER_UNAVAILABLE", "未知能力提供器类型")
        return self.provider

    async def enqueue(self, session, actor, plan_id, request, expected, key, request_id):
        _transaction(session)
        provider = await self.require_provider(session)
        current = await access.context(session, actor, "launch.edit")
        plans = LaunchStore(None)
        before = await plans.row(session, current, plan_id, unlocked=True)
        command = parse_plan_action(canonical(request).encode(), "allocation")
        plan = _decode(before["payload_json"])
        # provider只负责真实来源/权限证明，不把预读CAS头当不可变配置版本。
        captured = await provider.capture(session, current, plan, command)
        await access.clock(session, current, write=True)
        locked = await plans.row(session, current, plan_id, write=True)
        source = await capture_plan_source(session, current, locked)
        if source.payload_hash != before["payload_hash"] or source.payload() != plan:
            raise OrbitError(409, "REVISION_CONFLICT", "来源加锁后配置已变化")
        packet, manifest = _freeze(captured, source.payload(), command, source.source_revision)
        values = access.parameters(current) | {"plan": plan_id}
        intent = access.digest([plan_id, expected, command])
        replay = await access.replay(session, current, "allocation.create", key, intent)
        if replay:
            result = await self.get_for_context(session, current, plan_id, replay["id"])
            if result["input_hash"] != manifest.input_hash:
                raise OrbitError(
                    409, "ALLOCATION_SOURCE_CHANGED", "原分配来源证据已变化，旧键不能改换输入"
                )
            return result
        # 成功原键先经过当前授权/来源重验；只有全新键使用当前头If-Match。
        if locked["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "计划头已变化，请使用当前If-Match")
        if locked["state"] not in {"DRAFT", "VALIDATED"}:
            raise OrbitError(409, "PLAN_STATE_CONFLICT", "当前计划状态不允许创建分配")
        existing = await one(
            session,
            "SELECT id FROM orbit_launch_allocation WHERE tenant_id=:tenant "
            "AND plan_id=:plan AND input_hash=:hash FOR UPDATE",
            values | {"hash": manifest.input_hash},
        )
        if existing:
            result = await self.get_for_context(session, current, plan_id, existing["id"])
            await access.remember(
                session, current, "allocation.create", key, intent, {"id": result["id"]}
            )
            return result
        guard = await one(
            session,
            "SELECT allocation_id FROM orbit_launch_allocation_guard WHERE "
            "tenant_id=:tenant AND plan_id=:plan FOR UPDATE",
            values,
        )
        if guard:
            raise OrbitError(409, "ALLOCATION_BUSY", "该计划已有真实求解作业，不能并发创建第二项")
        active_rows = (
            (
                await session.execute(
                    text(
                        "SELECT id,seed,input_hash FROM orbit_launch_allocation WHERE "
                        "tenant_id=:tenant AND plan_id=:plan AND active=1 ORDER BY id "
                        "LIMIT 2 FOR UPDATE"
                    ),
                    values,
                )
            )
            .mappings()
            .all()
        )
        if len(active_rows) > 1:
            raise OrbitError(409, "ALLOCATION_MANIFEST_CORRUPT", "计划存在多个活跃分配，拒绝覆盖")
        active = active_rows[0] if active_rows else None
        if active and (active["seed"] >= 2147483647 or command["seed"] != active["seed"] + 1):
            raise OrbitError(
                409, "ALLOCATION_SEED_CONFLICT", "重新分配须明确新意图并使用旧seed加一"
            )
        identifier = str(uuid4())
        values |= {
            "id": identifier,
            "revision": source.source_revision,
            "seed": command["seed"],
            "hash": manifest.input_hash,
            "producer": provider.kind,
            "plan_hash": access.digest(plan),
            "source": packet["source_hash"],
            "authority": packet["authority_fingerprint"],
            "capability": packet["capability_version"],
            "manifest": manifest.manifest_hash,
            "document": manifest.document_hash,
            "bytes": manifest.byte_total,
            "chunks": len(manifest.chunks),
            "slots": manifest.slot_count,
            "previous": active["id"] if active else None,
            "previous_hash": active["input_hash"] if active else None,
        }
        await session.execute(
            text("""INSERT INTO orbit_launch_allocation
            (tenant_id,id,plan_id,plan_revision,state,task_id,algorithm_version,seed,input_hash,warnings_json,active,created_at,updated_at)
            VALUES(:tenant,:id,:plan,:revision,'QUEUED',NULL,'allocation-v1',:seed,:hash,'[]',0,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"""),
            values,
        )
        await session.execute(
            text("""INSERT INTO orbit_launch_allocation_runtime
            (tenant_id,allocation_id,plan_id,actor_id,producer_kind,phase,input_schema_version,plan_input_hash,source_hash,
            authority_fingerprint,capability_version,manifest_hash,document_hash,chunk_count,byte_total,slot_count,
            previous_allocation_id,previous_input_hash,next_attempt_at,created_at,updated_at)
            VALUES(:tenant,:id,:plan,:actor,:producer,'CAPTURED',1,:plan_hash,:source,:authority,:capability,:manifest,
            :document,:chunks,:bytes,:slots,:previous,:previous_hash,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"""),
            values,
        )
        for start in range(0, len(manifest.chunks), 16):
            await session.execute(
                text("""INSERT INTO orbit_launch_allocation_chunk
                (tenant_id,allocation_id,ordinal,payload,payload_hash,byte_size,created_at)
                VALUES(:tenant,:id,:ordinal,:payload,:sha,:size,UTC_TIMESTAMP(3))"""),
                [
                    values
                    | {"ordinal": index, "payload": chunk, "sha": sha(chunk), "size": len(chunk)}
                    for index, chunk in enumerate(manifest.chunks)
                    if start <= index < start + 16
                ],
            )
        await session.execute(
            text(
                "INSERT INTO orbit_launch_allocation_guard "
                "(tenant_id,plan_id,allocation_id,generation,updated_at) "
                "VALUES(:tenant,:plan,:id,1,UTC_TIMESTAMP(3))"
            ),
            values,
        )
        await session.execute(
            text(
                "UPDATE orbit_launch_allocation_runtime SET phase='QUEUED' WHERE "
                "tenant_id=:tenant AND allocation_id=:id AND phase='CAPTURED'"
            ),
            values,
        )
        await access.event(
            session,
            current,
            "ALLOCATION",
            identifier,
            source.source_revision,
            "allocation.queued",
            request_id,
            {
                "input_hash": manifest.input_hash,
                "slots": manifest.slot_count,
                "byte_total": manifest.byte_total,
                "producer_kind": provider.kind,
            },
        )
        await access.remember(
            session, current, "allocation.create", key, intent, {"id": identifier}
        )
        return await self.get_for_context(session, current, plan_id, identifier)

    async def get_for_context(self, session, current, plan_id, identifier):
        await LaunchStore(None).row(session, current, plan_id)
        row = await one(
            session,
            "SELECT * FROM orbit_launch_allocation WHERE tenant_id=:tenant "
            "AND plan_id=:plan AND id=:id FOR SHARE",
            {"tenant": current.tenant_id, "plan": plan_id, "id": identifier},
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "分配不存在或当前不可见")
        items = []
        if row["state"] == "SUCCEEDED":
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT ordinal,slot_key,account_id,asset_id,asset_revision FROM "
                            "orbit_launch_allocation_item WHERE tenant_id=:tenant AND "
                            "allocation_id=:id ORDER BY ordinal LIMIT 10001"
                        ),
                        {"tenant": current.tenant_id, "id": identifier},
                    )
                )
                .mappings()
                .all()
            )
            head = await one(
                session,
                "SELECT slot_count,phase FROM orbit_launch_allocation_runtime "
                "WHERE tenant_id=:tenant AND allocation_id=:id FOR SHARE",
                {"tenant": current.tenant_id, "id": identifier},
            )
            if (
                head is None
                or head["phase"] != "COMPLETE"
                or len(rows) != head["slot_count"]
                or len(rows) > 10000
                or any(item["ordinal"] != index for index, item in enumerate(rows))
            ):
                raise OrbitError(
                    409,
                    "ALLOCATION_MANIFEST_CORRUPT",
                    "成功分配必须有完整连续结果与真实终态manifest",
                )
            items = [
                {key: item[key] for key in ("slot_key", "account_id", "asset_id", "asset_revision")}
                for item in rows
            ]
        return {
            "id": row["id"],
            "plan_id": row["plan_id"],
            "plan_revision": row["plan_revision"],
            "state": row["state"],
            "task_id": None,
            "algorithm_version": row["algorithm_version"],
            "seed": row["seed"],
            "input_hash": row["input_hash"],
            "items": items,
            "warnings": _decode(row["warnings_json"]),
        }

    async def get(self, session, actor, plan_id, identifier):
        current = await access.context(session, actor, "launch.read")
        return await self.get_for_context(
            session,
            current,
            uuid_field(plan_id, ("id",)),
            uuid_field(identifier, ("allocation_id",)),
        )

    async def claim(self, session, worker_id, *, lease_seconds=120):
        _transaction(session)
        await self.require_provider(session)
        worker_id = uuid_field(worker_id, ("worker_id",))
        if type(lease_seconds) is not int or not 10 <= lease_seconds <= 300:
            raise ValueError("领取租约必须为10至300秒")
        # 两条有界索引分开查，避免OR让队列和租约恢复全表扫描。
        row = None
        for clause, ordering in (
            ("phase='QUEUED' AND next_attempt_at<=UTC_TIMESTAMP(3)", "next_attempt_at"),
            ("phase IN ('SOLVING','PUBLISHING') AND lease_until<=UTC_TIMESTAMP(3)", "lease_until"),
        ):
            row = await one(
                session,
                "SELECT tenant_id,allocation_id,claim_generation "
                f"FROM orbit_launch_allocation_runtime WHERE {clause} "
                "AND producer_kind=:producer AND claim_generation<9007199254740991 "
                f"ORDER BY {ordering},tenant_id,allocation_id LIMIT 1 FOR UPDATE SKIP LOCKED",
                {"producer": self.provider.kind},
            )
            if row:
                break
        if not row:
            return None
        claim = AllocationClaim(
            row["tenant_id"],
            row["allocation_id"],
            worker_id,
            str(uuid4()),
            row["claim_generation"] + 1,
        )
        values = _claim_values(claim) | {"lease": lease_seconds}
        await session.execute(
            text("""UPDATE orbit_launch_allocation_runtime SET phase='SOLVING',worker_id=:worker,
            claim_token=:token,claim_generation=:generation,attempt=attempt+1,heartbeat_at=UTC_TIMESTAMP(3),
            lease_until=TIMESTAMPADD(SECOND,:lease,UTC_TIMESTAMP(3)),updated_at=UTC_TIMESTAMP(3)
            WHERE tenant_id=:tenant AND allocation_id=:id"""),
            values,
        )
        await session.execute(
            text(
                "UPDATE orbit_launch_allocation SET "
                "state='RUNNING',updated_at=UTC_TIMESTAMP(3) WHERE "
                "tenant_id=:tenant AND id=:id"
            ),
            values,
        )
        return claim

    async def checked_claim(self, session, claim, *, lock=False):
        row = await one(
            session,
            """SELECT r.*,a.input_hash,a.plan_revision,a.state AS allocation_state
            FROM orbit_launch_allocation_runtime r JOIN orbit_launch_allocation a
            ON a.tenant_id=r.tenant_id AND a.id=r.allocation_id AND a.plan_id=r.plan_id
            WHERE r.tenant_id=:tenant AND r.allocation_id=:id AND r.worker_id=:worker
            AND r.claim_token=:token AND r.claim_generation=:generation
            AND r.phase IN ('SOLVING','PUBLISHING') AND r.lease_until>UTC_TIMESTAMP(3)"""
            + (" FOR UPDATE" if lock else ""),
            _claim_values(claim),
        )
        if row is None:
            raise OrbitError(409, "ALLOCATION_CLAIM_LOST", "领取已失效或被新围栏代次替代")
        return row

    async def heartbeat(self, session, claim, *, lease_seconds=120):
        _transaction(session)
        if type(lease_seconds) is not int or not 10 <= lease_seconds <= 300:
            raise ValueError("续租时长无效")
        await self.checked_claim(session, claim, lock=True)
        await session.execute(
            text(
                "UPDATE orbit_launch_allocation_runtime SET "
                "heartbeat_at=UTC_TIMESTAMP(3),lease_until=TIMESTAMPADD(SECOND,:lease,UTC_TIMESTAMP(3)),updated_at=UTC_TIMESTAMP(3)"
                " WHERE tenant_id=:tenant AND allocation_id=:id"
            ),
            _claim_values(claim) | {"lease": lease_seconds},
        )

    async def load(self, session, claim):
        head = await self.checked_claim(session, claim)
        current = await require_business_access(
            session, head["actor_id"], "launch", "launch.edit", acting_subject=False
        )
        if current.tenant_id != claim.tenant_id:
            raise OrbitError(403, "PERMISSION_DENIED", "受理主体租户已变化，禁止读取冻结输入")
        # 在读冻结大包/CPU求解前复核当前范围；无锁预读不逆转后续C素材→launch顺序。
        await LaunchStore(None).row(session, current, head["plan_id"], unlocked=True)
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT ordinal,payload,payload_hash,byte_size FROM "
                        "orbit_launch_allocation_chunk WHERE tenant_id=:tenant AND "
                        "allocation_id=:id ORDER BY ordinal LIMIT 257"
                    ),
                    _claim_values(claim),
                )
            )
            .mappings()
            .all()
        )
        packet, evidence = thaw_packet(head, rows)
        if (
            head["plan_input_hash"] != access.digest(packet["plan"])
            or head["plan_revision"] != packet["plan_revision"]
            or head["source_hash"] != packet["source_hash"]
            or head["authority_fingerprint"] != packet["authority_fingerprint"]
            or head["capability_version"] != packet["capability_version"]
        ):
            raise OrbitError(409, "ALLOCATION_MANIFEST_CORRUPT", "运行时头与冻结来源不一致")
        return head, packet, evidence

    async def publish(self, session, claim, solution, request_id):
        _transaction(session)
        provider = await self.require_provider(session)
        # 无锁预读仅确定主体/旧资源；真实来源按provider统一顺序先加锁，再计划CAS。
        head, packet, evidence = await self.load(session, claim)
        if head["producer_kind"] != provider.kind:
            raise OrbitError(
                503, "ALLOCATION_PROVIDER_UNAVAILABLE", "提供器种类不能接管另一来源作业"
            )
        current = await require_business_access(
            session, head["actor_id"], "launch", "launch.edit", acting_subject=False
        )
        if current.tenant_id != claim.tenant_id:
            raise OrbitError(403, "PERMISSION_DENIED", "受理主体租户已变化")
        captured, ticket = await provider.prepare_publication(
            session, current, packet, head["previous_allocation_id"]
        )
        _, current_manifest = _freeze(
            captured, packet["plan"], packet["request"], packet["plan_revision"]
        )
        if (
            current_manifest.input_hash != head["input_hash"]
            or current_manifest.document_hash != head["document_hash"]
        ):
            raise OrbitError(409, "ALLOCATION_SOURCE_CHANGED", "当前来源或完整授权证据已变化")
        # 复用纯DAG对完整分配/能力边/素材版本的独立机械检查，不产生任务。
        build_launch_dag(
            packet["plan"],
            plan_revision=packet["plan_revision"],
            allocation=solution,
            compatibility=evidence,
            material_revisions={
                key: row["revision"] for key, row in packet["material_metadata"].items()
            },
        )
        await access.clock(session, current, write=True)
        plan = await LaunchStore(None).row(session, current, head["plan_id"], write=True)
        source = await capture_plan_source(session, current, plan)
        assert_publication_source(source, packet, plan["state"])
        if plan["state"] == "VALIDATED" and plan["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "计划头已达上限，不能使预检失效")
        checked = await self.checked_claim(session, claim, lock=True)
        values = _claim_values(claim) | {"plan": head["plan_id"]}
        guard = await one(
            session,
            "SELECT allocation_id FROM orbit_launch_allocation_guard WHERE "
            "tenant_id=:tenant AND plan_id=:plan FOR UPDATE",
            values,
        )
        if guard is None or guard["allocation_id"] != claim.allocation_id:
            raise OrbitError(409, "ALLOCATION_CLAIM_LOST", "单计划求解指针已变化")
        active_rows = (
            (
                await session.execute(
                    text(
                        "SELECT id,input_hash FROM orbit_launch_allocation WHERE "
                        "tenant_id=:tenant AND plan_id=:plan AND active=1 ORDER BY id "
                        "LIMIT 2 FOR UPDATE"
                    ),
                    values,
                )
            )
            .mappings()
            .all()
        )
        if (
            len(active_rows) > 1
            or (active_rows[0]["id"] if active_rows else None) != checked["previous_allocation_id"]
            or (active_rows[0]["input_hash"] if active_rows else None)
            != checked["previous_input_hash"]
        ):
            raise OrbitError(409, "ALLOCATION_SOURCE_CHANGED", "旧活跃分配已变化，不能覆盖并发结果")
        await session.execute(
            text(
                "UPDATE orbit_launch_allocation_runtime SET phase='PUBLISHING' "
                "WHERE tenant_id=:tenant AND allocation_id=:id"
            ),
            values,
        )
        rows = []
        for ordinal, (slot_key, asset) in enumerate(solution.assignments):
            metadata = packet["material_metadata"][asset]
            rows.append(
                values
                | {
                    "ordinal": ordinal,
                    "slot": slot_key,
                    "account": slot_key.split("/", 1)[0],
                    "asset": asset,
                    "revision": metadata["revision"],
                    "sha": metadata["sha256"],
                }
            )
        for start in range(0, len(rows), 200):
            await session.execute(
                text("""INSERT INTO orbit_launch_allocation_item
                (tenant_id,allocation_id,ordinal,slot_key,account_id,asset_id,asset_revision,asset_sha256)
                VALUES(:tenant,:id,:ordinal,:slot,:account,:asset,:revision,:sha)"""),
                rows[start : start + 200],
            )
        await provider.publish_references(
            session,
            current,
            packet,
            solution,
            claim.allocation_id,
            checked["previous_allocation_id"],
            ticket,
            request_id,
        )
        # 长发布/引用事务跨越租约截止必须整批回滚；持行锁不能自动延长授权租约。
        await self.checked_claim(session, claim, lock=True)
        await session.execute(
            text(
                "UPDATE orbit_launch_allocation SET active=0 WHERE "
                "tenant_id=:tenant AND plan_id=:plan AND active=1"
            ),
            values,
        )
        await session.execute(
            text(
                "UPDATE orbit_launch_allocation SET "
                "state='SUCCEEDED',active=1,warnings_json=:warnings,updated_at=UTC_TIMESTAMP(3)"
                " WHERE tenant_id=:tenant AND id=:id"
            ),
            values | {"warnings": canonical(list(solution.warnings))},
        )
        # 分配变更只使已有预检失效；DRAFT无配置或状态变化时不制造新头/PlanVersion。
        if plan["state"] == "VALIDATED":
            changed = await session.execute(
                text(
                    "UPDATE orbit_launch_plan SET state='DRAFT',revision=revision+1,"
                    "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:plan "
                    "AND revision=:head_revision AND state='VALIDATED'"
                ),
                values | {"head_revision": plan["revision"]},
            )
            if changed.rowcount != 1:
                raise OrbitError(409, "REVISION_CONFLICT", "发布时计划状态头已变化")
        await session.execute(
            text(
                "UPDATE orbit_launch_allocation_runtime SET "
                "phase='COMPLETE',lease_until=NULL,error_code=NULL,updated_at=UTC_TIMESTAMP(3)"
                " WHERE tenant_id=:tenant AND allocation_id=:id"
            ),
            values,
        )
        await session.execute(
            text(
                "DELETE FROM orbit_launch_allocation_guard WHERE "
                "tenant_id=:tenant AND plan_id=:plan AND allocation_id=:id"
            ),
            values,
        )
        await access.event(
            session,
            current,
            "ALLOCATION",
            claim.allocation_id,
            packet["plan_revision"],
            "allocation.succeeded",
            request_id,
            {
                "input_hash": solution.input_hash,
                "slots": len(rows),
                "squared_usage": solution.squared_usage,
                "producer_kind": provider.kind,
            },
        )
        return await self.get_for_context(session, current, head["plan_id"], claim.allocation_id)

    async def fail(self, session, claim, code, request_id):
        """只记受控明确内部失败；DB故障不在失败事务继续写，由调用边界回滚后再调用。"""
        _transaction(session)
        if code not in {
            "ALLOCATION_NO_MATCH",
            "ALLOCATION_SOURCE_CHANGED",
            "ALLOCATION_MANIFEST_CORRUPT",
            "ALLOCATION_TIMEOUT",
            "ALLOCATION_AUTH_REVOKED",
            "ALLOCATION_INPUT_INVALID",
        }:
            raise ValueError("失败码必须为受控枚举，不记录异常正文")
        await self.require_provider(session)
        preview = await self.checked_claim(session, claim)
        # 与publish相同launch clock→plan→runtime，不能反向持runtime等待目录锁。
        await one(
            session,
            "SELECT plan_revision FROM orbit_launch_clock WHERE tenant_id=:tenant FOR UPDATE",
            _claim_values(claim),
        )
        plan = await one(
            session,
            "SELECT owner_user_id,owner_team_id FROM orbit_launch_plan WHERE "
            "tenant_id=:tenant AND id=:plan FOR UPDATE",
            _claim_values(claim) | {"plan": preview["plan_id"]},
        )
        head = await self.checked_claim(session, claim, lock=True)
        values = _claim_values(claim) | {"plan": head["plan_id"], "code": code}
        await session.execute(
            text(
                "UPDATE orbit_launch_allocation SET "
                "state='FAILED',active=0,warnings_json=:warnings,updated_at=UTC_TIMESTAMP(3) WHERE "
                "tenant_id=:tenant AND id=:id"
            ),
            values | {"warnings": canonical(["分配未完成：" + code])},
        )
        await session.execute(
            text(
                "UPDATE orbit_launch_allocation_runtime SET "
                "phase='FAILED',error_code=:code,lease_until=NULL,updated_at=UTC_TIMESTAMP(3)"
                " WHERE tenant_id=:tenant AND allocation_id=:id"
            ),
            values,
        )
        await session.execute(
            text(
                "DELETE FROM orbit_launch_allocation_guard WHERE "
                "tenant_id=:tenant AND plan_id=:plan AND allocation_id=:id"
            ),
            values,
        )
        # 即时撤权也须保存原主体审计，不借已撤动作重新取得写入能力；此处只终结既有内部作业。
        audit_context = BusinessContext(
            head["actor_id"], claim.tenant_id, "USER", plan["owner_user_id"], plan["owner_team_id"]
        )
        await access.event(
            session,
            audit_context,
            "ALLOCATION",
            claim.allocation_id,
            head["plan_revision"],
            "allocation.failed",
            request_id,
            {"error_code": code},
        )

    async def defer_timeout(self, session, claim, request_id, *, max_attempts=3):
        """纯CPU超时沿原hash/真实guard异步重排；不保存部分映射或改变seed。"""
        _transaction(session)
        await self.require_provider(session)
        if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
            raise ValueError("超时尝试上限必须1至10")
        preview = await self.checked_claim(session, claim)
        if preview["attempt"] >= max_attempts:
            return await self.fail(session, claim, "ALLOCATION_TIMEOUT", request_id)
        await one(
            session,
            "SELECT plan_revision FROM orbit_launch_clock WHERE tenant_id=:tenant FOR UPDATE",
            _claim_values(claim),
        )
        plan = await one(
            session,
            "SELECT owner_user_id,owner_team_id FROM orbit_launch_plan WHERE "
            "tenant_id=:tenant AND id=:plan FOR UPDATE",
            _claim_values(claim) | {"plan": preview["plan_id"]},
        )
        head = await self.checked_claim(session, claim, lock=True)
        values = _claim_values(claim)
        await session.execute(
            text("""UPDATE orbit_launch_allocation_runtime SET phase='QUEUED',lease_until=NULL,
            error_code='ALLOCATION_TIMEOUT',next_attempt_at=TIMESTAMPADD(SECOND,1,UTC_TIMESTAMP(3)),
            updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND allocation_id=:id"""),
            values,
        )
        await session.execute(
            text(
                "UPDATE orbit_launch_allocation SET "
                "state='QUEUED',updated_at=UTC_TIMESTAMP(3) WHERE "
                "tenant_id=:tenant AND id=:id"
            ),
            values,
        )
        audit_context = BusinessContext(
            head["actor_id"], claim.tenant_id, "USER", plan["owner_user_id"], plan["owner_team_id"]
        )
        await access.event(
            session,
            audit_context,
            "ALLOCATION",
            claim.allocation_id,
            head["plan_revision"],
            "allocation.deferred",
            request_id,
            {"input_hash": head["input_hash"], "attempt": head["attempt"]},
        )


def solve_packet(packet, evidence, *, seconds=60):
    """仅CPU；调用方必须已提交领取事务并在独立进程施加硬资源限制。"""
    return solve_allocation(
        ad_slots(packet["plan"]),
        packet["plan"]["asset_ids"],
        evidence,
        allow_repeat=packet["request"]["allow_repeat"],
        seed=packet["request"]["seed"],
        seconds=seconds,
        material_revisions={
            asset: row["revision"] for asset, row in packet["material_metadata"].items()
        },
    )
