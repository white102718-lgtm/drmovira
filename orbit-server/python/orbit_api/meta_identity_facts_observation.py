"""M3a只读身份事实；SDK字段声明不等于资源可投、能力发行或最终授权。"""

import asyncio
import hashlib
import json
import re
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit

import httpcore

from orbit_api.directory_tokens import canonical
from orbit_api.meta_launch_observation import (
    GraphReadResponse,
    MetaObservationFailure,
    MetaObservationLimits,
    _ReadBudget,
    external_id,
    fail,
    optional_text,
    utc_now,
)
from orbit_api.meta_observation_registry import prepare_rows
from orbit_api.oidc_http import PublicNetworkBackend

OBJECT_FIELDS = {
    "PAGE": "id,name,business,can_post",
    "PIXEL": (
        "id,name,owner_business,owner_ad_account,is_unavailable,"
        "is_restricted_use,user_access_expire_time"
    ),
    "APPLICATION": "id,name,business,ios_bundle_id,iphone_app_store_id,ipad_app_store_id",
}
ASSIGNMENT_FIELDS = "id,business,user_type"
_SAFE_UNVERIFIED = frozenset({"META_READ_FORBIDDEN", "META_READ_REJECTED"})


@dataclass(frozen=True)
class IdentityFactSelection:
    account_id: str
    kind: str
    external_id: str


@dataclass(frozen=True, repr=False)
class ResourceIdentityFacts:
    account_id: str
    kind: str
    external_id: str
    object_facts_json: bytes | None
    assignment_facts_json: bytes | None
    object_reason: str | None
    assignment_reason: str | None
    unknown_fields: tuple[str, ...]


@dataclass(frozen=True, repr=False)
class BoundIdentityFacts:
    source_binding_sha256: str
    source_config_id: str
    source_config_revision: int
    api_version: str
    business_id: str
    started_at: datetime
    observed_at: datetime
    principal_id: str | None
    principal_reason: str | None
    resources: tuple[ResourceIdentityFacts, ...]
    request_count: int
    response_bytes: int
    evidence_sha256: str
    # M1未绑定可选systemUserId；/me只观察，不宣称与配置主体相同。
    principal_binding: str = field(default="CONFIG_PRINCIPAL_NOT_BOUND", init=False)
    api_version_compatibility_verified: bool = field(default=False, init=False)
    execution_authorized: bool = field(default=False, init=False)
    durable: bool = field(default=False, init=False)
    capability_version: None = field(default=None, init=False)
    policy_version: None = field(default=None, init=False)


def validate_target(target):
    """默认网络层再次固定字段与GET目标，禁止任意路径、查询或Token参数。"""
    try:
        if not isinstance(target, str) or len(target) > 8192:
            fail("META_TARGET_INVALID")
        parsed = urlsplit(target)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "graph.facebook.com"
            or parsed.fragment
            or re.fullmatch(
                r"/v[0-9]{1,3}\.[0-9]{1,2}/(?:me|[0-9]{1,64}(?:/assigned_users)?)", parsed.path
            )
            is None
        ):
            fail("META_TARGET_INVALID")
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        values = dict(pairs)
        if len(pairs) != len(values):
            fail("META_TARGET_INVALID")
        if parsed.path.endswith("/me"):
            valid = values == {"fields": "id"}
        elif parsed.path.endswith("/assigned_users"):
            valid = (
                set(values)
                in ({"fields", "business", "limit"}, {"fields", "business", "limit", "after"})
                and values["fields"] == ASSIGNMENT_FIELDS
                and values["limit"] == "200"
            )
            external_id(values.get("business"))
            if "after" in values:
                cursor(values["after"])
        else:
            valid = set(values) == {"fields"} and values["fields"] in OBJECT_FIELDS.values()
        if not valid:
            fail("META_TARGET_INVALID")
    except (TypeError, ValueError):
        fail("META_TARGET_INVALID")


class IdentityGraphGetTransport:
    """无session、无POST、无重定向；默认真实网络不在本阶段测试中调用。"""

    def __init__(self):
        self.backend = PublicNetworkBackend()
        self.ssl_context = ssl.create_default_context()

    async def get(self, target, headers, *, maximum_bytes):
        validate_target(target)
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
        except MetaObservationFailure:
            raise
        except Exception:
            fail("META_READ_UNCERTAIN", retryable=True)


def cursor(value):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 2048
        or not value.isascii()
        or any(not 33 <= ord(char) <= 126 for char in value)
    ):
        fail("META_OBSERVATION_INCOMPLETE")
    return value


def text(value, token):
    result = optional_text(value)
    if result is not None and token in result:
        fail()
    return result


def object_facts(kind, row, token):
    facts, unknown = {}, []
    for key in OBJECT_FIELDS[kind].split(","):
        value = row.get(key)
        if value is None:
            unknown.append(key)
        elif key in {"business", "owner_business", "owner_ad_account"}:
            # 嵌套实体仅留白名单id；不保留自由正文或潜在Token。
            if not isinstance(value, dict):
                fail()
            value = {"id": external_id(value.get("id"))}
        elif key in {"can_post", "is_unavailable", "is_restricted_use"}:
            if type(value) is not bool:
                fail()
        elif key in {"id", "iphone_app_store_id", "ipad_app_store_id"}:
            value = external_id(value)
        elif key == "ios_bundle_id":
            if not isinstance(value, list) or len(value) > 500:
                fail()
            # 官方SDK类型为list<string>，不将数组改成单值或猜Android包名。
            for item in value:
                if text(item, token) is None:
                    fail()
        else:
            value = text(value, token)
        facts[key] = value
    return canonical(facts).encode("utf-8"), tuple(unknown)


class _FactsBudget(_ReadBudget):
    async def assignments(self, path):
        records, seen, after = {}, set(), None
        for _ in range(self.limits.max_pages):
            params = {
                "fields": ASSIGNMENT_FIELDS,
                "limit": "200",
                "business": self.configuration.business_id,
            }
            if after is not None:
                params["after"] = after
            value = await self.get(path, params)
            rows = value.get("data")
            if not isinstance(rows, list) or len(rows) > 200:
                fail()
            for row in rows:
                if not isinstance(row, dict):
                    fail()
                identifier = external_id(row.get("id"))
                if identifier in records:
                    fail("META_OBSERVATION_INCOMPLETE")
                business = row.get("business")
                if business is not None:
                    if not isinstance(business, dict):
                        fail()
                    business = {"id": external_id(business.get("id"))}
                records[identifier] = {
                    "id": identifier,
                    "business": business,
                    "user_type": text(row.get("user_type"), self.configuration.token),
                }
                if len(records) > self.limits.max_scope_records:
                    fail("META_RECORD_BUDGET_EXCEEDED")
            paging = value.get("paging", {})
            if not isinstance(paging, dict):
                fail()
            following = paging.get("next")
            if following is None or following == "":
                return canonical([records[key] for key in sorted(records)]).encode("utf-8")
            if not isinstance(following, str) or len(following) > 16384:
                fail("META_PAGINATION_INVALID")
            try:
                parsed = urlsplit(following)
                if (
                    parsed.scheme != "https"
                    or parsed.netloc not in {"graph.facebook.com", "graph.facebook.com:443"}
                    or parsed.fragment
                    or parsed.path != "/" + self.configuration.api_version + "/" + path
                ):
                    fail("META_PAGINATION_INVALID")
            except ValueError:
                fail("META_PAGINATION_INVALID")
            values = paging.get("cursors")
            after = cursor(values.get("after") if isinstance(values, dict) else None)
            if after in seen:
                fail("META_OBSERVATION_INCOMPLETE")
            seen.add(after)
        fail("META_PAGE_BUDGET_EXCEEDED")


def selection(bound, selected):
    # 复用M2纯校验：完整issuer/绑定/观察根及集合，不执行SQL、不登记或发能力。
    prepare_rows(bound)
    if not isinstance(selected, (list, tuple)) or not 1 <= len(selected) <= 500:
        fail("META_ACCOUNT_SELECTION_INVALID")
    external_accounts = {row.account_id: row.external_id for row in bound.source.accounts}
    allowed = {
        (account.external_id, resource.kind, resource.external_id)
        for account in bound.observation.accounts
        for resource in account.resources
    }
    result, seen = [], set()
    for item in selected:
        if not isinstance(item, IdentityFactSelection):
            fail("META_ACCOUNT_SELECTION_INVALID")
        key = (item.account_id, item.kind, item.external_id)
        external = external_accounts.get(item.account_id)
        if key in seen or (external, item.kind, item.external_id) not in allowed:
            fail("META_ACCOUNT_SELECTION_INVALID")
        seen.add(key)
        result.append(item)
    return tuple(sorted(result, key=lambda row: (row.account_id, row.kind, row.external_id)))


async def observe_identity_facts(bound, selected, *, transport=None, limits=None):
    """只返回绑定的观察，不接expected主体、verified开关、session或写入回调。"""
    selected = selection(bound, selected)
    configuration = bound.source.configuration
    configuration.validate()
    limits = limits if limits is not None else MetaObservationLimits()
    if not isinstance(limits, MetaObservationLimits):
        raise ValueError("需要有界只读预算")
    limits.validate()
    budget = _FactsBudget(
        configuration, transport if transport is not None else IdentityGraphGetTransport(), limits
    )
    started, principal, principal_reason, resources = utc_now(), None, None, []

    async def maybe_get(path, parameters):
        try:
            return await budget.get(path, parameters), None
        except MetaObservationFailure as error:
            if error.code not in _SAFE_UNVERIFIED:
                raise
            return None, error.code

    try:
        async with asyncio.timeout(limits.timeout_seconds):
            me, principal_reason = await maybe_get("me", {"fields": "id"})
            if me is not None:
                if me.get("id") is None:
                    principal_reason = "PRINCIPAL_ID_NOT_OBSERVED"
                else:
                    principal = external_id(me["id"])
            for item in selected:
                value, reason = await maybe_get(
                    item.external_id, {"fields": OBJECT_FIELDS[item.kind]}
                )
                facts, unknown = None, tuple(OBJECT_FIELDS[item.kind].split(","))
                if value is not None:
                    if value.get("id") != item.external_id:
                        fail("META_ACCOUNT_RESPONSE_MISMATCH")
                    facts, unknown = object_facts(item.kind, value, configuration.token)
                assignments, assignment_reason = None, "NOT_REQUESTED_FOR_APPLICATION"
                if item.kind != "APPLICATION":
                    assignment_reason = None
                    try:
                        assignments = await budget.assignments(item.external_id + "/assigned_users")
                    except MetaObservationFailure as error:
                        if error.code not in _SAFE_UNVERIFIED:
                            raise
                        assignment_reason = error.code
                resources.append(
                    ResourceIdentityFacts(
                        item.account_id,
                        item.kind,
                        item.external_id,
                        facts,
                        assignments,
                        reason,
                        assignment_reason,
                        unknown,
                    )
                )
    except TimeoutError:
        fail("META_READ_UNCERTAIN", retryable=True)
    observed = utc_now()
    document = {
        "schema_version": 1,
        "source_binding_sha256": bound.binding_sha256,
        "source_config_id": configuration.source_config_id,
        "source_config_revision": configuration.source_config_revision,
        "business_id": configuration.business_id,
        "api_version": configuration.api_version,
        "started_at": started.isoformat(),
        "observed_at": observed.isoformat(),
        "principal_id": principal,
        "principal_reason": principal_reason,
        "principal_binding": "CONFIG_PRINCIPAL_NOT_BOUND",
        "resources": [
            dict(
                account_id=row.account_id,
                kind=row.kind,
                external_id=row.external_id,
                object_facts=json.loads(row.object_facts_json) if row.object_facts_json else None,
                assignments=json.loads(row.assignment_facts_json)
                if row.assignment_facts_json
                else None,
                object_reason=row.object_reason,
                assignment_reason=row.assignment_reason,
                unknown_fields=row.unknown_fields,
            )
            for row in resources
        ],
    }
    encoded = canonical(document).encode("utf-8")
    if len(encoded) > limits.max_total_bytes:
        fail("META_RESPONSE_BUDGET_EXCEEDED")
    return BoundIdentityFacts(
        bound.binding_sha256,
        configuration.source_config_id,
        configuration.source_config_revision,
        configuration.api_version,
        configuration.business_id,
        started,
        observed,
        principal,
        principal_reason,
        tuple(resources),
        budget.requests,
        budget.bytes,
        hashlib.sha256(encoded).hexdigest(),
    )
