"""同事务列表授权复用纯协议测试；不计SQL锁、Cookie或容量实测。"""

import copy
import gc
import weakref
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import orbit_api.identity_publication_summary as module
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError


@pytest.fixture
def boundary(monkeypatch):
    state = SimpleNamespace(tx=object(), nested=None, native=object(), cookie=object())
    session = SimpleNamespace(
        sync_session=SimpleNamespace(
            get_transaction=lambda: state.tx, get_nested_transaction=lambda: state.nested
        )
    )
    current = BusinessContext(7, "tenant", "USER", "subject", "team")
    access = AsyncMock(return_value=(current, ["managed"]))
    cookie = AsyncMock()
    direct = AsyncMock(return_value=current)
    batched = AsyncMock(return_value=[])
    monkeypatch.setattr(module, "context", access)
    monkeypatch.setattr(module, "ensure_cookie_current", cookie)
    monkeypatch.setattr(module, "require_business_access", direct)
    monkeypatch.setattr(module, "rows", batched)
    monkeypatch.setattr(module, "current_auth_snapshot", lambda: state.native)
    monkeypatch.setattr(module, "current_cookie_identity", lambda: state.cookie)
    return SimpleNamespace(
        state=state,
        session=session,
        current=current,
        access=access,
        cookie=cookie,
        direct=direct,
        batched=batched,
        model=module.IdentityPublicationSummary(),
    )


async def issued(b):
    current, managed, ticket = await b.model.authorize_list(b.session, 7)
    assert current is b.current and managed == ["managed"]
    return ticket


@pytest.mark.asyncio
async def test_single_use_keeps_cookie_current_and_source_before_clock(boundary):
    b = boundary
    ticket = await issued(b)
    events = []
    b.cookie.side_effect = lambda *args: events.append("cookie")

    async def source(*args, **kwargs):
        events.append("source")
        assert "orbit_account_clock" not in args[1]
        return []

    b.batched.side_effect = source
    result = await b.model.prepare_for_list(b.session, 7, [], ticket)
    assert result.current is b.current
    assert result.transaction is b.state.tx
    assert events == ["cookie", "source"]
    b.access.assert_awaited_once_with(b.session, 7, "accounts.read")
    b.direct.assert_not_awaited()
    with pytest.raises(OrbitError):
        await b.model.prepare_for_list(b.session, 7, [], ticket)
    assert b.cookie.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "context",
        "fake",
        "copy",
        "other_instance",
        "actor",
        "session",
        "transaction",
        "nested",
        "native",
        "cookie",
        "ended",
    ],
)
async def test_wrong_or_stale_ticket_fails_closed_before_sources(boundary, kind):
    b = boundary
    ticket = await issued(b)
    model, session, actor = b.model, b.session, 7
    if kind == "context":
        ticket = b.current
    elif kind == "fake":
        ticket = SimpleNamespace(
            **{
                field: getattr(ticket, field)
                for field in ticket.__slots__
                if field != "__weakref__"
            }
        )
    elif kind == "copy":
        ticket = copy.copy(ticket)
    elif kind == "other_instance":
        model = module.IdentityPublicationSummary()
    elif kind == "actor":
        actor = 8
    elif kind == "session":
        session = SimpleNamespace(sync_session=b.session.sync_session)
    elif kind == "transaction":
        b.state.tx = object()
    elif kind == "nested":
        b.state.nested = object()
    elif kind == "native":
        b.state.native = object()
    elif kind == "cookie":
        b.state.cookie = object()
    else:
        b.state.tx = None
    with pytest.raises((OrbitError, ValueError)):
        await model.prepare_for_list(session, actor, [], ticket)
    b.direct.assert_not_awaited()
    b.cookie.assert_not_awaited()
    b.batched.assert_not_awaited()


@pytest.mark.asyncio
async def test_cookie_expiry_consumes_ticket_and_never_locks_source(boundary):
    b = boundary
    ticket = await issued(b)
    b.cookie.side_effect = OrbitError(401, "SESSION_REAUTH_REQUIRED", "会话已过期")
    with pytest.raises(OrbitError) as caught:
        await b.model.prepare_for_list(b.session, 7, [], ticket)
    assert caught.value.status == 401
    b.batched.assert_not_awaited()
    with pytest.raises(OrbitError):
        await b.model.prepare_for_list(b.session, 7, [], ticket)
    assert b.cookie.await_count == 1


@pytest.mark.asyncio
async def test_nested_issuance_refused_and_abandoned_weak_ticket_is_collected(boundary):
    b = boundary
    b.state.nested = object()
    with pytest.raises(OrbitError):
        await b.model.authorize_list(b.session, 7)
    b.access.assert_not_awaited()
    b.state.nested = None
    ticket = await issued(b)
    reference = weakref.ref(ticket)
    assert len(b.model._list_authorizations) == 1
    del ticket
    gc.collect()
    assert reference() is None
    assert len(b.model._list_authorizations) == 0


@pytest.mark.asyncio
async def test_ordinary_prepare_still_authorizes_and_sync_does_not_accept_list_ticket(boundary):
    b = boundary
    await b.model.prepare(b.session, 7, [])
    b.direct.assert_awaited_once_with(b.session, 7, "accounts", "accounts.read")
    b.cookie.assert_not_awaited()
    ticket = await issued(b)
    with pytest.raises(OrbitError):
        await b.model._prepare(b.session, 7, [], "accounts.sync", _list_authorization=ticket)
    assert b.direct.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["tx", "nested", "native", "cookie"])
async def test_cookie_await_cannot_switch_transaction_or_auth_context_before_sources(
    boundary, change
):
    b = boundary
    ticket = await issued(b)

    async def changed(*args):
        setattr(b.state, change, object())

    b.cookie.side_effect = changed
    with pytest.raises(OrbitError):
        await b.model.prepare_for_list(b.session, 7, [], ticket)
    b.batched.assert_not_awaited()
    b.direct.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("current", BusinessContext(7, "other-tenant", "SUPER_ADMIN", "subject", "team")),
        ("session", object()),
        ("transaction", object()),
        ("actor", 8),
        ("actor", True),
        ("permission", "accounts.sync"),
        ("managed", ("foreign-team",)),
        ("native_identity", object()),
        ("cookie_identity", object()),
    ],
)
async def test_forced_ticket_mutation_is_rejected_before_cookie_and_sources(boundary, field, value):
    b = boundary
    ticket = await issued(b)
    object.__setattr__(ticket, field, value)
    with pytest.raises(OrbitError):
        await b.model.prepare_for_list(b.session, 7, [], ticket)
    b.cookie.assert_not_awaited()
    b.batched.assert_not_awaited()
    b.direct.assert_not_awaited()
    assert len(b.model._list_authorizations) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("actor_id", 8),
        ("tenant_id", "foreign"),
        ("data_role", "SUPER_ADMIN"),
        ("subject_id", "foreign"),
        ("team_id", "foreign"),
    ],
)
async def test_forced_original_context_primitive_mutation_cannot_change_registered_expectation(
    boundary, field, value
):
    b = boundary
    ticket = await issued(b)
    object.__setattr__(ticket.current, field, value)
    with pytest.raises(OrbitError):
        await b.model.prepare_for_list(b.session, 7, [], ticket)
    b.cookie.assert_not_awaited()
    b.batched.assert_not_awaited()
    b.direct.assert_not_awaited()
