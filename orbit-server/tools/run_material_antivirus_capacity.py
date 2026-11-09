"""单独排队实测500MiB流；不重跑未改Worker/媒体/浏览器，不扩大验收范围。"""

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from clamd_fixture_attestation import attest_fixture
from material_antivirus_capacity_checks import run_material_antivirus_capacity_checks
from material_antivirus_engine_checks import fixture_scanner_policy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from orbit_api.material_antivirus import ClamdMaterialScanner  # noqa: E402


def main():
    receipt = {
        "name": "python-material-antivirus-capacity",
        "phase": "testing",
        "executed_at": datetime.now(UTC).isoformat(),
        "command": ".venv/Scripts/python.exe tools/run_material_antivirus_capacity.py",
        "scope": "实际500MiB ClamD INSTREAM；非HTTP上传/媒体解码/磁盘感染/整进程峰值验收",
        "result": "FAIL",
    }
    cases = []
    try:
        receipt["process_before"] = attest_fixture()
        scanner = ClamdMaterialScanner(
            fixture_scanner_policy(
                ROOT.parent / ".runtime/tools/clamav-1.5.4/trusted-fixture-manifest.json"
            )
        )
        receipt["measurements"] = run_material_antivirus_capacity_checks(scanner, cases)
        receipt["process_after"] = attest_fixture()
        assert receipt["process_before"] == receipt["process_after"]
        receipt["result"] = "PASS"
    except Exception as error:
        # 不记录任意输入流、进程环境或原始异常正文。
        receipt["failure_type"] = type(error).__name__
    receipt["summary"] = {"passed": len(cases), "expected": 2, "cases": cases}
    files = [
        "python/orbit_api/material_antivirus.py",
        "tools/run_material_antivirus_capacity.py",
        "tools/clamd_fixture_attestation.py",
        "tools/material_antivirus_capacity_checks.py",
        "tools/material_antivirus_engine_checks.py",
    ]
    receipt["source_sha256"] = {
        name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in files
    }
    output = ROOT / "docs/orbit/evidence/python-material-antivirus-capacity.json"
    if output.exists():
        raise ValueError("容量证据已存在，须先归档，不能无声覆盖")
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=True))
    return 0 if receipt["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
