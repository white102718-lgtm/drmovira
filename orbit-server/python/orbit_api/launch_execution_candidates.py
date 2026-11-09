"""完整执行清单的内部只读目录；非claim票据、无发送和生产authority默认实现。"""

import asyncio
import codecs
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import bindparam, text

from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_dag import MAX_PARENTS, DagNode
from orbit_api.launch_execution_lease_contract import MAX_REVISION, _integer, _utc, _uuid
from orbit_api.launch_execution_lease_store import _stored_binding
from orbit_api.task_contract import CHUNK_SIZE, KINDS, NODE_STATES, GraphDigest, node_id

VALUE_MEMORY_BUDGET = 16 * 1024 * 1024  # 内部读取保护，不是PRD字段长度约束。
BATCH_MEMORY_BUDGET = 16 * 1024 * 1024
ORIGINAL_FIELDS = frozenset(DagNode.__dataclass_fields__)


def unavailable(code="EXECUTION_DIRECTORY_UNVERIFIED"):
    raise OrbitError(503, code, "完整执行目录或明确执行授权尚未就绪")


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            unavailable()
        result[key] = value
    return result


class _JsonStream:
    """逐个顶层值/节点解码；UTF8可跨块，拒重复键/截断/多余尾值。"""

    def __init__(self, chunks):
        self.chunks = chunks.__aiter__()
        self.buffer = ""
        self.finished = False
        self.utf8 = codecs.getincrementaldecoder("utf-8")("strict")
        self.decoder = json.JSONDecoder(
            object_pairs_hook=_pairs, parse_constant=lambda _: unavailable()
        )

    async def fill(self):
        if self.finished:
            return False
        try:
            payload = await anext(self.chunks)
        except StopAsyncIteration:
            self.buffer += self.utf8.decode(b"", final=True)
            self.finished = True
            return False
        self.buffer += self.utf8.decode(payload)
        return True

    async def peek(self):
        while True:
            self.buffer = self.buffer.lstrip()
            if self.buffer:
                return self.buffer[0]
            if not await self.fill():
                unavailable()

    async def token(self, expected):
        if await self.peek() != expected:
            unavailable()
        self.buffer = self.buffer[1:]

    async def value(self):
        await self.peek()
        while True:
            if len(self.buffer.encode("utf-8")) > VALUE_MEMORY_BUDGET:
                unavailable("EXECUTION_DIRECTORY_MEMORY_BUDGET")
            try:
                value, end = self.decoder.raw_decode(self.buffer)
                # 数字/true等可能在块边界尚未结束，必须读取其后的分隔符。
                if end == len(self.buffer) and not self.finished:
                    await self.fill()
                    continue
                self.buffer = self.buffer[end:]
                # JSON字符串允许转义，但不接受孤立surrogate进入规范摘要。
                canonical(value).encode("utf-8")
                return value
            except json.JSONDecodeError:
                if not await self.fill():
                    unavailable()

    async def records(self):
        seen = set()  # 仅固定顶层字段，不保存全图节点键。
        await self.token("{")
        first = True
        while await self.peek() != "}":
            if not first:
                await self.token(",")
            key = await self.value()
            if not isinstance(key, str) or key in seen or len(seen) >= 32:
                unavailable()
            seen.add(key)
            await self.token(":")
            if key == "nodes":
                await self.token("[")
                first_node = True
                while await self.peek() != "]":
                    if not first_node:
                        await self.token(",")
                    yield "node", await self.value()
                    first_node = False
                await self.token("]")
            else:
                yield key, await self.value()
            first = False
        await self.token("}")
        while not self.finished:
            await self.fill()
        if self.buffer.strip() or "nodes" not in seen:
            unavailable()


@dataclass(frozen=True, repr=False)
class CandidateGrant:
    tenant_id: str
    task_id: str
    actor_id: int
    subject_id: str
    owner_user_id: str
    owner_team_id: str
    auth_revision: int
    source_revision: int
    source_hash: str
    manifest_hash: str
    intent_hash: str
    expires_at: datetime
    permission: str = "launch.execute"

    def __post_init__(self):
        for key in ("tenant_id", "task_id", "subject_id", "owner_user_id", "owner_team_id"):
            _uuid(getattr(self, key))
        for key in ("actor_id", "auth_revision", "source_revision"):
            _integer(getattr(self, key), MAX_REVISION)
        for value in (self.source_hash, self.manifest_hash, self.intent_hash):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise ValueError("需要完整规范摘要")
        _utc(self.expires_at)
        if self.permission != "launch.execute":
            raise ValueError("目录需要明确原执行权限，不接受tasks.read或维护权限替代")


class ExecutionCandidateAuthority(ABC):
    """可信执行目录来源；不从tasks.read、字符串TRUSTED或维护grant推断执行权限。"""

    @abstractmethod
    async def capture(self, task_id) -> CandidateGrant:
        """事务外捕获真实执行主体、范围与冻结来源；不执行平台写。"""

    @abstractmethod
    async def revalidate(self, session, grant) -> CandidateGrant:
        """先锁当前原动作及固定授权集合，最终复核不得扩锁到别的来源。"""


@dataclass(frozen=True, repr=False)
class ExecutionCandidate:
    node_id: str
    ordinal: int
    kind: str
    account_id: str
    target_key: str
    command_hash: str
    runtime_revision: int | None


@dataclass(frozen=True)
class CandidatePage:
    items: tuple[ExecutionCandidate, ...]
    next_ordinal: int | None
    raw_rows: int
    task_revision: int
    # 只读提示从返回时起即可过时，不携带可跨提交使用的授权票据。
    execution_authorized: bool = False


async def _rows(session, sql, params):
    return list((await session.execute(text(sql), params)).mappings())


async def _one(session, sql, params):
    rows = await _rows(session, sql, params)
    if len(rows) != 1:
        unavailable()
    return rows[0]


async def _bound_rows(session, sql, params, ids):
    return list(
        (
            await session.execute(
                text(sql).bindparams(bindparam("ids", expanding=True)), params | {"ids": ids}
            )
        ).mappings()
    )


class ExecutionCandidateDirectory:
    def __init__(self, authority=None, sessions_factory=None, *, clock=None):
        self.authority = authority
        self.sessions_factory = sessions_factory
        self.clock = clock or (lambda: datetime.now(UTC))

    async def _current(self, session, grant):
        current = await self.authority.revalidate(session, grant)
        now = self.clock()
        _utc(now)
        if not isinstance(current, CandidateGrant) or current != grant or now >= grant.expires_at:
            unavailable("EXECUTION_DIRECTORY_AUTHORITY_CHANGED")

    async def page(self, task_id, *, after_ordinal=None, limit=200):
        if not isinstance(self.authority, ExecutionCandidateAuthority):
            unavailable("EXECUTION_DIRECTORY_AUTHORITY_UNAVAILABLE")
        _uuid(task_id)
        if type(limit) is not int or limit not in {20, 50, 100, 200}:
            raise ValueError("候选页仅支持20/50/100/200")
        if after_ordinal is not None and (
            type(after_ordinal) is not int or not 0 <= after_ordinal < 100000
        ):
            raise ValueError("候选ordinal无效")
        async with asyncio.timeout(60):
            grant = await self.authority.capture(task_id)
            if (
                not isinstance(grant, CandidateGrant)
                or grant.task_id != task_id
                or self.clock() >= grant.expires_at
            ):
                unavailable()
            if self.sessions_factory is None:
                unavailable()
            async with self.sessions_factory() as session:
                if session.in_transaction():
                    raise ValueError("执行目录要求新事务")
                async with session.begin():
                    transaction = session.get_transaction()
                    await self._current(session, grant)
                    params = {"tenant": grant.tenant_id, "task": task_id}
                    await _one(
                        session,
                        "SELECT revision FROM orbit_task_clock WHERE tenant_id=:tenant FOR SHARE",
                        params,
                    )
                    task = await _one(
                        session,
                        "SELECT * FROM orbit_task WHERE tenant_id=:tenant AND id=:task FOR SHARE",
                        params,
                    )
                    prep = await _one(
                        session,
                        "SELECT * FROM orbit_launch_execution_preparation WHERE tenant_id=:tenant "
                        "AND task_id=:task FOR SHARE",
                        params,
                    )
                    accepted = await _one(
                        session,
                        "SELECT * FROM orbit_launch_execution_acceptance WHERE tenant_id=:tenant "
                        "AND task_id=:task",
                        params,
                    )
                    self._headers(task, prep, accepted, grant)
                    source = await _one(
                        session,
                        "SELECT payload_hash,CASE WHEN OCTET_LENGTH(payload_json)<=:memory "
                        "THEN payload_json ELSE NULL END AS payload_json "
                        "FROM orbit_launch_plan_version "
                        "WHERE tenant_id=:tenant AND plan_id=:plan AND revision=:source",
                        params
                        | {
                            "plan": task["source_plan_id"],
                            "source": task["source_revision"],
                            "memory": VALUE_MEMORY_BUDGET,
                        },
                    )
                    payload = _decode(source["payload_json"])
                    if (
                        not isinstance(payload, dict)
                        or source["payload_hash"] != grant.source_hash
                        or hashlib.sha256(canonical(payload).encode()).hexdigest()
                        != grant.source_hash
                    ):
                        unavailable()
                    await self._manifest(session, params, task, prep)
                    raw = await _rows(
                        session,
                        "SELECT id,ordinal,kind,state,attempt FROM orbit_task_node "
                        "WHERE tenant_id=:tenant AND task_id=:task "
                        "AND ordinal>:after ORDER BY ordinal LIMIT :limit",
                        params
                        | {"after": -1 if after_ordinal is None else after_ordinal, "limit": limit},
                    )
                    candidates = await self._candidates(session, params, raw, task, prep, grant)
                    await self._current(session, grant)
                    sql_now = await _one(session, "SELECT UTC_TIMESTAMP(6) AS now", {})
                    now = sql_now["now"].replace(tzinfo=UTC)
                    if now >= grant.expires_at or session.get_transaction() is not transaction:
                        unavailable()
                    next_ordinal = (
                        raw[-1]["ordinal"]
                        if raw and raw[-1]["ordinal"] < task["node_count"] - 1
                        else None
                    )
                    return CandidatePage(
                        tuple(candidates), next_ordinal, len(raw), task["revision"]
                    )

    @staticmethod
    def _headers(task, prep, accepted, grant):
        if task["manifest_phase"] != "COMPLETE" or prep["state"] != "ACCEPTED":
            unavailable()
        pairs = (
            (task["tenant_id"], grant.tenant_id),
            (task["id"], grant.task_id),
            (task["owner_user_id"], grant.owner_user_id),
            (task["owner_team_id"], grant.owner_team_id),
            (task["source_revision"], grant.source_revision),
            (task["source_hash"], grant.source_hash),
            (prep["tenant_id"], grant.tenant_id),
            (prep["task_id"], grant.task_id),
            (prep["plan_id"], task["source_plan_id"]),
            (prep["source_revision"], grant.source_revision),
            (prep["payload_hash"], grant.source_hash),
            (prep["manifest_hash"], grant.manifest_hash),
            (prep["intent_hash"], grant.intent_hash),
            (prep["actor_id"], grant.actor_id),
            (prep["subject_id"], grant.subject_id),
            (prep["owner_user_id"], grant.owner_user_id),
            (prep["owner_team_id"], grant.owner_team_id),
            (prep["graph_hash"], task["graph_hash"]),
            (prep["task_chunk_hash"], task["manifest_hash"]),
            (prep["manifest_schema_version"], task["dag_schema_version"]),
            (prep["plan_input_hash"], task["plan_input_hash"]),
            (prep["allocation_input_hash"], task["allocation_input_hash"]),
            (prep["expected_node_count"], task["node_count"]),
            (prep["expected_node_count"], task["expected_node_count"]),
            (prep["expected_node_chunks"], task["expected_chunk_count"]),
            (prep["expected_edge_count"], task["edge_count"]),
            (accepted["tenant_id"], grant.tenant_id),
            (accepted["task_id"], grant.task_id),
            (accepted["preparation_id"], prep["id"]),
            (accepted["plan_id"], prep["plan_id"]),
            (accepted["source_revision"], grant.source_revision),
            (accepted["intent_hash"], grant.intent_hash),
            (accepted["manifest_hash"], grant.manifest_hash),
            (accepted["validation_id"], prep["validation_id"]),
            (accepted["validation_hash"], prep["validation_hash"]),
            (accepted["validated_head_revision"], prep["validated_head_revision"]),
            (accepted["submitted_head_revision"], prep["accepted_head_revision"]),
            (accepted["accepted_request_id"], prep["accepted_request_id"]),
            (accepted["accepted_by"], prep["actor_id"]),
        )
        if any(left != right for left, right in pairs):
            unavailable()
        if (
            type(task["node_count"]) is not int
            or not 1 <= task["node_count"] <= 100000
            or task["dag_schema_version"] != 1
            or prep["sealed_at"] is None
            or prep["sealed_revision"] is None
            or prep["accepted_at"] is None
            or prep["expected_command_count"] != task["node_count"]
            or prep["expected_node_chunks"] != (task["node_count"] + CHUNK_SIZE - 1) // CHUNK_SIZE
        ):
            unavailable()
        for suffix in (
            "bytes",
            "byte_chunks",
            "node_count",
            "node_chunks",
            "command_count",
            "edge_count",
        ):
            if prep["persisted_" + suffix] != prep["expected_" + suffix]:
                unavailable()

    async def _manifest(self, session, params, task, prep):
        """完整静态来源逐项核验；每page全量成本明确保留，尚无跨事务proof缓存。"""
        params = params | {"id": prep["id"]}
        digest = hashlib.sha256()
        counters = [0, 0]

        async def chunks():
            while True:
                rows = await _rows(
                    session,
                    "SELECT ordinal,payload,byte_length,chunk_hash FROM "
                    "orbit_launch_execution_byte_chunk WHERE tenant_id=:tenant AND "
                    "preparation_id=:id AND ordinal>=:after ORDER BY ordinal LIMIT 16",
                    params | {"after": counters[0]},
                )
                if not rows:
                    return
                for row in rows:
                    payload = bytes(row["payload"])
                    if (
                        row["ordinal"] != counters[0]
                        or not 1 <= len(payload) <= 1048576
                        or row["byte_length"] != len(payload)
                        or hashlib.sha256(payload).hexdigest() != row["chunk_hash"]
                    ):
                        unavailable()
                    counters[0] += 1
                    counters[1] += len(payload)
                    if (
                        counters[0] > prep["expected_byte_chunks"]
                        or counters[1] > prep["expected_bytes"]
                    ):
                        unavailable()
                    digest.update(payload)
                    yield payload

        graph = GraphDigest(
            task["dag_schema_version"],
            task["source_revision"],
            task["plan_input_hash"],
            task["allocation_input_hash"],
        )
        headers, batch, total, edges, batch_bytes = {}, [], 0, 0, 0
        chunk_heads, chunk_digest, chunk_count = [], hashlib.sha256(b"["), 0

        async def consume():
            nonlocal total, edges, chunk_digest, chunk_count, batch_bytes
            if not batch:
                return
            size = await _one(
                session,
                "SELECT CAST(COALESCE(SUM(OCTET_LENGTH(n.initial_json)+"
                "OCTET_LENGTH(c.resolved_configuration_json)),0) AS UNSIGNED) AS storage_bytes "
                "FROM orbit_task_node n JOIN orbit_launch_execution_command c ON "
                "c.tenant_id=n.tenant_id AND c.task_id=n.task_id AND c.node_id=n.id "
                "WHERE n.tenant_id=:tenant AND n.task_id=:task "
                "AND n.ordinal>=:after AND n.ordinal<:end",
                params | {"after": total, "end": total + len(batch)},
            )
            # MySQL JSON空格可增加存储字节，先核总量再装载，避免200个坏大JSON瞬间物化。
            if (
                type(size["storage_bytes"]) is not int
                or not 0 <= size["storage_bytes"] <= 2 * BATCH_MEMORY_BUDGET
            ):
                unavailable("EXECUTION_DIRECTORY_MEMORY_BUDGET")
            rows = await _rows(
                session,
                "SELECT n.*,c.kind AS command_kind,c.node_key AS command_node_key,c.ordinal AS "
                "command_ordinal,c.preparation_id,c.node_id,c.purpose,c.account_id,c.target_key,"
                "c.resolved_configuration_json,c.resolved_configuration_hash,"
                "c.observation_binding_hash "
                "FROM orbit_task_node n JOIN orbit_launch_execution_command c ON "
                "c.tenant_id=n.tenant_id AND c.task_id=n.task_id AND c.node_id=n.id AND "
                "c.ordinal=n.ordinal WHERE n.tenant_id=:tenant AND n.task_id=:task AND "
                "n.ordinal>=:after ORDER BY n.ordinal LIMIT :limit",
                params | {"after": total, "limit": len(batch)},
            )
            if len(rows) != len(batch):
                unavailable()
            originals, ids, expected_edges = [], [], set()
            for row, document in zip(rows, batch, strict=True):
                original = self._static_node(row, document, prep, task, total)
                ids.append(row["id"])
                originals.append(original)
                expected_edges.update(
                    (row["id"], node_id(task["id"], parent)) for parent in original["parent_keys"]
                )
                if chunk_count:
                    chunk_digest.update(b",")
                chunk_digest.update(canonical(original).encode())
                chunk_count += 1
                total += 1
                if chunk_count == CHUNK_SIZE or total == task["node_count"]:
                    chunk_digest.update(b"]")
                    chunk_heads.append((len(chunk_heads), chunk_count, chunk_digest.hexdigest()))
                    if len(chunk_heads) > 200:
                        unavailable()
                    chunk_digest, chunk_count = hashlib.sha256(b"["), 0
            actual_edges = await _bound_rows(
                session,
                "SELECT e.child_id,e.parent_id,p.ordinal AS parent_ordinal,n.ordinal AS "
                "child_ordinal FROM orbit_task_edge e LEFT JOIN orbit_task_node p ON "
                "p.tenant_id=e.tenant_id AND p.task_id=e.task_id AND p.id=e.parent_id JOIN "
                "orbit_task_node n ON n.tenant_id=e.tenant_id AND n.task_id=e.task_id AND "
                "n.id=e.child_id WHERE e.tenant_id=:tenant AND e.task_id=:task AND e.child_id IN "
                ":ids ORDER BY e.child_id,e.parent_id LIMIT 20001",
                params,
                ids,
            )
            if (
                len(actual_edges) != len(expected_edges)
                or {(row["child_id"], row["parent_id"]) for row in actual_edges} != expected_edges
                or any(
                    type(row["parent_ordinal"]) is not int
                    or row["parent_ordinal"] >= row["child_ordinal"]
                    for row in actual_edges
                )
            ):
                unavailable()
            edges += len(actual_edges)
            graph.append(originals)
            batch.clear()
            batch_bytes = 0

        try:
            async for key, value in _JsonStream(chunks()).records():
                if key == "node":
                    if not isinstance(value, dict) or total + len(batch) >= task["node_count"]:
                        unavailable()
                    size = len(canonical(value).encode())
                    if batch and batch_bytes + size > BATCH_MEMORY_BUDGET:
                        await consume()
                    batch.append(value)
                    batch_bytes += size
                    if len(batch) == 200:
                        await consume()
                else:
                    # 仅保留小型明确绑定头；大输入值单独验证后即释放。
                    if key == "source_payload":
                        if (
                            not isinstance(value, dict)
                            or hashlib.sha256(canonical(value).encode()).hexdigest()
                            != task["source_hash"]
                            or value.get("execution_mode") != task["execution_mode"]
                            or value.get("ownership")
                            != {
                                "owner_user_id": task["owner_user_id"],
                                "owner_team_id": task["owner_team_id"],
                            }
                        ):
                            unavailable()
                        headers[key] = True
                    elif key == "observation_refs":
                        headers[key] = hashlib.sha256(canonical(value).encode()).hexdigest()
                    elif key in {
                        "schema_version",
                        "tenant_id",
                        "plan_id",
                        "plan_revision",
                        "source_payload_hash",
                        "validation_hash",
                        "dag",
                    }:
                        headers[key] = value
            await consume()
        except (UnicodeError, ValueError, TypeError, KeyError, RecursionError):
            unavailable()
        if (
            counters != [prep["expected_byte_chunks"], prep["expected_bytes"]]
            or digest.hexdigest() != prep["manifest_hash"]
            or total != task["node_count"]
            or edges != task["edge_count"]
            or graph.hexdigest() != task["graph_hash"]
            or hashlib.sha256(canonical(chunk_heads).encode()).hexdigest() != task["manifest_hash"]
        ):
            unavailable()
        expected_header = {
            "schema_version": 1,
            "tenant_id": task["tenant_id"],
            "plan_id": task["source_plan_id"],
            "plan_revision": task["source_revision"],
            "source_payload_hash": task["source_hash"],
            "validation_hash": prep["validation_hash"],
            "source_payload": True,
        }
        if any(headers.get(key) != value for key, value in expected_header.items()):
            unavailable()
        dag = headers.get("dag")
        if not isinstance(dag, dict) or any(
            dag.get(key) != value
            for key, value in {
                "node_count": task["node_count"],
                "graph_hash": task["graph_hash"],
                "plan_input_hash": task["plan_input_hash"],
                "allocation_input_hash": task["allocation_input_hash"],
            }.items()
        ):
            unavailable()
        if headers.get("observation_refs") is None:
            unavailable()
        observation = await _rows(
            session,
            "SELECT DISTINCT observation_binding_hash FROM orbit_launch_execution_command WHERE "
            "tenant_id=:tenant AND task_id=:task LIMIT 2",
            params,
        )
        if observation != [{"observation_binding_hash": headers["observation_refs"]}]:
            unavailable()
        chunk_rows = await _rows(
            session,
            "SELECT ordinal,expected_count,expected_hash,persisted FROM orbit_task_chunk WHERE "
            "tenant_id=:tenant AND task_id=:task ORDER BY ordinal LIMIT 201",
            params,
        )
        if [
            (row["ordinal"], row["expected_count"], row["expected_hash"]) for row in chunk_rows
        ] != chunk_heads or any(row["persisted"] != 1 for row in chunk_rows):
            unavailable()
        for table, expected in (
            ("orbit_task_node", total),
            ("orbit_task_edge", edges),
            ("orbit_task_chunk", len(chunk_heads)),
            ("orbit_launch_execution_command", total),
        ):
            row = await _one(
                session,
                "SELECT COUNT(*) AS n FROM " + table + " WHERE tenant_id=:tenant AND task_id=:task",
                params,
            )
            if row["n"] != expected:
                unavailable()

    @staticmethod
    def _static_node(row, document, prep, task, ordinal):
        original, configuration = (
            _decode(row["initial_json"]),
            _decode(row["resolved_configuration_json"]),
        )
        if (
            not isinstance(original, dict)
            or set(original) != ORIGINAL_FIELDS
            or not isinstance(configuration, dict)
        ):
            unavailable()
        parents = original.get("parent_keys")
        if (
            not isinstance(parents, list)
            or len(parents) > MAX_PARENTS
            or any(not isinstance(parent, str) or not parent for parent in parents)
            or len(set(parents)) != len(parents)
        ):
            unavailable()
        expected_document = original | {
            "resolved_configuration": configuration,
            "resolved_configuration_hash": row["resolved_configuration_hash"],
        }
        if (
            document != expected_document
            or hashlib.sha256(canonical(configuration).encode()).hexdigest()
            != row["resolved_configuration_hash"]
        ):
            unavailable()
        if (
            row["ordinal"] != ordinal
            or row["id"] != node_id(task["id"], original["node_key"])
            or row["preparation_id"] != prep["id"]
            or row["node_id"] != row["id"]
        ):
            unavailable()
        for field in ("node_key", "kind", "purpose", "account_id", "target_key"):
            if row[field] != original[field]:
                unavailable()
        if (
            row["kind"] not in KINDS
            or row["command_kind"] != row["kind"]
            or row["command_node_key"] != row["node_key"]
            or row["command_ordinal"] != row["ordinal"]
        ):
            unavailable()
        return original

    async def _candidates(self, session, params, raw, task, prep, grant):
        if not raw:
            return []
        ids = [row["id"] for row in raw]
        commands = await _bound_rows(
            session,
            "SELECT node_id,state,attempt,resolved_configuration_hash,account_id,target_key "
            "FROM orbit_launch_execution_command WHERE tenant_id=:tenant AND "
            "task_id=:task AND node_id IN :ids ORDER BY node_id",
            params,
            ids,
        )
        runtimes = await _bound_rows(
            session,
            "SELECT * FROM orbit_execution_command_runtime WHERE tenant_id=:tenant AND "
            "task_id=:task AND node_id IN :ids ORDER BY node_id",
            params,
            ids,
        )
        attempts = await _bound_rows(
            session,
            "SELECT a.* FROM orbit_execution_command_runtime r JOIN orbit_execution_attempt a ON "
            "a.tenant_id=r.tenant_id AND a.task_id=r.task_id AND a.node_id=r.node_id AND "
            "a.attempt_no=r.active_attempt WHERE r.tenant_id=:tenant AND r.task_id=:task AND "
            "r.node_id IN :ids ORDER BY r.node_id",
            params,
            ids,
        )
        parents = await _bound_rows(
            session,
            "SELECT e.child_id,p.state FROM orbit_task_edge e JOIN orbit_task_node p ON "
            "p.tenant_id=e.tenant_id AND p.task_id=e.task_id AND p.id=e.parent_id WHERE "
            "e.tenant_id=:tenant AND e.task_id=:task AND e.child_id IN :ids ORDER BY "
            "e.child_id,e.parent_id LIMIT 20001",
            params,
            ids,
        )
        command_map, runtime_map, attempt_map = (
            {row["node_id"]: row for row in rows} for rows in (commands, runtimes, attempts)
        )
        if (
            len(command_map) != len(raw)
            or set(command_map) != set(ids)
            or len(runtime_map) != len(runtimes)
            or len(attempt_map) != len(attempts)
            or not set(runtime_map).issubset(ids)
            or not set(attempt_map).issubset(ids)
            or len(parents) > 20000
        ):
            unavailable()
        blocked = {row["child_id"] for row in parents if row["state"] != "SUCCEEDED"}
        result = []
        for node in raw:
            command = command_map[node["id"]]
            runtime = runtime_map.get(node["id"])
            attempt = attempt_map.get(node["id"])
            if (
                node["state"] not in NODE_STATES
                or node["state"] != command["state"]
                or type(node["attempt"]) is not int
                or node["attempt"] != command["attempt"]
            ):
                unavailable()
            if runtime is None:
                if node["attempt"] != 0 or attempt is not None:
                    unavailable()
            else:
                if (
                    type(runtime["revision"]) is not int
                    or not 1 <= runtime["revision"] <= MAX_REVISION
                ):
                    unavailable()
                if runtime["active_attempt"] is None:
                    if (
                        any(
                            runtime[key] is not None
                            for key in (
                                "claim_id",
                                "worker_id",
                                "lease_expires_at",
                                "unknown_since",
                                "last_reconciled_at",
                                "next_reconcile_at",
                            )
                        )
                        or runtime["fencing_token"] != 0
                        or runtime["needs_manual_reconciliation"] != 0
                        or node["attempt"] != 0
                        or attempt is not None
                    ):
                        unavailable()
                else:
                    if attempt is None:
                        unavailable()
                    binding = _stored_binding(attempt)
                    expected = {
                        "tenant_id": grant.tenant_id,
                        "task_id": task["id"],
                        "node_id": node["id"],
                        "preparation_id": prep["id"],
                        "source_hash": task["source_hash"],
                        "manifest_hash": prep["manifest_hash"],
                        "command_hash": command["resolved_configuration_hash"],
                        "actor_id": prep["actor_id"],
                        "subject_id": prep["subject_id"],
                        "owner_user_id": task["owner_user_id"],
                        "owner_team_id": task["owner_team_id"],
                        "execution_mode": task["execution_mode"],
                    }
                    if (
                        any(getattr(binding, key) != value for key, value in expected.items())
                        or (
                            binding.attempt_no,
                            binding.fencing_token,
                            binding.claim_id,
                            binding.worker_id,
                        )
                        != (
                            runtime["active_attempt"],
                            runtime["fencing_token"],
                            runtime["claim_id"],
                            runtime["worker_id"],
                        )
                        or node["attempt"] != binding.attempt_no
                    ):
                        unavailable()
                    continue  # 现役代际仅核绑定，绝不重新领取/递增/重试。
            if (
                task["state"] not in {"QUEUED", "RUNNING"}
                or node["state"] != "QUEUED"
                or node["attempt"] != 0
                or node["id"] in blocked
            ):
                continue
            result.append(
                ExecutionCandidate(
                    node["id"],
                    node["ordinal"],
                    node["kind"],
                    command["account_id"],
                    command["target_key"],
                    command["resolved_configuration_hash"],
                    runtime["revision"] if runtime else None,
                )
            )
        return result
