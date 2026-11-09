"""运行证明纯测；注入观察器不是实际OS进程/连接验收。"""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from orbit_api import material_antivirus_runtime as runtime
from orbit_api.errors import OrbitError
from orbit_api.material_antivirus import ClamdMaterialScanner, ScanReceipt


@pytest.fixture
def configured(tmp_path):
    now = datetime.now(UTC)
    database = tmp_path / "databases"
    database.mkdir()
    hashes = {}
    for name in ("daily.cvd", "main.cvd", "bytecode.cvd"):
        path = database / name
        path.write_bytes(b"pure-fixture-" + name.encode())
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    executable = tmp_path / "clamd"
    executable.write_bytes(b"pure-fixture-executable")
    config = tmp_path / "clamd.conf"
    config.write_text(
        f"TCPSocket 19310\nTCPAddr 127.0.0.1\nDatabaseDirectory {database}\n"
        "MaxFileSize 600M\nMaxScanSize 1000M\nStreamMaxLength 600M\nAlertExceedsMax yes\n",
        encoding="utf-8",
    )

    def stamp(value):
        return value.isoformat().replace("+00:00", "Z")

    entry = {
        "revision": 1,
        "instance_id": "00000000-0000-4000-8000-000000000001",
        "pid": 123,
        "created_at_us": int((now - timedelta(minutes=5)).timestamp() * 1_000_000),
        "issued_at": stamp(now - timedelta(minutes=1)),
        "expires_at": stamp(now + timedelta(minutes=5)),
        "source_sha256": "a" * 64,
        "executable": str(executable),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "config_file": str(config),
        "database_directory": str(database),
        "database_files": hashes,
        "policy": {
            "port": 19310,
            "engine_version": "1.5.4",
            "daily_db_version": 28177,
            "daily_db_built_at": stamp(now - timedelta(hours=1)),
            "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
            "max_file_bytes": 600 * 1024**2,
            "max_scan_bytes": 1000 * 1024**2,
            "stream_max_bytes": 600 * 1024**2,
            "alert_exceeds_max": True,
        },
    }
    values = {runtime.PROFILE_KEY: json.dumps({"trusted": entry})}
    return entry, values, lambda: values


def update(configured):
    entry, values, _ = configured
    values[runtime.PROFILE_KEY] = json.dumps({"trusted": entry})


def test_profile_only_explicit_namespace_and_redacted_repr(configured):
    entry, values, provider = configured
    profile = runtime.read_runtime_profile("trusted", provider)
    assert profile.profile_id == "trusted" and profile.revision == 1
    assert profile.policy.port == 19310
    assert entry["config_file"] not in repr(profile)
    values["MATERIAL_SCANNER_PROFILES"] = values.pop(runtime.PROFILE_KEY)
    with pytest.raises(OrbitError, match="扫描实例"):
        runtime.read_runtime_profile("trusted", provider)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda v: v.update(pid=True),
        lambda v: v.update(revision=0),
        lambda v: v.update(executable="relative/path"),
        lambda v: v.update(instance_id="not-uuid"),
        lambda v: v.update(source_sha256="unknown"),
        lambda v: v.update(host="user-chosen.example"),
        lambda v: v["policy"].update(host="192.0.2.1"),
        lambda v: v["policy"].update(alert_exceeds_max=False),
        lambda v: v["database_files"].update({"user-file": "a" * 64}),
    ],
)
def test_profile_rejects_untrusted_or_invalid_fields(configured, mutation):
    entry, _, provider = configured
    mutation(entry)
    update(configured)
    with pytest.raises(OrbitError) as caught:
        runtime.read_runtime_profile("trusted", provider)
    assert caught.value.code == "ANTIVIRUS_PROFILE_UNAVAILABLE"


@pytest.mark.parametrize("raw", ['{"trusted":{},"trusted":{}}', "{}", "x" * 262145])
def test_profile_duplicate_empty_or_oversized_registry_rejected(configured, raw):
    _, values, provider = configured
    values[runtime.PROFILE_KEY] = raw
    with pytest.raises(OrbitError):
        runtime.read_runtime_profile("trusted", provider)


def test_actual_file_hash_and_config_semantics_checked(configured):
    entry, _, provider = configured
    profile = runtime.read_runtime_profile("trusted", provider)
    runtime._config_matches(profile)
    path = runtime.Path(entry["config_file"])
    path.write_text(path.read_text() + "Include untrusted.conf\n")
    entry["policy"]["config_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    update(configured)
    with pytest.raises(OrbitError):
        runtime._config_matches(runtime.read_runtime_profile("trusted", provider))


@pytest.mark.parametrize("changed", ["MaxFileSize 1M", "AlertExceedsMax no", "TCPSocket 19311"])
def test_config_sha_alone_does_not_attest_limits(configured, changed):
    entry, _, provider = configured
    path = runtime.Path(entry["config_file"])
    lines = path.read_text().splitlines()
    key = changed.split()[0]
    path.write_text("\n".join(changed if line.startswith(key + " ") else line for line in lines))
    entry["policy"]["config_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    update(configured)
    with pytest.raises(OrbitError):
        runtime._config_matches(runtime.read_runtime_profile("trusted", provider))


def test_bounded_file_hash_rejects_change_and_limit(configured):
    entry, _, _ = configured
    with pytest.raises(OrbitError):
        runtime._safe_file(entry["executable"], 1)
    assert runtime._safe_file(entry["executable"], 1024) == entry["executable_sha256"]


class Observer:
    def __init__(self, *, fail_at=0):
        self.checked = 0
        self.fail_at = fail_at

    def verify(self, profile):
        self.checked += 1
        if self.checked == self.fail_at:
            raise RuntimeError("不得回显的实际路径或系统消息")


def receipt():
    now = datetime.now(UTC)
    return ScanReceipt("CLEAN", "c" * 64, 10, now, now, "1.5.4", 28177, now, "d" * 64, None)


@pytest.mark.parametrize("fail_at", [1, 2])
def test_runtime_change_before_or_after_scan_never_keeps_clean(configured, monkeypatch, fail_at):
    _, _, provider = configured
    called = []
    monkeypatch.setattr(ClamdMaterialScanner, "scan", lambda *a: called.append(True) or receipt())
    scanner = runtime.ProcessBoundMaterialScanner(
        "trusted", values_provider=provider, observer=Observer(fail_at=fail_at)
    )
    result = scanner.scan(None, "tenant", "upload", "c" * 64, 10)
    assert result.receipt.result == "UNVERIFIED" and result.proof is None
    assert len(called) == fail_at - 1


def test_profile_revision_change_fails_instead_of_switching_endpoint(configured, monkeypatch):
    entry, _, provider = configured
    scanner = runtime.ProcessBoundMaterialScanner(
        "trusted", values_provider=provider, observer=Observer()
    )
    entry["revision"] = 2
    update(configured)
    monkeypatch.setattr(ClamdMaterialScanner, "scan", lambda *a: pytest.fail("不得扫描新profile"))
    result = scanner.scan(None, "tenant", "upload", "c" * 64, 10)
    assert result.receipt.result == "UNVERIFIED" and result.proof is None


def test_result_keeps_separate_runtime_proof_not_policy_sha_reinterpretation(
    configured, monkeypatch
):
    _, _, provider = configured
    original = receipt()
    monkeypatch.setattr(ClamdMaterialScanner, "scan", lambda *a: original)
    observer = Observer()
    scanner = runtime.ProcessBoundMaterialScanner(
        "trusted", values_provider=provider, observer=observer
    )
    result = scanner.scan(None, "tenant", "upload", "c" * 64, 10)
    assert result.receipt is original and result.receipt.policy_sha256 == "d" * 64
    assert result.proof.profile_id == "trusted" and observer.checked == 2
    assert result.proof.profile_sha256 != original.policy_sha256
    assert "executable" not in asdict(result.proof)


def test_invalid_socket_owner_closes_connection_without_fallback(configured, monkeypatch):
    _, _, provider = configured
    closed = []
    connection = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(ClamdMaterialScanner, "_connect", lambda *a: connection)
    observer = Observer()
    observer.verify_connection = lambda *a: (_ for _ in ()).throw(RuntimeError("不可回显"))
    scanner = runtime.ProcessBoundMaterialScanner(
        "trusted", values_provider=provider, observer=observer
    )
    with pytest.raises(OrbitError) as caught:
        scanner._connect(time_deadline := runtime.time.monotonic() + 1)
    assert caught.value.code == "ANTIVIRUS_CONNECTION_UNVERIFIED"
    assert closed == [True] and time_deadline > 0


@pytest.fixture
def process_fixture(configured, monkeypatch):
    import psutil

    _, _, provider = configured
    profile = runtime.read_runtime_profile("trusted", provider)
    connections = [
        SimpleNamespace(status="LISTEN", laddr=SimpleNamespace(ip="127.0.0.1", port=19310))
    ]
    process = SimpleNamespace(
        create_time=lambda: profile.created_at_us / 1_000_000,
        exe=lambda: profile.executable,
        cmdline=lambda: [profile.executable, "--config-file=" + profile.config_file],
        net_connections=lambda **kwargs: connections,
    )
    monkeypatch.setattr(psutil, "Process", lambda pid: process)
    return profile, process, connections


def test_os_observer_requires_process_and_all_trusted_files(process_fixture):
    profile, _, _ = process_fixture
    runtime.PsutilRuntimeObserver().verify(profile)
    runtime.Path(profile.database_directory, "daily.cvd").write_bytes(b"changed-database")
    with pytest.raises(OrbitError):
        runtime.PsutilRuntimeObserver().verify(profile)


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("create_time", lambda: 1),
        ("exe", lambda: "C:/unexpected/clamd.exe"),
        ("cmdline", lambda: ["C:/unexpected/clamd.exe", "--config-file=unknown"]),
        ("net_connections", lambda **kw: []),
    ],
)
def test_os_observer_rejects_pid_reuse_executable_command_or_listener_change(
    process_fixture,
    field,
    replacement,
):
    profile, process, _ = process_fixture
    setattr(process, field, replacement)
    with pytest.raises(OrbitError):
        runtime.PsutilRuntimeObserver().verify(profile)


def test_connection_must_be_established_reverse_tuple_owned_by_pinned_process(process_fixture):
    profile, _, connections = process_fixture
    connections.append(
        SimpleNamespace(
            status="ESTABLISHED",
            laddr=SimpleNamespace(ip="127.0.0.1", port=19310),
            raddr=SimpleNamespace(ip="127.0.0.1", port=45001),
        )
    )
    connection = SimpleNamespace(
        getsockname=lambda: ("127.0.0.1", 45001),
        getpeername=lambda: ("127.0.0.1", 19310),
    )
    runtime.PsutilRuntimeObserver().verify_connection(
        profile, connection, runtime.time.monotonic() + 1
    )


def test_listener_alone_does_not_prove_actual_connection_owner(process_fixture, monkeypatch):
    profile, _, _ = process_fixture
    connection = SimpleNamespace(
        getsockname=lambda: ("127.0.0.1", 45001),
        getpeername=lambda: ("127.0.0.1", 19310),
    )
    values = iter([0, 0.1, 0.2, 0.6])
    monkeypatch.setattr(runtime.time, "monotonic", lambda: next(values))
    monkeypatch.setattr(runtime.time, "sleep", lambda value: None)
    with pytest.raises(OrbitError) as caught:
        runtime.PsutilRuntimeObserver().verify_connection(profile, connection, 1)
    assert caught.value.code == "ANTIVIRUS_CONNECTION_UNVERIFIED"


@pytest.mark.parametrize("offset", [-3600, 3600])
def test_startup_source_expired_or_not_yet_valid_never_scans(configured, monkeypatch, offset):
    entry, _, provider = configured
    now = datetime.now(UTC)
    if offset < 0:
        entry["issued_at"] = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        entry["expires_at"] = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        entry["created_at_us"] = int((now - timedelta(hours=3)).timestamp() * 1_000_000)
    else:
        entry["issued_at"] = (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        entry["expires_at"] = (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    update(configured)
    scanner = runtime.ProcessBoundMaterialScanner(
        "trusted", values_provider=provider, observer=Observer()
    )
    monkeypatch.setattr(ClamdMaterialScanner, "scan", lambda *a: pytest.fail("不得调用扫描"))
    result = scanner.scan(None, "tenant", "upload", "c" * 64, 10)
    assert result.receipt.result == "UNVERIFIED" and result.proof is None


@pytest.mark.parametrize("stage", ["source_verification", "core_scan"])
def test_runtime_source_io_and_core_share_one_absolute_deadline(configured, monkeypatch, stage):
    _, _, provider = configured
    clock = [100.0]
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])

    class SlowObserver(Observer):
        def verify(self, profile):
            super().verify(profile)
            if stage == "source_verification":
                clock[0] += 151

    def core(*args):
        assert stage == "core_scan"
        clock[0] += 151
        return receipt()

    monkeypatch.setattr(ClamdMaterialScanner, "scan", core)
    scanner = runtime.ProcessBoundMaterialScanner(
        "trusted", values_provider=provider, observer=SlowObserver()
    )
    result = scanner.scan(None, "tenant", "upload", "c" * 64, 10)
    assert result.receipt.result == "UNVERIFIED" and result.proof is None
    assert runtime._SCAN_DEADLINE.get() is None


def test_socket_wait_is_clamped_to_remaining_runtime_budget(configured):
    _, _, provider = configured
    scanner = runtime.ProcessBoundMaterialScanner(
        "trusted", values_provider=provider, observer=Observer()
    )
    observed = []
    now = runtime.time.monotonic()
    token = runtime._SCAN_DEADLINE.set(now + 0.25)
    try:
        scanner._timeout(SimpleNamespace(settimeout=observed.append), now + 150)
        assert len(observed) == 1 and 0 < observed[0] <= 0.25
    finally:
        runtime._SCAN_DEADLINE.reset(token)


def test_file_hash_refuses_expired_budget_and_reparse_points(configured, monkeypatch):
    entry, _, _ = configured
    token = runtime._SCAN_DEADLINE.set(runtime.time.monotonic() - 1)
    try:
        with pytest.raises(OrbitError):
            runtime._safe_file(entry["executable"], 1024)
    finally:
        runtime._SCAN_DEADLINE.reset(token)
    monkeypatch.setattr(
        runtime.Path,
        "lstat",
        lambda self: SimpleNamespace(
            st_mode=runtime.stat.S_IFREG,
            st_file_attributes=0x400,
        ),
    )
    with pytest.raises(OrbitError):
        runtime._safe_file(entry["executable"], 1024)
