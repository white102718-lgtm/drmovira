"""原execute的纯不可变准备清单；没有Task受理、数据库或平台写授权。

现DagNode只含配置摘要/指针；本模块另外流式解析实际配置、最终名、身份和
文件描述。完整载荷能分块密封，禁止把DAG hash或runtime ID当作执行清单。
"""

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_allocation import AllocationSolution, CompatibilityEvidence
from orbit_api.launch_contract import fail, parse_model, parse_plan, parse_plan_action, uuid_field
from orbit_api.launch_dag import DagManifest, build_launch_dag
from orbit_api.launch_expansion import ad_slots, expanded_counts
from orbit_api.launch_plan_source import PlanSource
from orbit_api.launch_validation_contract import (
    SAFE_INTEGER,
    FrozenValidation,
    freeze_validation,
    is_current,
    utc_milliseconds,
)
from orbit_api.launch_validation_store import OBSERVATION_KINDS, ObservationReference
from orbit_api.reference_contract import StrictInput

MAX_PACKET = 64 * 1024 * 1024
DESCRIPTOR_FIELDS = (
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
)


class MetricProfile(StrictInput):
    """原OpenAPI MetricProfile，不增添整数revision或平台参数字段。"""

    id: str
    version: str = Field(min_length=1, max_length=64)
    source: Literal["META", "FIXTURE"]
    register_action_type: str | None = Field(min_length=1, max_length=64)
    purchase_action_type: str | None = Field(min_length=1, max_length=64)
    value_action_type: str | None = Field(min_length=1, max_length=64)
    attribution_windows: list[str] = Field(min_length=1, max_length=10)
    action_report_time: str = Field(min_length=1, max_length=64)
    timezone_policy: Literal["ACCOUNT_LOCAL"]
    breakdown: Literal["TOTAL"]
    maturity_days: int = Field(ge=1, le=90)
    verified: bool


class AttributionSpec(StrictInput):
    """Meta官方SDK AttributionSpec字段/类型；合法枚举组合仍由权威能力核验。

    https://github.com/meta/facebook-python-business-sdk/blob/main/
    facebook_business/adobjects/attributionspec.py (Field及_field_types)
    """

    event_type: str = Field(min_length=1, max_length=64)
    window_days: int = Field(ge=-(2**31), le=2**31 - 1)


class ResolvedMetricProfile(StrictInput):
    """明确内部适配器DTO，不是原MetricProfile；不从window字符串猜参数。"""

    profile: MetricProfile
    profile_source_hash: str = Field(min_length=64, max_length=64)
    adapter_version: str = Field(min_length=1, max_length=64)
    bound_profile_version: str = Field(min_length=1, max_length=64)
    registry_revision: int = Field(ge=1, le=SAFE_INTEGER)
    attribution_spec: list[AttributionSpec] = Field(min_length=1, max_length=10)


def stale():
    raise OrbitError(409, "STALE_PREVIEW", "配置源、完整冻结映射或预检已变化")


def _json(value):
    """原始源配置仍由原5MiB合同检查，附加完整映射有界编码，不deepcopy展开树。"""
    output = bytearray()
    try:
        for token in json.JSONEncoder(
            ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).iterencode(value):
            output.extend(token.encode())
            if len(output) > MAX_PACKET:
                raise OrbitError(413, "PAYLOAD_TOO_LARGE", "执行准备输入超过内部有界预算", "/")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise OrbitError(400, "INVALID_STRUCTURE", "执行准备输入必须为合法JSON", "/") from None
    return bytes(output)


@dataclass(frozen=True, repr=False)
class PreparedExecution:
    source: PlanSource
    validated_head_revision: int
    validation_hash: str
    validation_expires_at: datetime
    request_json: bytes
    inputs_json: bytes
    materials_json: bytes
    observations_json: bytes
    dag: DagManifest
    request_payload_hash: str
    manifest_hash: str
    manifest_bytes: int
    # 此常量不可从构造参数设True；Provider观察包/verified不是生产写授权。
    execution_authorized: bool = field(default=False, init=False)


def _materials(metadata, revisions, owner):
    if not isinstance(metadata, dict) or set(metadata) != set(revisions):
        fail(("material_metadata",), "每个分配池素材必须有明确文件描述")
    output = {}
    for identifier in sorted(metadata):
        row = metadata[identifier]
        if not isinstance(row, dict) or not set(DESCRIPTOR_FIELDS).issubset(row):
            fail(("material_metadata", identifier), "缺少真实素材版本/摘要/mime/尺寸/时长描述")
        value = {key: row[key] for key in DESCRIPTOR_FIELDS}
        if (
            value["id"] != identifier
            or type(value["revision"]) is not int
            or not 1 <= value["revision"] <= SAFE_INTEGER
            or value["revision"] != revisions[identifier]
        ):
            stale()
        uuid_field(value["owner_user_id"], ("material_metadata", identifier, "owner_user_id"))
        if value["owner_team_id"] != owner["owner_team_id"]:
            fail(
                ("material_metadata", identifier),
                "素材必须属于冻结团队；双方实时scope仍由Provider核",
            )
        if (
            row.get("state") != "READY"
            or row.get("physical_cleanup_state") != "LIVE"
            or row.get("antivirus_status") != "CLEAN"
            or row.get("execution_eligible") is not True
        ):
            raise OrbitError(
                503,
                "EXECUTION_MATERIAL_SOURCE_UNAVAILABLE",
                "素材观察未就绪，不能靠未知或旧READY状态准备执行",
            )
        if not isinstance(value["sha256"], str) or not re.fullmatch(
            r"[a-f0-9]{64}", value["sha256"]
        ):
            fail(("material_metadata", identifier, "sha256"), "文件摘要必须为真实SHA256")
        limits = {
            "image/jpeg": 20 * 1024 * 1024,
            "image/png": 20 * 1024 * 1024,
            "video/mp4": 500 * 1024 * 1024,
        }
        if (
            value["mime"] not in limits
            or type(value["size"]) is not int
            or not 1 <= value["size"] <= limits[value["mime"]]
        ):
            fail(("material_metadata", identifier), "文件类型或实际大小不符合原素材合同")
        if any(type(value[key]) is not int or value[key] < 1 for key in ("width", "height")):
            fail(("material_metadata", identifier), "文件尺寸未知，不能补零或猜测")
        duration = value["duration"]
        if duration is not None:
            if (
                not isinstance(duration, str)
                or not re.fullmatch(r"[0-9]+(\.[0-9]+)?", duration)
                or Decimal(duration) <= 0
            ):
                fail(("material_metadata", identifier, "duration"), "时长须为正Decimal字符串")
            value["duration"] = format(Decimal(duration).normalize(), "f")
        if value["mime"] == "video/mp4" and duration is None:
            fail(("material_metadata", identifier, "duration"), "视频缺真实时长")
        output[identifier] = value
    return output


def _required_configuration(plan):
    for ci, campaign in enumerate(plan["campaigns"]):
        for key in ("objective", "buying_type", "special_ad_categories", "bid_strategy"):
            if key not in campaign:
                fail(("campaigns", ci, key), "执行所需系列配置缺失")
        for si, group in enumerate(campaign["adsets"]):
            prefix = ("campaigns", ci, "adsets", si)
            for key in (
                "name",
                "country_codes",
                "age_min",
                "age_max",
                "placements",
                "optimization_goal",
                "billing_event",
                "start_time",
            ):
                if key not in group:
                    fail((*prefix, key), "执行所需广告组配置缺失")
            if campaign.get("budget") is None and group.get("budget") is None:
                fail((*prefix, "budget"), "每个预算拥有者分支必须有明确预算")
            for ai, ad in enumerate(group["ads"]):
                for key in ("name", "title", "body", "cta", "asset_type"):
                    if key not in ad:
                        fail((*prefix, "ads", ai, key), "执行所需创意/广告配置缺失")


def _observations(values):
    if not isinstance(values, tuple) or not 1 <= len(values) <= 4000:
        fail(("observation_refs",), "必须提供完整有界观察引用，不能用verified布尔替代")
    rows, seen = [], set()
    for value in values:
        if (
            not isinstance(value, ObservationReference)
            or value.kind not in OBSERVATION_KINDS
            or type(value.revision) is not int
            or not 1 <= value.revision <= SAFE_INTEGER
        ):
            fail(("observation_refs",), "观察引用须为白名单kind/UUID/正安全版本")
        identifier = uuid_field(value.id, ("observation_refs", "id"))
        if (value.kind, identifier) in seen:
            fail(("observation_refs",), "观察引用不得冲突或重复")
        seen.add((value.kind, identifier))
        rows.append({"kind": value.kind, "id": identifier, "revision": value.revision})
    encoded = _json(sorted(rows, key=lambda row: (row["kind"], row["id"])))
    if len(encoded) > 1024 * 1024:
        fail(("observation_refs",), "观察引用超过一MiB")
    return encoded


def _profiles(plan, supplied):
    if not isinstance(supplied, dict) or not supplied:
        raise OrbitError(
            503, "EXECUTION_METRIC_ADAPTER_UNAVAILABLE", "缺完整指标配置及版本绑定的目标参数适配器"
        )
    expected = {
        group.get("metric_profile_id")
        for campaign in plan["campaigns"]
        for group in campaign["adsets"]
    }
    if None in expected or set(supplied) != expected:
        raise OrbitError(
            503, "EXECUTION_METRIC_ADAPTER_UNAVAILABLE", "缺明确指标配置；不能猜账户默认归因参数"
        )
    output = {}
    for identifier in sorted(supplied):
        try:
            row = parse_model(_json(supplied[identifier]), ResolvedMetricProfile)
        except OrbitError:
            raise OrbitError(
                503, "EXECUTION_METRIC_ADAPTER_UNAVAILABLE", "指标适配器输出不符合严格协议"
            ) from None
        profile = row["profile"]
        if (
            profile["id"] != identifier
            or not profile["verified"]
            or profile["version"] != row["bound_profile_version"]
            or hashlib.sha256(canonical(profile).encode()).hexdigest() != row["profile_source_hash"]
        ):
            raise OrbitError(
                503, "EXECUTION_METRIC_ADAPTER_UNAVAILABLE", "指标源版本/摘要或适配绑定缺失"
            )
        if any(
            not isinstance(window, str) or not 1 <= len(window) <= 64
            for window in profile["attribution_windows"]
        ):
            raise OrbitError(
                503, "EXECUTION_METRIC_ADAPTER_UNAVAILABLE", "原指标窗口文本不符合合同"
            )
        output[identifier] = row
    return output


def _destination(plan, channel):
    if not isinstance(channel, dict):
        raise OrbitError(503, "EXECUTION_DESTINATION_UNAVAILABLE", "缺明确目的地快照")
    kind = channel.get("type")
    if kind not in {"WEBSITE", "APP"}:
        raise OrbitError(
            503, "EXECUTION_DESTINATION_UNAVAILABLE", "缺明确网站/应用来源，不能猜身份模式"
        )
    for binding in plan["identity_bindings"]:
        for group in binding["groups"]:
            if kind == "WEBSITE":
                if (
                    not group["pixel_id"]
                    or not group["conversion_event"]
                    or group["application_id"] is not None
                    or group["object_store_url"] is not None
                ):
                    fail(("identity_bindings",), "网站身份须有像素/事件且不混用应用配置")
            elif (
                group["pixel_id"] is not None
                or not group["application_id"]
                or not group["object_store_url"]
            ):
                fail(("identity_bindings",), "应用身份须有应用/商店URL且不混用网站像素")
    if kind == "WEBSITE" and any(
        not ad.get("url")
        for campaign in plan["campaigns"]
        for group in campaign["adsets"]
        for ad in group["ads"]
    ):
        fail(("campaigns",), "网站创意须有明确HTTPS落地页；实时SSRF核验仍属Provider")
    if kind == "APP" and any(
        ad.get("url") is not None
        for campaign in plan["campaigns"]
        for group in campaign["adsets"]
        for ad in group["ads"]
    ):
        fail(("campaigns",), "应用商店URL不得与网站落地页混用")


def prepare_execution(
    source,
    validation,
    *,
    validated_head_revision,
    allocation,
    name_reservation,
    compatibility,
    material_revisions,
    material_metadata,
    resolved_metric_profiles,
    capability_version,
    policy_version,
    scope_version,
    channel_snapshot,
    product_snapshot,
    currency,
    observation_refs,
    request,
    now,
):
    """只准备完整可密封载荷。当前动作/目标授权及实际Task受理仍属未来Store。"""
    if (
        not isinstance(source, PlanSource)
        or not isinstance(source.canonical_payload, bytes)
        or not isinstance(validation, FrozenValidation)
    ):
        fail(("source",), "须提供真实配置源与服务端冻结预检记录")
    if (
        type(validated_head_revision) is not int
        or not source.source_revision
        < validated_head_revision
        == source.head_revision
        <= SAFE_INTEGER
        or validation.source_revision != source.source_revision
    ):
        stale()
    if hashlib.sha256(
        source.canonical_payload
    ).hexdigest() != source.payload_hash or not is_current(validation, now):
        stale()
    plan = parse_plan(source.canonical_payload)
    expanded_counts(plan)
    from orbit_api.launch_meta_settings import require_meta_capabilities

    require_meta_capabilities(plan)
    _required_configuration(plan)
    request_value = parse_plan_action(_json(request), "execute")
    if request_value["hash"] != validation.hash:
        stale()
    if plan["activate_after_create"] and request_value["activate_ack"] is not True:
        fail(("activate_ack",), "启用发布须明确二次确认；当前launch.publish权限仍由Store重核")
    inputs = json.loads(
        _json(
            {
                "allocation": allocation,
                "name_reservation": name_reservation,
                "capability_version": capability_version,
                "policy_version": policy_version,
                "scope_version": scope_version,
                "channel_snapshot": channel_snapshot,
                "product_snapshot": product_snapshot,
                "currency": currency,
            }
        )
    )
    _destination(plan, inputs["channel_snapshot"])
    profiles = _profiles(plan, resolved_metric_profiles)
    replayed = freeze_validation(
        plan,
        plan_id=source.plan_id,
        source_revision=source.source_revision,
        total_dag_node_count=validation.total_dag_node_count,
        validated_at=validation.validated_at,
        **inputs,
    )
    if (
        replayed.hash != validation.hash
        or replayed.counts != validation.counts
        or replayed.budget_totals != validation.budget_totals
    ):
        stale()
    # 原完整对象已严格验证；按slot规范化，返回数组无语义顺序不改变清单。
    inputs["allocation"]["items"].sort(key=lambda row: row["slot_key"])
    inputs["name_reservation"]["items"].sort(key=lambda row: row["slot_key"])
    if (
        not isinstance(compatibility, CompatibilityEvidence)
        or compatibility.capability_version != capability_version
    ):
        raise OrbitError(
            503, "EXECUTION_COMPATIBILITY_UNAVAILABLE", "缺少完整兼容性输入，不能猜测可执行"
        )
    revisions = json.loads(_json(material_revisions))
    if not isinstance(revisions, dict) or any(
        type(value) is not int or not 1 <= value <= SAFE_INTEGER for value in revisions.values()
    ):
        fail(("material_revisions",), "素材版本必须为明确UUID到正安全版本的映射")
    metadata = json.loads(_json(material_metadata))
    resources = _materials(metadata, revisions, plan["ownership"])
    if set(revisions) != set(plan["asset_ids"]):
        fail(("material_revisions",), "素材版本须完整覆盖分配池")
    mapping = {row["slot_key"]: row for row in inputs["allocation"]["items"]}
    slots = sorted(ad_slots(plan))
    for row in mapping.values():
        if row["asset_revision"] != revisions.get(row["asset_id"]):
            stale()
    usage = Counter(row["asset_id"] for row in mapping.values())
    solution = AllocationSolution(
        inputs["allocation"]["algorithm_version"],
        inputs["allocation"]["seed"],
        inputs["allocation"]["input_hash"],
        capability_version,
        tuple((slot.key, mapping[slot.key]["asset_id"]) for slot in slots),
        tuple(sorted(usage.items())),
        sum(count * count for count in usage.values()),
        tuple(inputs["allocation"]["warnings"]),
    )
    dag = build_launch_dag(
        plan,
        plan_revision=source.source_revision,
        allocation=solution,
        compatibility=compatibility,
        material_revisions=revisions,
    )
    if dag.total_dag_node_count != validation.total_dag_node_count:
        stale()
    observations = _observations(observation_refs)
    references = {(row["kind"], row["id"]): row["revision"] for row in json.loads(observations)}
    for key, version in (
        ("ALLOCATION", inputs["allocation"]["id"]),
        ("NAME_RESERVATION", inputs["name_reservation"]["id"]),
    ):
        if references.get((key, version)) != source.source_revision:
            fail(("observation_refs",), "名称和分配须有精确观察版本引用")
    if references.get(("SCOPE", source.tenant_id)) != scope_version:
        fail(("observation_refs",), "缺当前真实范围版本引用")
    if any(("ACCOUNT", account) not in references for account in plan["account_ids"]) or any(
        references.get(("MATERIAL", asset)) != revisions[asset] for asset in usage
    ):
        fail(("observation_refs",), "缺账户或所用素材的完整观察引用")
    if not {"CAPABILITY", "POLICY"}.issubset({row["kind"] for row in json.loads(observations)}):
        raise OrbitError(503, "EXECUTION_AUTHORITY_SOURCE_UNAVAILABLE", "缺明确能力及政策观察引用")
    if any(
        references.get(("CONFIGURATION", identifier)) != row["registry_revision"]
        for identifier, row in profiles.items()
    ):
        fail(("observation_refs",), "指标适配器内部registry_revision须有同源引用，不冒充原version")
    materials = _json({identifier: resources[identifier] for identifier in sorted(usage)})
    request_json = _json(request_value)
    intent = _json(
        {
            "tenant_id": source.tenant_id,
            "plan_id": source.plan_id,
            "plan_revision": source.source_revision,
            "head_revision": validated_head_revision,
            "request": request_value,
        }
    )
    prepared = PreparedExecution(
        source,
        validated_head_revision,
        validation.hash,
        validation.expires_at,
        request_json,
        _json({**inputs, "resolved_metric_profiles": profiles}),
        materials,
        observations,
        dag,
        hashlib.sha256(intent).hexdigest(),
        "",
        0,
    )
    digest, size = hashlib.sha256(), 0
    for chunk in iter_prepared_chunks(prepared):
        digest.update(chunk)
        size += len(chunk)
    # dataclass不保存调用者可变dict；不保留完整展开配置副本，只保存有界原输入与DAG。
    from dataclasses import replace

    return replace(prepared, manifest_hash=digest.hexdigest(), manifest_bytes=size)


def _configuration(value):
    """原字段实际配置规范化；保留数组语义，金额/时间不转浮点。"""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {"copies", "adsets", "ads"}:
                continue
            if key in {"amount", "spend_cap"} and item is not None:
                item = format(Decimal(item).normalize(), "f")
            elif key in {"start_time", "end_time"} and item is not None:
                item = utc_milliseconds(datetime.fromisoformat(item.replace("Z", "+00:00")))
            else:
                item = _configuration(item)
            result[key] = item
        return result
    return [_configuration(row) for row in value] if isinstance(value, list) else value


def iter_execution_nodes(prepared):
    """单次建索引、每个DAG节点O(树深度)解析；不查库、不逐节点取资源。"""
    plan = prepared.source.payload()
    inputs, materials = json.loads(prepared.inputs_json), json.loads(prepared.materials_json)
    names = {row["slot_key"]: row for row in inputs["name_reservation"]["items"]}
    allocation = {row["slot_key"]: row for row in inputs["allocation"]["items"]}
    identities = {row["account_id"]: row for row in plan["identity_bindings"]}
    group_identities = {
        row["account_id"]: {group["adset_local_id"]: group for group in row["groups"]}
        for row in plan["identity_bindings"]
    }
    overrides = {
        row["account_id"]: {ad["ad_local_id"]: ad["page_id"] for ad in row["ad_overrides"]}
        for row in plan["identity_bindings"]
    }
    configurations = {}
    for node in prepared.dag.nodes:
        target_kind, *parts = node.target_key.split("/")
        account = parts[0]
        if target_kind == "UPLOAD":
            descriptor = materials[parts[1]]
            configuration = {"asset": descriptor}
        else:
            if node.source_pointer not in configurations:
                value = plan
                for part in node.source_pointer.split("/")[1:]:
                    value = value[int(part)] if isinstance(value, list) else value[part]
                configurations[node.source_pointer] = _configuration(value)
            configuration = dict(configurations[node.source_pointer])
            if target_kind == "CAMPAIGN":
                configuration["name"] = names["/".join(parts)]["name"]
            else:
                group_id = parts[3]
                identity = {
                    "page_id": identities[account]["page_id"],
                    **group_identities[account][group_id],
                }
                if target_kind in {"AD", "CREATIVE"}:
                    identity["page_id"] = overrides[account].get(parts[5], identity["page_id"])
                    assigned = allocation["/".join(parts)]
                    configuration["asset"] = materials[assigned["asset_id"]]
                configuration["identity"] = identity
                if target_kind == "ADSET":
                    profile = inputs["resolved_metric_profiles"][configuration["metric_profile_id"]]
                    configuration["attribution_spec"] = profile["attribution_spec"]
                    configuration["metric_profile_version"] = profile["profile"]["version"]
                    configuration["metric_profile_source_hash"] = profile["profile_source_hash"]
            if target_kind in {"CAMPAIGN", "ADSET", "AD"}:
                configuration["status"] = "PAUSED"
        if node.kind == "ENABLE":
            configuration = {
                "target_kind": target_kind,
                "name": configuration["name"],
                "status": "ACTIVE",
            }
        elif node.kind == "VERIFY":
            if node.purpose == "ENABLE":
                configuration = {
                    "target_kind": target_kind,
                    "name": configuration["name"],
                    "status": "ACTIVE",
                }
            configuration = {"target_kind": target_kind, "expected_configuration": configuration}
        resolved = canonical(configuration).encode()
        yield {
            **node.__dict__,
            "resolved_configuration": configuration,
            "resolved_configuration_hash": hashlib.sha256(resolved).hexdigest(),
        }


def _tokens(value):
    if isinstance(value, dict):
        yield b"{"
        for index, key in enumerate(sorted(value)):
            if index:
                yield b","
            yield json.dumps(key, ensure_ascii=False).encode()
            yield b":"
            yield from _tokens(value[key])
        yield b"}"
    elif isinstance(value, (list, tuple)) or hasattr(value, "__next__"):
        yield b"["
        for index, item in enumerate(value):
            if index:
                yield b","
            yield from _tokens(item)
        yield b"]"
    else:
        yield json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def iter_prepared_chunks(prepared, *, chunk_bytes=65536):
    """整个可重放JSON文档的字节块，不是空header或只有hash；临时URL不在清单。"""
    if type(chunk_bytes) is not int or not 1024 <= chunk_bytes <= 1024 * 1024:
        raise ValueError("准备块字节上限须在1KiB至1MiB")
    inputs = json.loads(prepared.inputs_json)
    document = {
        "schema_version": 1,
        "tenant_id": prepared.source.tenant_id,
        "plan_id": prepared.source.plan_id,
        "plan_revision": prepared.source.source_revision,
        "source_payload_hash": prepared.source.payload_hash,
        "validation_hash": prepared.validation_hash,
        **inputs,
        "source_payload": prepared.source.payload(),
        "materials": json.loads(prepared.materials_json),
        "observation_refs": json.loads(prepared.observations_json),
        "dag": {
            "graph_hash": prepared.dag.graph_hash,
            "plan_input_hash": prepared.dag.plan_input_hash,
            "allocation_input_hash": prepared.dag.allocation_input_hash,
            "node_count": prepared.dag.total_dag_node_count,
            "kind_counts": dict(prepared.dag.kind_counts),
        },
        "nodes": iter_execution_nodes(prepared),
    }
    buffer = bytearray()
    for token in _tokens(document):
        for offset in range(0, len(token), chunk_bytes):
            fragment = token[offset : offset + chunk_bytes]
            if len(buffer) + len(fragment) > chunk_bytes:
                yield bytes(buffer)
                buffer.clear()
            buffer.extend(fragment)
    if buffer:
        yield bytes(buffer)
