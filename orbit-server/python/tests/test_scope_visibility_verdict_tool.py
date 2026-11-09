"""新真实专项工具自身护栏纯测；不连接数据库，不证明触发器可执行。"""

import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

PATH = Path(__file__).resolve().parents[2] / "tools/scope_visibility_verdict_checks.py"
spec = importlib.util.spec_from_file_location("scope_verdict_tool", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "database,host,port",
    [
        ("orbit", "127.0.0.1", 13306),
        (None, "127.0.0.1", 13306),
        ("orbit_py_it_" + "a" * 32 + "\n", "127.0.0.1", 13306),
        ("orbit_py_it_" + "A" * 32, "127.0.0.1", 13306),
        ("orbit_py_it_" + "a" * 31, "127.0.0.1", 13306),
        ("orbit_py_it_" + "a" * 32, "localhost", 13306),
        ("orbit_py_it_" + "a" * 32, "192.0.2.1", 13306),
        ("orbit_py_it_" + "a" * 32, "127.0.0.1", 3306),
    ],
)
def test_rejects_wrong_target_before_any_fixture_or_private_runtime_import(database, host, port):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    with pytest.raises(ValueError):
        module.run_scope_visibility_verdict_checks(None, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()


def test_actual_database_name_must_equal_expected_uuid_database():
    cursor = Mock()
    cursor.fetchone.return_value = ("another_database",)
    manager = Mock()
    manager.__enter__ = Mock(return_value=cursor)
    manager.__exit__ = Mock(return_value=False)
    admin = SimpleNamespace(host="127.0.0.1", port=13306, cursor=lambda: manager)
    with pytest.raises(ValueError):
        module.guard_database(admin, "orbit_py_it_" + "a" * 32)
    cursor.execute.assert_called_once_with("SELECT DATABASE()")


def test_exact_eighteen_stable_unique_business_groups_and_optional_fixture_interface():
    names = module.SCOPE_VISIBILITY_VERDICT_CASES
    assert isinstance(names, tuple) and len(names) == len(set(names)) == 18
    assert all(name.startswith("pythonScopeVerdict") for name in names)
    parameters = inspect.signature(module.run_scope_visibility_verdict_checks).parameters
    assert list(parameters) == [
        "client",
        "admin",
        "headers",
        "password",
        "cache",
        "database",
        "cases",
        "identities",
    ]
    assert parameters["identities"].default is None
    assert parameters["identities"].kind == inspect.Parameter.KEYWORD_ONLY


def test_http_failure_diagnostic_does_not_read_or_disclose_response_body():
    response = SimpleNamespace(status_code=403, json=Mock(side_effect=AssertionError("private")))
    with pytest.raises(AssertionError) as failure:
        module.assert_status(response, 200)
    assert str(failure.value) == "scope_verdict_http expected=200 actual=403"
    response.json.assert_not_called()


def test_sql_code_extraction_never_formats_driver_query_or_parameters():
    original = Exception(1644, "secret query and token must not be printed")
    wrapped = SimpleNamespace(args=("private",), orig=original)
    assert module.sql_error_code(original) == module.sql_error_code(wrapped) == 1644
    assert module.sql_error_code(Exception("private")) is None


@pytest.mark.parametrize(
    "error,passes",
    [(Exception(1644, "private"), True), (Exception(2013, "private"), False), (None, False)],
)
def test_guard_probe_always_rolls_back_even_if_rejection_wrong_or_missing(error, passes):
    cursor = Mock()
    cursor.execute.side_effect = error
    manager = Mock()
    manager.__enter__ = Mock(return_value=cursor)
    manager.__exit__ = Mock(return_value=False)
    admin = SimpleNamespace(cursor=lambda: manager, begin=Mock(), rollback=Mock())
    if passes:
        module.assert_guard_rejects(admin, "controlled probe", ("private",))
    else:
        with pytest.raises(AssertionError) as failure:
            module.assert_guard_rejects(admin, "controlled probe", ("private",))
        assert "private" not in str(failure.value)
    admin.begin.assert_called_once()
    admin.rollback.assert_called_once()
