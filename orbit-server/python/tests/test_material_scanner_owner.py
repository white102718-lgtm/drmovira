"""受控所有者注入纯测：不启动/停止任何进程，不把假health当实际引擎验收。"""

import asyncio
import hashlib
import json
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from orbit_api.errors import OrbitError
from orbit_api.material_antivirus import ClamdPolicy
from orbit_api.material_scanner_owner import MaterialScannerOwner
from orbit_api.material_scanner_owner_definition import ScannerOwnerDefinition, verify_owner_files
from orbit_api.material_scanner_registry import MaterialScannerRegistry, ScannerProbeResult


@pytest.fixture
def definition(tmp_path):
    installed, owned = tmp_path / "approved-install", tmp_path / "owned-instance"
    installed.mkdir()
    owned.mkdir()
    database = installed / "database"
    database.mkdir()
    files = []
    for name in ("main.cvd", "daily.cvd", "bytecode.cvd"):
        data = b"pure unit bytes " + name.encode()
        (database / name).write_bytes(data)
        files.append((name, hashlib.sha256(data).hexdigest()))
    executable, receipt = (
        installed / "not-executable-fixture.exe",
        installed / "approval-receipt.json",
    )
    executable.write_bytes(b"pure fixture, must never execute")
    receipt.write_bytes(b"pure pinned bytes, not an actual official signature proof")
    config = owned / "clamd.conf"
    config.write_text(
        f"DatabaseDirectory {database}\nTCPSocket 19311\nTCPAddr 127.0.0.1\nForeground yes\n"
        f"TemporaryDirectory {owned}\nMaxFileSize 600M\nMaxScanSize 1000M\nStreamMaxLength 600M\n"
        "AlertExceedsMax yes\nMaxThreads 2\nMaxQueue 8\nMaxScanTime 120000\n",
        encoding="utf-8",
    )
    now = datetime.now(UTC)
    config_sha = hashlib.sha256(config.read_bytes()).hexdigest()
    return ScannerOwnerDefinition(
        "owner-fixture",
        1,
        "纯测所有者",
        installed,
        owned,
        executable,
        hashlib.sha256(executable.read_bytes()).hexdigest(),
        config,
        config_sha,
        database,
        tuple(files),
        receipt,
        hashlib.sha256(receipt.read_bytes()).hexdigest(),
        now - timedelta(minutes=1),
        now + timedelta(minutes=20),
        ClamdPolicy(
            19311,
            "1.5.4",
            28177,
            now - timedelta(hours=1),
            config_sha,
            600 * 1024**2,
            1000 * 1024**2,
            600 * 1024**2,
            True,
        ),
    )


class FakeAdapter:
    def __init__(self, registry):
        self.registry, self.events = registry, []
        self.available, self.supported, self.running = True, True, True
        self.close_failure = False
        self.process = SimpleNamespace(
            pid=123,
            created_at_us=int((datetime.now(UTC) - timedelta(seconds=1)).timestamp() * 1_000_000),
        )

    def require_job_support(self):
        self.events.append("job-support")
        if not self.supported:
            raise OrbitError(503, "SCANNER_OWNER_JOB_UNAVAILABLE", "纯测")

    def port_available(self, port, deadline):
        self.events.append("port")
        assert port == 19311
        return self.available

    def spawn(self, executable, config_file, owned_root, deadline):
        self.events.append("spawn")
        return self.process

    def alive(self, process):
        assert process is self.process
        self.events.append("alive")
        return self.running

    def close_owned(self, process, expected, deadline):
        self.events.append("close")
        assert not self.registry.candidates(), "必须先撤销公开registry再关闭自有进程"
        assert process is self.process and expected == (process.pid, process.created_at_us)
        if self.close_failure:
            raise OrbitError(503, "SCANNER_OWNER_CLOSE_FAILED", "纯测")
        self.running = False


def make_owner(*, health=None, audit=None, **kwargs):
    registry = MaterialScannerRegistry()
    adapter, events = FakeAdapter(registry), []

    async def fake_health(scanner, deadline):
        assert registry.candidates() == [], "健康成功前不能公开候选"
        events.append("health")
        private = MaterialScannerRegistry()
        binding = private.publish(scanner, "仅注入纯测")
        return ScannerProbeResult("READ_VERIFIED", "非实际扫描", binding)

    async def audit_sink(event):
        events.append(event)
        if audit:
            await audit(event)

    owner = MaterialScannerOwner(
        registry, adapter=adapter, health=health or fake_health, audit_sink=audit_sink, **kwargs
    )
    return owner, adapter, events


async def test_start_publishes_only_after_health_source_recheck_and_audit_then_withdraws_first(
    definition,
):
    owner, adapter, events = make_owner()
    binding = await owner.start(definition)
    assert adapter.events[:3] == ["job-support", "port", "spawn"]
    assert events[0]["action"] == "STARTING" and events[1] == "health"
    assert events[2]["action"] == "STARTED"
    assert owner.registry.resolve(definition.profile_id) is binding
    assert binding.profile.pid == adapter.process.pid
    serialized = json.dumps([event for event in events if isinstance(event, dict)])
    assert str(definition.owned_root) not in serialized
    assert all(
        key not in serialized for key in ['"pid"', '"port"', '"executable"', '"config_file"']
    )
    assert await owner.stop() is True
    assert events[-1]["action"] == "STOPPED" and owner.registry.candidates() == []
    assert await owner.stop() is False


async def test_missing_audit_sink_never_constructs_active_owner():
    with pytest.raises(OrbitError) as error:
        MaterialScannerOwner(MaterialScannerRegistry(), audit_sink=None)
    assert error.value.code == "SCANNER_OWNER_AUDIT_UNAVAILABLE"


@pytest.mark.parametrize(
    "condition,code",
    [("supported", "SCANNER_OWNER_JOB_UNAVAILABLE"), ("available", "SCANNER_OWNER_PORT_BUSY")],
)
async def test_job_missing_or_port_occupied_never_spawns_or_adopts(definition, condition, code):
    owner, adapter, _ = make_owner()
    setattr(adapter, condition, False)
    with pytest.raises(OrbitError) as error:
        await owner.start(definition)
    assert (
        error.value.code == code and "spawn" not in adapter.events and "close" not in adapter.events
    )
    assert owner.registry.candidates() == []


async def test_audit_failure_before_spawn_cannot_start(definition):
    async def failing(event):
        raise RuntimeError("private arbitrary exception")

    owner, adapter, _ = make_owner(audit=failing)
    with pytest.raises(OrbitError) as error:
        await owner.start(definition)
    assert "private" not in str(error.value) and "spawn" not in adapter.events


async def test_success_audit_failure_after_health_closes_own_child_without_publish(definition):
    async def failing(event):
        if event["action"] == "STARTED":
            raise RuntimeError("private fixture")

    owner, adapter, _ = make_owner(audit=failing)
    with pytest.raises(OrbitError):
        await owner.start(definition)
    assert adapter.events[-1] == "close" and owner.registry.candidates() == []


@pytest.mark.parametrize("result", [True, None, ScannerProbeResult("FAILED", "纯测")])
async def test_unknown_or_boolean_health_can_never_publish(definition, result):
    async def health(*args):
        return result

    owner, adapter, _ = make_owner(health=health)
    with pytest.raises(OrbitError) as error:
        await owner.start(definition)
    assert error.value.code == "SCANNER_OWNER_HEALTH_FAILED"
    assert adapter.events[-1] == "close" and not owner.registry.candidates()


async def test_source_drift_after_health_closes_without_publishing(definition):
    calls = []

    def files(current, deadline):
        calls.append(True)
        return ("a" if len(calls) == 1 else "b") * 64

    owner, adapter, _ = make_owner(files_verifier=files)
    with pytest.raises(OrbitError) as error:
        await owner.start(definition)
    assert error.value.code == "SCANNER_OWNER_SOURCE_CHANGED" and adapter.events[-1] == "close"


async def test_exited_child_cannot_publish_or_reuse_external_registry(definition):
    owner, adapter, _ = make_owner()
    adapter.running = False
    with pytest.raises(OrbitError):
        await owner.start(definition)
    assert owner.registry.candidates() == []


async def test_second_start_does_not_create_a_second_child(definition):
    owner, adapter, _ = make_owner()
    await owner.start(definition)
    with pytest.raises(OrbitError) as error:
        await owner.start(definition)
    assert error.value.code == "SCANNER_OWNER_BUSY" and adapter.events.count("spawn") == 1
    await owner.stop()


async def test_monitor_expiry_withdraws_then_stops_owned_child(definition):
    now = [datetime.now(UTC)]
    owner, adapter, events = make_owner(clock=lambda: now[0])
    await owner.start(definition)
    now[0] += timedelta(seconds=definition.proof_ttl_seconds + 1)
    assert await owner.monitor_once() is False
    assert not owner.registry.candidates() and adapter.events[-1] == "close"
    assert events[-1]["action"] == "INVALIDATED"


async def test_monitor_source_drift_does_not_leave_ready_candidate(definition):
    owner, adapter, _ = make_owner()
    await owner.start(definition)
    definition.config_file.write_bytes(b"changed")
    assert await owner.monitor_once() is False
    assert not owner.registry.candidates() and adapter.events[-1] == "close"


async def test_cancelled_late_spawn_is_closed_and_cannot_be_published(definition):
    owner, adapter, _ = make_owner()
    entered, release = threading.Event(), threading.Event()

    def late(*args):
        entered.set()
        assert release.wait(5)
        return adapter.process

    adapter.spawn = late
    task = asyncio.create_task(owner.start(definition))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(OrbitError):
        await owner.start(definition)
    release.set()
    await asyncio.wait_for(owner._pending, 5)
    assert adapter.events[-1] == "close" and not owner.registry.candidates()


async def test_cleanup_failure_blocks_restart_and_retains_owned_handle_for_retry(definition):
    owner, adapter, _ = make_owner()
    await owner.start(definition)
    adapter.close_failure = True
    with pytest.raises(OrbitError):
        await owner.stop()
    await owner._pending
    assert owner._unclosed and not owner.registry.candidates()
    with pytest.raises(OrbitError):
        await owner.start(definition)
    adapter.close_failure = False
    await owner.stop()
    assert not owner._unclosed


@pytest.mark.parametrize("target", ["executable", "release_receipt_file", "config_file"])
def test_pinned_release_config_and_executable_bytes_are_rechecked(definition, target):
    import time

    assert len(verify_owner_files(definition, time.monotonic() + 5)) == 64
    getattr(definition, target).write_bytes(b"changed")
    with pytest.raises(OrbitError):
        verify_owner_files(definition, time.monotonic() + 5)


@pytest.mark.parametrize(
    "extra",
    [
        "Include other.conf",
        "LogFile C:/outside.log",
        "PidFile C:/outside.pid",
        "TCPAddr 0.0.0.0",
        "MaxThreads 100",
    ],
)
def test_uncontrolled_config_side_effects_cannot_be_started(definition, extra):
    import time

    content = definition.config_file.read_bytes() + b"\n" + extra.encode()
    definition.config_file.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    changed = replace(
        definition, config_sha256=digest, policy=replace(definition.policy, config_sha256=digest)
    )
    with pytest.raises(OrbitError):
        verify_owner_files(changed, time.monotonic() + 5)


async def test_startup_health_waits_for_verified_result_within_same_private_registry(monkeypatch):
    import time

    import orbit_api.material_scanner_owner as module

    calls, binding = [], object()

    class Private:
        def publish(self, scanner, label):
            calls.append("private-publish")

        async def probe(self, enabled, settings):
            calls.append("actual-probe-substitute")
            return ScannerProbeResult(
                "FAILED" if len(calls) == 2 else "READ_VERIFIED", "纯测未实际扫描", binding
            )

    monkeypatch.setattr(module, "MaterialScannerRegistry", Private)
    result = await module.actual_owner_health(
        SimpleNamespace(profile=SimpleNamespace(profile_id="fixture")), time.monotonic() + 1
    )
    assert result.binding is binding and len(calls) == 3


async def test_expired_startup_health_never_scans_or_reports_success(monkeypatch):
    import time

    import orbit_api.material_scanner_owner as module

    calls = []

    class Private:
        def publish(self, *args):
            calls.append("private-only")

        async def probe(self, *args):
            pytest.fail("过期启动窗口不得开始扫描")

    monkeypatch.setattr(module, "MaterialScannerRegistry", Private)
    with pytest.raises(OrbitError) as error:
        await module.actual_owner_health(SimpleNamespace(), time.monotonic() - 1)
    assert error.value.code == "SCANNER_OWNER_HEALTH_FAILED" and calls == ["private-only"]
