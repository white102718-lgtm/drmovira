"""真实ZoneInfo时间规则的纯计算；无调度进程、无数据库运行证据。"""

from datetime import UTC, datetime, timedelta

import pytest

import orbit_api.rule_schedule as core
from orbit_api.rule_schedule import latest_due, preview_schedule


def moment(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def schedule(**updates):
    value = {
        "frequency": "DAILY",
        "interval_minutes": None,
        "time_of_day": "10:00",
        "weekday": None,
        "timezone": "Asia/Shanghai",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
    }
    value.update(updates)
    return value


def test_inclusive_start_end_strict_after_and_limits():
    definition = schedule(start_date="2026-01-01", end_date="2026-01-02")
    result = preview_schedule(definition, moment("2025-12-31T00:00:00Z"), 50)
    assert result.slots == (moment("2026-01-01T02:00:00Z"), moment("2026-01-02T02:00:00Z"))
    assert preview_schedule(definition, result.slots[0], 50).slots == result.slots[1:]
    assert not preview_schedule(definition, moment("2026-01-03T00:00:00Z")).slots


@pytest.mark.parametrize("limit", [0, 51, True, 1.0, "1"])
def test_preview_bounded_limit(limit):
    with pytest.raises(ValueError):
        preview_schedule(schedule(), moment("2026-01-01T00:00:00Z"), limit)


def test_new_york_spring_gap_skips_not_moves_and_audits_at_transition():
    definition = schedule(
        timezone="America/New_York",
        time_of_day="02:30",
        start_date="2026-03-07",
        end_date="2026-03-09",
    )
    result = preview_schedule(definition, moment("2026-03-07T00:00:00Z"))
    assert result.slots == (moment("2026-03-07T07:30:00Z"), moment("2026-03-09T06:30:00Z"))
    assert result.skipped_local_times == (datetime(2026, 3, 8, 2, 30),)
    due = latest_due(
        definition, moment("2026-03-08T06:00:00Z"), moment("2026-03-08T07:10:00Z"), enabled=True
    )
    assert due.slot is None
    assert due.skipped_local_times == result.skipped_local_times


def test_fall_overlap_earlier_utc_once_even_when_after_first_occurrence():
    definition = schedule(
        timezone="America/New_York",
        time_of_day="01:30",
        start_date="2026-11-01",
        end_date="2026-11-02",
    )
    first = moment("2026-11-01T05:30:00Z")
    assert preview_schedule(definition, moment("2026-11-01T00:00:00Z")).slots[0] == first
    assert preview_schedule(definition, first).slots == (moment("2026-11-02T06:30:00Z"),)
    due = latest_due(definition, first, moment("2026-11-01T06:45:00Z"), enabled=True)
    assert due.slot is None


def test_lord_howe_half_hour_gap_and_overlap():
    spring = schedule(
        timezone="Australia/Lord_Howe",
        time_of_day="02:15",
        start_date="2026-10-04",
        end_date="2026-10-05",
    )
    result = preview_schedule(spring, moment("2026-10-03T00:00:00Z"))
    assert result.skipped_local_times == (datetime(2026, 10, 4, 2, 15),)
    assert result.slots == (moment("2026-10-04T15:15:00Z"),)
    fall = schedule(
        timezone="Australia/Lord_Howe",
        time_of_day="01:45",
        start_date="2026-04-05",
        end_date="2026-04-05",
    )
    assert preview_schedule(fall, moment("2026-04-04T00:00:00Z")).slots == (
        moment("2026-04-04T14:45:00Z"),
    )


def test_apia_missing_entire_day_and_midnight_gap_anchor():
    daily = schedule(timezone="Pacific/Apia", start_date="2011-12-29", end_date="2011-12-31")
    result = preview_schedule(daily, moment("2011-12-28T00:00:00Z"))
    assert result.slots == (moment("2011-12-29T20:00:00Z"), moment("2011-12-30T20:00:00Z"))
    assert result.skipped_local_times == (datetime(2011, 12, 30, 10),)
    interval = schedule(
        frequency="INTERVAL",
        interval_minutes=30,
        time_of_day=None,
        timezone="America/Sao_Paulo",
        start_date="2018-11-04",
        end_date="2018-11-04",
    )
    assert preview_schedule(interval, moment("2018-11-04T00:00:00Z"), 1).slots == (
        moment("2018-11-04T03:00:00Z"),
    )


@pytest.mark.parametrize(
    "start,end,expected",
    [
        ("2026-03-08", "2026-03-08", 23 * 4),
        ("2026-11-01", "2026-11-01", 25 * 4),
    ],
)
def test_interval_elapsed_minutes_dst_exact_missed_slots(start, end, expected):
    definition = schedule(
        frequency="INTERVAL",
        interval_minutes=15,
        time_of_day=None,
        timezone="America/New_York",
        start_date=start,
        end_date=end,
    )
    anchor = moment("2026-03-08T05:00:00Z" if "03-08" in start else "2026-11-01T04:00:00Z")
    due = latest_due(
        definition,
        anchor - timedelta(microseconds=1),
        anchor + timedelta(minutes=15 * (expected - 1)),
        enabled=True,
    )
    assert due.slot == anchor + timedelta(minutes=15 * (expected - 1))
    assert due.missed_slots == expected - 1
    preview = preview_schedule(definition, anchor - timedelta(microseconds=1), 50)
    assert all(
        b - a == timedelta(minutes=15)
        for a, b in zip(preview.slots, preview.slots[1:], strict=False)
    )


def test_interval_not_reanchored_midnight_non_dividing_day():
    definition = schedule(
        frequency="INTERVAL",
        interval_minutes=1000,
        time_of_day=None,
        timezone="UTC",
        start_date="2026-01-01",
        end_date="2026-01-03",
    )
    assert preview_schedule(definition, moment("2025-12-31T00:00:00Z")).slots == tuple(
        moment("2026-01-01T00:00:00Z") + timedelta(minutes=1000 * n) for n in range(5)
    )


def test_weekly_iso_weekday_and_latest_recovery_exact_omissions():
    definition = schedule(
        frequency="WEEKLY", weekday=1, start_date="2026-01-01", end_date="2026-01-31"
    )
    expected = tuple(moment(f"2026-01-{day:02d}T02:00:00Z") for day in (5, 12, 19, 26))
    assert preview_schedule(definition, moment("2026-01-01T00:00:00Z")).slots == expected
    due = latest_due(definition, moment("2026-01-01T00:00:00Z"), expected[-1], enabled=True)
    assert due.slot == expected[-1]
    assert due.missed_slots == 3
    assert latest_due(definition, expected[0], expected[-1], enabled=True).missed_slots == 2


def test_disabled_expired_and_no_future_catchup():
    definition = schedule()
    last = moment("2026-01-01T00:00:00Z")
    assert latest_due(definition, last, moment("2026-01-20T00:00:00Z"), enabled=False).slot is None
    assert latest_due(definition, last, moment("2026-01-31T16:00:00Z"), enabled=True).slot is None
    with pytest.raises(ValueError):
        latest_due(definition, last, last - timedelta(seconds=1), enabled=True)
    with pytest.raises(ValueError):
        preview_schedule(definition, datetime(2026, 1, 1))


def test_bounded_complexity_366_days_without_interval_enumeration(monkeypatch):
    calls = 0
    original = core._wall_instants

    def counted(*args):
        nonlocal calls
        calls += 1
        return original(*args)

    monkeypatch.setattr(core, "_wall_instants", counted)
    definition = schedule(
        frequency="INTERVAL",
        interval_minutes=15,
        time_of_day=None,
        timezone="UTC",
        start_date="2024-01-01",
        end_date="2024-12-31",
    )
    due = latest_due(
        definition, moment("2023-12-31T23:59:59Z"), moment("2024-12-31T23:59:59Z"), enabled=True
    )
    assert due.missed_slots == 366 * 96 - 1
    assert calls == 2  # 只确定首尾，遗漏数用整数除法，不遍历35136个slot。
    calls = 0
    definition.update(frequency="DAILY", interval_minutes=None, time_of_day="10:00")
    due = latest_due(
        definition, moment("2023-12-31T23:59:59Z"), moment("2024-12-31T23:59:59Z"), enabled=True
    )
    assert due.missed_slots == 365
    assert calls <= 368


def test_subsecond_after_is_exclusive_without_rounding_back():
    definition = schedule(
        frequency="INTERVAL", interval_minutes=15, time_of_day=None, timezone="UTC"
    )
    anchor = moment("2026-01-01T00:00:00Z")
    assert preview_schedule(definition, anchor - timedelta(microseconds=1), 1).slots == (anchor,)
    assert preview_schedule(definition, anchor + timedelta(microseconds=1), 1).slots == (
        anchor + timedelta(minutes=15),
    )
    assert preview_schedule(definition, anchor.astimezone(UTC), 1).slots[0] > anchor


def test_terminal_calendar_end_does_not_wrap_or_escape_local_date():
    definition = schedule(
        frequency="INTERVAL",
        interval_minutes=1440,
        time_of_day=None,
        start_date="9999-12-31",
        end_date="9999-12-31",
    )
    assert preview_schedule(definition, moment("9999-12-30T00:00:00Z"), 50).slots == (
        moment("9999-12-30T16:00:00Z"),
    )


def test_skipped_complete_interval_day_has_zero_slots():
    definition = schedule(
        frequency="INTERVAL",
        interval_minutes=15,
        time_of_day=None,
        timezone="Pacific/Apia",
        start_date="2011-12-30",
        end_date="2011-12-30",
    )
    assert preview_schedule(definition, moment("2011-12-28T00:00:00Z"), 50).slots == ()
