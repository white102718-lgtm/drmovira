"""新真实桥工具边界自检；不作为实际扫描/HTTP受理验收。"""

import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tools.launch_execution_material_bridge_checks import (
    EXECUTION_MATERIAL_BRIDGE_CASES,
    IsolatedMaterialExecutionProvider,
    run_launch_execution_material_bridge_checks,
)


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "business_database"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
    ],
)
def test_bridge_tool_refuses_other_target_before_cursor_or_objects(host, port, database):
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    with pytest.raises(ValueError):
        run_launch_execution_material_bridge_checks(
            None, admin, {}, database, [], object_root="not-read", registry=None, user_fixture=None
        )
    admin.cursor.assert_not_called()


def test_protocol_provider_is_explicitly_isolated_and_case_inventory_has_no_production_claim():
    assert IsolatedMaterialExecutionProvider.kind == "ISOLATED_TEST"
    assert len(EXECUTION_MATERIAL_BRIDGE_CASES) == len(set(EXECUTION_MATERIAL_BRIDGE_CASES)) == 6
    parameters = inspect.signature(run_launch_execution_material_bridge_checks).parameters
    assert set(parameters) == {
        "client",
        "admin",
        "headers",
        "database",
        "cases",
        "object_root",
        "registry",
        "user_fixture",
    }
    assert all(
        "Meta" not in case and "Production" not in case for case in EXECUTION_MATERIAL_BRIDGE_CASES
    )


def test_plain_child_framework_import_does_not_require_repository_package_path():
    root = Path(__file__).resolve().parents[2]
    script = (
        "import sys;sys.path[:0]="
        + repr([str(root / "tools"), str(root / "python")])
        + ";import launch_execution_material_bridge_checks as m;"
        "assert m.IsolatedMaterialExecutionProvider.kind=='ISOLATED_TEST';"
        "assert len(m.EXECUTION_MATERIAL_BRIDGE_CASES)==6;print('IMPORT_OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root / "python" / "ruoyi_fastapi",
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, "FRAMEWORK工具导入失败"
    assert result.stdout.strip() == "IMPORT_OK"
