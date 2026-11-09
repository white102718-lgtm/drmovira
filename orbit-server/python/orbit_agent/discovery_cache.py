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

    @staticmethod
    def unavailable():
        return Discovery("UNKNOWN", "UNAVAILABLE", (), "PROFILE_DISCOVERY_FAILED")

    async def _worker(self):
        while True:
            try:
                self.latest = await self.source.discover()
            except Exception:
                # 不输出底层异常；后台失败不能留下未处理Task异常或伪装API仍可达。
                self.latest = self.unavailable()
            self.ready.set()
            await asyncio.sleep(self.refresh_interval)

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
