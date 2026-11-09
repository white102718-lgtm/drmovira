"""独立测试profile构造；固定已验签本机实例，不作为生产启动证明签发器。"""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4


def material_runtime_fixture_scanner():
    import psutil
    from clamd_fixture_attestation import ROOT, attest_fixture
    from material_antivirus_engine_checks import fixture_scanner_policy

    from orbit_api.material_antivirus_runtime import PROFILE_KEY, ProcessBoundMaterialScanner

    expected_root = Path(__file__).resolve().parents[2] / ".runtime/tools/clamav-1.5.4"
    assert ROOT.resolve() == expected_root.resolve()
    before = attest_fixture()
    manifest_path = expected_root / "trusted-fixture-manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8-sig"))
    policy = asdict(fixture_scanner_policy(manifest_path))
    policy["daily_db_built_at"] = policy["daily_db_built_at"].isoformat().replace("+00:00", "Z")
    command = psutil.Process(before["pid"]).cmdline()
    assert len(command) == 2 and command[1].startswith("--config-file=")
    config = command[1].removeprefix("--config-file=")
    assert Path(config).resolve() == (expected_root / "clamd.conf").resolve()
    now = datetime.now(UTC)
    entry = {
        "revision": 1,
        "instance_id": str(uuid4()),
        "pid": before["pid"],
        "created_at_us": round(before["process_created_at_epoch"] * 1_000_000),
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
        "source_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "executable": str(expected_root / "unpacked/clamav-1.5.4.win.x64/clamd.exe"),
        "executable_sha256": before["executable_sha256"],
        "config_file": config,
        "database_directory": (expected_root / "database").as_posix(),
        "database_files": {
            key + ".cvd": value["sha256"] for key, value in manifest["database"].items()
        },
        "policy": policy,
    }
    values = {PROFILE_KEY: json.dumps({"fixture": entry})}
    return ProcessBoundMaterialScanner("fixture", values_provider=lambda: values), before


def material_runtime_fixture_payload(scanner):
    """只导出固定夹具的单profile JSON给独占子进程，不导出整个私有配置。"""
    from clamd_fixture_attestation import ROOT, attest_fixture

    from orbit_api.material_antivirus_runtime import (
        PROFILE_KEY,
        ProcessBoundMaterialScanner,
        read_runtime_profile,
    )

    if not isinstance(scanner, ProcessBoundMaterialScanner):
        raise ValueError("视频夹具必须显式提供完整runtime scanner，不能退回裸policy")
    actual = attest_fixture()
    profile = read_runtime_profile(scanner.profile.profile_id, scanner.values_provider)
    if (
        profile != scanner.profile
        or profile.pid != actual["pid"]
        or (
            profile.created_at_us != round(actual["process_created_at_epoch"] * 1_000_000)
            or profile.policy.config_sha256 != actual["config_sha256"]
            or profile.executable_sha256 != actual["executable_sha256"]
            or profile.source_sha256
            != hashlib.sha256((ROOT / "trusted-fixture-manifest.json").read_bytes()).hexdigest()
        )
    ):
        raise ValueError("导出runtime profile与固定本机证明不符")
    profile.validate_time(datetime.now(UTC))
    entries = json.loads(scanner.values_provider()[PROFILE_KEY])
    return {
        "profile_id": profile.profile_id,
        "profiles": {profile.profile_id: entries[profile.profile_id]},
    }
