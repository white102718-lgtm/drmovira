"""C执行桥票据/协调协议；C查询替身不证明真实030/034或双主体权限验收。"""

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_launch_execution_contract import prepared

from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError
from orbit_api.launch_execution_material_bridge import (
    TICKET_KEY,
    ExecutionMaterialBridge,
)


@pytest.fixture
def environment(monkeypatch):
    import orbit_api.launch_execution_material_bridge as module

    value = prepared()
    ownership = value.source.payload()["ownership"]
    current = BusinessContext(
        1,
        value.source.tenant_id,
        "SUPER_ADMIN",
        ownership["owner_user_id"],
        ownership["owner_team_id"],
    )
    metadata = json.loads(value.materials_json)
    seed = next(iter(metadata.values()))
    rows = {
        identifier: dict(
            metadata.get(identifier, seed),
            id=identifier,
            state="READY",
            physical_cleanup_state="LIVE",
            antivirus_status="CLEAN",
            execution_eligible=True,
        )
        for identifier in value.source.payload()["asset_ids"]
    }
    identity = object()
    session = SimpleNamespace(
        info={},
        in_transaction=lambda: True,
        sync_session=SimpleNamespace(get_transaction=lambda: identity),
    )
    permission = AsyncMock(return_value=current)

    async def read(_session, context, owner, team, ids):
        assert context == current and (owner, team) == (current.subject_id, current.team_id)
        return {identifier: rows[identifier].copy() for identifier in ids}

    reader = AsyncMock(side_effect=read)

    async def register(_session, context, owner, team, assets, kind, task, request):
        assert context == current and kind == "EXECUTION"
        return {identifier: "reference" for identifier in assets}

    publisher = AsyncMock(side_effect=register)
    monkeypatch.setattr(module, "require_business_access", permission)
    monkeypatch.setattr(module, "require_allocation_assets", reader)
    monkeypatch.setattr(module, "register_active_material_references", publisher)
    return SimpleNamespace(
        value=value,
        current=current,
        rows=rows,
        session=session,
        permission=permission,
        reader=reader,
        publisher=publisher,
        implementation=ExecutionMaterialBridge(),
    )


async def ticket(environment):
    env = environment
    capture = await env.implementation.capture_materials(env.session, env.current, env.value.source)
    return await env.implementation.lock_for_accept(
        env.session, env.current, env.value.source, capture, env.value
    )


@pytest.mark.asyncio
async def test_capture_lock_publish_full_descriptor_and_consumes_same_transaction_ticket(
    environment,
):
    env = environment
    proof = await ticket(env)
    frozen = json.loads(proof.capture.metadata_json)
    assert all(
        set(row)
        >= {
            "id",
            "owner_user_id",
            "owner_team_id",
            "mime",
            "width",
            "height",
            "duration",
            "antivirus_status",
        }
        for row in frozen.values()
    )
    result = await env.implementation.publish(
        env.session, env.current, env.value.source, env.value, proof, "task", "request"
    )
    assert set(result) == set(json.loads(env.value.materials_json))
    assert env.session.info[TICKET_KEY] == []
    assert all(
        call.args[2:] == ("launch", "launch.execute") for call in env.permission.await_args_list
    )
    assert env.publisher.await_count > 0
    with pytest.raises(ValueError):
        await env.implementation.publish(
            env.session, env.current, env.value.source, env.value, proof, "task", "request"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        "tenant",
        "actor",
        "owner",
        "source_hash",
        "source_revision",
        "used",
        "transaction",
        "manifest",
        "bridge",
        "unregistered",
    ],
)
async def test_publication_ticket_exact_binding_and_cross_transaction_rejection(
    environment, changed
):
    env = environment
    proof = await ticket(env)
    implementation = env.implementation
    if changed == "tenant":
        proof = replace(proof, current=replace(env.current, tenant_id="another"))
    elif changed == "actor":
        proof = replace(proof, current=replace(env.current, actor_id=2))
    elif changed == "owner":
        proof = replace(proof, capture=replace(proof.capture, owner_user_id="another"))
    elif changed == "source_hash":
        proof = replace(proof, capture=replace(proof.capture, source_hash="0" * 64))
    elif changed == "source_revision":
        proof = replace(proof, capture=replace(proof.capture, source_revision=99))
    elif changed == "used":
        proof = replace(proof, used=())
    elif changed == "transaction":
        env.session.sync_session.get_transaction = lambda: object()
    elif changed == "manifest":
        proof = replace(proof, manifest_hash="0" * 64)
    elif changed == "bridge":
        implementation = ExecutionMaterialBridge()
    if changed == "unregistered":
        env.session.info[TICKET_KEY] = []
    else:
        # 即使服务器代码误将修改后的对象放回列表，结构绑定仍不能跨租户/来源消费。
        env.session.info[TICKET_KEY] = [proof]
    with pytest.raises(ValueError):
        await implementation.publish(
            env.session, env.current, env.value.source, env.value, proof, "task", "request"
        )
    env.publisher.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("revision", 99), ("sha256", "0" * 64), ("width", 999)])
async def test_changed_actual_material_snapshot_fails_before_ticket_or_publication(
    environment, field, value
):
    env = environment
    capture = await env.implementation.capture_materials(env.session, env.current, env.value.source)
    next(iter(env.rows.values()))[field] = value
    with pytest.raises(OrbitError) as failure:
        await env.implementation.lock_for_accept(
            env.session, env.current, env.value.source, capture, env.value
        )
    assert failure.value.code == "STALE_PREVIEW"
    assert TICKET_KEY not in env.session.info
    env.publisher.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "QUARANTINED"),
        ("physical_cleanup_state", "DELETED"),
        ("antivirus_status", "UNVERIFIED"),
        ("execution_eligible", False),
    ],
)
async def test_ready_without_complete_current_c_proof_cannot_be_captured(environment, field, value):
    env = environment
    next(iter(env.rows.values()))[field] = value
    with pytest.raises(OrbitError) as failure:
        await env.implementation.capture_materials(env.session, env.current, env.value.source)
    assert failure.value.code == "ANTIVIRUS_UNVERIFIED"
    env.publisher.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_pool_does_not_borrow_assets_read_or_call_c_helper(environment):
    env = environment
    from orbit_api.directory_tokens import canonical
    from orbit_api.launch_access import digest

    value = env.value.source.payload()
    value["asset_ids"] = []
    source = replace(
        env.value.source, canonical_payload=canonical(value).encode(), payload_hash=digest(value)
    )
    capture = await env.implementation.capture_materials(env.session, env.current, source)
    assert capture.pool == () and json.loads(capture.metadata_json) == {}
    env.reader.assert_not_awaited()
    env.permission.assert_awaited_once_with(
        env.session, env.current.actor_id, "launch", "launch.execute"
    )


@pytest.mark.asyncio
async def test_500_pool_is_globally_sorted_before_200_item_c_batches(environment):
    from uuid import UUID

    from orbit_api.directory_tokens import canonical
    from orbit_api.launch_access import digest

    env = environment
    plan = env.value.source.payload()
    identifiers = [str(UUID(int=index)) for index in range(10000, 10500)]
    plan["asset_ids"] = list(reversed(identifiers))
    seed = next(iter(env.rows.values()))
    env.rows.update({identifier: dict(seed, id=identifier) for identifier in identifiers})
    source = replace(
        env.value.source, canonical_payload=canonical(plan).encode(), payload_hash=digest(plan)
    )
    captured = await env.implementation.capture_materials(env.session, env.current, source)
    assert captured.pool == tuple(identifiers)
    batches = [list(call.args[4]) for call in env.reader.await_args_list]
    assert [len(batch) for batch in batches] == [200, 200, 100]
    assert [identifier for batch in batches for identifier in batch] == identifiers


@pytest.mark.asyncio
async def test_current_action_revocation_or_scope_change_stops_before_material_read(environment):
    env = environment
    env.permission.return_value = replace(env.current, actor_id=2)
    with pytest.raises(OrbitError) as failure:
        await env.implementation.capture_materials(env.session, env.current, env.value.source)
    assert failure.value.code == "STALE_PREVIEW"
    env.reader.assert_not_awaited()
