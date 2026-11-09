"""仅ORBIT本地13306测试实例的显式容量配置；不连接私有业务数据库。"""

import argparse
import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil
import pymysql

ROOT = Path(__file__).resolve().parents[1]
DATA = (ROOT.parent / ".runtime/mysql-it/data").resolve()
TARGET = 1024**3


def read_settings(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT @@global.innodb_buffer_pool_size,@@global.innodb_redo_log_capacity,"
            "@@global.innodb_flush_log_at_trx_commit,@@global.innodb_buffer_pool_chunk_size,"
            "@@global.innodb_buffer_pool_instances"
        )
        values = cursor.fetchone()
    return dict(
        zip(
            (
                "buffer_pool_bytes",
                "redo_capacity_bytes",
                "flush_log_at_commit",
                "chunk_bytes",
                "instances",
            ),
            values,
            strict=True,
        )
    )


def configure(connection, *, apply=False, available_memory, disk_free):
    if connection.host != "127.0.0.1" or connection.port != 13306:
        raise ValueError("ORBIT_OWNED_FIXTURE_REQUIRED")
    with connection.cursor() as cursor:
        cursor.execute("SELECT @@datadir")
        if Path(cursor.fetchone()[0]).resolve() != DATA:
            raise ValueError("ORBIT_OWNED_DATADIR_REQUIRED")
    before = read_settings(connection)
    granularity = before["chunk_bytes"] * before["instances"]
    pool_target = (
        (max(TARGET, before["buffer_pool_bytes"]) + granularity - 1) // granularity
    ) * granularity
    redo_target = max(TARGET, before["redo_capacity_bytes"])
    report = {
        "executed_at": datetime.now(UTC).isoformat(),
        "scope": "ORBIT-owned local test fixture only; no production or preview process restart",
        "before": before,
        "target_buffer_pool_bytes": pool_target,
        "target_redo_capacity_bytes": redo_target,
        "available_memory_bytes": available_memory,
        "workspace_disk_free_bytes": disk_free,
        "applied_settings": [],
        "result": "READ_ONLY",
    }
    if not apply:
        return report
    if before["flush_log_at_commit"] != 1:
        raise ValueError("CAPACITY_PROFILE_REQUIRES_DURABLE_COMMIT")
    memory_increase = max(0, pool_target - before["buffer_pool_bytes"])
    disk_increase = max(0, redo_target - before["redo_capacity_bytes"])
    # 本机还运行浏览器/IDE/既有预览；预留资源，不按专用数据库服务器比例抢占内存。
    if available_memory < memory_increase + 2 * TARGET or disk_free < disk_increase + 2 * TARGET:
        raise ValueError("CAPACITY_PROFILE_RESOURCE_RESERVE_REQUIRED")
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM information_schema.innodb_trx")
        if cursor.fetchone()[0] != 0:
            raise ValueError("CAPACITY_PROFILE_REQUIRES_NO_ACTIVE_TRANSACTIONS")
        try:
            if before["buffer_pool_bytes"] < pool_target:
                cursor.execute("SET GLOBAL innodb_buffer_pool_size=%s", (pool_target,))
                report["applied_settings"].append("innodb_buffer_pool_size")
            if before["redo_capacity_bytes"] < redo_target:
                cursor.execute("SET GLOBAL innodb_redo_log_capacity=%s", (redo_target,))
                report["applied_settings"].append("innodb_redo_log_capacity")
            deadline = time.monotonic() + 30
            while True:
                cursor.execute("SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_resize_status_code'")
                pool = cursor.fetchone()
                cursor.execute("SHOW GLOBAL STATUS LIKE 'Innodb_redo_log_capacity_resized'")
                redo = cursor.fetchone()
                ready = pool and pool[1] == "0" and redo and int(redo[1]) >= redo_target
                if ready:
                    report["result"] = "APPLIED"
                    break
                if time.monotonic() >= deadline:
                    report["result"] = "RESIZE_PENDING"
                    break
                time.sleep(0.1)
        except Exception as error:
            # 不记录SQL/参数/异常全文；部分应用也必须留下真实状态，不能报成功。
            report["result"] = "PARTIAL_FAILED"
            report["failure_type"] = type(error).__name__
    report["after"] = read_settings(connection)
    if report["after"]["flush_log_at_commit"] != before["flush_log_at_commit"]:
        report["result"] = "FAILED_UNEXPECTED_DURABILITY_CHANGE"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="明确应用1GiB缓冲池与1GiB重做日志")
    args = parser.parse_args()
    # 与既有隔离runner相同的无密码loopback夹具；绝不读取或回退真实.env业务连接。
    with pymysql.connect(
        host="127.0.0.1",
        port=13306,
        user="root",
        password="",
        autocommit=True,
        connect_timeout=3,
        read_timeout=5,
        write_timeout=5,
    ) as connection:
        report = configure(
            connection,
            apply=args.apply,
            available_memory=psutil.virtual_memory().available,
            disk_free=shutil.disk_usage(ROOT).free,
        )
    destination = ROOT / "docs/orbit/evidence/python-mysql060-capacity-profile.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["result"] in {"READ_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
