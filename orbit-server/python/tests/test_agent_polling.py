from unittest.mock import AsyncMock
from uuid import UUID

import pytest


@pytest.mark.asyncio
async def test_current_home_monitor_never_uploads_cdp_or_claims_valid(tmp_path):
    from orbit_agent.adspower_readonly import Discovery
    from orbit_agent.polling import run_cycle
    from orbit_agent.spool import Spool

    agent = str(UUID(int=1))
    adapter = AsyncMock()
    adapter.discover.return_value = Discovery(
        "READY",
        "ACTIVE_ONLY",
        (("p", "ACTIVE"),),
        "ADSPOWER_SUBSCRIPTION_REQUIRED",
        {"p": "private-debug-address"},
    )
    device = AsyncMock()
    device.configuration.return_value = {"agent_id": agent, "bindings": []}
    device.send.return_value = {
        "id": agent,
        "revision": 1,
        "state": "READY",
        "request_id": str(UUID(int=2)),
    }
    with Spool(tmp_path / "private", agent) as spool:
        result = await run_cycle(adapter, device, spool, selected_profiles=set())
        assert result["inventory_coverage"] == "ACTIVE_ONLY"
        assert "p" not in result and "private-debug-address" not in str(device.send.call_args_list)
        heartbeat = device.send.call_args_list[0].args[1]
        assert heartbeat["profiles"][0]["identity_state"] == "UNKNOWN"
        assert heartbeat["profiles"][0]["account_ids"] == []
        assert spool.pending() == []


def test_identity_report_requires_sequence():
    from orbit_agent.adspower_status import ProbeError
    from orbit_agent.protocol import ADAPTER_VERSION, validate_payload

    value = {
        "agent_id": str(UUID(int=1)),
        "boot_id": str(UUID(int=2)),
        "event_id": str(UUID(int=3)),
        "binding_id": str(UUID(int=4)),
        "binding_revision": 1,
        "profile_external_id": "p",
        "external_account_id": None,
        "currency": None,
        "identity_state": "UNKNOWN",
        "adapter_version": ADAPTER_VERSION,
        "observed_at": "2026-11-09T00:00:00Z",
        "evidence_sha256": "a" * 64,
    }
    with pytest.raises(ProbeError):
        validate_payload("identity", value)
    assert validate_payload("identity", value | {"seq": 1})["seq"] == 1


@pytest.mark.asyncio
async def test_unknown_delivery_replays_exact_persisted_heartbeat_before_new_sequence(tmp_path):
    from orbit_agent.adspower_readonly import Discovery
    from orbit_agent.adspower_status import ProbeError
    from orbit_agent.polling import run_cycle
    from orbit_agent.spool import Spool

    agent = str(UUID(int=1))
    adapter = AsyncMock()
    adapter.discover.return_value = Discovery("READY", "FULL", (), None)
    device = AsyncMock()
    device.configuration.return_value = {"agent_id": agent, "bindings": []}
    ack = {"id": agent, "revision": 1, "state": "READY", "request_id": str(UUID(int=2))}
    device.send.side_effect = [ProbeError("DEVICE_CONNECTION_FAILED"), ack, ack, ack]
    with Spool(tmp_path / "private", agent) as spool:
        first = await run_cycle(adapter, device, spool, selected_profiles=set())
        assert first["delivery"] == "PENDING"
        original = spool.pending()[0]["payload"]
        await run_cycle(adapter, device, spool, selected_profiles=set())
        assert device.send.call_args_list[1].args == ("heartbeat", original)
        assert device.send.call_args_list[2].args[1]["seq"] == 2
        assert spool.pending() == []


@pytest.mark.asyncio
async def test_same_profile_different_binding_expectations_do_not_reuse_result(
    tmp_path, monkeypatch
):
    from orbit_agent import polling
    from orbit_agent.adspower_readonly import Discovery
    from orbit_agent.spool import Spool

    agent = str(UUID(int=1))
    adapter = AsyncMock()
    adapter.discover.return_value = Discovery(
        "READY", "FULL", (("p", "ACTIVE"),), None, {"p": "private-debug-address"}
    )
    device = AsyncMock()
    expectations = [("111", "USD"), ("222", "USD"), ("111", "EUR"), ("111", "USD")]
    device.configuration.return_value = {
        "bindings": [
            {
                "id": str(UUID(int=index + 10)),
                "revision": 1,
                "profile_external_id": "p",
                "external_account_id": account,
                "currency": currency,
            }
            for index, (account, currency) in enumerate(expectations)
        ]
    }
    device.send.return_value = {"state": "READY"}
    facts = {
        "password": False,
        "challenge": False,
        "busy": False,
        "incomplete": False,
        "selectors": [{"account_id": "111", "name_sha256": "a" * 64}],
        "billing": {"account_id": "111", "name_sha256": "a" * 64, "currency": "USD"},
    }
    probe = AsyncMock(return_value=[facts])
    monkeypatch.setattr(polling, "observe_existing_pages", probe)
    with Spool(tmp_path / "private", agent) as spool:
        await polling.run_cycle(adapter, device, spool, selected_profiles={"p"})
    assert probe.await_count == 1
    reports = [call.args[1] for call in device.send.call_args_list if call.args[0] == "identity"]
    assert [report["identity_state"] for report in reports] == [
        "VALID",
        "IDENTITY_MISMATCH",
        "IDENTITY_MISMATCH",
        "VALID",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["network", "server"])
async def test_flush_stops_after_first_transient_nonheartbeat_failure(tmp_path, failure):
    from orbit_agent.adspower_status import ProbeError
    from orbit_agent.polling import flush
    from orbit_agent.spool import Spool
    from orbit_agent.transport import DeviceRejected

    agent = str(UUID(int=1))
    with Spool(tmp_path / "private", agent) as spool:
        heartbeat = spool.append(
            "heartbeat", {"profiles": [], "observed_at": "2026-11-09T00:00:00Z"}
        )
        spool.ack(heartbeat["local_id"])
        for _ in range(3):
            spool.append(
                "diagnostics",
                {
                    "seq": 1,
                    "observed_at": "2026-11-09T00:00:00Z",
                    "api_status": "READY",
                    "inventory_coverage": "FULL",
                    "error_code": None,
                },
            )
        device = AsyncMock()
        device.send.side_effect = (
            ProbeError("DEVICE_CONNECTION_FAILED")
            if failure == "network"
            else DeviceRejected("DEVICE_REQUEST_REJECTED", 503)
        )
        assert await flush(device, spool) is False
        assert device.send.await_count == 1
        assert len(spool.pending()) == 3


@pytest.mark.asyncio
async def test_flush_total_deadline_retains_uncertain_request(tmp_path):
    import asyncio

    from orbit_agent.polling import flush
    from orbit_agent.spool import Spool

    async def slow_send(*args):
        await asyncio.sleep(1)

    with Spool(tmp_path / "private", str(UUID(int=1))) as spool:
        original = spool.append(
            "heartbeat", {"profiles": [], "observed_at": "2026-11-09T00:00:00Z"}
        )
        device = AsyncMock()
        device.send.side_effect = slow_send
        assert await flush(device, spool, budget_seconds=0.01) is False
        assert spool.pending() == [original]


@pytest.mark.asyncio
async def test_identity_report_cap_rotates_without_fabricating_observations(tmp_path):
    from orbit_agent.adspower_readonly import Discovery
    from orbit_agent.polling import run_cycle
    from orbit_agent.spool import Spool

    agent = str(UUID(int=1))
    bindings = [
        {
            "id": str(UUID(int=index + 10)),
            "revision": 1,
            "profile_external_id": "p",
            "external_account_id": "111",
            "currency": "USD",
        }
        for index in range(250)
    ]
    adapter = AsyncMock()
    adapter.discover.return_value = Discovery("READY", "FULL", (("p", "ACTIVE"),), None)
    device = AsyncMock()
    device.configuration.return_value = {"bindings": bindings}
    device.send.return_value = {"state": "READY"}
    with Spool(tmp_path / "private", agent) as spool:
        for _ in range(3):
            result = await run_cycle(adapter, device, spool, selected_profiles={"p"})
            assert result["identity_report_count"] == 100
            assert result["identity_report_deferred_count"] == 150
    reports = [call.args[1] for call in device.send.call_args_list if call.args[0] == "identity"]
    assert len(reports) == 300
    assert {report["binding_id"] for report in reports} == {binding["id"] for binding in bindings}
    assert {report["identity_state"] for report in reports} == {"UNKNOWN"}


@pytest.mark.asyncio
async def test_cached_profile_keeps_actual_observation_time_not_heartbeat_time(tmp_path):
    from orbit_agent.adspower_readonly import Discovery
    from orbit_agent.polling import run_cycle
    from orbit_agent.spool import Spool

    adapter = AsyncMock()
    adapter.discover.return_value = Discovery(
        "READY", "FULL", (("p", "ACTIVE"),), None, observed_at="2026-11-09T00:00:00Z"
    )
    device = AsyncMock()
    device.configuration.return_value = {"bindings": []}
    device.send.return_value = {"state": "READY"}
    with Spool(tmp_path / "private", str(UUID(int=1))) as spool:
        await run_cycle(adapter, device, spool, selected_profiles=set())
        await run_cycle(adapter, device, spool, selected_profiles=set())
    heartbeats = [
        call.args[1] for call in device.send.call_args_list if call.args[0] == "heartbeat"
    ]
    assert len(heartbeats) == 2
    for heartbeat in heartbeats:
        assert heartbeat["profiles"][0]["observed_at"] == "2026-11-09T00:00:00Z"
        assert heartbeat["observed_at"] != heartbeat["profiles"][0]["observed_at"]
