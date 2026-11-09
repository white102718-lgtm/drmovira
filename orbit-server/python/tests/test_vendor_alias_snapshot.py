"""内部冻结动作授权与资料重验纯测试；账户历史落库真实性另由A020专项证明。"""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from orbit_api import vendor_alias_snapshot as source
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError

VENDOR = "10000000-0000-4000-8000-000000000001"
CONTEXT = BusinessContext(1, "tenant", "USER", "self", "team")


def vendor():
    return {
        "id": VENDOR,
        "kind": "VENDOR",
        "revision": 1,
        "catalog_revision": 3,
        "value_json": {
            "id": VENDOR,
            "kind": "VENDOR",
            "name": "不能截断为代称的完整名称",
            "source_key": "source",
            "availability": "AVAILABLE",
            "owner_team_id": "team",
            "data_owner_user_ids": ["self"],
        },
    }


@pytest.fixture
def setup(monkeypatch):
    auth = AsyncMock(return_value=CONTEXT)
    rows = AsyncMock(return_value={VENDOR: vendor()})
    aliases = AsyncMock(return_value={})
    monkeypatch.setattr(source, "require_business_access", auth)
    monkeypatch.setattr(source, "records", rows)
    monkeypatch.setattr(source, "managed_teams", AsyncMock(return_value=[]))
    monkeypatch.setattr(source, "alias_rows", aliases)
    return auth, rows, aliases


@pytest.mark.asyncio
async def test_import_only_freeze_uses_original_action_and_real_unknown_not_name(setup):
    auth, rows, aliases = setup
    result = await source.freeze_vendor_alias_snapshots(
        None, CONTEXT, {VENDOR: vendor()}, permission="accounts.import"
    )
    auth.assert_awaited_once_with(None, 1, "accounts", "accounts.import", acting_subject=True)
    assert result[VENDOR] == {
        "alias": None,
        "alias_revision": 1,
        "source": "UNSET",
        "vendor_availability": "AVAILABLE",
    }
    rows.assert_awaited_once_with(None, "tenant", [VENDOR])
    aliases.assert_awaited_once_with(None, "tenant", [VENDOR])


@pytest.mark.asyncio
async def test_worker_explicit_background_mode_still_reauthorizes_action(setup):
    auth, _, aliases = setup
    aliases.return_value = {VENDOR: {"alias": "真实代称", "revision": 4}}
    result = await source.freeze_vendor_alias_snapshots(
        None, CONTEXT, {VENDOR: vendor()}, permission="accounts.import", acting_subject=False
    )
    auth.assert_awaited_once_with(None, 1, "accounts", "accounts.import", acting_subject=False)
    assert result[VENDOR]["alias"] == "真实代称" and result[VENDOR]["alias_revision"] == 4


@pytest.mark.asyncio
async def test_assignment_uses_assign_not_read(setup):
    auth, _, _ = setup
    await source.freeze_vendor_alias_snapshots(
        None, CONTEXT, {VENDOR: vendor()}, permission="accounts.assign"
    )
    assert auth.await_args.args[3] == "accounts.assign"


@pytest.mark.asyncio
async def test_revoked_action_fails_before_any_source_read(setup):
    auth, rows, aliases = setup
    auth.side_effect = OrbitError(403, "PERMISSION_DENIED", "撤权")
    with pytest.raises(OrbitError):
        await source.freeze_vendor_alias_snapshots(
            None, CONTEXT, {VENDOR: vendor()}, permission="accounts.import"
        )
    rows.assert_not_awaited()
    aliases.assert_not_awaited()


@pytest.mark.parametrize(
    "field,value", [("tenant_id", "foreign"), ("data_role", "TEAM_ADMIN"), ("team_id", "moved")]
)
@pytest.mark.asyncio
async def test_changed_business_context_never_reuses_old_actor_scope(setup, field, value):
    auth, rows, _ = setup
    auth.return_value = replace(CONTEXT, **{field: value})
    with pytest.raises(OrbitError) as caught:
        await source.freeze_vendor_alias_snapshots(
            None, CONTEXT, {VENDOR: vendor()}, permission="accounts.import"
        )
    assert caught.value.status == 403
    rows.assert_not_awaited()


@pytest.mark.parametrize(
    "change", ["missing", "foreign_owner", "disabled", "revision", "source_key", "kind"]
)
@pytest.mark.asyncio
async def test_current_vendor_revalidation_rejects_drift_before_alias_reads(setup, change):
    _, rows, aliases = setup
    current = vendor()
    if change == "missing":
        rows.return_value = {}
    elif change == "revision":
        current["revision"] = 2
        rows.return_value = {VENDOR: current}
    elif change == "kind":
        current["kind"] = "PRODUCT"
        rows.return_value = {VENDOR: current}
    else:
        field, value = {
            "foreign_owner": ("data_owner_user_ids", ["other"]),
            "disabled": ("availability", "UNAVAILABLE"),
            "source_key": ("source_key", "changed"),
        }[change]
        current["value_json"][field] = value
        rows.return_value = {VENDOR: current}
    with pytest.raises(OrbitError) as caught:
        await source.freeze_vendor_alias_snapshots(
            None, CONTEXT, {VENDOR: vendor()}, permission="accounts.import"
        )
    assert caught.value.status == 422
    aliases.assert_not_awaited()


@pytest.mark.asyncio
async def test_unreadable_but_matching_supplied_vendor_cannot_bypass_scope(setup):
    _, rows, aliases = setup
    inaccessible = vendor()
    inaccessible["value_json"]["data_owner_user_ids"] = ["other"]
    rows.return_value = {VENDOR: inaccessible}
    with pytest.raises(OrbitError):
        await source.freeze_vendor_alias_snapshots(
            None, CONTEXT, {VENDOR: deepcopy(inaccessible)}, permission="accounts.import"
        )
    aliases.assert_not_awaited()


def test_cleared_real_source_keeps_maintained_revision_but_alias_null():
    assert source.alias_snapshot({"alias": None, "revision": 3})["source"] == "VENDOR_ALIAS"
    assert source.alias_snapshot({"alias": None, "revision": 3})["alias"] is None


@pytest.mark.parametrize(
    "row",
    [
        {"alias": "x" * 31, "revision": 2},
        {"alias": "bad\n", "revision": 2},
        {"alias": " e\u0301 ", "revision": 2},
        {"alias": "value", "revision": 1},
    ],
)
def test_corrupt_alias_source_is_not_normalized_or_truncated_into_snapshot(row):
    with pytest.raises(OrbitError):
        source.alias_snapshot(row)


@pytest.mark.parametrize("managed,allowed", [(["team"], True), ([], False)])
@pytest.mark.asyncio
async def test_team_admin_requires_explicit_managed_team_for_other_owners(
    setup, monkeypatch, managed, allowed
):
    auth, rows, aliases = setup
    manager = BusinessContext(1, "tenant", "TEAM_ADMIN", "manager", "home")
    auth.return_value = manager
    row = vendor()
    row["value_json"]["data_owner_user_ids"] = ["other"]
    rows.return_value = {VENDOR: deepcopy(row)}
    monkeypatch.setattr(source, "managed_teams", AsyncMock(return_value=managed))
    if allowed:
        result = await source.freeze_vendor_alias_snapshots(
            None, manager, {VENDOR: row}, permission="accounts.import"
        )
        assert result[VENDOR]["alias"] is None
    else:
        with pytest.raises(OrbitError):
            await source.freeze_vendor_alias_snapshots(
                None, manager, {VENDOR: row}, permission="accounts.import"
            )
        aliases.assert_not_awaited()
