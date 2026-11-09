"""Meta投放只读观察：固定GET、有界完整分页；不授予广告写权或生产policy版本。"""

import asyncio
import hashlib
import json
import re
import ssl
from dataclasses import dataclass
from dataclasses import field as data_field
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID

import httpcore

from orbit_api.directory_tokens import canonical
from orbit_api.oidc_http import PublicNetworkBackend, _constant, _object

HOST = "https://graph.facebook.com"
SAFE_INTEGER = 9007199254740991
RESOURCE_EDGES = (
    ("PAGE", "promote_pages"),
    ("PIXEL", "adspixels"),
    ("APPLICATION", "advertisable_applications"),
)
ACCOUNT_FIELDS = "id,account_id,name,currency,timezone_name,account_status,capabilities,user_tasks"
FAILURE_CODES = frozenset(
    {
        "META_ACCOUNT_NOT_OBSERVED_IN_BM",
        "META_ACCOUNT_RESPONSE_MISMATCH",
        "META_ACCOUNT_SELECTION_INVALID",
        "META_EXTERNAL_ID_INVALID",
        "META_OBSERVATION_INCOMPLETE",
        "META_OBSERVATION_INVALID",
        "META_PAGE_BUDGET_EXCEEDED",
        "META_PAGINATION_INVALID",
        "META_RATE_LIMITED",
        "META_READ_FORBIDDEN",
        "META_READ_REJECTED",
        "META_READ_UNCERTAIN",
        "META_RECORD_BUDGET_EXCEEDED",
        "META_REDIRECT_REJECTED",
        "META_REQUEST_BUDGET_EXCEEDED",
        "META_RESPONSE_BUDGET_EXCEEDED",
        "META_SERVICE_UNAVAILABLE",
        "META_SOURCE_INVALID",
        "META_TARGET_INVALID",
    }
)


class MetaObservationFailure(Exception):
    """仅固定错误类别；Graph消息、URL、响应正文和凭据从不进入异常。"""

    def __init__(self, code, *, retryable=False):
        self.code = (
            code if isinstance(code, str) and code in FAILURE_CODES else "META_READ_UNCERTAIN"
        )
        self.retryable = retryable is True
        super().__init__(self.code)


def fail(code="META_OBSERVATION_INVALID", *, retryable=False):
    raise MetaObservationFailure(code, retryable=retryable) from None


def external_id(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,64}", value) is None:
        fail("META_EXTERNAL_ID_INVALID")
    return value


@dataclass(frozen=True, repr=False)
class MetaLaunchReadConfiguration:
    source_config_id: str
    source_config_revision: int
    business_id: str
    api_version: str
    token: str = data_field(repr=False)

    def validate(self):
        try:
            if (
                not isinstance(self.source_config_id, str)
                or str(UUID(self.source_config_id)) != self.source_config_id
            ):
                fail("META_SOURCE_INVALID")
        except ValueError:
            fail("META_SOURCE_INVALID")
        if (
            type(self.source_config_revision) is not int
            or not 1 <= self.source_config_revision <= SAFE_INTEGER
        ):
            fail("META_SOURCE_INVALID")
        external_id(self.business_id)
        if (
            not isinstance(self.api_version, str)
            or re.fullmatch(r"v[0-9]{1,3}\.[0-9]{1,2}", self.api_version) is None
        ):
            fail("META_SOURCE_INVALID")
        if (
            not isinstance(self.token, str)
            or not 1 <= len(self.token) <= 8192
            or not self.token.isascii()
            or any(not 33 <= ord(char) <= 126 for char in self.token)
        ):
            fail("META_SOURCE_INVALID")


@dataclass(frozen=True)
class MetaObservationLimits:
    max_pages: int = 250
    max_scope_records: int = 50000
    max_resources_per_account: int = 5000
    max_requests: int = 2500
    max_response_bytes: int = 262144
    max_total_bytes: int = 33554432
    timeout_seconds: int = 60

    def validate(self):
        for name, maximum in (
            ("max_pages", 250),
            ("max_scope_records", 50000),
            ("max_resources_per_account", 5000),
            ("max_requests", 2500),
            ("max_response_bytes", 262144),
            ("max_total_bytes", 33554432),
            ("timeout_seconds", 60),
        ):
            if type(getattr(self, name)) is not int or not 1 <= getattr(self, name) <= maximum:
                raise ValueError("观察预算必须为正整数且不超过服务器硬上限")


@dataclass(frozen=True, repr=False)
class GraphReadResponse:
    status: int
    body: bytes


class GraphGetTransport:
    """默认真实HTTP实现只暴露GET；测试transport不代表真实Meta验收。"""

    def __init__(self):
        self.backend = PublicNetworkBackend()
        self.ssl_context = ssl.create_default_context()

    async def get(self, target, headers, *, maximum_bytes):
        # 默认transport本身也禁止任意URL；不只依赖上一层调用者遵守约定。
        try:
            if not isinstance(target, str) or len(target) > 8192:
                fail("META_TARGET_INVALID")
            parsed = urlsplit(target)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "graph.facebook.com"
                or parsed.fragment
                or re.fullmatch(
                    r"/v[0-9]{1,3}\.[0-9]{1,2}/(?:[0-9]{1,64}/(?:owned_ad_accounts|client_ad_accounts)"
                    r"|act_[0-9]{1,64}(?:/(?:promote_pages|adspixels|advertisable_applications))?)",
                    parsed.path,
                )
                is None
            ):
                fail("META_TARGET_INVALID")
            pairs = parse_qsl(parsed.query, strict_parsing=True, keep_blank_values=True)
            values = dict(pairs)
            if len(pairs) != len(values):
                fail("META_TARGET_INVALID")
            if parsed.path.endswith(("/owned_ad_accounts", "/client_ad_accounts")):
                expected_fields = "id,account_id"
            elif parsed.path.endswith(
                ("/promote_pages", "/adspixels", "/advertisable_applications")
            ):
                expected_fields = "id,name"
            else:
                expected_fields = ACCOUNT_FIELDS
            if values.get("fields") != expected_fields:
                fail("META_TARGET_INVALID")
            if expected_fields == ACCOUNT_FIELDS:
                if set(values) != {"fields"}:
                    fail("META_TARGET_INVALID")
            elif set(values) - {"fields", "limit", "after"} or values.get("limit") != "200":
                fail("META_TARGET_INVALID")
        except (ValueError, TypeError):
            fail("META_TARGET_INVALID")
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
                content = bytearray()
                async for chunk in response.aiter_stream():
                    if len(content) + len(chunk) > maximum_bytes:
                        fail("META_RESPONSE_BUDGET_EXCEEDED")
                    content.extend(chunk)
                return GraphReadResponse(response.status, bytes(content))
        except MetaObservationFailure as error:
            fail(error.code, retryable=error.retryable)
        except (
            TimeoutError,
            OSError,
            httpcore.NetworkError,
            httpcore.TimeoutException,
            httpcore.ProtocolError,
        ):
            fail("META_READ_UNCERTAIN", retryable=True)


@dataclass(frozen=True, repr=False)
class MetaIdentityObservation:
    kind: str
    external_id: str
    name: str | None


@dataclass(frozen=True, repr=False)
class MetaAccountObservation:
    external_id: str
    bm_edges: tuple[str, ...]
    metadata_json: bytes
    resources: tuple[MetaIdentityObservation, ...]
    unknown_fields: tuple[str, ...]


@dataclass(frozen=True, repr=False)
class MetaLaunchObservation:
    source_config_id: str
    source_config_revision: int
    business_id: str
    api_version: str
    started_at: datetime
    observed_at: datetime
    accounts: tuple[MetaAccountObservation, ...]
    evidence_sha256: str
    request_count: int
    response_bytes: int
    complete: bool = data_field(default=True, init=False)
    execution_authorized: bool = data_field(default=False, init=False)
    policy_version: None = data_field(default=None, init=False)
    workflow_version: None = data_field(default=None, init=False)


def optional_text(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 4096 or "\0" in value:
        fail()
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        fail()
    return value


def utc_now():
    value = datetime.now(UTC)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


class _ReadBudget:
    def __init__(self, configuration, transport, limits):
        self.configuration, self.transport, self.limits = configuration, transport, limits
        self.requests, self.bytes = 0, 0

    async def get(self, path, parameters):
        self.requests += 1
        if self.requests > self.limits.max_requests:
            fail("META_REQUEST_BUDGET_EXCEEDED")
        target = (
            HOST + "/" + self.configuration.api_version + "/" + path + "?" + urlencode(parameters)
        )
        headers = {
            "Authorization": "Bearer " + self.configuration.token,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        }
        try:
            response = await self.transport.get(
                target, headers, maximum_bytes=self.limits.max_response_bytes
            )
        except MetaObservationFailure as error:
            fail(error.code, retryable=error.retryable)
        except Exception:
            # 不把第三方transport异常正文拼进错误；可能含URL或Authorization。
            fail("META_READ_UNCERTAIN", retryable=True)
        if (
            not isinstance(response, GraphReadResponse)
            or not isinstance(response.body, bytes)
            or type(response.status) is not int
        ):
            fail()
        self.bytes += len(response.body)
        if (
            len(response.body) > self.limits.max_response_bytes
            or self.bytes > self.limits.max_total_bytes
        ):
            fail("META_RESPONSE_BUDGET_EXCEEDED")
        if response.status == 429:
            fail("META_RATE_LIMITED", retryable=True)
        if response.status >= 500:
            fail("META_SERVICE_UNAVAILABLE", retryable=True)
        if 300 <= response.status < 400:
            fail("META_REDIRECT_REJECTED")
        if response.status in {401, 403}:
            fail("META_READ_FORBIDDEN")
        if response.status not in {200, 400}:
            fail("META_READ_REJECTED")
        try:
            value = json.loads(
                response.body.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant
            )
        except (ValueError, UnicodeError, RecursionError):
            fail()
        if not isinstance(value, dict):
            fail()
        if "error" in value:
            error = value["error"]
            code = error.get("code") if isinstance(error, dict) else None
            if type(code) is int and code in {4, 17, 32, 613, 80004}:
                fail("META_RATE_LIMITED", retryable=True)
            if type(code) is int and code in {10, 190, 200}:
                fail("META_READ_FORBIDDEN")
            if isinstance(error, dict) and (
                error.get("is_transient") is True or type(code) is int and code in {1, 2}
            ):
                fail("META_SERVICE_UNAVAILABLE", retryable=True)
            fail("META_READ_REJECTED")
        if response.status != 200:
            fail("META_READ_REJECTED")
        return value

    async def edge(self, path, fields, maximum):
        rows, after, cursors = [], None, set()
        for _ in range(self.limits.max_pages):
            params = {"fields": fields, "limit": "200"}
            if after is not None:
                params["after"] = after
            value = await self.get(path, params)
            data = value.get("data")
            if (
                not isinstance(data, list)
                or len(data) > 200
                or any(not isinstance(row, dict) for row in data)
            ):
                fail()
            rows.extend(data)
            if len(rows) > maximum:
                fail("META_RECORD_BUDGET_EXCEEDED")
            paging = value.get("paging", {})
            if not isinstance(paging, dict):
                fail()
            following = paging.get("next")
            if following is None or following == "":
                return rows
            if not isinstance(following, str) or len(following) > 16384:
                fail("META_OBSERVATION_INCOMPLETE")
            try:
                parsed = urlsplit(following)
                if (
                    parsed.scheme != "https"
                    or parsed.hostname != "graph.facebook.com"
                    or parsed.port not in {None, 443}
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.fragment
                    or parsed.path != "/" + self.configuration.api_version + "/" + path
                ):
                    fail("META_PAGINATION_INVALID")
            except ValueError:
                fail("META_PAGINATION_INVALID")
            values = paging.get("cursors")
            after = values.get("after") if isinstance(values, dict) else None
            if (
                not isinstance(after, str)
                or not 1 <= len(after) <= 2048
                or not after.isascii()
                or any(not 33 <= ord(char) <= 126 for char in after)
                or after in cursors
            ):
                fail("META_OBSERVATION_INCOMPLETE")
            cursors.add(after)
            # 绝不跟随next或转发其access_token；只将不透明after放回固定当前path。
        fail("META_PAGE_BUDGET_EXCEEDED")


class MetaLaunchObserver:
    def __init__(self, configuration, *, transport=None, limits=None):
        if not isinstance(configuration, MetaLaunchReadConfiguration):
            fail("META_SOURCE_INVALID")
        configuration.validate()
        self.configuration = configuration
        self.transport = transport if transport is not None else GraphGetTransport()
        self.limits = limits if limits is not None else MetaObservationLimits()
        if not isinstance(self.limits, MetaObservationLimits):
            raise ValueError("需要有界只读预算")
        self.limits.validate()

    async def observe(self, account_ids):
        if not isinstance(account_ids, (tuple, list)) or not 1 <= len(account_ids) <= 500:
            fail("META_ACCOUNT_SELECTION_INVALID")
        wanted = tuple(sorted(external_id(value) for value in account_ids))
        if len(set(wanted)) != len(wanted):
            fail("META_ACCOUNT_SELECTION_INVALID")
        budget = _ReadBudget(self.configuration, self.transport, self.limits)
        started = utc_now()
        try:
            async with asyncio.timeout(self.limits.timeout_seconds):
                accounts = await self._observe(budget, wanted)
        except TimeoutError:
            fail("META_READ_UNCERTAIN", retryable=True)
        now = utc_now()
        document = {
            "source_config_id": self.configuration.source_config_id,
            "source_config_revision": self.configuration.source_config_revision,
            "business_id": self.configuration.business_id,
            "api_version": self.configuration.api_version,
            "started_at": started.isoformat(),
            "observed_at": now.isoformat(),
            "accounts": [
                {
                    "external_id": item.external_id,
                    "bm_edges": item.bm_edges,
                    "metadata": json.loads(item.metadata_json),
                    "resources": [row.__dict__ for row in item.resources],
                    "unknown_fields": item.unknown_fields,
                }
                for item in accounts
            ],
        }
        return MetaLaunchObservation(
            self.configuration.source_config_id,
            self.configuration.source_config_revision,
            self.configuration.business_id,
            self.configuration.api_version,
            started,
            now,
            accounts,
            hashlib.sha256(canonical(document).encode()).hexdigest(),
            budget.requests,
            budget.bytes,
        )

    async def _observe(self, budget, wanted):
        membership = {identifier: set() for identifier in wanted}
        for edge in ("owned_ad_accounts", "client_ad_accounts"):
            records = await budget.edge(
                self.configuration.business_id + "/" + edge,
                "id,account_id",
                self.limits.max_scope_records,
            )
            seen = set()
            for row in records:
                identifier = external_id(row.get("account_id"))
                if row.get("id") != "act_" + identifier or identifier in seen:
                    fail("META_OBSERVATION_INCOMPLETE")
                seen.add(identifier)
                if identifier in membership:
                    membership[identifier].add(edge)
        if any(not value for value in membership.values()):
            fail("META_ACCOUNT_NOT_OBSERVED_IN_BM")
        result = []
        for identifier in wanted:
            path = "act_" + identifier
            row = await budget.get(path, {"fields": ACCOUNT_FIELDS})
            if row.get("id") != path or row.get("account_id") != identifier:
                fail("META_ACCOUNT_RESPONSE_MISMATCH")
            metadata = {
                field: optional_text(row.get(field))
                for field in ("name", "currency", "timezone_name")
            }
            status = row.get("account_status")
            if status is not None and (type(status) is not int or not 0 <= status <= SAFE_INTEGER):
                fail()
            metadata["account_status"] = status
            for field in ("capabilities", "user_tasks"):
                value = row.get(field)
                if value is not None:
                    if (
                        not isinstance(value, list)
                        or len(value) > 500
                        or any(
                            not isinstance(item, str) or not 1 <= len(item) <= 128 for item in value
                        )
                    ):
                        fail()
                    for item in value:
                        optional_text(item)
                    value = sorted(set(value))
                metadata[field] = value
            resources, unknown = [], [key for key, value in metadata.items() if value is None]
            for kind, edge in RESOURCE_EDGES:
                records = await budget.edge(
                    path + "/" + edge, "id,name", self.limits.max_resources_per_account
                )
                seen = set()
                for resource in records:
                    external = external_id(resource.get("id"))
                    if external in seen:
                        fail("META_OBSERVATION_INCOMPLETE")
                    seen.add(external)
                    name = optional_text(resource.get("name"))
                    if name is None:
                        unknown.append(kind + ":" + external + ":name")
                    resources.append(MetaIdentityObservation(kind, external, name))
                if len(resources) > self.limits.max_resources_per_account:
                    fail("META_RECORD_BUDGET_EXCEEDED")
            result.append(
                MetaAccountObservation(
                    identifier,
                    tuple(sorted(membership[identifier])),
                    canonical(metadata).encode(),
                    tuple(sorted(resources, key=lambda item: (item.kind, item.external_id))),
                    tuple(sorted(unknown)),
                )
            )
        return tuple(result)
