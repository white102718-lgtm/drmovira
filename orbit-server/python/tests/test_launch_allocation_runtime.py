"""队列安全边界纯测；事务并发/回滚留独立真实MySQL专项，不能用假session冒充。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import URL
from test_launch_allocation_packet import prepare, stored

from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError
from orbit_api.launch_allocation_packet import thaw_packet
from orbit_api.launch_allocation_runtime import (
    AllocationClaim,
    AllocationProvider,
    AllocationRuntime,
    _claim_values,
)
from orbit_api.launch_allocation_worker import solve_in_process


class DatabaseOnly:
    def __init__(self, name):
        self.name = name
        self.executed = 0
        self.bind = SimpleNamespace(url=URL.create("mysql+asyncmy", host="127.0.0.1", port=13306))

    def in_transaction(self):
        return True

    async def execute(self, statement):
        self.executed += 1
        assert str(statement) == "SELECT DATABASE()"
        return self

    def scalar_one(self):
        return self.name


class IsolatedProvider(AllocationProvider):
    kind = "ISOLATED_TEST"

    async def capture(self, *args):
        raise AssertionError("本纯测不进入真实来源业务")

    async def prepare_publication(self, *args):
        raise AssertionError("本纯测不进入真实来源业务")

    async def publish_references(self, *args):
        raise AssertionError("本纯测不伪造素材引用")


def test_missing_provider_fails_503_before_any_queue_sql():
    database = DatabaseOnly("business")
    with pytest.raises(OrbitError) as info:
        asyncio.run(
            AllocationRuntime().enqueue(database, 1, str(uuid4()), {}, 1, "x", str(uuid4()))
        )
    assert info.value.status == 503
    assert info.value.code == "ALLOCATION_PROVIDER_UNAVAILABLE"
    assert database.executed == 0


@pytest.mark.parametrize(
    "name", ["orbit", "mysql", "orbit_py_it_x", "other_orbit_py_it_" + "a" * 32]
)
def test_isolated_fixture_provider_cannot_be_used_in_real_or_imprecise_database(name):
    with pytest.raises(OrbitError) as info:
        asyncio.run(AllocationRuntime(IsolatedProvider()).require_provider(DatabaseOnly(name)))
    assert info.value.status == 503


def test_explicit_uuid_isolation_required_for_fixture_provider():
    provider = IsolatedProvider()
    assert (
        asyncio.run(
            AllocationRuntime(provider).require_provider(DatabaseOnly("orbit_py_it_" + uuid4().hex))
        )
        is provider
    )


def test_unknown_producer_kind_and_missing_concrete_capture_rejected():
    provider = IsolatedProvider()
    provider.kind = "BROWSER_VERIFIED"
    with pytest.raises(OrbitError):
        asyncio.run(AllocationRuntime(provider).require_provider(DatabaseOnly("orbit")))
    with pytest.raises(TypeError):
        AllocationProvider()


def test_cannot_forge_claim_with_plain_dict_or_save_freeform_failure_message():
    with pytest.raises(ValueError):
        _claim_values({"token": "arbitrary"})
    database = DatabaseOnly("business")
    with pytest.raises(ValueError):
        asyncio.run(
            AllocationRuntime().fail(
                database, None, "free form error containing business data", str(uuid4())
            )
        )
    assert database.executed == 0


@pytest.mark.parametrize("stage", ["permission", "tenant", "plan_scope"])
def test_current_permission_tenant_or_plan_revocation_prevents_loading_frozen_chunks(
    monkeypatch, stage
):
    import orbit_api.launch_allocation_runtime as module

    tenant, plan_id = str(uuid4()), str(uuid4())
    claim = AllocationClaim(tenant, str(uuid4()), str(uuid4()), str(uuid4()), 1)
    runtime = AllocationRuntime()
    runtime.checked_claim = AsyncMock(return_value={"actor_id": 1, "plan_id": plan_id})
    current = BusinessContext(
        1, str(uuid4()) if stage == "tenant" else tenant, "USER", str(uuid4()), str(uuid4())
    )
    authorize = AsyncMock(return_value=current)
    if stage == "permission":
        authorize.side_effect = OrbitError(403, "PERMISSION_DENIED", "已撤权")
    row = AsyncMock(side_effect=OrbitError(404, "NOT_FOUND", "当前不可见"))
    monkeypatch.setattr(module, "require_business_access", authorize)
    monkeypatch.setattr(module.LaunchStore, "row", row)
    database = DatabaseOnly("business")
    with pytest.raises(OrbitError) as info:
        asyncio.run(runtime.load(database, claim))
    assert info.value.status == (404 if stage == "plan_scope" else 403)
    assert database.executed == 0
    assert authorize.await_args.kwargs == {"acting_subject": False}
    if stage == "plan_scope":
        assert row.await_args.kwargs == {"unlocked": True}
    else:
        row.assert_not_awaited()


def test_worker_real_spawn_has_no_session_and_returns_complete_pure_solution():
    packet, manifest, _ = prepare()
    restored, evidence = thaw_packet(*stored(packet, manifest))
    status, solution = solve_in_process(restored, evidence, seconds=1)
    assert status == "SUCCESS"
    assert solution.input_hash == manifest.input_hash
    assert len(solution.assignments) == manifest.slot_count


def test_worker_child_failure_is_fixed_code_without_exception_or_payload():
    status, code = solve_in_process(
        {"deliberately_invalid_private_payload": "never-return-this"}, None, seconds=1
    )
    assert (status, code) == ("FAILURE", "ALLOCATION_INPUT_INVALID")


@pytest.mark.parametrize("seconds", [0, -1, True, 61, 1.5])
def test_worker_process_wall_limit_cannot_be_unbounded(seconds):
    with pytest.raises(ValueError):
        solve_in_process({}, None, seconds=seconds)


@pytest.mark.parametrize(
    "host,port", [("localhost", 13306), ("127.0.0.1", 3306), ("192.0.2.1", 13306)]
)
def test_isolated_provider_checks_exact_host_and_port_before_database_query(host, port):
    database = DatabaseOnly("orbit_py_it_" + uuid4().hex)
    database.bind.url = URL.create("mysql+asyncmy", host=host, port=port)
    with pytest.raises(OrbitError) as info:
        asyncio.run(AllocationRuntime(IsolatedProvider()).require_provider(database))
    assert info.value.code == "ALLOCATION_PROVIDER_UNAVAILABLE"
    assert database.executed == 0


@pytest.mark.parametrize(
    "state,revision,changed_payload",
    [
        ("SUBMITTED", 1, False),
        ("ARCHIVED", 1, False),
        ("DRAFT", 2, False),
        ("VALIDATED", 1, True),
    ],
)
def test_publication_rejects_changed_source_or_non_publishable_state(
    state, revision, changed_payload
):
    from types import SimpleNamespace

    from orbit_api.directory_tokens import canonical
    from orbit_api.launch_access import digest
    from orbit_api.launch_allocation_runtime import assert_publication_source

    packet, _, _ = prepare()
    plan = dict(packet["plan"])
    if changed_payload:
        plan["name"] += " changed"
    source = SimpleNamespace(
        source_revision=revision,
        payload_hash=digest(plan),
        canonical_payload=canonical(plan).encode(),
    )
    with pytest.raises(OrbitError) as info:
        assert_publication_source(source, packet, state)
    assert info.value.code == "ALLOCATION_SOURCE_CHANGED"


@pytest.mark.parametrize("state", ["DRAFT", "VALIDATED"])
def test_publication_uses_real_configuration_source_and_ignores_only_state_head(state):
    from orbit_api.directory_tokens import canonical
    from orbit_api.launch_access import digest
    from orbit_api.launch_allocation_runtime import assert_publication_source
    from orbit_api.launch_plan_source import PlanSource

    packet, _, _ = prepare()
    source = PlanSource(
        str(uuid4()),
        str(uuid4()),
        packet["plan_revision"],
        99,
        digest(packet["plan"]),
        canonical(packet["plan"]).encode(),
    )
    assert_publication_source(source, packet, state)


@pytest.mark.parametrize("replay", [True, False])
def test_enqueue_old_success_key_rechecks_source_before_old_cas_but_new_key_requires_current_head(
    monkeypatch, replay
):
    import orbit_api.launch_allocation_runtime as module
    from orbit_api.directory_tokens import canonical
    from orbit_api.launch_access import digest
    from orbit_api.launch_plan_source import PlanSource

    packet, manifest, _ = prepare()
    _, evidence = thaw_packet(*stored(packet, manifest))
    from dataclasses import replace

    evidence = replace(evidence, source_hash=packet["provider_source_hash"])
    tenant, plan_id = str(uuid4()), str(uuid4())
    current = BusinessContext(1, tenant, "USER", str(uuid4()), str(uuid4()))
    head = {
        "revision": 9,
        "state": "DRAFT",
        "payload_hash": digest(packet["plan"]),
        "payload_json": canonical(packet["plan"]),
    }
    source = PlanSource(
        tenant,
        plan_id,
        packet["plan_revision"],
        9,
        head["payload_hash"],
        canonical(packet["plan"]).encode(),
    )
    events = []

    async def capture(session, ctx, plan, command):
        events.append("source-locks")
        return module.CapturedAllocation(
            evidence, packet["material_metadata"], packet["authority_fingerprint"], digest(plan)
        )

    async def clock(*args, **kwargs):
        events.append("launch-clock")

    async def row(*args, **kwargs):
        events.append("head-lock" if kwargs.get("write") else "pre-read")
        return head

    async def read_source(*args):
        events.append("real-version")
        return source

    async def old_key(*args):
        events.append("old-key")
        return {"id": "original"} if replay else None

    runtime = AllocationRuntime()
    provider = SimpleNamespace(capture=capture)
    runtime.require_provider = AsyncMock(return_value=provider)
    runtime.get_for_context = AsyncMock(
        return_value={"id": "original", "input_hash": packet["input_hash"]}
    )
    monkeypatch.setattr(module.access, "context", AsyncMock(return_value=current))
    monkeypatch.setattr(module.access, "clock", clock)
    monkeypatch.setattr(module.access, "replay", old_key)
    monkeypatch.setattr(module.LaunchStore, "row", row)
    monkeypatch.setattr(module, "capture_plan_source", read_source)
    database = DatabaseOnly("business")
    if replay:
        result = asyncio.run(
            runtime.enqueue(database, 1, plan_id, packet["request"], 1, "old-key", str(uuid4()))
        )
        assert result["id"] == "original"
    else:
        with pytest.raises(OrbitError) as info:
            asyncio.run(
                runtime.enqueue(database, 1, plan_id, packet["request"], 1, "new-key", str(uuid4()))
            )
        assert info.value.code == "REVISION_CONFLICT"
        runtime.get_for_context.assert_not_awaited()
    assert events == [
        "pre-read",
        "source-locks",
        "launch-clock",
        "head-lock",
        "real-version",
        "old-key",
    ]
    assert database.executed == 0
