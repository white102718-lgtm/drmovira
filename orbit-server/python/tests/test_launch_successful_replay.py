"""成功草稿重放只复核当前读权限/范围，不能用新来源或新CAS重做已成功命令。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from orbit_api import launch_access as access
from orbit_api import launch_store as plans
from orbit_api.authorization import BusinessContext
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError

CURRENT = BusinessContext(1, "tenant", "USER", "owner", "team")
RESULT = {"id": "original-plan", "revision": 1, "state": "DRAFT"}


class Session:
    def __init__(self, row):
        self.row = row
        self.sql = []

    async def execute(self, statement, values):
        self.sql.append((str(statement), values))
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: self.row))


@pytest.mark.asyncio
async def test_successful_result_precedes_changed_source_state_and_new_write_authority(monkeypatch):
    successful = AsyncMock(return_value=(CURRENT, RESULT))
    monkeypatch.setattr(access, "successful_replay", successful)
    mutation = AsyncMock(side_effect=AssertionError("成功重放不能重新要求写权限"))
    monkeypatch.setattr(access, "context", mutation)
    sources = AsyncMock(side_effect=AssertionError("成功重放不能重绑最新指标来源"))
    monkeypatch.setattr(plans, "validate_sources", sources)
    csrf = Mock()
    monkeypatch.setattr(plans, "verify_csrf", csrf)
    store = plans.LaunchStore(None)
    store.row = AsyncMock(return_value={"state": "SUBMITTED", "revision": 9})
    assert (
        await store.save(
            object(),
            1,
            "session",
            "csrf",
            "old-key",
            {"old": "intent"},
            "original-plan",
            0,
            "request",
        )
        == RESULT
    )
    mutation.assert_not_awaited()
    sources.assert_not_awaited()
    store.row.assert_awaited_once_with(store.row.await_args.args[0], CURRENT, "original-plan")
    csrf.assert_called_once()
    assert successful.await_args.args[2:5] == ("launch.read", "plan.update", "old-key")


@pytest.mark.asyncio
async def test_successful_result_still_requires_current_object_visibility(monkeypatch):
    monkeypatch.setattr(access, "successful_replay", AsyncMock(return_value=(CURRENT, RESULT)))
    monkeypatch.setattr(plans, "verify_csrf", lambda *args: None)
    store = plans.LaunchStore(None)
    store.row = AsyncMock(side_effect=OrbitError(404, "NOT_FOUND", "当前范围不可见"))
    with pytest.raises(OrbitError, match="当前范围不可见"):
        await store.save(object(), 1, "session", "csrf", "old-key", {}, None, None, "request")


@pytest.mark.asyncio
async def test_probe_miss_adds_no_business_authorization_or_gap_write_lock(monkeypatch):
    authorize = AsyncMock(side_effect=AssertionError("未命中不在探测中授权"))
    monkeypatch.setattr(access, "context", authorize)
    session = Session(None)
    assert (
        await access.successful_replay(session, 1, "launch.read", "plan.create", "key", "hash")
        is None
    )
    assert len(session.sql) == 1 and "FOR UPDATE" not in session.sql[0][0]
    assert session.sql[0][1]["key"] != "key"
    authorize.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["revoked", "tenant", "payload"])
async def test_probe_cannot_disclose_response_after_revocation_or_conflict(monkeypatch, failure):
    row = {
        "tenant_id": "other" if failure == "tenant" else "tenant",
        "input_hash": "hash",
        "result_json": canonical(RESULT),
    }
    authorize = AsyncMock(return_value=CURRENT)
    if failure == "revoked":
        authorize.side_effect = OrbitError(403, "PERMISSION_DENIED", "权限已撤回")
    monkeypatch.setattr(access, "context", authorize)
    with pytest.raises(OrbitError) as info:
        await access.successful_replay(
            Session(row),
            1,
            "launch.read",
            "plan.create",
            "key",
            "different" if failure == "payload" else "hash",
        )
    assert info.value.status == (409 if failure == "payload" else 403)
    authorize.assert_awaited_once()


@pytest.mark.asyncio
async def test_probe_returns_original_snapshot_after_current_read_authorization(monkeypatch):
    authorize = AsyncMock(return_value=CURRENT)
    monkeypatch.setattr(access, "context", authorize)
    session = Session(
        {"tenant_id": "tenant", "input_hash": "hash", "result_json": canonical(RESULT)}
    )
    assert await access.successful_replay(
        session, 1, "launch.read", "plan.create", "key", "hash"
    ) == (CURRENT, RESULT)
    authorize.assert_awaited_once_with(session, 1, "launch.read")


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_validated_edit_reads_real_config_source_instead_of_status_head(monkeypatch, changed):
    """仅Store接力协议纯测；真实身份来源未接，不冒充HTTP预检后编辑验收。"""
    from datetime import datetime

    value = {
        "name": "原配置",
        "campaigns": [],
        "account_ids": [],
        "ownership": {"owner_user_id": "owner", "owner_team_id": "team"},
    }
    previous = {
        "id": "plan",
        "revision": 2,
        "state": "VALIDATED",
        "payload_json": canonical(value),
        "created_at": datetime(2026, 11, 8),
        "updated_at": datetime(2026, 11, 8),
    }
    monkeypatch.setattr(access, "successful_replay", AsyncMock(return_value=None))
    monkeypatch.setattr(access, "context", AsyncMock(return_value=CURRENT))
    monkeypatch.setattr(access, "clock", AsyncMock())
    monkeypatch.setattr(access, "replay", AsyncMock(return_value=None))
    monkeypatch.setattr(access, "remember", AsyncMock())
    monkeypatch.setattr(plans, "verify_csrf", lambda *args: None)
    monkeypatch.setattr(plans, "validate_sources", AsyncMock(return_value={}))
    capture = AsyncMock(return_value=SimpleNamespace(source_revision=1))
    monkeypatch.setattr("orbit_api.launch_plan_source.capture_plan_source", capture)
    sql_calls = []

    async def execute(statement, params):
        sql_calls.append((str(statement), params))
        return SimpleNamespace(scalar_one=lambda: "{}")

    session = SimpleNamespace(execute=execute)
    store = plans.LaunchStore(None)
    store.row = AsyncMock(return_value=previous)
    store.persist = AsyncMock(return_value={"id": "plan", "revision": 3, "state": "DRAFT"})
    command = value | {"name": "修改后"} if changed else value
    result = await store.save(
        session, 1, "session", "csrf", "new-key", command, "plan", 2, "request"
    )
    capture.assert_awaited_once_with(session, CURRENT, previous)
    assert sql_calls[0][1]["revision"] == 1
    if changed:
        assert result["revision"] == 3 and result["state"] == "DRAFT"
        store.persist.assert_awaited_once()
    else:
        assert result["revision"] == 2 and result["state"] == "VALIDATED"
        store.persist.assert_not_awaited()
