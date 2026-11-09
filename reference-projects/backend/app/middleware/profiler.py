import logging
import os

from pyinstrument import Profiler
from starlette.types import ASGIApp, Receive, Scope, Send

ENABLED = os.getenv("SLOW_PROFILE", "1") == "1"
THRESHOLD_SEC = float(os.getenv("SLOW_PROFILE_SEC", "10"))
INTERVAL_SEC = float(os.getenv("SLOW_PROFILE_INTERVAL", "0.01"))


class SlowRequestProfilerMiddleware:
    """超过阈值的请求打印 pyinstrument 树形堆栈耗时报告。

    通过 env 开关:
      SLOW_PROFILE=1                 启用(默认开启,设为 0 关闭)
      SLOW_PROFILE_SEC=10            阈值秒数(默认 10)
      SLOW_PROFILE_INTERVAL=0.01     采样间隔秒数(越大内存越省、精度越粗)
    """

    def __init__(
        self,
        app: ASGIApp,
        threshold: float = THRESHOLD_SEC,
        interval: float = INTERVAL_SEC,
    ):
        self.app = app
        self.threshold = threshold
        self.interval = interval

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if not ENABLED or scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        profiler = Profiler(async_mode="enabled", interval=self.interval)
        profiler.start()
        try:
            await self.app(scope, receive, send)
        finally:
            profiler.stop()
            duration = profiler.last_session.duration
            if duration >= self.threshold:
                report = profiler.output_text(unicode=True, color=False)
                logging.warning(
                    "[SLOW REQUEST %.2fs] %s %s\n%s",
                    duration,
                    scope.get("method", ""),
                    scope.get("path", ""),
                    report,
                )
            del profiler
