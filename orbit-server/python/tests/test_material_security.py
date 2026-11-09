"""安全独立合同与原对象复核；真实HTTP/权限/重扫事务由主线专项验收。"""

import hashlib
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from orbit_api.errors import OrbitError
from orbit_api.material_objects import LocalMaterialObjects
from orbit_api.material_security import security_ids, verify_rescan_source
from orbit_api.material_store import MaterialStore, public_asset

A, B = str(UUID(int=1)), str(UUID(int=2))


def test_security_csv_is_canonical_sorted_bounded_and_never_accepts_duplicates():
    assert security_ids(B + "," + A) == [A, B]
    assert len(security_ids(",".join(str(UUID(int=i)) for i in range(1, 201)))) == 200


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        A + "," + A,
        A + ",",
        " " + A,
        "not-a-uuid",
        ",".join(str(UUID(int=i)) for i in range(1, 202)),
        "x" * 7400,
    ],
)
def test_security_csv_bad_input_is_explicit_not_partial(value):
    with pytest.raises(OrbitError) as error:
        security_ids(value)
    assert error.value.status == 422


def test_rescan_source_verifies_real_file_hash_size_and_missing_does_not_recreate(tmp_path):
    objects = LocalMaterialObjects(tmp_path)
    tenant, upload = str(uuid4()), str(uuid4())
    asset = {
        "object_upload_id": upload,
        "sha256": hashlib.sha256(b"safe-original").hexdigest(),
        "byte_size": 13,
    }
    with pytest.raises(OrbitError) as error:
        verify_rescan_source(objects, tenant, asset)
    assert error.value.code == "ORIGINAL_OBJECT_UNAVAILABLE"
    assert not (tmp_path / tenant / upload).exists()
    source = objects.directory(tenant, upload) / "original"
    source.write_bytes(b"safe-original")
    verify_rescan_source(objects, tenant, asset)
    source.write_bytes(b"changed-bytes")
    with pytest.raises(OrbitError) as error:
        verify_rescan_source(objects, tenant, asset)
    assert error.value.code == "ORIGINAL_OBJECT_CHANGED"


def test_legacy_ready_never_emits_preview_url_without_shared_scan_proof():
    asset = {
        "id": A,
        "name": "legacy",
        "kind": "IMAGE",
        "state": "READY",
        "revision": 1,
        "owner_user_id": A,
        "owner_team_id": B,
        "category_id": A,
        "sha256": "a" * 64,
        "preview_ready": 1,
        "duration_seconds": None,
    }
    assert public_asset(asset, [], "https://fixture.example")["preview_url"] is None
    verified = public_asset(asset | {"_scan_verified": True}, [], "https://fixture.example")
    assert verified["preview_url"] == f"https://fixture.example/api/v1/assets/{A}/preview"
    assert "_scan_verified" not in verified and "scan_status" not in verified


@pytest.mark.parametrize(
    "failure,expected",
    [
        ((400, "TOKEN_INVALID"), (403, "CSRF_INVALID")),
        ((403, "CSRF_INVALID"), (403, "CSRF_INVALID")),
        ((503, "KEY_UNAVAILABLE"), (503, "KEY_UNAVAILABLE")),
    ],
)
def test_csrf_maps_only_generic_invalid_token_and_preserves_unrelated_errors(failure, expected):
    def verify(*args):
        raise OrbitError(*failure, "fixture")

    service = MaterialStore(SimpleNamespace(verify=verify))
    with pytest.raises(OrbitError) as error:
        service.verify_csrf("auth", 1, "tenant", "invalid")
    assert (error.value.status, error.value.code) == expected


def test_valid_token_from_another_session_is_csrf_invalid():
    service = MaterialStore(
        SimpleNamespace(
            verify=lambda *args: {"binding": "old"}, session_binding=lambda *args: "current"
        )
    )
    with pytest.raises(OrbitError) as error:
        service.verify_csrf("auth", 1, "tenant", "signed-but-wrong-session")
    assert error.value.status == 403 and error.value.code == "CSRF_INVALID"
