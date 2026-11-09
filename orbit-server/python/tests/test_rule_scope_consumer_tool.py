"""新RULE消费真实工具护栏纯测；不代替真实SQL/HTTP或并发验收。"""

import ast
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

m = importlib.import_module("tools.rule_scope_consumer_checks")
DATABASE = "orbit_py_it_" + "a" * 32


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE + "\n"),
        ("127.0.0.1", 13306, None),
    ],
)
def test_guard_precedes_all_sql_http_and_fixture_import(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    client = Mock()
    with pytest.raises(ValueError, match="^RULE_CONSUMER_ISOLATED_UUID_REQUIRED$"):
        m.run_rule_scope_consumer_checks(client, admin, {}, "unused", None, database, [])
    admin.cursor.assert_not_called()
    client.get.assert_not_called()
    client.post.assert_not_called()


def test_eight_cases_and_exact_seven_argument_queue_entry():
    assert len(m.RULE_SCOPE_CONSUMER_CASES) == len(set(m.RULE_SCOPE_CONSUMER_CASES)) == 8
    assert list(inspect.signature(m.run_rule_scope_consumer_checks).parameters) == [
        "client",
        "admin",
        "headers",
        "password",
        "cache",
        "database",
        "cases",
    ]
    assert all(name.startswith("pythonRuleScopeConsumer") for name in m.RULE_SCOPE_CONSUMER_CASES)


def test_all_literal_sql_bound_parameter_counts_and_no_raw_percent():
    tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
    checked = 0
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or len(node.args) < 2
            or not isinstance(node.args[0], ast.Constant)
            or not isinstance(node.args[0].value, str)
            or not isinstance(node.args[1], ast.Tuple)
        ):
            continue
        is_sql = (isinstance(node.func, ast.Name) and node.func.id == "sql") or (
            isinstance(node.func, ast.Attribute) and node.func.attr == "execute"
        )
        if not is_sql:
            continue
        statement = node.args[0].value
        assert statement.count("%s") == len(node.args[1].elts)
        assert "%" not in statement.replace("%s", "")
        checked += 1
    assert checked >= 20


def test_collision_clone_full_four_tables_build_members_seal_audit_outbox_same_transaction():
    tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
    run = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_rule_scope_consumer_checks"
    )
    begin = next(
        index
        for index, node in enumerate(run.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "admin"
        and node.value.func.attr == "begin"
    )
    transaction = run.body[begin + 1]
    assert isinstance(transaction, ast.Try)
    statements = []
    for node in ast.walk(transaction):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
        ):
            assert isinstance(node.args[0], ast.Constant)
            statements.append(node.args[0].value)
    assert len(statements) == 5
    assert statements[0].startswith("INSERT INTO orbit_account_scope_snapshot")
    assert ",0,NULL,0," in statements[0]  # 不直接伪造ready成功header。
    assert statements[1].startswith("INSERT INTO orbit_account_scope_member")
    assert statements[2].startswith("UPDATE orbit_account_scope_snapshot SET ready=1")
    assert statements[3].startswith("INSERT INTO orbit_account_scope_event")
    assert statements[4].startswith("INSERT INTO orbit_account_scope_outbox")
    source = ast.unparse(transaction)
    assert "admin.commit()" in source and "admin.rollback()" in source and "raise" in source
    assert "FOREIGN_KEY_CHECKS" not in source and "DROP TRIGGER" not in source


def test_concurrency_is_real_requests_barrier_without_retry_or_mock_success():
    tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
    race = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "race"
    )
    calls = [node for node in ast.walk(race) if isinstance(node, ast.Call)]
    assert (
        sum(isinstance(node.func, ast.Attribute) and node.func.attr == "post" for node in calls)
        == 1
    )
    assert not any(isinstance(node, (ast.For, ast.While)) for node in ast.walk(race))
    source = Path(m.__file__).read_text(encoding="utf-8")
    assert "ThreadPoolExecutor(max_workers=2)" in source and "Barrier(2)" in source
    literal_lists = [
        ast.literal_eval(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.List) and all(isinstance(item, ast.Constant) for item in node.elts)
    ]
    assert [201, 409] in literal_lists and [0, 1, 2, 1, 1, 1, 1, 1] in literal_lists
    assert "route.fulfill" not in source and "sleep(" not in source
