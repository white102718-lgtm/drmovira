"""账户详情空户商短路纯测；不计实时权限/SQL或容量验收。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import orbit_api.account_details_store as module
from orbit_api.account_details_contract import filters
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError

ACCOUNT = "10000000-0000-4000-8000-000000000001"
VENDOR = "20000000-0000-4000-8000-000000000001"
OWNER = "30000000-0000-4000-8000-000000000001"
TEAM = "40000000-0000-4000-8000-000000000001"
TENANT = "50000000-0000-4000-8000-000000000001"
NOW = datetime(2026, 10, 22, tzinfo=UTC)


def account(vendor):
    return {
        "id": ACCOUNT,
        "external_id": "123456",
        "name": "原账户",
        "vendor_id": vendor,
        "owner_user_id": OWNER,
        "owner_team_id": TEAM,
        "currency": "USD",
        "revision": 1,
        "auth_status": "AUTHORIZED",
        "account_status": "ACTIVE",
        "timezone_id": "UTC",
        "synced_at": None,
        "unbound_at": None,
        "value_json": "{}",
        "details_json": "{}",
    }


@pytest.fixture
def boundary(monkeypatch):
    records, aliases = AsyncMock(return_value={}), AsyncMock(return_value={})
    monkeypatch.setattr(module, "records", records)
    monkeypatch.setattr(module, "resolve_vendor_alias_snapshots", aliases)
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(mappings=lambda: [])))
    return SimpleNamespace(
        records=records,
        aliases=aliases,
        session=session,
        current=BusinessContext(7, TENANT, "USER", OWNER, TEAM),
        store=module.AccountDetailsStore(None),
        query=filters({"date_from": "2026-10-01", "date_to": "2026-10-20"}),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("vendor", [None, VENDOR])
async def test_no_catalog_vendor_does_not_enter_alias_source_and_preserves_null(boundary, vendor):
    b = boundary
    value = await b.store.enrich(b.session, b.current, [], [account(vendor)], b.query, NOW, None)
    b.records.assert_awaited_once_with(b.session, TENANT, [] if vendor is None else [VENDOR])
    b.aliases.assert_not_awaited()
    assert value[0]["account"]["vendor_id"] == vendor
    assert value[0]["account"]["vendor_alias"] is None
    assert value[0]["details"]["vendor_display"] == {
        "name": None,
        "source": "REFERENCE_CATALOG",
        "reason_code": "NOT_PROVIDED",
        "alias_source": "NOT_VISIBLE",
        "alias_revision": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", [None, "真实代称"])
async def test_existing_vendor_retains_original_helper_and_unknown_is_not_replaced_by_name(
    boundary, alias
):
    b = boundary
    b.records.return_value = {
        VENDOR: {
            "kind": "VENDOR",
            "value_json": {
                "name": "完整户商名称不能冒充代称",
                "data_owner_user_ids": [OWNER],
                "owner_team_id": TEAM,
            },
        }
    }
    b.aliases.return_value = {
        VENDOR: {
            "alias": alias,
            "alias_revision": 1,
            "source": "UNSET" if alias is None else "VENDOR_ALIAS",
        }
    }
    value = await b.store.enrich(b.session, b.current, [], [account(VENDOR)], b.query, NOW, None)
    b.aliases.assert_awaited_once_with(b.session, b.current, [VENDOR])
    assert value[0]["account"]["vendor_alias"] == alias
    display = value[0]["details"]["vendor_display"]
    assert display["name"] == "完整户商名称不能冒充代称"
    assert display["reason_code"] == ("ALIAS_UNSET" if alias is None else None)
    assert display["alias_revision"] == 1


@pytest.mark.asyncio
async def test_nonempty_vendor_current_permission_revocation_is_not_swallowed(boundary):
    b = boundary
    b.records.return_value = {VENDOR: {"kind": "VENDOR", "value_json": {}}}
    denial = OrbitError(403, "PERMISSION_DENIED", "当前户商权限撤销")
    b.aliases.side_effect = denial
    with pytest.raises(OrbitError) as caught:
        await b.store.enrich(b.session, b.current, [], [account(VENDOR)], b.query, NOW, None)
    assert caught.value is denial
    # 来源拒绝后没有继续拥有者/消费查询，也未返回部分DTO。
    assert b.session.execute.await_count == 1


@pytest.mark.asyncio
async def test_empty_account_page_still_avoids_all_sources(boundary):
    b = boundary
    assert await b.store.enrich(b.session, b.current, [], [], b.query, NOW, None) == []
    b.records.assert_not_awaited()
    b.aliases.assert_not_awaited()
    b.session.execute.assert_not_awaited()
