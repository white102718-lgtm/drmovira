"""真实临时目录验证原始输入留存与完整性，不修改用户预览或对象目录。"""

import hashlib
from uuid import uuid4

import pytest

from orbit_api.account_objects import AccountImportObjects


def test_original_unicode_text_roundtrips_and_object_is_immutable(tmp_path):
    objects = AccountImportObjects(tmp_path)
    tenant, identifier = str(uuid4()), str(uuid4())
    raw = "act_0001，0001\r\n  bad😀"
    digest = objects.put(tenant, identifier, raw)
    assert digest == hashlib.sha256(raw.encode()).hexdigest()
    assert objects.read(tenant, identifier, digest) == raw
    with pytest.raises(FileExistsError):
        objects.put(tenant, identifier, "999")
    assert objects.read(tenant, identifier, digest) == raw


def test_object_hash_mismatch_is_rejected(tmp_path):
    objects = AccountImportObjects(tmp_path)
    tenant, identifier = str(uuid4()), str(uuid4())
    objects.put(tenant, identifier, "001")
    with pytest.raises(ValueError, match="摘要"):
        objects.read(tenant, identifier, "0" * 64)


@pytest.mark.parametrize("identifier", ["../escape", "x/..", "not-a-uuid"])
def test_object_key_cannot_escape_owned_directory(tmp_path, identifier):
    with pytest.raises(ValueError):
        AccountImportObjects(tmp_path).put(str(uuid4()), identifier, "1")


def test_root_must_exist_and_cannot_be_a_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        AccountImportObjects(tmp_path / "absent")
    file = tmp_path / "file"
    file.write_text("existing")
    with pytest.raises(ValueError):
        AccountImportObjects(file)
    assert file.read_text() == "existing"
