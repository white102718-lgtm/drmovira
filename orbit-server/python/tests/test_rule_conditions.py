"""每个真值组合和所有叶子，独立核Decimal精度，不创建模拟结果。"""

import itertools
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest
from test_rule_contract import parse, sample_rule

from orbit_api.rule_conditions import combine, compile_conditions, evaluate_conditions
from orbit_api.rule_contract import Rule, parse_rule_response


@pytest.mark.parametrize(
    "logic,values",
    tuple(
        itertools.product(("AND", "OR"), itertools.product(("TRUE", "FALSE", "UNKNOWN"), repeat=3))
    ),
)
def test_three_valued_complete_table(logic, values):
    # SQL三值的独立集合真值表，而不是重跑受测函数内部折叠。
    and_table = {
        frozenset({"TRUE"}): "TRUE",
        frozenset({"FALSE"}): "FALSE",
        frozenset({"UNKNOWN"}): "UNKNOWN",
        frozenset({"TRUE", "FALSE"}): "FALSE",
        frozenset({"TRUE", "UNKNOWN"}): "UNKNOWN",
        frozenset({"FALSE", "UNKNOWN"}): "FALSE",
        frozenset({"TRUE", "FALSE", "UNKNOWN"}): "FALSE",
    }
    or_table = {
        frozenset({"TRUE"}): "TRUE",
        frozenset({"FALSE"}): "FALSE",
        frozenset({"UNKNOWN"}): "UNKNOWN",
        frozenset({"TRUE", "FALSE"}): "TRUE",
        frozenset({"TRUE", "UNKNOWN"}): "TRUE",
        frozenset({"FALSE", "UNKNOWN"}): "UNKNOWN",
        frozenset({"TRUE", "FALSE", "UNKNOWN"}): "TRUE",
    }
    assert combine(logic, values) == (and_table if logic == "AND" else or_table)[frozenset(values)]


def tree(metric="spend", operator="EQ", threshold="0"):
    value = sample_rule()
    value["groups"][0]["conditions"][0].update(
        metric=metric, operator=operator, threshold=threshold
    )
    return compile_conditions(parse(value))


@pytest.mark.parametrize(
    "operator,observed,expected",
    [
        ("GT", "1.000001", "TRUE"),
        ("GT", "1", "FALSE"),
        ("GTE", "1.000000", "TRUE"),
        ("GTE", "0.999999", "FALSE"),
        ("LT", "0.999999", "TRUE"),
        ("LT", "1", "FALSE"),
        ("LTE", "1", "TRUE"),
        ("LTE", "1.000001", "FALSE"),
        ("EQ", "1.000000", "TRUE"),
        ("EQ", "1.000001", "FALSE"),
        ("NEQ", "1.000001", "TRUE"),
        ("NEQ", "1.000000", "FALSE"),
    ],
)
def test_all_comparators_exact_decimal(operator, observed, expected):
    result = evaluate_conditions(tree(operator=operator, threshold="1"), {"spend": observed})
    assert result.result == expected
    assert result.conditions[0].value == Decimal(observed)


@pytest.mark.parametrize(
    "value",
    [
        None,
        0,
        True,
        0.0,
        "NaN",
        "Infinity",
        "01",
        "1e3",
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-1"),
    ],
)
def test_unknown_never_becomes_true_for_neq_zero(value):
    result = evaluate_conditions(tree(operator="NEQ"), {"spend": value})
    assert result.result == "UNKNOWN"
    assert result.conditions[0].value is None
    assert result.conditions[0].reason_code == (
        "METRIC_MISSING" if value is None else "METRIC_INVALID"
    )


def test_missing_metric_and_fractional_count_unknown():
    assert evaluate_conditions(tree(), {}).result == "UNKNOWN"
    assert evaluate_conditions(tree(metric="clicks"), {"clicks": "1.000001"}).result == "UNKNOWN"


def test_no_short_circuit_stable_indices_all_groups():
    value = sample_rule()
    value["groups"] = [
        {
            "logic": "AND",
            "conditions": [
                {"metric": "spend", "operator": "GT", "threshold": "100"},
                {"metric": "clicks", "operator": "NEQ", "threshold": "0"},
            ],
        },
        {
            "logic": "OR",
            "conditions": [
                {"metric": "ctr", "operator": "LTE", "threshold": "1"},
                {"metric": "purchases", "operator": "GT", "threshold": "0"},
            ],
        },
    ]
    result = evaluate_conditions(compile_conditions(parse(value)), {"spend": "10", "ctr": "0.5"})
    assert result.result == "FALSE"
    assert result.groups == ("FALSE", "TRUE")
    assert [r.condition_index for r in result.conditions] == [0, 1, 2, 3]
    assert [r.result for r in result.conditions] == ["FALSE", "UNKNOWN", "TRUE", "UNKNOWN"]


def test_count_above_js_safe_precision_and_equal_scale():
    result = evaluate_conditions(
        tree("impressions", "EQ", "9007199254740993"),
        {
            "impressions": Decimal("9007199254740993.000000"),
        },
    )
    assert result.result == "TRUE"
    assert (
        evaluate_conditions(
            tree("impressions", "EQ", "9007199254740993"),
            {
                "impressions": "9007199254740992",
            },
        ).result
        == "FALSE"
    )


def test_compiled_tree_detached_and_frozen():
    value = parse(sample_rule())
    compiled = compile_conditions(value)
    value.groups[0].conditions[0].threshold = "999"
    value.groups.clear()
    assert compiled.groups[0].conditions[0].threshold == 0
    with pytest.raises(FrozenInstanceError):
        compiled.logic = "OR"


def test_same_threshold_evaluates_each_account_currency_independently():
    compiled = tree(threshold="10", operator="GTE")
    assert evaluate_conditions(compiled, {"spend": "11"}).result == "TRUE"  # USD对象
    assert evaluate_conditions(compiled, {"spend": "9"}).result == "FALSE"  # EUR对象
    # 没有跨对象SUM或汇率输入，也不把两对象结果合并成一个指标值。


@pytest.mark.parametrize("value", [Decimal("1E+999999"), Decimal("0.0000001"), "9" * 29])
def test_observation_numeric_expansion_is_bounded(value):
    assert evaluate_conditions(tree(), {"spend": value}).result == "UNKNOWN"


def test_rule_response_can_compile_without_misreading_id_as_rulewrite_unknown_field():
    from test_rule_contract import ID

    rule = parse_rule_response(
        Rule, {**sample_rule(), "id": ID, "revision": 1, "state": "DRAFT", "next_run_at": None}
    )
    assert evaluate_conditions(compile_conditions(rule), {"spend": "0"}).result == "TRUE"


def test_negative_zero_decimal_is_not_legal_unsigned_metric_text():
    assert evaluate_conditions(tree(), {"spend": Decimal("-0")}).result == "UNKNOWN"
