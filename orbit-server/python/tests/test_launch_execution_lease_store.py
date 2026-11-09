"""窄Store读取/信任纯测；替身不证明真实MySQL锁序或正式authority已接入。"""

import asyncio
import hashlib
from dataclasses import asdict, replace
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from test_launch_execution_lease_contract import NOW, binding, fact

import orbit_api.launch_execution_lease_store as module
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_lease_contract import FactKind


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class FixtureAuthority(module.ExecutionLeaseAuthority):
    """显式纯测内部协议，绝不注册应用或声称真实证据已核实。"""

    def __init__(self):
        self.validated = []
        self.grant_transform = lambda grant: grant
        self.fact_transform = lambda receipt: receipt

    async def authorize(self, session, actor_id, attempt, operation):
        return self.grant_transform(module.LeaseAuthorityGrant(actor_id, attempt, operation))

    async def verify_fact(self, session, record, *, recorded_at):
        self.validated.append(record.event_id)
        return self.fact_transform(
            module.FactValidationReceipt.for_fact(record, recorded_at=recorded_at)
        )


class Session:
    def __init__(self):
        self.transaction = object()
        self.active = True
        self.calls = []
        self.configuration = {"isolated_protocol_only": True}
        self.binding = binding(
            command_hash=hashlib.sha256(canonical(self.configuration).encode()).hexdigest()
        )
        self.clock = {"revision": 3}
        self.task = {
            "owner_user_id": self.binding.owner_user_id,
            "owner_team_id": self.binding.owner_team_id,
            "source_hash": self.binding.source_hash,
            "execution_mode": self.binding.execution_mode,
            "manifest_phase": "COMPLETE",
            "node_count": 20,
            "expected_node_count": 20,
        }
        self.command = {
            "state": "RUNNING",
            "attempt": 1,
            "preparation_id": self.binding.preparation_id,
            "resolved_configuration_json": canonical(self.configuration),
            "resolved_configuration_hash": self.binding.command_hash,
        }
        self.preparation = {
            "id": self.binding.preparation_id,
            "task_id": self.binding.task_id,
            "manifest_hash": self.binding.manifest_hash,
            "payload_hash": self.binding.source_hash,
            "state": "ACCEPTED",
            "expected_command_count": 20,
            "persisted_command_count": 20,
        }
        self.node = {"state": "RUNNING", "attempt": 1}
        self.runtime = {
            "revision": 2,
            "active_attempt": 1,
            "fencing_token": self.binding.fencing_token,
            "claim_id": self.binding.claim_id,
            "worker_id": self.binding.worker_id,
            "lease_expires_at": NOW.replace(tzinfo=None),
            "unknown_since": None,
            "last_reconciled_at": None,
        }
        self.attempt = asdict(self.binding)
        self.facts = []

    def in_transaction(self):
        return self.active

    def get_transaction(self):
        return self.transaction if self.active else None

    async def execute(self, statement, values):
        sql = str(statement)
        assert sql.startswith("SELECT "), "本阶段禁止任何写入"
        self.calls.append((sql, values))
        if "FROM orbit_execution_attempt_fact " in sql:
            assert "sequence_no>:after" in sql and "ORDER BY sequence_no LIMIT 200 FOR SHARE" in sql
            return Result([row for row in self.facts if row["sequence_no"] > values["after"]][:200])
        for name, record in (
            ("FROM orbit_task_clock ", self.clock),
            ("FROM orbit_task ", self.task),
            ("FROM orbit_launch_execution_preparation ", self.preparation),
            ("FROM orbit_launch_execution_command c ", self.command),
            ("FROM orbit_task_node ", self.node),
            ("FROM orbit_execution_command_runtime ", self.runtime),
            ("FROM orbit_execution_attempt ", self.attempt),
        ):
            if name in sql:
                return Result([] if record is None else [record])
        if sql == "SELECT UTC_TIMESTAMP(6) AS now":
            return Result([{"now": NOW.replace(tzinfo=None)}])
        raise AssertionError("未识别固定SQL")

    def row(self, sequence, kind=FactKind.PROVED_NOT_SENT):
        record = fact(
            kind,
            binding=self.binding,
            event_id=str(UUID(int=10000 + sequence)),
        )
        return {
            "sequence_no": sequence,
            "attempt_no": self.binding.attempt_no,
            "fencing_token": self.binding.fencing_token,
            "claim_id": self.binding.claim_id,
            "worker_id": self.binding.worker_id,
            "event_id": record.event_id,
            "fact_kind": record.kind.value,
            "send_phase": record.phase.value,
            "evidence_source": record.source.value,
            "evidence_sha256": record.evidence_sha256,
            "external_id": record.external_id,
            "occurred_at": NOW.replace(tzinfo=None),
            "recorded_at": NOW.replace(tzinfo=None),
        }


def expected(session):
    return module.RuntimeExpectation(
        2,
        session.binding.attempt_no,
        session.binding.fencing_token,
        session.binding.claim_id,
        session.binding.worker_id,
    )


async def capture(session, authority=None, guard=None):
    return await module.ExecutionLeaseStore(authority or FixtureAuthority()).capture_recovery(
        session, 1, session.binding, guard or expected(session)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("authority", [None, True, SimpleNamespace(kind="TRUSTED")])
async def test_missing_or_label_only_authority_fails_before_any_sql(authority):
    session = Session()
    with pytest.raises(OrbitError) as error:
        await module.ExecutionLeaseStore(authority).capture_recovery(
            session, 1, session.binding, expected(session)
        )
    assert error.value.code == "EXECUTION_LEASE_AUTHORITY_UNAVAILABLE"
    assert not session.calls


@pytest.mark.asyncio
async def test_requires_outer_transaction_and_has_no_implicit_commit():
    session = Session()
    session.active = False
    with pytest.raises(ValueError):
        await capture(session)
    assert not session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transform",
    [
        lambda grant: None,
        lambda grant: True,
        lambda grant: replace(grant, actor_id=2),
        lambda grant: replace(grant, operation=module.LeaseOperation.HISTORICAL_FACT),
        lambda grant: replace(grant, binding=binding()),
    ],
)
async def test_grant_must_bind_exact_actor_operation_and_frozen_attempt(transform):
    session, authority = Session(), FixtureAuthority()
    authority.grant_transform = transform
    with pytest.raises(OrbitError) as error:
        await capture(session, authority)
    assert error.value.code == "EXECUTION_LEASE_AUTHORITY_UNAVAILABLE"
    assert not session.calls


@pytest.mark.asyncio
async def test_empty_facts_are_complete_but_cannot_prove_not_sent():
    session = Session()
    result = await capture(session)
    assert result.summary.total_count == 0
    assert result.summary.counts == ()
    assert result.decision(session).state_path == ("RUNNING", "UNKNOWN")
    tables = [sql.split("FROM ")[1].split()[0] for sql, _ in session.calls if "FROM " in sql]
    assert tables[:7] == [
        "orbit_task_clock",
        "orbit_task",
        "orbit_launch_execution_preparation",
        "orbit_launch_execution_command",
        "orbit_task_node",
        "orbit_execution_command_runtime",
        "orbit_execution_attempt",
    ]
    assert "FOR UPDATE" in session.calls[0][0]


@pytest.mark.asyncio
async def test_two_hundred_eighty_eight_facts_stream_to_empty_page_with_bounded_summary():
    session, authority = Session(), FixtureAuthority()
    session.facts = [session.row(n, FactKind.READBACK_INCONCLUSIVE) for n in range(1, 289)]
    result = await capture(session, authority)
    assert result.summary.total_count == result.summary.last_sequence == 288
    assert result.summary.counts == ((FactKind.READBACK_INCONCLUSIVE, 288),)
    assert len(result.summary.representatives) == 1
    assert len(authority.validated) == 288
    pages = [values["after"] for sql, values in session.calls if "attempt_fact " in sql]
    assert pages == [0, 200, 288]
    assert result.decision(session).state_path[-1] == "UNKNOWN"


@pytest.mark.asyncio
async def test_unknown_twenty_four_hours_requires_manual_without_incrementing_execution_attempt():
    session = Session()
    session.command["state"] = session.node["state"] = "UNKNOWN"
    session.runtime.update(
        unknown_since=(NOW - timedelta(hours=24)).replace(tzinfo=None),
        last_reconciled_at=(NOW - timedelta(minutes=5)).replace(tzinfo=None),
        lease_expires_at=None,
    )
    session.facts = [session.row(n, FactKind.READBACK_INCONCLUSIVE) for n in range(1, 289)]
    result = await capture(session)
    decision = result.decision(session)
    assert decision.state_path == ("UNKNOWN",)
    assert decision.needs_manual_reconciliation
    assert not decision.retryable and not decision.readonly_reconcile_due
    assert session.runtime["active_attempt"] == session.node["attempt"] == 1


@pytest.mark.asyncio
async def test_intent_after_page_two_is_not_dropped_and_prevents_safe_retry():
    session = Session()
    session.facts = [session.row(n) for n in range(1, 202)]
    session.facts.append(session.row(202, FactKind.WRITE_INTENT))
    result = await capture(session)
    assert result.summary.total_count == 202
    assert len(result.summary.representatives) == 2
    decision = result.decision(session)
    assert decision.state_path == ("RUNNING", "UNKNOWN") and not decision.retryable


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [FactKind.READBACK_SUCCEEDED, FactKind.READBACK_REJECTED, FactKind.READBACK_INCONCLUSIVE],
)
async def test_late_page_readback_conflicts_with_early_positive_not_sent(kind):
    session = Session()
    session.facts = [session.row(n) for n in range(1, 201)] + [session.row(201, kind)]
    result = await capture(session)
    assert result.decision(session).code == "SEND_EVIDENCE_CONFLICT"
    assert not result.decision(session).retryable


@pytest.mark.asyncio
@pytest.mark.parametrize("gap", [1, 199, 200, 201, 287])
async def test_any_sequence_gap_rejects_instead_of_certifying_partial_facts(gap):
    session = Session()
    session.facts = [session.row(n) for n in range(1, 289) if n != gap]
    with pytest.raises(OrbitError) as error:
        await capture(session)
    assert error.value.code == "EXECUTION_LEASE_SOURCE_UNVERIFIED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "column,value",
    [
        ("fencing_token", 2),
        ("claim_id", str(UUID(int=50))),
        ("worker_id", str(UUID(int=51))),
        ("attempt_no", 2),
        ("fact_kind", "UNKNOWN"),
        ("send_phase", "DISPATCH_STARTED"),
        ("evidence_sha256", "G" * 64),
        ("external_id", "123x"),
        ("occurred_at", NOW + timedelta(seconds=1)),
        ("recorded_at", NOW + timedelta(seconds=1)),
    ],
)
async def test_every_fact_binding_phase_hash_and_sql_time_is_checked(column, value):
    session = Session()
    session.facts = [session.row(1) | {column: value}]
    with pytest.raises(OrbitError) as error:
        await capture(session)
    assert error.value.code == "EXECUTION_LEASE_SOURCE_UNVERIFIED"


@pytest.mark.asyncio
@pytest.mark.parametrize("receipt", [None, True, "VERIFIED"])
async def test_each_fact_needs_typed_controlled_verification_not_a_boolean_or_hash(receipt):
    session, authority = Session(), FixtureAuthority()
    session.facts = [session.row(1)]
    authority.fact_transform = lambda value: receipt
    with pytest.raises(OrbitError):
        await capture(session, authority)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["external", "recorded", "hash"])
async def test_receipt_must_bind_entire_exact_fact_and_recorded_time(change):
    session, authority = Session(), FixtureAuthority()
    session.facts = [session.row(1)]

    def transform(receipt):
        if change == "recorded":
            return replace(receipt, recorded_at=receipt.recorded_at - timedelta(seconds=1))
        return replace(
            receipt,
            fact=replace(
                receipt.fact,
                **(
                    {"external_id": "123"}
                    if change == "external"
                    else {"evidence_sha256": "1" * 64}
                ),
            ),
        )

    authority.fact_transform = transform
    with pytest.raises(OrbitError):
        await capture(session, authority)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"revision": 3},
        {"attempt_no": 2},
        {"fencing_token": 2},
        {"claim_id": str(UUID(int=55))},
        {"worker_id": str(UUID(int=56))},
    ],
)
async def test_expected_head_checks_revision_and_all_fencing_fields(change):
    session = Session()
    with pytest.raises(OrbitError) as error:
        await capture(session, guard=replace(expected(session), **change))
    assert error.value.code == "EXECUTION_LEASE_STALE"
    assert not any("attempt_fact " in sql for sql, _ in session.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,field,value",
    [
        ("task", "manifest_phase", "BUILDING"),
        ("task", "expected_node_count", 21),
        ("task", "source_hash", "1" * 64),
        ("command", "state", "QUEUED"),
        ("preparation", "persisted_command_count", 19),
        ("preparation", "state", "BUILDING"),
        ("command", "resolved_configuration_json", '{"changed":true}'),
        ("node", "state", "UNKNOWN"),
        ("node", "attempt", 2),
        ("attempt", "authority_hash", "1" * 64),
        ("attempt", "auth_version", 2),
    ],
)
async def test_real_source_attempt_node_and_command_must_all_agree(target, field, value):
    session = Session()
    getattr(session, target)[field] = value
    with pytest.raises(OrbitError) as error:
        await capture(session)
    assert error.value.code == "EXECUTION_LEASE_SOURCE_UNVERIFIED"


@pytest.mark.asyncio
async def test_summary_cannot_be_used_after_outer_transaction_changes_or_with_forged_issuer():
    session = Session()
    session.facts = [session.row(1)]
    result = await capture(session)
    assert result.decision(session).retryable
    for tampered in (
        replace(result, _issuer=object()),
        replace(result, summary=replace(result.summary, _issuer=object())),
        replace(result, summary=replace(result.summary, representatives=())),
        replace(result, database_now=result.database_now + timedelta(days=1)),
        replace(result, snapshot=replace(result.snapshot, revision=3)),
    ):
        with pytest.raises(OrbitError):
            tampered.decision(session)
    session.transaction = object()
    with pytest.raises(OrbitError):
        result.decision(session)


@pytest.mark.asyncio
async def test_read_budget_exhaustion_is_not_complete_or_safe_retry(monkeypatch):
    session, authority = Session(), FixtureAuthority()
    session.facts = [session.row(1)]

    async def delayed(*args, **kwargs):
        await asyncio.sleep(1)

    authority.verify_fact = delayed
    monkeypatch.setattr(module, "FACT_READ_SECONDS", 0.001)
    with pytest.raises(OrbitError) as error:
        await capture(session, authority)
    assert error.value.code == "EXECUTION_FACT_READ_TIMEOUT"
