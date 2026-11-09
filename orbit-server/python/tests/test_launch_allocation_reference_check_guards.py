"""真实桥工具护栏纯测，无数据库/扫描/进程操作。"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def checks():
    path = Path(__file__).resolve().parents[2] / "tools/launch_allocation_reference_checks.py"
    spec = importlib.util.spec_from_file_location("allocation_reference_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("192.0.2.1", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "production"),
    ],
)
def test_wrong_database_target_rejected_before_files_or_sql(checks, host, port, database):
    with pytest.raises(ValueError):
        checks.validate_target(SimpleNamespace(host=host, port=port), database, "missing")


def test_only_current_backend_uuid_bundle_can_be_used(checks, tmp_path, monkeypatch):
    backend = tmp_path / "backend"
    tools = backend / "tools"
    tools.mkdir(parents=True)
    monkeypatch.setattr(checks, "__file__", str(tools / "launch_allocation_reference_checks.py"))
    root = backend / ".runtime/integration-objects/run-12345678/materials"
    root.mkdir(parents=True)
    admin = SimpleNamespace(host="127.0.0.1", port=13306)
    assert checks.validate_target(admin, "orbit_py_it_" + "a" * 32, root) == root
    for wrong in (tmp_path, root.parent, root / "nested"):
        with pytest.raises(ValueError):
            checks.validate_target(admin, "orbit_py_it_" + "a" * 32, wrong)


def test_exact_eight_case_names_are_unique_and_tool_does_not_insert_clean_proofs(checks):
    assert len(checks.LAUNCH_ALLOCATION_REFERENCE_CASES) == 8
    assert len(set(checks.LAUNCH_ALLOCATION_REFERENCE_CASES)) == 8
    source = Path(checks.__file__).read_text(encoding="utf-8")
    assert "ConfiguredMaterialWorker" in source and "CompletedPart" in source
    assert "INSERT INTO orbit_material_scan_receipt" not in source
    assert "INSERT INTO orbit_material_scan_runtime_proof" not in source
    assert "ISOLATED-SQL-CAPABILITY-NOT-META" in source
    compile(source, checks.__file__, "exec")
