"""合仓边界必须拒绝私有配置、运行数据及原Java业务目录。"""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "prepare_monorepo", Path(__file__).parents[1] / "prepare_monorepo.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize(
    "path",
    [
        ".env.local",
        "python/ruoyi_fastapi/.env.prod",
        "python/key.pem",
        ".runtime/results.json",
        "node_modules/package/a.js",
        "../outside.py",
        "python/__pycache__/a.pyc",
        "ruoyi-system/src/main/Legacy.java",
    ],
)
def test_excludes_private_and_retired_files(path):
    assert not MODULE.permitted(path, backend=True)


@pytest.mark.parametrize("path", ["python/orbit_api/application.py", "pyproject.toml", "LICENSE"])
def test_keeps_python_sources(path):
    assert MODULE.permitted(path, backend=True)


def test_existing_target_never_overwritten(tmp_path):
    marker = tmp_path / "keep.txt"
    marker.write_text("existing", encoding="utf-8")
    with pytest.raises(ValueError, match="目标目录已存在"):
        MODULE.export(tmp_path, tmp_path, tmp_path)
    assert marker.read_text(encoding="utf-8") == "existing"
