"""兼容现有若依Vue3的JSON登录；不修改前端，也不缓存或记录密码正文。"""

import json
from urllib.parse import urlencode

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class LoginJsonAdapter:
    """仅转换POST /login；上游原生Form登录、权限、验证码和限流仍执行。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == "/login"
        ):
            original_send = send

            async def private_login_response(message):
                if message["type"] == "http.response.start":
                    # 原生Form与JSON兼容入口共用保护，成功Token和错误响应均不缓存。
                    message = dict(message)
                    message["headers"] = [
                        (key, value)
                        for key, value in message.get("headers", [])
                        if key.lower() not in {b"cache-control", b"pragma"}
                    ] + [(b"cache-control", b"no-store"), (b"pragma", b"no-cache")]
                await original_send(message)

            send = private_login_response
        headers = dict(scope.get("headers", []))
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/login"
            or headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
            != b"application/json"
        ):
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 16_384:
                await JSONResponse({"code": 413, "msg": "登录请求过大"}, 413)(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        try:

            def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
                result: dict[str, object] = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError
                    result[key] = value
                return result

            data = json.loads(body.decode("utf-8"), object_pairs_hook=unique)
            if not isinstance(data, dict) or set(data) - {"username", "password", "code", "uuid"}:
                raise ValueError
            if not {"username", "password"}.issubset(data):
                raise ValueError
            if any(not isinstance(value, str) for value in data.values()):
                raise ValueError
            encoded = urlencode(data).encode("utf-8")
        except (ValueError, TypeError, UnicodeError):
            await JSONResponse({"code": 400, "msg": "登录请求结构无效"}, 400)(scope, receive, send)
            return
        converted = dict(scope)
        converted["headers"] = [
            (key, value)
            for key, value in scope["headers"]
            if key.lower() not in {b"content-type", b"content-length"}
        ] + [
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"content-length", str(len(encoded)).encode("ascii")),
        ]
        delivered = False

        async def rewritten() -> dict:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": encoded, "more_body": False}
            return await receive()

        await self.app(converted, rewritten, send)
