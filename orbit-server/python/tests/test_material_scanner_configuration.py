"""正式配置消费者纯测；不冒充真实SQL、HTTP或实际引擎验收。"""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_material_antivirus_runtime import configured as configured

from orbit_api.configuration import parse_write
from orbit_api.errors import OrbitError
from orbit_api.material_antivirus_runtime import ProcessBoundMaterialScanner
from orbit_api.material_scanner_registry import MaterialScannerRegistry
from orbit_api.material_scanner_selection import (
    ConfiguredMaterialWorker,
    select_scanner,
    verify_selection,
)


def parse(profile="trusted", enabled=True, **extra):
    return parse_write(
        json.dumps(
            {
                "section": "MATERIAL_SCANNER",
                "name": "素材安全",
                "enabled": enabled,
                "settings": {"profileId": profile, **extra},
                "secrets": {},
                "reason": "配置可信候选",
            }
        ).encode()
    )


@pytest.mark.parametrize("value", ["../trusted", "https://scanner", "a" * 41, "UPPER", "x y", ""])
def test_profile_syntax_cannot_be_path_address_or_arbitrary_input(value):
    with pytest.raises(OrbitError):
        parse(value)


def test_disabled_can_retain_empty_but_no_transport_fields():
    assert parse("", False).settings == {"profileId": ""}
    with pytest.raises(OrbitError) as error:
        parse(port=19310)
    assert error.value.code == "UNKNOWN_FIELD"


@pytest.fixture
def registry(configured):
    _, _, provider = configured
    registry = MaterialScannerRegistry()
    scanner = ProcessBoundMaterialScanner("trusted", values_provider=provider)
    binding = registry.publish(scanner, "本地安全扫描")
    return registry, binding


def test_registry_public_candidates_exclude_infrastructure_and_generation(registry):
    current, binding = registry
    assert current.candidates() == [
        {"id": "trusted", "label": "本地安全扫描", "availability": "READY"}
    ]
    assert current.resolve("trusted") is binding
    current.verify(binding)
    replacement = current.publish(binding.scanner, "更新实例")
    assert replacement.generation != binding.generation
    with pytest.raises(OrbitError) as error:
        current.verify(binding)
    assert error.value.code == "SCANNER_PROFILE_CHANGED"


def test_registry_label_normalizes_nfc_and_counts_eighty_unicode_codepoints(registry):
    current, binding = registry
    assert current.publish(binding.scanner, " Cafe\u0301 ").label == "Café"
    assert current.publish(binding.scanner, "😀" * 80).label == "😀" * 80
    with pytest.raises(ValueError):
        current.publish(binding.scanner, "😀" * 81)


@pytest.mark.parametrize(
    "label",
    [
        "",
        "   ",
        "x\n",
        "x\t",
        "x\x7f",
        "x\u0085",
        "x\u202e",
        "x\u200b",
        "x\ud800",
        "x\u2028",
        "x\u2029",
        "C:/private",
        "C:\\private",
    ],
)
def test_registry_rejects_control_format_surrogates_and_infrastructure_paths(registry, label):
    current, binding = registry
    with pytest.raises(ValueError):
        current.publish(binding.scanner, label)


def test_changed_trusted_source_rejected_without_registry_republish(registry, configured):
    from test_material_antivirus_runtime import update

    current, binding = registry
    configured[0]["revision"] += 1
    update(configured)
    with pytest.raises(OrbitError):
        current.verify(binding)


def test_transaction_generation_check_does_not_read_private_provider(registry, monkeypatch):
    current, binding = registry

    def forbidden():
        raise AssertionError("数据库锁内不得读取私有文件或执行OS检查")

    monkeypatch.setattr(binding.scanner, "values_provider", forbidden)
    current.verify(binding, source=False)
    with pytest.raises(OrbitError):
        current.verify(binding)


async def test_empty_and_disabled_probe_cannot_report_verified():
    registry = MaterialScannerRegistry()
    assert registry.candidates() == []
    assert (await registry.probe(True, {"profileId": "trusted"})).status == "BLOCKED"
    assert (await registry.probe(False, {"profileId": "trusted"})).status == "BLOCKED"


async def test_actual_probe_never_accepts_raw_clean_or_missing_runtime_proof(registry, monkeypatch):
    from orbit_api.material_antivirus_runtime import RuntimeScanResult

    current, binding = registry
    monkeypatch.setattr(binding.scanner, "scan", lambda *args: "CLEAN")
    assert (await current.probe(True, {"profileId": "trusted"})).status == "FAILED"
    monkeypatch.setattr(binding.scanner, "scan", lambda *args: RuntimeScanResult(None, None))
    assert (await current.probe(True, {"profileId": "trusted"})).status == "FAILED"


async def test_probe_busy_refuses_another_scan_without_unbounded_queue(registry):
    current, _ = registry
    assert current._probe_slot.acquire(blocking=False)
    try:
        with pytest.raises(OrbitError) as error:
            await current.probe(True, {"profileId": "trusted"})
        assert error.value.code == "SCANNER_PROBE_BUSY"
    finally:
        current._probe_slot.release()


async def test_probe_request_cancellation_retains_slot_until_scanner_thread_exits(
    registry, monkeypatch
):
    import asyncio
    import threading

    current, binding = registry
    started, release = threading.Event(), threading.Event()

    def scan(*args):
        started.set()
        assert release.wait(5)
        return None

    monkeypatch.setattr(binding.scanner, "scan", scan)
    task = asyncio.create_task(current.probe(True, {"profileId": "trusted"}))
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not current._probe_slot.acquire(blocking=False)
    release.set()
    assert await asyncio.to_thread(current._probe_slot.acquire, True, 5)
    current._probe_slot.release()


class Session:
    def __init__(self, rows):
        self.rows, self.statements = rows, []

    async def execute(self, query, values):
        self.statements.append((str(query), values))
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: self.rows))


@pytest.mark.parametrize("rows", [[], [{"enabled": False}], [{"enabled": True}, {"enabled": True}]])
async def test_missing_disabled_or_ambiguous_tenant_selection_fails_closed(rows):
    with pytest.raises(OrbitError):
        await select_scanner(Session(rows), "tenant", MaterialScannerRegistry())


async def test_selected_source_binds_full_configuration_revision_and_tenant(registry):
    current, binding = registry
    row = {
        "id": "config",
        "revision": 7,
        "enabled": True,
        "settings_json": '{"profileId":"trusted"}',
    }
    session = Session([row])
    selection = await select_scanner(session, "tenant", current)
    assert selection.configuration_revision == 7
    await verify_selection(session, selection, {"tenant_id": "tenant"}, binding.profile)
    assert "FOR SHARE" in session.statements[-1][0]
    assert session.statements[-1][1] == {"tenant": "tenant"}
    for changed in [
        replace(selection, tenant_id="other"),
        replace(selection, configuration_revision=6),
    ]:
        with pytest.raises(OrbitError):
            await verify_selection(session, changed, {"tenant_id": "tenant"}, binding.profile)


async def test_record_and_finish_source_guards_never_call_provider_under_sql_lock(
    registry, monkeypatch
):
    current, binding = registry
    row = {
        "id": "config",
        "revision": 7,
        "enabled": True,
        "settings_json": '{"profileId":"trusted"}',
    }
    session = Session([row])
    selection = await select_scanner(session, "tenant", current)

    def forbidden():
        raise AssertionError("收据/完成事务锁内不允许调用provider")

    monkeypatch.setattr(binding.scanner, "values_provider", forbidden)
    await verify_selection(session, selection, {"tenant_id": "tenant"}, binding.profile)
    worker = ConfiguredMaterialWorker(None, None, registry=current)
    worker._selection = selection
    assert await worker.runtime_source_current(session, {"tenant_id": "tenant"})


async def test_configuration_probe_finish_rechecks_generation_without_provider_io(
    registry, monkeypatch
):
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from orbit_api import configuration_store
    from orbit_api.material_scanner_registry import ScannerProbeResult

    current, binding = registry
    now = datetime.now(UTC).replace(tzinfo=None)
    context = SimpleNamespace(actor_id=1, tenant_id=str(uuid4()))
    monkeypatch.setattr(
        configuration_store, "require_configuration_access", AsyncMock(return_value=context)
    )
    store = configuration_store.ConfigurationStore(None, current)
    before = {
        "id": str(uuid4()),
        "tenant_id": context.tenant_id,
        "section": "MATERIAL_SCANNER",
        "name": "扫描",
        "enabled": True,
        "revision": 3,
        "settings_json": {"profileId": "trusted"},
        "secrets_json": {},
        "verification_status": "UNTESTED",
        "verified_at": None,
        "updated_at": now,
    }
    after = {**before, "revision": 4, "verification_status": "READ_VERIFIED", "verified_at": now}
    monkeypatch.setattr(store, "_row", AsyncMock(side_effect=[before, after]))
    monkeypatch.setattr(store, "_append_event", AsyncMock())

    def forbidden():
        raise AssertionError("finish_probe事务内不能读取provider")

    monkeypatch.setattr(binding.scanner, "values_provider", forbidden)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: now))
    )
    response = await store.finish_probe(
        session,
        context,
        before["id"],
        3,
        ScannerProbeResult("READ_VERIFIED", "实际安全PNG通过", binding),
        "复验",
        str(uuid4()),
    )
    assert (
        response["result"]["status"] == "READ_VERIFIED"
        and response["configuration"]["revision"] == 4
    )


async def test_formal_worker_cannot_accept_fixture_scanner_or_missing_source():
    with pytest.raises(ValueError):
        ConfiguredMaterialWorker(None, None, scanner=object())
    worker = ConfiguredMaterialWorker(None, None)
    with pytest.raises(OrbitError):
        worker.runtime_selection({"tenant_id": "tenant"})


async def test_formal_worker_refuses_config_change_during_scan(registry):
    current, binding = registry
    worker = ConfiguredMaterialWorker(None, None, registry=current)
    row = {
        "id": "config",
        "revision": 7,
        "enabled": True,
        "settings_json": '{"profileId":"trusted"}',
    }
    session = Session([row])
    selected = await select_scanner(session, "tenant", current)
    worker._selection = selected
    session.rows[0] = {**row, "revision": 8}
    assert not await worker.runtime_source_current(session, {"tenant_id": "tenant"})
    assert worker.scanner is not binding.scanner
