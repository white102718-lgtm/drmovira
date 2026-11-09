"""模板共享候选最小动作与旧模板归属边界，真实SQL另走主线专项。"""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from orbit_api import template_options as options
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError


def uid(value):
    return str(UUID(int=value))


def current():
    return BusinessContext(1, uid(1), "USER", uid(2), uid(3))


async def test_recipient_cursor_wrong_scope_rejects_before_any_people_query(monkeypatch):
    authorized = AsyncMock(return_value=current())
    monkeypatch.setattr(options.access, "context", authorized)
    monkeypatch.setattr(options.access, "teams", AsyncMock(return_value=[]))
    monkeypatch.setattr(options, "scope_version", AsyncMock(return_value=1))

    class Tokens:
        def verify(self, purpose, token):
            assert purpose == "TEMPLATE_CURSOR_V1"
            return {"scope": "other-signed-actor-team-or-template"}

    with pytest.raises(OrbitError) as info:
        await options.recipient_options(object(), Tokens(), 1, "", cursor="signed")
    assert info.value.status == 409
    assert authorized.await_args.args[2] == "templates.share"
    assert authorized.await_count == 1


@pytest.mark.parametrize("owner,state,status", [(4, "ACTIVE", 403), (2, "ARCHIVED", 409)])
async def test_contextual_candidates_cannot_maintain_visible_other_owner_or_archived(
    monkeypatch, owner, state, status
):
    monkeypatch.setattr(options.access, "context", AsyncMock(return_value=current()))
    monkeypatch.setattr(
        options.TemplateStore,
        "row",
        AsyncMock(
            return_value={
                "owner_user_id": uid(owner),
                "owner_team_id": uid(3),
                "state": state,
                "revision": 1,
            }
        ),
    )
    with pytest.raises(OrbitError) as info:
        await options.recipient_options(object(), None, 1, "", template_id=uid(7))
    assert info.value.status == status


async def test_explicit_empty_template_uuid_is_not_silently_defaulted(monkeypatch):
    monkeypatch.setattr(options.access, "context", AsyncMock(return_value=current()))
    with pytest.raises(OrbitError) as info:
        await options.recipient_options(object(), None, 1, "", template_id="")
    assert info.value.status == 422
