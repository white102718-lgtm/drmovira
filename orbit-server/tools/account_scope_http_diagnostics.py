"""显式隔离范围POST同请求墙钟诊断；不读取参数、认证头或业务响应。"""

import asyncio
import contextvars
import functools
import json
import os
import re
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

if __package__:
    from .account_scope_capacity_diagnostics import (
        PHASES,
        install_scope_create_diagnostics,
        sql_phase,
    )
else:
    from account_scope_capacity_diagnostics import (
        PHASES,
        install_scope_create_diagnostics,
        sql_phase,
    )

BASE = Path(__file__).resolve().parents[1] / ".runtime" / "account-scope-http-profile"
MAX_REQUESTS = 1000
MAX_SPANS = 512
_TRACE = contextvars.ContextVar("orbit_scope_http_diagnostic", default=None)
_installed = None


def guard_output(output_dir, *, isolated_test=False):
    if isolated_test is not True:
        raise ValueError("SCOPE_HTTP_EXPLICIT_ISOLATED_TEST_REQUIRED")
    path = Path(output_dir).absolute()
    if path.parent != BASE or re.fullmatch(r"[a-f0-9]{32}", path.name) is None:
        raise ValueError("SCOPE_HTTP_PATH_REJECTED")
    for entry in (path, *path.parents):
        try:
            mode = entry.lstat()
        except FileNotFoundError:
            mode = None
        if mode is not None:
            if stat.S_ISLNK(mode.st_mode) or getattr(mode, "st_file_attributes", 0) & 0x400:
                raise ValueError("SCOPE_HTTP_LINK_REJECTED")
        if entry == BASE.parent.parent:
            break
    path.mkdir(parents=True, exist_ok=True)
    if path.resolve() != path:
        raise ValueError("SCOPE_HTTP_PATH_REJECTED")
    return path


class Observation:
    def __init__(self, state, path):
        self.state, self.path = state, path
        self.started, self.closed, self.executing = time.perf_counter(), False, False
        self.report = {
            "schema": 1,
            "trace": path.stem,
            "status": "RUNNING",
            "clock": "PERF_COUNTER_RELATIVE_MS_WALL_NOT_CPU",
            "native_scope": "NATIVE_RESOLVER_ONLY_OTHER_COOKIE_WORK_UNKNOWN",
            "store_scope": "ORDINARY_LAZY_SESSION_NOT_RC",
            "timing": {"http_enter_ms": 0.0},
            "native_calls": 0,
            "store_calls": 0,
            "sql_calls": 0,
            "member_batches_attempted": 0,
            "member_batches_completed": 0,
            "inflight_sql": None,
            "spans": [],
            "dropped_spans": 0,
            "diagnostic_write_failures": 0,
            "execute_restored": None,
        }

    def now(self):
        return round((time.perf_counter() - self.started) * 1000, 3)

    def mark(self, name):
        if not self.closed:
            self.report["timing"][name] = self.now()
            self.save()

    def span(self, phase, **technical):
        row = {
            "phase": phase,
            "enter_ms": self.now(),
            "exit_ms": None,
            "outcome": "RUNNING",
            **technical,
        }
        if len(self.report["spans"]) < MAX_SPANS:
            self.report["spans"].append(row)
        else:
            self.report["dropped_spans"] += 1
        return row

    def finish(self, row, outcome):
        if not self.closed:
            row.update(exit_ms=self.now(), outcome=outcome)
            self.save()

    def save(self):
        if self.closed:
            return
        temporary = None
        try:
            guard_output(self.state.path, isolated_test=True)
            if self.path.is_symlink() or (
                self.path.exists() and getattr(self.path.lstat(), "st_file_attributes", 0) & 0x400
            ):
                raise ValueError("SCOPE_HTTP_LINK_REJECTED")
            temporary = self.path.with_name(self.path.name + "." + uuid4().hex + ".tmp")
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(self.report, stream, ensure_ascii=True, allow_nan=False)
            os.replace(temporary, self.path)
        except BaseException:
            # 任何诊断错误不得覆盖原认证、SQL、取消或应用异常。
            self.report["diagnostic_write_failures"] += 1
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except BaseException:
                    pass


def current(state):
    observation = _TRACE.get()
    return (
        observation
        if (
            isinstance(observation, Observation)
            and observation.state is state
            and not observation.closed
        )
        else None
    )


def outcome(exc):
    return "CANCELLED" if isinstance(exc, asyncio.CancelledError) else "ERROR"


def _targets():
    from module_admin.service.login_service import LoginService

    from orbit_api.account_scope_store import AccountScopeStore

    return LoginService, AccountScopeStore


def install_scope_http_diagnostics(output_dir, *, isolated_test=False):
    """旧scope诊断先安装、本模块后安装；卸载逆序，所有原descriptor精确恢复。"""
    global _installed
    path = guard_output(output_dir, isolated_test=isolated_test)
    if _installed is not None:
        raise ValueError("SCOPE_HTTP_ALREADY_INSTALLED")
    LoginService, AccountScopeStore = _targets()
    native_descriptor = vars(LoginService).get("_resolve_current_user")
    if not isinstance(native_descriptor, classmethod):
        raise ValueError("SCOPE_HTTP_NATIVE_DESCRIPTOR_CHANGED")
    original_native, original_create = native_descriptor.__func__, AccountScopeStore.create
    state = type("Installation", (), {})()
    state.path, state.active, state.closed = path, 0, False
    state.written = len(list(path.glob("*.json")))
    state.dropped = 0

    @functools.wraps(original_native)
    async def native(*args, **kwargs):
        observed = current(state)
        if observed is None:
            return await original_native(*args, **kwargs)
        observed.report["native_calls"] += 1
        span = observed.span("NATIVE_RESOLVER")
        observed.mark("native_enter_ms")
        result = "RETURNED"
        try:
            return await original_native(*args, **kwargs)
        except BaseException as exc:
            result = outcome(exc)
            raise
        finally:
            observed.finish(span, result)
            observed.mark("native_exit_ms")

    @functools.wraps(original_create)
    async def create(store, session, *args, **kwargs):
        observed = current(state)
        if observed is None or observed.executing:
            return await original_create(store, session, *args, **kwargs)
        observed.report["store_calls"] += 1
        observed.mark("store_enter_ms")
        span = observed.span("STORE_CREATE")

        async def unmeasured():
            result = "RETURNED"
            try:
                return await original_create(store, session, *args, **kwargs)
            except BaseException as exc:
                result = outcome(exc)
                raise
            finally:
                observed.finish(span, result)
                observed.mark("store_exit_ms")

        try:
            previous, had_local = session.execute, "execute" in vars(session)
        except Exception:
            observed.report["execute_restored"] = "UNKNOWN"
            return await unmeasured()

        async def execute(statement, *values, **options):
            if observed.closed:
                return await previous(statement, *values, **options)
            # SQL只在内存归类；不读取values/options，不输出SQL或它们的repr。
            try:
                phase = sql_phase(statement)
                if type(phase) is not str or phase not in PHASES:
                    phase = "OTHER"
            except Exception:
                phase = "OTHER"
            observed.report["sql_calls"] += 1
            member = phase == "SCOPE_MEMBER_WRITE"
            if member:
                observed.report["member_batches_attempted"] += 1
            entry = observed.span(
                phase,
                sql_ordinal=observed.report["sql_calls"],
                member_batch=observed.report["member_batches_attempted"] if member else None,
            )
            observed.report["inflight_sql"] = dict(entry)
            observed.save()
            result = "RETURNED"
            try:
                value = await previous(statement, *values, **options)
                if member:
                    observed.report["member_batches_completed"] += 1
                return value
            except BaseException as exc:
                result = outcome(exc)
                raise
            finally:
                observed.report["inflight_sql"] = None
                observed.finish(entry, result)

        observed.executing = True
        try:
            session.execute = execute
        except Exception:
            observed.executing = False
            observed.report["execute_restored"] = "UNKNOWN"
            return await unmeasured()
        result = "RETURNED"
        try:
            return await original_create(store, session, *args, **kwargs)
        except BaseException as exc:
            result = outcome(exc)
            raise
        finally:
            # 旧scope wrapper在original_create内部先恢复到本包装，再由本层还原。
            try:
                if vars(session).get("execute") is execute:
                    if had_local:
                        session.execute = previous
                    else:
                        del session.execute
                    observed.report["execute_restored"] = True
                else:
                    observed.report["execute_restored"] = False
            except BaseException:
                observed.report["execute_restored"] = False
            observed.executing = False
            observed.finish(span, result)
            observed.mark("store_exit_ms")

    installed_native = classmethod(native)
    try:
        LoginService._resolve_current_user = installed_native
        AccountScopeStore.create = create
    except BaseException:
        # 安装尚未返回句柄时也只恢复自己已替换的值；不覆盖第三方包装。
        for target, name, installed, previous in (
            (AccountScopeStore, "create", create, original_create),
            (LoginService, "_resolve_current_user", installed_native, native_descriptor),
        ):
            try:
                if vars(target).get(name) is installed:
                    setattr(target, name, previous)
            except BaseException:
                pass
        raise

    def uninstall():
        global _installed
        if state.active:
            raise ValueError("SCOPE_HTTP_ACTIVE_REQUEST")
        if (
            vars(LoginService).get("_resolve_current_user") is not installed_native
            or AccountScopeStore.create is not create
            or _installed is not state
        ):
            raise ValueError("SCOPE_HTTP_INSTALLATION_CHANGED")
        LoginService._resolve_current_user = native_descriptor
        AccountScopeStore.create = original_create
        state.closed = True
        _installed = None

    state.remove = uninstall
    _installed = state
    return uninstall


def wrap_scope_http_diagnostics(app, output_dir, *, isolated_test=False):
    path = guard_output(output_dir, isolated_test=isolated_test)
    state = _installed
    if state is None or state.path != path or state.closed:
        raise ValueError("SCOPE_HTTP_INSTALL_FIRST")

    async def wrapped(scope, receive, send):
        if (
            state.closed
            or scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/api/v1/scope-snapshots"
        ):
            return await app(scope, receive, send)
        if state.written >= MAX_REQUESTS:
            state.dropped += 1
            return await app(scope, receive, send)
        state.written += 1
        observed = Observation(state, path / (uuid4().hex + ".json"))
        token = _TRACE.set(observed)
        state.active += 1
        observed.save()

        async def measured_send(message):
            if message.get("type") == "http.response.start":
                observed.mark("response_start_enter_ms")
                try:
                    return await send(message)
                finally:
                    observed.mark("response_start_exit_ms")
            if message.get("type") == "http.response.body" and not message.get("more_body", False):
                observed.mark("last_body_enter_ms")
                try:
                    return await send(message)
                finally:
                    observed.mark("last_body_exit_ms")
            return await send(message)

        try:
            value = await app(scope, receive, measured_send)
            observed.report["status"] = "APP_RETURNED"
            return value
        except BaseException as exc:
            observed.report["status"] = outcome(exc)
            raise
        finally:
            observed.mark("app_end_ms")
            observed.closed = True
            state.active -= 1
            _TRACE.reset(token)

    return wrapped


def _save_context_summary(path, report):
    """固定技术清理回执，不保存异常文本；写入失败不影响原异常身份。"""
    temporary = None
    try:
        guard_output(path, isolated_test=True)
        target = path / "context-cleanup.json"
        try:
            mode = target.lstat()
        except FileNotFoundError:
            mode = None
        if mode is not None and (
            stat.S_ISLNK(mode.st_mode) or getattr(mode, "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("SCOPE_HTTP_LINK_REJECTED")
        temporary = path / ("context-cleanup." + uuid4().hex + ".tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=True, allow_nan=False)
        os.replace(temporary, target)
    except BaseException:
        report["diagnostic_write_failures"] += 1
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except BaseException:
                pass


@contextmanager
def scope_http_diagnostics_context(app, old_output_dir, output_dir, *, isolated_test=False):
    """从安装到运行共用同一清理边界；原异常优先，所有已装层都尝试逆序恢复。"""
    path = guard_output(output_dir, isolated_test=isolated_test)
    if _installed is not None:
        raise ValueError("SCOPE_HTTP_ALREADY_INSTALLED")
    report = {
        "schema": 1,
        "kind": "SCOPE_HTTP_CONTEXT_CLEANUP",
        "setup_stage": "START",
        "original_exception": None,
        "cleanup_attempts": [],
        "cleanup_failed": [],
        "diagnostic_write_failures": 0,
    }
    removers = []
    original_failed = False
    try:
        stop_old = install_scope_create_diagnostics(old_output_dir)
        removers.append(("OLD_SCOPE_REMOVE", stop_old))
        report["setup_stage"] = "OLD_SCOPE_INSTALLED"
        try:
            stop_http = install_scope_http_diagnostics(path, isolated_test=True)
        except BaseException:
            # 兼容调用边界在安装已完成后抛错；仅回收本次新出现且同路径的私有安装。
            candidate = _installed
            if candidate is not None and candidate.path == path:
                removers.append(("HTTP_REMOVE", candidate.remove))
            raise
        removers.append(("HTTP_REMOVE", stop_http))
        report["setup_stage"] = "HTTP_INSTALLED"
        wrapped = wrap_scope_http_diagnostics(app, path, isolated_test=True)
        report["setup_stage"] = "WRAPPED"
        yield wrapped
        report["setup_stage"] = "APP_RETURNED"
    except BaseException as exc:
        original_failed = True
        report["original_exception"] = outcome(exc)
        raise
    finally:
        for label, remove in reversed(removers):
            report["cleanup_attempts"].append(label)
            try:
                remove()
            except BaseException:
                report["cleanup_failed"].append(label)
        try:
            _save_context_summary(path, report)
        except BaseException:
            report["diagnostic_write_failures"] += 1
        if report["cleanup_failed"] and not original_failed:
            # 无原异常时明确拒绝把未恢复的诊断层标成成功；底层异常内容不泄出。
            raise RuntimeError("SCOPE_HTTP_CLEANUP_FAILED") from None
