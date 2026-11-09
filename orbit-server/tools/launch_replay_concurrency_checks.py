"""实际HTTP双请求先miss后串行重放；用数据库等待观测而非睡眠猜测窗口。"""

import hashlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from launch_draft_template_checks import assert_status, draft
from scope_visibility_verdict_checks import guard_database

LAUNCH_REPLAY_CONCURRENCY_CASES = (
    "pythonLaunchReplayTwoActualClockWaitersRecheckCurrentReadAfterConcurrentMiss",
)


def run_launch_replay_concurrency_checks(client, admin, headers, database, cases):
    guard_database(admin, database)
    with admin.cursor() as cursor:
        cursor.execute("SELECT tenant_id,id,team_id FROM orbit_business_user WHERE user_id=1")
        tenant, owner, team = cursor.fetchone()
        cursor.execute("SELECT status FROM sys_menu WHERE menu_id=31021")
        old_status = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orbit_launch_plan WHERE tenant_id=%s", (tenant,))
        before_plans = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orbit_task")
        before_tasks = cursor.fetchone()[0]
    caps = assert_status(client.get("/api/v1/launch-plans/capabilities", headers=headers), 200)
    key = str(uuid4())
    write = headers | {"X-CSRF-Token": caps["csrf_token"], "Idempotency-Key": key}
    body = draft({"id": owner, "team": team})
    futures = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            with admin.cursor() as cursor:
                cursor.execute("UPDATE sys_menu SET status='1' WHERE menu_id=31021")
            admin.commit()
            admin.begin()
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT plan_revision FROM orbit_launch_clock WHERE tenant_id=%s FOR UPDATE",
                    (tenant,),
                )
                assert cursor.fetchone() is not None
            for _ in range(2):
                futures.append(
                    pool.submit(client.post, "/api/v1/launch-plans", headers=write, json=body)
                )
            deadline = time.monotonic() + 5
            observed_waiters = 0
            while time.monotonic() < deadline:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(DISTINCT w.REQUESTING_THREAD_ID) "
                        "FROM performance_schema.data_lock_waits w "
                        "JOIN performance_schema.data_locks r "
                        "ON r.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID "
                        "WHERE r.OBJECT_SCHEMA=%s AND r.OBJECT_NAME='orbit_launch_clock'",
                        (database,),
                    )
                    observed_waiters = cursor.fetchone()[0]
                if observed_waiters == 2:
                    break
                if any(future.done() for future in futures):
                    raise AssertionError("两个请求必须都实际到达写clock，不能提前重放或失败")
                time.sleep(0.02)
            assert observed_waiters == 2, "必须观测到两个真实clock等待者"
            admin.commit()
            responses = [future.result(timeout=10) for future in futures]
            assert sorted(response.status_code for response in responses) == [201, 403]
            original = next(
                response.json() for response in responses if response.status_code == 201
            )
            rejected = next(
                response.json() for response in responses if response.status_code == 403
            )
            assert rejected["code"] == "PERMISSION_DENIED" and "id" not in rejected
            assert_status(client.post("/api/v1/launch-plans", headers=write, json=body), 403)
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_launch_plan WHERE tenant_id=%s", (tenant,)
                )
                assert cursor.fetchone()[0] == before_plans + 1
                cursor.execute(
                    "SELECT COUNT(*) FROM orbit_launch_idempotency WHERE tenant_id=%s "
                    "AND actor_id=1 AND operation='plan.create' AND key_hash=%s",
                    (tenant, hashlib.sha256(key.encode()).hexdigest()),
                )
                assert cursor.fetchone()[0] == 1
                cursor.execute("SELECT COUNT(*) FROM orbit_task")
                assert cursor.fetchone()[0] == before_tasks
        finally:
            admin.rollback()
            # 先释放独立clock锁，让失败的窗口检查也能等到两个请求实际退出，再恢复菜单。
            active_failure = sys.exc_info()[0] is not None
            cleanup_failed = False
            try:
                for future in futures:
                    try:
                        future.result(timeout=15)
                    except Exception:
                        cleanup_failed = True
            finally:
                with admin.cursor() as cursor:
                    cursor.execute(
                        "UPDATE sys_menu SET status=%s WHERE menu_id=31021", (old_status,)
                    )
                admin.commit()
            if cleanup_failed and not active_failure:
                raise AssertionError("并发窗口请求清理未完成")
    assert (
        assert_status(client.post("/api/v1/launch-plans", headers=write, json=body), 201)
        == original
    )
    cases.append(LAUNCH_REPLAY_CONCURRENCY_CASES[0])
    return {"actual_clock_waiters": observed_waiters, "plan_writes": 1, "task_writes": 0}
