"""原业务错误与配置扩展合同分开验证；真实HTTP回环另有MySQL/Redis专项。"""

from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from orbit_api.errors import OrbitError
from orbit_api.http_boundary import OrbitApiBoundary, register_errors


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "callback_path", ["/api/v1/auth/callback", "/api/v1/integrations/meta/callback"]
)
async def test_callback_query_is_hidden_before_inner_middleware_and_access_log(callback_path):
    scope = {
        "type": "http",
        "path": callback_path,
        "query_string": b"state=fixture-state&code=fixture-secret-code",
    }
    events = []

    async def app(inner_scope, receive, send):
        assert inner_scope["query_string"] == b""
        assert inner_scope["state"]["orbit_callback_query"].endswith(b"fixture-secret-code")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def send(message):
        assert scope["query_string"] == b""
        events.append(message)

    await OrbitApiBoundary(app)(scope, None, send)
    assert "orbit_callback_query" not in scope["state"]
    assert (b"referrer-policy", b"no-referrer") in events[0]["headers"]


@pytest.mark.asyncio
async def test_oidc_provider_transport_errors_use_product_503_contract():
    app = FastAPI()
    app.add_middleware(OrbitApiBoundary)
    register_errors(app)

    @app.post("/api/v1/auth/authorization-sessions")
    async def unavailable():
        raise OrbitError(502, "OIDC_DISCOVERY_INVALID", "登录提供者发现文档不符合要求")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fixture"
    ) as client:
        result = await client.post("/api/v1/auth/authorization-sessions")
    assert result.status_code == 503
    assert result.json()["code"] == "OIDC_DISCOVERY_INVALID"
    assert result.json()["retryable"] is True


@pytest.mark.parametrize(
    "path,fields",
    [
        ("/api/v1/teams", {"code", "message", "field_errors", "retryable", "request_id"}),
        (
            "/api/v1/system-configurations-extra",
            {"code", "message", "field_errors", "retryable", "request_id"},
        ),
        ("/api/v1/system-configurations", {"code", "message", "request_id"}),
    ],
)
async def test_field_errors_follow_each_exact_contract(path, fields):
    app = FastAPI()
    app.add_middleware(OrbitApiBoundary)
    register_errors(app)

    @app.get(path)
    async def invalid():
        raise OrbitError(422, "FIELD_INVALID", "名称无效", "/name")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fixture"
    ) as client:
        response = await client.get(path, headers={"X-Request-ID": "client-cannot-spoof"})
    assert response.status_code == 422
    value = response.json()
    assert set(value) == fields
    assert str(UUID(value["request_id"])) == value["request_id"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"
    if "field_errors" in fields:
        assert value["field_errors"] == [
            {"path": "/name", "code": "FIELD_INVALID", "message": "名称无效", "constraint": ""}
        ]
        assert value["retryable"] is False
    else:
        assert "/name" in value["message"]


@pytest.mark.parametrize("status", [401, 403, 404])
async def test_native_http_exceptions_use_product_shape_only_inside_orbit(status):
    app = FastAPI()
    app.add_middleware(OrbitApiBoundary)
    register_errors(app)

    @app.get("/api/v1/teams")
    @app.get("/native")
    async def denied():
        raise HTTPException(status, detail="fixture-sensitive-detail")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fixture"
    ) as client:
        business = await client.get("/api/v1/teams")
        native = await client.get("/native")
    assert business.status_code == status
    assert set(business.json()) == {"code", "message", "field_errors", "retryable", "request_id"}
    assert "fixture-sensitive-detail" not in business.text
    assert native.json() == {"detail": "fixture-sensitive-detail"}


async def test_unexpected_errors_are_safe_and_retryable_without_traceback():
    app = FastAPI()
    app.add_middleware(OrbitApiBoundary)
    register_errors(app)

    @app.get("/api/v1/teams")
    async def failed():
        raise RuntimeError("fixture-credential-and-sql-detail")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fixture"
    ) as client:
        response = await client.get("/api/v1/teams")
    assert response.status_code == 503
    assert response.json()["retryable"] is True
    assert response.json()["field_errors"] == []
    assert "fixture-credential-and-sql-detail" not in response.text


@pytest.mark.parametrize("status", [403, 404])
async def test_native_business_denials_keep_original_shape_without_orbit_request_state(status):
    app = FastAPI()
    app.add_middleware(OrbitApiBoundary)
    register_errors(app)

    @app.get("/system/user/999")
    async def denied():
        raise OrbitError(status, "NOT_FOUND", "人员不存在或不可见")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fixture"
    ) as client:
        response = await client.get("/system/user/999")
    assert response.status_code == status
    assert response.json() == {"code": status, "msg": "人员不存在或不可见"}
    assert response.headers["cache-control"] == "no-store"
