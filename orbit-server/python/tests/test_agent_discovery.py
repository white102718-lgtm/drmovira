import httpx
import pytest


@pytest.mark.asyncio
async def test_paid_inventory_failure_is_active_only_and_never_exports_private_fields():
    from orbit_agent.adspower_readonly import ReadonlyAdsPower

    async def no_wait(_):
        pass

    def handler(request):
        if request.url.path == "/status":
            return httpx.Response(200, json={"code": 0})
        if request.url.path == "/api/v1/browser/local-active":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "list": [
                            {
                                "user_id": "abc",
                                "ws": {
                                    "puppeteer": "ws://127.0.0.1:53000/devtools/browser/private"
                                },
                                "password": "never-export",
                            }
                        ]
                    },
                },
            )
        assert request.url.path == "/api/v1/user/list"
        return httpx.Response(200, json={"code": -1, "msg": "private paid subscriptions"})

    adapter = ReadonlyAdsPower(transport=httpx.MockTransport(handler), sleep=no_wait)
    snapshot = await adapter.discover()
    assert snapshot.coverage == "ACTIVE_ONLY" and snapshot.profiles == (("abc", "ACTIVE"),)
    assert "private" not in repr(snapshot) and "never-export" not in repr(snapshot)
    assert snapshot.error_code == "ADSPOWER_SUBSCRIPTION_REQUIRED"


@pytest.mark.asyncio
async def test_full_inventory_is_not_all_active():
    from orbit_agent.adspower_readonly import ReadonlyAdsPower

    async def no_wait(_):
        pass

    def handler(request):
        if request.url.path == "/status":
            return httpx.Response(200, json={"code": 0})
        if request.url.path.endswith("local-active"):
            return httpx.Response(200, json={"code": 0, "data": {"list": []}})
        return httpx.Response(
            200,
            json={"code": 0, "data": {"list": [{"user_id": "abc"}], "page": 1, "page_size": 100}},
        )

    value = await ReadonlyAdsPower(transport=httpx.MockTransport(handler), sleep=no_wait).discover()
    assert value.coverage == "FULL" and value.profiles == (("abc", "INACTIVE"),)


@pytest.mark.parametrize(
    "value",
    [
        "ws://evil.example:123/devtools/browser/id",
        "ws://127.0.0.1:123/devtools/browser/id?token=x",
        "ws://user:password@127.0.0.1:123/devtools/browser/id",
    ],
)
def test_cdp_address_not_trusted_outside_literal_loopback(value):
    from orbit_agent.adspower_readonly import cdp_endpoint
    from orbit_agent.adspower_status import ProbeError

    with pytest.raises(ProbeError):
        cdp_endpoint(value)


@pytest.mark.asyncio
async def test_bounded_response_and_redirect_do_not_follow_or_echo():
    from orbit_agent.adspower_readonly import ReadonlyAdsPower

    async def no_wait(_):
        pass

    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://example.com/private"})

    result = await ReadonlyAdsPower(
        transport=httpx.MockTransport(handler), sleep=no_wait
    ).discover()
    assert result.api_status == "UNREACHABLE" and result.coverage == "UNAVAILABLE"
    assert len(calls) == 1 and "private" not in repr(result)


@pytest.mark.asyncio
async def test_api_key_required_body_is_authentication_failure_not_generic_discovery_failure():
    from orbit_agent.adspower_readonly import ReadonlyAdsPower
    from orbit_agent.adspower_status import ProbeError

    def handler(request):
        return httpx.Response(200, json={"code": -1, "msg": "Require api-key"})

    adapter = ReadonlyAdsPower(transport=httpx.MockTransport(handler))
    with pytest.raises(ProbeError) as failure:
        await adapter.get("/api/v1/browser/local-active")
    assert failure.value.code == "ADSPOWER_AUTH_FAILED"


@pytest.mark.asyncio
async def test_profile_authentication_failure_survives_discovery_summary():
    from orbit_agent.adspower_readonly import ReadonlyAdsPower

    async def no_wait(_):
        pass

    def handler(request):
        return httpx.Response(
            200,
            json={"code": 0}
            if request.url.path == "/status"
            else {"code": -1, "msg": "Require api-key"},
        )

    snapshot = await ReadonlyAdsPower(
        transport=httpx.MockTransport(handler), sleep=no_wait
    ).discover()
    assert snapshot.coverage == "UNAVAILABLE"
    assert snapshot.error_code == "ADSPOWER_AUTH_FAILED"
