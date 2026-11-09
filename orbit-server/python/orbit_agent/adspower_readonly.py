"""仅本机只读AdsPower发现；活跃集合不冒充完整Profile库存。"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from orbit_agent.adspower_status import (
    DEFAULT_ENDPOINT,
    ProbeError,
    _unique_object,
    canonical_endpoint,
    read_api_key,
)
from orbit_agent.protocol import profile_id

MAX_BODY = 2 * 1024 * 1024


def cdp_endpoint(value):
    if (
        type(value) is not str
        or re.fullmatch(
            r"ws://127\.0\.0\.1:([1-9][0-9]{0,4})/devtools/browser/[A-Za-z0-9_-]{1,128}", value
        )
        is None
    ):
        raise ProbeError("CDP_UNAVAILABLE")
    port = int(value.split(":")[2].split("/")[0])
    if not 1 <= port <= 65535:
        raise ProbeError("CDP_UNAVAILABLE")
    return value


@dataclass(frozen=True)
class Discovery:
    api_status: str
    coverage: str
    profiles: tuple
    error_code: str | None
    _cdp: dict = field(default_factory=dict, repr=False)
    observed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_monotonic: float = field(default_factory=time.monotonic, repr=False)

    def selected_cdp(self, external_profile_id):
        return self._cdp.get(external_profile_id)

    def summary(self):
        return {
            "api_status": self.api_status,
            "inventory_coverage": self.coverage,
            "observed_profile_count": len(self.profiles),
            "error_code": self.error_code,
        }


class ReadonlyAdsPower:
    def __init__(
        self,
        endpoint=DEFAULT_ENDPOINT,
        *,
        api_key_file=None,
        allowed_ports=frozenset({50325}),
        transport=None,
        sleep=asyncio.sleep,
    ):
        self.endpoint = canonical_endpoint(endpoint, allowed_ports=allowed_ports)
        self.api_key_file = api_key_file
        self.transport = transport
        self.sleep = sleep
        self.next_request = 0.0
        self.lock = asyncio.Lock()

    async def get(self, path, params=None):
        if path not in {"/status", "/api/v1/browser/local-active", "/api/v1/user/list"}:
            raise ProbeError("READONLY_PATH_REJECTED")
        async with self.lock:
            await self.sleep(max(0, self.next_request - time.monotonic()))
            self.next_request = time.monotonic() + 1.0
            headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
            if self.api_key_file is not None:
                headers["Authorization"] = "Bearer " + read_api_key(self.api_key_file)
            try:
                async with asyncio.timeout(5):
                    async with httpx.AsyncClient(
                        trust_env=False,
                        follow_redirects=False,
                        timeout=5,
                        transport=self.transport,
                        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
                    ) as client:
                        async with client.stream(
                            "GET", self.endpoint + path, params=params, headers=headers
                        ) as response:
                            if response.status_code in {401, 403}:
                                raise ProbeError("ADSPOWER_AUTH_FAILED")
                            if response.status_code == 429:
                                self.next_request = time.monotonic() + 5.0
                                raise ProbeError("PROFILE_DISCOVERY_FAILED")
                            if response.status_code != 200:
                                raise ProbeError("ADSPOWER_RESPONSE_INVALID")
                            if (
                                sum(len(k) + len(v) for k, v in response.headers.raw) > 8192
                                or response.headers.get("content-encoding", "identity").lower()
                                != "identity"
                            ):
                                raise ProbeError("ADSPOWER_RESPONSE_INVALID")
                            raw = bytearray()
                            async for chunk in response.aiter_bytes(chunk_size=65536):
                                if len(raw) + len(chunk) > MAX_BODY:
                                    raise ProbeError("ADSPOWER_RESPONSE_INVALID")
                                raw.extend(chunk)
                result = json.loads(raw, object_pairs_hook=_unique_object)
                if type(result) is not dict or type(result.get("code")) is not int:
                    raise ProbeError("ADSPOWER_RESPONSE_INVALID")
                if result["code"] != 0:
                    if (
                        path == "/api/v1/user/list"
                        and result["code"] == -1
                        and type(result.get("msg")) is str
                        and "paid subscriptions" in result["msg"].lower()
                    ):
                        raise ProbeError("ADSPOWER_SUBSCRIPTION_REQUIRED")
                    raise ProbeError("PROFILE_DISCOVERY_FAILED")
                return result
            except (TimeoutError, httpx.TimeoutException):
                raise ProbeError("ADSPOWER_TIMEOUT") from None
            except httpx.HTTPError:
                raise ProbeError("ADSPOWER_UNREACHABLE") from None
            except (ValueError, UnicodeError, RecursionError):
                raise ProbeError("ADSPOWER_RESPONSE_INVALID") from None
            finally:
                headers.pop("Authorization", None)

    @staticmethod
    def records(value):
        data = value.get("data")
        if type(data) is not dict or type(data.get("list")) is not list or len(data["list"]) > 5000:
            raise ProbeError("ADSPOWER_RESPONSE_INVALID")
        result = {}
        for item in data["list"]:
            if type(item) is not dict:
                raise ProbeError("ADSPOWER_RESPONSE_INVALID")
            identifier = profile_id(item.get("user_id"))
            if identifier in result:
                raise ProbeError("ADSPOWER_RESPONSE_INVALID")
            result[identifier] = item
        return result

    async def discover(self):
        observed_at = datetime.now(UTC).isoformat()
        started = time.monotonic()

        def snapshot(*args):
            return Discovery(*args, observed_at=observed_at, started_monotonic=started)

        try:
            await self.get("/status")
        except ProbeError as error:
            status = "AUTH_FAILED" if error.code == "ADSPOWER_AUTH_FAILED" else "UNREACHABLE"
            return snapshot(
                status,
                "UNAVAILABLE",
                (),
                error.code
                if error.code
                in {"ADSPOWER_TIMEOUT", "ADSPOWER_AUTH_FAILED", "ADSPOWER_UNREACHABLE"}
                else "ADSPOWER_RESPONSE_INVALID",
            )
        active, endpoints, active_known = {}, {}, False
        try:
            active = self.records(await self.get("/api/v1/browser/local-active"))
            active_known = True
            for identifier, row in active.items():
                ws = row.get("ws")
                if type(ws) is dict and ws.get("puppeteer"):
                    try:
                        endpoints[identifier] = cdp_endpoint(ws["puppeteer"])
                    except ProbeError:
                        pass
        except ProbeError:
            pass
        inventory = {}
        try:
            for page in range(1, 52):
                value = await self.get("/api/v1/user/list", {"page": page, "page_size": 100})
                records = self.records(value)
                if len(records) > 100 or inventory.keys() & records.keys():
                    raise ProbeError("PROFILE_DISCOVERY_FAILED")
                inventory.update(records)
                if len(inventory) > 5000:
                    raise ProbeError("PROFILE_DISCOVERY_FAILED")
                if len(records) < 100:
                    if active.keys() - inventory.keys():
                        # 库存分页期间发生变化：保留活跃观察，不声明全量一致。
                        raise ProbeError("PROFILE_DISCOVERY_FAILED")
                    return snapshot(
                        "READY",
                        "FULL",
                        tuple(
                            (
                                i,
                                "ACTIVE"
                                if i in active
                                else "INACTIVE"
                                if active_known
                                else "UNKNOWN",
                            )
                            for i in sorted(inventory)
                        ),
                        None,
                        endpoints,
                    )
            raise ProbeError("PROFILE_DISCOVERY_FAILED")
        except ProbeError as error:
            return snapshot(
                "READY",
                "ACTIVE_ONLY" if active_known else "UNAVAILABLE",
                tuple((i, "ACTIVE") for i in sorted(active)),
                (
                    "ADSPOWER_SUBSCRIPTION_REQUIRED"
                    if error.code == "ADSPOWER_SUBSCRIPTION_REQUIRED"
                    else "PROFILE_DISCOVERY_FAILED"
                ),
                endpoints,
            )
