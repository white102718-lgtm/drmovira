"""046纯协议边界；不执行SQL、不证明正式写授权或真实平台结果。"""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from orbit_api.launch_execution_lease_contract import (
    MAX_ATTEMPT,
    MAX_REVISION,
    AttemptBinding,
    AttemptFact,
    EvidenceSource,
    FactKind,
    RuntimeSnapshot,
    SendPhase,
    aggregate_task_state,
    recover_expired,
)
from orbit_api.task_contract import NODE_STATES, TASK_STATES

NOW = datetime(2026, 11, 9, 1, 0, tzinfo=UTC)


def uid(number):
    return str(UUID(int=number))


def binding(**kwargs):
    values = dict(
        tenant_id=uid(1),
        task_id=uid(2),
        node_id=uid(3),
        preparation_id=uid(4),
        claim_id=uid(5),
        worker_id=uid(6),
        attempt_no=1,
        fencing_token=1,
        command_hash="a" * 64,
        manifest_hash="b" * 64,
        source_hash="c" * 64,
        authority_hash="d" * 64,
        authorization_hash="e" * 64,
        execution_mode="META_API",
        actor_id=1,
        subject_id=uid(7),
        owner_user_id=uid(8),
        owner_team_id=uid(9),
        auth_version=1,
    )
    return AttemptBinding(**(values | kwargs))


def snapshot(**kwargs):
    return RuntimeSnapshot(
        **(
            dict(
                binding=binding(),
                revision=1,
                state="RUNNING",
                lease_expires_at=NOW,
            )
            | kwargs
        )
    )


def fact(kind=FactKind.PROVED_NOT_SENT, **kwargs):
    phase, source = {
        FactKind.WRITE_INTENT: (SendPhase.BEFORE_DISPATCH, EvidenceSource.LOCAL_INTENT),
        FactKind.PROVED_NOT_SENT: (
            SendPhase.BEFORE_DISPATCH,
            EvidenceSource.TRANSPORT_PROVEN_NO_SEND,
        ),
        FactKind.ACCEPTED: (SendPhase.ACKNOWLEDGED, EvidenceSource.PLATFORM_ACK),
        FactKind.READBACK_SUCCEEDED: (SendPhase.READBACK, EvidenceSource.PLATFORM_READBACK),
        FactKind.READBACK_REJECTED: (SendPhase.READBACK, EvidenceSource.PLATFORM_READBACK),
        FactKind.READBACK_INCONCLUSIVE: (SendPhase.READBACK, EvidenceSource.PLATFORM_READBACK),
    }[kind]
    return AttemptFact(
        **(
            dict(
                binding=binding(),
                event_id=uid(100 + list(FactKind).index(kind)),
                kind=kind,
                phase=phase,
                source=source,
                evidence_sha256="f" * 64,
                occurred_at=NOW,
                external_id="123" if kind == FactKind.READBACK_SUCCEEDED else None,
            )
            | kwargs
        )
    )


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, "1", MAX_ATTEMPT + 1])
def test_attempt_counter_exact_unsigned_integer(value):
    with pytest.raises(ValueError):
        binding(attempt_no=value)


@pytest.mark.parametrize("value", [True, 0, -1, 1.0, MAX_REVISION + 1])
def test_fencing_counter_bounded(value):
    with pytest.raises(ValueError):
        binding(fencing_token=value)


@pytest.mark.parametrize("value", ["A" * 64, "a" * 63, "a" * 64 + "\n", None, 1])
def test_digest_strict_and_no_newline(value):
    with pytest.raises(ValueError):
        binding(command_hash=value)


@pytest.mark.parametrize("field", ["claim_id", "worker_id", "task_id", "node_id", "tenant_id"])
def test_binding_requires_canonical_uuid(field):
    with pytest.raises(ValueError):
        binding(**{field: "not-a-uuid"})


def test_frozen_binding_and_redacted_repr():
    item = binding(attempt_no=MAX_ATTEMPT, fencing_token=MAX_REVISION)
    with pytest.raises(FrozenInstanceError):
        item.attempt_no = 2
    assert item.command_hash not in repr(item)
    assert item.claim_id not in repr(item)


@pytest.mark.parametrize("mode", [None, "TRUSTED", "M2", "meta_api", "AUTO"])
def test_observation_or_label_cannot_supply_execution_channel(mode):
    with pytest.raises(ValueError):
        binding(execution_mode=mode)


@pytest.mark.parametrize("kind", list(FactKind))
def test_private_fact_enum_is_not_public_node_state(kind):
    item = fact(kind)
    assert item.kind is kind
    if kind not in {FactKind.ACCEPTED}:
        assert kind.value not in NODE_STATES


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "PROVED_NOT_SENT"},
        {"phase": SendPhase.DISPATCH_STARTED},
        {"source": EvidenceSource.LOCAL_INTENT},
        {"source": "TRANSPORT_PROVEN_NO_SEND"},
        {"occurred_at": NOW.replace(tzinfo=None)},
        {"occurred_at": NOW.astimezone(timezone(timedelta(hours=8)))},
        {"external_id": "123\n"},
        {"external_id": "x123"},
        {"external_id": "1" * 65},
    ],
)
def test_not_sent_requires_typed_exact_before_dispatch_evidence(overrides):
    # replace避免fixture根据kind重选来源，真实验证DTO本身。
    with pytest.raises(ValueError):
        replace(fact(), **overrides)


def test_verified_readback_requires_unique_external_id():
    with pytest.raises(ValueError):
        fact(FactKind.READBACK_SUCCEEDED, external_id=None)


def test_expired_without_intent_is_unknown_not_safe_retry():
    result = recover_expired(snapshot(), (), now=NOW, facts_complete=True)
    assert result.state_path == ("RUNNING", "UNKNOWN")
    assert result.retryable is False
    assert result.next_reconcile_at == NOW + timedelta(minutes=5)


def test_positive_not_sent_requires_complete_attempt_evidence():
    safe = recover_expired(snapshot(), (fact(),), now=NOW, facts_complete=True)
    assert safe.state_path == ("RUNNING", "FAILED")
    assert safe.retryable is True
    assert safe.code == "PROVED_NOT_SENT"
    incomplete = recover_expired(snapshot(), (fact(),), now=NOW)
    assert incomplete.state_path[-1] == "UNKNOWN"
    assert incomplete.retryable is False


def test_intent_and_conflicting_not_sent_remain_unknown():
    result = recover_expired(
        snapshot(),
        (fact(), fact(FactKind.WRITE_INTENT)),
        now=NOW,
        facts_complete=True,
    )
    assert result.state_path == ("RUNNING", "UNKNOWN")
    assert result.retryable is False


@pytest.mark.parametrize(
    "kind",
    [
        FactKind.READBACK_SUCCEEDED,
        FactKind.READBACK_REJECTED,
        FactKind.READBACK_INCONCLUSIVE,
    ],
)
@pytest.mark.parametrize("acknowledged", [False, True])
def test_current_readback_conflicts_with_not_sent_even_without_write_intent(kind, acknowledged):
    evidence = (fact(), fact(kind))
    if acknowledged:
        evidence += (fact(FactKind.ACCEPTED),)
    result = recover_expired(snapshot(), evidence, now=NOW, facts_complete=True)
    assert result.state_path == ("RUNNING", "UNKNOWN")
    assert result.code == "SEND_EVIDENCE_CONFLICT"
    assert not result.retryable
    assert result.next_reconcile_at == NOW + timedelta(minutes=5)


@pytest.mark.parametrize(
    "kind",
    [
        FactKind.READBACK_SUCCEEDED,
        FactKind.READBACK_REJECTED,
        FactKind.READBACK_INCONCLUSIVE,
    ],
)
def test_old_fence_readback_cannot_drive_or_contaminate_current_decision(kind):
    current = snapshot(binding=binding(fencing_token=2, attempt_no=2, claim_id=uid(20)))
    old = fact(kind)
    # 当前精确正向证明仍按当前事实判断；旧读回不构成当前冲突。
    result = recover_expired(
        current, (fact(binding=current.binding), old), now=NOW, facts_complete=True
    )
    assert result.state_path == ("RUNNING", "FAILED")
    assert result.retryable
    # 只有旧正向证明、当前读回时，旧证明也不能给当前提供安全重试资格。
    old_not_sent = fact()
    result = recover_expired(
        current,
        (old_not_sent, fact(kind, binding=current.binding)),
        now=NOW,
        facts_complete=True,
    )
    assert result.state_path == ("RUNNING", "UNKNOWN")
    assert not result.retryable


@pytest.mark.parametrize(
    "changes",
    [
        {"fencing_token": 2},
        {"attempt_no": 2},
        {"claim_id": uid(90)},
        {"worker_id": uid(91)},
        {"command_hash": "1" * 64},
        {"manifest_hash": "1" * 64},
        {"source_hash": "1" * 64},
        {"authority_hash": "1" * 64},
        {"authorization_hash": "1" * 64},
        {"execution_mode": "ADSPOWER_UI"},
        {"tenant_id": uid(92)},
        {"node_id": uid(93)},
        {"actor_id": 2},
        {"subject_id": uid(94)},
        {"owner_user_id": uid(95)},
        {"owner_team_id": uid(96)},
        {"auth_version": 2},
    ],
)
def test_late_or_different_facts_do_not_advance_current_attempt(changes):
    old = fact(FactKind.ACCEPTED, binding=binding(**changes))
    assert recover_expired(snapshot(), (old,), now=NOW).state_path[-1] == "UNKNOWN"
    old_no_send = fact(binding=binding(**changes))
    assert (
        recover_expired(snapshot(), (old_no_send,), now=NOW, facts_complete=True).state_path[-1]
        == "UNKNOWN"
    )


def test_exact_ack_requires_readback_not_success():
    result = recover_expired(snapshot(), (fact(FactKind.ACCEPTED),), now=NOW)
    assert result.state_path == ("RUNNING", "ACCEPTED", "VERIFYING")
    assert not result.retryable
    assert recover_expired(snapshot(state="ACCEPTED"), (), now=NOW).state_path == (
        "ACCEPTED",
        "VERIFYING",
    )


def test_valid_lease_never_recovers_early_and_expiry_is_inclusive():
    result = recover_expired(snapshot(), (), now=NOW - timedelta(microseconds=1))
    assert result.state_path == ("RUNNING",)
    assert result.code == "LEASE_STILL_VALID"
    assert recover_expired(snapshot(), (), now=NOW).state_path[-1] == "UNKNOWN"


def test_expired_verification_cannot_infer_failure_or_success_from_no_send():
    for item in (fact(), fact(FactKind.READBACK_SUCCEEDED)):
        result = recover_expired(snapshot(state="VERIFYING"), (item,), now=NOW, facts_complete=True)
        assert result.state_path == ("VERIFYING", "UNKNOWN")


@pytest.mark.parametrize("seconds,due", [(299, False), (300, True), (301, True)])
def test_unknown_five_minute_read_only_watermark(seconds, due):
    item = snapshot(state="UNKNOWN", unknown_since=NOW)
    result = recover_expired(item, (), now=NOW + timedelta(seconds=seconds))
    assert result.state_path == ("UNKNOWN",)
    assert result.readonly_reconcile_due is due
    assert not result.retryable
    assert not result.needs_manual_reconciliation


def test_unknown_manual_boundary_and_never_automatic_retry_or_channel_change():
    item = snapshot(state="UNKNOWN", unknown_since=NOW)
    before = recover_expired(item, (), now=NOW + timedelta(hours=24, microseconds=-1))
    assert not before.needs_manual_reconciliation
    for elapsed in (timedelta(hours=24), timedelta(days=3)):
        result = recover_expired(item, (fact(),), now=NOW + elapsed, facts_complete=True)
        assert result.state_path == ("UNKNOWN",)
        assert result.needs_manual_reconciliation
        assert not result.retryable and not result.readonly_reconcile_due
        assert result.next_reconcile_at is None


def test_reconcile_watermark_does_not_reset_twenty_four_hour_origin():
    item = snapshot(
        state="UNKNOWN", unknown_since=NOW, last_reconciled_at=NOW + timedelta(hours=23)
    )
    result = recover_expired(item, (), now=NOW + timedelta(hours=24))
    assert result.needs_manual_reconciliation


@pytest.mark.parametrize(
    "changes",
    [
        {"state": "WAITING_RETRY"},
        {"state": "FAILED_RETRYABLE"},
        {"state": "UNKNOWN"},
        {"unknown_since": NOW},
        {"lease_expires_at": NOW.replace(tzinfo=None)},
        {"revision": True},
        {"revision": MAX_REVISION + 1},
        {"last_reconciled_at": NOW},
    ],
)
def test_invalid_runtime_shape(changes):
    with pytest.raises(ValueError):
        snapshot(**changes)


def test_no_lease_active_runtime_is_invalid():
    with pytest.raises(ValueError):
        recover_expired(snapshot(lease_expires_at=None), (), now=NOW)


@pytest.mark.parametrize(
    "state", sorted(NODE_STATES - {"RUNNING", "VERIFYING", "UNKNOWN", "ACCEPTED"})
)
def test_other_states_are_not_lease_retry_shortcuts(state):
    assert recover_expired(snapshot(state=state), (), now=NOW).state_path == (state,)


def test_no_fact_sampling_duplicates_or_future_facts():
    for values in ([fact()], (fact(),) * 201, (fact(), fact())):
        with pytest.raises(ValueError):
            recover_expired(snapshot(), values, now=NOW)
    with pytest.raises(ValueError):
        recover_expired(snapshot(), (fact(occurred_at=NOW + timedelta(seconds=1)),), now=NOW)
    with pytest.raises(ValueError):
        recover_expired(snapshot(), (), now=NOW, facts_complete=1)


@pytest.mark.parametrize(
    "states,expected",
    [
        (["UNKNOWN", "NEEDS_HUMAN", "RUNNING"], "UNKNOWN"),
        (["NEEDS_HUMAN", "RUNNING"], "NEEDS_HUMAN"),
        (["RUNNING", "VERIFYING", "RETRY_WAIT"], "RUNNING"),
        (["ACCEPTED", "VERIFYING"], "RUNNING"),
        (["VERIFYING", "RETRY_WAIT"], "VERIFYING"),
        (["RETRY_WAIT", "QUEUED"], "RETRY_WAIT"),
        (["QUEUED", "SUCCEEDED"], "QUEUED"),
        (["DRAFT", "VALIDATED"], "QUEUED"),
        (["SUCCEEDED", "SUCCEEDED"], "SUCCEEDED"),
        (["SUCCEEDED", "CANCELLED"], "PARTIAL_SUCCESS"),
        (["SUCCEEDED", "BLOCKED_DEPENDENCY"], "PARTIAL_SUCCESS"),
        (["FAILED", "CANCELLED"], "FAILED"),
        (["EXPIRED", "BLOCKED_AUTH"], "FAILED"),
        (["CANCELLED", "CANCELLED"], "CANCELLED"),
    ],
)
def test_original_task_aggregation_priority(states, expected):
    assert aggregate_task_state(states) == expected
    assert expected in TASK_STATES


@pytest.mark.parametrize(
    "states", [[], ["WAITING_RETRY"], ["FAILED_RETRYABLE"], ["QUEUED"] * 100001]
)
def test_aggregation_rejects_empty_overflow_or_invented_states(states):
    with pytest.raises(ValueError):
        aggregate_task_state(states)


def test_candidate_has_only_three_tables_six_guards_and_exact_fk_direction():
    sql = (
        Path(__file__).resolve().parents[2]
        / "docs/orbit/sql-drafts/046_execution_command_leases_candidate.sql"
    ).read_text(encoding="utf-8")
    assert sql.count("CREATE TABLE ") == 3
    assert sql.count("CREATE TRIGGER ") == 6
    assert sql.count("DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs") == 3
    assert "ALTER TABLE" not in sql
    attempt, runtime, fact_sql = sql.split("CREATE TABLE ")[1:]
    assert "REFERENCES orbit_execution_command_runtime" not in attempt
    assert "REFERENCES orbit_execution_attempt" in runtime
    assert "REFERENCES orbit_execution_attempt" in fact_sql
    assert "active_attempt,fencing_token,claim_id,worker_id" in runtime
    assert "EXECUTION_ATTEMPT_IMMUTABLE" in sql
    assert "EXECUTION_FACT_IMMUTABLE" in sql
    assert "EXECUTION_RUNTIME_CAS_INVALID" in sql
    assert "WAITING_RETRY" not in sql and "FAILED_RETRYABLE" not in sql
    assert "CHAR_LENGTH(evidence_sha256)=64" in fact_sql
    assert "NOT REGEXP_LIKE(evidence_sha256,'[^0-9a-f]','c')" in fact_sql


@pytest.mark.parametrize("complete", [True, False])
def test_ack_and_proved_not_sent_are_conflict_without_readback(complete):
    result = recover_expired(
        snapshot(), (fact(), fact(FactKind.ACCEPTED)), now=NOW, facts_complete=complete
    )
    assert result.state_path[-1] == "UNKNOWN"
    assert result.code == "SEND_EVIDENCE_CONFLICT" and not result.retryable


def test_already_accepted_head_does_not_override_same_attempt_ack_not_sent_conflict():
    result = recover_expired(
        snapshot(state="ACCEPTED"), (fact(), fact(FactKind.ACCEPTED)), now=NOW, facts_complete=True
    )
    assert result.state_path == ("ACCEPTED", "VERIFYING", "UNKNOWN")
    assert result.code == "SEND_EVIDENCE_CONFLICT" and not result.retryable
