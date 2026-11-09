"""allocation-v1纯残量流求解；缺权威兼容证据拒绝，不注册HTTP或伪异步任务。"""

import hashlib
import re
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic

from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest
from orbit_api.launch_contract import uuid_field

ALGORITHM = "allocation-v1"


class AllocationTimeout(TimeoutError):
    """必须由未来真实持久任务边界处理；异常不携带部分分配。"""

    def __init__(self, phase, source_hash, input_hash=None):
        super().__init__("完整分配求解超时，尚未产生可用分配")
        self.phase, self.source_hash, self.input_hash = phase, source_hash, input_hash


class Budget:
    def __init__(self, seconds, clock, phase, source_hash, input_hash=None):
        if isinstance(seconds, bool) or not 0 < seconds <= 60:
            raise ValueError("求解预算须大于0且不超过60秒")
        self.clock = clock
        self.deadline = clock() + seconds
        self.phase, self.source_hash, self.input_hash = phase, source_hash, input_hash

    def check(self):
        if self.clock() >= self.deadline:
            raise AllocationTimeout(self.phase, self.source_hash, self.input_hash)


def phase_budget(seconds, clock, phase, source_hash, input_hash=None, shared=None):
    """建图和两段流共用同一真实deadline，不能串联两个60秒预算冒充总时限。"""
    budget = (
        shared if shared is not None else Budget(seconds, clock, phase, source_hash, input_hash)
    )
    if not isinstance(budget, Budget) or budget.source_hash != source_hash:
        raise ValueError("共享时限必须绑定同一权威来源")
    budget.phase, budget.input_hash = phase, input_hash
    budget.check()
    return budget


@dataclass(frozen=True)
class CompatibilityEvidence:
    """仅受信内部能力适配器构建；verified不是浏览器可提交的认证字段。"""

    capability_version: str
    source_hash: str
    slot_keys: tuple[str, ...]
    asset_ids: tuple[str, ...]
    compatible_masks: tuple[int, ...]
    evaluated_masks: tuple[int, ...]
    verified: bool
    complete: bool
    slot_inputs_hash: str
    material_revisions: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class AllocationSolution:
    algorithm_version: str
    seed: int
    input_hash: str
    capability_version: str
    # 与slot原合同字典顺序一致，公开API仍须由真实store附asset_revision。
    assignments: tuple[tuple[str, str], ...]
    usage: tuple[tuple[str, int], ...]
    squared_usage: int
    warnings: tuple[str, ...]


def inputs(slots, asset_ids):
    ordered_slots = tuple(sorted(slots))
    assets = tuple(
        sorted(uuid_field(value, ("asset_ids", index)) for index, value in enumerate(asset_ids))
    )
    if not 1 <= len(ordered_slots) <= 10000 or len({row.key for row in ordered_slots}) != len(
        ordered_slots
    ):
        raise OrbitError(422, "ALLOCATION_SLOT_INVALID", "完整展开slot须为1至10000且唯一")
    if not 1 <= len(assets) <= min(500, len(ordered_slots)) or len(set(assets)) != len(assets):
        raise OrbitError(
            422, "ALLOCATION_POOL_INVALID", "素材池须唯一且不超过广告数及500项", "/asset_ids"
        )
    return ordered_slots, assets


def authority(version, source_hash, verified, complete):
    if (
        verified is not True
        or complete is not True
        or not isinstance(version, str)
        or not 1 <= len(version.strip()) <= 64
        or not isinstance(source_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", source_hash) is None
    ):
        raise OrbitError(
            503,
            "CAPABILITY_COMPATIBILITY_UNAVAILABLE",
            "缺完整权威能力版本及兼容证据，不能猜测兼容",
        )


def revisions_tuple(assets, revisions):
    if (
        not isinstance(revisions, Mapping)
        or set(revisions) != set(assets)
        or any(
            type(value) is not int or not 1 <= value <= 9007199254740991
            for value in revisions.values()
        )
    ):
        raise OrbitError(409, "MATERIAL_VERSION_REQUIRED", "必须冻结每项真实素材版本")
    return tuple((asset, revisions[asset]) for asset in assets)


def build_compatibility_evidence(
    slots,
    asset_ids,
    *,
    capability_version,
    source_hash,
    verified,
    complete,
    evaluate,
    material_revisions,
    seconds=60,
    clock=monotonic,
    work_budget=None,
):
    """逐slot×素材评估全部图；evaluate只读已冻结本地权威包，不得联网或按READY猜兼容。"""
    authority(capability_version, source_hash, verified, complete)
    slots, assets = inputs(slots, asset_ids)
    versions = revisions_tuple(assets, material_revisions)
    budget = phase_budget(seconds, clock, "COMPATIBILITY_GRAPH", source_hash, shared=work_budget)
    masks = []
    for row in slots:
        accepted = 0
        for index, asset in enumerate(assets):
            if index % 64 == 0:
                budget.check()
            compatible = evaluate(row, asset)
            if type(compatible) is not bool:
                raise OrbitError(
                    503, "CAPABILITY_COMPATIBILITY_UNAVAILABLE", "存在未知兼容边，完整图尚未建立"
                )
            if compatible:
                accepted |= 1 << index
        masks.append(accepted)
    budget.check()
    return CompatibilityEvidence(
        capability_version,
        source_hash,
        tuple(row.key for row in slots),
        assets,
        tuple(masks),
        ((1 << len(assets)) - 1,) * len(slots),
        True,
        True,
        digest([row.__dict__ for row in slots]),
        versions,
    )


def verify_evidence(slots, assets, evidence):
    if not isinstance(evidence, CompatibilityEvidence):
        raise OrbitError(503, "CAPABILITY_COMPATIBILITY_UNAVAILABLE", "缺权威兼容图")
    authority(
        evidence.capability_version, evidence.source_hash, evidence.verified, evidence.complete
    )
    full = (1 << len(assets)) - 1
    if (
        evidence.slot_keys != tuple(row.key for row in slots)
        or evidence.slot_inputs_hash != digest([row.__dict__ for row in slots])
        or evidence.asset_ids != assets
        or len(evidence.compatible_masks) != len(slots)
        or len(evidence.evaluated_masks) != len(slots)
        or any(type(mask) is not int or mask != full for mask in evidence.evaluated_masks)
        or any(
            type(mask) is not int or mask < 0 or mask > full for mask in evidence.compatible_masks
        )
    ):
        raise OrbitError(
            503, "CAPABILITY_COMPATIBILITY_UNAVAILABLE", "兼容图缺边、来源集合或版本不匹配"
        )


def stable_assets(assets, seed):
    """固定seed资产边优先级，slot仍按原元组排序；不向主目标加入会压过usage²的费用。"""
    return tuple(
        sorted(
            range(len(assets)),
            key=lambda index: (
                hashlib.sha256(f"{ALGORITHM}\0{seed}\0{assets[index]}".encode()).digest(),
                assets[index],
            ),
        )
    )


def residual_match(masks, columns, order, capacity, budget, *, convex):
    """完整残量增广；asset→sink边的凸增量2u+1，内部正反边费用均0。

    用members[a]&columns[b]找到a上可移给b的真实已匹配slot，压缩搜索节点为资产。
    每次最短残量路可迁移既有分配，绝非逐slot固定贪心。无负费用内部边，故最短
    augment路径只需在全部可达终点中选最小边际费；先前最小费用流归纳保证全局最优。
    """
    size = len(order)
    assignments = [-1] * len(masks)
    members, usage = [0] * size, [0] * size
    for root, mask in enumerate(masks):
        budget.check()
        parent = {}
        queue = deque()
        best = None
        lower_bound = min(usage) if convex else 0

        def consider(asset, previous, slot, parents=parent, pending=queue, lower=lower_bound):
            nonlocal best
            parents[asset] = (previous, slot)
            pending.append(asset)
            if usage[asset] < capacity and (best is None or usage[asset] < usage[best]):
                best = asset
            return best is not None and (not convex or usage[best] == lower)

        for asset in order:
            if mask & (1 << asset) and consider(asset, None, root):
                break
        else:
            while queue:
                previous = queue.popleft()
                budget.check()
                for offset, asset in enumerate(order):
                    if offset % 64 == 0:
                        budget.check()
                    if asset in parent:
                        continue
                    witnesses = members[previous] & columns[asset]
                    if witnesses:
                        slot = (witnesses & -witnesses).bit_length() - 1
                        if consider(asset, previous, slot):
                            queue.clear()
                            break
        if best is None:
            raise OrbitError(422, "ALLOCATION_NO_MATCH", "完整兼容图不存在全匹配，未保存部分分配")
        asset = best
        while True:
            previous, slot = parent[asset]
            old = assignments[slot]
            assignments[slot] = asset
            members[asset] |= 1 << slot
            usage[asset] += 1
            if old != -1:
                members[old] &= ~(1 << slot)
                usage[old] -= 1
            if previous is None:
                break
            if old != previous:
                raise RuntimeError("残量图父边必须对应真实既有匹配")
            asset = previous
    return assignments, usage


def solve_allocation(
    slots,
    asset_ids,
    evidence,
    *,
    allow_repeat,
    seed,
    material_revisions,
    seconds=60,
    clock=monotonic,
    work_budget=None,
):
    """纯内部完整结果；超时仅抛typed异常，未来真实任务边界负责排队，不能返回假202。"""
    slots, assets = inputs(slots, asset_ids)
    if type(allow_repeat) is not bool or type(seed) is not int or not 0 <= seed <= 2147483647:
        raise OrbitError(422, "ALLOCATION_INPUT_INVALID", "重复开关或seed不符合原合同")
    if not allow_repeat and len(assets) != len(slots):
        raise OrbitError(
            422, "ALLOCATION_POOL_COUNT_MISMATCH", "不重复时素材数必须等于完整广告数", "/asset_ids"
        )
    verify_evidence(slots, assets, evidence)
    if evidence.material_revisions != revisions_tuple(assets, material_revisions):
        raise OrbitError(409, "MATERIAL_VERSION_CONFLICT", "素材版本已变化，必须重新建立权威兼容图")
    input_hash = digest(
        {
            "algorithm": ALGORITHM,
            "seed": seed,
            "allow_repeat": allow_repeat,
            "slots": [row.__dict__ for row in slots],
            "assets": assets,
            "material_revisions": material_revisions,
            "capability_version": evidence.capability_version,
            "capability_source_hash": evidence.source_hash,
            "compatible_masks": evidence.compatible_masks,
        }
    )
    budget = phase_budget(
        seconds, clock, "RESIDUAL_FLOW", evidence.source_hash, input_hash, work_budget
    )
    columns = [0] * len(assets)
    for index, mask in enumerate(evidence.compatible_masks):
        if index % 64 == 0:
            budget.check()
        remaining = mask
        while remaining:
            bit = remaining & -remaining
            columns[bit.bit_length() - 1] |= 1 << index
            remaining -= bit
    order = stable_assets(assets, seed)
    # 先实际容量最大匹配；repeat的asset容量为slot_count，非重复容量为1。
    assignments, usage = residual_match(
        evidence.compatible_masks,
        columns,
        order,
        len(slots) if allow_repeat else 1,
        budget,
        convex=False,
    )
    if allow_repeat:
        assignments, usage = residual_match(
            evidence.compatible_masks, columns, order, len(slots), budget, convex=True
        )
    budget.check()
    if len(assignments) != len(slots) or any(asset < 0 for asset in assignments):
        raise RuntimeError("必须返回完整匹配，不得暴露部分结果")
    warnings = (
        ("兼容约束下已取得全局最优使用差异；不能保证每素材次数差至多1",)
        if max(usage) - min(usage) > 1
        else ()
    )
    return AllocationSolution(
        ALGORITHM,
        seed,
        input_hash,
        evidence.capability_version,
        tuple((row.key, assets[asset]) for row, asset in zip(slots, assignments, strict=True)),
        tuple(zip(assets, usage, strict=True)),
        sum(count * count for count in usage),
        warnings,
    )
