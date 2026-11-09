"""主动探测纯协议与安全状态边界；SQL并发和真实TLS另由集成验收覆盖。"""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from orbit_api.errors import OrbitError

NOW = datetime(2026, 11, 9, tzinfo=UTC)


def uid(n):
    return str(UUID(int=n))


def payload(**changes):
    return {
        "agent_id": uid(1),
        "boot_id": uid(2),
        "seq": 2,
        "observed_at": NOW.isoformat(),
    } | changes


def row(**changes):
    return {
        "id": uid(3),
        "agent_id": uid(1),
        "state": "QUEUED",
        "created_at": NOW - timedelta(seconds=1),
        "expires_at": NOW + timedelta(seconds=119),
        "completed_at": None,
        "error_code": None,
    } | changes


def test_completion_strict_original_device_fields():
    from orbit_api.agent_probe_contract import parse_completion

    assert parse_completion(json.dumps(payload()).encode()) == payload()


@pytest.mark.parametrize(
    "change",
    [
        {"seq": True},
        {"seq": 0},
        {"seq": 9007199254740992},
        {"agent_id": "x"},
        {"boot_id": "x"},
        {"observed_at": "2026-11-09"},
        {"state": "COMPLETED"},
        {"token": "secret"},
    ],
)
def test_completion_rejects_claimed_result_and_invalid_shape(change):
    from orbit_api.agent_probe_contract import parse_completion

    with pytest.raises(OrbitError):
        parse_completion(json.dumps(payload(**change)).encode())


def test_exact_expiration_boundary_and_terminal_state_not_rewritten():
    from orbit_api.agent_probe_store import public_request

    assert public_request(row(), NOW)["state"] == "QUEUED"
    assert public_request(row(expires_at=NOW), NOW)["state"] == "EXPIRED"
    assert public_request(row(state="COMPLETED", expires_at=NOW), NOW)["state"] == "COMPLETED"
    assert set(public_request(row(), NOW)) == {
        "id",
        "agent_id",
        "state",
        "created_at",
        "expires_at",
        "completed_at",
        "error_code",
    }


def test_complete_requires_new_observation_and_current_diagnostic():
    from orbit_api.agent_probe_store import completion_state

    head = {
        "boot_id": uid(2),
        "last_seq": 2,
        "received_at": NOW,
        "diagnostic_seq": 2,
        "diagnostic_received_at": NOW,
        "diagnostic_json": {"api_status": "READY"},
    }
    assert completion_state(row(), head, payload(), NOW) == ("COMPLETED", None)
    assert completion_state(
        row(), head | {"diagnostic_json": {"api_status": "UNKNOWN"}}, payload(), NOW
    ) == ("FAILED", "LOCAL_API_UNAVAILABLE")
    for change in [
        {"diagnostic_seq": 1},
        {"diagnostic_received_at": None},
        {"boot_id": uid(9)},
        {"last_seq": 3},
    ]:
        with pytest.raises(OrbitError):
            completion_state(row(), head | change, payload(), NOW)
    for observed in [NOW - timedelta(seconds=2), NOW + timedelta(seconds=6)]:
        with pytest.raises(OrbitError):
            completion_state(row(), head, payload(observed_at=observed.isoformat()), NOW)
    with pytest.raises(OrbitError) as e:
        completion_state(row(expires_at=NOW), head, payload(), NOW)
    assert e.value.status == 410


async def test_enqueue_current_permission_precedes_replay(monkeypatch):
    from orbit_api import agent_probe_store as target

    async def deny(*args, **kwargs):
        raise OrbitError(403, "PERMISSION_DENIED", "revoked")

    monkeypatch.setattr(target.access, "context", deny)
    with pytest.raises(OrbitError) as error:
        await target.AgentProbeStore().enqueue(None, 1, uid(1), "", "", "key", 1, uid(10))
    assert error.value.status == 403


async def test_complete_authorization_precedes_successful_replay(monkeypatch):
    from orbit_api import agent_probe_store as target

    store = target.AgentProbeStore()

    async def authenticate(*args, **kwargs):
        return {"tenant": uid(4), "agent": uid(1)}, NOW

    async def request_row(*args, **kwargs):
        return row(
            tenant_id=uid(4),
            completion_hash=target.access.digest(payload()),
            completion_ack={"state": "COMPLETED"},
        )

    async def deny(*args, **kwargs):
        raise OrbitError(403, "PROBE_AUTHORIZATION_REVOKED", "revoked")

    monkeypatch.setattr(store.monitor, "authenticate", authenticate)
    monkeypatch.setattr(store, "request_row", request_row)
    monkeypatch.setattr(store, "initiator", deny)
    with pytest.raises(OrbitError) as error:
        await store.complete(None, b"der", uid(3), payload(), uid(10))
    assert error.value.status == 403


async def test_completed_exact_replay_survives_new_seq_and_expiration(monkeypatch):
    from orbit_api import agent_probe_store as target

    store = target.AgentProbeStore()
    ack = {"id": uid(3), "revision": 1, "state": "COMPLETED", "request_id": uid(10)}

    async def authenticate(*args, **kwargs):
        return {"tenant": uid(4), "agent": uid(1)}, NOW + timedelta(days=1)

    async def request_row(*args, **kwargs):
        return row(
            state="COMPLETED",
            tenant_id=uid(4),
            completion_hash=target.access.digest(payload()),
            completion_ack=ack,
        )

    async def noop(*args, **kwargs):
        return None

    async def no_head(*args, **kwargs):
        raise AssertionError("Exact acknowledged retry must not depend on latest sequence")

    monkeypatch.setattr(store.monitor, "authenticate", authenticate)
    monkeypatch.setattr(store.monitor, "head", no_head)
    monkeypatch.setattr(store, "request_row", request_row)
    monkeypatch.setattr(store, "initiator", noop)
    monkeypatch.setattr(store, "agent_revision", noop)
    assert await store.complete(None, b"der", uid(3), payload(), uid(11)) == ack
    with pytest.raises(OrbitError) as error:
        await store.complete(None, b"der", uid(3), payload(seq=3), uid(11))
    assert error.value.code == "PROBE_COMPLETION_CONFLICT"


def test_missing_head_and_outdated_heartbeat_never_complete():
    from orbit_api.agent_probe_store import completion_state

    with pytest.raises(OrbitError):
        completion_state(row(), None, payload(), NOW)
    head = {
        "boot_id": uid(2),
        "last_seq": 2,
        "received_at": NOW - timedelta(seconds=90),
        "diagnostic_seq": 2,
        "diagnostic_received_at": NOW,
        "diagnostic_json": {"api_status": "READY"},
    }
    with pytest.raises(OrbitError):
        completion_state(row(), head, payload(), NOW)


async def test_initiator_moved_tenant_cannot_authorize_existing_request(monkeypatch):
    from types import SimpleNamespace

    from orbit_api import agent_probe_store as target

    async def context(*args, **kwargs):
        return SimpleNamespace(tenant_id=uid(99), data_role="SUPER_ADMIN")

    monkeypatch.setattr(target.access, "context", context)
    with pytest.raises(OrbitError) as error:
        await target.AgentProbeStore().initiator(None, row(actor_id=1, tenant_id=uid(4)))
    assert error.value.code == "PROBE_AUTHORIZATION_REVOKED"
