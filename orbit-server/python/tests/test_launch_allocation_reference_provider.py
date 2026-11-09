"""独立素材Provider桥纯测；DB/权限适配显式桩，不当作真实引用或平台验收。"""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from test_launch_allocation_packet import prepare, stored

import orbit_api.launch_allocation_reference_provider as module
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError
from orbit_api.launch_access import digest
from orbit_api.launch_allocation import build_compatibility_evidence
from orbit_api.launch_allocation_packet import thaw_packet
from orbit_api.launch_allocation_runtime import _freeze, solve_packet
from orbit_api.launch_expansion import ad_slots


def setup(monkeypatch, count=1):
    initial, _, _ = prepare()
    plan = initial["plan"]
    plan["asset_ids"] = sorted(str(uuid4()) for _ in range(count))
    plan["allow_repeat"] = True
    plan["campaigns"][0]["adsets"][0]["ads"] = [
        {"local_id": str(uuid4()), "copies": 1} for _ in range(max(2, count))
    ]
    packet, _, _ = prepare(plan)
    context = BusinessContext(1, str(uuid4()), "USER", str(uuid4()), str(uuid4()))
    transaction = object()
    session = SimpleNamespace(
        in_transaction=lambda: True,
        info={},
        sync_session=SimpleNamespace(get_transaction=lambda: transaction),
    )
    events = []
    rows = {
        asset: {
            "revision": 3,
            "sha256": "b" * 64,
            "kind": "IMAGE",
            "mime": "image/png",
            "size": 100,
            "width": 24,
            "height": 24,
            "duration": None,
            "state": "READY",
            "physical_cleanup_state": "LIVE",
            "antivirus_status": "CLEAN",
            "execution_eligible": True,
        }
        for asset in plan["asset_ids"]
    }

    class Authority(module.AllocationReferenceAuthority):
        async def lock_sources(self, session, current, plan, request):
            events.append("authority-locks")
            return module.LockedAllocationAuthority(
                transaction, current, digest(plan), "c" * 64, "PURE-TEST-NOT-PLATFORM", "a" * 64
            )

        def compatibility(self, locked, plan, request, materials):
            events.append("compatibility")
            return build_compatibility_evidence(
                ad_slots(plan),
                plan["asset_ids"],
                capability_version=locked.capability_version,
                source_hash=locked.source_hash,
                verified=True,
                complete=True,
                evaluate=lambda _slot, _asset: True,
                material_revisions={key: row["revision"] for key, row in materials.items()},
            )

    async def materials(session, current, owner, team, identifiers):
        events.append(("materials", tuple(identifiers)))
        return {key: dict(rows[key]) for key in identifiers}

    monkeypatch.setattr(module, "require_business_access", AsyncMock(return_value=context))
    monkeypatch.setattr(module, "require_allocation_assets", materials)
    return (
        module.ReferenceBackedAllocationProvider(Authority()),
        session,
        context,
        packet,
        rows,
        events,
    )


def test_absent_authority_fail_closed_before_permissions_or_material_sql(monkeypatch):
    provider, session, context, packet, _, _ = setup(monkeypatch)
    provider.authority = None
    forbidden = AsyncMock(side_effect=AssertionError("不能调用权限或SQL"))
    monkeypatch.setattr(module, "require_business_access", forbidden)
    with pytest.raises(OrbitError) as error:
        asyncio.run(provider.capture(session, context, packet["plan"], packet["request"]))
    assert error.value.code == "ALLOCATION_AUTHORITY_UNAVAILABLE"
    forbidden.assert_not_awaited()


def test_five_hundred_pool_has_globally_sorted_two_hundred_item_batches(monkeypatch):
    provider, session, context, packet, _, events = setup(monkeypatch, 500)
    result = asyncio.run(provider.capture(session, context, packet["plan"], packet["request"]))
    batches = [item[1] for item in events if isinstance(item, tuple)]
    assert list(map(len, batches)) == [200, 200, 100]
    assert [key for batch in batches for key in batch] == sorted(packet["plan"]["asset_ids"])
    assert events[0] == "authority-locks" and events[-1] == "compatibility"
    assert set(result.material_metadata) == set(packet["plan"]["asset_ids"])
    assert all(
        set(value)
        == {
            "revision",
            "sha256",
            "kind",
            "mime",
            "byte_size",
            "width_px",
            "height_px",
            "duration_seconds",
        }
        for value in result.material_metadata.values()
    )
    assert not session.info.get(module.TICKET_KEY)


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "PROCESSING"),
        ("physical_cleanup_state", "DELETED"),
        ("antivirus_status", "UNVERIFIED"),
        ("execution_eligible", False),
        ("execution_eligible", 1),
    ],
)
def test_media_ready_or_truthy_flag_never_substitutes_clean_source(monkeypatch, field, value):
    provider, session, context, packet, rows, events = setup(monkeypatch)
    next(iter(rows.values()))[field] = value
    with pytest.raises(OrbitError) as error:
        asyncio.run(provider.capture(session, context, packet["plan"], packet["request"]))
    assert error.value.code == "ANTIVIRUS_UNVERIFIED" and "compatibility" not in events


def test_missing_batch_item_rejects_whole_pool(monkeypatch):
    provider, session, context, packet, _, events = setup(monkeypatch)
    monkeypatch.setattr(module, "require_allocation_assets", AsyncMock(return_value={}))
    with pytest.raises(OrbitError) as error:
        asyncio.run(provider.capture(session, context, packet["plan"], packet["request"]))
    assert error.value.code == "ALLOCATION_MATERIAL_PROOF_UNAVAILABLE"
    assert "compatibility" not in events


def test_current_authorization_drift_rejects_before_source_locks(monkeypatch):
    provider, session, context, packet, _, events = setup(monkeypatch)
    monkeypatch.setattr(
        module,
        "require_business_access",
        AsyncMock(return_value=replace(context, tenant_id=str(uuid4()))),
    )
    with pytest.raises(OrbitError) as error:
        asyncio.run(provider.capture(session, context, packet["plan"], packet["request"]))
    assert error.value.status == 403 and not events


@pytest.mark.parametrize("fault", ["transaction", "source", "context", "plan", "capability"])
def test_authority_ticket_must_bind_transaction_current_context_and_real_plan(monkeypatch, fault):
    provider, session, context, packet, _, events = setup(monkeypatch)
    original = provider.authority.lock_sources

    async def malformed(*args):
        result = await original(*args)
        changes = {
            "transaction": {"transaction": object()},
            "source": {"source_hash": "bad"},
            "context": {"context": replace(context, actor_id=2)},
            "plan": {"plan_hash": "d" * 64},
            "capability": {"capability_version": ""},
        }[fault]
        return replace(result, **changes)

    provider.authority.lock_sources = malformed
    with pytest.raises(OrbitError) as error:
        asyncio.run(provider.capture(session, context, packet["plan"], packet["request"]))
    assert error.value.status == 503 and not any(isinstance(value, tuple) for value in events)


def test_publication_prelocks_old_new_union_and_registers_only_used_then_consumes_ticket(
    monkeypatch,
):
    provider, session, context, packet, _, events = setup(monkeypatch, 3)
    previous, new = str(uuid4()), str(uuid4())

    def compatible_subset(locked, plan, request, materials):
        return build_compatibility_evidence(
            ad_slots(plan),
            plan["asset_ids"],
            capability_version=locked.capability_version,
            source_hash=locked.source_hash,
            verified=True,
            complete=True,
            evaluate=lambda _slot, asset: asset != max(plan["asset_ids"]),
            material_revisions={key: row["revision"] for key, row in materials.items()},
        )

    provider.authority.compatibility = compatible_subset
    old_ticket = object()

    async def lock_old(*args, **kwargs):
        events.append(("union", args[3], tuple(kwargs["additional_asset_ids"])))
        return old_ticket

    async def release(*args):
        assert args[2] is old_ticket
        events.append("release")

    registered = []

    async def register(*args):
        events.append("register")
        registered.append(args)

    monkeypatch.setattr(module, "lock_active_material_reference_set", lock_old)
    monkeypatch.setattr(module, "deactivate_locked_material_references", release)
    monkeypatch.setattr(module, "register_active_material_references", register)

    async def publish():
        captured, ticket = await provider.prepare_publication(session, context, packet, previous)
        final_packet, manifest = _freeze(captured, packet["plan"], packet["request"], 1)
        restored, evidence = thaw_packet(*stored(final_packet, manifest))
        solution = solve_packet(restored, evidence)
        await provider.publish_references(
            session, context, restored, solution, new, previous, ticket, str(uuid4())
        )
        assert events[0] == "authority-locks" and events[1][0] == "union"
        assert events[-2:] == ["release", "register"]
        assert registered[0][5:7] == ("ALLOCATION", new)
        assert set(registered[0][4]) == {asset for _, asset in solution.assignments}
        assert len(registered[0][4]) < 3
        with pytest.raises(ValueError):
            await provider.publish_references(
                session, context, restored, solution, new, previous, ticket, str(uuid4())
            )

    asyncio.run(publish())


@pytest.mark.parametrize(
    "fault",
    ["foreign-provider", "wrong-previous", "different-transaction", "changed-metadata", "partial"],
)
def test_reference_publication_rejects_stale_or_forged_ticket_before_any_write(monkeypatch, fault):
    provider, session, context, packet, _, _ = setup(monkeypatch)
    forbidden = AsyncMock(side_effect=AssertionError("不能写引用"))
    monkeypatch.setattr(module, "register_active_material_references", forbidden)

    async def reject():
        captured, ticket = await provider.prepare_publication(session, context, packet, None)
        final_packet, manifest = _freeze(captured, packet["plan"], packet["request"], 1)
        restored, evidence = thaw_packet(*stored(final_packet, manifest))
        solution = solve_packet(restored, evidence)
        target, previous = provider, None
        if fault == "foreign-provider":
            target = module.ReferenceBackedAllocationProvider(provider.authority)
        elif fault == "wrong-previous":
            previous = str(uuid4())
        elif fault == "different-transaction":
            session.sync_session.get_transaction = lambda: object()
        elif fault == "changed-metadata":
            next(iter(restored["material_metadata"].values()))["revision"] += 1
        else:
            solution = replace(solution, assignments=solution.assignments[:1])
        with pytest.raises((ValueError, OrbitError)):
            await target.publish_references(
                session, context, restored, solution, str(uuid4()), previous, ticket, str(uuid4())
            )

    asyncio.run(reject())
    forbidden.assert_not_awaited()


@pytest.mark.parametrize("fault", ["source", "capability", "revision"])
def test_compatibility_evidence_cannot_change_locked_source_or_actual_material_version(
    monkeypatch, fault
):
    provider, session, context, packet, _, _ = setup(monkeypatch)
    original = provider.authority.compatibility

    def altered(*args):
        evidence = original(*args)
        if fault == "source":
            return replace(evidence, source_hash="d" * 64)
        if fault == "capability":
            return replace(evidence, capability_version="CHANGED")
        return replace(
            evidence,
            material_revisions=tuple(
                (key, revision + 1) for key, revision in evidence.material_revisions
            ),
        )

    provider.authority.compatibility = altered
    with pytest.raises(OrbitError):
        asyncio.run(provider.capture(session, context, packet["plan"], packet["request"]))
    assert not session.info.get(module.TICKET_KEY)


@pytest.mark.parametrize(
    "status,code",
    [
        (404, "MATERIAL_REFERENCE_UNAVAILABLE"),
        (409, "REVISION_CONFLICT"),
        (422, "REFERENCE_TEAM_MISMATCH"),
    ],
)
def test_actual_material_gate_failure_is_not_turned_into_partial_success(monkeypatch, status, code):
    provider, session, context, packet, _, events = setup(monkeypatch)
    monkeypatch.setattr(
        module,
        "require_allocation_assets",
        AsyncMock(side_effect=OrbitError(status, code, "受控失败")),
    )
    with pytest.raises(OrbitError) as error:
        asyncio.run(provider.capture(session, context, packet["plan"], packet["request"]))
    assert (error.value.status, error.value.code) == (status, code)
    assert "compatibility" not in events


def test_old_reference_release_failure_never_registers_new_and_ticket_not_consumed(monkeypatch):
    provider, session, context, packet, _, _ = setup(monkeypatch)
    monkeypatch.setattr(
        module, "lock_active_material_reference_set", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(
        module,
        "deactivate_locked_material_references",
        AsyncMock(side_effect=OrbitError(409, "REFERENCE_SET_CHANGED", "旧引用已变化")),
    )
    registered = AsyncMock()
    monkeypatch.setattr(module, "register_active_material_references", registered)

    async def reject():
        previous = str(uuid4())
        captured, ticket = await provider.prepare_publication(session, context, packet, previous)
        frozen, manifest = _freeze(captured, packet["plan"], packet["request"], 1)
        restored, evidence = thaw_packet(*stored(frozen, manifest))
        with pytest.raises(OrbitError) as error:
            await provider.publish_references(
                session,
                context,
                restored,
                solve_packet(restored, evidence),
                str(uuid4()),
                previous,
                ticket,
                str(uuid4()),
            )
        assert error.value.code == "REFERENCE_SET_CHANGED"
        assert any(item is ticket for item in session.info[module.TICKET_KEY])

    asyncio.run(reject())
    registered.assert_not_awaited()
