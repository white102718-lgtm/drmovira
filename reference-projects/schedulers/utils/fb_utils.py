import json
import logging
import os
import time
import traceback
from datetime import datetime
from functools import partial
from typing import Union, Dict, List
from zoneinfo import ZoneInfo

import requests
from facebook_business import FacebookSession
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.advideo import AdVideo
from facebook_business.adobjects.user import User
from facebook_business.api import FacebookAdsApi
from facebook_business.exceptions import FacebookRequestError

from conf.api_conf import get_proxies
from db.clients import erp_db
from utils.common import Developer, HourFormat

FB_VIDEO_ERROR_KEY_PREFIX = "ad_materials:fb_video_error"
FB_VIDEO_ERROR_TTL_SECONDS = 1 * 24 * 3600


# ============================================================
# FB API 用量埋点
# 提供两种接入方式:
#   1) install_fb_usage_backoff(): monkey-patch 全局 FacebookAdsApi.call,可选 auto_sleep 软退避。
#      其它 worker(scrape / fetch / 同步 consumer)走这条路保持原行为。
#   2) MonitoredFacebookAdsApi(FacebookAdsApi): 子类 + override call,纯观测、不退避。
#      异步 consumer 走这条路,避免 60 容器场景下集体 sleep。
# 两种方式不要在同一进程同时使用,会重复打日志。
# ============================================================


def _soft_backoff_seconds(peak: float) -> int:
    """70%→60s, 90%→600s,区间内线性插值;>=90% 夹紧到 600s。"""
    if peak < 70:
        return 0
    if peak >= 90:
        return 600
    return int(60 + (peak - 70) * 27)


def _log_fb_usage(headers) -> int:
    """解析 FB 用量 header,打日志,返回需要睡眠的秒数(0=不睡)。

    监控三类 header:
      - x-app-usage: app 级 call/cpu/time 用量百分比
      - x-business-use-case-usage: BUC(广告账户)级用量,带 estimated_time_to_regain_access
      - x-fb-ads-insights-throttle: insights 专属节流,字段 app_id_util_pct/acc_id_util_pct
        (FB 官方文档 marketing-api/insights/best-practices 明确以此 header 控制 insights 速率)
    """
    if not headers:
        return 0
    app_usage = headers.get("x-app-usage") or headers.get("X-App-Usage")
    biz_usage = headers.get("x-business-use-case-usage") or headers.get(
        "X-Business-Use-Case-Usage"
    )
    insights_throttle = headers.get("x-fb-ads-insights-throttle") or headers.get(
        "X-FB-Ads-Insights-Throttle"
    )

    peak = 0
    hard_ban_seconds = 0

    if app_usage:
        try:
            au = json.loads(app_usage) if isinstance(app_usage, str) else app_usage
            logging.info(
                f"[FB-USAGE][app] call={au.get('call_count', 0)}% "
                f"cpu={au.get('total_cputime', 0)}% "
                f"time={au.get('total_time', 0)}%"
            )
            peak = max(
                peak,
                au.get("call_count", 0) or 0,
                au.get("total_cputime", 0) or 0,
                au.get("total_time", 0) or 0,
            )
        except Exception as e:
            logging.warning(
                f"[FB-USAGE][app] 解析失败 err={e} raw={app_usage!r}",
                exc_info=True,
            )
    if biz_usage:
        try:
            bu = json.loads(biz_usage) if isinstance(biz_usage, str) else biz_usage
            for acct, entries in (bu or {}).items():
                for e in entries or []:
                    ban = e.get("estimated_time_to_regain_access", 0) or 0
                    line = (
                        f"[FB-USAGE][biz] acct={acct} type={e.get('type')} "
                        f"call={e.get('call_count', 0)}% "
                        f"cpu={e.get('total_cputime', 0)}% "
                        f"time={e.get('total_time', 0)}%"
                    )
                    if ban > 0:
                        logging.warning(f"{line} 🚨THROTTLED ban_in={ban}min")
                        hard_ban_seconds = max(hard_ban_seconds, ban * 60)
                    else:
                        logging.info(line)
                    peak = max(
                        peak,
                        e.get("call_count", 0) or 0,
                        e.get("total_cputime", 0) or 0,
                        e.get("total_time", 0) or 0,
                    )
        except Exception as e:
            logging.warning(
                f"[FB-USAGE][biz] 解析失败 err={e} raw={biz_usage!r}",
                exc_info=True,
            )

    # x-fb-ads-insights-throttle: insights 专属节流,>=100 会被硬限流;
    # 字段 app_id_util_pct / acc_id_util_pct 都参与 peak,任一接近 100 都减速
    if insights_throttle:
        try:
            it = (
                json.loads(insights_throttle)
                if isinstance(insights_throttle, str)
                else insights_throttle
            )
            app_pct = it.get("app_id_util_pct", 0) or 0
            acc_pct = it.get("acc_id_util_pct", 0) or 0
            tier = it.get("ads_api_access_tier", "")
            line = (
                f"[FB-USAGE][insights] app={app_pct}% acc={acc_pct}% tier={tier}"
            )
            if max(app_pct, acc_pct) >= 80:
                logging.warning(f"{line} 🚨INSIGHTS-THROTTLE")
            else:
                logging.info(line)
            peak = max(peak, app_pct, acc_pct)
        except Exception as e:
            logging.warning(
                f"[FB-USAGE][insights] 解析失败 err={e} raw={insights_throttle!r}",
                exc_info=True,
            )

    if hard_ban_seconds > 0:
        return hard_ban_seconds
    return _soft_backoff_seconds(peak)


def install_fb_usage_backoff(auto_sleep: bool = True) -> None:
    """安装 FacebookAdsApi.call 的用量日志包装(monkey-patch 方式).

    - 始终: 解析 X-App-Usage / X-Business-Use-Case-Usage 打用量日志,供 Grafana 告警
    - auto_sleep=True : 高用量时进程内 time.sleep 软退避(主下载 worker / scrape worker / scheduler 用)
    - auto_sleep=False: 只打日志不睡眠(同步 consumer 已有自己的 RetryBudget 机制,不要再加全局 sleep)

    每个进程调用一次,重复调用无害(以首次为准).
    各服务在自己的 main 入口处显式调用,避免模块级 import 副作用导致行为耦合.

    注: 异步 consumer 已改用 MonitoredFacebookAdsApi 子类,不再调用本函数。
    """
    if getattr(FacebookAdsApi.call, "_fb_usage_wrapped", False):
        return

    _original_fb_call = FacebookAdsApi.call

    def _logged_fb_call(self, *args, **kwargs):
        response = _original_fb_call(self, *args, **kwargs)
        sleep_seconds = 0
        try:
            sleep_seconds = _log_fb_usage(response.headers() if response else None)
        except Exception as e:
            logging.warning(f"[FB-USAGE] 日志埋点异常: {e}")
        if auto_sleep and sleep_seconds > 0:
            logging.warning(f"[FB-USAGE] 触发退避,睡眠 {sleep_seconds}s")
            time.sleep(sleep_seconds)
        return response

    _logged_fb_call._fb_usage_wrapped = True
    FacebookAdsApi.call = _logged_fb_call


class MonitoredFacebookAdsApi(FacebookAdsApi):
    """子类化 FacebookAdsApi,每次 call() 后解析用量 header 打日志(纯观测)。

    不修改任何调用行为(不退避、不重试、不 sleep);_log_fb_usage 的返回值在此忽略。
    适合 60 容器异步 consumer 这种"不希望全局 sleep"的场景。
    业务进程把 FacebookAdsApi(session) 替换成 MonitoredFacebookAdsApi(session) 即生效;
    set_default_api(api) 仍用 FacebookAdsApi.set_default_api(api) 写法,保证 SDK 内部
    通过 FacebookAdsApi.get_default_api() 能取到子类实例。
    """

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
        response = super().call(
            method, path, params, headers, files, url_override, api_version
        )
        try:
            _log_fb_usage(response.headers() if response else None)
        except Exception as e:
            logging.warning(f"[FB-USAGE] 日志埋点异常: {e}")
        return response


def get_best_video_source(video_id, ad_id):
    if not video_id:
        return None

    try:
        video = AdVideo(video_id)
        # Use SDK to get fields
        data = video.api_get(fields=["source", "format{width,bitrate,url}"])

        # Data is already a dict-like object (AbstractObject)
        formats = data.get("format", [])

        # Filter formats that have a valid 'url'
        valid_formats = [f for f in formats if f.get("url")]

        # 选择最高质量视频：先比宽度，再比码率
        if valid_formats:
            best = max(
                valid_formats, key=lambda f: (f.get("width", 0), f.get("bitrate", 0))
            )
            return best.get("url")

        # fallback to source if no format found
        if "source" in data:
            return data["source"]

        logging.warning(
            f"[⚠️] No video URL found in formats or source for video {video_id}. Formats: {len(formats)}"
        )
        return None

    except FacebookRequestError:
        # 不在这里标记 Redis 错误去重: 主流程失败会走 Playwright 兜底,
        # 由 ad_creative_scrape_worker 在 Playwright 也拿不到 URL 时才标记
        logging.error(f"[❌] Facebook API Error: {traceback.format_exc()}")
        return None
    except Exception as e:
        logging.warning(f"[⚠️] 获取视频 info 失败: {e}")
        return None


def _prepare_params(fields, default_fields, params):
    if fields is None:
        fields = default_fields
    if params is None:
        params = {"limit": 1000}
    elif "limit" not in params:
        params["limit"] = 1000
    return fields, params


TZ_ALIAS = {
    "Asia/Calcutta": "Asia/Kolkata",
    "EST": "America/New_York",
    "Asia/Choibalsan": "Asia/Ulaanbaatar",
    "CST6CDT": "America/Chicago",
    "America/Buenos_Aires": "America/Argentina/Buenos_Aires",
    "Asia/Macao": "Asia/Shanghai",
}


def resolve_tz(timezone_name: str) -> ZoneInfo:
    return ZoneInfo(TZ_ALIAS.get(timezone_name, timezone_name))


def change_date(china_date: Union[datetime, str], timezone_name):
    if isinstance(china_date, str):
        dt = datetime.strptime(china_date, HourFormat)
        china_date = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return china_date.astimezone(resolve_tz(timezone_name))


class FacebookAdsHelper:

    def __init__(self, dev: Developer):
        self._dev = dev

    def set_proxy(
        self,
        proxy=None,
        app_id=None,
        app_secret=None,
        access_token=None,
        username=os.environ["PROXY_USER"],
        password=os.environ["PROXY_PASS"],
        port=int(os.environ["PROXY_PORT"]),
    ):
        if proxy is None:
            proxy = self._dev["proxy"]
        if proxy is None:
            raise ValueError(f"proxy is None for dev: {self._dev.get('app_id')}")
        if app_id is None:
            app_id = self._dev["app_id"]
        if app_secret is None:
            app_secret = self._dev["app_secret"]
        if access_token is None:
            access_token = self._dev["access_token"]
        proxy = f"socks5://{username}:REDACTED_REFERENCE_SECRET@{proxy}:{port}"
        proxies = {"http": proxy, "https": proxy}
        session = FacebookSession(
            app_id,
            app_secret,
            access_token,
            proxies=proxies,
        )
        api = FacebookAdsApi(session)
        FacebookAdsApi.set_default_api(api)
        return api

    @staticmethod
    def get_accounts(api=None, fields=None, params=None):
        fields, params = _prepare_params(fields, ["account_id", "name"], params)
        me = User(fbid="me", api=api)
        accounts = me.get_ad_accounts(fields=fields, params=params)
        time.sleep(5)
        return accounts

    @staticmethod
    def get_campaigns(account, fields=None, params=None):
        fields, params = _prepare_params(fields, ["id", "name"], params)
        campaigns = list(account.get_campaigns(fields=fields, params=params))
        time.sleep(5)
        return campaigns

    @staticmethod
    def get_ad_sets(campaign, fields=None, params=None):
        fields, params = _prepare_params(fields, ["id", "name"], params)
        ad_sets = campaign.get_ad_sets(fields=fields, params=params)
        time.sleep(5)
        return ad_sets

    @staticmethod
    def get_ads(ad_set, fields=None, params=None):
        fields, params = _prepare_params(fields, ["id", "name"], params)
        ads = ad_set.get_ads(fields=fields, params=params)
        time.sleep(5)
        return ads


def download_ad_creatives_to_memory(ad_ids, dev):
    """
    根据 ad_id 列表下载广告创意素材到内存（生成器版本，防止内存溢出）

    Args:
        ad_ids: 广告ID列表，必须是字符串列表，如 ["123", "456", "789"]
        dev: 开发者信息字典，包含:
            - app_id: Facebook App ID
            - app_secret: Facebook App Secret
            - access_token: Facebook Access Token
            - proxy: 代理服务器地址（可选）

    Yields:
        元组 (ad_id, content, extension)，其中:
        - content: 文件内容（bytes）或 None（下载失败）
        - extension: 文件扩展名（"jpg" 或 "mp4"）或 None
    """

    proxies = get_proxies(dev["proxy"])

    def download_to_memory(url):
        """下载文件到内存并返回二进制内容"""
        try:
            response = requests.get(url, proxies=proxies, timeout=120)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logging.warning(f"⚠️ 下载失败 {url}: {e}")
            return None

    # 设置代理和 API
    session = FacebookSession(
        dev["app_id"],
        dev["app_secret"],
        dev["access_token"],
        proxies=proxies,
    )
    api = FacebookAdsApi(session)
    FacebookAdsApi.set_default_api(api)

    # 记录已处理的广告ID
    yielded_ad_ids = set()

    # 分批处理：批量获取 creative_id，然后立即获取详情并下载
    batch_num = 10
    for i in range(0, len(ad_ids), batch_num):
        chunk = ad_ids[i : i + batch_num]

        # Step 1: 批量获取这一批的 creative_id
        batch_ad_to_creative = []

        def on_creative_success(response, ad_id):
            data = response.json()
            creative = data.get("creative") or {}
            batch_ad_to_creative.append(
                {
                    "ad_id": ad_id,
                    "image_url": creative.get("image_url"),
                    "object_story_spec": creative.get("object_story_spec"),
                }
            )

        def on_creative_failure(response, ad_id):
            logging.warning(
                f"⚠️ 获取广告 {ad_id} 的 creative_id 失败: {response.error()}"
            )

        batch = api.new_batch()
        for ad_id in chunk:
            ad = Ad(ad_id)
            ad.api_get(
                fields=[
                    "creative{image_url,object_story_spec{video_data{video_id},link_data{picture}}}"
                ],
                batch=batch,
                success=partial(on_creative_success, ad_id=ad_id),
                failure=partial(on_creative_failure, ad_id=ad_id),
            )

        batch.execute()

        # Step 2: 立即下载这一批的文件并 yield（不等所有批次完成）
        for result in batch_ad_to_creative:
            ad_id = result["ad_id"]
            media_url = None
            extension = "jpg"  # Default to jpg

            # 优先使用 image_url
            if result.get("image_url"):
                media_url = result["image_url"]
            # 尝试从 object_story_spec 中获取视频 URL
            elif result.get("object_story_spec"):
                story_spec = result["object_story_spec"]
                # 尝试获取视频链接
                if "video_data" in story_spec:
                    video_data = story_spec["video_data"]
                    video_id = video_data.get("video_id")
                    if video_id:
                        media_url = get_best_video_source(video_id, ad_id=ad_id)
                        if media_url:
                            extension = "mp4"
                # 尝试获取链接数据中的图片
                elif "link_data" in story_spec:
                    link_data = story_spec["link_data"]
                    media_url = link_data.get("picture")

            # 下载文件并立即 yield 返回
            if media_url:
                content = download_to_memory(media_url)
                yielded_ad_ids.add(ad_id)
                yield ad_id, content, extension
            else:
                logging.warning(f"⚠️ 广告 {ad_id} 没有找到可下载的媒体 URL")
                yielded_ad_ids.add(ad_id)
                yield ad_id, None, None

        # 处理这一批中没有获取到 creative_id 的广告
        batch_ad_ids = set(chunk)
        for ad_id in batch_ad_ids:
            if ad_id not in yielded_ad_ids:
                yielded_ad_ids.add(ad_id)
                yield ad_id, None, None

        # 清理这一批的临时数据，释放内存
        batch_ad_to_creative = []


def get_channel_account_mapping() -> Dict[str, List[str]]:
    """
    从 ERP 获取渠道与账户的映射关系

    Returns:
        Dict[channel_id, List[account_ids]] - 渠道ID到账户ID列表的映射（账户ID无 act_ 前缀，与 Doris 一致）
    """
    sql = """
    SELECT ca.channel_id, ca.fb_account_id
    FROM fbad_channel_account ca
    """
    results = erp_db.read(sql)

    mapping = {}
    for row in results:
        channel_id = str(row[0])
        account_id = str(row[1])
        if channel_id not in mapping:
            mapping[channel_id] = []
        mapping[channel_id].append(account_id)

    return mapping


def get_channel_names(channel_ids: List[str]) -> Dict[str, str]:
    """
    获取渠道ID与名称的映射

    Returns:
        Dict[channel_id, channel_name]
    """
    normalized_channel_ids = []
    for channel_id in channel_ids or []:
        normalized_channel_id = str(channel_id).strip()
        if normalized_channel_id:
            normalized_channel_ids.append(normalized_channel_id)

    normalized_channel_ids = list(dict.fromkeys(normalized_channel_ids))
    if not normalized_channel_ids:
        return {}

    quoted_channel_ids = ", ".join(
        "'" + channel_id.replace("'", "''") + "'"
        for channel_id in normalized_channel_ids
    )
    sql = f"""
    SELECT id, channel_name
    FROM fbad_channel
    WHERE id IN ({quoted_channel_ids})
    """

    results = erp_db.read(sql)
    return {
        str(row[0]).strip(): (row[1] or "").strip()
        for row in results
        if row[0] is not None and (row[1] or "").strip()
    }


if __name__ == "__main__":
    china_time_str = "2024-01-01 03"
    india_time = change_date(china_time_str, "Asia/Calcutta")
    shanghai_time = change_date(india_time, "Asia/Shanghai")
    print(india_time, "Back to Shanghai:", shanghai_time)
