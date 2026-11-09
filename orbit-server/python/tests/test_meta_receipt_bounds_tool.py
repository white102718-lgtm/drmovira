"""051工具护栏/探针结构纯测；不模拟CHECK成功，不代替真实MySQL执行。"""

import json
from types import SimpleNamespace

import pytest
from tools.meta_receipt_bounds_checks import (
    META_RECEIPT_BOUNDS_CASES,
    assert_check_diagnostics,
    guard_meta_receipt_target,
    receipt_probes,
)

BASE = {
    "registry_id": "04504504-5045-4045-8045-045045045045",
    "binding_sha256": "a" * 64,
    "observed_at": "2026-11-09T08:00:00.123499Z",
    "account_count": 2,
    "resource_count": 4,
    "execution_authorized": False,
}


@pytest.mark.parametrize(
    "change",
    [
        {"host": "production.invalid"},
        {"port": 3306},
        {"database": "orbit"},
        {"database": "orbit_py_it_wrong"},
        {"server_status": 1},
    ],
)
def test_guard_rejects_target_or_existing_transaction_before_sql(change):
    values = dict(host="127.0.0.1", port=13306, database="orbit_py_it_" + "a" * 32, server_status=0)
    values.update(change)
    database = values.pop("database")
    with pytest.raises(ValueError):
        guard_meta_receipt_target(SimpleNamespace(**values), database)


def test_valid_boundaries_are_four_independent_exact_integer_combinations():
    good, _bad = receipt_probes(BASE)
    assert len(good) == 4
    bodies = [json.loads(body) for _label, body in good]
    assert {(row["account_count"], row["resource_count"]) for row in bodies} == {
        (1, 0),
        (1, 2500000),
        (500, 0),
        (500, 2500000),
    }
    assert all(type(row["account_count"]) is type(row["resource_count"]) is int for row in bodies)
    assert BASE["account_count"] == 2 and BASE["resource_count"] == 4


def test_negative_probes_preserve_missing_keys_and_json_native_types():
    _good, bad = receipt_probes(BASE)
    probes = dict(bad)
    assert len(probes) == len(bad)
    for key in BASE:
        missing = json.loads(probes[key + "Missing"])
        assert key not in missing and len(missing) == 6
        assert json.loads(probes[key + "Null"])[key] is None
    for key in ("account_count", "resource_count"):
        assert type(json.loads(probes[key + "Double"])[key]) is float
        assert type(json.loads(probes[key + "Scientific"])[key]) is float
        assert "1e0" in probes[key + "Scientific"]
        assert type(json.loads(probes[key + "String"])[key]) is str
        assert type(json.loads(probes[key + "True"])[key]) is bool
        assert type(json.loads(probes[key + "Array"])[key]) is list
        assert type(json.loads(probes[key + "Object"])[key]) is dict


def test_diagnostics_accept_only_no_diagnostics_or_exact_requested_check_error():
    assert_check_diagnostics([])
    assert_check_diagnostics([("Error", 3819, "ignored private body")], expected_error=3819)


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([("Warning", 1235, "private")], None),
        ([("Warning", 1292, "private")], None),
        ([("Error", 1142, "private")], 3819),
        ([("Error", 3819, "private"), ("Warning", 1235, "private")], 3819),
        ([], 3819),
    ],
)
def test_diagnostics_never_swallow_other_errors_or_conversion_warnings(rows, expected):
    with pytest.raises(AssertionError) as error:
        assert_check_diagnostics(rows, expected_error=expected)
    assert "private" not in str(error.value)


def test_three_matrix_cases_have_unique_names_not_sample_count_inflation():
    assert len(META_RECEIPT_BOUNDS_CASES) == len(set(META_RECEIPT_BOUNDS_CASES)) == 3
