"""范围同请求诊断纯协议；无数据库/HTTP服务，不作为容量或CPU证明。"""

import asyncio
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

m = importlib.import_module("tools.account_scope_http_diagnostics")
old = importlib.import_module("tools.account_scope_capacity_diagnostics")


class Session:
    async def execute(self, statement, *args, **kwargs):
        return sentinel


sentinel = object()


class Native:
    @classmethod
    async def _resolve_current_user(cls, *args, **kwargs):
        return sentinel


class Store:
    async def create(self, session, *args, **kwargs):
        assert (
            await session.execute("SELECT x FROM orbit_ad_account WHERE x=:secret", sentinel)
            is sentinel
        )
        assert (
            await session.execute(
                "INSERT INTO orbit_account_scope_member (x) VALUES (:secret)", sentinel
            )
            is sentinel
        )
        return sentinel


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "BASE", tmp_path / ".runtime" / "account-scope-http-profile")
    monkeypatch.setattr(m, "_targets", lambda: (Native, Store))
    return m.BASE / ("a" * 32)


@pytest.mark.parametrize("flag", [False, 1, "True", None])
def test_explicit_boolean_true_only(environment, flag):
    with pytest.raises(ValueError):
        m.install_scope_http_diagnostics(environment, isolated_test=flag)


@pytest.mark.parametrize("name", ["a" * 31, "A" * 32, "a" * 33, "..", "a" * 32 + "/nested"])
def test_exact_safe_child_path(environment, name):
    with pytest.raises(ValueError):
        m.install_scope_http_diagnostics(m.BASE / name, isolated_test=True)


def test_foreign_path_rejected_before_import(environment, monkeypatch):
    monkeypatch.setattr(m, "_targets", lambda: pytest.fail("must not import production targets"))
    with pytest.raises(ValueError):
        m.install_scope_http_diagnostics(environment.parent.parent / ("b" * 32), isolated_test=True)


def test_reparse_point_rejected_before_install(environment, monkeypatch):
    environment.mkdir(parents=True)
    previous = Path.lstat

    def lstat(path, *args, **kwargs):
        value = previous(path, *args, **kwargs)
        if path == environment:
            return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400)
        return value

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(ValueError, match="LINK_REJECTED"):
        m.install_scope_http_diagnostics(environment, isolated_test=True)


def reports(path):
    return [json.loads(file.read_text(encoding="utf-8")) for file in path.glob("*.json")]


async def run_app(app, scope=None):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"private-request-body", "more_body": False}

    async def send(message):
        messages.append(message)

    value = await app(
        scope or {"type": "http", "method": "POST", "path": "/api/v1/scope-snapshots"},
        receive,
        send,
    )
    return value, messages


@pytest.mark.parametrize("own_execute", [False, True])
def test_original_result_native_descriptor_sql_args_and_asgi_messages(environment, own_execute):
    original_native = vars(Native)["_resolve_current_user"]
    original_create = Store.create
    session = Session()
    if own_execute:
        session.execute = session.execute
    previous = vars(session).get("execute")
    response_start = {
        "type": "http.response.start",
        "status": 201,
        "headers": [(b"x-private", b"private-header")],
    }
    chunk = {"type": "http.response.body", "body": b"private-body", "more_body": True}
    tail = {"type": "http.response.body", "body": b"last-private-body", "more_body": False}

    async def app(scope, receive, send):
        assert await Native._resolve_current_user(sentinel, token=sentinel) is sentinel
        assert await Store().create(session, sentinel, private=sentinel) is sentinel
        assert (await receive())["body"] == b"private-request-body"
        await send(response_start)
        await send(chunk)
        await send(tail)
        return sentinel

    uninstall = m.install_scope_http_diagnostics(environment, isolated_test=True)
    try:
        wrapped = m.wrap_scope_http_diagnostics(app, environment, isolated_test=True)
        result, messages = asyncio.run(run_app(wrapped))
        assert result is sentinel and messages == [response_start, chunk, tail]
        assert all(a is b for a, b in zip(messages, [response_start, chunk, tail], strict=True))
    finally:
        uninstall()
    assert (
        vars(Native)["_resolve_current_user"] is original_native and Store.create is original_create
    )
    assert vars(session).get("execute") is previous
    assert ("execute" in vars(session)) is own_execute
    (report,) = reports(environment)
    assert report["status"] == "APP_RETURNED" and report["execute_restored"] is True
    assert report["native_calls"] == report["store_calls"] == 1
    assert report["sql_calls"] == 2 and report["member_batches_completed"] == 1
    assert report["inflight_sql"] is None
    timing = report["timing"]
    assert timing["native_enter_ms"] <= timing["native_exit_ms"] <= timing["store_enter_ms"]
    assert (
        timing["store_exit_ms"]
        <= timing["response_start_enter_ms"]
        <= timing["last_body_exit_ms"]
        <= timing["app_end_ms"]
    )
    raw = json.dumps(report)
    for secret in ("private", "SELECT", ":secret", "x-private", "WHERE", "INSERT INTO"):
        assert secret not in raw
    assert m._TRACE.get() is None


@pytest.mark.parametrize(
    "scope",
    [
        {"type": "lifespan"},
        {"type": "http", "method": "GET", "path": "/api/v1/scope-snapshots"},
        {"type": "http", "method": "POST", "path": "/api/v1/scope-snapshots/x"},
        {"type": "http", "method": "POST", "path": "/api/v1/other"},
    ],
)
def test_nontarget_and_no_request_context_unchanged(environment, scope):
    session = Session()

    async def app(actual, receive, send):
        assert actual is scope
        assert await Native._resolve_current_user() is sentinel
        assert await Store().create(session) is sentinel
        return sentinel

    uninstall = m.install_scope_http_diagnostics(environment, isolated_test=True)
    try:
        assert asyncio.run(Store().create(session)) is sentinel
        assert asyncio.run(Native._resolve_current_user()) is sentinel
        wrapped = m.wrap_scope_http_diagnostics(app, environment, isolated_test=True)
        assert asyncio.run(run_app(wrapped, scope))[0] is sentinel
        assert reports(environment) == [] and "execute" not in vars(session)
    finally:
        uninstall()


@pytest.mark.parametrize(
    "error", [RuntimeError("private-error"), asyncio.CancelledError(), TimeoutError()]
)
def test_original_errors_cancel_and_exact_execute_restore(environment, monkeypatch, error):
    session = Session()

    async def create(store, actual, *args, **kwargs):
        await actual.execute("INSERT INTO orbit_account_scope_member (x) VALUES (:secret)")
        raise error

    monkeypatch.setattr(Store, "create", create)

    async def app(scope, receive, send):
        await Store().create(session)

    uninstall = m.install_scope_http_diagnostics(environment, isolated_test=True)
    try:
        with pytest.raises(type(error)) as caught:
            asyncio.run(
                run_app(m.wrap_scope_http_diagnostics(app, environment, isolated_test=True))
            )
        assert caught.value is error
        assert "execute" not in vars(session) and m._TRACE.get() is None
        (report,) = reports(environment)
        assert report["status"] == (
            "CANCELLED" if isinstance(error, asyncio.CancelledError) else "ERROR"
        )
        assert report["execute_restored"] is True and report["inflight_sql"] is None
        assert "private-error" not in json.dumps(report)
    finally:
        uninstall()


def test_inflight_fixed_phase_and_batch_persist_before_await(environment, monkeypatch):
    async def execute(session, statement, *args, **kwargs):
        (report,) = reports(environment)
        entry = report["inflight_sql"]
        assert entry["phase"] == "SCOPE_MEMBER_WRITE" and entry["member_batch"] == 1
        assert entry["exit_ms"] is None and report["member_batches_completed"] == 0
        return sentinel

    async def create(store, session):
        return await session.execute("INSERT INTO orbit_account_scope_member (x) VALUES (:secret)")

    monkeypatch.setattr(Session, "execute", execute)
    monkeypatch.setattr(Store, "create", create)

    async def app(scope, receive, send):
        return await Store().create(Session())

    uninstall = m.install_scope_http_diagnostics(environment, isolated_test=True)
    try:
        assert (
            asyncio.run(
                run_app(m.wrap_scope_http_diagnostics(app, environment, isolated_test=True))
            )[0]
            is sentinel
        )
    finally:
        uninstall()


def test_quota_span_bounds_and_unknown_phase_fail_safe(environment, monkeypatch):
    monkeypatch.setattr(m, "MAX_REQUESTS", 1)
    monkeypatch.setattr(m, "MAX_SPANS", 1)
    monkeypatch.setattr(m, "sql_phase", lambda statement: "PRIVATE_SQL_MUST_NOT_LEAK")

    async def app(scope, receive, send):
        return await Store().create(Session())

    uninstall = m.install_scope_http_diagnostics(environment, isolated_test=True)
    try:
        wrapped = m.wrap_scope_http_diagnostics(app, environment, isolated_test=True)
        for _ in range(2):
            assert asyncio.run(run_app(wrapped))[0] is sentinel
        (report,) = reports(environment)
        assert report["dropped_spans"] > 0 and len(report["spans"]) == 1
        assert "PRIVATE_SQL" not in json.dumps(report)
        assert m._installed.dropped == 1
    finally:
        uninstall()


def test_diagnostic_io_failure_never_overwrites_business_error(environment, monkeypatch):
    error = RuntimeError("original-only")

    async def app(scope, receive, send):
        raise error

    uninstall = m.install_scope_http_diagnostics(environment, isolated_test=True)
    monkeypatch.setattr(
        m.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("private-path"))
    )
    try:
        with pytest.raises(RuntimeError) as caught:
            asyncio.run(
                run_app(m.wrap_scope_http_diagnostics(app, environment, isolated_test=True))
            )
        assert caught.value is error and not list(environment.glob("*.tmp"))
        assert m._TRACE.get() is None
    finally:
        uninstall()


def test_duplicate_install_and_active_uninstall_rejected(environment):
    uninstall = m.install_scope_http_diagnostics(environment, isolated_test=True)
    try:
        with pytest.raises(ValueError):
            m.install_scope_http_diagnostics(environment, isolated_test=True)

        async def app(scope, receive, send):
            with pytest.raises(ValueError, match="ACTIVE_REQUEST"):
                uninstall()

        asyncio.run(run_app(m.wrap_scope_http_diagnostics(app, environment, isolated_test=True)))
    finally:
        uninstall()


def test_unsupported_session_introspection_keeps_original_business(environment, monkeypatch):
    class SlottedSession:
        __slots__ = ()

        async def execute(self, *args, **kwargs):
            return sentinel

    async def app(scope, receive, send):
        return await Store().create(SlottedSession())

    uninstall = m.install_scope_http_diagnostics(environment, isolated_test=True)
    try:
        assert (
            asyncio.run(
                run_app(m.wrap_scope_http_diagnostics(app, environment, isolated_test=True))
            )[0]
            is sentinel
        )
        (report,) = reports(environment)
        assert report["execute_restored"] == "UNKNOWN" and report["sql_calls"] == 0
        assert report["timing"]["store_exit_ms"] >= report["timing"]["store_enter_ms"]
    finally:
        uninstall()


@pytest.mark.parametrize("phase", ["native", "sql"])
def test_inner_failure_keeps_exact_exception_and_fixed_outcome(environment, monkeypatch, phase):
    error = RuntimeError("private-inner-error")

    async def fail(*args, **kwargs):
        raise error

    if phase == "native":
        monkeypatch.setattr(Native, "_resolve_current_user", classmethod(fail))
    else:
        monkeypatch.setattr(Session, "execute", fail)

    async def app(scope, receive, send):
        await Native._resolve_current_user()
        return await Store().create(Session())

    uninstall = m.install_scope_http_diagnostics(environment, isolated_test=True)
    try:
        with pytest.raises(RuntimeError) as caught:
            asyncio.run(
                run_app(m.wrap_scope_http_diagnostics(app, environment, isolated_test=True))
            )
        assert caught.value is error
        (report,) = reports(environment)
        assert any(row["outcome"] == "ERROR" for row in report["spans"])
        assert report["inflight_sql"] is None and "private-inner-error" not in json.dumps(report)
    finally:
        uninstall()


def test_existing_context_restored_and_wrap_path_must_match_install(environment):
    marker = object()
    token = m._TRACE.set(marker)

    async def app(scope, receive, send):
        assert isinstance(m._TRACE.get(), m.Observation)

    uninstall = m.install_scope_http_diagnostics(environment, isolated_test=True)
    try:
        with pytest.raises(ValueError, match="INSTALL_FIRST"):
            m.wrap_scope_http_diagnostics(app, m.BASE / ("c" * 32), isolated_test=True)
        asyncio.run(run_app(m.wrap_scope_http_diagnostics(app, environment, isolated_test=True)))
        assert m._TRACE.get() is marker
    finally:
        uninstall()
        m._TRACE.reset(token)


def test_concurrent_context_isolation_and_no_late_postapp_changes(environment):
    async def run():
        ready = asyncio.Event()
        entered = 0
        late = []

        async def app(scope, receive, send):
            nonlocal entered
            entered += 1
            if entered == 2:
                ready.set()
            await ready.wait()
            await Native._resolve_current_user()
            await Store().create(Session())
            observed = m._TRACE.get()

            async def after():
                await asyncio.sleep(0)
                observed.mark("must_not_appear")

            late.append(asyncio.create_task(after()))

        wrapped = m.wrap_scope_http_diagnostics(app, environment, isolated_test=True)
        await asyncio.gather(run_app(wrapped), run_app(wrapped))
        await asyncio.gather(*late)

    uninstall = m.install_scope_http_diagnostics(environment, isolated_test=True)
    try:
        asyncio.run(run())
        actual = reports(environment)
        assert len(actual) == 2 and len({report["trace"] for report in actual}) == 2
        assert all(report["native_calls"] == 1 and report["sql_calls"] == 2 for report in actual)
        assert all("must_not_appear" not in report["timing"] for report in actual)
    finally:
        uninstall()


@pytest.mark.parametrize("failure", [None, "cancel", "error"])
def test_old_scope_then_new_http_reverse_uninstall_combination(
    environment, monkeypatch, tmp_path, failure
):
    from orbit_api.account_scope_store import AccountScopeStore

    old_base = tmp_path / ".runtime" / "account-scope-capacity-profile"
    monkeypatch.setattr(old, "BASE", old_base)
    old_path = old_base / ("b" * 32)
    original = AccountScopeStore.create

    async def create(store, session, *args, **kwargs):
        await session.execute("INSERT INTO orbit_account_scope_member (x) VALUES (:secret)", [])
        if failure == "cancel":
            raise asyncio.CancelledError
        if failure == "error":
            raise RuntimeError("original-composition-error")
        return sentinel

    monkeypatch.setattr(AccountScopeStore, "create", create)
    monkeypatch.setattr(m, "_targets", lambda: (Native, AccountScopeStore))
    remove_old = old.install_scope_create_diagnostics(old_path)
    old_wrapped = AccountScopeStore.create
    remove_new = m.install_scope_http_diagnostics(environment, isolated_test=True)
    session = Session()

    async def app(scope, receive, send):
        assert await AccountScopeStore(None).create(session) is sentinel

    try:
        wrapped = m.wrap_scope_http_diagnostics(app, environment, isolated_test=True)
        if failure:
            with pytest.raises(asyncio.CancelledError if failure == "cancel" else RuntimeError):
                asyncio.run(run_app(wrapped))
        else:
            asyncio.run(run_app(wrapped))
    finally:
        remove_new()
        assert AccountScopeStore.create is old_wrapped
        remove_old()
    assert AccountScopeStore.create is create and original is not create
    assert "execute" not in vars(session)
    assert reports(environment)[0]["execute_restored"] is True
    assert reports(old_path)[0]["execute_restored"] is True


@pytest.mark.parametrize("failure", [None, "old", "http", "wrap"])
def test_context_setup_failures_restore_every_installed_layer(environment, monkeypatch, failure):
    order = []
    error = RuntimeError("private-setup-message")

    def install(label):
        def start(*args, **kwargs):
            order.append("install-" + label)
            if failure == label:
                raise error
            return lambda: order.append("remove-" + label)

        return start

    def wrap(app, *args, **kwargs):
        order.append("wrap")
        if failure == "wrap":
            raise error
        return sentinel

    monkeypatch.setattr(m, "install_scope_create_diagnostics", install("old"))
    monkeypatch.setattr(m, "install_scope_http_diagnostics", install("http"))
    monkeypatch.setattr(m, "wrap_scope_http_diagnostics", wrap)
    if failure:
        with pytest.raises(RuntimeError) as caught:
            with m.scope_http_diagnostics_context(
                object(), environment, environment, isolated_test=True
            ):
                pytest.fail("failed setup must not yield")
        assert caught.value is error
    else:
        with m.scope_http_diagnostics_context(
            object(), environment, environment, isolated_test=True
        ) as app:
            assert app is sentinel
            order.append("run")
    expected = {
        "old": ["install-old"],
        "http": ["install-old", "install-http", "remove-old"],
        "wrap": ["install-old", "install-http", "wrap", "remove-http", "remove-old"],
        None: ["install-old", "install-http", "wrap", "run", "remove-http", "remove-old"],
    }
    assert order == expected[failure]
    report = json.loads((environment / "context-cleanup.json").read_text())
    assert report["cleanup_failed"] == []
    assert report["original_exception"] == ("ERROR" if failure else None)
    assert "private-setup-message" not in json.dumps(report)


@pytest.mark.parametrize("original", [False, True, "cancel"])
@pytest.mark.parametrize("failures", [("http",), ("old",), ("http", "old")])
def test_context_cleanup_all_attempted_original_error_or_cancel_has_priority(
    environment, monkeypatch, original, failures
):
    attempted = []
    error = asyncio.CancelledError() if original == "cancel" else RuntimeError("uvicorn-original")

    def install(label):
        def start(*args, **kwargs):
            def stop():
                attempted.append(label)
                if label in failures:
                    raise RuntimeError("private-cleanup-details")

            return stop

        return start

    monkeypatch.setattr(m, "install_scope_create_diagnostics", install("old"))
    monkeypatch.setattr(m, "install_scope_http_diagnostics", install("http"))
    monkeypatch.setattr(m, "wrap_scope_http_diagnostics", lambda app, *a, **k: app)
    with pytest.raises(type(error) if original else RuntimeError) as caught:
        with m.scope_http_diagnostics_context(
            sentinel, environment, environment, isolated_test=True
        ) as app:
            assert app is sentinel
            if original:
                raise error
    if original:
        assert caught.value is error
    else:
        assert str(caught.value) == "SCOPE_HTTP_CLEANUP_FAILED"
        assert caught.value.__suppress_context__ is True
    assert attempted == ["http", "old"]
    summary = json.loads((environment / "context-cleanup.json").read_text())
    assert len(summary["cleanup_failed"]) == len(failures)
    assert summary["cleanup_attempts"] == ["HTTP_REMOVE", "OLD_SCOPE_REMOVE"]
    assert "private-cleanup-details" not in json.dumps(summary)


def test_context_recovers_install_completed_before_boundary_raises(environment, monkeypatch):
    original_create = Store.create
    original_native = vars(Native)["_resolve_current_user"]
    actual_install = m.install_scope_http_diagnostics
    stopped = []
    error = RuntimeError("after-completed-install")

    def broken_install(*args, **kwargs):
        actual_install(*args, **kwargs)
        raise error

    monkeypatch.setattr(
        m, "install_scope_create_diagnostics", lambda *a: lambda: stopped.append("old")
    )
    monkeypatch.setattr(m, "install_scope_http_diagnostics", broken_install)
    with pytest.raises(RuntimeError) as caught:
        with m.scope_http_diagnostics_context(
            sentinel, environment, environment, isolated_test=True
        ):
            pytest.fail("must not yield")
    assert caught.value is error and stopped == ["old"]
    assert m._installed is None and Store.create is original_create
    assert vars(Native)["_resolve_current_user"] is original_native
    summary = json.loads((environment / "context-cleanup.json").read_text())
    assert summary["cleanup_attempts"] == ["HTTP_REMOVE", "OLD_SCOPE_REMOVE"]


def test_partial_http_descriptor_install_rolls_back_before_old_cleanup(environment, monkeypatch):
    error = RuntimeError("private-descriptor-install-error")
    original_native = vars(Native)["_resolve_current_user"]

    class RejectCreate(type):
        def __setattr__(cls, name, value):
            if name == "create":
                raise error
            return super().__setattr__(name, value)

    class RejectStore(metaclass=RejectCreate):
        async def create(self, *args, **kwargs):
            return sentinel

    attempted = []
    monkeypatch.setattr(m, "_targets", lambda: (Native, RejectStore))
    monkeypatch.setattr(
        m, "install_scope_create_diagnostics", lambda *a: lambda: attempted.append("old")
    )
    with pytest.raises(RuntimeError) as caught:
        with m.scope_http_diagnostics_context(
            sentinel, environment, environment, isolated_test=True
        ):
            pytest.fail("must not yield after partial install")
    assert caught.value is error and attempted == ["old"] and m._installed is None
    assert vars(Native)["_resolve_current_user"] is original_native


def test_context_summary_write_failure_cannot_mask_original(environment, monkeypatch):
    attempted = []
    monkeypatch.setattr(
        m, "install_scope_create_diagnostics", lambda *a: lambda: attempted.append("old")
    )
    monkeypatch.setattr(
        m, "install_scope_http_diagnostics", lambda *a, **k: lambda: attempted.append("http")
    )
    monkeypatch.setattr(m, "wrap_scope_http_diagnostics", lambda app, *a, **k: app)
    monkeypatch.setattr(
        m, "_save_context_summary", lambda *a: (_ for _ in ()).throw(OSError("private"))
    )
    error = RuntimeError("original")
    with pytest.raises(RuntimeError) as caught:
        with m.scope_http_diagnostics_context(
            sentinel, environment, environment, isolated_test=True
        ):
            raise error
    assert caught.value is error and attempted == ["http", "old"]


def test_context_uses_actual_old_and_new_wrappers_and_restores(environment, monkeypatch, tmp_path):
    from orbit_api.account_scope_store import AccountScopeStore

    old_base = tmp_path / ".runtime" / "account-scope-capacity-profile"
    monkeypatch.setattr(old, "BASE", old_base)
    monkeypatch.setattr(m, "_targets", lambda: (Native, AccountScopeStore))
    original_native = vars(Native)["_resolve_current_user"]

    async def create(store, session, *args, **kwargs):
        return await session.execute("SELECT x FROM orbit_ad_account WHERE x=:secret")

    monkeypatch.setattr(AccountScopeStore, "create", create)
    session = Session()

    async def app(scope, receive, send):
        await Native._resolve_current_user()
        return await AccountScopeStore(None).create(session)

    with m.scope_http_diagnostics_context(
        app, old_base / ("b" * 32), environment, isolated_test=True
    ) as wrapped:
        assert asyncio.run(run_app(wrapped))[0] is sentinel
    assert (
        AccountScopeStore.create is create
        and vars(Native)["_resolve_current_user"] is original_native
    )
    assert "execute" not in vars(session) and m._installed is None
    summary = json.loads((environment / "context-cleanup.json").read_text())
    assert summary["cleanup_failed"] == [] and summary["setup_stage"] == "APP_RETURNED"
