"""ORBIT接口请求关联与安全错误；不改变若依原API的兼容响应。"""

from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from orbit_api.errors import OrbitError


def error_body(path, request_id, status, code, message, pointer=None):
    """配置扩展保留三字段合同；产品原业务错误遵守五字段合同，均不含原始异常。"""
    body = {"code": code, "message": message, "request_id": request_id}
    if not (
        path == "/api/v1/system-configurations" or path.startswith("/api/v1/system-configurations/")
    ):
        body["retryable"] = status in {408, 429, 500, 502, 503, 504}
        body["field_errors"] = (
            [
                {
                    "path": pointer if len(pointer) <= 255 else "/",
                    "code": code,
                    "message": message,
                    "constraint": "",
                }
            ]
            if pointer
            else []
        )
    elif pointer:
        body["message"] += f"（字段：{pointer}）"
    return body


class OrbitApiBoundary:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["orbit_request_id"] = request_id
        callback = scope.get("path") in {
            "/api/v1/auth/callback",
            "/api/v1/integrations/meta/callback",
        }
        if callback:
            # 在原中间件及访问日志看到请求前移走授权码；仅回调处理器读取请求内存。
            scope["state"]["orbit_callback_query"] = scope.get("query_string", b"")
            scope["query_string"] = b""
        started = False

        async def secured(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() not in {b"x-request-id", b"cache-control", b"pragma"}
                ]
                message["headers"] = headers + [
                    (b"x-request-id", request_id.encode()),
                    (b"cache-control", b"no-store"),
                    (b"pragma", b"no-cache"),
                ]
                if callback or scope.get("path", "").startswith("/api/v1/auth/"):
                    message["headers"].append((b"referrer-policy", b"no-referrer"))
            await send(message)

        try:
            await self.app(scope, receive, secured)
        except Exception:
            if started:
                raise
            await JSONResponse(
                error_body(
                    scope["path"], request_id, 503, "SERVICE_UNAVAILABLE", "业务服务暂不可用"
                ),
                503,
            )(scope, receive, secured)
        finally:
            if callback:
                scope["state"].pop("orbit_callback_query", None)


def register_errors(app: FastAPI) -> None:
    from exceptions.exception import AuthException
    from starlette.exceptions import HTTPException

    original_auth = app.exception_handlers.get(AuthException)
    original_http = app.exception_handlers.get(HTTPException)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        if request.url.path.startswith("/api/v1/"):
            code, message = {
                401: ("SESSION_REQUIRED", "请重新登录"),
                403: ("PERMISSION_DENIED", "当前身份无此权限"),
                404: ("NOT_FOUND", "资源不存在或不可见"),
            }.get(error.status_code, ("INVALID_REQUEST", "请求无效"))
            return JSONResponse(
                error_body(
                    request.url.path,
                    request.state.orbit_request_id,
                    error.status_code,
                    code,
                    message,
                ),
                error.status_code,
            )
        return await original_http(request, error)

    @app.exception_handler(OrbitError)
    async def orbit_error(request: Request, error: OrbitError):
        if not request.url.path.startswith("/api/v1/"):
            # 原菜单没有ORBIT请求ID中间件，仍返回原code/msg形状，避免拒绝越权时再抛500。
            return JSONResponse(
                {"code": error.status, "msg": error.message},
                error.status,
                headers={"Cache-Control": "no-store"},
            )
        status = (
            503
            if request.url.path.startswith("/api/v1/auth/") and error.status == 502
            else error.status
        )
        return JSONResponse(
            error_body(
                request.url.path,
                request.state.orbit_request_id,
                status,
                error.code,
                error.message,
                error.pointer,
            ),
            status,
        )

    @app.exception_handler(AuthException)
    async def authentication_error(request: Request, error: AuthException):
        if request.url.path.startswith("/api/v1/"):
            return JSONResponse(
                error_body(
                    request.url.path,
                    request.state.orbit_request_id,
                    401,
                    "SESSION_REQUIRED",
                    "请重新登录",
                ),
                401,
            )
        return await original_auth(request, error)
