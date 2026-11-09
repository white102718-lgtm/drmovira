"""只读认证自有session边界纯测试；不连接数据库/缓存，不代替真实原认证链。"""

import ast
import asyncio
import importlib.util
import inspect
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from starlette.requests import Request


class Role(BaseModel):
    name: str


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    password: str = Field(default="excluded-value", exclude=True)
    role: list[Role]


class User(BaseModel):
    model_config = ConfigDict(extra="allow")
    user: UserInfo
    permissions: list[str]
    roles: list[str]
    pwd_chrtype: str = "4"
    is_default_modify_pwd: bool = True
    is_password_expired: bool = False
    _private: dict = PrivateAttr(default_factory=lambda: {"preserve": True})


@pytest.fixture
def adapter(monkeypatch):
    events = []
    owned = object()
    user = User(
        user=UserInfo(user_id=7, role=[Role(name="reader")]),
        permissions=["accounts.read"],
        roles=["reader"],
        extra_field={"nested": ["kept"]},
    )
    resolver = AsyncMock(return_value=user)

    @asynccontextmanager
    async def session(*, log_sql):
        assert log_sql is False
        events.append("owned-enter")
        try:
            yield owned
        except BaseException as exc:
            events.append(("owned-error", exc))
            raise
        finally:
            events.append("owned-exit")

    async def oauth2():
        return None

    modules = {
        "config.database": {"DataSourceRegistry": SimpleNamespace(session=session)},
        "module_admin.entity.vo.user_vo": {"CurrentUserModel": User},
        "module_admin.service.login_service": {
            "LoginService": SimpleNamespace(get_current_user=resolver),
            "oauth2_scheme": oauth2,
        },
    }
    for name, values in modules.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    source = Path(__file__).parents[1] / "orbit_api/account_read_identity.py"
    spec = importlib.util.spec_from_file_location("pure_account_read_identity", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return SimpleNamespace(
        module=module, events=events, owned=owned, user=user, resolver=resolver, oauth2=oauth2
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["Bearer opaque-test-token", None])
async def test_complete_original_entry_and_owned_exit_before_business(adapter, token):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/accounts/extended",
            "headers": [(b"cookie", b"opaque-test-cookie")],
            "state": {"query_db": object()},
        }
    )
    original_shared = request.state.query_db

    def resolved(*args):
        assert adapter.events == ["owned-enter"]
        adapter.events.append("original-auth-complete")
        return adapter.user

    adapter.resolver.side_effect = resolved
    result = await adapter.module.account_read_identity(request, token)
    assert result is adapter.user
    adapter.resolver.assert_awaited_once_with(request, token, adapter.owned)
    assert request.state.query_db is original_shared
    assert adapter.events == ["owned-enter", "original-auth-complete", "owned-exit"]
    assert result.user.user_id == 7 and result.pwd_chrtype == "4"
    assert result.user.password == "excluded-value"
    assert result.__pydantic_extra__ == {"extra_field": {"nested": ["kept"]}}
    assert result._private == {"preserve": True}
    assert result.user.role[0].name == "reader"
    assert result.permissions == ["accounts.read"] and result.roles == ["reader"]
    assert result.is_default_modify_pwd is True and result.is_password_expired is False
    signature = inspect.signature(adapter.module.account_read_identity)
    assert signature.parameters["token"].annotation.__metadata__[0].dependency is adapter.oauth2


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["initial-token", "validator", "cookie", "policy", "final-token"])
async def test_all_original_auth_failures_propagate_without_translation(adapter, phase):
    failure = RuntimeError(phase)
    adapter.resolver.side_effect = failure
    with pytest.raises(RuntimeError) as caught:
        await adapter.module.account_read_identity(object(), None)
    assert caught.value is failure
    assert adapter.events == ["owned-enter", ("owned-error", failure), "owned-exit"]
    assert adapter.resolver.await_count == 1


@pytest.mark.asyncio
async def test_original_excluded_result_none_preserved(adapter):
    adapter.resolver.return_value = None
    assert await adapter.module.account_read_identity(object(), None) is None
    assert adapter.events == ["owned-enter", "owned-exit"]


@pytest.mark.asyncio
async def test_inflight_cancel_preserves_error_and_exits_owned_session(adapter):
    entered = asyncio.Event()

    async def blocked(*args):
        entered.set()
        await asyncio.Event().wait()

    adapter.resolver.side_effect = blocked
    task = asyncio.create_task(adapter.module.account_read_identity(object(), "opaque-test-token"))
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert adapter.events[0] == "owned-enter" and adapter.events[-1] == "owned-exit"
    assert isinstance(adapter.events[1][1], asyncio.CancelledError)


@pytest.mark.asyncio
async def test_owned_exit_failure_prevents_business_result(adapter, monkeypatch):
    failure = RuntimeError("close-failed")

    @asynccontextmanager
    async def session(*, log_sql):
        yield adapter.owned
        raise failure

    monkeypatch.setattr(adapter.module.DataSourceRegistry, "session", session)
    with pytest.raises(RuntimeError) as caught:
        await adapter.module.account_read_identity(object(), None)
    assert caught.value is failure


@pytest.mark.asyncio
async def test_user_nested_values_materialized_before_owned_session_closes(adapter, monkeypatch):
    state = {"closed": False, "reads": 0}

    class Source:
        def __getattribute__(self, name):
            if name in {"user_id", "role"}:
                assert state["closed"] is False
                state["reads"] += 1
                return 7 if name == "user_id" else [{"name": "reader"}]
            return object.__getattribute__(self, name)

    async def resolve(*args):
        return User(
            user=UserInfo.model_validate(Source()), permissions=["accounts.read"], roles=["reader"]
        )

    @asynccontextmanager
    async def session(*, log_sql):
        yield adapter.owned
        state["closed"] = True

    monkeypatch.setattr(adapter.module.DataSourceRegistry, "session", session)
    adapter.resolver.side_effect = resolve
    result = await adapter.module.account_read_identity(object(), None)
    reads = state["reads"]
    assert state["closed"] is True
    assert result.user.user_id == 7 and result.user.role[0].name == "reader"
    assert state["reads"] == reads
    assert isinstance(result.user, BaseModel) and isinstance(result.user.role[0], BaseModel)


def test_only_two_target_routes_use_new_dependency_owner_options_keeps_original():
    path = Path(__file__).parents[1] / "orbit_api/account_details_routes.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    functions = {n.name: n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)}
    for name in ("extended", "details"):
        user = next(a for a in functions[name].args.args if a.arg == "user")
        assert isinstance(user.annotation, ast.Name) and user.annotation.id == "ReadUser"
    user = next(a for a in functions["owner_options"].args.args if a.arg == "user")
    assert user.annotation.id == "User"
    for name in ("extended", "details"):
        body = ast.unparse(functions[name])
        assert "read_committed_session(DataSourceRegistry)" in body
        assert "details_store().list" in body


@pytest.mark.asyncio
async def test_concurrent_calls_create_and_exit_distinct_owned_sessions(adapter, monkeypatch):
    created = []
    exited = []

    @asynccontextmanager
    async def session(*, log_sql):
        assert log_sql is False
        owned = object()
        created.append(owned)
        try:
            yield owned
        finally:
            exited.append(owned)

    async def resolve(request, token, owned):
        assert owned in created and owned not in exited
        await asyncio.sleep(0)
        return adapter.user

    monkeypatch.setattr(adapter.module.DataSourceRegistry, "session", session)
    adapter.resolver.side_effect = resolve
    result = await asyncio.gather(
        *[adapter.module.account_read_identity(object(), None) for _ in range(4)]
    )
    assert all(value is adapter.user for value in result)
    assert len(created) == len(exited) == len(result)
    assert len({id(value) for value in created}) == len(result)
    assert all(value in exited for value in created)


@pytest.mark.asyncio
async def test_session_enter_failure_never_calls_original_auth(adapter, monkeypatch):
    failure = RuntimeError("owned-enter-failed")

    @asynccontextmanager
    async def session(*, log_sql):
        raise failure
        yield

    monkeypatch.setattr(adapter.module.DataSourceRegistry, "session", session)
    with pytest.raises(RuntimeError) as caught:
        await adapter.module.account_read_identity(object(), None)
    assert caught.value is failure
    adapter.resolver.assert_not_awaited()
