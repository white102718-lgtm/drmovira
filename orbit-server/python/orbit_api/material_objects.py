"""受控本地对象适配器：只允许服务端UUID键；生产对象存储尚未接入。"""

import hashlib
import os
import stat
from pathlib import Path
from uuid import UUID, uuid4

from orbit_api.errors import OrbitError
from orbit_api.material_contract import PART_SIZE, verify_magic


def _key(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError("对象键必须为服务端规范UUID") from None
    return value


def _regular(path, *, directory=False):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("对象目录不能包含链接或重解析点")
    if directory and not stat.S_ISDIR(info.st_mode):
        raise ValueError("对象目录无效")
    if not directory and not stat.S_ISREG(info.st_mode):
        raise ValueError("对象必须为普通文件")


class LocalMaterialObjects:
    """root只能来自可信启动配置，构造器不创建或清理未知目录。"""

    def __init__(self, root: Path):
        root = Path(root).absolute()
        for ancestor in (*reversed(root.parents), root):
            _regular(ancestor, directory=True)
        self.root = root

    def directory(self, tenant, upload):
        path = self.root
        for ancestor in (*reversed(path.parents), path):
            _regular(ancestor, directory=True)
        for component in (_key(tenant), _key(upload)):
            path = path / component
            path.mkdir(exist_ok=True)
            _regular(path, directory=True)
        return path

    def mutation_guard(self, tenant, upload):
        # 延迟导入避免对象适配器与生命周期模块循环初始化；不启用物理删除。
        from orbit_api.material_lifecycle_objects import LifecycleObjectFence

        return LifecycleObjectFence(self.root).mutation_guard(tenant, upload)

    def _existing_directory(self, tenant, upload):
        """纯读取解析不得mkdir，防止已回收对象被迟到读取重建空目录。"""
        for ancestor in (*reversed(self.root.parents), self.root):
            _regular(ancestor, directory=True)
        path = self.root
        for component in (_key(tenant), _key(upload)):
            path = path / component
            _regular(path, directory=True)
        return path

    def part_path(self, tenant, upload, number):
        if type(number) is not int or not 1 <= number <= 10000:
            raise ValueError("分片编号无效")
        return self.directory(tenant, upload) / f"part-{number:05d}"

    def put_part(self, tenant, upload, number, content, expected_size):
        with self.mutation_guard(tenant, upload):
            return self._put_part(tenant, upload, number, content, expected_size)

    def _put_part(self, tenant, upload, number, content, expected_size):
        if len(content) != expected_size or not 0 < expected_size <= PART_SIZE:
            raise OrbitError(422, "PART_SIZE_INVALID", "分片尺寸不符")
        target = self.part_path(tenant, upload, number)
        digest = hashlib.sha256(content).hexdigest()
        if target.exists():
            _regular(target)
            if target.stat().st_size != expected_size or self._hash_file(target)[0] != digest:
                raise OrbitError(409, "PART_CONFLICT", "相同分片已有不同内容")
            return digest
        # UUID临时键不使用原文件名；失败仅清理自身临时文件，不递归删除目录。
        temporary = target.with_name("temporary-" + str(uuid4()))
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, target)
        except FileExistsError:
            _regular(target)
            if self._hash_file(target)[0] != digest:
                raise OrbitError(409, "PART_CONFLICT", "相同分片已有不同内容") from None
        finally:
            temporary.unlink(missing_ok=True)
        return digest

    @staticmethod
    def _hash_file(path):
        digest, size = hashlib.sha256(), 0
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
                size += len(block)
        return digest.hexdigest(), size

    def assemble(self, tenant, upload, parts, size, sha256, mime):
        with self.mutation_guard(tenant, upload):
            return self._assemble(tenant, upload, parts, size, sha256, mime)

    def _assemble(self, tenant, upload, parts, size, sha256, mime):
        """流式合并，峰值内存不随500MiB视频增长；返回内部键，不泄露文件路径。"""
        directory = self.directory(tenant, upload)
        temporary = directory / ("temporary-" + str(uuid4()))
        target = directory / "original"
        digest, total, header = hashlib.sha256(), 0, b""
        try:
            with temporary.open("xb") as output:
                for part in parts:
                    path = self.part_path(tenant, upload, part.part_number)
                    try:
                        _regular(path)
                    except FileNotFoundError:
                        raise OrbitError(422, "PART_MISSING", "上传分片尚未齐全") from None
                    part_hash = hashlib.sha256()
                    with path.open("rb") as source:
                        while block := source.read(1024 * 1024):
                            total += len(block)
                            if total > size:
                                raise OrbitError(422, "FILE_SIZE_INVALID", "文件尺寸不符")
                            if len(header) < 64:
                                header += block[: 64 - len(header)]
                            digest.update(block)
                            part_hash.update(block)
                            output.write(block)
                    if part_hash.hexdigest() != part.etag:
                        raise OrbitError(422, "PART_HASH_INVALID", "分片摘要不符")
                if total != size or digest.hexdigest() != sha256:
                    raise OrbitError(422, "FILE_HASH_INVALID", "文件摘要或尺寸不符")
                verify_magic(mime, header)
                output.flush()
                os.fsync(output.fileno())
            if target.exists():
                _regular(target)
                if self._hash_file(target) != (sha256, size):
                    raise OrbitError(409, "OBJECT_CONFLICT", "已上传对象不一致")
            else:
                os.link(temporary, target)
            return f"{tenant}/{upload}/original"
        finally:
            temporary.unlink(missing_ok=True)

    def original(self, tenant, upload):
        path = self._existing_directory(tenant, upload) / "original"
        _regular(path)
        return path

    def preview(self, tenant, upload):
        path = self._existing_directory(tenant, upload) / "preview.jpg"
        _regular(path)
        return path
