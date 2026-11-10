"""采集设置精确合同和状态脱敏；不把页面开关当进程已启动。"""

import importlib
import importlib.util
import json
from datetime import datetime
from uuid import uuid4

import pytest


def api():
    assert importlib.util.find_spec("orbit_api.meta_sync_store") is not None
    return importlib.import_module("orbit_api.meta_sync_store")


def value():
    return {
        "profile_id": str(uuid4()),
        "adapter_version": "verified-v1",
        "scheduler_enabled": False,
        "revision": 0,
    }


def test_policy_first_save_has_explicit_profile_and_disabled_default():
    v = value()
    assert api().parse_policy(json.dumps(v).encode()) == v
    assert api().public_policy(None) == {
        "profile_id": None,
        "adapter_version": None,
        "scheduler_enabled": False,
        "revision": 0,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"revision": True},
        {"revision": -1},
        {"revision": 2**53},
        {"scheduler_enabled": "false"},
        {"profile_id": None},
        {"adapter_version": ""},
        {"unknown": "field"},
    ],
)
def test_policy_rejects_invalid_fields(change):
    from orbit_api.errors import OrbitError

    with pytest.raises(OrbitError):
        api().parse_policy(json.dumps(value() | change).encode())


def test_status_unknown_error_does_not_expose_checkpoint_or_token():
    row = dict(
        job_id=str(uuid4()),
        state="FAILED",
        updated_at=datetime(2026, 11, 10),
        checkpoint_json={"last_error": "private-token", "after": "private-cursor"},
        attempts=3,
        next_run_at=datetime(2026, 11, 10),
        page_number=2,
        date_from=datetime(2026, 11, 1).date(),
        date_to=datetime(2026, 11, 9).date(),
        profile_id=str(uuid4()),
        profile_version="v1",
        adapter_version="v1",
    )
    result = api().public_job(row)
    assert result["last_error"] == "META_COLLECTION_UNVERIFIED"
    assert "private" not in json.dumps(result)
    assert result["state"] == "FAILED" and result["page_number"] == 2


def test_status_no_job_remains_unknown():
    assert api().public_job({"job_id": None}) is None


@pytest.mark.asyncio
async def test_policy_replay_and_conflict_do_not_revalidate_or_write(monkeypatch):
    import hashlib
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from orbit_api.errors import OrbitError

    mod = api()
    v = value()
    result = v | {"revision": 1}
    receipt = {
        "input_hash": hashlib.sha256(
            mod.canonical({"operation": "META_SYNC_POLICY", "value": v}).encode()
        ).hexdigest(),
        "result_json": result,
    }
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: receipt))
        )
    )
    monkeypatch.setattr(mod, "lock_account_clock", AsyncMock())
    validate = AsyncMock()
    monkeypatch.setattr(mod, "resolve_policy_profile", validate)
    current = SimpleNamespace(tenant_id="tenant", actor_id="actor")
    assert await mod.save_policy(session, current, v, "key", "request") == result
    with pytest.raises(OrbitError) as exc:
        await mod.save_policy(session, current, v | {"scheduler_enabled": True}, "key", "request")
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    validate.assert_not_awaited()
    assert session.execute.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["create", "enable", "disable", "stale"])
async def test_policy_cas_and_disabled_expired_profile(monkeypatch, mode):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from orbit_api.errors import OrbitError

    mod = api()
    v = value() | {"revision": 0 if mode == "create" else 2, "scheduler_enabled": mode == "enable"}
    old = (
        None
        if mode == "create"
        else v | {"scheduler_enabled": True, "revision": 3 if mode == "stale" else 2}
    )
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: None))
        )
    )
    monkeypatch.setattr(mod, "lock_account_clock", AsyncMock())
    monkeypatch.setattr(mod, "read_policy", AsyncMock(return_value=old))
    validate, audit = AsyncMock(), AsyncMock()
    monkeypatch.setattr(mod, "resolve_policy_profile", validate)
    monkeypatch.setattr(mod, "event", audit)
    current = SimpleNamespace(tenant_id="tenant", actor_id="actor")
    if mode == "stale":
        with pytest.raises(OrbitError) as exc:
            await mod.save_policy(session, current, v, "key", "request")
        assert exc.value.code == "REVISION_CONFLICT"
        validate.assert_not_awaited()
        audit.assert_not_awaited()
        assert session.execute.await_count == 1
    else:
        assert (await mod.save_policy(session, current, v, "key", "request"))["revision"] == v[
            "revision"
        ] + 1
        assert validate.await_count == (0 if mode == "disable" else 1)
        assert audit.await_count == 1
        statements = [str(call.args[0]) for call in session.execute.await_args_list]
        assert any("orbit_meta_request_receipt" in s and "INSERT" in s for s in statements)
        assert any(
            "orbit_meta_sync_policy" in s and ("INSERT" in s or "UPDATE" in s) for s in statements
        )


@pytest.mark.asyncio
async def test_policy_resolver_uses_same_connection_current_revision(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    mod = api()
    row = {"source_connection_id": "original-connection", "revision": 9}
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))
        )
    )
    resolved = AsyncMock(return_value={"profile": "verified"})
    monkeypatch.setattr(mod, "resolved_profile", resolved)
    assert await mod.resolve_policy_profile(session, "tenant", "profile", "adapter") == {
        "profile": "verified"
    }
    resolved.assert_awaited_once_with(
        session, "tenant", "profile", "adapter", "original-connection", 9
    )


@pytest.mark.asyncio
async def test_policy_choices_filter_unavailable_current_source(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from orbit_api.errors import OrbitError

    mod = api()
    rows = [
        {"profile_id": "old", "profile_version": "v1", "adapter_version": "a"},
        {"profile_id": "current", "profile_version": "v1", "adapter_version": "a"},
    ]
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
        )
    )
    monkeypatch.setattr(
        mod,
        "resolve_policy_profile",
        AsyncMock(
            side_effect=[OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "unavailable"), {}]
        ),
    )
    assert await mod.policy_choices(session, SimpleNamespace(tenant_id="tenant")) == rows[1:]


def test_connection_policy_profile_cannot_use_another_connection(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from orbit_api.errors import OrbitError

    module = api()
    result = SimpleNamespace(
        mappings=lambda: SimpleNamespace(
            first=lambda: {"source_connection_id": str(uuid4()), "revision": 3}
        )
    )
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    with pytest.raises(OrbitError):
        asyncio.run(
            module.resolve_policy_profile(
                session, str(uuid4()), str(uuid4()), "v1", connection_id=str(uuid4())
            )
        )


@pytest.mark.parametrize(
    "role,owner,allowed", [("USER", 1, True), ("USER", 2, False), ("SUPER_ADMIN", 2, True)]
)
def test_connection_policy_visibility_matches_connection_owner(role, owner, allowed):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from orbit_api.errors import OrbitError

    identifier = str(uuid4())
    result = SimpleNamespace(
        mappings=lambda: SimpleNamespace(first=lambda: {"id": identifier, "actor_id": owner})
    )
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    current = SimpleNamespace(tenant_id=str(uuid4()), actor_id=1, data_role=role)
    call = api().policy_connection(session, current, identifier)
    if allowed:
        assert asyncio.run(call)["id"] == identifier
    else:
        with pytest.raises(OrbitError) as error:
            asyncio.run(call)
        assert error.value.status == 404
    assert session.execute.call_args.args[1]["tenant"] == current.tenant_id
