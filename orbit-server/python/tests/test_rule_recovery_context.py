"""规则再认证上下文纯协议/实际路由适配；不读取配置、不连接SQL或HTTP服务。"""

import importlib.util
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import Depends
from pydantic import BaseModel, ValidationError
from starlette.requests import Request

from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError


def uid(n):
    return str(UUID(int=n))


@pytest.fixture
def core(monkeypatch):
    async def dep():
        pass

    def boundary(request, allowed):
        assert allowed == {"action"}
        if set(request.query_params) - allowed:
            raise OrbitError(400, "UNKNOWN_FIELD", "未知")
        if "x-target-tenant" in request.headers:
            raise OrbitError(403, "PERMISSION_DENIED", "无")
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise OrbitError(400, "INVALID_STRUCTURE", "重复")

    modules = {
        "common.aspect.pre_auth": {"CurrentUserDependency": lambda: Depends(dep)},
        "config.database": {"DataSourceRegistry": SimpleNamespace()},
        "module_admin.entity.vo.user_vo": {"CurrentUserModel": BaseModel},
        "orbit_api.configuration_routes": {
            "_read_boundary": boundary,
            "credential_cipher": lambda: pytest.fail("boundary must reject before cipher"),
        },
    }
    for name, values in modules.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    path = Path(__file__).resolve().parents[1] / "orbit_api/rule_recovery_context_routes.py"
    spec = importlib.util.spec_from_file_location("pure_rule_recovery_routes", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request(query=b"action=PAUSE", *, body=b"", headers=()):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/rules/recovery-context",
            "query_string": query,
            "headers": list(headers),
        },
        receive,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values,status,code",
    [
        ({"query": b""}, 422, "FIELD_INVALID"),
        ({"query": b"action=DELETE"}, 422, "FIELD_INVALID"),
        ({"query": b"action=PAUSE&rule_id=" + uid(2).encode()}, 400, "UNKNOWN_FIELD"),
        ({"query": b"action=PAUSE&actor_id=91"}, 400, "UNKNOWN_FIELD"),
        ({"query": b"action=PAUSE&tenant_id=" + uid(1).encode()}, 400, "UNKNOWN_FIELD"),
        ({"query": b"action=PAUSE&action=ARCHIVE"}, 400, "INVALID_STRUCTURE"),
        ({"headers": [(b"x-target-tenant", uid(1).encode())]}, 403, "PERMISSION_DENIED"),
        ({"body": b"{}"}, 400, "INVALID_STRUCTURE"),
        ({"body": b" "}, 400, "INVALID_STRUCTURE"),
    ],
)
async def test_actual_get_boundary_before_session_or_cipher(core, values, status, code):
    with pytest.raises(OrbitError) as caught:
        await core.recovery_context(request(**values), SimpleNamespace())
    assert (caught.value.status, caught.value.code) == (status, code)
    if status == 422:
        assert caught.value.pointer == "/action"


def response(**changes):
    return {
        "actor_id": 91,
        "tenant_id": uid(1),
        "csrf_token": "opaque-current-session-csrf",
    } | changes


@pytest.mark.parametrize(
    "changes",
    [
        {"actor_id": True},
        {"actor_id": 0},
        {"actor_id": 9007199254740992},
        {"actor_id": "91"},
        {"tenant_id": "bad"},
        {"tenant_id": uid(255).upper()},
        {"tenant_id": UUID(int=1)},
        {"csrf_token": "x" * 15},
        {"csrf_token": "x" * 256},
        {"csrf_token": None},
        {"permissions": ["rules.read"]},
        {"rule_id": uid(2)},
    ],
)
def test_response_exact_three_strict_native_id_tenant_and_csrf(core, changes):
    with pytest.raises(ValidationError):
        core.RuleRecoveryContext.model_validate(response(**changes))


def session():
    tx = object()
    return SimpleNamespace(
        in_transaction=lambda: True, sync_session=SimpleNamespace(get_transaction=lambda: tx)
    )


class Tokens:
    def __init__(self, events):
        self.events = events
        self.issued = []

    def session_binding(self, authorization, actor, tenant):
        assert authorization == "memory-only-auth" and actor == 91 and tenant == uid(1)
        self.events.append("binding")
        return "session-hash"

    def issue(self, purpose, claims):
        self.events.append("issue")
        self.issued.append((purpose, claims))
        return "opaque-current-session-csrf"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,permission",
    [
        ("CREATE", "rules.create"),
        ("UPDATE", "rules.edit"),
        ("ENABLE", "rules.enable"),
        ("PAUSE", "rules.pause"),
        ("ARCHIVE", "rules.archive"),
        ("SIMULATE", "rules.read"),
    ],
)
async def test_action_independent_current_identity_original_csrf_and_last_reauth(
    core, monkeypatch, action, permission
):
    actual = session()
    current = BusinessContext(91, uid(1), "USER", uid(2), uid(3))
    access, events = SimpleNamespace(current=current), []

    async def authorize(db, actor, code):
        assert db is actual and actor == 91 and code == permission
        events.append("authorize")
        return access

    async def final(db, original):
        assert db is actual and original is access
        events.append("final")

    monkeypatch.setattr(core, "authorize_rule", authorize)
    monkeypatch.setattr(core, "revalidate_access", final)
    tokens = Tokens(events)
    result = await core.current_recovery_context(actual, 91, "memory-only-auth", action, tokens)
    assert result == response() and set(result) == {"actor_id", "tenant_id", "csrf_token"}
    assert events == ["authorize", "binding", "issue", "final"]
    assert tokens.issued == [("DIRECTORY_CSRF_V1", {"binding": "session-hash"})]


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["initial", "final"])
@pytest.mark.parametrize("status", [401, 403, 409])
async def test_current_denials_never_return_identity_or_token(core, monkeypatch, where, status):
    events, actual = [], session()
    failure = OrbitError(status, "PERMISSION_DENIED", "固定安全错误")
    access = SimpleNamespace(current=BusinessContext(91, uid(1), "USER", uid(2), uid(3)))
    auth, final = AsyncMock(return_value=access), AsyncMock()
    (auth if where == "initial" else final).side_effect = failure
    monkeypatch.setattr(core, "authorize_rule", auth)
    monkeypatch.setattr(core, "revalidate_access", final)
    tokens = Tokens(events)
    with pytest.raises(OrbitError) as caught:
        await core.current_recovery_context(actual, 91, "memory-only-auth", "PAUSE", tokens)
    assert caught.value is failure
    if where == "initial":
        assert tokens.issued == []
        final.assert_not_awaited()


@pytest.mark.asyncio
async def test_actor_mismatch_fails_closed_before_token_and_bad_internal_output_503(
    core, monkeypatch
):
    current = BusinessContext(92, uid(1), "USER", uid(2), uid(3))
    monkeypatch.setattr(
        core, "authorize_rule", AsyncMock(return_value=SimpleNamespace(current=current))
    )
    final = AsyncMock()
    monkeypatch.setattr(core, "revalidate_access", final)
    tokens = Tokens([])
    with pytest.raises(OrbitError) as caught:
        await core.current_recovery_context(session(), 91, "memory-only-auth", "PAUSE", tokens)
    assert caught.value.status == 503 and tokens.issued == []
    final.assert_not_awaited()
    monkeypatch.setattr(
        core,
        "authorize_rule",
        AsyncMock(
            return_value=SimpleNamespace(
                current=BusinessContext(91, uid(1), "USER", uid(2), uid(3))
            )
        ),
    )
    tokens.issue = lambda *a: "bad"
    with pytest.raises(OrbitError) as caught:
        await core.current_recovery_context(session(), 91, "memory-only-auth", "PAUSE", tokens)
    assert caught.value.status == 503


@pytest.mark.asyncio
async def test_actual_route_one_outer_transaction_native_user_no_user_supplied_actor(
    core, monkeypatch
):
    actual, events = SimpleNamespace(), []

    @asynccontextmanager
    async def begin():
        events.append("begin")
        yield
        events.append("end")

    @asynccontextmanager
    async def sessions(*, log_sql):
        assert log_sql is False
        yield actual

    async def get(db, actor, authorization, action, tokens):
        assert db is actual and actor == 91 and authorization == "memory-only-auth"
        assert action == "ARCHIVE" and tokens is sentinel
        assert events == ["begin"]
        return response()

    sentinel = object()
    actual.begin = begin
    core.DataSourceRegistry.session = sessions
    monkeypatch.setattr(core, "credential_cipher", lambda: None)
    monkeypatch.setattr(core, "DirectoryTokens", lambda cipher: sentinel)
    monkeypatch.setattr(core, "current_recovery_context", get)
    result = await core.recovery_context(
        request(b"action=ARCHIVE", headers=[(b"authorization", b"memory-only-auth")]),
        SimpleNamespace(user=SimpleNamespace(user_id=91)),
    )
    assert result == response() and events == ["begin", "end"]


@pytest.mark.asyncio
async def test_cookie_uses_original_in_memory_csrf_without_new_mac_or_bearer(core, monkeypatch):
    import orbit_api.cookie_identity as cookies
    from orbit_api.directory_tokens import DirectoryTokens

    identity = SimpleNamespace(
        actor_id=91,
        tenant_id=uid(1),
        session_id=uid(5),
        csrf_token="actual-cookie-current-session-csrf",
    )
    monkeypatch.setattr(cookies, "current_cookie_identity", lambda: identity)
    access = SimpleNamespace(current=BusinessContext(91, uid(1), "USER", uid(2), uid(3)))
    monkeypatch.setattr(core, "authorize_rule", AsyncMock(return_value=access))
    final = AsyncMock()
    monkeypatch.setattr(core, "revalidate_access", final)
    result = await core.current_recovery_context(
        session(), 91, "", "ARCHIVE", DirectoryTokens(None)
    )
    assert result == response(csrf_token=identity.csrf_token)
    final.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [{"actor_id": 92}, {"tenant_id": uid(99)}])
async def test_cookie_context_mismatch_returns_no_recovery_token(core, monkeypatch, changed):
    import orbit_api.cookie_identity as cookies
    from orbit_api.directory_tokens import DirectoryTokens

    identity = SimpleNamespace(
        **(
            {
                "actor_id": 91,
                "tenant_id": uid(1),
                "session_id": uid(5),
                "csrf_token": "actual-current-session-csrf",
            }
            | changed
        )
    )
    monkeypatch.setattr(cookies, "current_cookie_identity", lambda: identity)
    access = SimpleNamespace(current=BusinessContext(91, uid(1), "USER", uid(2), uid(3)))
    monkeypatch.setattr(core, "authorize_rule", AsyncMock(return_value=access))
    final = AsyncMock()
    monkeypatch.setattr(core, "revalidate_access", final)
    with pytest.raises(OrbitError) as caught:
        await core.current_recovery_context(session(), 91, "", "PAUSE", DirectoryTokens(None))
    assert (caught.value.status, caught.value.code) == (401, "SESSION_REQUIRED")
    final.assert_not_awaited()
