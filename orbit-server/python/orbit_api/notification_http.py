"""受控通知Webhook：真实回执才确认接受，发送结果未知时禁止自动重发。"""

import asyncio
import hashlib
import hmac
import json
import ssl
import time
from dataclasses import dataclass

import httpcore

from orbit_api.errors import OrbitError
from orbit_api.oidc_http import PublicNetworkBackend, _constant, _object, secure_url


@dataclass(frozen=True)
class DeliveryOutcome:
    status: str
    failure_code: str | None = None


class NotificationHttp:
    """独立连接、不跟随重定向或代理；任何秘密只存在于本次发送内存。"""

    def __init__(self, *, network_backend=None, ssl_context=None):
        self.backend = network_backend or PublicNetworkBackend()
        self.ssl_context = ssl_context or ssl.create_default_context()

    async def send(self, endpoint, delivery_id, body, signing_token=None):
        try:
            if secure_url(endpoint).query:
                raise ValueError
            if not isinstance(body, bytes) or not 1 <= len(body) <= 16384:
                raise ValueError
            if not isinstance(delivery_id, str) or len(delivery_id) != 36:
                raise ValueError
            # 仅接受UUID形状，避免任何外来内容进入HTTP头。
            from uuid import UUID

            if str(UUID(delivery_id)) != delivery_id:
                raise ValueError
            if signing_token is not None and (
                not isinstance(signing_token, str) or not 1 <= len(signing_token) <= 8192
            ):
                raise ValueError
        except (OrbitError, ValueError):
            return DeliveryOutcome("FAILED", "WEBHOOK_CONFIGURATION_INVALID")
        headers = [
            (b"Content-Type", b"application/json"),
            (b"Accept", b"application/json"),
            (b"Accept-Encoding", b"identity"),
            (b"Idempotency-Key", delivery_id.encode("ascii")),
        ]
        if signing_token is not None:
            timestamp = str(int(time.time())).encode("ascii")
            signature = hmac.new(
                signing_token.encode("utf-8"), timestamp + b"." + body, hashlib.sha256
            ).hexdigest()
            headers += [
                (b"X-ORBIT-Timestamp", timestamp),
                (b"X-ORBIT-Signature", ("sha256=" + signature).encode("ascii")),
            ]
        try:
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
                    "POST",
                    endpoint,
                    headers=headers,
                    content=body,
                    extensions={"timeout": dict(connect=5, read=10, write=5, pool=5)},
                ) as response,
            ):
                if 300 <= response.status < 500:
                    return DeliveryOutcome("FAILED", "WEBHOOK_REQUEST_REJECTED")
                if not 200 <= response.status < 300:
                    return DeliveryOutcome("UNKNOWN", "WEBHOOK_SERVER_RESULT_UNKNOWN")
                media = [v for k, v in response.headers if k.lower() == b"content-type"]
                if len(media) != 1 or media[0].split(b";", 1)[0].lower() != b"application/json":
                    return DeliveryOutcome("UNKNOWN", "WEBHOOK_RECEIPT_INVALID")
                data = bytearray()
                async for chunk in response.aiter_stream():
                    data.extend(chunk)
                    if len(data) > 65536:
                        return DeliveryOutcome("UNKNOWN", "WEBHOOK_RECEIPT_INVALID")
                result = json.loads(data, object_pairs_hook=_object, parse_constant=_constant)
                if not isinstance(result, dict) or result.get("delivery_id") != delivery_id:
                    return DeliveryOutcome("UNKNOWN", "WEBHOOK_RECEIPT_INVALID")
                if result.get("accepted") is True:
                    return DeliveryOutcome("ACCEPTED")
                if result.get("accepted") is False:
                    return DeliveryOutcome("FAILED", "WEBHOOK_DELIVERY_REJECTED")
                return DeliveryOutcome("UNKNOWN", "WEBHOOK_RECEIPT_INVALID")
        except OrbitError:
            # 安全网络后端在发送前拒绝内网或元数据地址，不回显DNS与URL。
            return DeliveryOutcome("FAILED", "WEBHOOK_ENDPOINT_REJECTED")
        except (
            httpcore.NetworkError,
            httpcore.TimeoutException,
            httpcore.ProtocolError,
            OSError,
            TimeoutError,
        ):
            return DeliveryOutcome("UNKNOWN", "WEBHOOK_TRANSPORT_RESULT_UNKNOWN")
        except (ValueError, UnicodeError, RecursionError):
            return DeliveryOutcome("UNKNOWN", "WEBHOOK_RECEIPT_INVALID")
