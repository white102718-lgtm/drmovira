"""056工具护栏及矩阵完整性纯测，不执行MySQL。"""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

TOOL_DIRECTORY = str(Path(__file__).resolve().parents[2] / "tools")
sys.path.insert(0, TOOL_DIRECTORY)
try:
    schema = importlib.import_module("metric_fact_schema_checks")
    manifest_tool = importlib.import_module("metrics_result_manifest_checks")
finally:
    sys.path.remove(TOOL_DIRECTORY)


@pytest.mark.parametrize("has_manifest", [False, True])
def test_original_exact_32_triggers_and_only_explicit_056_one_extra(has_manifest):
    names = sorted(schema.BASE_METRIC_TRIGGER_NAMES)
    if has_manifest:
        names.append("metric_query_expected_manifest_guard")
    schema.validate_metric_trigger_names(names, has_expected_manifest=has_manifest)
    with pytest.raises(AssertionError):
        schema.validate_metric_trigger_names(names[:-1], has_expected_manifest=has_manifest)
    with pytest.raises(AssertionError):
        schema.validate_metric_trigger_names(
            names + ["unknown_extra"], has_expected_manifest=has_manifest
        )
    with pytest.raises(AssertionError):
        schema.validate_metric_trigger_names(names + [names[0]], has_expected_manifest=has_manifest)


def test_manifest_tool_target_guard_precedes_any_fixture_or_seed(monkeypatch):
    called = []
    monkeypatch.setattr(
        manifest_tool, "MetricFactSqlFixture", lambda *args: called.append("fixture")
    )
    with pytest.raises(ValueError):
        manifest_tool.run_metrics_expected_manifest_checks(
            SimpleNamespace(host="127.0.0.1", port=3306), "not_isolated", []
        )
    assert called == []


def test_all_mixed_null_insert_combinations_and_independent_frozen_counts_are_covered(monkeypatch):
    class Fixture:
        tenant = str(uuid4())
        instances = []

        def __init__(self, *args):
            self.insertions, self.denials = [], []
            self.instances.append(self)

        def publication(self, *args, **kwargs):
            return {"id": str(uuid4())}

        def publish(self, *args, **kwargs):
            return 1

        def query(self, *args, **kwargs):
            return {"id": str(uuid4()), "tenant_id": self.tenant, **kwargs}

        def insert(self, table, row, *, deny=None):
            self.insertions.append((dict(row), deny))

        def denied(self, sql, values, expected):
            self.denials.append((sql, expected))

        def sql(self, statement, values=(), **kwargs):
            if "information_schema.COLUMNS" in statement:
                return tuple((field, "非空中文说明") for field in manifest_tool.FIELDS)
            if "information_schema.TRIGGERS" in statement:
                return (("metric_query_expected_manifest_guard",),)
            if statement.startswith("SELECT expected_unit_hash"):
                return (
                    ("a" * 64, "b" * 64, 1, "orbit-metric-expectation-canonical-lines-v2", 1, 1),
                )
            return 1

    monkeypatch.setattr(manifest_tool, "MetricFactSqlFixture", Fixture)
    monkeypatch.setattr(manifest_tool, "validate_metric_fact_schema_target", lambda *args: None)
    monkeypatch.setattr(
        manifest_tool,
        "seed_metric_profile_browser_fixture",
        lambda *args: {"profiles": [{"id": str(uuid4())}]},
    )
    cases = []
    manifest_tool.run_metrics_expected_manifest_checks(None, "pure", cases)
    fixture = Fixture.instances[-1]
    assert cases == list(manifest_tool.METRICS_EXPECTED_MANIFEST_CASES)
    null_matrix = fixture.insertions[:16]
    assert len(null_matrix) == 16
    assert sum(deny is None for _, deny in null_matrix) == 2
    assert sum(deny == {3819} for _, deny in null_matrix) == 14
    assert len(fixture.insertions) == 24
    assert len(fixture.denials) == 7
    for field in ("expected_account_count", "expected_cell_count"):
        assert any(f"{field}={field}+1" in sql for sql, _ in fixture.denials)
