"""ad_sync_new.pipeline:把 .airbyte 暴露的 airbyte 原子接口组装成"一户一天
的完整取数流程",跟 fb_account_consumer_async.py 的 fetch_data() 需要的数据
集合一一对应。

约定:
  - 不修改 .airbyte 内任何代码,只 import + 调用
  - 不做业务转换:每个 value 都是 list[dict] (或 dict),FB 原始格式
  - 单一入口 fetch_all(message, fetch_day),下游想写 doris / mongo / JSON 都行

返回 dict 的 key 与 fb_account_consumer_async 内的语义一一对应:
  ad_account                  — AdAccount 单条元数据 (spend_cap/balance/tz/amount_spent)
  campaigns                   — 户下全部 campaign 元数据 (含 0 成效)
  ad_sets                     — 户下全部 adset 元数据 (含 0 成效)
  ads                         — 户下全部 ad 元数据 (含 0 成效,含 creative)
  account_insights            — level=account 一天成效 (合计行,1 条或 0 条)
  ad_insights                 — level=ad 主报告:一天 × 全部 insights_fields + video
  breakdown_age_gender        — level=ad × age+gender breakdown
  frequency_campaign_{3,5,7}d — level=campaign × 多日 frequency
  frequency_adset_{3,5,7}d    — level=adset × 多日 frequency
  frequency_ad_{3,5,7}d       — level=ad × 多日 frequency
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adsinsights import AdsInsights

from conf.api_conf import get_proxies

from tasks.ad_sync_new.airbyte import (
    API,
    DateInterval,
    InsightAsyncJob,
    InsightAsyncJobManager,
    build_insight_params,
    fetch_ad_account,
    fetch_ad_sets,
    fetch_ads,
    fetch_ads_by_ids,
    fetch_ads_under_adsets,
    fetch_ads_under_campaigns,
    fetch_adsets_by_ids,
    fetch_adsets_under_campaigns,
    fetch_campaigns,
    fetch_campaigns_by_ids,
)
from tasks.ad_sync_new.consts import is_review


logger = logging.getLogger(__name__)


# ── 与 fb_account_consumer_async.insights_fields 对齐 ─────────────────────────
INSIGHTS_FIELDS: List[str] = [
    AdsInsights.Field.spend,
    AdsInsights.Field.impressions,
    AdsInsights.Field.clicks,
    AdsInsights.Field.unique_clicks,
    AdsInsights.Field.actions,
    AdsInsights.Field.action_values,
    AdsInsights.Field.frequency,
    AdsInsights.Field.reach,
    AdsInsights.Field.cpm,
    AdsInsights.Field.ctr,
    AdsInsights.Field.cpc,
    AdsInsights.Field.inline_link_clicks,
    AdsInsights.Field.inline_link_click_ctr,
    AdsInsights.Field.unique_inline_link_clicks,
    AdsInsights.Field.unique_inline_link_click_ctr,
    AdsInsights.Field.conversions,
]

# ── 与 fb_account_consumer_async.video_insights_fields 对齐 ──────────────────
VIDEO_INSIGHTS_FIELDS: List[str] = [
    AdsInsights.Field.video_play_actions,
    AdsInsights.Field.video_p25_watched_actions,
    AdsInsights.Field.video_p50_watched_actions,
    AdsInsights.Field.video_p75_watched_actions,
    AdsInsights.Field.video_p95_watched_actions,
    AdsInsights.Field.video_p100_watched_actions,
]

# ── 主报告 + breakdown 额外要的层级 id/name ──────────────────────────────────
AD_LEVEL_EXTRA_FIELDS: List[str] = [
    "campaign_id", "campaign_name",
    "adset_id", "adset_name",
    "ad_id", "ad_name",
    "date_start", "date_stop",
]

# ── 跟 consumer._submit_frequency_reports 一致 ───────────────────────────────
FREQUENCY_WINDOWS = [3, 5, 7]
# frequency 9 个报告超时即放弃(不重试/拆分),超时的户当天缺这份数据
FREQUENCY_JOB_TIMEOUT_MINUTES = 20
LEVEL_TO_ID_FIELD = {
    "campaign": "campaign_id",
    "adset": "adset_id",
    "ad": "ad_id",
}

# 实体 list 的"两阶段"过滤分组:
#   - ACTIVE 组:当前还在账户里能看到的,需要无视 updated_time(老 adset 即使
#                几天没改过也要拉到)
#   - DELETED 组:删除态,需要 updated_time 窗口卡住,只拉近期删的,避免历史
#                几年前删的把 x-app-usage 撑爆
DELETED_STATUSES = ["DELETED", "ARCHIVED"]
ACTIVE_AD_STATUSES = [s for s in (
    "ACTIVE", "ADSET_PAUSED", "CAMPAIGN_PAUSED", "DISAPPROVED", "IN_PROCESS",
    "PAUSED", "PENDING_BILLING_INFO", "PENDING_REVIEW", "PREAPPROVED",
    "WITH_ISSUES",
)]
ACTIVE_ADSET_STATUSES = [s for s in (
    "ACTIVE", "CAMPAIGN_PAUSED", "IN_PROCESS", "PAUSED", "WITH_ISSUES",
)]
ACTIVE_CAMPAIGN_STATUSES = [s for s in (
    "ACTIVE", "IN_PROCESS", "PAUSED", "WITH_ISSUES",
)]

# ad_fields 与 consumer.ad_fields 对齐 —— 拉 ad 列表时带上 creative 子结构,
# 这样下游 _extract_creative_info 可以直接取
# 实体元数据字段 —— 全部与 fb_account_consumer_async 内的 *_fields 对齐,
# 不用 airbyte 默认全集(default 都几十个),省 payload + 省 BUC 配额。
# updated_time 是 _state_filter 用的,自动包含进来以便下游知道实体最后修改时间。

# 对齐 consumer.account_fields
AD_ACCOUNT_FIELDS: List[str] = [
    "account_id",
    "name",
    "account_status",
    "created_time",
    "timezone_name",
    "spend_cap",
    "amount_spent",
]

# 对齐 consumer.campaign_fields + id/updated_time
CAMPAIGNS_LIST_FIELDS: List[str] = [
    "id",
    "name",
    "status",
    "effective_status",
    "daily_budget",
    "created_time",
    "updated_time",
    "objective",
]

# 精简到 transform 实际消费的字段:
#   id (键)、name (ad_set_name)、daily_budget (adset_budget)、
#   status (实体自身开关,落 doris status 列)、
#   effective_status (兜底 fallback dict 时填 "DELETED",落 doris delivery/delivery_str)、
#   campaign_id (transform 把"没成效的 adset"用它挂到所属 campaign 做 budget 累加 ——
#                没这个字段就没法知道该 adset 属于哪个 campaign)、
#   learning_stage_info (学习期状态,只有 adset 层有,落 doris learning_stage)、
#   promoted_object (推广对象,pixel_id / custom_event_type 只有 adset 层有)。
# updated_time 只用于 server-side filter,不需要返回响应里;created_time 没人读。
AD_SETS_LIST_FIELDS: List[str] = [
    "id",
    "name",
    "daily_budget",
    "status",
    "effective_status",
    "campaign_id",
    "learning_stage_info",
    "promoted_object",
]


ADS_LIST_FIELDS: List[str] = [
    Ad.Field.id,
    Ad.Field.name,
    Ad.Field.adset_id,
    Ad.Field.campaign_id,
    Ad.Field.created_time,
    Ad.Field.updated_time,
    Ad.Field.status,
    Ad.Field.effective_status,
    "creative{effective_object_story_id,asset_feed_spec,"
    "object_story_spec{link_data{link},video_data{call_to_action{value{link}}}},"
    "call_to_action{value{link}}}",
]


# ── helpers ──────────────────────────────────────────────────────────────────

def _build_api(message: Mapping[str, Any]) -> API:
    return API(
        app_id=message["app_id"],
        app_secret=message["app_secret"],
        access_token=message["access_token"],
        proxies=get_proxies(message["proxy"]),
    )


def _strip_act(account_id_raw: str) -> str:
    return account_id_raw[len("act_"):] if account_id_raw.startswith("act_") else account_id_raw


def _extract_insight_entity_ids(
    result: Mapping[str, Any],
) -> Dict[str, set]:
    """从已经填好的 result(所有 insight 报告并集)抽出 ad/adset/campaign id 集合。
    用于 entity 拉取阶段按 insight 命中的 id 兜底补元数据。

    扫所有 list 类型的 result value,只要行里有 ad_id/adset_id/campaign_id
    就加到对应 set。这样无论 ad_insights / breakdowns / frequency 哪个报告里
    出现的 entity,只要 insight 拉到了就不会漏元数据。
    """
    ids: Dict[str, set] = {"campaign": set(), "adset": set(), "ad": set()}
    for key, rows in result.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            for level, id_field in LEVEL_TO_ID_FIELD.items():
                v = row.get(id_field)
                if v:
                    ids[level].add(str(v))
    return ids


def _fetch_entity_list(
    fetch_fn,
    message: Mapping[str, Any],
    *,
    active_statuses: List[str],
    since_ts: Optional[int],
    insight_ids: Optional[set],
    extra_kwargs: Optional[Dict[str, Any]] = None,
    batch_fetch_fn=None,
    api: Optional[API] = None,
) -> tuple[List[Dict[str, Any]], set]:
    """拉实体元数据,只保留"有 insight"和"近期变动"的实体。两步:

      A. 近期变动:filter_statuses = ACTIVE-ish + [DELETED, ARCHIVED] + since_timestamp=since_ts
         → 一次 GET `/<account>/<edge>?filtering=...` 拿"最近 N 小时变动的活/删实体"。
         since_ts=None 时整步跳过(review / dev tier 走这条路径)。

      B. insight 命中兜底:ids ∈ (insight_ids - 已拉到的)
         → 补"有成效但 updated_time 老"的实体(典型:跑了很久的稳定广告)。
         走 FB Batch API 把 per-id `Entity(fbid).api_get()` 50 个一批打包,而不是
         `?filtering=[id IN ...]` 的 account-edge 调用 —— 配额仍按 per-id 单调用算
         (最省 `ads_management`,dev tier 更能撑),只省 HTTP 往返。

    insight_ids 为 None / 空 → 跳过 B 步;batch_fetch_fn=None → 也跳过 B 步。

    返回 (out, recent_change_ids):recent_change_ids 是"近期变动"一步(A)拉到的
    id 集合,供上层对状态翻转的父级按 id 展开子级。
    """
    extra_kwargs = extra_kwargs or {}
    seen: set = set()
    out: List[Dict[str, Any]] = []

    def _ingest(rows):
        for row in rows:
            rid = row.get("id")
            if rid is None:
                out.append(row)
                continue
            rid = str(rid)
            if rid in seen:
                continue
            seen.add(rid)
            out.append(row)

    # 近期变动:filter_statuses = ACTIVE-ish + [DELETED, ARCHIVED],一次 GET 把活的 +
    # 近期删/归档的实体一起拉回来。
    # since_ts 非 None ⟺ standard_access(fetch_all 已按 tier 门控,dev tier / review
    # 的 since_ts=None 在此整步跳过),所以这里直接带 status 过滤即可 —— dev tier 撞
    # 17/2446079 的那条"只传 updated_time"路径根本走不到。
    if since_ts is not None:
        _ingest(fetch_fn(
            message,
            since_timestamp=since_ts,
            filter_statuses=list(active_statuses) + DELETED_STATUSES,
            api=api,
            **extra_kwargs,
        ))
    recent_change_ids = set(seen)

    # insight 命中兜底:FB Batch API,缺失 id 50 个一批。
    if insight_ids and batch_fetch_fn is not None:
        missing = [i for i in insight_ids if i not in seen]
        logger.info(
            "[%s] 近期变动=%d 条, insight 命中=%d 个 id (已 join=%d, 待按 id 兜底=%d)",
            fetch_fn.__name__, len(seen), len(insight_ids),
            len(insight_ids) - len(missing), len(missing),
        )
        _ingest(batch_fetch_fn(message, missing, fields=extra_kwargs.get("fields"), api=api))

    return out, recent_change_ids


def _build_insight_job(
    api: API,
    account,
    tz_name: str,
    interval: DateInterval,
    fields: List[str],
    level: str = "ad",
    breakdowns: Optional[List[str]] = None,
    primary_key: Optional[List[str]] = None,
    job_timeout_minutes: int = 60,
    name: str = "",
    abandon_on_timeout: bool = False,
) -> InsightAsyncJob:
    """构造一个 InsightAsyncJob,挂上 _report_name 属性供并行 manager 路由
    结果。不启动 job —— 启动由 InsightAsyncJobManager 统一调度,这样 12 个
    report 可以并发跑。
    """
    params = build_insight_params(
        fields=fields,
        timezone_name=tz_name,
        level=level,
        breakdowns=breakdowns,
    )
    if primary_key is None:
        primary_key = [f"{level}_id", "date_start"]
        if breakdowns:
            primary_key = primary_key + list(breakdowns)

    job = InsightAsyncJob(
        api=api.api,
        edge_object=account,
        interval=interval,
        params=params,
        job_timeout=timedelta(minutes=job_timeout_minutes),
        primary_key=primary_key,
        abandon_on_timeout=abandon_on_timeout,
    )
    # 给 job 打标签:manager 直接 yield 同一个 job;split 出来的子 job
    # 由 async_job._split_by_edge_class / _split_by_fields_parent 透传 _report_name
    job._report_name = name  # type: ignore[attr-defined]
    return job


def fetch_entities(
    message: Mapping[str, Any],
    api: API,
    insight_result: Mapping[str, Any],
    *,
    entity_since_ts: Optional[int],
) -> Dict[str, List[Dict[str, Any]]]:
    """拉 ads/ad_sets/campaigns 元数据 —— 跟成效拉取解耦的独立一步。

    依赖 insight_result 里已填好的成效报告(取命中 id 兜底)。
    顺序必须 ads → ad_sets → campaigns:子级先到,才能把"只改了开关、无成效"的
    ad 的 adset_id/campaign_id 加进父级兜底集合 —— 否则父级 updated_time 没变又无
    insight 命中,会整个缺元数据,transform 把系列/组 name 置 None 并误标 DELETED。

    三级拉完后再做一步反向展开(_expand_changed_parents):对本轮"近期变动"
    拉到的父级,按父 id 重拉子级,修复"系列/组暂停后子级状态停在投放中"。
    """
    insight_ids = _extract_insight_entity_ids(insight_result)

    ads, _ = _fetch_entity_list(
        fetch_ads, message,
        active_statuses=ACTIVE_AD_STATUSES,
        since_ts=entity_since_ts,
        insight_ids=insight_ids["ad"],
        extra_kwargs={"fields": ADS_LIST_FIELDS},
        batch_fetch_fn=fetch_ads_by_ids,
        api=api,
    )

    adset_need = set(insight_ids["adset"])
    campaign_need = set(insight_ids["campaign"])
    for ad in ads:
        if ad.get("adset_id"):
            adset_need.add(str(ad["adset_id"]))
        if ad.get("campaign_id"):
            campaign_need.add(str(ad["campaign_id"]))

    ad_sets, adset_recent = _fetch_entity_list(
        fetch_ad_sets, message,
        active_statuses=ACTIVE_ADSET_STATUSES,
        since_ts=entity_since_ts,
        insight_ids=adset_need,
        extra_kwargs={"fields": AD_SETS_LIST_FIELDS},
        batch_fetch_fn=fetch_adsets_by_ids,
        api=api,
    )

    for adset in ad_sets:
        if adset.get("campaign_id"):
            campaign_need.add(str(adset["campaign_id"]))

    campaigns, campaign_recent = _fetch_entity_list(
        fetch_campaigns, message,
        active_statuses=ACTIVE_CAMPAIGN_STATUSES,
        since_ts=entity_since_ts,
        insight_ids=campaign_need,
        extra_kwargs={"fields": CAMPAIGNS_LIST_FIELDS},
        batch_fetch_fn=fetch_campaigns_by_ids,
        api=api,
    )

    _expand_changed_parents(
        message, api, ads, ad_sets,
        campaign_recent=campaign_recent, adset_recent=adset_recent,
    )

    return {"ads": ads, "ad_sets": ad_sets, "campaigns": campaigns}


def _expand_changed_parents(
    message: Mapping[str, Any],
    api: API,
    ads: List[Dict[str, Any]],
    ad_sets: List[Dict[str, Any]],
    *,
    campaign_recent: set,
    adset_recent: set,
) -> None:
    """对"近期变动"一步刚抓到的、状态翻转的父级,按父 id 重拉其子级,刷新子级
    effective_status —— 暂停/重开系列或组时 FB 级联改子级状态但不 bump 子级
    updated_time,子级否则会停在旧状态(系列暂停了广告仍显示投放中)。
    新拉到的子级按 id dedup 合并进 ads / ad_sets(已有的保留,不覆盖)。
    就地修改 ads / ad_sets。
    """
    if not campaign_recent and not adset_recent:
        return

    existing_ad_ids = {str(a["id"]) for a in ads if a.get("id")}
    existing_adset_ids = {str(s["id"]) for s in ad_sets if s.get("id")}
    adset_campaign = {
        str(s["id"]): str(s.get("campaign_id") or "") for s in ad_sets if s.get("id")
    }
    child_ad_statuses = ACTIVE_AD_STATUSES + DELETED_STATUSES
    child_adset_statuses = ACTIVE_ADSET_STATUSES + DELETED_STATUSES

    new_adsets: List[Dict[str, Any]] = []
    new_ads: List[Dict[str, Any]] = []

    if campaign_recent:
        cids = list(campaign_recent)
        new_adsets += fetch_adsets_under_campaigns(
            message, cids, fields=AD_SETS_LIST_FIELDS,
            filter_statuses=child_adset_statuses, api=api,
        )
        # Campaign.get_ads 一次返回系列下全部 ad(跨其所有 adset),不必再逐 adset 展开
        new_ads += fetch_ads_under_campaigns(
            message, cids, fields=ADS_LIST_FIELDS,
            filter_statuses=child_ad_statuses, api=api,
        )

    # 只展开"自己变了、但所属 campaign 没变"的 adset;campaign 变了的子级上面已覆盖
    lone_adsets = [
        sid for sid in adset_recent if adset_campaign.get(sid) not in campaign_recent
    ]
    if lone_adsets:
        new_ads += fetch_ads_under_adsets(
            message, lone_adsets, fields=ADS_LIST_FIELDS,
            filter_statuses=child_ad_statuses, api=api,
        )

    added_adset = added_ad = 0
    for s in new_adsets:
        sid = str(s.get("id") or "")
        if sid and sid not in existing_adset_ids:
            existing_adset_ids.add(sid)
            ad_sets.append(s)
            added_adset += 1
    for a in new_ads:
        aid = str(a.get("id") or "")
        if aid and aid not in existing_ad_ids:
            existing_ad_ids.add(aid)
            ads.append(a)
            added_ad += 1

    logger.info(
        "[expand_changed_parents] 变动 campaign=%d adset=%d -> 补子级 adset=%d ad=%d",
        len(campaign_recent), len(adset_recent), added_adset, added_ad,
    )


def fetch_all(
    message: Mapping[str, Any],
    fetch_day: str,
    *,
    include_entities: bool = True,
    include_frequency: bool = True,
    include_breakdowns: bool = True,
    entity_lookback_hours: Optional[int] = 2,
    # 故意 > account_consumer 账户级 kill 阈值(最大 ACCOUNT_KILL_REVIEW_SEC=40min):job 级
    # 超时永不触发 → 不重试不拆分,一个 AdReportRun 跑到底,账号级 kill 唯一兜底
    job_timeout_minutes: int = 70,
) -> Dict[str, Any]:
    """拉取 fb_account_consumer_async 需要的全部 raw 数据(一户一天)。

    Args:
        message: 与 fb_account_consumer 一致的 dict
                 (account_id / app_id / app_secret / access_token / proxy)
        fetch_day: "YYYY-MM-DD" —— 账户本地时区的那一天 (调用方自己换算 tz)
        include_entities: 是否拉 Campaigns/AdSets/Ads 元数据列表 (0 成效也带回)
        include_frequency: 是否拉 3/5/7d frequency (3 levels × 3 windows = 9 个 async report);
                 仅 review 跑实际拉取,hourly 跳过(见下方 is_rev 门控)
        include_breakdowns: 是否拉 age × gender breakdown;同 frequency,仅 review 跑拉取
        entity_lookback_hours: "近期变动" 一步的 updated_time 窗口下限,
                 `updated_time >= now - N 小时`(UTC)。consumer 每小时跑一次,
                 N=2 给 1h cron 一个 buffer 防止 cron 漂移漏数据;**review 模式下
                 完全跳过"近期变动"一步**,只靠 insight 命中 id 兜底。
                 设为 None 也等价于跳过"近期变动"一步。
        job_timeout_minutes: 单个 async report 的硬超时

    Returns:
        dict,详见模块 docstring。所有 value 都是 list[dict] 或 dict。
    """
    account_id_raw = message["account_id"]
    account_id = _strip_act(account_id_raw)

    api = _build_api(message)
    account = api.get_account(account_id=account_id)
    tz_name = account.get("timezone_name")
    if not tz_name:
        raise RuntimeError(f"account {account_id_raw} has no timezone_name")

    day_dt = datetime.strptime(fetch_day, "%Y-%m-%d").date()
    day_interval = DateInterval(start=day_dt, end=day_dt)

    result: Dict[str, Any] = {}

    _t_meta_start = time.monotonic()
    # ── 1) AdAccount 单条元数据 (consumer 只需 7 个字段) ──
    result["ad_account"] = fetch_ad_account(message, fields=AD_ACCOUNT_FIELDS, api=api)

    # ── 2) 实体列表准备:算 entity_since_ts;实体 list 延后到 insight 跑完才发起 ──
    # entity list 走"近期变动 + insight 命中 id 兜底"模式 —— 只拉"有成效"或"近期
    # 改过"的实体,把暂停且长期没动过的几万行无成效记录挡在 API 之外。
    # 下面三种情况都让 entity_since_ts=None,从而**整步跳过** `/<account>/<edge>` 调用,
    # 只靠"insight 命中 id 兜底"per-id 拉:
    #   - review=True(整日回填):避免回填时拉一堆"现在还活但跟那天无关"的实体
    #   - dev tier(非 standard_access):线上多进程并发跑同 dev 时,即便 filter 只剩
    #     updated_time 仍持续撞 17/2446079(见 2026-05-14 线上日志 Logs-16_47_34)。
    #     dev tier 配额太低撑不住 /<account>/adsets 这种 account-edge 调用
    #   - 没配 lookback_hours
    tier = message.get("ads_api_access_tier")
    is_rev = is_review(message["date"])
    # frequency(3/5/7d 滚动)/ age_gender 拆分不需要小时级刷新,只在每日 review 跑拉一次,
    # hourly 跳过 —— 每户省掉 9+1 份 async report,大幅降 insights 节流压力。
    include_frequency = include_frequency and is_rev
    include_breakdowns = include_breakdowns and is_rev
    entity_since_ts: Optional[int] = None
    if (
        include_entities
        and entity_lookback_hours is not None
        and not is_rev
        and tier == "standard_access"
    ):
        lookback_dt = datetime.now(timezone.utc) - timedelta(hours=entity_lookback_hours)
        entity_since_ts = int(lookback_dt.timestamp())

    # ── 3 ~ 6) 全部 async insights 一次性塞给一个 manager 并发跑 ──
    # 旧版每个 report 一个 manager,串行 → 12 × 30s = 6+ min。
    # 新版一个 manager 调度全部,墙钟 ≈ 最慢那个 report ≈ 30-60s。
    insight_jobs: List[InsightAsyncJob] = []

    def _add(name: str, *, job_timeout_minutes: int = job_timeout_minutes, abandon_on_timeout: bool = False, **kwargs):
        result.setdefault(name, [])  # 占位,即使空也保证 key 存在
        insight_jobs.append(_build_insight_job(
            api=api,
            account=account,
            tz_name=tz_name,
            job_timeout_minutes=job_timeout_minutes,
            abandon_on_timeout=abandon_on_timeout,
            name=name,
            **kwargs,
        ))

    # 3) level=account 一天成效
    _add(
        "account_insights",
        interval=day_interval,
        fields=list(INSIGHTS_FIELDS) + ["date_start", "date_stop"],
        level="account",
        primary_key=["date_start"],
    )

    # 4) level=ad 主报告 (insights + video + 层级 id/name)
    _add(
        "ad_insights",
        interval=day_interval,
        fields=list(INSIGHTS_FIELDS) + list(VIDEO_INSIGHTS_FIELDS) + list(AD_LEVEL_EXTRA_FIELDS),
        level="ad",
    )

    # 5) age × gender breakdown
    if include_breakdowns:
        _add(
            "breakdown_age_gender",
            interval=day_interval,
            fields=[
                AdsInsights.Field.impressions,
                AdsInsights.Field.spend,
                AdsInsights.Field.actions,
                AdsInsights.Field.action_values,
                AdsInsights.Field.conversions,
                "ad_id", "date_start", "date_stop",
            ],
            level="ad",
            breakdowns=["age", "gender"],
            primary_key=["ad_id", "date_start", "age", "gender"],
        )

    # 6) frequency 3/5/7d × 3 levels
    # end_date = fetch_day - 1, start_date = end_date - (N - 1) —— 跟
    # fb_account_consumer_async._submit_frequency_reports 同步
    if include_frequency:
        end_date = day_dt - timedelta(days=1)
        for level, id_field in LEVEL_TO_ID_FIELD.items():
            for days in FREQUENCY_WINDOWS:
                start_date = end_date - timedelta(days=days - 1)
                _add(
                    f"frequency_{level}_{days}d",
                    interval=DateInterval(start=start_date, end=end_date),
                    fields=[id_field, AdsInsights.Field.frequency],
                    level=level,
                    primary_key=[id_field, "date_start"],
                    job_timeout_minutes=FREQUENCY_JOB_TIMEOUT_MINUTES,
                    abandon_on_timeout=True,
                )

    _t_insights_start = time.monotonic()
    # 各阶段耗时随完成即打,账户被 40min kill 时也能看到卡在 insights 还是 entities
    logger.info(
        "[fetch_all] account=%s acct_meta 完成 %.1fs,开始 insights(%d 报告)",
        account_id, _t_insights_start - _t_meta_start, len(insight_jobs),
    )
    if insight_jobs:
        manager = InsightAsyncJobManager(
            api=api,
            jobs=iter(insight_jobs),
            account_id=account_id,
        )
        for completed in manager.completed_jobs():
            name = getattr(completed, "_report_name", None)
            if not name:
                # split 出来的子 job 不带 name —— 仅 FB 失败时才会出现
                logger.warning(
                    "[fetch_all][%s] completed job 缺 _report_name (split child?): %s",
                    account_id_raw, completed,
                )
                continue
            if completed.failed:
                # 放弃的 job(frequency 超时 / 拆分无子对象)→ 跳过,该户该天缺这份
                logger.warning(
                    "[fetch_all][%s] 报告 %s 放弃,无数据", account_id_raw, name,
                )
                continue
            for obj in completed.get_result():
                data = obj.export_all_data() if hasattr(obj, "export_all_data") else dict(obj)
                result[name].append(dict(data))

    # ── 7) 实体列表(ads/ad_sets/campaigns)—— 独立成 fetch_entities,跟成效解耦 ──
    _t_entities_start = time.monotonic()
    logger.info(
        "[fetch_all] account=%s insights 完成 %.1fs,开始 entities",
        account_id, _t_entities_start - _t_insights_start,
    )
    if include_entities:
        result.update(
            fetch_entities(message, api, result, entity_since_ts=entity_since_ts)
        )

    logger.info(
        "[fetch_all] account=%s entities 完成 %.1fs",
        account_id, time.monotonic() - _t_entities_start,
    )
    return result


__all__ = [
    "fetch_all",
    "fetch_entities",
    "INSIGHTS_FIELDS",
    "VIDEO_INSIGHTS_FIELDS",
    "AD_LEVEL_EXTRA_FIELDS",
    "ADS_LIST_FIELDS",
    "FREQUENCY_WINDOWS",
    "LEVEL_TO_ID_FIELD",
]
