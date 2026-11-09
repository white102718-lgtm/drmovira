"""身份可信证据边界纯测试；数据库事务/真实采集/外部可用性另走专项。"""

from datetime import UTC, datetime, timedelta

import pytest

from orbit_api.account_identities_store import (
    AccountIdentitiesStore,
    fingerprint,
    validate_evidence,
)
from orbit_api.errors import OrbitError

ID = "10000000-0000-4000-8000-000000000001"
NOW = datetime(2026, 11, 8, 6, tzinfo=UTC)


def fixture():
    value = {
        "account_id": ID,
        "resources": [],
        "capability_version": "fixture-v1",
        "observed_at": "2026-11-08T05:00:00.000Z",
    }
    evidence = {
        "verified": 1,
        "complete": 1,
        "revoked_at": None,
        "evidence_ref": "fixture-only-not-real-platform",
        "account_id": ID,
        "account_revision": 2,
        "source_config_revision": 4,
        "credential_expires_at": None,
        "capability_version": "fixture-v1",
        "observed_at": datetime(2026, 11, 8, 5),
        "payload_hash": fingerprint(value),
    }
    source = {
        "section": "META_BM",
        "enabled": 1,
        "verification_status": "READ_VERIFIED",
        "revision": 4,
        "secrets_json": '{"accessToken":"fixture-encrypted-reference-not-used"}',
    }
    return evidence, {"id": ID, "revision": 2}, source, value


def test_verified_complete_evidence_binds_exact_account_revision_and_payload_without_default_ttl():
    evidence, account, source, value = fixture()
    assert validate_evidence(evidence, account, source, value, NOW) is None
    assert validate_evidence(evidence, account, source, value, NOW + timedelta(days=365)) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("verified", 0),
        ("complete", 0),
        ("revoked_at", NOW),
        ("evidence_ref", ""),
        ("account_id", "another-account"),
        ("account_revision", 3),
    ],
)
def test_registry_invalidation_never_preserves_usable_claim(field, value):
    evidence, account, source, body = fixture()
    evidence[field] = value
    with pytest.raises(OrbitError) as failure:
        validate_evidence(evidence, account, source, body, NOW)
    assert failure.value.status == 503
    assert failure.value.code == "ACCOUNT_IDENTITY_EVIDENCE_UNVERIFIED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("section", "GPT"),
        ("enabled", 0),
        ("verification_status", "UNVERIFIED"),
        ("revision", 5),
        ("secrets_json", "{}"),
    ],
)
def test_current_source_must_remain_verified_and_same_revision(field, value):
    evidence, account, source, body = fixture()
    source[field] = value
    with pytest.raises(OrbitError) as failure:
        validate_evidence(evidence, account, source, body, NOW)
    assert failure.value.code == "ACCOUNT_IDENTITY_SOURCE_UNAVAILABLE"


@pytest.mark.parametrize("seconds", [-1, 0, 1])
def test_known_credential_expiry_boundary(seconds):
    evidence, account, source, body = fixture()
    evidence["credential_expires_at"] = NOW + timedelta(seconds=seconds)
    if seconds > 0:
        assert validate_evidence(evidence, account, source, body, NOW) is None
    else:
        with pytest.raises(OrbitError) as failure:
            validate_evidence(evidence, account, source, body, NOW)
        assert failure.value.code == "ACCOUNT_IDENTITY_CREDENTIAL_EXPIRED"


@pytest.mark.parametrize("target", ["version", "time", "resources", "future"])
def test_cannot_replace_observed_payload_or_publish_arbitrary_version(target):
    evidence, account, source, body = fixture()
    if target == "version":
        body["capability_version"] = "arbitrary-version"
    elif target == "time":
        body["observed_at"] = "2026-11-08T04:00:00.000Z"
    elif target == "resources":
        body["resources"] = [
            {
                "kind": "PAGE",
                "external_id": "123",
                "name": "",
                "usable": True,
                "reason_code": None,
            }
        ]
    else:
        evidence["observed_at"] = NOW + timedelta(seconds=1)
    with pytest.raises(OrbitError) as failure:
        validate_evidence(evidence, account, source, body, NOW)
    assert failure.value.code == "ACCOUNT_IDENTITY_EVIDENCE_MISMATCH"


def test_resource_set_order_does_not_change_trusted_digest_but_usable_does():
    _, _, _, body = fixture()
    first = {"kind": "PAGE", "external_id": "001", "usable": True}
    second = {"kind": "PIXEL", "external_id": "002", "usable": False}
    original = body | {"resources": [first, second]}
    assert fingerprint(original) == fingerprint(body | {"resources": [second, first]})
    assert fingerprint(original) != fingerprint(
        body | {"resources": [first | {"usable": False}, second]}
    )


@pytest.mark.asyncio
async def test_publication_refuses_without_explicit_transaction_before_any_query():
    class Session:
        def in_transaction(self):
            return False

    with pytest.raises(ValueError):
        await AccountIdentitiesStore().publish(Session(), 1, ID, {}, 0, ID)


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [-1, True, "1", 9_007_199_254_740_991])
async def test_invalid_revision_rejected_before_database_and_without_coercion(revision):
    class Session:
        def in_transaction(self):
            return True

    with pytest.raises(OrbitError) as failure:
        await AccountIdentitiesStore().publish(Session(), 1, ID, {}, revision, ID)
    assert failure.value.status == 422
