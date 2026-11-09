"""
Dashboard 维度明细查询 (重构版)
==============================
每个维度独立定义自己的 SQL 构建逻辑, 不再用 if/else 判断。
- 非小时数据 → ad_daily_detail
- 小时数据   → ad_hourly_detail
- 填充数据   → ad_hourly_summary (含 bi 字段)
"""

from __future__ import annotations

from abc import ABC
from datetime import datetime, timedelta
import re
from types import SimpleNamespace
from typing import List, Dict, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import auth_current_user
from app.db.async_mysql import AsyncMySQL
from app.db.clients import get_db, get_erp_db
from app.db.mongo import cols, user_cols
from app.model_type_defs.common_models import ApiResponse, DayFormat, ErrResponse
from app.model_type_defs.user_models import UserModel, Roles, DEPT_ALL
from .dashboard import (
    DashboardQueryParams,
    DimensionType,
    dimension_list,
    newest_dim,
    generate_dimension_subset,
    validate_and_build_order_clause,
    build_filter_conditions,
    parse_metric_filters,
    get_channel_account_mapping,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class PersonnelSpendQueryParams(BaseModel):
    """人员消耗面板的筛选及下钻参数。筛选维度支持逗号分隔的多选值。"""

    date: str = Field(..., description="日期范围，格式 YYYY-MM-DD,YYYY-MM-DD")
    department: str | None = None
    game_platform: str | None = None
    placer_id: str | None = None
    account_id: str | None = None
    account_attribute: str | None = None  # ERP whitelist_type，多选逗号分隔
    level: Literal["personnel", "account", "project", "campaign"] = "personnel"


def _split_filter_values(value: str | None) -> list[str]:
    """拆分前端多选下拉传入的逗号分隔值。"""
    return [item.strip() for item in (value or "").split(",") if item.strip()]


async def _personnel_spend_permission_where(
    current_user: UserModel,
) -> tuple[str, list[str]]:
    """构建与维度明细接口一致的部门/个人账户数据权限条件（不含 AND）。"""
    departments = current_user.departments or []
    if DEPT_ALL in departments:
        return "", []
    if departments:
        placeholders = ", ".join(["%s"] * len(departments))
        return f"department IN ({placeholders})", list(departments)

    personal_accounts = await cols.personal_accounts.find(
        {"user_name": current_user.real_name, "status": True}, {"accounts.id": 1}
    ).to_list(length=None)
    account_ids = [
        str(account["id"]).removeprefix("act_")
        for doc in personal_accounts
        for account in doc.get("accounts", [])
        if account.get("id")
    ]
    if account_ids:
        placeholders = ", ".join(["%s"] * len(account_ids))
        return (
            f"(placer_id = %s OR account_id IN ({placeholders}))",
            [current_user.real_name, *account_ids],
        )
    return "placer_id = %s", [current_user.real_name]


# ═══════════════════════════════════════════════════════════════════════════
# 公共指标列定义
# ═══════════════════════════════════════════════════════════════════════════

def _agg_columns() -> dict:
    """聚合模式下的公共指标列 (用于 newest / filled 的 GROUP BY 查询)"""
    return {
        "花费金额": "ROUND(SUM(amount_spent),2)",
        "覆盖人数": "SUM(reach)",
        "展示次数": "SUM(impressions)",
        "点击数": "SUM(clicks_all)",
        "点击率": "CONCAT(CAST(SUM(clicks_all)*100.0/SUM(impressions) AS DECIMAL(10,2)),'%%')",
        "点击成本": "ROUND(SUM(amount_spent)/SUM(clicks_all),2)",
        "链接点击数": "SUM(inline_link_clicks)",
        "落地页浏览": "SUM(landing_page_view)",
        "落地页成本": "ROUND(SUM(amount_spent)/SUM(landing_page_view),2)",
        "安装数": "SUM(app_installs)",
        "注册数": "SUM(complete_registration)",
        "注册转化率": "CONCAT(CAST(SUM(complete_registration)/SUM(clicks_all)*100 AS DECIMAL(10,2)),'%%')",
        "注册成本": "ROUND(SUM(amount_spent)/SUM(complete_registration),2)",
        "订阅数": "SUM(subscribe_website)",
        "订阅率": "CONCAT(CAST(SUM(subscribe_website)/SUM(complete_registration)*100 AS DECIMAL(10,2)),'%%')",
        "订阅成本": "ROUND(SUM(amount_spent)/SUM(subscribe_website),2)",
        "订阅价值": "ROUND(SUM(subscribe_website_values),2)",
        "购物数": "SUM(purchases)",
        "购物率": "CONCAT(CAST(SUM(purchases)/SUM(complete_registration)*100 AS DECIMAL(10,2)),'%%')",
        "购物成本": "ROUND(SUM(amount_spent)/SUM(purchases),2)",
        "购物价值": "ROUND(SUM(purchases_value),2)",
        "购物roas": "ROUND(SUM(purchases_value)/SUM(amount_spent),2)",
    }


def _agg_dedup_columns() -> dict:
    """不在 newest_dim 中的维度额外拥有的去重点击列"""
    return {
        "去重链接点击数": "SUM(unique_inline_link_clicks)",
        "去重点击成本": "ROUND(SUM(amount_spent)/SUM(unique_inline_link_clicks),2)",
    }


def _agg_1d_columns() -> dict:
    """show_1d 时插入的 1d 指标列"""
    return {
        "1d安装数": "SUM(app_installs_1dclick)",
        "1d注册数": "SUM(register_1dclick)",
        "1d注册成本": "ROUND(SUM(amount_spent)/SUM(register_1dclick),2)",
        "1d订阅数": "SUM(subscriptions_1dclick)",
        "1d订阅成本": "ROUND(SUM(amount_spent)/SUM(subscriptions_1dclick),2)",
        "1d订阅价值": "ROUND(SUM(subscriptions_value_1dclick),2)",
        "1d购物数": "SUM(purchases_1dclick)",
        "1d购物成本": "ROUND(SUM(amount_spent)/SUM(purchases_1dclick),2)",
        "1d购物价值": "ROUND(SUM(purchase_values_1dclick),2)",
        "1d购物roas": "ROUND(SUM(purchase_values_1dclick)/SUM(amount_spent),2)",
    }


def _hourly_columns() -> dict:
    """小时明细模式下的公共指标列 (单行, 无聚合)"""
    return {
        "花费金额": "ROUND(amount_spent,2)",
        "覆盖人数": "reach",
        "展示次数": "impressions",
        "点击数": "clicks_all",
        "点击率": "CONCAT(CAST(clicks_all*100.0/NULLIF(impressions,0) AS DECIMAL(10,2)),'%%')",
        "点击成本": "ROUND(amount_spent/clicks_all,2)",
        "链接点击数": "inline_link_clicks",
        "落地页浏览": "landing_page_view",
        "落地页成本": "ROUND(amount_spent/landing_page_view,2)",
        "安装数": "app_installs",
        "注册数": "complete_registration",
        "注册转化率": "CONCAT(CAST(complete_registration/clicks_all*100 AS DECIMAL(10,2)),'%%')",
        "注册成本": "ROUND(amount_spent/complete_registration,2)",
        "订阅数": "subscribe_website",
        "订阅率": "CONCAT(CAST(subscribe_website/complete_registration*100 AS DECIMAL(10,2)),'%%')",
        "订阅成本": "ROUND(amount_spent/subscribe_website,2)",
        "订阅价值": "subscribe_website_values",
        "购物数": "purchases",
        "购物率": "CONCAT(CAST(purchases/complete_registration*100 AS DECIMAL(10,2)),'%%')",
        "购物成本": "ROUND(amount_spent/purchases,2)",
        "购物价值": "purchases_value",
        "购物roas": "ROUND(purchases_value/amount_spent,2)",
    }


def _hourly_dedup_columns() -> dict:
    return {
        "去重链接点击数": "unique_inline_link_clicks",
        "去重点击成本": "ROUND(amount_spent/unique_inline_link_clicks,2)",
    }


def _hourly_1d_columns() -> dict:
    return {
        "1d安装数": "app_installs_1dclick",
        "1d注册数": "register_1dclick",
        "1d注册成本": "ROUND(amount_spent/register_1dclick,2)",
        "1d订阅数": "subscriptions_1dclick",
        "1d订阅成本": "ROUND(amount_spent/subscriptions_1dclick,2)",
        "1d订阅价值": "subscriptions_value_1dclick",
        "1d购物数": "purchases_1dclick",
        "1d购物成本": "ROUND(amount_spent/purchases_1dclick,2)",
        "1d购物价值": "purchase_values_1dclick",
        "1d购物roas": "ROUND(purchase_values_1dclick/amount_spent,2)",
    }


# 在跑 = 投放中; PAUSED 及其余状态、停用账户均视为已关停
_RUNNING_COND = "delivery_str IN ('ACTIVE','IN_PROCESS') AND account_status IN (1,8,9)"


def _spend_split_columns() -> dict:
    """按每天快照的状态把消耗拆成已关停/在跑两列"""
    return {
        "已关停消耗": f"ROUND(SUM(CASE WHEN {_RUNNING_COND} THEN 0 ELSE amount_spent END),2)",
        "在跑消耗": f"ROUND(SUM(CASE WHEN {_RUNNING_COND} THEN amount_spent ELSE 0 END),2)",
    }


def _insert_after(d: dict, target_key: str, new_items: dict) -> dict:
    """在字典指定 key 后插入新的键值对"""
    result = {}
    for k, v in d.items():
        result[k] = v
        if k == target_key:
            result.update(new_items)
    return result


def _insert_1d(columns: dict, show_1d: bool, agg: bool) -> dict:
    """按位置插入 1d 指标列"""
    if not show_1d:
        return columns
    items = _agg_1d_columns() if agg else _hourly_1d_columns()
    columns = _insert_after(columns, "安装数", {"1d安装数": items["1d安装数"]})
    columns = _insert_after(columns, "注册数", {"1d注册数": items["1d注册数"]})
    columns = _insert_after(columns, "注册成本", {"1d注册成本": items["1d注册成本"]})
    columns = _insert_after(columns, "订阅数", {"1d订阅数": items["1d订阅数"]})
    columns = _insert_after(columns, "订阅成本", {"1d订阅成本": items["1d订阅成本"]})
    columns = _insert_after(columns, "订阅价值", {"1d订阅价值": items["1d订阅价值"]})
    columns = _insert_after(columns, "购物数", {"1d购物数": items["1d购物数"]})
    columns = _insert_after(columns, "购物成本", {"1d购物成本": items["1d购物成本"]})
    columns = _insert_after(columns, "购物价值", {"1d购物价值": items["1d购物价值"]})
    columns = _insert_after(columns, "购物roas", {"1d购物roas": items["1d购物roas"]})
    return columns


# ═══════════════════════════════════════════════════════════════════════════
# 基类: 定义每个维度 builder 的接口
# ═══════════════════════════════════════════════════════════════════════════

class DimensionQueryBuilder(ABC):
    """维度查询构建器基类"""

    # 子类必须定义
    dimension: str           # e.g. "department"
    name_field: str          # e.g. "department"
    level: str               # e.g. "campaign"

    # 非 campaign/adset/ad 维度自动从 ad 级别聚合
    _OWN_LEVEL_DIMS = {"campaign_id", "ad_set_id", "ad_id", "account_id"}
    should_enrich_running_budget = True

    @property
    def from_ad_level(self) -> bool:
        return self.dimension not in self._OWN_LEVEL_DIMS

    def id_expr(self) -> str:
        return self.dimension

    def build_daily_sql(self, ctx: "DetailQueryHandler") -> tuple[str, dict]:
        """非小时数据: 查 ad_daily_detail, 每天已存最新一条, 直接聚合"""
        columns = self._build_daily_columns(ctx)
        name_filter = ctx.search_filter(self.name_field, self.id_expr())
        select_fields = [f"{expr} AS {col}" for col, expr in columns.items()]
        query_level = 'ad' if self.from_ad_level else self.level

        where_clause = f"level = '{query_level}' AND {ctx.effective_date_sql} {ctx.where_sql} {name_filter}"
        extra_window = self._daily_window_columns()
        extra_rn = self._extra_rn_columns()

        if extra_window or extra_rn:
            sql = f"""WITH daily_data AS (
    SELECT
        {extra_window}{extra_rn}*
    FROM ad_daily_detail
    WHERE {where_clause}
)
SELECT {', '.join(select_fields)}
FROM daily_data t
GROUP BY {self.dimension}, {self.name_field}
{ctx.filter_clause()}
{ctx.order_clause()}
LIMIT {ctx.page_size} OFFSET {ctx.offset};"""
        else:
            sql = f"""SELECT {', '.join(select_fields)}
FROM ad_daily_detail t
WHERE {where_clause}
GROUP BY {self.dimension}, {self.name_field}
{ctx.filter_clause()}
{ctx.order_clause()}
LIMIT {ctx.page_size} OFFSET {ctx.offset};"""
        return sql, columns

    def build_hourly_sql(self, ctx: "DetailQueryHandler") -> tuple[str, dict]:
        """小时 + 最新数据: 查 ad_hourly_detail, 直接单行明细"""
        columns = self._build_hourly_columns(ctx)
        name_filter = ctx.search_filter(self.name_field, self.id_expr())
        select_fields = [f"{expr} AS {col}" for col, expr in columns.items()]

        sql = f"""SELECT {', '.join(select_fields)}
FROM ad_hourly_detail
WHERE level = '{self.level}'
  AND {ctx.date_sql} {ctx.where_sql} {name_filter}
  {ctx.filter_clause(is_hourly=True, where_mode=True)}
{ctx.order_clause(is_hourly=True)}
LIMIT {ctx.page_size} OFFSET {ctx.offset};"""
        return sql, columns

    def build_count_sql(self, ctx: "DetailQueryHandler") -> str:
        """总记录数"""
        name_filter = ctx.search_filter(self.name_field, self.id_expr())
        query_level = 'ad' if self.from_ad_level else self.level
        return f"""SELECT COUNT(DISTINCT {self.dimension}) AS total
FROM (
    SELECT DISTINCT {self.dimension}
    FROM {ctx.table}
    WHERE level = '{query_level}' AND {ctx.effective_date_sql} {ctx.where_sql} {name_filter}
) t"""

    def build_filled_sql(self, ctx: "DetailQueryHandler", subset: set) -> tuple[str, dict]:
        """填充数据: 查 ad_hourly_summary"""
        columns = self._build_filled_columns(ctx)
        name_filter = ctx.search_filter(self.name_field, self.id_expr())
        select_fields = [f"{expr} AS {col}" for col, expr in columns.items()]

        sql = f"""WITH latest_date AS (
    SELECT {self.dimension}, MAX(date) AS max_date
    FROM ad_hourly_summary
    WHERE {ctx.date_sql} {ctx.where_sql} {name_filter}
    GROUP BY {self.dimension}
)
SELECT {', '.join(select_fields)}
FROM ad_hourly_summary t
JOIN latest_date ld ON t.{self.dimension} = ld.{self.dimension} AND t.date = ld.max_date
GROUP BY t.{self.dimension}, ld.max_date
{ctx.filter_clause()}
{ctx.order_clause()}
LIMIT {ctx.page_size} OFFSET {ctx.offset};"""
        return sql, columns

    def build_filled_count_sql(self, ctx: "DetailQueryHandler") -> str:
        name_filter = ctx.search_filter(self.name_field, self.id_expr())
        return f"""SELECT COUNT(DISTINCT {self.dimension}) AS total
FROM ad_hourly_summary
WHERE {ctx.date_sql} {ctx.where_sql} {name_filter}"""

    # ── 列构建 (子类可覆盖) ─────────────────────────────────────────

    def _build_daily_columns(self, ctx: "DetailQueryHandler") -> dict:
        cols = {"id": self.id_expr(), "name": self.name_field}
        cols.update(_agg_columns())
        cols = _insert_after(cols, "花费金额", {
            "最新时间": "DATE_FORMAT(MAX(fetch_time) + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            **_spend_split_columns(),
        })
        cols = _insert_1d(cols, ctx.show_1d, agg=True)
        cols["对话数"] = "SUM(messaging_conversation_started)"
        cols["对话成本"] = "ROUND(SUM(amount_spent)/SUM(messaging_conversation_started),2)"
        return cols

    def _build_hourly_columns(self, ctx: "DetailQueryHandler") -> dict:
        cols = {"id": self.id_expr(), "name": self.name_field}
        cols.update(_hourly_columns())
        cols = _insert_after(cols, "花费金额", {
            "最新时间": "DATE_FORMAT(fetch_time + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "时间": "DATE_FORMAT(date, '%%m-%%d %%H:%%i')",
        })
        cols = _insert_1d(cols, ctx.show_1d, agg=False)
        cols["对话数"] = "messaging_conversation_started"
        cols["对话成本"] = "ROUND(amount_spent/messaging_conversation_started,2)"
        return cols

    def _build_filled_columns(self, ctx: "DetailQueryHandler") -> dict:
        cols = {"id": f"t.{self.id_expr()}", "name": f"t.{self.name_field}"}
        base = _agg_columns()
        cols["花费金额"] = base["花费金额"]
        cols["时间"] = "DATE_FORMAT(ld.max_date, '%%Y-%%m-%%d %%H时')"
        cols.update({
            "bi注册数": "SUM(bi_registrations)",
            "bi首充人数": "SUM(bi_first_recharge_users)",
            "bi首充金额": "SUM(bi_first_recharge_amount)",
            "bi首充成本": "ROUND(SUM(amount_spent)/SUM(bi_first_recharge_users),2)",
            "bi首次roas": "ROUND(SUM(bi_first_recharge_amount)/16000/SUM(amount_spent),2)",
            "bi首次arppu": "ROUND(SUM(bi_first_recharge_amount)/16000/SUM(bi_first_recharge_users),2)",
            "bi注册成本": "ROUND(SUM(amount_spent)/SUM(bi_registrations),2)",
        })
        # 剩余指标
        for k, v in base.items():
            if k != "花费金额":
                cols[k] = v
        cols = _insert_1d(cols, ctx.show_1d, agg=True)
        return cols

    # ── 窗口函数钩子 (子类可覆盖) ──────────────────────────────────

    def _daily_window_columns(self) -> str:
        """CTE 中的额外窗口列 (如 FIRST_VALUE)"""
        return ""

    def _extra_rn_columns(self) -> str:
        """额外的 ROW_NUMBER 列 (子类可覆盖)"""
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# 各维度实现
# ═══════════════════════════════════════════════════════════════════════════

class DepartmentBuilder(DimensionQueryBuilder):
    dimension = "department"
    name_field = "department"
    level = "campaign"

    def build_hourly_sql(self, ctx):
        # 高层维度不走单行明细, 仍走聚合 (ad_hourly_detail + CTE)
        return self._build_hourly_agg_sql(ctx)

    def _build_hourly_agg_sql(self, ctx):
        """小时模式：from_ad_level 维度按维度+小时直接聚合，不做 ROW_NUMBER 去重"""
        columns = self._build_hourly_agg_columns(ctx)
        columns = _insert_after(columns, "花费金额", {
            "时间": "DATE_FORMAT(date, '%%m-%%d %%H:%%i')",
        })
        name_filter = ctx.search_filter(self.name_field, self.id_expr())
        select_fields = [f"{expr} AS {col}" for col, expr in columns.items()]

        sql = f"""SELECT {', '.join(select_fields)}
FROM ad_hourly_detail t
WHERE level = 'ad'
  AND {ctx.date_sql} {ctx.where_sql} {name_filter}
GROUP BY {self.dimension}, {self.name_field}, date
{ctx.filter_clause()}
{ctx.order_clause()}
LIMIT {ctx.page_size} OFFSET {ctx.offset};"""
        return sql, columns

    def _build_hourly_agg_columns(self, ctx) -> dict:
        """hourly 聚合模式列 (在跑预算在 Python 层补充)"""
        cols = {"id": self.id_expr(), "name": self.name_field}
        cols.update(_agg_columns())
        cols = _insert_after(cols, "花费金额", {
            "最新时间": "DATE_FORMAT(MAX(fetch_time) + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            **_spend_split_columns(),
        })
        cols = _insert_1d(cols, ctx.show_1d, agg=True)
        cols["对话数"] = "SUM(messaging_conversation_started)"
        cols["对话成本"] = "ROUND(SUM(amount_spent)/SUM(messaging_conversation_started),2)"
        return cols


class GamePlatformBuilder(DepartmentBuilder):
    """与部门维度结构完全相同, 仅替换 dimension/name_field"""
    dimension = "game_platform"
    name_field = "game_platform"


class AdPlatformBuilder(DimensionQueryBuilder):
    dimension = "ad_platform"
    name_field = "ad_platform"
    level = "campaign"


class AgentLineBuilder(DepartmentBuilder):
    """与部门维度结构相同, 但 filled SQL 有特殊的 subset 列展示"""
    dimension = "agent_line"
    name_field = "agent_line"

    def build_filled_sql(self, ctx, subset):
        cols = {"id": "agent_line", "name": "agent_line"}
        cols["花费金额"] = "ROUND(SUM(amount_spent),2)"
        cols["时间"] = "DATE_FORMAT(date, '%%Y-%%m-%%d %%H时')"
        # subset 中的维度作为额外展示列
        subset_name_map = {
            "department": "部门",
            "game_platform": "游戏平台",
            "ad_platform": "广告平台",
        }
        subset_cols = {subset_name_map[k]: k for k in subset if k in subset_name_map}
        cols.update(subset_cols)
        cols.update({
            "bi注册数": "SUM(bi_registrations)",
            "bi首充人数": "SUM(bi_first_recharge_users)",
            "bi首充金额": "SUM(bi_first_recharge_amount)",
            "bi首充成本": "ROUND(SUM(amount_spent)/SUM(bi_first_recharge_users),2)",
            "bi首次roas": "ROUND(SUM(bi_first_recharge_amount)/16000/SUM(amount_spent),2)",
            "bi首次arppu": "ROUND(SUM(bi_first_recharge_amount)/16000/SUM(bi_first_recharge_users),2)",
            "bi注册成本": "ROUND(SUM(amount_spent)/SUM(bi_registrations),2)",
        })
        for k, v in _agg_columns().items():
            if k != "花费金额":
                cols[k] = v
        cols = _insert_1d(cols, ctx.show_1d, agg=True)

        select_fields = [f"{expr} AS {col}" for col, expr in cols.items()]
        subset_group = (", " + ", ".join(subset)) if subset else ""
        extra_order = ctx.order_clause().replace("ORDER BY ", "") if ctx.sort_by else f"{self.dimension} ASC"

        sql = f"""WITH ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY agent_line ORDER BY date DESC) AS rn
    FROM ad_hourly_summary
    WHERE {ctx.date_sql} {ctx.where_sql} {ctx.search_filter(self.name_field, self.id_expr())}
)
SELECT {', '.join(select_fields)}
FROM ranked
WHERE rn = 1
GROUP BY date, {self.dimension}, {self.name_field}{subset_group}
ORDER BY date DESC, {extra_order}
LIMIT {ctx.page_size} OFFSET {ctx.offset};"""
        return sql, cols


class PlacerIdBuilder(DimensionQueryBuilder):
    dimension = "placer_id"
    name_field = "placer_id"
    level = "campaign"

    def build_hourly_sql(self, ctx):
        # 高层维度走聚合, 复用 DepartmentBuilder 的逻辑
        return DepartmentBuilder._build_hourly_agg_sql(self, ctx)


class AccountIdBuilder(DimensionQueryBuilder):
    dimension = "account_id"
    name_field = "account_name"
    level = "account"

    def id_expr(self):
        return "account_id"

    def _daily_window_columns(self):
        return (
            "FIRST_VALUE(delivery_str) OVER (PARTITION BY account_id ORDER BY date DESC) AS latest_delivery_str,\n        "
            "FIRST_VALUE(account_status) OVER (PARTITION BY account_id ORDER BY date DESC) AS latest_account_status,\n        "
        )

    def _build_daily_columns(self, ctx):
        cols = {"id": self.id_expr(), "name": self.name_field}
        cols.update(_agg_columns())
        cols = _insert_after(cols, "花费金额", {
            "最新时间": "DATE_FORMAT(MAX(fetch_time) + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "status": "ANY_VALUE(status)",
            "effective_status": "ANY_VALUE(latest_delivery_str)",
            "account_status": "ANY_VALUE(latest_account_status)",
            "户余额": "CAST(ANY_VALUE(balance) / 100 AS INT)",
            "户限额": "CAST(ANY_VALUE(spend_cap) / 100 AS INT)",
            "单日限额": "ANY_VALUE(account_dsl)",
        })
        cols = _insert_1d(cols, ctx.show_1d, agg=True)
        cols["对话数"] = "SUM(messaging_conversation_started)"
        cols["对话成本"] = "ROUND(SUM(amount_spent)/SUM(messaging_conversation_started),2)"
        return cols

    def _build_hourly_columns(self, ctx):
        cols = {"id": self.id_expr(), "name": self.name_field}
        cols.update(_hourly_columns())
        # status 紧跟花费金额: 花费金额/在跑预算/最新时间/status 都 pin 左侧, 固定列必须连续否则前端错位
        cols = _insert_after(cols, "花费金额", {
            "最新时间": "DATE_FORMAT(fetch_time + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "status": "status",
            "effective_status": "delivery_str",
            "account_status": "account_status",
            "时间": "DATE_FORMAT(date, '%%m-%%d %%H:%%i')",
            "户余额": "CAST(balance / 100 AS INT)",
            "户限额": "CAST(spend_cap / 100 AS INT)",
            "单日限额": "account_dsl",
        })
        cols = _insert_1d(cols, ctx.show_1d, agg=False)
        cols["对话数"] = "messaging_conversation_started"
        cols["对话成本"] = "ROUND(amount_spent/messaging_conversation_started,2)"
        return cols


class CampaignIdBuilder(DimensionQueryBuilder):
    dimension = "campaign_id"
    name_field = "campaign_name"
    level = "campaign"

    def _daily_window_columns(self):
        return (
            "FIRST_VALUE(budget) OVER (PARTITION BY campaign_id ORDER BY date DESC) AS latest_budget,\n        "
            "FIRST_VALUE(delivery_str) OVER (PARTITION BY campaign_id ORDER BY date DESC) AS latest_delivery_str,\n        "
            "FIRST_VALUE(account_status) OVER (PARTITION BY campaign_id ORDER BY date DESC) AS latest_account_status,\n        "
        )

    def _build_daily_columns(self, ctx):
        cols = {"id": self.dimension, "name": self.name_field}
        cols.update(_agg_columns())
        # 去重点击
        cols = _insert_after(cols, "链接点击数", _agg_dedup_columns())
        # 千展
        cols = _insert_after(cols, "展示次数", {
            "千展": "ROUND(SUM(amount_spent)/SUM(impressions)*1000,2)",
        })
        cols = _insert_after(cols, "花费金额", {
            "最新时间": "DATE_FORMAT(MAX(fetch_time) + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "创建时间": "DATE_FORMAT(ANY_VALUE(create_time) + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "status": "ANY_VALUE(status)",
            "effective_status": "ANY_VALUE(latest_delivery_str)",
            "account_status": "ANY_VALUE(latest_account_status)",
            "预算": "ANY_VALUE(latest_budget)/100",
        })
        # 频次
        cols["频次"] = "ROUND(AVG(frequency),2)"
        cols["3d频次"] = "ROUND(AVG(frequency_3d),2)"
        cols["5d频次"] = "ROUND(AVG(frequency_5d),2)"
        cols["7d频次"] = "ROUND(AVG(frequency_7d),2)"
        cols = _insert_1d(cols, ctx.show_1d, agg=True)
        cols["对话数"] = "SUM(messaging_conversation_started)"
        cols["对话成本"] = "ROUND(SUM(amount_spent)/SUM(messaging_conversation_started),2)"
        cols["账户名"] = "ANY_VALUE(account_name)"
        cols["账户ID"] = "ANY_VALUE(account_id)"
        return cols

    def _build_hourly_columns(self, ctx):
        cols = {"id": self.dimension, "name": self.name_field}
        cols.update(_hourly_columns())
        cols = _insert_after(cols, "链接点击数", _hourly_dedup_columns())
        cols = _insert_after(cols, "展示次数", {"千展": "ROUND(cpm,2)"})
        cols = _insert_after(cols, "花费金额", {
            "时间": "DATE_FORMAT(date, '%%m-%%d %%H:%%i')",
            "最新时间": "DATE_FORMAT(fetch_time + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "创建时间": "DATE_FORMAT(create_time + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "status": "status",
            "effective_status": "delivery_str",
            "account_status": "account_status",
            "预算": "budget/100",
        })
        cols["频次"] = "ROUND(frequency,2)"
        cols["3d频次"] = "ROUND(frequency_3d,2)"
        cols["5d频次"] = "ROUND(frequency_5d,2)"
        cols["7d频次"] = "ROUND(frequency_7d,2)"
        cols = _insert_1d(cols, ctx.show_1d, agg=False)
        cols["对话数"] = "messaging_conversation_started"
        cols["对话成本"] = "ROUND(amount_spent/messaging_conversation_started,2)"
        cols["账户ID"] = "account_id"
        cols["账户名称"] = "account_name"
        return cols


class AdSetIdBuilder(DimensionQueryBuilder):
    dimension = "ad_set_id"
    name_field = "ad_set_name"
    level = "adset"

    def _daily_window_columns(self):
        return (
            "FIRST_VALUE(budget) OVER (PARTITION BY ad_set_id ORDER BY date DESC) AS latest_budget,\n        "
            "FIRST_VALUE(delivery_str) OVER (PARTITION BY ad_set_id ORDER BY date DESC) AS latest_delivery_str,\n        "
            "FIRST_VALUE(learning_stage) OVER (PARTITION BY ad_set_id ORDER BY date DESC) AS latest_learning_stage,\n        "
            "FIRST_VALUE(account_status) OVER (PARTITION BY ad_set_id ORDER BY date DESC) AS latest_account_status,\n        "
        )

    def _build_daily_columns(self, ctx):
        cols = {"id": self.dimension, "name": self.name_field}
        cols.update(_agg_columns())
        cols = _insert_after(cols, "链接点击数", _agg_dedup_columns())
        cols = _insert_after(cols, "展示次数", {
            "千展": "ROUND(SUM(amount_spent)/SUM(impressions)*1000,2)",
        })
        cols = _insert_after(cols, "花费金额", {
            "最新时间": "DATE_FORMAT(MAX(fetch_time) + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "创建时间": "DATE_FORMAT(ANY_VALUE(create_time) + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "status": "ANY_VALUE(status)",
            "effective_status": "ANY_VALUE(latest_delivery_str)",
            "learning_stage": "ANY_VALUE(latest_learning_stage)",
            "account_status": "ANY_VALUE(latest_account_status)",
            "预算": "ANY_VALUE(latest_budget)/100",
        })
        cols["频次"] = "ROUND(AVG(frequency),2)"
        cols["3d频次"] = "ROUND(AVG(frequency_3d),2)"
        cols["5d频次"] = "ROUND(AVG(frequency_5d),2)"
        cols["7d频次"] = "ROUND(AVG(frequency_7d),2)"
        cols = _insert_1d(cols, ctx.show_1d, agg=True)
        cols["对话数"] = "SUM(messaging_conversation_started)"
        cols["对话成本"] = "ROUND(SUM(amount_spent)/SUM(messaging_conversation_started),2)"
        return cols

    def _build_hourly_columns(self, ctx):
        cols = {"id": self.dimension, "name": self.name_field}
        cols.update(_hourly_columns())
        cols = _insert_after(cols, "链接点击数", _hourly_dedup_columns())
        cols = _insert_after(cols, "展示次数", {"千展": "ROUND(cpm,2)"})
        cols = _insert_after(cols, "花费金额", {
            "时间": "DATE_FORMAT(date, '%%m-%%d %%H:%%i')",
            "最新时间": "DATE_FORMAT(fetch_time + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "创建时间": "DATE_FORMAT(create_time + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "status": "status",
            "effective_status": "delivery_str",
            "learning_stage": "learning_stage",
            "account_status": "account_status",
            "预算": "budget/100",
        })
        cols["频次"] = "ROUND(frequency,2)"
        cols["3d频次"] = "ROUND(frequency_3d,2)"
        cols["5d频次"] = "ROUND(frequency_5d,2)"
        cols["7d频次"] = "ROUND(frequency_7d,2)"
        cols = _insert_1d(cols, ctx.show_1d, agg=False)
        cols["对话数"] = "messaging_conversation_started"
        cols["对话成本"] = "ROUND(amount_spent/messaging_conversation_started,2)"
        return cols


class AdIdBuilder(DimensionQueryBuilder):
    dimension = "ad_id"
    name_field = "ad_name"
    level = "ad"

    def _daily_window_columns(self):
        return (
            "FIRST_VALUE(unique_name) OVER (PARTITION BY ad_id ORDER BY (unique_name IS NULL), date DESC) AS first_unique_name,\n        "
            "COUNT(DISTINCT ad_id) OVER (PARTITION BY post_id) AS post_ad_count,\n        "
            "FIRST_VALUE(account_id) OVER (PARTITION BY ad_id ORDER BY date DESC) AS latest_account_id,\n        "
            "FIRST_VALUE(account_name) OVER (PARTITION BY ad_id ORDER BY date DESC) AS latest_account_name,\n        "
            "FIRST_VALUE(department) OVER (PARTITION BY ad_id ORDER BY date DESC) AS latest_department,\n        "
            "FIRST_VALUE(game_platform) OVER (PARTITION BY ad_id ORDER BY date DESC) AS latest_game_platform,\n        "
            "FIRST_VALUE(delivery_str) OVER (PARTITION BY ad_id ORDER BY date DESC) AS latest_delivery_str,\n        "
            "FIRST_VALUE(account_status) OVER (PARTITION BY ad_id ORDER BY date DESC) AS latest_account_status,\n        "
        )

    def _build_daily_columns(self, ctx):
        cols = {"id": self.dimension, "name": self.name_field}
        cols.update(_agg_columns())
        cols = _insert_after(cols, "链接点击数", _agg_dedup_columns())
        cols = _insert_after(cols, "展示次数", {
            "千展": "ROUND(SUM(amount_spent)/SUM(impressions)*1000,2)",
        })
        cols = _insert_after(cols, "花费金额", {
            "最新时间": "DATE_FORMAT(MAX(fetch_time) + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "创建时间": "DATE_FORMAT(ANY_VALUE(create_time) + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "status": "ANY_VALUE(status)",
            "effective_status": "ANY_VALUE(latest_delivery_str)",
            "account_status": "ANY_VALUE(latest_account_status)",
        })
        # 无预算列
        cols["频次"] = "ROUND(AVG(frequency),2)"
        cols["3d频次"] = "ROUND(AVG(frequency_3d),2)"
        cols["5d频次"] = "ROUND(AVG(frequency_5d),2)"
        cols["7d频次"] = "ROUND(AVG(frequency_7d),2)"
        cols = _insert_1d(cols, ctx.show_1d, agg=True)
        cols["对话数"] = "SUM(messaging_conversation_started)"
        cols["对话成本"] = "ROUND(SUM(amount_spent)/SUM(messaging_conversation_started),2)"
        cols["unique_name"] = "ANY_VALUE(first_unique_name)"
        cols["主页ID"] = "ANY_VALUE(page_id)"
        cols["帖子ID"] = "ANY_VALUE(post_id)"
        cols["原帖数量"] = "ANY_VALUE(post_ad_count)"
        cols["投放链接"] = "ANY_VALUE(landing_url)"
        cols["账户ID"] = "ANY_VALUE(latest_account_id)"
        cols["账户名称"] = "ANY_VALUE(latest_account_name)"
        cols["部门"] = "ANY_VALUE(latest_department)"
        cols["游戏平台"] = "ANY_VALUE(latest_game_platform)"
        return cols

    def _build_hourly_columns(self, ctx):
        cols = {"id": self.dimension, "name": self.name_field}
        cols.update(_hourly_columns())
        cols = _insert_after(cols, "链接点击数", _hourly_dedup_columns())
        cols = _insert_after(cols, "展示次数", {"千展": "ROUND(cpm,2)"})
        cols = _insert_after(cols, "花费金额", {
            "时间": "DATE_FORMAT(date, '%%m-%%d %%H:%%i')",
            "最新时间": "DATE_FORMAT(fetch_time + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "创建时间": "DATE_FORMAT(create_time + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            "status": "status",
            "effective_status": "delivery_str",
            "account_status": "account_status",
        })
        cols["频次"] = "ROUND(frequency,2)"
        cols["3d频次"] = "ROUND(frequency_3d,2)"
        cols["5d频次"] = "ROUND(frequency_5d,2)"
        cols["7d频次"] = "ROUND(frequency_7d,2)"
        cols = _insert_1d(cols, ctx.show_1d, agg=False)
        cols["对话数"] = "messaging_conversation_started"
        cols["对话成本"] = "ROUND(amount_spent/messaging_conversation_started,2)"
        cols["unique_name"] = "unique_name"
        cols["主页ID"] = "page_id"
        cols["帖子ID"] = "post_id"
        cols["投放链接"] = "landing_url"
        return cols


class PixelIdBuilder(AdIdBuilder):
    """像素维度：每个像素关联的每条广告单独展示。"""

    dimension = "pixel_id"
    name_field = "pixel_id"
    level = "ad"
    # 像素与广告是一对多关系，预算无法无歧义地归属到单个像素。
    should_enrich_running_budget = False

    @staticmethod
    def _pixel_condition() -> str:
        return "AND pixel_id IS NOT NULL AND pixel_id != ''"

    def _build_daily_columns(self, ctx):
        cols = super()._build_daily_columns(ctx)
        # 原广告 Tab 的 name 已改为像素名，广告/账户名称保留在尾部。
        account_name = cols.pop("账户名称")
        cols["广告名称"] = "ANY_VALUE(ad_name)"
        cols["账户名称"] = account_name
        return cols

    def _build_hourly_columns(self, ctx):
        cols = super()._build_hourly_columns(ctx)
        cols["广告名称"] = "ad_name"
        cols["账户名称"] = "account_name"
        return cols

    def build_daily_sql(self, ctx: "DetailQueryHandler") -> tuple[str, dict]:
        columns = self._build_daily_columns(ctx)
        name_filter = ctx.search_filter(self.name_field, self.id_expr())
        select_fields = [f"{expr} AS {col}" for col, expr in columns.items()]
        where_clause = (
            f"level = 'ad' AND {ctx.effective_date_sql} {ctx.where_sql} "
            f"{name_filter} {self._pixel_condition()}"
        )

        sql = f"""WITH daily_data AS (
    SELECT
        {self._daily_window_columns()}*
    FROM ad_daily_detail
    WHERE {where_clause}
)
SELECT {', '.join(select_fields)}
FROM daily_data t
GROUP BY pixel_id, ad_id
{ctx.filter_clause()}
{ctx.order_clause()}
LIMIT {ctx.page_size} OFFSET {ctx.offset};"""
        return sql, columns

    def build_hourly_sql(self, ctx: "DetailQueryHandler") -> tuple[str, dict]:
        columns = self._build_hourly_columns(ctx)
        name_filter = ctx.search_filter(self.name_field, self.id_expr())
        select_fields = [f"{expr} AS {col}" for col, expr in columns.items()]

        sql = f"""SELECT {', '.join(select_fields)}
FROM ad_hourly_detail
WHERE level = 'ad'
  AND {ctx.date_sql} {ctx.where_sql} {name_filter}
  {self._pixel_condition()}
  {ctx.filter_clause(is_hourly=True, where_mode=True)}
{ctx.order_clause(is_hourly=True)}
LIMIT {ctx.page_size} OFFSET {ctx.offset};"""
        return sql, columns

    def build_count_sql(self, ctx: "DetailQueryHandler") -> str:
        name_filter = ctx.search_filter(self.name_field, self.id_expr())
        return f"""SELECT COUNT(*) AS total
FROM (
    SELECT DISTINCT pixel_id, ad_id
    FROM {ctx.table}
    WHERE level = 'ad' AND {ctx.effective_date_sql} {ctx.where_sql} {name_filter}
      {self._pixel_condition()}
) t"""


class ChannelBuilder:
    """渠道维度: JOIN Doris fb_ad_channel, 按渠道聚合其下账户的系列(campaign)消耗"""
    dimension = "channel"

    async def query(
        self,
        ctx: "DetailQueryHandler",
        db: AsyncMySQL,
    ) -> tuple[list, dict, int]:
        cols = _agg_columns()
        cols = _insert_after(cols, "花费金额", {
            # 预算是时点值, 只取每个 campaign 最新一天(rn=1)的快照; 花费等累加指标对全范围求和
            # 在跑预算紧跟花费金额: 两列都 pin 在左侧, 固定列必须连续否则前端错位
            "在跑预算": f"SUM(CASE WHEN rn = 1 AND {_RUNNING_COND} THEN budget ELSE 0 END) / 100",
            "最新时间": "DATE_FORMAT(MAX(fetch_time) + INTERVAL 8 HOUR, '%%m-%%d %%H:%%i')",
            **_spend_split_columns(),
        })
        cols = _insert_1d(cols, ctx.show_1d, agg=True)
        cols["对话数"] = "SUM(messaging_conversation_started)"
        cols["对话成本"] = "ROUND(SUM(amount_spent)/SUM(messaging_conversation_started),2)"

        all_cols = {"id": "ca.channel_id", "name": "ca.channel_name"}
        all_cols.update(cols)
        select_fields = [f"{expr} AS {col}" for col, expr in all_cols.items()]

        channel_cte = """channel_accounts AS (
    SELECT id AS channel_id, channel_name, acc_id AS account_id
    FROM fb_ad_channel
    LATERAL VIEW EXPLODE_JSON_ARRAY_STRING(json_extract(account_ids_json, '$[*].account_id')) exp_acc AS acc_id
)"""
        name_filter = ctx.search_filter("ca.channel_name", "ca.channel_id")

        if ctx.is_hour:
            # 小时表内同一天的行是累计快照, 先取每个 campaign 每天最末一条
            dedup_cte = f"""ads AS (
    SELECT *,
           CASE
             WHEN EXTRACT(HOUR FROM date) = 0
                  THEN CAST(date - INTERVAL '1' DAY AS DATE)
             ELSE CAST(date AS DATE)
           END AS grouping_date
    FROM {ctx.table}
    WHERE level = 'campaign'
      AND {ctx.effective_date_sql} {ctx.where_sql}
),
daily_max_ads AS (
    SELECT
        ROW_NUMBER() OVER (
            PARTITION BY account_id, campaign_id, grouping_date
            ORDER BY
                CASE WHEN EXTRACT(HOUR FROM date) = 0 THEN 0 ELSE 1 END,
                date DESC
        ) AS rn,
        *
    FROM ads
)"""
            base_table = "daily_max_ads"
            rn_filter = "WHERE t.rn = 1"
        else:
            dedup_cte = f"""daily_ranked AS (
    SELECT
        ROW_NUMBER() OVER (
            PARTITION BY account_id, campaign_id
            ORDER BY date DESC
        ) AS rn,
        *
    FROM {ctx.table}
    WHERE level = 'campaign'
      AND {ctx.effective_date_sql} {ctx.where_sql}
)"""
            base_table = "daily_ranked"
            rn_filter = ""

        sql = f"""WITH {dedup_cte},
{channel_cte}
SELECT {', '.join(select_fields)}
FROM {base_table} t
JOIN channel_accounts ca ON t.account_id = ca.account_id {name_filter}
{rn_filter}
GROUP BY ca.channel_id, ca.channel_name
{ctx.order_clause()}
LIMIT {ctx.page_size} OFFSET {ctx.offset};"""

        count_sql = f"""WITH {channel_cte}
SELECT COUNT(DISTINCT ca.channel_id) AS total
FROM (
    SELECT DISTINCT account_id
    FROM {ctx.table}
    WHERE level = 'campaign'
      AND {ctx.effective_date_sql} {ctx.where_sql}
) t
JOIN channel_accounts ca ON t.account_id = ca.account_id {name_filter}"""

        result = await db.fetchall(sql, ctx.statement_params, as_dict=True)
        count_result = await db.fetchone(count_sql, ctx.statement_params, as_dict=True)
        total = count_result["total"] if count_result else 0

        columns = {"id": "channel_id", "name": "channel_name"}
        columns.update(cols)
        return result, columns, total


# ═══════════════════════════════════════════════════════════════════════════
# 维度注册表
# ═══════════════════════════════════════════════════════════════════════════

DIMENSION_BUILDERS: Dict[str, DimensionQueryBuilder | ChannelBuilder] = {
    DimensionType.DEPARTMENT.value: DepartmentBuilder(),
    DimensionType.GAME_PLATFORM.value: GamePlatformBuilder(),
    DimensionType.AD_PLATFORM.value: AdPlatformBuilder(),
    DimensionType.AGENT_LINE.value: AgentLineBuilder(),
    DimensionType.PLACER_ID.value: PlacerIdBuilder(),
    DimensionType.CHANNEL_ID.value: ChannelBuilder(),
    DimensionType.ACCOUNT_ID.value: AccountIdBuilder(),
    DimensionType.CAMPAIGN_ID.value: CampaignIdBuilder(),
    DimensionType.AD_SET_ID.value: AdSetIdBuilder(),
    DimensionType.AD_ID.value: AdIdBuilder(),
    DimensionType.PIXEL_ID.value: PixelIdBuilder(),
}


# ═══════════════════════════════════════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════════════════════════════════════

class DetailQueryHandler:
    """维度明细查询处理器，封装全部查询逻辑"""

    def __init__(
        self,
        dimension: DimensionType,
        query_params: DashboardQueryParams,
        db: AsyncMySQL,
        erp_db: AsyncMySQL,
        current_user: UserModel,
    ):
        self.dim = dimension.value
        self.db = db
        self.erp_db = erp_db
        self.current_user = current_user

        self.q_params = query_params.split()
        self.sort_by = self.q_params.get("sort_by", [None])[0] if "sort_by" in self.q_params else None
        self.sort_order = self.q_params.get("sort_order", ["desc"])[0] if "sort_order" in self.q_params else "desc"
        self.page = self.q_params.get("page", 1)
        self.page_size = self.q_params.get("page_size", 100)
        self.name = self.q_params.get("name", [None])[0]
        search_ids = self.q_params.get("id", [])
        self.search_ids = list(dict.fromkeys(
            search_id.removeprefix("act_")
            for search_id in search_ids
            if search_id
        ))
        # 数值筛选从原始参数取, split() 的逗号拆分会破坏格式
        self.metric_filters = parse_metric_filters(query_params.filters)

        # 仅对应 where_sql 的权限、维度和状态条件；补充指标查询会复用它。
        self.params: list = []
        # 仅对应 search_filter 的 name / id 占位符；主列表和总数查询使用。
        self.search_filter_params: list = []
        # pixel_id 维度的 name 同时支持像素 ID 和 Mongo 中维护的像素名称。
        # 名称解析完成后，这些 ID 会作为 Doris 查询的 IN 条件参数。
        self.pixel_name_ids: list[str] = []
        self.where_sql = ""
        self.date_sql = ""
        self.is_hour = False
        self.subset: set = set()
        self.ad_level_filters: Dict[str, List[str]] = {}
        self.ad_level_null_filters: List[str] = []

    def _check_permission(self) -> bool:
        return (
            any("operator" in role for role in self.current_user.roles)
            or Roles.DEVELOPER in self.current_user.roles
            or Roles.TEST in self.current_user.roles
            or Roles.ADMIN in self.current_user.roles
            or Roles.AM in self.current_user.roles
            or self.dim in newest_dim
        )

    def _parse_date(self):
        start, end = self.q_params["date"][0], self.q_params["date"][1]
        self.is_hour = len(start) == 13
        if self.is_hour:
            self.date_sql = f"date BETWEEN '{start}' AND '{end}'"
            self.daily_date_sql = self.date_sql
        else:
            end_dt = (datetime.strptime(end, DayFormat) + timedelta(days=1)).strftime(DayFormat)
            self.date_sql = f"date BETWEEN '{start}' AND '{end_dt}'"
            self.daily_date_sql = f"date BETWEEN '{start}' AND '{end}'"

    async def _init_where(self):
        depts = self.current_user.departments or []

        if DEPT_ALL in depts:
            pass
        elif depts:
            dept_list = ", ".join([repr(d) for d in depts])
            self.where_sql = f"AND (department IN ({dept_list}))"
        else:
            real_name = self.current_user.real_name
            docs = await cols.personal_accounts.find(
                {"user_name": real_name, "status": True}, {"accounts.id": 1}
            ).to_list(length=None)
            account_ids = [acc["id"] for d in docs for acc in d.get("accounts", []) if acc.get("id")]
            if account_ids:
                placeholders = ", ".join(["%s"] * len(account_ids))
                self.where_sql = f"AND (placer_id = %s OR account_id IN ({placeholders}))"
            else:
                self.where_sql = "AND (placer_id = %s)"
            self.params += [real_name, *account_ids]

    def _build_subset_filters(self):
        self.subset = generate_dimension_subset(self.dim, tabs=self.q_params.get("tab_order"))
        subset_params = {k: v for k, v in self.q_params.items() if k in self.subset}

        self._channel_filter_ids = None
        _is_ad_level_dim = self.dim in (
            DimensionType.CAMPAIGN_ID.value,
            DimensionType.AD_SET_ID.value,
            DimensionType.AD_ID.value,
        )
        # ID 类字段在各级别都存在，IS NULL 可直接应用
        _own_level_fields = {"campaign_id", "ad_set_id", "ad_id", "account_id"}

        for key, value in subset_params.items():
            if "null" in value:
                # 对于 ad 级别维度，非 ID 字段的 IS NULL 存入 ad_level_null_filters
                # 因为 ad 级别的 department/agent_line 等可能被 landing_url 覆盖
                if _is_ad_level_dim and key not in _own_level_fields:
                    self.ad_level_null_filters.append(key)
                else:
                    self.where_sql += f" AND {key} IS NULL"
                value = [v for v in value if v != "null"]
            if key == "date" or not value:
                continue
            if key == "channel":
                self._channel_filter_ids = value
                continue
            if key == "account_id":
                value = [v.removeprefix("act_") for v in value]
            if _is_ad_level_dim:
                self.ad_level_filters[key] = value
                continue
            placeholders = ", ".join(["%s"] * len(value))
            self.where_sql += f" AND {key} IN ({placeholders})"
            self.params.extend(value)

        self._subset_params = subset_params

        # 应用"下钻"筛选: 当前维度之后的 ID 维度(如在渠道/账户页面筛选 account_id/campaign_id,
        # 在系列/组页面筛选 ad_set_id/ad_id)
        _drill_down_dims = {"account_id", "campaign_id", "ad_set_id", "ad_id"}
        for key in _drill_down_dims:
            if key != self.dim and key not in self.subset and key in self.q_params:
                value = self.q_params[key]
                if not isinstance(value, list) or not value:
                    continue
                if key == "account_id":
                    value = [v.removeprefix("act_") for v in value]
                if _is_ad_level_dim:
                    self.ad_level_filters[key] = value
                else:
                    placeholders = ", ".join(["%s"] * len(value))
                    self.where_sql += f" AND {key} IN ({placeholders})"
                    self.params.extend(value)

    async def _apply_channel_filter(self):
        if not self._channel_filter_ids:
            return
        channel_mapping = await get_channel_account_mapping(self.erp_db)
        channel_account_ids = list({
            aid for cid in self._channel_filter_ids
            for aid in channel_mapping.get(cid, [])
        })
        if channel_account_ids:
            placeholders = ", ".join(["%s"] * len(channel_account_ids))
            self.where_sql += f" AND account_id IN ({placeholders})"
            self.params.extend(channel_account_ids)
        else:
            self.where_sql += " AND account_id IS NULL"

    async def _apply_account_filter(self):
        if self.dim != DimensionType.ACCOUNT_ID.value or not self.where_sql:
            return
        # 使用内联子查询替代 IN 大列表，避免 Doris 表达式树节点数超限
        # (Exceeded the maximum children of an expression tree)
        # 从 ad 级别查找，因为 department/agent_line 等字段在 ad 级别最准确
        subquery = (
            f"SELECT DISTINCT account_id FROM {self.table} "
            f"WHERE level = 'ad' AND {self.effective_date_sql} {self.where_sql}"
        )
        # params 保持不变，继续服务于子查询内部继承的 where_sql
        self.where_sql = f"AND account_id IN ({subquery})"

    async def _apply_channel_dim_filter(self):
        if self.dim != DimensionType.CHANNEL_ID.value:
            return
        extra_filter = ""
        extra_params: list = []
        for key in ("game_platform", "ad_platform", "agent_line", "placer_id"):
            if key in self.q_params and key not in self._subset_params:
                values = self.q_params[key]
                if isinstance(values, list) and values:
                    placeholders = ", ".join(["%s"] * len(values))
                    extra_filter += f" AND {key} IN ({placeholders})"
                    extra_params.extend(values)
        if not self.where_sql and not extra_filter:
            return
        # 系列粒度筛选: 户粒度会把该户其他平台/部门的系列消耗也算进渠道页。
        # 维度字段在 ad 级最准, 先筛出命中的 campaign_id; 内联子查询避免 IN 大列表超限
        subquery = (
            f"SELECT DISTINCT campaign_id FROM {self.table} "
            f"WHERE level = 'ad' AND {self.effective_date_sql} {self.where_sql}{extra_filter}"
        )
        # 原 where_sql 的 params 已内嵌到子查询，末尾追加 extra_params
        self.params = list(self.params) + extra_params
        self.where_sql = f"AND campaign_id IN ({subquery})"

    def _apply_status_filter(self):
        if "status" in self.q_params and self.q_params["status"]:
            status_list = self.q_params["status"]
            placeholders = ", ".join(["%s"] * len(status_list))
            # 列表展示和筛选项都基于投放状态 effective_status(=delivery_str),
            # status 是 FB 配置状态,广告级的 ADSET_PAUSED/CAMPAIGN_PAUSED 等只存在于 delivery_str
            col = "account_status" if self.dim == DimensionType.ACCOUNT_ID.value else "delivery_str"
            self.where_sql += f" AND {col} IN ({placeholders})"
            self.params.extend(status_list)

    async def _apply_ad_level_filters(self):
        if not self.ad_level_filters and not self.ad_level_null_filters:
            return
        # 系列/广告组/广告维度: 区分可直接应用的字段和需要从 ad 级别查询的字段
        if self.dim in (
            DimensionType.CAMPAIGN_ID.value,
            DimensionType.AD_SET_ID.value,
            DimensionType.AD_ID.value,
        ):
            # 自身及祖先 ID(如系列维度的 account_id/campaign_id)在本级别行上存在，可直接作为 WHERE 条件;
            # 后代 ID(如系列维度的 ad_id)只在 ad 级别行上有，走子查询反查
            _id_order = ["account_id", "campaign_id", "ad_set_id", "ad_id"]
            _dim_idx = _id_order.index(self.dim)
            direct_filters = {}
            ad_only_filters = {}
            for field, values in self.ad_level_filters.items():
                if field in _id_order and _id_order.index(field) <= _dim_idx:
                    direct_filters[field] = values
                else:
                    ad_only_filters[field] = values

            # 直接应用 ID 类筛选
            for field, values in direct_filters.items():
                placeholders = ", ".join(["%s"] * len(values))
                self.where_sql += f" AND {field} IN ({placeholders})"
                self.params.extend(values)

            # department/agent_line 等仅在 ad 级别准确
            # ad_id 维度本身就查 ad level，可直接应用这些条件，无需子查询
            if self.dim == DimensionType.AD_ID.value:
                for field, values in ad_only_filters.items():
                    placeholders = ", ".join(["%s"] * len(values))
                    self.where_sql += f" AND {field} IN ({placeholders})"
                    self.params.extend(values)
                for f in self.ad_level_null_filters:
                    self.where_sql += f" AND {f} IS NULL"
            elif ad_only_filters or self.ad_level_null_filters:
                # campaign/ad_set 维度需先从 ad 级别筛出对应实体 ID。
                # 原实现把结果物化到 Python 再拼 IN (...)，entity_ids 过多时会触发
                # Doris "Exceeded the maximum children of an expression tree (10000)"。
                # 改为内联子查询，由 Doris 自行处理，表达式树只占 1 个子查询节点。
                ad_filter_sql = ""
                ad_filter_params: list = []
                for field, values in ad_only_filters.items():
                    placeholders = ", ".join(["%s"] * len(values))
                    ad_filter_sql += f" AND {field} IN ({placeholders})"
                    ad_filter_params.extend(values)
                for f in self.ad_level_null_filters:
                    ad_filter_sql += f" AND {f} IS NULL"

                # 子查询继承当前 where_sql（含用户部门权限 + direct_filters + status_filter）
                # 注意: self.where_sql 中已有的 %s 占位符会在子查询中再出现一次，
                # 因此 params 需要复制一份以保证顺序正确。
                # 最终 params 顺序: [外层原 params] + [子查询内 where_sql 的 params 副本] + [ad_filter_params]
                subquery = (
                    f"SELECT DISTINCT {self.dim} FROM {self.table} "
                    f"WHERE level = 'ad' AND {self.effective_date_sql} {self.where_sql}{ad_filter_sql}"
                )
                self.params.extend(list(self.params) + ad_filter_params)
                self.where_sql += f" AND {self.dim} IN ({subquery})"
        else:
            for field, values in self.ad_level_filters.items():
                placeholders = ", ".join(["%s"] * len(values))
                self.where_sql += f" AND {field} IN ({placeholders})"
                self.params.extend(values)

    @property
    def table(self) -> str:
        return "ad_hourly_detail" if self.is_hour else "ad_daily_detail"

    @property
    def effective_date_sql(self) -> str:
        return self.date_sql if self.is_hour else self.daily_date_sql

    @property
    def is_newest(self) -> bool:
        return self.q_params.get("is_newest", True)

    @property
    def show_1d(self) -> bool:
        return self.q_params.get("show_1d", True)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def statement_params(self) -> list:
        """主列表 SQL 的参数：where_sql 参数后接 search_filter 参数。"""
        return [*self.params, *self.search_filter_params]

    def search_filter(self, name_field: str, id_field: str) -> str:
        """name 忽略大小写模糊匹配 + 一个或多个 id 精确匹配"""
        filters = ""
        if self.name:
            if self.dim == DimensionType.PIXEL_ID.value:
                pixel_conditions = [f"LOWER({name_field}) LIKE %s"]
                if self.pixel_name_ids:
                    placeholders = ", ".join(["%s"] * len(self.pixel_name_ids))
                    pixel_conditions.append(f"{id_field} IN ({placeholders})")
                filters += f" AND ({' OR '.join(pixel_conditions)})"
            else:
                filters += f" AND LOWER({name_field}) LIKE '%%{self.name.lower()}%%'"
        if self.search_ids:
            placeholders = ", ".join(["%s"] * len(self.search_ids))
            filters += f" AND {id_field} IN ({placeholders})"
        return filters

    async def _resolve_pixel_name_filter(self):
        """将像素名称关键字解析为像素 ID，供 Doris 查询阶段筛选。"""
        if self.dim != DimensionType.PIXEL_ID.value or not self.name:
            return

        async for doc in cols.fb_pixels.find(
            {"name": {"$regex": re.escape(self.name), "$options": "i"}},
            {"_id": 1},
        ):
            self.pixel_name_ids.append(str(doc["_id"]))
        self.pixel_name_ids.sort()

        # search_filter 中的占位符位于所有现有 where_sql 条件之后。
        self.search_filter_params.extend([f"%{self.name.lower()}%", *self.pixel_name_ids])

    def _append_search_id_params(self):
        """search_filter 的 ID 占位符在现有 where_sql 条件之后。"""
        self.search_filter_params.extend(self.search_ids)

    def order_clause(self, is_hourly: bool = False) -> str:
        return validate_and_build_order_clause(self.sort_by, self.sort_order, is_hourly=is_hourly)

    def filter_clause(self, is_hourly: bool = False, where_mode: bool = False) -> str:
        """数值筛选子句: 聚合查询用 HAVING(紧跟 GROUP BY), 单行明细查询用 AND 续接 WHERE"""
        conditions = build_filter_conditions(self.metric_filters, is_hourly=is_hourly)
        if not conditions:
            return ""
        joined = " AND ".join(conditions)
        return f"AND {joined}" if where_mode else f"HAVING {joined}"

    def _make_response(self, data: list, columns: dict, total: int) -> ApiResponse:
        columns.pop("id", None)
        return ApiResponse(data={
            "data": data,
            "columns": list(columns.keys()),
            "pagination": {
                "page": self.page, "page_size": self.page_size,
                "total": total, "total_pages": (total + self.page_size - 1) // self.page_size,
            },
        })

    async def _enrich_campaign_channels(self, result: list, columns: dict):
        if self.dim != DimensionType.CAMPAIGN_ID.value or not result:
            return
        account_ids = [str(row["账户ID"]) for row in result if row.get("账户ID")]
        if not account_ids:
            return
        # page_size 上限 100000，IN 列表过长会撑爆 MySQL max_allowed_packet，分批查询。
        channel_rows: list = []
        chunk_size = 1000
        for i in range(0, len(account_ids), chunk_size):
            chunk = account_ids[i:i + chunk_size]
            placeholders = ", ".join(["%s"] * len(chunk))
            chunk_rows = await self.erp_db.fetchall(
                f"SELECT ca.fb_account_id, fc.channel_name "
                f"FROM fbad_channel_account ca "
                f"JOIN fbad_channel fc ON ca.channel_id = fc.id "
                f"WHERE ca.fb_account_id IN ({placeholders})",
                chunk,
                as_dict=True,
            )
            channel_rows.extend(chunk_rows)
        acct_channel_map: dict[str, list[str]] = {}
        for cr in channel_rows:
            acct_channel_map.setdefault(str(cr["fb_account_id"]), []).append(cr["channel_name"])
        for row in result:
            channels = acct_channel_map.get(str(row.get("账户ID", "")), [])
            row["渠道"] = ", ".join(channels) if channels else None
        columns["渠道"] = "channel_name"

    async def _enrich_campaign_ad_dimensions(self, result: list, columns: dict):
        """系列维度补充部门/游戏平台: ad 级别有这些字段, campaign 级别没有。"""
        if self.dim != DimensionType.CAMPAIGN_ID.value or not result:
            return
        campaign_ids = [str(row["id"]) for row in result if row.get("id")]
        if not campaign_ids:
            return
        # page_size 最大 10000，IN 列表直接展开会触发 Doris
        # "Exceeded the maximum children of an expression tree (10000)"，分批查询。
        rows: list = []
        chunk_size = 1000
        for i in range(0, len(campaign_ids), chunk_size):
            chunk = campaign_ids[i:i + chunk_size]
            placeholders = ", ".join(["%s"] * len(chunk))
            chunk_rows = await self.db.fetchall(
                f"SELECT DISTINCT campaign_id, department, game_platform "
                f"FROM {self.table} "
                f"WHERE level = 'ad' AND {self.effective_date_sql} "
                f"  AND campaign_id IN ({placeholders})",
                chunk,
                as_dict=True,
            )
            rows.extend(chunk_rows)
        dept_map: dict[str, set[str]] = {}
        plat_map: dict[str, set[str]] = {}
        for r in rows:
            cid = str(r["campaign_id"])
            if r.get("department"):
                dept_map.setdefault(cid, set()).add(r["department"])
            if r.get("game_platform"):
                plat_map.setdefault(cid, set()).add(r["game_platform"])
        for row in result:
            cid = str(row.get("id", ""))
            depts = dept_map.get(cid, set())
            plats = plat_map.get(cid, set())
            row["部门"] = ", ".join(sorted(depts)) if depts else None
            row["游戏平台"] = ", ".join(sorted(plats)) if plats else None
        columns["部门"] = "department"
        columns["游戏平台"] = "game_platform"

    async def _enrich_pixel_names(self, result: list):
        """将成效表中的 pixel_id 批量映射为 Mongo 中维护的像素名称。"""
        if self.dim != DimensionType.PIXEL_ID.value or not result:
            return
        pixel_ids = {str(row["id"]) for row in result if row.get("id")}
        if not pixel_ids:
            return
        pixel_names: dict[str, str] = {}
        async for doc in cols.fb_pixels.find(
            {"_id": {"$in": list(pixel_ids)}}, {"_id": 1, "name": 1}
        ):
            pixel_names[str(doc["_id"])] = doc.get("name") or str(doc["_id"])
        for row in result:
            pixel_id = str(row.get("id") or "")
            row["name"] = pixel_names.get(pixel_id, pixel_id)

    async def _enrich_running_budget(self, result: list, builder, columns: dict):
        """从 campaign level 查去重的在跑系列预算，Python 层补到结果中。
        ad level 有维度字段(department/agent_line等)但没有 budget；
        campaign level 有 budget 但没有维度字段。
        所以用 JOIN: ad 级别取维度→campaign_id 映射, campaign 级别取预算。
        """
        dim = builder.dimension
        table = self.table
        budget_date_sql = self.effective_date_sql

        # ad 级别映射不限日期: campaign 的 agent_line 由 landing_url 决定, 不随日期变化
        # campaign 级别用日期过滤取最新预算
        budget_sql = f"""SELECT t_ad.{dim}, SUM(t_camp.budget)/100 AS total_budget
FROM (
    SELECT DISTINCT {dim}, campaign_id
    FROM {table}
    WHERE level = 'ad' {self.where_sql}
) t_ad
JOIN (
    SELECT campaign_id, budget, delivery_str, account_status,
        ROW_NUMBER() OVER (PARTITION BY campaign_id ORDER BY date DESC) AS rn
    FROM {table}
    WHERE level = 'campaign' AND {budget_date_sql}
) t_camp ON t_ad.campaign_id = t_camp.campaign_id
WHERE t_camp.rn = 1 AND t_camp.delivery_str IN ('ACTIVE','IN_PROCESS') AND t_camp.account_status IN (1,8,9)
GROUP BY t_ad.{dim}"""
        budget_rows = await self.db.fetchall(budget_sql, self.params, as_dict=True)
        budget_map = {str(row[dim]): row["total_budget"] for row in budget_rows}

        for row in result:
            row["在跑预算"] = budget_map.get(str(row.get("id")), None)

        # 紧跟花费金额插入: 两列都 pin 在左侧, 固定列必须连续否则前端错位
        if "在跑预算" not in columns:
            new_columns = {}
            for k, v in columns.items():
                new_columns[k] = v
                if k == "花费金额":
                    new_columns["在跑预算"] = "total_budget"
            columns.clear()
            columns.update(new_columns)

    async def _enrich_account_spend_split(self, result: list, columns: dict):
        """户维度补充已关停/在跑消耗: 户快照只有账户级状态, 按系列快照状态拆分才和其他维度同口径"""
        if self.dim != DimensionType.ACCOUNT_ID.value or not result:
            return
        split_exprs = _spend_split_columns()
        # 小时表内行是当日累计快照, 系列级按 (户, 小时) 聚合后与户行同口径
        time_col = ",\n    DATE_FORMAT(date, '%%m-%%d %%H:%%i') AS ts" if self.is_hour else ""
        group_by = "account_id, date" if self.is_hour else "account_id"
        sql = f"""SELECT account_id{time_col},
    {split_exprs['已关停消耗']} AS stopped_spent,
    {split_exprs['在跑消耗']} AS running_spent
FROM {self.table}
WHERE level = 'campaign' AND {self.effective_date_sql} {self.where_sql}
GROUP BY {group_by}"""
        rows = await self.db.fetchall(sql, self.params, as_dict=True)
        if self.is_hour:
            split_map = {(str(r["account_id"]), r["ts"]): r for r in rows}
        else:
            split_map = {str(r["account_id"]): r for r in rows}
        for row in result:
            k = (str(row.get("id")), row.get("时间")) if self.is_hour else str(row.get("id"))
            r = split_map.get(k)
            row["已关停消耗"] = r["stopped_spent"] if r else None
            row["在跑消耗"] = r["running_spent"] if r else None
        # 插在单日限额后: 花费金额/在跑预算/status 都 pin 左侧, 固定列之间不能夹未固定列
        new_columns = _insert_after(
            columns, "单日限额", {"已关停消耗": "stopped_spent", "在跑消耗": "running_spent"}
        )
        columns.clear()
        columns.update(new_columns)

    async def _enrich_account_attributes(self, result: list, columns: dict):
        """从 ERP 补齐账户属性（fbad_channel_account.whitelist_type）。"""
        if self.dim != DimensionType.ACCOUNT_ID.value:
            return

        columns["account_attribute"] = "whitelist_type"
        account_ids = list({str(row["id"]) for row in result if row.get("id")})
        attribute_by_account = await _account_attributes(self.erp_db, account_ids)
        for row in result:
            row["account_attribute"] = attribute_by_account.get(str(row.get("id")))

    async def execute(self) -> ApiResponse | ErrResponse:
        # if not self._check_permission():
        #     return ApiResponse(data={"data": [], "columns": []})

        self._parse_date()
        await self._init_where()
        self._build_subset_filters()
        await self._apply_channel_filter()
        await self._apply_account_filter()
        await self._apply_channel_dim_filter()
        self._apply_status_filter()
        await self._apply_ad_level_filters()
        await self._resolve_pixel_name_filter()
        self._append_search_id_params()

        builder = DIMENSION_BUILDERS[self.dim]

        # 渠道维度走独立逻辑
        if isinstance(builder, ChannelBuilder):
            result, columns, total = await builder.query(self, self.db)
            return self._make_response(result, columns, total)

        # 选择 SQL 构建路径
        if not self.is_newest and len(self.subset) <= dimension_list.index("agent_line"):
            sql, columns = builder.build_filled_sql(self, self.subset)
            count_sql = builder.build_filled_count_sql(self)
        elif self.is_hour:
            sql, columns = builder.build_hourly_sql(self)
            count_sql = builder.build_count_sql(self)
        else:
            sql, columns = builder.build_daily_sql(self)
            count_sql = builder.build_count_sql(self)

        if self.metric_filters:
            # 原 count SQL 不含数值筛选, 复用数据 SQL 去掉排序/分页后包一层 COUNT 保证总数准确
            # 顶层 ORDER BY 是整条 SQL 的最后一个, rsplit 不会误切窗口函数内的 ORDER BY
            inner_sql = sql.rsplit("ORDER BY", 1)[0]
            count_sql = f"SELECT COUNT(*) AS total FROM ({inner_sql}) t_cnt"

        result = await self.db.fetchall(sql, self.statement_params, as_dict=True)
        count_result = await self.db.fetchone(count_sql, self.statement_params, as_dict=True)
        total = count_result["total"] if count_result else 0

        await self._enrich_account_spend_split(result, columns)
        await self._enrich_account_attributes(result, columns)
        await self._enrich_pixel_names(result)
        if result and (
            (builder.from_ad_level and builder.should_enrich_running_budget)
            or self.dim == DimensionType.ACCOUNT_ID.value
        ):
            await self._enrich_running_budget(result, builder, columns)
        await self._enrich_campaign_channels(result, columns)
        await self._enrich_campaign_ad_dimensions(result, columns)

        return self._make_response(result, columns, total)


# 没匹配到代理线的广告，采集侧会把 placer_id 落成授权个号的运营同事
# (schedulers/tasks/ad_sync_new/dispatcher.py)，这些消耗要按 ERP 授权关系转记给投放。
_OPERATION_DEPARTMENT = "运营部"

# 户级返回给前端直接展示的标识
_NURTURING_TAG = "养户"

# 账户可用，取 _RUNNING_COND 的账户部分；账户层快照的 delivery_str 是状态码不是投放状态
_LIVE_ACCOUNT_COND = "account_status IN (1,8,9)"

# 项目/系列层额外返回的成效指标，口径跟广告面板(点击成本)和概览(付费成本)一致。
# 这两层必定限定在单个账户内，所以是单币种，可以直接给标量而不用像消耗那样按币种拆。
_DRILL_METRICS = {
    "cpc": "ROUND(SUM(amount_spent)/NULLIF(SUM(clicks_all),0),2)",
    "cpm": "ROUND(SUM(amount_spent)*1000/NULLIF(SUM(impressions),0),2)",
    "register_cost": "ROUND(SUM(amount_spent)/NULLIF(SUM(complete_registration),0),2)",
    "payment_cost": "ROUND(SUM(amount_spent)/NULLIF(SUM(purchases),0),2)",
}


def _strip_act(account_id) -> str:
    return str(account_id or "").removeprefix("act_")


async def _account_attributes(
    erp_db: AsyncMySQL, account_ids: list[str]
) -> dict[str, int]:
    """户 -> ERP 账户属性（fbad_channel_account.whitelist_type）。"""
    result: dict[str, int] = {}
    for i in range(0, len(account_ids), 1000):  # 分批避免 ERP MySQL 的 IN 列表过长
        chunk = account_ids[i : i + 1000]
        placeholders = ", ".join(["%s"] * len(chunk))
        rows = await erp_db.fetchall(
            f"SELECT fb_account_id, whitelist_type FROM fbad_channel_account "
            f"WHERE fb_account_id IN ({placeholders})",
            chunk,
            as_dict=True,
        )
        for row in rows:
            if row.get("fb_account_id") and row.get("whitelist_type") is not None:
                result[str(row["fb_account_id"])] = row["whitelist_type"]
    return result


async def _accounts_by_attribute(
    erp_db: AsyncMySQL, attribute_values: list[str]
) -> list[str]:
    """这些账户类型（whitelist_type）下的户。"""
    placeholders = ", ".join(["%s"] * len(attribute_values))
    rows = await erp_db.fetchall(
        f"SELECT DISTINCT fb_account_id FROM fbad_channel_account "
        f"WHERE whitelist_type IN ({placeholders}) AND fb_account_id IS NOT NULL",
        attribute_values,
        as_dict=True,
    )
    return [str(row["fb_account_id"]) for row in rows]


async def _operation_placer_ids() -> list[str]:
    """运营部同事的 real_name。"""
    docs = await user_cols.user.find(
        {"department": _OPERATION_DEPARTMENT}, {"real_name": 1}
    ).to_list(length=None)
    return sorted({str(doc["real_name"]) for doc in docs if doc.get("real_name")})


async def _placer_departments(placer_ids: list[str]) -> dict[str, str | None]:
    docs = await user_cols.user.find(
        {"real_name": {"$in": placer_ids}}, {"real_name": 1, "department": 1}
    ).to_list(length=None)
    return {
        str(doc["real_name"]): doc.get("department")
        for doc in docs
        if doc.get("real_name")
    }


async def _feishu_placers_by_account() -> dict[str, list[dict]]:
    """在用户 -> 飞书登记的当前使用人；一个户登记多人时用逗号分隔。

    登记的是中文姓名（对应 user.full_name），要转成 Doris 的 placer_id（user.real_name）；
    对不上平台用户的登记（媒介代号、外部团队）不参与转记。
    """
    docs = await cols.feishu_account_used_record.find(
        {"in_use": True}, {"account_id": 1, "user_name": 1}
    ).to_list(length=None)
    if not docs:
        return {}
    user_docs = await user_cols.user.find(
        {}, {"real_name": 1, "full_name": 1, "department": 1}
    ).to_list(length=None)
    placer_by_name = {
        str(doc["full_name"]): {
            "placer_id": str(doc["real_name"]),
            "placer_name": str(doc["full_name"]),
            "department": doc.get("department"),
        }
        for doc in user_docs
        if doc.get("full_name") and doc.get("real_name")
    }

    result: dict[str, list[dict]] = {}
    for doc in docs:
        targets = [
            placer_by_name[name]
            for name in _split_filter_values(doc.get("user_name"))
            if name in placer_by_name
        ]
        if targets:
            result[_strip_act(doc.get("account_id"))] = targets
    return result


def _accounts_of_placers(
    placers_by_account: dict[str, list[dict]], placer_ids: list[str]
) -> list[str]:
    """这些投放在飞书登记里被记为当前使用人的户。"""
    wanted = set(placer_ids)
    return [
        account_id
        for account_id, targets in placers_by_account.items()
        if any(target["placer_id"] in wanted for target in targets)
    ]


def _personnel_spend_allowed_departments(
    current_user: UserModel, department_values: list[str]
) -> set[str] | None:
    """转记后的行必须落在这些部门里；None 表示不限。"""
    limits = []
    departments = current_user.departments or []
    if departments and DEPT_ALL not in departments:
        limits.append(set(departments))
    if department_values:
        limits.append(set(department_values))
    return set.intersection(*limits) if limits else None


def _personnel_spend_reattribute(
    rows: list[dict],
    placers_by_account: dict[str, list[dict]],
    operation_placers: set[str],
    allowed_departments: set[str] | None,
    placer_values: list[str],
) -> list[dict]:
    """把挂在运营同事名下的消耗改记到飞书登记的当前使用人名下。

    一户登记多个使用人时每人全额计，不拆分消耗；登记里查不到的户维持原样。
    """
    operation_rows = [r for r in rows if str(r.get("id") or "") in operation_placers]
    if not operation_rows:
        return rows
    result = [r for r in rows if str(r.get("id") or "") not in operation_placers]
    for row in operation_rows:
        targets = placers_by_account.get(_strip_act(row.get("account_id"))) or [
            {
                "placer_id": row["id"],
                "placer_name": row["name"],
                "department": row.get("department"),
            }
        ]
        for target in targets:
            if (
                allowed_departments is not None
                and target["department"] not in allowed_departments
            ):
                continue
            if placer_values and target["placer_id"] not in placer_values:
                continue
            result.append(
                {**row, "id": target["placer_id"], "name": target["placer_name"]}
            )
    return result


def _drop_reattributed_accounts(
    rows: list[dict], placers_by_account: dict[str, list[dict]]
) -> list[dict]:
    """下钻到运营同事名下时，已转记给投放的户不再在他名下重复出现。"""
    return [
        r for r in rows if _strip_act(r.get("account_id")) not in placers_by_account
    ]


async def _personnel_spend_currencies(rows: list[dict]) -> dict[str, str]:
    """一次 Mongo 查询补齐账户币种，避免随列表行数增长的 N+1 查询。"""
    account_ids = {
        _strip_act(row.get("account_id")) for row in rows if row.get("account_id")
    }
    if not account_ids:
        return {}
    account_docs = await cols.fb_ad_accounts.find(
        {"_id": {"$in": list(account_ids)}}, {"_id": 1, "currency": 1}
    ).to_list(length=None)
    return {
        str(doc["_id"]): str(doc.get("currency") or "未知币种")
        for doc in account_docs
        if doc.get("_id")
    }


def _personnel_spend_sort(items: list[dict], amount_by_id: dict[str, dict[str, float]]):
    """不同币种不混算；按 USD、其他币种、名称、ID 的顺序稳定排序。"""
    currency_order = [
        "USD",
        *sorted(
            {
                currency
                for currency_amounts in amount_by_id.values()
                for currency in currency_amounts
                if currency != "USD"
            }
        ),
    ]
    items.sort(
        key=lambda item: (
            *[-amount_by_id[item["id"]].get(currency, 0) for currency in currency_order],
            item["name"],
            item["id"],
        )
    )


def _personnel_spend_items(
    rows: list[dict], currency_by_account: dict[str, str]
) -> tuple[list[dict], dict[str, dict[str, float]]]:
    """将 Doris 的单币种账户聚合结果整理成前端可展示的多币种消耗。"""
    amounts_by_id: dict[str, dict[str, float]] = {}
    names_by_id: dict[str, str] = {}
    for row in rows:
        item_id = str(row.get("id") or "")
        if not item_id:
            continue
        currency = currency_by_account.get(_strip_act(row.get("account_id")), "未知币种")
        amounts = amounts_by_id.setdefault(item_id, {})
        amounts[currency] = amounts.get(currency, 0) + float(row.get("amount") or 0)
        names_by_id.setdefault(item_id, str(row.get("name") or item_id))

    items = [
        {
            "id": item_id,
            "name": names_by_id[item_id],
            "spends": [
                {"currency": currency, "amount": round(amount, 2)}
                for currency, amount in sorted(amounts.items())
            ],
        }
        for item_id, amounts in amounts_by_id.items()
    ]
    _personnel_spend_sort(items, amounts_by_id)
    return items, amounts_by_id


@router.get("/personnel-spend", summary="按投放人员汇总消耗")
async def get_personnel_spend(
    query_params: PersonnelSpendQueryParams = Depends(),
    db: AsyncMySQL = Depends(get_db),
    erp_db: AsyncMySQL = Depends(get_erp_db),
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    """人员面板的四层下钻：人员 → 账户 → 项目 → 系列。

    消耗始终从 ad 层统计，避免把层级快照和广告明细相加造成重复。每次点击只按
    当前父节点聚合；币种、人员名称分别使用两次批量 Mongo 查询补齐，不产生 N+1。

    挂在运营同事名下的消耗按飞书账户登记转记给投放（见 _personnel_spend_reattribute）：
    部门权限、部门筛选、投手筛选只约束原始归属，转记行绕过这三项后按投放的部门重新裁剪。
    """
    date_values = _split_filter_values(query_params.date)
    if len(date_values) != 2:
        return ErrResponse(message="date 参数格式应为 YYYY-MM-DD,YYYY-MM-DD")
    try:
        start_date = datetime.strptime(date_values[0], DayFormat)
        end_date = datetime.strptime(date_values[1], DayFormat) + timedelta(days=1)
    except ValueError:
        return ErrResponse(message="date 参数格式应为 YYYY-MM-DD,YYYY-MM-DD")
    if start_date >= end_date:
        return ErrResponse(message="结束日期不能早于开始日期")

    placer_values = _split_filter_values(query_params.placer_id)
    placer_id = placer_values[0] if len(placer_values) == 1 else None
    if query_params.level != "personnel" and len(placer_values) != 1:
        return ErrResponse(message="投放人员下钻时只能传一个 placer_id")
    account_id = (query_params.account_id or "").strip().removeprefix("act_") or None
    attribute_values = _split_filter_values(query_params.account_attribute)
    game_platform_values = _split_filter_values(query_params.game_platform)
    game_platform = (
        game_platform_values[0] if len(game_platform_values) == 1 else None
    )
    if query_params.level == "campaign" and len(game_platform_values) != 1:
        return ErrResponse(message="系列下钻时只能传一个 game_platform")

    if query_params.level != "personnel" and not placer_id:
        return ErrResponse(message="投放人员下钻必须传 placer_id")
    if query_params.level in {"project", "campaign"} and not account_id:
        return ErrResponse(message="项目下钻必须传 account_id")
    if query_params.level == "campaign" and not game_platform:
        return ErrResponse(message="系列下钻必须传 game_platform")

    conditions = ["date >= %s", "date < %s", "placer_id IS NOT NULL", "placer_id != ''"]
    sql_params: list[str] = [
        start_date.strftime(DayFormat),
        end_date.strftime(DayFormat),
    ]
    # 账户层快照只有 account_id/placer_id，能照搬到 idle 查询上的筛选另攒一份
    account_conditions: list[str] = []
    account_params: list = []

    permission_sql, permission_params = await _personnel_spend_permission_where(
        current_user
    )
    # scoped_* 是只约束原始归属的条件，运营部的行会绕过它们；无部门用户的个人账户
    # 权限跟归属无关，必须留在外层不被绕过。
    scoped_conditions: list[str] = []
    scoped_params: list[str] = []
    if permission_sql and current_user.departments:
        scoped_conditions.append(permission_sql)
        scoped_params.extend(permission_params)
    elif permission_sql:
        conditions.append(permission_sql)
        sql_params.extend(permission_params)
        account_conditions.append(permission_sql)
        account_params.extend(permission_params)

    department_values = _split_filter_values(query_params.department)
    for field, values in (
        ("department", department_values),
        ("placer_id", placer_values),
    ):
        if values:
            placeholders = ", ".join(["%s"] * len(values))
            scoped_conditions.append(f"{field} IN ({placeholders})")
            scoped_params.extend(values)

    operation_placers = await _operation_placer_ids()
    placers_by_account = await _feishu_placers_by_account() if operation_placers else {}
    allowed_departments = _personnel_spend_allowed_departments(
        current_user, department_values
    )
    # 部门可见性在 ad 层靠 department 列判断；转记行和账户层快照都没有该列，
    # 只能退回按投手本人的部门裁剪
    visible_placers = placer_values
    if placer_values and allowed_departments is not None:
        dept_by_placer = await _placer_departments(placer_values)
        visible_placers = [
            p for p in placer_values if dept_by_placer.get(p) in allowed_departments
        ]

    extra_sql, extra_params = "", []
    if operation_placers and scoped_conditions:
        placeholders = ", ".join(["%s"] * len(operation_placers))
        extra_sql = f"placer_id IN ({placeholders})"
        extra_params = list(operation_placers)
        if placer_values:
            # 下钻/筛选到具体投手时，只放行飞书登记在他名下、且部门可见的户
            accounts = _accounts_of_placers(placers_by_account, visible_placers)
            if accounts:
                placeholders = ", ".join(["%s"] * len(accounts))
                extra_sql += f" AND account_id IN ({placeholders})"
                extra_params.extend(accounts)
            else:
                extra_sql, extra_params = "", []
    if extra_sql:
        conditions.append(f"(({' AND '.join(scoped_conditions)}) OR ({extra_sql}))")
        sql_params.extend([*scoped_params, *extra_params])
    else:
        conditions.extend(scoped_conditions)
        sql_params.extend(scoped_params)

    if game_platform_values:
        placeholders = ", ".join(["%s"] * len(game_platform_values))
        conditions.append(f"game_platform IN ({placeholders})")
        sql_params.extend(game_platform_values)

    if account_id:
        conditions.append("account_id IN (%s, %s)")
        sql_params.extend([account_id, f"act_{account_id}"])
        account_conditions.append("account_id IN (%s, %s)")
        account_params.extend([account_id, f"act_{account_id}"])

    if attribute_values:
        # 账户类型只在 ERP 有，先取出这些类型的户再限定 Doris 的 account_id
        attribute_accounts = await _accounts_by_attribute(erp_db, attribute_values)
        if not attribute_accounts:
            return ApiResponse(
                data={"data": [], "total": 0, "level": query_params.level}
            )
        placeholders = ", ".join(["%s"] * len(attribute_accounts))
        conditions.append(f"account_id IN ({placeholders})")
        sql_params.extend(attribute_accounts)
        account_conditions.append(f"account_id IN ({placeholders})")
        account_params.extend(attribute_accounts)

    where_sql = " AND ".join(["level = 'ad'", *conditions])
    select_params: list[str] = []
    idle_sql, idle_params = "", []
    having_sql = ""
    metric_select = [f"{expr} AS {name}" for name, expr in _DRILL_METRICS.items()]
    if query_params.level == "personnel":
        # department 供转记时给 ERP 没覆盖的户做部门裁剪
        select_sql = (
            "placer_id AS id, placer_id AS name, account_id, "
            "ANY_VALUE(department) AS department"
        )
        group_sql = "placer_id, account_id"
    elif query_params.level == "account":
        select_sql = (
            "account_id AS id, ANY_VALUE(account_name) AS name, account_id"
        )
        if operation_placers:
            # 户里有挂在运营同事名下的消耗，就是在养户
            placeholders = ", ".join(["%s"] * len(operation_placers))
            select_sql += (
                f", MAX(CASE WHEN placer_id IN ({placeholders}) THEN 1 ELSE 0 END)"
                " AS nurturing"
            )
            select_params.extend(operation_placers)
        group_sql = "account_id"
        conditions.append("account_id IS NOT NULL")
        conditions.append("account_id != ''")
        where_sql = " AND ".join(["level = 'ad'", *conditions])
        # 区间内没消耗的户只有账户层快照，另捞一遍补成 0 花费的行。快照没有
        # game_platform，筛了项目就等于要求这个户跑过广告，此时不补。
        idle_scopes, idle_scope_params = [], []
        if visible_placers:
            placeholders = ", ".join(["%s"] * len(visible_placers))
            idle_scopes.append(f"placer_id IN ({placeholders})")
            idle_scope_params.extend(visible_placers)
        if extra_sql:
            idle_scopes.append(extra_sql)
            idle_scope_params.extend(extra_params)
        if idle_scopes and not game_platform_values:
            idle_conditions = [
                "level = 'account'",
                "date >= %s",
                "date < %s",
                _LIVE_ACCOUNT_COND,
                "account_id IS NOT NULL",
                "account_id != ''",
                "(" + " OR ".join(f"({scope})" for scope in idle_scopes) + ")",
                *account_conditions,
            ]
            idle_sql = f"""SELECT {select_sql}, 0 AS amount
FROM ad_daily_detail
WHERE {" AND ".join(idle_conditions)}
GROUP BY {group_sql}"""
            idle_params = [
                *select_params,
                start_date.strftime(DayFormat),
                end_date.strftime(DayFormat),
                *idle_scope_params,
                *account_params,
            ]
    elif query_params.level == "project":
        select_sql = ", ".join(
            [
                "game_platform AS id",
                "game_platform AS name",
                "account_id",
                *metric_select,
            ]
        )
        group_sql = "game_platform, account_id"
        where_sql += " AND game_platform IS NOT NULL AND game_platform != ''"
    else:
        # 列出区间内有花费的系列。只按最后一条快照是否在跑筛，会丢掉花完钱又暂停的
        # 系列，项目层的消耗就跟系列层加不上账。
        select_sql = ", ".join(
            [
                "campaign_id AS id",
                "ANY_VALUE(campaign_name) AS name",
                "account_id",
                *metric_select,
            ]
        )
        group_sql = "campaign_id, account_id"
        where_sql += " AND campaign_id IS NOT NULL AND campaign_id != ''"
        having_sql = "\nHAVING SUM(amount_spent) > 0"

    rows = await db.fetchall(
        f"""SELECT {select_sql}, ROUND(SUM(amount_spent), 2) AS amount
FROM ad_daily_detail
WHERE {where_sql}
GROUP BY {group_sql}{having_sql}""",
        [*select_params, *sql_params],
        as_dict=True,
    )
    if idle_sql:
        spent = {str(row["id"]) for row in rows}
        rows = [
            *rows,
            *[
                row
                for row in await db.fetchall(idle_sql, idle_params, as_dict=True)
                if str(row["id"]) not in spent
            ],
        ]
    if rows and query_params.level == "personnel":
        rows = _personnel_spend_reattribute(
            rows,
            placers_by_account,
            set(operation_placers),
            allowed_departments,
            placer_values,
        )
    elif rows and placer_id in operation_placers:
        rows = _drop_reattributed_accounts(rows, placers_by_account)
    if not rows:
        return ApiResponse(data={"data": [], "total": 0, "level": query_params.level})

    currency_by_account = await _personnel_spend_currencies(rows)
    items, amounts_by_id = _personnel_spend_items(rows, currency_by_account)
    if query_params.level == "personnel":
        placer_ids = [item["id"] for item in items]
        user_docs = await user_cols.user.find(
            {"real_name": {"$in": placer_ids}}, {"real_name": 1, "full_name": 1}
        ).to_list(length=None)
        name_by_placer = {
            str(doc["real_name"]): str(doc.get("full_name") or doc["real_name"])
            for doc in user_docs
            if doc.get("real_name")
        }
        for item in items:
            item["name"] = name_by_placer.get(item["id"], item["name"])
        _personnel_spend_sort(items, amounts_by_id)
    elif query_params.level == "account":
        # 账户属性跟广告面板同源(见 DetailQueryHandler._enrich_account_attributes)
        attribute_by_account = await _account_attributes(
            erp_db, [item["id"] for item in items]
        )
        nurturing = {str(row["id"]) for row in rows if row.get("nurturing")}
        for item in items:
            item["tag"] = _NURTURING_TAG if item["id"] in nurturing else None
            item["account_attribute"] = attribute_by_account.get(item["id"])
    else:
        # 项目/系列层都限定在单个账户内，一个 id 只有一行，指标直接按 id 贴回去
        row_by_id = {str(row["id"]): row for row in rows}
        for item in items:
            row = row_by_id.get(item["id"], {})
            for metric in _DRILL_METRICS:
                item[metric] = row.get(metric)

    return ApiResponse(
        data={"data": items, "total": len(items), "level": query_params.level}
    )


@router.get("/detail/{dimension}")
async def get_detail_by_dimension_v2(
    dimension: DimensionType,
    query_params: DashboardQueryParams = Depends(),
    db: AsyncMySQL = Depends(get_db),
    erp_db: AsyncMySQL = Depends(get_erp_db),
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    handler = DetailQueryHandler(dimension, query_params, db, erp_db, current_user)
    return await handler.execute()


DRILL_LEVEL_DIMS = {
    "campaign": DimensionType.CAMPAIGN_ID.value,
    "adset": DimensionType.AD_SET_ID.value,
    "ad": DimensionType.AD_ID.value,
}


@router.get("/drill/{level}", summary="单对象每半小时明细")
async def get_half_hour_drill(
    level: str,
    object_id: str,
    date: str,
    end_date: str | None = None,
    show_1d: bool = True,
    page: int = 1,
    page_size: int = 100,
    db: AsyncMySQL = Depends(get_db),
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    dim = DRILL_LEVEL_DIMS.get(level)
    if not dim:
        return ErrResponse(message=f"不支持的层级: {level}")
    builder = DIMENSION_BUILDERS[dim]
    # 列与面板小时模式完全一致; _build_hourly_columns 只依赖 ctx.show_1d
    columns = builder._build_hourly_columns(SimpleNamespace(show_1d=show_1d))
    select_fields = [f"{expr} AS {col}" for col, expr in columns.items()]
    # 00:00 槽是前一天的定稿快照(采集侧归属, 见 doris_writer), 窗口不做偏移
    end = (datetime.strptime(end_date or date, DayFormat) + timedelta(days=1)).strftime(
        DayFormat
    )
    page = max(page, 1)
    page_size = min(max(page_size, 1), 1000)
    where = f"level = '{level}' AND {dim} = %s AND date >= %s AND date < %s"
    params = [object_id, date, end]
    count_row = await db.fetchone(
        f"SELECT COUNT(*) AS total FROM ad_half_hour_detail WHERE {where}",
        params, as_dict=True,
    )
    total = count_row["total"] if count_row else 0
    sql = f"""SELECT {', '.join(select_fields)}
FROM ad_half_hour_detail
WHERE {where}
ORDER BY date DESC
LIMIT {page_size} OFFSET {(page - 1) * page_size}"""
    rows = await db.fetchall(sql, params, as_dict=True)
    columns.pop("id", None)
    return ApiResponse(
        data={"data": rows, "columns": list(columns.keys()), "total": total}
    )


class BmMapRequest(BaseModel):
    account_ids: List[str] = Field(..., description="账户 ID 列表(不带 act_ 前缀)")


@router.post("/bm-map", summary="按账户 ID 批量查所属 BM")
async def get_bm_map(
    request: BmMapRequest,
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse:
    """返回 {account_id: [{bm_id, bm_name}]}。fb_businesses.accounts.id 新老数据
    带/不带 act_ 前缀都有,两形态匹配后统一按去前缀的 id 归组。"""
    ids = [i for i in {i.strip() for i in request.account_ids} if i]
    if not ids:
        return ApiResponse(data={})

    both_forms = ids + [f"act_{i}" for i in ids]
    wanted = set(ids)
    result: dict[str, list[dict]] = {}
    seen: dict[str, set[str]] = {}
    async for doc in cols.fb_businesses.find(
        {"accounts.id": {"$in": both_forms}},
        {"business_id": 1, "business_name": 1, "accounts.id": 1},
    ):
        bm_id = doc.get("business_id")
        if not bm_id:
            continue
        for acc in doc.get("accounts") or []:
            acc_id = str(acc.get("id") or "").removeprefix("act_")
            if acc_id in wanted and bm_id not in seen.setdefault(acc_id, set()):
                seen[acc_id].add(bm_id)
                result.setdefault(acc_id, []).append(
                    {"bm_id": bm_id, "bm_name": doc.get("business_name", "")}
                )
    return ApiResponse(data=result)
