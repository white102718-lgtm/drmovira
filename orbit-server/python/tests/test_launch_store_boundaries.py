"""投放内部权限/限量/模板CAS边界，纯测不冒充真实SQL。"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from orbit_api import launch_access as access
from orbit_api import launch_references as refs
from orbit_api import template_store as templates
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import parse_plan_action
from orbit_api.launch_store import PAGE_BYTES, bounded_page, public_plan
from orbit_api.template_contract import parse_template_action


def uid(number):
    return str(UUID(int=number))


def current(role="USER"):
    return BusinessContext(1, uid(1), role, uid(2), uid(3))


@pytest.mark.parametrize(
    "role,owner,team,managed,allowed",
    [
        ("USER", 2, 99, [], True),
        ("USER", 4, 3, [uid(3)], False),
        ("TEAM_ADMIN", 2, 99, [], True),
        ("TEAM_ADMIN", 4, 3, [], False),
        ("TEAM_ADMIN", 4, 5, [uid(5)], True),
        ("SUPER_ADMIN", 4, 99, [], True),
    ],
)
def test_single_owner_scope_never_auto_grants_home_peers(role, owner, team, managed, allowed):
    assert (
        access.readable(
            current(role), managed, {"owner_user_id": uid(owner), "owner_team_id": uid(team)}
        )
        is allowed
    )


def test_original_page_byte_limit_is_bounded_progressing_and_not_silent_truncation():
    rows = [{"id": uid(i), "payload_bytes": PAGE_BYTES // 2} for i in range(1, 4)]
    assert bounded_page(rows, 3, "payload_bytes") == [uid(1)]
    assert bounded_page(rows[1:], 3, "payload_bytes") == [uid(2)]
    assert bounded_page([{"id": uid(8), "payload_bytes": PAGE_BYTES + 1}], 20, "payload_bytes") == [
        uid(8)
    ]


def test_public_plan_preserves_all_original_config_and_time_but_no_dependency_internals():
    payload = {"name": "草稿", "channel_id": None, "campaigns": []}
    row = {
        "id": uid(9),
        "revision": 2,
        "state": "DRAFT",
        "payload_json": json.dumps(payload),
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 2),
        "dependency_json": {"private": True},
    }
    value = public_plan(row)
    assert value["campaigns"] == [] and value["created_at"].endswith("Z")
    assert value["revision"] == 2 and "dependency_json" not in value


@pytest.mark.parametrize(
    "action,value,status",
    [
        (
            "allocation",
            {
                "asset_ids": [uid(1)],
                "allow_repeat": False,
                "seed": True,
                "algorithm_version": "allocation-v1",
            },
            400,
        ),
        (
            "allocation",
            {
                "asset_ids": [uid(1)],
                "allow_repeat": False,
                "seed": -1,
                "algorithm_version": "allocation-v1",
            },
            422,
        ),
        (
            "allocation",
            {
                "asset_ids": [uid(1), uid(1)],
                "allow_repeat": False,
                "seed": 0,
                "algorithm_version": "allocation-v1",
            },
            422,
        ),
        ("execute", {"hash": "g" * 64, "activate_ack": False}, 422),
        ("execute", {"hash": "a" * 64, "activate_ack": "false"}, 400),
        ("validate", {"allocation_id": uid(1), "name_reservation_id": "bad"}, 422),
    ],
)
def test_action_schema_failures_never_create_fake_task_or_hash(action, value, status):
    with pytest.raises(OrbitError) as info:
        parse_plan_action(json.dumps(value).encode(), action)
    assert info.value.status == status


def test_archive_is_strict_original_reason_and_apply_single_owner():
    assert parse_template_action(b'{"reason":"archive"}', "archive") == {"reason": "archive"}
    with pytest.raises(OrbitError) as info:
        parse_template_action(b'{"reason":"archive","recipient_user_ids":[]}', "archive")
    assert info.value.code == "UNKNOWN_FIELD"


async def test_empty_reference_draft_needs_no_source_read_menus(monkeypatch):
    monkeypatch.setattr(refs, "owner", AsyncMock(return_value=1))
    source = AsyncMock(side_effect=AssertionError("空引用不应强加来源菜单"))
    monkeypatch.setattr(refs, "source_contexts", source)
    result = await refs.validate_sources(
        SimpleNamespace(in_transaction=lambda: True),
        current(),
        {
            "ownership": {"owner_user_id": uid(2), "owner_team_id": uid(3)},
            "account_ids": [],
            "asset_ids": [],
            "channel_id": None,
            "campaigns": [],
            "identity_bindings": [],
        },
        permission="launch.create",
    )
    assert result == {"accounts": {}, "assets": {}, "channel": None}
    source.assert_not_awaited()


async def test_cross_module_target_must_be_current_tenant_subject_team_and_non_acting(monkeypatch):
    foreign = BusinessContext(8, uid(99), "SUPER_ADMIN", uid(4), uid(3))
    permission = AsyncMock(side_effect=[current(), foreign])
    monkeypatch.setattr(refs, "require_business_access", permission)
    with pytest.raises(OrbitError) as info:
        await refs.source_contexts(
            object(), current(), {"owner_user_id": uid(4), "owner_team_id": uid(3)}, 8, "accounts"
        )
    assert info.value.status == 404
    assert permission.await_args_list[1].kwargs == {"acting_subject": False}


async def test_metric_profile_unknown_tenant_dependency_never_saved_as_opaque_uuid(monkeypatch):
    monkeypatch.setattr(refs, "owner", AsyncMock(return_value=1))
    resolver = AsyncMock(side_effect=OrbitError(404, "METRIC_PROFILE_UNAVAILABLE", "来源不可用"))
    monkeypatch.setattr(
        "orbit_api.metric_profile_references.resolve_metric_profile_dependencies", resolver
    )
    with pytest.raises(OrbitError) as info:
        await refs.validate_sources(
            object(),
            current(),
            {
                "ownership": {"owner_user_id": uid(2), "owner_team_id": uid(3)},
                "campaigns": [{"adsets": [{"metric_profile_id": uid(99)}]}],
            },
            permission="launch.create",
        )
    assert info.value.status == 404
    assert info.value.code == "METRIC_PROFILE_UNAVAILABLE"
    assert resolver.await_args.args[-1] == [uid(99)]
    assert resolver.await_args.kwargs == {"permission": "launch.create", "isolated_fixture": False}


async def test_apply_rejects_future_if_match_when_unlocked_source_revision_differs(monkeypatch):
    # 防止先预读旧树，随后用猜测的未来If-Match接受新版本并复制旧树。
    monkeypatch.setattr(access, "context", AsyncMock(return_value=current()))
    monkeypatch.setattr(access, "clock", AsyncMock(return_value={}))
    monkeypatch.setattr(access, "replay", AsyncMock(return_value=None))
    monkeypatch.setattr(access, "successful_replay", AsyncMock(return_value=None))
    monkeypatch.setattr(templates, "verify_csrf", lambda *args: None)
    monkeypatch.setattr(
        templates, "validate_sources", AsyncMock(return_value={"accounts": {}, "assets": {}})
    )
    store = templates.TemplateStore(None)
    source = {"revision": 1, "config_json": []}
    store.row = AsyncMock(side_effect=[source, source | {"revision": 2, "state": "ACTIVE"}])
    with pytest.raises(OrbitError) as info:
        await store.apply(
            object(),
            1,
            "",
            "",
            "key",
            uid(5),
            2,
            {"ownership": {"owner_user_id": uid(2), "owner_team_id": uid(3)}, "reason": "应用"},
            uid(6),
        )
    assert info.value.status == 409 and info.value.code == "REVISION_CONFLICT"
