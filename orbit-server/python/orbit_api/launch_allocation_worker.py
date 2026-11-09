"""分配实际CPU进程边界；领取/读取/发布各自短事务，无平台外发、无空Task。"""

import asyncio
import multiprocessing
from uuid import uuid4

from orbit_api.errors import OrbitError
from orbit_api.launch_allocation import AllocationTimeout
from orbit_api.launch_allocation_runtime import AllocationRuntime, solve_packet


def _child(connection, packet, evidence, seconds):
    try:
        connection.send(("SUCCESS", solve_packet(packet, evidence, seconds=seconds)))
    except AllocationTimeout:
        connection.send(("FAILURE", "ALLOCATION_TIMEOUT"))
    except OrbitError as error:
        code = (
            "ALLOCATION_NO_MATCH"
            if error.code == "ALLOCATION_NO_MATCH"
            else "ALLOCATION_INPUT_INVALID"
        )
        connection.send(("FAILURE", code))
    except BaseException:
        # 不把自由异常、计划正文、平台响应或凭据输送到父进程/日志。
        connection.send(("FAILURE", "ALLOCATION_INPUT_INVALID"))
    finally:
        connection.close()


def solve_in_process(packet, evidence, *, seconds=60):
    """spawn隔离进程；算法共享60秒CPU工作预算，外层另留10秒启动/序列化后硬终止。"""
    if type(seconds) is not int or not 1 <= seconds <= 60:
        raise ValueError("求解秒数必须1至60")
    context = multiprocessing.get_context("spawn")
    receiving, sending = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(sending, packet, evidence, seconds), daemon=True)
    try:
        process.start()
        sending.close()
        if not receiving.poll(seconds + 10):
            return "FAILURE", "ALLOCATION_TIMEOUT"
        try:
            return receiving.recv()
        except EOFError:
            return "FAILURE", "ALLOCATION_INPUT_INVALID"
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            process.close()
        receiving.close()
        sending.close()


class AllocationWorker:
    def __init__(self, sessions, provider=None, *, worker_id=None):
        self.sessions = sessions
        self.runtime = AllocationRuntime(provider)
        self.worker_id = worker_id or str(uuid4())

    async def run_once(self):
        """幂等外层调度；缺生产provider503，数据库/审计故障回滚并由租约恢复重领。"""
        async with self.sessions() as session, session.begin():
            claim = await self.runtime.claim(session, self.worker_id)
        if claim is None:
            return False
        try:
            async with self.sessions() as session, session.begin():
                _, packet, evidence = await self.runtime.load(session, claim)
            # CPU不持数据库事务/对象锁，防止求解期间阻塞其他模块。
            status, result = await asyncio.to_thread(solve_in_process, packet, evidence)
            if status == "SUCCESS":
                async with self.sessions() as session, session.begin():
                    await self.runtime.heartbeat(session, claim)
                async with self.sessions() as session, session.begin():
                    await self.runtime.publish(session, claim, result, str(uuid4()))
            else:
                async with self.sessions() as session, session.begin():
                    if result == "ALLOCATION_TIMEOUT":
                        await self.runtime.defer_timeout(session, claim, str(uuid4()))
                    else:
                        await self.runtime.fail(session, claim, result, str(uuid4()))
        except OrbitError as error:
            if error.code == "ALLOCATION_CLAIM_LOST":
                return True
            code = {
                "ALLOCATION_MANIFEST_CORRUPT": "ALLOCATION_MANIFEST_CORRUPT",
                "PERMISSION_DENIED": "ALLOCATION_AUTH_REVOKED",
                "REVISION_CONFLICT": "ALLOCATION_SOURCE_CHANGED",
                "ALLOCATION_SOURCE_CHANGED": "ALLOCATION_SOURCE_CHANGED",
                "LAUNCH_SOURCE_STATE_UNAVAILABLE": "ALLOCATION_SOURCE_CHANGED",
                "PLAN_STATE_CONFLICT": "ALLOCATION_SOURCE_CHANGED",
            }.get(error.code, "ALLOCATION_INPUT_INVALID")
            async with self.sessions() as session, session.begin():
                try:
                    await self.runtime.fail(session, claim, code, str(uuid4()))
                except OrbitError as lost:
                    if lost.code != "ALLOCATION_CLAIM_LOST":
                        raise
        return True
