"""日事实归属冻结边界：异常日内不猜零点拥有者，迟到指标不重写归属。"""

from datetime import date, datetime

import pytest

from orbit_api.account_details_contract import fact_interval, freeze_attribution


def assignment(start, end=None, owner="first"):
    return {"starts_at": start, "ends_at": end, "owner_user_id": owner, "owner_team_id": "team"}


@pytest.mark.parametrize("day,hours", [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_iana_day_window_obeys_dst_not_utc_24_hours(day, hours):
    start, end = fact_interval(day, "America/New_York", datetime(2026, 11, 8))
    assert (end - start).total_seconds() == hours * 3600


def test_today_window_ends_at_actual_observation_not_future_day_end():
    start, end = fact_interval(date(2026, 3, 8), "America/New_York", datetime(2026, 3, 8, 15))
    assert start == datetime(2026, 3, 8, 5) and end == datetime(2026, 3, 8, 15)


def test_single_complete_interval_can_own_day_and_exact_next_midnight_is_excluded():
    start, end = datetime(2026, 3, 7), datetime(2026, 3, 8)
    value = freeze_attribution(start, end, [assignment(start, end), assignment(end, owner="next")])
    assert value["owner_user_id"] == "first" and value["attribution_reason"] == "COVERED"


@pytest.mark.parametrize(
    "intervals",
    [
        [],
        [assignment(datetime(2026, 3, 7, 12))],
        [assignment(datetime(2026, 3, 7), datetime(2026, 3, 7, 12))],
        [
            assignment(datetime(2026, 3, 7), datetime(2026, 3, 7, 12)),
            assignment(datetime(2026, 3, 7, 12), owner="next"),
        ],
        [assignment(datetime(2026, 3, 7)), assignment(datetime(2026, 3, 7, 12), owner="overlap")],
    ],
)
def test_partial_gap_midday_transfer_or_overlap_does_not_award_whole_day(intervals):
    value = freeze_attribution(datetime(2026, 3, 7), datetime(2026, 3, 8), intervals)
    assert value["owner_user_id"] is None and value["owner_team_id"] is None
    assert value["attribution_reason"].startswith("UNASSIGNED_")


@pytest.mark.parametrize("owner", [None, "original"])
def test_later_metrics_copy_original_owner_and_attribution_version(owner):
    old = {
        "owner_user_id": owner,
        "owner_team_id": "team" if owner else None,
        "attribution_version": 7,
        "attribution_reason": "COVERED" if owner else "UNASSIGNED_NO_COVERAGE",
    }
    new = freeze_attribution(
        datetime(2026, 3, 7),
        datetime(2026, 3, 8),
        [assignment(datetime(2026, 1, 1), owner="changed")],
        old,
    )
    assert new == old and new is not old


def test_empty_observation_window_is_unknown():
    point = datetime(2026, 3, 7)
    assert (
        freeze_attribution(point, point, [assignment(point)])["attribution_reason"]
        == "UNASSIGNED_EMPTY_WINDOW"
    )
