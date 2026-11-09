"""原Rule DTO边界；不把纯合同通过称为业务引用或模拟验收。"""

import copy
import json
from pathlib import Path

import pytest

from orbit_api.errors import OrbitError
from orbit_api.rule_contract import (
    Condition,
    ConditionGroup,
    ConditionResult,
    EnableRule,
    Rule,
    RulePage,
    RuleReason,
    RuleRun,
    RuleRunPage,
    RuleWrite,
    Schedule,
    Simulation,
    parse_rule_action,
    parse_rule_response,
    parse_rule_write,
    parse_schedule,
)

ID = "11111111-1111-4111-8111-111111111111"


def sample_rule():
    return {
        "name": "规则",
        "ownership": {"owner_user_id": ID, "owner_team_id": ID},
        "target_level": "AD",
        "scope_snapshot_id": ID,
        "logic": "AND",
        "groups": [
            {
                "logic": "AND",
                "conditions": [
                    {
                        "metric": "spend",
                        "operator": "GTE",
                        "threshold": "0",
                    }
                ],
            }
        ],
        "window": "LAST_3D",
        "metric_profile_id": ID,
        "schedule": {
            "frequency": "INTERVAL",
            "interval_minutes": 30,
            "time_of_day": None,
            "weekday": None,
            "timezone": "Asia/Shanghai",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
        "cooldown_minutes": 60,
        "max_daily": 5,
    }


def parse(value):
    return parse_rule_write(json.dumps(value, ensure_ascii=True).encode())


def rejected(value, status, path=None):
    with pytest.raises(OrbitError) as caught:
        parse(value)
    assert caught.value.status == status
    if status == 422:
        assert caught.value.code == "FIELD_VALIDATION_FAILED"
    if path is not None:
        assert caught.value.pointer == path


def test_original_schema_field_sets_no_silent_defaults():
    baseline = json.loads(
        (Path(__file__).parents[2] / "docs/orbit/baseline/contracts/openapi.json").read_text(
            encoding="utf-8"
        )
    )["components"]["schemas"]
    for model, name in [
        (RuleWrite, "RuleWrite"),
        (Schedule, "Schedule"),
        (Condition, "Condition"),
        (ConditionGroup, "ConditionGroup"),
        (Rule, "Rule"),
        (Simulation, "Simulation"),
        (ConditionResult, "ConditionResult"),
        (RuleRun, "RuleRun"),
        (RulePage, "RulePage"),
        (RuleRunPage, "RuleRunPage"),
        (RuleReason, "Reason"),
        (EnableRule, "EnableRule"),
    ]:
        assert set(model.model_fields) == set(baseline[name]["properties"])
        assert all(field.is_required() for field in model.model_fields.values())


def test_valid_normalization_does_not_mutate_input_or_change_case():
    value = sample_rule()
    value["name"] = "  e\u0301规则  "
    before = copy.deepcopy(value)
    result = parse(value)
    assert result.name == "é规则"
    assert value == before
    assert parse({**value, "name": "RULE"}).name != parse({**value, "name": "rule"}).name


@pytest.mark.parametrize("field", list(sample_rule()))
def test_every_rule_key_required(field):
    value = sample_rule()
    del value[field]
    rejected(value, 400, "/" + field)


@pytest.mark.parametrize("field", list(sample_rule()["schedule"]))
def test_all_schedule_keys_even_null_are_required(field):
    value = sample_rule()
    del value["schedule"][field]
    rejected(value, 400, "/schedule/" + field)


@pytest.mark.parametrize(
    "field,value,status",
    [
        ("cooldown_minutes", True, 400),
        ("max_daily", "5", 400),
        ("cooldown_minutes", -1, 422),
        ("cooldown_minutes", 10081, 422),
        ("max_daily", 0, 422),
        ("max_daily", 1001, 422),
        ("target_level", "GROUP", 422),
        ("target_level", 1, 400),
        ("logic", "and", 422),
        ("window", "LAST_30D", 422),
        ("scope_snapshot_id", "not-uuid", 422),
        ("metric_profile_id", None, 400),
        ("name", "", 422),
        ("name", "x" * 81, 422),
        ("name", "x\n", 422),
        ("name", "\ud800", 422),
        ("name", "x\u200b", 422),
        ("name", "x\u2028", 422),
    ],
)
def test_rule_values_and_types(field, value, status):
    body = sample_rule()
    body[field] = value
    rejected(body, status, "/" + field)


def test_codepoint_count_and_zero_cooldown_boundaries():
    value = sample_rule()
    value.update(name="😀" * 80, cooldown_minutes=0, max_daily=1000)
    assert len(parse(value).name) == 80


@pytest.mark.parametrize(
    "raw",
    [
        b'{"name":"a","name":"b"}',
        b"\xff",
        b'{"name":"a\x00"}',
        b"NaN",
        b'{"cooldown_minutes":NaN}',
        b'{"max_daily":Infinity}',
    ],
)
def test_invalid_json_constants_duplicates_utf8(raw):
    with pytest.raises(OrbitError) as caught:
        parse_rule_write(raw)
    assert caught.value.status == 400


def test_nested_unknown_pointer_is_escaped():
    value = sample_rule()
    value["groups"][0]["conditions"][0]["bad~/field"] = "private"
    rejected(value, 400, "/groups/0/conditions/0/bad~0~1field")


@pytest.mark.parametrize(
    "metric,text,valid",
    [
        ("impressions", "9007199254740993", True),
        ("clicks", "1.000000", True),
        ("clicks", "1.000001", False),
        ("spend", "1000000000", True),
        ("spend", "1000000000.000001", False),
        ("roas", "1000000", True),
        ("roas", "1000000.000001", False),
        ("ctr", "100", True),
        ("ctr", "100.000001", False),
        ("spend", "01", False),
        ("spend", "-1", False),
        ("spend", "+1", False),
        ("spend", "1e2", False),
        ("spend", "0.0000001", False),
        ("spend", "1.", False),
        ("spend", " 1", False),
        ("spend", "１２", False),
        ("purchases", "9" * 29, False),
        ("cpa", "NaN", False),
    ],
)
def test_threshold_exact_decimal_ranges(metric, text, valid):
    value = sample_rule()
    value["groups"][0]["conditions"][0].update(metric=metric, threshold=text)
    if valid:
        assert parse(value).groups[0].conditions[0].threshold == text
    else:
        rejected(value, 422, "/groups/0/conditions/0/threshold")


def test_groups_total_and_no_third_layer():
    value = sample_rule()
    leaf = value["groups"][0]["conditions"][0]
    value["groups"] = [{"logic": "OR", "conditions": [leaf] * 10}] * 2
    assert sum(len(g.conditions) for g in parse(value).groups) == 20
    value["groups"].append({"logic": "AND", "conditions": [leaf]})
    rejected(value, 422, "/groups")
    value = sample_rule()
    value["groups"][0]["conditions"][0]["conditions"] = []
    rejected(value, 400)


@pytest.mark.parametrize(
    "updates,path",
    [
        ({"interval_minutes": None}, "interval_minutes"),
        ({"time_of_day": "10:00"}, "time_of_day"),
        ({"weekday": 1}, "weekday"),
        ({"interval_minutes": 14}, "interval_minutes"),
        ({"timezone": "+08:00"}, "timezone"),
        ({"timezone": "../UTC"}, "timezone"),
        ({"start_date": "2026-02-30"}, "start_date"),
        ({"end_date": "2025-12-31"}, "end_date"),
        ({"end_date": "2027-01-02"}, "end_date"),
    ],
)
def test_schedule_value_boundaries(updates, path):
    value = sample_rule()
    value["schedule"].update(updates)
    rejected(value, 422, "/schedule/" + path)


def test_366_inclusive_days_and_daily_weekly_interlocks():
    value = sample_rule()["schedule"]
    value.update(start_date="2024-01-01", end_date="2024-12-31")
    assert parse_schedule(value).end_date == "2024-12-31"
    value.update(frequency="DAILY", interval_minutes=None, time_of_day="10:00")
    assert parse_schedule(value).weekday is None
    value.update(frequency="WEEKLY", weekday=7)
    assert parse_schedule(value).weekday == 7


def test_original_reason_1000_not_configuration_500_and_enable_uuid():
    assert (
        len(parse_rule_action("PAUSE", json.dumps({"reason": "x" * 1000}).encode()).reason) == 1000
    )
    assert (
        parse_rule_action("ENABLE", json.dumps({"simulation_id": ID}).encode()).simulation_id == ID
    )
    with pytest.raises(OrbitError):
        parse_rule_action("ARCHIVE", b'{"reason":"x","simulation_id":null}')


def simulation():
    return {
        "id": ID,
        "rule_id": ID,
        "revision": 1,
        "snapshot_id": ID,
        "hash": "a" * 64,
        "account_count": 1,
        "scanned_count": 3,
        "hit_count": 1,
        "unknown_count": 1,
        "false_count": 1,
        "conditions": [],
        "expires_at": "2026-11-09T00:00:00Z",
        "next_cursor": None,
    }


def test_simulation_full_counts_never_derive_from_first_conditions_page():
    assert parse_rule_response(Simulation, simulation()).scanned_count == 3
    value = simulation()
    value["hit_count"] = 2
    with pytest.raises(OrbitError) as caught:
        parse_rule_response(Simulation, value)
    assert caught.value.code == "FIELD_VALIDATION_FAILED"


def test_rule_response_original_exact15_and_utc():
    value = {**sample_rule(), "id": ID, "revision": 1, "state": "DRAFT", "next_run_at": None}
    assert len(parse_rule_response(Rule, value).model_dump()) == 15
    value["next_run_at"] = "2026-01-01T10:00:00+08:00"
    with pytest.raises(OrbitError):
        parse_rule_response(Rule, value)


def test_condition_unknown_value_null_and_reason_stays_explicit():
    row = {
        "entity_id": ID,
        "condition_index": 19,
        "value": None,
        "result": "UNKNOWN",
        "reason_code": "METRIC_MISSING",
    }
    assert parse_rule_response(ConditionResult, row).value is None
    with pytest.raises(OrbitError):
        parse_rule_response(ConditionResult, {**row, "value": "1e3"})


@pytest.mark.parametrize(
    "location,key",
    [
        ("ownership", "owner_user_id"),
        ("ownership", "owner_team_id"),
        ("group", "logic"),
        ("group", "conditions"),
        ("condition", "metric"),
        ("condition", "operator"),
        ("condition", "threshold"),
    ],
)
def test_nested_original_required_fields(location, key):
    value = sample_rule()
    nested = {
        "ownership": value["ownership"],
        "group": value["groups"][0],
        "condition": value["groups"][0]["conditions"][0],
    }[location]
    del nested[key]
    rejected(value, 400)


@pytest.mark.parametrize("field", ["cooldown_minutes", "max_daily"])
def test_nonstandard_numeric_json_in_otherwise_complete_body(field):
    value = sample_rule()
    value[field] = float("nan")
    with pytest.raises(OrbitError) as caught:
        parse_rule_write(json.dumps(value).encode())
    assert caught.value.status == 400
    assert caught.value.pointer == "/" + field


def test_response_nested_manual_validation_preserves_exact_pointer():
    value = simulation()
    value["conditions"] = [
        {
            "entity_id": "wrong",
            "condition_index": 0,
            "value": None,
            "result": "UNKNOWN",
            "reason_code": "METRIC_MISSING",
        }
    ]
    with pytest.raises(OrbitError) as caught:
        parse_rule_response(Simulation, value)
    assert caught.value.pointer == "/conditions/0/entity_id"
    row = {**sample_rule(), "id": ID, "revision": 1, "state": "DRAFT", "next_run_at": None}
    row["name"] = "bad\n"
    page = {
        "items": [row],
        "next_cursor": None,
        "data_as_of": "2026-01-01T00:00:00Z",
        "scope_version": 1,
    }
    with pytest.raises(OrbitError) as caught:
        parse_rule_response(RulePage, page)
    assert caught.value.pointer == "/items/0/name"


@pytest.mark.parametrize(
    "time",
    ["2026-01-01", "2026-01-01 10:00:00+00:00", "2026-01-01T10:00:00", "2026-02-30T10:00:00Z"],
)
def test_response_date_time_cannot_accept_date_or_naive_or_invalid_date(time):
    value = simulation()
    value["expires_at"] = time
    with pytest.raises(OrbitError) as caught:
        parse_rule_response(Simulation, value)
    assert caught.value.pointer == "/expires_at"


def test_response_array_ceiling_uses_original10000_not_entity_count():
    row = {
        "entity_id": ID,
        "condition_index": 0,
        "value": None,
        "result": "UNKNOWN",
        "reason_code": "METRIC_MISSING",
    }
    value = simulation()
    value["conditions"] = [row] * 10001
    with pytest.raises(OrbitError) as caught:
        parse_rule_response(Simulation, value)
    assert caught.value.code == "FIELD_VALIDATION_FAILED"
    assert caught.value.pointer == "/conditions"


@pytest.mark.parametrize("value", ["", "x" * 2049, "bad\x00cursor"])
def test_original_next_cursor_bounds_and_controls(value):
    response = simulation()
    response["next_cursor"] = value
    with pytest.raises(OrbitError) as caught:
        parse_rule_response(Simulation, response)
    assert caught.value.code == "FIELD_VALIDATION_FAILED"
    assert caught.value.pointer == "/next_cursor"
