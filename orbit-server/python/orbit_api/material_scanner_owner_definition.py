"""受控启动定义：只读指定私有命名空间，不接受租户请求或自动发现已有进程。"""

import hashlib
import json
import re
import stat
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from orbit_api.configuration import short_text
from orbit_api.errors import OrbitError
from orbit_api.material_antivirus import ClamdPolicy

OWNER_DEFINITIONS_KEY = "ORBIT_PYTHON_MATERIAL_SCANNER_OWNER_DEFINITIONS"
MAX_REVISION = 9_007_199_254_740_991


def owner_error(code="SCANNER_OWNER_UNAVAILABLE"):
    return OrbitError(503, code, "受控扫描实例尚不可用，请联系服务器管理员")


def check_budget(deadline):
    if time.monotonic() >= deadline:
        raise owner_error("SCANNER_OWNER_DEADLINE")


def safe_path(path, *, directory=False):
    """逐级拒绝链接/reparse；不创建目录，不把用户路径转换成可信目录。"""
    if not isinstance(path, Path) or not path.is_absolute():
        raise owner_error("SCANNER_OWNER_SOURCE_INVALID")
    if str(path).startswith(("\\\\", "//")):
        raise owner_error("SCANNER_OWNER_SOURCE_INVALID")
    for item in (path, *path.parents):
        data = item.lstat()
        if stat.S_ISLNK(data.st_mode) or getattr(data, "st_file_attributes", 0) & 0x400:
            raise owner_error("SCANNER_OWNER_SOURCE_INVALID")
    data = path.stat()
    if not (stat.S_ISDIR(data.st_mode) if directory else stat.S_ISREG(data.st_mode)):
        raise owner_error("SCANNER_OWNER_SOURCE_INVALID")
    return path.resolve(strict=True)


def file_hash(path, maximum, deadline):
    check_budget(deadline)
    resolved = safe_path(path)
    before = resolved.stat()
    if not 0 < before.st_size <= maximum:
        raise owner_error("SCANNER_OWNER_SOURCE_INVALID")
    result, size = hashlib.sha256(), 0
    with resolved.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            check_budget(deadline)
            size += len(block)
            if size > maximum:
                raise owner_error("SCANNER_OWNER_SOURCE_INVALID")
            result.update(block)
    after = resolved.stat()

    def identity(value):
        return (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )

    if identity(before) != identity(after) or size != before.st_size:
        raise owner_error("SCANNER_OWNER_SOURCE_CHANGED")
    return result.hexdigest()


@dataclass(frozen=True, repr=False)
class ScannerOwnerDefinition:
    profile_id: str
    revision: int
    label: str
    installation_root: Path
    owned_root: Path
    executable: Path
    executable_sha256: str
    config_file: Path
    config_sha256: str
    database_directory: Path
    database_files: tuple[tuple[str, str], ...]
    release_receipt_file: Path
    release_receipt_sha256: str
    issued_at: datetime
    expires_at: datetime
    policy: ClamdPolicy
    proof_ttl_seconds: int = 300
    startup_seconds: int = 30
    shutdown_seconds: int = 5

    def validate(self, now):
        try:
            if not re.fullmatch(r"[a-z0-9_-]{1,40}", self.profile_id):
                raise ValueError
            if type(self.revision) is not int or not 1 <= self.revision <= MAX_REVISION:
                raise ValueError
            if short_text(self.label, 80, "/label") != self.label or any(
                c in self.label for c in "\\/"
            ):
                raise ValueError
            for value, maximum in (
                (self.proof_ttl_seconds, 86400),
                (self.startup_seconds, 120),
                (self.shutdown_seconds, 30),
            ):
                if type(value) is not int or not 1 <= value <= maximum:
                    raise ValueError
            if (
                not self.issued_at <= now < self.expires_at
                or not 0 < (self.expires_at - self.issued_at).total_seconds() <= 86400
            ):
                raise ValueError
            if any(
                not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in (
                    self.executable_sha256,
                    self.config_sha256,
                    self.release_receipt_sha256,
                )
            ):
                raise ValueError
            if len(self.database_files) != 3 or set(dict(self.database_files)) != {
                "main.cvd",
                "daily.cvd",
                "bytecode.cvd",
            }:
                raise ValueError
            if any(not re.fullmatch(r"[0-9a-f]{64}", value) for _, value in self.database_files):
                raise ValueError
            for value in (
                self.installation_root,
                self.owned_root,
                self.executable,
                self.config_file,
                self.database_directory,
                self.release_receipt_file,
            ):
                if not isinstance(value, Path) or not value.is_absolute():
                    raise ValueError
            self.policy.validate(now)
            if self.policy.config_sha256 != self.config_sha256:
                raise ValueError
        except (ValueError, TypeError, AttributeError, OrbitError):
            raise owner_error("SCANNER_OWNER_DEFINITION_INVALID") from None


def verify_owner_files(definition, deadline):
    """重验服务器钉住的发行审批回执/实际字节；不将自报verified布尔值当GPG证明。"""
    definition.validate(datetime.now(UTC))
    installation = safe_path(definition.installation_root, directory=True)
    owned = safe_path(definition.owned_root, directory=True)
    database = safe_path(definition.database_directory, directory=True)
    if installation == owned or not database.is_relative_to(installation):
        raise owner_error("SCANNER_OWNER_SOURCE_INVALID")
    for path, root in (
        (definition.executable, installation),
        (definition.release_receipt_file, installation),
        (definition.config_file, owned),
    ):
        if not safe_path(path).is_relative_to(root):
            raise owner_error("SCANNER_OWNER_SOURCE_INVALID")
    entries = (
        (definition.executable, definition.executable_sha256, 256 * 1024**2),
        (definition.config_file, definition.config_sha256, 65536),
        (definition.release_receipt_file, definition.release_receipt_sha256, 1024 * 1024),
    )
    for path, expected, maximum in entries:
        if file_hash(path, maximum, deadline) != expected:
            raise owner_error("SCANNER_OWNER_SOURCE_CHANGED")
    for name, expected in definition.database_files:
        if file_hash(database / name, 512 * 1024**2, deadline) != expected:
            raise owner_error("SCANNER_OWNER_SOURCE_CHANGED")
    # 最小foreground配置不允许额外文件日志/PID文件/Include/远程监听等未受控副作用。
    selected = {}
    allowed = {
        "DatabaseDirectory",
        "TCPSocket",
        "TCPAddr",
        "Foreground",
        "MaxFileSize",
        "MaxScanSize",
        "StreamMaxLength",
        "AlertExceedsMax",
        "MaxScanTime",
        "MaxThreads",
        "MaxQueue",
        "TemporaryDirectory",
    }
    with definition.config_file.open("rb") as stream:
        raw_config = stream.read(65537)
    if (
        len(raw_config) > 65536
        or hashlib.sha256(raw_config).hexdigest() != definition.config_sha256
    ):
        raise owner_error("SCANNER_OWNER_SOURCE_CHANGED")
    for line in raw_config.decode("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(" ")
        if not separator or key not in allowed or key in selected:
            raise owner_error("SCANNER_OWNER_CONFIG_INVALID")
        selected[key] = value.strip().strip('"')
    expected = {
        "DatabaseDirectory": str(definition.database_directory),
        "TCPSocket": str(definition.policy.port),
        "TCPAddr": "127.0.0.1",
        "Foreground": "yes",
        "AlertExceedsMax": "yes",
        "TemporaryDirectory": str(definition.owned_root),
    }
    if any(selected.get(key) != value for key, value in expected.items()):
        raise owner_error("SCANNER_OWNER_CONFIG_INVALID")
    for key, maximum in (("MaxThreads", 4), ("MaxQueue", 16), ("MaxScanTime", 120000)):
        raw = selected.get(key, "")
        if not re.fullmatch(r"[1-9][0-9]*", raw) or not 1 <= int(raw) <= maximum:
            raise owner_error("SCANNER_OWNER_CONFIG_INVALID")
    for key, maximum in (
        ("MaxFileSize", definition.policy.max_file_bytes),
        ("MaxScanSize", definition.policy.max_scan_bytes),
        ("StreamMaxLength", definition.policy.stream_max_bytes),
    ):
        raw = re.fullmatch(r"([1-9][0-9]*)([KMG]?)", selected.get(key, ""))
        if not raw or int(raw[1]) * 1024 ** (" KMG".index(raw[2]) if raw[2] else 0) != maximum:
            raise owner_error("SCANNER_OWNER_CONFIG_INVALID")
    check_budget(deadline)
    return hashlib.sha256(
        json.dumps(
            {
                "profile_id": definition.profile_id,
                "revision": definition.revision,
                "executable": definition.executable_sha256,
                "config": definition.config_sha256,
                "databases": definition.database_files,
                "release_receipt": definition.release_receipt_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
