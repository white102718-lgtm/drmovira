"""租约设备客户端严格响应边界，网络成功不代表可发送。"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from orbit_agent.adspower_status import ProbeError
from orbit_agent.transport import DeviceClient


def uid(n):
    return str(UUID(int=n))


def lease():
    return {
        **{
            k: uid(i + 1)
            for i, k in enumerate(
                ("id", "operation_id", "task_id", "node_id", "attempt_id", "profile_binding_id")
            )
        },
        "expires_at": (datetime.now(UTC) + timedelta(seconds=120)).isoformat(),
        "fencing_token": 1,
        "workflow_version": "pause_entity_v1",
        "adapter_version": "isolated-v1",
        "command_hash": "a" * 64,
    }


def client(response):
    value = object.__new__(DeviceClient)
    value.agent_id = uid(10)
    value.request = AsyncMock(return_value=response)
    return value


async def test_next_lease_exact_protocol_and_empty_backoff():
    dev = client({"lease": lease(), "retry_after_seconds": 20})
    assert hasattr(dev, "next_lease"), "device lease consumer is missing"
    result = await dev.next_lease()
    assert result["lease"]["fencing_token"] == 1
    dev.request.assert_awaited_once_with("GET", "/api/v1/agent-api/leases/next")
    dev.request.return_value = {"lease": None, "retry_after_seconds": 20}
    assert (await dev.next_lease())["lease"] is None


@pytest.mark.parametrize("bad", [True, -1, 301, "20"])
async def test_next_rejects_invalid_backoff(bad):
    dev = client({"lease": None, "retry_after_seconds": bad})
    assert hasattr(dev, "next_lease")
    with pytest.raises(ProbeError):
        await dev.next_lease()


@pytest.mark.parametrize(
    "change",
    [
        {"fencing_token": True},
        {"command_hash": "X" * 64},
        {"token": "secret"},
        {"expires_at": "2026-11-10"},
    ],
)
async def test_next_rejects_untrusted_lease(change):
    dev = client({"lease": lease() | change, "retry_after_seconds": 20})
    assert hasattr(dev, "next_lease")
    with pytest.raises(ProbeError):
        await dev.next_lease()


async def test_renew_cannot_substitute_lease_or_fence():
    row = lease()
    dev = client(row)
    assert hasattr(dev, "renew_lease")
    assert await dev.renew_lease(row["id"], uid(20), 1) == row
    dev.request.assert_awaited_once_with(
        "POST",
        f"/api/v1/agent-api/leases/{row['id']}/renew",
        {"agent_id": uid(10), "boot_id": uid(20), "fencing_token": 1},
    )
    dev.request.return_value = row | {"fencing_token": 2}
    with pytest.raises(ProbeError):
        await dev.renew_lease(row["id"], uid(20), 1)


async def test_event_ack_must_cover_exact_sent_ids_once():
    event = {"event_id": uid(21)}
    dev = client(
        {
            "accepted_event_ids": [uid(21)],
            "duplicate_event_ids": [],
            "rejected_event_ids": [],
            "historical_event_ids": [],
            "request_id": uid(22),
        }
    )
    assert hasattr(dev, "report_events")
    assert (await dev.report_events([event]))["accepted_event_ids"] == [uid(21)]
    for change in (
        {"accepted_event_ids": [uid(23)]},
        {"duplicate_event_ids": [uid(21)]},
        {"accepted_event_ids": []},
        {"historical_event_ids": [uid(23)]},
    ):
        dev.request.return_value = {
            "accepted_event_ids": [uid(21)],
            "duplicate_event_ids": [],
            "rejected_event_ids": [],
            "historical_event_ids": [],
            "request_id": uid(22),
        } | change
        with pytest.raises(ProbeError):
            await dev.report_events([event])


@pytest.mark.parametrize("bad", [[{}], [None], "not-a-list"])
async def test_event_ack_invalid_members_produce_safe_protocol_error(bad):
    dev = client(
        {
            "accepted_event_ids": bad,
            "duplicate_event_ids": [],
            "rejected_event_ids": [],
            "historical_event_ids": [],
            "request_id": uid(22),
        }
    )
    with pytest.raises(ProbeError):
        await dev.report_events([{"event_id": uid(21)}])


async def test_command_rejects_wrong_lease_and_missing_create_manifest():
    instruction = {
        "lease_id": uid(1),
        "command_hash": "a" * 64,
        "account_id": uid(2),
        "external_account_id": "123",
        "node_key": "pause:123",
        "kind": "PAUSE",
        "target": None,
        "plan": None,
        "manual": None,
        "policy_version": "v1",
        "submission_group_id": None,
        "allowed_until": datetime.now(UTC).isoformat(),
        "execution_manifest_id": None,
        "execution_manifest_hash": None,
    }
    dev = client(instruction)
    assert await dev.execution_command(uid(1)) == instruction
    with pytest.raises(ProbeError):
        await dev.execution_command(uid(3))
    dev.request.return_value = instruction | {"kind": "CREATE"}
    with pytest.raises(ProbeError):
        await dev.execution_command(uid(1))
