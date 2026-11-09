"""A025范围消费与原请求幂等边界；真实SQL/HTTP证据另由主线执行。"""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from orbit_api import launch_access as access
from orbit_api import launch_references as refs
from orbit_api import launch_store as plans
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError


def uid(number):
    return str(UUID(int=number))


def current():
    return BusinessContext(1, uid(1), "SUPER_ADMIN", uid(2), uid(3))


DEFAULT_SCOPE = uid(9)


def request(scope=DEFAULT_SCOPE):
    return {
        "name": "范围草稿",
        "ownership": {"owner_user_id": uid(2), "owner_team_id": uid(3)},
        "account_ids": [],
        "account_scope_snapshot_id": scope,
        "asset_ids": [],
        "identity_bindings": [],
        "channel_id": None,
        "allow_repeat": False,
        "activate_after_create": False,
        "execution_mode": "META_API",
        "campaigns": [{"copies": 1, "adsets": [{"copies": 1, "ads": [{"copies": 1}]}]}],
    }


def session_for(count):
    row = {
        "scope_version": 7,
        "members_hash": "a" * 64,
        "auth_fingerprint": "b" * 64,
        "member_count": count,
    }
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: row))
    return SimpleNamespace(execute=AsyncMock(return_value=result))


async def test_scope_consumption_calls_original_resolver_and_keeps_immutable_provenance(
    monkeypatch,
):
    resolve = AsyncMock(return_value=[uid(12), uid(11)])
    monkeypatch.setattr(refs.AccountScopeStore, "resolve_for_plan", resolve)
    value = request()
    session = session_for(2)
    result = await refs.resolve_account_scope(session, current(), value)
    resolve.assert_awaited_once_with(
        session, current(), uid(9), owner_user_id=uid(2), owner_team_id=uid(3)
    )
    assert value["account_ids"] == [uid(11), uid(12)]
    assert value["account_scope_snapshot_id"] is None
    assert result == {
        "scope_id": uid(9),
        "members_hash": "a" * 64,
        "scope_version": 7,
        "auth_fingerprint": "b" * 64,
        "resolved_ids_hash": access.digest([uid(11), uid(12)]),
        "count": 2,
    }


async def test_no_scope_never_adds_accounts_read_or_calls_scope_database(monkeypatch):
    resolve = AsyncMock(side_effect=AssertionError("无范围不应增加权限"))
    monkeypatch.setattr(refs.AccountScopeStore, "resolve_for_plan", resolve)
    value = request(None)
    assert await refs.resolve_account_scope(object(), current(), value) is None
    resolve.assert_not_awaited()


async def test_explicit_ids_and_snapshot_conflict_before_resolving(monkeypatch):
    resolve = AsyncMock()
    monkeypatch.setattr(refs.AccountScopeStore, "resolve_for_plan", resolve)
    value = request() | {"account_ids": [uid(11)]}
    with pytest.raises(OrbitError) as failure:
        await refs.resolve_account_scope(object(), current(), value)
    assert failure.value.status == 422 and failure.value.pointer == "/account_ids"
    resolve.assert_not_awaited()


@pytest.mark.parametrize("status", [403, 404, 409])
async def test_revoked_foreign_and_drifted_snapshot_fail_without_mutation(monkeypatch, status):
    monkeypatch.setattr(
        refs.AccountScopeStore,
        "resolve_for_plan",
        AsyncMock(side_effect=OrbitError(status, "SCOPE_FAILURE", "真实范围失败")),
    )
    value = request()
    before = deepcopy(value)
    with pytest.raises(OrbitError) as failure:
        await refs.resolve_account_scope(object(), current(), value)
    assert failure.value.status == status and value == before


@pytest.mark.parametrize("count", [0, 501])
async def test_out_of_plan_limit_never_silently_truncates_or_mutates(monkeypatch, count):
    monkeypatch.setattr(
        refs.AccountScopeStore,
        "resolve_for_plan",
        AsyncMock(return_value=[uid(i + 10) for i in range(count)]),
    )
    value = request()
    before = deepcopy(value)
    with pytest.raises(OrbitError) as failure:
        await refs.resolve_account_scope(object(), current(), value)
    assert failure.value.code == "PLAN_ACCOUNT_LIMIT" and value == before


async def test_five_hundred_resolved_accounts_expand_before_any_plan_persistence(monkeypatch):
    monkeypatch.setattr(
        refs.AccountScopeStore,
        "resolve_for_plan",
        AsyncMock(return_value=[uid(i + 10) for i in range(500)]),
    )
    value = request()
    value["campaigns"][0]["copies"] = 2
    value["campaigns"][0]["adsets"][0]["copies"] = 3
    value["campaigns"][0]["adsets"][0]["ads"][0]["copies"] = 4
    before = deepcopy(value)
    with pytest.raises(OrbitError) as failure:
        await refs.resolve_account_scope(object(), current(), value)
    assert failure.value.code == "PLAN_NODE_LIMIT" and value == before


async def test_snapshot_metadata_count_mismatch_rejects_whole_consumption(monkeypatch):
    monkeypatch.setattr(
        refs.AccountScopeStore, "resolve_for_plan", AsyncMock(return_value=[uid(11)])
    )
    value = request()
    before = deepcopy(value)
    with pytest.raises(OrbitError) as failure:
        await refs.resolve_account_scope(session_for(2), current(), value)
    assert failure.value.code == "SCOPE_CHANGED" and value == before


async def store_harness(monkeypatch):
    monkeypatch.setattr(plans.access, "context", AsyncMock(return_value=current()))
    monkeypatch.setattr(plans, "verify_csrf", lambda *args: None)
    monkeypatch.setattr(plans.access, "clock", AsyncMock(return_value={}))
    replay = AsyncMock(return_value=None)
    monkeypatch.setattr(plans.access, "replay", replay)
    monkeypatch.setattr(plans.access, "successful_replay", AsyncMock(return_value=None))

    async def sources(session, context, value, **kwargs):
        assert kwargs == {"permission": "launch.create", "isolated_fixture": False}
        value["account_ids"] = [uid(11)]
        value["account_scope_snapshot_id"] = None
        return {
            "accounts": {uid(11): {"revision": 1}},
            "assets": {},
            "channel": None,
            "account_scope_snapshot": {"scope_id": uid(9)},
        }

    monkeypatch.setattr(plans, "validate_sources", sources)
    store = plans.LaunchStore(None)
    store.persist = AsyncMock(return_value={"id": uid(20)})
    return store, replay


async def test_store_does_not_mutate_original_command_across_retry_and_hashes_raw_scope(
    monkeypatch,
):
    store, replay = await store_harness(monkeypatch)
    value = request()
    before = deepcopy(value)
    for _ in range(2):
        await store.save(
            object(), 1, "session", "csrf", "same-original-key", value, None, 0, uid(30)
        )
    assert value == before
    assert [call.args[4] for call in replay.await_args_list] == [
        access.digest([None, 0, before])
    ] * 2
    for call in store.persist.await_args_list:
        assert call.args[2]["account_ids"] == [uid(11)]
        assert call.args[2]["account_scope_snapshot_id"] is None
        assert call.args[2] is not value


async def test_different_snapshots_same_resolved_ids_are_different_original_idempotency_intents(
    monkeypatch,
):
    store, replay = await store_harness(monkeypatch)
    for identifier in (uid(9), uid(10)):
        await store.save(
            object(), 1, "session", "csrf", "same-key", request(identifier), None, 0, uid(30)
        )
    assert replay.await_args_list[0].args[4] != replay.await_args_list[1].args[4]


async def test_resolved_ids_cannot_push_final_configuration_above_original_five_mib(monkeypatch):
    from orbit_api.launch_contract import MAX_CONFIG_BYTES, ensure_config_size

    store, replay = await store_harness(monkeypatch)
    value = request()
    ad = value["campaigns"][0]["adsets"][0]["ads"][0]
    ad["body"] = ""
    size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
    # 直接store边界fixture只验证最终字节保护，原API还会独立检查每个字段长度。
    ad["body"] = "x" * (MAX_CONFIG_BYTES - size)
    ensure_config_size(value)
    with pytest.raises(OrbitError) as failure:
        await store.save(object(), 1, "session", "csrf", "scope-size-key", value, None, 0, uid(30))
    assert failure.value.status == 413
    assert value["account_ids"] == [] and value["account_scope_snapshot_id"] == uid(9)
    store.persist.assert_not_awaited()
    replay.assert_not_awaited()
