"""显式原代际恢复服务；不注册调度、不签发维护授权、不发送平台写。"""

import asyncio
import math
from dataclasses import asdict
from datetime import UTC, datetime

from orbit_api.errors import OrbitError
from orbit_api.launch_execution_recovery_scanner import (
    ExecutionRecoveryScanner,
    RecoveryScanAuthorityProvider,
    RecoveryScanReport,
    _validate_grant,
)


def _number(value, lower, upper):
    if type(value) not in {int, float} or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError("恢复服务时间预算无效")


class _FixedProvider(RecoveryScanAuthorityProvider):
    def __init__(self, provider, grant, clock):
        self.provider, self.grant, self.clock = provider, grant, clock

    async def capture(self):
        return await self.current(self.grant)

    async def current(self, grant):
        _validate_grant(self.grant, self.clock())
        current = await self.provider.current(self.grant)
        _validate_grant(current, self.clock())
        if grant != self.grant or current != self.grant:
            raise OrbitError(503, "RECOVERY_SERVICE_AUTHORITY_CHANGED", "恢复维护授权已变化")
        return self.grant

    async def authority(self, grant):
        await self.current(grant)
        return await self.provider.authority(self.grant)


class ExecutionRecoveryService:
    """一次性实例；factory必须可信注入，不接收HTTP配置或任意租户列表。"""

    def __init__(self, provider=None, scanner_factory=None, *, clock=None):
        self.provider = provider
        self.scanner_factory = scanner_factory or (
            lambda provider: ExecutionRecoveryScanner(provider)
        )
        self.clock = clock or (lambda: datetime.now(UTC))
        self.state = "NEW"
        self.scanner = None
        self.active_task = None
        self.retained_tasks = ()

    async def _finish(self, watcher, drain_seconds):
        if self.scanner is not None:
            self.scanner.request_stop()
        if watcher is not None:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        active = self.active_task
        if active is not None and not active.done():
            done, _ = await asyncio.wait({active}, timeout=drain_seconds)
            if not done:
                active.cancel()
                done, _ = await asyncio.wait({active}, timeout=5)
                if not done:
                    raise OrbitError(
                        503, "RECOVERY_SERVICE_CLEANUP_UNVERIFIED", "恢复服务清理尚未证实"
                    )
        if active is not None and active.done() and not active.cancelled():
            error = active.exception()
            if error is not None:
                raise error

    async def run(
        self,
        *,
        mode,
        stop,
        interval_seconds=30,
        cycles=None,
        max_candidates=100,
        max_raw_rows=1000,
        time_budget_seconds=10,
        budget_interval_seconds=0.1,
        drain_seconds=5,
        report=None,
    ):
        if mode not in {"once", "serve"} or not isinstance(stop, asyncio.Event):
            raise ValueError("恢复服务必须显式选择模式及停止事件")
        _number(interval_seconds, 1, 300)
        _number(budget_interval_seconds, 0.1, 300)
        _number(drain_seconds, 0, 5)
        if drain_seconds == 0:
            raise ValueError("排空预算必须严格为正")
        _number(time_budget_seconds, 0.001, 60)
        if type(max_candidates) is not int or not 1 <= max_candidates <= 200:
            raise ValueError("恢复候选预算无效")
        if type(max_raw_rows) is not int or not 1 <= max_raw_rows <= 10000:
            raise ValueError("恢复原始行预算无效")
        if cycles is not None and (
            mode != "serve" or type(cycles) is not int or not 1 <= cycles <= 1000
        ):
            raise ValueError("有限轮数仅适用于常驻模式")
        if self.state != "NEW":
            raise OrbitError(409, "RECOVERY_SERVICE_ALREADY_USED", "恢复服务实例不可重复启动")
        self.state = "RUNNING"
        counts = {"cycles": 0, "recovered": 0, "blocked": 0, "stale": 0, "raw_rows": 0}
        watcher = None
        failed = False
        try:
            if not isinstance(self.provider, RecoveryScanAuthorityProvider):
                raise OrbitError(
                    503, "RECOVERY_SERVICE_AUTHORITY_UNAVAILABLE", "恢复维护主体未配置"
                )
            if stop.is_set():
                return {"result": "STOPPED", **counts, "cleanup_complete": True}
            async with asyncio.timeout(5):
                grant = await self.provider.capture()
                _validate_grant(grant, self.clock())
                fixed = _FixedProvider(self.provider, grant, self.clock)
                await fixed.current(grant)
            if stop.is_set():
                return {"result": "STOPPED", **counts, "cleanup_complete": True}
            self.scanner = self.scanner_factory(fixed)
            blocked_rounds = 0
            while not stop.is_set():
                async with asyncio.timeout(5):
                    await fixed.current(grant)
                if stop.is_set():
                    break
                self.active_task = asyncio.create_task(
                    self.scanner.scan_once(
                        max_candidates=max_candidates,
                        max_raw_rows=max_raw_rows,
                        time_budget_seconds=time_budget_seconds,
                    )
                )
                watcher = asyncio.create_task(stop.wait())
                await asyncio.wait({self.active_task, watcher}, return_when=asyncio.FIRST_COMPLETED)
                if stop.is_set():
                    self.scanner.request_stop()
                    break
                result = self.active_task.result()  # 原1205/协议/未知异常直接退出，不重试。
                if not isinstance(result, RecoveryScanReport):
                    raise ValueError("恢复扫描返回协议无效")
                values = asdict(result)
                if any(
                    type(values[key]) is not int or values[key] < 0
                    for key in values
                    if key not in {"stopped", "budget_exhausted"}
                ):
                    raise ValueError("恢复扫描统计无效")
                if type(result.stopped) is not bool or type(result.budget_exhausted) is not bool:
                    raise ValueError("恢复扫描统计无效")
                counts["cycles"] += 1
                for key in ("recovered", "blocked", "stale", "raw_rows"):
                    counts[key] += values[key]
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
                watcher = None
                if report is not None:
                    report({"result": "RUNNING", "code": "RECOVERY_SERVICE_CYCLE", **counts})
                if (
                    result.stopped
                    or mode == "once"
                    or (cycles is not None and counts["cycles"] >= cycles)
                ):
                    break
                blocked_rounds = min(blocked_rounds + 1, 10) if result.blocked else 0
                delay = (
                    min(300, interval_seconds * 2**blocked_rounds)
                    if blocked_rounds
                    else (budget_interval_seconds if result.budget_exhausted else interval_seconds)
                )
                try:
                    async with asyncio.timeout(delay):
                        await stop.wait()
                except TimeoutError:
                    pass
            return {
                "result": "STOPPED" if stop.is_set() else "COMPLETED",
                **counts,
                "cleanup_complete": True,
            }
        except BaseException:
            failed = True
            raise
        finally:
            self.state = "STOPPING"
            try:
                await self._finish(watcher, drain_seconds)
            except BaseException:
                self.state = "FAILED"
                self.retained_tasks = tuple(
                    task
                    for task in (self.active_task, watcher)
                    if task is not None and not task.done()
                )
                raise
            self.state = "FAILED" if failed else "STOPPED"
