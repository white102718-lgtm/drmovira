"""airbyte source-facebook-marketing 的逐文件移植版(原子接口层)。

这一层不动业务,只对应 airbyte 上游的 7 个文件:

  common.py           ← airbyte/streams/common.py        (retry_pattern + 速率码常量)
  utils.py            ← airbyte/utils.py                 (DateInterval)
  api.py              ← airbyte/api.py                   (MyFacebookAdsApi + API 封装,加 proxy)
  async_job.py        ← airbyte/streams/async_job.py     (AsyncJob/ParentAsyncJob/InsightAsyncJob)
  async_job_manager.py← airbyte/streams/async_job_manager.py (APILimit + InsightAsyncJobManager)
  runner.py           ← 本仓库新增:fetch_account_insights() 单 async-report 入口
  entity_streams.py   ← airbyte/streams/streams.py 的实体列表流 + base_streams 的辅助函数

编排层在上一级 ../pipeline.py。
"""

from .api import API, MyFacebookAdsApi
from .async_job import AsyncJob, InsightAsyncJob, ParentAsyncJob, Status
from .async_job_manager import APILimit, InsightAsyncJobManager
from .entity_streams import (
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
    VALID_AD_STATUSES,
    VALID_ADSET_STATUSES,
    VALID_CAMPAIGN_STATUSES,
    fetch_activities,
    fetch_ad_account,
    fetch_ad_by_id,
    fetch_ad_creatives,
    fetch_ad_creatives_from_ads,
    fetch_ad_sets,
    fetch_ads,
    fetch_ads_by_ids,
    fetch_ads_under_adsets,
    fetch_ads_under_campaigns,
    fetch_adset_by_id,
    fetch_adsets_by_ids,
    fetch_adsets_under_campaigns,
    fetch_campaign_by_id,
    fetch_campaigns,
    fetch_campaigns_by_ids,
    fetch_custom_audiences,
    fetch_custom_conversions,
    fetch_images,
    fetch_videos,
)
from .runner import build_insight_params, fetch_account_insights
from .utils import DateInterval

__all__ = [
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
    "fetch_ad_by_id",
    "fetch_adset_by_id",
    "fetch_campaign_by_id",
    "fetch_ads_by_ids",
    "fetch_adsets_by_ids",
    "fetch_campaigns_by_ids",
    "fetch_ads_under_campaigns",
    "fetch_adsets_under_campaigns",
    "fetch_ads_under_adsets",
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
]
