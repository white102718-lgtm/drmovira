"""执行真实路由的纯适配合同；无DB、私有env、真实来源200或浏览器验收。"""

import base64
import importlib.util
import json
import sys
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from fastapi import Depends
from pydantic import BaseModel
from starlette.requests import Request

from orbit_api import cookie_identity
from orbit_api.authorization import BusinessContext
from orbit_api.credentials import CredentialCipher
from orbit_api.directory_tokens import DirectoryTokens, canonical
from orbit_api.errors import OrbitError
from orbit_api.metrics_contract import parse_metric_query
from orbit_api.metrics_query_result_store import MetricsQueryResultStore

TENANT = "00000000-0000-0000-0000-000000000001"
PROFILE = "00000000-0000-0000-0000-000000000002"
ACTOR = 31
BEARER = "Bearer pure-metrics-session"
QUERY = {
    "date_from": "2026-01-01",
    "date_to": "2026-01-04",
    "dataset": "AD",
    "metric_profile_id": PROFILE,
    "scope_snapshot_id": None,
    "channel_id": None,
    "operator_user_id": None,
    "q": "",
    "sort": "spend",
    "direction": "DESC",
    "cursor": None,
    "page_size": 20,
    "granularity": "SUMMARY",
}


@pytest.fixture
def harness(monkeypatch):
    """仅替换框架导入边界，实际路由、严格parser、CSRF、默认Store继续执行。"""
    events = []
    session = SimpleNamespace(bind=SimpleNamespace(connect=Mock()), active=False)

    @asynccontextmanager
    async def begin():
        assert not session.active
        session.active = True
        events.append("auth-begin")
        try:
            yield
        finally:
            session.active = False
            events.append("auth-end")

    session.begin = begin

    @asynccontextmanager
    async def sessions(*, log_sql):
        assert log_sql is False
        events.append("session-enter")
        try:
            yield session
        finally:
            events.append("session-exit")

    registry = SimpleNamespace(session=sessions)
    cipher = CredentialCipher("pure", {"pure": base64.b64encode(b"m" * 32).decode()})
    tokens = DirectoryTokens(cipher)
    csrf = tokens.issue(
        "DIRECTORY_CSRF_V1", {"binding": tokens.session_binding(BEARER, ACTOR, TENANT)}
    )
    raw = canonical(QUERY).encode()

    async def boundary(_request):
        events.append("boundary")
        return "metrics-pure-key-0001", csrf, 0, raw

    async def authorized(_session, actor, menu, permission):
        assert _session is session and session.active
        assert (actor, menu, permission) == (ACTOR, "monitor", "monitor.read")
        events.append("monitor-authorized")
        return BusinessContext(ACTOR, TENANT, "USER", PROFILE, PROFILE)

    async def dependency():
        return None

    modules = {
        "common.aspect.pre_auth": {"CurrentUserDependency": lambda: Depends(dependency)},
        "config.database": {"DataSourceRegistry": registry},
        "module_admin.entity.vo.user_vo": {"CurrentUserModel": BaseModel},
        "orbit_api.configuration_routes": {
            "_read_boundary": Mock(),
            "credential_cipher": lambda: cipher,
        },
        "orbit_api.reference_routes": {"write_boundary": boundary},
    }
    for name, values in modules.items():
        stub = ModuleType(name)
        stub.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, stub)
    path = Path(__file__).parents[1] / "orbit_api" / "metrics_routes.py"
    spec = importlib.util.spec_from_file_location("pure_metrics_route_under_test", path)
    route = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(route)
    monkeypatch.setattr(route, "require_business_access", authorized)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/metrics/query",
            "headers": [(b"authorization", BEARER.encode())],
            "query_string": b"",
            "state": {"orbit_request_id": "original-pure-request-id"},
            "app": SimpleNamespace(state=SimpleNamespace()),
        }
    )
    user = SimpleNamespace(user=SimpleNamespace(user_id=ACTOR))
    return SimpleNamespace(
        route=route,
        session=session,
        registry=registry,
        events=events,
        cipher=cipher,
        csrf=csrf,
        request=request,
        user=user,
        raw=raw,
    )


@pytest.mark.asyncio
async def test_actual_route_passes_strict_parsed_dict_to_real_store_interface_after_auth_end(
    harness, monkeypatch
):
    h = harness
    service = create_autospec(MetricsQueryResultStore, instance=True)

    async def run(engine, actor, body, key, request_id, authorization):
        assert engine is h.session.bind and not h.session.active
        assert h.events[-1] == "auth-end"
        assert actor == ACTOR and authorization == BEARER
        assert type(body) is dict and body == parse_metric_query(h.raw) and len(body) == 13
        assert body is not QUERY
        assert key == "metrics-pure-key-0001" and request_id == "original-pure-request-id"
        h.events.append("store-run")
        return {"pure_adapter_fixture": True}  # 替身响应，不冒充真实Metrics200业务来源。

    service.run.side_effect = run
    monkeypatch.setattr(h.route, "result_service", lambda request: service)
    response = await h.route.query(h.request, h.user)
    assert response.status_code == 200 and json.loads(response.body) == {
        "pure_adapter_fixture": True
    }
    assert h.events == [
        "boundary",
        "session-enter",
        "auth-begin",
        "monitor-authorized",
        "auth-end",
        "store-run",
        "session-exit",
    ]
    service.run.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        canonical(QUERY | {"unexpected": True}).encode(),
        canonical(
            {key: value for key, value in QUERY.items() if key != "scope_snapshot_id"}
        ).encode(),
        b'{"date_from":"2026-01-01","date_from":"2026-01-02"}',
        canonical(QUERY | {"page_size": True}).encode(),
    ],
)
async def test_strict_original_body_rejected_before_authorization_session(
    harness, monkeypatch, raw
):
    h = harness
    monkeypatch.setattr(h.route, "write_boundary", AsyncMock(return_value=("key", h.csrf, 0, raw)))
    service = Mock()
    monkeypatch.setattr(h.route, "result_service", service)
    with pytest.raises(OrbitError) as caught:
        await h.route.query(h.request, h.user)
    assert caught.value.status in {400, 422}
    assert h.events == []
    service.assert_not_called()


@pytest.mark.asyncio
async def test_csrf_current_session_checked_before_constructing_store(harness, monkeypatch):
    h = harness
    other = DirectoryTokens(h.cipher)
    csrf = other.issue(
        "DIRECTORY_CSRF_V1", {"binding": other.session_binding("Bearer another", ACTOR, TENANT)}
    )
    monkeypatch.setattr(h.route, "write_boundary", AsyncMock(return_value=("key", csrf, 0, h.raw)))
    service = Mock()
    monkeypatch.setattr(h.route, "result_service", service)
    with pytest.raises(OrbitError) as caught:
        await h.route.query(h.request, h.user)
    assert (caught.value.status, caught.value.code) == (403, "CSRF_INVALID")
    service.assert_not_called()
    assert h.events == [
        "session-enter",
        "auth-begin",
        "monitor-authorized",
        "auth-end",
        "session-exit",
    ]


@pytest.mark.asyncio
async def test_current_monitor_denied_cannot_enter_store_or_borrow_other_actions(
    harness, monkeypatch
):
    h = harness
    denied = AsyncMock(side_effect=OrbitError(403, "PERMISSION_DENIED", "pure deny"))
    monkeypatch.setattr(h.route, "require_business_access", denied)
    service = Mock()
    monkeypatch.setattr(h.route, "result_service", service)
    with pytest.raises(OrbitError) as caught:
        await h.route.query(h.request, h.user)
    assert caught.value.status == 403
    assert denied.await_args.args[1:] == (ACTOR, "monitor", "monitor.read")
    assert denied.await_count == 1
    service.assert_not_called()


@pytest.mark.asyncio
async def test_actual_default_store_without_provider_raises503_before_owned_connection(harness):
    h = harness
    service = h.route.result_service(h.request)
    assert type(service) is MetricsQueryResultStore
    assert service.read.source_provider is None and service.expected_provider is None
    with pytest.raises(OrbitError) as caught:
        await h.route.query(h.request, h.user)
    assert caught.value.status == 503
    h.session.bind.connect.assert_not_called()
    assert not h.session.active and h.events[-2:] == ["auth-end", "session-exit"]


@pytest.mark.asyncio
async def test_actual_capabilities_uses_current_monitor_context_and_session_binding(harness):
    h = harness
    result = await h.route.capabilities(h.request, h.user)
    assert set(result) == {"csrf_token"}
    claims = DirectoryTokens(h.cipher).verify("DIRECTORY_CSRF_V1", result["csrf_token"])
    assert claims["binding"] == DirectoryTokens.session_binding(BEARER, ACTOR, TENANT)
    assert claims["binding"] != DirectoryTokens.session_binding("Bearer another", ACTOR, TENANT)
    assert h.events == [
        "session-enter",
        "auth-begin",
        "monitor-authorized",
        "auth-end",
        "session-exit",
    ]


@pytest.mark.asyncio
async def test_verified_cookie_capability_and_post_use_cookie_session_not_bearer(
    harness, monkeypatch
):
    h = harness
    identity = cookie_identity.CookieIdentity(
        ACTOR,
        TENANT,
        1,
        "cookie-pure-session",
        "cookie-pure-csrf-" + "a" * 32,
        datetime.now(UTC) + timedelta(minutes=5),
    )
    context = ContextVar("pure_metrics_cookie", default=identity)
    monkeypatch.setattr(cookie_identity, "_identity", context)
    result = await h.route.capabilities(h.request, h.user)
    assert result == {"csrf_token": identity.csrf_token}
    # 已验证Cookie身份由原认证依赖提供；纯路由测试不冒充Cookie数据库认证。
    assert DirectoryTokens.session_binding(
        BEARER, ACTOR, TENANT
    ) == DirectoryTokens.session_binding("", ACTOR, TENANT)
    monkeypatch.setattr(
        h.route,
        "write_boundary",
        AsyncMock(return_value=("metrics-pure-key-0001", result["csrf_token"], 0, h.raw)),
    )
    service = create_autospec(MetricsQueryResultStore, instance=True)
    service.run.return_value = {"pure_adapter_fixture": True}
    monkeypatch.setattr(h.route, "result_service", lambda request: service)
    await h.route.query(h.request, h.user)
    assert service.run.await_args.args[2] == QUERY


@pytest.mark.asyncio
async def test_cookie_csrf_cannot_be_reused_from_another_verified_cookie_session(
    harness, monkeypatch
):
    h = harness
    identity = cookie_identity.CookieIdentity(
        ACTOR,
        TENANT,
        1,
        "new-cookie-session",
        "new-cookie-csrf-" + "b" * 32,
        datetime.now(UTC) + timedelta(minutes=5),
    )
    monkeypatch.setattr(
        cookie_identity, "_identity", ContextVar("pure_metrics_cookie", default=identity)
    )
    # 原native签名CSRF也不能替代本Cookie会话的唯一CSRF。
    service = Mock()
    monkeypatch.setattr(h.route, "result_service", service)
    with pytest.raises(OrbitError) as caught:
        await h.route.query(h.request, h.user)
    assert (caught.value.status, caught.value.code) == (403, "CSRF_INVALID")
    service.assert_not_called()
