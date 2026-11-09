"""显式执行一次邀请通知任务；无默认发送模式，不接受凭据或连接字符串参数。"""

import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--send", action="store_true", help="显式授权本轮向已配置Webhook发送")
    modes.add_argument("--recover", action="store_true", help="仅把超时SENDING转为UNKNOWN，不发送")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--serve", action="store_true", help="显式常驻轮询，不随Web应用启动")
    parser.add_argument("--interval", type=int, default=30, help="常驻周期之间等待秒数，5至3600")
    parser.add_argument(
        "--cycles", type=int, help="仅配合--serve的受控验收轮数，1至1000；省略则常驻"
    )
    result = parser.parse_args(argv)
    if not 1 <= result.limit <= 100:
        parser.error("单轮批次仅允许1至100")
    if not 5 <= result.interval <= 3600:
        parser.error("轮询间隔仅允许5至3600秒")
    if result.cycles is not None and (not result.serve or not 1 <= result.cycles <= 1000):
        parser.error("--cycles仅用于--serve受控验收，轮数1至1000")
    return result


async def execute(options):
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root / "python"), str(root / "python/ruoyi_fastapi")]
    from config.database import DataSourceRegistry

    from orbit_api.configuration_routes import credential_cipher
    from orbit_api.cookie_auth import public_origin
    from orbit_api.invitation_delivery import InvitationDeliveryWorker
    from orbit_api.invitation_job import run_job

    stop = asyncio.Event()
    previous = {}
    try:
        # 标准信号处理兼容Windows事件循环；信号不强行中断正在持有的投递事务。
        loop = asyncio.get_running_loop()
        for value in (signal.SIGINT, signal.SIGTERM):
            previous[value] = signal.signal(value, lambda *_: loop.call_soon_threadsafe(stop.set))
        await DataSourceRegistry.initialize(log_enabled=False)
        worker = InvitationDeliveryWorker(
            lambda: DataSourceRegistry.session(log_sql=False), credential_cipher(), public_origin()
        )
        return await run_job(
            worker,
            send=options.send,
            limit=options.limit,
            stop=stop,
            interval=options.interval,
            cycles=(options.cycles if options.serve else 1),
            report=(lambda result: print(json.dumps(result), flush=True))
            if options.serve
            else None,
        )
    finally:
        try:
            await DataSourceRegistry.dispose_all()
        finally:
            for value, handler in previous.items():
                signal.signal(value, handler)


def main(argv=None):
    options = arguments(argv)
    try:
        from invitation_worker_lock import worker_lock

        # 一次性和常驻模式共享同一个锁；数据库SKIP LOCKED仍是跨机器的认领底线。
        with worker_lock(Path(__file__).resolve().parents[1] / ".runtime/invitation-worker.lock"):
            result = asyncio.run(execute(options))
        if not options.serve or result.get("result") == "FAILED":
            print(json.dumps(result), flush=True)
        return 1 if result.get("result") == "FAILED" else 0
    except Exception:
        # SQL/HTTP异常可能含连接参数或通道响应，终端与任务日志均只输出固定类别。
        print(json.dumps({"result": "FAILED", "code": "INVITATION_WORKER_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
