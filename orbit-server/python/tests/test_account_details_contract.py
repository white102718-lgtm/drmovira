"""18列扩展的日期/十进制/来源/覆盖纯逻辑专项，不代表真实数据库或平台验收。"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from orbit_api.account_details_contract import (
    amount,
    fact_input,
    filters,
    observed_fields,
    timestamp,
    window,
)
from orbit_api.account_details_store import summarize
from orbit_api.errors import OrbitError

ID = "10000000-0000-4000-8000-000000000001"
NOW = datetime(2026, 3, 8, 5, 30, tzinfo=UTC)


def test_today_is_each_account_local_day_at_one_frozen_utc_reference():
    query = filters({})
    assert window(query, "America/New_York", NOW) == (date(2026, 3, 8),) * 2
    assert window(query, "America/Los_Angeles", NOW) == (date(2026, 3, 7),) * 2
    assert window(query, "Asia/Shanghai", NOW) == (date(2026, 3, 8),) * 2


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("YESTERDAY", ("2026-03-07", "2026-03-07")),
        ("LAST7", ("2026-03-02", "2026-03-08")),
        ("LAST14", ("2026-02-23", "2026-03-08")),
        ("LAST30", ("2026-02-07", "2026-03-08")),
        ("THISWEEK", ("2026-03-02", "2026-03-08")),
        ("LASTWEEK", ("2026-02-23", "2026-03-01")),
        ("THISMONTH", ("2026-03-01", "2026-03-08")),
        ("LASTMONTH", ("2026-02-01", "2026-02-28")),
    ],
)
def test_local_calendar_shortcuts_do_not_subtract_utc_seconds_across_dst(mode, expected):
    assert (
        tuple(x.isoformat() for x in window(filters({"mode": mode}), "America/New_York", NOW))
        == expected
    )


def test_custom_same_named_days_and_unknown_max_have_no_fabricated_date():
    query = filters({"date_from": "2026-03-01", "date_to": "2026-03-08"})
    assert query["mode"] == "CUSTOM"
    assert window(query, "America/Los_Angeles", NOW) == (date(2026, 3, 1), date(2026, 3, 8))
    assert window(filters({"mode": "MAX"}), "UTC", NOW) == (None, None)


@pytest.mark.parametrize(
    "query",
    [
        {"date_from": "2026-03-01"},
        {"mode": "TODAY", "date_from": "2026-03-01", "date_to": "2026-03-08"},
        {"date_from": "2026-03-09", "date_to": "2026-03-08"},
        {"date_from": "2026-02-30", "date_to": "2026-03-08"},
        {"mode": "created_at"},
    ],
)
def test_date_mode_or_boundaries_fail_explicitly(query):
    with pytest.raises(OrbitError) as error:
        filters(query)
    assert error.value.status == 422


@pytest.mark.parametrize(
    "value", ["-1", "1e3", "NaN", "01", "0.0000001", 0, "1000000000000000000000"]
)
def test_money_rejects_noncanonical_or_overflow(value):
    with pytest.raises(OrbitError):
        amount(value, "/amount")


def test_complete_zero_is_distinct_from_missing_or_partial_and_decimal_never_float():
    start, end = date(2026, 3, 7), date(2026, 3, 8)
    result, coverage = summarize(
        "USD",
        start,
        end,
        {
            "days": 2,
            "complete_days": 2,
            "amount": Decimal("0.000000"),
            "observed_at": NOW.replace(tzinfo=None),
        },
    )
    assert (
        result["amount"] == "0.000000"
        and coverage == "COMPLETE"
        and result["business_date"] is None
    )
    for aggregate in [
        None,
        {"days": 1, "complete_days": 1, "amount": Decimal("900")},
        {"days": 2, "complete_days": 1, "amount": Decimal("900")},
    ]:
        value, state = summarize("USD", start, end, aggregate)
        assert value["amount"] is None and state != "COMPLETE" and value["observed_at"] is None


def test_aggregate_overflow_never_rounds_or_leaks_invalid_contract_amount():
    day = date(2026, 3, 8)
    aggregate = {
        "days": 1,
        "complete_days": 1,
        "amount": Decimal("9999999999999999999999999.123456"),
        "observed_at": NOW.replace(tzinfo=None),
    }
    with pytest.raises(OrbitError) as error:
        summarize("USD", day, day, aggregate)
    assert error.value.code == "ACCOUNT_AGGREGATE_RANGE_EXCEEDED"


@pytest.mark.parametrize(
    "value", ["2026-03-08", "20260308T000000Z", "2026-03-08T00:00:00", "2026-03-08 00:00:00Z"]
)
def test_observation_time_requires_explicit_rfc3339_zone(value):
    with pytest.raises(OrbitError):
        timestamp(value, "/observed_at")


def fact(**changes):
    return {
        "account_id": ID,
        "business_date": "2026-03-07",
        "amount": "0",
        "currency": "USD",
        "coverage": "COMPLETE",
        "source": "META_INSIGHTS",
        "observed_at": "2026-03-08T05:30:00Z",
    } | changes


def test_fact_zero_is_valid_but_owner_and_currency_or_future_business_day_are_not():
    value = fact_input(fact(), "USD", "America/New_York")
    assert value["amount"] == "0" and value["business_date"] == date(2026, 3, 7)
    for item in [
        fact(owner_user_id=ID),
        fact(currency="EUR"),
        fact(business_date="2026-03-09"),
        fact(coverage="PARTIAL"),
        fact(amount=None),
        fact(source=[]),
        fact(coverage=[]),
    ]:
        with pytest.raises(OrbitError) as error:
            fact_input(item, "USD", "America/New_York")
        assert error.value.status == 422


def test_observation_contract_forbids_secret_fields_and_available_balance_inference():
    with pytest.raises(OrbitError):
        observed_fields({"accessToken": "never-save"}, "USD")
    value = {
        "amount": "1",
        "currency": "USD",
        "kind": "AVAILABLE",
        "status": "SYNCED",
        "source": "META_GRAPH_METADATA",
        "business_date": None,
        "observed_at": "2026-03-08T05:30:00Z",
    }
    with pytest.raises(OrbitError):
        observed_fields({"balance": value}, "USD")
    value["kind"] = "UNKNOWN"
    assert observed_fields({"balance": value}, "USD")["balance"]["amount"] == "1"


@pytest.mark.parametrize(
    "changes", [{"status": []}, {"source": []}, {"value": 2}, {"value": "\ud800"}]
)
def test_bad_text_observation_types_are_rejected_without_runtime_type_error(changes):
    value = {
        "value": None,
        "code": None,
        "status": "UNKNOWN",
        "reason_code": None,
        "source": "AUTHORIZED_VENDOR",
        "observed_at": None,
    } | changes
    with pytest.raises(OrbitError):
        observed_fields({"personal_profile": value}, "USD")
