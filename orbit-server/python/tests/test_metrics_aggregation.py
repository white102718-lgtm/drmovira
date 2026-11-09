"""核对原分子/分母口径，覆盖未知、跨组、舍入和大金额精度。"""

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from orbit_api.errors import OrbitError
from orbit_api.metrics_aggregation import ADDITIVE_NAMES, MetricAccumulator, MetricGroup
from orbit_api.metrics_contract import MetricValues

GROUP = MetricGroup("tenant-a", "USD", "profile-a", "version-1")


def values(**changes):
    return dict.fromkeys(ADDITIVE_NAMES, "0") | changes


def test_weighted_ratios_use_aggregate_numerators_and_purchases():
    accumulator = MetricAccumulator(GROUP)
    accumulator.add(
        GROUP,
        values(
            spend="1",
            impressions="10",
            clicks="1",
            registrations="50",
            purchases="1",
            purchase_value="10",
        ),
    )
    accumulator.add(
        GROUP,
        values(
            spend="99",
            impressions="90",
            clicks="9",
            registrations="950",
            purchases="4",
            purchase_value="90",
        ),
    )
    result = accumulator.finish(ratios_allowed=True)
    assert result == values(
        spend="100",
        impressions="100",
        clicks="10",
        registrations="1000",
        purchases="5",
        purchase_value="100",
    ) | {"roas": "1", "cpm": "1000", "ctr": "10", "cpc": "10", "cpa": "20", "usage": None}
    assert MetricValues.model_validate(result).model_dump() == result


@pytest.mark.parametrize("name", ADDITIVE_NAMES)
def test_missing_any_part_keeps_column_unknown(name):
    accumulator = MetricAccumulator(GROUP)
    accumulator.add(GROUP, values(**{name: None}))
    accumulator.add(GROUP, values(**{name: "2"}))
    result = accumulator.finish(ratios_allowed=True)
    assert result[name] is None
    if name != "registrations":
        assert all(result[key] is None for key in ("roas", "cpm", "ctr", "cpc", "cpa"))


def test_no_rows_is_unknown_but_explicit_complete_zero_has_real_zero_numerators():
    accumulator = MetricAccumulator(GROUP)
    assert set(accumulator.finish(ratios_allowed=True).values()) == {None}
    accumulator.add(GROUP, values())
    result = accumulator.finish(ratios_allowed=True)
    assert all(result[name] == "0" for name in ADDITIVE_NAMES)
    assert all(result[name] is None for name in ("roas", "cpm", "ctr", "cpc", "cpa", "usage"))


def test_quality_gate_is_explicit_and_does_not_destroy_base_values():
    accumulator = MetricAccumulator(GROUP)
    accumulator.add(GROUP, values(spend="2", purchase_value="3"))
    result = accumulator.finish(ratios_allowed=False)
    assert result["spend"] == "2" and result["purchase_value"] == "3"
    assert result["roas"] is None
    with pytest.raises(OrbitError):
        accumulator.finish(ratios_allowed=1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "other"),
        ("currency", "EUR"),
        ("profile_id", "other"),
        ("profile_version", "version-2"),
    ],
)
def test_cross_group_rejected_before_mutation(field, value):
    accumulator = MetricAccumulator(GROUP)
    with pytest.raises(OrbitError):
        accumulator.add(replace(GROUP, **{field: value}), values(spend="1"))
    assert set(accumulator.finish(ratios_allowed=True).values()) == {None}


@pytest.mark.parametrize(
    "bad", [0, True, 1.5, Decimal("1"), "01", "-1", "1e2", "1.0000001", "NaN", "9" * 29]
)
def test_bad_numerator_does_not_partly_add_the_row(bad):
    accumulator = MetricAccumulator(GROUP)
    accumulator.add(GROUP, values(spend="2"))
    with pytest.raises(OrbitError) as failure:
        accumulator.add(GROUP, values(spend="7", purchase_value=bad))
    assert failure.value.status == 503
    assert accumulator.finish(ratios_allowed=False)["spend"] == "2"


def test_extra_ratio_or_missing_base_field_rejected():
    accumulator = MetricAccumulator(GROUP)
    for row in (values() | {"roas": "2"}, {"spend": "2"}):
        with pytest.raises(OrbitError):
            accumulator.add(GROUP, row)


def test_decimal_global_precision_never_rounds_large_money():
    accumulator = MetricAccumulator(GROUP)
    with localcontext() as context:
        context.prec = 3
        accumulator.add(GROUP, values(spend="123456789012345678901.123456"))
        accumulator.add(GROUP, values(spend="0.000001"))
        assert accumulator.finish(ratios_allowed=False)["spend"] == "123456789012345678901.123457"


def test_sum_overflow_fails_instead_of_truncating_or_scientific_notation():
    accumulator = MetricAccumulator(GROUP)
    accumulator.add(GROUP, values(spend="9" * 28))
    with pytest.raises(OrbitError):
        accumulator.add(GROUP, values(spend="1"))
    assert accumulator.finish(ratios_allowed=False)["spend"] == "9" * 28


@pytest.mark.parametrize(
    "spend,purchases,expected",
    [("1", "2000000", "0.000001"), ("2", "5000000", "0"), ("1", "1", "1")],
)
def test_final_ratio_half_up_six_decimal_places(spend, purchases, expected):
    accumulator = MetricAccumulator(GROUP)
    accumulator.add(
        GROUP,
        values(spend=spend, impressions="1", clicks="1", purchases=purchases, purchase_value="1"),
    )
    assert accumulator.finish(ratios_allowed=True)["cpa"] == expected


def test_ratio_overflow_is_whole_result_failure():
    accumulator = MetricAccumulator(GROUP)
    accumulator.add(
        GROUP,
        values(
            spend="9" * 28, impressions="0.000001", clicks="1", purchases="1", purchase_value="1"
        ),
    )
    with pytest.raises(OrbitError):
        accumulator.finish(ratios_allowed=True)


def test_finish_repeat_and_chunking_do_not_change_results():
    accumulator = MetricAccumulator(GROUP)
    for _ in range(10000):
        accumulator.add(GROUP, values(spend="0.000001", impressions="1"))
    result = accumulator.finish(ratios_allowed=True)
    assert result["spend"] == "0.01" and result["impressions"] == "10000"
    assert accumulator.finish(ratios_allowed=True) == result
