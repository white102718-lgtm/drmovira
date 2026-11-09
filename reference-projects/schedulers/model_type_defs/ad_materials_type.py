# -*- coding:utf-8 -*-
"""
ad_materials 模块消息类型定义
"""

from typing import NotRequired, TypedDict


# ──────────────────────────────────────────────
# Redis 队列配置常量（生产者 & 消费者共用）
# ──────────────────────────────────────────────

AD_CREATIVE_FETCH_QUEUE_KEY = "ad_creative_fetch_pending"
AD_MATERIALS_PRIMARY_FETCH_QUEUE_KEY = "ad_materials_primary_fetch_pending"


# ──────────────────────────────────────────────
# mongo:广告 -> FB 素材原始文件名(asset_name_sync 写,_id = ad_id 兼作去重表)
# ──────────────────────────────────────────────

AD_ASSET_NAME_COLLECTION = "ad_asset_names"


# ──────────────────────────────────────────────
# 子字段：Facebook 开发者 / 账户信息
# ──────────────────────────────────────────────


class FbDevApp(TypedDict):
    """调用 Facebook API 所需的开发者凭据"""

    app_id: str
    app_secret: str
    access_token: str
    proxy: NotRequired[str | None]  # 代理主机（IP 或域名），None 表示不走代理


class AdCreativeMetadata(TypedDict, total=False):
    """素材保存时使用的业务元数据（对应 backend materials/internal 接口字段）"""

    unique_name: str
    date: str
    game_platform: str
    ad_platform: str
    country: str
    category: str
    agent_line: str
    timezone_name: str
    campaign_id: str
    ad_set_id: str
    creative_id: str
    video_id: str


# ──────────────────────────────────────────────
# Redis 输入消息（生产者 → ad_creative_scrape_worker）
# ──────────────────────────────────────────────


class AdCreativeFetchMessage(TypedDict):
    """
    广告素材抓取任务消息

    当主下载流程 (utils/fb_utils.py) 遇到 "没有找到可下载的媒体 URL" 时，
    将此消息 RPUSH 进 AD_CREATIVE_FETCH_QUEUE_KEY，由 worker 用 BLPOP 异步消费。
    """

    ad_id: str
    account_id: str
    dev: FbDevApp
    metadata: NotRequired[AdCreativeMetadata]


# ──────────────────────────────────────────────
# Redis 主下载队列消息 (ad_materials_sync 生产者 → ad_materials_fetch_worker)
# ──────────────────────────────────────────────


class AdRecordPayload(TypedDict):
    """单条广告记录在队列消息中的序列化形式"""

    ad_id: str
    unique_name: str
    account_id: NotRequired[str]
    dev_id: NotRequired[str]
    game_platform: NotRequired[str]
    ad_platform: NotRequired[str]
    unique_key_fields: dict


class AdMaterialsPrimaryFetchMessage(TypedDict):
    """
    主下载队列消息:一个 fetch_config (group) 下的一批广告。
    worker 拿到后调用 FB SDK 批量下载,成功写 MongoDB + 更新 Doris unique_name,
    失败的 ad_id 再走 AD_CREATIVE_FETCH_QUEUE_KEY 兜底 (Playwright)。
    """

    group_key: str
    fetch_config: FbDevApp
    ad_records: list[AdRecordPayload]
