"""Bundle dict → doris row list 的业务转换层。

入口:`bundle_to_doris_rows(message, bundle) -> List[Dict]`

数据来源:`pipeline.fetch_all(message, fetch_day)` 产出的 16-key dict。

业务移植自 `tasks/ad_sync/fb_account_consumer_async.py:FacebookAdsSyncAsync`,
按 "不引用老代码" 的要求,所有方法在这里重新实现一遍。行级转换逻辑、聚合
规则、agent_line 匹配、status 推导全部对齐老 consumer,保证写出来的 doris
行与老 consumer 字段顺序、字段值都一致 —— 老/新可以双写同一张表对账。

**新增能力(老 consumer 没有)**:`_attach_zero_spend_skeleton`
  把 `bundle["ads"]` 里有、但 `bundle["ad_insights"]` 没有的 ad 补成 0-metric
  insight 行,参与 `_assemble_all_levels` 流程。这样:
    - 今天新建但还没投放出量的 ad 也会进 doris(原 consumer 漏)
    - status 字段反映实体真实 effective_status(原 consumer 缺这条 ad)
  0 成效合并在 ad 层做,父级 adset/campaign 通过 `_build_aggregated_insight`
  自动 cascade(0 成效 ad 聚合到父级 = spend=0 但保留实体)。

字段约定:bundle 各 key 的 row 都是 `AbstractObject.export_all_data()` 出来
的纯 dict,所以 `.get("field")` 跟 SDK 字段名一一对应,不需要再走 FB SDK。
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

from utils.common import (
    LEVEL,
    MinuteFormat,
    SecondFormat,
    build_line_maps,
    get_line_from_campaign_name,
    get_placer_and_department,
    get_platform_lines_cached,
    is_valid_unique_name,
    match_agent_line_by_url,
)
from utils.fb_utils import change_date

from tasks.ad_sync_new.consts import compute_fetch_day, effective_account_dt


logger = logging.getLogger(__name__)


# 业务用到的 status 常量,不依赖 facebook_business
AD_EFFECTIVE_STATUS_ACTIVE = "ACTIVE"

# 层级遍历顺序,与老 consumer.levels 等价
LEVEL_ORDER: List[Optional[LEVEL]] = [None, LEVEL.account, LEVEL.campaign, LEVEL.adset, LEVEL.ad]


class BundleTransform:
    """bundle dict → doris row list 的状态机。

    跟老 `FacebookAdsSyncAsync` 的字段一一对应,只是 entity 字段来源换了:
      - 老:`self.account = AdAccount.api_get(...)` 等 SDK object
      - 新:`self.account = bundle["ad_account"]` 等 dict
    `process_insight_data` 等方法实现保持等价。
    """

    def __init__(self, message: Mapping[str, Any], bundle: Mapping[str, Any]):
        self.message = dict(message)
        self.bundle = bundle

        # account 元数据(单条 dict,由 fetch_ad_account 拉)
        self.account: Dict[str, Any] = dict(bundle.get("ad_account") or {})

        # entity 元数据按 id 索引,供 _assemble_all_levels 查表
        self.campaign_by_id: Dict[str, Dict[str, Any]] = {
            c["id"]: c for c in bundle.get("campaigns", []) if c.get("id")
        }
        self.adset_by_id: Dict[str, Dict[str, Any]] = {
            s["id"]: s for s in bundle.get("ad_sets", []) if s.get("id")
        }
        self.ad_by_id: Dict[str, Dict[str, Any]] = {
            a["id"]: a for a in bundle.get("ads", []) if a.get("id")
        }

        # 当前 walk 状态(仿老 consumer set_field 的指针)
        self.level: Optional[LEVEL] = None
        self.campaign: Optional[Dict[str, Any]] = None
        self.adset: Optional[Dict[str, Any]] = None
        self.ad: Optional[Dict[str, Any]] = None

        # campaign 维度的业务派生字段(每进一个 campaign 重算)
        self.objective: Optional[str] = None
        self.agent_line: Optional[str] = None
        self.placer_id: Optional[str] = self.message.get("placer_id")
        self.department: Optional[str] = None
        self.game_platform: Optional[str] = None

        # 全量线表(含禁用平台), 进程内缓存
        self.plat_map: Dict[str, List[str]] = get_platform_lines_cached()

        # breakdown 索引,由 _build_breakdown_map 填,在 _build_breakdown_json 查
        self.breakdown_map: Dict[str, List[Dict[str, Any]]] = {}

        # frequency_3/5/7d 索引,由 _index_frequency 填
        self.freq_lookup: Dict[str, Dict[str, Dict[str, Any]]] = {
            LEVEL.campaign.value: defaultdict(dict),
            LEVEL.adset.value: defaultdict(dict),
            LEVEL.ad.value: defaultdict(dict),
        }

        # 同账户内重复 url / agent_line 的 Mongo 查询去重(实例级=单账户单线程,无需加锁)
        self._url_match_cache: Dict[tuple, tuple] = {}
        self._placer_dept_cache: Dict[Optional[str], tuple] = {}

    # ── 通用工具(对齐 fb_account_consumer_async 的同名 static) ──────────────

    @staticmethod
    def get_field(obj: Optional[Mapping[str, Any]], field: str, default=None, type_=None):
        if obj and (value := obj.get(field)) is not None:
            return type_(value) if type_ else value
        return default

    @property
    def level_obj(self) -> Optional[Mapping[str, Any]]:
        if self.level is None:
            return None
        return getattr(self, self.level.value, None) if hasattr(self.level, "value") else getattr(self, self.level, None)

    def set_field(self, level: LEVEL, value: Optional[Mapping[str, Any]]) -> None:
        """走到下一层,把下层指针清掉(对齐老 consumer.set_field)"""
        setattr(self, level.value, value)
        self.level = level
        idx = LEVEL_ORDER.index(level)
        for child in LEVEL_ORDER[idx + 1:]:
            if child is not None:
                setattr(self, child.value, None)

    # ── 日期 / 时区(对齐 account_date / fetch_day property) ────────────────

    @property
    def account_date(self) -> datetime:
        tz_name = self.get_field(self.account, "timezone_name")
        # review = 账户本地次日 0 点(目标日未走完钳到现在);hourly = 中国整点的本地时刻。
        return effective_account_dt(self.message["date"], tz_name)

    @property
    def fetch_day(self) -> str:
        tz_name = self.get_field(self.account, "timezone_name")
        return compute_fetch_day(self.message["date"], tz_name)

    # ── action / video / creative 抽取 ───────────────────────────────────────

    @staticmethod
    def _sum_action_value(items):
        """`video_*_actions` 是 [{action_type, value}] 列表,按业界口径全部相加。"""
        return int(sum(float(item.get("value", 0) or 0) for item in (items or [])))

    @staticmethod
    def process_action_metrics(actions, action_values, conversions):
        # 默认 None:区分"FB 没返这个 action"(NULL) 和"FB 返了 action_value=0"(0)
        metrics: Dict[str, Any] = {
            "purchases": None,
            "purchase_values": None,
            "subscriptions": None,
            "subscriptions_value": None,
            "register": None,
            "messaging_conversation_started": None,
            "add_to_cart": None,
            "landing_page_view": None,
        }
        action_type_mapping = {
            "purchase": "purchases",
            "app_install": "app_installs",
            "complete_registration": "register",
            "offsite_conversion.fb_pixel_custom": "subscriptions",
            "offsite_conversion.fb_pixel_lead": "lead",
            "onsite_conversion.messaging_conversation_started_7d": "messaging_conversation_started",
            "add_to_cart": "add_to_cart",
            "landing_page_view": "landing_page_view",
        }
        for action in actions or []:
            action_type = action.get("action_type")
            if action_type in action_type_mapping:
                key = action_type_mapping[action_type]
                metrics[key] = action.get("value", 0)
                metrics[key + "_1dclick"] = action.get("1d_click")

        values = [
            x.get("value", 0)
            for x in (conversions or [])
            if x.get("action_type") == "subscribe_total"
        ]
        metrics["subscriptions"] = int(values[0]) if values else None

        value_type_mapping = {
            "purchase": "purchase_values",
            "offsite_conversion.fb_pixel_custom": "subscriptions_value",
        }
        for action_v in action_values or []:
            action_type = action_v.get("action_type")
            if action_type in value_type_mapping:
                key = value_type_mapping[action_type]
                metrics[key] = action_v.get("value", 0)
                metrics[key + "_1dclick"] = action_v.get("1d_click")
        return metrics

    def _build_video_metrics(self, insight: Mapping[str, Any]) -> Dict[str, int]:
        """ad 层完播率/漏斗 —— 各档 count,rate 由下游 SQL 现算 count / NULLIF(play, 0)。"""
        return {
            "video_play_count": self._sum_action_value(insight.get("video_play_actions")),
            "video_p25_count": self._sum_action_value(insight.get("video_p25_watched_actions")),
            "video_p50_count": self._sum_action_value(insight.get("video_p50_watched_actions")),
            "video_p75_count": self._sum_action_value(insight.get("video_p75_watched_actions")),
            "video_p95_count": self._sum_action_value(insight.get("video_p95_watched_actions")),
            "video_p100_count": self._sum_action_value(insight.get("video_p100_watched_actions")),
        }

    @staticmethod
    def _extract_creative_info(creative: Mapping[str, Any]):
        """从 ad.creative 抽取 (page_id, post_id, landing_url),对齐老 consumer。"""
        page_id = None
        post_id = None
        effective_story_id = (creative or {}).get("effective_object_story_id", "")
        if effective_story_id and "_" in effective_story_id:
            page_id, post_id = effective_story_id.split("_", 1)

        creative = creative or {}
        landing_url = (
            creative.get("call_to_action", {}).get("value", {}).get("link")
            or creative.get("object_story_spec", {}).get("link_data", {}).get("link")
            or creative.get("object_story_spec", {})
            .get("video_data", {})
            .get("call_to_action", {})
            .get("value", {})
            .get("link")
            or creative.get("asset_feed_spec", {})
            .get("link_urls", [{}])[0]
            .get("website_url")
        )
        return page_id, post_id, landing_url

    # ── breakdown / frequency 索引 ───────────────────────────────────────────

    def _build_breakdown_map(self, breakdown_rows: List[Mapping[str, Any]]) -> None:
        """从 bundle["breakdown_age_gender"] 构建 {ad_id: [{age, gender, metrics...}]} 索引。"""
        for row in breakdown_rows or []:
            ad_id = row.get("ad_id")
            if not ad_id:
                continue
            item = {
                "age": row.get("age"),
                "gender": row.get("gender"),
                "impressions": int(row.get("impressions", 0) or 0),
                "spend": round(float(row.get("spend", 0) or 0), 2),
            }
            metrics = self.process_action_metrics(
                row.get("actions", []),
                row.get("action_values", []),
                row.get("conversions", []),
            )
            item["complete_registration"] = int(metrics.get("register", 0) or 0)
            item["subscribe_website"] = int(metrics.get("subscriptions", 0) or 0)
            item["subscribe_website_values"] = round(
                float(metrics.get("subscriptions_value", 0) or 0), 2
            )
            item["purchases"] = int(metrics.get("purchases", 0) or 0)
            item["purchases_value"] = round(float(metrics.get("purchase_values", 0) or 0), 2)
            self.breakdown_map.setdefault(ad_id, []).append(item)
        logger.info(
            "[transform] breakdown_age_gender: %d 行 -> 覆盖 %d 个 ad",
            len(breakdown_rows or []),
            len(self.breakdown_map),
        )

    def _build_breakdown_json(self, ad: Mapping[str, Any]) -> Dict[str, str]:
        """从 breakdown_map 查表组 json。当天 0 曝光的 ad 落空返 [] (老 consumer 同语义)。"""
        ad_id = (ad or {}).get("id")
        return {
            "age_gender_breakdown_json": json.dumps(
                self.breakdown_map.get(ad_id, []), ensure_ascii=False
            )
        }

    def _index_frequency(self, bundle: Mapping[str, Any]) -> None:
        """把 frequency_{campaign,adset,ad}_{3,5,7}d 索引成 {level: {id: {f3d, f5d, f7d}}}。"""
        level_id_field = {
            LEVEL.campaign.value: "campaign_id",
            LEVEL.adset.value: "adset_id",
            LEVEL.ad.value: "ad_id",
        }
        for level, id_field in level_id_field.items():
            for days in (3, 5, 7):
                for row in bundle.get(f"frequency_{level}_{days}d", []) or []:
                    obj_id = row.get(id_field)
                    if obj_id:
                        self.freq_lookup[level][obj_id][f"frequency_{days}d"] = row.get("frequency")

    # ── 聚合 (ad → adset → campaign) ────────────────────────────────────────

    @staticmethod
    def _build_aggregated_insight(child_rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        """对齐老 consumer._build_aggregated_insight:
          - int 字段输出 "200" 而非 "200.0"(Doris INT strict 模式会拒)
          - spend / action_values 是金额,保浮点
          - cpm/ctr/cpc/frequency 重新由分子分母现算
          - actions / conversions count;action_values 是金额
        """
        if not child_rows:
            return {}

        int_sum_fields = [
            "impressions",
            "clicks",
            "unique_clicks",
            "reach",
            "inline_link_clicks",
            "unique_inline_link_clicks",
        ]
        float_sum_fields = ["spend"]

        result: Dict[str, Any] = {}
        for field in int_sum_fields:
            values = [float(r.get(field, 0) or 0) for r in child_rows]
            result[field] = str(int(round(sum(values))))
        for field in float_sum_fields:
            values = [float(r.get(field, 0) or 0) for r in child_rows]
            result[field] = str(sum(values))

        impressions = float(result["impressions"])
        clicks = float(result["clicks"])
        spend = float(result["spend"])
        reach = float(result["reach"])

        result["cpm"] = (
            str(round(spend / impressions * 1000, 6)) if impressions else "0"
        )
        result["ctr"] = (
            str(round(clicks / impressions * 100, 6)) if impressions else "0"
        )
        result["cpc"] = str(round(spend / clicks, 6)) if clicks else "0"
        result["frequency"] = str(round(impressions / reach, 6)) if reach else "0"

        ilc = float(result.get("inline_link_clicks", 0) or 0)
        uilc = float(result.get("unique_inline_link_clicks", 0) or 0)
        result["inline_link_click_ctr"] = (
            str(round(ilc / impressions * 100, 6)) if impressions else "0"
        )
        result["unique_inline_link_click_ctr"] = (
            str(round(uilc / impressions * 100, 6)) if impressions else "0"
        )

        count_style = {"actions", "conversions"}
        for list_field in ["actions", "action_values", "conversions"]:
            is_count = list_field in count_style
            merged: Dict[str, Dict[str, str]] = {}
            for row in child_rows:
                for item in row.get(list_field, []) or []:
                    at = item["action_type"]
                    if at not in merged:
                        merged[at] = {"action_type": at, "value": "0"}
                        for k in item:
                            if k not in ("action_type", "value"):
                                merged[at][k] = "0"
                    new_val = float(merged[at]["value"]) + float(item.get("value", 0) or 0)
                    merged[at]["value"] = (
                        str(int(round(new_val))) if is_count else str(new_val)
                    )
                    for k in item:
                        if k in ("action_type", "value"):
                            continue
                        new_k = float(merged[at].get(k, 0) or 0) + float(item.get(k, 0) or 0)
                        merged[at][k] = (
                            str(int(round(new_k))) if is_count else str(new_k)
                        )
            result[list_field] = list(merged.values()) if merged else []

        result["date_start"] = child_rows[0].get("date_start")
        result["date_stop"] = child_rows[0].get("date_stop")
        return result

    # ── 时间字段 / status 推导 ──────────────────────────────────────────────

    def get_create_time(self) -> Optional[datetime]:
        """读 self.level_obj 的 created_time 字段,FB 格式 → datetime(utc)。"""
        result = self.get_field(self.level_obj, "created_time")
        if not result:
            return None
        try:
            return datetime.strptime(result, "%Y-%m-%dT%H:%M:%S%z").replace(
                tzinfo=timezone.utc
            )
        except (ValueError, TypeError):
            return None

    # ── 0 成效合并(新增,老 consumer 没有) ────────────────────────────────

    def _attach_zero_spend_skeleton(
        self, ad_insights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """把 bundle.ads 里有、ad_insights 里没的 ad 补成"空指标"insight 行。

        构造的空行只填路由所需 id + 空 actions,数值字段全 None:这样下游能区分
        "FB 当天没返这条" (各 metric=NULL) 与 "FB 返了零值" (各 metric=0)。
        父级聚合不受影响:_build_aggregated_insight 里 r.get(field, 0) or 0 把
        None 当 0 求和。
        """
        existing_ad_ids = {row.get("ad_id") for row in ad_insights if row.get("ad_id")}

        # 已经在 fetch_day 之前删除的 ad,不应该出现在今天的快照里 (老 consumer 不补 0)
        day_str = self.fetch_day
        zero_rows: List[Dict[str, Any]] = []
        for ad in self.ad_by_id.values():
            ad_id = ad.get("id")
            if not ad_id or ad_id in existing_ad_ids:
                continue
            zero_rows.append({
                "ad_id": ad_id,
                "ad_name": ad.get("name"),
                "adset_id": ad.get("adset_id"),
                "campaign_id": ad.get("campaign_id"),
                "date_start": day_str,
                "date_stop": day_str,
                "actions": [],
                "action_values": [],
                "conversions": [],
                "video_play_actions": [],
                "video_p25_watched_actions": [],
                "video_p50_watched_actions": [],
                "video_p75_watched_actions": [],
                "video_p95_watched_actions": [],
                "video_p100_watched_actions": [],
            })
        if zero_rows:
            logger.info(
                "[transform] entity skeleton: 补空指标 ad %d 条 (bundle.ads=%d, ad_insights=%d)",
                len(zero_rows), len(self.ad_by_id), len(existing_ad_ids),
            )
        return list(ad_insights) + zero_rows

    # ── 主行构建 ────────────────────────────────────────────────────────────

    def _match_agent_line_by_url(self, objective, landing_url) -> tuple:
        key = (objective, landing_url)
        if key not in self._url_match_cache:
            self._url_match_cache[key] = match_agent_line_by_url(objective, landing_url)
        return self._url_match_cache[key]

    def _get_placer_and_department(self, agent_line) -> tuple:
        if agent_line not in self._placer_dept_cache:
            self._placer_dept_cache[agent_line] = get_placer_and_department(agent_line)
        return self._placer_dept_cache[agent_line]

    def process_insight_data(self, insight: Mapping[str, Any]) -> Dict[str, Any]:
        """单条 insight + 当前 walk 状态 → 单条 doris row(对齐老 consumer 字段顺序)。"""
        actions = insight.get("actions", []) or []
        conversions = insight.get("conversions", []) or []
        action_values = insight.get("action_values", []) or []
        impressions = insight.get("impressions")
        frequency = insight.get("frequency")
        frequency_3d = insight.get("frequency_3d")
        frequency_5d = insight.get("frequency_5d")
        frequency_7d = insight.get("frequency_7d")
        reach = insight.get("reach")
        _raw_spend = insight.get("spend")
        spend = round(float(_raw_spend), 2) if _raw_spend not in (None, "") else None
        metrics = self.process_action_metrics(actions, action_values, conversions)

        if self.level == LEVEL.account:
            # account_status 是 FB 数字状态码,delivery_str 列是 varchar,统一成字符串
            status = self.get_field(self.level_obj, "account_status", type_=str)
        else:
            status = self.get_field(self.level_obj, "effective_status")

        # 实体自身开关(configured status),account 层无此字段 → None
        own_status = self.get_field(self.level_obj, "status")

        create_time_obj = self.get_create_time()
        create_time_str = create_time_obj.strftime(SecondFormat) if create_time_obj else None

        page_id = None
        post_id = None
        landing_url = None
        is_original = None
        age_gender_breakdown_json = None
        video_metrics: Dict[str, int] = {}

        # ad 维度:每条 ad 走匹配 (落地页 / unique_name / breakdown)
        ad_agent_line = self.agent_line
        ad_placer_id = self.placer_id
        ad_department = self.department
        ad_game_platform = self.game_platform

        if self.level == LEVEL.ad:
            creative = self.get_field(self.ad, "creative") or {}
            page_id, post_id, landing_url = self._extract_creative_info(creative)
            age_gender_breakdown_json = insight.get("age_gender_breakdown_json")
            video_metrics = self._build_video_metrics(insight)
            if page_id and post_id:
                is_original = bool(landing_url)

            matched = self._match_agent_line_by_url(self.objective, landing_url)
            if matched[0]:
                ad_agent_line, ad_placer_id, ad_department, ad_game_platform = matched

        ad_name = self.get_field(self.ad, "name")
        unique_name = ad_name if is_valid_unique_name(ad_name) else None

        return {
            "level": self.level.value if self.level else None,
            "game_platform": ad_game_platform,
            "department": ad_department,
            "ad_platform": self.message["ad_platform"],
            "agent_line": ad_agent_line,
            "timezone_name": self.get_field(self.account, "timezone_name"),
            "account_name": self.get_field(self.account, "name"),
            "campaign_name": self.get_field(self.campaign, "name"),
            "ad_set_name": self.get_field(self.adset, "name"),
            "ad_name": ad_name,
            "unique_name": unique_name,
            # 精确半点(MinuteFormat);hourly/daily 表的粒度在 doris_writer 落库前才截
            "date": self.account_date.strftime(MinuteFormat),
            "china_date": change_date(self.account_date, "Asia/Shanghai").strftime(MinuteFormat),
            "ad_id": self.get_field(self.ad, "id"),
            "dev_id": self.message["dev_id"],
            "create_time": create_time_str,
            "account_id": self.get_field(self.account, "account_id"),
            "campaign_id": self.get_field(self.campaign, "id"),
            "ad_set_id": self.get_field(self.adset, "id"),
            "delivery": (
                1 if status == AD_EFFECTIVE_STATUS_ACTIVE else None if status is None else 0
            ),
            "frequency": frequency,
            "frequency_3d": frequency_3d,
            "frequency_5d": frequency_5d,
            "frequency_7d": frequency_7d,
            "reach": reach,
            "delivery_str": status,
            "status": own_status,
            # 学习期状态 / 像素只有 adset 层有,ad 行继承所属 adset 的值
            "learning_stage": (self.get_field(self.adset, "learning_stage_info") or {}).get("status"),
            "pixel_id": (self.get_field(self.adset, "promoted_object") or {}).get("pixel_id"),
            "account_status": self.get_field(self.account, "account_status", type_=int),
            "placer_id": ad_placer_id,
            "cam_budget": self.get_field(self.campaign, "daily_budget", type_=int),
            "adset_budget": self.get_field(self.adset, "daily_budget", type_=int),
            "budget": (
                self.get_field(self.campaign, "daily_budget", type_=int)
                if self.get_field(self.campaign, "daily_budget", 0, int) > 0
                else self.get_field(self.adset, "daily_budget", 0, type_=int)
            ),
            "amount_spent": spend,
            "impressions": impressions,
            "clicks_all": insight.get("clicks"),
            "clicks_unique": insight.get("unique_clicks"),
            "app_installs": metrics.get("app_installs"),
            "purchases": metrics["purchases"],
            "purchases_value": metrics["purchase_values"],
            "complete_registration": metrics["register"],
            "subscribe_website": metrics["subscriptions"],
            "subscribe_website_values": metrics["subscriptions_value"],
            "lead": metrics.get("lead"),
            "add_to_cart": metrics["add_to_cart"],
            "purchases_1dclick": metrics.get("purchases_1dclick"),
            "purchase_values_1dclick": metrics.get("purchase_values_1dclick"),
            "subscriptions_1dclick": metrics.get("subscriptions_1dclick"),
            "subscriptions_value_1dclick": metrics.get("subscriptions_value_1dclick"),
            "app_installs_1dclick": metrics.get("app_installs_1dclick"),
            "register_1dclick": metrics.get("register_1dclick"),
            "lead_1dclick": metrics.get("lead_1dclick"),
            "package_name": self.message.get("app_name"),
            "fetch_time": datetime.now(timezone.utc).strftime(SecondFormat),
            "cpm": insight.get("cpm"),
            "ctr": insight.get("ctr"),
            "cpc": insight.get("cpc"),
            "inline_link_clicks": insight.get("inline_link_clicks"),
            "inline_link_click_ctr": insight.get("inline_link_click_ctr"),
            "unique_inline_link_clicks": insight.get("unique_inline_link_clicks"),
            "unique_inline_link_click_ctr": insight.get("unique_inline_link_click_ctr"),
            "landing_page_view": metrics.get("landing_page_view"),
            "messaging_conversation_started": metrics.get("messaging_conversation_started"),
            "cost_per_messaging_conversation_started": (
                round(spend / float(metrics["messaging_conversation_started"]), 2)
                if spend is not None
                and metrics.get("messaging_conversation_started")
                and float(metrics["messaging_conversation_started"]) > 0
                else None
            ),
            "page_id": page_id,
            "post_id": post_id,
            "landing_url": landing_url,
            "age_gender_breakdown_json": age_gender_breakdown_json,
            "video_play_count": video_metrics.get("video_play_count"),
            "video_p25_count": video_metrics.get("video_p25_count"),
            "video_p50_count": video_metrics.get("video_p50_count"),
            "video_p75_count": video_metrics.get("video_p75_count"),
            "video_p95_count": video_metrics.get("video_p95_count"),
            "video_p100_count": video_metrics.get("video_p100_count"),
            "objective": self.objective,
            "is_original": is_original,
            "spend_cap": (
                self.get_field(self.account, "spend_cap")
                if self.level == LEVEL.account else None
            ),
            "balance": (
                spend_cap - self.get_field(self.account, "amount_spent", type_=int)
                if self.level == LEVEL.account
                and (spend_cap := self.get_field(self.account, "spend_cap", type_=int))
                else None
            ),
        }

    # ── 主流程:bundle → rows ────────────────────────────────────────────────

    def _assemble_all_levels(
        self, ad_insights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """走 ad→adset→campaign,有/无成效一起处理。
        - 有成效的实体取 insight 行的 spend/impressions 等指标
        - 没成效的实体走空聚合,指标为空但 budget / name / status 等元数据保留,
          以便后续 _convert_with_budget_accumulation 把 adset.daily_budget 累加
          到 campaign 和 account
        实体元数据从已索引的 self.*_by_id 查表;实体不在 *_by_id 里(被删/没拉到)
        但出现在 insight 行里的,用 fallback dict 占位。
        """
        insights_by_ad: Dict[str, Dict[str, Any]] = {
            row["ad_id"]: row for row in ad_insights if row.get("ad_id")
        }

        # 1) 先从 insight 收 (campaign, adset, ad) 三元组
        campaign_adsets: Dict[str, set] = defaultdict(set)
        adset_ads: Dict[str, set] = defaultdict(set)
        for row in ad_insights:
            cid, sid, aid = row.get("campaign_id"), row.get("adset_id"), row.get("ad_id")
            if cid and sid:
                campaign_adsets[cid].add(sid)
            if sid and aid:
                adset_ads[sid].add(aid)

        # 2) 再合并 entity 元数据里的"没成效但存在"的实体:
        #    - adset.campaign_id → campaign_adsets[cid] 加入 adset_id
        #    - ad.adset_id → adset_ads[sid] 加入 ad_id
        #    - 没匹配到 campaign 的 adset 也单独成 campaign 桶,保证 budget 不丢
        for sid, adset_obj in self.adset_by_id.items():
            cid = adset_obj.get("campaign_id")
            if cid:
                campaign_adsets[cid].add(sid)
        for aid, ad_obj in self.ad_by_id.items():
            sid = ad_obj.get("adset_id")
            if sid:
                adset_ads[sid].add(aid)
        # campaign 本身在 campaign_by_id 但 insight / adset 都没指到它 —— 也保留
        for cid in self.campaign_by_id:
            campaign_adsets.setdefault(cid, set())

        # plat_map 反查 line -> game_platform(平台按启用排前, 同名线取先出现的)
        reverse, line_index = build_line_maps(self.plat_map)
        results: List[Dict[str, Any]] = []

        # 稳定输出顺序:campaign / adset / ad 都按 id 字典序遍历
        for campaign_id in sorted(campaign_adsets):
            adset_ids = campaign_adsets[campaign_id]
            # 缺元数据 ≠ 已删除:pipeline 兜底没拉到(真删了或配额拒了)时留 None,
            # 不伪造 DELETED,避免把活着的系列误标已删除。
            campaign_obj = self.campaign_by_id.get(campaign_id) or {
                "id": campaign_id, "name": None,
                "status": None, "effective_status": None,
            }
            self.set_field(LEVEL.campaign, campaign_obj)
            campaign_name = campaign_obj.get("name", "")
            self.objective = campaign_obj.get("objective")
            self.agent_line = get_line_from_campaign_name(campaign_name or "", line_index)
            self.game_platform = reverse.get(self.agent_line)
            self.placer_id, self.department = (
                self._get_placer_and_department(self.agent_line)
                if self.agent_line
                else (self.message.get("placer_id"), None)
            )
            # 系列名没匹配出代理线时,用广告层 URL 匹配回填:仅当本系列下"能匹配到
            # 线"的广告全指向同一条线才回填,出现不同线则放弃;匹配不到的广告不参与。
            name_matched = bool(self.agent_line)
            ad_fallback_lines: Dict[str, tuple] = {}
            adset_result_refs: List[Dict[str, Any]] = []

            campaign_children: List[Dict[str, Any]] = []
            all_campaign_insights: List[Dict[str, Any]] = []

            for adset_id in sorted(adset_ids):
                adset_obj = self.adset_by_id.get(adset_id) or {
                    "id": adset_id, "name": None,
                    "status": None, "effective_status": None,
                }
                self.set_field(LEVEL.adset, adset_obj)

                adset_children: List[Dict[str, Any]] = []
                all_adset_insights: List[Dict[str, Any]] = []

                for ad_id in sorted(adset_ads[adset_id]):
                    ad_obj = self.ad_by_id.get(ad_id) or {
                        "id": ad_id, "name": None,
                        "status": None, "effective_status": None,
                        "creative": {},
                    }
                    self.set_field(LEVEL.ad, ad_obj)

                    # 没成效的 ad:用空 insight 兜底,指标全 None;
                    # 有成效的:用 insight 行,frequency_*d 从 lookup 注入
                    insight = dict(insights_by_ad.get(ad_id) or {})
                    freq = self.freq_lookup[LEVEL.ad.value].get(ad_id, {})
                    insight["frequency_3d"] = freq.get("frequency_3d")
                    insight["frequency_5d"] = freq.get("frequency_5d")
                    insight["frequency_7d"] = freq.get("frequency_7d")
                    insight.update(self._build_breakdown_json(ad_obj))

                    ad_result = self.process_insight_data(insight)
                    if ad_result:
                        adset_children.append(ad_result)
                        # 系列名没匹配时,收广告层 URL 匹配到的线(四件套)做回填候选
                        if not name_matched and ad_result.get("agent_line"):
                            ad_fallback_lines[ad_result["agent_line"]] = (
                                ad_result["agent_line"], ad_result["placer_id"],
                                ad_result["department"], ad_result["game_platform"],
                            )
                    # 只有"真有 insight"的 ad 才参与 adset 聚合,避免空行
                    # 把 spend / impressions 稀释掉
                    if ad_id in insights_by_ad:
                        all_adset_insights.append(insight)

                # adset 聚合行
                self.set_field(LEVEL.adset, adset_obj)
                adset_agg = self._build_aggregated_insight(all_adset_insights)
                freq = self.freq_lookup[LEVEL.adset.value].get(adset_id, {})
                adset_agg["frequency_3d"] = freq.get("frequency_3d")
                adset_agg["frequency_5d"] = freq.get("frequency_5d")
                adset_agg["frequency_7d"] = freq.get("frequency_7d")
                adset_result = self.process_insight_data(adset_agg)
                if adset_result:
                    campaign_children.append(adset_result)
                    adset_result_refs.append(adset_result)
                campaign_children.extend(adset_children)
                all_campaign_insights.extend(all_adset_insights)

            # 系列名没匹配且广告层唯一一条线 → 回填四件套到 self,系列聚合行随后
            # 产出即带上;组行已在循环中产出,需事后就地回填。
            ad_fallback = None
            if not name_matched and len(ad_fallback_lines) == 1:
                ad_fallback = next(iter(ad_fallback_lines.values()))
                (self.agent_line, self.placer_id,
                 self.department, self.game_platform) = ad_fallback
                logger.info(
                    "[transform] 系列名未匹配,按广告层 URL 回填 campaign=%s -> agent_line=%s",
                    campaign_id, ad_fallback[0],
                )
            elif not name_matched and len(ad_fallback_lines) > 1:
                logger.warning(
                    "[transform] 系列名未匹配,广告层出现多条线放弃回填 campaign=%s -> lines=%s",
                    campaign_id, sorted(ad_fallback_lines),
                )

            # campaign 聚合行
            self.set_field(LEVEL.campaign, campaign_obj)
            campaign_agg = self._build_aggregated_insight(all_campaign_insights)
            freq = self.freq_lookup[LEVEL.campaign.value].get(campaign_id, {})
            campaign_agg["frequency_3d"] = freq.get("frequency_3d")
            campaign_agg["frequency_5d"] = freq.get("frequency_5d")
            campaign_agg["frequency_7d"] = freq.get("frequency_7d")
            campaign_result = self.process_insight_data(campaign_agg)
            if campaign_result:
                results.append(campaign_result)

            # 组行在循环中已用旧 self.agent_line(None)产出,这里就地回填四件套
            if ad_fallback:
                for ar in adset_result_refs:
                    (ar["agent_line"], ar["placer_id"],
                     ar["department"], ar["game_platform"]) = ad_fallback

            results.extend(campaign_children)

        return results

    def _build_account_row(self) -> Optional[Dict[str, Any]]:
        """构造 account 级的 doris 行。bundle.account_insights 给 spend/impressions
        等指标,bundle.ad_account 给 spend_cap/amount_spent/timezone_name。
        """
        if not self.account:
            return None
        account_insights = self.bundle.get("account_insights") or []
        # account-level insights 单 row(或 0 row);用 sync get_insights 时它有
        # frequency_3/5/7d,这里我们用 account 级 frequency_*_d 没拉 → 都 None
        if account_insights:
            base_insight = dict(account_insights[0])
        else:
            base_insight = {
                "spend": None, "impressions": None, "clicks": None, "unique_clicks": None,
                "actions": [], "action_values": [], "conversions": [],
                "frequency": None, "reach": None, "cpm": None, "ctr": None,
                "cpc": None, "inline_link_clicks": None, "inline_link_click_ctr": None,
                "unique_inline_link_clicks": None, "unique_inline_link_click_ctr": None,
                "date_start": self.fetch_day, "date_stop": self.fetch_day,
            }
        base_insight["frequency_3d"] = None
        base_insight["frequency_5d"] = None
        base_insight["frequency_7d"] = None

        self.set_field(LEVEL.account, self.account)
        return self.process_insight_data(base_insight)

    @staticmethod
    def _convert_with_budget_accumulation(raw_data: List[Dict]) -> List[Dict]:
        """对齐老 convert_to_standard_format —— 顺序遍历 raw_data,把 adset.budget
        累加到 campaign.budget,再把 campaign.budget 累加到 account.budget。
        前提:raw_data 顺序是 [account, campaign1, adset1.1, ad..., adset1.2, ad...,
        campaign2, ...],跟 _assemble_all_levels 的输出顺序一致。
        """
        if not raw_data:
            return []

        current_account_index: Optional[int] = None
        current_campaign_index: Optional[int] = None
        accumulated_adset_budget = 0

        for i, result in enumerate(raw_data):
            level = result.get("level")

            if level == LEVEL.account.value:
                if current_campaign_index is not None:
                    raw_data[current_campaign_index]["budget"] = (
                        (raw_data[current_campaign_index].get("budget") or 0)
                        + accumulated_adset_budget
                    )
                    if current_account_index is not None:
                        raw_data[current_account_index]["budget"] = (
                            (raw_data[current_account_index].get("budget") or 0)
                            + (raw_data[current_campaign_index].get("budget") or 0)
                        )

                current_account_index = i
                current_campaign_index = None
                accumulated_adset_budget = 0

            elif level == LEVEL.campaign.value:
                if current_campaign_index is not None:
                    raw_data[current_campaign_index]["budget"] = (
                        (raw_data[current_campaign_index].get("budget") or 0)
                        + accumulated_adset_budget
                    )
                    if current_account_index is not None:
                        raw_data[current_account_index]["budget"] = (
                            (raw_data[current_account_index].get("budget") or 0)
                            + (raw_data[current_campaign_index].get("budget") or 0)
                        )

                current_campaign_index = i
                accumulated_adset_budget = 0

            elif level == LEVEL.adset.value:
                accumulated_adset_budget += result.get("adset_budget") or 0

        # 处理最后一个 campaign
        if current_campaign_index is not None:
            raw_data[current_campaign_index]["budget"] = (
                (raw_data[current_campaign_index].get("budget") or 0)
                + accumulated_adset_budget
            )
            if current_account_index is not None:
                raw_data[current_account_index]["budget"] = (
                    (raw_data[current_account_index].get("budget") or 0)
                    + (raw_data[current_campaign_index].get("budget") or 0)
                )

        return raw_data

    # ── 入口 ────────────────────────────────────────────────────────────────

    def to_rows(self) -> List[Dict[str, Any]]:
        """Bundle → doris row list 主入口:
          1. 索引 frequency_* 查表
          2. 索引 breakdown_age_gender 查表
          3. 0 成效 ad 合并(给 bundle.ad_insights 补 entity skeleton)
          4. account 行 + 各级行 (_assemble_all_levels)
          5. budget 累加 (_convert_with_budget_accumulation)
        """
        self._index_frequency(self.bundle)
        self._build_breakdown_map(self.bundle.get("breakdown_age_gender", []))

        ad_insights = self._attach_zero_spend_skeleton(
            list(self.bundle.get("ad_insights", []) or [])
        )

        rows: List[Dict[str, Any]] = []
        account_row = self._build_account_row()
        if account_row:
            rows.append(account_row)

        rows.extend(self._assemble_all_levels(ad_insights))
        return self._convert_with_budget_accumulation(rows)


def bundle_to_doris_rows(
    message: Mapping[str, Any], bundle: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    """便捷入口 —— 一行调用,把 pipeline.fetch_all 的输出转成 doris 行列表。"""
    return BundleTransform(message, bundle).to_rows()


__all__ = [
    "BundleTransform",
    "bundle_to_doris_rows",
]
