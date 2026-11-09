"""素材浏览器专项的真实处理线程；仅当前UUID测试库，结束只停止本夹具线程。"""

import asyncio
import re
import threading
from pathlib import Path

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def start_material_browser_worker(admin, database, object_root, *, scanner):
    if not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", database):
        raise ValueError("素材浏览器Worker只允许隔离测试库")
    from orbit_api.material_objects import LocalMaterialObjects
    from orbit_api.material_worker import MaterialWorker

    def decoded(value):
        return value.decode() if isinstance(value, bytes) else value

    url = URL.create(
        "mysql+asyncmy",
        username=decoded(admin.user),
        password=decoded(admin.password),
        host=admin.host,
        port=admin.port,
        database=database,
    )
    objects = LocalMaterialObjects(Path(object_root))
    stopped = threading.Event()
    errors = []

    async def run():
        engine = create_async_engine(url, echo=False)
        try:
            worker = MaterialWorker(
                async_sessionmaker(engine, expire_on_commit=False),
                objects,
                scanner=scanner,
                runtime_profile_provider=lambda claim: scanner.profile,
            )
            while not stopped.is_set():
                await worker.run_once(10)
                await asyncio.sleep(0.25)
        except Exception:
            # 不记录连接或文件原始异常；stop时交给主运行器失败，不能静默冒充浏览器已通过。
            errors.append("素材真实处理线程失败")
        finally:
            await engine.dispose()

    thread = threading.Thread(
        target=lambda: asyncio.run(run()), name="orbit-material-fixture", daemon=True
    )
    thread.start()

    def stop():
        stopped.set()
        thread.join(timeout=240)
        if thread.is_alive():
            raise RuntimeError("素材处理夹具尚未退出，不能清理其对象目录")
        if errors:
            raise RuntimeError(errors[0])

    return stop
