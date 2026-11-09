"""原Metrics纯结果/质量/排序参考；不含HTTP、MySQL、来源授权或容量验收。"""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from functools import cmp_to_key
from uuid import uuid4

import pytest

from orbit_api.errors import OrbitError
from orbit_api.metrics_aggregation import MetricGroup
from orbit_api.metrics_query_result import (
    CoverageAccumulator,
    DisplayContribution,
    DisplayReducer,
    MetricResultRow,
    MetricResultTotal,
    ResultGroupKey,
    compare_metric_rows,
    coverage_text,
    metrics_page,
)
from orbit_api.metrics_query_result_contract import QuerySourceIdentity

TENANT, PROFILE, ENTITY, OWNER, TEAM, CHANNEL, PUBLICATION = (str(uuid4()) for _ in range(7))
NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)
VALUES = {
    "spend": "100",
    "impressions": "1000",
    "clicks": "10",
    "registrations": "3",
    "purchases": "2",
    "purchase_value": "250",
}


def group(**changes):
    return ResultGroupKey(
        **{
            "tenant_id": TENANT,
            "dataset": "AD",
            "entity_id": ENTITY,
            "currency": "USD",
            "profile_id": PROFILE,
            "profile_version": "observed-v001",
            "business_date": None,
            **changes,
        }
    )


def display(**changes):
    return DisplayContribution(
        **{
            "entity_id": ENTITY,
            "name": "真实历史广告",
            "business_date": date(2026, 1, 1),
            "capture_sequence": 120,
            "observed_at": NOW - timedelta(minutes=1),
            "snapshot_id": str(uuid4()),
            "owner_team_id": TEAM,
            "operator_user_id": OWNER,
            "channel_id": CHANNEL,
            "product_name_snapshot": "历史产品",
            **changes,
        }
    )


def built_row(*, source_values=None, age=timedelta(minutes=1), key=None):
    result = MetricResultRow(key or group())
    result.display.add(
        display(
            entity_id=result.group.entity_id,
            business_date=result.group.business_date or date(2026, 1, 1),
        )
    )
    result.add_values(
        result.group.metric_group(), VALUES if source_values is None else source_values
    )
    result.coverage.add_unit(complete=True, critical_complete=True, observed_at=NOW - age)
    return result.finish(now=NOW, account_count=1, ad_count=1)


def built_total(*, missing=False):
    result = MetricResultTotal(MetricGroup(TENANT, "USD", PROFILE, "observed-v001"))
    result.add_values(result.group, VALUES)
    result.coverage.add_unit(
        complete=True, critical_complete=True, observed_at=NOW - timedelta(minutes=1)
    )
    if missing:
        result.coverage.add_unit(complete=False, critical_complete=False, observed_at=None)
    return result.finish(now=NOW, account_count=1, ad_count=1)


def page(**changes):
    return metrics_page(
        **{
            "source": QuerySourceIdentity(
                TENANT, PUBLICATION, 12, PROFILE, "observed-v001", "a" * 64, "ISOLATED_TEST"
            ),
            "query_snapshot_id": str(uuid4()),
            "scope_version": 1,
            "data_as_of": NOW,
            "missing_count": 0,
            "items": [built_row()],
            "totals": [built_total()],
            "next_cursor": None,
            "page_size": 20,
            **changes,
        }
    )


@pytest.mark.parametrize("dataset", ["ACCOUNT", "CAMPAIGN", "ADSET", "AD"])
@pytest.mark.parametrize("business_date", [None, date(2026, 1, 1)])
def test_all_first_phase_datasets_support_summary_and_account_local_day_without_extra_groups(
    dataset, business_date
):
    row = built_row(key=group(dataset=dataset, business_date=business_date))
    assert len(row) == 15 and len(row["values"]) == 12
    assert row["entity_id"] == ENTITY and row["business_date"] == (
        business_date.isoformat() if business_date else None
    )
    assert row["values"] | {} == {
        **VALUES,
        "usage": None,
        "roas": "2.5",
        "cpm": "100",
        "ctr": "1",
        "cpc": "10",
        "cpa": "50",
    }


@pytest.mark.parametrize(
    "field", ["owner_team_id", "operator_user_id", "channel_id", "product_name_snapshot"]
)
@pytest.mark.parametrize("mixed", [None, "different"])
def test_nullable_metadata_is_single_only_when_all_real_contributions_agree(field, mixed):
    reducer = DisplayReducer(group())
    first = display()
    reducer.add(first)
    value = (
        None
        if mixed is None
        else (str(uuid4()) if field != "product_name_snapshot" else "另一产品")
    )
    reducer.add(replace(first, **{field: value}))
    result = reducer.finish()
    assert result[field] is None
    assert all(
        result[key] == getattr(first, key)
        for key in ("owner_team_id", "operator_user_id", "channel_id", "product_name_snapshot")
        if key != field
    )


def test_latest_name_uses_true_day_capture_observation_and_snapshot_order():
    reducer = DisplayReducer(group())
    old = display(name="ZZZ旧名", business_date=date(2026, 1, 1), capture_sequence=999)
    new = display(name="AAA新名", business_date=date(2026, 1, 2), capture_sequence=1)
    reducer.add(old)
    reducer.add(new)
    assert reducer.finish()["name"] == "AAA新名"
    newer = replace(new, capture_sequence=2, name="真实更高采集版本")
    reducer.add(newer)
    assert reducer.finish()["name"] == "真实更高采集版本"
    last = replace(newer, observed_at=NOW, name="实际后观察名")
    reducer.add(last)
    assert reducer.finish()["name"] == "实际后观察名"


def test_same_name_version_conflict_is_not_input_order_and_does_not_half_update_nullable_metadata():
    reducer = DisplayReducer(group())
    original = display()
    reducer.add(original)
    with pytest.raises(OrbitError):
        reducer.add(replace(original, name="矛盾原文", channel_id=None))
    assert reducer.finish()["name"] == original.name and reducer.finish()["channel_id"] == CHANNEL


def test_full_old_name_preserved_and_only_selected_projection_over_255_is_503():
    reducer = DisplayReducer(group())
    reducer.add(display(name="旧" * 10000))
    reducer.add(display(name="实际新名称", business_date=date(2026, 1, 2)))
    assert reducer.finish()["name"] == "实际新名称"
    reducer.add(display(name="新" * 256, business_date=date(2026, 1, 3)))
    with pytest.raises(OrbitError):
        reducer.finish()


@pytest.mark.parametrize(
    "complete,expected,text",
    [
        (0, 0, "0"),
        (0, 2, "0"),
        (1, 3, "0.333333"),
        (9999999, 10000000, "0.999999"),
        (10000000, 10000000, "1"),
        (1000000, 1000001, "0.999999"),
    ],
)
def test_coverage_six_places_down_never_promotes_one_missing_to_one(complete, expected, text):
    assert coverage_text(complete, expected) == text


@pytest.mark.parametrize("complete,expected", [(True, 1), (1, False), (3, 2), (-1, 2), (1.0, 3)])
def test_coverage_rejects_false_numeric_types_or_invalid_counts(complete, expected):
    with pytest.raises(OrbitError):
        coverage_text(complete, expected)


@pytest.mark.parametrize(
    "condition,quality,coverage,missing,ratios",
    [
        ("empty", "UNKNOWN", "0", 0, False),
        ("all-missing", "UNKNOWN", "0", 1, False),
        ("partial", "PARTIAL", "0.5", 1, False),
        ("critical-missing", "PARTIAL", "1", 0, False),
        ("exact-30", "COMPLETE", "1", 0, True),
        ("stale", "STALE", "1", 0, False),
        ("partial-stale", "PARTIAL", "0.5", 1, False),
    ],
)
def test_quality_precedence_and_exact_thirty_minute_boundary(
    condition, quality, coverage, missing, ratios
):
    counter = CoverageAccumulator()
    if condition != "empty":
        complete = condition != "all-missing"
        age = (
            timedelta(minutes=30)
            if condition == "exact-30"
            else timedelta(minutes=31)
            if condition in {"stale", "partial-stale"}
            else timedelta(minutes=1)
        )
        counter.add_unit(
            complete=complete,
            critical_complete=complete and condition != "critical-missing",
            observed_at=NOW - age if complete else None,
        )
    if condition in {"partial", "partial-stale"}:
        counter.add_unit(complete=False, critical_complete=False, observed_at=None)
    result = counter.finish(NOW)
    assert (result.quality, result.coverage, result.missing_count, result.ratios_allowed) == (
        quality,
        coverage,
        missing,
        ratios,
    )


def test_stale_keeps_additive_sources_but_all_derived_ratios_are_null():
    row = built_row(age=timedelta(minutes=30, microseconds=1))
    assert row["quality"] == "STALE" and row["values"]["spend"] == "100"
    assert all(
        row["values"][name] is None for name in ("roas", "cpm", "ctr", "cpc", "cpa", "usage")
    )


def test_unexpected_missing_critical_source_cannot_be_complete_despite_good_unit_flag():
    row = built_row(source_values=VALUES | {"purchase_value": None})
    assert row["quality"] == "PARTIAL" and row["values"]["purchase_value"] is None
    assert row["values"]["spend"] == "100" and row["values"]["roas"] is None


def test_ratio_uses_aggregate_sources_not_average_and_cpa_uses_purchases():
    result = MetricResultRow(group())
    result.display.add(display())
    result.add_values(result.group.metric_group(), VALUES)
    result.add_values(
        result.group.metric_group(),
        VALUES | {"spend": "300", "purchase_value": "100", "purchases": "3"},
    )
    result.coverage.add_unit(complete=True, critical_complete=True, observed_at=NOW)
    row = result.finish(now=NOW, account_count=1, ad_count=2)
    assert row["values"]["roas"] == "0.875" and row["values"]["cpa"] == "80"


def test_money_overflow_and_float_are_503_not_rounded_or_coerced():
    with pytest.raises(OrbitError):
        built_row(source_values=VALUES | {"spend": 100.0})
    result = MetricResultRow(group())
    result.add_values(result.group.metric_group(), VALUES | {"spend": "9" * 28})
    with pytest.raises(OrbitError):
        result.add_values(result.group.metric_group(), VALUES | {"spend": "1"})


def test_total_is_original_eight_fields_and_missing_totals_do_not_come_from_page():
    summary = built_total(missing=True)
    assert len(summary) == 8 and summary["missing_count"] == 1 and summary["coverage"] == "0.5"
    assert summary["values"]["spend"] == "100" and summary["values"]["roas"] is None
    response = page(items=[], totals=[summary], missing_count=1)
    assert (
        response["items"] == []
        and response["totals"][0] == summary
        and response["missing_count"] == 1
    )


@pytest.mark.parametrize(
    "sort", ["spend", "impressions", "clicks", "purchases", "roas", "cpm", "name"]
)
@pytest.mark.parametrize("direction", ["ASC", "DESC"])
def test_all_sort_fields_both_directions_have_stable_ties_and_null_last(sort, direction):
    first = built_row()
    second = built_row(key=group(entity_id=str(uuid4())))
    first, second = sorted([first, second], key=lambda item: item["entity_id"])
    assert compare_metric_rows(first, second, sort=sort, direction=direction) == -1
    if sort != "name":
        missing = second | {"values": second["values"] | {sort: None}}
        assert compare_metric_rows(first, missing, sort=sort, direction=direction) == -1
        assert compare_metric_rows(missing, first, sort=sort, direction=direction) == 1


def test_numeric_sort_is_decimal_not_lexical_and_name_binary_keeps_trailing_space():
    first = built_row()
    second = first | {"values": first["values"] | {"spend": "20"}}
    assert compare_metric_rows(first, second, sort="spend", direction="ASC") == 1
    assert (
        compare_metric_rows(
            first | {"name": "A"}, first | {"name": "A "}, sort="name", direction="ASC"
        )
        == -1
    )


@pytest.mark.parametrize("size", [20, 50, 100, 200])
def test_page_size_does_not_change_totals_and_byte_short_page_can_still_have_cursor(size):
    response = page(page_size=size, next_cursor="opaque-signed-next", items=[built_row()])
    assert len(response) == 8 and len(response["items"]) == 1
    assert response["next_cursor"] == "opaque-signed-next" and response["totals"] == [built_total()]


@pytest.mark.parametrize(
    "changes",
    [
        {"page_size": True},
        {"page_size": 21},
        {"scope_version": 0},
        {"missing_count": 1},
        {"totals": []},
        {"totals": [built_total(), built_total()]},
        {"items": [built_row(), built_row()]},
        {"items": [built_row() | {"tenant_id": str(uuid4())}]},
    ],
)
def test_complete_response_rejects_size_scope_duplicate_cross_tenant_or_missing_total(changes):
    with pytest.raises(OrbitError):
        page(**changes)


def test_empty_expected_selection_uses_empty_arrays_not_fake_zero_metric_row():
    response = page(items=[], totals=[], missing_count=0)
    assert response["items"] == response["totals"] == [] and response["missing_count"] == 0


def test_constant_memory_reducers_do_not_collect_entire_history_or_global_result_sets():
    reducer = DisplayReducer(group())
    for index in range(1001):
        reducer.add(display(capture_sequence=index + 1))
    assert len(reducer._values) == 4 and len(reducer._mixed) <= 4
    assert "history" not in vars(reducer)
    rows = [built_row(key=group(entity_id=str(uuid4()))) for _ in range(21)]
    reference = sorted(
        rows, key=cmp_to_key(lambda a, b: compare_metric_rows(a, b, sort="name", direction="ASC"))
    )
    assert [item["entity_id"] for item in reference] == sorted(item["entity_id"] for item in rows)


@pytest.mark.parametrize(
    "changes",
    [
        {"currency": "EUR"},
        {"tenant_id": str(uuid4())},
        {"profile_id": str(uuid4())},
        {"profile_version": "different-version"},
    ],
)
def test_explicit_source_group_rejects_cross_currency_tenant_profile_version(changes):
    result = MetricResultRow(group())
    source = replace(result.group.metric_group(), **changes)
    with pytest.raises(OrbitError):
        result.add_values(source, VALUES)
    assert result._value_rows == 0


def test_values_cannot_exist_outside_any_independent_expected_unit():
    row = MetricResultRow(group())
    row.display.add(display())
    row.add_values(row.group.metric_group(), VALUES)
    with pytest.raises(OrbitError):
        row.finish(now=NOW, account_count=1, ad_count=1)
    total = MetricResultTotal(MetricGroup(TENANT, "USD", PROFILE, "observed-v001"))
    total.add_values(total.group, VALUES)
    with pytest.raises(OrbitError):
        total.finish(now=NOW, account_count=1, ad_count=1)


@pytest.mark.parametrize("bad_day", ["not-a-day", "2026-1-01", "2026-02-30"])
def test_outbound_page_rejects_bad_frozen_business_day(bad_day):
    with pytest.raises(OrbitError):
        page(items=[built_row() | {"business_date": bad_day}])
