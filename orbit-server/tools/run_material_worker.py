"""显式单Worker扫描入口；默认不运行，不接受路径、服务器、凭据或Token参数。"""

import argparse
import asyncio
import json
import signal
import sys
from contextlib import nullcontext
from pathlib import Path


def arguments(argv=None):
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            # 未知参数可能含误粘贴Token；不回显原argv或类型转换异常。
            self.exit(
                2,
                json.dumps({"result": "FAILED", "code": "MATERIAL_WORKER_ARGUMENTS_INVALID"})
                + "\n",
            )

    parser = SafeParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="仅处理至多一个素材任务并关闭自有实例")
    mode.add_argument(
        "--serve", action="store_true", help="显式常驻，来源或监控失效/未处理异常退出"
    )
    parser.add_argument("--interval", type=int, default=1, help="任务轮询间隔1至3600秒")
    parser.add_argument("--cycles", type=int, help="仅serve验收轮数1至1000，省略则常驻")
    options = parser.parse_args(argv)
    if not 1 <= options.interval <= 3600:
        parser.error("轮询间隔必须1至3600秒")
    if options.cycles is not None and (not options.serve or not 1 <= options.cycles <= 1000):
        parser.error("cycles仅用于serve且必须1至1000")
    return options


def initial_configuration(values_provider=None):
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root / "python"), str(root / "python/ruoyi_fastapi")]
    if values_provider is None:
        from config.orbit_runtime import private_values

        values_provider = private_values
    from orbit_api.material_scanner_owner_loader import load_owner_configuration

    values = values_provider()
    return values, load_owner_configuration(lambda: values), values_provider


def process_lock():
    """固定本地锁随整个asyncio.run持有，不在后台线程收尾前提前解锁。"""
    from invitation_worker_lock import worker_lock

    path = Path(__file__).resolve().parents[1] / ".runtime/material-worker.lock"
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if item.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("扫描任务进程锁不允许链接或reparse")
    return worker_lock(path)


async def execute(
    options,
    *,
    values_provider=None,
    data_sources=None,
    objects_factory=None,
    supervisor_factory=None,
    service_runner=None,
    lock_factory=None,
    stop=None,
    install_signals=True,
    report=None,
):
    root = Path(__file__).resolve().parents[1]
    from orbit_api.material_scanner_owner_loader import load_owner_configuration

    values, snapshot, values_provider = initial_configuration(values_provider)
    if not snapshot.enabled:
        return {
            "result": "DISABLED",
            "code": "MATERIAL_WORKER_DISABLED",
            "cycles": 0,
            "processed": 0,
            "ready": 0,
            "failed": 0,
            "cleanup_complete": True,
        }
    # 关闭模式在这些导入和初始化之前返回，不能访问DB/对象根或启动锁。
    if objects_factory is None:
        from orbit_api.material_objects import LocalMaterialObjects

        objects_factory = LocalMaterialObjects
    configured_root = values.get("ORBIT_PYTHON_MATERIAL_OBJECT_ROOT")
    if (
        not isinstance(configured_root, str)
        or configured_root.strip() != configured_root
        or not Path(configured_root).is_absolute()
    ):
        raise ValueError("素材对象根尚未完整配置")
    objects = objects_factory(Path(configured_root))
    if data_sources is None:
        from config.database import DataSourceRegistry

        data_sources = DataSourceRegistry
    if supervisor_factory is None:
        from orbit_api.material_scanner_supervisor import MaterialScannerSupervisor

        supervisor_factory = MaterialScannerSupervisor
    if service_runner is None:
        from orbit_api.material_worker_service import run_material_worker_service

        service_runner = run_material_worker_service
    if lock_factory is None:
        from invitation_worker_lock import worker_lock

        lock_factory = worker_lock
    from orbit_api.material_scanner_registry import MaterialScannerRegistry

    previous, result, initialized = {}, None, False
    stop = stop or asyncio.Event()
    try:
        with lock_factory(root / ".runtime/material-worker.lock"):
            if install_signals:
                loop = asyncio.get_running_loop()
                for value in (signal.SIGINT, signal.SIGTERM):
                    previous[value] = signal.signal(
                        value, lambda *_: loop.call_soon_threadsafe(stop.set)
                    )
            await data_sources.initialize(log_enabled=False)
            initialized = True
            supervisor = supervisor_factory(
                registry=MaterialScannerRegistry(),
                sessions=lambda: data_sources.session(log_sql=False),
                objects=objects,
                snapshot_provider=lambda: load_owner_configuration(values_provider),
            )
            result = await service_runner(
                supervisor,
                mode="serve" if options.serve else "once",
                stop=stop,
                interval=options.interval,
                cycles=options.cycles,
                report=report if options.serve else None,
            )
            return result
    finally:
        try:
            if initialized and result is not None and result.get("cleanup_complete") is True:
                await data_sources.dispose_all()
        finally:
            for value, handler in previous.items():
                signal.signal(value, handler)


def main(argv=None):
    options = arguments(argv)
    try:
        _, snapshot, _ = initial_configuration()
        if not snapshot.enabled:
            print(
                json.dumps(
                    {
                        "result": "DISABLED",
                        "code": "MATERIAL_WORKER_DISABLED",
                        "cycles": 0,
                        "processed": 0,
                        "ready": 0,
                        "failed": 0,
                        "cleanup_complete": True,
                    }
                ),
                flush=True,
            )
            return 0
        with process_lock():
            result = asyncio.run(
                execute(
                    options,
                    lock_factory=lambda _: nullcontext(),
                    report=lambda item: print(json.dumps(item), flush=True),
                )
            )
        print(json.dumps(result), flush=True)
        return (
            0 if result.get("cleanup_complete") is True and result.get("result") != "FAILED" else 1
        )
    except KeyboardInterrupt:
        print(
            json.dumps(
                {
                    "result": "FAILED",
                    "code": "MATERIAL_WORKER_INTERRUPTED",
                    "cleanup_complete": False,
                }
            )
        )
        return 130
    except asyncio.CancelledError:
        print(
            json.dumps(
                {"result": "FAILED", "code": "MATERIAL_WORKER_CANCELLED", "cleanup_complete": False}
            )
        )
        return 130
    except Exception:
        print(
            json.dumps(
                {"result": "FAILED", "code": "MATERIAL_WORKER_FAILED", "cleanup_complete": False}
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
