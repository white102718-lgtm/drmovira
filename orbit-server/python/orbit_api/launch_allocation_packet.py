"""分配冻结文档与有界字节manifest；仅可信provider可构造，不是公开认证DTO。"""

import hashlib
import json
import re
from dataclasses import dataclass, replace

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest
from orbit_api.launch_allocation import (
    ALGORITHM,
    CompatibilityEvidence,
    inputs,
    revisions_tuple,
    verify_evidence,
)
from orbit_api.launch_contract import parse_plan, parse_plan_action
from orbit_api.launch_expansion import ad_slots

CHUNK_BYTES = 256 * 1024
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
MAX_CHUNKS = 256
PACKET_FIELDS = {
    "schema_version",
    "plan",
    "plan_revision",
    "request",
    "source_hash",
    "authority_fingerprint",
    "capability_version",
    "material_metadata",
    "compatible_masks",
    "input_hash",
    "provider_source_hash",
}
MATERIAL_FIELDS = {
    "revision",
    "sha256",
    "kind",
    "mime",
    "byte_size",
    "width_px",
    "height_px",
    "duration_seconds",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True)
class PacketManifest:
    input_hash: str
    document_hash: str
    manifest_hash: str
    byte_total: int
    slot_count: int
    chunks: tuple[bytes, ...]


def freeze_packet(
    plan,
    request,
    evidence,
    material_metadata,
    *,
    plan_revision,
    authority_fingerprint,
    provider_plan_hash,
):
    """机械校验完整可信捕获；provider必须已真实完成权限/来源/能力证明，不接浏览器flag。"""
    value = parse_plan(canonical(plan).encode())
    command = parse_plan_action(canonical(request).encode(), "allocation")
    if type(plan_revision) is not int or not 1 <= plan_revision <= 9007199254740991:
        raise OrbitError(422, "FIELD_INVALID", "冻结计划版本无效", "/revision")
    if provider_plan_hash != digest(value) or not _hash(authority_fingerprint):
        raise OrbitError(503, "ALLOCATION_AUTHORITY_UNAVAILABLE", "缺完整当前计划与授权可信证明")
    if not value["account_ids"] or value.get("account_scope_snapshot_id"):
        raise OrbitError(422, "ALLOCATION_INPUT_INVALID", "须先冻结实际账户范围", "/account_ids")
    if (
        set(command["asset_ids"]) != set(value["asset_ids"])
        or command["allow_repeat"] != value["allow_repeat"]
    ):
        raise OrbitError(409, "ALLOCATION_INPUT_CHANGED", "素材池或重复开关与计划不一致")
    slots, assets = inputs(ad_slots(value), command["asset_ids"])
    verify_evidence(slots, assets, evidence)
    if not isinstance(material_metadata, dict) or set(material_metadata) != set(assets):
        raise OrbitError(503, "ALLOCATION_MATERIAL_PROOF_UNAVAILABLE", "冻结素材证明须完整对应池")
    revisions = {}
    for row in material_metadata.values():
        if not isinstance(row, dict) or set(row) != MATERIAL_FIELDS:
            raise OrbitError(
                503, "ALLOCATION_MATERIAL_PROOF_UNAVAILABLE", "素材证明字段须最小完整且不含凭证"
            )
        if (
            type(row["revision"]) is not int
            or not 1 <= row["revision"] <= 9007199254740991
            or not _hash(row["sha256"])
            or row["kind"] not in {"IMAGE", "VIDEO"}
            or not isinstance(row["mime"], str)
            or not 1 <= len(row["mime"]) <= 128
            or type(row["byte_size"]) is not int
            or row["byte_size"] < 1
            or any(
                v is not None and (type(v) is not int or v < 1)
                for v in (row["width_px"], row["height_px"])
            )
            or (
                row["duration_seconds"] is not None
                and (
                    not isinstance(row["duration_seconds"], str)
                    or re.fullmatch(r"[0-9]+(\.[0-9]+)?", row["duration_seconds"]) is None
                )
            )
        ):
            raise OrbitError(
                503, "ALLOCATION_MATERIAL_PROOF_UNAVAILABLE", "素材证明含未知或不受控字段值"
            )
    revisions = {asset: material_metadata[asset]["revision"] for asset in assets}
    if evidence.material_revisions != revisions_tuple(assets, revisions):
        raise OrbitError(409, "MATERIAL_VERSION_CONFLICT", "冻结素材版本不一致")
    source_hash = digest(
        [
            evidence.source_hash,
            plan_revision,
            digest(value),
            authority_fingerprint,
            material_metadata,
        ]
    )
    input_hash = digest(
        {
            "algorithm": ALGORITHM,
            "seed": command["seed"],
            "allow_repeat": command["allow_repeat"],
            "slots": [row.__dict__ for row in slots],
            "assets": assets,
            "material_revisions": revisions,
            "capability_version": evidence.capability_version,
            "capability_source_hash": source_hash,
            "compatible_masks": evidence.compatible_masks,
        }
    )
    # 固定十六进制长度，避免500位数被浏览器/数据库数字解析丢精度。
    width = (len(assets) + 3) // 4
    packet = {
        "schema_version": 1,
        "plan": value,
        "plan_revision": plan_revision,
        "request": command,
        "source_hash": source_hash,
        "provider_source_hash": evidence.source_hash,
        "authority_fingerprint": authority_fingerprint,
        "capability_version": evidence.capability_version,
        "material_metadata": material_metadata,
        "compatible_masks": [f"{mask:0{width}x}" for mask in evidence.compatible_masks],
        "input_hash": input_hash,
    }
    raw = canonical(packet).encode()
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise OrbitError(413, "ALLOCATION_MANIFEST_LIMIT", "完整内部冻结输入超过64MiB，不可截断")
    chunks = tuple(raw[i : i + CHUNK_BYTES] for i in range(0, len(raw), CHUNK_BYTES))
    manifest = [(index, len(chunk), sha(chunk)) for index, chunk in enumerate(chunks)]
    return packet, PacketManifest(
        input_hash, sha(raw), digest(manifest), len(raw), len(slots), chunks
    )


def thaw_packet(head, chunks):
    """先校每块/总字节/manifest，再重组UTF8；最后严格重验规范JSON及冻结内容。"""
    if (
        type(head["chunk_count"]) is not int
        or not 1 <= head["chunk_count"] <= MAX_CHUNKS
        or type(head["byte_total"]) is not int
        or not 1 <= head["byte_total"] <= MAX_DOCUMENT_BYTES
        or len(chunks) != head["chunk_count"]
    ):
        raise OrbitError(409, "ALLOCATION_MANIFEST_CORRUPT", "冻结分块数量或总大小无效")
    total, manifest, pieces = 0, [], []
    for ordinal, row in enumerate(chunks):
        payload = bytes(row["payload"])
        if (
            row["ordinal"] != ordinal
            or not 1 <= len(payload) <= CHUNK_BYTES
            or row["byte_size"] != len(payload)
            or row["payload_hash"] != sha(payload)
        ):
            raise OrbitError(
                409, "ALLOCATION_MANIFEST_CORRUPT", "冻结分块缺失、次序、长度或摘要不符"
            )
        total += len(payload)
        if total > MAX_DOCUMENT_BYTES:
            raise OrbitError(409, "ALLOCATION_MANIFEST_CORRUPT", "冻结分块总量超限")
        manifest.append((ordinal, len(payload), row["payload_hash"]))
        pieces.append(payload)
    if total != head["byte_total"] or digest(manifest) != head["manifest_hash"]:
        raise OrbitError(409, "ALLOCATION_MANIFEST_CORRUPT", "冻结清单或总字节数不符")
    raw = b"".join(pieces)
    if sha(raw) != head["document_hash"]:
        raise OrbitError(409, "ALLOCATION_MANIFEST_CORRUPT", "完整冻结文档摘要不符")
    try:
        packet = json.loads(raw)
        if (
            set(packet) != PACKET_FIELDS
            or packet["schema_version"] != 1
            or canonical(packet).encode() != raw
        ):
            raise ValueError
        plan = packet["plan"]
        slots, assets = inputs(ad_slots(plan), plan["asset_ids"])
        width = (len(assets) + 3) // 4
        masks = packet["compatible_masks"]
        if (
            not isinstance(masks, list)
            or len(masks) != len(slots)
            or any(
                not isinstance(m, str) or re.fullmatch(f"[0-9a-f]{{{width}}}", m) is None
                for m in masks
            )
        ):
            raise ValueError
        revisions = {asset: packet["material_metadata"][asset]["revision"] for asset in assets}
        evidence = CompatibilityEvidence(
            packet["capability_version"],
            packet["provider_source_hash"],
            tuple(row.key for row in slots),
            assets,
            tuple(int(m, 16) for m in masks),
            ((1 << len(assets)) - 1,) * len(slots),
            True,
            True,
            digest([row.__dict__ for row in slots]),
            tuple(sorted(revisions.items())),
        )
        checked, rebuilt = freeze_packet(
            plan,
            packet["request"],
            evidence,
            packet["material_metadata"],
            plan_revision=packet["plan_revision"],
            authority_fingerprint=packet["authority_fingerprint"],
            provider_plan_hash=digest(plan),
        )
        if (
            checked != packet
            or rebuilt.document_hash != head["document_hash"]
            or rebuilt.input_hash != head["input_hash"]
            or rebuilt.slot_count != head["slot_count"]
        ):
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError, OrbitError):
        raise OrbitError(
            409, "ALLOCATION_MANIFEST_CORRUPT", "冻结文档不是完整规范受控输入"
        ) from None
    return packet, replace(evidence, source_hash=packet["source_hash"])
