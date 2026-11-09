"""053专项工具护栏；不连接数据库，不将静态检查计为SQL/HTTP验收。"""

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools/identity_publication_checks.py"
spec = importlib.util.spec_from_file_location("identity_publication_checks", SOURCE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_case_plan_unique_and_expected_original_get_scope_and_rollback():
    assert len(tool.IDENTITY_PUBLICATION_CASES) == 12
    assert len(set(tool.IDENTITY_PUBLICATION_CASES)) == 12
    names = set(tool.IDENTITY_PUBLICATION_CASES)
    assert "pythonIdentityPublicationAuditAndOutbox1644WholeRollback" in names
    assert "pythonIdentityPublicationUnknownForeignAndUnsyncedObjects" in names
    assert "pythonIdentityPublicationOldRrManagedRevocationCurrentGet" in names


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("external.example", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit_preview"),
    ],
)
def test_wrong_database_is_rejected_before_any_cursor_or_http(host, port, database):
    admin = SimpleNamespace(host=host, port=port)
    with pytest.raises(ValueError):
        tool.run_identity_publication_checks(None, admin, None, None, None, database, [])


def test_candidate_is_additive_and_never_inserts_capability_release():
    sql = (
        ROOT / "docs/orbit/sql-drafts/053_identity_publication_provenance_candidate.sql"
    ).read_text(encoding="utf-8")
    assert sql.count("CREATE TABLE ") == 3
    assert sql.count("CREATE TRIGGER ") == 6
    assert "ALTER TABLE orbit_account_identity" not in sql
    assert "INSERT INTO orbit_identity_capability_release" not in sql
    assert "UTC_FLOOR_MS_V1" in sql
    assert "DECIMAL(65,0)" in sql
    assert "JSON_EXTRACT(receipt_json,'$.revision')) BETWEEN" not in sql


def test_store_owns_no_http_send_and_cannot_self_issue_release():
    source = (ROOT / "python/orbit_api/identity_publication_store.py").read_text(encoding="utf-8")
    assert "INSERT INTO orbit_identity_capability_release" not in source
    tree = ast.parse(source)
    assert not any(
        isinstance(n, ast.Import) and any(v.name in {"httpx", "requests"} for v in n.names)
        for n in ast.walk(tree)
    )
    assert "UTC_TIMESTAMP(6)" in source


def test_runner_callable_signature_matches_parent_contract():
    import inspect

    signature = inspect.signature(tool.run_identity_publication_checks)
    assert list(signature.parameters) == [
        "client",
        "admin",
        "headers",
        "password",
        "cache",
        "database",
        "cases",
        "cipher",
        "prepare_browser_fixture",
        "include_inventory_boundaries",
        "launch_draft_hook",
    ]
    assert signature.parameters["cipher"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["prepare_browser_fixture"].default is False
    assert signature.parameters["include_inventory_boundaries"].default is False


def test_boundary_case_plan_does_not_change_default_original_twelve():
    assert len(tool.IDENTITY_PUBLICATION_CASES) == 12
    assert len(tool.IDENTITY_INVENTORY_BOUNDARY_CASES) == 2
    assert not set(tool.IDENTITY_PUBLICATION_CASES) & set(tool.IDENTITY_INVENTORY_BOUNDARY_CASES)


@pytest.mark.parametrize("total,pages", [(0, 1), (5000, 25), (5001, 26)])
def test_protocol_inventory_has_exact_ids_and_bounded_pages(total, pages):
    after, observed, actual_pages = None, [], 0
    while True:
        rows, after = tool.inventory_protocol_page(total, after)
        assert len(rows) <= 200
        observed += rows
        actual_pages += 1
        if after is None:
            break
        assert actual_pages <= pages
    assert actual_pages == pages
    assert len(observed) == total
    assert len({row["id"] for row in observed}) == total
    assert {row["id"] for row in observed} == {"000000" + str(i).zfill(5) for i in range(total)}


@pytest.mark.parametrize(
    "total,after",
    [
        (True, None),
        (5002, None),
        (5000, "inventory-0"),
        (5000, "inventory-201"),
        (5000, "inventory-5000"),
        (5000, "external-token"),
    ],
)
def test_protocol_fixture_rejects_undeclared_count_and_cursor(total, after):
    with pytest.raises(ValueError):
        tool.inventory_protocol_page(total, after)
