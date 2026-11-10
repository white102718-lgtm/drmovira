import pytest


@pytest.mark.asyncio
async def test_exchange_requires_debug_and_matching_subject():
    from orbit_api.meta_connection_contract import MetaApplication
    from orbit_api.meta_oauth_transport import MetaOAuthTransport

    calls = []

    async def request(method, path, params, token):
        calls.append((method, path, params, token))
        if path == "oauth/access_token":
            return {"access_token": "customer-private-token"}
        if path == "debug_token":
            return {
                "data": {
                    "app_id": "123",
                    "user_id": "42",
                    "is_valid": True,
                    "scopes": ["ads_read"],
                    "expires_at": 253402300000,
                    "data_access_expires_at": 253402300000,
                }
            }
        return {"id": "42"}

    adapter = MetaOAuthTransport(
        MetaApplication("123", "private-secret", "v24.0", "456"), request=request
    )
    token, grant = await adapter.exchange("private-code")
    assert token == "customer-private-token" and grant.principal_id == "42"
    assert [c[1] for c in calls] == ["oauth/access_token", "debug_token", "me"]
    assert calls[0][0] == "POST"
    assert "customer-private-token" not in repr(adapter)


@pytest.mark.asyncio
async def test_exchange_refuses_subject_mismatch():
    from orbit_api.meta_connection_contract import MetaApplication
    from orbit_api.meta_oauth_transport import MetaOAuthTransport

    async def request(method, path, params, token):
        if path == "oauth/access_token":
            return {"access_token": "token"}
        if path == "debug_token":
            return {
                "data": {
                    "app_id": "123",
                    "user_id": "42",
                    "is_valid": True,
                    "scopes": ["ads_read"],
                    "expires_at": 253402300000,
                    "data_access_expires_at": 253402300000,
                }
            }
        return {"id": "99"}

    with pytest.raises(ValueError):
        await MetaOAuthTransport(
            MetaApplication("123", "secret", "v24.0", "456"), request=request
        ).exchange("code")


@pytest.mark.asyncio
async def test_bm_principal_must_be_in_selected_business_system_users():
    from orbit_api.meta_connection_contract import MetaApplication
    from orbit_api.meta_oauth_transport import MetaOAuthTransport

    requests = []

    async def request(method, path, params, token):
        requests.append((method, path, params))
        return {"data": [{"id": "42"}]}

    transport = MetaOAuthTransport(
        MetaApplication("123", "secret", "v24.0", "456"), request=request
    )
    assert hasattr(transport, "verify_system_user"), "BM缺少系统用户成员核验"
    await transport.verify_system_user("token", "789", "42")
    assert requests == [("GET", "789/system_users", {"fields": "id", "limit": "200"})]
    with pytest.raises(ValueError):
        await transport.verify_system_user("token", "789", "99")


@pytest.mark.asyncio
async def test_system_user_paging_never_follows_provider_next_url():
    from orbit_api.meta_connection_contract import MetaApplication
    from orbit_api.meta_oauth_transport import MetaOAuthTransport

    calls = []

    async def request(method, path, params, token):
        calls.append(path)
        return {
            "data": [],
            "paging": {"next": "https://evil.test/steal", "cursors": {"after": "opaque"}},
        }

    transport = MetaOAuthTransport(
        MetaApplication("123", "secret", "v24.0", "456"), request=request
    )
    assert hasattr(transport, "verify_system_user")
    with pytest.raises(ValueError):
        await transport.verify_system_user("token", "789", "42")
    assert calls and set(calls) == {"789/system_users"}
