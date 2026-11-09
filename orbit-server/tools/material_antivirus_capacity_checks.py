"""真实500MiB INSTREAM线协议容量；有界虚拟安全流，非500MiB视频/磁盘验收。"""

import hashlib
import json
import time
from contextlib import nullcontext

MATERIAL_ANTIVIRUS_CAPACITY_CASES = [
    "pythonMaterialAntivirusActuallyStreamsFiveHundredMiBWithinVerifiedPolicy",
    "pythonMaterialAntivirusOneByteOverClientLimitNeverOpensSource",
]


def run_material_antivirus_capacity_checks(scanner, cases):
    # 固定无害零字节流；不得替换为用户文件或标准测试签名，块大小不随总量增长。
    block = b"\0" * (1024 * 1024)
    limit = 500 * 1024 * 1024
    digest = hashlib.sha256()
    for _ in range(500):
        digest.update(block)
    expected = digest.hexdigest()
    observed = {"opened": 0, "bytes": 0, "maximum_requested": 0}

    class Source:
        def __init__(self):
            self.remaining = limit

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, maximum):
            assert 0 < maximum <= len(block)
            observed["maximum_requested"] = max(observed["maximum_requested"], maximum)
            size = min(self.remaining, maximum)
            self.remaining -= size
            observed["bytes"] += size
            return block[:size]

    class VirtualObject:
        def open(self, mode):
            assert mode == "rb"
            observed["opened"] += 1
            return Source()

    class MemoryObjects:
        def original(self, tenant, upload):
            assert (tenant, upload) == ("memory-capacity", "no-disk-object")
            return VirtualObject()

        def mutation_guard(self, tenant, upload):
            return nullcontext()

    started = time.monotonic()
    receipt = scanner.scan(MemoryObjects(), "memory-capacity", "no-disk-object", expected, limit)
    elapsed = time.monotonic() - started
    diagnostic = {
        "phase": "actual_500_mib_stream",
        "result": receipt.result,
        "error_code": receipt.error_code,
        "elapsed_seconds": round(elapsed, 3),
        "source_opened": observed["opened"],
        "source_read_bytes": observed["bytes"],
        "source_max_read_bytes": observed["maximum_requested"],
        "expected_bytes": limit,
    }
    # 主线runner只保存异常类型；断言前独立输出固定字段，不含内容/连接/路径/凭据。
    print("MATERIAL_CAPACITY_DIAGNOSTIC " + json.dumps(diagnostic, sort_keys=True), flush=True)
    assert receipt.result == "CLEAN" and receipt.error_code is None, (
        receipt.result,
        receipt.error_code,
    )
    assert observed == {"opened": 1, "bytes": limit, "maximum_requested": len(block)}
    assert receipt.sha256 == expected and receipt.byte_size == limit
    cases.append(MATERIAL_ANTIVIRUS_CAPACITY_CASES[0])
    before = dict(observed)
    rejected = scanner.scan(
        MemoryObjects(), "memory-capacity", "no-disk-object", expected, limit + 1
    )
    print(
        "MATERIAL_CAPACITY_DIAGNOSTIC "
        + json.dumps(
            {
                "phase": "one_byte_over_limit",
                "result": rejected.result,
                "error_code": rejected.error_code,
                "source_unchanged": observed == before,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    assert rejected.result == "UNVERIFIED" and rejected.error_code == "ANTIVIRUS_OBJECT_INVALID"
    assert rejected.engine_version is None and observed == before
    cases.append(MATERIAL_ANTIVIRUS_CAPACITY_CASES[1])
    return {
        "actual_streamed_bytes": limit,
        "elapsed_seconds": round(elapsed, 3),
        "source_max_read_bytes": observed["maximum_requested"],
        "scope": "Actual ClamD INSTREAM only; no video decode, HTTP upload, DB Worker, "
        "disk infection, or full process RSS measurement",
    }
