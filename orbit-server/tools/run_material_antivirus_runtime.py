"""单队列固定本机真实进程证明专项；保留失败，不初始化业务数据库。"""

import hashlib
import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from material_antivirus_runtime_checks import (  # noqa: E402
    MATERIAL_ANTIVIRUS_RUNTIME_CASES,
    run_material_antivirus_runtime_checks,
)


def main():
    output = ROOT / "docs/orbit/evidence/python-material-antivirus-runtime.json"
    if output.exists():
        raise ValueError("证据已存在，先归档，不无声覆盖")
    cases = []
    result = {
        "name": "python-material-antivirus-runtime",
        "result": "FAIL",
        "executed_at": datetime.now(UTC).isoformat(),
        "command": ".venv/Scripts/python.exe tools/run_material_antivirus_runtime.py",
        "scope": (
            "固定本机实际ClamD/PID/连接四元组；负例是期望证明漂移，非实际换进程/SQL030或生产验收"
        ),
    }
    try:
        result["measurements"] = run_material_antivirus_runtime_checks(cases)
        assert cases == MATERIAL_ANTIVIRUS_RUNTIME_CASES
        result["result"] = "PASS"
    except Exception as error:
        result["failure_type"] = type(error).__name__
        result["failure_frames"] = [
            {
                "file": str(Path(frame.filename).relative_to(ROOT)).replace("\\", "/"),
                "line": frame.lineno,
            }
            for frame in traceback.extract_tb(error.__traceback__)
            if Path(frame.filename).is_relative_to(ROOT)
        ]
    result["summary"] = {
        "expected": len(MATERIAL_ANTIVIRUS_RUNTIME_CASES),
        "passed": len(cases),
        "cases": cases,
    }
    names = [
        "tools/run_material_antivirus_runtime.py",
        "tools/material_antivirus_runtime_checks.py",
        "tools/clamd_fixture_attestation.py",
        "tools/material_antivirus_engine_checks.py",
        "python/orbit_api/material_antivirus_runtime.py",
        "python/orbit_api/material_antivirus.py",
        "pyproject.toml",
    ]
    result["source_sha256"] = {
        name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in names
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
