"""原规则账户当地窗口纯测试；不是SQL来源、模拟或平台验收。"""

from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from orbit_api.rule_metric_windows import (
    AccountMetricTimezone,
    RuleMetricWindowError,
    resolve_rule_metric_window,
    resolve_rule_metric_windows,
)

ACCOUNT = "00000000-0000-0000-0000-000000000001"


def account(zone="America/New_York", identifier=ACCOUNT):
    return AccountMetricTimezone(identifier, zone)


@pytest.mark.parametrize(
    "window,start,end",
    [
        ("TODAY", "2024-03-10", "2024-03-10"),
        ("YESTERDAY", "2024-03-09", "2024-03-09"),
        ("LAST_3D", "2024-03-08", "2024-03-10"),
        ("LAST_7D", "2024-03-04", "2024-03-10"),
    ],
)
def test_original_windows_include_today_and_both_endpoints(window, start, end):
    instant = datetime(2024, 3, 10, 12, tzinfo=UTC)
    value = resolve_rule_metric_window(instant, window, account())
    assert value.date_from == date.fromisoformat(start)
    assert value.date_to == date.fromisoformat(end)
    assert value.local_today == date(2024, 3, 10)
    assert value.evaluated_at is instant
    assert value.timezone_name == "America/New_York"


def test_one_instant_has_different_account_dates_not_schedule_shanghai_date():
    instant = datetime(2026, 1, 1, 1, tzinfo=UTC)
    values = resolve_rule_metric_windows(
        instant,
        "TODAY",
        [
            account("Pacific/Kiritimati"),
            account("America/Los_Angeles", str(UUID(int=2))),
        ],
    )
    assert [v.local_today for v in values] == [date(2026, 1, 1), date(2025, 12, 31)]
    assert all(v.evaluated_at is instant for v in values)


@pytest.mark.parametrize("hour", [5, 6])
def test_dst_fold_is_same_business_date_at_both_real_instants(hour):
    value = resolve_rule_metric_window(
        datetime(2024, 11, 3, hour, 30, tzinfo=UTC), "LAST_3D", account()
    )
    assert value.date_from == date(2024, 11, 1)
    assert value.date_to == date(2024, 11, 3)


@pytest.mark.parametrize("hour", [6, 7])
def test_dst_gap_uses_real_instant_without_constructing_nonexistent_wall_time(hour):
    value = resolve_rule_metric_window(
        datetime(2024, 3, 10, hour, 30, tzinfo=UTC), "YESTERDAY", account()
    )
    assert value.date_from == value.date_to == date(2024, 3, 9)


def test_leap_day_and_year_transition_are_calendar_days():
    value = resolve_rule_metric_window(datetime(2024, 3, 1, tzinfo=UTC), "LAST_3D", account("UTC"))
    assert (value.date_from, value.date_to) == (date(2024, 2, 28), date(2024, 3, 1))
    value = resolve_rule_metric_window(datetime(2026, 1, 1, tzinfo=UTC), "LAST_7D", account("UTC"))
    assert value.date_from == date(2025, 12, 26)


def test_international_date_line_skipped_day_is_calendar_label_not_claimed_zero_fact():
    value = resolve_rule_metric_window(
        datetime(2011, 12, 30, 12, tzinfo=UTC), "LAST_3D", account("Pacific/Apia")
    )
    assert value.local_today == date(2011, 12, 31)
    assert value.date_from == date(2011, 12, 29)
    assert not hasattr(value, "complete") and not hasattr(value, "ready")


@pytest.mark.parametrize(
    "zone", [None, "", "Asia/NoSuchCity", "UTC+08:00", " Asia/Shanghai", "x" * 65]
)
def test_bad_timezone_never_falls_back_to_utc(zone):
    with pytest.raises(RuleMetricWindowError) as caught:
        resolve_rule_metric_window(datetime(2026, 1, 1, tzinfo=UTC), "TODAY", account(zone))
    assert caught.value.reason_code == "TIMEZONE_INVALID"


@pytest.mark.parametrize(
    "instant",
    [
        None,
        "2026-01-01T00:00:00Z",
        datetime(2026, 1, 1),
        datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_input_must_be_explicit_utc_instant(instant):
    with pytest.raises(RuleMetricWindowError) as caught:
        resolve_rule_metric_window(instant, "TODAY", account())
    assert caught.value.reason_code == "EVALUATION_INSTANT_INVALID"


def test_zoneinfo_utc_is_accepted_without_reading_current_clock():
    instant = datetime(2024, 2, 29, 23, 59, 59, 999999, tzinfo=ZoneInfo("UTC"))
    assert resolve_rule_metric_window(instant, "TODAY", account("UTC")).date_to == date(2024, 2, 29)


@pytest.mark.parametrize("window", ["LAST3", "LAST7", "", None, [], "last_3d"])
def test_only_original_rule_window_enum(window):
    with pytest.raises(RuleMetricWindowError) as caught:
        resolve_rule_metric_window(datetime(2026, 1, 1, tzinfo=UTC), window, account())
    assert caught.value.reason_code == "WINDOW_INVALID"


@pytest.mark.parametrize(
    "instant,window,zone",
    [
        (datetime.min.replace(tzinfo=UTC), "YESTERDAY", "UTC"),
        (datetime.min.replace(tzinfo=UTC), "LAST_7D", "UTC"),
        (datetime.min.replace(tzinfo=UTC), "TODAY", "America/New_York"),
        (datetime.max.replace(tzinfo=UTC), "TODAY", "Pacific/Kiritimati"),
    ],
)
def test_date_arithmetic_or_local_conversion_overflow_fails_explicitly(instant, window, zone):
    with pytest.raises(RuleMetricWindowError) as caught:
        resolve_rule_metric_window(instant, window, account(zone))
    assert caught.value.reason_code == "WINDOW_DATE_OVERFLOW"


def test_date_extrema_that_do_not_overflow_are_retained():
    assert (
        resolve_rule_metric_window(
            datetime.min.replace(tzinfo=UTC), "TODAY", account("UTC")
        ).date_to
        == date.min
    )
    assert (
        resolve_rule_metric_window(
            datetime.max.replace(tzinfo=UTC), "TODAY", account("UTC")
        ).date_to
        == date.max
    )


def test_batch_is_bounded_ordered_unique_and_all_or_error():
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    accounts = [account("UTC", str(UUID(int=i))) for i in range(1, 201)]
    values = resolve_rule_metric_windows(instant, "LAST_7D", accounts)
    assert len(values) == 200 and [v.account_id for v in values] == [v.account_id for v in accounts]
    assert all(v.evaluated_at is instant for v in values)
    assert resolve_rule_metric_windows(instant, "TODAY", []) == ()
    for invalid in (accounts + [account()], iter(accounts)):
        with pytest.raises(RuleMetricWindowError) as caught:
            resolve_rule_metric_windows(instant, "TODAY", invalid)
        assert caught.value.reason_code == "WINDOW_BATCH_LIMIT"
    with pytest.raises(RuleMetricWindowError) as caught:
        resolve_rule_metric_windows(instant, "TODAY", [account(), account()])
    assert caught.value.reason_code == "DUPLICATE_ACCOUNT"


@pytest.mark.parametrize("identifier", [None, "x", "0" * 32, "{" + ACCOUNT + "}"])
def test_internal_account_requires_full_uuid(identifier):
    with pytest.raises(RuleMetricWindowError) as caught:
        resolve_rule_metric_window(
            datetime(2026, 1, 1, tzinfo=UTC), "TODAY", account("UTC", identifier)
        )
    assert caught.value.reason_code == "ACCOUNT_ID_INVALID"
