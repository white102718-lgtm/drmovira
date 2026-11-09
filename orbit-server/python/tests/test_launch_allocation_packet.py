"""64MiB冻结预算与输入恢复纯测；所有能力标记均为隔离fixture，不是平台证明。"""

from dataclasses import replace

import pytest
from test_launch_dag import fixture, plan, uid

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest
from orbit_api.launch_allocation import CompatibilityEvidence
from orbit_api.launch_allocation_packet import CHUNK_BYTES, freeze_packet, sha, thaw_packet
from orbit_api.launch_contract import MAX_CONFIG_BYTES, parse_plan
from orbit_api.launch_expansion import ad_slots


def metadata(value):
    return {
        asset: {
            "revision": 3,
            "sha256": "b" * 64,
            "kind": "IMAGE",
            "mime": "image/png",
            "byte_size": 100,
            "width_px": 24,
            "height_px": 24,
            "duration_seconds": None,
        }
        for asset in value["asset_ids"]
    }


def prepare(value=None, **changes):
    value = parse_plan(canonical(value or plan()).encode())
    evidence = fixture(value)["compatibility"]
    request = {
        "asset_ids": value["asset_ids"],
        "allow_repeat": value["allow_repeat"],
        "seed": 0,
        "algorithm_version": "allocation-v1",
    }
    arguments = (
        dict(plan_revision=1, authority_fingerprint="c" * 64, provider_plan_hash=digest(value))
        | changes
    )
    packet, manifest = freeze_packet(value, request, evidence, metadata(value), **arguments)
    return packet, manifest, arguments


def stored(packet, manifest):
    head = {
        "input_hash": manifest.input_hash,
        "chunk_count": len(manifest.chunks),
        "byte_total": manifest.byte_total,
        "manifest_hash": manifest.manifest_hash,
        "document_hash": manifest.document_hash,
        "slot_count": manifest.slot_count,
    }
    rows = [
        {"ordinal": i, "payload": raw, "payload_hash": sha(raw), "byte_size": len(raw)}
        for i, raw in enumerate(manifest.chunks)
    ]
    return head, rows


def test_complete_freeze_restore_binds_full_plan_revision_and_authority_to_solver_input():
    packet, manifest, _ = prepare()
    head, rows = stored(packet, manifest)
    restored, evidence = thaw_packet(head, rows)
    assert restored == packet
    assert evidence.source_hash == packet["source_hash"]
    assert evidence.source_hash != packet["provider_source_hash"]
    assert prepare(plan_revision=2)[1].input_hash != manifest.input_hash
    assert prepare(authority_fingerprint="d" * 64)[1].input_hash != manifest.input_hash
    value = plan()
    value["campaigns"][0]["adsets"][0]["ads"][0]["url"] = "https://example.test/different"
    assert prepare(value)[1].input_hash != manifest.input_hash


@pytest.mark.parametrize(
    "mutation",
    ["missing", "ordinal", "payload", "size", "hash", "total", "manifest", "document", "slots"],
)
def test_missing_corrupt_or_mismatched_manifest_never_restores_partial_input(mutation):
    packet, manifest, _ = prepare()
    head, rows = stored(packet, manifest)
    if mutation == "missing":
        rows.clear()
    elif mutation == "ordinal":
        rows[0]["ordinal"] = 1
    elif mutation == "payload":
        rows[0]["payload"] += b"x"
    elif mutation == "size":
        rows[0]["byte_size"] += 1
    elif mutation == "hash":
        rows[0]["payload_hash"] = "f" * 64
    elif mutation == "total":
        head["byte_total"] += 1
    elif mutation == "manifest":
        head["manifest_hash"] = "f" * 64
    elif mutation == "document":
        head["document_hash"] = "f" * 64
    else:
        head["slot_count"] += 1
    with pytest.raises(OrbitError) as info:
        thaw_packet(head, rows)
    assert info.value.code == "ALLOCATION_MANIFEST_CORRUPT"


def test_secret_or_unknown_material_fields_rejected_before_freezing():
    value = parse_plan(canonical(plan()).encode())
    args = fixture(value)
    materials = metadata(value)
    materials[value["asset_ids"][0]]["access_token"] = "forbidden-fixture-value"
    with pytest.raises(OrbitError) as info:
        freeze_packet(
            value,
            {
                "asset_ids": value["asset_ids"],
                "allow_repeat": True,
                "seed": 0,
                "algorithm_version": "allocation-v1",
            },
            args["compatibility"],
            materials,
            plan_revision=1,
            authority_fingerprint="c" * 64,
            provider_plan_hash=digest(value),
        )
    assert info.value.status == 503


def test_wrong_full_plan_proof_and_unverified_provider_fail_closed():
    with pytest.raises(OrbitError) as info:
        prepare(provider_plan_hash="0" * 64)
    assert info.value.status == 503
    value = parse_plan(canonical(plan()).encode())
    args = fixture(value)
    with pytest.raises(OrbitError) as info:
        freeze_packet(
            value,
            {
                "asset_ids": value["asset_ids"],
                "allow_repeat": True,
                "seed": 0,
                "algorithm_version": "allocation-v1",
            },
            replace(args["compatibility"], verified=False),
            metadata(value),
            plan_revision=1,
            authority_fingerprint="c" * 64,
            provider_plan_hash=digest(value),
        )
    assert info.value.status == 503


def capacity_packet(*, maximum_plan=True, accounts=1):
    """最大真实slot数与500素材；可选把原计划精确填到5MiB，非能力验证。"""
    value = plan(accounts=accounts, assets=500)
    ads = [{"local_id": uid(1000 + n), "copies": 1, "body": "x"} for n in range(10000 // accounts)]
    value["campaigns"][0]["adsets"][0]["ads"] = ads
    value["channel_id"] = None
    if maximum_plan:
        remaining = MAX_CONFIG_BYTES - len(canonical(value).encode())
        per_ad, extra = divmod(remaining, len(ads))
        assert per_ad + 2 <= 2000
        for n, ad in enumerate(ads):
            ad["body"] += "x" * (per_ad + (n < extra))
        assert len(canonical(value).encode()) == MAX_CONFIG_BYTES
    value = parse_plan(canonical(value).encode())
    slots = tuple(sorted(ad_slots(value)))
    assets = tuple(sorted(value["asset_ids"]))
    revisions = tuple((asset, 3) for asset in assets)
    mask = (1 << 500) - 1
    evidence = CompatibilityEvidence(
        "isolated-capacity-fixture",
        "a" * 64,
        tuple(row.key for row in slots),
        assets,
        (mask,) * len(slots),
        (mask,) * len(slots),
        True,
        True,
        digest([row.__dict__ for row in slots]),
        revisions,
    )
    request = {
        "asset_ids": list(assets),
        "allow_repeat": True,
        "seed": 0,
        "algorithm_version": "allocation-v1",
    }
    return freeze_packet(
        value,
        request,
        evidence,
        metadata(value),
        plan_revision=1,
        authority_fingerprint="c" * 64,
        provider_plan_hash=digest(value),
    )


@pytest.mark.parametrize("accounts,maximum_plan", [(1, True), (500, False)])
def test_actual_maximum_10000_by_500_manifest_under_64mib_without_truncation(
    accounts, maximum_plan
):
    packet, manifest = capacity_packet(maximum_plan=maximum_plan, accounts=accounts)
    assert manifest.slot_count == 10000
    assert len(packet["material_metadata"]) == 500
    assert len(packet["compatible_masks"]) == 10000
    assert all(len(mask) == 125 for mask in packet["compatible_masks"])
    assert manifest.byte_total < 64 * 1024 * 1024
    assert len(manifest.chunks) <= 256
    assert all(0 < len(chunk) <= CHUNK_BYTES for chunk in manifest.chunks)
    head, rows = stored(packet, manifest)
    restored, evidence = thaw_packet(head, rows)
    assert restored == packet
    assert len(evidence.slot_keys) == 10000
    assert all(mask.bit_count() == 500 for mask in evidence.compatible_masks)
    if maximum_plan:
        assert len(canonical(packet["plan"]).encode()) == MAX_CONFIG_BYTES


def test_utf8_can_cross_chunks_but_only_full_verified_document_is_decoded():
    value = plan(copies=1)
    value["campaigns"][0]["adsets"][0]["ads"] = [
        {"local_id": uid(1000 + n), "copies": 1, "body": "🙂" * 1000} for n in range(80)
    ]
    for padding in range(4):
        value["campaigns"][0]["adsets"][0]["ads"][0]["body"] = "x" * padding + "🙂" * 1000
        packet, manifest, _ = prepare(value)
        if any(_invalid_utf8(chunk) for chunk in manifest.chunks):
            break
    assert len(manifest.chunks) > 1
    assert any(_invalid_utf8(chunk) for chunk in manifest.chunks)
    assert thaw_packet(*stored(packet, manifest))[0] == packet
    with pytest.raises(UnicodeDecodeError):
        # 专门验证切片允许位于多字节码点中间，不逐块.decode掩盖/损坏数据。
        next(chunk for chunk in manifest.chunks if _invalid_utf8(chunk)).decode()


def _invalid_utf8(raw):
    try:
        raw.decode()
    except UnicodeDecodeError:
        return True
    return False
