"""扫描状态事务控制单测；SQL/实际引擎/并发租约由真实专项另外验收。"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from orbit_api import material_worker as module
from orbit_api.errors import OrbitError
from orbit_api.material_antivirus import ScanReceipt
from orbit_api.material_antivirus_runtime import RuntimeScanResult

CLAIM = {
    "tenant_id": "tenant",
    "asset_id": "asset",
    "claim_id": "claim",
    "revision": 3,
    "sha256": "a" * 64,
    "byte_size": 100,
    "actor_id": 1,
}


def receipt(**changes):
    now = datetime.now(UTC)
    return replace(
        ScanReceipt(
            "CLEAN",
            "a" * 64,
            100,
            now,
            now,
            "1.5.4",
            28177,
            now - timedelta(hours=1),
            "b" * 64,
            None,
        ),
        **changes,
    )


class Session:
    def __init__(self):
        self.sql = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return self

    async def execute(self, statement, params):
        self.sql.append((str(statement), params))
        return SimpleNamespace(rowcount=1)


@pytest.fixture
def setup(monkeypatch):
    session = Session()
    options = {
        "authorized": True,
        "job": {"state": "RUNNING", "claim_id": "claim"},
        "asset": {"state": "SCANNING", "revision": 3, "sha256": "a" * 64, "byte_size": 100},
    }

    async def one(session, sql, params):
        return options["job"] if "orbit_material_job" in sql else options["asset"]

    async def authorized(*args):
        return options["authorized"]

    async def clock(*args):
        pass

    monkeypatch.setattr(module, "one", one)
    monkeypatch.setattr(module, "validate_job_actor", authorized)
    monkeypatch.setattr(module.MaterialWorker, "lock_clock", clock)
    return module.MaterialWorker(lambda: session, None), session, options


@pytest.mark.parametrize(
    "value,expected,code",
    [
        (receipt(), "PROCESSING_FAILED", "ANTIVIRUS_RUNTIME_UNVERIFIED"),
        (
            receipt(result="INFECTED", error_code="ANTIVIRUS_INFECTED"),
            "QUARANTINED",
            "ANTIVIRUS_INFECTED",
        ),
        (
            receipt(result="UNVERIFIED", error_code="ANTIVIRUS_TIMEOUT"),
            "PROCESSING_FAILED",
            "ANTIVIRUS_TIMEOUT",
        ),
        (receipt(sha256="b" * 64), "PROCESSING_FAILED", "ANTIVIRUS_EVIDENCE_INVALID"),
        (receipt(byte_size=101), "PROCESSING_FAILED", "ANTIVIRUS_EVIDENCE_INVALID"),
        (receipt(engine_version=None), "PROCESSING_FAILED", "ANTIVIRUS_EVIDENCE_INVALID"),
        (receipt(database_version=None), "PROCESSING_FAILED", "ANTIVIRUS_EVIDENCE_INVALID"),
        (receipt(policy_sha256=None), "PROCESSING_FAILED", "ANTIVIRUS_EVIDENCE_INVALID"),
    ],
)
def test_scanning_only_advances_after_complete_clean_evidence(setup, value, expected, code):
    worker, session, _ = setup
    next_claim, state = asyncio.run(worker.record_scan(CLAIM, value))
    assert state == expected
    assert (next_claim is not None) == (expected == "PROCESSING")
    if next_claim:
        assert next_claim["revision"] == 4
    persisted = next(
        params for sql, params in session.sql if "INSERT INTO orbit_material_scan_receipt" in sql
    )
    assert persisted["scan_result"] == ("UNVERIFIED" if value.result == "CLEAN" else value.result)
    assert persisted["error"] == code
    assert not any("COMMIT" in sql for sql, _ in session.sql)


@pytest.mark.parametrize("failure", ["job", "claim", "state", "revision", "hash", "size"])
def test_old_scan_result_cannot_overwrite_new_claim_or_asset(setup, failure):
    worker, session, options = setup
    if failure == "job":
        options["job"] = None
    elif failure == "claim":
        options["job"]["claim_id"] = "replacement"
    else:
        key, value = {
            "state": ("state", "ARCHIVED"),
            "revision": ("revision", 4),
            "hash": ("sha256", "b" * 64),
            "size": ("byte_size", 101),
        }[failure]
        options["asset"][key] = value
    assert asyncio.run(worker.record_scan(CLAIM, receipt())) == (None, "STALE")
    assert session.sql == []


def test_authorization_revocation_preserves_receipt_but_never_ready(setup):
    worker, session, options = setup
    options["authorized"] = False
    assert asyncio.run(worker.record_scan(CLAIM, receipt())) == (None, "PROCESSING_FAILED")
    assert any("orbit_material_scan_receipt" in sql for sql, _ in session.sql)
    assert any("AUTHORIZATION_CHANGED" in sql for sql, _ in session.sql)
    assert not any(params.get("next_state") == "PROCESSING" for _, params in session.sql)


def test_runtime_wrapper_without_proof_cannot_upgrade_actual_engine_clean(setup):
    worker, session, _ = setup
    value = RuntimeScanResult(receipt(), None)
    assert asyncio.run(worker.record_scan(CLAIM, value)) == (None, "PROCESSING_FAILED")
    persisted = next(
        params for sql, params in session.sql if "INSERT INTO orbit_material_scan_receipt" in sql
    )
    assert persisted["scan_result"] == "UNVERIFIED"
    assert persisted["error"] == "ANTIVIRUS_RUNTIME_UNVERIFIED"
    assert not any("orbit_material_scan_runtime_proof" in sql for sql, _ in session.sql)


def test_finish_cannot_publish_existing_media_without_current_runtime_proof(setup, monkeypatch):
    worker, session, _ = setup

    async def unverified(*args):
        return False

    monkeypatch.setattr(module, "processing_scan_verified", unverified)
    media = SimpleNamespace(width=24, height=24, duration=None)
    assert asyncio.run(worker.finish(CLAIM, "READY", None, media)) == (True, "PROCESSING_FAILED")
    changed = next(params for sql, params in session.sql if "width_px=:width" in sql)
    assert changed["state"] == "PROCESSING_FAILED" and changed["preview"] == 0
    assert changed["width"] is None and changed["error"] == "ANTIVIRUS_RUNTIME_UNVERIFIED"


def test_missing_current_profile_cannot_pass_runtime_result_to_processor(monkeypatch):
    claims = [dict(CLAIM), None]
    captured = []

    async def claim():
        return claims.pop(0)

    async def record(current, value, **kwargs):
        captured.append(value)
        return None, "PROCESSING_FAILED"

    worker = module.MaterialWorker(
        None,
        None,
        processor=lambda *a: pytest.fail("不得媒体处理"),
        scanner=SimpleNamespace(scan=lambda *a: RuntimeScanResult(receipt(), None)),
    )
    monkeypatch.setattr(worker, "claim", claim)
    monkeypatch.setattr(worker, "record_scan", record)
    # 扫描器参数属于真实claim的受控对象键；本测试仅验证provider缺失的控制流。
    claims[0]["object_upload_id"] = "object"
    assert asyncio.run(worker.run_once(1)) == [{"asset_id": "asset", "state": "PROCESSING_FAILED"}]
    assert (
        captured[0].result == "UNVERIFIED"
        and captured[0].error_code == "ANTIVIRUS_RUNTIME_UNVERIFIED"
    )


def test_profile_provider_exception_does_not_scan_or_process(monkeypatch):
    async def claim():
        return {**CLAIM, "object_upload_id": "object"}

    def unavailable(current):
        raise OrbitError(503, "ANTIVIRUS_RUNTIME_UNVERIFIED", "测试来源未验证")

    captured = []

    async def record(current, value, **kwargs):
        captured.append(value)
        return None, "PROCESSING_FAILED"

    worker = module.MaterialWorker(
        None,
        None,
        processor=lambda *a: pytest.fail("不得媒体处理"),
        scanner=SimpleNamespace(scan=lambda *a: pytest.fail("来源无效不得扫描")),
        runtime_profile_provider=unavailable,
    )
    monkeypatch.setattr(worker, "claim", claim)
    monkeypatch.setattr(worker, "record_scan", record)
    assert asyncio.run(worker.run_once(1))[0]["state"] == "PROCESSING_FAILED"
    assert captured[0].result == "UNVERIFIED"
