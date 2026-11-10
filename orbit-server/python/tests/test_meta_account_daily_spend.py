from datetime import UTC, datetime
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_daily_spend_keeps_explicit_zero_and_does_not_fill_missing_days():
    from orbit_api.meta_account_daily_spend import read_daily_spend

    class Adapter:
        async def _page(self, path, params, normalize, **kwargs):
            assert path == "act_123/insights"
            assert params["time_increment"] == "1"
            assert "actions" not in params["fields"]
            row = dict(
                account_id="123",
                account_currency="USD",
                date_start="2026-11-09",
                date_stop="2026-11-09",
                spend="0",
            )
            return SimpleNamespace(items=[normalize(row)], complete=True, checkpoint=None)

    rows = await read_daily_spend(
        Adapter(), "123", "USD", "America/New_York", now=datetime(2026, 11, 10, 1, tzinfo=UTC)
    )
    assert len(rows) == 1
    assert rows[0]["business_date"] == "2026-11-09"
    assert rows[0]["amount"] == "0"
    assert rows[0]["coverage"] == "COMPLETE"


@pytest.mark.asyncio
async def test_daily_spend_empty_response_is_unknown_not_zero():
    from orbit_api.meta_account_daily_spend import read_daily_spend

    class Adapter:
        async def _page(self, *args, **kwargs):
            return SimpleNamespace(items=[], complete=True, checkpoint=None)

    assert (
        await read_daily_spend(
            Adapter(), "123", "USD", "UTC", now=datetime(2026, 11, 10, tzinfo=UTC)
        )
        == []
    )


@pytest.mark.asyncio
async def test_daily_spend_incomplete_pages_publish_nothing():
    from orbit_api.meta_account_daily_spend import read_daily_spend
    from orbit_api.meta_read_contract import MetaReadFailure

    class Adapter:
        async def _page(self, *args, **kwargs):
            return SimpleNamespace(items=[], complete=False, checkpoint=None)

    with pytest.raises(MetaReadFailure):
        await read_daily_spend(
            Adapter(), "123", "USD", "UTC", now=datetime(2026, 11, 10, tzinfo=UTC)
        )


@pytest.mark.asyncio
async def test_daily_spend_real_adapter_uses_fixed_read_only_parameters():
    from test_meta_read_adapter import Fake, config

    from orbit_api.meta_account_daily_spend import read_daily_spend
    from orbit_api.meta_read_adapter import MetaReadAdapter

    fake = Fake(
        {
            "data": [
                dict(
                    account_id="123",
                    account_currency="USD",
                    date_start="2026-11-10",
                    date_stop="2026-11-10",
                    spend="12.34",
                )
            ]
        }
    )
    rows = await read_daily_spend(
        MetaReadAdapter(config(), transport=fake),
        "123",
        "USD",
        "UTC",
        now=datetime(2026, 11, 10, tzinfo=UTC),
    )
    assert rows[0]["amount"] == "12.34"
    assert fake.calls[0][0] == "GET"


@pytest.mark.parametrize(
    "change",
    [
        dict(account_id="456"),
        dict(account_currency="EUR"),
        dict(date_stop="2026-11-11"),
        dict(spend="0.0000001"),
        dict(spend="NaN"),
    ],
)
@pytest.mark.asyncio
async def test_daily_spend_rejects_identity_date_and_precision_changes(change):
    from test_meta_read_adapter import Fake, config

    from orbit_api.meta_account_daily_spend import read_daily_spend
    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import MetaReadFailure

    row = dict(
        account_id="123",
        account_currency="USD",
        date_start="2026-11-10",
        date_stop="2026-11-10",
        spend="12.34",
    )
    fake = Fake({"data": [row | change]})
    with pytest.raises(MetaReadFailure):
        await read_daily_spend(
            MetaReadAdapter(config(), transport=fake),
            "123",
            "USD",
            "UTC",
            now=datetime(2026, 11, 10, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_initial_sync_requires_sync_permission_not_just_import(monkeypatch):
    import orbit_api.authorization as authorization
    from orbit_api.errors import OrbitError
    from orbit_api.meta_account_daily_spend import enqueue_initial_sync

    async def deny(session, actor, menu, permission, **kwargs):
        assert permission == "accounts.sync" and kwargs == {"acting_subject": False}
        raise OrbitError(403, "PERMISSION_DENIED", "denied")

    monkeypatch.setattr(authorization, "require_business_access", deny)
    assert await enqueue_initial_sync(None, SimpleNamespace(actor_id=1), None, None, None) is False


@pytest.mark.asyncio
async def test_publish_daily_spend_skips_newer_facts_and_reuses_original_publisher(monkeypatch):
    from datetime import date

    from orbit_api.account_details_store import AccountDetailsStore
    from orbit_api.meta_account_daily_spend import publish_daily_spend

    calls = []

    async def watermark(self, session, tenant, **kwargs):
        return {"revision": 7}

    async def publish(self, session, actor, revision, **kwargs):
        calls.append((actor, revision, kwargs["facts"]))

    monkeypatch.setattr(AccountDetailsStore, "watermark", watermark)
    monkeypatch.setattr(AccountDetailsStore, "publish", publish)

    class Session:
        def in_transaction(self):
            return True

        async def execute(self, statement, parameters):
            assert parameters["tenant"] == "tenant" and parameters["account"] == "account"
            return SimpleNamespace(
                mappings=lambda: [
                    {"business_date": date(2026, 11, 9), "observed_at": datetime(2026, 11, 10)}
                ]
            )

    facts = [
        dict(business_date="2026-11-09", observed_at="2026-11-09T23:00:00Z"),
        dict(business_date="2026-11-10", observed_at="2026-11-10T01:00:00Z"),
    ]
    await publish_daily_spend(
        Session(), SimpleNamespace(tenant_id="tenant", actor_id=1), "account", facts
    )
    assert calls == [(1, 7, [facts[1] | {"account_id": "account"}])]
