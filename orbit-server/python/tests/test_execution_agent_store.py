"""设备登记事务编排回归；真实SQL/HTTP由主线独立验收。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from orbit_api.errors import OrbitError


def current():
    return SimpleNamespace(actor_id=1, tenant_id="t", subject_id="u", data_role="SUPER_ADMIN")


async def setup(monkeypatch, state="OFFLINE", revision=1):
    from orbit_api import execution_agent_store as module

    for name, result in [
        ("context", current()),
        ("clock", 1),
        ("replay", None),
        ("remember", None),
        ("event", None),
    ]:
        monkeypatch.setattr(module.access, name, AsyncMock(return_value=result))
    monkeypatch.setattr(module.access, "verify_csrf", lambda *args: None)
    store = module.ExecutionAgentStore(None)
    row = {
        "id": "00000000-0000-0000-0000-000000000001",
        "revision": revision,
        "state": state,
        "last_heartbeat": None,
        "name": "Mac",
        "endpoint": "http://127.0.0.1:50325",
        "probe_interval": 15,
    }
    store.row = AsyncMock(return_value=row)
    return module, store, row


async def test_new_registry_insert_is_offline_without_heartbeat(monkeypatch):
    module, store, row = await setup(monkeypatch)
    session = SimpleNamespace(execute=AsyncMock())
    result = await store.save(
        session,
        1,
        "auth",
        "csrf",
        "key",
        {k: row[k] for k in ("name", "endpoint", "probe_interval")},
        None,
        0,
        "request",
    )
    assert result["state"] == "OFFLINE" and result["last_heartbeat"] is None
    sql = str(session.execute.await_args_list[0].args[0])
    assert "INSERT INTO orbit_execution_agent" in sql and "'OFFLINE',NULL" in sql
    module.access.event.assert_awaited_once()
    module.access.remember.assert_awaited_once()


@pytest.mark.parametrize(
    "state,revision,expected,code",
    [("REVOKED", 1, 1, "AGENT_REVOKED"), ("OFFLINE", 2, 1, "REVISION_CONFLICT")],
)
async def test_revoked_or_stale_agent_never_updates(monkeypatch, state, revision, expected, code):
    module, store, row = await setup(monkeypatch, state, revision)
    session = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(OrbitError) as caught:
        await store.save(
            session,
            1,
            "auth",
            "csrf",
            "key",
            {k: row[k] for k in ("name", "endpoint", "probe_interval")},
            row["id"],
            expected,
            "request",
        )
    assert caught.value.code == code
    session.execute.assert_not_awaited()
    module.access.event.assert_not_awaited()


async def test_unimplemented_profile_read_returns_503_after_object_authorization(monkeypatch):
    _, store, row = await setup(monkeypatch)
    with pytest.raises(OrbitError) as caught:
        await store.unavailable(object(), 1, row["id"], "profiles")
    assert caught.value.status == 503
    store.row.assert_awaited_once()


@pytest.mark.parametrize(
    "operation,permission,write",
    [
        ("READ", "environments.read", False),
        ("ENROLL", "environments.enroll", True),
        ("REVOKE", "environments.revoke", True),
        ("PROBE", "environments.probe", True),
    ],
)
async def test_capabilities_only_checks_requested_action(monkeypatch, operation, permission, write):
    module, store, _ = await setup(monkeypatch)
    store.tokens = SimpleNamespace(
        session_binding=lambda *args: "binding", issue=lambda *args: "csrf"
    )
    session = object()
    result = await store.capabilities(session, 1, "auth", operation)
    module.access.context.assert_awaited_once_with(session, 1, permission, write=write)
    assert set(result) == {"actor_id", "tenant_id", "data_role", "csrf_token"}
    assert result["csrf_token"] == ("csrf" if write else None)


@pytest.mark.parametrize(
    "field,value", [("channel_id", "x"), ("metric_profile_id", "x"), ("entity_type", "AD")]
)
async def test_missing_association_filter_fails_after_read_authorization(monkeypatch, field, value):
    module, store, _ = await setup(monkeypatch)
    with pytest.raises(OrbitError) as caught:
        await store.list(object(), 1, {"page_size": 50, "q": "", field: value})
    assert caught.value.status == 503
    assert caught.value.pointer == "/" + field
    module.access.context.assert_awaited_once()
    module.access.clock.assert_not_awaited()


async def test_successful_idempotency_key_never_updates_or_resends_revoke(monkeypatch):
    module, store, row = await setup(monkeypatch)
    original = dict(row) | {"state": "REVOKED", "revision": 2}
    module.access.replay.return_value = original
    session = SimpleNamespace(execute=AsyncMock())
    result = await store.save(
        session,
        1,
        "auth",
        "csrf",
        "key",
        {"reason": "stop"},
        row["id"],
        1,
        "request",
        mode="revoke",
    )
    assert result == original
    session.execute.assert_not_awaited()
    module.access.event.assert_not_awaited()
