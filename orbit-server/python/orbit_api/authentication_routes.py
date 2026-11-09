"""产品OIDC与Cookie接口；不接受tenant/actor身份注入，不使用默认正文审计缓存。"""

import hashlib
from typing import Annotated
from urllib.parse import parse_qsl, quote

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse

from orbit_api.authentication_service import AuthenticationService
from orbit_api.browser_session_store import BrowserSessionStore
from orbit_api.configuration_routes import credential_cipher
from orbit_api.cookie_auth import BINDING_COOKIE, public_origin, read_cookie, require_same_origin
from orbit_api.cookie_identity import bind_verified_cookie
from orbit_api.errors import OrbitError
from orbit_api.oidc_contract import (
    ABSOLUTE_SECONDS,
    SESSION_COOKIE,
    opaque_token,
    parse_authorization_start,
    parse_invitation_authorization_start,
)
from orbit_api.session_read import session_payload

router = APIRouter(prefix="/api/v1/auth", tags=["ORBIT身份认证"])


def authentication_service():
    from config.database import DataSourceRegistry

    return AuthenticationService(
        lambda: DataSourceRegistry.session(log_sql=False), credential_cipher()
    )


ServiceDependency = Annotated[AuthenticationService, Depends(authentication_service)]


def _boundary(request):
    if request.query_params:
        raise OrbitError(400, "UNKNOWN_FIELD", "此接口不接受查询参数")
    if "x-target-tenant" in request.headers:
        raise OrbitError(403, "PERMISSION_DENIED", "登录会话不能切换指定租户")


async def _limit(request, operation, maximum):
    peer = request.client.host if request.client else "unknown"
    key = "orbit:auth:rate:" + hashlib.sha256((operation + ":" + peer).encode()).hexdigest()
    count = await request.app.state.redis.eval(
        "local n=redis.call('INCR',KEYS[1]); "
        "if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n",
        1,
        key,
    )
    if count > maximum:
        raise OrbitError(429, "AUTH_RATE_LIMITED", "登录请求过于频繁，请稍后重试")


def _set_cookie(response, name, value):
    response.set_cookie(
        name, value, max_age=ABSOLUTE_SECONDS, path="/", secure=True, httponly=True, samesite="lax"
    )


@router.get("/providers")
async def providers(request: Request, service: ServiceDependency):
    _boundary(request)
    await _limit(request, "providers", 60)
    return {"items": await service.providers(public_origin())}


async def _start(request, service, provider_id=None, *, invitation=False):
    _boundary(request)
    require_same_origin(request)
    await _limit(request, "start", 20)
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 4096:
            raise OrbitError(413, "BODY_TOO_LARGE", "登录请求正文超过上限")
        raw.extend(chunk)
    value = (
        parse_invitation_authorization_start(bytes(raw))
        if invitation
        else parse_authorization_start(bytes(raw))
    )
    try:
        binding = read_cookie(request, BINDING_COOKIE)
    except OrbitError:
        # 没有主机绑定时发放新随机量；不从session/localStorage或可控请求字段推导。
        binding = opaque_token()
    if invitation:
        result = await service.start_invitation(
            public_origin(),
            binding,
            value.invitation_token,
            value.return_to,
            request.state.orbit_request_id,
        )
    else:
        result = await service.start(
            public_origin(),
            binding,
            value.return_to,
            request.state.orbit_request_id,
            provider_id=provider_id,
        )
    response = JSONResponse(result)
    _set_cookie(response, BINDING_COOKIE, binding)
    return response


@router.post("/authorization-sessions")
async def start(request: Request, service: ServiceDependency):
    return await _start(request, service)


@router.post("/providers/{provider_id}/authorization-sessions")
async def start_with_provider(provider_id: str, request: Request, service: ServiceDependency):
    from orbit_api.configuration_store import _uuid

    return await _start(request, service, _uuid(provider_id))


@router.post("/invitation-authorization-sessions")
async def start_invitation(request: Request, service: ServiceDependency):
    return await _start(request, service, invitation=True)


@router.get("/callback")
async def callback(request: Request, service: ServiceDependency):
    if "x-target-tenant" in request.headers:
        raise OrbitError(403, "PERMISSION_DENIED", "登录回调不能指定租户")
    await _limit(request, "callback", 60)
    try:
        raw = request.scope["state"].get("orbit_callback_query", b"")
        if len(raw) > 32768:
            raise ValueError
        values = parse_qsl(
            raw.decode("utf-8"),
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=2,
        )
        parameters = dict(values)
        if len(values) != 2 or set(parameters) != {"state", "code"}:
            raise ValueError
        if not all(1 <= len(value) <= 2048 for value in parameters.values()):
            raise ValueError
    except (ValueError, UnicodeError):
        raise OrbitError(400, "OIDC_CALLBACK_INVALID", "登录回调参数缺失或无效") from None
    binding = read_cookie(request, BINDING_COOKIE)
    cookie, result, return_to = await service.callback(
        parameters["state"], parameters["code"], binding, request.state.orbit_request_id
    )
    response = JSONResponse(result, headers={"X-ORBIT-Return-To": quote(return_to, safe="")})
    _set_cookie(response, SESSION_COOKIE, cookie)
    _set_cookie(response, BINDING_COOKIE, binding)
    return response


@router.get("/session")
async def session_read(request: Request, service: ServiceDependency):
    _boundary(request)
    cookie, binding = read_cookie(request, SESSION_COOKIE), read_cookie(request, BINDING_COOKIE)
    async with service.sessions() as session, session.begin():
        identity = await BrowserSessionStore(service.cipher).resolve(session, cookie, binding)
        bind_verified_cookie(identity)
        return await session_payload(session, identity)


@router.delete("/session")
async def sign_out(request: Request, service: ServiceDependency):
    _boundary(request)
    require_same_origin(request)
    # 退出仍要求凭据归属和CSRF；不用先拒绝REVOKED，才能重放已提交的退出回执。
    cookie, binding = read_cookie(request, SESSION_COOKIE), read_cookie(request, BINDING_COOKIE)
    csrf, keys = request.headers.getlist("x-csrf-token"), request.headers.getlist("idempotency-key")
    if len(csrf) != 1:
        raise OrbitError(403, "CSRF_INVALID", "退出需要唯一的会话校验值")
    if len(keys) != 1:
        raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "退出需要唯一的幂等键")
    async for chunk in request.stream():
        if chunk:
            raise OrbitError(400, "INVALID_STRUCTURE", "退出接口不接受正文")
    async with service.sessions() as session, session.begin():
        result = await BrowserSessionStore(service.cipher).logout(
            session, cookie, binding, csrf[0], keys[0], request.state.orbit_request_id
        )
    response = JSONResponse(result)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return response
