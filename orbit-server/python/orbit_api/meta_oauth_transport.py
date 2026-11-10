"""Meta授权后端传输：固定官方源，禁止重定向，异常不暴露授权码或Token。"""

import asyncio
import hashlib
import hmac
import json
import re
import ssl
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpcore

from orbit_api.meta_connection_contract import CALLBACK, validate_grant
from orbit_api.oidc_http import PublicNetworkBackend, _constant, _object


class MetaOAuthTransport:
    def __init__(self, app, *, request=None):
        self.app = app
        self.request = request or self._request

    async def _request(self, method, path, params, token):
        if (method, path) not in {
            ("POST", "oauth/access_token"),
            ("GET", "debug_token"),
            ("GET", "me"),
        } and not (method == "GET" and re.fullmatch(r"[0-9]{1,64}/system_users", path)):
            raise ValueError("授权传输路径无效")
        target = "https://graph.facebook.com/" + self.app.graph_version + "/" + path
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        body = None
        if token:
            headers["Authorization"] = "Bearer " + token
        if method == "POST":
            body = urlencode(params).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            target += "?" + urlencode(params)
        try:
            async with (
                asyncio.timeout(20),
                httpcore.AsyncConnectionPool(
                    network_backend=PublicNetworkBackend(),
                    ssl_context=ssl.create_default_context(),
                    max_connections=1,
                    max_keepalive_connections=0,
                    retries=0,
                ) as pool,
                pool.stream(method, target, headers=headers, content=body) as response,
            ):
                if response.status != 200:
                    raise ValueError
                raw = bytearray()
                async for chunk in response.aiter_stream():
                    if len(raw) + len(chunk) > 65536:
                        raise ValueError
                    raw.extend(chunk)
                data = json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)
                if not isinstance(data, dict) or "error" in data:
                    raise ValueError
                return data
        except (
            ValueError,
            TypeError,
            OSError,
            TimeoutError,
            httpcore.NetworkError,
            httpcore.TimeoutException,
            httpcore.ProtocolError,
            UnicodeError,
            RecursionError,
        ):
            raise ValueError("Meta授权服务暂不可用或授权被拒绝") from None

    async def validate(self, token, *, system_user=False):
        debug = await self.request(
            "GET",
            "debug_token",
            {"input_token": token},
            self.app.app_id + "|" + self.app.app_secret,
        )
        grant = validate_grant(
            debug.get("data"), self.app, datetime.now(UTC), system_user=system_user
        )
        proof = hmac.new(self.app.app_secret.encode(), token.encode(), hashlib.sha256).hexdigest()
        principal = await self.request(
            "GET", "me", {"fields": "id", "appsecret_proof": proof}, token
        )
        if principal.get("id") != grant.principal_id:
            raise ValueError("Meta凭据主体不一致")
        return grant

    async def verify_system_user(self, token, business_id, principal_id):
        """官方Business.system_users读取核主体；不猜debug_token.type未证实枚举。"""
        if any(
            not isinstance(v, str) or not re.fullmatch(r"[0-9]{1,64}", v)
            for v in (business_id, principal_id)
        ):
            raise ValueError("BM系统用户主体尚未验证")
        after, seen = None, set()
        for _ in range(50):
            params = {"fields": "id", "limit": "200"}
            if after is not None:
                params["after"] = after
            response = await self.request("GET", business_id + "/system_users", params, token)
            rows = response.get("data") if isinstance(response, dict) else None
            if (
                not isinstance(rows, list)
                or len(rows) > 200
                or any(
                    not isinstance(row, dict)
                    or not isinstance(row.get("id"), str)
                    or not re.fullmatch(r"[0-9]{1,64}", row["id"])
                    for row in rows
                )
            ):
                raise ValueError("BM系统用户列表无效")
            if any(row["id"] == principal_id for row in rows):
                return
            paging = response.get("paging", {})
            if not isinstance(paging, dict):
                raise ValueError("BM系统用户分页无效")
            if not paging.get("next"):
                break
            cursors = paging.get("cursors")
            after = cursors.get("after") if isinstance(cursors, dict) else None
            if (
                not isinstance(after, str)
                or not 1 <= len(after) <= 2048
                or any(ord(c) < 33 or ord(c) > 126 for c in after)
                or after in seen
            ):
                raise ValueError("BM系统用户分页无效")
            seen.add(after)
        raise ValueError("凭据主体不是指定BM下可验证的系统用户")

    async def exchange(self, code):
        if not isinstance(code, str) or not 1 <= len(code) <= 4096:
            raise ValueError("授权码无效")
        response = await self.request(
            "POST",
            "oauth/access_token",
            {
                "client_id": self.app.app_id,
                "client_secret": self.app.app_secret,
                "redirect_uri": CALLBACK,
                "code": code,
            },
            None,
        )
        token = response.get("access_token")
        if (
            not isinstance(token, str)
            or not 1 <= len(token) <= 8192
            or not token.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in token)
        ):
            raise ValueError("Meta授权响应无效")
        return token, await self.validate(token)
