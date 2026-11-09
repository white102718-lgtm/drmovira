"""单一所有者显式启动/停止状态机；未实例化调用时无进程、线程或环境发现副作用。"""

import asyncio
import hashlib
import inspect
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from orbit_api.material_antivirus_runtime import PROFILE_KEY, ProcessBoundMaterialScanner
from orbit_api.material_scanner_owner_definition import (
    ScannerOwnerDefinition,
    owner_error,
    verify_owner_files,
)
from orbit_api.material_scanner_owner_process import WindowsOwnerProcessAdapter
from orbit_api.material_scanner_registry import MaterialScannerRegistry, ScannerProbeResult


async def actual_owner_health(scanner, deadline):
    """健康检查在不对客户端公开的临时registry执行实际内存安全PNG/proof验证。"""
    private = MaterialScannerRegistry()
    private.publish(scanner, "受控实例启动健康检查")
    while True:
        # clamd恢复线程后仍需加载病毒库；只有有界启动窗口内真实READ_VERIFIED才可发布。
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise owner_error("SCANNER_OWNER_HEALTH_FAILED")
        result = await private.probe(True, {"profileId": scanner.profile.profile_id})
        if result.status == "READ_VERIFIED":
            return result
        await asyncio.sleep(min(0.1, max(0, deadline - time.monotonic())))


@dataclass(repr=False)
class OwnedScanner:
    definition: ScannerOwnerDefinition
    process: object
    scanner: ProcessBoundMaterialScanner
    binding: object
    source_digest: str


class MaterialScannerOwner:
    """只在一个显式所有者进程使用；不提供HTTP入口、自动重启或多进程共享承诺。"""

    def __init__(
        self,
        registry,
        *,
        audit_sink,
        adapter=None,
        files_verifier=verify_owner_files,
        scanner_factory=ProcessBoundMaterialScanner,
        health=actual_owner_health,
        clock=None,
        monotonic=None,
    ):
        if not isinstance(registry, MaterialScannerRegistry):
            raise ValueError("受控所有者需要显式registry")
        if audit_sink is None or not callable(audit_sink):
            raise owner_error("SCANNER_OWNER_AUDIT_UNAVAILABLE")
        self.registry, self.audit_sink = registry, audit_sink
        self.adapter = adapter if adapter is not None else WindowsOwnerProcessAdapter()
        self.verify_files, self.scanner_factory, self.health = (
            files_verifier,
            scanner_factory,
            health,
        )
        self.clock, self.monotonic = (
            clock or (lambda: datetime.now(UTC)),
            monotonic or time.monotonic,
        )
        self._lock, self._owned = asyncio.Lock(), None
        self._pending = None
        self._unclosed = []

    def _remaining(self, deadline):
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise owner_error("SCANNER_OWNER_DEADLINE")
        return remaining

    async def _thread(self, function, *args, deadline):
        return await asyncio.wait_for(asyncio.to_thread(function, *args), self._remaining(deadline))

    async def _audit(self, definition, instance_id, action, digest, deadline):
        event = {
            "event_id": str(uuid4()),
            "profile_id": definition.profile_id,
            "definition_revision": definition.revision,
            "instance_id": instance_id,
            "action": action,
            "source_sha256": digest,
            "executable_sha256": definition.executable_sha256,
            "config_sha256": definition.config_sha256,
            "release_receipt_sha256": definition.release_receipt_sha256,
            "occurred_at": self.clock().isoformat(),
        }
        result = self.audit_sink(event)
        if not inspect.isawaitable(result):
            raise owner_error("SCANNER_OWNER_AUDIT_UNAVAILABLE")
        await asyncio.wait_for(result, self._remaining(deadline))

    async def _late_close(self, task, definition):
        try:
            owned = await task
        except BaseException:
            return
        try:
            await asyncio.to_thread(
                self.adapter.close_owned,
                owned,
                (owned.pid, owned.created_at_us),
                self.monotonic() + definition.shutdown_seconds,
            )
        except BaseException:
            # 不把未知清理结果当已关闭；保留自有句柄并阻止新启动，stop可再试。
            self._unclosed.append((owned, definition))

    def _raw_profile(self, definition, process, digest, instance):
        issued = self.clock()
        expires = min(
            issued + timedelta(seconds=definition.proof_ttl_seconds), definition.expires_at
        )
        policy = definition.policy
        source = hashlib.sha256(
            json.dumps(
                [
                    digest,
                    instance,
                    process.pid,
                    process.created_at_us,
                    issued.isoformat(),
                    expires.isoformat(),
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return {
            "revision": definition.revision,
            "instance_id": instance,
            "pid": process.pid,
            "created_at_us": process.created_at_us,
            "issued_at": issued.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "expires_at": expires.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "source_sha256": source,
            "executable": str(definition.executable),
            "executable_sha256": definition.executable_sha256,
            "config_file": str(definition.config_file),
            "database_directory": str(definition.database_directory),
            "database_files": dict(definition.database_files),
            "policy": {
                "port": policy.port,
                "engine_version": policy.engine_version,
                "daily_db_version": policy.daily_db_version,
                "daily_db_built_at": policy.daily_db_built_at.astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "config_sha256": policy.config_sha256,
                "max_file_bytes": policy.max_file_bytes,
                "max_scan_bytes": policy.max_scan_bytes,
                "stream_max_bytes": policy.stream_max_bytes,
                "alert_exceeds_max": policy.alert_exceeds_max,
                "max_db_age_seconds": policy.max_db_age_seconds,
                "deadline_seconds": policy.deadline_seconds,
            },
        }

    async def start(self, definition):
        async with self._lock:
            if (
                self._owned is not None
                or self._unclosed
                or (self._pending is not None and not self._pending.done())
            ):
                raise owner_error("SCANNER_OWNER_BUSY")
            if not isinstance(definition, ScannerOwnerDefinition):
                raise owner_error("SCANNER_OWNER_DEFINITION_INVALID")
            definition.validate(self.clock())
            if any(row["id"] == definition.profile_id for row in self.registry.candidates()):
                raise owner_error("SCANNER_OWNER_ALREADY_REGISTERED")
            deadline = self.monotonic() + definition.startup_seconds
            process, binding, instance, digest = None, None, str(uuid4()), None
            try:
                await self._thread(self.adapter.require_job_support, deadline=deadline)
                digest = await self._thread(
                    self.verify_files, definition, deadline, deadline=deadline
                )
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise owner_error("SCANNER_OWNER_SOURCE_INVALID")
                if not await self._thread(
                    self.adapter.port_available, definition.policy.port, deadline, deadline=deadline
                ):
                    raise owner_error("SCANNER_OWNER_PORT_BUSY")
                await self._audit(definition, instance, "STARTING", digest, deadline)
                task = asyncio.create_task(
                    asyncio.to_thread(
                        self.adapter.spawn,
                        definition.executable,
                        definition.config_file,
                        definition.owned_root,
                        deadline,
                    )
                )
                try:
                    process = await asyncio.wait_for(
                        asyncio.shield(task), self._remaining(deadline)
                    )
                except BaseException:
                    self._pending = asyncio.create_task(self._late_close(task, definition))
                    raise
                if not await self._thread(self.adapter.alive, process, deadline=deadline):
                    raise owner_error("SCANNER_OWNER_IDENTITY_CHANGED")
                raw = self._raw_profile(definition, process, digest, instance)
                values = {PROFILE_KEY: json.dumps({definition.profile_id: raw})}
                scanner = self.scanner_factory(
                    definition.profile_id, values_provider=lambda: dict(values)
                )
                if not isinstance(scanner, ProcessBoundMaterialScanner):
                    raise owner_error("SCANNER_OWNER_HEALTH_FAILED")
                healthy = await asyncio.wait_for(
                    self.health(scanner, deadline), self._remaining(deadline)
                )
                if (
                    not isinstance(healthy, ScannerProbeResult)
                    or healthy.status != "READ_VERIFIED"
                    or healthy.binding is None
                    or healthy.binding.scanner is not scanner
                ):
                    raise owner_error("SCANNER_OWNER_HEALTH_FAILED")
                if (
                    await self._thread(self.verify_files, definition, deadline, deadline=deadline)
                    != digest
                ):
                    raise owner_error("SCANNER_OWNER_SOURCE_CHANGED")
                if not await self._thread(self.adapter.alive, process, deadline=deadline):
                    raise owner_error("SCANNER_OWNER_IDENTITY_CHANGED")
                definition.validate(self.clock())
                await self._audit(definition, instance, "STARTED", digest, deadline)
                self._remaining(deadline)
                binding = self.registry.publish(scanner, definition.label)
                self._owned = OwnedScanner(definition, process, scanner, binding, digest)
                return binding
            except BaseException as problem:
                if binding is not None and self.registry.same_generation(binding):
                    self.registry.withdraw(definition.profile_id)
                if process is not None:
                    try:
                        await self._thread(
                            self.adapter.close_owned,
                            process,
                            (process.pid, process.created_at_us),
                            self.monotonic() + definition.shutdown_seconds,
                            deadline=self.monotonic() + definition.shutdown_seconds,
                        )
                    except Exception:
                        self._pending = asyncio.create_task(
                            self._late_close(
                                asyncio.create_task(asyncio.sleep(0, result=process)), definition
                            )
                        )
                if isinstance(problem, asyncio.CancelledError):
                    raise
                raise owner_error(
                    problem.code if hasattr(problem, "code") else "SCANNER_OWNER_START_FAILED"
                ) from None

    async def stop(self):
        async with self._lock:
            return await self._stop("STOPPED")

    async def _stop(self, action):
        owned = self._owned
        if owned is None:
            if self._pending is not None and not self._pending.done():
                raise owner_error("SCANNER_OWNER_CLEANUP_PENDING")
            for process, definition in list(self._unclosed):
                deadline = self.monotonic() + definition.shutdown_seconds
                await self._thread(
                    self.adapter.close_owned,
                    process,
                    (process.pid, process.created_at_us),
                    deadline,
                    deadline=deadline,
                )
                self._unclosed.remove((process, definition))
            if hasattr(self.adapter, "cleanup_failed"):
                # 适配器可能在spawn未返回前已持有自有句柄；不通过PID发现或接管外部进程。
                deadline = self.monotonic() + 5
                await self._thread(self.adapter.cleanup_failed, deadline, deadline=deadline)
            return False
        if self.registry.same_generation(owned.binding):
            self.registry.withdraw(owned.definition.profile_id)
        self._owned = None
        deadline = self.monotonic() + owned.definition.shutdown_seconds
        try:
            await self._thread(
                self.adapter.close_owned,
                owned.process,
                (owned.process.pid, owned.process.created_at_us),
                deadline,
                deadline=deadline,
            )
        except Exception:
            self._pending = asyncio.create_task(
                self._late_close(
                    asyncio.create_task(asyncio.sleep(0, result=owned.process)), owned.definition
                )
            )
            raise owner_error("SCANNER_OWNER_CLOSE_FAILED") from None
        await self._audit(
            owned.definition,
            owned.scanner.profile.instance_id,
            action,
            owned.source_digest,
            deadline,
        )
        return True

    async def monitor_once(self):
        async with self._lock:
            owned = self._owned
            if owned is None:
                return False
            deadline = self.monotonic() + owned.definition.startup_seconds
            try:
                owned.definition.validate(self.clock())
                owned.scanner.profile.validate_time(self.clock())
                if not self.registry.same_generation(owned.binding):
                    raise owner_error("SCANNER_OWNER_IDENTITY_CHANGED")
                if not await self._thread(self.adapter.alive, owned.process, deadline=deadline):
                    raise owner_error("SCANNER_OWNER_IDENTITY_CHANGED")
                if (
                    await self._thread(
                        self.verify_files, owned.definition, deadline, deadline=deadline
                    )
                    != owned.source_digest
                ):
                    raise owner_error("SCANNER_OWNER_SOURCE_CHANGED")
                return True
            except Exception:
                await self._stop("INVALIDATED")
                return False
