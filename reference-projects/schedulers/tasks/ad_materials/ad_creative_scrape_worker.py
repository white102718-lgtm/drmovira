"""
广告素材 URL 抓取 worker (Redis 队列消费者)

当主下载流程 (utils/fb_utils.py) 遇到 "没有找到可下载的媒体 URL" 时，
把 ad_id 及上下文推入 Redis 队列 AD_CREATIVE_FETCH_QUEUE_KEY，
由本 worker 异步消费：

1. 用 Graph API (SDK, 走代理) 调 /{ad_id}/previews 拿预览 iframe URL
2. Playwright 打开 iframe (不走代理, 走本地网络)，
   监听网络请求捕获真实 mp4 / 图片 URL
3. 下载文件 (本地网络) → 调用 _save_material_sync 保存到 backend

注：不再做基于 creative 字段的轻量 fallback —— 那些应该由主流程负责，
能进队列的就只剩 Playwright 兜底这条路。

Redis 消息 schema 定义在 model_type_defs.ad_materials_type.AdCreativeFetchMessage，
配套队列名常量 AD_CREATIVE_FETCH_QUEUE_KEY。

用法:
    python -m tasks.ad_materials.ad_creative_scrape_worker
"""

import json
import logging
import re
import time
import traceback
from datetime import datetime
from typing import Optional, Tuple

import requests
from facebook_business import FacebookSession
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adpreview import AdPreview
from facebook_business.api import FacebookAdsApi
from playwright.sync_api import sync_playwright

from conf.api_conf import get_proxies
from conf.log_conf import init
from db.clients import redis_cli_1 as redis_cli
from model_type_defs.ad_materials_type import (
    AD_CREATIVE_FETCH_QUEUE_KEY,
    AdCreativeFetchMessage,
    FbDevApp,
)
from tasks.ad_materials.ad_materials_sync import (
    _save_material_sync,
    release_fetch_pending_locks,
    update_doris_unique_names_batch,
)
from utils.fb_utils import (
    FB_VIDEO_ERROR_KEY_PREFIX,
    FB_VIDEO_ERROR_TTL_SECONDS,
    install_fb_usage_backoff,
)

init("ad_creative_scrape_worker")


BLPOP_TIMEOUT_SECONDS = 5
PLAYWRIGHT_GOTO_TIMEOUT_MS = 30000
# domcontentloaded 后媒体走 JS 异步加载，抓到就立即返回，最多等到 MAX
PLAYWRIGHT_MAX_WAIT_MS = 15000
PLAYWRIGHT_POLL_INTERVAL_MS = 500

_VIDEO_CDN_KEYWORDS = (".mp4",)
_IMAGE_EXT_KEYWORDS = (".jpg", ".jpeg", ".png", ".webp")

# 抓取失败累计到 FB_VIDEO_FAIL_MAX_ATTEMPTS 次才进去重集合(1 天内不再重试)
FB_VIDEO_FAIL_COUNT_KEY_PREFIX = "ad_materials:fb_video_fail_count"
FB_VIDEO_FAIL_MAX_ATTEMPTS = 2

# 单条消息内即时重试:首次 + 最多重试 2 次
SCRAPE_MAX_ATTEMPTS = 3


# ============================================================
# Facebook API 初始化 (每条消息用独立 session，不共享全局 state)
# ============================================================


def _init_api(dev: FbDevApp) -> FacebookAdsApi:
    session = FacebookSession(
        dev["app_id"],
        dev["app_secret"],
        dev["access_token"],
        proxies=get_proxies(dev["proxy"]),
    )
    api = FacebookAdsApi(session)
    FacebookAdsApi.set_default_api(api)
    return api


def _mark_fb_video_error_ad_id(ad_id):
    if not ad_id:
        return
    try:
        count_key = f"{FB_VIDEO_FAIL_COUNT_KEY_PREFIX}:{ad_id}"
        attempts = redis_cli.incr(count_key)
        if attempts == 1:
            redis_cli.expire(count_key, FB_VIDEO_ERROR_TTL_SECONDS)
        if attempts < FB_VIDEO_FAIL_MAX_ATTEMPTS:
            logging.warning(f"[{ad_id}] 兜底抓取失败第 {attempts} 次,留待下个周期重试")
            return

        today = datetime.now().strftime("%Y%m%d")
        redis_key = f"{FB_VIDEO_ERROR_KEY_PREFIX}:{today}"
        redis_cli.sadd(redis_key, str(ad_id))
        # 仅在没有TTL时设置过期时间，避免每次写入都刷新TTL
        if redis_cli.ttl(redis_key) < 0:
            redis_cli.expire(redis_key, FB_VIDEO_ERROR_TTL_SECONDS)
        logging.warning(f"[{ad_id}] 兜底抓取失败第 {attempts} 次,标记 1 天内不再重试")
    except Exception as redis_err:
        logging.error(
            f"[⚠️] 记录视频错误去重 ad_id 失败: ad_id={ad_id}, err={redis_err}"
        )


def _fetch_iframe_src(ad_id: str) -> Optional[str]:
    """用 SDK 调 /{ad_id}/previews 拿预览 iframe 的 src (走 SDK 代理)。"""
    ad = Ad(ad_id)
    formats = ("MOBILE_FEED_STANDARD", "DESKTOP_FEED_STANDARD", "INSTAGRAM_STANDARD")
    fmt_status: list[str] = []
    for fmt in formats:
        try:
            previews = list(
                ad.get_previews(
                    fields=[AdPreview.Field.body],
                    params={"ad_format": fmt},
                )
            )
            if not previews:
                fmt_status.append(f"{fmt}=empty")
                continue
            body = previews[0].get(AdPreview.Field.body, "") or ""
            m = re.search(r'src="([^"]+preview_iframe\.php[^"]+)"', body)
            if m:
                src = m.group(1).replace("&amp;", "&")
                # business.facebook.com 需要 BM 登录 cookie，换成 www 绕过
                return src.replace("business.facebook.com", "www.facebook.com")
            fmt_status.append(f"{fmt}=no_iframe_in_body(body_len={len(body)})")
        except Exception as e:
            fmt_status.append(f"{fmt}={type(e).__name__}")
            logging.warning(f"[{ad_id}] get_previews({fmt}) 失败: {type(e).__name__}: {e}")
    logging.warning(
        f"[{ad_id}] 所有 ad_format 均未拿到 iframe URL: {fmt_status}"
    )
    return None


def _try_preview_iframe_playwright(ad_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Playwright 打开 iframe 监听网络请求抓 mp4 / 图片。

    Graph API 走 SDK 配置的 SOCKS5 代理；
    Playwright 本身不带代理，直接用容器/机器的本地网络访问 FB iframe 和 CDN。
    """
    iframe_src = _fetch_iframe_src(ad_id)
    if not iframe_src:
        # _fetch_iframe_src 已记录每个 ad_format 的具体失败原因
        return None, None

    logging.info(f"[{ad_id}] 拿到 iframe URL，启动 Playwright: {iframe_src[:160]}")

    captured_videos: list[str] = []
    captured_images: list[str] = []
    goto_ok = False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                page = context.new_page()

                def on_request(request):
                    url = request.url
                    if any(k in url for k in _VIDEO_CDN_KEYWORDS) or (
                        "video-" in url and "fbcdn" in url
                    ):
                        captured_videos.append(url)
                    elif any(k in url for k in _IMAGE_EXT_KEYWORDS) and "fbcdn" in url:
                        captured_images.append(url)

                page.on("request", on_request)

                # 拦截视频字节流，只要 URL 不要内容
                def _maybe_abort(route):
                    req_url = route.request.url
                    if (
                        req_url in captured_videos
                        and route.request.resource_type == "media"
                    ):
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", _maybe_abort)

                try:
                    page.goto(
                        iframe_src,
                        wait_until="domcontentloaded",
                        timeout=PLAYWRIGHT_GOTO_TIMEOUT_MS,
                    )
                    goto_ok = True
                except Exception as e:
                    logging.warning(
                        f"[{ad_id}] iframe goto 失败但继续: {type(e).__name__}: {e}"
                    )

                # 自适应等待:抓到真实视频才提前返回。视频广告会先出封面图(t15./v/t)，
                # 不能一见图片就 break，否则会把视频降级成封面图；只有图片时等满窗口兜底。
                waited = 0
                while waited < PLAYWRIGHT_MAX_WAIT_MS:
                    page.wait_for_timeout(PLAYWRIGHT_POLL_INTERVAL_MS)
                    waited += PLAYWRIGHT_POLL_INTERVAL_MS
                    if any(u.startswith("http") for u in captured_videos):
                        break

                # DOM 里直接取 video.src 作为补充
                video_src_from_dom = page.evaluate(
                    """() => {
                        const v = document.querySelector('video');
                        return v ? v.src || v.currentSrc : null;
                    }"""
                )
                if video_src_from_dom and video_src_from_dom.startswith("http"):
                    captured_videos.insert(0, video_src_from_dom)
            finally:
                browser.close()
    except Exception as e:
        logging.error(f"[{ad_id}] Playwright 异常: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None, None

    real_videos = [u for u in captured_videos if u.startswith("http")]
    main_images = [u for u in captured_images if "t15." in u or "/v/t" in u]

    if real_videos:
        return real_videos[0], "mp4"
    if main_images:
        return main_images[0], "jpg"

    sample_video = captured_videos[0][:120] if captured_videos else None
    sample_image = captured_images[0][:120] if captured_images else None
    logging.error(
        f"[{ad_id}] Playwright 抓取完成但未命中: goto_ok={goto_ok}, "
        f"videos_total={len(captured_videos)}(http={len(real_videos)}), "
        f"images_total={len(captured_images)}(t15或/v/t={len(main_images)}), "
        f"sample_video={sample_video}, sample_image={sample_image}"
    )
    return None, None


# ============================================================
# 下载 & 保存
# ============================================================


def _download_to_memory(url: str, proxy: str) -> Optional[bytes]:
    """下载媒体文件到内存。"""
    try:
        resp = requests.get(url, proxies=get_proxies(proxy), timeout=60)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        logging.warning(f"下载失败 {url[:80]}...: {e}")
        return None


def _process_message(msg: AdCreativeFetchMessage) -> bool:
    ad_id = msg["ad_id"]
    dev = msg["dev"]
    account_id = msg["account_id"]
    metadata = msg.get("metadata") or {}

    logging.info(
        f"开始处理 ad_id={ad_id} account_id={account_id} app_id={dev.get('app_id')} "
        f"proxy={dev.get('proxy')} token={dev.get('access_token', '')[:10]}... "
        f"ad_platform={metadata.get('ad_platform')}"
    )

    try:
        _init_api(dev)
    except Exception as e:
        logging.error(f"[{ad_id}] 初始化 FB API 失败: {e}")
        return False

    media_url, extension = None, None
    for attempt in range(1, SCRAPE_MAX_ATTEMPTS + 1):
        try:
            media_url, extension = _try_preview_iframe_playwright(ad_id)
        except Exception as e:
            logging.error(
                f"[{ad_id}] Playwright 抓取异常(第 {attempt}/{SCRAPE_MAX_ATTEMPTS} 次): {e}"
            )
            traceback.print_exc()
        if media_url:
            break
        if attempt < SCRAPE_MAX_ATTEMPTS:
            logging.warning(
                f"[{ad_id}] 未拉取到素材,重试(第 {attempt}/{SCRAPE_MAX_ATTEMPTS} 次)"
            )

    if not media_url:
        # 具体失败原因 (iframe 拿不到 / Playwright 未命中 / Playwright 异常)
        # 已经在 _fetch_iframe_src / _try_preview_iframe_playwright 内部 log 了
        _mark_fb_video_error_ad_id(ad_id)
        return False
    logging.info(f"[{ad_id}] Playwright 命中: ext={extension}")

    content = _download_to_memory(media_url, dev["proxy"])
    if not content:
        return False

    unique_name = metadata.get("unique_name") or f"ad_{ad_id}"
    try:
        saved_name = _save_material_sync(
            file_content=content,
            unique_name=unique_name,
            metadata={**metadata, "ad_id": ad_id, "account_id": account_id},
            extension=extension,
        )
        logging.info(f"✅ [{ad_id}] MongoDB 保存成功: {unique_name} -> {saved_name}")
    except Exception as e:
        logging.error(f"[{ad_id}] 保存 MongoDB 失败: {e}")
        return False

    if not saved_name:
        logging.warning(f"[{ad_id}] 未拿到 saved_name(素材可能已存在),跳过 Doris 更新")
        return False

    unique_key_tuple = (
        metadata.get("date"),
        metadata.get("ad_platform"),
        metadata.get("timezone_name"),
        account_id,
        metadata.get("campaign_id"),
        metadata.get("ad_set_id"),
        ad_id,
    )
    try:
        update_doris_unique_names_batch({unique_key_tuple: saved_name})
        logging.info(f"✅ [{ad_id}] Doris unique_name 更新完成 -> {saved_name}")
        release_fetch_pending_locks([ad_id])
        return True
    except Exception as e:
        logging.error(f"[{ad_id}] 更新 Doris 失败: {e}")
        return False


# ============================================================
# Redis 队列消费循环
# ============================================================


def _pop_one(
    queue_name: str = AD_CREATIVE_FETCH_QUEUE_KEY,
    timeout: int = BLPOP_TIMEOUT_SECONDS,
) -> Optional[AdCreativeFetchMessage]:
    try:
        result = redis_cli.blpop(queue_name, timeout=timeout)
    except Exception as e:
        logging.error(f"Redis BLPOP 异常: {e}")
        time.sleep(1)
        return None

    if not result:
        return None

    _, payload = result
    try:
        return json.loads(
            payload.decode("utf-8") if isinstance(payload, bytes) else payload
        )
    except Exception as e:
        logging.error(f"消息 JSON 解析失败: {e}, raw={payload!r}")
        return None


def main():
    # scrape 兜底 worker: 兜底场景对延迟不敏感,保留 sleep 退避保护账户
    install_fb_usage_backoff(auto_sleep=True)
    logging.info(f"启动 ad_creative_scrape_worker, queue={AD_CREATIVE_FETCH_QUEUE_KEY}")
    while True:
        msg = _pop_one()
        if not msg:
            continue
        try:
            _process_message(msg)
        except Exception as e:
            logging.error(f"处理消息异常: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
