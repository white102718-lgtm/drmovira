"""投放完整纯DAG：只描述实际操作及回读，不创建任务、不签发预检、不调用平台。"""

import copy
import json
from collections import Counter
from dataclasses import dataclass, replace

from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest
from orbit_api.launch_allocation import (
    ALGORITHM,
    AllocationSolution,
    inputs,
    revisions_tuple,
    verify_evidence,
)
from orbit_api.launch_contract import parse_plan
from orbit_api.launch_expansion import ad_slots, budget_totals, expanded_counts

DAG_SCHEMA_VERSION = 1
DAG_NODE_LIMIT = 100000
MAX_PARENTS = 100


@dataclass(frozen=True)
class DagNode:
    """内部节点非原TaskNode响应；尚无状态/外部ID，不能当成已受理命令。"""

    node_key: str
    kind: str
    parent_keys: tuple[str, ...]
    account_id: str
    target_key: str
    source_pointer: str
    purpose: str
    configuration_hash: str
    asset_id: str | None = None
    asset_revision: int | None = None


@dataclass(frozen=True)
class DagManifest:
    schema_version: int
    plan_revision: int
    plan_input_hash: str
    allocation_input_hash: str
    graph_hash: str
    campaign_count: int
    adset_count: int
    ad_count: int
    total_dag_node_count: int
    kind_counts: tuple[tuple[str, int], ...]
    # 金额保持Decimal规范字符串，不转浮点，也不跨币种合并。
    budget_totals: tuple[tuple[str, str], ...]
    nodes: tuple[DagNode, ...]
    execution_authorized: bool = False


def _invalid(pointer, message):
    raise OrbitError(422, "DAG_INPUT_INVALID", message, pointer)


def _verify_allocation(plan, slots, allocation, evidence, revisions):
    """复核纯求解结果完整性；可信包的采集/时效/权限仍须真实调用方保证。"""
    if not isinstance(allocation, AllocationSolution):
        raise OrbitError(503, "ALLOCATION_UNAVAILABLE", "缺完整分配结果，不能猜测素材映射")
    ordered, assets = inputs(slots, plan["asset_ids"])
    verify_evidence(ordered, assets, evidence)
    if evidence.material_revisions != revisions_tuple(assets, revisions):
        raise OrbitError(409, "MATERIAL_VERSION_CONFLICT", "分配素材版本已变化", "/asset_ids")
    if (
        allocation.algorithm_version != ALGORITHM
        or type(allocation.seed) is not int
        or not 0 <= allocation.seed <= 2147483647
        or allocation.capability_version != evidence.capability_version
    ):
        raise OrbitError(409, "ALLOCATION_VERSION_CONFLICT", "分配算法或能力版本不一致")
    expected_hash = digest(
        {
            "algorithm": ALGORITHM,
            "seed": allocation.seed,
            "allow_repeat": plan["allow_repeat"],
            "slots": [row.__dict__ for row in ordered],
            "assets": assets,
            "material_revisions": revisions,
            "capability_version": evidence.capability_version,
            "capability_source_hash": evidence.source_hash,
            "compatible_masks": evidence.compatible_masks,
        }
    )
    if allocation.input_hash != expected_hash:
        raise OrbitError(409, "ALLOCATION_INPUT_CHANGED", "分配输入已变化，须重新求解")
    if len(allocation.assignments) != len(ordered):
        _invalid("/allocation_id", "完整分配须覆盖每个广告slot，不能部分成功")
    positions = {asset: index for index, asset in enumerate(assets)}
    usage = Counter()
    mapping = {}
    for index, (slot, assignment) in enumerate(zip(ordered, allocation.assignments, strict=True)):
        if not isinstance(assignment, tuple) or len(assignment) != 2:
            _invalid("/allocation_id", "分配映射结构不完整")
        key, asset = assignment
        if key != slot.key or asset not in positions:
            _invalid("/allocation_id", "分配slot或素材不属于当前完整集合")
        if not evidence.compatible_masks[index] & (1 << positions[asset]):
            _invalid("/allocation_id", "素材与广告slot无权威兼容边")
        usage[asset] += 1
        mapping[key] = asset
    if not plan["allow_repeat"] and (len(assets) != len(ordered) or max(usage.values()) > 1):
        _invalid("/allow_repeat", "不重复分配必须每个slot使用不同素材且池大小相等")
    if allocation.usage != tuple((asset, usage[asset]) for asset in assets) or (
        allocation.squared_usage != sum(count * count for count in usage.values())
    ):
        _invalid("/allocation_id", "分配使用次数与完整映射不一致")
    return mapping


def _complete_tree(plan):
    """草稿可为空，但不能据空草稿生成看似成功的空DAG。保留原数组字段指针。"""
    if not plan["account_ids"]:
        _invalid("/account_ids", "构图至少需要一个实际账户")
    if plan.get("account_scope_snapshot_id"):
        _invalid("/account_scope_snapshot_id", "构图前必须消费真实范围并冻结实际账户")
    if not plan["campaigns"]:
        _invalid("/campaigns", "构图至少需要一个系列")
    for ci, campaign in enumerate(plan["campaigns"]):
        if not campaign["adsets"]:
            _invalid(f"/campaigns/{ci}/adsets", "每个系列至少需要一个广告组")
        for si, group in enumerate(campaign["adsets"]):
            if not group["ads"]:
                _invalid(f"/campaigns/{ci}/adsets/{si}/ads", "每个广告组至少需要一个广告")


def _configuration_hash(value):
    """集合规范排序，配置树兄弟顺序保持语义；不改变用于错误定位的原数组。"""
    canonical = copy.deepcopy(value)
    for field in ("account_ids", "asset_ids", "profile_binding_ids"):
        if field in canonical:
            canonical[field] = sorted(canonical[field])
    canonical["identity_bindings"].sort(key=lambda row: row["account_id"])
    for binding in canonical["identity_bindings"]:
        binding["groups"].sort(key=lambda row: row["adset_local_id"])
        binding["ad_overrides"].sort(key=lambda row: row["ad_local_id"])
    return digest(canonical)


def build_launch_dag(plan, *, plan_revision, allocation, compatibility, material_revisions):
    """严格结构→完整兼容分配→稳定拓扑；结果仅供后续真实预检/manifest使用。

    所有新对象初始PAUSED。activate=true时每99个真实广告回读的组尾累计
    组内及上组核验依赖，再逐父层ENABLE及回读。每个VERIFY有真实目标，
    没有空屏障。权限/身份/policy/实际素材与能力包必须由未来事务边界另行复核。
    """
    if type(plan_revision) is not int or not 1 <= plan_revision <= 9007199254740991:
        _invalid("/revision", "计划版本必须为安全正整数")
    value = parse_plan(json.dumps(plan, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    _complete_tree(value)
    counts = expanded_counts(value)
    slots = ad_slots(value)
    assignment = _verify_allocation(value, slots, allocation, compatibility, material_revisions)
    upload_pairs = sorted({(row.account_id, assignment[row.key]) for row in slots})
    predicted = (
        2 * len(upload_pairs)
        + 2 * counts.campaign_count
        + 2 * counts.adset_count
        + 4 * counts.ad_count
    )
    if value["activate_after_create"]:
        predicted += 2 * (counts.campaign_count + counts.adset_count + counts.ad_count)
    if predicted > DAG_NODE_LIMIT:
        raise OrbitError(
            422, "PLAN_NODE_LIMIT", "完整上传/创建/回读/启用节点超过十万", "/campaigns"
        )
    input_hash = _configuration_hash(value)
    nodes = []
    known = set()

    def add(kind, key, parents, account, target, pointer, purpose, asset=None):
        if len(nodes) >= DAG_NODE_LIMIT:
            raise OrbitError(422, "PLAN_NODE_LIMIT", "完整上传/创建/回读/启用节点超过十万", pointer)
        parents = tuple(sorted(set(parents)))
        if (
            key in known
            or len(key) > 512
            or len(parents) > MAX_PARENTS
            or any(parent not in known for parent in parents)
        ):
            raise RuntimeError("内部DAG须唯一、有界且所有父节点已按拓扑生成")
        node = DagNode(
            key,
            kind,
            parents,
            account,
            target,
            pointer,
            purpose,
            digest(
                [
                    DAG_SCHEMA_VERSION,
                    plan_revision,
                    input_hash,
                    allocation.input_hash,
                    kind,
                    key,
                    parents,
                    asset,
                    material_revisions[asset] if asset else None,
                ]
            ),
            asset,
            material_revisions[asset] if asset else None,
        )
        nodes.append(node)
        known.add(key)
        return key

    def verify(target, account, pointer, *, purpose="CREATE", extra=(), object_target=None):
        return add(
            "VERIFY",
            f"VERIFY/{purpose}/{target}",
            (target, *extra),
            account,
            object_target or target,
            pointer,
            purpose,
        )

    # 上传映射原契约按tenant+asset+account；相同素材只在同账户内去重。
    # 不按hash跨owner/不同asset ID合并，不把未选择使用的池成员算作真实上传。
    uploads = {}
    asset_pointers = {asset: f"/asset_ids/{i}" for i, asset in enumerate(value["asset_ids"])}
    for account, asset in upload_pairs:
        key = f"UPLOAD/{account}/{asset}"
        add("UPLOAD", key, (), account, key, asset_pointers[asset], "CREATE", asset)
        uploads[account, asset] = verify(key, account, asset_pointers[asset])

    objects = []
    pending_verifies = []
    gate = None
    campaign_rows = sorted(enumerate(value["campaigns"]), key=lambda row: row[1]["local_id"])
    for account in sorted(value["account_ids"]):
        for ci, campaign in campaign_rows:
            cp = f"/campaigns/{ci}"
            for cc in range(1, campaign["copies"] + 1):
                ckey = f"CAMPAIGN/{account}/{campaign['local_id']}/{cc}"
                add("CAMPAIGN", ckey, (), account, ckey, cp, "CREATE_PAUSED")
                cv = verify(ckey, account, cp)
                objects.append((ckey, cv, None, account, cp))
                for si, group in sorted(
                    enumerate(campaign["adsets"]), key=lambda row: row[1]["local_id"]
                ):
                    sp = f"{cp}/adsets/{si}"
                    for sc in range(1, group["copies"] + 1):
                        skey = (
                            f"ADSET/{account}/{campaign['local_id']}/{cc}/{group['local_id']}/{sc}"
                        )
                        add("ADSET", skey, (cv,), account, skey, sp, "CREATE_PAUSED")
                        sv = verify(skey, account, sp)
                        objects.append((skey, sv, ckey, account, sp))
                        for ai, ad in sorted(
                            enumerate(group["ads"]), key=lambda row: row[1]["local_id"]
                        ):
                            ap = f"{sp}/ads/{ai}"
                            for ac in range(1, ad["copies"] + 1):
                                slot_key = "/".join(
                                    map(
                                        str,
                                        (
                                            account,
                                            campaign["local_id"],
                                            cc,
                                            group["local_id"],
                                            sc,
                                            ad["local_id"],
                                            ac,
                                        ),
                                    )
                                )
                                asset = assignment[slot_key]
                                cr = f"CREATIVE/{slot_key}"
                                add(
                                    "CREATIVE",
                                    cr,
                                    (uploads[account, asset], sv),
                                    account,
                                    cr,
                                    ap,
                                    "CREATE",
                                    asset,
                                )
                                crv = verify(cr, account, ap)
                                ak = f"AD/{slot_key}"
                                add("AD", ak, (sv, crv), account, ak, ap, "CREATE_PAUSED", asset)
                                extra = ()
                                if value["activate_after_create"] and len(pending_verifies) == 98:
                                    extra = (*pending_verifies, *((gate,) if gate else ()))
                                av = verify(ak, account, ap, extra=extra)
                                objects.append((ak, av, skey, account, ap))
                                if value["activate_after_create"]:
                                    if len(pending_verifies) == 98:
                                        gate = av
                                        pending_verifies.clear()
                                    else:
                                        pending_verifies.append(av)

    if value["activate_after_create"]:
        # 末组不足99时补齐最后一个已有真实广告VERIFY的依赖，无新增读请求/假屏障。
        if pending_verifies:
            tail = nodes[-1]
            if tail.node_key != pending_verifies[-1] or tail.kind != "VERIFY":
                raise RuntimeError("末组门禁必须对应最后一个真实广告回读")
            parents = tuple(
                sorted(set((*tail.parent_keys, *pending_verifies[:-1], *((gate,) if gate else ()))))
            )
            if len(parents) > MAX_PARENTS:
                raise RuntimeError("末组真实回读依赖超过原合同")
            nodes[-1] = replace(
                tail,
                parent_keys=parents,
                configuration_hash=digest(
                    [
                        DAG_SCHEMA_VERSION,
                        plan_revision,
                        input_hash,
                        allocation.input_hash,
                        tail.kind,
                        tail.node_key,
                        parents,
                        tail.asset_id,
                        tail.asset_revision,
                    ]
                ),
            )
            gate = tail.node_key
        enabled = {}
        for target, original_verify, parent, account, pointer in objects:
            key = f"ENABLE/{target}"
            parents = (
                (original_verify, gate)
                if parent is None
                else (original_verify, gate, enabled[parent])
            )
            add("ENABLE", key, parents, account, target, pointer, "ENABLE")
            enabled[target] = verify(key, account, pointer, purpose="ENABLE", object_target=target)

    result_nodes = tuple(nodes)
    if len(result_nodes) != predicted:
        raise RuntimeError("完整DAG计数与实际生成节点数不一致")
    return DagManifest(
        DAG_SCHEMA_VERSION,
        plan_revision,
        input_hash,
        allocation.input_hash,
        digest(
            [
                DAG_SCHEMA_VERSION,
                plan_revision,
                input_hash,
                allocation.input_hash,
                [
                    {key: item for key, item in row.__dict__.items() if key != "source_pointer"}
                    for row in result_nodes
                ],
            ]
        ),
        counts.campaign_count,
        counts.adset_count,
        counts.ad_count,
        len(nodes),
        tuple(sorted(Counter(row.kind for row in nodes).items())),
        tuple((row["currency"], row["amount"]) for row in budget_totals(value)),
        result_nodes,
    )
