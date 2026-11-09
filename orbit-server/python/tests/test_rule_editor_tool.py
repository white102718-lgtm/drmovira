"""编辑辅助真实工具的零DB护栏；不替代实际角色/候选HTTP。"""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

m = importlib.import_module("tools.rule_editor_checks")
DATABASE = "orbit_py_it_" + "a" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE + "\n"),
    ],
)
def test_isolated_guard_before_sql_or_http(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError):
        m.run_rule_editor_checks(client, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()
    client.get.assert_not_called()


def test_case_names_new_limited_eight_not_original_rule_api_evidence():
    assert len(m.RULE_EDITOR_CASES) == len(set(m.RULE_EDITOR_CASES)) == 8
    assert all(name.startswith("pythonRuleEditor") for name in m.RULE_EDITOR_CASES)


def test_literal_sql_bound_parameters_match_tuple_arguments():
    tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
    checked = 0
    for call in ast.walk(tree):
        if (
            not isinstance(call, ast.Call)
            or not isinstance(call.func, ast.Name)
            or call.func.id != "sql"
            or len(call.args) < 2
            or not isinstance(call.args[0], ast.Constant)
            or not isinstance(call.args[0].value, str)
            or not isinstance(call.args[1], ast.Tuple)
        ):
            continue
        assert call.args[0].value.count("%s") == len(call.args[1].elts)
        checked += 1
    assert checked >= 15


@pytest.mark.parametrize(
    "code,expected",
    [
        (401, 401),
        ("SESSION_REQUIRED", "SESSION_REQUIRED"),
        ("secret-token-value", None),
        ({"token": "secret"}, None),
        (True, None),
    ],
)
def test_checked_prints_only_safe_status_diagnostic(code, expected, capsys):
    response = SimpleNamespace(
        status_code=401,
        headers={},
        json=lambda: {"code": code, "token": "secret", "msg": "password-secret"},
    )
    with pytest.raises(AssertionError, match="^RULE_EDITOR_HTTP_STATUS_MISMATCH$"):
        m.checked(response)
    import json

    output = capsys.readouterr().out
    assert json.loads(output) == {
        "scope": "rule-editor-fixture",
        "phase": "http-status",
        "expected": 200,
        "actual": 401,
        "code": expected,
    }
    assert "secret" not in output and "token" not in output and "password" not in output


def test_successful_login_stays_strict_and_silent(capsys):
    value = {"token": "secret"}
    response = SimpleNamespace(
        status_code=200, headers={"cache-control": "no-store"}, json=lambda: value
    )
    assert m.checked(response) is value
    assert capsys.readouterr().out == ""
    response.headers.clear()
    with pytest.raises(AssertionError):
        m.checked(response)


def test_native_fixture_retains_original_authentication_bindings():
    source = Path(m.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    statements = [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "sql"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]
    assert any(
        "INSERT INTO sys_identity_subject(user_id,subject_id,auth_version,create_time)" in text
        and "VALUES(%s,%s,1,UTC_TIMESTAMP(3))" in text
        for text in statements
    )
    assert any(
        "INSERT INTO sys_user_role(user_id,role_id) VALUES(%s,%s)" in text for text in statements
    )
    assert any(
        "INSERT INTO orbit_user_scope(user_id,tenant_id,data_role)" in text and "'USER'" in text
        for text in statements
    )
    assert any(
        "INSERT INTO orbit_business_user" in text
        and "invited" in text
        and ",0,UTC_TIMESTAMP(3))" in text
        for text in statements
    )
    # 与已通过的原规则夹具相同：复制原root已验证密码hash，经原登录接口签发会话。
    assert any("password,'0','0' FROM sys_user WHERE user_id=1" in text for text in statements)
    assert 'fixture_login(client, cache, {"username": username, "password": password})' in source
    assert "ORBIT_TRUST" not in source


@pytest.mark.parametrize(
    "change", ["self", "wrong_owner", "wrong_team", "noncanonical_id", "state", "revision"]
)
def test_foreign_fixture_requires_real_different_owner_and_original_created_rule(change):
    from uuid import uuid4

    owner, actor, team = str(uuid4()), str(uuid4()), str(uuid4())
    rule = {
        "id": str(uuid4()),
        "ownership": {"owner_user_id": owner, "owner_team_id": team},
        "revision": 1,
        "state": "DRAFT",
    }
    m.assert_foreign_rule(rule, owner, actor, team)
    if change == "self":
        actor = owner
    elif change == "wrong_owner":
        rule["ownership"]["owner_user_id"] = actor
    elif change == "wrong_team":
        rule["ownership"]["owner_team_id"] = str(uuid4())
    elif change == "noncanonical_id":
        rule["id"] = "not-an-id"
    elif change == "state":
        rule["state"] = "ARCHIVED"
    else:
        rule["revision"] = 2
    with pytest.raises((AssertionError, ValueError)):
        m.assert_foreign_rule(rule, owner, actor, team)


def test_foreign_rule_is_seeded_through_original_http_before_readonly_baseline():
    source = Path(m.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    seed = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "seed_rule"
    )
    endpoints = [
        node.args[0].value
        for node in ast.walk(seed)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "post"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    ]
    assert endpoints == ["/api/v1/scope-snapshots", "/api/v1/rules"]
    assert "rule = seed_rule(owner)" in source and "foreign_rule = seed_rule(root_owner)" in source
    assert source.index("foreign_rule = seed_rule(root_owner)") < source.index(
        "foreign_baseline = counts()"
    )
    assert "assert counts() == foreign_baseline" in source
    assert '"rule_id": foreign_rule["id"]}, status=404' in source
    assert "ORDER BY id LIMIT 1" not in source
