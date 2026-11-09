"""首次领取纯建议，不创建数据库/授权主体/预算锁或真实领取。"""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from orbit_api import launch_execution_claim_contract as c
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_lease_contract import AttemptBinding

NOW = datetime(2026, 11, 9, 1, tzinfo=UTC)


def uid(n):
    return str(UUID(int=n))


def fixture():
    transaction = object()
    target = c.ClaimTarget(
        uid(1),
        uid(2),
        uid(3),
        uid(4),
        uid(5),
        1,
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "META_API",
        1,
        uid(6),
        uid(7),
        uid(8),
        uid(9),
        "campaign:source",
        "CAMPAIGN",
        "CREATE",
    )
    request = c.ClaimRequest(
        target, uid(10), uid(11), c.ExpectedClaimHead(1, "QUEUED", "QUEUED", 0, 0, None)
    )
    snapshot = c.LockedClaimSnapshot(
        target,
        1,
        0,
        "QUEUED",
        "QUEUED",
        "QUEUED",
        0,
        0,
        None,
        (),
        (("QUEUED", 2),),
        "COMPLETE",
        "ACCEPTED",
        False,
        transaction,
    )
    source = c.ClaimSourceFacts(
        target,
        request.worker_id,
        uid(12),
        1,
        1,
        1,
        ("launch.execute",),
        NOW - timedelta(seconds=1),
        NOW + timedelta(minutes=5),
        NOW + timedelta(seconds=30),
        True,
        "e" * 64,
        2,
        (),
        transaction,
    )
    switches = (
        c.ClaimSwitchFact(c.SwitchScope.GLOBAL, None, 1, False),
        c.ClaimSwitchFact(c.SwitchScope.TENANT, target.tenant_id, 1, False),
        c.ClaimSwitchFact(c.SwitchScope.ACCOUNT, target.account_id, 1, False),
    )
    resources = c.ClaimResourceFacts(
        target,
        c.logical_command_hash(target),
        switches,
        "policy-v1",
        "f" * 64,
        uid(13),
        c.ReservationKind.NO_BUDGET_EFFECT,
        None,
        None,
        None,
        NOW - timedelta(seconds=1),
        NOW + timedelta(minutes=5),
        transaction,
    )
    return request, snapshot, source, resources, transaction


def decision(request=None, snapshot=None, source=None, resources=None, transaction=None):
    r, s, f, p, t = fixture()
    return c.propose_first_claim(
        request or r,
        snapshot or s,
        database_now=NOW,
        source_facts=source or f,
        resource_facts=resources or p,
        transaction=transaction or t,
    )


def call(data):
    r, s, f, p, t = data
    return c.propose_first_claim(
        r, s, database_now=NOW, source_facts=f, resource_facts=p, transaction=t
    )


def test_first_proposal_is_not_claim_or_transport_and_same_transaction_only():
    data = fixture()
    result = call(data)
    assert result.code == "CLAIM_FIRST_PROPOSAL_ONLY"
    proposal = result.proposal
    assert (proposal.next_attempt, proposal.next_fencing_token, proposal.next_runtime_revision) == (
        1,
        1,
        1,
    )
    assert (
        proposal.next_task_revision,
        proposal.next_task_sequence,
        proposal.node_path,
        proposal.task_state,
    ) == (2, 1, ("QUEUED", "RUNNING"), "RUNNING")
    assert not any(
        (
            result.claimed,
            result.transport_eligible,
            proposal.claimed,
            proposal.transport_eligible,
            proposal.writes_intent,
            proposal.releases_resources,
        )
    )
    proposal.require_same_transaction(data[-1])
    with pytest.raises(ValueError):
        proposal.require_same_transaction(object())
    with pytest.raises(FrozenInstanceError):
        proposal.claimed = True


@pytest.mark.parametrize(
    "source,resources,code",
    [
        (None, None, "EXECUTION_CLAIM_SOURCE_UNAVAILABLE"),
        (object(), object(), "EXECUTION_CLAIM_SOURCE_UNAVAILABLE"),
        ("valid", None, "EXECUTION_CLAIM_RESOURCES_UNAVAILABLE"),
    ],
)
def test_absent_proofs_never_default_to_claim(source, resources, code):
    data = fixture()
    if source == "valid":
        source = data[2]
    with pytest.raises(OrbitError) as caught:
        c.propose_first_claim(
            None, None, database_now=NOW, source_facts=source, resource_facts=resources
        )
    assert caught.value.status == 503 and caught.value.code == code


@pytest.mark.parametrize("position", [1, 2, 3])
def test_each_projection_bound_to_identical_transaction(position):
    data = list(fixture())
    data[position] = replace(data[position], _transaction=object())
    with pytest.raises(ValueError, match="SAME_TRANSACTION"):
        call(data)


@pytest.mark.parametrize("position", [1, 2, 3])
def test_target_binding_cannot_cross_account_or_source(position):
    data = list(fixture())
    data[position] = replace(data[position], target=replace(data[0].target, source_hash="0" * 64))
    assert call(data).code == "CLAIM_BINDING_MISMATCH"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("worker_enabled", False, "CLAIM_WORKER_DISABLED"),
        ("authorized_actions", (), "CLAIM_ACTION_DENIED"),
        ("worker_id", uid(99), "CLAIM_BINDING_MISMATCH"),
        ("captured_at", NOW + timedelta(microseconds=1), "CLAIM_SOURCE_EXPIRED"),
        ("expected_node_count", 3, "CLAIM_TASK_AGGREGATE_UNVERIFIED"),
        ("parent_ids", (uid(100),), "CLAIM_PARENT_BINDING_UNVERIFIED"),
    ],
)
def test_source_boundaries(field, value, code):
    data = list(fixture())
    data[2] = replace(data[2], **{field: value})
    assert call(data).code == code and call(data).proposal is None


@pytest.mark.parametrize("scope", range(3))
def test_each_kill_switch_blocks_even_other_two_are_open(scope):
    data = list(fixture())
    switches = list(data[3].switches)
    switches[scope] = replace(switches[scope], blocked=True)
    data[3] = replace(data[3], switches=tuple(switches))
    assert call(data).code == "CLAIM_KILL_SWITCH_ACTIVE"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("logical_command_hash", "0" * 64, "CLAIM_RESOURCE_BINDING_MISMATCH"),
        ("captured_at", NOW + timedelta(microseconds=1), "CLAIM_RESOURCES_EXPIRED"),
        ("expires_at", NOW, "CLAIM_RESOURCES_EXPIRED"),
    ],
)
def test_resource_boundaries(field, value, code):
    data = list(fixture())
    data[3] = replace(data[3], **{field: value})
    assert call(data).code == code


def test_enable_requires_publish_in_addition_to_execute():
    data = list(fixture())
    target = replace(data[0].target, kind="ENABLE", purpose="ENABLE")
    for i in range(4):
        data[i] = replace(data[i], target=target)
    data[3] = replace(data[3], logical_command_hash=c.logical_command_hash(target))
    assert call(data).code == "CLAIM_ACTION_DENIED"
    data[2] = replace(data[2], authorized_actions=("launch.execute", "launch.publish"))
    assert call(data).proposal is not None


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("cancel_requested", True, "CLAIM_CANCEL_REQUESTED"),
        ("manifest_phase", "BUILDING", "CLAIM_MANIFEST_INCOMPLETE"),
        ("preparation_state", "SEALED", "CLAIM_MANIFEST_INCOMPLETE"),
        ("node_state_counts", (("QUEUED", 1),), "CLAIM_TASK_AGGREGATE_UNVERIFIED"),
        ("task_revision", 2, "CLAIM_STALE"),
        ("node_attempt", 1, "CLAIM_STALE"),
        ("command_attempt", 1, "CLAIM_STALE"),
        ("command_state", "UNKNOWN", "CLAIM_STALE"),
    ],
)
def test_locked_snapshot_boundaries(field, value, code):
    data = list(fixture())
    data[1] = replace(data[1], **{field: value})
    assert call(data).code == code


@pytest.mark.parametrize("state", sorted(c.NODE_STATES - {"SUCCEEDED"}))
def test_parent_must_be_exact_success_not_accepted_or_unknown(state):
    data = list(fixture())
    parent = c.ParentClaimState(data[0].target.tenant_id, data[0].target.task_id, uid(100), state)
    data[1] = replace(data[1], parents=(parent,))
    data[2] = replace(data[2], parent_ids=(parent.node_id,))
    assert call(data).code == "CLAIM_PARENTS_NOT_SUCCEEDED"


@pytest.mark.parametrize("field", ["tenant_id", "task_id", "node_id"])
def test_parent_cannot_be_foreign_or_self(field):
    data = list(fixture())
    values = {
        "tenant_id": data[0].target.tenant_id,
        "task_id": data[0].target.task_id,
        "node_id": uid(100),
        "state": "SUCCEEDED",
    }
    values[field] = data[0].target.node_id if field == "node_id" else uid(101)
    parent = c.ParentClaimState(**values)
    data[1] = replace(data[1], parents=(parent,))
    data[2] = replace(data[2], parent_ids=(parent.node_id,))
    assert call(data).code == "CLAIM_PARENT_BINDING_UNVERIFIED"


def test_reserved_budget_requires_all_explicit_identity_fields():
    resources = fixture()[3]
    with pytest.raises(ValueError):
        replace(resources, reservation_kind=c.ReservationKind.RESERVED)
    reserved = replace(
        resources,
        reservation_kind=c.ReservationKind.RESERVED,
        reservation_id=uid(110),
        budget_owner_lock_id=uid(111),
        budget_baseline_hash="1" * 64,
    )
    assert reserved.reservation_id == uid(110)
    with pytest.raises(ValueError):
        replace(resources, reservation_id=uid(110))


@pytest.mark.parametrize(
    "changes",
    [
        {"node_attempt": True},
        {"command_attempt": -1},
        {"task_revision": 0},
        {"cancel_requested": 1},
        {"node_state_counts": (("QUEUED", 1), ("QUEUED", 1))},
    ],
)
def test_strict_original_state_counters_and_counts(changes):
    with pytest.raises(ValueError):
        replace(fixture()[1], **changes)


def receipt(request):
    target = request.target
    binding = AttemptBinding(
        target.tenant_id,
        target.task_id,
        target.node_id,
        target.preparation_id,
        uid(150),
        request.worker_id,
        1,
        1,
        target.command_hash,
        target.manifest_hash,
        target.source_hash,
        "e" * 64,
        "f" * 64,
        target.execution_mode,
        target.actor_id,
        target.subject_id,
        target.owner_user_id,
        target.owner_team_id,
        1,
    )
    return c.ClaimReceipt(
        uid(151),
        request.request_id,
        c.request_hash(request),
        binding,
        1,
        2,
        1,
        NOW + timedelta(seconds=30),
        NOW,
    )


def test_successful_original_receipt_is_same_object_and_never_renews_or_reserves():
    request = fixture()[0]
    original = receipt(request)
    assert c.match_original_receipt(request, original) is original
    assert not any(
        (original.transport_eligible, original.renews_lease, original.reserves_resources)
    )
    # 不要求当前head/expiry输入；旧CAS是原请求内容，非用于再次领取。
    assert original.lease_expires_at == NOW + timedelta(seconds=30)


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_id", uid(170)),
        ("worker_id", uid(171)),
        ("expected", c.ExpectedClaimHead(2, "QUEUED", "QUEUED", 0, 0, None)),
    ],
)
def test_same_receipt_different_intent_conflicts(field, value):
    request = fixture()[0]
    with pytest.raises(OrbitError) as caught:
        c.match_original_receipt(replace(request, **{field: value}), receipt(request))
    assert caught.value.status == 409


def test_logical_command_excludes_worker_request_and_has_stable_frozen_source():
    request = fixture()[0]
    changed = replace(request, worker_id=uid(200), request_id=uid(201))
    assert c.logical_command_hash(request.target) == c.logical_command_hash(changed.target)
    assert c.request_hash(request) != c.request_hash(changed)
    assert c.logical_command_hash(request.target) != c.logical_command_hash(
        replace(request.target, source_hash="0" * 64)
    )


@pytest.mark.parametrize("state", ["UNKNOWN", "NEEDS_HUMAN", "VERIFYING", "RETRY_WAIT"])
def test_non_claimable_task_aggregate_with_current_queued_node_is_not_revived(state):
    data = list(fixture())
    data[1] = replace(
        data[1],
        task_state=c.aggregate_task_state(("QUEUED", state)),
        node_state_counts=tuple(sorted((("QUEUED", 1), (state, 1)))),
    )
    assert call(data).code == "CLAIM_NOT_FIRST_QUEUED"


@pytest.mark.parametrize("field", ["task_revision", "task_sequence", "runtime_revision"])
def test_counter_exhaustion_never_wraps_generation(field):
    data = list(fixture())
    if field == "runtime_revision":
        runtime = c.ClaimRuntimeSnapshot(
            c.MAX_REVISION, None, 0, None, None, None, None, None, None, False
        )
        data[1] = replace(data[1], runtime=runtime)
        data[0] = replace(
            data[0], expected=replace(data[0].expected, runtime_revision=c.MAX_REVISION)
        )
    else:
        data[1] = replace(data[1], **{field: c.MAX_REVISION})
        if field == "task_revision":
            data[0] = replace(
                data[0], expected=replace(data[0].expected, task_revision=c.MAX_REVISION)
            )
    assert call(data).code == "CLAIM_COUNTER_EXHAUSTED"


def test_existing_empty_runtime_revision_advances_without_reusing_old_generation():
    data = list(fixture())
    data[1] = replace(
        data[1],
        runtime=c.ClaimRuntimeSnapshot(7, None, 0, None, None, None, None, None, None, False),
    )
    data[0] = replace(data[0], expected=replace(data[0].expected, runtime_revision=7))
    assert call(data).proposal.next_runtime_revision == 8


def test_actual_active_runtime_is_never_reclaimed_by_first_claim():
    data = list(fixture())
    data[1] = replace(
        data[1],
        runtime=c.ClaimRuntimeSnapshot(
            7,
            1,
            1,
            uid(230),
            data[0].worker_id,
            NOW + timedelta(seconds=20),
            None,
            None,
            None,
            False,
        ),
    )
    data[0] = replace(data[0], expected=replace(data[0].expected, runtime_revision=7))
    assert call(data).code == "CLAIM_ALREADY_ACTIVE"


def test_lease_exactly_expired_and_resource_lifetime_shorter_than_lease_fail_closed():
    data = list(fixture())
    data[2] = replace(data[2], lease_expires_at=NOW)
    assert call(data).code == "CLAIM_SOURCE_EXPIRED"
    data = list(fixture())
    data[3] = replace(data[3], expires_at=NOW + timedelta(seconds=29))
    assert call(data).code == "CLAIM_RESOURCES_EXPIRED"


@pytest.mark.parametrize(
    "changes",
    [
        {"switches": ()},
        {"switches": fixture()[3].switches[:2]},
        {"policy_proof_hash": None},
        {"target_lock_id": None},
        {"reservation_kind": "NO_BUDGET_EFFECT"},
    ],
)
def test_resources_have_no_optional_default_success_or_plain_string_policy(changes):
    with pytest.raises(ValueError):
        replace(fixture()[3], **changes)


def test_projection_objects_do_not_claim_issuer_authenticity():
    # 结构合法不代表已查数据库/权限/平台；此模块最多纯建议且不持久化。
    data = fixture()
    changed = list(data)
    changed[2] = replace(data[2], manifest_proof_hash="0" * 64)
    assert call(changed).code == "CLAIM_FIRST_PROPOSAL_ONLY"
    assert call(changed).proposal.transport_eligible is False
