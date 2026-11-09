"""结果专项工具的隔离与独立登记护栏纯测；不运行MySQL。"""

import importlib
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from orbit_api.errors import OrbitError

TOOLS = str(Path(__file__).resolve().parents[2] / "tools")
sys.path.insert(0, TOOLS)
try:
    tool = importlib.import_module("metrics_query_result_checks")
finally:
    sys.path.remove(TOOLS)


def test_exact_eight_business_cases_and_query_window():
    assert len(tool.METRIC_QUERY_RESULT_CASES) == len(set(tool.METRIC_QUERY_RESULT_CASES)) == 8
    body = tool.query(str(uuid4()))
    assert (body["date_from"], body["date_to"]) == ("2026-01-01", "2026-01-02")


@pytest.mark.parametrize(
    "value", [None, "", "it_metric_expect_bad", "x;DROP TABLE x", "it_metric_expect_" + "A" * 16]
)
def test_random_registry_name_is_strict(value):
    with pytest.raises(ValueError):
        tool.RegisteredSqlExpected(value)


def test_target_guard_runs_before_fixture_and_seed(monkeypatch):
    touched = []
    monkeypatch.setattr(tool, "MetricFactSqlFixture", lambda *args: touched.append("fixture"))
    monkeypatch.setattr(
        tool, "seed_metric_profile_browser_fixture", lambda *args: touched.append("seed")
    )
    with pytest.raises(ValueError):
        tool.run_metrics_query_result_checks(
            None, SimpleNamespace(host="127.0.0.1", port=3306), {}, "", None, "invalid", []
        )
    assert touched == []


class Session:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    async def execute(self, statement, values):
        self.calls.append((str(statement), values))
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: self.rows))


def registered():
    tenant, profile, publication, subject = (str(uuid4()) for _ in range(4))
    source = tool.QuerySourceIdentity(
        tenant, publication, 120, profile, "observed-v001", "a" * 64, "ISOLATED_TEST"
    )
    body = tool.query(profile)
    empty_hash = tool.stream_hash(())
    manifest = tool.ExpectedUnitManifest(
        source,
        1,
        subject,
        1,
        "b" * 64,
        tool.metric_query_hash(body),
        "ACCOUNT",
        date(2026, 1, 1),
        date(2026, 1, 2),
        None,
        None,
        None,
        0,
        empty_hash,
        0,
        empty_hash,
    )
    saved = {
        "kind": "SQL_ONLY_NOT_PLATFORM",
        "manifest": tool.encode_manifest(manifest),
        "units": [],
        "members": [],
    }
    row = {"body_json": saved, "body_hash": tool.digest(saved), "revoked": 0}
    scope = SimpleNamespace(current=SimpleNamespace(tenant_id=tenant, actor_id=1))
    return manifest, body, row, scope


@pytest.mark.asyncio
async def test_provider_returns_registered_manifest_and_binds_exact_query_scope():
    manifest, body, row, scope = registered()
    provider = tool.RegisteredSqlExpected("it_metric_expect_" + "a" * 16)
    session = Session([row])
    assert await provider.prepare_manifest(session, scope, body, manifest.source) == manifest
    assert session.calls[0][1] == {
        "tenant": scope.current.tenant_id,
        "actor": 1,
        "hash": tool.metric_query_hash(body),
        "source": manifest.source.publication_id,
    }
    assert "FOR SHARE" in session.calls[0][0]
    assert [
        batch async for batch in provider.iter_unit_batches(session, scope, body, manifest)
    ] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage", ["missing", "duplicate", "revoked", "hash", "kind", "extra", "old_member"]
)
async def test_provider_never_trusts_bad_or_unregistered_complete_body(damage):
    manifest, body, row, scope = registered()
    rows = [row]
    if damage == "missing":
        rows = []
    elif damage == "duplicate":
        rows = [row, row]
    elif damage == "revoked":
        row["revoked"] = 1
    elif damage == "hash":
        row["body_hash"] = "0" * 64
    else:
        if damage == "kind":
            row["body_json"]["kind"] = "TRUSTED"
        elif damage == "extra":
            row["body_json"]["unknown"] = True
        else:
            # v1九字段成员缺当前真实name_observed_at，不得补占位值。
            row["body_json"]["members"] = [["legacy"] * 9]
        row["body_hash"] = tool.digest(row["body_json"])
    provider = tool.RegisteredSqlExpected("it_metric_expect_" + "b" * 16)
    with pytest.raises(OrbitError) as error:
        await provider.prepare_manifest(Session(rows), scope, body, manifest.source)
    assert error.value.status == 503


@pytest.mark.asyncio
async def test_provider_revalidates_registered_source_instead_of_echoing_input():
    from dataclasses import replace

    manifest, body, row, scope = registered()
    provider = tool.RegisteredSqlExpected("it_metric_expect_" + "c" * 16)
    session = Session([row])
    with pytest.raises(OrbitError):
        await provider.prepare_manifest(
            session, scope, body, replace(manifest.source, generation=121)
        )
    with pytest.raises(OrbitError):
        await provider.revalidate_manifest(session, scope, body, replace(manifest, unit_count=1))


@pytest.mark.parametrize(
    "row",
    [None, ("Sleep", None, "idle", "1"), ("Query", "private SQL text", "secret query text", "bad")],
)
def test_cancel_diagnostic_only_fixed_states_counts_and_namespace_event(row):
    value = tool.safe_cancel_diagnostic(
        row,
        transactions=1,
        waits=0,
        connection=SimpleNamespace(invalidated=True, closed=True),
        cleanup_state="FAILED",
    )
    assert value["remaining_transactions"] == 1 and value["remaining_lock_waits"] == 0
    assert value["client_invalidated"] and value["client_closed"]
    encoded = str(value)
    assert "private SQL text" not in encoded and "secret query text" not in encoded
    assert value["state"] in {"NONE", "OTHER"}


def test_cancel_diagnostic_saves_atomic_structured_report_before_assertion(monkeypatch, tmp_path):
    import json

    target = tmp_path / "safe-result.json"
    monkeypatch.setattr(tool, "METRIC_RESULT_CANCEL_REPORT", target)
    value = tool.safe_cancel_diagnostic(
        None,
        transactions=0,
        waits=0,
        connection=SimpleNamespace(invalidated=True, closed=True),
        cleanup_state="FAILED",
    )
    tool.save_cancel_diagnostic(value)
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert set(saved) == {"version", "recorded_at", "diagnostic"} and saved["version"] == 1
    assert saved["diagnostic"] == value
    assert not target.with_suffix(".tmp").exists()


@pytest.mark.asyncio
async def test_trx_sampling_idle_exceeds_mysql_last_read_protection_and_does_not_change_deadline():
    # 复现last_read每次读均更新；采样空窗须真跨100ms而不是累加20ms忙轮询。
    class Cache:
        now = 0.0
        last_read = 0.0
        cached_transactions = 1
        server_transactions = 0

        def read(self):
            if self.now - self.last_read > 0.1:
                self.cached_transactions = self.server_transactions
            self.last_read = self.now
            return self.cached_transactions

        async def sleep(self, seconds):
            self.now += seconds

    cache = Cache()
    for _ in range(100):
        await cache.sleep(0.02)
        assert cache.read() == 1
    original_deadline = cache.now + 2
    await tool.fresh_trx_observer_window(sleep=cache.sleep)
    assert cache.read() == 0
    assert tool.TRX_OBSERVER_IDLE_SECONDS > 0.1
    assert cache.now < original_deadline
