"""事件协议纯测；SQL/真实会话/SSE网络由主线独立专项验证。"""

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from orbit_api.errors import OrbitError
from orbit_api.task_event_contract import StreamQuota, cursor_id, event_frame, revoked_frame
from orbit_api.task_event_publisher import publish_fixture_running
from orbit_api.task_event_store import TaskEventStore
from orbit_api.task_event_stream import EventResponse

TASK, TENANT, EVENT = (str(UUID(int=i)) for i in (1, 2, 3))


class Tokens:
    def __init__(self):
        self.claims = None

    def issue(self, purpose, claims, ttl):
        assert purpose == "TASK_EVENT_CHECKPOINT_V1" and ttl == 60
        self.claims = claims
        return "pure-checkpoint"

    def verify(self, purpose, token):
        assert purpose == "TASK_EVENT_CHECKPOINT_V1" and token == "pure-checkpoint"
        return self.claims


def checkpoint():
    tokens = Tokens()
    store = TaskEventStore(tokens)
    row = {
        "tenant_id": TENANT,
        "id": TASK,
        "revision": 5,
        "latest_sequence": 8,
        "latest_event_id": EVENT,
    }
    store.checkpoint(row, "fingerprint")
    return store, tokens, row


def test_checkpoint_old_snapshot_accepts_current_updates_without_retry_starvation():
    store, tokens, row = checkpoint()
    assert (
        store.checkpoint_sequence(
            "pure-checkpoint",
            SimpleNamespace(tenant_id=TENANT),
            row | {"revision": 9, "latest_sequence": 12},
            "fingerprint",
            EVENT,
        )
        == 8
    )
    assert tokens.claims["revision"] == 5


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant", TASK),
        ("task", TENANT),
        ("fingerprint", "changed"),
        ("event", TASK),
        ("revision", 6),
        ("revision", True),
        ("sequence", 9),
        ("sequence", 0),
        ("sequence", True),
    ],
)
def test_checkpoint_rejects_foreign_or_forged_bounds(field, value):
    store, tokens, row = checkpoint()
    tokens.claims[field] = value
    with pytest.raises(OrbitError) as failure:
        store.checkpoint_sequence(
            "pure-checkpoint", SimpleNamespace(tenant_id=TENANT), row, "fingerprint", EVENT
        )
    assert (failure.value.status, failure.value.code) == (400, "EVENT_CURSOR_INVALID")


def test_task_event_strict_frame_and_observer_has_no_global_event_id():
    row = {
        "event_id": EVENT,
        "sequence": 2,
        "schema_version": 1,
        "task_id": TASK,
        "task_revision": 2,
        "node_id": None,
        "state": "RUNNING",
        "request_id": TENANT,
        "occurred_at": datetime(2026, 1, 1),
    }
    frame = event_frame(row).decode()
    payload = json.loads(frame.split("data: ", 1)[1])
    assert set(payload) == set(row)
    assert payload["occurred_at"] == "2026-01-01T00:00:00.000Z"
    assert frame.startswith("id: " + EVENT + "\n")
    assert revoked_frame() == b'event: SCOPE_REVOKED\ndata: {"code":"SCOPE_REVOKED"}\n\n'


@pytest.mark.parametrize("value", ["bad", "", "a\nb", "0" * 4096])
def test_bad_event_uuid_is_original_controlled_400(value):
    with pytest.raises(OrbitError) as failure:
        cursor_id(value)
    assert (failure.value.status, failure.value.code) == (400, "EVENT_CURSOR_INVALID")


def test_quota_limits_and_release_do_not_grow_unbounded():
    quota = StreamQuota(total=2, per_actor=1)
    quota.acquire(1)
    with pytest.raises(OrbitError) as failure:
        quota.acquire(1)
    assert failure.value.status == 429
    quota.acquire(2)
    with pytest.raises(OrbitError):
        quota.acquire(3)
    quota.release(1)
    quota.acquire(3)
    quota.release(1)
    assert quota.active == {2: 1, 3: 1}


@pytest.mark.asyncio
async def test_production_publisher_fails_before_any_sql_or_platform_call():
    with pytest.raises(OrbitError) as failure:
        await publish_fixture_running(object(), 1, TASK, TASK, EVENT)
    assert (failure.value.status, failure.value.code) == (
        503,
        "TASK_AUTHORITY_PROVIDER_UNAVAILABLE",
    )


@pytest.mark.asyncio
async def test_slow_send_is_cancelled_as_soon_as_live_guard_revokes(monkeypatch):
    import orbit_api.task_event_stream as module

    monkeypatch.setattr(module, "POLL_SECONDS", 0.001)
    checks, cancelled = 0, asyncio.Event()

    async def guard(after):
        nonlocal checks
        checks += 1
        if checks == 2:
            raise OrbitError(403, "PERMISSION_DENIED", "受控撤权")

    async def blocked_send(message):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    response = EventResponse(actor=1, after=1, read_batch=None, guard=guard, quota=StreamQuota())
    with pytest.raises(OrbitError):
        await asyncio.wait_for(response.checked_send(blocked_send, b"not delivered"), 0.2)
    assert cancelled.is_set() and checks == 2


@pytest.mark.asyncio
async def test_each_frame_reauthorizes_and_revocation_stops_rest_of_batch():
    quota, messages = StreamQuota(), []
    quota.acquire(1)
    row = {
        "event_id": EVENT,
        "sequence": 1,
        "schema_version": 1,
        "task_id": TASK,
        "task_revision": 1,
        "node_id": None,
        "state": "QUEUED",
        "request_id": TENANT,
        "occurred_at": datetime(2026, 1, 1),
    }

    async def read(after):
        return [row, row | {"sequence": 2}]

    async def guard(after):
        if after == 1:
            raise OrbitError(403, "PERMISSION_DENIED", "受控撤权")

    async def send(message):
        messages.append(message)

    async def receive():
        await asyncio.Event().wait()

    await EventResponse(actor=1, after=0, read_batch=read, guard=guard, quota=quota)(
        {}, receive, send
    )
    assert sum(b"id: " in item.get("body", b"") for item in messages) == 1
    assert sum(item.get("body") == revoked_frame() for item in messages) == 1
    assert quota.active == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 404, 503])
async def test_idle_failed_authorization_does_not_send_old_task_data(status):
    quota, messages = StreamQuota(), []
    quota.acquire(1)

    async def read(after):
        raise OrbitError(status, "CONTROLLED_FAILURE", "受控异常")

    async def send(message):
        messages.append(message)

    async def receive():
        await asyncio.Event().wait()

    await EventResponse(actor=1, after=1, read_batch=read, guard=None, quota=quota)(
        {}, receive, send
    )
    bodies = [item.get("body", b"") for item in messages]
    assert sum(body == revoked_frame() for body in bodies) == (status != 503)
    assert not any(b"id: " in body for body in bodies)
    assert quota.active == {}


@pytest.mark.asyncio
async def test_disconnect_cancels_idle_work_and_returns_connection_quota():
    quota, cancelled = StreamQuota(), asyncio.Event()
    quota.acquire(1)

    async def read(after):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def send(message):
        pass

    async def receive():
        await asyncio.sleep(0)
        return {"type": "http.disconnect"}

    await EventResponse(actor=1, after=1, read_batch=read, guard=None, quota=quota)(
        {}, receive, send
    )
    assert cancelled.is_set() and quota.active == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["id", "revision", "latest_event_id"])
async def test_snapshot_header_never_joins_a_different_detail_version(key):
    store, _, row = checkpoint()

    async def context(session, actor, task_id):
        return None, row, "fingerprint"

    store.context = context
    payload = {"id": TASK, "revision": 5, "latest_event_id": EVENT}
    payload[key] = 99 if key == "revision" else TENANT
    with pytest.raises(OrbitError) as failure:
        await store.checkpoint_for_detail(object(), 1, TASK, payload)
    assert (failure.value.status, failure.value.code) == (503, "TASK_SNAPSHOT_UNAVAILABLE")


@pytest.mark.asyncio
async def test_cookie_first_stream_invokes_original_external_resolver_in_explicit_session(
    monkeypatch,
):
    from orbit_api import task_event_session as routes

    session, called = object(), []
    request = SimpleNamespace(headers={"cookie": "controlled-cookie-fixture"})

    async def resolve(actual_request, token, actual_session):
        called.append((actual_request, token, actual_session))
        return SimpleNamespace(user=SimpleNamespace(user_id=7))

    monkeypatch.setattr(routes, "current_cookie_identity", lambda: None)
    login = SimpleNamespace(get_current_user=resolve)
    assert await routes.resolve_actor(session, request, login, ValueError) == 7
    assert called == [(request, None, session)]


@pytest.mark.asyncio
async def test_bearer_stream_uses_non_renewing_session_resolver(monkeypatch):
    from orbit_api import task_event_session as routes

    session, called = object(), []
    request = SimpleNamespace(headers={"authorization": "Bearer pure-fixture"})

    async def resolve(actual_request, token, actual_session):
        called.append((actual_request, token, actual_session))
        return SimpleNamespace(user=SimpleNamespace(user_id=8))

    monkeypatch.setattr(routes, "current_cookie_identity", lambda: None)
    login = SimpleNamespace(get_current_user_for_plugin_session=resolve)
    assert await routes.resolve_actor(session, request, login, ValueError) == 8
    assert called == [(request, "Bearer pure-fixture", session)]
