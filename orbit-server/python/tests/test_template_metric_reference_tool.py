"""模板指标真实工具目标护栏与原TemplateWrite/历史NULL断言纯测。"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest

from orbit_api.directory_tokens import canonical
from orbit_api.template_contract import parse_template

PATH = Path(__file__).resolve().parents[2] / "tools/template_metric_reference_checks.py"
spec = importlib.util.spec_from_file_location("template_metric_guard", PATH)
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
def test_target_guard_runs_before_http_database_or_credentials_use(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock(side_effect=AssertionError("禁止DB")))
    client = Mock(side_effect=AssertionError("禁止HTTP"))
    with pytest.raises(ValueError):
        module.run_template_metric_reference_checks(client, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()
    client.assert_not_called()


def test_fixture_is_actual_original_templatewrite_without_plan_ownership_or_execution_fields(
    monkeypatch,
):
    monkeypatch.syspath_prepend(str(PATH.parent))
    profile_id = str(UUID(int=44))
    value = module.template_metric_write_fixture(profile_id)
    parsed = parse_template(canonical(value).encode())
    assert parsed["campaigns"][0]["adsets"][0]["metric_profile_id"] == profile_id
    assert set(parsed) == {"name", "description", "visibility", "recipient_user_ids", "campaigns"}
    assert parsed["visibility"] == "PRIVATE" and parsed["recipient_user_ids"] == []
    assert "dependency_json" not in parsed and "ownership" not in parsed


def test_historical_null_is_preserved_for_every_real_version():
    module.assert_historical_metric_dependencies_unknown(None, {1: None}, (1,))
    module.assert_historical_metric_dependencies_unknown(
        None, {1: None, 2: None, 3: None}, (1, 2, 3)
    )


@pytest.mark.parametrize(
    "head,versions",
    [
        ({}, {1: None, 2: None, 3: None}),
        (None, {1: None, 2: {}, 3: None}),
        (None, {1: None, 2: None}),
        (None, {1: None, 2: None, 3: {"metric_profiles": {}}}),
        (None, {1: None, 2: None, 3: None, 4: None}),
    ],
)
def test_null_guard_rejects_fake_verified_empty_dependency_and_missing_history(head, versions):
    with pytest.raises(AssertionError):
        module.assert_historical_metric_dependencies_unknown(head, versions, (1, 2, 3))


def test_exports_are_eleven_distinct_limited_http_groups_and_reserved_native_identity():
    names = module.TEMPLATE_METRIC_REFERENCE_CASES
    assert len(names) == len(set(names)) == 11
    assert all(name.startswith("pythonTemplateMetric") for name in names)
    assert module.NATIVE_ACTOR == module.NATIVE_ROLE == 940440001
