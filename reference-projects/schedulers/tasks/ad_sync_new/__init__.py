"""FB 广告数据抽取 — airbyte source-facebook-marketing 移植 + 本地编排。

结构:
  airbyte/        ← airbyte 原子接口 (api / async_job / async_job_manager /
                    common / entity_streams / runner / utils)
                    一行不改,只移植。详见 airbyte/__init__.py
  pipeline.py     ← 本地编排层:fetch_all(message, fetch_day),一户一天拉完
                    fb_account_consumer_async 需要的 16 个数据 key

常用入口:
    from tasks.ad_sync_new import fetch_all
    bundle = fetch_all(message=msg, fetch_day="2026-05-10")

如果只要某条 airbyte 原子接口:
    from tasks.ad_sync_new import fetch_account_insights, fetch_campaigns, ...
    # 这些都从 .airbyte 透传出来,保持旧调用点不破

或者显式从 airbyte 子包取,语义更清楚:
    from tasks.ad_sync_new.airbyte import fetch_account_insights
"""

from tasks.ad_sync_new.airbyte import (  # noqa: F401  re-export airbyte 原子接口
    API,
    APILimit,
    AsyncJob,
    DEFAULT_AD_ACCOUNT_FIELDS,
    DEFAULT_AD_CREATIVE_FIELDS,
    DEFAULT_AD_FIELDS,
    DEFAULT_ADSET_FIELDS,
    DEFAULT_ACTIVITY_FIELDS,
    DEFAULT_CAMPAIGN_FIELDS,
    DEFAULT_CUSTOM_AUDIENCE_FIELDS,
    DEFAULT_CUSTOM_CONVERSION_FIELDS,
    DEFAULT_IMAGE_FIELDS,
    DEFAULT_VIDEO_FIELDS,
    DateInterval,
    InsightAsyncJob,
    InsightAsyncJobManager,
    MyFacebookAdsApi,
    ParentAsyncJob,
    Status,
    VALID_AD_STATUSES,
    VALID_ADSET_STATUSES,
    VALID_CAMPAIGN_STATUSES,
    build_insight_params,
    fetch_account_insights,
    fetch_activities,
    fetch_ad_account,
    fetch_ad_creatives,
    fetch_ad_creatives_from_ads,
    fetch_ad_sets,
    fetch_ads,
    fetch_campaigns,
    fetch_custom_audiences,
    fetch_custom_conversions,
    fetch_images,
    fetch_videos,
)
from tasks.ad_sync_new.pipeline import (  # noqa: F401  re-export 编排层
    AD_LEVEL_EXTRA_FIELDS,
    ADS_LIST_FIELDS,
    FREQUENCY_WINDOWS,
    INSIGHTS_FIELDS,
    LEVEL_TO_ID_FIELD,
    VIDEO_INSIGHTS_FIELDS,
    fetch_all,
)

__all__ = [
    # ── airbyte 原子接口 ──
    "API",
    "MyFacebookAdsApi",
    "AsyncJob",
    "InsightAsyncJob",
    "ParentAsyncJob",
    "Status",
    "APILimit",
    "InsightAsyncJobManager",
    "DateInterval",
    "build_insight_params",
    "fetch_account_insights",
    "fetch_ads",
    "fetch_ad_sets",
    "fetch_campaigns",
    "fetch_ad_account",
    "fetch_ad_creatives",
    "fetch_ad_creatives_from_ads",
    "fetch_videos",
    "fetch_activities",
    "fetch_custom_conversions",
    "fetch_custom_audiences",
    "fetch_images",
    "VALID_AD_STATUSES",
    "VALID_ADSET_STATUSES",
    "VALID_CAMPAIGN_STATUSES",
    "DEFAULT_AD_FIELDS",
    "DEFAULT_ADSET_FIELDS",
    "DEFAULT_CAMPAIGN_FIELDS",
    "DEFAULT_AD_ACCOUNT_FIELDS",
    "DEFAULT_AD_CREATIVE_FIELDS",
    "DEFAULT_VIDEO_FIELDS",
    "DEFAULT_ACTIVITY_FIELDS",
    "DEFAULT_CUSTOM_CONVERSION_FIELDS",
    "DEFAULT_CUSTOM_AUDIENCE_FIELDS",
    "DEFAULT_IMAGE_FIELDS",
    # ── 编排层 ──
    "fetch_all",
    "INSIGHTS_FIELDS",
    "VIDEO_INSIGHTS_FIELDS",
    "AD_LEVEL_EXTRA_FIELDS",
    "ADS_LIST_FIELDS",
    "FREQUENCY_WINDOWS",
    "LEVEL_TO_ID_FIELD",
]
