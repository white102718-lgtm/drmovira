"""原execute独立持久接力；在制私有Store尚未通过真实受理专项。

039由主线创建/真实验证后接持久方法。不得借此文件打开生产execute，或更改
旧TaskManifestStore隔离构建器的source==head/ISOLATED_TEST语义。
"""

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import bindparam, text

from orbit_api import launch_access as access
from orbit_api import task_access
from orbit_api.authorization import BusinessContext
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import parse_plan_action, uuid_field
from orbit_api.launch_execution_contract import (
    PreparedExecution,
    iter_execution_nodes,
    iter_prepared_chunks,
)
from orbit_api.launch_expansion import Counts
from orbit_api.launch_plan_source import PlanSource, capture_plan_source
from orbit_api.launch_store import LaunchStore
from orbit_api.launch_validation_contract import FrozenValidation, is_current, validation_response
from orbit_api.launch_validation_store import (
    LaunchValidationStore,
    ValidationEvidence,
    _csrf,
)
from orbit_api.task_contract import CHUNK_SIZE, GraphDigest, node_id
from orbit_api.task_store import TaskStore


def unavailable():
    raise OrbitError(503, "LAUNCH_EXECUTION_AUTHORITY_UNAVAILABLE", "生产执行权威来源尚未就绪")


def corrupt():
    raise OrbitError(503, "LAUNCH_EXECUTION_PREPARATION_UNAVAILABLE", "完整执行准备载荷不一致")


class ExecutionAuthorityProvider(ABC):
    """服务端受控注入；任意verified布尔或结构合法不等于权威许可。"""

    kind = "TRUSTED"

    @abstractmethod
    async def capture(self, request):
        """事务外只读采集，不接数据库session，不执行平台写入。"""

    @abstractmethod
    async def revalidate(self, session, current, source, evidence):
        """仅当前数据库来源锁；来源→launch clock顺序，不做网络或持久写。"""

    @abstractmethod
    async def publish_references(self, session, current, evidence, task_id, request_id):
        """实际受理事务登记完整EXECUTION引用；锁须已在head之前取得，不能空成功。"""


async def require_execution_provider(session, provider):
    """必须在任何隐藏Task/command INSERT之前调用；不把kind字符串当权限。"""
    if not isinstance(provider, ExecutionAuthorityProvider):
        unavailable()
    if provider.kind == "TRUSTED":
        return provider
    if provider.kind != "ISOLATED_TEST":
        unavailable()
    url = session.bind.url
    # 先检查目标，不为普通生产库执行测试协议查询。
    if url.host != "127.0.0.1" or url.port != 13306:
        unavailable()
    database = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
    if not isinstance(database, str) or not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database):
        unavailable()
    return provider


@dataclass(frozen=True, repr=False)
class BytePacket:
    ordinal: int
    payload: bytes
    sha256: str


@dataclass(frozen=True, repr=False)
class NodePacket:
    ordinal: int
    initial_json: bytes
    commands_json: bytes
    count: int
    edge_count: int
    sha256: str


@dataclass(frozen=True)
class StageBlueprint:
    """只保存有界期望头；不是数据库seal证明或已获得执行授权。"""

    expected_bytes: int
    expected_byte_chunks: int
    expected_node_count: int
    expected_node_chunks: int
    expected_command_count: int
    expected_edge_count: int
    manifest_hash: str
    task_chunk_hash: str


def iter_byte_packets(prepared):
    """完整字节文档分块，逐块最多64KiB；不物化全展开文档。"""
    if not isinstance(prepared, PreparedExecution):
        corrupt()
    for ordinal, payload in enumerate(iter_prepared_chunks(prepared)):
        yield BytePacket(ordinal, payload, hashlib.sha256(payload).hexdigest())


def iter_node_packets(prepared):
    """同一遍历产出原DagNode和完整resolved命令，最多500节点一包。"""
    if not isinstance(prepared, PreparedExecution) or not prepared.dag.nodes:
        corrupt()
    fields = tuple(prepared.dag.nodes[0].__dataclass_fields__)
    originals, commands, ordinal = [], [], 0
    for row in iter_execution_nodes(prepared):
        originals.append({key: row[key] for key in fields})
        commands.append(row)
        if len(originals) == CHUNK_SIZE:
            yield _packet(ordinal, originals, commands)
            ordinal += 1
            originals, commands = [], []
    if originals:
        yield _packet(ordinal, originals, commands)


def _packet(ordinal, originals, commands):
    original_bytes = canonical(originals).encode()
    return NodePacket(
        ordinal,
        original_bytes,
        canonical(commands).encode(),
        len(originals),
        sum(len(row["parent_keys"]) for row in originals),
        hashlib.sha256(original_bytes).hexdigest(),
    )


def stage_blueprint(prepared):
    """事务外重核完整字节/节点，最多保留200个块头；不信自填expected计数。"""
    digest, size, byte_count = hashlib.sha256(), 0, 0
    for packet in iter_byte_packets(prepared):
        digest.update(packet.payload)
        size += len(packet.payload)
        byte_count += 1
    chunks, nodes, edges = [], 0, 0
    for packet in iter_node_packets(prepared):
        if packet.ordinal != len(chunks) or not 1 <= packet.count <= CHUNK_SIZE:
            corrupt()
        chunks.append((packet.ordinal, packet.count, packet.sha256))
        nodes += packet.count
        edges += packet.edge_count
        if len(chunks) > 200:
            corrupt()
    if (
        digest.hexdigest() != prepared.manifest_hash
        or size != prepared.manifest_bytes
        or nodes != prepared.dag.total_dag_node_count
        or not 1 <= nodes <= 100000
    ):
        corrupt()
    return StageBlueprint(
        size,
        byte_count,
        nodes,
        len(chunks),
        nodes,
        edges,
        prepared.manifest_hash,
        hashlib.sha256(canonical(chunks).encode()).hexdigest(),
    )


@dataclass(frozen=True)
class NodeChunkProof:
    ordinal: int
    count: int
    edge_count: int
    node_sha256: str
    command_sha256: str
    node_bytes: int
    command_bytes: int


@dataclass(frozen=True)
class ExecutionBuildSpec:
    blueprint: StageBlueprint
    chunks: tuple[NodeChunkProof, ...]


def execution_build_spec(prepared):
    """事务外完整实算；命令包根不从DB自报头或HTTP输入构造。"""
    blueprint = stage_blueprint(prepared)
    chunks = tuple(
        NodeChunkProof(
            row.ordinal,
            row.count,
            row.edge_count,
            row.sha256,
            hashlib.sha256(row.commands_json).hexdigest(),
            len(row.initial_json),
            len(row.commands_json),
        )
        for row in iter_node_packets(prepared)
    )
    if len(chunks) != blueprint.expected_node_chunks:
        corrupt()
    return ExecutionBuildSpec(blueprint, chunks)


def checked_node_packet(packet, spec):
    """先核不可变受控编译证明与长度，再解析一个有界包，避免N+1/任意JSON。"""
    if not isinstance(packet, NodePacket) or not isinstance(spec, ExecutionBuildSpec):
        corrupt()
    if (
        not isinstance(packet.initial_json, bytes)
        or not isinstance(packet.commands_json, bytes)
        or type(packet.count) is not int
        or type(packet.edge_count) is not int
    ):
        corrupt()
    if type(packet.ordinal) is not int or not 0 <= packet.ordinal < len(spec.chunks):
        corrupt()
    proof = spec.chunks[packet.ordinal]
    if (
        (
            packet.count,
            packet.edge_count,
            packet.sha256,
            len(packet.initial_json),
            len(packet.commands_json),
        )
        != (proof.count, proof.edge_count, proof.node_sha256, proof.node_bytes, proof.command_bytes)
        or hashlib.sha256(packet.initial_json).hexdigest() != proof.node_sha256
        or hashlib.sha256(packet.commands_json).hexdigest() != proof.command_sha256
    ):
        corrupt()
    originals, commands = json.loads(packet.initial_json), json.loads(packet.commands_json)
    if (
        not isinstance(originals, list)
        or not isinstance(commands, list)
        or len(originals) != proof.count
        or len(commands) != proof.count
    ):
        corrupt()
    return originals, commands


@dataclass(frozen=True, repr=False)
class ExecutionEvidence:
    current: BusinessContext
    validation_id: str
    fingerprint: str
    prepared: PreparedExecution


@dataclass(frozen=True, repr=False)
class StageHandle:
    id: str
    task_id: str
    evidence: ExecutionEvidence
    spec: ExecutionBuildSpec
    auth_version: int
    authorization_fingerprint: str
    key_hash: str


def stale():
    raise OrbitError(409, "STALE_PREVIEW", "执行来源、当前授权或完整准备已变化")


async def database_now(session):
    value = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
    if not isinstance(value, datetime):
        corrupt()
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def authorization_snapshot(session, current):
    version = (
        await session.execute(
            text("SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"),
            {"actor": current.actor_id},
        )
    ).scalar_one()
    if type(version) is not int or not 1 <= version <= 9007199254740991:
        stale()
    teams = await access.teams(session, current)
    return version, access.digest([current.__dict__, version, sorted(teams)])


async def insert_values(session, table, values):
    """只供内部常量表/列；值一律SQL绑定，批量最多500节点或其有界父边。"""
    if not values:
        return
    batch = values if isinstance(values, list) else [values]
    keys = tuple(batch[0])
    if any(tuple(row) != keys for row in batch):
        corrupt()
    batch = [
        {
            key: (
                value.astimezone(UTC).replace(tzinfo=None)
                if isinstance(value, datetime) and value.tzinfo is not None
                else value
            )
            for key, value in row.items()
        }
        for row in batch
    ]
    await session.execute(
        text(
            "INSERT INTO "
            + table
            + "("
            + ",".join(keys)
            + ") VALUES("
            + ",".join(":" + key for key in keys)
            + ")"
        ),
        batch,
    )


class LaunchExecutionStore:
    """新受控私有持久方法；尚未开放execute/accept，不启动发送Worker。"""

    def __init__(self, tokens, provider=None):
        self.tokens, self.provider = tokens, provider

    async def _authorized(self, session, actor, authorization, csrf, evidence):
        current = await access.context(session, actor, "launch.execute")
        _csrf(self.tokens, current, authorization, csrf)
        await require_execution_provider(session, self.provider)
        if not isinstance(evidence, ExecutionEvidence) or current != evidence.current:
            stale()
        if (
            not isinstance(evidence.prepared, PreparedExecution)
            or not isinstance(evidence.fingerprint, str)
            or not re.fullmatch(r"[a-f0-9]{64}", evidence.fingerprint)
        ):
            corrupt()
        if evidence.prepared.source.tenant_id != current.tenant_id:
            stale()
        if self.provider.kind == "TRUSTED":
            profiles = json.loads(evidence.prepared.inputs_json).get("resolved_metric_profiles", {})
            if not profiles or any(
                row.get("profile", {}).get("source") != "META" for row in profiles.values()
            ):
                unavailable()
        if evidence.prepared.source.payload()["activate_after_create"]:
            if await access.context(session, actor, "launch.publish") != current:
                stale()
            if json.loads(evidence.prepared.request_json)["activate_ack"] is not True:
                stale()
        return current

    async def stage_begin(
        self, session, actor, authorization, csrf, key, request_id, evidence, spec
    ):
        """私有构建开始：source→launch写→head→038/引用→task写→真实Task→prep。

        spec必须在外层事务之前由execution_build_spec产生；不能接HTTP的prepared_id。
        此处只创建隐藏BUILDING，不写受理回执/公开事件或平台命令发送。
        """
        if not session.in_transaction():
            raise ValueError("私有stage必须处于调用者外层事务")
        current = await self._authorized(session, actor, authorization, csrf, evidence)
        if (
            not isinstance(spec, ExecutionBuildSpec)
            or spec.blueprint.manifest_hash != evidence.prepared.manifest_hash
        ):
            corrupt()
        if not isinstance(key, str) or not re.fullmatch(r"[ -~]{16,128}", key):
            raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "须提供原幂等键")
        prepared = evidence.prepared
        # revalidate只能持来源DB锁，不能网络/先持launch头。
        if (
            await self.provider.revalidate(session, current, prepared.source, evidence)
            is not evidence
        ):
            stale()
        await access.clock(session, current, write=True)
        head = await LaunchStore(self.tokens).row(
            session, current, prepared.source.plan_id, write=True
        )
        if head["state"] != "VALIDATED" or head["revision"] != prepared.validated_head_revision:
            stale()
        source = await capture_plan_source(session, current, head)
        if source != prepared.source:
            stale()
        params = {"tenant": current.tenant_id, "validation": evidence.validation_id}
        validation = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_launch_validation WHERE tenant_id=:tenant AND "
                        "id=:validation FOR SHARE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        if validation is None or (
            validation["plan_id"],
            validation["source_revision"],
            validation["payload_hash"],
            validation["validated_head_revision"],
            validation["validation_hash"],
        ) != (
            source.plan_id,
            source.source_revision,
            source.payload_hash,
            source.head_revision,
            prepared.validation_hash,
        ):
            stale()
        arguments = json.loads(prepared.inputs_json)
        # 内部复用仅DB引用核对，无edit/read授权入口；完整items仍各一次集合锁读。
        adapter = ValidationEvidence(
            evidence.fingerprint,
            arguments["scope_version"],
            prepared.dag.total_dag_node_count,
            (),
            (),
            prepared.inputs_json,
        )
        await LaunchValidationStore(self.tokens)._lock_references(
            session,
            current,
            source,
            {
                "allocation_id": arguments["allocation"]["id"],
                "name_reservation_id": arguments["name_reservation"]["id"],
            },
            adapter,
        )
        now = await database_now(session)
        expiry = validation["expires_at"]
        expiry = expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry.astimezone(UTC)
        if (
            now >= expiry
            or validation["naming_date"] != (now + timedelta(hours=8)).date()
            or expiry != prepared.validation_expires_at
        ):
            stale()
        version, fingerprint = await authorization_snapshot(session, current)
        await task_access.clock(session, current, write=True)
        old = (
            (
                await session.execute(
                    text(
                        "SELECT id,manifest_phase FROM orbit_task WHERE tenant_id=:tenant AND "
                        "source_plan_id=:plan "
                        "AND source_revision=:source FOR UPDATE"
                    ),
                    {
                        "tenant": current.tenant_id,
                        "plan": source.plan_id,
                        "source": source.source_revision,
                    },
                )
            )
            .mappings()
            .first()
        )
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        if old is not None:
            existing = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_launch_execution_preparation WHERE "
                            "tenant_id=:tenant AND task_id=:task FOR UPDATE"
                        ),
                        {"tenant": current.tenant_id, "task": old["id"]},
                    )
                )
                .mappings()
                .first()
            )
            if (
                existing is None
                or old["manifest_phase"] != "BUILDING"
                or existing["state"] not in {"BUILDING", "SEALING", "SEALED"}
            ):
                stale()
            if (
                existing["actor_id"],
                existing["subject_id"],
                existing["intent_hash"],
                existing["manifest_hash"],
                existing["idempotency_key_hash"],
                existing["authorization_fingerprint"],
                existing["validation_id"],
            ) != (
                actor,
                current.subject_id,
                prepared.request_payload_hash,
                prepared.manifest_hash,
                key_hash,
                fingerprint,
                evidence.validation_id,
            ):
                stale()
            handle = StageHandle(
                existing["id"], old["id"], evidence, spec, version, fingerprint, key_hash
            )
            verify_stage_binding(existing, handle, self.provider.kind)
            expiry = existing["expires_at"]
            expiry = expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry.astimezone(UTC)
            if now >= expiry:
                stale()
            # 不能把原构建者的handle交给并发请求；后者失败后的ABORT会误杀前者。
            # 无分布式lease不承诺TTL内接管；同key保留意图，稍后仅重放真实已受理Task。
            raise OrbitError(
                409,
                "EXECUTION_PREPARATION_IN_PROGRESS",
                "同一执行意图仍在完整准备，请保留原请求重查",
            )
        task_id, preparation_id = str(uuid4()), str(uuid4())
        proof = spec.blueprint
        await insert_values(
            session,
            "orbit_task",
            dict(
                tenant_id=current.tenant_id,
                id=task_id,
                owner_user_id=head["owner_user_id"],
                owner_team_id=head["owner_team_id"],
                source_plan_id=source.plan_id,
                source_revision=source.source_revision,
                source_hash=source.payload_hash,
                execution_mode=source.payload()["execution_mode"],
                producer_kind=self.provider.kind,
                graph_hash=prepared.dag.graph_hash,
                manifest_hash=proof.task_chunk_hash,
                expected_node_count=proof.expected_node_count,
                expected_chunk_count=proof.expected_node_chunks,
                accepted_request_id=request_id,
                created_by=actor,
                created_at=now,
                updated_at=now,
                dag_schema_version=prepared.dag.schema_version,
                plan_input_hash=prepared.dag.plan_input_hash,
                allocation_input_hash=prepared.dag.allocation_input_hash,
            ),
        )
        midnight = datetime.combine(
            (now + timedelta(hours=8)).date() + timedelta(days=1), datetime.min.time(), tzinfo=UTC
        ) - timedelta(hours=8)
        await insert_values(
            session,
            "orbit_launch_execution_preparation",
            dict(
                tenant_id=current.tenant_id,
                id=preparation_id,
                task_id=task_id,
                plan_id=source.plan_id,
                source_revision=source.source_revision,
                payload_hash=source.payload_hash,
                validation_id=evidence.validation_id,
                validated_head_revision=source.head_revision,
                validation_hash=prepared.validation_hash,
                validation_expires_at=expiry,
                naming_date=validation["naming_date"],
                actor_id=actor,
                subject_id=current.subject_id,
                owner_user_id=head["owner_user_id"],
                owner_team_id=head["owner_team_id"],
                auth_version=version,
                authorization_fingerprint=fingerprint,
                intent_hash=prepared.request_payload_hash,
                idempotency_key_hash=key_hash,
                provider_kind=self.provider.kind,
                provider_fingerprint=evidence.fingerprint,
                manifest_schema_version=1,
                manifest_hash=proof.manifest_hash,
                task_chunk_hash=proof.task_chunk_hash,
                graph_hash=prepared.dag.graph_hash,
                plan_input_hash=prepared.dag.plan_input_hash,
                allocation_input_hash=prepared.dag.allocation_input_hash,
                expected_bytes=proof.expected_bytes,
                expected_byte_chunks=proof.expected_byte_chunks,
                expected_node_count=proof.expected_node_count,
                expected_node_chunks=proof.expected_node_chunks,
                expected_command_count=proof.expected_command_count,
                expected_edge_count=proof.expected_edge_count,
                created_at=now,
                updated_at=now,
                expires_at=min(expiry, midnight),
            ),
        )
        return StageHandle(preparation_id, task_id, evidence, spec, version, fingerprint, key_hash)

    async def _locked(self, session, actor, authorization, csrf, handle):
        if not session.in_transaction() or not isinstance(handle, StageHandle):
            corrupt()
        current = await self._authorized(session, actor, authorization, csrf, handle.evidence)
        head = await LaunchStore(self.tokens).row(
            session, current, handle.evidence.prepared.source.plan_id, unlocked=True
        )
        if (
            head["revision"] != handle.evidence.prepared.validated_head_revision
            or head["state"] != "VALIDATED"
        ):
            stale()
        version, fingerprint = await authorization_snapshot(session, current)
        if (version, fingerprint) != (handle.auth_version, handle.authorization_fingerprint):
            stale()
        params = {"tenant": current.tenant_id, "task": handle.task_id, "id": handle.id}
        task = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_task WHERE tenant_id=:tenant AND id=:task FOR UPDATE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        stage = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_launch_execution_preparation WHERE "
                        "tenant_id=:tenant AND id=:id AND task_id=:task FOR UPDATE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        now = await database_now(session)
        if (
            task is None
            or stage is None
            or stage["actor_id"] != actor
            or stage["subject_id"] != current.subject_id
        ):
            stale()
        expiry = stage["expires_at"]
        expiry = expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry.astimezone(UTC)
        if (
            now >= expiry
            or stage["intent_hash"] != handle.evidence.prepared.request_payload_hash
            or stage["manifest_hash"] != handle.spec.blueprint.manifest_hash
        ):
            stale()
        if task["manifest_phase"] != "BUILDING" or stage["state"] != "BUILDING":
            stale()
        verify_stage_binding(stage, handle, self.provider.kind)
        return current, task, stage, params

    async def append_bytes(self, session, actor, authorization, csrf, handle, packet):
        if (
            not isinstance(packet, BytePacket)
            or type(packet.ordinal) is not int
            or not 0 <= packet.ordinal < handle.spec.blueprint.expected_byte_chunks
        ):
            corrupt()
        if (
            not isinstance(packet.payload, bytes)
            or not 1 <= len(packet.payload) <= 65536
            or hashlib.sha256(packet.payload).hexdigest() != packet.sha256
        ):
            corrupt()
        current, task, stage, params = await self._locked(
            session, actor, authorization, csrf, handle
        )
        if packet.ordinal < stage["persisted_byte_chunks"]:
            old = (
                (
                    await session.execute(
                        text(
                            "SELECT payload,chunk_hash FROM orbit_launch_execution_byte_chunk "
                            "WHERE tenant_id=:tenant AND preparation_id=:id AND "
                            "ordinal=:ordinal"
                        ),
                        params | {"ordinal": packet.ordinal},
                    )
                )
                .mappings()
                .first()
            )
            if (
                old is None
                or bytes(old["payload"]) != packet.payload
                or old["chunk_hash"] != packet.sha256
            ):
                stale()
            return
        if packet.ordinal != stage["persisted_byte_chunks"]:
            stale()
        await insert_values(
            session,
            "orbit_launch_execution_byte_chunk",
            dict(
                tenant_id=current.tenant_id,
                preparation_id=handle.id,
                ordinal=packet.ordinal,
                byte_length=len(packet.payload),
                chunk_hash=packet.sha256,
                payload=packet.payload,
                created_at=await database_now(session),
            ),
        )
        await session.execute(
            text(
                "UPDATE orbit_launch_execution_preparation SET "
                "persisted_bytes=persisted_bytes+:bytes,"
                "persisted_byte_chunks=persisted_byte_chunks+1,mutation_revision=mutation_revis"
                "ion+1,updated_at=UTC_TIMESTAMP(3) "
                "WHERE tenant_id=:tenant AND id=:id"
            ),
            params | {"bytes": len(packet.payload)},
        )

    async def append_nodes(self, session, actor, authorization, csrf, handle, packet):
        if not isinstance(handle, StageHandle):
            corrupt()
        originals, commands = checked_node_packet(packet, handle.spec)
        current, task, stage, params = await self._locked(
            session, actor, authorization, csrf, handle
        )
        if packet.ordinal < stage["persisted_node_chunks"]:
            old = (
                (
                    await session.execute(
                        text(
                            "SELECT expected_count,expected_hash,persisted FROM "
                            "orbit_task_chunk WHERE tenant_id=:tenant AND task_id=:task AND "
                            "ordinal=:ordinal"
                        ),
                        params | {"ordinal": packet.ordinal},
                    )
                )
                .mappings()
                .first()
            )
            if (
                old is None
                or old["expected_count"] != packet.count
                or old["expected_hash"] != packet.sha256
                or old["persisted"] != 1
            ):
                stale()
            return
        if packet.ordinal != stage["persisted_node_chunks"]:
            stale()
        now = await database_now(session)
        rows, edges, intents = [], [], []
        observation_hash = hashlib.sha256(handle.evidence.prepared.observations_json).hexdigest()
        for index, (original, command) in enumerate(zip(originals, commands, strict=True)):
            identifier = node_id(handle.task_id, original["node_key"])
            rows.append(
                dict(
                    tenant_id=current.tenant_id,
                    task_id=handle.task_id,
                    id=identifier,
                    ordinal=packet.ordinal * CHUNK_SIZE + index,
                    node_key=original["node_key"],
                    kind=original["kind"],
                    initial_json=canonical(original),
                    updated_at=now,
                )
            )
            edges.extend(
                dict(
                    tenant_id=current.tenant_id,
                    task_id=handle.task_id,
                    child_id=identifier,
                    parent_id=node_id(handle.task_id, parent),
                )
                for parent in original["parent_keys"]
            )
            configuration = canonical(command["resolved_configuration"])
            if (
                hashlib.sha256(configuration.encode()).hexdigest()
                != command["resolved_configuration_hash"]
            ):
                corrupt()
            intents.append(
                dict(
                    tenant_id=current.tenant_id,
                    preparation_id=handle.id,
                    task_id=handle.task_id,
                    node_id=identifier,
                    ordinal=packet.ordinal * CHUNK_SIZE + index,
                    node_key=original["node_key"],
                    kind=original["kind"],
                    purpose=original["purpose"],
                    account_id=original["account_id"],
                    target_key=original["target_key"],
                    resolved_configuration_json=configuration,
                    resolved_configuration_hash=command["resolved_configuration_hash"],
                    observation_binding_hash=observation_hash,
                    updated_at=now,
                    created_at=now,
                )
            )
        await insert_values(session, "orbit_task_node", rows)
        await insert_values(session, "orbit_task_edge", edges)
        await insert_values(session, "orbit_launch_execution_command", intents)
        await insert_values(
            session,
            "orbit_task_chunk",
            dict(
                tenant_id=current.tenant_id,
                task_id=handle.task_id,
                ordinal=packet.ordinal,
                expected_count=packet.count,
                expected_hash=packet.sha256,
                persisted=1,
            ),
        )
        await session.execute(
            text(
                "UPDATE orbit_task SET node_count=node_count+:nodes,edge_count=edge_count+:edges,"
                "updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:task"
            ),
            params | {"nodes": packet.count, "edges": packet.edge_count},
        )
        await session.execute(
            text(
                "UPDATE orbit_launch_execution_preparation SET "
                "persisted_node_count=persisted_node_count+:nodes,"
                "persisted_node_chunks=persisted_node_chunks+1,persisted_command_count=persiste"
                "d_command_count+:nodes,"
                "persisted_edge_count=persisted_edge_count+:edges,mutation_revision=mutation_re"
                "vision+1,updated_at=UTC_TIMESTAMP(3) "
                "WHERE tenant_id=:tenant AND id=:id"
            ),
            params | {"nodes": packet.count, "edges": packet.edge_count},
        )

    async def prepare(
        self,
        session_factory,
        actor,
        authorization,
        csrf,
        key,
        value,
        identifier,
        expected,
        request_id,
    ):
        return await _prepare_execution(
            self,
            session_factory,
            actor,
            authorization,
            csrf,
            key,
            value,
            identifier,
            expected,
            request_id,
        )

    async def abort_stage(self, session, handle):
        return await _abort_stage(session, handle)

    async def cleanup_stage(self, session, handle, *, limit=500):
        return await _cleanup_stage(session, handle, limit=limit)

    async def cleanup_expired(self, session, *, limit=500):
        return await _cleanup_expired(session, limit=limit)

    async def seal(self, session_factory, actor, authorization, csrf, handle):
        return await _seal_execution(self, session_factory, actor, authorization, csrf, handle)

    async def accept(
        self,
        session,
        actor,
        authorization,
        csrf,
        key,
        value,
        identifier,
        expected,
        request_id,
        sealed,
    ):
        return await _accept_execution(
            self,
            session,
            actor,
            authorization,
            csrf,
            key,
            value,
            identifier,
            expected,
            request_id,
            sealed,
        )


@dataclass(frozen=True, repr=False)
class SealedExecution:
    handle: StageHandle
    sealed_revision: int
    sealed_at: datetime


def verify_stage_binding(stage, handle, provider_kind):
    """完整header只比受控内存源/证明，不信SQL自报expected就接受。"""
    source = handle.evidence.prepared.source
    expected = dict(
        task_id=handle.task_id,
        plan_id=source.plan_id,
        source_revision=source.source_revision,
        payload_hash=source.payload_hash,
        validation_id=handle.evidence.validation_id,
        validated_head_revision=source.head_revision,
        validation_hash=handle.evidence.prepared.validation_hash,
        actor_id=handle.evidence.current.actor_id,
        subject_id=handle.evidence.current.subject_id,
        auth_version=handle.auth_version,
        authorization_fingerprint=handle.authorization_fingerprint,
        intent_hash=handle.evidence.prepared.request_payload_hash,
        idempotency_key_hash=handle.key_hash,
        provider_kind=provider_kind,
        provider_fingerprint=handle.evidence.fingerprint,
        manifest_hash=handle.spec.blueprint.manifest_hash,
        task_chunk_hash=handle.spec.blueprint.task_chunk_hash,
        graph_hash=handle.evidence.prepared.dag.graph_hash,
        plan_input_hash=handle.evidence.prepared.dag.plan_input_hash,
        allocation_input_hash=handle.evidence.prepared.dag.allocation_input_hash,
        **{
            key: value
            for key, value in handle.spec.blueprint.__dict__.items()
            if key.startswith("expected_")
        },
    )
    if any(stage.get(key) != value for key, value in expected.items()):
        stale()


async def _stage_seal_context(
    implementation, session, actor, authorization, csrf, handle, *, write=False
):
    """seal只锁prep；不在持prep时等待Task或child，避免反序。"""
    current = await implementation._authorized(session, actor, authorization, csrf, handle.evidence)
    version, fingerprint = await authorization_snapshot(session, current)
    if (version, fingerprint) != (handle.auth_version, handle.authorization_fingerprint):
        stale()
    head = await LaunchStore(implementation.tokens).row(
        session, current, handle.evidence.prepared.source.plan_id, unlocked=True
    )
    if (
        head["state"] != "VALIDATED"
        or head["revision"] != handle.evidence.prepared.validated_head_revision
    ):
        stale()
    stage = (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_launch_execution_preparation WHERE tenant_id=:tenant "
                    "AND id=:id AND task_id=:task " + ("FOR UPDATE" if write else "FOR SHARE")
                ),
                {"tenant": current.tenant_id, "id": handle.id, "task": handle.task_id},
            )
        )
        .mappings()
        .first()
    )
    if stage is None:
        stale()
    verify_stage_binding(stage, handle, implementation.provider.kind)
    expiry = stage["expires_at"]
    expiry = expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry.astimezone(UTC)
    if await database_now(session) >= expiry:
        stale()
    return current, stage


async def _seal_execution(implementation, session_factory, actor, authorization, csrf, handle):
    """真实持久全量核验；每批短事务，编码/散列在关闭该批事务后进行。"""
    if not isinstance(handle, StageHandle):
        corrupt()
    params = {"tenant": handle.evidence.current.tenant_id, "id": handle.id, "task": handle.task_id}
    proof = handle.spec.blueprint
    async with session_factory() as session, session.begin():
        _, stage = await _stage_seal_context(
            implementation, session, actor, authorization, csrf, handle, write=True
        )
        if stage["state"] == "BUILDING":
            if any(
                stage["persisted_" + key.removeprefix("expected_")] != value
                for key, value in proof.__dict__.items()
                if key.startswith("expected_")
            ):
                stale()
            await session.execute(
                text(
                    "UPDATE orbit_launch_execution_preparation SET state='SEALING',"
                    "mutation_revision=mutation_revision+1,updated_at=UTC_TIMESTAMP(3) WHERE "
                    "tenant_id=:tenant AND id=:id"
                ),
                params,
            )
        elif stage["state"] not in {"SEALING", "SEALED"}:
            stale()
    byte_digest, total_bytes, byte_count = hashlib.sha256(), 0, 0
    # 最多16个64KiB块每批；字节块单块SQL上限1MiB，读取也按协议实际64KiB验证。
    while byte_count < proof.expected_byte_chunks:
        async with session_factory() as session, session.begin():
            _, stage = await _stage_seal_context(
                implementation, session, actor, authorization, csrf, handle
            )
            if stage["state"] not in {"SEALING", "SEALED"}:
                stale()
            packets = list(
                (
                    await session.execute(
                        text(
                            "SELECT ordinal,payload,byte_length,chunk_hash FROM "
                            "orbit_launch_execution_byte_chunk WHERE tenant_id=:tenant AND "
                            "preparation_id=:id "
                            "AND ordinal>=:after ORDER BY ordinal LIMIT 16"
                        ),
                        params | {"after": byte_count},
                    )
                ).mappings()
            )
        if not packets:
            corrupt()
        for packet in packets:
            payload = bytes(packet["payload"])
            if (
                packet["ordinal"] != byte_count
                or not 1 <= len(payload) <= 65536
                or packet["byte_length"] != len(payload)
                or hashlib.sha256(payload).hexdigest() != packet["chunk_hash"]
            ):
                corrupt()
            byte_digest.update(payload)
            total_bytes += len(payload)
            byte_count += 1
    if (
        byte_count != proof.expected_byte_chunks
        or total_bytes != proof.expected_bytes
        or byte_digest.hexdigest() != proof.manifest_hash
    ):
        corrupt()
    graph = GraphDigest(
        handle.evidence.prepared.dag.schema_version,
        handle.evidence.prepared.source.source_revision,
        handle.evidence.prepared.dag.plan_input_hash,
        handle.evidence.prepared.dag.allocation_input_hash,
    )
    observed_nodes, observed_edges = 0, 0
    observation_hash = hashlib.sha256(handle.evidence.prepared.observations_json).hexdigest()
    for chunk in handle.spec.chunks:
        start = chunk.ordinal * CHUNK_SIZE
        async with session_factory() as session, session.begin():
            _, stage = await _stage_seal_context(
                implementation, session, actor, authorization, csrf, handle
            )
            if stage["state"] not in {"SEALING", "SEALED"}:
                stale()
            nodes = list(
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_task_node WHERE tenant_id=:tenant AND "
                            "task_id=:task "
                            "AND ordinal>=:start AND ordinal<:end ORDER BY ordinal"
                        ),
                        params | {"start": start, "end": start + CHUNK_SIZE},
                    )
                ).mappings()
            )
            commands = list(
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_launch_execution_command WHERE tenant_id=:tenant "
                            "AND task_id=:task AND ordinal>=:start AND ordinal<:end ORDER BY "
                            "ordinal"
                        ),
                        params | {"start": start, "end": start + CHUNK_SIZE},
                    )
                ).mappings()
            )
            chunk_row = (
                (
                    await session.execute(
                        text(
                            "SELECT expected_count,expected_hash,persisted FROM orbit_task_chunk "
                            "WHERE tenant_id=:tenant AND task_id=:task AND ordinal=:ordinal"
                        ),
                        params | {"ordinal": chunk.ordinal},
                    )
                )
                .mappings()
                .first()
            )
            ids = [row["id"] for row in nodes]
            edges = (
                (
                    await session.execute(
                        text(
                            "SELECT child_id,parent_id FROM orbit_task_edge WHERE "
                            "tenant_id=:tenant "
                            "AND task_id=:task AND child_id IN :ids"
                        ).bindparams(bindparam("ids", expanding=True)),
                        params | {"ids": ids},
                    )
                ).all()
                if ids
                else []
            )
        if (
            len(nodes) != chunk.count
            or len(commands) != chunk.count
            or chunk_row is None
            or (chunk_row["expected_count"], chunk_row["expected_hash"], chunk_row["persisted"])
            != (chunk.count, chunk.node_sha256, 1)
        ):
            corrupt()
        persisted_originals = [_decode(row["initial_json"]) for row in nodes]
        if hashlib.sha256(canonical(persisted_originals).encode()).hexdigest() != chunk.node_sha256:
            corrupt()
        originals, actual_commands = [], []
        for index, (node, command, original) in enumerate(
            zip(nodes, commands, persisted_originals, strict=True)
        ):
            identifier = node_id(handle.task_id, original["node_key"])
            if (
                node["id"],
                node["ordinal"],
                node["node_key"],
                node["kind"],
                node["state"],
                node["attempt"],
                node["external_id"],
                node["error_code"],
                node["error_message"],
                node["retryable"],
                node["configuration_state"],
                node["delivery_state"],
            ) != (
                identifier,
                start + index,
                original["node_key"],
                original["kind"],
                "QUEUED",
                0,
                None,
                None,
                None,
                0,
                "UNVERIFIED",
                "UNKNOWN",
            ):
                corrupt()
            configuration = _decode(command["resolved_configuration_json"])
            if (
                command["preparation_id"],
                command["node_id"],
                command["ordinal"],
                command["node_key"],
                command["kind"],
                command["purpose"],
                command["account_id"],
                command["target_key"],
                command["state"],
                command["attempt"],
                command["observation_binding_hash"],
            ) != (
                handle.id,
                identifier,
                start + index,
                original["node_key"],
                original["kind"],
                original["purpose"],
                original["account_id"],
                original["target_key"],
                "QUEUED",
                0,
                observation_hash,
            ):
                corrupt()
            if (
                hashlib.sha256(canonical(configuration).encode()).hexdigest()
                != command["resolved_configuration_hash"]
            ):
                corrupt()
            originals.append(original)
            actual_commands.append(
                original
                | {
                    "resolved_configuration": configuration,
                    "resolved_configuration_hash": command["resolved_configuration_hash"],
                }
            )
        if (
            hashlib.sha256(canonical(originals).encode()).hexdigest() != chunk.node_sha256
            or hashlib.sha256(canonical(actual_commands).encode()).hexdigest()
            != chunk.command_sha256
        ):
            corrupt()
        expected_edges = {
            (node_id(handle.task_id, row["node_key"]), node_id(handle.task_id, parent))
            for row in originals
            for parent in row["parent_keys"]
        }
        if set(edges) != expected_edges or len(edges) != len(expected_edges):
            corrupt()
        graph.append(originals)
        observed_nodes += len(nodes)
        observed_edges += len(edges)
    if (
        observed_nodes != proof.expected_node_count
        or observed_edges != proof.expected_edge_count
        or graph.hexdigest() != handle.evidence.prepared.dag.graph_hash
    ):
        corrupt()
    # 按实际表计数堵住额外尾节点/边/命令/块，不只数已声明的包。
    async with session_factory() as session, session.begin():
        _, stage = await _stage_seal_context(
            implementation, session, actor, authorization, csrf, handle, write=True
        )
        if stage["state"] not in {"SEALING", "SEALED"}:
            stale()
        for table, expected in (
            ("orbit_task_node", proof.expected_node_count),
            ("orbit_task_edge", proof.expected_edge_count),
            ("orbit_task_chunk", proof.expected_node_chunks),
            ("orbit_launch_execution_command", proof.expected_command_count),
        ):
            count = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM "
                        + table
                        + " WHERE tenant_id=:tenant AND task_id=:task"
                    ),
                    params,
                )
            ).scalar_one()
            if count != expected:
                corrupt()
        count = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM orbit_launch_execution_byte_chunk WHERE "
                    "tenant_id=:tenant AND preparation_id=:id"
                ),
                params,
            )
        ).scalar_one()
        if count != proof.expected_byte_chunks:
            corrupt()
        now = await database_now(session)
        if stage["state"] == "SEALED":
            return SealedExecution(
                handle, stage["sealed_revision"], stage["sealed_at"].replace(tzinfo=UTC)
            )
        revision = stage["mutation_revision"] + 1
        await session.execute(
            text(
                "UPDATE orbit_launch_execution_preparation SET state='SEALED',"
                "sealed_revision=:revision,mutation_revision=:revision,sealed_at=:now,updated_a"
                "t=:now "
                "WHERE tenant_id=:tenant AND id=:id"
            ),
            params | {"revision": revision, "now": now},
        )
        return SealedExecution(handle, revision, now)


OPERATION = "plan.execute"


def execute_request(value, identifier, expected):
    identifier = uuid_field(identifier, ("id",))
    if type(expected) is not int or not 1 <= expected < 9007199254740991:
        raise OrbitError(400, "REVISION_REQUIRED", "须提供有效If-Match版本")
    request = parse_plan_action(canonical(value).encode(), "execute")
    return identifier, request


def intent_for(current, identifier, source_revision, expected, request):
    return access.digest(
        dict(
            tenant_id=current.tenant_id,
            plan_id=identifier,
            plan_revision=source_revision,
            head_revision=expected,
            request=request,
        )
    )


def verify_accepted_intent(current, accepted, identifier, source_revision, expected, request):
    """同配置源只有原完整执行意图可重放；不拿SUBMITTED当前头替代原受理CAS。"""
    if (
        accepted["validation_hash"] != request["hash"]
        or accepted["validated_head_revision"] != expected
        or accepted["intent_hash"]
        != intent_for(current, identifier, source_revision, expected, request)
    ):
        raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一配置源已受理的完整执行意图不得改变")


async def _task_response(implementation, session, current, task):
    # 仅已授权execute上下文；不调用需要tasks.read的公共detail/auth入口。
    version, _ = await authorization_snapshot(session, current)
    fingerprint = access.digest(
        [
            current.actor_id,
            current.tenant_id,
            current.subject_id,
            current.data_role,
            current.team_id,
            sorted(await access.teams(session, current)),
            version,
        ]
    )
    store = TaskStore(implementation.tokens)
    nodes, _ = await store.nodes(
        session,
        current,
        task,
        {"q": "", "page_size": 200, "status": None, "operator_user_id": None},
    )
    if not nodes or task["node_count"] < 1:
        corrupt()
    return store.public(task, fingerprint, nodes, len(nodes) - 1)


async def _publish_permission_for_task(session, current, task, request):
    source = (
        (
            await session.execute(
                text(
                    "SELECT payload_json,payload_hash FROM orbit_launch_plan_version "
                    "WHERE tenant_id=:tenant AND plan_id=:plan AND revision=:source FOR SHARE"
                ),
                {
                    "tenant": current.tenant_id,
                    "plan": task["source_plan_id"],
                    "source": task["source_revision"],
                },
            )
        )
        .mappings()
        .first()
    )
    if source is None or source["payload_hash"] != task["source_hash"]:
        corrupt()
    payload = _decode(source["payload_json"])
    if access.digest(payload) != task["source_hash"]:
        corrupt()
    if payload.get("activate_after_create") is True:
        if await access.context(session, current.actor_id, "launch.publish") != current:
            stale()
        if request["activate_ack"] is not True:
            raise OrbitError(422, "FIELD_VALIDATION_FAILED", "启用发布须明确确认", "/activate_ack")


async def _known_execution_replay(session, current, key, identifier, expected, request):
    # 幂等结果合法写方只INSERT不改；先无锁观察，成功回放不反向等launch/task clock。
    old = (
        (
            await session.execute(
                text(
                    "SELECT input_hash,result_json FROM orbit_launch_idempotency "
                    "WHERE tenant_id=:tenant AND actor_id=:actor AND operation=:operation AND "
                    "key_hash=:key"
                ),
                {
                    "tenant": current.tenant_id,
                    "actor": current.actor_id,
                    "operation": OPERATION,
                    "key": hashlib.sha256(key.encode()).hexdigest(),
                },
            )
        )
        .mappings()
        .first()
    )
    if old is None:
        return None
    result = _decode(old["result_json"])
    if not isinstance(result, dict) or not isinstance(result.get("id"), str):
        corrupt()
    task = await task_access.task(session, current, result["id"])
    if task["source_plan_id"] != identifier or old["input_hash"] != intent_for(
        current, identifier, task["source_revision"], expected, request
    ):
        raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不得改变完整execute意图")
    if result.get("ownership") != {key: task[key] for key in ("owner_user_id", "owner_team_id")}:
        corrupt()
    await _publish_permission_for_task(session, current, task, request)
    return result


async def _accept_execution(
    implementation,
    session,
    actor,
    authorization,
    csrf,
    key,
    value,
    identifier,
    expected,
    request_id,
    sealed,
):
    """全部完整真实Task+Node+command已密封，才原子转可读并返回原Task供HTTP202。

    不做任何平台写；没有AuthorityProvider或完整引用钩子不能落受理。
    """
    if not session.in_transaction():
        raise ValueError("execute accept必须处于调用者外层原子事务")
    identifier, request = execute_request(value, identifier, expected)
    request_id = uuid_field(request_id, ("request_id",))
    if not isinstance(key, str) or not re.fullmatch(r"[ -~]{16,128}", key):
        raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "须提供原幂等键")
    current = await access.context(session, actor, "launch.execute")
    _csrf(implementation.tokens, current, authorization, csrf)
    plans = LaunchStore(implementation.tokens)
    await plans.row(session, current, identifier, unlocked=True)
    replayed = await _known_execution_replay(session, current, key, identifier, expected, request)
    if replayed is not None:
        return replayed
    if isinstance(sealed, ExecutionPreparation):
        flow = sealed
        if (
            flow.current != current
            or flow.plan_id != identifier
            or flow.expected != expected
            or flow.request_json != canonical(request).encode()
        ):
            stale()
        if flow.existing_task_id is not None:
            await access.clock(session, current, write=True)
            head = await plans.row(session, current, identifier, write=True)
            replayed = await _known_execution_replay(
                session, current, key, identifier, expected, request
            )
            if replayed is not None:
                return replayed
            source = await capture_plan_source(session, current, head)
            accepted = (
                (
                    await session.execute(
                        text(
                            "SELECT task_id,validation_hash,intent_hash,validated_head_revision "
                            "FROM "
                            "orbit_launch_execution_acceptance WHERE "
                            "tenant_id=:tenant AND plan_id=:plan AND source_revision=:source"
                        ),
                        {
                            "tenant": current.tenant_id,
                            "plan": identifier,
                            "source": source.source_revision,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if accepted is None or accepted["task_id"] != flow.existing_task_id:
                stale()
            verify_accepted_intent(
                current, accepted, identifier, source.source_revision, expected, request
            )
            task = await task_access.task(session, current, accepted["task_id"])
            await _publish_permission_for_task(session, current, task, request)
            result = await _task_response(implementation, session, current, task)
            await access.remember(
                session,
                current,
                OPERATION,
                key,
                intent_for(current, identifier, source.source_revision, expected, request),
                result,
            )
            return result
        if flow.provider is not implementation.provider:
            stale()
        sealed = flow.sealed
    await require_execution_provider(session, implementation.provider)
    if not isinstance(sealed, SealedExecution):
        corrupt()
    handle = sealed.handle
    evidence = handle.evidence
    prepared = evidence.prepared
    if (
        prepared.source.plan_id != identifier
        or prepared.validated_head_revision != expected
        or json.loads(prepared.request_json) != request
        or handle.key_hash != hashlib.sha256(key.encode()).hexdigest()
    ):
        stale()
    if await implementation._authorized(session, actor, authorization, csrf, evidence) != current:
        stale()
    if (
        await implementation.provider.revalidate(session, current, prepared.source, evidence)
        is not evidence
    ):
        stale()
    await access.clock(session, current, write=True)
    head = await plans.row(session, current, identifier, write=True)
    replayed = await _known_execution_replay(session, current, key, identifier, expected, request)
    if replayed is not None:
        return replayed
    # 不同键同source不得创建第二Task；现有受理仍须当前冻结Task范围。
    origin = await capture_plan_source(session, current, head)
    accepted = (
        (
            await session.execute(
                text(
                    "SELECT task_id,validation_hash,intent_hash,validated_head_revision FROM "
                    "orbit_launch_execution_acceptance "
                    "WHERE tenant_id=:tenant AND plan_id=:plan AND source_revision=:source"
                ),
                {"tenant": current.tenant_id, "plan": identifier, "source": origin.source_revision},
            )
        )
        .mappings()
        .first()
    )
    if accepted is not None:
        verify_accepted_intent(
            current, accepted, identifier, origin.source_revision, expected, request
        )
        task = await task_access.task(session, current, accepted["task_id"])
        await _publish_permission_for_task(session, current, task, request)
        result = await _task_response(implementation, session, current, task)
        await access.remember(
            session,
            current,
            OPERATION,
            key,
            intent_for(current, identifier, origin.source_revision, expected, request),
            result,
        )
        return result
    if head["state"] != "VALIDATED" or head["revision"] != expected or origin != prepared.source:
        raise OrbitError(409, "REVISION_CONFLICT", "计划预检头或配置源已变化")
    validation = (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_launch_validation WHERE tenant_id=:tenant "
                    "AND id=:validation FOR SHARE"
                ),
                {"tenant": current.tenant_id, "validation": evidence.validation_id},
            )
        )
        .mappings()
        .first()
    )
    if validation is None or (
        validation["plan_id"],
        validation["source_revision"],
        validation["payload_hash"],
        validation["validated_head_revision"],
        validation["validation_hash"],
    ) != (
        identifier,
        origin.source_revision,
        origin.payload_hash,
        expected,
        prepared.validation_hash,
    ):
        stale()
    arguments = json.loads(prepared.inputs_json)
    adapter = ValidationEvidence(
        evidence.fingerprint,
        arguments["scope_version"],
        prepared.dag.total_dag_node_count,
        (),
        (),
        prepared.inputs_json,
    )
    await LaunchValidationStore(implementation.tokens)._lock_references(
        session,
        current,
        origin,
        {
            "allocation_id": arguments["allocation"]["id"],
            "name_reservation_id": arguments["name_reservation"]["id"],
        },
        adapter,
    )
    now = await database_now(session)
    expiry = validation["expires_at"]
    expiry = expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry.astimezone(UTC)
    if (
        now >= expiry
        or expiry != prepared.validation_expires_at
        or validation["naming_date"] != (now + timedelta(hours=8)).date()
    ):
        stale()
    version, fingerprint = await authorization_snapshot(session, current)
    if (version, fingerprint) != (handle.auth_version, handle.authorization_fingerprint):
        stale()
    await task_access.clock(session, current, write=True)
    params = {"tenant": current.tenant_id, "task": handle.task_id, "id": handle.id}
    task = (
        (
            await session.execute(
                text("SELECT * FROM orbit_task WHERE tenant_id=:tenant AND id=:task FOR UPDATE"),
                params,
            )
        )
        .mappings()
        .first()
    )
    stage = (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_launch_execution_preparation WHERE tenant_id=:tenant "
                    "AND id=:id AND task_id=:task FOR UPDATE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    if task is None or stage is None:
        stale()
    verify_stage_binding(stage, handle, implementation.provider.kind)
    proof = handle.spec.blueprint
    if (
        stage["state"] != "SEALED"
        or stage["sealed_revision"] != sealed.sealed_revision
        or stage["mutation_revision"] != sealed.sealed_revision
    ):
        stale()
    actual_sealed = stage["sealed_at"]
    actual_sealed = (
        actual_sealed.replace(tzinfo=UTC)
        if actual_sealed.tzinfo is None
        else actual_sealed.astimezone(UTC)
    )
    if actual_sealed != sealed.sealed_at:
        stale()
    stage_expiry = stage["expires_at"]
    stage_expiry = (
        stage_expiry.replace(tzinfo=UTC)
        if stage_expiry.tzinfo is None
        else stage_expiry.astimezone(UTC)
    )
    if now >= stage_expiry or (
        task["manifest_phase"],
        task["node_count"],
        task["edge_count"],
        task["expected_node_count"],
        task["manifest_hash"],
        task["graph_hash"],
        task["source_hash"],
    ) != (
        "BUILDING",
        proof.expected_node_count,
        proof.expected_edge_count,
        proof.expected_node_count,
        proof.task_chunk_hash,
        prepared.dag.graph_hash,
        origin.payload_hash,
    ):
        stale()
    # 引用钩子必须实际写完整集合，空实现不能由DTO verified冒充成功。
    await implementation.provider.publish_references(
        session, current, evidence, handle.task_id, request_id
    )
    used = set(json.loads(prepared.materials_json))
    refs = list(
        (
            await session.execute(
                text(
                    "SELECT asset_id,id,active FROM orbit_material_reference WHERE "
                    "tenant_id=:tenant "
                    "AND kind='EXECUTION' AND resource_id=:task ORDER BY asset_id LIMIT 501 "
                    "FOR SHARE"
                ),
                params,
            )
        ).mappings()
    )
    if (
        len(refs) != len(used)
        or {row["asset_id"] for row in refs} != used
        or any(row["active"] != 1 for row in refs)
    ):
        corrupt()
    # 引用登记等真实DB工作结束后再次取UTC，不把先前时刻冒充最终受理边界。
    now = await database_now(session)
    if (
        now >= expiry
        or now >= stage_expiry
        or validation["naming_date"] != (now + timedelta(hours=8)).date()
    ):
        stale()
    revision = expected + 1
    changed = await session.execute(
        text(
            "UPDATE orbit_launch_plan SET state='SUBMITTED',revision=:revision,updated_at=:now "
            "WHERE tenant_id=:tenant AND id=:plan AND revision=:expected"
        ),
        params
        | {
            "plan": identifier,
            "revision": revision,
            "expected": expected,
            "now": now.replace(tzinfo=None),
        },
    )
    if changed.rowcount != 1:
        stale()
    await insert_values(
        session,
        "orbit_launch_execution_acceptance",
        dict(
            tenant_id=current.tenant_id,
            plan_id=identifier,
            source_revision=origin.source_revision,
            task_id=handle.task_id,
            preparation_id=handle.id,
            validation_id=evidence.validation_id,
            validated_head_revision=expected,
            submitted_head_revision=revision,
            validation_hash=prepared.validation_hash,
            manifest_hash=prepared.manifest_hash,
            intent_hash=prepared.request_payload_hash,
            accepted_request_id=request_id,
            accepted_by=actor,
            accepted_at=now,
        ),
    )
    await session.execute(
        text(
            "UPDATE orbit_launch_execution_preparation SET "
            "state='ACCEPTED',mutation_revision=mutation_revision+1,"
            "accepted_head_revision=:revision,accepted_request_id=:request,accepted_at=:now,upd"
            "ated_at=:now "
            "WHERE tenant_id=:tenant AND id=:id"
        ),
        params | {"revision": revision, "request": request_id, "now": now.replace(tzinfo=None)},
    )
    event_id, audit_id = str(uuid4()), str(uuid4())
    await insert_values(
        session,
        "orbit_task_event",
        dict(
            tenant_id=current.tenant_id,
            task_id=handle.task_id,
            event_id=event_id,
            sequence=1,
            task_revision=1,
            node_id=None,
            state="QUEUED",
            occurred_at=now,
            request_id=request_id,
        ),
    )
    await session.execute(
        text(
            "UPDATE orbit_task SET manifest_phase='COMPLETE',accepted_request_id=:request,"
            "created_at=:now,updated_at=:now,latest_event_id=:event,latest_sequence=1 WHERE "
            "tenant_id=:tenant AND id=:task"
        ),
        params | {"request": request_id, "now": now.replace(tzinfo=None), "event": event_id},
    )
    await session.execute(
        text("UPDATE orbit_task_clock SET revision=revision+1 WHERE tenant_id=:tenant"), params
    )
    await insert_values(
        session,
        "orbit_task_audit",
        dict(
            id=audit_id,
            tenant_id=current.tenant_id,
            task_id=handle.task_id,
            actor_id=actor,
            request_id=request_id,
            action="EXECUTE_ACCEPTED",
            created_at=now,
        ),
    )
    await insert_values(
        session,
        "orbit_task_outbox",
        dict(
            audit_id=audit_id, tenant_id=current.tenant_id, task_id=handle.task_id, created_at=now
        ),
    )
    await access.event(
        session,
        current,
        "PLAN",
        identifier,
        revision,
        "plan.execute.accepted",
        request_id,
        {
            "task_id": handle.task_id,
            "source_revision": origin.source_revision,
            "manifest_hash": prepared.manifest_hash,
        },
    )
    task = await task_access.task(session, current, handle.task_id)
    result = await _task_response(implementation, session, current, task)
    await access.remember(session, current, OPERATION, key, prepared.request_payload_hash, result)
    return result


@dataclass(frozen=True, repr=False)
class ExecutionInput:
    current: BusinessContext
    source: PlanSource
    validation_id: str
    validation: FrozenValidation
    request_json: bytes


@dataclass(frozen=True, repr=False)
class ExecutionPreparation:
    current: BusinessContext
    plan_id: str
    expected: int
    request_json: bytes
    provider: ExecutionAuthorityProvider | None
    sealed: SealedExecution | None = None
    existing_task_id: str | None = None


def frozen_validation_row(row):
    """038持久十字段严格重建，不从客户端valid或任意version字符串得权威。"""
    try:
        summary = _decode(row["summary_json"])
        totals = tuple((item["currency"], item["amount"]) for item in summary["budget_totals"])
        started, expires = row["validated_at"], row["expires_at"]
        started = started.replace(tzinfo=UTC) if started.tzinfo is None else started.astimezone(UTC)
        expires = expires.replace(tzinfo=UTC) if expires.tzinfo is None else expires.astimezone(UTC)
        frozen = FrozenValidation(
            row["validation_hash"],
            row["source_revision"],
            Counts(*(summary[field] for field in ("campaign_count", "adset_count", "ad_count"))),
            totals,
            row["scope_version"],
            summary["total_dag_node_count"],
            started,
            expires,
            row["naming_date"],
        )
        if validation_response(frozen) != summary or expires - started != timedelta(minutes=15):
            corrupt()
        return frozen
    except (TypeError, ValueError, KeyError, AttributeError, OrbitError):
        corrupt()


async def _prepare_execution(
    implementation,
    session_factory,
    actor,
    authorization,
    csrf,
    key,
    value,
    identifier,
    expected,
    request_id,
):
    """原HTTP之前的内部capture→完整持久→seal；没有202/Task成功回执。"""
    identifier, request = execute_request(value, identifier, expected)
    request_id = uuid_field(request_id, ("request_id",))
    if not isinstance(key, str) or not re.fullmatch(r"[ -~]{16,128}", key):
        raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "须提供原幂等键")
    request_bytes = canonical(request).encode()
    async with session_factory() as session, session.begin():
        current = await access.context(session, actor, "launch.execute")
        _csrf(implementation.tokens, current, authorization, csrf)
        plans = LaunchStore(implementation.tokens)
        await plans.row(session, current, identifier, unlocked=True)
        replayed = await _known_execution_replay(
            session, current, key, identifier, expected, request
        )
        if replayed is not None:
            return ExecutionPreparation(
                current,
                identifier,
                expected,
                request_bytes,
                implementation.provider,
                existing_task_id=replayed["id"],
            )
        await access.clock(session, current, write=True)
        head = await plans.row(session, current, identifier, write=True)
        source = await capture_plan_source(session, current, head)
        accepted = (
            (
                await session.execute(
                    text(
                        "SELECT task_id,validation_hash,intent_hash,validated_head_revision FROM "
                        "orbit_launch_execution_acceptance "
                        "WHERE tenant_id=:tenant AND plan_id=:plan AND source_revision=:source"
                    ),
                    {
                        "tenant": current.tenant_id,
                        "plan": identifier,
                        "source": source.source_revision,
                    },
                )
            )
            .mappings()
            .first()
        )
        if accepted is not None:
            verify_accepted_intent(
                current, accepted, identifier, source.source_revision, expected, request
            )
            task = await task_access.task(session, current, accepted["task_id"])
            await _publish_permission_for_task(session, current, task, request)
            return ExecutionPreparation(
                current,
                identifier,
                expected,
                request_bytes,
                implementation.provider,
                existing_task_id=task["id"],
            )
        provider = await require_execution_provider(session, implementation.provider)
        if head["state"] != "VALIDATED" or head["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "计划预检头已变化")
        row = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_launch_validation WHERE tenant_id=:tenant "
                        "AND plan_id=:plan AND validated_head_revision=:head FOR SHARE"
                    ),
                    {"tenant": current.tenant_id, "plan": identifier, "head": expected},
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["source_revision"] != source.source_revision
            or row["payload_hash"] != source.payload_hash
            or row["validation_hash"] != request["hash"]
        ):
            stale()
        frozen = frozen_validation_row(row)
        if not is_current(frozen, await database_now(session)):
            stale()
        captured = ExecutionInput(current, source, row["id"], frozen, request_bytes)
    # 外部只读capture/完整编译全部在关闭自有短事务后；没有数据库session传入。
    evidence = await provider.capture(captured)
    if (
        not isinstance(evidence, ExecutionEvidence)
        or evidence.current != current
        or evidence.validation_id != captured.validation_id
    ):
        corrupt()
    prepared = evidence.prepared
    if (
        not isinstance(prepared, PreparedExecution)
        or prepared.source != captured.source
        or prepared.request_json != request_bytes
        or prepared.validation_hash != frozen.hash
        or prepared.validation_expires_at != frozen.expires_at
    ):
        stale()
    spec = execution_build_spec(prepared)
    handle = None
    try:
        async with session_factory() as session, session.begin():
            handle = await implementation.stage_begin(
                session, actor, authorization, csrf, key, request_id, evidence, spec
            )
        # 每一包先在事务外产生，再独立短事务写；未完整不会公开任何Task。
        for packet in iter_byte_packets(prepared):
            async with session_factory() as session, session.begin():
                await implementation.append_bytes(
                    session, actor, authorization, csrf, handle, packet
                )
        for packet in iter_node_packets(prepared):
            async with session_factory() as session, session.begin():
                await implementation.append_nodes(
                    session, actor, authorization, csrf, handle, packet
                )
        sealed = await implementation.seal(session_factory, actor, authorization, csrf, handle)
        return ExecutionPreparation(
            current, identifier, expected, request_bytes, provider, sealed=sealed
        )
    except BaseException as original:
        if handle is not None:
            # 即时撤权也允许同服务器原handle做负向ABORT，不赋予发布/历史读取权限。
            # 清理失败不能把异常冒作成功；到期监督仍须扫描残留私有头。
            try:
                async with session_factory() as session, session.begin():
                    await _abort_stage(session, handle)
            except Exception:
                # 原失败必须保留；残留头由DB到期扫描处理，不泄漏清理异常正文。
                original.add_note("私有准备负向清理尚未确认，须由到期监督继续处理")
        raise


async def _abort_stage(session, handle):
    if not session.in_transaction() or not isinstance(handle, StageHandle):
        corrupt()
    params = {"tenant": handle.evidence.current.tenant_id, "task": handle.task_id, "id": handle.id}
    task = (
        await session.execute(
            text("SELECT id FROM orbit_task WHERE tenant_id=:tenant AND id=:task FOR UPDATE"),
            params,
        )
    ).first()
    stage = (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_launch_execution_preparation WHERE tenant_id=:tenant "
                    "AND id=:id AND task_id=:task FOR UPDATE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    if task is None or stage is None:
        return False
    # 内部私有handle必须精确绑定原意图/actor；不能跨源删除，更不能取消已受理Task。
    verify_stage_binding(stage, handle, stage["provider_kind"])
    if stage["state"] in {"ACCEPTED", "ABORTED"}:
        return False
    await session.execute(
        text(
            "UPDATE orbit_launch_execution_preparation SET state='ABORTED',"
            "mutation_revision=mutation_revision+1,updated_at=UTC_TIMESTAMP(3) "
            "WHERE tenant_id=:tenant AND id=:id"
        ),
        params,
    )
    return True


async def _cleanup_stage(session, handle, *, limit=500):
    """每次一个有界批次；只有服务器原handle+ABORTED，绝不清ACCEPTED历史。"""
    if (
        not session.in_transaction()
        or not isinstance(handle, StageHandle)
        or type(limit) is not int
        or not 1 <= limit <= 500
    ):
        corrupt()
    params = {
        "tenant": handle.evidence.current.tenant_id,
        "task": handle.task_id,
        "id": handle.id,
        "limit": limit,
    }
    task = (
        await session.execute(
            text("SELECT id FROM orbit_task WHERE tenant_id=:tenant AND id=:task FOR UPDATE"),
            params,
        )
    ).first()
    stage = (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_launch_execution_preparation WHERE tenant_id=:tenant "
                    "AND id=:id AND task_id=:task FOR UPDATE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    if task is None and stage is None:
        return True
    if task is None or stage is None or stage["state"] != "ABORTED":
        stale()
    verify_stage_binding(stage, handle, stage["provider_kind"])
    return await _delete_aborted_batch(session, params)


async def _delete_aborted_batch(session, params):
    """调用者已按Task→prep锁定并证明ABORTED；每次最多一表limit条。"""
    for table, column in (
        ("orbit_launch_execution_command", "task_id"),
        ("orbit_task_edge", "task_id"),
        ("orbit_task_node", "task_id"),
        ("orbit_task_chunk", "task_id"),
        ("orbit_launch_execution_byte_chunk", "preparation_id"),
    ):
        result = await session.execute(
            text(
                "DELETE FROM "
                + table
                + " WHERE tenant_id=:tenant AND "
                + column
                + ("=:id" if column == "preparation_id" else "=:task")
                + " LIMIT :limit"
            ),
            params,
        )
        if result.rowcount:
            return False
    # 触发器/FK仍保护任何异常历史引用；不绕过这些约束强删。
    await session.execute(
        text("DELETE FROM orbit_launch_execution_preparation WHERE tenant_id=:tenant AND id=:id"),
        params,
    )
    await session.execute(
        text("DELETE FROM orbit_task WHERE tenant_id=:tenant AND id=:task"), params
    )
    return True


async def _cleanup_expired(session, *, limit=500):
    """仅内部监督入口：真实DB到期、单个准备、单批删除，不接HTTP身份或prepared_id。

    无授权恢复/接管；合法构建者、接受者、此扫描均Task→prep，seal仅prep短锁。
    候选无锁读取允许竞争，随后当前锁读及精确state/expiry/revision CAS再判定。
    已ACCEPTED永不删除；正常负向ABORT可在expires前继续有界清理。
    """
    if not session.in_transaction() or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("到期清理须处于短事务且limit为1至500")
    now = await database_now(session)
    candidate = (
        (
            await session.execute(
                text(
                    "SELECT tenant_id,id,task_id FROM orbit_launch_execution_preparation "
                    "WHERE state='ABORTED' OR (state IN('BUILDING','SEALING','SEALED') "
                    "AND expires_at<=:now) ORDER BY expires_at,tenant_id,id LIMIT 1"
                ),
                {"now": now.replace(tzinfo=None)},
            )
        )
        .mappings()
        .first()
    )
    if candidate is None:
        return {"aborted": 0, "completed": False, "found": False}
    params = {
        "tenant": candidate["tenant_id"],
        "id": candidate["id"],
        "task": candidate["task_id"],
        "limit": limit,
    }
    task = (
        (
            await session.execute(
                text(
                    "SELECT manifest_phase FROM orbit_task "
                    "WHERE tenant_id=:tenant AND id=:task FOR UPDATE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    stage = (
        (
            await session.execute(
                text(
                    "SELECT state,expires_at,mutation_revision FROM "
                    "orbit_launch_execution_preparation WHERE tenant_id=:tenant "
                    "AND id=:id AND task_id=:task FOR UPDATE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    if stage is None:
        return {"aborted": 0, "completed": False, "found": False}
    if stage["state"] == "ACCEPTED":
        return {"aborted": 0, "completed": False, "found": False}
    if task is None or task["manifest_phase"] != "BUILDING":
        corrupt()
    aborted = 0
    if stage["state"] != "ABORTED":
        # 采候选后可能等待合法accept；因此锁齐后重新读实际DB时间与完整expiry。
        now = await database_now(session)
        expiry = stage["expires_at"]
        expiry = expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry.astimezone(UTC)
        if now < expiry:
            return {"aborted": 0, "completed": False, "found": False}
        changed = await session.execute(
            text(
                "UPDATE orbit_launch_execution_preparation SET state='ABORTED',"
                "mutation_revision=mutation_revision+1,updated_at=:now WHERE tenant_id=:tenant "
                "AND id=:id AND task_id=:task AND state=:state AND expires_at=:expiry "
                "AND expires_at<=:now AND mutation_revision=:revision"
            ),
            params
            | {
                "state": stage["state"],
                "expiry": expiry.replace(tzinfo=None),
                "revision": stage["mutation_revision"],
                "now": now.replace(tzinfo=None),
            },
        )
        if changed.rowcount != 1:
            stale()
        aborted = 1
    return {
        "aborted": aborted,
        "completed": await _delete_aborted_batch(session, params),
        "found": True,
    }
