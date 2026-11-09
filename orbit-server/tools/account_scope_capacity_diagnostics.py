"""显式隔离child范围诊断；不记录SQL/参数/身份/凭据，不改变业务结果。"""

import asyncio
import functools
import json
import os
import re
import stat
import time
from pathlib import Path
from uuid import uuid4

BASE = Path(__file__).resolve().parents[1] / ".runtime" / "account-scope-capacity-profile"
PHASES = frozenset(
    {
        "AUTH_READ",
        "CLOCK_READ",
        "SCOPE_HEAD_WRITE",
        "SCOPE_HEAD_READ",
        "ACCOUNT_READ",
        "SCOPE_MEMBER_WRITE",
        "SCOPE_MEMBER_READ",
        "SCOPE_SEAL_WRITE",
        "SCOPE_EVENT_WRITE",
        "SCOPE_OUTBOX_WRITE",
        "OTHER",
    }
)


def guard_output(output_dir):
    path = Path(output_dir).absolute()
    if path.parent != BASE or re.fullmatch(r"[a-f0-9]{32}", path.name) is None:
        raise ValueError("SCOPE_DIAGNOSTIC_PATH_REJECTED")
    for item in (path, *path.parents):
        if item.exists():
            value = item.lstat()
            if stat.S_ISLNK(value.st_mode) or getattr(value, "st_file_attributes", 0) & 0x400:
                raise ValueError("SCOPE_DIAGNOSTIC_LINK_REJECTED")
        if item == BASE.parent.parent:
            break
    path.mkdir(parents=True, exist_ok=True)
    if path.resolve() != path:
        raise ValueError("SCOPE_DIAGNOSTIC_PATH_REJECTED")
    return path


def sql_phase(statement):
    text = " ".join(str(statement).upper().split())
    if text.startswith("INSERT INTO ORBIT_ACCOUNT_SCOPE_MEMBER "):
        return "SCOPE_MEMBER_WRITE"
    if text.startswith("UPDATE ORBIT_ACCOUNT_SCOPE_SNAPSHOT SET READY=1"):
        return "SCOPE_SEAL_WRITE"
    for table, phase in (
        ("ORBIT_ACCOUNT_SCOPE_SNAPSHOT", "SCOPE_HEAD"),
        ("ORBIT_ACCOUNT_SCOPE_EVENT", "SCOPE_EVENT"),
        ("ORBIT_ACCOUNT_SCOPE_OUTBOX", "SCOPE_OUTBOX"),
    ):
        if text.startswith("INSERT INTO " + table + " "):
            return phase + "_WRITE"
    if text.startswith("SELECT "):
        if "FROM ORBIT_ACCOUNT_SCOPE_SNAPSHOT " in text:
            return "SCOPE_HEAD_READ"
        if "FROM ORBIT_ACCOUNT_SCOPE_MEMBER " in text:
            return "SCOPE_MEMBER_READ"
        if "FROM ORBIT_AD_ACCOUNT " in text:
            return "ACCOUNT_READ"
        if "FROM ORBIT_ACCOUNT_CLOCK " in text:
            return "CLOCK_READ"
        if any(
            value in text
            for value in (
                "SYS_IDENTITY_SUBJECT",
                "ORBIT_USER_SCOPE",
                "SYS_ROLE_MENU",
                "ORBIT_BUSINESS_USER",
                "ORBIT_BUSINESS_TEAM_MANAGER",
            )
        ):
            return "AUTH_READ"
    return "OTHER"


def _save(path, value):
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        if (
            path.is_symlink()
            or path.exists()
            and getattr(path.lstat(), "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("SCOPE_DIAGNOSTIC_LINK_REJECTED")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=True, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def install_scope_create_diagnostics(output_dir):
    """返回uninstall；只显式测试启动调用，导入本模块不会加载Store或环境。"""
    destination = guard_output(output_dir)
    from orbit_api.account_scope_store import AccountScopeStore

    original = AccountScopeStore.create
    if getattr(original, "_scope_capacity_diagnostic", False) is True:
        raise ValueError("SCOPE_DIAGNOSTIC_ALREADY_INSTALLED")

    @functools.wraps(original)
    async def instrumented(store, session, *args, **kwargs):
        previous = session.execute
        had_local = "execute" in vars(session)
        started = time.perf_counter()
        path = destination / ("scope-create-" + uuid4().hex + ".json")
        report = {
            "schema": 1,
            "status": "RUNNING",
            "execute_restored": False,
            "calls": 0,
            "elapsed_ms": 0.0,
            "member_batches_attempted": 0,
            "member_batches_completed": 0,
            "member_rows_attempted": 0,
            "member_rows_completed": 0,
            "diagnostic_write_failures": 0,
            "sql": {},
        }

        def save():
            report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
            try:
                _save(path, report)
            except (OSError, ValueError):
                # 仅诊断失败不覆盖原业务返回/异常，也不打印文件路径或异常文本。
                report["diagnostic_write_failures"] += 1

        async def measured(statement, *values, **options):
            phase = sql_phase(statement)
            if phase not in PHASES:
                phase = "OTHER"
            bucket = report["sql"].setdefault(
                phase, {"calls": 0, "completed": 0, "failed": 0, "total_ms": 0.0, "max_ms": 0.0}
            )
            report["calls"] += 1
            bucket["calls"] += 1
            parameters = values[0] if values else options.get("params", options.get("parameters"))
            count = len(parameters) if isinstance(parameters, (tuple, list)) else 1
            member = phase == "SCOPE_MEMBER_WRITE"
            if member and type(parameters) is dict and type(parameters.get("member_ids")) is list:
                count = len(parameters["member_ids"])
            if member:
                report["member_batches_attempted"] += 1
                report["member_rows_attempted"] += count
            tick = time.perf_counter()
            try:
                result = await previous(statement, *values, **options)
                bucket["completed"] += 1
                if member:
                    report["member_batches_completed"] += 1
                    report["member_rows_completed"] += count
                return result
            except BaseException:
                bucket["failed"] += 1
                raise
            finally:
                elapsed = (time.perf_counter() - tick) * 1000
                bucket["total_ms"] = round(bucket["total_ms"] + elapsed, 3)
                bucket["max_ms"] = round(max(bucket["max_ms"], elapsed), 3)
                if member:
                    save()

        session.execute = measured
        save()
        try:
            result = await original(store, session, *args, **kwargs)
            report["status"] = "CREATE_RETURNED"  # 不等于外层已commit/HTTP已发出。
            return result
        except asyncio.CancelledError:
            report["status"] = "CANCELLED"
            raise
        except TimeoutError:
            report["status"] = "TIMEOUT"
            raise
        except BaseException:
            report["status"] = "EXCEPTION"
            raise
        finally:
            if had_local:
                session.execute = previous
            else:
                del session.execute
            report["execute_restored"] = True
            save()

    instrumented._scope_capacity_diagnostic = True
    AccountScopeStore.create = instrumented

    def uninstall():
        if AccountScopeStore.create is not instrumented:
            raise ValueError("SCOPE_DIAGNOSTIC_INSTALLATION_CHANGED")
        AccountScopeStore.create = original

    return uninstall


def collect_timeout_diagnostic(admin, database, output_dir):
    destination = guard_output(output_dir)
    if (
        admin.host != "127.0.0.1"
        or type(admin.port) is not int
        or admin.port != 13306
        or not isinstance(database, str)
        or re.fullmatch(r"orbit_py_it_[a-f0-9]{32}", database) is None
    ):
        raise ValueError("SCOPE_DIAGNOSTIC_DATABASE_REJECTED")
    with admin.cursor() as cursor:
        cursor.execute("SELECT DATABASE()")
        if cursor.fetchone()[0] != database:
            raise ValueError("SCOPE_DIAGNOSTIC_DATABASE_REJECTED")
        cursor.execute(
            "SELECT PROCESSLIST_COMMAND,COUNT(*) FROM performance_schema.threads "
            "WHERE PROCESSLIST_DB=%s GROUP BY PROCESSLIST_COMMAND",
            (database,),
        )
        commands = {name: 0 for name in ("QUERY", "SLEEP", "CONNECT", "OTHER")}
        for command, count in cursor.fetchall():
            category = command.upper() if isinstance(command, str) else "OTHER"
            commands[category if category in commands else "OTHER"] += int(count)
        cursor.execute(
            "SELECT COUNT(*) FROM performance_schema.data_lock_waits w "
            "JOIN performance_schema.threads t ON t.THREAD_ID=w.REQUESTING_THREAD_ID "
            "WHERE t.PROCESSLIST_DB=%s",
            (database,),
        )
        waits = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT COUNT(*),COALESCE(SUM(x.trx_rows_locked),0),"
            "COALESCE(SUM(x.trx_rows_modified),0) FROM information_schema.INNODB_TRX x "
            "JOIN performance_schema.threads t ON t.PROCESSLIST_ID=x.trx_mysql_thread_id "
            "WHERE t.PROCESSLIST_DB=%s",
            (database,),
        )
        transactions, locked, modified = (int(value) for value in cursor.fetchone())
    result = {
        "schema": 1,
        "status": "TIMEOUT_SNAPSHOT",
        "commands": commands,
        "lock_waits": waits,
        "transactions": transactions,
        "rows_locked": locked,
        "rows_modified": modified,
    }
    _save(destination / ("timeout-" + uuid4().hex + ".json"), result)
    return result
