"""监测原合同纯测试；不等同真实事实来源、MySQL查询或生产指标验收。"""

import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

import pytest

from orbit_api.errors import OrbitError
from orbit_api.metrics_contract import (
    METRIC_NAMES,
    MetricQuery,
    MetricRow,
    Metrics,
    MetricTotal,
    MetricValues,
    parse_metric_query,
    parse_metrics,
    validate_account_local_today,
)


def uid(number=1):
    return str(UUID(int=number))


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def query():
    return {
        "date_from": "2026-01-01",
        "date_to": "2026-01-01",
        "dataset": "ACCOUNT",
        "metric_profile_id": uid(),
        "scope_snapshot_id": None,
        "channel_id": None,
        "operator_user_id": None,
        "q": "",
        "sort": "spend",
        "direction": "DESC",
        "cursor": None,
        "page_size": 20,
        "granularity": "SUMMARY",
    }


def values():
    return dict.fromkeys(METRIC_NAMES, None)


def row():
    return {
        "tenant_id": uid(),
        "owner_team_id": None,
        "operator_user_id": None,
        "entity_id": "00000123456789012345678901234567890",
        "name": "",
        "channel_id": None,
        "product_name_snapshot": None,
        "currency": "USD",
        "metric_profile_id": uid(2),
        "business_date": None,
        "account_count": 0,
        "ad_count": 0,
        "values": values(),
        "quality": "UNKNOWN",
        "coverage": "0",
    }


def total():
    return {
        "tenant_id": uid(),
        "currency": "USD",
        "metric_profile_id": uid(2),
        "values": values(),
        "account_count": 0,
        "ad_count": 0,
        "missing_count": 0,
        "coverage": "0",
    }


def response():
    return {
        "items": [row()],
        "next_cursor": None,
        "scope_version": 1,
        "snapshot_id": uid(3),
        "data_as_of": "2026-01-01T00:00:00.000Z",
        "missing_count": 0,
        "query_snapshot_id": uid(4),
        "totals": [total()],
    }


def reject(parser, value, status, path):
    with pytest.raises(OrbitError) as caught:
        parser(encode(value))
    # 出站坏数据不归咎用户字段：拒绝全包并隐藏内部字段位置。
    assert caught.value.status == (503 if parser is parse_metrics else status)
    assert caught.value.pointer == (None if parser is parse_metrics else path)
    if parser is parse_metrics:
        assert caught.value.code == "METRICS_DATA_UNVERIFIED"
    return caught.value


@pytest.mark.parametrize("model", [MetricQuery, MetricValues, MetricRow, MetricTotal, Metrics])
def test_original_fields_are_exact_and_all_required(model):
    baseline = (
        Path(__file__).resolve().parents[3]
        / "data/ORBIT_Codex开发PRD/contracts/openapi-current.json"
    )
    original = json.loads(baseline.read_text(encoding="utf-8"))["components"]["schemas"][
        model.__name__
    ]
    assert set(model.model_fields) == set(original["properties"])
    assert {key for key, value in model.model_fields.items() if value.is_required()} == set(
        original["required"]
    )


def test_query_preserves_all_nullable_required_fields_and_normalizes_nfc():
    value = query() | {"q": "  e\u0301  ", "channel_id": "legacy-channel-code"}
    actual = parse_metric_query(encode(value))
    assert actual == value | {"q": "é"}
    assert len(actual) == 13


@pytest.mark.parametrize("key", list(query()))
def test_every_query_field_is_required_even_nullable(key):
    value = query()
    del value[key]
    reject(parse_metric_query, value, 400, "/" + key)


@pytest.mark.parametrize(
    "dataset", ["ACCOUNT", "CAMPAIGN", "ADSET", "AD", "OPERATOR", "CHANNEL", "ASSET", "LAUNCH"]
)
@pytest.mark.parametrize("granularity", ["SUMMARY", "DAY"])
def test_all_original_dataset_and_granularity_are_retained(dataset, granularity):
    actual = parse_metric_query(encode(query() | {"dataset": dataset, "granularity": granularity}))
    assert actual["dataset"] == dataset
    assert actual["granularity"] == granularity


@pytest.mark.parametrize(
    "sort", ["spend", "impressions", "clicks", "purchases", "roas", "cpm", "name"]
)
@pytest.mark.parametrize("direction", ["ASC", "DESC"])
def test_all_sort_and_direction_values(sort, direction):
    assert (
        parse_metric_query(encode(query() | {"sort": sort, "direction": direction}))["sort"] == sort
    )


@pytest.mark.parametrize("size", [20, 50, 100, 200])
def test_four_page_sizes(size):
    assert parse_metric_query(encode(query() | {"page_size": size}))["page_size"] == size


@pytest.mark.parametrize(
    ("change", "status", "path"),
    [
        ({"dataset": "TOTAL"}, 422, "/dataset"),
        ({"sort": "registrations"}, 422, "/sort"),
        ({"direction": "asc"}, 422, "/direction"),
        ({"granularity": "MONTH"}, 422, "/granularity"),
        ({"page_size": 201}, 422, "/page_size"),
        ({"page_size": 20.0}, 400, "/page_size"),
        ({"page_size": True}, 400, "/page_size"),
        ({"dataset": 1}, 400, "/dataset"),
        ({"q": 1}, 400, "/q"),
        ({"q": "🙂" * 101}, 422, "/q"),
        ({"q": "a\nb"}, 422, "/q"),
        ({"q": "a\u200bb"}, 422, "/q"),
        ({"cursor": ""}, 422, "/cursor"),
        ({"cursor": "x" * 2049}, 422, "/cursor"),
        ({"channel_id": ""}, 422, "/channel_id"),
        ({"channel_id": "x" * 65}, 422, "/channel_id"),
        ({"metric_profile_id": "1"}, 422, "/metric_profile_id"),
        ({"scope_snapshot_id": "{" + uid() + "}"}, 422, "/scope_snapshot_id"),
        ({"operator_user_id": uid().replace("-", "")}, 422, "/operator_user_id"),
        ({"date_from": "2026-1-01"}, 422, "/date_from"),
        ({"date_from": "2026-02-30"}, 422, "/date_from"),
        ({"date_to": "2025-12-31"}, 422, "/date_to"),
        ({"date_to": "2026-04-04"}, 422, "/date_to"),
        ({"date_to": "2026-01-01T00:00:00Z"}, 422, "/date_to"),
        ({"product_id": uid()}, 400, "/product_id"),
        ({"unexpected~/field": "private"}, 400, "/unexpected~0~1field"),
    ],
)
def test_query_strict_shapes_boundaries_and_json_pointers(change, status, path):
    failure = reject(parse_metric_query, query() | change, status, path)
    assert "private" not in failure.message


def test_nfc_is_applied_before_length_and_valid_cursor_is_opaque():
    actual = parse_metric_query(
        encode(query() | {"q": "e\u0301" * 100, "cursor": "+/opaque==", "channel_id": "x" * 64})
    )
    assert actual["q"] == "é" * 100
    assert actual["cursor"] == "+/opaque=="


def test_channel_short_text_normalizes_but_does_not_become_uuid_only():
    assert parse_metric_query(encode(query() | {"channel_id": " e\u0301 "}))["channel_id"] == "é"
    reject(parse_metric_query, query() | {"channel_id": "   "}, 422, "/channel_id")
    reject(parse_metric_query, query() | {"channel_id": "a\nb"}, 422, "/channel_id")


def test_inclusive_93_days_leap_day_and_no_implicit_today():
    assert (
        parse_metric_query(encode(query() | {"date_to": "2026-04-03"}))["date_to"] == "2026-04-03"
    )
    assert (
        parse_metric_query(encode(query() | {"date_from": "2024-02-29", "date_to": "2024-02-29"}))[
            "date_from"
        ]
        == "2024-02-29"
    )
    # 未取得账户时区/当天时不借UTC或上海日历伪造未来判断。
    assert (
        parse_metric_query(encode(query() | {"date_from": "2099-01-01", "date_to": "2099-01-01"}))[
            "date_to"
        ]
        == "2099-01-01"
    )


def test_future_check_uses_explicit_account_today_per_account_not_global_calendar():
    raw = encode(query())
    assert parse_metric_query(raw, account_local_today=date(2026, 1, 1))["date_to"] == "2026-01-01"
    with pytest.raises(OrbitError) as caught:
        parse_metric_query(raw, account_local_today=date(2025, 12, 31))
    assert caught.value.pointer == "/date_to"
    with pytest.raises(ValueError):
        validate_account_local_today(query(), datetime(2026, 1, 1))


@pytest.mark.parametrize("key", ["metric_profile_id", "scope_snapshot_id", "operator_user_id"])
def test_query_canonical_uuid_accepts_uppercase_only_hyphenated(key):
    value = "abcdefab-cdef-abcd-efab-cdefabcdefab"
    assert parse_metric_query(encode(query() | {key: value.upper()}))[key] == value


def test_all_response_fields_nullable_metrics_and_external_numeric_id_preserved():
    value = response()
    actual = parse_metrics(encode(value))
    assert actual == value
    assert len(actual) == 8 and len(actual["items"][0]) == 15 and len(actual["totals"][0]) == 8
    assert actual["items"][0]["values"] == dict.fromkeys(METRIC_NAMES, None)
    assert actual["items"][0]["entity_id"].startswith("00000")


@pytest.mark.parametrize("metric", METRIC_NAMES)
@pytest.mark.parametrize("amount", ["0", "0.000000", "1.123456", "9" * 21 + ".123456"])
def test_every_metric_preserves_exact_decimal_text(metric, amount):
    value = response()
    value["items"][0]["values"][metric] = amount
    assert parse_metrics(encode(value))["items"][0]["values"][metric] == amount


@pytest.mark.parametrize(
    "amount",
    [
        0,
        1.2,
        True,
        "-1",
        "+1",
        "01",
        "1e3",
        " 1",
        "1.0000001",
        "1.",
        ".1",
        "1" * 29,
        "NaN",
        "Infinity",
    ],
)
@pytest.mark.parametrize("collection", ["items", "totals"])
def test_invalid_money_is_not_coerced_or_floated(amount, collection):
    value = response()
    value[collection][0]["values"]["spend"] = amount
    reject(
        parse_metrics,
        value,
        400 if type(amount) is not str else 422,
        f"/{collection}/0/values/spend",
    )


@pytest.mark.parametrize("metric", METRIC_NAMES)
def test_every_metric_is_required_even_when_unknown(metric):
    value = response()
    del value["items"][0]["values"][metric]
    reject(parse_metrics, value, 400, f"/items/0/values/{metric}")


@pytest.mark.parametrize(
    ("path", "bad", "status"),
    [
        (("scope_version",), 0, 422),
        (("scope_version",), 9007199254740992, 422),
        (("scope_version",), True, 400),
        (("missing_count",), -1, 422),
        (("missing_count",), 2147483648, 422),
        (("next_cursor",), "", 422),
        (("snapshot_id",), "unknown", 422),
        (("query_snapshot_id",), None, 400),
        (("data_as_of",), "2026-02-30T00:00:00Z", 422),
        (("data_as_of",), "2026-01-01T00:00:00", 422),
        (("items", 0, "account_count"), 0.0, 400),
        (("items", 0, "ad_count"), True, 400),
        (("items", 0, "quality"), "SUFFICIENT", 422),
        (("items", 0, "quality"), 1, 400),
        (("items", 0, "entity_id"), "", 422),
        (("items", 0, "entity_id"), "x" * 65, 422),
        (("items", 0, "name"), "🙂" * 256, 422),
        (("items", 0, "product_name_snapshot"), "", 422),
        (("items", 0, "channel_id"), "legacy-code", 422),
        (("items", 0, "owner_team_id"), "unknown", 422),
        (("items", 0, "business_date"), "2026-01-32", 422),
        (("totals", 0, "currency"), "US", 422),
        (("totals", 0, "values", "cost"), "0", 400),
    ],
)
def test_nested_response_error_pointer(path, bad, status):
    value = response()
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad
    reject(parse_metrics, value, status, "/" + "/".join(map(str, path)))


@pytest.mark.parametrize("quality", ["COMPLETE", "PARTIAL", "STALE", "UNKNOWN"])
def test_quality_enum_does_not_fill_or_claim_coverage(quality):
    value = response()
    value["items"][0]["quality"] = quality
    assert parse_metrics(encode(value))["items"][0]["values"]["spend"] is None


def test_array_boundaries_full_totals_not_assumed_to_equal_current_page():
    value = response()
    value["items"] = [deepcopy(row()) for _ in range(200)]
    value["totals"] = [deepcopy(total()) for _ in range(1000)]
    value["totals"][0]["values"]["spend"] = "1000"
    actual = parse_metrics(encode(value))
    assert len(actual["items"]) == 200 and len(actual["totals"]) == 1000
    assert actual["totals"][0]["values"]["spend"] == "1000"
    value["items"].append(row())
    reject(parse_metrics, value, 422, "/items")
    value["items"] = []
    value["totals"].append(total())
    reject(parse_metrics, value, 422, "/totals")


@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b"[]",
        b'{"x":NaN}',
        b'{"q":"a","q":"b"}',
        b"{",
        b'"secret"',
        b"\xff",
        b'{"x":Infinity}',
    ],
)
def test_invalid_json_and_structure_are_safe(raw):
    with pytest.raises(OrbitError) as caught:
        parse_metric_query(raw)
    assert caught.value.status == 400
    assert "secret" not in caught.value.message


def test_response_empty_arrays_and_required_fields_have_no_defaults():
    value = response() | {"items": [], "totals": []}
    assert parse_metrics(encode(value))["items"] == []
    for key in list(value):
        missing = value.copy()
        del missing[key]
        reject(parse_metrics, missing, 400, "/" + key)


@pytest.mark.parametrize("key", list(row()))
def test_every_row_required_field_including_nullable_is_rejected_when_missing(key):
    value = response()
    del value["items"][0][key]
    reject(parse_metrics, value, 400, "/items/0/" + key)


@pytest.mark.parametrize("key", list(total()))
def test_every_total_required_field_is_rejected_when_missing(key):
    value = response()
    del value["totals"][0][key]
    reject(parse_metrics, value, 400, "/totals/0/" + key)


def test_bad_persisted_response_is_whole_package_503_not_user_422_or_partial_success():
    value = response()
    value["items"].append(row() | {"currency": "private-invalid-value"})
    with pytest.raises(OrbitError) as caught:
        parse_metrics(encode(value))
    assert caught.value.status == 503
    assert caught.value.code == "METRICS_DATA_UNVERIFIED"
    assert caught.value.pointer is None
    assert "private" not in caught.value.message
