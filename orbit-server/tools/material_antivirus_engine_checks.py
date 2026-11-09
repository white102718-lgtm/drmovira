"""实际ClamD适配器内存专项；标准测试串只在内存流中，不写对象或测试文件。"""

import base64
import hashlib
import json
from contextlib import nullcontext
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image

MATERIAL_ANTIVIRUS_ENGINE_CASES = [
    "pythonMaterialAntivirusAdapterActualEngineSafePngCleanInMemory",
    "pythonMaterialAntivirusAdapterActualEngineStandardSignatureInMemoryDetected",
    "pythonMaterialAntivirusAdapterActualEngineNeverCleansChangedSourceHash",
]


def fixture_scanner_policy(manifest_path):
    from orbit_api.material_antivirus import ClamdPolicy

    root = Path(__file__).resolve().parents[2] / ".runtime/tools/clamav-1.5.4"
    supplied = Path(manifest_path).resolve()
    if supplied != (root / "trusted-fixture-manifest.json").resolve():
        raise ValueError("扫描专项仅接受主线固定隔离manifest，不接受任意路径")
    value = json.loads(supplied.read_text("utf-8-sig"))
    assert hashlib.sha256((root / "clamd.conf").read_bytes()).hexdigest() == value["config_sha256"]
    for name, expected in value["database"].items():
        assert name in {"daily", "main", "bytecode"}
        digest = hashlib.sha256()
        with (root / "database" / (name + ".cvd")).open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        assert digest.hexdigest() == expected["sha256"]
    return ClamdPolicy(
        host=value["host"],
        port=value["port"],
        engine_version=value["engine_version"],
        daily_db_version=value["daily_db_version"],
        daily_db_built_at=datetime.fromisoformat(value["daily_db_built_at"]),
        config_sha256=value["config_sha256"],
        max_file_bytes=value["max_file_bytes"],
        max_scan_bytes=value["max_scan_bytes"],
        stream_max_bytes=value["max_stream_bytes"],
        alert_exceeds_max=value["alert_exceeds_max"],
        max_db_age_seconds=value["max_db_age_seconds"],
    )


def run_material_antivirus_engine_checks(scanner, cases):
    class MemorySource:
        def __init__(self, value):
            self.value = value

        def open(self, mode):
            assert mode == "rb"
            return BytesIO(self.value)

    class MemoryObjects:
        def __init__(self, value):
            self.value = value

        def original(self, tenant, upload):
            return MemorySource(self.value)

        def mutation_guard(self, tenant, upload):
            return nullcontext()

    buffer = BytesIO()
    Image.new("RGB", (16, 16), "orange").save(buffer, "PNG")
    content = buffer.getvalue()
    clean = scanner.scan(
        MemoryObjects(content),
        "memory-fixture",
        "no-disk-object",
        hashlib.sha256(content).hexdigest(),
        len(content),
    )
    assert clean.result == "CLEAN" and clean.error_code is None
    cases.append(MATERIAL_ANTIVIRUS_ENGINE_CASES[0])
    # 官方无害标准签名经base64在内存中构造；严禁落盘、打印或混入上传对象。
    signature = base64.b64decode(
        "WDVPIVAlQEFQWzRcUFpYNTQoUF4pN0NDKTd9JEVJQ0FSLVNUQU5EQVJELUFOVElWSVJVUy1URVNULUZJTEUhJEgrSCo="
    )
    infected = scanner.scan(
        MemoryObjects(signature),
        "memory-fixture",
        "no-disk-object",
        hashlib.sha256(signature).hexdigest(),
        len(signature),
    )
    assert infected.result == "INFECTED" and infected.error_code == "ANTIVIRUS_INFECTED"
    cases.append(MATERIAL_ANTIVIRUS_ENGINE_CASES[1])
    changed = scanner.scan(
        MemoryObjects(content), "memory-fixture", "no-disk-object", "a" * 64, len(content)
    )
    assert changed.result == "UNVERIFIED" and changed.error_code == "ANTIVIRUS_OBJECT_CHANGED"
    cases.append(MATERIAL_ANTIVIRUS_ENGINE_CASES[2])
