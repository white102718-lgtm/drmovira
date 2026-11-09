"""投放拥有者候选只依赖原投放动作，跨身份/筛选游标不能重放。"""

from unittest.mock import AsyncMock

import pytest

from orbit_api import launch_options as options
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError


@pytest.mark.parametrize("create_allowed", [True, False])
async def test_owner_candidates_need_create_or_edit_without_source_menu(
    monkeypatch, create_allowed
):
    current = BusinessContext(1, "tenant", "USER", "subject", "team")
    calls = []

    async def require(session, actor, permission):
        calls.append(permission)
        if not create_allowed and permission == "launch.create":
            raise OrbitError(403, "PERMISSION_DENIED", "动作未授予")
        return current

    monkeypatch.setattr(options.access, "context", require)
    assert await options.ownership_context(object(), 1) is current
    assert calls == (["launch.create"] if create_allowed else ["launch.create", "launch.edit"])


async def test_revoking_both_actions_disallows_candidates_even_with_read(monkeypatch):
    monkeypatch.setattr(
        options.access,
        "context",
        AsyncMock(side_effect=OrbitError(403, "PERMISSION_DENIED", "无写动作")),
    )
    with pytest.raises(OrbitError) as info:
        await options.ownership_context(object(), 1)
    assert info.value.status == 403


async def test_foreign_scope_cursor_rejected_before_any_candidate_query(monkeypatch):
    current = BusinessContext(1, "tenant", "TEAM_ADMIN", "subject", "team")
    monkeypatch.setattr(options, "ownership_context", AsyncMock(return_value=current))
    monkeypatch.setattr(options, "scope_version", AsyncMock(return_value=5))
    monkeypatch.setattr(options.access, "teams", AsyncMock(return_value=["managed-team"]))

    class Tokens:
        def verify(self, purpose, token):
            assert purpose == "LAUNCH_CURSOR_V1"
            return {"scope": "signed-for-another-actor-or-page"}

    with pytest.raises(OrbitError) as info:
        await options.ownership_options(object(), Tokens(), 1, cursor="signed")
    assert info.value.status == 409 and info.value.code == "SCOPE_CHANGED"
