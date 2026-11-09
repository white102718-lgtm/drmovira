"""显式隔离账户列表诊断；只输出技术计时，不保存SQL、参数或业务值。"""

import asyncio
import functools
import json
import re
import stat
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import unquote_to_bytes
from uuid import uuid4
from weakref import WeakValueDictionary

BASE = Path(__file__).resolve().parents[1] / ".runtime" / "account-list-query-profile"
MAX_REPORTS = 1000
_CURRENT = ContextVar("account_list_query_profile", default=None)
_TAG = "_account_list_query_diagnostic"
_HTTP = ContextVar("account_query_http_profile", default=None)
_RC = ContextVar("account_query_rc_profile", default=None)
_CLOSING = ContextVar("account_query_closing_profile", default=None)
_POOL = ContextVar("account_query_checkout_pool_profile", default=None)
_STAGE_TAG = "_account_query_stage_diagnostic"
_QUOTAS = WeakValueDictionary()


class _OutputQuota:
    def __init__(self, destination):
        self.reserved = sum(1 for _ in destination.iterdir())
        if self.reserved > MAX_REPORTS:
            raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_REPORT_LIMIT")

    def reserve(self):
        if self.reserved >= MAX_REPORTS:
            return False
        self.reserved += 1
        return True


def _quota(destination):
    key = str(destination)
    value = _QUOTAS.get(key)
    if value is None:
        value = _OutputQuota(destination)
        _QUOTAS[key] = value
    return value


_TABLES = (
    ("ORBIT_BROWSER_SESSION", "COOKIE_CURRENT"),
    ("ORBIT_USER_SCOPE", "BUSINESS_AUTH"),
    ("SYS_ROLE_MENU", "BUSINESS_AUTH"),
    ("ORBIT_ACCOUNT_CLOCK", "ACCOUNT_CLOCK"),
    ("ORBIT_ACCOUNT_DETAILS_CLOCK", "DETAILS_CLOCK"),
    ("ORBIT_REFERENCE_CLOCK", "REFERENCE_CLOCK"),
    ("ORBIT_ACCOUNT_SPEND_DAY", "SPEND_AGGREGATE"),
    ("ORBIT_ACCOUNT_IDENTITY_HEAD", "IDENTITY_HEAD"),
    ("ORBIT_ACCOUNT_IDENTITY_EVIDENCE", "IDENTITY_EVIDENCE"),
    ("ORBIT_IDENTITY_PUBLICATION_PROVENANCE", "IDENTITY_PROOF"),
    ("ORBIT_IDENTITY_INVENTORY_SEAL", "IDENTITY_SEAL"),
    ("ORBIT_META_RAW_HEAD", "IDENTITY_RAW"),
    ("ORBIT_IDENTITY_CAPABILITY_RELEASE", "IDENTITY_RELEASE"),
    ("ORBIT_SYSTEM_CONFIGURATION", "SOURCE_CONFIGURATION"),
    ("ORBIT_ACCOUNT_DETAILS_CURRENT", "DETAILS_OBSERVATION"),
    ("ORBIT_AD_ACCOUNT", "ACCOUNT_PAGE"),
    ("ORBIT_VENDOR_ALIAS", "VENDOR_ALIAS"),
    ("ORBIT_REFERENCE", "REFERENCE_CATALOG"),
    ("ORBIT_BUSINESS_TEAM_MANAGER", "MANAGED_TEAMS"),
    ("ORBIT_BUSINESS_USER", "OWNER_DISPLAY"),
)


def guard_output(output_dir):
    path = Path(output_dir).absolute()
    if path.parent != BASE or re.fullmatch(r"[a-f0-9]{32}", path.name) is None:
        raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_PATH_REJECTED")
    for item in (path, *path.parents):
        try:
            value = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(value.st_mode) or getattr(value, "st_file_attributes", 0) & 0x400:
            raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_LINK_REJECTED")
    path.mkdir(parents=True, exist_ok=True)
    if path.resolve() != path:
        raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_PATH_REJECTED")
    return path


def sql_label(statement):
    try:
        text = " ".join(str(statement)[:65536].upper().split())
    except Exception:
        return "OTHER"
    for table, label in _TABLES:
        if re.search(r"\b" + table + r"\b", text):
            return label
    return "SERVER_TIME" if "UTC_TIMESTAMP(" in text else "OTHER"


def _write(destination, report):
    guard_output(destination)
    # 随机技术名，仅结束时落一次；不持久化运行中的参数或异常正文。
    with (destination / ("request-" + uuid4().hex + ".json")).open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=True, allow_nan=False)


def install_account_list_query_diagnostics(output_dir, *, isolated_test=False):
    """显式test-only安装并返回uninstall；导入无副作用，不安装生产路由。"""
    if isolated_test is not True:
        raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_ISOLATION_REQUIRED")
    destination = guard_output(output_dir)
    from orbit_api import identity_publication_summary as summary
    from orbit_api.account_details_store import AccountDetailsStore

    original_list, original_match = AccountDetailsStore.list, summary.matches_current_seal
    if getattr(original_list, _TAG, False) or getattr(original_match, _TAG, False):
        raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_ALREADY_INSTALLED")
    quota, active_sessions = _quota(destination), set()
    counts = {"recorded": 0, "dropped_cursor": 0, "dropped_identifier": 0, "dropped_limit": 0}
    installed = True

    @functools.wraps(original_match)
    def measured_match(*args, **kwargs):
        report = _CURRENT.get()
        if report is None:
            return original_match(*args, **kwargs)
        began = time.perf_counter()
        report["seal"]["calls"] += 1
        try:
            return original_match(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - began
            report["seal"]["total_seconds"] += elapsed
            report["seal"]["max_seconds"] = max(report["seal"]["max_seconds"], elapsed)

    @functools.wraps(original_list)
    async def measured_list(store, session, *args, **kwargs):
        if id(session) in active_sessions or _CURRENT.get() is not None:
            raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_REENTRY_REJECTED")
        cursor = args[2] if len(args) > 2 else kwargs.get("cursor")
        if cursor not in (None, ""):
            counts["dropped_cursor"] += 1
            return await original_list(store, session, *args, **kwargs)
        if kwargs.get("identifier") is not None:
            counts["dropped_identifier"] += 1
            return await original_list(store, session, *args, **kwargs)
        http = _HTTP.get()
        if http is not None and http["destination"] != destination:
            raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_CONTEXT_PATH_CHANGED")
        if http is not None and http["list_report"] is not None:
            raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_REENTRY_REJECTED")
        if http is None and not quota.reserve():
            counts["dropped_limit"] += 1
            return await original_list(store, session, *args, **kwargs)
        if http is not None:
            http["events"]["list_enter"] = time.perf_counter() - http["started"]
        # 参数仅透传；只读取原已规范化query的page_size这一技术枚举，不观察其他值。
        query = args[1] if len(args) > 1 else kwargs.get("query")
        size = query.get("page_size") if type(query) is dict else None
        size = size if type(size) is int and size in (20, 50, 100, 200) else None
        report = {
            "schema": 1,
            "technical_trace": http["trace"] if http is not None else None,
            "output_deferred_to_asgi": http is not None,
            "first_page_only": True,
            "status": "FAILED",
            "page_size": size,
            "items_count": None,
            "list_seconds": 0.0,
            "execute_seconds": 0.0,
            "non_execute_seconds": 0.0,
            "non_execute_is_cpu": False,
            "execute_calls": 0,
            "execute_restored": False,
            "seal": {"calls": 0, "total_seconds": 0.0, "max_seconds": 0.0},
            "sql": {},
        }
        previous = session.execute
        had_local = "execute" in vars(session)
        active_sessions.add(id(session))
        token = _CURRENT.set(report)
        began = time.perf_counter()

        async def measured_execute(statement, *parameters, **options):
            label = sql_label(statement)
            bucket = report["sql"].setdefault(
                label,
                {
                    "calls": 0,
                    "completed": 0,
                    "failed": 0,
                    "total_seconds": 0.0,
                    "max_seconds": 0.0,
                    "rowcount": 0,
                },
            )
            bucket["calls"] += 1
            report["execute_calls"] += 1
            tick = time.perf_counter()
            try:
                result = await previous(statement, *parameters, **options)
                bucket["completed"] += 1
                try:
                    count = getattr(result, "rowcount", None)
                    count = count if type(count) is int and count >= 0 else None
                except Exception:
                    count = None
                bucket["rowcount"] = (
                    None
                    if count is None or bucket["rowcount"] is None
                    else bucket["rowcount"] + count
                )
                return result
            except BaseException:
                bucket["failed"] += 1
                raise
            finally:
                elapsed = time.perf_counter() - tick
                report["execute_seconds"] += elapsed
                bucket["total_seconds"] += elapsed
                bucket["max_seconds"] = max(bucket["max_seconds"], elapsed)

        try:
            session.execute = measured_execute
            service_began = time.perf_counter()
            try:
                value = await original_list(store, session, *args, **kwargs)
            finally:
                service_end = time.perf_counter()
                report["service_seconds"] = service_end - service_began
                if http is not None:
                    http["events"]["list_service_exit"] = service_end - http["started"]
            report["status"] = "RETURNED"
            if type(value) is dict and type(value.get("items")) is list:
                report["items_count"] = len(value["items"])
            return value
        except asyncio.CancelledError:
            report["status"] = "CANCELLED"
            raise
        finally:
            report["list_seconds"] = time.perf_counter() - began
            report["non_execute_seconds"] = max(
                0.0, report["list_seconds"] - report["execute_seconds"]
            )
            if had_local:
                session.execute = previous
            elif "execute" in vars(session):
                del session.execute
            report["execute_restored"] = session.execute == previous
            _CURRENT.reset(token)
            active_sessions.discard(id(session))
            try:
                if http is not None:
                    http["list_report"] = report
                    http["events"]["list_wrapper_exit"] = time.perf_counter() - http["started"]
                else:
                    _write(destination, report)
                counts["recorded"] += 1
            except (OSError, ValueError):
                # 诊断磁盘失败不吞业务返回/异常，不打印异常正文或目标路径。
                pass

    setattr(measured_list, _TAG, True)
    setattr(measured_match, _TAG, True)
    AccountDetailsStore.list, summary.matches_current_seal = measured_list, measured_match

    def uninstall():
        nonlocal installed
        if not installed:
            return
        if (
            AccountDetailsStore.list is not measured_list
            or summary.matches_current_seal is not measured_match
        ):
            raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_WRAPPER_CHANGED")
        AccountDetailsStore.list, summary.matches_current_seal = original_list, original_match
        installed = False

    uninstall.summary = lambda: {"first_page_only": True, **counts}
    return uninstall


def _target_http(scope):
    if (
        scope.get("type") != "http"
        or scope.get("method") != "GET"
        or scope.get("path") != "/api/v1/accounts/extended"
    ):
        return False
    query = scope.get("query_string", b"")
    # 只判断cursor存在性；不解析/记录其他参数，超长诊断输入直接透传原应用处理。
    if type(query) is not bytes or len(query) > 16384:
        return False
    for part in query.split(b"&"):
        key, _, value = part.partition(b"=")
        if len(key) <= 18 and unquote_to_bytes(key) == b"cursor" and value:
            return False
    return True


def _phases(events, list_report):
    def delta(left, right):
        if events[left] is None or events[right] is None:
            return None
        return events[right] - events[left]

    return {
        "before_list": events["list_enter"],
        "service": list_report.get("service_seconds") if list_report is not None else None,
        "list_wrapper": delta("list_enter", "list_wrapper_exit"),
        "after_list_to_response_start": delta("list_wrapper_exit", "response_start_before"),
        "response_start_send": delta("response_start_before", "response_start_after"),
        "response_start_to_last_body": delta("response_start_after", "last_body_before"),
        "last_body_send": delta("last_body_before", "last_body_after"),
        "app_total": events["app_end"],
    }


def wrap_account_query_http(app, output_dir, *, isolated_test=False):
    """纯ASGI外层；不读取body/headers/status，非目标和lifespan完全原样透传。"""
    if isolated_test is not True:
        raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_ISOLATION_REQUIRED")
    if getattr(app, "_account_query_http_diagnostic", False):
        raise ValueError("ACCOUNT_HTTP_DIAGNOSTIC_ALREADY_WRAPPED")
    destination = guard_output(output_dir)
    quota = _quota(destination)
    counts = {"recorded": 0, "dropped_limit": 0}

    async def wrapped(scope, receive, send):
        if not _target_http(scope):
            return await app(scope, receive, send)
        if _HTTP.get() is not None:
            raise ValueError("ACCOUNT_HTTP_DIAGNOSTIC_REENTRY_REJECTED")
        if not quota.reserve():
            counts["dropped_limit"] += 1
            return await app(scope, receive, send)
        events = dict.fromkeys(
            (
                "list_enter",
                "list_service_exit",
                "list_wrapper_exit",
                "response_start_before",
                "response_start_after",
                "last_body_before",
                "last_body_after",
                "app_end",
            )
        )
        observation = {
            "destination": destination,
            "trace": uuid4().hex,
            "started": time.perf_counter(),
            "events": events,
            "list_report": None,
        }
        token = _HTTP.set(observation)
        status = "FAILED"
        send_seconds, send_calls, body_send_seconds = 0.0, 0, 0.0

        async def measured_send(message):
            nonlocal send_seconds, send_calls, body_send_seconds
            kind = message.get("type")
            last = kind == "http.response.body" and not message.get("more_body", False)
            tick = time.perf_counter()
            if kind == "http.response.start":
                events["response_start_before"] = tick - observation["started"]
            if last:
                events["last_body_before"] = tick - observation["started"]
            try:
                return await send(message)
            finally:
                end = time.perf_counter()
                send_seconds += end - tick
                send_calls += 1
                if kind == "http.response.body":
                    body_send_seconds += end - tick
                if kind == "http.response.start":
                    events["response_start_after"] = end - observation["started"]
                if last:
                    events["last_body_after"] = end - observation["started"]

        try:
            result = await app(scope, receive, measured_send)
            status = "RETURNED"
            return result
        except asyncio.CancelledError:
            status = "CANCELLED"
            raise
        finally:
            events["app_end"] = time.perf_counter() - observation["started"]
            _HTTP.reset(token)
            for cleanup in observation.pop("_native_lease_cleanups", []):
                try:
                    cleanup()
                except Exception:
                    # 诊断清理不能掩盖原ASGI异常或取消。
                    pass
            report = {
                "schema": 2,
                "first_page_only": True,
                "technical_trace": observation["trace"],
                "status": status,
                "events_seconds": events,
                "phases_seconds": _phases(events, observation["list_report"]),
                "send_calls": send_calls,
                "send_seconds": send_seconds,
                "body_send_seconds": body_send_seconds,
                "wall_time_not_cpu": True,
                "output_deferred_after_app_end": True,
                "list": observation["list_report"],
                "detailed_stages": observation.get("detailed_stages", {}),
                "native_resolver_observed": "native_auth_resolve"
                in observation.get("detailed_stages", {}),
                "cookie_resolver_timing": "UNKNOWN",
                "pool_checkout_samples": observation.get("pool_checkout_samples", []),
                "pool_checkout_observation": "OBSERVED"
                if observation.get("pool_checkout_samples")
                else "UNKNOWN",
                "native_lease": observation.get("native_lease", {"observation": "UNKNOWN"}),
            }
            try:
                _write(destination, report)
                counts["recorded"] += 1
            except (OSError, ValueError):
                pass

    wrapped._account_query_http_diagnostic = True
    wrapped.summary = lambda: {"first_page_only": True, **counts}
    return wrapped


def _stage_begin(label):
    observation = _HTTP.get()
    if observation is None:
        return None
    try:
        began = time.perf_counter()
        bucket = observation.setdefault("detailed_stages", {}).setdefault(
            label,
            {
                "calls": 0,
                "failed": 0,
                "cancelled": 0,
                "total_seconds": 0.0,
                "max_seconds": 0.0,
                "first_enter": None,
                "last_exit": None,
                "intervals": [],
            },
        )
        bucket["calls"] += 1
        if bucket["first_enter"] is None:
            bucket["first_enter"] = began - observation["started"]
        return observation, bucket, began
    except Exception:
        return None


def _stage_end(stamp, outcome):
    if stamp is None:
        return
    try:
        observation, bucket, began = stamp
        end = time.perf_counter()
        bucket["total_seconds"] += end - began
        bucket["max_seconds"] = max(bucket["max_seconds"], end - began)
        bucket["last_exit"] = end - observation["started"]
        bucket["failed"] += int(outcome == "FAILED")
        bucket["cancelled"] += int(outcome == "CANCELLED")
        if len(bucket["intervals"]) < 64:
            bucket["intervals"].append(
                [began - observation["started"], end - observation["started"]]
            )
    except Exception:
        pass


def _selected(selector, args):
    if _HTTP.get() is None:
        return False
    try:
        return selector(args)
    except Exception:
        # 诊断自省失败只使该段未知，不能掩盖原对象的业务返回/异常。
        return False


def _async_stage(original, label, selector=lambda args: True):
    @functools.wraps(original)
    async def wrapper(*args, **kwargs):
        if not _selected(selector, args):
            return await original(*args, **kwargs)
        stamp, outcome = _stage_begin(label), "FAILED"
        try:
            result = await original(*args, **kwargs)
            outcome = "RETURNED"
            return result
        except asyncio.CancelledError:
            outcome = "CANCELLED"
            raise
        finally:
            _stage_end(stamp, outcome)

    setattr(wrapper, _STAGE_TAG, True)
    return wrapper


def _sync_stage(original, label, selector=lambda args: True):
    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        if not _selected(selector, args):
            return original(*args, **kwargs)
        stamp, outcome = _stage_begin(label), "FAILED"
        try:
            result = original(*args, **kwargs)
            outcome = "RETURNED"
            return result
        finally:
            _stage_end(stamp, outcome)

    setattr(wrapper, _STAGE_TAG, True)
    return wrapper


def _stage_targets():
    # 只显式安装时导入已运行环境，默认模块导入不加载框架配置。
    from module_admin.service.login_service import LoginService
    from sqlalchemy.dialects.mysql.asyncmy import MySQLDialect_asyncmy
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSessionTransaction
    from starlette.responses import JSONResponse

    from orbit_api import account_details_routes

    return {
        "route": account_details_routes,
        "login": LoginService,
        "connection": AsyncConnection,
        "transaction": AsyncSessionTransaction,
        "dialect": MySQLDialect_asyncmy,
        "response": JSONResponse,
    }


def install_account_query_stage_diagnostics(output_dir, *, isolated_test=False):
    """补充同trace固定阶段；无SQL、无策略修改，返回精确卸载函数。"""
    if isolated_test is not True:
        raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_ISOLATION_REQUIRED")
    guard_output(output_dir)
    targets = _stage_targets()
    patches = []

    def plan(owner, name, replacement):
        had_local = name in vars(owner)
        descriptor = vars(owner).get(name)
        current = getattr(owner, name)
        if getattr(current, _STAGE_TAG, False):
            raise ValueError("ACCOUNT_STAGE_DIAGNOSTIC_ALREADY_INSTALLED")
        patches.append((owner, name, had_local, descriptor, replacement))

    login = targets["login"]
    descriptor = vars(login).get("_resolve_current_user")
    if not isinstance(descriptor, classmethod):
        raise ValueError("ACCOUNT_STAGE_NATIVE_RESOLVER_SHAPE_CHANGED")
    native = _async_stage(descriptor.__func__, "native_auth_resolve")
    plan(login, "_resolve_current_user", classmethod(native))

    route = targets["route"]
    original_rc = route.read_committed_session

    @asynccontextmanager
    async def timed_rc(*args, **kwargs):
        state = {"connection": None, "session": None}
        token = _RC.set(state)
        entering, exiting, outcome = _stage_begin("rc_context_enter"), None, "FAILED"
        try:
            async with original_rc(*args, **kwargs) as session:
                _stage_end(entering, "RETURNED")
                entering = None
                state["session"] = session
                try:
                    yield session
                finally:
                    exiting = _stage_begin("rc_context_exit")
            outcome = "RETURNED"
        except asyncio.CancelledError:
            outcome = "CANCELLED"
            raise
        finally:
            _stage_end(entering, outcome)
            _stage_end(exiting, outcome)
            _RC.reset(token)

    @functools.wraps(original_rc)
    def rc_wrapper(*args, **kwargs):
        if _HTTP.get() is None:
            return original_rc(*args, **kwargs)
        return timed_rc(*args, **kwargs)

    setattr(rc_wrapper, _STAGE_TAG, True)
    plan(route, "read_committed_session", rc_wrapper)

    def connection_enter(args):
        state = _RC.get()
        if state is None or state["connection"] is not None:
            return False
        state["connection"] = args[0]
        return True

    def same_connection(args):
        state = _RC.get()
        return state is not None and state["connection"] is args[0]

    connection = targets["connection"]
    for name, label, selector in (
        ("__aenter__", "rc_checkout", connection_enter),
        ("execution_options", "rc_isolation_options", same_connection),
        ("__aexit__", "rc_connection_exit", same_connection),
    ):
        plan(connection, name, _async_stage(getattr(connection, name), label, selector))
    original_close = connection.close
    measured_close = _async_stage(original_close, "rc_connection_close", same_connection)

    @functools.wraps(original_close)
    async def close_wrapper(*args, **kwargs):
        if not _selected(same_connection, args):
            return await original_close(*args, **kwargs)
        token = _CLOSING.set(args[0])
        try:
            return await measured_close(*args, **kwargs)
        finally:
            _CLOSING.reset(token)

    setattr(close_wrapper, _STAGE_TAG, True)
    plan(connection, "close", close_wrapper)

    def same_session(args):
        state = _RC.get()
        return state is not None and args[0].session is state["session"]

    transaction = targets["transaction"]
    plan(
        transaction,
        "__aexit__",
        _async_stage(transaction.__aexit__, "rc_transaction_exit", same_session),
    )

    def same_dialect(args):
        state = _RC.get()
        return (
            state is not None
            and _CLOSING.get() is state["connection"]
            and state["connection"] is not None
            and state["connection"].dialect is args[0]
        )

    dialect = targets["dialect"]
    plan(
        dialect,
        "reset_isolation_level",
        _sync_stage(dialect.reset_isolation_level, "rc_isolation_reset", same_dialect),
    )
    response = targets["response"]
    plan(response, "__init__", _sync_stage(response.__init__, "json_response_construction"))

    applied = []
    try:
        for patch in patches:
            owner, name, _, _, replacement = patch
            setattr(owner, name, replacement)
            applied.append(patch)
    except BaseException:
        for owner, name, had_local, original, _ in reversed(applied):
            if had_local:
                setattr(owner, name, original)
            else:
                delattr(owner, name)
        raise
    installed = True

    def uninstall():
        nonlocal installed
        if not installed:
            return
        # 先核全体再恢复，不能恢复一半才发现别人替换了其余包装。
        if any(
            vars(owner).get(name) is not replacement for owner, name, _, _, replacement in patches
        ):
            raise ValueError("ACCOUNT_STAGE_DIAGNOSTIC_WRAPPER_CHANGED")
        for owner, name, had_local, original, _ in reversed(patches):
            if had_local:
                setattr(owner, name, original)
            else:
                delattr(owner, name)
        installed = False

    return uninstall


def _pool_targets():
    from sqlalchemy.dialects.mysql.asyncmy import MySQLDialect_asyncmy
    from sqlalchemy.ext.asyncio import AsyncConnection
    from sqlalchemy.pool.impl import QueuePool
    from sqlalchemy.util.queue import AsyncAdaptedQueue, Empty

    return {
        "connection": AsyncConnection,
        "pool": QueuePool,
        "queue": AsyncAdaptedQueue,
        "dialect": MySQLDialect_asyncmy,
        "empty": Empty,
    }


def _pool_counts(pool):
    # 只读固定整数；不调用status/repr，不持久化pool或连接标识。
    try:
        values = {
            "size": pool.size(),
            "checkedout": pool.checkedout(),
            "overflow": pool.overflow(),
            "max_overflow": pool._max_overflow,
        }
        return values if all(type(v) is int for v in values.values()) else None
    except Exception:
        return None


def install_account_query_pool_diagnostics(output_dir, *, isolated_test=False):
    """仅细分当前RC checkout；同trace嵌套墙钟，不推断池耗尽。"""
    if isolated_test is not True:
        raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_ISOLATION_REQUIRED")
    guard_output(output_dir)
    targets = _pool_targets()
    patches = []
    tag = "_account_query_pool_diagnostic"

    def plan(owner, name, replacement):
        if getattr(getattr(owner, name), tag, False):
            raise ValueError("ACCOUNT_POOL_DIAGNOSTIC_ALREADY_INSTALLED")
        setattr(replacement, tag, True)
        patches.append((owner, name, name in vars(owner), vars(owner).get(name), replacement))

    def selected(args, kind):
        state = _POOL.get()
        return state is not None and state[kind] is args[0]

    def measure(original, kind, label):
        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            if not _selected(lambda a: selected(a, kind), args):
                return original(*args, **kwargs)
            actual_label = label
            if kind == "queue":
                block = args[1] if len(args) > 1 else kwargs.get("block", True)
                # block=True也可能直接get_nowait成功，不能称为真实队列等待。
                actual_label += "_blocking" if block else "_nonblocking"
            stamp, outcome = _stage_begin(actual_label), "FAILED"
            try:
                value = original(*args, **kwargs)
                outcome = "RETURNED"
                return value
            except targets["empty"]:
                outcome = "EMPTY"
                if stamp is not None:
                    try:
                        stamp[1]["empty"] = stamp[1].get("empty", 0) + 1
                    except Exception:
                        pass
                raise
            except asyncio.CancelledError:
                outcome = "CANCELLED"
                raise
            finally:
                _stage_end(stamp, outcome)

        return wrapper

    original_enter = targets["connection"].__aenter__

    @functools.wraps(original_enter)
    async def checkout(*args, **kwargs):
        def bind(values):
            rc = _RC.get()
            if rc is None or (rc["connection"] is not None and rc["connection"] is not values[0]):
                return False
            pool = values[0].engine.sync_engine.pool
            return isinstance(pool, targets["pool"])

        if not _selected(bind, args):
            return await original_enter(*args, **kwargs)
        # bind自省成功后再次取值，失败也必须继续原checkout，不遮业务异常。
        try:
            pool = args[0].engine.sync_engine.pool
            state = {"pool": pool, "queue": pool._pool, "dialect": pool._dialect}
            observation = _HTTP.get()
            samples = observation.setdefault("pool_checkout_samples", [])
            sample = {"before": _pool_counts(pool), "after": None, "outcome": "FAILED"}
            if len(samples) < 64:
                samples.append(sample)
        except Exception:
            return await original_enter(*args, **kwargs)
        token = _POOL.set(state)
        try:
            value = await original_enter(*args, **kwargs)
            sample["outcome"] = "RETURNED"
            return value
        except asyncio.CancelledError:
            sample["outcome"] = "CANCELLED"
            raise
        finally:
            sample["after"] = _pool_counts(pool)
            _POOL.reset(token)

    plan(targets["connection"], "__aenter__", checkout)
    for kind, name, label in (
        ("pool", "_do_get", "rc_pool_do_get"),
        ("queue", "get", "rc_pool_queue_get"),
        ("dialect", "connect", "rc_pool_physical_connect"),
        ("dialect", "_do_ping_w_event", "rc_pool_pre_ping"),
    ):
        owner = targets[kind]
        plan(owner, name, measure(getattr(owner, name), kind, label))

    applied = []
    try:
        for patch in patches:
            owner, name, _, _, replacement = patch
            setattr(owner, name, replacement)
            applied.append(patch)
    except BaseException:
        for owner, name, local, original, _ in reversed(applied):
            if local:
                setattr(owner, name, original)
            else:
                delattr(owner, name)
        raise
    installed = True

    def uninstall():
        nonlocal installed
        if not installed:
            return
        if any(
            vars(owner).get(name) is not replacement for owner, name, _, _, replacement in patches
        ):
            raise ValueError("ACCOUNT_POOL_DIAGNOSTIC_WRAPPER_CHANGED")
        for owner, name, local, original, _ in reversed(patches):
            if local:
                setattr(owner, name, original)
            else:
                delattr(owner, name)
        installed = False

    return uninstall


def _native_lease_targets():
    from module_admin.service.login_service import LoginService
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

    return {
        "login": LoginService,
        "connection": AsyncConnection,
        "engine": AsyncEngine,
        "session": AsyncSession,
        "event": event,
    }


def install_account_query_native_lease_diagnostics(output_dir, *, isolated_test=False):
    """请求内关联native租约与RC；只监听事件，不触发连接/SQL或释放业务资源。"""
    if isolated_test is not True:
        raise ValueError("ACCOUNT_LIST_DIAGNOSTIC_ISOLATION_REQUIRED")
    guard_output(output_dir)
    targets = _native_lease_targets()
    patches = []
    active = [0]
    failed_cleanups = []
    tag = "_account_query_native_lease_diagnostic"

    def plan(owner, name, value):
        current = getattr(owner, name)
        if getattr(current, tag, False):
            raise ValueError("ACCOUNT_NATIVE_LEASE_ALREADY_INSTALLED")
        function = value.__func__ if isinstance(value, classmethod) else value
        setattr(function, tag, True)
        patches.append((owner, name, name in vars(owner), vars(owner).get(name), value))

    def record(connection):
        # 只读已存在的代理字段，不用Connection.connection属性，避免重连副作用。
        proxy = getattr(connection, "_dbapi_connection", None)
        return getattr(proxy, "_connection_record", None) if proxy is not None else None

    def setup(observation, session):
        report = {
            "observation": "UNKNOWN",
            "native_leases": [],
            "rc_checkouts": [],
            "resolver_exit_transaction_active": None,
            "cleanup": "NOT_INSTALLED",
        }
        observation["native_lease"] = report
        if not isinstance(session, targets["session"]):
            return None
        try:
            bind = session.bind
            engine = bind.engine if isinstance(bind, targets["connection"]) else bind
            if not isinstance(engine, targets["engine"]):
                return None
            pool, sync_session = engine.sync_engine.pool, session.sync_session
        except Exception:
            return None
        state = {"pool": pool, "records": [], "pending": [], "report": report, "closed": False}
        observation["_native_lease_state"] = state
        listeners = []
        event = targets["event"]

        def now():
            return time.perf_counter() - observation["started"]

        def checkout(raw, entry, proxy):
            try:
                # pool事件可能由其他并发请求触发；只存当前HTTP同一字典的候选。
                if state["closed"] or _HTTP.get() is not observation:
                    return
                if len(state["pending"]) < 16:
                    state["pending"].append((entry, now()))
                else:
                    report["observation"] = "UNKNOWN"
            except Exception:
                report["observation"] = "UNKNOWN"

        def begin(actual_session, tx, connection):
            try:
                if state["closed"] or actual_session is not sync_session:
                    return
                if connection.engine.pool is not pool:
                    report["observation"] = "UNKNOWN"
                    return
                entry = record(connection)
                if entry is None or len(state["records"]) >= 16:
                    report["observation"] = "UNKNOWN"
                    return
                if any(
                    item["entry"] is entry and item["released"] is False
                    for item in state["records"]
                ):
                    return
                candidates = [stamp for candidate, stamp in state["pending"] if candidate is entry]
                row = {
                    "checkout_seconds": candidates[-1] if candidates else None,
                    "after_begin_seconds": now(),
                    "release_seconds": None,
                    "active_at_resolver_exit": None,
                }
                state["records"].append({"entry": entry, "released": False, "row": row})
                report["native_leases"].append(row)
                if not candidates:
                    report["observation"] = "UNKNOWN"
            except Exception:
                report["observation"] = "UNKNOWN"

        def checkin(raw, entry):
            try:
                if state["closed"]:
                    return
                for item in state["records"]:
                    if item["entry"] is entry and not item["released"]:
                        item["released"] = True
                        item["row"]["release_seconds"] = now()
            except Exception:
                report["observation"] = "UNKNOWN"

        def cleanup():
            if report["cleanup"] == "REMOVED":
                return
            state["closed"] = True
            failed = False
            remaining = []
            for owner, name, callback in reversed(listeners):
                try:
                    event.remove(owner, name, callback)
                except Exception:
                    failed = True
                    remaining.append((owner, name, callback))
            listeners[:] = list(reversed(remaining))
            report["cleanup"] = "FAILED" if failed else "REMOVED"
            if failed:
                if cleanup not in failed_cleanups:
                    failed_cleanups.append(cleanup)
            else:
                active[0] -= 1
                if cleanup in failed_cleanups:
                    failed_cleanups.remove(cleanup)
            # 断开私有对象引用，防止报告字典延长业务连接/session生命周期。
            observation.pop("_native_lease_state", None)
            state["records"].clear()
            state["pending"].clear()

        active[0] += 1
        report["cleanup"] = "PENDING"
        observation.setdefault("_native_lease_cleanups", []).append(cleanup)
        try:
            for owner, name, callback in (
                (pool, "checkout", checkout),
                (pool, "checkin", checkin),
                (sync_session, "after_begin", begin),
            ):
                event.listen(owner, name, callback)
                listeners.append((owner, name, callback))
            report["observation"] = "OBSERVED"
            # 预存事务只读核已有连接；没有先前checkout时间时必须UNKNOWN。
            tx = sync_session.get_transaction()
            connections = getattr(tx, "_connections", {}) if tx is not None else {}
            if len(connections) > 32:
                report["observation"] = "UNKNOWN"
            else:
                for value in connections.values():
                    begin(sync_session, tx, value[0])
        except Exception:
            report["observation"] = "UNKNOWN"
            cleanup()
            return None
        return state

    login = targets["login"]
    descriptor = vars(login).get("_resolve_current_user")
    if not isinstance(descriptor, classmethod):
        raise ValueError("ACCOUNT_NATIVE_LEASE_RESOLVER_SHAPE_CHANGED")
    original_native = descriptor.__func__

    @functools.wraps(original_native)
    async def native(*args, **kwargs):
        observation = _HTTP.get()
        state = None
        session = args[3] if len(args) > 3 else kwargs.get("query_db")
        if observation is not None and "native_lease" not in observation:
            state = setup(observation, session)
        try:
            return await original_native(*args, **kwargs)
        finally:
            if state is not None:
                try:
                    state["report"]["resolver_exit_transaction_active"] = bool(
                        session.in_transaction()
                    )
                    for item in state["records"]:
                        item["row"]["active_at_resolver_exit"] = not item["released"]
                except Exception:
                    state["report"]["observation"] = "UNKNOWN"

    plan(login, "_resolve_current_user", classmethod(native))
    connection_class = targets["connection"]
    original_enter = connection_class.__aenter__

    @functools.wraps(original_enter)
    async def rc_enter(*args, **kwargs):
        observation = _HTTP.get()
        state = observation.get("_native_lease_state") if observation is not None else None
        row = None
        try:
            rc = _RC.get()
            if (
                state is not None
                and not state["closed"]
                and rc is not None
                and (rc["connection"] is None or rc["connection"] is args[0])
            ):
                if len(state["report"]["rc_checkouts"]) < 16:
                    row = {
                        "enter_seconds": time.perf_counter() - observation["started"],
                        "exit_seconds": None,
                        "outcome": "FAILED",
                        "same_pool": args[0].engine.sync_engine.pool is state["pool"],
                        "active_native_leases_at_enter": sum(
                            not item["released"] for item in state["records"]
                        ),
                        "active_native_leases_at_exit": None,
                        "same_active_native_record": None,
                    }
                    state["report"]["rc_checkouts"].append(row)
        except Exception:
            row = None
        try:
            value = await original_enter(*args, **kwargs)
            if row is not None:
                row["outcome"] = "RETURNED"
            return value
        except asyncio.CancelledError:
            if row is not None:
                row["outcome"] = "CANCELLED"
            raise
        finally:
            if row is not None:
                try:
                    row["exit_seconds"] = time.perf_counter() - observation["started"]
                    row["active_native_leases_at_exit"] = sum(
                        not item["released"] for item in state["records"]
                    )
                    entry = record(args[0].sync_connection)
                    if entry is not None:
                        row["same_active_native_record"] = any(
                            item["entry"] is entry and not item["released"]
                            for item in state["records"]
                        )
                except Exception:
                    pass

    plan(connection_class, "__aenter__", rc_enter)
    applied = []
    try:
        for patch in patches:
            owner, name, _, _, replacement = patch
            setattr(owner, name, replacement)
            applied.append(patch)
    except BaseException:
        for owner, name, local, original, _ in reversed(applied):
            if local:
                setattr(owner, name, original)
            else:
                delattr(owner, name)
        raise
    installed = True

    def uninstall():
        nonlocal installed
        if not installed:
            return
        for cleanup in tuple(failed_cleanups):
            cleanup()
        if active[0]:
            raise ValueError("ACCOUNT_NATIVE_LEASE_REQUEST_ACTIVE")
        if any(
            vars(owner).get(name) is not replacement for owner, name, _, _, replacement in patches
        ):
            raise ValueError("ACCOUNT_NATIVE_LEASE_WRAPPER_CHANGED")
        for owner, name, local, original, _ in reversed(patches):
            if local:
                setattr(owner, name, original)
            else:
                delattr(owner, name)
        installed = False

    return uninstall
