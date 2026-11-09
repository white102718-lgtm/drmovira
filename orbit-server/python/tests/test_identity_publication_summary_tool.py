"""055专项工具护栏，不连接DB，不替代DDL/HTTP/锁等待真实结果。"""

import ast
import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools/identity_publication_summary_checks.py"
spec = importlib.util.spec_from_file_location("identity_publication_summary_checks", SOURCE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_exact_default_cases_and_capacity_remain_separate():
    assert len(tool.IDENTITY_SUMMARY_CASES) == len(set(tool.IDENTITY_SUMMARY_CASES)) == 12
    assert len(tool.IDENTITY_SUMMARY_CAPACITY_CASES) == 1
    assert len(tool.IDENTITY_SUMMARY_PUBLIC_CASES) == 1
    assert set(tool.IDENTITY_SUMMARY_CASES).isdisjoint(tool.IDENTITY_SUMMARY_CAPACITY_CASES)
    assert len(set(tool.SUMMARY_TRIGGER_NAMES)) == 13


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("remote.example", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit_preview"),
    ],
)
def test_unsafe_target_rejected_before_sql_or_http(host, port, database):
    admin = SimpleNamespace(host=host, port=port)
    with pytest.raises(ValueError):
        tool.run_identity_publication_summary_checks(None, admin, None, None, None, database, [])


def test_default_never_loads_capacity_and_explicit_exact_ids_only():
    assert tool.guard_summary_options(None) is None
    ids = [str(uuid4()) for _ in range(200)]
    assert tool.guard_summary_options(ids) == tuple(sorted(ids))
    for bad in ([], ids[:199], ids + [str(uuid4())], ids[:199] + [ids[0]], True):
        with pytest.raises(ValueError):
            tool.guard_summary_options(bad)


def test_page_change_fixture_uses_real_name_prefix_without_casefold_or_truncating_name():
    name = " MiXeD摘要" + "长" * 200
    assert tool.fixture_name_columns(name) == (name, name[:191])
    assert tool.fixture_name_columns("") == ("", "")
    source = SOURCE.read_text(encoding="utf-8")
    assert source.count("UPDATE orbit_ad_account SET name=%s,name_prefix=%s") == 3
    assert "assert anchor in candidates and account_id not in candidates" in source
    assert "assert set(current_items) == {account_id, anchor}" in source


def test_parent_runner_signature_is_explicit_and_bounded():
    parameters = inspect.signature(tool.run_identity_publication_summary_checks).parameters
    assert list(parameters) == [
        "client",
        "admin",
        "headers",
        "password",
        "cache",
        "database",
        "cases",
        "cipher",
        "capacity_account_ids",
        "prepare_browser_fixture",
        "prepare_capacity",
        "prepare_http_profile",
        "backend_pid",
    ]
    assert parameters["capacity_account_ids"].default is None
    assert parameters["cipher"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["prepare_browser_fixture"].default is False
    assert parameters["prepare_capacity"].default is False
    assert parameters["backend_pid"].default is None


@pytest.mark.parametrize("value", [None, True, 0, -1, "123"])
def test_capacity_requires_real_api_pid_before_loading(value):
    admin = SimpleNamespace(host="127.0.0.1", port=13306)
    with pytest.raises(ValueError, match="RSS"):
        tool.run_identity_publication_summary_checks(
            None,
            admin,
            None,
            None,
            None,
            "orbit_py_it_" + "a" * 32,
            [],
            prepare_capacity=True,
            backend_pid=value,
        )


@pytest.mark.parametrize("value", [None, 1, "true", [], {}])
def test_capacity_loading_requires_explicit_bool_before_sql(value):
    admin = SimpleNamespace(host="127.0.0.1", port=13306)
    with pytest.raises(ValueError, match="百万容量"):
        tool.run_identity_publication_summary_checks(
            None,
            admin,
            None,
            None,
            None,
            "orbit_py_it_" + "a" * 32,
            [],
            prepare_capacity=value,
        )


def test_capacity_and_browser_cannot_mix_or_override_preloaded_ids():
    admin = SimpleNamespace(host="127.0.0.1", port=13306)
    for kwargs in (
        {"prepare_capacity": True, "prepare_browser_fixture": True},
        {"prepare_capacity": True, "capacity_account_ids": [str(uuid4()) for _ in range(200)]},
    ):
        with pytest.raises(ValueError, match="互斥"):
            tool.run_identity_publication_summary_checks(
                None,
                admin,
                None,
                None,
                None,
                "orbit_py_it_" + "a" * 32,
                [],
                **kwargs,
            )


def test_capacity_loads_actual_protocol_per_account_and_never_copies_seals():
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    loops = [node for node in ast.walk(tree) if isinstance(node, ast.For)]
    loaders = [node for node in loops if ast.unparse(node.iter) == "range(200)"]
    loader = next(
        node
        for node in loaders
        if 'len(json.loads(prepared.payload_json)["resources"]) == 5000'
        in ast.get_source_segment(source, node)
    )
    segment = ast.get_source_segment(source, loader)
    assert "prepared = await prepare(0)" in segment
    assert "receipt = await persist(prepared)" in segment
    assert 'len(json.loads(prepared.payload_json)["resources"]) == 5000' in segment
    assert "(index + 1) % 20 == 0" in segment
    assert "INSERT INTO orbit_identity_inventory_seal" not in segment
    assert "UPDATE" not in segment and "INSERT" not in segment
    assert '"capacity_actual_resources"' in source
    assert '"capacity_load_controlled_graph_gets"' in source
    assert '"capacity_store_seconds"' in source
    assert "capacity_http_seconds=first" in source


def test_capacity_percentiles_keep_all_samples_and_original_target():
    values = list(range(200))
    assert tool.percentile(values, 0.50) == 99
    assert tool.percentile(values, 0.95) == 189
    assert tool.percentile(values, 0.99) == 197
    with pytest.raises(ValueError):
        tool.percentile([float("nan")], 0.95)
    source = SOURCE.read_text(encoding="utf-8")
    assert "threading.Barrier(20)" in source and "for _ in range(10)" in source
    assert 'len(samples) == 200 and measurement["p95_seconds"] <= 1.0' in source
    assert '"backend_rss_before_bytes"' in source
    assert '"backend_rss_after_bytes"' in source


def test_actual_plans_are_from_captured_sql_and_natural_variant_not_fabricated():
    source = SOURCE.read_text(encoding="utf-8")
    assert "statement, parameters = args[2], args[3]" in source
    assert 'cursor.execute("EXPLAIN ANALYZE " + statement, parameters)' in source
    assert 'cursor.execute("EXPLAIN ANALYZE " + natural, parameters)' in source
    assert '"actual_statement": actual' in source
    assert '"natural_without_force_index": without_force' in source
    assert '"actual_had_force_index"' in source
    assert 'set(captured_reads) == {"head", "proof", "seal", "raw", "config"}' in source
    identifier = str(uuid4())
    assert tool.safe_plan("Index lookup id='" + identifier + "' rows=200 loops=1") == (
        "Index lookup id='<UUID>' rows=200 loops=1"
    )


@pytest.mark.parametrize("value", [None, 1, "true", [], {}])
def test_browser_fixture_requires_explicit_bool_before_sql(value):
    admin = SimpleNamespace(host="127.0.0.1", port=13306)
    with pytest.raises(ValueError, match="浏览器fixture"):
        tool.run_identity_publication_summary_checks(
            None,
            admin,
            None,
            None,
            None,
            "orbit_py_it_" + "a" * 32,
            [],
            prepare_browser_fixture=value,
        )


def test_public_http_and_browser_are_complete_source_not_stub_response():
    source = SOURCE.read_text(encoding="utf-8")
    assert '"/api/v1/accounts/extended"' in source
    assert 'f"/api/v1/accounts/{account_id}/details"' in source
    assert 'assert item["details"][field] == expected' in source
    assert '"expected_summary": expected_summary' in source
    assert 'assert {r["usable"] for r in expected["resources"]} == {True, False}' in source
    assert "if not prepare_browser_fixture or browser_fixture is None:" in source
    assert "revoked_at=UTC_TIMESTAMP(6)" in source


def test_rc_uses_parent_owned_helper_and_checks_same_physical_connection():
    source = SOURCE.read_text(encoding="utf-8")
    assert "from orbit_api.read_sessions import read_committed_session" in source
    assert "return read_committed_session(RegistryAdapter)" in source
    assert "restored == rc_id" in source
    assert 'level == "REPEATABLE-READ"' in source
    assert 'isolation_level="READ COMMITTED"' not in source
    assert "SET SESSION transaction_isolation" not in source
    assert "SET TRANSACTION" not in source


def test_thirteen_guard_matrix_and_rollback_keep_exact_errno():
    source = SOURCE.read_text(encoding="utf-8")
    assert "error.args[0] == 1644" in source
    assert "error.orig.args[0] == 1644" in source
    assert "state() == before" in source
    assert "future.result(timeout=5) == 1644" in source
    assert "_locked_wait(observer, writer_id, pending=future)" in source
    assert "observer.autocommit(True)" in source
    assert "DROP TRIGGER " in source  # 仅恢复工具自有故障注入trigger。
    assert "DROP TRIGGER trg_identity_" not in source


def test_network_only_controlled_get_and_zero_resource_reads_in_summary():
    source = SOURCE.read_text(encoding="utf-8")
    assert 'request.method == "GET"' in source
    assert 'request.url.host == "graph.facebook.com"' in source
    assert "engine.pool.checkedout() == 0" in source
    assert '"real_meta_requests": 0' in source
    assert '"orbit_account_identity_resource" in statement' in source
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"os", "subprocess"}
        and node.func.attr in {"system", "Popen", "run"}
        for node in calls
    )


def test_fixture_does_not_modify_existing_tools_or_fabricate_http_routes():
    source = SOURCE.read_text(encoding="utf-8")
    assert "run_identity_publication_checks(" not in source
    assert "inventory_protocol_page" in source
    assert "route.fulfill" not in source
    assert "ISOLATED_PROTOCOL" in source
    assert "ISOLATED_TEST" in source
    assert '".runtime/identity-summary-capacity-current.json"' in source
    assert "open(" not in source
    tree = ast.parse(source)
    writes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "write_text"
    ]
    assert len(writes) == 1  # 只写固定安全运行回执，不修改源/旧工具。
