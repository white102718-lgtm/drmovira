"""真实ClamD流扫描；可信策略注入、双向版本核验与完整对象证据，未知绝不CLEAN。"""

import hashlib
import re
import socket
import struct
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from orbit_api.errors import OrbitError

MAX_BYTES = 500 * 1024 * 1024


@dataclass(frozen=True, repr=False)
class ClamdPolicy:
    port: int
    engine_version: str
    daily_db_version: int
    daily_db_built_at: datetime
    config_sha256: str
    max_file_bytes: int
    max_scan_bytes: int
    stream_max_bytes: int
    alert_exceeds_max: bool
    host: str = "127.0.0.1"
    max_db_age_seconds: int = 172800
    deadline_seconds: int = 150

    def validate(self, now):
        if (
            self.host != "127.0.0.1"
            or type(self.port) is not int
            or not 1 <= self.port <= 65535
            or not re.fullmatch(r"\d+\.\d+\.\d+", self.engine_version)
            or type(self.daily_db_version) is not int
            or self.daily_db_version < 1
            or not re.fullmatch(r"[0-9a-f]{64}", self.config_sha256)
            or any(
                type(value) is not int or not MAX_BYTES <= value <= 2 * 1024**3
                for value in (self.max_file_bytes, self.max_scan_bytes, self.stream_max_bytes)
            )
            or self.max_scan_bytes < self.max_file_bytes
            or self.alert_exceeds_max is not True
            or type(self.deadline_seconds) is not int
            or not 1 <= self.deadline_seconds <= 150
            or type(self.max_db_age_seconds) is not int
            or not 1 <= self.max_db_age_seconds <= 172800
        ):
            raise OrbitError(503, "ANTIVIRUS_POLICY_UNVERIFIED", "扫描配置未经完整验证")
        built = self.daily_db_built_at
        if not isinstance(built, datetime) or built.tzinfo is None:
            raise OrbitError(503, "ANTIVIRUS_DATABASE_UNVERIFIED", "病毒库构建时间未知")
        age = (now - built.astimezone(UTC)).total_seconds()
        if not 0 <= age <= self.max_db_age_seconds:
            raise OrbitError(503, "ANTIVIRUS_DATABASE_STALE", "病毒库过时或时间异常")


@dataclass(frozen=True, repr=False)
class ScanReceipt:
    result: str
    sha256: str
    byte_size: int
    started_at: datetime
    completed_at: datetime
    engine_version: str | None
    database_version: int | None
    database_built_at: datetime | None
    policy_sha256: str | None
    error_code: str | None


class ClamdMaterialScanner:
    def __init__(self, policy: ClamdPolicy):
        if not isinstance(policy, ClamdPolicy):
            raise ValueError("扫描器必须由可信配置构造，不接受请求字典")
        self.policy = policy

    @staticmethod
    def _timeout(connection, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OrbitError(503, "ANTIVIRUS_TIMEOUT", "病毒扫描超时")
        connection.settimeout(min(10, remaining))

    def _connect(self, deadline):
        self._remaining(deadline)
        return socket.create_connection(
            (self.policy.host, self.policy.port), timeout=min(2, deadline - time.monotonic())
        )

    @staticmethod
    def _remaining(deadline):
        if time.monotonic() >= deadline:
            raise OrbitError(503, "ANTIVIRUS_TIMEOUT", "病毒扫描超时")

    def _send(self, connection, data, deadline):
        self._timeout(connection, deadline)
        connection.sendall(data)

    def _record(self, connection, deadline):
        response = bytearray()
        while True:
            self._timeout(connection, deadline)
            data = connection.recv(1024)
            if not data:
                break
            response.extend(data)
            if len(response) > 8192:
                raise OrbitError(503, "ANTIVIRUS_PROTOCOL_INVALID", "扫描响应越界")
        if not response.endswith(b"\0") or response.count(0) != 1:
            raise OrbitError(503, "ANTIVIRUS_PROTOCOL_INVALID", "扫描结果不完整或含多个记录")
        return bytes(response[:-1])

    def _version(self, deadline):
        with self._connect(deadline) as connection:
            self._send(connection, b"zVERSION\0", deadline)
            reply = self._record(connection, deadline)
        matched = re.fullmatch(rb"ClamAV (\d+\.\d+\.\d+)/(\d+)/[^\r\n\0]+", reply)
        if (
            matched is None
            or matched[1].decode("ascii") != self.policy.engine_version
            or int(matched[2]) != self.policy.daily_db_version
        ):
            raise OrbitError(503, "ANTIVIRUS_VERSION_CHANGED", "实际扫描引擎或病毒库与可信策略不符")

    def scan(self, objects, tenant, upload, sha256, byte_size):
        started = datetime.now(UTC)
        outcome, error = "UNVERIFIED", None
        engine, database, built = None, None, None
        try:
            self.policy.validate(started)
            if (
                not isinstance(sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", sha256)
                or type(byte_size) is not int
                or not 1 <= byte_size <= MAX_BYTES
            ):
                raise OrbitError(409, "ANTIVIRUS_OBJECT_INVALID", "待扫描原对象清单无效")
            deadline = time.monotonic() + self.policy.deadline_seconds
            self._version(deadline)
            engine = self.policy.engine_version
            database, built = self.policy.daily_db_version, self.policy.daily_db_built_at
            digest, size = hashlib.sha256(), 0
            with objects.mutation_guard(tenant, upload):
                source = objects.original(tenant, upload)
                with source.open("rb") as stream, self._connect(deadline) as connection:
                    self._send(connection, b"zINSTREAM\0", deadline)
                    while True:
                        self._remaining(deadline)
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > byte_size or size > MAX_BYTES:
                            raise OrbitError(409, "ANTIVIRUS_OBJECT_CHANGED", "原对象尺寸已变化")
                        digest.update(chunk)
                        self._send(connection, struct.pack("!I", len(chunk)), deadline)
                        self._send(connection, chunk, deadline)
                    if size != byte_size or digest.hexdigest() != sha256:
                        raise OrbitError(409, "ANTIVIRUS_OBJECT_CHANGED", "原对象摘要或尺寸已变化")
                    self._send(connection, struct.pack("!I", 0), deadline)
                    reply = self._record(connection, deadline)
            if reply == b"stream: OK":
                outcome = "CLEAN"
            elif re.fullmatch(rb"stream: [^\r\n\0]+ FOUND", reply):
                if b"Heuristics.Limits.Exceeded" in reply:
                    raise OrbitError(503, "ANTIVIRUS_LIMIT_EXCEEDED", "扫描未覆盖完整对象")
                outcome, error = "INFECTED", "ANTIVIRUS_INFECTED"
            else:
                raise OrbitError(503, "ANTIVIRUS_PROTOCOL_INVALID", "扫描失败或结果未知")
            self._version(deadline)
            self.policy.validate(datetime.now(UTC))
        except OrbitError as problem:
            outcome, error = "UNVERIFIED", problem.code
        except TimeoutError:
            outcome, error = "UNVERIFIED", "ANTIVIRUS_TIMEOUT"
        except (OSError, ValueError, TypeError):
            outcome, error = "UNVERIFIED", "ANTIVIRUS_UNAVAILABLE"
        return ScanReceipt(
            outcome,
            sha256,
            byte_size,
            started,
            datetime.now(UTC),
            engine,
            database,
            built,
            self.policy.config_sha256,
            error,
        )


class UnavailableMaterialScanner:
    """缺可信配置是显式失败；绝不以测试或本地模式跳过扫描。"""

    def scan(self, objects, tenant, upload, sha256, byte_size):
        now = datetime.now(UTC)
        return ScanReceipt(
            "UNVERIFIED",
            sha256,
            byte_size,
            now,
            now,
            None,
            None,
            None,
            None,
            "ANTIVIRUS_UNAVAILABLE",
        )
