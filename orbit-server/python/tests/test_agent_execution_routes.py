"""真实ASGI边界：设备专用租约入口，未装可信来源不能领取。"""

from contextlib import asynccontextmanager

import httpx
import pytest

from orbit_api import agent_monitor_routes as module
from orbit_api.agent_monitor_transport import DevicePeer


@pytest.mark.parametrize(
    "path", ["/leases/next", "/leases/00000000-0000-0000-0000-000000000001/command"]
)
async def test_execution_routes_require_actual_tls_peer(path):
    app = module.create_device_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://localhost"
    ) as client:
        response = await client.get("/api/v1/agent-api" + path, headers={"x-client-cert": "forged"})
    assert response.status_code == 401


async def test_no_dispatch_authority_is_not_successful_empty_lease(monkeypatch):
    @asynccontextmanager
    async def session(_):
        yield object()

    monkeypatch.setattr(module, "device_session", session)
    app = module.create_device_app()

    async def trusted(scope, receive, send):
        scope["orbit.device_peer"] = DevicePeer(b"fixture")
        await app(scope, receive, send)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=trusted), base_url="https://localhost"
    ) as client:
        response = await client.get("/api/v1/agent-api/leases/next")
        bad = await client.get("/api/v1/agent-api/leases/next?agent_id=forged")
    assert response.status_code == 503
    assert response.json()["code"] == "EXECUTION_AUTHORITY_UNAVAILABLE"
    assert bad.status_code == 400
