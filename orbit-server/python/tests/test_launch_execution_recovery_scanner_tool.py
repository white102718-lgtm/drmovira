"""扫描器真实工具隔离护栏；不连接DB或启动服务。"""

import asyncio
import importlib
import inspect
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import UUID

import pytest
from test_launch_execution_lease_contract import NOW, binding

from orbit_api.launch_execution_lease_store import LeaseOperation

module = importlib.import_module("tools.launch_execution_recovery_scanner_checks")
DATABASE = "orbit_py_it_" + "a" * 32


def test_service_flag_is_explicit_default_off_and_original_case_contract_unchanged():
    parameter = inspect.signature(module.run_execution_recovery_scanner_checks).parameters[
        "include_service"
    ]
    assert parameter.default is False and parameter.kind == inspect.Parameter.KEYWORD_ONLY
    assert len(module.SCANNER_CASES) == 10 and len(module.SERVICE_CASES) == 4
    assert len(set(module.SCANNER_CASES + module.SERVICE_CASES)) == 14


@pytest.mark.parametrize("flag", [None, 0, 1, "true", [], {}])
def test_service_flag_cannot_be_truthy_untrusted_value(flag):
    admin, client = Mock(), Mock()
    with pytest.raises(ValueError):
        module.run_execution_recovery_scanner_checks(
            client, admin, {}, "unused", None, DATABASE, [], include_service=flag
        )
    assert not admin.mock_calls and not client.mock_calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        None,
        "cleanup_false",
        "failed",
        "retained",
        "running",
        "wrong_scanner",
        "pending",
        "exception",
    ],
)
async def test_service_cleanup_asserts_exact_finished_task_and_scanner(bad):
    future = asyncio.get_running_loop().create_future()
    scanner = SimpleNamespace(_running=False)
    service = SimpleNamespace(
        state="STOPPED", scanner=scanner, retained_tasks=(), active_task=future
    )
    outcome = {"cleanup_complete": True}
    if bad != "pending":
        if bad == "exception":
            future.set_exception(RuntimeError("pure"))
        else:
            future.set_result(None)
    if bad == "cleanup_false":
        outcome["cleanup_complete"] = False
    elif bad == "failed":
        service.state = "FAILED"
    elif bad == "retained":
        service.retained_tasks = (future,)
    elif bad == "running":
        scanner._running = True
    elif bad == "wrong_scanner":
        service.scanner = object()
    try:
        if bad is None:
            module.assert_service_cleanup(service, outcome, [scanner])
        else:
            with pytest.raises(AssertionError):
                module.assert_service_cleanup(service, outcome, [scanner])
    finally:
        if not future.done():
            future.cancel()
        elif not future.cancelled():
            future.exception()


@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, DATABASE),
        ("192.0.2.1", 13306, DATABASE),
        ("127.0.0.1", 3306, DATABASE),
        ("127.0.0.1", "13306", DATABASE),
        ("127.0.0.1", 13306.0, DATABASE),
        ("127.0.0.1", True, DATABASE),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, DATABASE[:-1]),
        ("127.0.0.1", 13306, DATABASE + "\n"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
        ("127.0.0.1", 13306, None),
    ],
)
def test_target_guard_before_database_or_http(host, port, database):
    client = Mock()
    admin = SimpleNamespace(host=host, port=port, cursor=Mock())
    with pytest.raises(ValueError):
        module.run_execution_recovery_scanner_checks(
            client, admin, {}, "unused", None, database, []
        )
    admin.cursor.assert_not_called()
    assert not client.mock_calls


def test_actual_selected_database_must_match_before_http():
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchall.return_value = (("orbit_py_it_" + "b" * 32,),)
    client = Mock()
    admin = SimpleNamespace(
        host="127.0.0.1", port=13306, cursor=Mock(return_value=cursor), commit=Mock()
    )
    with pytest.raises(AssertionError):
        module.run_execution_recovery_scanner_checks(
            client, admin, {}, "unused", None, DATABASE, []
        )
    cursor.execute.assert_called_once_with("SELECT DATABASE()", ())
    assert not client.mock_calls


@pytest.mark.asyncio
async def test_technical_provider_is_explicit_bound_scope_and_revocation_changes_revision():
    attempt = binding()
    admin = SimpleNamespace(host="127.0.0.1", port=13306)
    provider = module.TechnicalScannerProvider(
        admin, DATABASE, attempt.tenant_id, {attempt.node_id: attempt}, {}, NOW
    )
    first = await provider.capture()
    assert first.tenants == (attempt.tenant_id,) and first.actor_id == 1
    assert first.action is LeaseOperation.RECOVER_EXPIRED and first.expires_at == NOW + timedelta(
        hours=1
    )
    assert str(UUID(first.grant_id)) == first.grant_id
    assert await provider.current(first) == first
    provider.revoked = True
    changed = await provider.current(first)
    assert changed.revision == first.revision + 1 and changed.principal_id == first.principal_id


def test_three_bucket_diagnostic_contains_only_safe_state_counters():
    expected = module.RuntimeExpectation(1, 1, 1, str(UUID(int=2)), str(UUID(int=3)))
    report = SimpleNamespace(
        pages=5,
        raw_rows=405,
        attempted=3,
        recovered=3,
        noop=0,
        stale=0,
        blocked=0,
        filtered=402,
        secret="must-not-appear",
    )
    result = module.three_bucket_diagnostic(
        expected, expected, ("UNKNOWN", 1, 3), ("UNKNOWN", 1, 2), report
    )
    assert set(result) == {"scope", "phase", "accepted", "manual", "counts"}
    assert result["accepted"] == {
        "before_runtime_revision": 1,
        "before_attempt": 1,
        "after_state": "UNKNOWN",
        "after_attempt": 1,
        "after_runtime_revision": 3,
    }
    assert "secret" not in str(result) and expected.claim_id not in str(result)


def test_three_bucket_diagnostic_rejects_uncontrolled_values():
    expected = module.RuntimeExpectation(1, 1, 1, str(UUID(int=2)), str(UUID(int=3)))
    report = SimpleNamespace(
        pages=1, raw_rows=1, attempted=1, recovered=1, noop=0, stale=0, blocked=0, filtered=0
    )
    with pytest.raises(ValueError):
        module.three_bucket_diagnostic(
            expected, expected, ("raw-exception", 1, 2), ("UNKNOWN", 1, 2), report
        )


@pytest.mark.asyncio
async def test_expired_accepted_can_be_seen_again_on_later_expiry_page(monkeypatch):
    from dataclasses import replace

    from test_launch_execution_recovery_scanner import (
        Provider,
        Sessions,
        candidate,
        fake_recovery_transaction,
    )

    import orbit_api.launch_execution_recovery_scanner as scanner_module

    value = candidate()
    model = {"state": "ACCEPTED", "revision": 1}
    generations = []

    async def page(session, tenant, bucket, position, limit):
        if bucket is scanner_module.RecoveryBucket.EXPIRED:
            keys = [i for i in range(1, 404) if position.key is None or (i,) > position.key][:limit]
            hints = []
            for key in keys:
                possible = None
                if key == 403 and model["state"] == "VERIFYING":
                    possible = replace(
                        value, expected=replace(value.expected, revision=model["revision"])
                    )
                hints.append(scanner_module.RawRecoveryHint((key,), possible, blocked=False))
            return NOW, position.cutoff or NOW, hints
        if bucket is scanner_module.RecoveryBucket.ACCEPTED and model["state"] == "ACCEPTED":
            return NOW, NOW, [scanner_module.RawRecoveryHint((1,), value)]
        return NOW, NOW, []

    async def recover(store, session, actor, attempt, expected, request):
        generations.append(expected.revision)
        model["state"] = "VERIFYING" if model["state"] == "ACCEPTED" else "UNKNOWN"
        model["revision"] += 1
        return SimpleNamespace(changed=True)

    monkeypatch.setattr(scanner_module, "_recovery_transaction", fake_recovery_transaction)
    monkeypatch.setattr(scanner_module, "_candidate_page", page)
    monkeypatch.setattr(scanner_module.ExecutionRecoveryStore, "recover_expired", recover)
    sessions = Sessions()
    result = await scanner_module.ExecutionRecoveryScanner(
        Provider(), lambda: sessions, clock=lambda: NOW
    ).scan_once(max_raw_rows=1000)
    assert model == {"state": "UNKNOWN", "revision": 3} and generations == [1, 2]
    assert result.recovered == 2


def expired_chain_rows(attempt):
    return [
        (
            (1, 2, "ACCEPTED_REQUIRES_READBACK", 1, "SEALED", 1, 2, 1, 2),
            (2, 3, "LEASE_OUTCOME_UNKNOWN", 1, "SEALED", 2, 3, 2, 3),
        ),
        (
            ("ACCEPTED", "VERIFYING", "VERIFYING", 2, 2, attempt.node_id),
            ("VERIFYING", "UNKNOWN", "UNKNOWN", 3, 3, attempt.node_id),
        ),
        (
            (
                "UNKNOWN",
                "UNKNOWN",
                1,
                1,
                attempt.fencing_token,
                attempt.claim_id,
                attempt.worker_id,
                3,
            ),
        ),
        (("UNKNOWN", 3, 3),),
    ]


def test_expired_accepted_requires_two_exact_decisions_edges_and_original_attempt():
    attempt = binding()
    before = module.RuntimeExpectation(
        1, 1, attempt.fencing_token, attempt.claim_id, attempt.worker_id
    )
    query = Mock(side_effect=expired_chain_rows(attempt))
    module.assert_expired_accepted_recovery(query, attempt.tenant_id, attempt, before)
    assert query.call_count == 4


@pytest.mark.parametrize(
    "part", ["missing_decision", "wrong_middle_state", "attempt_increased", "missing_task_revision"]
)
def test_expired_accepted_chain_rejects_omitted_or_changed_original_contract(part):
    attempt = binding()
    before = module.RuntimeExpectation(
        1, 1, attempt.fencing_token, attempt.claim_id, attempt.worker_id
    )
    rows = expired_chain_rows(attempt)
    if part == "missing_decision":
        rows[0] = rows[0][:1]
    elif part == "wrong_middle_state":
        rows[1] = (("ACCEPTED", "UNKNOWN", "UNKNOWN", 2, 2, attempt.node_id),) + rows[1][1:]
    elif part == "attempt_increased":
        rows[2] = (
            (
                "UNKNOWN",
                "UNKNOWN",
                2,
                2,
                attempt.fencing_token,
                attempt.claim_id,
                attempt.worker_id,
                3,
            ),
        )
    else:
        rows[3] = (("UNKNOWN", 2, 2),)
    with pytest.raises(AssertionError):
        module.assert_expired_accepted_recovery(
            Mock(side_effect=rows), attempt.tenant_id, attempt, before
        )


def test_owned_lock_diagnostic_never_returns_process_state_text_or_sql():
    report = module.safe_lock_wait_diagnostic(
        [(11, 12, 13, "Query", "executing", 2, "WAITING", "50")]
    )
    assert report["waits"] == [
        {
            "requesting_thread": 11,
            "blocking_thread": 12,
            "connection_id": 13,
            "command_class": "QUERY",
            "state_class": "EXECUTING",
            "process_seconds": 2,
            "lock_status": "WAITING",
            "server_lock_wait_timeout": 50,
        }
    ]
    safe = module.safe_lock_wait_diagnostic(
        [(11, 12, None, "uncontrolled", "sensitive SQL text here", None, "WAITING", None)]
    )
    assert "sensitive" not in str(safe) and "uncontrolled" not in str(safe)
    assert safe["waits"][0]["command_class"] == "OTHER"
    assert safe["waits"][0]["state_class"] == "GONE"


@pytest.mark.parametrize(
    "row",
    [
        (True, 12, 13, "Query", "executing", 2, "WAITING", "50"),
        (11, 12, 13, "Query", "executing", 2, "BAD", "50"),
        (11, 12, 13, "Query", "executing", 2, "WAITING", "secret"),
    ],
)
def test_owned_lock_diagnostic_rejects_non_whitelisted_fields(row):
    with pytest.raises(ValueError):
        module.safe_lock_wait_diagnostic([row])
