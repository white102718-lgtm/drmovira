"""受控邀请任务循环；不随Web应用启动，不并发运行周期，也不重试未知投递。"""

import asyncio


async def run_job(worker, *, send, limit, stop, interval=30, cycles=1, report=None):
    """cycles=None为显式常驻模式；停止信号只等待当前单条完成，不认领下一条。"""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("单轮批次仅允许1至100")
    if type(interval) is not int or not 5 <= interval <= 3600:
        raise ValueError("轮询间隔仅允许5至3600秒")
    if cycles is not None and (type(cycles) is not int or not 1 <= cycles <= 1000):
        raise ValueError("有限运行轮数仅允许1至1000")
    completed, failures = 0, 0
    last = None
    while not stop.is_set() and (cycles is None or completed < cycles):
        try:
            last = {"recovered_unknown": await worker.recover_interrupted(limit)}
            if send:
                counts = {"claimed": 0, "accepted": 0, "failed": 0, "unknown": 0}
                for _ in range(limit):
                    if stop.is_set():
                        break
                    # 一次仅处理一条；未知结果由存储状态保护，永不在任务循环重发。
                    item = await worker.run_once(1)
                    for key in counts:
                        counts[key] += item[key]
                    if not item["claimed"]:
                        break
                last.update(counts)
            failures = 0
        except Exception:
            # 不输出异常详情，避免SQL连接、加密载荷或渠道响应进入任务日志。
            failures += 1
            last = {"result": "FAILED", "code": "INVITATION_WORKER_FAILED"}
        completed += 1
        if report is not None:
            report(last)
        if failures >= 3:
            return {"result": "FAILED", "code": "INVITATION_WORKER_REPEATED_FAILURE"}
        if stop.is_set() or (cycles is not None and completed >= cycles):
            break
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
    return last or {"result": "STOPPED", "cycles": 0}
