"""040真实工具护栏纯测；不连接数据库或替代真实SQL用例。"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "tools/metric_profile_registry_checks.py"
spec = importlib.util.spec_from_file_location("metric_registry_checks_guard", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("192.0.2.1", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 31),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 33),
        ("127.0.0.1", 13306, "orbit_py_it_" + "a" * 32 + "\n"),
        ("127.0.0.1", 13306, None),
        ("127.0.0.1", 13306, True),
    ],
)
def test_target_rejects_before_cursor_or_any_fixture_write(host, port, database):
    cursor = Mock(side_effect=AssertionError("guard之前禁止访问数据库"))
    admin = SimpleNamespace(host=host, port=port, cursor=cursor)
    cases = []
    with pytest.raises(ValueError):
        module.run_metric_profile_registry_checks(admin, database, cases)
    cursor.assert_not_called()
    assert cases == []


def test_exact_uuid_local_target_is_only_permitted_shape():
    admin = SimpleNamespace(host="127.0.0.1", port=13306)
    assert (
        module.validate_metric_registry_target(admin, "orbit_py_it_" + "0123456789abcdef" * 2)
        is None
    )


def test_exported_case_names_are_bounded_unique_and_not_acceptance_claims():
    names = module.METRIC_PROFILE_REGISTRY_CASES
    assert len(names) == 13 and len(set(names)) == 13
    assert all(name.startswith("pythonMetricRegistry") and len(name) <= 120 for name in names)


def test_actual_database_must_match_before_any_fixture_mutation():
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.return_value = ("different_database",)
    admin = SimpleNamespace(host="127.0.0.1", port=13306, cursor=Mock(return_value=cursor))
    with pytest.raises(AssertionError):
        module.run_metric_profile_registry_checks(admin, "orbit_py_it_" + "a" * 32, [])
    cursor.execute.assert_called_once_with("SELECT DATABASE()")


def test_success_fixture_builds_actual_publication_with_explicit_null_meta_source():
    from orbit_api.metric_profile_store import checked_prepared

    profile, prepared = module.metric_registry_publication_fixture("fixed-safe-fixture")
    assert prepared.profile() == profile and profile["source"] == "FIXTURE"
    assert prepared.proof.source_config_id is None
    assert prepared.proof.source_config_revision is None
    assert checked_prepared(prepared) == prepared
    assert profile["version"] == "observed-string-release"
    assert profile["attribution_windows"] == ["opaque-original-window"]
