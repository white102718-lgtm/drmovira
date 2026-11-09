"""主动只读探测协调；旧库存不冒充新结果，丢失完成ACK保留原载荷。"""

import asyncio
import time
from datetime import UTC, datetime

from orbit_agent.adspower_status import ProbeError
from orbit_agent.transport import DeviceRejected


class ProbeRequests:
    def __init__(self, *, budget_seconds=2):
        self.budget_seconds = budget_seconds
        self.current = None
        self.generation = None
        self.started_after = None
        self.pending = None
        self.credits = {}

    def clear(self):
        self.current = None
        self.generation = None
        self.started_after = None
        self.pending = None
        self.credits = {}

    async def _complete(self, device):
        identifier, payload = self.pending
        try:
            async with asyncio.timeout(self.budget_seconds):
                await device.complete_probe(identifier, payload)
        except DeviceRejected as error:
            if error.status in {400, 403, 404, 409, 410, 422}:
                # 未完成的旧seq不能续交；下一轮重新读取请求并取得新观察。
                self.clear()
        except (ProbeError, TimeoutError):
            pass
        else:
            self.clear()

    async def before_cycle(self, adapter, device):
        # 完成载荷重放发生在新心跳之前；服务端精确重放返回原Ack。
        if self.pending is not None:
            await self._complete(device)
            if self.pending is not None:
                return
        try:
            async with asyncio.timeout(self.budget_seconds):
                value = await device.probe_requests()
        except DeviceRejected as error:
            if error.status in {401, 403, 404, 410}:
                self.clear()
            return
        except (ProbeError, TimeoutError):
            return
        item = value["request"]
        if item is None or datetime.fromisoformat(item["expires_at"]) <= datetime.now(UTC):
            self.clear()
            return
        if self.current is None or self.current["id"] != item["id"]:
            self.clear()
            self.current = dict(item)
            self.started_after = time.monotonic()
            self.generation = adapter.request_refresh()

    @staticmethod
    def binding_fingerprint(binding):
        """仅内存保存当前绑定及预期身份；版本或任一身份字段变化就必须重新观察。"""
        return tuple(
            binding.get(key)
            for key in (
                "id",
                "revision",
                "profile_external_id",
                "account_id",
                "external_account_id",
                "currency",
            )
        )

    async def after_cycle(
        self, adapter, device, spool, snapshot, seq, *, eligible=(), reported=(), verified=True
    ):
        if self.current is None or self.pending is not None:
            return
        if not verified:
            # 配置失败、报告拒绝或未ACK时，不保留可能已失效的跨轮覆盖。
            self.credits.clear()
            return
        if datetime.fromisoformat(self.current["expires_at"]) <= datetime.now(UTC):
            self.clear()
            return
        if (
            not adapter.is_refresh_result(snapshot, self.generation)
            or snapshot.started_monotonic < self.started_after
            or datetime.fromisoformat(snapshot.observed_at)
            < datetime.fromisoformat(self.current["created_at"])
        ):
            return
        clock = time.monotonic()
        required = {self.binding_fingerprint(binding) for binding in eligible}
        # 额度轮转最多100个；只累计本请求内当前版本、仍在90秒身份有效期以内的报告。
        # 保守75秒窗口留出交付和服务端核验时间；120秒请求TTL仍独立生效。
        self.credits = {
            key: observed
            for key, observed in self.credits.items()
            if key in required and 0 <= clock - observed < 75
        }
        for binding in reported:
            fingerprint = self.binding_fingerprint(binding)
            if fingerprint in required:
                self.credits[fingerprint] = clock
        if not required.issubset(self.credits):
            return
        self.pending = (
            self.current["id"],
            {
                "agent_id": spool.agent_id,
                "boot_id": spool.boot_id,
                "seq": seq,
                "observed_at": snapshot.observed_at,
            },
        )
        await self._complete(device)
