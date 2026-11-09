"""固定本机真实ClamD实例证明专项；不重启/改配置，不从任意环境读取profile。"""

import copy
import hashlib
import json
from contextlib import nullcontext
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image

MATERIAL_ANTIVIRUS_RUNTIME_CASES = [
    "pythonMaterialRuntimeActualPinnedEngineSafePngCleanWithSeparateProof",
    "pythonMaterialRuntimeActualAcceptedConnectionsOwnedByPinnedPid",
    "pythonMaterialRuntimeProfileRevisionDriftRejectedBeforeObjectRead",
    "pythonMaterialRuntimeActualPidBirthDriftRejectedWithoutRestart",
    "pythonMaterialRuntimeActualConfigDigestMismatchRejectedWithoutEditingFile",
    "pythonMaterialRuntimeExpiredTrustedSourceRejectedBeforeObjectRead",
]


def run_material_antivirus_runtime_checks(cases):
    from clamd_fixture_attestation import ROOT, attest_fixture
    from material_antivirus_engine_checks import fixture_scanner_policy

    from orbit_api.material_antivirus_runtime import (
        PROFILE_KEY,
        ProcessBoundMaterialScanner,
        PsutilRuntimeObserver,
    )

    before = attest_fixture()
    fixed_root = Path(__file__).resolve().parents[2] / ".runtime/tools/clamav-1.5.4"
    assert ROOT.resolve() == fixed_root.resolve()
    manifest_path = fixed_root / "trusted-fixture-manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8-sig"))
    policy = asdict(fixture_scanner_policy(manifest_path))
    policy["daily_db_built_at"] = policy["daily_db_built_at"].isoformat().replace("+00:00", "Z")
    # 仅固定已验签实例的现有命令格式；既不采集环境，也不允许外部路径参数。
    import psutil

    process = psutil.Process(before["pid"])
    command = process.cmdline()
    assert len(command) == 2 and command[1].startswith("--config-file=")
    config_file = command[1].removeprefix("--config-file=")
    assert Path(config_file).resolve() == (fixed_root / "clamd.conf").resolve()
    now = datetime.now(UTC)
    entry = {
        "revision": 1,
        "instance_id": str(uuid4()),
        "pid": before["pid"],
        "created_at_us": round(before["process_created_at_epoch"] * 1_000_000),
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
        "source_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "executable": str(fixed_root / "unpacked/clamav-1.5.4.win.x64/clamd.exe"),
        "executable_sha256": before["executable_sha256"],
        "config_file": config_file,
        "database_directory": (fixed_root / "database").as_posix(),
        "database_files": {
            key + ".cvd": value["sha256"] for key, value in manifest["database"].items()
        },
        "policy": policy,
    }
    values = {PROFILE_KEY: json.dumps({"fixture": entry})}
    opens = []
    buffer = BytesIO()
    Image.new("RGB", (16, 16), "orange").save(buffer, "PNG")
    content = buffer.getvalue()
    digest = hashlib.sha256(content).hexdigest()

    class MemorySource:
        def open(self, mode):
            assert mode == "rb"
            opens.append(True)
            return BytesIO(content)

    class MemoryObjects:
        def original(self, tenant, upload):
            assert (tenant, upload) == ("runtime-fixture", "no-disk-object")
            return MemorySource()

        def mutation_guard(self, tenant, upload):
            return nullcontext()

    class ObservedActualObserver(PsutilRuntimeObserver):
        # 只计数真实父类成功返回，不替换任何OS观察/连接/哈希结果。
        connections_verified = 0

        def verify_connection(self, profile, connection, deadline):
            super().verify_connection(profile, connection, deadline)
            self.connections_verified += 1

    observer = ObservedActualObserver()
    scanner = ProcessBoundMaterialScanner(
        "fixture", values_provider=lambda: values, observer=observer
    )
    result = scanner.scan(
        MemoryObjects(), "runtime-fixture", "no-disk-object", digest, len(content)
    )
    assert result.receipt.result == "CLEAN" and result.receipt.error_code is None, (
        result.receipt.result,
        result.receipt.error_code,
    )
    assert result.proof is not None and result.proof.instance_id == entry["instance_id"]
    assert result.proof.config_sha256 == before["config_sha256"]
    cases.append(MATERIAL_ANTIVIRUS_RUNTIME_CASES[0])
    assert observer.connections_verified == 3
    assert result.proof.verified_before <= result.proof.verified_after < result.proof.expires_at
    cases.append(MATERIAL_ANTIVIRUS_RUNTIME_CASES[1])

    def require_unknown(candidate):
        count = len(opens)
        rejected = candidate.scan(
            MemoryObjects(),
            "runtime-fixture",
            "no-disk-object",
            digest,
            len(content),
        )
        assert rejected.receipt.result == "UNVERIFIED" and rejected.proof is None
        assert len(opens) == count

    changed = copy.deepcopy(entry)
    changed["revision"] = 2
    values[PROFILE_KEY] = json.dumps({"fixture": changed})
    require_unknown(scanner)
    cases.append(MATERIAL_ANTIVIRUS_RUNTIME_CASES[2])
    for index, mutate in [
        (3, lambda value: value.update(created_at_us=value["created_at_us"] + 1000)),
        (4, lambda value: value["policy"].update(config_sha256="0" * 64)),
        (
            5,
            lambda value: value.update(
                issued_at=(now - timedelta(seconds=10)).isoformat().replace("+00:00", "Z"),
                expires_at=(now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
            ),
        ),
    ]:
        changed = copy.deepcopy(entry)
        mutate(changed)
        values[PROFILE_KEY] = json.dumps({"fixture": changed})
        require_unknown(ProcessBoundMaterialScanner("fixture", values_provider=lambda: values))
        cases.append(MATERIAL_ANTIVIRUS_RUNTIME_CASES[index])
    after = attest_fixture()
    assert before == after
    return {
        "actual_engine_clean": True,
        "actual_pid_bound_connections": observer.connections_verified,
        "fixed_process_unchanged": before == after,
        "scope": "Fixed actual OS process and PNG stream; profile expectation drift negatives, "
        "no process restart/config edit; no SQL030/HTTP/production launcher acceptance",
    }
