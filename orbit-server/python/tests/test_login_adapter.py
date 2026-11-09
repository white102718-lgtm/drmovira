"""登录适配仅检验传输边界；真实框架认证/数据库另作集成验证。"""

from urllib.parse import parse_qs

import httpx
import pytest

from orbit_api.login_adapter import LoginJsonAdapter


@pytest.mark.asyncio
async def test_json_login_preserves_unicode_and_special_characters_without_body_cache():
    captured = {}

    async def app(scope, receive, send):
        captured["headers"] = dict(scope["headers"])
        captured["body"] = (await receive())["body"]
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=LoginJsonAdapter(app)), base_url="http://fixture"
    ) as client:
        response = await client.post(
            "/login", json={"username": "用户", "password": "a+&%=特殊", "code": "", "uuid": "id"}
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert parse_qs(captured["body"].decode(), keep_blank_values=True) == {
        "username": ["用户"],
        "password": ["a+&%=特殊"],
        "code": [""],
        "uuid": ["id"],
    }
    assert captured["headers"][b"content-type"] == b"application/x-www-form-urlencoded"
    assert int(captured["headers"][b"content-length"]) == len(captured["body"])


@pytest.mark.parametrize(
    "body",
    [
        '{"username":"one","username":"two","password":"secret"}',
        '{"username":"one","password":"secret","tenant_id":"forged"}',
        '{"username":1,"password":"secret"}',
        '{"username":"one","password":null}',
        '{"username":"one"}',
        "null",
        "[]",
        "{} {}",
        "{",
    ],
)
async def test_invalid_json_never_reaches_authentication_or_leaks_password(body):
    async def forbidden(scope, receive, send):
        pytest.fail("非法请求不应进入认证")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=LoginJsonAdapter(forbidden)), base_url="http://fixture"
    ) as client:
        response = await client.post(
            "/login", content=body, headers={"content-type": "application/json"}
        )
    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert "secret" not in response.text


async def test_oversized_login_is_rejected_before_authentication():
    async def forbidden(scope, receive, send):
        pytest.fail("超限请求不应进入认证")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=LoginJsonAdapter(forbidden)), base_url="http://fixture"
    ) as client:
        response = await client.post(
            "/login", content=" " * 16_385, headers={"content-type": "application/json"}
        )
    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 401, 429])
@pytest.mark.parametrize("json_login", [True, False])
async def test_native_and_json_login_never_cache_success_or_errors(status, json_login):
    async def app(scope, receive, send):
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"Cache-Control", b"public, max-age=300"),
                    (b"pragma", b"cache"),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"{}"})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=LoginJsonAdapter(app)), base_url="http://fixture"
    ) as client:
        arguments = (
            {"json": {"username": "fixture", "password": "fixture-only"}}
            if json_login
            else {"data": {"username": "fixture", "password": "fixture-only"}}
        )
        response = await client.post("/login", **arguments)
    assert response.status_code == status and response.content == b"{}"
    assert response.headers.get_list("cache-control") == ["no-store"]
    assert response.headers.get_list("pragma") == ["no-cache"]
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [("GET", "/login"), ("POST", "/unrelated")])
async def test_other_responses_preserve_their_cache_policy(method, path):
    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"cache-control", b"public, max-age=300")],
            }
        )
        await send({"type": "http.response.body", "body": b"{}"})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=LoginJsonAdapter(app)), base_url="http://fixture"
    ) as client:
        response = await client.request(method, path)
    assert response.headers["cache-control"] == "public, max-age=300"
