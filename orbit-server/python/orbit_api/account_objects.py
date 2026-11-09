"""导入原始文本的受控本机对象适配器；只接收服务端UUID键，不暴露路径。"""

import hashlib
import os
import stat
from pathlib import Path
from uuid import UUID, uuid4


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("对象键必须为服务端规范UUID")
    return value


def _directory(path):
    for part in (*reversed(path.parents), path):
        attributes = part.lstat()
        if (
            not stat.S_ISDIR(attributes.st_mode)
            or stat.S_ISLNK(attributes.st_mode)
            or getattr(attributes, "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("原始输入对象目录不能包含链接或重解析点")


class AccountImportObjects:
    """可信root必须预先存在；单对象不超过80KB，不递归删除任何目录。"""

    def __init__(self, root):
        if not Path(root).is_absolute():
            raise ValueError("原始输入对象根必须为可信绝对路径")
        self.root = Path(root).absolute()
        _directory(self.root)

    def _path(self, tenant, identifier, *, create=True):
        _directory(self.root)
        directory = self.root / _uuid(tenant)
        if create:
            directory.mkdir(exist_ok=True)
        _directory(directory)
        return directory / _uuid(identifier)

    def put(self, tenant, identifier, value):
        from orbit_api.account_contract import tokenize

        tokenize(value)
        content = value.encode("utf-8")
        target = self._path(tenant, identifier)
        temporary = target.with_name(str(uuid4()))
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            # 不覆盖既有对象；对象UUID只由服务端生成，相同键冲突不能静默替换原始输入。
            os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return hashlib.sha256(content).hexdigest()

    def read(self, tenant, identifier, expected_hash):
        path = self._path(tenant, identifier, create=False)
        attributes = path.lstat()
        if (
            not stat.S_ISREG(attributes.st_mode)
            or stat.S_ISLNK(attributes.st_mode)
            or getattr(attributes, "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("原始输入对象必须是普通文件")
        if not 1 <= attributes.st_size <= 80000:
            raise ValueError("原始输入对象大小无效")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValueError("原始输入对象摘要不符")
        return content.decode("utf-8")
