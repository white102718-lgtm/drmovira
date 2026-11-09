"""主动探测必须使用新的观察，并且不破坏原心跳交付。"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from orbit_agent.adspower_readonly import Discovery
from orbit_agent.adspower_status import ProbeError
from orbit_agent.discovery_cache import BackgroundDiscovery
from orbit_agent.polling import run_cycle
from orbit_agent.spool import Spool
from orbit_agent.transport import DeviceClient

AGENT = str(UUID(int=1))
REQUEST = str(UUID(int=2))


def coordinator():
    from orbit_agent import polling

    assert hasattr(polling, "ProbeRequests"), "active probe coordinator is not connected"
    return polling.ProbeRequests()


def request():
    clock = datetime.now(UTC)
    return {
        "agent_id": AGENT,
        "request": {
            "id": REQUEST,
            "created_at": (clock - timedelta(seconds=1)).isoformat(),
            "expires_at": (clock + timedelta(seconds=119)).isoformat(),
        },
    }


def device():
    obj = AsyncMock()
    obj.configuration.return_value = {"bindings": []}
    obj.send.return_value = {"state": "READY"}
    obj.probe_requests.return_value = request()
    obj.complete_probe.return_value = {"state": "COMPLETED"}
    return obj


@pytest.mark.asyncio
async def test_new_request_cannot_use_preexisting_cached_observation(tmp_path):
    probes = coordinator()
    source = AsyncMock()
    source.discover.side_effect = lambda: Discovery("READY", "FULL", (), None)
    cache = BackgroundDiscovery(source, refresh_interval=100)
    dev = device()
    try:
        await cache.discover()
        with Spool(tmp_path / "private", AGENT) as spool:
            await run_cycle(cache, dev, spool, selected_profiles=set(), probes=probes)
            assert dev.complete_probe.await_count == 0
            await asyncio.sleep(0)
            await run_cycle(cache, dev, spool, selected_profiles=set(), probes=probes)
            assert dev.complete_probe.await_count == 1
            payload = dev.complete_probe.call_args.args[1]
            assert payload["seq"] == 2
            assert payload["boot_id"] == spool.boot_id
            assert payload["agent_id"] == AGENT
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_forced_discovery_never_overlaps_or_blocks_heartbeats(tmp_path):
    probes = coordinator()
    started, finish = asyncio.Event(), asyncio.Event()
    calls = 0

    async def discovery():
        nonlocal calls
        calls += 1
        started.set()
        await finish.wait()
        return Discovery("READY", "FULL", (), None)

    source = AsyncMock()
    source.discover.side_effect = discovery
    cache = BackgroundDiscovery(source, initial_wait=0.001)
    dev = device()
    try:
        with Spool(tmp_path / "private", AGENT) as spool:
            for _ in range(3):
                result = await asyncio.wait_for(
                    run_cycle(cache, dev, spool, selected_profiles=set(), probes=probes), 0.15
                )
                assert result["delivery"] == "ACKNOWLEDGED"
            assert calls == 1 and not finish.is_set()
            assert dev.complete_probe.await_count == 0
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_probe_fetch_and_configuration_failure_do_not_suppress_heartbeat(tmp_path):
    probes = coordinator()
    dev = device()
    dev.configuration.side_effect = ProbeError("DEVICE_CONNECTION_FAILED")
    dev.probe_requests.side_effect = ProbeError("DEVICE_CONNECTION_FAILED")
    adapter = AsyncMock()
    adapter.discover.return_value = Discovery("READY", "FULL", (), None)
    with Spool(tmp_path / "private", AGENT) as spool:
        result = await run_cycle(adapter, dev, spool, selected_profiles=set(), probes=probes)
        assert result["delivery"] == "ACKNOWLEDGED"
        assert [call.args[0] for call in dev.send.call_args_list] == ["heartbeat", "diagnostics"]
        assert dev.complete_probe.await_count == 0


@pytest.mark.asyncio
async def test_lost_completion_ack_retries_original_before_next_heartbeat(tmp_path):
    probes = coordinator()
    source = AsyncMock()
    source.discover.side_effect = lambda: Discovery("READY", "FULL", (), None)
    cache = BackgroundDiscovery(source, initial_wait=0.01)
    dev = device()
    dev.complete_probe.side_effect = [
        ProbeError("DEVICE_CONNECTION_FAILED"),
        {"state": "COMPLETED"},
    ]
    try:
        with Spool(tmp_path / "private", AGENT) as spool:
            await run_cycle(cache, dev, spool, selected_profiles=set(), probes=probes)
            assert dev.complete_probe.await_count == 1
            initial = dev.complete_probe.call_args.args
            dev.probe_requests.return_value = {"agent_id": AGENT, "request": None}
            await run_cycle(cache, dev, spool, selected_profiles=set(), probes=probes)
            assert dev.complete_probe.call_args.args == initial
            assert initial[1]["seq"] == 1
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_expired_request_does_not_trigger_discovery_or_completion(tmp_path):
    probes = coordinator()
    dev = device()
    dev.probe_requests.return_value["request"]["expires_at"] = (
        datetime.now(UTC) - timedelta(seconds=1)
    ).isoformat()
    adapter = AsyncMock()
    adapter.discover.return_value = Discovery("READY", "FULL", (), None)
    with Spool(tmp_path / "private", AGENT) as spool:
        await run_cycle(adapter, dev, spool, selected_profiles=set(), probes=probes)
    assert not adapter.request_refresh.called and not dev.complete_probe.called


@pytest.mark.asyncio
async def test_diagnostics_not_acknowledged_cannot_complete_probe(tmp_path):
    probes = coordinator()
    source = AsyncMock()
    source.discover.side_effect = lambda: Discovery("READY", "FULL", (), None)
    cache = BackgroundDiscovery(source, initial_wait=0.01)
    dev = device()
    dev.send.side_effect = [{"state": "READY"}, ProbeError("DEVICE_CONNECTION_FAILED")]
    try:
        with Spool(tmp_path / "private", AGENT) as spool:
            result = await run_cycle(cache, dev, spool, selected_profiles=set(), probes=probes)
            assert result["delivery"] == "PENDING"
            assert not dev.complete_probe.called
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_probe_transport_uses_fixed_paths_and_rejects_other_request_ack():
    assert hasattr(DeviceClient, "probe_requests"), "probe transport is not implemented"
    client = object.__new__(DeviceClient)
    client.agent_id = AGENT
    client.request = AsyncMock(return_value=request())
    assert (await client.probe_requests())["request"]["id"] == REQUEST
    assert client.request.call_args.args == ("GET", "/api/v1/agent-api/probe-requests")
    value = {
        "agent_id": AGENT,
        "boot_id": str(UUID(int=3)),
        "seq": 1,
        "observed_at": datetime.now(UTC).isoformat(),
    }
    client.request.return_value = {
        "id": str(UUID(int=99)),
        "revision": 1,
        "state": "COMPLETED",
        "request_id": str(UUID(int=4)),
    }
    with pytest.raises(ProbeError):
        await client.complete_probe(REQUEST, value)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["diagnostics", "identity"])
async def test_rejected_report_is_not_mistaken_for_fully_acknowledged_probe(tmp_path, kind):
    from orbit_agent.transport import DeviceRejected

    probes = coordinator()
    source = AsyncMock()
    source.discover.side_effect = lambda: Discovery("READY", "FULL", (("p", "ACTIVE"),), None)
    cache = BackgroundDiscovery(source, initial_wait=0.01)
    dev = device()
    if kind == "identity":
        dev.configuration.return_value = {
            "bindings": [
                {
                    "id": str(UUID(int=4)),
                    "revision": 1,
                    "profile_external_id": "p",
                    "external_account_id": "123",
                    "currency": "USD",
                }
            ]
        }

    async def send(event_kind, payload):
        if event_kind == kind:
            raise DeviceRejected("DEVICE_REQUEST_REJECTED", 409)
        return {"state": "READY"}

    dev.send.side_effect = send
    try:
        with Spool(tmp_path / "private", AGENT) as spool:
            await run_cycle(cache, dev, spool, selected_profiles={"p"}, probes=probes)
            assert not dev.complete_probe.called
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_initial_suspect_heartbeat_cannot_complete_identity_probe(tmp_path):
    probes = coordinator()
    source = AsyncMock()
    source.discover.side_effect = lambda: Discovery("READY", "FULL", (), None)
    cache = BackgroundDiscovery(source, initial_wait=0.01)
    dev = device()
    dev.send.return_value = {"state": "SUSPECT"}
    try:
        with Spool(tmp_path / "private", AGENT) as spool:
            await run_cycle(cache, dev, spool, selected_profiles=set(), probes=probes)
            assert not dev.complete_probe.called
    finally:
        await cache.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"agent_id": str(UUID(int=8))},
        {
            "request": {
                "id": REQUEST,
                "created_at": "2026-11-09T00:00:00Z",
                "expires_at": "2026-11-09T00:05:00Z",
            }
        },
        {"script": "forbidden"},
    ],
)
async def test_probe_transport_rejects_other_device_unknown_fields_and_long_ttl(change):
    client = object.__new__(DeviceClient)
    client.agent_id = AGENT
    client.request = AsyncMock(return_value=request() | change)
    with pytest.raises(ProbeError):
        await client.probe_requests()


@pytest.mark.asyncio
async def test_request_fetch_timeout_keeps_heartbeat_and_diagnostics_deliverable(tmp_path):
    probes = coordinator()
    probes.budget_seconds = 0.001
    dev = device()

    async def unreachable():
        await asyncio.Event().wait()

    dev.probe_requests.side_effect = unreachable
    source = AsyncMock()
    source.discover.return_value = Discovery("READY", "FULL", (), None)
    with Spool(tmp_path / "private", AGENT) as spool:
        result = await asyncio.wait_for(
            run_cycle(source, dev, spool, selected_profiles=set(), probes=probes), 0.2
        )
    assert result["delivery"] == "ACKNOWLEDGED"
    assert [call.args[0] for call in dev.send.call_args_list] == ["heartbeat", "diagnostics"]


@pytest.mark.asyncio
async def test_request_during_inflight_discovery_requires_the_following_fresh_generation(tmp_path):
    probes = coordinator()
    release = asyncio.Event()
    observations = []

    async def discover():
        snapshot = Discovery("READY", "FULL", (), None)
        observations.append(snapshot)
        if len(observations) == 1:
            await release.wait()
        return snapshot

    source = AsyncMock()
    source.discover.side_effect = discover
    cache = BackgroundDiscovery(source, initial_wait=0.001, refresh_interval=100)
    dev = device()
    try:
        await cache.discover()
        assert len(observations) == 1
        with Spool(tmp_path / "private", AGENT) as spool:
            await run_cycle(cache, dev, spool, selected_profiles=set(), probes=probes)
            release.set()
            for _ in range(20):
                await asyncio.sleep(0)
                if cache.completed_generation == 2:
                    break
            assert cache.completed_generation == 2
            await run_cycle(cache, dev, spool, selected_profiles=set(), probes=probes)
            payload = dev.complete_probe.call_args.args[1]
            assert payload["observed_at"] == observations[1].observed_at
            assert payload["observed_at"] != observations[0].observed_at
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_old_server_without_probe_endpoint_still_monitors(tmp_path):
    from orbit_agent.transport import DeviceRejected

    probes = coordinator()
    dev = device()
    dev.probe_requests.side_effect = DeviceRejected("DEVICE_REQUEST_REJECTED", 404)
    source = AsyncMock()
    source.discover.return_value = Discovery("READY", "FULL", (), None)
    with Spool(tmp_path / "private", AGENT) as spool:
        result = await run_cycle(source, dev, spool, selected_profiles=set(), probes=probes)
    assert result["delivery"] == "ACKNOWLEDGED"
    assert not dev.complete_probe.called


def many_bindings(count=101):
    return [
        {
            "id": str(UUID(int=100 + i)),
            "revision": 1,
            "account_id": str(UUID(int=1000 + i)),
            "profile_external_id": "p",
            "external_account_id": str(10000 + i),
            "currency": "USD",
        }
        for i in range(count)
    ]


@pytest.mark.asyncio
async def test_probe_accumulates_101_current_bindings_across_two_acknowledged_cycles(tmp_path):
    probes = coordinator()
    source = AsyncMock()
    source.discover.side_effect = lambda: Discovery("READY", "FULL", (("p", "ACTIVE"),), None)
    cache = BackgroundDiscovery(source, initial_wait=0.01)
    dev = device()
    dev.configuration.return_value = {"bindings": many_bindings()}
    try:
        with Spool(tmp_path / "private", AGENT) as spool:
            first = await run_cycle(cache, dev, spool, selected_profiles={"p"}, probes=probes)
            assert first["identity_report_count"] == 100 and not dev.complete_probe.called
            await run_cycle(cache, dev, spool, selected_profiles={"p"}, probes=probes)
            assert dev.complete_probe.await_count == 1
            assert dev.complete_probe.call_args.args[1]["seq"] == 2
    finally:
        await cache.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["revision", "account", "request", "configuration", "partial_failure"]
)
async def test_probe_does_not_reuse_credits_after_context_change_or_failed_batch(tmp_path, change):
    from orbit_agent.transport import DeviceRejected

    probes = coordinator()
    source = AsyncMock()
    source.discover.side_effect = lambda: Discovery("READY", "FULL", (("p", "ACTIVE"),), None)
    cache = BackgroundDiscovery(source, initial_wait=0.01)
    dev = device()
    bindings = many_bindings()
    dev.configuration.return_value = {"bindings": bindings}
    try:
        with Spool(tmp_path / "private", AGENT) as spool:
            await run_cycle(cache, dev, spool, selected_profiles={"p"}, probes=probes)
            # Round two visits 100,0..98. Binding 99 has only a round-one credit.
            if change == "revision":
                bindings[99] = bindings[99] | {"revision": 2}
            elif change == "account":
                bindings[99] = bindings[99] | {"external_account_id": "999999", "currency": "EUR"}
            elif change == "request":
                dev.probe_requests.return_value = request()
                dev.probe_requests.return_value["request"]["id"] = str(UUID(int=98))
                source.discover.side_effect = lambda: Discovery(
                    "READY", "FULL", (("p", "ACTIVE"),), None
                )
            elif change == "configuration":
                dev.configuration.side_effect = ProbeError("DEVICE_CONNECTION_FAILED")
            else:

                async def reject_one(kind, payload):
                    if kind == "identity" and payload["binding_id"] == bindings[100]["id"]:
                        raise DeviceRejected("DEVICE_REQUEST_REJECTED", 409)
                    return {"state": "READY"}

                dev.send.side_effect = reject_one
            await run_cycle(cache, dev, spool, selected_profiles={"p"}, probes=probes)
            assert not dev.complete_probe.called
            if change in {"revision", "account"}:
                await run_cycle(cache, dev, spool, selected_profiles={"p"}, probes=probes)
                assert dev.complete_probe.await_count == 1
            elif change in {"configuration", "partial_failure"}:
                dev.configuration.side_effect = None
                dev.send.side_effect = None
                await run_cycle(cache, dev, spool, selected_profiles={"p"}, probes=probes)
                # Failed round cleared earlier coverage; this is only the first new batch.
                assert not dev.complete_probe.called
                await run_cycle(cache, dev, spool, selected_profiles={"p"}, probes=probes)
                assert dev.complete_probe.await_count == 1
            else:
                await asyncio.sleep(0)
                await run_cycle(cache, dev, spool, selected_profiles={"p"}, probes=probes)
                assert not dev.complete_probe.called
                await run_cycle(cache, dev, spool, selected_profiles={"p"}, probes=probes)
                assert dev.complete_probe.await_count == 1
    finally:
        await cache.close()
