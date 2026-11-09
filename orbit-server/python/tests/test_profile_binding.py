"""Profile关联原字段、未知证明、当前范围与成功重放边界。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from orbit_api.errors import OrbitError


def U(n):
    return str(UUID(int=n))


def body():
    return {
        "account_id": U(1),
        "agent_id": U(2),
        "profile_external_id": "profile-甲",
        "ownership": {"owner_user_id": U(3), "owner_team_id": U(4)},
    }


def test_original_write_fields():
    from orbit_api.profile_binding_contract import parse_write

    assert parse_write(json.dumps(body()).encode()) == body()


@pytest.mark.parametrize(
    "change",
    [
        {"identity_state": "VALID"},
        {"verified_at": "2026-11-09T00:00:00Z"},
        {"profile_external_id": ""},
        {"profile_external_id": "x" * 129},
        {"profile_external_id": "x\n"},
        {"account_id": True},
        {"account_id": "x"},
    ],
)
def test_untrusted_or_invalid_binding_fields_rejected(change):
    from orbit_api.profile_binding_contract import parse_write

    with pytest.raises(OrbitError):
        parse_write(json.dumps(body() | change).encode())


def test_unbind_requires_exact_reason():
    from orbit_api.profile_binding_contract import parse_unbind

    assert parse_unbind(b'{"reason":"confirmed"}') == {"reason": "confirmed"}
    for raw in (b"{}", b'{"reason":""}', b'{"reason":"x","state":"VALID"}'):
        with pytest.raises(OrbitError):
            parse_unbind(raw)


def test_public_binding_never_invents_validation():
    from orbit_api.profile_binding_store import public_binding

    row = body() | {
        "id": U(5),
        "revision": 1,
        "owner_user_id": U(3),
        "owner_team_id": U(4),
        "identity_state": "UNKNOWN",
        "verified_at": None,
    }
    row.pop("ownership")
    assert public_binding(row) == body() | {
        "id": U(5),
        "revision": 1,
        "identity_state": "UNKNOWN",
        "verified_at": None,
    }


@pytest.mark.asyncio
async def test_write_replay_precedes_rechecking_unbound_object(monkeypatch):
    from orbit_api import profile_binding_store as module

    current = SimpleNamespace(tenant_id=U(9), actor_id=1)
    monkeypatch.setattr(module.access, "context", AsyncMock(return_value=current))
    monkeypatch.setattr(module.access, "clock", AsyncMock(return_value=4))
    monkeypatch.setattr(module, "verify_csrf", lambda *args: None)
    receipt = {"id": U(5), "revision": 2, "unbound_at": "2026-11-09T00:00:00.000000Z"}
    replay = AsyncMock(return_value=receipt)
    monkeypatch.setattr(module.access, "replay", replay)
    store = module.ProfileBindingStore(None)
    monkeypatch.setattr(
        store, "row", AsyncMock(side_effect=AssertionError("replay must not read unbound"))
    )
    result = await store.unbind(
        None, 1, "auth", "csrf", "key", U(5), 1, {"reason": "confirmed"}, U(10)
    )
    assert result == receipt
    module.access.context.assert_awaited_once_with(None, 1, "environments.enroll", write=True)


def test_superadmin_can_repair_stale_or_revoked_agent_binding():
    from orbit_api.profile_binding_access import visible

    value = visible(SimpleNamespace(data_role="SUPER_ADMIN"))
    assert value == "b.unbound_at IS NULL"


def test_other_users_need_current_matching_account_and_live_agent():
    from orbit_api.profile_binding_access import visible

    value = visible(SimpleNamespace(data_role="USER"))
    assert "b.owner_user_id=a.owner_user_id" in value
    assert "b.owner_team_id=a.owner_team_id" in value
    assert "g.state<>'REVOKED'" in value
    assert "a.owner_user_id=:subject" in value


@pytest.mark.asyncio
async def test_revoked_target_agent_rejected_before_write(monkeypatch):
    from orbit_api import profile_binding_store as module

    current = SimpleNamespace(tenant_id=U(9), actor_id=1, subject_id=U(3))
    monkeypatch.setattr(module.access, "context", AsyncMock(return_value=current))
    monkeypatch.setattr(module.access, "clock", AsyncMock(return_value=4))
    monkeypatch.setattr(module.access, "replay", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "verify_csrf", lambda *args: None)
    monkeypatch.setattr(
        module, "query_rows", AsyncMock(return_value=[{"id": U(2), "state": "REVOKED"}])
    )
    store = module.ProfileBindingStore(None)
    monkeypatch.setattr(
        store, "account", AsyncMock(return_value={"owner_user_id": U(3), "owner_team_id": U(4)})
    )
    with pytest.raises(OrbitError) as caught:
        await store.save(None, 1, "auth", "csrf", "key", body(), None, 0, U(10))
    assert (caught.value.status, caught.value.code) == (409, "AGENT_REVOKED")


def test_team_scope_manager_subquery_is_current_locking_read():
    from orbit_api.profile_binding_access import visible

    clause = visible(SimpleNamespace(data_role="TEAM_ADMIN"))
    assert "manager_user_id=:actor AND tm.enabled=1 FOR SHARE)" in clause
    assert "a.owner_user_id=:subject" in clause
    assert "b.owner_user_id=a.owner_user_id" in clause
    assert "b.owner_team_id=a.owner_team_id" in clause
    assert "g.state<>'REVOKED'" in clause
    # 普通用户不获团队管理分支，超管仍可读取失配归属便于修复。
    assert "orbit_business_team_manager" not in visible(SimpleNamespace(data_role="USER"))
    assert visible(SimpleNamespace(data_role="SUPER_ADMIN")) == "b.unbound_at IS NULL"
