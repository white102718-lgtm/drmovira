"""设备租约严格合同与默认关闭边界。"""

import json
from uuid import uuid4

import pytest

from orbit_api.agent_execution_contract import instruction_hash, parse_events, parse_renew
from orbit_api.agent_execution_store import AgentExecutionStore, ExecutionDispatchAuthority
from orbit_api.errors import OrbitError


def test_renew_exact():
    value = {"agent_id": str(uuid4()), "boot_id": str(uuid4()), "fencing_token": 1}
    assert parse_renew(json.dumps(value).encode()) == value
    for change in ({"fencing_token": True}, {"fencing_token": 0}, {"x": 1}, {"agent_id": "wrong"}):
        with pytest.raises(OrbitError):
            parse_renew(json.dumps(value | change).encode())


def test_instruction_hash_dynamic_fields():
    a = {
        "account_id": str(uuid4()),
        "lease_id": str(uuid4()),
        "command_hash": "a" * 64,
        "allowed_until": "old",
    }
    assert instruction_hash(a) == instruction_hash(
        a | {"lease_id": str(uuid4()), "allowed_until": "new", "command_hash": "b" * 64}
    )
    assert instruction_hash(a) != instruction_hash(a | {"account_id": str(uuid4())})


@pytest.mark.asyncio
async def test_unconfigured_authority_never_enqueues():
    with pytest.raises(OrbitError) as error:
        await AgentExecutionStore().enqueue(None, {}, "request")
    assert error.value.code == "EXECUTION_AUTHORITY_UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,args",
    [
        ("next", (b"cert", "request")),
        ("command", (b"cert", str(uuid4()))),
        ("renew", (b"cert", str(uuid4()), {}, "request")),
        ("events", (b"cert", {}, "request")),
    ],
)
async def test_no_authority_never_accesses_database(method, args):
    with pytest.raises(OrbitError) as error:
        await getattr(AgentExecutionStore(), method)(None, *args)
    assert error.value.code == "EXECUTION_AUTHORITY_UNAVAILABLE"


def test_authority_requires_actual_receipt_validation_implementation():
    class Incomplete(ExecutionDispatchAuthority):
        async def revalidate(self, *a, **k):
            pass

        async def claim(self, *a, **k):
            pass

    with pytest.raises(TypeError):
        Incomplete()


@pytest.mark.parametrize("events", [[], [{}], [{}] * 101])
def test_events_reject_missing_fields_or_unbounded_batch(events):
    with pytest.raises(OrbitError):
        parse_events(json.dumps({"events": events}).encode())


def dispatch_grant():
    grant = {
        key: str(uuid4())
        for key in (
            "tenant_id",
            "id",
            "task_id",
            "node_id",
            "operation_id",
            "agent_id",
            "profile_binding_id",
        )
    }
    grant.update(
        binding_revision=1,
        actor_id=1,
        entity_type="CAMPAIGN",
        versions={
            key: "v1"
            for key in (
                "workflow_version",
                "adapter_version",
                "client_version",
                "browser_version",
                "page_language",
            )
        },
        instruction=dict(
            account_id=str(uuid4()),
            external_account_id="12345",
            node_key="campaign",
            kind="CREATE",
            target=None,
            plan=None,
            manual=None,
            policy_version="v1",
            submission_group_id=None,
            execution_manifest_id=str(uuid4()),
            execution_manifest_hash="a" * 64,
        ),
    )
    return grant


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed", ["none", "versions", "actor", "operation", "instruction", "permission"]
)
async def test_enqueue_replay_checks_current_authority_and_full_frozen_intent(monkeypatch, changed):
    from unittest.mock import AsyncMock

    from orbit_api import agent_execution_store as module
    from orbit_api.directory_tokens import canonical

    class Authority(ExecutionDispatchAuthority):
        async def revalidate(self, session, dispatch, *, phase):
            if changed == "permission":
                raise OrbitError(403, "PERMISSION_DENIED", "已撤权")

        async def claim(self, *a):
            pass

        async def expire(self, *a):
            pass

        async def record_event(self, *a, **k):
            pass

    grant = dispatch_grant()
    row = {k: v for k, v in grant.items() if k not in ("instruction", "versions")} | {
        "instruction_json": canonical(grant["instruction"]),
        "versions_json": canonical(grant["versions"]),
        "command_hash": instruction_hash(grant["instruction"]),
        "state": "LEASED",
    }
    if changed == "versions":
        grant["versions"]["adapter_version"] = "v2"
    if changed == "actor":
        grant["actor_id"] = 2
    if changed == "operation":
        grant["operation_id"] = str(uuid4())
    if changed == "instruction":
        grant["instruction"]["policy_version"] = "v2"
    monkeypatch.setattr(module.access, "clock", AsyncMock())
    read = AsyncMock(return_value=row)
    monkeypatch.setattr(module, "one", read)
    store = AgentExecutionStore(Authority())
    store._command_row = AsyncMock(return_value={"state": "RUNNING", "attempt": 1})
    store._event = AsyncMock()
    if changed == "none":
        assert await store.enqueue(object(), grant, str(uuid4())) == {
            "id": row["id"],
            "command_hash": row["command_hash"],
        }
    else:
        with pytest.raises(OrbitError) as error:
            await store.enqueue(object(), grant, str(uuid4()))
        assert error.value.code == (
            "PERMISSION_DENIED" if changed == "permission" else "EXECUTION_DISPATCH_CONFLICT"
        )
        if changed == "permission":
            read.assert_not_awaited()
    store._event.assert_not_awaited()
