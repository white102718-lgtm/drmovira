"""显式注册服务端扫描实例；公开候选仅含标识和标签，绝不采用客户端连接参数。"""

import asyncio
import base64
import hashlib
import re
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

from orbit_api.configuration import short_text
from orbit_api.errors import OrbitError
from orbit_api.material_antivirus_runtime import (
    ProcessBoundMaterialScanner,
    RuntimeScanResult,
    TrustedRuntimeProfile,
    read_runtime_profile,
)


@dataclass(frozen=True, repr=False)
class ScannerBinding:
    scanner: ProcessBoundMaterialScanner
    profile: TrustedRuntimeProfile
    generation: str
    label: str


@dataclass(frozen=True, repr=False)
class ScannerProbeResult:
    status: str
    message: str
    binding: ScannerBinding | None = None


class MaterialScannerRegistry:
    """只允许受信启动器显式发布已绑定实例；注册本身不能冒充真实扫描。"""

    def __init__(self):
        self._entries = {}
        self._lock = threading.RLock()
        self._probe_slot = threading.BoundedSemaphore(1)

    def publish(self, scanner, label):
        if not isinstance(scanner, ProcessBoundMaterialScanner):
            raise ValueError("只接受绑定实际运行实例的扫描器")
        if not isinstance(label, str):
            raise ValueError("候选标签必须是受控简短文本")
        try:
            label = short_text(label, 80, "/label")
        except OrbitError:
            raise ValueError("候选标签必须是受控简短文本") from None
        if "\\" in label or "/" in label:
            raise ValueError("候选标签不能包含路径分隔符")
        binding = ScannerBinding(scanner, scanner.profile, str(uuid4()), label)
        with self._lock:
            if len(self._entries) >= 16 and scanner.profile.profile_id not in self._entries:
                raise ValueError("扫描候选数量超限")
            self._entries[scanner.profile.profile_id] = binding
        return binding

    def withdraw(self, profile_id):
        with self._lock:
            self._entries.pop(profile_id, None)

    def same_generation(self, binding):
        """仅复核注册代际；历史扫描有效期不转成素材读取或媒体完成的TTL。"""
        with self._lock:
            return self._entries.get(binding.profile.profile_id) is binding

    def resolve(self, profile_id):
        if not isinstance(profile_id, str) or not re.fullmatch(r"[a-z0-9_-]{1,40}", profile_id):
            raise OrbitError(
                422, "SCANNER_PROFILE_INVALID", "请选择有效的扫描候选", "/settings/profileId"
            )
        with self._lock:
            binding = self._entries.get(profile_id)
        if binding is None:
            raise OrbitError(
                422,
                "SCANNER_PROFILE_UNAVAILABLE",
                "扫描候选不存在或尚未由服务端启动",
                "/settings/profileId",
            )
        if not binding.profile.issued_at <= datetime.now(UTC) < binding.profile.expires_at:
            raise OrbitError(503, "SCANNER_PROFILE_UNAVAILABLE", "扫描候选来源证明已失效")
        return binding

    def verify(self, binding, *, source=True):
        current = self.resolve(binding.profile.profile_id)
        if not source:
            if current is not binding:
                raise OrbitError(409, "SCANNER_PROFILE_CHANGED", "扫描实例已变化，请重新操作")
            return
        try:
            matching = (
                read_runtime_profile(binding.profile.profile_id, binding.scanner.values_provider)
                == binding.profile
            )
        except Exception:
            matching = False
        if current is not binding or not matching:
            raise OrbitError(409, "SCANNER_PROFILE_CHANGED", "扫描实例已变化，请重新操作")

    def candidates(self):
        with self._lock:
            entries = sorted(self._entries.items())
        now = datetime.now(UTC)
        return [
            {
                "id": key,
                "label": value.label,
                "availability": "READY"
                if value.profile.issued_at <= now < value.profile.expires_at
                else "UNAVAILABLE",
            }
            for key, value in entries
        ]

    async def probe(self, enabled, settings):
        if not enabled:
            return ScannerProbeResult("BLOCKED", "请先启用素材扫描配置")
        try:
            binding = self.resolve(settings.get("profileId"))
        except OrbitError:
            return ScannerProbeResult("BLOCKED", "服务端扫描候选尚不可用")
        if not self._probe_slot.acquire(blocking=False):
            raise OrbitError(409, "SCANNER_PROBE_BUSY", "扫描安全测试正在进行，请稍后重试")

        def actual_probe():
            try:
                # 固定安全PNG只存在内存；不把请求参数当作文件、路径或网络地址。
                content = base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5n8AAAAASUVORK5CYII="
                )
                tenant, upload = str(uuid4()), str(uuid4())

                class Source:
                    def open(self, mode):
                        if mode != "rb":
                            raise ValueError
                        return BytesIO(content)

                class Objects:
                    def original(self, current_tenant, current_upload):
                        if (current_tenant, current_upload) != (tenant, upload):
                            raise ValueError
                        return Source()

                    def mutation_guard(self, current_tenant, current_upload):
                        if (current_tenant, current_upload) != (tenant, upload):
                            raise ValueError
                        return nullcontext()

                self.verify(binding)
                result = binding.scanner.scan(
                    Objects(), tenant, upload, hashlib.sha256(content).hexdigest(), len(content)
                )
                self.verify(binding)
                if (
                    not isinstance(result, RuntimeScanResult)
                    or result.proof is None
                    or result.receipt.result != "CLEAN"
                ):
                    return ScannerProbeResult("FAILED", "实际安全文件扫描未通过")
                from orbit_api.material_runtime_store import validate_runtime_binding

                validate_runtime_binding(
                    {
                        "tenant_id": tenant,
                        "asset_id": str(uuid4()),
                        "claim_id": str(uuid4()),
                        "owner_user_id": str(uuid4()),
                        "owner_team_id": str(uuid4()),
                        "actor_id": 1,
                        "actor_auth_version": 1,
                        "revision": 1,
                        "byte_size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "scope_digest": "0" * 64,
                    },
                    result,
                    binding.profile,
                    datetime.now(UTC),
                )
                return ScannerProbeResult(
                    "READ_VERIFIED", "实际安全PNG扫描与运行实例复核通过", binding
                )
            except Exception:
                return ScannerProbeResult("FAILED", "实际扫描或运行实例复核失败")
            finally:
                self._probe_slot.release()

        # 请求取消不释放仍在真实扫描的槽位；线程最终退出时释放，避免无界叠加。
        return await asyncio.shield(asyncio.create_task(asyncio.to_thread(actual_probe)))


EMPTY_SCANNER_REGISTRY = MaterialScannerRegistry()


def scanner_registry(request):
    registry = getattr(request.app.state, "material_scanner_registry", None)
    return registry if isinstance(registry, MaterialScannerRegistry) else EMPTY_SCANNER_REGISTRY
