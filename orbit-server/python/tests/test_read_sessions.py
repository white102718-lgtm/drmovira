"""独占RC读取生命周期；真实MySQL隔离级别和池恢复另由集成工具验收。"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import orbit_api.read_sessions as module
from orbit_api.errors import OrbitError


class Session:
    created = []

    def __init__(self, **options):
        self.options = options
        self.bind = options.get("bind")
        self.sync_session = SimpleNamespace()
        self.autoflush = False
        self.info = options.get("info", {})
        self.created.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True


class Engine:
    def __init__(self):
        self.connection = SimpleNamespace(
            execution_options=AsyncMock(), invalidate=AsyncMock(), invalidated=False
        )

    @asynccontextmanager
    async def connect(self):
        try:
            yield self.connection
        finally:
            self.closed = True


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(module, "AsyncEngine", Engine)
    engine = Engine()
    template = Session(bind=engine, info={"cache": object()})

    @asynccontextmanager
    async def session(**options):
        assert options == {"log_sql": False}
        yield template

    return SimpleNamespace(session=session), template, engine


@pytest.mark.asyncio
async def test_owned_connection_is_configured_before_yield_and_keeps_framework_cache(setup):
    registry, template, engine = setup
    async with module.read_committed_session(registry) as session:
        engine.connection.execution_options.assert_awaited_once_with(
            isolation_level="READ COMMITTED"
        )
        assert session.bind is engine.connection
        assert session.options["sync_session_class"] is type(template.sync_session)
        assert session.options["expire_on_commit"] is False
        assert session.info == template.info and session.info is not template.info
        session.info["request"] = True
        assert "request" not in template.info
    assert session.closed and engine.closed
    engine.connection.invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_expected_business_error_preserves_safe_connection_reuse(setup):
    registry, _, engine = setup
    error = OrbitError(404, "NOT_FOUND", "记录不可见")
    with pytest.raises(OrbitError) as caught:
        async with module.read_committed_session(registry):
            raise error
    assert caught.value is error and engine.closed
    engine.connection.invalidate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [asyncio.CancelledError(), RuntimeError("cleanup")])
async def test_unknown_failure_or_cancel_invalidates_owned_connection(setup, error):
    registry, _, engine = setup
    with pytest.raises(type(error)):
        async with module.read_committed_session(registry):
            raise error
    engine.connection.invalidate.assert_awaited_once()
    assert engine.closed


@pytest.mark.asyncio
async def test_invalidated_connection_is_never_reconnected_for_restoration(setup):
    registry, _, engine = setup
    engine.connection.invalidated = True
    with pytest.raises(RuntimeError):
        async with module.read_committed_session(registry):
            raise RuntimeError("lost")
    engine.connection.invalidate.assert_not_awaited()
    assert engine.closed


@pytest.mark.asyncio
async def test_wrong_bind_fails_before_owned_connection_or_yield(setup):
    registry, template, engine = setup
    template.bind = object()
    with pytest.raises(TypeError):
        async with module.read_committed_session(registry):
            pytest.fail("不能产生未配置RC的会话")
    engine.connection.execution_options.assert_not_awaited()
