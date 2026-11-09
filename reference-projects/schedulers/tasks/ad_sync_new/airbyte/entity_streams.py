"""Ported from airbyte source-facebook-marketing/streams/streams.py + base_streams.py.

实体列表流 (Ads / AdSets / Campaigns / AdAccount):用 account.get_xxx() 直接列
出全部实体,跟 AdsInsights (只返回有成效的行) 完全独立。这是 airbyte"没成效
也能拉到"的来源 —— 数仓侧 LEFT JOIN 实体表 + 成效表得到完整视图。

约定与 runner.fetch_account_insights 对齐:
  - 入参 message: {"account_id", "app_id", "app_secret", "access_token", "proxy"}
  - 返回 list[dict] (AdAccount 单条返 dict),纯原始数据,不做业务转换、不写库
  - account_id 带不带 'act_' 前缀都行,内部统一去前缀

对应 airbyte 文件:
  base_streams.FBMarketingStream.fix_date_time          -> _fix_date_time
  base_streams.FBMarketingStream.add_account_id         -> _add_account_id
  base_streams.FBMarketingStream._filter_all_statuses   -> _build_filter_params(status 部分)
  base_streams.FBMarketingIncrementalStream._state_filter -> _build_filter_params(since 部分)
  streams.Ads / AdSets / Campaigns / AdAccount.list_objects -> fetch_*
"""

import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional

from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adaccount import AdAccount as FBAdAccount
from facebook_business.adobjects.adcreative import AdCreative as FBAdCreative
from facebook_business.adobjects.adimage import AdImage
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.campaign import Campaign
from facebook_business.exceptions import FacebookRequestError

from conf.api_conf import get_proxies

from .api import API


logger = logging.getLogger(__name__)


# ---- valid status enums (mirrors spec.py:35-37) ----------------------------
# 跟 airbyte 一样取 SDK EffectiveStatus 的全部枚举值,过滤掉私有属性
def _enum_values(cls) -> List[str]:
    return [v for k, v in cls.__dict__.items() if not k.startswith("_") and isinstance(v, str)]


VALID_AD_STATUSES: List[str] = _enum_values(Ad.EffectiveStatus)
VALID_ADSET_STATUSES: List[str] = _enum_values(AdSet.EffectiveStatus)
VALID_CAMPAIGN_STATUSES: List[str] = _enum_values(Campaign.EffectiveStatus)


# ---- default fields (字段集与 airbyte schema/{ads,ad_sets,campaigns,ad_account}.json 对齐) ----
DEFAULT_AD_FIELDS: List[str] = [
    "bid_type", "account_id", "campaign_id", "adset_id", "adlabels",
    "bid_amount", "bid_info", "status", "creative", "id", "updated_time",
    "created_time", "name", "targeting", "effective_status",
    "last_updated_by_app_id", "recommendations", "source_ad_id",
    "tracking_specs", "conversion_specs",
]
DEFAULT_ADSET_FIELDS: List[str] = [
    "name", "end_time", "promoted_object", "id", "account_id", "updated_time",
    "daily_budget", "budget_remaining", "status", "effective_status",
    "campaign_id", "created_time", "start_time", "lifetime_budget", "targeting",
    "bid_info", "bid_strategy", "bid_amount", "bid_constraints", "adlabels",
    "learning_stage_info",
]
DEFAULT_CAMPAIGN_FIELDS: List[str] = [
    "account_id", "adlabels", "bid_strategy", "boosted_object_id",
    "budget_rebalance_flag", "budget_remaining", "buying_type", "daily_budget",
    "created_time", "configured_status", "effective_status", "id",
    "issues_info", "lifetime_budget", "name", "objective",
    "smart_promotion_type", "source_campaign_id", "special_ad_category",
    "special_ad_category_country", "spend_cap", "start_time", "status",
    "stop_time", "updated_time",
]
DEFAULT_AD_CREATIVE_FIELDS: List[str] = [
    "body", "object_story_id", "image_url", "id", "account_id", "actor_id",
    "adlabels", "applink_treatment", "asset_feed_spec", "call_to_action_type",
    "effective_instagram_media_id", "effective_object_story_id", "title",
    "name", "image_crops", "instagram_user_id", "instagram_permalink_url",
    "link_og_id", "object_id", "object_story_spec", "object_type",
    "object_url", "product_set_id", "source_instagram_media_id", "status",
    "template_url", "template_url_spec", "thumbnail_url", "image_hash",
    "url_tags", "video_id", "link_url",
    # thumbnail_data_url 是 airbyte 端计算字段(base64 嵌入),不向 FB 请求,默认排除
]
DEFAULT_VIDEO_FIELDS: List[str] = [
    # account_id 由 _add_account_id 注入,airbyte 也是 fields 排除 + 处理时补上
    "id", "ad_breaks", "backdated_time", "backdated_time_granularity",
    "content_category", "content_tags", "created_time", "custom_labels",
    "description", "embed_html", "embeddable", "format", "icon",
    "is_crosspost_video", "is_crossposting_eligible", "is_episode",
    "is_instagram_eligible", "length", "live_status", "permalink_url",
    "post_views", "premiere_living_room_status", "published",
    "scheduled_publish_time", "source", "title", "universal_video_id",
    "updated_time", "views",
]
DEFAULT_ACTIVITY_FIELDS: List[str] = [
    # 同 Videos:account_id 由 _add_account_id 注入
    "actor_id", "actor_name", "application_id", "application_name",
    "date_time_in_timezone", "event_time", "event_type", "extra_data",
    "object_id", "object_name", "object_type", "translated_event_type",
]
DEFAULT_CUSTOM_CONVERSION_FIELDS: List[str] = [
    "id", "account_id", "business", "creation_time", "custom_event_type",
    "data_sources", "default_conversion_value", "description",
    "event_source_type", "first_fired_time", "is_archived", "is_unavailable",
    "last_fired_time", "name", "offline_conversion_data_set", "retention_days",
    "rule",
]
# CustomAudiences 的 'rule' 字段会触发 "Please reduce the amount of data"
# (airbyte oncall #2765),fields_exceptions=["rule"] —— 默认排除
DEFAULT_CUSTOM_AUDIENCE_FIELDS: List[str] = [
    "id", "account_id", "approximate_count_lower_bound",
    "approximate_count_upper_bound", "customer_file_source", "data_source",
    "delivery_status", "description", "is_value_based",
    "lookalike_audience_ids", "lookalike_spec", "name", "operation_status",
    "opt_out_link", "page_deletion_marked_delete_time",
    "permission_for_actions", "pixel_id", "retention_days", "rule_aggregation",
    "sharing_status", "subtype", "time_content_updated", "time_created",
    "time_updated",
]
DEFAULT_IMAGE_FIELDS: List[str] = [
    "account_id", "id", "name", "creatives", "original_height",
    "original_width", "permalink_url", "status", "url", "created_time",
    "hash", "url_128", "is_associated_creatives_in_adgroups", "filename",
    "updated_time", "height", "width",
]
# AdAccount 默认字段已剔除 funding_source_details / is_prepay_account
# (airbyte 在 AdAccount.fields(account_id) 里通过 get_task_permissions 检查 MANAGE
# 权限再决定加不加;我们这边按需 opt-in,不强行查权限以省一次 API 调用)
DEFAULT_AD_ACCOUNT_FIELDS: List[str] = [
    "account_id", "account_status", "age", "amount_spent", "balance",
    "business", "business_city", "business_country_code", "business_name",
    "business_state", "business_street", "business_street2", "business_zip",
    "can_create_brand_lift_study", "capabilities", "created_time", "currency",
    "disable_reason", "end_advertiser", "end_advertiser_name",
    "extended_credit_invoice_group", "failed_delivery_checks", "fb_entity",
    "funding_source", "has_migrated_permissions", "id", "io_number",
    "is_attribution_spec_system_default", "is_direct_deals_enabled",
    "is_in_3ds_authorization_enabled_market", "is_notifications_enabled",
    "is_personal", "is_tax_id_required", "line_numbers", "media_agency",
    "min_campaign_group_spend_cap", "min_daily_budget", "name",
    "offsite_pixels_tos_accepted", "owner", "partner", "rf_spec", "spend_cap",
    "tax_id", "tax_id_status", "tax_id_type", "timezone_id", "timezone_name",
    "timezone_offset_hours_utc", "tos_accepted", "user_tasks",
    "user_tos_accepted",
]


# ---- airbyte FBMarketingStream helpers (verbatim port) ---------------------

# 跟 base_streams.FBMarketingStream.fix_date_time 同名 tuple
_DATE_TIME_FIELDS = (
    "created_time", "creation_time", "updated_time", "event_time",
    "start_time", "first_fired_time", "last_fired_time",
)


def _fix_date_time(record):
    """FB 偶发返 't' / ' 0000' 不合 ISO-8601,airbyte 统一改 'T' / '+0000',
    递归处理 nested dict / list。"""
    if isinstance(record, dict):
        for field, value in record.items():
            if isinstance(value, str):
                if field in _DATE_TIME_FIELDS:
                    record[field] = value.replace("t", "T").replace(" 0000", "+0000")
            else:
                _fix_date_time(value)
    elif isinstance(record, list):
        for entry in record:
            _fix_date_time(entry)


def _add_account_id(record: dict, account_id: str) -> None:
    if "account_id" not in record:
        record["account_id"] = account_id


def _build_filter_params(
    entity_prefix: str,
    status_field: Optional[str],
    filter_statuses: Optional[List[str]],
    since_timestamp: Optional[int],
    ids: Optional[List[str]] = None,
    cursor_field: str = "updated_time",
    page_size: int = 100,
) -> Dict[str, Any]:
    """合并 _filter_all_statuses + _state_filter + id IN 三段 filtering 到一个 params。

    - status: airbyte 的 _filter_all_statuses,有 filter_statuses 才出
              {field: "<prefix>.<status_field>", op: IN, value: [...]}
    - since:  airbyte 的 _state_filter,有 since_timestamp 才出
              {field: "<prefix>.<cursor_field>", op: GREATER_THAN, value: <ts>}
    - ids:    新加的 id 白名单,用来"按 insight 命中的 entity 集合补齐元数据"
              {field: "<prefix>.id", op: IN, value: [...]}
              注:filtering 数组里多个条件是 AND,如果同时传 ids + filter_statuses
              结果是交集 —— 调用方按需自己决定要不要混用。
    """
    # summary='false' 是为了**关闭** FB SDK 自动加的 `summary=true`:
    # facebook_business/api.py:830 在 cursor request 里自动塞 summary=True,
    # 触发 FB 端额外的 total_count 聚合(消耗 dev tier ads_management 配额)。
    # 只要 params 里已经有 summary 字段,SDK 就跳过自动添加,'false' 字符串
    # 告诉 FB 别算这个 summary block。
    params: Dict[str, Any] = {"limit": page_size, "summary": "false"}
    filtering: List[Dict[str, Any]] = []
    if filter_statuses and status_field:
        filtering.append({
            "field": f"{entity_prefix}.{status_field}",
            "operator": "IN",
            "value": filter_statuses,
        })
    if since_timestamp is not None:
        filtering.append({
            "field": f"{entity_prefix}.{cursor_field}",
            "operator": "GREATER_THAN",
            "value": int(since_timestamp),
        })
    if ids:
        filtering.append({
            "field": f"{entity_prefix}.id",
            "operator": "IN",
            "value": list(ids),
        })
    if filtering:
        params["filtering"] = filtering
    return params


def _build_api(message: Mapping[str, Any]) -> API:
    return API(
        app_id=message["app_id"],
        app_secret=message["app_secret"],
        access_token=message["access_token"],
        proxies=get_proxies(message["proxy"]),
    )


def _strip_act_prefix(account_id_raw: str) -> str:
    return account_id_raw[len("act_"):] if account_id_raw.startswith("act_") else account_id_raw


def _normalize(
    records: Iterable[Any],
    account_id: str,
    progress_label: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """对应 base_streams.FBMarketingStream.read_records 的内层:
       AbstractObject -> dict -> fix_date_time -> add_account_id。
    progress_label 给定时,每 300 条打一行,用来观察 FB 翻页是否在推进。
    """
    out: List[Dict[str, Any]] = []
    for r in records:
        data = r.export_all_data() if hasattr(r, "export_all_data") else dict(r)
        _fix_date_time(data)
        _add_account_id(data, account_id)
        out.append(data)
        if progress_label and len(out) % 300 == 0:
            logger.info(
                "%s: account=%s 已拉取 %d 条", progress_label, account_id, len(out),
            )
    return out


# ---- public fetch_* (一个流一个函数) ----------------------------------------

def fetch_ads(
    message: Mapping[str, Any],
    fields: Optional[List[str]] = None,
    filter_statuses: Optional[List[str]] = None,
    since_timestamp: Optional[int] = None,
    ids: Optional[List[str]] = None,
    page_size: int = 100,
    api: Optional[API] = None,
) -> List[Dict[str, Any]]:
    """List ALL ads under the account.

    Mirrors streams.Ads (FBMarketingIncrementalStream, entity_prefix="ad",
    status_field="effective_status", valid_statuses=ValidAdStatuses).
    doc: https://developers.facebook.com/docs/marketing-api/reference/adgroup
    """
    fields = fields or DEFAULT_AD_FIELDS
    account_id_raw = message["account_id"]
    account_id = _strip_act_prefix(account_id_raw)
    account = (api or _build_api(message)).get_account(account_id=account_id)
    params = _build_filter_params(
        entity_prefix="ad",
        status_field="effective_status",
        filter_statuses=filter_statuses,
        since_timestamp=since_timestamp,
        ids=ids,
        page_size=page_size,
    )
    rows = _normalize(
        account.get_ads(params=params, fields=fields), account_id,
        progress_label="fetch_ads",
    )
    logger.info("fetch_ads: account=%s -> %d rows", account_id_raw, len(rows))
    return rows


def fetch_ad_sets(
    message: Mapping[str, Any],
    fields: Optional[List[str]] = None,
    filter_statuses: Optional[List[str]] = None,
    since_timestamp: Optional[int] = None,
    ids: Optional[List[str]] = None,
    page_size: int = 100,
    api: Optional[API] = None,
) -> List[Dict[str, Any]]:
    """List ALL ad sets under the account.

    Mirrors streams.AdSets (FBMarketingIncrementalStream, entity_prefix="adset",
    status_field="effective_status", valid_statuses=ValidAdSetStatuses).
    doc: https://developers.facebook.com/docs/marketing-api/reference/ad-campaign
    """
    fields = fields or DEFAULT_ADSET_FIELDS
    account_id_raw = message["account_id"]
    account_id = _strip_act_prefix(account_id_raw)
    account = (api or _build_api(message)).get_account(account_id=account_id)
    params = _build_filter_params(
        entity_prefix="adset",
        status_field="effective_status",
        filter_statuses=filter_statuses,
        since_timestamp=since_timestamp,
        ids=ids,
        page_size=page_size,
    )
    rows = _normalize(
        account.get_ad_sets(params=params, fields=fields), account_id,
        progress_label="fetch_ad_sets",
    )
    logger.info("fetch_ad_sets: account=%s -> %d rows", account_id_raw, len(rows))
    return rows


def fetch_campaigns(
    message: Mapping[str, Any],
    fields: Optional[List[str]] = None,
    filter_statuses: Optional[List[str]] = None,
    since_timestamp: Optional[int] = None,
    ids: Optional[List[str]] = None,
    page_size: int = 100,
    api: Optional[API] = None,
) -> List[Dict[str, Any]]:
    """List ALL campaigns under the account — 这是"没成效系列"的来源。

    Mirrors streams.Campaigns (FBMarketingIncrementalStream, entity_prefix=
    "campaign", status_field="effective_status", valid_statuses=
    ValidCampaignStatuses).
    doc: https://developers.facebook.com/docs/marketing-api/reference/ad-campaign-group
    """
    fields = fields or DEFAULT_CAMPAIGN_FIELDS
    account_id_raw = message["account_id"]
    account_id = _strip_act_prefix(account_id_raw)
    account = (api or _build_api(message)).get_account(account_id=account_id)
    params = _build_filter_params(
        entity_prefix="campaign",
        status_field="effective_status",
        filter_statuses=filter_statuses,
        since_timestamp=since_timestamp,
        ids=ids,
        page_size=page_size,
    )
    rows = _normalize(
        account.get_campaigns(params=params, fields=fields), account_id,
        progress_label="fetch_campaigns",
    )
    logger.info("fetch_campaigns: account=%s -> %d rows", account_id_raw, len(rows))
    return rows


def fetch_campaign_by_id(
    message: Mapping[str, Any],
    campaign_id: str,
    fields: Optional[List[str]] = None,
    api: Optional[API] = None,
) -> Optional[Dict[str, Any]]:
    """单 ID 直接 GET `/<campaign_id>`。等价于:

        Campaign(fbid="123").api_get(fields=["id", "name"])

    用途:已知一组 ID,要批量补元数据时,逐个调本函数。

    注意 dev tier 配额下的成本差异(2026-05-14 实测):FB Marketing API 不同调用
    形态消耗 `ads_management` 配额的速率不同 —— 同一组 ID,
    `/<account>/<edge>?filtering=[id IN [...]]` 一次调用消耗的配额比
    `/<entity_id>` 多。配额耗尽时所有调用都会被拒,但用 per-id 形式更不容易先
    把配额烧光,能在低额度下多撑几次。

    抛 FacebookRequestError 时返 None(由调用方决定要不要忽略),不重试。
    """
    fields = fields or DEFAULT_CAMPAIGN_FIELDS
    api = api or _build_api(message)
    try:
        obj = Campaign(fbid=campaign_id, api=api.api).api_get(fields=fields)
    except FacebookRequestError as e:
        logger.warning("fetch_campaign_by_id: %s failed: %s", campaign_id, e.api_error_message())
        return None
    data = obj.export_all_data() if hasattr(obj, "export_all_data") else dict(obj)
    _fix_date_time(data)
    _add_account_id(data, _strip_act_prefix(message["account_id"]))
    return data


def fetch_adset_by_id(
    message: Mapping[str, Any],
    adset_id: str,
    fields: Optional[List[str]] = None,
    api: Optional[API] = None,
) -> Optional[Dict[str, Any]]:
    """单 ID 直接 GET `/<adset_id>` —— 详见 `fetch_campaign_by_id` docstring。"""
    fields = fields or DEFAULT_ADSET_FIELDS
    api = api or _build_api(message)
    try:
        obj = AdSet(fbid=adset_id, api=api.api).api_get(fields=fields)
    except FacebookRequestError as e:
        logger.warning("fetch_adset_by_id: %s failed: %s", adset_id, e.api_error_message())
        return None
    data = obj.export_all_data() if hasattr(obj, "export_all_data") else dict(obj)
    _fix_date_time(data)
    _add_account_id(data, _strip_act_prefix(message["account_id"]))
    return data


def fetch_ad_by_id(
    message: Mapping[str, Any],
    ad_id: str,
    fields: Optional[List[str]] = None,
    api: Optional[API] = None,
) -> Optional[Dict[str, Any]]:
    """单 ID 直接 GET `/<ad_id>` —— 详见 `fetch_campaign_by_id` docstring。"""
    fields = fields or DEFAULT_AD_FIELDS
    api = api or _build_api(message)
    try:
        obj = Ad(fbid=ad_id, api=api.api).api_get(fields=fields)
    except FacebookRequestError as e:
        logger.warning("fetch_ad_by_id: %s failed: %s", ad_id, e.api_error_message())
        return None
    data = obj.export_all_data() if hasattr(obj, "export_all_data") else dict(obj)
    _fix_date_time(data)
    _add_account_id(data, _strip_act_prefix(message["account_id"]))
    return data


_ID_BATCH_SIZE = 50


def _fetch_by_ids_in_batch(
    message: Mapping[str, Any],
    ids: List[str],
    edge_class,
    fields: List[str],
    api: API,
) -> List[Dict[str, Any]]:
    """per-id `Entity(fbid).api_get()` 的批量版,用 FB Batch API 50 个一批。
    用 batch 而非 `?filtering=[id IN ...]`:后者更费 ads_management 配额,dev tier 撑不住。
    """
    account_id = _strip_act_prefix(message["account_id"])
    out: List[Dict[str, Any]] = []

    def _on_success(eid):
        def cb(response):
            data = response.json()
            _fix_date_time(data)
            _add_account_id(data, account_id)
            out.append(data)
        return cb

    def _on_failure(eid):
        def cb(response):
            logger.warning("batch fetch %s failed: %s", eid, response.body())
        return cb

    for i in range(0, len(ids), _ID_BATCH_SIZE):
        chunk = ids[i:i + _ID_BATCH_SIZE]
        batch = api.api.new_batch()
        for eid in chunk:
            edge_class(fbid=eid, api=api.api).api_get(
                fields=fields, batch=batch,
                success=_on_success(eid), failure=_on_failure(eid),
            )
        while batch:
            batch = batch.execute()
    return out


def fetch_ads_by_ids(
    message: Mapping[str, Any],
    ad_ids: List[str],
    fields: Optional[List[str]] = None,
    api: Optional[API] = None,
) -> List[Dict[str, Any]]:
    api = api or _build_api(message)
    return _fetch_by_ids_in_batch(message, ad_ids, Ad, fields or DEFAULT_AD_FIELDS, api)


def fetch_adsets_by_ids(
    message: Mapping[str, Any],
    adset_ids: List[str],
    fields: Optional[List[str]] = None,
    api: Optional[API] = None,
) -> List[Dict[str, Any]]:
    api = api or _build_api(message)
    return _fetch_by_ids_in_batch(message, adset_ids, AdSet, fields or DEFAULT_ADSET_FIELDS, api)


def fetch_campaigns_by_ids(
    message: Mapping[str, Any],
    campaign_ids: List[str],
    fields: Optional[List[str]] = None,
    api: Optional[API] = None,
) -> List[Dict[str, Any]]:
    api = api or _build_api(message)
    return _fetch_by_ids_in_batch(message, campaign_ids, Campaign, fields or DEFAULT_CAMPAIGN_FIELDS, api)


# ---- 按父 id 列子级(绕开子级 updated_time)----------------------------------
# 父级状态翻转(暂停/重开系列或组)时,FB 把子级 effective_status 级联改成
# CAMPAIGN_PAUSED/ADSET_PAUSED,但**不** bump 子级自己的 updated_time。靠 updated_time
# 的"近期变动"增量因此漏掉子级。这里按变动父级的 edge 直接列子级,只按
# effective_status 过滤、不卡 updated_time。

def _fetch_under_parents(
    message: Mapping[str, Any],
    parent_ids: Iterable[str],
    parent_class,
    edge_getter: str,
    entity_prefix: str,
    fields: List[str],
    filter_statuses: Optional[List[str]],
    api: API,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    account_id = _strip_act_prefix(message["account_id"])
    params = _build_filter_params(
        entity_prefix=entity_prefix,
        status_field="effective_status",
        filter_statuses=filter_statuses,
        since_timestamp=None,
        page_size=page_size,
    )
    out: List[Dict[str, Any]] = []
    for pid in parent_ids:
        getter = getattr(parent_class(fbid=pid, api=api.api), edge_getter)
        out.extend(_normalize(getter(params=params, fields=fields), account_id))
    return out


def fetch_adsets_under_campaigns(
    message: Mapping[str, Any],
    campaign_ids: List[str],
    fields: Optional[List[str]] = None,
    filter_statuses: Optional[List[str]] = None,
    api: Optional[API] = None,
) -> List[Dict[str, Any]]:
    api = api or _build_api(message)
    return _fetch_under_parents(
        message, campaign_ids, Campaign, "get_ad_sets", "adset",
        fields or DEFAULT_ADSET_FIELDS, filter_statuses, api,
    )


def fetch_ads_under_campaigns(
    message: Mapping[str, Any],
    campaign_ids: List[str],
    fields: Optional[List[str]] = None,
    filter_statuses: Optional[List[str]] = None,
    api: Optional[API] = None,
) -> List[Dict[str, Any]]:
    api = api or _build_api(message)
    return _fetch_under_parents(
        message, campaign_ids, Campaign, "get_ads", "ad",
        fields or DEFAULT_AD_FIELDS, filter_statuses, api,
    )


def fetch_ads_under_adsets(
    message: Mapping[str, Any],
    adset_ids: List[str],
    fields: Optional[List[str]] = None,
    filter_statuses: Optional[List[str]] = None,
    api: Optional[API] = None,
) -> List[Dict[str, Any]]:
    api = api or _build_api(message)
    return _fetch_under_parents(
        message, adset_ids, AdSet, "get_ads", "ad",
        fields or DEFAULT_AD_FIELDS, filter_statuses, api,
    )


def fetch_ad_account(
    message: Mapping[str, Any],
    fields: Optional[List[str]] = None,
    api: Optional[API] = None,
) -> Dict[str, Any]:
    """Fetch the AdAccount object itself (one record).

    Mirrors streams.AdAccount.list_objects — 包括对 owner / funding_source_details
    两个权限相关字段的 fallback 重试 (airbyte oncall #3167 / #3031)。
    doc: https://developers.facebook.com/docs/marketing-api/reference/ad-account
    """
    fields = list(fields or DEFAULT_AD_ACCOUNT_FIELDS)
    account_id_raw = message["account_id"]
    account_id = _strip_act_prefix(account_id_raw)
    api = api or _build_api(message)
    fbid = api.get_account(account_id=account_id).get_id() or f"act_{account_id}"

    def _do_fetch(fld: List[str]):
        return FBAdAccount(fbid, api=api.api).api_get(fields=fld)

    try:
        full = _do_fetch(fields)
    except FacebookRequestError as e:
        # airbyte oncall #3167: account 看似有权限但 owner 字段拒绝
        if e.api_error_code() == 200 and e.api_error_message() == \
                "(#200) Requires business_management permission to manage the object":
            if "owner" in fields:
                fields.remove("owner")
                full = _do_fetch(fields)
            else:
                raise
        # airbyte oncall #3031: funding_source_details 即便有 MANAGE 也偶发 100/Unsupported
        elif e.api_error_code() == 100 and e.api_error_message() == \
                "Unsupported request - method type: get":
            if "funding_source_details" in fields:
                fields.remove("funding_source_details")
                full = _do_fetch(fields)
            else:
                raise
        else:
            raise

    data = full.export_all_data() if hasattr(full, "export_all_data") else dict(full)
    _fix_date_time(data)
    _add_account_id(data, account_id)
    logger.info("fetch_ad_account: account=%s -> 1 row", account_id_raw)
    return data


def fetch_ad_creatives(
    message: Mapping[str, Any],
    fields: Optional[List[str]] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """List ALL ad creatives under the account (append-only stream).

    Mirrors streams.AdCreatives (FBMarketingStream, entity_prefix="adcreative").
    无 status/incremental filter,thumbnail_data_url 是 airbyte 端 base64 计算
    字段不向 FB 请求,默认字段已排除。
    doc: https://developers.facebook.com/docs/marketing-api/reference/ad-creative
    """
    fields = fields or DEFAULT_AD_CREATIVE_FIELDS
    account_id_raw = message["account_id"]
    account_id = _strip_act_prefix(account_id_raw)
    account = _build_api(message).get_account(account_id=account_id)
    params: Dict[str, Any] = {"limit": page_size}
    rows = _normalize(account.get_ad_creatives(params=params, fields=fields), account_id)
    logger.info("fetch_ad_creatives: account=%s -> %d rows", account_id_raw, len(rows))
    return rows


def fetch_ad_creatives_from_ads(
    message: Mapping[str, Any],
    creative_fields: Optional[List[str]] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """Two-step: list ads -> dedup creative_id -> per-creative api_get.

    Mirrors streams.AdCreativesFromAds —— 大账户用 get_ad_creatives 直拉容易撞
    "Please reduce the amount of data" (airbyte oncall #11128),改成先列 ads
    取 creative.id 再逐个 api_get 拿详情。

    doc: https://developers.facebook.com/docs/marketing-api/reference/adgroup
    """
    creative_fields = creative_fields or [
        f for f in DEFAULT_AD_CREATIVE_FIELDS if f not in ("thumbnail_data_url", "account_id")
    ]
    account_id_raw = message["account_id"]
    account_id = _strip_act_prefix(account_id_raw)
    account = _build_api(message).get_account(account_id=account_id)

    seen_creative_ids = set()
    out: List[Dict[str, Any]] = []
    ad_iter = account.get_ads(params={"limit": page_size}, fields=["id", "creative"])
    for ad in ad_iter:
        ad_data = ad.export_all_data() if hasattr(ad, "export_all_data") else dict(ad)
        creative_id = (ad_data.get("creative") or {}).get("id")
        if not creative_id or creative_id in seen_creative_ids:
            continue
        seen_creative_ids.add(creative_id)
        try:
            creative = FBAdCreative(creative_id).api_get(fields=creative_fields)
        except FacebookRequestError as e:
            logger.warning("fetch_ad_creatives_from_ads: creative %s failed: %s", creative_id, e)
            continue
        data = creative.export_all_data() if hasattr(creative, "export_all_data") else dict(creative)
        _fix_date_time(data)
        _add_account_id(data, account_id)
        out.append(data)
    logger.info("fetch_ad_creatives_from_ads: account=%s -> %d creatives", account_id_raw, len(out))
    return out


def fetch_videos(
    message: Mapping[str, Any],
    fields: Optional[List[str]] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """List ALL videos under the account.

    Mirrors streams.Videos (FBMarketingReversedIncrementalStream, entity_prefix=
    "video")。airbyte 注释明确"Remove filtering as it is not working since
    2023-01-13",所以不传 filtering;同样把 account_id 从 fields 排除,统一由
    _add_account_id 注入。Reversed 流的"读到 cursor 就 stop"逻辑这里不实现,
    上层自己按 updated_time 截断。
    doc: https://developers.facebook.com/docs/marketing-api/reference/video
    """
    fields = fields or DEFAULT_VIDEO_FIELDS
    account_id_raw = message["account_id"]
    account_id = _strip_act_prefix(account_id_raw)
    account = _build_api(message).get_account(account_id=account_id)
    rows = _normalize(account.get_ad_videos(params={"limit": page_size}, fields=fields), account_id)
    logger.info("fetch_videos: account=%s -> %d rows", account_id_raw, len(rows))
    return rows


def fetch_activities(
    message: Mapping[str, Any],
    fields: Optional[List[str]] = None,
    since_timestamp: Optional[int] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """List ALL ad activities (audit log).

    Mirrors streams.Activities (FBMarketingIncrementalStream, entity_prefix=
    "activity", cursor_field="event_time", primary_key=None)。注意它的
    _state_filter 用 {"since": int(timestamp)} 直接放 params,不是 filtering
    数组,跟 Ads/AdSets/Campaigns 的语义不同 —— 这里照搬。account_id 同样从
    fields 排除。
    doc: https://developers.facebook.com/docs/marketing-api/reference/ad-activity
    """
    fields = fields or DEFAULT_ACTIVITY_FIELDS
    account_id_raw = message["account_id"]
    account_id = _strip_act_prefix(account_id_raw)
    account = _build_api(message).get_account(account_id=account_id)
    params: Dict[str, Any] = {"limit": page_size}
    if since_timestamp is not None:
        params["since"] = int(since_timestamp)
    rows = _normalize(account.get_activities(fields=fields, params=params), account_id)
    logger.info("fetch_activities: account=%s -> %d rows", account_id_raw, len(rows))
    return rows


def fetch_custom_conversions(
    message: Mapping[str, Any],
    fields: Optional[List[str]] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """List ALL custom conversions.

    Mirrors streams.CustomConversions (FBMarketingStream, entity_prefix=
    "customconversion")。
    doc: https://developers.facebook.com/docs/marketing-api/reference/custom-conversion
    """
    fields = fields or DEFAULT_CUSTOM_CONVERSION_FIELDS
    account_id_raw = message["account_id"]
    account_id = _strip_act_prefix(account_id_raw)
    account = _build_api(message).get_account(account_id=account_id)
    rows = _normalize(
        account.get_custom_conversions(params={"limit": page_size}, fields=fields),
        account_id,
    )
    logger.info("fetch_custom_conversions: account=%s -> %d rows", account_id_raw, len(rows))
    return rows


def fetch_custom_audiences(
    message: Mapping[str, Any],
    fields: Optional[List[str]] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """List ALL custom audiences.

    Mirrors streams.CustomAudiences (FBMarketingStream, entity_prefix=
    "customaudience", fields_exceptions=["rule"])。默认 fields 已排除 'rule'
    避免 "Please reduce the amount of data" (airbyte oncall #2765);要 rule
    自行 opt-in。
    doc: https://developers.facebook.com/docs/marketing-api/reference/custom-audience
    """
    fields = fields or DEFAULT_CUSTOM_AUDIENCE_FIELDS
    account_id_raw = message["account_id"]
    account_id = _strip_act_prefix(account_id_raw)
    account = _build_api(message).get_account(account_id=account_id)
    rows = _normalize(
        account.get_custom_audiences(params={"limit": page_size}, fields=fields),
        account_id,
    )
    logger.info("fetch_custom_audiences: account=%s -> %d rows", account_id_raw, len(rows))
    return rows


def fetch_images(
    message: Mapping[str, Any],
    fields: Optional[List[str]] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """List ALL ad images under the account.

    Mirrors streams.Images (FBMarketingReversedIncrementalStream)。同 Videos,
    Reversed 流的 cursor 截断逻辑不在这里实现,上层自行处理。
    doc: https://developers.facebook.com/docs/marketing-api/reference/ad-image
    """
    fields = fields or DEFAULT_IMAGE_FIELDS
    account_id_raw = message["account_id"]
    account_id = _strip_act_prefix(account_id_raw)
    account = _build_api(message).get_account(account_id=account_id)
    rows = _normalize(
        account.get_ad_images(params={"limit": page_size}, fields=fields),
        account_id,
    )
    # AdImage 用作存在性校验的 status enum 触达点(airbyte 通过 deleted 标记)
    _ = AdImage  # 引用一下,IDE 不会判定 unused;运行时 status 字段直接走 dict
    logger.info("fetch_images: account=%s -> %d rows", account_id_raw, len(rows))
    return rows
