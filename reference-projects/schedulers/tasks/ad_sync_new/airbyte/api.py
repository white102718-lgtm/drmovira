"""Ported from airbyte source-facebook-marketing/api.py.

Changes vs upstream:
  - `API.__init__` now takes app_id / app_secret / access_token / proxies so it
    can build a `FacebookSession` with this project's socks5 proxy. Upstream
    only takes access_token because airbyte uses a different auth flow.
  - `API.get_account` no longer prepends 'act_' (this project's account_id
    fields already include the prefix).
  - `_find_account` fetches more fields than upstream (timezone_name only),
    matching what fb_account_consumer needs.

MyFacebookAdsApi (rate-limit-aware FacebookAdsApi subclass) is verbatim,
**except** `_handle_call_rate_limit` 在 usage > 50% 时打一行 INFO,把响应头
`x-business-use-case-usage` / `x-app-usage` / `x-ad-account-usage` 完整 dump 出来。
原版只在 ≥85% 时 warning,看不到 17/2446079 撞墙前的水位走势。
"""

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from time import sleep
from typing import Dict, Optional

import backoff
import requests
from facebook_business import FacebookAdsApi, FacebookSession
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.api import FacebookResponse
from facebook_business.exceptions import FacebookRequestError
from requests.adapters import HTTPAdapter

from .common import retry_pattern


# 单进程 30 worker 并发跑同一个 dev 时,FacebookSession 默认 requests.Session
# 连接池 pool_maxsize=10 会被打爆 ("Connection pool is full, discarding connection")。
# 多余连接被丢弃后每次重建 TCP+TLS 握手,性能下降。提到 128 留足并发余量。
_FB_HTTP_POOL_SIZE = 128



logger = logging.getLogger(__name__)


class FacebookAPIException(Exception):
    """General class for all API errors"""


backoff_policy = retry_pattern(
    backoff.expo,
    # 加 requests.ConnectionError:30 worker 并发时 socks5 proxy 偶发
    # TCP RST (WinError 10054),retry 5 次能恢复
    # 加 ChunkedEncodingError:FB 偶发把响应流中途掐断(IncompleteRead),
    # 它不是 ConnectionError 子类,得单列才能 retry
    (
        FacebookRequestError,
        requests.exceptions.ConnectionError,
        requests.exceptions.ChunkedEncodingError,
    ),
    max_tries=5,
    factor=5,
)


class MyFacebookAdsApi(FacebookAdsApi):
    """Custom Facebook API class to intercept all API calls and handle call rate limits"""

    MAX_RATE, MAX_PAUSE_INTERVAL = (95, timedelta(minutes=10))
    MIN_RATE, MIN_PAUSE_INTERVAL = (85, timedelta(minutes=2))

    # see `_should_restore_page_size` method docstring for more info.
    # attribute to handle the reduced request limit
    request_record_limit_is_reduced: bool = False
    # attribute to save the status of the last successful call
    last_api_call_is_successful: bool = False

    @dataclass
    class Throttle:
        """Utilization of call rate in %, from 0 to 100"""

        per_application: float
        per_account: float

    # Insights async jobs throttle (default 0/0 until first /insights call updates it)
    _ads_insights_throttle: Throttle = Throttle(per_application=0.0, per_account=0.0)

    # FB 在 x-ad-account-usage / x-business-use-case-usage 的 JSON 里返回的
    # ads_api_access_tier 字段,值是 "development_access" / "standard_access" 等。
    # 第一次 API 调用之后缓存住,dispatcher 调 _list_account_ids 后即可读到。
    _ads_api_access_tier: Optional[str] = None

    @property
    def ads_insights_throttle(self) -> Throttle:
        return self._ads_insights_throttle

    @property
    def ads_api_access_tier(self) -> Optional[str]:
        return self._ads_api_access_tier

    @staticmethod
    def _parse_call_rate_header(headers):
        usage = 0
        pause_interval = timedelta()

        usage_header_business = headers.get("x-business-use-case-usage")
        usage_header_app = headers.get("x-app-usage")
        usage_header_ad_account = headers.get("x-ad-account-usage")

        if usage_header_ad_account:
            usage_header_ad_account_loaded = json.loads(usage_header_ad_account)
            usage = max(usage, float(usage_header_ad_account_loaded.get("acc_id_util_pct", 0)))

        if usage_header_app:
            usage_header_app_loaded = json.loads(usage_header_app)
            usage = max(
                usage,
                float(usage_header_app_loaded.get("call_count", 0)),
                float(usage_header_app_loaded.get("total_time", 0)),
                float(usage_header_app_loaded.get("total_cputime", 0)),
            )

        if usage_header_business:
            usage_header_business_loaded = json.loads(usage_header_business)
            for business_object_id in usage_header_business_loaded:
                usage_limits = usage_header_business_loaded.get(business_object_id)[0]
                usage = max(
                    usage,
                    float(usage_limits.get("call_count", 0)),
                    float(usage_limits.get("total_cputime", 0)),
                    float(usage_limits.get("total_time", 0)),
                )
                pause_interval = max(
                    pause_interval,
                    timedelta(minutes=usage_limits.get("estimated_time_to_regain_access", 0)),
                )

        return usage, pause_interval

    def _compute_pause_interval(self, usage, pause_interval):
        """The sleep time will be calculated based on usage consumed."""
        if usage >= self.MAX_RATE:
            return max(self.MAX_PAUSE_INTERVAL, pause_interval)
        return max(self.MIN_PAUSE_INTERVAL, pause_interval)

    def _get_max_usage_pause_interval_from_batch(self, records):
        usage = 0
        pause_interval = self.MIN_PAUSE_INTERVAL

        for record in records:
            # there are two types of failures:
            # 1. no response (we execute batch until all inner requests has response)
            # 2. response with error (we crash loudly)
            # in case it is failed inner request the headers might not be present
            if "headers" not in record:
                continue
            headers = {header["name"].lower(): header["value"] for header in record["headers"]}
            (
                usage_from_response,
                pause_interval_from_response,
            ) = self._parse_call_rate_header(headers)
            usage = max(usage, usage_from_response)
            pause_interval = max(pause_interval_from_response, pause_interval)
        return usage, pause_interval

    def _handle_call_rate_limit(self, response, params):
        if "batch" in params:
            records = response.json()
            usage, pause_interval = self._get_max_usage_pause_interval_from_batch(records)
            buc = app = acc = "<batch>"
        else:
            headers = response.headers()
            usage, pause_interval = self._parse_call_rate_header(headers)
            buc = headers.get("x-business-use-case-usage")
            app = headers.get("x-app-usage")
            acc = headers.get("x-ad-account-usage")
            # 抽 ads_api_access_tier 缓存,供 dispatcher 在分发前判断 tier。
            # FB 不同端点返不同 header:
            #   - /me/adaccounts(user-level)只返 x-business-use-case-usage
            #   - /<ad_account>/<edge>(ad-account-level)返 x-ad-account-usage
            # 两个 header 都可能带 ads_api_access_tier,有哪个就用哪个。
            # 没拿到时保留旧值不被 None 覆盖。
            if acc:
                tier = json.loads(acc).get("ads_api_access_tier")
                if tier:
                    self._ads_api_access_tier = tier
            if not self._ads_api_access_tier and buc:
                buc_loaded = json.loads(buc)
                for business_id, buckets in buc_loaded.items():
                    if not buckets:
                        continue
                    tier = buckets[0].get("ads_api_access_tier")
                    if tier:
                        self._ads_api_access_tier = tier
                        break

        # 非 verbatim:usage > 50% 才打,观察撞墙前的水位走势,低水位静默
        if usage > 50:
            logger.info("FB usage=%s%% buc=%s app=%s acc=%s", usage, buc, app, acc)

        if usage >= self.MIN_RATE:
            sleep_time = self._compute_pause_interval(usage=usage, pause_interval=pause_interval)
            logger.warning(f"Facebook API Utilization is too high ({usage})%, pausing for {sleep_time}")
            sleep(sleep_time.total_seconds())

    @staticmethod
    def _to_float(value, default: float = 0.0) -> float:
        # FB 偶发把 util_pct 返成 "unknown" 等非数字字符串,转不动按 default(=无压力)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _update_insights_throttle_limit(self, response: FacebookResponse):
        """
        For /insights call every response contains x-fb-ads-insights-throttle
        header representing current throttle limit parameter for async insights
        jobs for current app/account.  We need this information to adjust
        number of running async jobs for optimal performance.
        """
        ads_insights_throttle = response.headers().get("x-fb-ads-insights-throttle")
        if ads_insights_throttle:
            ads_insights_throttle = json.loads(ads_insights_throttle)
            self._ads_insights_throttle = self.Throttle(
                per_application=self._to_float(ads_insights_throttle.get("app_id_util_pct", 0)),
                per_account=self._to_float(ads_insights_throttle.get("acc_id_util_pct", 0)),
            )

    def _should_restore_default_page_size(self, params):
        """
        Track the state of the `request_record_limit_is_reduced` and `last_api_call_is_successful`,
        based on the logic from `@backoff_policy` (common.py > `reduce_request_record_limit` and `revert_request_record_limit`)
        """
        params = True if params else False
        return params and not self.request_record_limit_is_reduced and self.last_api_call_is_successful

    # FB 偶发对正常请求返回 200,但 body 是个 JSON 字符串而不是对象 / 批量元素,
    # 触发下游 parse_single / batch 解析抛 TypeError / AttributeError。
    # batch 两种坏形状都算:整个 body 是裸字符串,或 list 里混了字符串元素 —— 后者
    # 就是 FacebookAdsApiBatch.execute() 里 response.get('body') 炸 AttributeError 的元凶。
    @staticmethod
    def _has_bad_body(response, params) -> bool:
        try:
            data = response.json()
        except Exception:
            return False
        if params and "batch" in params:
            return isinstance(data, str) or (
                isinstance(data, list) and any(isinstance(x, str) for x in data)
            )
        return isinstance(data, str)

    @backoff_policy
    def call(
        self,
        method,
        path,
        params=None,
        headers=None,
        files=None,
        url_override=None,
        api_version=None,
    ):
        """Makes an API call, delegate actual work to parent class and handles call rates"""
        if self._should_restore_default_page_size(params):
            params.update(**{"limit": self.default_page_size})
        try:
            response = super().call(method, path, params, headers, files, url_override, api_version)
            if self._has_bad_body(response, params):
                logger.warning(
                    "FB 返回 bad body (非对象/批量元素是字符串),重试 method=%s path=%s body=%.500s",
                    method, path, response.json(),
                )
                response = super().call(method, path, params, headers, files, url_override, api_version)
        except FacebookRequestError as exc:
            # 17/2446079 撞墙时,backoff 的 ERROR 只带 Response body,看不到 header
            # 里的 BUC / app / acc / insights_throttle 真实水位 —— 把它们全 dump,
            # 方便定位是哪个桶撑爆(ads_management / ads_insights / app-level)。
            if exc.api_error_subcode() == 2446079:
                h = exc.http_headers() or {}
                logger.error(
                    "FB usage (on 2446079): buc=%s app=%s acc=%s insights_throttle=%s",
                    h.get("x-business-use-case-usage"),
                    h.get("x-app-usage"),
                    h.get("x-ad-account-usage"),
                    h.get("x-fb-ads-insights-throttle"),
                )
            raise
        self._update_insights_throttle_limit(response)
        self._handle_call_rate_limit(response, params)
        return response


class API:
    """Wrapper around Facebook API. Modified vs airbyte upstream to support
    app_id/app_secret + socks5 proxies (this project's auth flow)."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        access_token: str,
        proxies: Optional[Dict[str, str]] = None,
        page_size: int = 100,
    ):
        self._accounts: Dict[str, AdAccount] = {}
        # Build the rate-limit-aware FacebookAdsApi via session (so proxies stick).
        session = FacebookSession(
            app_id, app_secret, access_token, proxies=proxies
        )
        # 加大 requests.Session 连接池,支持多 worker 并发(默认 10 不够)
        adapter = HTTPAdapter(
            pool_connections=_FB_HTTP_POOL_SIZE, pool_maxsize=_FB_HTTP_POOL_SIZE,
        )
        session.requests.mount("https://", adapter)
        session.requests.mount("http://", adapter)
        self.api = MyFacebookAdsApi(session)
        # adding the default page size from config to the api base class
        # reference issue: https://github.com/airbytehq/airbyte/issues/25383
        setattr(self.api, "default_page_size", page_size)
        # set the default API client to Facebook lib.
        FacebookAdsApi.set_default_api(self.api)

    def get_account(self, account_id: str) -> AdAccount:
        """Get AdAccount object by id (cached). account_id may or may not include 'act_' prefix."""
        if account_id in self._accounts:
            return self._accounts[account_id]
        self._accounts[account_id] = self._find_account(account_id)
        return self._accounts[account_id]

    def _find_account(self, account_id: str) -> AdAccount:
        """Actual implementation of find account。绑定本实例 api,使 account 及其
        派生对象(get_insights / AdReportRun)不 fall back 到全局 default(并发下会串线程)。"""
        fbid = account_id if account_id.startswith("act_") else f"act_{account_id}"
        return AdAccount(fbid, api=self.api).api_get(fields=["timezone_name", "name", "account_status"])
