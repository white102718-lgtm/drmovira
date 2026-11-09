"""素材字段边界与结构测试；不代表真实MySQL或浏览器验收。"""

import json

import pytest

from orbit_api.errors import OrbitError
from orbit_api.material_contract import (
    IMAGE_LIMIT,
    PART_SIZE,
    VIDEO_LIMIT,
    AssetWrite,
    BulkDelete,
    CompleteUpload,
    UploadRequest,
    expected_part_size,
    parse_material,
    verify_magic,
)

CATEGORY = "00000000-0000-4000-8000-000000000001"


def upload(**changes):
    return {
        "metadata": {"name": "测试素材", "category_id": CATEGORY, "tag_ids": []},
        "mime": "image/png",
        "size": 10,
        "sha256": "a" * 64,
    } | changes


def parse(model, value):
    return parse_material(model, json.dumps(value).encode())


@pytest.mark.parametrize("field", list(upload()))
def test_upload_requires_every_original_field(field):
    value = upload()
    value.pop(field)
    with pytest.raises(OrbitError) as error:
        parse(UploadRequest, value)
    assert error.value.status == 400


@pytest.mark.parametrize("size", [0, -1, True, "10", None, VIDEO_LIMIT + 1])
def test_sizes_are_strict_and_bounded(size):
    with pytest.raises(OrbitError):
        parse(UploadRequest, upload(size=size))


def test_image_and_video_have_distinct_limits():
    assert parse(UploadRequest, upload(size=IMAGE_LIMIT)).size == IMAGE_LIMIT
    with pytest.raises(OrbitError) as error:
        parse(UploadRequest, upload(size=IMAGE_LIMIT + 1))
    assert error.value.code == "FILE_TOO_LARGE"
    assert parse(UploadRequest, upload(mime="video/mp4", size=VIDEO_LIMIT)).size == VIDEO_LIMIT


@pytest.mark.parametrize("mime", [None, 1, True, [], {}])
def test_non_string_mime_is_structure_error(mime):
    with pytest.raises(OrbitError) as error:
        parse(UploadRequest, upload(mime=mime))
    assert error.value.status == 400 and error.value.pointer == "/mime"


@pytest.mark.parametrize("digest", ["A" * 64, "a" * 63, "../" * 20, "", "0" * 65])
def test_hash_is_canonical(digest):
    with pytest.raises(OrbitError):
        parse(UploadRequest, upload(sha256=digest))


def test_no_user_paths_and_duplicate_tags():
    with pytest.raises(OrbitError) as error:
        parse(UploadRequest, upload(path="../../x"))
    assert error.value.status == 400
    with pytest.raises(OrbitError) as error:
        parse(
            AssetWrite, {"name": "素材", "category_id": CATEGORY, "tag_ids": [CATEGORY, CATEGORY]}
        )
    assert error.value.code == "DUPLICATE_VALUE"


@pytest.mark.parametrize("numbers", [[1, 1], [2], [1, 3], [0, 1], [1, 2, 3]])
def test_completion_requires_exact_contiguous_parts(numbers):
    with pytest.raises(OrbitError):
        parse(
            CompleteUpload,
            {
                "size": PART_SIZE + 1,
                "sha256": "a" * 64,
                "parts": [{"part_number": n, "etag": "b" * 64} for n in numbers],
            },
        )


def test_unordered_parts_normalize_and_final_part_is_bounded():
    value = parse(
        CompleteUpload,
        {
            "size": PART_SIZE + 1,
            "sha256": "a" * 64,
            "parts": [{"part_number": n, "etag": "b" * 64} for n in [2, 1]],
        },
    )
    assert [p.part_number for p in value.parts] == [1, 2]
    assert expected_part_size(value.size, 2) == 1
    with pytest.raises(OrbitError):
        expected_part_size(value.size, 3)


@pytest.mark.parametrize(
    "mime,header",
    [
        ("image/jpeg", b"\xff\xd8\xff"),
        ("image/png", b"\x89PNG\r\n\x1a\n"),
        ("video/mp4", b"\x00\x00\x00\x18ftypmp42"),
    ],
)
def test_magic_cannot_be_replaced_by_extension(mime, header):
    verify_magic(mime, header)
    with pytest.raises(OrbitError):
        verify_magic(mime, b"<script>bad</script>")


def test_bulk_delete_duplicate_and_reason_boundaries():
    value = {"assets": [{"id": CATEGORY, "revision": 1}] * 2, "reason": "清理"}
    with pytest.raises(OrbitError) as error:
        parse(BulkDelete, value)
    assert error.value.code == "DUPLICATE_VALUE"
    with pytest.raises(OrbitError):
        parse(BulkDelete, {"assets": [{"id": CATEGORY, "revision": True}], "reason": "清理"})
