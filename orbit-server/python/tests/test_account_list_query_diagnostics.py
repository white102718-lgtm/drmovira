"""隔离诊断护栏及透明性纯测试；不计HTTP/数据库性能验收。"""

import asyncio
import importlib
import json
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from orbit_api import identity_publication_summary as summary
from orbit_api.account_details_store import AccountDetailsStore

m = importlib.import_module("tools.account_list_query_diagnostics")
SECRET = "DO_NOT_RECORD_REQUEST_PARAMETER_OR_RESPONSE_VALUE"


@pytest.fixture
def destination(tmp_path, monkeypatch):
    base = tmp_path / ".runtime" / "account-list-query-profile"
    monkeypatch.setattr(m, "BASE", base)
    return base / ("a" * 32)


class Session:
    async def execute(self, *args, **kwargs):
        return SimpleNamespace(rowcount=-1)


def reports(destination):
    return [json.loads(path.read_text()) for path in destination.glob("request-*.json")]


@pytest.mark.parametrize("flag", [False, None, 1, "True"])
def test_requires_exact_true_no_class_wrapping(destination, flag):
    original = AccountDetailsStore.list
    with pytest.raises(ValueError, match="ISOLATION_REQUIRED"):
        m.install_account_list_query_diagnostics(destination, isolated_test=flag)
    assert AccountDetailsStore.list is original
    assert not destination.exists()


@pytest.mark.parametrize("name", ["", "a" * 31, "a" * 33, "A" * 32, "..", "a" * 32 + "/nested"])
def test_only_exact_runtime_child(destination, name):
    with pytest.raises(ValueError):
        m.guard_output(m.BASE / name)


@pytest.mark.parametrize("mode,attributes", [(stat.S_IFLNK, 0), (stat.S_IFDIR, 0x400)])
def test_symlink_or_windows_junction_ancestor_rejected(destination, monkeypatch, mode, attributes):
    original = Path.lstat

    def status(path, *args, **kwargs):
        if path == destination.parent:
            return SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", status)
    with pytest.raises(ValueError, match="LINK_REJECTED"):
        m.guard_output(destination)


@pytest.mark.parametrize(
    "statement,label",
    [
        ("SELECT * FROM orbit_ad_account WHERE name=:private", "ACCOUNT_PAGE"),
        ("SELECT * FROM orbit_account_spend_day", "SPEND_AGGREGATE"),
        ("SELECT * FROM orbit_account_identity_evidence", "IDENTITY_EVIDENCE"),
        ("SELECT * FROM orbit_identity_inventory_seal", "IDENTITY_SEAL"),
        ("SELECT * FROM orbit_browser_session", "COOKIE_CURRENT"),
        ("SELECT * FROM orbit_user_scope", "BUSINESS_AUTH"),
        ("SELECT UTC_TIMESTAMP(6)", "SERVER_TIME"),
        ("SELECT :unknown", "OTHER"),
    ],
)
def test_classifier_only_fixed_tags(statement, label):
    assert m.sql_label(statement) == label


@pytest.mark.asyncio
@pytest.mark.parametrize("local", [False, True])
async def test_transparent_return_secret_free_output_and_exact_restore(
    destination, monkeypatch, local
):
    value = {"items": [{"private": SECRET}, {"private": SECRET}]}
    result = SimpleNamespace(rowcount=-1)
    original_result = result
    events = []

    async def implementation(store, session, actor, query, cursor=None, **kwargs):
        answer = await session.execute(
            "SELECT * FROM orbit_ad_account WHERE secret=:secret", {"secret": SECRET}
        )
        assert answer is original_result
        assert summary.matches_current_seal(SECRET, SECRET, SECRET) is True
        return value

    monkeypatch.setattr(AccountDetailsStore, "list", implementation)
    monkeypatch.setattr(
        summary, "matches_current_seal", lambda *args: events.append("seal") or True
    )
    original_match = summary.matches_current_seal
    session = Session()
    if local:
        session.execute = AsyncMock(return_value=result)
    else:
        monkeypatch.setattr(Session, "execute", AsyncMock(return_value=result))
    previous = session.execute
    uninstall = m.install_account_list_query_diagnostics(destination, isolated_test=True)
    try:
        answer = await AccountDetailsStore(None).list(session, 7, {"page_size": 200, "q": SECRET})
        assert answer is value and session.execute == previous
        assert ("execute" in vars(session)) is local
        report = reports(destination)[0]
        assert report["first_page_only"] is True
        assert report["page_size"] == 200 and report["items_count"] == 2
        assert report["execute_calls"] == 1 and report["seal"]["calls"] == 1
        assert report["sql"]["ACCOUNT_PAGE"]["rowcount"] is None
        assert report["non_execute_is_cpu"] is False and report["execute_restored"] is True
        assert report["list_seconds"] >= report["execute_seconds"] >= 0
        assert SECRET not in json.dumps(report)
        assert m._CURRENT.get() is None
        assert uninstall.summary()["recorded"] == 1
    finally:
        uninstall()
    assert (
        AccountDetailsStore.list is implementation
        and summary.matches_current_seal is original_match
    )
    uninstall()


@pytest.mark.asyncio
async def test_exception_and_cancellation_restore_and_do_not_log_exception(
    destination, monkeypatch
):
    ready = asyncio.Event()
    mode = "failure"

    async def implementation(store, session, *args, **kwargs):
        if mode == "failure":
            raise RuntimeError(SECRET)
        ready.set()
        await session.execute("SELECT * FROM orbit_ad_account")

    monkeypatch.setattr(AccountDetailsStore, "list", implementation)
    session = Session()
    previous = session.execute
    uninstall = m.install_account_list_query_diagnostics(destination, isolated_test=True)
    try:
        with pytest.raises(RuntimeError, match=SECRET):
            await AccountDetailsStore(None).list(session, 7, {"page_size": 20})
        assert session.execute == previous and "execute" not in vars(session)
        mode = "cancel"
        gate = asyncio.Event()
        session.execute = AsyncMock(side_effect=lambda *args: None)

        async def blocked(*args, **kwargs):
            await gate.wait()

        session.execute = blocked
        task = asyncio.create_task(AccountDetailsStore(None).list(session, 7, {"page_size": 50}))
        await ready.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert session.execute is blocked
        values = reports(destination)
        assert {r["status"] for r in values} == {"FAILED", "CANCELLED"}
        assert all(SECRET not in json.dumps(r) for r in values)
        assert m._CURRENT.get() is None
    finally:
        uninstall()


@pytest.mark.asyncio
async def test_skip_later_pages_identifiers_and_cap_without_changing_business(
    destination, monkeypatch
):
    calls = []

    async def implementation(store, session, actor, query, cursor=None, **kwargs):
        calls.append(True)
        return {"items": []}

    monkeypatch.setattr(AccountDetailsStore, "list", implementation)
    monkeypatch.setattr(m, "MAX_REPORTS", 2)
    uninstall = m.install_account_list_query_diagnostics(destination, isolated_test=True)
    try:
        store, session = AccountDetailsStore(None), Session()
        await store.list(session, 7, {"page_size": 20}, "opaque-private-cursor")
        await store.list(session, 7, {"page_size": 20}, identifier=SECRET)
        for size in (20, 50, 100):
            await store.list(session, 7, {"page_size": size})
        assert len(calls) == 5 and len(reports(destination)) == 2
        assert uninstall.summary() == {
            "first_page_only": True,
            "recorded": 2,
            "dropped_cursor": 1,
            "dropped_identifier": 1,
            "dropped_limit": 1,
        }
    finally:
        uninstall()


@pytest.mark.asyncio
async def test_reentry_and_duplicate_install_are_rejected(destination, monkeypatch):
    async def implementation(store, session, *args, **kwargs):
        return await store.list(session, *args, **kwargs)

    monkeypatch.setattr(AccountDetailsStore, "list", implementation)
    uninstall = m.install_account_list_query_diagnostics(destination, isolated_test=True)
    try:
        with pytest.raises(ValueError, match="ALREADY_INSTALLED"):
            m.install_account_list_query_diagnostics(destination, isolated_test=True)
        with pytest.raises(ValueError, match="REENTRY_REJECTED"):
            await AccountDetailsStore(None).list(Session(), 7, {"page_size": 20})
        assert m._CURRENT.get() is None
    finally:
        uninstall()


@pytest.mark.asyncio
async def test_parallel_sessions_contexts_do_not_mix_and_unknown_page_size_is_null(
    destination, monkeypatch
):
    async def implementation(store, session, *args, **kwargs):
        await asyncio.sleep(0)
        summary.matches_current_seal(None, None, None)
        await session.execute("SELECT UTC_TIMESTAMP(6)")
        return {"items": []}

    monkeypatch.setattr(AccountDetailsStore, "list", implementation)
    monkeypatch.setattr(summary, "matches_current_seal", lambda *args: True)
    uninstall = m.install_account_list_query_diagnostics(destination, isolated_test=True)
    try:
        await asyncio.gather(
            *[AccountDetailsStore(None).list(Session(), 7, {"page_size": True}) for _ in range(2)]
        )
        values = reports(destination)
        assert len(values) == 2
        assert all(r["seal"]["calls"] == 1 and r["execute_calls"] == 1 for r in values)
        assert all(r["page_size"] is None for r in values)
    finally:
        uninstall()


@pytest.mark.asyncio
async def test_diagnostic_write_failure_does_not_override_result(destination, monkeypatch):
    value = {"items": []}

    async def implementation(*args, **kwargs):
        return value

    monkeypatch.setattr(AccountDetailsStore, "list", implementation)
    monkeypatch.setattr(m, "_write", lambda *args: (_ for _ in ()).throw(OSError(SECRET)))
    uninstall = m.install_account_list_query_diagnostics(destination, isolated_test=True)
    try:
        assert await AccountDetailsStore(None).list(Session(), 7, {"page_size": 20}) is value
        assert uninstall.summary()["recorded"] == 0
    finally:
        uninstall()


@pytest.mark.asyncio
async def test_overlapping_same_session_rejected_without_disturbing_original_request(
    destination, monkeypatch
):
    ready, release = asyncio.Event(), asyncio.Event()

    async def implementation(store, session, *args, **kwargs):
        ready.set()
        await release.wait()
        return {"items": []}

    monkeypatch.setattr(AccountDetailsStore, "list", implementation)
    uninstall = m.install_account_list_query_diagnostics(destination, isolated_test=True)
    session = Session()
    previous = session.execute
    first = asyncio.create_task(AccountDetailsStore(None).list(session, 7, {"page_size": 200}))
    try:
        await ready.wait()
        with pytest.raises(ValueError, match="REENTRY_REJECTED"):
            await AccountDetailsStore(None).list(session, 7, {"page_size": 200})
        release.set()
        assert await first == {"items": []}
        assert session.execute == previous and "execute" not in vars(session)
        assert len(reports(destination)) == 1
    finally:
        release.set()
        await first
        uninstall()


def target_scope(**changes):
    return {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/accounts/extended",
        "query_string": b"page_size=200&q=" + SECRET.encode(),
        **changes,
    }


@pytest.mark.asyncio
async def test_asgi_correlates_one_report_same_trace_and_preserves_messages_receive(
    destination, monkeypatch
):
    value = {"items": [{}] * 200}

    async def implementation(store, session, *args, **kwargs):
        await session.execute("SELECT * FROM orbit_ad_account", {"secret": SECRET})
        return value

    monkeypatch.setattr(AccountDetailsStore, "list", implementation)
    received = AsyncMock(return_value={"type": "http.request", "body": SECRET.encode()})
    messages = [
        {"type": "http.response.start", "status": 200, "headers": [(b"private", SECRET.encode())]},
        {"type": "http.response.body", "body": SECRET.encode(), "more_body": True},
        {"type": "http.response.body", "body": b"end", "more_body": False},
    ]
    sent = []

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        assert receive is received
        assert await AccountDetailsStore(None).list(Session(), 7, {"page_size": 200}) is value
        assert not list(destination.glob("request-*.json"))
        for message in messages:
            await send(message)
        return value

    uninstall = m.install_account_list_query_diagnostics(destination, isolated_test=True)
    wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
    try:
        assert await wrapped(target_scope(), received, send) is value
        received.assert_not_awaited()
        assert all(a is b for a, b in zip(messages, sent, strict=True))
        report = reports(destination)[0]
        assert report["schema"] == 2
        assert report["technical_trace"] == report["list"]["technical_trace"]
        assert len(report["technical_trace"]) == 32
        assert report["list"]["output_deferred_to_asgi"] is True
        assert report["output_deferred_after_app_end"] is True
        assert report["phases_seconds"]["service"] == report["list"]["service_seconds"]
        assert all(value is not None for value in report["events_seconds"].values())
        assert report["body_send_seconds"] <= report["send_seconds"]
        assert report["send_calls"] == 3
        assert SECRET not in json.dumps(report)
        assert m._HTTP.get() is None and m._CURRENT.get() is None
    finally:
        uninstall()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope",
    [
        {"type": "lifespan"},
        target_scope(method="POST"),
        target_scope(path="/other"),
        target_scope(query_string=b"cursor=opaque"),
        target_scope(query_string=b"%63ursor=opaque"),
        target_scope(query_string=b"x" * 16385),
    ],
)
async def test_asgi_non_target_is_exact_passthrough_no_profile(destination, scope):
    receive, send = AsyncMock(), AsyncMock()
    seen = []

    async def app(original_scope, original_receive, original_send):
        seen.append((original_scope, original_receive, original_send))
        return SECRET

    wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
    assert await wrapped(scope, receive, send) == SECRET
    assert seen[0][0] is scope and seen[0][1] is receive and seen[0][2] is send
    receive.assert_not_awaited()
    assert reports(destination) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_asgi_failure_cancel_resets_context_does_not_mask_original(
    destination, monkeypatch, cancel
):
    ready = asyncio.Event()

    async def app(scope, receive, send):
        if cancel:
            ready.set()
            await asyncio.Event().wait()
        raise RuntimeError(SECRET)

    wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
    if cancel:
        task = asyncio.create_task(wrapped(target_scope(), AsyncMock(), AsyncMock()))
        await ready.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(RuntimeError, match=SECRET):
            await wrapped(target_scope(), AsyncMock(), AsyncMock())
    report = reports(destination)[0]
    assert report["status"] == ("CANCELLED" if cancel else "FAILED")
    assert report["list"] is None and report["phases_seconds"]["before_list"] is None
    assert report["phases_seconds"]["service"] is None
    assert report["phases_seconds"]["last_body_send"] is None
    assert SECRET not in json.dumps(report)
    assert m._HTTP.get() is None
    monkeypatch.setattr(m, "_write", lambda *args: (_ for _ in ()).throw(OSError(SECRET)))
    with pytest.raises(RuntimeError, match=SECRET):

        async def failure(*args):
            raise RuntimeError(SECRET)

        await m.wrap_account_query_http(failure, destination, isolated_test=True)(
            target_scope(), AsyncMock(), AsyncMock()
        )


@pytest.mark.asyncio
async def test_asgi_and_standalone_list_share_file_quota(destination, monkeypatch):
    monkeypatch.setattr(m, "MAX_REPORTS", 2)

    async def implementation(*args, **kwargs):
        return {"items": []}

    monkeypatch.setattr(AccountDetailsStore, "list", implementation)

    async def app(scope, receive, send):
        return await AccountDetailsStore(None).list(Session(), 7, {"page_size": 20})

    uninstall = m.install_account_list_query_diagnostics(destination, isolated_test=True)
    wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
    try:
        await AccountDetailsStore(None).list(Session(), 7, {"page_size": 20})
        await wrapped(target_scope(), AsyncMock(), AsyncMock())
        await wrapped(target_scope(), AsyncMock(), AsyncMock())
        assert len(reports(destination)) == 2
        assert wrapped.summary()["dropped_limit"] == 1
        assert uninstall.summary()["dropped_limit"] == 1
    finally:
        uninstall()


def test_asgi_exact_flag_and_duplicate_wrap_rejected(destination):
    async def app(*args):
        pass

    with pytest.raises(ValueError, match="ISOLATION_REQUIRED"):
        m.wrap_account_query_http(app, destination, isolated_test=1)
    wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
    with pytest.raises(ValueError, match="ALREADY_WRAPPED"):
        m.wrap_account_query_http(wrapped, destination, isolated_test=True)


@pytest.mark.asyncio
async def test_asgi_child_task_and_concurrent_requests_keep_same_trace_isolated(
    destination, monkeypatch
):
    async def implementation(store, session, *args, **kwargs):
        await asyncio.sleep(0)
        return {"items": []}

    monkeypatch.setattr(AccountDetailsStore, "list", implementation)

    async def app(scope, receive, send):
        # 模拟Starlette中间件child Task；共享字典须关联到同一次外层ASGI。
        await asyncio.create_task(AccountDetailsStore(None).list(Session(), 7, {"page_size": 20}))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    uninstall = m.install_account_list_query_diagnostics(destination, isolated_test=True)
    wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
    try:
        await asyncio.gather(*[wrapped(target_scope(), AsyncMock(), AsyncMock()) for _ in range(2)])
        values = reports(destination)
        assert len(values) == 2
        assert len({r["technical_trace"] for r in values}) == 2
        assert all(r["technical_trace"] == r["list"]["technical_trace"] for r in values)
        assert m._HTTP.get() is None and m._CURRENT.get() is None
    finally:
        uninstall()


@pytest.fixture
def stage_targets(monkeypatch):
    from contextlib import asynccontextmanager

    calls = []

    class Login:
        @classmethod
        async def _resolve_current_user(cls, *args, **kwargs):
            calls.append("native")
            return args[0] if args else None

    class BaseDialect:
        def reset_isolation_level(self, raw):
            calls.append("reset")
            return raw

    class Dialect(BaseDialect):
        pass

    class ConnectionBase:
        async def __aenter__(self):
            calls.append("checkout")
            return self

    class Connection(ConnectionBase):
        def __init__(self):
            self.dialect = Dialect()

        async def execution_options(self, **kwargs):
            calls.append("options")
            return self

        async def close(self):
            calls.append("close")
            self.dialect.reset_isolation_level(None)

        async def __aexit__(self, *args):
            await asyncio.create_task(self.close())

    class Transaction:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            calls.append("tx-exit")
            return False

    class Response:
        def __init__(self, value, headers=None):
            calls.append("response")
            self.value, self.headers = value, headers

    @asynccontextmanager
    async def rc(*args, **kwargs):
        async with Connection() as connection:
            assert (
                await connection.execution_options(isolation_level="READ COMMITTED") is connection
            )
            yield SimpleNamespace(connection=connection)

    route = SimpleNamespace(read_committed_session=rc)
    targets = {
        "login": Login,
        "connection": Connection,
        "transaction": Transaction,
        "dialect": Dialect,
        "response": Response,
        "route": route,
    }
    monkeypatch.setattr(m, "_stage_targets", lambda: targets)
    originals = {
        (name, key): value
        for name, target in targets.items()
        for key, value in vars(target).items()
    }
    return targets, calls, originals


@pytest.mark.asyncio
async def test_detailed_stage_hooks_keep_identity_and_restore_inherited_descriptors(
    destination, stage_targets
):
    targets, calls, originals = stage_targets
    uninstall = m.install_account_query_stage_diagnostics(destination, isolated_test=True)
    value, headers = object(), [(b"private", SECRET.encode())]

    async def app(scope, receive, send):
        assert await targets["login"]._resolve_current_user(value, token=SECRET) is value
        async with targets["route"].read_committed_session(None) as session:
            async with targets["transaction"](session):
                response = targets["response"](value, headers=headers)
                assert response.value is value and response.headers is headers
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": SECRET.encode()})
        return value

    try:
        wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
        assert await wrapped(target_scope(), AsyncMock(), AsyncMock()) is value
        report = reports(destination)[0]
        labels = report["detailed_stages"]
        assert set(labels) == {
            "native_auth_resolve",
            "rc_context_enter",
            "rc_context_exit",
            "rc_checkout",
            "rc_isolation_options",
            "rc_transaction_exit",
            "rc_connection_exit",
            "rc_connection_close",
            "rc_isolation_reset",
            "json_response_construction",
        }
        assert all(v["calls"] == 1 and v["failed"] == 0 for v in labels.values())
        assert all(v["total_seconds"] >= 0 and len(v["intervals"]) == 1 for v in labels.values())
        assert report["native_resolver_observed"] is True
        assert report["cookie_resolver_timing"] == "UNKNOWN"
        assert SECRET not in json.dumps(report)
        assert m._RC.get() is None and m._CLOSING.get() is None
    finally:
        uninstall()
    assert "__aenter__" not in vars(targets["connection"])
    assert "reset_isolation_level" not in vars(targets["dialect"])
    for (name, key), original in originals.items():
        assert vars(targets[name])[key] is original
    assert calls == ["native", "checkout", "options", "response", "tx-exit", "close", "reset"]
    uninstall()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_detailed_native_exception_or_cancel_keeps_original_and_marks_only_fixed_status(
    destination, stage_targets, monkeypatch, cancel
):
    targets, _calls, _originals = stage_targets
    ready = asyncio.Event()

    async def failing(cls, *args, **kwargs):
        if cancel:
            ready.set()
            await asyncio.Event().wait()
        raise RuntimeError(SECRET)

    monkeypatch.setattr(targets["login"], "_resolve_current_user", classmethod(failing))
    uninstall = m.install_account_query_stage_diagnostics(destination, isolated_test=True)

    async def app(*args):
        return await targets["login"]._resolve_current_user()

    wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
    try:
        if cancel:
            task = asyncio.create_task(wrapped(target_scope(), AsyncMock(), AsyncMock()))
            await ready.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(RuntimeError, match=SECRET):
                await wrapped(target_scope(), AsyncMock(), AsyncMock())
        stage = reports(destination)[0]["detailed_stages"]["native_auth_resolve"]
        assert stage["cancelled"] == int(cancel) and stage["failed"] == int(not cancel)
        assert SECRET not in json.dumps(reports(destination))
        assert m._RC.get() is None
    finally:
        uninstall()


@pytest.mark.asyncio
async def test_detailed_non_target_and_cookie_unobserved_stays_unknown(destination, stage_targets):
    targets, calls, _ = stage_targets
    uninstall = m.install_account_query_stage_diagnostics(destination, isolated_test=True)

    async def app(scope, receive, send):
        targets["response"](SECRET)
        await targets["login"]._resolve_current_user()

    try:
        wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
        await wrapped(target_scope(path="/other"), AsyncMock(), AsyncMock())
        assert reports(destination) == [] and calls == ["response", "native"]

        # 没有经过原native resolver时不能伪造Cookie或完整dependency的时间。
        async def cookie_path(*args):
            return None

        await m.wrap_account_query_http(cookie_path, destination, isolated_test=True)(
            target_scope(), AsyncMock(), AsyncMock()
        )
        value = reports(destination)[0]
        assert value["native_resolver_observed"] is False
        assert value["cookie_resolver_timing"] == "UNKNOWN" and value["detailed_stages"] == {}
    finally:
        uninstall()


def test_detailed_exact_true_duplicate_install_and_changed_hook_failclosed(
    destination, stage_targets
):
    targets, _, _ = stage_targets
    with pytest.raises(ValueError, match="ISOLATION_REQUIRED"):
        m.install_account_query_stage_diagnostics(destination, isolated_test=1)
    uninstall = m.install_account_query_stage_diagnostics(destination, isolated_test=True)
    replacement = targets["response"].__init__
    try:
        with pytest.raises(ValueError, match="ALREADY_INSTALLED"):
            m.install_account_query_stage_diagnostics(destination, isolated_test=True)
        targets["response"].__init__ = lambda *args: None
        with pytest.raises(ValueError, match="WRAPPER_CHANGED"):
            uninstall()
    finally:
        targets["response"].__init__ = replacement
        uninstall()


@pytest.mark.asyncio
async def test_detailed_selector_introspection_failure_does_not_override_original(
    destination, stage_targets
):
    targets, calls, _ = stage_targets
    uninstall = m.install_account_query_stage_diagnostics(destination, isolated_test=True)

    class BadTransaction:
        @property
        def session(self):
            raise RuntimeError(SECRET)

    async def app(scope, receive, send):
        async with targets["route"].read_committed_session(None):
            assert (
                await targets["transaction"].__aexit__(BadTransaction(), None, None, None) is False
            )

    try:
        await m.wrap_account_query_http(app, destination, isolated_test=True)(
            target_scope(), AsyncMock(), AsyncMock()
        )
        stages = reports(destination)[0]["detailed_stages"]
        assert "rc_transaction_exit" not in stages and "tx-exit" in calls
        assert SECRET not in json.dumps(stages)
    finally:
        uninstall()


@pytest.mark.asyncio
async def test_detailed_parallel_rc_sessions_are_isolated(destination, stage_targets):
    targets, _, _ = stage_targets
    uninstall = m.install_account_query_stage_diagnostics(destination, isolated_test=True)

    async def app(scope, receive, send):
        async with targets["route"].read_committed_session(None) as session:
            await asyncio.sleep(0)
            async with targets["transaction"](session):
                targets["response"](None)

    try:
        wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
        await asyncio.gather(*[wrapped(target_scope(), AsyncMock(), AsyncMock()) for _ in range(2)])
        values = reports(destination)
        assert len(values) == 2 and len({v["technical_trace"] for v in values}) == 2
        assert all(v["detailed_stages"]["rc_checkout"]["calls"] == 1 for v in values)
        assert all(v["detailed_stages"]["rc_transaction_exit"]["calls"] == 1 for v in values)
        assert m._RC.get() is None and m._CLOSING.get() is None
    finally:
        uninstall()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_detailed_rc_failure_cancel_closes_original_and_resets_all_contexts(
    destination, stage_targets, cancel
):
    targets, calls, _ = stage_targets
    ready = asyncio.Event()
    uninstall = m.install_account_query_stage_diagnostics(destination, isolated_test=True)

    async def app(scope, receive, send):
        async with targets["route"].read_committed_session(None) as session:
            async with targets["transaction"](session):
                ready.set()
                if cancel:
                    await asyncio.Event().wait()
                raise RuntimeError(SECRET)

    wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
    try:
        if cancel:
            task = asyncio.create_task(wrapped(target_scope(), AsyncMock(), AsyncMock()))
            await ready.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(RuntimeError, match=SECRET):
                await wrapped(target_scope(), AsyncMock(), AsyncMock())
        labels = reports(destination)[0]["detailed_stages"]
        assert labels["rc_context_exit"]["cancelled" if cancel else "failed"] == 1
        assert calls == ["checkout", "options", "tx-exit", "close", "reset"]
        assert m._RC.get() is None and m._CLOSING.get() is None and m._HTTP.get() is None
    finally:
        uninstall()


@pytest.fixture
def pool_targets(monkeypatch):
    class Empty(Exception):
        pass

    class Queue:
        def get(self, block=True, timeout=None):
            if not block:
                raise Empty()
            return object()

    class DialectBase:
        def connect(self, *args, **kwargs):
            return object()

        def _do_ping_w_event(self, raw):
            return True

    class Dialect(DialectBase):
        pass

    class Pool:
        _max_overflow = 10

        def __init__(self):
            self._pool, self._dialect = Queue(), Dialect()

        def size(self):
            return 5

        def checkedout(self):
            return 2

        def overflow(self):
            return -1

        def _do_get(self):
            try:
                self._pool.get(False, 30)
            except Empty:
                pass
            self._pool.get(True, 30)
            return self._dialect.connect(SECRET, password=SECRET)

    class ConnectionBase:
        async def __aenter__(self):
            value = self.engine.sync_engine.pool._do_get()
            self.engine.sync_engine.pool._dialect._do_ping_w_event(value)
            await asyncio.sleep(0)
            return self

    class Connection(ConnectionBase):
        def __init__(self, pool):
            self.engine = SimpleNamespace(sync_engine=SimpleNamespace(pool=pool))

    targets = {
        "connection": Connection,
        "pool": Pool,
        "queue": Queue,
        "dialect": Dialect,
        "empty": Empty,
    }
    monkeypatch.setattr(m, "_pool_targets", lambda: targets)
    return targets


@pytest.mark.asyncio
async def test_pool_exact_nested_labels_normal_empty_counts_and_inherited_restore(
    destination, pool_targets
):
    t = pool_targets
    originals = {k: dict(vars(v)) for k, v in t.items()}
    uninstall = m.install_account_query_pool_diagnostics(destination, isolated_test=True)
    connection = t["connection"](t["pool"]())

    async def app(*args):
        token = m._RC.set({"connection": connection})
        try:
            assert await connection.__aenter__() is connection
        finally:
            m._RC.reset(token)

    try:
        await m.wrap_account_query_http(app, destination, isolated_test=True)(
            target_scope(), AsyncMock(), AsyncMock()
        )
        report = reports(destination)[0]
        labels = report["detailed_stages"]
        assert set(labels) == {
            "rc_pool_do_get",
            "rc_pool_queue_get_blocking",
            "rc_pool_queue_get_nonblocking",
            "rc_pool_physical_connect",
            "rc_pool_pre_ping",
        }
        assert all(v["calls"] == 1 and v["failed"] == 0 for v in labels.values())
        assert labels["rc_pool_queue_get_nonblocking"]["empty"] == 1
        assert report["pool_checkout_samples"] == [
            {
                "before": {"size": 5, "checkedout": 2, "overflow": -1, "max_overflow": 10},
                "after": {"size": 5, "checkedout": 2, "overflow": -1, "max_overflow": 10},
                "outcome": "RETURNED",
            }
        ]
        assert report["pool_checkout_observation"] == "OBSERVED"
        assert SECRET not in json.dumps(report)
        assert m._POOL.get() is None
    finally:
        uninstall()
    for k, owner in t.items():
        assert dict(vars(owner)) == originals[k]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["outside", "unsupported", "other_pool"])
async def test_pool_non_target_unsupported_and_other_pool_do_not_leak_measurement(
    destination, pool_targets, mode
):
    t = pool_targets
    connection = t["connection"](t["pool"]())
    other = t["pool"]()
    uninstall = m.install_account_query_pool_diagnostics(destination, isolated_test=True)

    async def app(*args):
        if mode == "outside":
            assert await connection.__aenter__() is connection
        elif mode == "unsupported":

            class Unsupported:
                async def __aenter__(self):
                    return self

            bad = Unsupported()
            token = m._RC.set({"connection": bad})
            try:
                assert await t["connection"].__aenter__(bad) is bad
            finally:
                m._RC.reset(token)
        else:
            token = m._POOL.set(
                {
                    "pool": connection.engine.sync_engine.pool,
                    "queue": connection.engine.sync_engine.pool._pool,
                    "dialect": connection.engine.sync_engine.pool._dialect,
                }
            )
            try:
                other._do_get()
            finally:
                m._POOL.reset(token)

    # unsupported自省失败必须保留原方法行为；原实现访问engine抛原AttributeError。
    try:
        wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
        if mode == "unsupported":
            with pytest.raises(AttributeError):
                await wrapped(target_scope(), AsyncMock(), AsyncMock())
        else:
            await wrapped(target_scope(), AsyncMock(), AsyncMock())
        value = reports(destination)[0]
        assert value["detailed_stages"] == {} and value["pool_checkout_observation"] == "UNKNOWN"
    finally:
        uninstall()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_pool_error_cancel_original_exception_and_context_reset(
    destination, pool_targets, monkeypatch, cancel
):
    t = pool_targets
    failure = asyncio.CancelledError() if cancel else RuntimeError(SECRET)

    def failed(self, *args, **kwargs):
        raise failure

    monkeypatch.setattr(t["dialect"], "connect", failed)
    connection = t["connection"](t["pool"]())
    uninstall = m.install_account_query_pool_diagnostics(destination, isolated_test=True)

    async def app(*args):
        token = m._RC.set({"connection": connection})
        try:
            await connection.__aenter__()
        finally:
            m._RC.reset(token)

    try:
        with pytest.raises(type(failure)) as caught:
            await m.wrap_account_query_http(app, destination, isolated_test=True)(
                target_scope(), AsyncMock(), AsyncMock()
            )
        assert caught.value is failure
        value = reports(destination)[0]
        assert value["pool_checkout_samples"][0]["outcome"] == ("CANCELLED" if cancel else "FAILED")
        label = value["detailed_stages"]["rc_pool_physical_connect"]
        assert label["cancelled" if cancel else "failed"] == 1
        assert m._POOL.get() is None and m._RC.get() is None and m._HTTP.get() is None
        assert SECRET not in json.dumps(value)
    finally:
        uninstall()


def test_pool_guard_duplicate_install_and_exact_uninstall(destination, pool_targets):
    t = pool_targets
    with pytest.raises(ValueError, match="ISOLATION_REQUIRED"):
        m.install_account_query_pool_diagnostics(destination, isolated_test=1)
    uninstall = m.install_account_query_pool_diagnostics(destination, isolated_test=True)
    try:
        with pytest.raises(ValueError, match="ALREADY_INSTALLED"):
            m.install_account_query_pool_diagnostics(destination, isolated_test=True)
        replacement = t["pool"]._do_get
        t["pool"]._do_get = lambda *args: None
        with pytest.raises(ValueError, match="WRAPPER_CHANGED"):
            uninstall()
        t["pool"]._do_get = replacement
    finally:
        uninstall()
    uninstall()


@pytest.mark.asyncio
async def test_pool_concurrent_contexts_each_keep_own_trace(destination, pool_targets):
    t = pool_targets
    uninstall = m.install_account_query_pool_diagnostics(destination, isolated_test=True)

    async def app(*args):
        connection = t["connection"](t["pool"]())
        token = m._RC.set({"connection": connection})
        try:
            await connection.__aenter__()
        finally:
            m._RC.reset(token)

    try:
        wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
        await asyncio.gather(*[wrapped(target_scope(), AsyncMock(), AsyncMock()) for _ in range(2)])
        values = reports(destination)
        assert len(values) == 2
        assert len({v["technical_trace"] for v in values}) == 2
        assert all(len(v["pool_checkout_samples"]) == 1 for v in values)
        assert all(v["detailed_stages"]["rc_pool_do_get"]["calls"] == 1 for v in values)
        assert m._POOL.get() is None
    finally:
        uninstall()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_pool_real_async_queue_greenlet_wait_and_cancel(
    destination, pool_targets, monkeypatch, cancel
):
    from sqlalchemy.util.concurrency import greenlet_spawn
    from sqlalchemy.util.queue import AsyncAdaptedQueue, Empty

    t = pool_targets
    t["queue"], t["empty"] = AsyncAdaptedQueue, Empty
    pool = t["pool"]()
    pool._pool = AsyncAdaptedQueue()
    connection = t["connection"](pool)
    entered = asyncio.Event()

    def checkout_sync():
        entered.set()
        return pool._do_get()

    async def enter(self):
        await greenlet_spawn(checkout_sync)
        return self

    # 原do_get只捕获本夹具Empty，改为捕获真实queue.Empty，不改变诊断实现。
    def do_get(self):
        try:
            return self._pool.get(False)
        except Empty:
            return self._pool.get(True)

    monkeypatch.setattr(t["connection"], "__aenter__", enter)
    monkeypatch.setattr(t["pool"], "_do_get", do_get)
    uninstall = m.install_account_query_pool_diagnostics(destination, isolated_test=True)

    async def app(*args):
        token = m._RC.set({"connection": connection})
        try:
            assert await connection.__aenter__() is connection
        finally:
            m._RC.reset(token)

    try:
        pending = asyncio.create_task(
            m.wrap_account_query_http(app, destination, isolated_test=True)(
                target_scope(), AsyncMock(), AsyncMock()
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        if cancel:
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            pool._pool.put_nowait(object())
            await pending
        label = reports(destination)[0]["detailed_stages"]["rc_pool_queue_get_blocking"]
        assert label["calls"] == 1 and label["cancelled"] == int(cancel)
        assert m._POOL.get() is None and m._RC.get() is None
    finally:
        uninstall()


@pytest.fixture
def native_lease_targets(monkeypatch):
    class Events:
        def __init__(self):
            self.listeners = []

        def listen(self, owner, name, callback):
            self.listeners.append((owner, name, callback))

        def remove(self, owner, name, callback):
            for index, (target, label, function) in enumerate(self.listeners):
                if target is owner and label == name and function is callback:
                    self.listeners.pop(index)
                    return
            raise ValueError("LISTENER_NOT_REGISTERED")

        def emit(self, owner, name, *args):
            for target, label, callback in tuple(self.listeners):
                if target is owner and label == name:
                    callback(*args)

    event = Events()

    class Engine:
        def __init__(self, pool):
            self.sync_engine = SimpleNamespace(pool=pool)

    class Session:
        def __init__(self, engine, preexisting=False):
            self.bind = engine
            self.entry = object()
            self.connection = SimpleNamespace(
                engine=engine.sync_engine,
                _dbapi_connection=SimpleNamespace(_connection_record=self.entry),
            )
            self.sync_session = SimpleNamespace(
                get_transaction=lambda: (
                    SimpleNamespace(_connections={1: (self.connection,)}) if preexisting else None
                )
            )

        def in_transaction(self):
            return True

    class ConnectionBase:
        async def __aenter__(self):
            self.entry = object()
            event.emit(self.engine.sync_engine.pool, "checkout", None, self.entry, None)
            self.sync_connection = SimpleNamespace(
                _dbapi_connection=SimpleNamespace(_connection_record=self.entry)
            )
            await asyncio.sleep(0)
            return self

    class Connection(ConnectionBase):
        def __init__(self, engine):
            self.engine = engine

    class Login:
        @classmethod
        async def _resolve_current_user(cls, request, token, query_db, **kwargs):
            event.emit(query_db.bind.sync_engine.pool, "checkout", None, query_db.entry, None)
            event.emit(
                query_db.sync_session,
                "after_begin",
                query_db.sync_session,
                None,
                query_db.connection,
            )
            await asyncio.sleep(0)
            return query_db

    targets = {
        "login": Login,
        "connection": Connection,
        "engine": Engine,
        "session": Session,
        "event": event,
    }
    monkeypatch.setattr(m, "_native_lease_targets", lambda: targets)
    return targets


@pytest.mark.asyncio
async def test_native_lease_checkout_before_begin_rc_overlap_and_child_checkin(
    destination, native_lease_targets
):
    t = native_lease_targets
    engine = t["engine"](object())
    session = t["session"](engine)
    uninstall = m.install_account_query_native_lease_diagnostics(destination, isolated_test=True)

    async def app(*args):
        assert await t["login"]._resolve_current_user(None, SECRET, session) is session
        connection = t["connection"](engine)
        token = m._RC.set({"connection": None})
        try:
            assert await connection.__aenter__() is connection
        finally:
            m._RC.reset(token)

        async def release():
            t["event"].emit(engine.sync_engine.pool, "checkin", None, session.entry)

        await asyncio.create_task(release())

    try:
        await m.wrap_account_query_http(app, destination, isolated_test=True)(
            target_scope(), AsyncMock(), AsyncMock()
        )
        value = reports(destination)[0]["native_lease"]
        assert value["observation"] == "OBSERVED" and value["cleanup"] == "REMOVED"
        lease = value["native_leases"][0]
        assert lease["checkout_seconds"] <= lease["after_begin_seconds"] < lease["release_seconds"]
        assert lease["active_at_resolver_exit"] is True
        assert value["resolver_exit_transaction_active"] is True
        rc = value["rc_checkouts"][0]
        assert rc["same_pool"] is True and rc["same_active_native_record"] is False
        assert rc["active_native_leases_at_enter"] == rc["active_native_leases_at_exit"] == 1
        assert rc["enter_seconds"] < rc["exit_seconds"] < lease["release_seconds"]
        assert t["event"].listeners == []
        assert SECRET not in json.dumps(reports(destination))
    finally:
        uninstall()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["preexisting", "unowned_checkout", "unsupported_session", "different_pool"]
)
async def test_native_lease_unknown_not_false_proof_and_different_pool(
    destination, native_lease_targets, monkeypatch, mode
):
    t = native_lease_targets
    engine = t["engine"](object())
    session = t["session"](engine, preexisting=mode == "preexisting")
    if mode == "unsupported_session":
        session = SimpleNamespace()

    async def resolve(cls, request, token, query_db, **kwargs):
        if mode == "unowned_checkout":
            context = m._HTTP.set(None)
            try:
                t["event"].emit(engine.sync_engine.pool, "checkout", None, session.entry, None)
            finally:
                m._HTTP.reset(context)
            t["event"].emit(
                session.sync_session, "after_begin", session.sync_session, None, session.connection
            )
        return query_db

    monkeypatch.setattr(t["login"], "_resolve_current_user", classmethod(resolve))
    uninstall = m.install_account_query_native_lease_diagnostics(destination, isolated_test=True)

    async def app(*args):
        await t["login"]._resolve_current_user(None, SECRET, session)
        if mode == "different_pool":
            token = m._RC.set({"connection": None})
            try:
                await t["connection"](t["engine"](object())).__aenter__()
            finally:
                m._RC.reset(token)

    try:
        await m.wrap_account_query_http(app, destination, isolated_test=True)(
            target_scope(), AsyncMock(), AsyncMock()
        )
        value = reports(destination)[0]["native_lease"]
        if mode == "different_pool":
            assert (
                value["observation"] == "OBSERVED"
                and value["rc_checkouts"][0]["same_pool"] is False
            )
        else:
            assert value["observation"] == "UNKNOWN"
        if mode in ("preexisting", "unowned_checkout"):
            assert value["native_leases"][0]["checkout_seconds"] is None
        assert t["event"].listeners == []
    finally:
        uninstall()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_native_lease_failure_cancel_cleans_all_listeners_without_changing_failure(
    destination, native_lease_targets, monkeypatch, cancel
):
    t = native_lease_targets
    failure = asyncio.CancelledError() if cancel else RuntimeError(SECRET)
    original = t["login"]._resolve_current_user

    async def failed(cls, request, token, query_db, **kwargs):
        await original(request, token, query_db)
        raise failure

    monkeypatch.setattr(t["login"], "_resolve_current_user", classmethod(failed))
    uninstall = m.install_account_query_native_lease_diagnostics(destination, isolated_test=True)
    session = t["session"](t["engine"](object()))

    async def app(*args):
        await t["login"]._resolve_current_user(None, SECRET, session)

    try:
        with pytest.raises(type(failure)) as caught:
            await m.wrap_account_query_http(app, destination, isolated_test=True)(
                target_scope(), AsyncMock(), AsyncMock()
            )
        assert caught.value is failure and t["event"].listeners == []
        assert reports(destination)[0]["native_lease"]["cleanup"] == "REMOVED"
        assert SECRET not in json.dumps(reports(destination))
    finally:
        uninstall()


@pytest.mark.asyncio
async def test_native_lease_parallel_same_pool_cannot_claim_other_request(
    destination, native_lease_targets
):
    t = native_lease_targets
    engine = t["engine"](object())
    uninstall = m.install_account_query_native_lease_diagnostics(destination, isolated_test=True)

    async def app(*args):
        session = t["session"](engine)
        await t["login"]._resolve_current_user(None, SECRET, session)
        await asyncio.sleep(0)
        t["event"].emit(engine.sync_engine.pool, "checkin", None, session.entry)

    try:
        wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
        await asyncio.gather(*[wrapped(target_scope(), AsyncMock(), AsyncMock()) for _ in range(2)])
        values = reports(destination)
        assert len(values) == 2
        assert all(len(r["native_lease"]["native_leases"]) == 1 for r in values)
        assert all(
            r["native_lease"]["native_leases"][0]["release_seconds"] is not None for r in values
        )
        assert t["event"].listeners == []
    finally:
        uninstall()


def test_native_lease_guard_and_duplicate_exact_restore(destination, native_lease_targets):
    t = native_lease_targets
    original = vars(t["login"])["_resolve_current_user"]
    with pytest.raises(ValueError, match="ISOLATION_REQUIRED"):
        m.install_account_query_native_lease_diagnostics(destination, isolated_test=1)
    uninstall = m.install_account_query_native_lease_diagnostics(destination, isolated_test=True)
    try:
        with pytest.raises(ValueError, match="ALREADY_INSTALLED"):
            m.install_account_query_native_lease_diagnostics(destination, isolated_test=True)
    finally:
        uninstall()
    assert vars(t["login"])["_resolve_current_user"] is original
    assert "__aenter__" not in vars(t["connection"])


@pytest.mark.asyncio
async def test_native_lease_non_target_does_not_attach_or_uninstall_active_request(
    destination, native_lease_targets
):
    t = native_lease_targets
    uninstall = m.install_account_query_native_lease_diagnostics(destination, isolated_test=True)
    session = t["session"](t["engine"](object()))

    async def app(scope, receive, send):
        assert await t["login"]._resolve_current_user(None, SECRET, session) is session
        if scope["path"] == "/api/v1/accounts/extended":
            with pytest.raises(ValueError, match="REQUEST_ACTIVE"):
                uninstall()

    wrapped = m.wrap_account_query_http(app, destination, isolated_test=True)
    try:
        await wrapped(target_scope(path="/other"), AsyncMock(), AsyncMock())
        assert reports(destination) == [] and t["event"].listeners == []
        await wrapped(target_scope(), AsyncMock(), AsyncMock())
        assert t["event"].listeners == []
    finally:
        uninstall()


@pytest.mark.asyncio
async def test_native_lease_failed_cleanup_blocks_late_callbacks_and_retries(
    destination, native_lease_targets, monkeypatch
):
    t = native_lease_targets
    session = t["session"](t["engine"](object()))
    event = t["event"]
    original_remove = event.remove
    fail_once = [True]

    def remove(owner, name, callback):
        if name == "checkin" and fail_once[0]:
            fail_once[0] = False
            raise ValueError("REMOVE_FAILED")
        original_remove(owner, name, callback)

    monkeypatch.setattr(event, "remove", remove)
    uninstall = m.install_account_query_native_lease_diagnostics(destination, isolated_test=True)

    async def app(*args):
        await t["login"]._resolve_current_user(None, SECRET, session)

    await m.wrap_account_query_http(app, destination, isolated_test=True)(
        target_scope(), AsyncMock(), AsyncMock()
    )
    before = reports(destination)
    assert before[0]["native_lease"]["cleanup"] == "FAILED"
    assert len(event.listeners) == 1
    event.emit(session.bind.sync_engine.pool, "checkin", None, session.entry)
    assert reports(destination) == before
    uninstall()
    assert event.listeners == [] and reports(destination) == before
