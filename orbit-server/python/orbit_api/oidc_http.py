"""OIDC专用HTTPS读取与交换：连接到已检查IP，保留原主机名TLS校验，禁止代理和重试。"""

import asyncio
import ipaddress
import json
import socket
import ssl
from urllib.parse import urlsplit

import httpcore

from orbit_api.errors import OrbitError


def secure_url(value):
    """受信配置仍须满足URL语法；禁止凭据、片段、反斜线及不可见字符。"""
    try:
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= 2048
            or not value.isascii()
            or any(ord(char) <= 32 or ord(char) == 127 for char in value)
            or "\\" in value
        ):
            raise ValueError
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
            or parts.port not in {None, 443}
            or "%" in parts.netloc
        ):
            raise ValueError
        return parts
    except ValueError:
        raise OrbitError(503, "OIDC_ENDPOINT_INVALID", "登录提供者HTTPS地址无效") from None


def public_address(value):
    try:
        address = ipaddress.ip_address(value)
        return (
            address.is_global
            and not address.is_multicast
            and not address.is_reserved
            and not address.is_unspecified
        )
    except ValueError:
        return False


class PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """DNS每次连接解析一次，全部地址须为公网；后续连接使用IP防止二次解析重绑定。"""

    def __init__(self):
        self.backend = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if port != 443:
            raise OrbitError(503, "OIDC_ENDPOINT_INVALID", "登录提供者仅支持标准HTTPS端口")
        async with asyncio.timeout(min(timeout or 10, 10)):
            answers = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
            addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
            if not addresses or len(addresses) > 32 or not all(map(public_address, addresses)):
                raise OrbitError(503, "OIDC_ENDPOINT_INVALID", "登录提供者解析地址不可访问")
            # TLS由httpcore继续使用原origin主机名校验，不把IP替换成证书主机名。
            return await self.backend.connect_tcp(
                addresses[0],
                port,
                timeout=timeout,
                local_address=local_address,
                socket_options=socket_options,
            )

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _constant(_value):
    raise ValueError


class OidcHttp:
    """不持久化外部响应；依赖注入仅供隔离测试，应用使用默认安全网络后端。"""

    def __init__(self, *, network_backend=None, ssl_context=None):
        self.backend = network_backend or PublicNetworkBackend()
        self.ssl_context = ssl_context or ssl.create_default_context()

    async def json(self, method, url, *, headers=None, content=None):
        secure_url(url)
        if method not in {"GET", "POST"}:
            raise ValueError("OIDC仅允许发现读取和授权码交换")
        request_headers = [(b"Accept", b"application/json"), (b"Accept-Encoding", b"identity")]
        request_headers += list(headers or [])
        try:
            # 独立池无环境代理、无自动重定向、无连接重试；请求有绝对时限和正文上限。
            async with (
                asyncio.timeout(15),
                httpcore.AsyncConnectionPool(
                    ssl_context=self.ssl_context,
                    network_backend=self.backend,
                    retries=0,
                    max_connections=1,
                    max_keepalive_connections=0,
                ) as pool,
                pool.stream(
                    method,
                    url,
                    headers=request_headers,
                    content=content,
                    extensions={"timeout": dict(connect=5, read=10, write=5, pool=5)},
                ) as response,
            ):
                if response.status != 200:
                    raise OrbitError(502, "OIDC_RESPONSE_REJECTED", "登录提供者未接受请求")
                media = [v for k, v in response.headers if k.lower() == b"content-type"]
                if len(media) != 1 or media[0].split(b";", 1)[0].lower() != b"application/json":
                    raise ValueError
                data = bytearray()
                async for chunk in response.aiter_stream():
                    data.extend(chunk)
                    if len(data) > 65_536:
                        raise ValueError
                result = json.loads(data, object_pairs_hook=_object, parse_constant=_constant)
                if not isinstance(result, dict):
                    raise ValueError
                return result
        except OrbitError:
            raise
        except (
            httpcore.NetworkError,
            httpcore.TimeoutException,
            httpcore.ProtocolError,
            OSError,
            TimeoutError,
        ):
            code = "OIDC_EXCHANGE_UNKNOWN" if method == "POST" else "OIDC_PROVIDER_UNAVAILABLE"
            raise OrbitError(503, code, "登录提供者暂不可用，请重新发起登录") from None
        except (ValueError, UnicodeError, RecursionError):
            raise OrbitError(502, "OIDC_RESPONSE_INVALID", "登录提供者响应无效") from None
