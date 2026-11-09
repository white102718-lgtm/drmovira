"""030绑定边界纯测；原子回滚/FK/重复事件须独立真实MySQL验证。"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from orbit_api.errors import OrbitError
from orbit_api.material_antivirus import ClamdPolicy, ScanReceipt
from orbit_api.material_antivirus_runtime import (
    RuntimeScanProof,
    RuntimeScanResult,
    TrustedRuntimeProfile,
)
from orbit_api.material_runtime_store import append_runtime_scan, validate_runtime_binding


@pytest.fixture
def binding():
    now = datetime.now(UTC)
    policy = ClamdPolicy(
        19310,
        "1.5.4",
        28177,
        now - timedelta(hours=1),
        "a" * 64,
        600 * 1024**2,
        1000 * 1024**2,
        600 * 1024**2,
        True,
    )
    profile = TrustedRuntimeProfile(
        "trusted",
        1,
        "00000000-0000-4000-8000-000000000004",
        123,
        int((now - timedelta(hours=1)).timestamp() * 1_000_000),
        now - timedelta(minutes=10),
        now + timedelta(minutes=10),
        "b" * 64,
        "C:/trusted/clamd.exe",
        "c" * 64,
        "C:/trusted/clamd.conf",
        "C:/trusted/db",
        (("main.cvd", "d" * 64),),
        policy,
        "e" * 64,
    )
    claim = {
        "tenant_id": "00000000-0000-4000-8000-000000000001",
        "asset_id": "00000000-0000-4000-8000-000000000002",
        "claim_id": "00000000-0000-4000-8000-000000000003",
        "owner_user_id": "00000000-0000-4000-8000-000000000005",
        "owner_team_id": "00000000-0000-4000-8000-000000000006",
        "actor_id": 1,
        "actor_auth_version": 1,
        "revision": 1,
        "byte_size": 100,
        "sha256": "f" * 64,
        "scope_digest": "0" * 64,
        "mime": "image/png",
    }
    receipt = ScanReceipt(
        "CLEAN",
        claim["sha256"],
        100,
        now - timedelta(seconds=2),
        now - timedelta(seconds=1),
        "1.5.4",
        28177,
        policy.daily_db_built_at,
        "a" * 64,
        None,
    )
    proof = RuntimeScanProof(
        profile.profile_id,
        profile.revision,
        profile.instance_id,
        profile.profile_sha256,
        profile.source_sha256,
        profile.executable_sha256,
        profile.policy.config_sha256,
        profile.created_at_us,
        profile.issued_at,
        profile.expires_at,
        now - timedelta(seconds=3),
        now - timedelta(milliseconds=500),
    )
    return claim, RuntimeScanResult(receipt, proof), profile, now


def test_complete_binding_preserves_config_digest_semantics(binding):
    claim, result, profile, now = binding
    proof, receipt = validate_runtime_binding(claim, result, profile, now)
    assert proof is result.proof and receipt is result.receipt
    assert receipt.policy_sha256 == proof.config_sha256 != proof.profile_sha256


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "1" * 64),
        ("byte_size", 101),
        ("result", "SKIPPED"),
        ("engine_version", "1.5.3"),
        ("database_version", 1),
        ("database_version", True),
        ("database_built_at", None),
        ("policy_sha256", "0" * 64),
        ("error_code", "ANTIVIRUS_UNAVAILABLE"),
        ("started_at", datetime.now()),
    ],
)
def test_receipt_identity_and_scan_evidence_mismatch_rejected(binding, field, value):
    claim, result, profile, now = binding
    bad = replace(result, receipt=replace(result.receipt, **{field: value}))
    with pytest.raises(OrbitError) as caught:
        validate_runtime_binding(claim, bad, profile, now)
    assert caught.value.code == "MATERIAL_RUNTIME_PROOF_INVALID"


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile_id", "other"),
        ("profile_revision", 2),
        ("profile_revision", True),
        ("instance_id", "00000000-0000-4000-8000-000000000007"),
        ("profile_sha256", "0" * 64),
        ("source_sha256", "0" * 64),
        ("executable_sha256", "0" * 64),
        ("config_sha256", "0" * 64),
        ("created_at_us", 1),
        ("issued_at", datetime.now()),
    ],
)
def test_runtime_profile_fields_or_generation_cannot_be_borrowed(binding, field, value):
    claim, result, profile, now = binding
    bad = replace(result, proof=replace(result.proof, **{field: value}))
    with pytest.raises(OrbitError):
        validate_runtime_binding(claim, bad, profile, now)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "invalid"),
        ("claim_id", "invalid"),
        ("revision", True),
        ("actor_id", 0),
        ("byte_size", 500 * 1024**2 + 1),
        ("scope_digest", "unknown"),
    ],
)
def test_claim_fields_are_strict_and_bounded(binding, field, value):
    claim, result, profile, now = binding
    with pytest.raises(OrbitError):
        validate_runtime_binding({**claim, field: value}, result, profile, now)


def test_old_receipt_without_runtime_proof_cannot_be_upgraded(binding):
    claim, result, profile, now = binding
    with pytest.raises(OrbitError):
        validate_runtime_binding(claim, replace(result, proof=None), profile, now)


@pytest.mark.parametrize("case", ["expiry", "future_receipt", "wrong_order", "long_scan"])
def test_expiry_future_and_scan_window_rejected(binding, case):
    claim, result, profile, now = binding
    if case == "expiry":
        now = profile.expires_at
    if case == "future_receipt":
        now = result.receipt.completed_at - timedelta(seconds=1)
    if case == "wrong_order":
        result = replace(result, proof=replace(result.proof, verified_before=now))
    if case == "long_scan":
        result = replace(
            result, proof=replace(result.proof, verified_before=now - timedelta(seconds=151))
        )
    with pytest.raises(OrbitError):
        validate_runtime_binding(claim, result, profile, now)


@pytest.mark.parametrize(
    "status,code", [("INFECTED", "ANTIVIRUS_INFECTED"), ("UNVERIFIED", "ANTIVIRUS_UNAVAILABLE")]
)
def test_negative_real_result_can_be_immutably_bound_without_clean_promotion(binding, status, code):
    claim, result, profile, now = binding
    result = replace(result, receipt=replace(result.receipt, result=status, error_code=code))
    _, receipt = validate_runtime_binding(claim, result, profile, now)
    assert receipt.result == status


@pytest.mark.asyncio
async def test_append_requires_explicit_outer_transaction(binding):
    claim, result, profile, _ = binding
    with pytest.raises(RuntimeError, match="显式事务"):
        await append_runtime_scan(
            SimpleNamespace(in_transaction=lambda: False), claim, result, profile
        )
