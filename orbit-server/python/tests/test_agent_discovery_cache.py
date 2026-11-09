import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_slow_full_inventory_does_not_block_heartbeats_and_eventually_becomes_full():
    from orbit_agent.adspower_readonly import Discovery
    from orbit_agent.discovery_cache import BackgroundDiscovery

    finish = asyncio.Event()
    snapshot = Discovery("READY", "FULL", (("fake-profile", "ACTIVE"),), None)

    async def source_discovery():
        await finish.wait()
        return snapshot

    source = AsyncMock()
    source.discover.side_effect = source_discovery
    cache = BackgroundDiscovery(source, initial_wait=0.01)
    try:
        first = await asyncio.wait_for(cache.discover(), timeout=0.1)
        assert first.coverage == "UNAVAILABLE" and first.profiles == ()
        second = await asyncio.wait_for(cache.discover(), timeout=0.1)
        assert second.api_status == "UNKNOWN"
        assert source.discover.await_count == 1
        finish.set()
        await asyncio.sleep(0)
        full = await cache.discover()
        assert full is snapshot and full.coverage == "FULL"
        assert (await cache.discover()).observed_at == snapshot.observed_at
    finally:
        await cache.close()
    assert cache.task.done()


@pytest.mark.asyncio
async def test_stale_snapshot_never_renews_profiles_api_or_inventory_truth():
    from orbit_agent.adspower_readonly import Discovery
    from orbit_agent.discovery_cache import BackgroundDiscovery

    source = AsyncMock()
    source.discover.return_value = replace(
        Discovery("READY", "FULL", (("fake-profile", "ACTIVE"),), None), started_monotonic=0
    )
    cache = BackgroundDiscovery(source, clock=lambda: 76, initial_wait=0.1)
    try:
        snapshot = await cache.discover()
        assert snapshot.profiles == ()
        assert snapshot.api_status == "UNKNOWN" and snapshot.coverage == "UNAVAILABLE"
        assert snapshot.error_code == "PROFILE_DISCOVERY_FAILED"
        assert snapshot.selected_cdp("fake-profile") is None
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_small_inventory_keeps_first_round_full_and_close_cancels_worker():
    from orbit_agent.adspower_readonly import Discovery
    from orbit_agent.discovery_cache import BackgroundDiscovery

    source = AsyncMock()
    source.discover.return_value = Discovery("READY", "FULL", (), None)
    cache = BackgroundDiscovery(source, initial_wait=0.1)
    assert (await cache.discover()).coverage == "FULL"
    await cache.close()
    assert cache.task.done()


@pytest.mark.asyncio
async def test_long_inventory_allows_two_real_spooled_heartbeats_before_inventory_finishes(
    tmp_path,
):
    from uuid import UUID

    from orbit_agent.adspower_readonly import Discovery
    from orbit_agent.discovery_cache import BackgroundDiscovery
    from orbit_agent.polling import run_cycle
    from orbit_agent.spool import Spool

    finish = asyncio.Event()

    async def slow_inventory():
        await finish.wait()
        return Discovery("READY", "FULL", (("p", "ACTIVE"),), None)

    source = AsyncMock()
    source.discover.side_effect = slow_inventory
    cache = BackgroundDiscovery(source, initial_wait=0.001)
    device = AsyncMock()
    device.configuration.return_value = {"bindings": []}
    device.send.return_value = {"state": "READY"}
    try:
        with Spool(tmp_path / "private", str(UUID(int=1))) as spool:
            for _ in range(2):
                result = await asyncio.wait_for(
                    run_cycle(cache, device, spool, selected_profiles=set()), timeout=0.2
                )
                assert result["delivery"] == "ACKNOWLEDGED"
                assert result["inventory_coverage"] == "UNAVAILABLE"
        hearts = [
            call.args[1] for call in device.send.call_args_list if call.args[0] == "heartbeat"
        ]
        assert [heart["seq"] for heart in hearts] == [1, 2]
        assert all(heart["profiles"] == [] for heart in hearts)
        assert source.discover.await_count == 1 and not finish.is_set()
    finally:
        await cache.close()
