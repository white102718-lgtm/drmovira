"""Meta正式Graph只读传输和分块采集；POST仅创建Insights报告，不操作广告。"""

import asyncio
import hashlib
import json
import re
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpcore

from orbit_api.directory_tokens import canonical
from orbit_api.meta_account_daily_spend import SPEND_FIELDS
from orbit_api.meta_account_enrichment import OPTIONAL_FIELDS
from orbit_api.meta_read_contract import (
    AsyncReport,
    InsightWindow,
    MetaAttribution,
    MetaReadConfiguration,
    MetaReadFailure,
    ReadCheckpoint,
    ReadPage,
    ReportStatus,
    decimal_value,
    external_id,
    fail,
    validate_api_version,
)
from orbit_api.oidc_http import PublicNetworkBackend, _constant, _object

ACCOUNT_FIELDS = (
    "id,account_id,name,currency,timezone_name,account_status,amount_spent,balance,spend_cap"
)
STRUCTURE_FIELDS = {
    "CAMPAIGN": (
        "id,account_id,name,status,effective_status,objective,"
        "daily_budget,lifetime_budget,updated_time"
    ),
    "ADSET": (
        "id,account_id,campaign_id,name,status,effective_status,daily_budget,"
        "lifetime_budget,optimization_goal,billing_event,updated_time"
    ),
    "AD": "id,account_id,campaign_id,adset_id,name,status,effective_status,updated_time",
}
INSIGHT_FIELDS = (
    "account_id,account_currency,campaign_id,adset_id,ad_id,date_start,date_stop,"
    "spend,impressions,clicks,reach,actions,action_values"
)
MAX_BYTES = 1048576


@dataclass(frozen=True, repr=False)
class GraphResponse:
    status: int
    body: bytes


class GraphReadTransport:
    """固定HTTPS主机、公共地址DNS、拒绝重定向及代理，绝不向广告端点POST。"""

    async def request(self, method, path, parameters, token, *, maximum_bytes):
        allowed = (
            r"/v[0-9]{1,3}\.[0-9]{1,2}/(?:me|me/adaccounts|[0-9]{1,64}/"
            r"(?:owned_ad_accounts|client_ad_accounts|insights)|[0-9]{1,64}|"
            r"act_[0-9]{1,64}(?:/(?:campaigns|adsets|ads|insights))?)"
        )
        if (
            method not in {"GET", "POST"}
            or not isinstance(path, str)
            or re.fullmatch(allowed, path) is None
            or (
                method == "POST"
                and re.fullmatch(r"/v[0-9]{1,3}\.[0-9]{1,2}/act_[0-9]{1,64}/insights", path) is None
            )
            or type(parameters) is not dict
            or set(parameters)
            - {
                "fields",
                "limit",
                "after",
                "time_range",
                "time_increment",
                "level",
                "async",
                "action_attribution_windows",
                "action_report_time",
            }
            or any(not isinstance(v, str) or len(v) > 4096 for v in parameters.values())
            or not isinstance(token, str)
            or not 1 <= len(token) <= 8192
            or any(not 33 <= ord(c) <= 126 for c in token)
            or type(maximum_bytes) is not int
            or not 1 <= maximum_bytes <= MAX_BYTES
        ):
            fail("META_REQUEST_INVALID")
        validate_api_version(path.split("/")[1])
        validate_graph_parameters(method, path, parameters)
        target = "https://graph.facebook.com" + path
        data = urlencode(parameters)
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        }
        body = b""
        if method == "GET":
            target += "?" + data
        else:
            body = data.encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            async with (
                asyncio.timeout(20),
                httpcore.AsyncConnectionPool(
                    network_backend=PublicNetworkBackend(),
                    ssl_context=ssl.create_default_context(),
                    retries=0,
                    max_connections=1,
                    max_keepalive_connections=0,
                ) as pool,
                pool.stream(
                    method,
                    target,
                    headers=headers,
                    content=body,
                    extensions={"timeout": dict(connect=5, read=15, write=5, pool=5)},
                ) as response,
            ):
                content = bytearray()
                async for chunk in response.aiter_stream():
                    if len(content) + len(chunk) > maximum_bytes:
                        fail("META_RESPONSE_TOO_LARGE")
                    content.extend(chunk)
                return GraphResponse(response.status, bytes(content))
        except MetaReadFailure:
            raise
        except Exception:
            fail("META_TRANSIENT_FAILURE", retryable=True)


def validate_graph_parameters(method, path, parameters):
    """v24.0固定只读字段组合；仅允许Insights建报告，不开放通用Graph请求。"""
    resource = path.split("/", 2)[2]
    paged = False
    required = {"fields"}
    optional = set()
    if resource.endswith(("/adaccounts", "/owned_ad_accounts", "/client_ad_accounts")):
        fields = ACCOUNT_FIELDS
        paged = True
    elif resource == "me":
        fields = "id,name"
    elif re.fullmatch(r"act_[0-9]{1,64}", resource):
        fields = parameters.get("fields")
        if fields not in (ACCOUNT_FIELDS, *("id,account_id," + item for item in OPTIONAL_FIELDS)):
            fail("META_REQUEST_INVALID")
    elif re.fullmatch(r"[0-9]{1,64}", resource):
        fields = "id,account_id,async_status,async_percent_completion"
    elif resource.endswith("/insights") and parameters.get("fields") == SPEND_FIELDS:
        fields = SPEND_FIELDS
        paged = True
        required |= {"level", "time_range", "time_increment"}
        if (
            method != "GET"
            or not re.fullmatch(r"act_[0-9]{1,64}/insights", resource)
            or parameters.get("level") != "account"
            or parameters.get("time_increment") != "1"
        ):
            fail("META_REQUEST_INVALID")
        try:
            from datetime import date

            window = json.loads(parameters["time_range"], object_pairs_hook=_object)
            if set(window) != {"since", "until"}:
                fail("META_REQUEST_INVALID")
            InsightWindow(
                date.fromisoformat(window["since"]), date.fromisoformat(window["until"]), "UTC"
            )
        except (ValueError, KeyError, TypeError):
            fail("META_REQUEST_INVALID")
    elif resource.endswith("/insights"):
        fields = INSIGHT_FIELDS
        paged = True
        if resource.startswith("act_"):
            required |= {
                "level",
                "time_range",
                "time_increment",
                "action_attribution_windows",
                "action_report_time",
            }
            if (
                parameters.get("level") not in {"account", "campaign", "adset", "ad"}
                or parameters.get("time_increment") != "1"
                or parameters.get("action_report_time") not in {"impression", "conversion", "mixed"}
            ):
                fail("META_REQUEST_INVALID")
            try:
                windows = json.loads(parameters["action_attribution_windows"])
                window = json.loads(parameters["time_range"], object_pairs_hook=_object)
                from datetime import date

                if (
                    type(windows) is not list
                    or not 1 <= len(windows) <= 3
                    or any(not isinstance(w, str) for w in windows)
                    or len(set(windows)) != len(windows)
                    or not set(windows) <= {"1d_click", "7d_click", "1d_view"}
                    or set(window) != {"since", "until"}
                ):
                    fail("META_REQUEST_INVALID")
                InsightWindow(
                    date.fromisoformat(window["since"]), date.fromisoformat(window["until"]), "UTC"
                )
            except (ValueError, KeyError, TypeError):
                fail("META_REQUEST_INVALID")
    else:
        kind = {"campaigns": "CAMPAIGN", "adsets": "ADSET", "ads": "AD"}.get(
            resource.rsplit("/", 1)[-1]
        )
        if kind is None:
            fail("META_REQUEST_INVALID")
        fields = STRUCTURE_FIELDS[kind]
        paged = True
    if paged:
        required.add("limit")
        if parameters.get("limit") != "200":
            fail("META_REQUEST_INVALID")
        if method == "GET":
            optional.add("after")
    if (
        parameters.get("fields") != fields
        or not required <= set(parameters)
        or set(parameters) - required - optional
    ):
        fail("META_REQUEST_INVALID")
    if "after" in parameters and not 1 <= len(parameters["after"]) <= 2048:
        fail("META_REQUEST_INVALID")


def optional_text(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
        fail()
    return value


def account_record(row):
    account = external_id(row.get("account_id"))
    if row.get("id") != "act_" + account:
        fail("META_ACCOUNT_MISMATCH")
    currency = optional_text(row.get("currency"))
    if currency is not None and re.fullmatch("[A-Z]{3}", currency) is None:
        fail()
    timezone = optional_text(row.get("timezone_name"))
    if timezone:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError):
            fail()
    return {
        "id": row["id"],
        "account_id": account,
        "name": optional_text(row.get("name")),
        "currency": currency,
        "timezone_name": timezone,
        "account_status": decimal_value(row.get("account_status"), integer=True),
        **{
            k + "_minor": decimal_value(row.get(k), integer=True)
            for k in ("amount_spent", "balance", "spend_cap")
        },
    }


class MetaReadAdapter:
    """每调用最多一页；worker负责持久检查点、权限复验与完整后原子发布。"""

    def __init__(self, configuration, *, transport=None, sleep=asyncio.sleep):
        if not isinstance(configuration, MetaReadConfiguration):
            fail("META_CONFIG_INVALID")
        self.configuration = configuration
        self.transport = transport or GraphReadTransport()
        self.sleep = sleep

    def fingerprint(self, path, parameters, extra=None):
        return hashlib.sha256(
            canonical([self.configuration.fingerprint, path, parameters, extra]).encode()
        ).hexdigest()

    async def _request(self, method, path, parameters):
        # 三次重试加首次共四次；异步建报告不盲目重试不确定POST。
        for attempt in range(4):
            try:
                response = await self.transport.request(
                    method,
                    "/" + self.configuration.api_version + "/" + path,
                    parameters,
                    self.configuration.token,
                    maximum_bytes=MAX_BYTES,
                )
                if (
                    not isinstance(response, GraphResponse)
                    or type(response.status) is not int
                    or not isinstance(response.body, bytes)
                ):
                    fail()
                if len(response.body) > MAX_BYTES:
                    fail("META_RESPONSE_TOO_LARGE")
                if 300 <= response.status < 400:
                    fail("META_REDIRECT_REJECTED")
                if response.status == 429:
                    fail("META_RATE_LIMITED", retryable=True)
                if response.status >= 500:
                    fail("META_TRANSIENT_FAILURE", retryable=True)
                if response.status == 401:
                    fail("META_AUTH_FAILED")
                try:
                    value = json.loads(
                        response.body.decode(), object_pairs_hook=_object, parse_constant=_constant
                    )
                except (ValueError, UnicodeError, RecursionError):
                    fail()
                if not isinstance(value, dict):
                    fail()
                if "error" in value:
                    error = value["error"]
                    code = error.get("code") if isinstance(error, dict) else None
                    if type(code) is int and code in {102, 190}:
                        fail("META_AUTH_FAILED")
                    if type(code) is int and code in {10, 200, 294}:
                        fail("META_READ_FORBIDDEN")
                    if type(code) is int and code in {4, 17, 32, 613, 80004}:
                        fail("META_RATE_LIMITED", retryable=True)
                    if isinstance(error, dict) and (
                        error.get("is_transient") is True or code in (1, 2)
                    ):
                        fail("META_TRANSIENT_FAILURE", retryable=True)
                    if response.status == 403:
                        fail("META_READ_FORBIDDEN")
                    fail("META_READ_REJECTED")
                if response.status == 403:
                    fail("META_READ_FORBIDDEN")
                if response.status != 200:
                    fail("META_READ_REJECTED")
                return value, response.body
            except MetaReadFailure as error:
                if method == "POST" and error.code in {
                    "META_TRANSIENT_FAILURE",
                    "META_RESPONSE_INVALID",
                    "META_RESPONSE_TOO_LARGE",
                }:
                    fail("META_REPORT_START_UNKNOWN")
                if not error.retryable or attempt == 3:
                    raise
                await self.sleep(min(8, 2**attempt))
            except Exception:
                if method == "POST":
                    fail("META_REPORT_START_UNKNOWN")
                if attempt == 3:
                    fail("META_TRANSIENT_FAILURE", retryable=True)
                await self.sleep(min(8, 2**attempt))
        fail()

    async def _page(self, path, parameters, normalize, *, checkpoint=None, extra=None, key=None):
        fingerprint = self.fingerprint(path, parameters, extra)
        pages = 0
        count = 0
        cursors = ()
        keys = ()
        params = dict(parameters)
        if checkpoint is not None:
            if (
                not isinstance(checkpoint, ReadCheckpoint)
                or checkpoint.source_fingerprint != self.configuration.fingerprint
                or checkpoint.request_fingerprint != fingerprint
            ):
                fail("META_CHECKPOINT_MISMATCH")
            pages, count, cursors, keys = (
                checkpoint.page_number,
                checkpoint.record_count,
                checkpoint.seen_cursors,
                checkpoint.seen_keys,
            )
            if (
                type(pages) is not int
                or not 1 <= pages < 250
                or type(count) is not int
                or not 0 <= count <= 50000
            ):
                fail("META_CHECKPOINT_MISMATCH")
            if not isinstance(checkpoint.after, str) or not 1 <= len(checkpoint.after) <= 2048:
                fail("META_CHECKPOINT_MISMATCH")
            params["after"] = checkpoint.after
        value, raw = await self._request("GET", path, params)
        rows = value.get("data")
        if (
            not isinstance(rows, list)
            or len(rows) > 200
            or any(type(row) is not dict for row in rows)
        ):
            fail()
        items = tuple(normalize(row) for row in rows)
        current_keys = tuple((key(item) if key else item["id"]) for item in items)
        if len(set(current_keys)) != len(current_keys) or set(current_keys) & set(keys):
            fail("META_PAGINATION_INVALID")
        count += len(items)
        pages += 1
        if count > 50000:
            fail("META_RECORD_LIMIT")
        paging = value.get("paging", {})
        if not isinstance(paging, dict):
            fail("META_PAGINATION_INVALID")
        following = paging.get("next")
        if following is not None and not isinstance(following, str):
            fail("META_PAGINATION_INVALID")
        next_checkpoint = None
        if following:
            if not isinstance(following, str) or len(following) > 16384:
                fail("META_PAGINATION_INVALID")
            url = urlsplit(following)
            if (
                url.scheme != "https"
                or url.netloc != "graph.facebook.com"
                or url.fragment
                or url.path != "/" + self.configuration.api_version + "/" + path
            ):
                fail("META_PAGINATION_INVALID")
            cursor_data = paging.get("cursors", {})
            after = cursor_data.get("after") if isinstance(cursor_data, dict) else None
            if (
                not isinstance(after, str)
                or not 1 <= len(after) <= 2048
                or after in cursors
                or (checkpoint and after == checkpoint.after)
            ):
                fail("META_PAGINATION_INVALID")
            try:
                pairs = parse_qsl(url.query, strict_parsing=True)
                query = dict(pairs)
            except ValueError:
                fail("META_PAGINATION_INVALID")
            if len(pairs) != len(query) or query.get("after") != after:
                fail("META_PAGINATION_INVALID")
            if pages >= 250:
                fail("META_PAGE_LIMIT")
            next_checkpoint = ReadCheckpoint(
                self.configuration.fingerprint,
                fingerprint,
                after,
                pages,
                count,
                cursors + (after,),
                keys + current_keys,
            )
        return ReadPage(
            items,
            next_checkpoint,
            next_checkpoint is None,
            self.configuration.fingerprint,
            fingerprint,
            hashlib.sha256(raw).hexdigest(),
            datetime.now(UTC),
        )

    async def accounts_page(self, *, edge="me", business_id=None, checkpoint=None):
        if edge == "me" and business_id is None:
            path = "me/adaccounts"
        elif edge in {"owned", "client"}:
            path = (
                external_id(business_id)
                + "/"
                + ("owned_ad_accounts" if edge == "owned" else "client_ad_accounts")
            )
        else:
            fail("META_REQUEST_INVALID")
        return await self._page(
            path, {"fields": ACCOUNT_FIELDS, "limit": "200"}, account_record, checkpoint=checkpoint
        )

    async def account_page(self, account_id):
        """账户元数据也保留实际响应摘要，供worker原子暂存与来源复验。"""
        account_id = external_id(account_id)
        path, params = "act_" + account_id, {"fields": ACCOUNT_FIELDS}
        value, raw = await self._request("GET", path, params)
        result = account_record(value)
        if result["account_id"] != account_id:
            fail("META_ACCOUNT_MISMATCH")
        return ReadPage(
            (result,),
            None,
            True,
            self.configuration.fingerprint,
            self.fingerprint(path, params),
            hashlib.sha256(raw).hexdigest(),
            datetime.now(UTC),
        )

    async def account(self, account_id):
        return (await self.account_page(account_id)).items[0]

    async def account_extras(self, account_id, *, principal=False):
        """可选字段独立读取；字段无权限不影响基础账户，认证/限流/撤权仍传播。"""
        account_id = external_id(account_id)
        result = {}
        for field in OPTIONAL_FIELDS:
            try:
                row, _ = await self._request(
                    "GET", "act_" + account_id, {"fields": "id,account_id," + field}
                )
            except MetaReadFailure as error:
                if error.code in {"META_READ_FORBIDDEN", "META_READ_REJECTED"}:
                    continue
                raise
            if row.get("id") != "act_" + account_id or row.get("account_id") != account_id:
                fail("META_ACCOUNT_MISMATCH")
            key = field.split("{")[0]
            result[key] = row.get(key)
        person = None
        if principal:
            try:
                row, _ = await self._request("GET", "me", {"fields": "id,name"})
                person = {"id": external_id(row.get("id")), "name": optional_text(row.get("name"))}
            except MetaReadFailure as error:
                if error.code not in {"META_READ_FORBIDDEN", "META_READ_REJECTED"}:
                    raise
        return result, person

    async def structure_page(self, account_id, kind, *, checkpoint=None):
        account_id = external_id(account_id)
        if kind not in STRUCTURE_FIELDS:
            fail("META_REQUEST_INVALID")

        def normalize(row):
            if row.get("account_id") != account_id:
                fail("META_ACCOUNT_MISMATCH")
            result = {"id": external_id(row.get("id")), "account_id": account_id, "kind": kind}
            for name in (
                "name",
                "status",
                "effective_status",
                "objective",
                "optimization_goal",
                "billing_event",
                "updated_time",
            ):
                result[name] = optional_text(row.get(name))
            for name in ("campaign_id", "adset_id"):
                required = (
                    name == "campaign_id"
                    and kind in {"ADSET", "AD"}
                    or name == "adset_id"
                    and kind == "AD"
                )
                result[name] = external_id(row.get(name)) if required else None
            for name in ("daily_budget", "lifetime_budget"):
                result[name + "_minor"] = decimal_value(row.get(name), integer=True)
            return result

        return await self._page(
            "act_"
            + account_id
            + "/"
            + {"CAMPAIGN": "campaigns", "ADSET": "adsets", "AD": "ads"}[kind],
            {"fields": STRUCTURE_FIELDS[kind], "limit": "200"},
            normalize,
            checkpoint=checkpoint,
        )

    def _insight_parameters(self, window, level, attribution):
        if not isinstance(attribution, MetaAttribution):
            fail("META_REQUEST_INVALID")
        if not isinstance(window, InsightWindow) or level not in {
            "account",
            "campaign",
            "adset",
            "ad",
        }:
            fail("META_REQUEST_INVALID")
        return {
            "fields": INSIGHT_FIELDS,
            "limit": "200",
            "level": level,
            **window.parameters(),
            **attribution.parameters(),
        }

    def _insight_normalizer(self, account_id, window, level, attribution):
        def normalize(row):
            from datetime import date

            if row.get("account_id") != account_id:
                fail("META_ACCOUNT_MISMATCH")
            try:
                start = date.fromisoformat(row["date_start"])
                stop = date.fromisoformat(row["date_stop"])
            except (ValueError, TypeError, KeyError):
                fail()
            if start != stop or not window.since <= start <= window.until:
                fail()
            result = {
                "account_id": account_id,
                "date_start": start.isoformat(),
                "date_stop": stop.isoformat(),
                "timezone_name": window.timezone_name,
                "level": level,
            }
            for name in ("campaign_id", "adset_id", "ad_id"):
                required = (
                    name == "campaign_id"
                    and level in {"campaign", "adset", "ad"}
                    or name == "adset_id"
                    and level in {"adset", "ad"}
                    or name == "ad_id"
                    and level == "ad"
                )
                result[name] = external_id(row.get(name)) if required else None
            currency = row.get("account_currency")
            if currency is not None and (
                not isinstance(currency, str) or re.fullmatch("[A-Z]{3}", currency) is None
            ):
                fail()
            result["currency"] = currency
            result["spend"] = decimal_value(row.get("spend"))
            for name in ("impressions", "clicks", "reach"):
                result[name] = decimal_value(row.get(name), integer=True)
            for name in ("actions", "action_values"):
                values = row.get(name)
                if values is None:
                    result[name] = None
                    continue
                if not isinstance(values, list) or len(values) > 500:
                    fail()
                normalized = []
                seen = set()
                for action in values:
                    if not isinstance(action, dict):
                        fail()
                    action_type = optional_text(action.get("action_type"))
                    if not action_type or action_type in seen:
                        fail()
                    seen.add(action_type)
                    normalized.append(
                        {
                            "action_type": action_type,
                            "value": decimal_value(action.get("value")),
                            "attribution_values": {
                                w: decimal_value(action.get(w)) for w in attribution.windows
                            },
                        }
                    )
                result[name] = normalized
            return result

        return normalize

    async def insights_page(
        self, account_id, window, *, attribution=None, level="ad", checkpoint=None
    ):
        account_id = external_id(account_id)
        return await self._page(
            "act_" + account_id + "/insights",
            self._insight_parameters(window, level, attribution),
            self._insight_normalizer(account_id, window, level, attribution),
            checkpoint=checkpoint,
            extra=[window.timezone_name, attribution.fingerprint],
            key=lambda row: canonical(
                [
                    row["date_start"],
                    row["account_id"],
                    row["campaign_id"],
                    row["adset_id"],
                    row["ad_id"],
                ]
            ),
        )

    async def start_report(self, account_id, window, *, attribution=None, level="ad"):
        account_id = external_id(account_id)
        params = self._insight_parameters(window, level, attribution)
        path = "act_" + account_id + "/insights"
        value, _ = await self._request("POST", path, params)
        try:
            report_id = external_id(value.get("report_run_id"))
        except MetaReadFailure:
            fail("META_REPORT_START_UNKNOWN")
        return AsyncReport(
            report_id,
            account_id,
            self.configuration.fingerprint,
            self.fingerprint(path, params, [window.timezone_name, attribution.fingerprint]),
            window,
            level,
            attribution,
        )

    def _report(self, report):
        if (
            not isinstance(report, AsyncReport)
            or report.source_fingerprint != self.configuration.fingerprint
        ):
            fail("META_CHECKPOINT_MISMATCH")
        external_id(report.report_run_id)
        external_id(report.account_id)
        params = self._insight_parameters(report.window, report.level, report.attribution)
        if report.request_fingerprint != self.fingerprint(
            "act_" + report.account_id + "/insights",
            params,
            [report.window.timezone_name, report.attribution.fingerprint],
        ):
            fail("META_CHECKPOINT_MISMATCH")

    async def report_status(self, report):
        self._report(report)
        value, _ = await self._request(
            "GET",
            report.report_run_id,
            {"fields": "id,account_id,async_status,async_percent_completion"},
        )
        if value.get("id") != report.report_run_id or value.get("account_id") != report.account_id:
            fail("META_ACCOUNT_MISMATCH")
        state = value.get("async_status")
        percent = value.get("async_percent_completion")
        if type(percent) is not int or not 0 <= percent <= 100:
            fail()
        if state in {"Job Failed", "Job Skipped"}:
            fail("META_REPORT_FAILED")
        if state not in {"Job Not Started", "Job Started", "Job Running", "Job Completed"}:
            fail()
        return ReportStatus(state, percent, state == "Job Completed" and percent == 100)

    async def report_page(self, report, *, checkpoint=None):
        status = await self.report_status(report)
        if not status.complete:
            fail("META_REPORT_NOT_READY", retryable=True)
        return await self._page(
            report.report_run_id + "/insights",
            {"fields": INSIGHT_FIELDS, "limit": "200"},
            self._insight_normalizer(
                report.account_id, report.window, report.level, report.attribution
            ),
            checkpoint=checkpoint,
            extra=report.request_fingerprint,
            key=lambda row: canonical(
                [
                    row["date_start"],
                    row["account_id"],
                    row["campaign_id"],
                    row["adset_id"],
                    row["ad_id"],
                ]
            ),
        )
