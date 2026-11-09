"""原Task/TaskNode读取合同及内部非执行DAG校验，不扩展原枚举。"""

import hashlib
import re
from dataclasses import asdict
from uuid import UUID, uuid5

from orbit_api.configuration import short_text
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_dag import DagManifest

TASK_STATES = frozenset(
    {
        "QUEUED",
        "RUNNING",
        "VERIFYING",
        "UNKNOWN",
        "RETRY_WAIT",
        "SUCCEEDED",
        "PARTIAL_SUCCESS",
        "FAILED",
        "CANCELLED",
        "NEEDS_HUMAN",
    }
)
NODE_STATES = frozenset(
    {
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
)
KINDS = frozenset(
    {"UPLOAD", "CAMPAIGN", "ADSET", "CREATIVE", "AD", "VERIFY", "ENABLE", "ALLOCATION"}
)
PAGE_SIZES = {20, 50, 100, 200}
CHUNK_SIZE = 500
MAX_NODES = 100000


def invalid(pointer, message="任务查询字段无效"):
    raise OrbitError(422, "FIELD_VALIDATION_FAILED", message, pointer)


def identifier(value, pointer="/id"):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower():
            raise ValueError
        return str(UUID(value))
    except ValueError:
        invalid(pointer)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def node_id(task_id, key):
    return str(uuid5(UUID(task_id), key))


class GraphDigest:
    """与B原canonical数组逐字节一致，有界分块重算而不重载十万图。"""

    def __init__(self, schema, revision, plan_hash, allocation_hash):
        if (
            type(schema) is not int
            or schema != 1
            or type(revision) is not int
            or not 1 <= revision <= 9007199254740991
            or any(
                not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
                for value in (plan_hash, allocation_hash)
            )
        ):
            raise OrbitError(
                409, "TASK_DAG_HEADER_UNVERIFIED", "真实DAG类型化头缺失或无效，不能发布"
            )
        self.hash = hashlib.sha256()
        self.hash.update(canonical([schema, revision, plan_hash, allocation_hash])[:-1].encode())
        self.hash.update(b",[")
        self.count = 0

    def append(self, records):
        for row in records:
            if self.count:
                self.hash.update(b",")
            self.hash.update(
                canonical(
                    {key: value for key, value in row.items() if key != "source_pointer"}
                ).encode()
            )
            self.count += 1

    def hexdigest(self):
        result = self.hash.copy()
        result.update(b"]]")
        return result.hexdigest()


def filters(query, *, nodes=False):
    allowed = {
        "q",
        "cursor",
        "page_size",
        "status",
        "date_from",
        "date_to",
        "operator_user_id",
        "channel_id",
        "metric_profile_id",
        "entity_type",
    }
    if set(query) - allowed:
        raise OrbitError(400, "UNKNOWN_FIELD", "任务接口不接受此查询参数")
    for name in {"date_from", "date_to", "channel_id", "metric_profile_id", "entity_type"}:
        if query.get(name) not in {None, ""}:
            invalid("/" + name, "该任务筛选的领域语义尚未定义，不能静默忽略")
    q = query.get("q", "")
    if not isinstance(q, str):
        invalid("/q")
    if q and not nodes:
        invalid("/q", "任务列表尚不支持名称搜索；节点支持真实node_key前缀")
    if q:
        try:
            q = short_text(q, 100, "/q")
        except OrbitError as error:
            # 共享文本规则不变；原Task合同的字段错误码按API_SEMANTICS规范化。
            if error.status == 422:
                invalid(error.pointer, error.message)
            raise
    size = query.get("page_size", "50")
    if size not in {str(value) for value in PAGE_SIZES}:
        invalid("/page_size")
    status = query.get("status") or None
    if status is not None and status not in (NODE_STATES if nodes else TASK_STATES):
        invalid("/status")
    operator = query.get("operator_user_id") or None
    if operator:
        operator = identifier(operator, "/operator_user_id")
    cursor = query.get("cursor")
    if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048):
        invalid("/cursor")
    return {"q": q, "page_size": int(size), "status": status, "operator_user_id": operator}, cursor


def validate_dag(dag):
    """校完整真实节点/拓扑/hash；不把结构校验变成执行授权。"""
    if not isinstance(dag, DagManifest) or dag.schema_version != 1:
        invalid("/manifest", "必须提供真实版本化DagManifest")
    if not 1 <= len(dag.nodes) <= MAX_NODES or dag.total_dag_node_count != len(dag.nodes):
        raise OrbitError(422, "PLAN_NODE_LIMIT", "真实完整DAG必须1至100000节点")
    known, records = set(), []
    for node in dag.nodes:
        if (
            node.kind not in KINDS
            or not isinstance(node.node_key, str)
            or not 1 <= len(node.node_key) <= 512
            or node.node_key in known
            or len(node.parent_keys) > 100
            or len(set(node.parent_keys)) != len(node.parent_keys)
            or any(parent not in known for parent in node.parent_keys)
            or not re.fullmatch(r"[a-f0-9]{64}", node.configuration_hash)
        ):
            invalid("/manifest/nodes", "DAG必须唯一、无环、父在前且每节点父不超过100")
        identifier(node.account_id, "/manifest/account_id")
        known.add(node.node_key)
        records.append(asdict(node))
    graph = GraphDigest(
        dag.schema_version, dag.plan_revision, dag.plan_input_hash, dag.allocation_input_hash
    )
    graph.append(records)
    expected = graph.hexdigest()
    if expected != dag.graph_hash:
        raise OrbitError(409, "TASK_MANIFEST_HASH_CONFLICT", "DAG摘要与实际节点不一致")
    return records


def chunk_manifest(records):
    return [
        (
            offset // CHUNK_SIZE,
            len(records[offset : offset + CHUNK_SIZE]),
            digest(records[offset : offset + CHUNK_SIZE]),
        )
        for offset in range(0, len(records), CHUNK_SIZE)
    ]
