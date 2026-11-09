"""设备管理权限与当前账户关联范围，替身不替代MySQL验收。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from orbit_api.errors import OrbitError


@pytest.mark.parametrize("role", ["USER", "TEAM_ADMIN"])
async def test_exact_permission_cannot_grant_non_superadmin_device_management(monkeypatch, role):
    from orbit_api import execution_agent_access as access

    monkeypatch.setattr(
        access, "require_business_access", AsyncMock(return_value=SimpleNamespace(data_role=role))
    )
    with pytest.raises(OrbitError) as error:
        await access.context(object(), 1, "environments.enroll", write=True)
    assert error.value.status == 403


async def test_clock_locks_current_accounts_before_registry(monkeypatch):
    from orbit_api import execution_agent_access as access

    events = []

    async def account_clock(*args):
        events.append("account")
        return 7

    async def execute(*args):
        events.append("environment")
        return SimpleNamespace(scalar_one_or_none=lambda: 9)

    monkeypatch.setattr(access.account_access, "clock", account_clock)
    current = SimpleNamespace(tenant_id="t", actor_id=1, subject_id="u")
    assert await access.clock(SimpleNamespace(execute=execute), current, write=True) == 9
    assert events == ["account", "environment"]


def test_read_visibility_joins_current_bound_account_and_never_uses_creator_scope():
    from orbit_api.execution_agent_access import visibility_clause

    current = SimpleNamespace(data_role="USER")
    sql = visibility_clause(current)
    for fragment in (
        "orbit_profile_binding",
        "orbit_ad_account",
        "unbound_at IS NULL",
        "owner_user_id",
        "owner_team_id",
    ):
        assert fragment in sql
    assert "created_by" not in sql
    assert visibility_clause(SimpleNamespace(data_role="SUPER_ADMIN")) == "1=1"
