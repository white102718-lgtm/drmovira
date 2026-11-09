"""独立真实scope runner的执行边界；纯测不连接数据库或冒充scope实际通过。"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def scope_tool(monkeypatch):
    tools = Path(__file__).parents[2] / "tools"
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location(
        "material_scanner_scope_tool", tools / "material_scanner_configuration_scope_checks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture():
    return {
        "users": [{"native": index} for index in range(4)],
        "actor_headers": {"Authorization": "Bearer fixture"},
        "manager_headers": {"Authorization": "Bearer fixture-manager"},
    }


@pytest.mark.parametrize(
    "database",
    ["orbit", "production", "orbit_py_it_", "orbit_py_it_" + "g" * 32, "orbit_py_it_" + "a" * 31],
)
def test_scope_runner_refuses_nonisolated_databases_before_any_io(scope_tool, database):
    with pytest.raises(ValueError):
        scope_tool.validate_scope_fixture(
            SimpleNamespace(host="127.0.0.1", port=13306), database, fixture()
        )


@pytest.mark.parametrize(
    "host,port", [("db.example.org", 13306), ("127.0.0.1", 3306), ("localhost", 13307)]
)
def test_scope_runner_cannot_operate_remote_or_shared_default_database(scope_tool, host, port):
    with pytest.raises(ValueError):
        scope_tool.validate_scope_fixture(
            SimpleNamespace(host=host, port=port), "orbit_py_it_" + "a" * 32, fixture()
        )


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"users": [1, 2, 3, 4]},
        {"users": [], "actor_headers": {"a": "b"}, "manager_headers": {"a": "b"}},
    ],
)
def test_scope_runner_requires_actual_user_fixture_and_headers(scope_tool, data):
    with pytest.raises(ValueError):
        scope_tool.validate_scope_fixture(
            SimpleNamespace(host="127.0.0.1", port=13306), "orbit_py_it_" + "a" * 32, data
        )


def test_scope_runner_accepts_only_explicit_fixture_and_has_unique_named_cases(scope_tool):
    scope_tool.validate_scope_fixture(
        SimpleNamespace(host="127.0.0.1", port=13306), "orbit_py_it_" + "a" * 32, fixture()
    )
    names = scope_tool.MATERIAL_SCANNER_CONFIGURATION_SCOPE_CASES
    assert len(names) == len(set(names)) == 12


@pytest.mark.parametrize(
    "status,code,extra",
    [
        (403, "PERMISSION_DENIED", {}),
        (200, "SESSION_REQUIRED", {}),
        (401, "UNKNOWN", {}),
        (401, "SESSION_REQUIRED", {"items": []}),
    ],
)
def test_disabled_identity_assertion_never_accepts_permission_fallback_or_business_body(
    scope_tool, status, code, extra
):
    response = SimpleNamespace(
        status_code=status,
        json=lambda: {"code": code, "message": "安全错误", "request_id": "fixture", **extra},
    )
    with pytest.raises(AssertionError):
        scope_tool.assert_disabled_identity_response(response)


def test_disabled_identity_assertion_matches_native_authentication_boundary(scope_tool):
    scope_tool.assert_disabled_identity_response(
        SimpleNamespace(
            status_code=401,
            json=lambda: {
                "code": "SESSION_REQUIRED",
                "message": "请重新登录",
                "request_id": "fixture",
            },
        )
    )
