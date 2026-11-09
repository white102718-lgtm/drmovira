"""真实独占临时文件生命周期guard；不操作共享对象或数据库。"""

from pathlib import Path
from uuid import uuid4

import pytest

from orbit_api.errors import OrbitError
from orbit_api.material_lifecycle_objects import LifecycleObjectFence
from orbit_api.material_objects import LocalMaterialObjects


@pytest.fixture
def objects(tmp_path):
    tenant, upload = str(uuid4()), str(uuid4())
    directory = LocalMaterialObjects(tmp_path).directory(tenant, upload)
    return tmp_path, tenant, upload, directory


def test_unintegrated_protocol_never_deletes_existing_object(objects):
    root, tenant, upload, directory = objects
    (directory / "original").write_bytes(b"immutable")
    with pytest.raises(OrbitError) as error:
        LifecycleObjectFence(root).purge(tenant, upload, str(uuid4()))
    assert error.value.code == "FENCE_NOT_INTEGRATED"
    assert (directory / "original").read_bytes() == b"immutable"


def test_real_purge_retains_tombstone_and_prevents_uuid_revival(objects):
    root, tenant, upload, directory = objects
    for name in ("original", "preview.jpg", "part-00001", "temporary-" + str(uuid4())):
        (directory / name).write_bytes(b"controlled")
    fence = LifecycleObjectFence(root, writers_fenced=True)
    assert fence.purge(tenant, upload, str(uuid4())) == 4
    assert not directory.exists()
    assert fence.purge(tenant, upload, str(uuid4())) == 0
    with pytest.raises(OrbitError) as error, fence.mutation_guard(tenant, upload):
        raise AssertionError("墓碑后不能进入写入区")
    assert error.value.code == "OBJECT_EXPIRED"
    marker = root / ".lifecycle" / tenant / (upload + ".tombstone")
    assert marker.is_file()


def test_partial_real_delete_failure_can_retry_without_false_done(objects):
    root, tenant, upload, directory = objects
    (directory / "original").write_bytes(b"one")
    (directory / "preview.jpg").write_bytes(b"two")
    fence = LifecycleObjectFence(root, writers_fenced=True)
    removed = []

    def fail_second(path):
        if removed:
            raise PermissionError("fixture injected filesystem refusal")
        Path.unlink(path)
        removed.append(path.name)

    with pytest.raises(OrbitError) as error:
        fence.purge(tenant, upload, str(uuid4()), unlinker=fail_second)
    assert error.value.code == "LIFECYCLE_DELETE_FAILED"
    assert len(list(directory.iterdir())) == 1
    assert fence.purge(tenant, upload, str(uuid4())) == 1
    assert not directory.exists()


@pytest.mark.parametrize("name", ["unknown-user-file", "part-00000", "part-10001"])
def test_unknown_entries_reject_whole_preflight_before_any_delete(objects, name):
    root, tenant, upload, directory = objects
    (directory / "original").write_bytes(b"keep")
    (directory / name).write_bytes(b"unexpected")
    with pytest.raises(OrbitError) as error:
        LifecycleObjectFence(root, writers_fenced=True).purge(tenant, upload, str(uuid4()))
    assert error.value.code == "OBJECT_LAYOUT_INVALID"
    assert (directory / "original").read_bytes() == b"keep"


def test_nested_directory_never_recursively_deletes(objects):
    root, tenant, upload, directory = objects
    (directory / "temporary-folder").mkdir()
    with pytest.raises(OrbitError):
        LifecycleObjectFence(root, writers_fenced=True).purge(tenant, upload, str(uuid4()))
    assert (directory / "temporary-folder").is_dir()


@pytest.mark.parametrize("bad", ["../outside", "C:/outside", "", "0" * 36])
def test_lifecycle_never_accepts_arbitrary_object_path(objects, bad):
    root, tenant, upload, directory = objects
    with pytest.raises(ValueError):
        LifecycleObjectFence(root, writers_fenced=True).purge(tenant, bad, str(uuid4()))
    assert directory.is_dir()


def test_real_process_guard_is_exclusive_and_released_after_process_death(objects):
    import os
    import subprocess
    import sys

    root, tenant, upload, _ = objects
    python_root = Path(__file__).resolve().parents[1]
    code = """import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from orbit_api.material_lifecycle_objects import LifecycleObjectFence
with LifecycleObjectFence(Path(sys.argv[2])).mutation_guard(sys.argv[3],sys.argv[4]):
    print('GUARD_READY',flush=True)
    time.sleep(10)
"""
    system = os.environ.get("SystemRoot", "C:/Windows")
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(python_root), str(root), tenant, upload],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"SystemRoot": system, "WINDIR": system, "PYTHONIOENCODING": "utf-8"},
    )
    fence = LifecycleObjectFence(root)
    try:
        assert child.stdout.readline().strip() == b"GUARD_READY"
        with pytest.raises(OrbitError) as error, fence.mutation_guard(tenant, upload, timeout=0.05):
            raise AssertionError("另一个进程持有对象guard时不能进入")
        assert error.value.code == "OBJECT_BUSY"
    finally:
        child.kill()
        child.communicate(timeout=5)
    with fence.mutation_guard(tenant, upload):
        pass


def test_all_integrated_write_paths_refuse_tombstone_and_reads_do_not_recreate(objects):
    from io import BytesIO

    from PIL import Image

    from orbit_api.material_contract import CompletedPart
    from orbit_api.material_processing import process_material

    root, tenant, upload, directory = objects
    adapter = LocalMaterialObjects(root)
    buffer = BytesIO()
    Image.new("RGB", (16, 12), "red").save(buffer, "PNG")
    data = buffer.getvalue()
    digest = adapter.put_part(tenant, upload, 1, data, len(data))
    parts = [CompletedPart(part_number=1, etag=digest)]
    adapter.assemble(tenant, upload, parts, len(data), digest, "image/png")
    process_material(adapter, tenant, upload, "image/png")
    LifecycleObjectFence(root, writers_fenced=True).purge(tenant, upload, str(uuid4()))
    for operation in (
        lambda: adapter.put_part(tenant, upload, 1, data, len(data)),
        lambda: adapter.assemble(tenant, upload, parts, len(data), digest, "image/png"),
        lambda: process_material(adapter, tenant, upload, "image/png"),
    ):
        with pytest.raises(OrbitError) as error:
            operation()
        assert error.value.code == "OBJECT_EXPIRED"
        assert not directory.exists()
    for read in (adapter.original, adapter.preview):
        with pytest.raises(FileNotFoundError):
            read(tenant, upload)
        assert not directory.exists()
