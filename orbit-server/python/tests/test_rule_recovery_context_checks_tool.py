"""HTTP工具护栏纯测；不连接数据库，不代替真实授权/CSRF专项。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from tools.rule_recovery_context_checks import (
    ACTIONS,
    NATIVE_ACTORS,
    RULE_RECOVERY_CONTEXT_CASES,
    assert_context,
    assert_no_context,
    guard_target,
    native_response,
)


def value():
    return {"actor_id": 1, "tenant_id": str(uuid4()), "csrf_token": "a" * 32}


def test_exact_context_valid_and_preserves_original_token():
    item = value()
    assert assert_context(item, 1, item["tenant_id"]) is item


@pytest.mark.parametrize(
    "change",
    [
        {"actor_id": True},
        {"actor_id": "1"},
        {"actor_id": 2},
        {"tenant_id": str(uuid4())},
        {"csrf_token": None},
        {"csrf_token": "a" * 15},
        {"csrf_token": "a" * 256},
        {"other": "forbidden"},
    ],
)
def test_bad_context_fail_closed_without_secret_diagnostic(change):
    item = value()
    tenant = item["tenant_id"]
    item.update(change)
    with pytest.raises(AssertionError) as error:
        assert_context(item, 1, tenant)
    assert "csrf_token" not in str(error.value)


@pytest.mark.parametrize("missing", ["actor_id", "tenant_id", "csrf_token"])
def test_partial_context_rejected(missing):
    item = value()
    del item[missing]
    with pytest.raises(AssertionError):
        assert_context(item, 1, str(uuid4()))


@pytest.mark.parametrize("field", ["actor_id", "tenant_id", "csrf_token"])
def test_denied_response_must_not_contain_partial_context(field):
    assert_no_context({"code": "PERMISSION_DENIED", "message": "blocked"})
    with pytest.raises(AssertionError):
        assert_no_context({"code": "PERMISSION_DENIED", field: None})


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("remote.example", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", True, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "production"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
    ],
)
def test_wrong_target_rejected_before_any_sql(host, port, database):
    with pytest.raises(ValueError):
        guard_target(SimpleNamespace(host=host, port=port), database)


def test_fixed_finite_cases_and_exact_six_original_permissions():
    assert len(RULE_RECOVERY_CONTEXT_CASES) == len(set(RULE_RECOVERY_CONTEXT_CASES)) == 8
    assert len(NATIVE_ACTORS) == len(set(NATIVE_ACTORS)) == 6
    assert ACTIONS == {
        "CREATE": "rules.create",
        "UPDATE": "rules.edit",
        "ENABLE": "rules.enable",
        "PAUSE": "rules.pause",
        "ARCHIVE": "rules.archive",
        "SIMULATE": "rules.read",
    }


def test_native_protocol_does_not_require_orbit_cache_control():
    login = {"code": 200, "token": "fixture-token-" + "a" * 32}
    assert native_response(SimpleNamespace(status_code=200, json=lambda: login)) is login
    info = {"code": 200, "user": {"userId": 12}, "permissions": ["rules.read"]}
    assert native_response(SimpleNamespace(status_code=200, json=lambda: info), actor=12) is info


@pytest.mark.parametrize(
    "body,actor,status",
    [
        ({"code": 200, "token": "short"}, None, 200),
        ({"code": "200", "token": "a" * 32}, None, 200),
        ({"code": 401, "token": "a" * 32}, None, 200),
        ({"code": 200, "token": "a" * 32}, None, 401),
        ({"code": 200, "user": {"userId": 13}, "permissions": []}, 12, 200),
        ({"code": 200, "user": {"userId": True}, "permissions": []}, 1, 200),
        ({"code": 200, "user": {"userId": 12}, "permissions": "rules.read"}, 12, 200),
        ({"code": 200, "user": {"userId": 12}, "permissions": [1]}, 12, 200),
    ],
)
def test_native_malformed_protocol_stays_rejected(body, actor, status):
    with pytest.raises(AssertionError):
        native_response(SimpleNamespace(status_code=status, json=lambda: body), actor=actor)
