"""新真实专项的入口/隔离护栏纯测；不执行任何SQL或HTTP。"""

import ast
import inspect
from types import SimpleNamespace

import pytest
from tools.rule_scope_options_checks import (
    RULE_SCOPE_OPTIONS_CASES,
    guard_target,
    run_rule_scope_options_checks,
)

DATABASE = "orbit_py_it_" + "a" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("127.0.0.2", 13306, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE.upper()),
        ("127.0.0.1", 13306, DATABASE + "x"),
        ("127.0.0.1", 13306, None),
    ],
)
def test_explicit_exact_isolated_database_only(host, port, database):
    with pytest.raises(ValueError):
        guard_target(SimpleNamespace(host=host, port=port), database)


def test_guard_first_and_fixed_ten_distinct_names_signature():
    guard_target(SimpleNamespace(host="127.0.0.1", port=13306), DATABASE)
    assert tuple(inspect.signature(run_rule_scope_options_checks).parameters) == (
        "client",
        "admin",
        "headers",
        "password",
        "cache",
        "database",
        "cases",
    )
    assert len(RULE_SCOPE_OPTIONS_CASES) == len(set(RULE_SCOPE_OPTIONS_CASES)) == 10
    source = inspect.getsource(run_rule_scope_options_checks)
    tree = ast.parse(source)
    assert isinstance(tree.body[0].body[0].value, ast.Call)
    assert tree.body[0].body[0].value.func.id == "guard_target"
    # 保留原8并新增2次具名append，不以一个循环重复膨胀通过数。
    appends = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "append"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "cases"
    ]
    assert len(appends) == 10


def test_original_eight_cases_kept_and_real_mutations_not_sql_head():
    assert RULE_SCOPE_OPTIONS_CASES[:8] == (
        "pythonRuleScopeOptionsOriginalActionOnlyWithoutBorrowedMenus",
        "pythonRuleScopeOptionsOperatorFourSizesExactBusinessUuidAndHistoricalDisabled",
        "pythonRuleScopeOptionsVendorFourFieldsAliasUnknownAndUnavailableHistory",
        "pythonRuleScopeOptionsUserAndTeamExplicitManagementDualAccountIntersection",
        "pythonRuleScopeOptionsBothReferenceScopesAndLiteralPrefix",
        "pythonRuleScopeOptionsCursorSessionKindSizeFilterAndAllSourceClocks",
        "pythonRuleScopeOptionsImmediateActionRevocationAndMissingRuleHidden",
        "pythonRuleScopeOptionsStrictGetNoBodyDuplicateUnknownAndNoBusinessWrites",
    )
    source = inspect.getsource(run_rule_scope_options_checks)
    assert 'write_rule("PUT"' in source or '"PUT",' in source
    assert '"/archive"' in source
    assert "UPDATE orbit_rule_head" not in source and "INSERT INTO orbit_rule_head" not in source
    assert "INSERT INTO orbit_tenant" in source and "JOIN orbit_reference_record" in source
    assert 'rejected["code"] == "OWNER_UNAVAILABLE"' in source
    assert 'rejected["code"] == "OWNERSHIP_DENIED"' in source


def test_readonly_http_except_private_role_and_login_no_platform():
    source = inspect.getsource(run_rule_scope_options_checks)
    assert '"/api/v1/roles"' in source
    assert '"/api/v1/rules/editor-scope-options"' in source
    assert "fixture_login" in source and "SELECT DATABASE()" in source
    assert "graph.facebook" not in source and "connect(" not in source
    assert "DROP " not in source and "TRUNCATE " not in source
    assert "SQL_ONLY" in inspect.getmodule(run_rule_scope_options_checks).__doc__
