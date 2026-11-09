"""Meta只读账户适配器：固定官方HTTPS源、完整BM范围核验、有界分页和脱敏错误。"""

import asyncio
import json
import re
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpcore

from orbit_api.oidc_http import PublicNetworkBackend, _constant, _object


@dataclass(frozen=True, repr=False)
class MetaReadConfiguration:
    business_id: str
    graph_version: str
    token: str

    def validate(self):
        if (
            not isinstance(self.business_id, str)
            or not re.fullmatch(r"[0-9]{1,64}", self.business_id)
            or not isinstance(self.graph_version, str)
            or not re.fullmatch(r"v[0-9]{1,3}\.[0-9]{1,2}", self.graph_version)
            or not isinstance(self.token, str)
            or not 1 <= len(self.token) <= 8192
            or not self.token.isascii()
            or any(ord(ch) < 33 or ord(ch) > 126 for ch in self.token)
        ):
            raise AccountReadFailure("ACCOUNT_SOURCE_INVALID")


class AccountReadFailure(Exception):
    """只读失败不同于广告写入UNKNOWN；只暴露固定类别和是否允许受控重读。"""

    def __init__(self, code, *, retryable=False):
        super().__init__(code)
        self.code, self.retryable = code, retryable


class MetaAccountPlatform:
    """一个实例仅服务一轮冻结来源；prepare最多冻结500个目标，不跨轮长期缓存授权。"""

    FIELDS = "id,account_id,name,currency,timezone_name,account_status"

    def __init__(self, configuration, *, network_backend=None, ssl_context=None):
        configuration.validate()
        self.configuration = configuration
        self.backend = network_backend or PublicNetworkBackend()
        self.ssl_context = ssl_context or ssl.create_default_context()
        self.authorized = None
        self.preflight = None

    async def _get(self, path, parameters):
        if self.preflight is not None:
            await self.preflight()
        target = (
            "https://graph.facebook.com/"
            + self.configuration.graph_version
            + "/"
            + path
            + "?"
            + urlencode(parameters)
        )
        headers = {
            "Authorization": "Bearer " + self.configuration.token,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        }
        try:
            async with (
                asyncio.timeout(15),
                httpcore.AsyncConnectionPool(
                    network_backend=self.backend,
                    ssl_context=self.ssl_context,
                    retries=0,
                    max_connections=1,
                    max_keepalive_connections=0,
                ) as pool,
                pool.stream(
                    "GET",
                    target,
                    headers=headers,
                    extensions={"timeout": dict(connect=5, read=10, write=5, pool=5)},
                ) as response,
            ):
                if response.status == 429:
                    raise AccountReadFailure("ACCOUNT_PLATFORM_RATE_LIMITED", retryable=True)
                if response.status >= 500:
                    raise AccountReadFailure("ACCOUNT_PLATFORM_UNAVAILABLE", retryable=True)
                if 300 <= response.status < 400:
                    raise AccountReadFailure("ACCOUNT_PLATFORM_REDIRECT_REJECTED")
                if response.status in {401, 403}:
                    raise AccountReadFailure("ACCOUNT_PLATFORM_FORBIDDEN")
                if response.status not in {200, 400}:
                    raise AccountReadFailure("ACCOUNT_PLATFORM_REQUEST_REJECTED")
                content = bytearray()
                async for chunk in response.aiter_stream():
                    if len(content) + len(chunk) > 65536:
                        raise AccountReadFailure("ACCOUNT_PLATFORM_RESPONSE_INVALID")
                    content.extend(chunk)
                try:
                    value = json.loads(
                        content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant
                    )
                except (ValueError, UnicodeError, RecursionError):
                    raise AccountReadFailure("ACCOUNT_PLATFORM_RESPONSE_INVALID") from None
                if not isinstance(value, dict):
                    raise AccountReadFailure("ACCOUNT_PLATFORM_RESPONSE_INVALID")
                if "error" in value:
                    # Graph也会用HTTP400返回限流/瞬时错误，不把可重读故障误判为永久失败。
                    error = value["error"]
                    code = error.get("code") if isinstance(error, dict) else None
                    if type(code) is int and code in {4, 17, 32, 613, 80004}:
                        raise AccountReadFailure("ACCOUNT_PLATFORM_RATE_LIMITED", retryable=True)
                    if type(code) is int and code in {10, 190, 200}:
                        raise AccountReadFailure("ACCOUNT_PLATFORM_FORBIDDEN")
                    if isinstance(error, dict) and (
                        error.get("is_transient") is True or type(code) is int and code in {1, 2}
                    ):
                        raise AccountReadFailure("ACCOUNT_PLATFORM_UNAVAILABLE", retryable=True)
                    raise AccountReadFailure("ACCOUNT_PLATFORM_RESPONSE_INVALID")
                if response.status != 200:
                    raise AccountReadFailure("ACCOUNT_PLATFORM_REQUEST_REJECTED")
                return value
        except AccountReadFailure:
            raise
        except (
            TimeoutError,
            OSError,
            httpcore.NetworkError,
            httpcore.TimeoutException,
            httpcore.ProtocolError,
        ):
            # 只读查询未改变平台状态，允许后续有限重读；不借此宣称本地绑定成功。
            raise AccountReadFailure("ACCOUNT_PLATFORM_READ_UNCERTAIN", retryable=True) from None

    async def prepare(self, identifiers):
        self.authorized = None
        wanted = set(identifiers)
        if not 1 <= len(wanted) <= 500 or any(
            not isinstance(item, str) or not re.fullmatch(r"[0-9]{1,32}", item) for item in wanted
        ):
            raise ValueError("只读授权预检仅允许1至500个规范导入ID")
        matched = set()
        try:
            # 两个BM边一次性有界扫描，不为同批500个ID各重复遍历整个BM。
            async with asyncio.timeout(30):
                for edge in ("owned_ad_accounts", "client_ad_accounts"):
                    after, seen, count = None, set(), 0
                    while True:
                        parameters = {"fields": "id,account_id", "limit": "200"}
                        if after:
                            parameters["after"] = after
                        response = await self._get(
                            self.configuration.business_id + "/" + edge, parameters
                        )
                        data = response.get("data")
                        if not isinstance(data, list) or len(data) > 200:
                            raise AccountReadFailure("ACCOUNT_PLATFORM_SCOPE_INVALID")
                        count += len(data)
                        if count > 50000:
                            raise AccountReadFailure("ACCOUNT_PLATFORM_SCOPE_LIMIT")
                        for item in data:
                            if (
                                not isinstance(item, dict)
                                or not isinstance(item.get("account_id"), str)
                                or not re.fullmatch(r"[0-9]{1,64}", item["account_id"])
                                or item.get("id") != "act_" + item["account_id"]
                            ):
                                raise AccountReadFailure("ACCOUNT_PLATFORM_SCOPE_INVALID")
                            if item["account_id"] in wanted:
                                matched.add(item["account_id"])
                        if matched == wanted:
                            self.authorized = frozenset(matched)
                            return
                        paging = response.get("paging", {})
                        if not isinstance(paging, dict):
                            raise AccountReadFailure("ACCOUNT_PLATFORM_SCOPE_INVALID")
                        # next只作为继续标志；绝不跟随平台提供的完整URL或其中的access_token。
                        if not paging.get("next"):
                            break
                        cursors = paging.get("cursors")
                        following = cursors.get("after") if isinstance(cursors, dict) else None
                        if (
                            not isinstance(following, str)
                            or not 1 <= len(following) <= 2048
                            or following in seen
                            or not following.isascii()
                            or any(ord(ch) < 33 or ord(ch) > 126 for ch in following)
                        ):
                            raise AccountReadFailure("ACCOUNT_PLATFORM_SCOPE_INVALID")
                        seen.add(following)
                        after = following
                self.authorized = frozenset(matched)
        except TimeoutError:
            raise AccountReadFailure("ACCOUNT_PLATFORM_READ_UNCERTAIN", retryable=True) from None

    async def fetch_metadata(self, external_id):
        if self.authorized is None:
            raise AccountReadFailure("ACCOUNT_SCOPE_PRECHECK_REQUIRED")
        if external_id not in self.authorized:
            raise AccountReadFailure("ACCOUNT_PLATFORM_FORBIDDEN")
        value = await self._get("act_" + external_id, {"fields": self.FIELDS})
        required = {"id", "account_id", "name", "currency", "timezone_name", "account_status"}
        if (
            not required.issubset(value)
            or value["account_id"] != external_id
            or value["id"] != "act_" + external_id
            or type(value["account_status"]) is not int
            or not isinstance(value["name"], str)
            or not 1 <= len(value["name"]) <= 10000
        ):
            raise AccountReadFailure("ACCOUNT_METADATA_INVALID")
        try:
            value["name"].encode("utf-8")
        except UnicodeError:
            raise AccountReadFailure("ACCOUNT_METADATA_INVALID") from None
        return {
            "external_id": value["account_id"],
            "name": value["name"],
            "currency": value["currency"],
            "timezone_id": value["timezone_name"],
            "account_status": "ACTIVE"
            if value["account_status"] == 1
            else "DISABLED"
            if value["account_status"] == 2
            else "UNKNOWN",
            "auth_status": "AUTHORIZED",
            "observed_at": datetime.now(UTC),
        }
