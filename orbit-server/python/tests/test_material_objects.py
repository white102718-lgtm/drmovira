"""使用真实隔离临时文件验证对象读写、摘要、魔数及图片衍生，无真实云操作。"""

import hashlib
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

from orbit_api.errors import OrbitError
from orbit_api.material_contract import CompletedPart
from orbit_api.material_objects import LocalMaterialObjects
from orbit_api.material_processing import process_material


@pytest.fixture
def fixture(tmp_path):
    return LocalMaterialObjects(tmp_path), str(uuid4()), str(uuid4())


def png():
    output = BytesIO()
    Image.new("RGB", (50, 40), "red").save(output, "PNG")
    return output.getvalue()


def assemble(objects, tenant, upload, data, *, sha=None, mime="image/png"):
    digest = objects.put_part(tenant, upload, 1, data, len(data))
    return objects.assemble(
        tenant, upload, [CompletedPart(part_number=1, etag=digest)], len(data), sha or digest, mime
    )


def test_real_image_hash_part_replay_decode_and_preview(fixture):
    objects, tenant, upload = fixture
    data = png()
    internal_key = assemble(objects, tenant, upload, data)
    assert internal_key == f"{tenant}/{upload}/original"
    assert assemble(objects, tenant, upload, data) == internal_key
    result = process_material(objects, tenant, upload, "image/png")
    assert (result.width, result.height, result.duration) == (50, 40, None)
    with Image.open(objects.preview(tenant, upload)) as preview:
        assert preview.format == "JPEG" and preview.size == (50, 40)


def test_part_content_conflict_does_not_overwrite(fixture):
    objects, tenant, upload = fixture
    objects.put_part(tenant, upload, 1, b"abcd", 4)
    with pytest.raises(OrbitError) as error:
        objects.put_part(tenant, upload, 1, b"efgh", 4)
    assert error.value.code == "PART_CONFLICT"
    assert objects.part_path(tenant, upload, 1).read_bytes() == b"abcd"


@pytest.mark.parametrize("bad", ["../secret", "C:/secret", "", "a" * 36])
def test_paths_are_not_accepted(fixture, bad):
    objects, tenant, _ = fixture
    with pytest.raises(ValueError):
        objects.directory(tenant, bad)


def test_no_original_published_after_hash_or_magic_failure(fixture):
    objects, tenant, upload = fixture
    with pytest.raises(OrbitError):
        assemble(objects, tenant, upload, png(), sha="0" * 64)
    assert not (objects.directory(tenant, upload) / "original").exists()
    other = str(uuid4())
    with pytest.raises(OrbitError) as error:
        assemble(objects, tenant, other, b"<html>not an image</html>")
    assert error.value.code == "FILE_SIGNATURE_INVALID"
    assert not (objects.directory(tenant, other) / "original").exists()


def test_signature_only_image_never_becomes_ready(fixture):
    objects, tenant, upload = fixture
    assemble(objects, tenant, upload, b"\x89PNG\r\n\x1a\n" + b"bad" * 100)
    with pytest.raises(OrbitError) as error:
        process_material(objects, tenant, upload, "image/png")
    assert error.value.code == "IMAGE_DECODE_FAILED"
    assert not (objects.directory(tenant, upload) / "preview.jpg").exists()


def test_jpeg_orientation_uses_display_dimensions_and_strips_exif(fixture):
    objects, tenant, upload = fixture
    buffer = BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "用户原始图片备注"
    Image.new("RGB", (40, 20), "red").save(buffer, "JPEG", exif=exif)
    assemble(objects, tenant, upload, buffer.getvalue(), mime="image/jpeg")
    actual = process_material(objects, tenant, upload, "image/jpeg")
    assert (actual.width, actual.height) == (20, 40)
    with Image.open(objects.preview(tenant, upload)) as preview:
        assert preview.size == (20, 40) and not preview.getexif()


def test_owners_never_share_object_keys(fixture):
    objects, tenant, upload = fixture
    data = png()
    assemble(objects, tenant, upload, data)
    other_upload = str(uuid4())
    assemble(objects, tenant, other_upload, data)
    assert objects.original(tenant, upload) != objects.original(tenant, other_upload)
    assert (
        hashlib.sha256(objects.original(tenant, upload).read_bytes()).hexdigest()
        == hashlib.sha256(data).hexdigest()
    )
