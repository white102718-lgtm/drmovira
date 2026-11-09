"""有界observer；每帧及空闲当前授权，无数据库事务跨网络等待。"""

import asyncio
import time
from contextlib import suppress

from starlette.responses import Response

from orbit_api.errors import OrbitError
from orbit_api.task_event_contract import (
    MAX_STREAM_SECONDS,
    POLL_SECONDS,
    SEND_TIMEOUT_SECONDS,
    event_frame,
    revoked_frame,
)


class EventResponse(Response):
    media_type = "text/event-stream"

    def __init__(self, *, actor, after, read_batch, guard, quota):
        super().__init__(
            content=b"",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )
        self.raw_headers = [(k, v) for k, v in self.raw_headers if k != b"content-length"]
        self.actor, self.after = actor, after
        self.read_batch, self.guard, self.quota = read_batch, guard, quota

    async def checked_send(self, send, body):
        """慢发送期间仍复核；撤权即取消尚未完成send，不把整批排入ASGI缓冲。"""
        await self.guard(self.after)
        pending = asyncio.create_task(
            send({"type": "http.response.body", "body": body, "more_body": True})
        )
        deadline = time.monotonic() + SEND_TIMEOUT_SECONDS
        try:
            while not pending.done():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                done, _ = await asyncio.wait({pending}, timeout=min(POLL_SECONDS, remaining))
                if not done:
                    await self.guard(self.after)
            await pending
        finally:
            if not pending.done():
                pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending

    async def run(self, send):
        deadline = time.monotonic() + MAX_STREAM_SECONDS
        while time.monotonic() < deadline:
            rows = await self.read_batch(self.after)
            for row in rows:
                await self.checked_send(send, event_frame(row))
                self.after = row["sequence"]
            if not rows:
                await self.checked_send(send, b": keepalive\n\n")
                await asyncio.sleep(POLL_SECONDS)

    async def __call__(self, scope, receive, send):
        async def disconnected():
            while True:
                if (await receive())["type"] == "http.disconnect":
                    return

        stream, watcher = None, None
        try:
            await send({"type": "http.response.start", "status": 200, "headers": self.raw_headers})
            stream = asyncio.create_task(self.run(send))
            watcher = asyncio.create_task(disconnected())
            done, _ = await asyncio.wait({stream, watcher}, return_when=asyncio.FIRST_COMPLETED)
            if stream in done:
                try:
                    await stream
                except OrbitError as error:
                    if error.status in {401, 403, 404}:
                        # 此控制帧无Task数据；发送也有界，不能等待被撤权客户端无限读。
                        with suppress(TimeoutError):
                            await asyncio.wait_for(
                                send(
                                    {
                                        "type": "http.response.body",
                                        "body": revoked_frame(),
                                        "more_body": True,
                                    }
                                ),
                                SEND_TIMEOUT_SECONDS,
                            )
                    # 410/依赖故障关闭，下次HTTP重连能得到真实状态；不伪造业务事件。
                except TimeoutError:
                    pass
                except Exception:
                    # 依赖故障后失败关闭；不将异常正文写入SSE。
                    pass
            if watcher not in done:
                await asyncio.wait_for(
                    send({"type": "http.response.body", "body": b"", "more_body": False}),
                    SEND_TIMEOUT_SECONDS,
                )
        finally:
            for pending in (stream, watcher):
                if pending is not None:
                    pending.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await pending
            self.quota.release(self.actor)
