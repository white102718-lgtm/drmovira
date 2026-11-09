"""指标HTTP专项工具护栏及21个真实原DTO SQL样本纯测，不连接DB。"""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from orbit_api.directory_tokens import canonical
from orbit_api.launch_contract import parse_model
from orbit_api.launch_execution_contract import MetricProfile

PATH = Path(__file__).resolve().parents[2] / "tools/metric_profile_query_checks.py"
spec = importlib.util.spec_from_file_location("metric_query_guard", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("192.0.2.1", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 31),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 32 + "\n"),
        ("127.0.0.1", 13306, None),
    ],
)
def test_seed_and_checker_both_guard_before_database_or_http(host, port, database):
    admin = SimpleNamespace(
        host=host, port=port, cursor=Mock(side_effect=AssertionError("不能访问DB"))
    )
    client = Mock(side_effect=AssertionError("不能访问HTTP"))
    for function, args in (
        (module.seed_metric_profile_browser_fixture, (admin, database)),
        (module.run_metric_profile_query_checks, (client, admin, {}, "unused", None, database, [])),
    ):
        with pytest.raises(ValueError):
            function(*args)
    admin.cursor.assert_not_called()
    client.assert_not_called()


@pytest.mark.parametrize("index", range(1, 22))
def test_every_sql_sample_is_an_actual_strict_original_profile_with_explicit_nullable_actions(
    index,
):
    profile, digest, proof_json = module.query_profile_sql_sample(index)
    assert parse_model(canonical(profile).encode(), MetricProfile) == profile
    assert digest == hashlib.sha256(canonical(profile).encode()).hexdigest()
    assert len(profile) == 12 and profile["version"] == f"observed-v{index:03d}"
    assert profile["register_action_type"] is None and profile["value_action_type"] is None
    assert profile["attribution_windows"] == [f"opaque-original-window-{index:03d}"]
    proof = json.loads(proof_json)
    assert proof["source_config_id"] is None and proof["source_config_revision"] is None
    assert proof["evidence_ref"] == "isolated-query:SQL_ONLY_NOT_META"


class Cursor:
    def __init__(self, database):
        self.database = database
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, values=None):
        self.statements.append((statement, values))

    def fetchone(self):
        statement = self.statements[-1][0]
        if statement == "SELECT DATABASE()":
            return (self.database,)
        if statement.startswith("SELECT tenant_id"):
            return ("00000000-0000-0000-0000-000000000001",)
        if statement.startswith("SELECT revision"):
            return (1,)
        raise AssertionError("未定义的SQL夹具查询")


def test_actual_database_mismatch_stops_before_any_mutation_and_rolls_back():
    cursor = Cursor("foreign_database")
    admin = SimpleNamespace(host="127.0.0.1", port=13306, cursor=lambda: cursor, rollback=Mock())
    with pytest.raises(AssertionError):
        module.seed_metric_profile_browser_fixture(admin, "orbit_py_it_" + "a" * 32)
    assert cursor.statements == [("SELECT DATABASE()", None)]
    admin.rollback.assert_called_once()


def test_independent_browser_seed_inserts_exact_twenty_one_profiles_and_heads_same_transaction():
    database = "orbit_py_it_" + "a" * 32
    cursor = Cursor(database)
    admin = SimpleNamespace(
        host="127.0.0.1", port=13306, cursor=lambda: cursor, commit=Mock(), rollback=Mock()
    )
    result = module.seed_metric_profile_browser_fixture(admin, database)
    assert len(result["ids"]) == len(set(result["ids"])) == len(result["profiles"]) == 21
    versions = [
        (sql, values)
        for sql, values in cursor.statements
        if sql.startswith("INSERT INTO orbit_metric_profile_version")
    ]
    heads = [
        (sql, values)
        for sql, values in cursor.statements
        if sql.startswith("INSERT INTO orbit_metric_profile_head")
    ]
    assert len(versions) == len(heads) == 21
    for (_, values), (_, head_values), profile in zip(
        versions, heads, result["profiles"], strict=True
    ):
        assert json.loads(values[3]) == profile
        assert values[4] == hashlib.sha256(canonical(profile).encode()).hexdigest()
        assert values[1] == head_values[1] == profile["id"]
        proof = json.loads(values[-1])
        assert values[5].isoformat() == proof["observed_at"].replace("+00:00", "")
        assert values[5].microsecond % 1000 == 0
    for statement, values in cursor.statements:
        if values is not None:
            assert statement.count("%s") == len(values)
    assert cursor.statements[2][0].endswith("FOR UPDATE")
    assert cursor.statements[-1][0].startswith("UPDATE orbit_metric_profile_clock")
    admin.commit.assert_called_once()
    admin.rollback.assert_not_called()


def test_case_exports_are_fifteen_unique_explicitly_limited_protocol_checks():
    names = module.METRIC_PROFILE_QUERY_CASES
    assert len(names) == len(set(names)) == 15
    assert all(name.startswith("pythonMetricQuery") for name in names)
