"""可信profile与进程代际绑定；独立扩展，尚未接入Worker/030持久化。"""

import hashlib
import json
import re
import stat
import time
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from orbit_api.errors import OrbitError
from orbit_api.material_antivirus import ClamdMaterialScanner, ClamdPolicy, ScanReceipt

PROFILE_KEY = "ORBIT_PYTHON_MATERIAL_SCANNER_PROFILES"
_SHA = re.compile(r"[0-9a-f]{64}")
_SCAN_DEADLINE = ContextVar("material_runtime_scan_deadline", default=None)


def _bounded_deadline(deadline):
    active = _SCAN_DEADLINE.get()
    return min(active, deadline) if active is not None else deadline


def _check_deadline():
    active = _SCAN_DEADLINE.get()
    if active is not None and time.monotonic() >= active:
        raise _failure("ANTIVIRUS_TIMEOUT")


def _failure(code="ANTIVIRUS_RUNTIME_UNVERIFIED"):
    return OrbitError(503, code, "扫描实例或可信来源尚未完整验证")


def _utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC:
        raise ValueError
    return parsed


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError
        result[name] = value
    return result


@dataclass(frozen=True, repr=False)
class TrustedRuntimeProfile:
    profile_id: str
    revision: int
    instance_id: str
    pid: int
    created_at_us: int
    issued_at: datetime
    expires_at: datetime
    source_sha256: str
    executable: str
    executable_sha256: str
    config_file: str
    database_directory: str
    database_files: tuple[tuple[str, str], ...]
    policy: ClamdPolicy
    profile_sha256: str

    def validate_time(self, now):
        if not self.issued_at <= now < self.expires_at:
            raise _failure("ANTIVIRUS_RUNTIME_EXPIRED")


def read_runtime_profile(profile_id, values_provider=None):
    """provider只用于服务端显式注入；默认唯一指定私有文件，不读取通用环境变量。"""
    if values_provider is None:
        from config.orbit_runtime import private_values

        values_provider = private_values
    try:
        if not isinstance(profile_id, str) or not re.fullmatch(r"[a-z0-9_-]{1,40}", profile_id):
            raise ValueError
        raw = values_provider().get(PROFILE_KEY)
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > 256 * 1024:
            raise ValueError
        entries = json.loads(raw, object_pairs_hook=_unique)
        if not isinstance(entries, dict) or not 1 <= len(entries) <= 16:
            raise ValueError
        value = entries[profile_id]
        fields = {
            "revision",
            "instance_id",
            "pid",
            "created_at_us",
            "issued_at",
            "expires_at",
            "source_sha256",
            "executable",
            "executable_sha256",
            "config_file",
            "database_directory",
            "database_files",
            "policy",
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError
        for field in ("revision", "pid", "created_at_us"):
            if type(value[field]) is not int or not 1 <= value[field] <= 9_007_199_254_740_991:
                raise ValueError
        if str(UUID(value["instance_id"])) != value["instance_id"]:
            raise ValueError
        for field in ("source_sha256", "executable_sha256"):
            if not isinstance(value[field], str) or not _SHA.fullmatch(value[field]):
                raise ValueError
        for field in ("executable", "config_file", "database_directory"):
            if not isinstance(value[field], str) or not Path(value[field]).is_absolute():
                raise ValueError
        issued, expires = _utc(value["issued_at"]), _utc(value["expires_at"])
        if not 0 < (expires - issued).total_seconds() <= 86400:
            raise ValueError
        if value["created_at_us"] > int(issued.timestamp() * 1_000_000):
            raise ValueError
        files = value["database_files"]
        if not isinstance(files, dict) or set(files) != {"main.cvd", "daily.cvd", "bytecode.cvd"}:
            raise ValueError
        if any(not isinstance(v, str) or not _SHA.fullmatch(v) for v in files.values()):
            raise ValueError
        policy = dict(value["policy"])
        policy["daily_db_built_at"] = _utc(policy["daily_db_built_at"])
        configured = ClamdPolicy(**policy)
        configured.validate(datetime.now(UTC))
        fingerprint = hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return TrustedRuntimeProfile(
            profile_id,
            value["revision"],
            value["instance_id"],
            value["pid"],
            value["created_at_us"],
            issued,
            expires,
            value["source_sha256"],
            value["executable"],
            value["executable_sha256"],
            value["config_file"],
            value["database_directory"],
            tuple(sorted(files.items())),
            configured,
            fingerprint,
        )
    except (KeyError, TypeError, ValueError, OverflowError, OSError, RuntimeError, OrbitError):
        raise _failure("ANTIVIRUS_PROFILE_UNAVAILABLE") from None


def _safe_file(path, maximum):
    """拒逐级链接/reparse并限制哈希I/O；前后身份变化不视为同一可信文件。"""
    path = Path(path)
    _check_deadline()
    for item in (path, *path.parents):
        metadata = item.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise _failure()
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
        raise _failure()
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            _check_deadline()
            size += len(chunk)
            if size > maximum:
                raise _failure()
            digest.update(chunk)
    after = path.stat()

    def identity(s):
        return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns

    if identity(before) != identity(after) or size != before.st_size:
        raise _failure()
    return digest.hexdigest()


def _config_matches(profile):
    if _safe_file(profile.config_file, 65536) != profile.policy.config_sha256:
        raise _failure()
    selected = {}
    for line in Path(profile.config_file).read_text("utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        key, value = parts[0], parts[1] if len(parts) == 2 else ""
        if key == "Include":
            raise _failure()
        if key in {
            "TCPSocket",
            "TCPAddr",
            "DatabaseDirectory",
            "MaxFileSize",
            "MaxScanSize",
            "StreamMaxLength",
            "AlertExceedsMax",
        }:
            if key in selected:
                raise _failure()
            selected[key] = value.strip().strip('"')
    expected = {
        "TCPSocket": str(profile.policy.port),
        "TCPAddr": "127.0.0.1",
        "DatabaseDirectory": profile.database_directory,
        "AlertExceedsMax": "yes",
    }
    if any(selected.get(k) != v for k, v in expected.items()):
        raise _failure()
    for key, expected_size in (
        ("MaxFileSize", profile.policy.max_file_bytes),
        ("MaxScanSize", profile.policy.max_scan_bytes),
        ("StreamMaxLength", profile.policy.stream_max_bytes),
    ):
        matched = re.fullmatch(r"([1-9][0-9]*)([KMG]?)", selected.get(key, ""))
        if (
            not matched
            or int(matched[1]) * 1024 ** (" KMG".index(matched[2]) if matched[2] else 0)
            != expected_size
        ):
            raise _failure()


class PsutilRuntimeObserver:
    """只观察服务端钉住进程，不启动/停止任何服务；缺权限或依赖即拒绝。"""

    def _process(self, profile):
        import psutil

        _check_deadline()
        process = psutil.Process(profile.pid)
        if round(process.create_time() * 1_000_000) != profile.created_at_us:
            raise _failure()
        expected = Path(profile.executable).resolve()
        if Path(process.exe()).resolve() != expected:
            raise _failure()
        command = process.cmdline()
        if len(command) != 2 or Path(command[0]).resolve() != expected:
            raise _failure()
        if command[1] != "--config-file=" + profile.config_file:
            raise _failure()
        return process

    def verify(self, profile):
        process = self._process(profile)
        if _safe_file(profile.executable, 256 * 1024**2) != profile.executable_sha256:
            raise _failure()
        _config_matches(profile)
        for filename, expected in profile.database_files:
            if _safe_file(Path(profile.database_directory) / filename, 512 * 1024**2) != expected:
                raise _failure()
        listeners = {
            (item.laddr.ip, item.laddr.port)
            for item in process.net_connections(kind="tcp")
            if item.status == "LISTEN"
        }
        if listeners != {("127.0.0.1", profile.policy.port)}:
            raise _failure()
        self._process(profile)

    def verify_connection(self, profile, connection, deadline):
        client, server = connection.getsockname(), connection.getpeername()
        if server != ("127.0.0.1", profile.policy.port) or client[0] != "127.0.0.1":
            raise _failure()
        accept_deadline = min(deadline, time.monotonic() + 0.5)
        while time.monotonic() < accept_deadline:
            process = self._process(profile)
            for item in process.net_connections(kind="tcp"):
                if (
                    item.status == "ESTABLISHED"
                    and item.raddr
                    and ((item.laddr.ip, item.laddr.port), (item.raddr.ip, item.raddr.port))
                    == (server, client)
                ):
                    return
            time.sleep(min(0.01, max(0, accept_deadline - time.monotonic())))
        raise _failure("ANTIVIRUS_CONNECTION_UNVERIFIED")


@dataclass(frozen=True, repr=False)
class RuntimeScanProof:
    profile_id: str
    profile_revision: int
    instance_id: str
    profile_sha256: str
    source_sha256: str
    executable_sha256: str
    config_sha256: str
    created_at_us: int
    issued_at: datetime
    expires_at: datetime
    verified_before: datetime
    verified_after: datetime


@dataclass(frozen=True, repr=False)
class RuntimeScanResult:
    receipt: ScanReceipt
    proof: RuntimeScanProof | None


class ProcessBoundMaterialScanner(ClamdMaterialScanner):
    """显式返回双证据，禁止未接Worker时丢弃进程proof冒充原scanner。"""

    def __init__(self, profile_id, *, values_provider=None, observer=None):
        self.profile = read_runtime_profile(profile_id, values_provider)
        self.values_provider = values_provider
        self.observer = observer or PsutilRuntimeObserver()
        super().__init__(self.profile.policy)

    def _check(self):
        _check_deadline()
        current = read_runtime_profile(self.profile.profile_id, self.values_provider)
        if current != self.profile:
            raise _failure("ANTIVIRUS_PROFILE_CHANGED")
        self.profile.validate_time(datetime.now(UTC))
        self.observer.verify(self.profile)
        _check_deadline()

    def _timeout(self, connection, deadline):
        super()._timeout(connection, _bounded_deadline(deadline))

    def _remaining(self, deadline):
        super()._remaining(_bounded_deadline(deadline))

    def _connect(self, deadline):
        deadline = _bounded_deadline(deadline)
        connection = super()._connect(deadline)
        try:
            self.observer.verify_connection(self.profile, connection, deadline)
            return connection
        except Exception:
            connection.close()
            raise _failure("ANTIVIRUS_CONNECTION_UNVERIFIED") from None

    def scan(self, objects, tenant, upload, sha256, byte_size):
        started = datetime.now(UTC)
        token = _SCAN_DEADLINE.set(time.monotonic() + self.policy.deadline_seconds)
        receipt = None
        try:
            self._check()
            receipt = super().scan(objects, tenant, upload, sha256, byte_size)
            if receipt.error_code == "ANTIVIRUS_CONNECTION_UNVERIFIED":
                raise _failure()
            self._check()
            after = datetime.now(UTC)
            p = self.profile
            p.validate_time(after)
            return RuntimeScanResult(
                receipt,
                RuntimeScanProof(
                    p.profile_id,
                    p.revision,
                    p.instance_id,
                    p.profile_sha256,
                    p.source_sha256,
                    p.executable_sha256,
                    p.policy.config_sha256,
                    p.created_at_us,
                    p.issued_at,
                    p.expires_at,
                    started,
                    after,
                ),
            )
        except Exception:
            failed = receipt or ScanReceipt(
                "UNVERIFIED",
                sha256,
                byte_size,
                started,
                datetime.now(UTC),
                None,
                None,
                None,
                None,
                "ANTIVIRUS_RUNTIME_UNVERIFIED",
            )
            return RuntimeScanResult(
                replace(
                    failed,
                    result="UNVERIFIED",
                    error_code="ANTIVIRUS_RUNTIME_UNVERIFIED",
                    completed_at=datetime.now(UTC),
                ),
                None,
            )
        finally:
            _SCAN_DEADLINE.reset(token)
