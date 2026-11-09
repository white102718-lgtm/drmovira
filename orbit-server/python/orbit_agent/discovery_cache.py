"""完整库存后台串行发现；缓存保留事实原时间，不阻塞设备心跳或伪造FULL。"""

import asyncio
import time

from orbit_agent.adspower_readonly import Discovery


class BackgroundDiscovery:
    def __init__(self, source, *, initial_wait=5, refresh_interval=15, clock=time.monotonic):
        self.source = source
        self.initial_wait = initial_wait
        self.refresh_interval = refresh_interval
        self.clock = clock
        self.latest = None
        self.task = None
        self.ready = asyncio.Event()
        self.refresh = asyncio.Event()
        self.started_generation = 0
        self.completed_generation = 0

    @staticmethod
    def unavailable():
        return Discovery("UNKNOWN", "UNAVAILABLE", (), "PROFILE_DISCOVERY_FAILED")

    async def _worker(self):
        while True:
            self.refresh.clear()
            self.started_generation += 1
            try:
                self.latest = await self.source.discover()
            except Exception:
                # 不输出底层异常；后台失败不能留下未处理Task异常或伪装API仍可达。
                self.latest = self.unavailable()
            self.completed_generation = self.started_generation
            self.ready.set()
            try:
                async with asyncio.timeout(self.refresh_interval):
                    await self.refresh.wait()
            except TimeoutError:
                pass

    def request_refresh(self):
        """只唤醒串行后台任务；已在进行的旧发现不能当成新请求的结果。"""
        target = self.started_generation + 1
        self.refresh.set()
        return target

    def is_refresh_result(self, snapshot, generation):
        return snapshot is self.latest and self.completed_generation >= generation

    async def discover(self):
        if self.task is None:
            self.task = asyncio.create_task(self._worker())
        if self.latest is None:
            try:
                async with asyncio.timeout(self.initial_wait):
                    await self.ready.wait()
            except TimeoutError:
                return self.unavailable()
        snapshot = self.latest
        if snapshot is None or not 0 <= self.clock() - snapshot.started_monotonic <= 75:
            return self.unavailable()
        return snapshot

    async def close(self):
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
