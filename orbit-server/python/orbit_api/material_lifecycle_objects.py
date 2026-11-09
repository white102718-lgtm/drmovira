"""生命周期对象隔离协议；默认拒绝物理删除，所有真实写方接入后才可启用。"""

import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

from orbit_api.errors import OrbitError
from orbit_api.material_objects import LocalMaterialObjects, _key, _regular


class LifecycleObjectFence:
    def __init__(self, root: Path, *, writers_fenced=False):
        self.root = LocalMaterialObjects(root).root
        self.writers_fenced = writers_fenced

    def _state(self, tenant):
        _key(tenant)
        for ancestor in (*reversed(self.root.parents), self.root):
            _regular(ancestor, directory=True)
        directory = self.root
        for name in (".lifecycle", tenant):
            directory = directory / name
            directory.mkdir(exist_ok=True)
            _regular(directory, directory=True)
        return directory

    @contextmanager
    def _lock(self, tenant, upload, timeout=2):
        _key(upload)
        directory = self._state(tenant)
        target = directory / (upload + ".lock")
        if target.exists() or target.is_symlink():
            _regular(target)
        with target.open("a+b") as stream:
            _regular(target)
            if stream.seek(0, 2) == 0:
                stream.write(b"0")
                stream.flush()
            locked = False
            deadline = time.monotonic() + timeout
            try:
                while not locked:
                    try:
                        stream.seek(0)
                        if os.name == "nt":
                            import msvcrt

                            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl

                            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        locked = True
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise OrbitError(
                                409, "OBJECT_BUSY", "对象仍有进行中的安全操作"
                            ) from None
                        time.sleep(0.01)
                yield directory / (upload + ".tombstone")
            finally:
                if locked:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def mutation_guard(self, tenant, upload, *, timeout=2):
        """未来分片/合并/预览发布共同使用；墓碑一经持久化，旧对象UUID不能复活。"""
        with self._lock(tenant, upload, timeout) as marker:
            if marker.exists() or marker.is_symlink():
                _regular(marker)
                raise OrbitError(409, "OBJECT_EXPIRED", "对象已进入生命周期回收，不能继续写入")
            yield

    @staticmethod
    def _allowed(name):
        if name in {"original", "preview.jpg"}:
            return True
        if re.fullmatch(r"part-[0-9]{5}", name):
            return 1 <= int(name[5:]) <= 10000
        if name.startswith("temporary-"):
            _key(name.removeprefix("temporary-"))
            return True
        if name.startswith("preview-") and name.endswith(".jpg"):
            _key(name.removeprefix("preview-").removesuffix(".jpg"))
            return True
        return False

    def purge(self, tenant, upload, job, *, unlinker=None):
        """仅单个规范对象目录，先完整检查再逐普通文件删除；失败保留墓碑供重试。"""
        _key(tenant)
        _key(upload)
        _key(job)
        if not self.writers_fenced:
            raise OrbitError(503, "FENCE_NOT_INTEGRATED", "对象写入安全协议尚未全部接入")
        try:
            with self._lock(tenant, upload) as marker:
                if marker.exists() or marker.is_symlink():
                    _regular(marker)
                else:
                    with marker.open("xb") as stream:
                        stream.write(json.dumps({"version": 1, "job": job}).encode())
                        stream.flush()
                        os.fsync(stream.fileno())
                tenant_directory = self.root / tenant
                directory = tenant_directory / upload
                if not tenant_directory.exists() and not tenant_directory.is_symlink():
                    return 0
                _regular(tenant_directory, directory=True)
                if not directory.exists() and not directory.is_symlink():
                    return 0
                _regular(directory, directory=True)
                entries = []
                for entry in directory.iterdir():
                    if len(entries) >= 10010 or not self._allowed(entry.name):
                        raise OrbitError(
                            409, "OBJECT_LAYOUT_INVALID", "对象包含未知条目或清理上限外内容"
                        )
                    _regular(entry)
                    entries.append(entry)
                for entry in entries:
                    _regular(entry)
                    (unlinker or Path.unlink)(entry)
                directory.rmdir()
                return len(entries)
        except OrbitError:
            raise
        except (OSError, ValueError):
            raise OrbitError(503, "LIFECYCLE_DELETE_FAILED", "对象回收未完成，稍后重试") from None
