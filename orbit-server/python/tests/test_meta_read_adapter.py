"""Meta读取真实协议边界；合成transport不作为外部API验收。"""

import json
from datetime import date
from uuid import UUID

import pytest


def config():
    from orbit_api.meta_read_contract import MetaReadConfiguration

    return MetaReadConfiguration(str(UUID(int=1)), 1, "v24.0", "private-fixture-token")


def test_config_requires_version_and_hides_token():
    from orbit_api.meta_read_contract import MetaReadConfiguration, MetaReadFailure

    with pytest.raises(MetaReadFailure):
        MetaReadConfiguration(str(UUID(int=1)), 1, "", "token")
    assert "private-fixture-token" not in repr(config())


def test_business_window_dst_and_decimal_null():
    from orbit_api.meta_read_contract import InsightWindow, decimal_value

    window = InsightWindow(date(2026, 3, 8), date(2026, 3, 8), "America/New_York")
    start, end = window.utc_bounds()
    assert (end - start).total_seconds() == 23 * 3600
    assert decimal_value(None) is None
    assert decimal_value("0.100000000000000001") == "0.100000000000000001"


class Fake:
    def __init__(self, *values):
        self.values = list(values)
        self.calls = []

    async def request(self, method, path, parameters, token, *, maximum_bytes):
        from orbit_api.meta_read_adapter import GraphResponse, validate_graph_parameters

        validate_graph_parameters(method, path, parameters)
        self.calls.append((method, path, parameters))
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        status, payload = value if isinstance(value, tuple) else (200, value)
        return GraphResponse(status, json.dumps(payload).encode())


@pytest.mark.asyncio
async def test_complete_only_after_final_page_and_cursor_bound_to_request():
    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import MetaReadFailure

    fake = Fake(
        {
            "data": [{"id": "act_123", "account_id": "123"}],
            "paging": {
                "next": "https://graph.facebook.com/v24.0/me/adaccounts?after=abc&access_token=secret",
                "cursors": {"after": "abc"},
            },
        },
        {"data": [{"id": "act_456", "account_id": "456"}]},
    )
    adapter = MetaReadAdapter(config(), transport=fake)
    first = await adapter.accounts_page()
    assert not first.complete and first.checkpoint.after == "abc"
    with pytest.raises(MetaReadFailure):
        await adapter.accounts_page(edge="owned", business_id="99", checkpoint=first.checkpoint)
    last = await adapter.accounts_page(checkpoint=first.checkpoint)
    assert last.complete and last.checkpoint is None
    assert fake.calls[1][2]["after"] == "abc"
    assert "access_token" not in fake.calls[1][2]


@pytest.mark.asyncio
async def test_rate_limit_three_retries_auth_never_retried():
    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import MetaReadFailure

    delays = []

    async def sleep(value):
        delays.append(value)

    fake = Fake(*[(429, {"error": {"code": 4}})] * 4)
    with pytest.raises(MetaReadFailure, match="META_RATE_LIMITED"):
        await MetaReadAdapter(config(), transport=fake, sleep=sleep).accounts_page()
    assert len(fake.calls) == 4 and len(delays) == 3
    fake = Fake((400, {"error": {"code": 190, "message": "private-fixture-token"}}))
    with pytest.raises(MetaReadFailure, match="META_AUTH_FAILED") as error:
        await MetaReadAdapter(config(), transport=fake, sleep=sleep).accounts_page()
    assert len(fake.calls) == 1 and "private-fixture-token" not in str(error.value)


@pytest.mark.asyncio
async def test_async_start_unknown_not_replayed_and_incomplete_not_read():
    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import InsightWindow, MetaReadFailure

    window = InsightWindow(date(2026, 11, 1), date(2026, 11, 1), "UTC")
    fake = Fake(TimeoutError("sensitive"))
    with pytest.raises(MetaReadFailure, match="META_REPORT_START_UNKNOWN"):
        await MetaReadAdapter(config(), transport=fake).start_report(
            "123", window, attribution=attribution()
        )
    assert len(fake.calls) == 1
    fake = Fake(
        {"report_run_id": "456"},
        {
            "id": "456",
            "account_id": "123",
            "async_status": "Job Running",
            "async_percent_completion": 100,
        },
    )
    adapter = MetaReadAdapter(config(), transport=fake)
    report = await adapter.start_report("123", window, attribution=attribution())
    with pytest.raises(MetaReadFailure, match="META_REPORT_NOT_READY"):
        await adapter.report_page(report)
    assert len(fake.calls) == 2


@pytest.mark.parametrize(
    "next_url",
    [
        "http://graph.facebook.com/v24.0/me/adaccounts?after=x",
        "https://evil.test/v24.0/me/adaccounts?after=x",
        "https://graph.facebook.com/v24.0/99/insights?after=x",
        False,
    ],
)
@pytest.mark.asyncio
async def test_untrusted_pagination_never_becomes_complete(next_url):
    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import MetaReadFailure

    fake = Fake({"data": [], "paging": {"next": next_url, "cursors": {"after": "x"}}})
    with pytest.raises(MetaReadFailure, match="META_PAGINATION_INVALID"):
        await MetaReadAdapter(config(), transport=fake).accounts_page()
    assert len(fake.calls) == 1


@pytest.mark.parametrize("value", [1.1, True, "NaN", "Infinity", "-1", "1e8", "0.1x"])
def test_float_special_negative_and_malformed_money_rejected(value):
    from orbit_api.meta_read_contract import MetaReadFailure, decimal_value

    with pytest.raises(MetaReadFailure):
        decimal_value(value)


@pytest.mark.asyncio
async def test_insight_missing_metrics_stay_null_and_target_hierarchy_required():
    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import InsightWindow, MetaReadFailure

    window = InsightWindow(date(2026, 11, 1), date(2026, 11, 1), "UTC")
    row = {
        "account_id": "123",
        "campaign_id": "1",
        "adset_id": "2",
        "ad_id": "3",
        "date_start": "2026-11-01",
        "date_stop": "2026-11-01",
        "spend": "1.000000000001",
    }
    adapter = MetaReadAdapter(
        config(), transport=Fake({"data": [row]}, {"data": [row | {"account_id": "999"}]})
    )
    result = await adapter.insights_page("123", window, attribution=attribution())
    assert result.items[0]["spend"] == "1.000000000001"
    assert result.items[0]["impressions"] is None and result.items[0]["actions"] is None
    with pytest.raises(MetaReadFailure, match="META_ACCOUNT_MISMATCH"):
        await adapter.insights_page("123", window, attribution=attribution())


@pytest.mark.asyncio
async def test_complete_async_report_fetches_only_report_edge():
    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import InsightWindow

    window = InsightWindow(date(2026, 11, 1), date(2026, 11, 1), "UTC")
    fake = Fake(
        {"report_run_id": "456"},
        {
            "id": "456",
            "account_id": "123",
            "async_status": "Job Completed",
            "async_percent_completion": 100,
        },
        {"data": []},
    )
    adapter = MetaReadAdapter(config(), transport=fake)
    result = await adapter.report_page(
        await adapter.start_report("123", window, attribution=attribution())
    )
    assert result.complete
    assert fake.calls[0][0:2] == ("POST", "/v24.0/act_123/insights")
    assert fake.calls[-1][0:2] == ("GET", "/v24.0/456/insights")


@pytest.mark.asyncio
async def test_same_cursor_and_duplicate_rows_rejected():
    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import MetaReadFailure

    first = {
        "data": [{"id": "act_1", "account_id": "1"}],
        "paging": {
            "next": "https://graph.facebook.com/v24.0/me/adaccounts?after=x",
            "cursors": {"after": "x"},
        },
    }
    fake = Fake(first, {"data": [{"id": "act_1", "account_id": "1"}]})
    adapter = MetaReadAdapter(config(), transport=fake)
    page = await adapter.accounts_page()
    with pytest.raises(MetaReadFailure, match="META_PAGINATION_INVALID"):
        await adapter.accounts_page(checkpoint=page.checkpoint)


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/v24.0/act_1/ads"),
        ("DELETE", "/v24.0/1"),
        ("GET", "https://evil.test/"),
        ("GET", "/v24.0/me?access_token=x"),
    ],
)
@pytest.mark.asyncio
async def test_transport_rejects_non_read_surface_before_network(method, path):
    from orbit_api.meta_read_adapter import GraphReadTransport
    from orbit_api.meta_read_contract import MetaReadFailure

    with pytest.raises(MetaReadFailure, match="META_REQUEST_INVALID"):
        await GraphReadTransport().request(
            method, path, {}, "private-fixture-token", maximum_bytes=1024
        )


def attribution():
    from orbit_api.meta_read_contract import MetaAttribution

    return MetaAttribution(
        str(UUID(int=2)),
        "fixture-v1",
        1,
        "a" * 64,
        "fixture-adapter-v1",
        "b" * 64,
        ("7d_click", "1d_view"),
        "impression",
    )


@pytest.mark.asyncio
async def test_missing_metric_profile_blocks_before_network():
    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import InsightWindow, MetaReadFailure

    fake = Fake()
    with pytest.raises(MetaReadFailure):
        await MetaReadAdapter(config(), transport=fake).insights_page(
            "123", InsightWindow(date(2026, 11, 1), date(2026, 11, 1), "UTC")
        )
    assert fake.calls == []


@pytest.mark.asyncio
async def test_explicit_attribution_is_sent_and_version_change_invalidates_cursor():
    from dataclasses import replace

    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import InsightWindow, MetaReadFailure

    window = InsightWindow(date(2026, 11, 1), date(2026, 11, 1), "UTC")
    fake = Fake(
        {
            "data": [],
            "paging": {
                "next": "https://graph.facebook.com/v24.0/act_123/insights?after=x",
                "cursors": {"after": "x"},
            },
        }
    )
    adapter = MetaReadAdapter(config(), transport=fake)
    page = await adapter.insights_page("123", window, attribution=attribution())
    assert json.loads(fake.calls[0][2]["action_attribution_windows"]) == ["7d_click", "1d_view"]
    assert fake.calls[0][2]["action_report_time"] == "impression"
    with pytest.raises(MetaReadFailure, match="META_CHECKPOINT_MISMATCH"):
        await adapter.insights_page(
            "123",
            window,
            attribution=replace(attribution(), registry_revision=2),
            checkpoint=page.checkpoint,
        )


def test_resolved_attribution_requires_verified_matching_mapping_and_source_hash():
    import hashlib

    from orbit_api.directory_tokens import canonical
    from orbit_api.meta_read_contract import MetaAttribution, MetaReadFailure

    profile = {
        "id": str(UUID(int=2)),
        "version": "v1",
        "source": "META",
        "verified": True,
        "timezone_policy": "ACCOUNT_LOCAL",
        "breakdown": "TOTAL",
        "attribution_windows": ["7d_click", "1d_view"],
        "action_report_time": "conversion",
    }
    resolved = {
        "profile": profile,
        "profile_source_hash": hashlib.sha256(canonical(profile).encode()).hexdigest(),
        "bound_profile_version": "v1",
        "registry_revision": 1,
        "adapter_version": "v1",
        "attribution_spec": [
            {"event_type": "CLICK_THROUGH", "window_days": 7},
            {"event_type": "VIEW_THROUGH", "window_days": 1},
        ],
    }
    assert MetaAttribution.from_resolved(resolved).report_time == "conversion"
    with pytest.raises(MetaReadFailure):
        MetaAttribution.from_resolved(
            resolved | {"attribution_spec": [{"event_type": "EXPLICIT", "window_days": 7}]}
        )
    with pytest.raises(MetaReadFailure):
        MetaAttribution.from_resolved(resolved | {"profile_source_hash": "0" * 64})


@pytest.mark.asyncio
async def test_checkpoint_json_round_trip_and_account_receipt():
    from dataclasses import asdict

    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import ReadCheckpoint

    fake = Fake(
        {
            "data": [],
            "paging": {
                "next": "https://graph.facebook.com/v24.0/me/adaccounts?after=x",
                "cursors": {"after": "x"},
            },
        },
        {"data": []},
        {"id": "act_123", "account_id": "123", "currency": "USD"},
    )
    adapter = MetaReadAdapter(config(), transport=fake)
    first = await adapter.accounts_page()
    checkpoint = ReadCheckpoint(**json.loads(json.dumps(asdict(first.checkpoint))))
    assert (await adapter.accounts_page(checkpoint=checkpoint)).complete
    page = await adapter.account_page("123")
    assert page.complete and len(page.evidence_sha256) == 64 and page.items[0]["currency"] == "USD"


@pytest.mark.parametrize("version", ["v1.0", "v23.0", "v25.0", "v999.0"])
def test_unreviewed_api_versions_fail_before_transport(version):
    from orbit_api.meta_read_contract import MetaReadConfiguration, MetaReadFailure

    with pytest.raises(MetaReadFailure, match="META_API_VERSION_UNSUPPORTED"):
        MetaReadConfiguration(str(UUID(int=1)), 1, version, "private-fixture-token")


@pytest.mark.asyncio
async def test_transport_rejects_fields_not_in_pinned_version_contract():
    from orbit_api.meta_read_adapter import GraphReadTransport
    from orbit_api.meta_read_contract import MetaReadFailure

    with pytest.raises(MetaReadFailure, match="META_REQUEST_INVALID"):
        await GraphReadTransport().request(
            "GET",
            "/v24.0/act_123",
            {"fields": "id,unknown_field"},
            "private-fixture-token",
            maximum_bytes=1024,
        )
    with pytest.raises(MetaReadFailure, match="META_API_VERSION_UNSUPPORTED"):
        await GraphReadTransport().request(
            "GET", "/v1.0/act_123", {"fields": "id"}, "private-fixture-token", maximum_bytes=1024
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,parents",
    [
        ("CAMPAIGN", {}),
        ("ADSET", {"campaign_id": "1"}),
        ("AD", {"campaign_id": "1", "adset_id": "2"}),
    ],
)
async def test_structure_fields_match_version_and_minor_budgets_preserve_precision(kind, parents):
    from orbit_api.meta_read_adapter import MetaReadAdapter

    fake = Fake(
        {
            "data": [
                {
                    "id": "3",
                    "account_id": "123",
                    "name": "entity",
                    "daily_budget": "12345678901234567890",
                    **parents,
                }
            ]
        }
    )
    page = await MetaReadAdapter(config(), transport=fake).structure_page("123", kind)
    assert page.complete and page.items[0]["daily_budget_minor"] == "12345678901234567890"
    assert page.items[0]["lifetime_budget_minor"] is None
