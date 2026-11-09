"""独立单Worker任务驱动；monitor与耗时处理分开，不自动挂API或重启扫描来源。"""

import asyncio

HANDLED_STATES = frozenset({"READY", "QUARANTINED", "UPLOAD_FAILED", "PROCESSING_FAILED", "STALE"})


def _tasks(supervisor):
    result = {}
    for name in ("_inflight", "_owner_stop_task", "_cleanup_task"):
        task = getattr(supervisor, name, None)
        if task is not None:
            result[name] = task
    owner = getattr(supervisor, "_owner", None)
    if owner is not None and getattr(owner, "_pending", None) is not None:
        result["owner_pending"] = owner._pending
    return result


def _finished_cleanly(task):
    return task.done() and not task.cancelled() and task.exception() is None


async def run_material_worker_service(
    supervisor, *, mode, stop, interval=1, cycles=None, monitor_interval=15, report=None
):
    """显式once/serve；已处理单素材终态继续，来源/监控/协议或未处理异常退出。"""
    if mode not in {"once", "serve"} or not isinstance(stop, asyncio.Event):
        raise ValueError("任务服务需要显式模式及停止事件")
    if type(interval) is not int or not 1 <= interval <= 3600:
        raise ValueError("轮询间隔必须1至3600秒")
    if cycles is not None and (
        mode != "serve" or type(cycles) is not int or not 1 <= cycles <= 1000
    ):
        raise ValueError("有限轮数仅用于serve且必须1至1000")
    if type(monitor_interval) not in {int, float} or not 0.01 <= monitor_interval <= 60:
        raise ValueError("监督间隔必须有界")
    counts = {"cycles": 0, "processed": 0, "ready": 0, "failed": 0}
    result, code = "STOPPED", "MATERIAL_WORKER_STOPPED"
    finished = asyncio.Event()
    monitor_task, active_task, shutdown_task = None, None, None
    monitor_failed = False
    cancelled = False
    active_counted = False

    def count_rows(rows):
        if (
            not isinstance(rows, list)
            or len(rows) > 1
            or any(
                not isinstance(row, dict)
                or not isinstance(row.get("state"), str)
                or row["state"] not in HANDLED_STATES
                for row in rows
            )
        ):
            raise ValueError("任务返回形状无效")
        counts["cycles"] += 1
        counts["processed"] += len(rows)
        ready = sum(row.get("state") == "READY" for row in rows)
        counts["ready"] += ready
        counts["failed"] += len(rows) - ready

    async def monitor():
        nonlocal monitor_failed
        while not stop.is_set() and not finished.is_set():
            try:
                await asyncio.wait_for(finished.wait(), monitor_interval)
                return
            except TimeoutError:
                pass
            if stop.is_set():
                return
            try:
                healthy = await supervisor.monitor_once()
            except Exception:
                healthy = False
            if not healthy:
                monitor_failed = True
                supervisor.accepting = False
                stop.set()
                return

    try:
        if not stop.is_set():
            enabled = await supervisor.start()
            if not enabled:
                result, code = "DISABLED", "MATERIAL_WORKER_DISABLED"
            else:
                monitor_task = asyncio.create_task(monitor())
                while not stop.is_set():
                    active_task = asyncio.create_task(supervisor.run_once())
                    active_counted = False
                    stop_wait = asyncio.create_task(stop.wait())
                    try:
                        await asyncio.wait(
                            {active_task, stop_wait, monitor_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if monitor_task.done() and not stop.is_set():
                            monitor_failed = True
                            stop.set()
                        if stop.is_set() or monitor_failed:
                            supervisor.accepting = False
                            break
                        rows = await asyncio.shield(active_task)
                    finally:
                        stop_wait.cancel()
                        try:
                            await stop_wait
                        except asyncio.CancelledError:
                            pass
                    count_rows(rows)
                    active_counted = True
                    if report is not None:
                        report({"result": "RUNNING", "code": "MATERIAL_WORKER_CYCLE", **counts})
                    if mode == "once" or (cycles is not None and counts["cycles"] >= cycles):
                        result, code = (
                            ("COMPLETED", "MATERIAL_WORKER_COMPLETED")
                            if counts["processed"]
                            else ("IDLE", "MATERIAL_WORKER_IDLE")
                        )
                        break
                    try:
                        await asyncio.wait_for(stop.wait(), interval)
                    except TimeoutError:
                        pass
    except asyncio.CancelledError:
        cancelled = True
        result, code = "FAILED", "MATERIAL_WORKER_CANCELLED"
    except Exception:
        result, code = "FAILED", "MATERIAL_WORKER_FAILED"
    finally:
        supervisor.accepting = False
        finished.set()
        cleanup_complete = True
        # 不丢monitor/worker/shutdown的精确Task，关闭按supervisor预算排空。
        if monitor_task is not None:
            try:
                await asyncio.wait_for(
                    asyncio.shield(monitor_task), getattr(supervisor, "source_seconds", 5) + 120
                )
            except Exception:
                cleanup_complete = False
            except asyncio.CancelledError:
                cleanup_complete = False
        shutdown_task = asyncio.create_task(supervisor.shutdown())
        shutdown_task.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        try:
            budget = (
                getattr(supervisor, "drain_seconds", 180)
                + 2 * getattr(supervisor, "cleanup_seconds", 30)
                + 5
            )
            await asyncio.wait_for(asyncio.shield(shutdown_task), budget)
        except Exception:
            cleanup_complete = False
        except asyncio.CancelledError:
            cleanup_complete = False
        if active_task is not None:
            if not active_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(active_task), 1)
                except Exception:
                    cleanup_complete = False
                except asyncio.CancelledError:
                    cleanup_complete = False
            if active_task.done():
                if active_task.cancelled() or active_task.exception() is not None:
                    result, code = "FAILED", "MATERIAL_WORKER_FAILED"
                elif not active_counted:
                    try:
                        count_rows(active_task.result())
                    except Exception:
                        result, code = "FAILED", "MATERIAL_WORKER_FAILED"
            else:
                cleanup_complete = False
        tracked = {**_tasks(supervisor), "shutdown": shutdown_task}
        if monitor_task is not None:
            tracked["monitor"] = monitor_task
        if active_task is not None:
            tracked["active"] = active_task
        if any(not _finished_cleanly(task) for task in tracked.values()):
            cleanup_complete = False
        owner = getattr(supervisor, "_owner", None)
        if owner is not None and (
            getattr(owner, "_owned", None) is not None
            or getattr(owner, "_unclosed", [])
            or getattr(getattr(owner, "adapter", None), "_failed", [])
        ):
            cleanup_complete = False
        if monitor_failed:
            result, code = "FAILED", "MATERIAL_WORKER_MONITOR_FAILED"
        if getattr(supervisor, "state", None) == "FAILED" and result != "FAILED":
            result, code = "FAILED", "MATERIAL_WORKER_SUPERVISOR_FAILED"
        if not cleanup_complete:
            result, code = "FAILED", "MATERIAL_WORKER_CLEANUP_UNVERIFIED"
            # 保留所有原生清理/后台任务到调用者进程退出，不自动重启或释放仍在途DB。
            supervisor.service_retained_tasks = tracked
    if cancelled:
        raise asyncio.CancelledError
    return {"result": result, "code": code, **counts, "cleanup_complete": cleanup_complete}
