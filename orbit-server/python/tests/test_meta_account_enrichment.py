from datetime import UTC, datetime

import pytest

from orbit_api.account_metadata import metadata


def test_optional_metadata_observations_are_validated():
    value = dict(
        external_id="123",
        name="A",
        currency="USD",
        timezone_id="UTC",
        account_status="ACTIVE",
        auth_status="AUTHORIZED",
        observed_at=datetime.now(UTC),
        observations={
            "payment_type": dict(
                value="预付",
                code="PREPAY",
                status="SYNCED",
                reason_code=None,
                source="META_GRAPH_METADATA",
                observed_at="2026-11-10T00:00:00Z",
            )
        },
    )
    assert metadata(value, "123", {"USD"}).observations["payment_type"]["code"] == "PREPAY"


def test_meta_details_money_units_and_unknowns():
    from orbit_api.meta_account_enrichment import observations

    now = datetime.now(UTC)
    for currency, expected in [("USD", "12.34"), ("JPY", "1234"), ("HUF", "1234")]:
        result = observations(
            dict(
                currency=currency,
                amount_spent_minor="1234",
                balance_minor="0",
                business_name="Acme",
                is_prepay_account=True,
            ),
            now,
        )
        assert result["lifetime_spend"]["amount"] == expected
        assert result["payable"]["amount"] == "0"
        assert "balance" not in result
        assert result["business_entity"]["value"] == "Acme"
        assert result["payment_type"]["code"] == "PREPAY"
    result = observations(dict(currency="ZZZ", amount_spent_minor="1234"), now)
    assert result["lifetime_spend"]["amount"] is None
    assert result["payment_method"]["value"] is None


def test_merge_uses_newer_observation_without_erasing_other_sources():
    from orbit_api.account_metadata import merge_observations

    older = {"value": "old", "observed_at": "2026-11-09T00:00:00Z"}
    newer = {"value": "new", "observed_at": "2026-11-10T00:00:00Z"}
    assert (
        merge_observations({"payment_type": newer}, {"payment_type": older})["payment_type"]
        == newer
    )


@pytest.mark.asyncio
async def test_optional_reads_keep_core_on_field_denial_and_read_only_allowlist():
    from test_meta_read_adapter import Fake, config

    from orbit_api.meta_read_adapter import MetaReadAdapter

    denied = {"error": {"code": 200}}
    fake = Fake(
        denied,
        {"id": "act_123", "account_id": "123", "business": {"id": "9", "name": "BM"}},
        {"id": "act_123", "account_id": "123", "is_prepay_account": False},
        denied,
        {"id": "act_123", "account_id": "123", "disable_reason": 0},
        {"id": "7", "name": "Person"},
    )
    extras, principal = await MetaReadAdapter(config(), transport=fake).account_extras(
        "123", principal=True
    )
    assert extras["business"]["id"] == "9"
    assert principal["name"] == "Person"
    assert all(call[0] == "GET" for call in fake.calls)


def test_business_managers_require_verified_id_and_name():
    from orbit_api.meta_account_enrichment import business_managers

    assert business_managers({"business": {"id": "9", "name": "BM"}}) == [
        {"external_id": "9", "name": "BM"}
    ]
    assert business_managers({"business": None}) is None
    assert business_managers({"business": {"id": "bogus", "name": "BM"}}) is None


@pytest.mark.asyncio
async def test_manual_bm_metadata_has_same_observations():
    from orbit_api.account_platform import MetaAccountPlatform, MetaReadConfiguration

    reader = MetaAccountPlatform(MetaReadConfiguration("9", "v24.0", "fixture"))
    reader.authorized = frozenset({"123"})

    async def get(path, params, **kwargs):
        return dict(
            id="act_123",
            account_id="123",
            name="A",
            currency="USD",
            timezone_name="UTC",
            account_status=1,
            amount_spent="1234",
            balance="567",
            business_name="Acme",
            is_prepay_account=False,
        )

    reader._get = get
    result = await reader.fetch_metadata("123")
    assert result["observations"]["payable"]["amount"] == "5.67"


@pytest.mark.parametrize("code,expected", [(190, "META_AUTH_FAILED"), (4, "META_RATE_LIMITED")])
@pytest.mark.asyncio
async def test_optional_403_does_not_hide_auth_or_rate_failure(code, expected):
    from test_meta_read_adapter import Fake, config

    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import MetaReadFailure

    fake = Fake(*[(403, {"error": {"code": code}})] * 4)

    async def sleep(_):
        pass

    adapter = MetaReadAdapter(config(), transport=fake, sleep=sleep)
    with pytest.raises(MetaReadFailure) as error:
        await adapter.account_extras("123")
    assert error.value.code == expected
