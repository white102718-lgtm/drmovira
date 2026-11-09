"""新持久接力基础协议；替身不证明真实SQL护栏或生产Authority可用。"""

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from test_launch_execution_contract import prepared

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_store import (
    ExecutionAuthorityProvider,
    iter_byte_packets,
    iter_node_packets,
    require_execution_provider,
    stage_blueprint,
)
from orbit_api.task_contract import chunk_manifest, validate_dag


class Provider(ExecutionAuthorityProvider):
    kind = "ISOLATED_TEST"

    async def capture(self, request):
        raise AssertionError("门禁不采集或发送")

    async def revalidate(self, session, current, source, evidence):
        raise AssertionError("门禁不核验或发送")

    async def publish_references(self, session, current, evidence, task_id, request_id):
        raise AssertionError("门禁不登记引用或发送")


def session(host="127.0.0.1", port=13306, database="orbit_py_it_" + "a" * 32):
    return SimpleNamespace(
        bind=SimpleNamespace(url=SimpleNamespace(host=host, port=port)),
        execute=AsyncMock(return_value=Mock(scalar_one=Mock(return_value=database))),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [None, {"kind": "TRUSTED", "verified": True}, object()])
async def test_missing_or_uncontrolled_provider_refuses_before_any_sql(provider):
    connection = session()
    with pytest.raises(OrbitError) as info:
        await require_execution_provider(connection, provider)
    assert info.value.status == 503
    connection.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("host", "port", "database"),
    [
        ("localhost", 13306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 3306, "orbit_py_it_" + "a" * 32),
        ("127.0.0.1", 13306, "orbit_python"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "A" * 32),
    ],
)
async def test_isolated_provider_requires_exact_local_uuid_database(host, port, database):
    connection = session(host, port, database)
    with pytest.raises(OrbitError):
        await require_execution_provider(connection, Provider())
    assert connection.execute.await_count == (1 if host == "127.0.0.1" and port == 13306 else 0)


@pytest.mark.asyncio
async def test_isolated_provider_guard_only_proves_protocol_target_not_authority():
    provider = Provider()
    connection = session()
    assert await require_execution_provider(connection, provider) is provider
    assert str(connection.execute.await_args.args[0]) == "SELECT DATABASE()"


def test_packets_preserve_complete_bytes_original_graph_and_resolved_commands():
    value = prepared()
    byte_packets = list(iter_byte_packets(value))
    encoded = b"".join(row.payload for row in byte_packets)
    assert hashlib.sha256(encoded).hexdigest() == value.manifest_hash
    assert all(len(row.payload) <= 65536 for row in byte_packets)
    assert [row.ordinal for row in byte_packets] == list(range(len(byte_packets)))
    assert all(hashlib.sha256(row.payload).hexdigest() == row.sha256 for row in byte_packets)
    packets = list(iter_node_packets(value))
    originals, commands = [], []
    for packet in packets:
        originals.extend(json.loads(packet.initial_json))
        commands.extend(json.loads(packet.commands_json))
    assert originals == json.loads(canonical(validate_dag(value.dag)))
    assert len(commands) == value.dag.total_dag_node_count
    assert all("resolved_configuration" in row for row in commands)
    assert all("resolved_configuration" not in row for row in originals)
    assert any(row["resolved_configuration"].get("name") for row in commands)
    blueprint = stage_blueprint(value)
    assert blueprint.expected_bytes == len(encoded)
    assert blueprint.expected_command_count == len(commands)
    assert blueprint.expected_edge_count == sum(len(row["parent_keys"]) for row in originals)
    assert (
        blueprint.task_chunk_hash
        == hashlib.sha256(canonical(chunk_manifest(originals)).encode()).hexdigest()
    )
    assert blueprint.manifest_hash != blueprint.task_chunk_hash
    with pytest.raises(FrozenInstanceError):
        packets[0].count = 0


@pytest.mark.parametrize("damage", ["hash", "bytes"])
def test_blueprint_recomputes_actual_manifest_instead_of_trusting_declared_header(damage):
    value = prepared()
    altered = replace(
        value,
        **(
            {"manifest_hash": "0" * 64}
            if damage == "hash"
            else {"manifest_bytes": value.manifest_bytes + 1}
        ),
    )
    with pytest.raises(OrbitError) as info:
        stage_blueprint(altered)
    assert info.value.code == "LAUNCH_EXECUTION_PREPARATION_UNAVAILABLE"


def test_build_spec_separately_binds_complete_command_configuration_and_original_nodes():
    from orbit_api.launch_execution_store import checked_node_packet, execution_build_spec

    value = prepared()
    spec = execution_build_spec(value)
    packet = next(iter_node_packets(value))
    originals, commands = checked_node_packet(packet, spec)
    assert len(originals) == len(commands) == packet.count
    damaged = json.loads(packet.commands_json)
    damaged[0]["resolved_configuration"] = {"placeholder": True}
    altered = replace(packet, commands_json=canonical(damaged).encode())
    with pytest.raises(OrbitError) as failure:
        checked_node_packet(altered, spec)
    assert failure.value.status == 503
    assert spec.chunks[0].node_sha256 != spec.chunks[0].command_sha256
    with pytest.raises(FrozenInstanceError):
        spec.chunks[0].command_sha256 = "0" * 64


def validation_row():
    """来自纯合同夹具的038形状；不声称真实SQL或权威来源。"""
    from test_launch_execution_contract import fixture

    from orbit_api.launch_validation_contract import validation_response

    _source, frozen, _inputs = fixture()
    return {
        "summary_json": validation_response(frozen),
        "validated_at": frozen.validated_at.replace(tzinfo=None),
        "expires_at": frozen.expires_at.replace(tzinfo=None),
        "validation_hash": frozen.hash,
        "source_revision": frozen.source_revision,
        "scope_version": frozen.scope_version,
        "naming_date": frozen.naming_date,
    }


def test_validation_row_rehydrates_original_ten_fields_and_naive_database_utc():
    from datetime import UTC

    from orbit_api.launch_execution_store import frozen_validation_row
    from orbit_api.launch_validation_contract import validation_response

    row = validation_row()
    frozen = frozen_validation_row(row)
    assert frozen.validated_at.tzinfo is UTC
    assert frozen.expires_at.tzinfo is UTC
    assert validation_response(frozen) == row["summary_json"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("valid", False),
        ("campaign_count", True),
        ("ad_count", -1),
        ("hash", "different"),
        ("errors", [{"message": "must never leak"}]),
        ("unexpected", "must never leak"),
        ("budget_totals", [{"currency": "USD", "amount": "NaN"}]),
    ],
)
def test_validation_row_corruption_is_fixed_unavailable_without_source_values(field, value):
    from orbit_api.launch_execution_store import frozen_validation_row

    row = validation_row()
    row["summary_json"][field] = value
    with pytest.raises(OrbitError) as failure:
        frozen_validation_row(row)
    assert failure.value.code == "LAUNCH_EXECUTION_PREPARATION_UNAVAILABLE"
    assert "must never leak" not in failure.value.message


def test_validation_row_rejects_non_exact_ttl_without_reissuing_a_new_expiry():
    from datetime import timedelta

    from orbit_api.launch_execution_store import frozen_validation_row

    row = validation_row()
    row["validated_at"] -= timedelta(milliseconds=1)
    with pytest.raises(OrbitError) as failure:
        frozen_validation_row(row)
    assert failure.value.status == 503


@pytest.mark.parametrize(
    "changed", [None, "ack", "expected", "hash", "stored_head", "stored_intent"]
)
def test_accepted_source_replay_requires_exact_original_body_head_and_intent(changed):
    import orbit_api.launch_execution_store as store

    current = store.BusinessContext(1, "tenant", "SUPER", "owner", "team")
    request, expected = {"hash": "a" * 64, "activate_ack": False}, 8
    accepted = {
        "validation_hash": request["hash"],
        "validated_head_revision": expected,
        "intent_hash": store.intent_for(current, "plan", 7, expected, request),
    }
    if changed == "ack":
        request["activate_ack"] = True
    elif changed == "expected":
        expected = 9
    elif changed == "hash":
        request["hash"] = "b" * 64
    elif changed == "stored_head":
        accepted["validated_head_revision"] = 9
    elif changed == "stored_intent":
        accepted["intent_hash"] = "c" * 64
    if changed is None:
        store.verify_accepted_intent(current, accepted, "plan", 7, expected, request)
    else:
        with pytest.raises(OrbitError) as failure:
            store.verify_accepted_intent(current, accepted, "plan", 7, expected, request)
        assert (failure.value.status, failure.value.code) == (409, "IDEMPOTENCY_CONFLICT")


def mapped_result(value):
    result = Mock()
    result.mappings.return_value.first.return_value = value
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["BUILDING", "SEALING", "SEALED"])
async def test_same_key_in_progress_never_shares_original_builders_abort_handle(monkeypatch, phase):
    """只验证Store协调协议；锁与真正并发由主线真实MySQL专项证明。"""
    from datetime import timedelta

    import orbit_api.launch_execution_store as store

    value = prepared()
    current = store.BusinessContext(1, value.source.tenant_id, "SUPER", "owner", "team")
    evidence = store.ExecutionEvidence(current, "validation", "a" * 64, value)
    now = value.validation_expires_at - timedelta(minutes=1)
    key = "fixture-existing-key"
    existing = {
        "id": "existing-private-stage",
        "state": phase,
        "actor_id": 1,
        "subject_id": current.subject_id,
        "intent_hash": value.request_payload_hash,
        "manifest_hash": value.manifest_hash,
        "idempotency_key_hash": hashlib.sha256(key.encode()).hexdigest(),
        "authorization_fingerprint": "f" * 64,
        "validation_id": evidence.validation_id,
        "expires_at": value.validation_expires_at,
    }
    validation = dict(
        plan_id=value.source.plan_id,
        source_revision=value.source.source_revision,
        payload_hash=value.source.payload_hash,
        validated_head_revision=value.source.head_revision,
        validation_hash=value.validation_hash,
        expires_at=value.validation_expires_at,
        naming_date=(now + timedelta(hours=8)).date(),
    )
    connection = SimpleNamespace(
        in_transaction=lambda: True,
        execute=AsyncMock(
            side_effect=[
                mapped_result(validation),
                mapped_result({"id": "task", "manifest_phase": "BUILDING"}),
                mapped_result(existing),
            ]
        ),
    )
    provider = SimpleNamespace(kind="ISOLATED_TEST", revalidate=AsyncMock(return_value=evidence))
    implementation = store.LaunchExecutionStore(None, provider)
    monkeypatch.setattr(implementation, "_authorized", AsyncMock(return_value=current))
    monkeypatch.setattr(store.access, "clock", AsyncMock())
    monkeypatch.setattr(store.task_access, "clock", AsyncMock())
    monkeypatch.setattr(
        store.LaunchStore,
        "row",
        AsyncMock(return_value={"state": "VALIDATED", "revision": value.validated_head_revision}),
    )
    monkeypatch.setattr(store, "capture_plan_source", AsyncMock(return_value=value.source))
    monkeypatch.setattr(store.LaunchValidationStore, "_lock_references", AsyncMock())
    monkeypatch.setattr(store, "database_now", AsyncMock(return_value=now))
    monkeypatch.setattr(store, "authorization_snapshot", AsyncMock(return_value=(1, "f" * 64)))
    # 此测试不重复完整绑定矩阵，关注通过相同绑定之后绝不能交出他人的handle。
    binding = Mock()
    monkeypatch.setattr(store, "verify_stage_binding", binding)
    with pytest.raises(OrbitError) as failure:
        await implementation.stage_begin(
            connection,
            1,
            "auth",
            "csrf",
            key,
            "request",
            evidence,
            store.execution_build_spec(value),
        )
    assert failure.value.code == "EXECUTION_PREPARATION_IN_PROGRESS"
    assert failure.value.status == 409
    binding.assert_called_once()
    assert all(
        str(call.args[0]).startswith("SELECT") for call in connection.execute.await_args_list
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted_race", [False, True])
async def test_expiry_sweep_uses_current_state_and_never_deletes_accepted_task(
    monkeypatch, accepted_race
):
    from datetime import timedelta

    import orbit_api.launch_execution_store as store

    now = prepared().validation_expires_at
    stage = {
        "state": "ACCEPTED" if accepted_race else "BUILDING",
        "expires_at": now - timedelta(milliseconds=1),
        "mutation_revision": 9,
    }
    connection = SimpleNamespace(
        in_transaction=lambda: True,
        execute=AsyncMock(
            side_effect=[
                mapped_result({"tenant_id": "tenant", "id": "prep", "task_id": "task"}),
                mapped_result({"manifest_phase": "COMPLETE" if accepted_race else "BUILDING"}),
                mapped_result(stage),
                SimpleNamespace(rowcount=1),
            ]
        ),
    )
    monkeypatch.setattr(store, "database_now", AsyncMock(return_value=now))
    deletion = AsyncMock(return_value=False)
    monkeypatch.setattr(store, "_delete_aborted_batch", deletion)
    result = await store.LaunchExecutionStore(None).cleanup_expired(connection, limit=200)
    calls = connection.execute.await_args_list
    assert "orbit_task " in str(calls[1].args[0])
    assert "FOR UPDATE" in str(calls[1].args[0])
    assert "orbit_launch_execution_preparation " in str(calls[2].args[0])
    assert "FOR UPDATE" in str(calls[2].args[0])
    if accepted_race:
        assert result == {"aborted": 0, "completed": False, "found": False}
        deletion.assert_not_awaited()
        assert len(calls) == 3
    else:
        update, parameters = calls[3].args
        assert "state=:state AND expires_at=:expiry" in str(update)
        assert "mutation_revision=:revision" in str(update)
        assert parameters["revision"] == 9
        assert parameters["state"] == "BUILDING"
        assert parameters["expiry"] == stage["expires_at"].replace(tzinfo=None)
        deletion.assert_awaited_once()
        assert result == {"aborted": 1, "completed": False, "found": True}


@pytest.mark.asyncio
async def test_stage_missing_provider_checks_execute_permission_before_write(
    monkeypatch,
):
    import orbit_api.launch_execution_store as store
    from orbit_api.authorization import BusinessContext

    current = BusinessContext(1, "tenant", "USER", "owner", "team")
    permission = AsyncMock(return_value=current)
    monkeypatch.setattr(store.access, "context", permission)
    monkeypatch.setattr(store, "_csrf", Mock())
    connection = SimpleNamespace(in_transaction=lambda: True, execute=AsyncMock())
    with pytest.raises(OrbitError) as failure:
        await store.LaunchExecutionStore(None).stage_begin(
            connection, 1, "auth", "csrf", "idempotency-fixture-key", "request", None, None
        )
    assert failure.value.code == "LAUNCH_EXECUTION_AUTHORITY_UNAVAILABLE"
    permission.assert_awaited_once_with(connection, 1, "launch.execute")
    connection.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_append_packet_keeps_nodes_and_resolved_commands_separate(
    monkeypatch,
):
    import orbit_api.launch_execution_store as store
    from orbit_api.authorization import BusinessContext

    value = prepared()
    spec = store.execution_build_spec(value)
    evidence = store.ExecutionEvidence(
        BusinessContext(
            1,
            value.source.tenant_id,
            "SUPER_ADMIN",
            value.source.payload()["ownership"]["owner_user_id"],
            value.source.payload()["ownership"]["owner_team_id"],
        ),
        "validation",
        "a" * 64,
        value,
    )
    handle = store.StageHandle("preparation", "task", evidence, spec, 1, "b" * 64, "c" * 64)
    packet = next(store.iter_node_packets(value))
    database = SimpleNamespace(execute=AsyncMock())
    implementation = store.LaunchExecutionStore(None)
    monkeypatch.setattr(
        implementation,
        "_locked",
        AsyncMock(
            return_value=(
                evidence.current,
                {},
                {"persisted_node_chunks": 0},
                {"tenant": value.source.tenant_id, "task": "task", "id": "preparation"},
            )
        ),
    )
    monkeypatch.setattr(store, "database_now", AsyncMock(return_value=value.validation_expires_at))
    # 真实稳定UUID namespace与packet相互独立；此处只验证绑定SQL意图，不声称落库。
    from uuid import uuid4

    handle = replace(handle, task_id=str(uuid4()))
    await implementation.append_nodes(database, 1, "auth", "csrf", handle, packet)
    inserts = {
        str(call.args[0]).split("(")[0]: call.args[1]
        for call in database.execute.await_args_list
        if str(call.args[0]).startswith("INSERT")
    }
    nodes = inserts["INSERT INTO orbit_task_node"]
    commands = inserts["INSERT INTO orbit_launch_execution_command"]
    assert len(nodes) == len(commands) == packet.count
    assert all("resolved_configuration" not in json.loads(row["initial_json"]) for row in nodes)
    assert all(isinstance(json.loads(row["resolved_configuration_json"]), dict) for row in commands)
    assert [row["node_key"] for row in nodes] == [row["node_key"] for row in commands]
    assert {row["observation_binding_hash"] for row in commands} == {
        hashlib.sha256(value.observations_json).hexdigest()
    }
