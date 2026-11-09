import json
import logging
import tempfile
import time
from copy import deepcopy
from pathlib import Path
import requests
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adimage import AdImage
from facebook_business.adobjects.advideo import AdVideo
from facebook_business.api import FacebookAdsApi
from facebook_business.exceptions import FacebookRequestError
from conf.api_conf import get_proxies, backend_api
from db.clients import mongo_client, redis_cli_3 as operation_redis
from model_type_defs.ad_operation_type import (
    CampaignType,
    OpType,
    RetryableOperationError,
)
from model_type_defs.file_type import FileType
from tasks.ad_operation_new.common import (
    dev_queue_key,
    normalize_campaign_type,
)
from utils.common_util import fb_api_retry
from utils.message_signing import build_signed_payload

REGULATION_CACHE_TTL = 7 * 24 * 3600
REGULATION_MISS_CACHE_TTL = 10 * 60
REGULATION_LOCK_TTL = 60

class AdPublisher:
    def __init__(
        self,
        dev_conf,
        config: dict,
        api: FacebookAdsApi,
        source_message: dict | None = None,
    ):
        self.app_id = dev_conf["app_id"]
        self.app_secret = dev_conf["app_secret"]
        self.access_token = dev_conf["access_token"]
        self.proxy = dev_conf["proxy"]
        self.config = config
        self.api = api
        self.account_id = config["account_id"]
        self.account = AdAccount(
            self.account_id
            if self.account_id.startswith("act_")
            else f"act_{self.account_id}",
            api=self.api,
        )
        self.source_message = source_message or {}

    def _requeue(self, create_config: list[dict]):
        message = {
            "auto_run": self.source_message.get("auto_run", True),
            "dev_app": self.source_message.get("dev_app"),
            "is_send": self.source_message.get("is_send", False),
            "type": OpType.CREATE.value,
            "create_config": create_config,
            "real_name": self.source_message.get("real_name"),
            "user_id": self.source_message.get("user_id"),
            "api_key": self.source_message.get("api_key"),
        }
        if batch_id := self.source_message.get("batch_id"):
            message["batch_id"] = batch_id
        message = build_signed_payload(payload=message, api_key=message["api_key"])
        try:
            operation_redis.rpush(
                dev_queue_key(self.app_id, OpType.CREATE.value),
                json.dumps(message, ensure_ascii=False).encode("utf-8"),
            )
        except Exception as e:
            raise RetryableOperationError(f"follow-up 消息发送失败: {e}") from e

    def publish(self):
        logging.info(f"--- Processing Account: {self.account_id} ---")
        if "campaigns" in self.config:
            self._flow_campaigns()
        elif "campaign_id" in self.config:
            self._flow_adset()
        elif "adset_id" in self.config:
            self._flow_ad()
        else:
            raise ValueError("无法推断创建层级")

    def _flow_campaigns(self):
        """基于账户创建系列，requeue 组配置"""
        campaigns = self.config.get("campaigns")
        if not campaigns:
            raise ValueError("缺少campaigns参数")
        next_adsets = []
        for camp_cfg in campaigns:
            campaign = self._create_campaign(camp_cfg)
            for adset_cfg in camp_cfg.get("adsets", []):
                next_cfg = deepcopy(adset_cfg)
                next_cfg["campaign_id"] = campaign["id"]
                next_cfg["campaign_name"] = camp_cfg.get("name")
                next_cfg["account_id"] = self.account_id
                next_cfg["campaign_type"] = normalize_campaign_type(camp_cfg.get("objective"))
                if camp_cfg.get("auto_regulation_identity"):
                    next_cfg["auto_regulation_identity"] = True
                self._maybe_inject_regulation(next_cfg)
                next_adsets.append(next_cfg)
        # 一条组消息只包含一个广告组：某组失败只能影响自己；消息仍携带相同
        # batch_id，因此进度查询可还原整批次的系列→组→广告树。
        for adset_cfg in next_adsets:
            self._requeue([adset_cfg])

    def _flow_adset(self):
        """基于系列创建单个组，requeue 广告配置"""
        if not self.config.get("campaign_id"):
            raise ValueError("缺少campaign_id参数")
        campaign_name = self.config.get("campaign_name") or self.config["campaign_id"]
        campaign_type = normalize_campaign_type(self.config.get("campaign_type"))
        self._maybe_inject_regulation(self.config)
        ad_set = self._create_adset()
        ads_data = self.config.get("ads", [])
        if not ads_data:
            return
        next_ads = []
        adset_name = f"{campaign_name}||{self.config.get('name')}"
        for ad_cfg in deepcopy(ads_data):
            ad_cfg["adset_id"] = ad_set["id"]
            ad_cfg["adset_name"] = adset_name
            ad_cfg["account_id"] = self.account_id
            ad_cfg["campaign_type"] = campaign_type
            ad_cfg["is_dynamic_creative"] = self.config.get("is_dynamic_creative")
            next_ads.append(ad_cfg)
        if next_ads:
            self._requeue(next_ads)

    def _flow_ad(self):
        """基于组创建单个广告"""
        if not self.config.get("adset_id"):
            raise ValueError("缺少adset_id参数")
        self._create_ad()

    @fb_api_retry
    def upload_media(self, url, type_, filename):
        if type_ == FileType.IMAGE:
            image_response = requests.get(
                url, proxies=get_proxies(self.proxy), timeout=120
            )
            image_bytes = image_response.content
            tmp = tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False)
            tmp_path = tmp.name
            try:
                with tmp:
                    tmp.write(image_bytes)
                image = self.account.create_ad_image(params={"filename": tmp_path})
            finally:
                Path(tmp_path).unlink(missing_ok=True)
            return image[AdImage.Field.hash], False
        else:
            video = self.account.create_ad_video(params={"file_url": url})
            video_id = video[AdVideo.Field.id]
            return video_id, True

    @fb_api_retry
    def upload_image_base64(self, base64_data: str) -> str:
        image = self.account.create_ad_image(params={AdImage.Field.bytes: base64_data})
        return image[AdImage.Field.hash]

    def _upload_video_thumbnail(self, material: dict) -> str | None:
        """视频封面：优先素材库的 1080 大图；老素材还没回填 poster_url 时退回 120px 的 img"""
        if poster_url := material.get("poster_url"):
            image_hash, _ = self.upload_media(
                poster_url,
                FileType.IMAGE,
                f"{Path(material['filename']).stem}.jpg",
            )
            return image_hash
        if thumb_base64 := material.get("img"):
            return self.upload_image_base64(thumb_base64)
        return None

    @fb_api_retry
    def _create_campaign(self, camp_cfg):
        camp_params = camp_cfg.copy()
        camp_params.pop("adsets", None)
        camp_params.pop("campaign_type", None)
        campaign = self.account.create_campaign(params=camp_params)
        logging.info(f"Created Campaign: {camp_params['name']} (ID: {campaign['id']})")
        return campaign

    def _resolve_account_regulation(self) -> dict | None:
        """投受限地区(如巴西)需要的「广告主」合规字段。复用本账户已有 ad set 的
        regional_regulated_categories + regional_regulation_identities;按账户缓存 2 天
        (含「无」结果)。账户下没有组、或都没设置该参数,返回 None(即不传)。"""
        cache_key = f"ad_reg_identity:{self.account_id}"
        cached = operation_redis.get(cache_key)
        if cached is not None:
            return json.loads(cached) if cached else None
        lock_key = f"{cache_key}:lock"
        while not operation_redis.set(lock_key, "1", nx=True, ex=REGULATION_LOCK_TTL):
            time.sleep(0.05)
        try:
            cached = operation_redis.get(cache_key)  # 双重检查:等锁期间别人可能已写
            if cached is not None:
                return json.loads(cached) if cached else None
            found = None
            for ad_set in self.account.get_ad_sets(
                fields=["regional_regulated_categories", "regional_regulation_identities"],
                params={"limit": 50},
            ):
                operation_redis.expire(lock_key, REGULATION_LOCK_TTL)
                data = ad_set.export_all_data()
                if data.get("regional_regulation_identities"):
                    found = {
                        "regional_regulated_categories": data.get("regional_regulated_categories"),
                        "regional_regulation_identities": data["regional_regulation_identities"],
                    }
                    break
            operation_redis.set(
                cache_key,
                json.dumps(found) if found else "",
                ex=REGULATION_CACHE_TTL if found else REGULATION_MISS_CACHE_TTL,
            )
            return found
        finally:
            operation_redis.delete(lock_key)

    def _maybe_inject_regulation(self, cfg: dict) -> None:
        """cfg 带 auto_regulation_identity 时,把账户合规字段就地写进 cfg;查不到则不写。
        在扇出前(系列流)调用,避免多个组并发各查一次。"""
        if not cfg.pop("auto_regulation_identity", None):
            return
        reg = self._resolve_account_regulation()
        if reg:
            cfg["regional_regulated_categories"] = reg["regional_regulated_categories"]
            cfg["regional_regulation_identities"] = reg["regional_regulation_identities"]

    @fb_api_retry
    def _create_adset(self):
        as_params = self.config.copy()
        as_params.pop("ads", None)
        as_params.pop("account_id", None)
        as_params.pop("campaign_name", None)
        as_params.pop("auto_regulation_identity", None)
        page_id = as_params.pop("page_id", None)
        campaign_type = normalize_campaign_type(as_params.pop("campaign_type", None))
        if campaign_type == CampaignType.ENGAGEMENT.value:
            as_params["promoted_object"] = {"page_id": page_id}
        if campaign_type == CampaignType.APP_PROMOTION.value:
            as_params.pop("pixel_id", None)
            as_params.pop("pixel_name", None)
            promoted_object = as_params.get("promoted_object")
            if isinstance(promoted_object, dict):
                promoted_object.pop("pixel_id", None)
                promoted_object.pop("pixel_name", None)
        ad_set = self.account.create_ad_set(params=as_params)
        logging.info(f"  Created Ad Set: {as_params['name']} (ID: {ad_set['id']})")
        return ad_set

    def _get_saved_page_info(self, page_id: str) -> dict:
        return mongo_client["fb_pages"].find_one(
            {"_id": page_id},
            {"instagram_user_id": 1},
        ) or {}

    def _process_instagram_accounts(self, page_id: str) -> str | None:
        page_info = self._get_saved_page_info(page_id)
        if page_info.get("instagram_user_id"):
            return page_info.get("instagram_user_id")
        else:
            return None

    def _build_page_welcome_message(self, creative_cfg: dict) -> str | None:
        page_welcome_message = creative_cfg.pop("page_welcome_message", None)
        if not page_welcome_message:
            return None
        if isinstance(page_welcome_message, str):
            return page_welcome_message
        return json.dumps(page_welcome_message, ensure_ascii=False)

    def _fetch_material(self, name: str) -> dict:
        response = None
        for attempt in range(3):
            try:
                response = requests.get(
                    f"{backend_api}/materials/url_by_basename/{name}",
                    timeout=30,
                )
                response.raise_for_status()
                break
            except requests.exceptions.RequestException:
                if attempt == 2:
                    raise
                logging.warning(
                    f"url_by_basename请求失败，第{attempt + 1}次重试", exc_info=True
                )
        data = response.json()
        if data["code"] != 0:
            raise ValueError(f'调用url_by_basename报错: {data["message"]}')
        return data

    def _apply_instagram_user(self, object_story_spec: dict, page_id: str) -> None:
        instagram_user_id = self.config.get("instagram_user_id")
        if isinstance(instagram_user_id, str):
            object_story_spec["instagram_user_id"] = instagram_user_id
        elif instagram_user_id is None:
            resolved = self._process_instagram_accounts(page_id=page_id)
            if resolved:
                object_story_spec["instagram_user_id"] = resolved

    def _build_creative_param(self, ad_params: dict):
        creative_cfg = ad_params.pop("creative", {})
        members = ad_params.pop("dynamic_members", None)
        page_welcome_message = self._build_page_welcome_message(creative_cfg)
        page_id = ad_params.get("page_id", None)
        link_url = ad_params.get("link_url", None)
        display_link = ad_params.get("display_link", None)

        creative_params = {
            "name": self.config["name"],
            "object_story_spec": {
                "page_id": page_id,
            },
            "contextual_multi_ads": self.config.get("contextual_multi_ads"),
        }
        self._apply_instagram_user(creative_params["object_story_spec"], page_id)

        enhancement = creative_cfg.get("enhancement") or {}
        add_music = bool(enhancement.get("add_music"))
        degrees_of_freedom_spec = creative_cfg.get("degrees_of_freedom_spec")

        # 优化网站目标位置(把每个人导到站内最相关的页面),需有落地页 + 后台开关
        if link_url and enhancement.get("website_destination_optimization"):
            creative_params["destination_spec"] = {
                "website": {
                    "optimization": {
                        "status": "OPT_IN",
                        "type": "website_destination_optimization",
                    }
                }
            }

        if self.config.get("is_dynamic_creative"):
            # 单素材动态 = 单元素素材池,与多素材走同一条 asset_feed_spec 流程
            pool = members or [{"name": ad_params["name"], "creative": creative_cfg}]
            spec, _ = self._build_asset_feed_spec(pool, link_url, add_music)
            creative_params["asset_feed_spec"] = spec
            if degrees_of_freedom_spec:
                creative_params["degrees_of_freedom_spec"] = degrees_of_freedom_spec
            return creative_params

        data = self._fetch_material(ad_params["name"])
        media_ref, is_video = self.upload_media(
            data["data"]["url"],
            data["data"]["filetype"],
            data["data"]["filename"],
        )
        if degrees_of_freedom_spec:
            creative_params["degrees_of_freedom_spec"] = degrees_of_freedom_spec

        call_to_action = creative_cfg.get("call_to_action") or (
            {"type": "LEARN_MORE"} if link_url else None
        )

        if is_video:
            if call_to_action and link_url:
                call_to_action["value"] = {"link": link_url}
                if display_link:
                    call_to_action["value"]["link_caption"] = display_link
            video_data = {
                "video_id": media_ref,
                "message": creative_cfg.get("body"),
                "title": creative_cfg.get("title"),
                "call_to_action": call_to_action,
            }
            if thumb_hash := self._upload_video_thumbnail(data["data"]):
                video_data["image_hash"] = thumb_hash
            if page_welcome_message:
                video_data["page_welcome_message"] = page_welcome_message
            creative_params["object_story_spec"]["video_data"] = video_data
        else:
            link_data = {
                "message": creative_cfg.get("body"),
                "name": creative_cfg.get("title"),
                "call_to_action": call_to_action,
            }
            if link_url:
                link_data["link"] = link_url
            if display_link:
                link_data["caption"] = display_link
            if media_ref:
                link_data["image_hash"] = media_ref
            if page_welcome_message:
                link_data["page_welcome_message"] = page_welcome_message
            creative_params["object_story_spec"]["link_data"] = link_data
            # 图片随机配乐(对应后台"添加音乐";视频自带音轨不加)
            if add_music:
                creative_params["asset_feed_spec"] = {"audios": [{"type": "random"}]}

        return creative_params

    def _build_asset_feed_spec(self, members: list[dict], link_url, add_music: bool):
        """动态素材广告:同类型素材池化进一个 asset_feed_spec(单素材即单元素池)。
        members 已按类型分好(全图或全视频)。FB 上限:媒体 ≤10、bodies/titles 各 ≤5。"""
        images, videos, bodies, titles, cta_types = [], [], [], [], []
        is_video = False
        for member in members[:10]:
            data = self._fetch_material(member["name"])
            media_ref, is_video = self.upload_media(
                data["data"]["url"],
                data["data"]["filetype"],
                data["data"]["filename"],
            )
            creative_cfg = member.get("creative") or {}
            if is_video:
                video = {"video_id": media_ref}
                if thumb_hash := self._upload_video_thumbnail(data["data"]):
                    video["thumbnail_hash"] = thumb_hash
                videos.append(video)
            else:
                images.append({"hash": media_ref})
            if creative_cfg.get("body"):
                bodies.append(creative_cfg["body"])
            if creative_cfg.get("title"):
                titles.append(creative_cfg["title"])
            cta = (creative_cfg.get("call_to_action") or {}).get("type")
            if cta:
                cta_types.append(cta)

        if is_video:
            spec = {"videos": videos, "ad_formats": ["SINGLE_VIDEO"]}
        else:
            # 图片随机配乐(对应后台"添加音乐";视频自带音轨不加)
            spec = {"images": images, "ad_formats": ["SINGLE_IMAGE"]}
            if add_music:
                spec["audios"] = [{"type": "random"}]
        bodies = list(dict.fromkeys(bodies))[:5]
        titles = list(dict.fromkeys(titles))[:5]
        if bodies:
            spec["bodies"] = [{"text": b} for b in bodies]
        if titles:
            spec["titles"] = [{"text": t} for t in titles]
        if link_url:
            spec["link_urls"] = [{"website_url": link_url}]
        cta_types = list(dict.fromkeys(cta_types)) or (
            ["LEARN_MORE"] if link_url else []
        )
        if cta_types:
            spec["call_to_action_types"] = cta_types
        return spec, is_video

    @staticmethod
    def _is_video_not_ready_error(err: dict) -> bool:
        """subcode 为主、user_msg 关键字为辅(兜底 FB 换 subcode 的情况)"""
        if err.get("error_subcode") == 1885252:
            return True
        user_msg = err.get("error_user_msg") or ""
        return ("处理中" in user_msg) or ("still being processed" in user_msg.lower())

    def _create_ad_creative_with_video_wait(
        self, creative_params: dict, max_attempts: int = 5, interval: int = 30
    ):
        """创建 creative,遇到 FB "视频仍在处理中" 按固定间隔重试;
        耗尽后抛 RuntimeError,避免外层 fb_api_retry 因 is_transient=true
        再触发重试导致媒体重复上传。"""
        last_err = None
        retried_transient = False
        for attempt in range(1, max_attempts + 1):
            try:
                return self.account.create_ad_creative(params=creative_params)
            except FacebookRequestError as e:
                err = (e.body() or {}).get("error", {}) if hasattr(e, "body") else {}
                if err.get("error_subcode") == 1487390 and not retried_transient:
                    retried_transient = True
                    logging.warning("creative 创建遇到 FB 临时错误,重试一次 (subcode=1487390)")
                    time.sleep(5)
                    continue
                if not self._is_video_not_ready_error(err):
                    raise
                last_err = e
                logging.warning(
                    f"视频仍在处理中,creative 创建第 {attempt}/{max_attempts} 次失败,"
                    f"{interval}s 后重试 (subcode={err.get('error_subcode')})"
                )
                if attempt < max_attempts:
                    time.sleep(interval)
        raise RuntimeError(
            f"视频处理超时:creative 创建重试 {max_attempts} 次仍未就绪 "
            f"(last_error={(last_err.body() or {}).get('error') if last_err else None})"
        )

    @fb_api_retry
    def _create_ad(self):
        ad_params = self.config.copy()
        ad_params.pop("account_id", None)
        ad_params.pop("campaign_type", None)
        ad_params.pop("adset_name", None)
        ad_params.pop("is_dynamic_creative", None)
        # 如果穿了原贴ID，直接引用就好了
        post_id = ad_params.get("creative").get("post_id", None)
        if post_id:
            creative_params = {"name": self.config["name"], "object_story_id": post_id}
        else:
            creative_params = self._build_creative_param(ad_params=ad_params)

        creative = self._create_ad_creative_with_video_wait(creative_params)

        ad_params["creative"] = {"creative_id": creative["id"]}

        ad_params.pop("page_id", None)
        ad_params.pop("link_url", None)
        ad = self.account.create_ad(params=ad_params)
        ad_name = self.config.get("name")
        if ad:
            redis_key = f"ad_task:{self.account_id}:{self.config['adset_id']}"
            operation_redis.hset(redis_key, ad_name, ad["id"])
            operation_redis.expire(redis_key, 7 * 24 * 3600, nx=True)
        logging.info(f"    Created Ad: {ad_params['name']} (ID: {ad['id']})")
