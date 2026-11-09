"""单Worker显式生命周期；不自动挂API、不跨进程共享registry、不自动续签来源。"""

import asyncio
import re

from orbit_api.material_scanner_owner import MaterialScannerOwner
from orbit_api.material_scanner_owner_definition import owner_error
from orbit_api.material_scanner_owner_loader import OwnerConfiguration, disabled_owner_configuration
from orbit_api.material_scanner_owner_store import create_owner_audit_sink
from orbit_api.material_scanner_registry import MaterialScannerRegistry
from orbit_api.material_scanner_selection import ConfiguredMaterialWorker


class MaterialScannerSupervisor:
    """构造无I/O；start/monitor/run_once/shutdown必须由可信单Worker入口显式调用。"""

    def __init__(
        self,
        *,
        registry,
        sessions,
        objects,
        snapshot_provider=None,
        owner_factory=MaterialScannerOwner,
        worker_factory=ConfiguredMaterialWorker,
        audit_sink=None,
        drain_seconds=180,
        cleanup_seconds=30,
        source_seconds=5,
    ):
        if not isinstance(registry, MaterialScannerRegistry) or not callable(sessions):
            raise ValueError("监督器需要显式本进程registry及session工厂")
        if (snapshot_provider is not None and not callable(snapshot_provider)) or not all(
            callable(factory) for factory in (owner_factory, worker_factory)
        ):
            raise ValueError("监督器依赖必须是显式服务端可调用对象")
        for value, maximum in ((drain_seconds, 300), (cleanup_seconds, 60), (source_seconds, 30)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("监督器预算必须有界")
        self.registry, self.sessions, self.objects = registry, sessions, objects
        self.snapshot_provider = snapshot_provider or disabled_owner_configuration
        self.owner_factory, self.worker_factory = owner_factory, worker_factory
        self.audit_sink = (
            audit_sink if audit_sink is not None else create_owner_audit_sink(sessions)
        )
        self.drain_seconds, self.cleanup_seconds, self.source_seconds = (
            drain_seconds,
            cleanup_seconds,
            source_seconds,
        )
        self._lock, self._inflight = asyncio.Lock(), None
        self._owner, self._worker, self._snapshot, self._binding = None, None, None, None
        self._cleanup_task = None
        self._owner_stop_task = None
        self.state, self.accepting, self.last_error_code = "NEW", False, None

    async def _read_snapshot(self):
        value = await asyncio.wait_for(
            asyncio.to_thread(self.snapshot_provider), self.source_seconds
        )
        if not isinstance(value, OwnerConfiguration):
            raise owner_error("SCANNER_OWNER_CONFIGURATION_INVALID")
        if (
            type(value.enabled) is not bool
            or not isinstance(value.sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", value.sha256)
            or (value.enabled and value.definition is None)
            or (not value.enabled and value.definition is not None)
        ):
            raise owner_error("SCANNER_OWNER_CONFIGURATION_INVALID")
        return value

    def _withdraw(self):
        if self._binding is not None and self.registry.same_generation(self._binding):
            self.registry.withdraw(self._binding.profile.profile_id)

    async def _close_owner(self):
        if self._owner is None:
            return
        async with asyncio.timeout(self.cleanup_seconds):
            pending = getattr(self._owner, "_pending", None)
            if pending is not None and not pending.done():
                await asyncio.shield(pending)
            if self._owner_stop_task is None:
                self._owner_stop_task = asyncio.create_task(self._owner.stop())
                self._owner_stop_task.add_done_callback(
                    lambda task: None if task.cancelled() else task.exception()
                )
            current = self._owner_stop_task
            try:
                # 不取消owner.stop：其内部to_thread可能仍持原生Job，必须保留精确Task。
                await asyncio.shield(current)
            finally:
                if current.done():
                    self._owner_stop_task = None

    def _retain_cleanup(self):
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._close_owner())
            # 保留Task供显式shutdown复验，同时消费未观察异常防止默认日志带出底层细节。
            self._cleanup_task.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )

    async def start(self):
        async with self._lock:
            if self.state != "NEW":
                raise owner_error("SCANNER_SUPERVISOR_ALREADY_STARTED")
            self.state = "STARTING"
            try:
                self._snapshot = await self._read_snapshot()
                if not self._snapshot.enabled:
                    self.state = "DISABLED"
                    return False
                if self.objects is None:
                    raise owner_error("SCANNER_SUPERVISOR_OBJECTS_UNAVAILABLE")
                self._owner = self.owner_factory(self.registry, audit_sink=self.audit_sink)
                self._binding = await self._owner.start(self._snapshot.definition)
                # 发布后再读私有定义，启动期间配置变化不能留下半旧来源。
                if await self._read_snapshot() != self._snapshot:
                    raise owner_error("SCANNER_OWNER_CONFIGURATION_CHANGED")
                self._worker = self.worker_factory(
                    self.sessions, self.objects, registry=self.registry
                )
                self.state, self.accepting = "RUNNING", True
                return True
            except BaseException as problem:
                self.accepting, self.state = False, "FAILED"
                self._withdraw()
                self.last_error_code = getattr(problem, "code", "SCANNER_SUPERVISOR_START_FAILED")
                try:
                    await self._close_owner()
                except Exception:
                    self.last_error_code = "SCANNER_SUPERVISOR_CLEANUP_PENDING"
                if isinstance(problem, asyncio.CancelledError):
                    raise
                raise owner_error(self.last_error_code) from None

    async def run_once(self):
        async with self._lock:
            if not self.accepting or self.state != "RUNNING":
                raise owner_error("SCANNER_SUPERVISOR_UNAVAILABLE")
            if self._inflight is not None and not self._inflight.done():
                raise owner_error("SCANNER_SUPERVISOR_WORKER_BUSY")
            if self._completed_worker_failed():
                await self._fail_locked("SCANNER_SUPERVISOR_WORKER_FAILED")
                raise owner_error(self.last_error_code)
            try:
                if await self._read_snapshot() != self._snapshot:
                    raise owner_error("SCANNER_OWNER_CONFIGURATION_CHANGED")
                self.registry.verify(self._binding, source=False)
            except Exception as problem:
                self.accepting, self.state = False, "FAILED"
                self.last_error_code = getattr(problem, "code", "SCANNER_SUPERVISOR_UNAVAILABLE")
                self._withdraw()
                try:
                    await self._close_owner()
                except Exception:
                    self.last_error_code = "SCANNER_SUPERVISOR_CLEANUP_PENDING"
                raise owner_error(self.last_error_code) from None
            # 一个实例一次仅一个任务；不并发覆盖ConfiguredMaterialWorker的选择快照。
            self._inflight = asyncio.create_task(self._worker.run_once(limit=1))
            self._inflight.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
            current = self._inflight
        # 请求取消不能遗忘后台scan/process线程；保留任务供shutdown排空。
        try:
            return await asyncio.shield(current)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._invalidate("SCANNER_SUPERVISOR_WORKER_FAILED")
            raise owner_error("SCANNER_SUPERVISOR_WORKER_FAILED") from None

    def _completed_worker_failed(self):
        """只检查精确旧Task，不在回调中改变生命周期；调用方持有监督器锁。"""
        if self._inflight is None or not self._inflight.done():
            return False
        try:
            self._inflight.result()
            return False
        except (Exception, asyncio.CancelledError):
            return True

    async def _fail_locked(self, code):
        self.accepting, self.state, self.last_error_code = False, "FAILED", code
        self._withdraw()
        try:
            await self._close_owner()
        except Exception:
            self.last_error_code = "SCANNER_SUPERVISOR_CLEANUP_PENDING"

    async def _invalidate(self, code):
        async with self._lock:
            await self._fail_locked(code)

    async def monitor_once(self):
        async with self._lock:
            if self.state != "RUNNING" or not self.accepting:
                return False
            if self._completed_worker_failed():
                await self._fail_locked("SCANNER_SUPERVISOR_WORKER_FAILED")
                return False
            try:
                if await self._read_snapshot() != self._snapshot:
                    raise owner_error("SCANNER_OWNER_CONFIGURATION_CHANGED")
                if not await self._owner.monitor_once():
                    raise owner_error("SCANNER_OWNER_SOURCE_CHANGED")
                return True
            except asyncio.CancelledError:
                self.accepting, self.state = False, "FAILED"
                self._withdraw()
                self._retain_cleanup()
                raise
            except Exception as problem:
                self.accepting, self.state = False, "FAILED"
                self.last_error_code = getattr(problem, "code", "SCANNER_SUPERVISOR_MONITOR_FAILED")
                self._withdraw()
                try:
                    await self._close_owner()
                except Exception:
                    self.last_error_code = "SCANNER_SUPERVISOR_CLEANUP_PENDING"
                return False

    async def shutdown(self):
        async with self._lock:
            self.accepting = False
            if self.state == "STOPPED":
                return True
            was_failed = self.state == "FAILED"
            self.state = "STOPPING"
            drain_failed = False
            try:
                if self._cleanup_task is not None:
                    await asyncio.wait_for(asyncio.shield(self._cleanup_task), self.cleanup_seconds)
                    self._cleanup_task = None
                if self._inflight is not None:
                    try:
                        await asyncio.wait_for(asyncio.shield(self._inflight), self.drain_seconds)
                    except TimeoutError:
                        drain_failed = True
                    except asyncio.CancelledError:
                        if self._inflight.cancelled():
                            was_failed = True
                        else:
                            raise
                    except Exception:
                        # 已完成的失败任务不谎报“仍在途”，但失败状态仍锁存。
                        was_failed = True
                self._withdraw()
                await self._close_owner()
            except asyncio.CancelledError:
                self._withdraw()
                self.state, self.last_error_code = "FAILED", "SCANNER_SUPERVISOR_CLEANUP_PENDING"
                self._retain_cleanup()
                raise
            except Exception:
                self.state, self.last_error_code = "FAILED", "SCANNER_SUPERVISOR_CLEANUP_PENDING"
                raise owner_error(self.last_error_code) from None
            if drain_failed or (self._inflight is not None and not self._inflight.done()):
                self.state, self.last_error_code = "FAILED", "SCANNER_SUPERVISOR_INFLIGHT_PENDING"
                raise owner_error(self.last_error_code)
            self.state = "FAILED" if was_failed else "STOPPED"
            return not was_failed
