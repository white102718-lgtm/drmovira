"""新Python凭据认证加密边界；无HTTP解密或凭据读取端点。"""

import base64
import os

import pytest

from orbit_api.credentials import CredentialCipher
from orbit_api.errors import OrbitError


def key():
    return base64.b64encode(os.urandom(32)).decode()


def test_random_nonces_roundtrip_and_repr_never_contains_key_or_plaintext():
    encoded = key()
    cipher = CredentialCipher("current", {"current": encoded})
    one = cipher.encrypt("fixture-token-中文", "tenant", "config", "apiKey")
    two = cipher.encrypt("fixture-token-中文", "tenant", "config", "apiKey")
    assert one != two
    assert cipher.decrypt_internal(one, "tenant", "config", "apiKey") == "fixture-token-中文"
    assert "fixture-token" not in one
    assert encoded not in repr(cipher)


@pytest.mark.parametrize(
    "context",
    [("other", "config", "apiKey"), ("tenant", "other", "apiKey"), ("tenant", "config", "other")],
)
def test_cross_tenant_object_and_field_copies_are_rejected(context):
    cipher = CredentialCipher("v1", {"v1": key()})
    envelope = cipher.encrypt("fixture-secret", "tenant", "config", "apiKey")
    with pytest.raises(OrbitError) as error:
        cipher.decrypt_internal(envelope, *context)
    assert error.value.code == "CREDENTIAL_INTEGRITY_FAILED"
    assert "fixture-secret" not in str(error.value)


def test_aad_length_prefix_prevents_ambiguous_concatenated_identity():
    cipher = CredentialCipher("v1", {"v1": key()})
    envelope = cipher.encrypt("fixture", "a", "bc", "d")
    with pytest.raises(OrbitError):
        cipher.decrypt_internal(envelope, "ab", "c", "d")


@pytest.mark.parametrize(
    "corrupt", ["v2.key.a.b", "v1.missing.a.b", "v1.key.!bad.b", "too.few", "v1.key.a.b.extra"]
)
def test_malformed_unknown_version_or_key_rejected_without_raw_input(corrupt):
    cipher = CredentialCipher("key", {"key": key()})
    with pytest.raises(OrbitError) as error:
        cipher.decrypt_internal(corrupt, "tenant", "config", "apiKey")
    assert corrupt not in str(error.value)


def test_ciphertext_and_tag_tampering_are_rejected():
    cipher = CredentialCipher("key", {"key": key()})
    envelope = cipher.encrypt("fixture", "t", "c", "s")
    parts = envelope.split(".")
    parts[3] = ("A" if parts[3][0] != "A" else "B") + parts[3][1:]
    with pytest.raises(OrbitError):
        cipher.decrypt_internal(".".join(parts), "t", "c", "s")


def test_missing_key_never_uses_plaintext_or_fallback():
    cipher = CredentialCipher(None, {})
    assert not cipher.ready
    with pytest.raises(OrbitError, match="独立凭据主密钥"):
        cipher.encrypt("fixture", "t", "c", "s")
    with pytest.raises(OrbitError):
        cipher.decrypt_internal("fixture", "t", "c", "s")


@pytest.mark.parametrize(
    "active,keys",
    [
        ("missing", {"key": "eA=="}),
        ("missing", {"key": key()}),
        ("bad.id", {"bad.id": key()}),
        ("key", {"key": "!not-base64"}),
    ],
)
def test_invalid_key_material_and_key_ids_are_redacted(active, keys):
    with pytest.raises(OrbitError) as error:
        CredentialCipher(active, keys)
    for value in keys.values():
        assert value not in str(error.value)


def test_jwt_material_cannot_be_reused_and_old_key_rotation_remains_readable():
    old = os.urandom(32)
    encoded = base64.b64encode(old).decode()
    with pytest.raises(OrbitError):
        CredentialCipher("old", {"old": encoded}, forbidden_material=(old,))
    with pytest.raises(OrbitError):
        CredentialCipher("old", {"old": encoded}, forbidden_material=(encoded.encode(),))
    one = CredentialCipher("old", {"old": encoded})
    envelope = one.encrypt("fixture", "t", "c", "s")
    two = CredentialCipher("new", {"old": encoded, "new": key()})
    rotated = two.rotate_internal(envelope, "t", "c", "s")
    assert rotated.startswith("v1.new.")
    assert two.decrypt_internal(envelope, "t", "c", "s") == "fixture"
    assert two.decrypt_internal(rotated, "t", "c", "s") == "fixture"


def test_request_hmac_is_stable_across_rotation_when_original_key_id_is_kept():
    old = key()
    first = CredentialCipher("old", {"old": old})
    request = b"fixture-sensitive-request"
    original = first.request_digest_internal(request, "old")
    rotated = CredentialCipher("new", {"old": old, "new": key()})
    assert rotated.request_digest_internal(request, "old") == original
    assert rotated.request_digest_internal(request, "new") != original
    assert first.request_digest_internal(b"changed", "old") != original
    assert len(original) == 64
    assert "fixture-sensitive-request" not in original


def test_missing_original_request_key_version_is_blocked_not_silently_rehashed():
    cipher = CredentialCipher("new", {"new": key()})
    with pytest.raises(OrbitError) as error:
        cipher.request_digest_internal(b"fixture-sensitive-request", "missing")
    assert error.value.code == "IDEMPOTENCY_KEY_UNAVAILABLE"


def test_business_cursor_domains_cannot_replay_another_modules_signature():
    cipher = CredentialCipher("key", {"key": key()})
    payload = b"same-tenant-actor-filter-and-position"
    purposes = (
        "ACCOUNT_CURSOR_V1",
        "ACCOUNT_SCOPE_CURSOR_V1",
        "LAUNCH_CURSOR_V1",
        "TEMPLATE_CURSOR_V1",
        "ACCOUNT_IMPORT_CURSOR_V1",
        "ACCOUNT_DETAILS_CURSOR_V1",
        "ACCOUNT_DETAILS_OWNER_CURSOR_V1",
        "REFERENCE_CURSOR_V1",
        "CHANNEL_CURSOR_V1",
        "MATERIAL_CURSOR_V1",
        "MATERIAL_TAXONOMY_CURSOR_V1",
        "METRIC_PROFILE_CURSOR_V1",
        "METRICS_QUERY_CURSOR_V1",
        "IDENTITY_SUMMARY_SEAL_V1",
        "RULE_CURSOR_V1",
        "RULE_EDITOR_CURSOR_V1",
        "RULE_EDITOR_SCOPE_CURSOR_V1",
        "RULE_SCOPE_OPTIONS_CURSOR_V1",
        "DIRECTORY_CURSOR_V1",
        "BROWSER_SESSION_CSRF_V1",
    )
    signatures = {cipher.application_mac(purpose, payload) for purpose in purposes}
    assert len(signatures) == len(purposes)
    with pytest.raises(ValueError):
        cipher.application_mac("UNREGISTERED_CURSOR_V1", payload)
