import asyncio
import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, List, Dict
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import skip_ip_auth, auth_current_user
from app.db.async_mysql import AsyncMySQL
from app.db.clients import get_db, get_erp_db, redis_cli
from app.db.mongo import cols
from app.model_type_defs.ad_sync_models import RunStatus
from app.model_type_defs.common_models import (
    ApiResponse,
    DayFormat,
    HourFormat,
    ErrResponse,
    SecondFormat,
)
from app.model_type_defs.user_models import UserModel, Roles
from app.utils.tg import send_tg_msg

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
china_tz = timezone(timedelta(hours=8))
REDIS_KEY_HOURLY = "adsservice:events.hourly_check"


class DashboardQueryParams(BaseModel):
    campaign_id: Optional[str] = Field(None)
    account_id: Optional[str] = Field(None)
    agent_line: Optional[str] = Field(None)
    ad_set_id: Optional[str] = Field(None)
    game_platform: Optional[str] = Field(None)
    department: Optional[str] = Field(None)
    ad_platform: Optional[str] = Field(None)
    ad_id: Optional[str] = Field(None)
    pixel_id: Optional[str] = Field(None)
    placer_id: Optional[str] = Field(None)
    channel: Optional[str] = Field(None, description="渠道ID，多个用逗号分隔")
    date: str = Field(None)
    is_newest: Optional[bool] = Field(True)
    show_1d: Optional[bool] = Field(True)
    tab_order: Optional[str] = Field(None)
    sort_by: Optional[str] = Field(None, description="排序字段（中文显示名称）")
    sort_order: Optional[str] = Field(
        "desc", description="排序方向: asc/desc，默认降序"
    )
    page: Optional[int] = Field(1, description="页码，从1开始", ge=1)
    page_size: Optional[int] = Field(100, description="每页条数", ge=10, le=100000)
    status: Optional[str] = Field(None, description="状态过滤，多个用逗号分隔")
    name: Optional[str] = Field(None, description="过滤某个层级的名称")
    id: Optional[str] = Field(None, description="过滤层级 ID，多个用逗号分隔")
    filters: Optional[str] = Field(
        None, description="数值筛选，格式 字段:gt|lt:值，多条用分号分隔"
    )

    def split(self) -> Dict[str, List[str] | str | bool]:
        result = {}
        for field_name, value in self.model_dump().items():
            if value is not None:
                result[field_name] = (
                    value.split(",") if isinstance(value, str) else value
                )
        return result


class DimensionType(str, Enum):
    DEPARTMENT = "department"
    GAME_PLATFORM = "game_platform"
    AD_PLATFORM = "ad_platform"
    AGENT_LINE = "agent_line"
    PLACER_ID = "placer_id"
    CHANNEL_ID = "channel"
    ACCOUNT_ID = "account_id"
    CAMPAIGN_ID = "campaign_id"
    AD_SET_ID = "ad_set_id"
    AD_ID = "ad_id"
    PIXEL_ID = "pixel_id"


dimension_list = [dim.value for dim in DimensionType]
newest_dim = dimension_list[: dimension_list.index("account_id") + 1]

# 可排序字段映射字典
SORTABLE_FIELDS = {
    "aggregated": {
        # 基础指标
        "花费金额": "SUM(amount_spent)",
        "覆盖人数": "SUM(reach)",
        "展示次数": "SUM(impressions)",
        "点击数": "SUM(clicks_all)",
        "点击率": "SUM(clicks_all) * 100.0 / SUM(impressions)",
        "点击成本": "SUM(amount_spent)/SUM(clicks_all)",
        "链接点击数": "SUM(inline_link_clicks)",
        "落地页浏览": "SUM(landing_page_view)",
        "落地页成本": "SUM(amount_spent)/SUM(landing_page_view)",
        "去重链接点击数": "SUM(unique_inline_link_clicks)",
        "去重点击成本": "SUM(amount_spent)/SUM(unique_inline_link_clicks)",
        "千展": "SUM(amount_spent)/SUM(impressions)*1000",
        # 转化指标
        "安装数": "SUM(app_installs)",
        "注册数": "SUM(complete_registration)",
        "注册转化率": "SUM(complete_registration)/SUM(clicks_all)*100",
        "注册成本": "SUM(amount_spent)/SUM(complete_registration)",
        # 订阅指标
        "订阅数": "SUM(subscribe_website)",
        "订阅率": "SUM(subscribe_website)/SUM(complete_registration)*100",
        "订阅成本": "SUM(amount_spent)/SUM(subscribe_website)",
        "订阅价值": "SUM(subscribe_website_values)",
        # 购物指标
        "购物数": "SUM(purchases)",
        "购物率": "SUM(purchases)/SUM(complete_registration)*100",
        "购物成本": "SUM(amount_spent)/SUM(purchases)",
        "购物价值": "SUM(purchases_value)",
        "购物roas": "SUM(purchases_value)/SUM(amount_spent)",
        # 其他
        "频次": "AVG(frequency)",
        "3d频次": "AVG(frequency_3d)",
        "5d频次": "AVG(frequency_5d)",
        "7d频次": "AVG(frequency_7d)",
        "预算": "SUM(budget)/100",
        "户余额": "ANY_VALUE(balance)",
        "户限额": "ANY_VALUE(spend_cap)",
        "单日限额": "ANY_VALUE(account_dsl)",
        "对话数": "SUM(messaging_conversation_started)",
        "对话成本": "SUM(amount_spent)/SUM(messaging_conversation_started)",
        # 1d指标
        "1d安装数": "SUM(app_installs_1dclick)",
        "1d注册数": "SUM(register_1dclick)",
        "1d注册成本": "SUM(amount_spent)/SUM(register_1dclick)",
        "1d订阅数": "SUM(subscriptions_1dclick)",
        "1d订阅成本": "SUM(amount_spent)/SUM(subscriptions_1dclick)",
        "1d订阅价值": "SUM(subscriptions_value_1dclick)",
        "1d购物数": "SUM(purchases_1dclick)",
        "1d购物成本": "SUM(amount_spent)/SUM(purchases_1dclick)",
        "1d购物价值": "SUM(purchase_values_1dclick)",
        "1d购物roas": "SUM(purchase_values_1dclick)/SUM(amount_spent)",
        # BI指标
        "bi注册数": "SUM(bi_registrations)",
        "bi首充人数": "SUM(bi_first_recharge_users)",
        "bi首充金额": "SUM(bi_first_recharge_amount)",
        "bi首充成本": "SUM(amount_spent)/SUM(bi_first_recharge_users)",
        "bi首次roas": "SUM(bi_first_recharge_amount)/16000/SUM(amount_spent)",
        "bi首次arppu": "SUM(bi_first_recharge_amount)/16000/SUM(bi_first_recharge_users)",
        "bi注册成本": "SUM(amount_spent)/SUM(bi_registrations)",
    },
    "hourly": {
        # 基础指标
        "花费金额": "amount_spent",
        "覆盖人数": "reach",
        "展示次数": "impressions",
        "点击数": "clicks_all",
        "点击率": "clicks_all * 100.0 / impressions",
        "点击成本": "amount_spent/clicks_all",
        "链接点击数": "inline_link_clicks",
        "落地页浏览": "landing_page_view",
        "落地页成本": "amount_spent/landing_page_view",
        "去重链接点击数": "unique_inline_link_clicks",
        "去重点击成本": "amount_spent/unique_inline_link_clicks",
        "千展": "cpm",
        # 转化指标
        "安装数": "app_installs",
        "注册数": "complete_registration",
        "注册转化率": "complete_registration/clicks_all*100",
        "注册成本": "amount_spent/complete_registration",
        # 订阅指标
        "订阅数": "subscribe_website",
        "订阅率": "subscribe_website/complete_registration*100",
        "订阅成本": "amount_spent/subscribe_website",
        "订阅价值": "subscribe_website_values",
        # 购物指标
        "购物数": "purchases",
        "购物率": "purchases/complete_registration*100",
        "购物成本": "amount_spent/purchases",
        "购物价值": "purchases_value",
        "购物roas": "purchases_value/amount_spent",
        # 其他
        "频次": "frequency",
        "3d频次": "frequency_3d",
        "5d频次": "frequency_5d",
        "7d频次": "frequency_7d",
        "对话数": "messaging_conversation_started",
        "对话成本": "amount_spent/messaging_conversation_started",
        "预算": "budget/100",
        "户余额": "balance",
        "户限额": "spend_cap",
        "单日限额": "account_dsl",
        # 1d指标
        "1d安装数": "app_installs_1dclick",
        "1d注册数": "register_1dclick",
        "1d注册成本": "amount_spent/register_1dclick",
        "1d订阅数": "subscriptions_1dclick",
        "1d订阅成本": "amount_spent/subscriptions_1dclick",
        "1d订阅价值": "subscriptions_value_1dclick",
        "1d购物数": "purchases_1dclick",
        "1d购物成本": "amount_spent/purchases_1dclick",
        "1d购物价值": "purchase_values_1dclick",
        "1d购物roas": "purchase_values_1dclick/amount_spent",
    },
}


def validate_and_build_order_clause(
    sort_by: Optional[str],
    sort_order: Optional[str],
    is_hourly: bool = False,
) -> str:
    """
    验证排序参数并构建 ORDER BY 子句

    Args:
        sort_by: 排序字段（中文显示名称）
        sort_order: 排序方向 ('asc' 或 'desc')
        is_hourly: 是否为小时详情查询

    Returns:
        ORDER BY 子句字符串

    Raises:
        ValueError: 如果参数无效
    """
    # 验证 sort_order
    if sort_order and sort_order.lower() not in ["asc", "desc"]:
        raise ValueError(f"无效的 sort_order: {sort_order}，必须是 'asc' 或 'desc'")

    sort_order_upper = (sort_order or "desc").upper()

    # 选择对应的白名单
    whitelist = (
        SORTABLE_FIELDS["hourly"] if is_hourly else SORTABLE_FIELDS["aggregated"]
    )

    # 默认排序：按花费金额降序
    if not sort_by:
        sort_expression = whitelist["花费金额"]
        return f"ORDER BY {sort_expression} {sort_order_upper} NULLS LAST"

    # 验证 sort_by 是否在白名单中
    if sort_by not in whitelist:
        raise ValueError(
            f"无效的排序字段: {sort_by}。允许的字段: {', '.join(whitelist.keys())}"
        )

    # 获取排序表达式
    sort_expression = whitelist[sort_by]

    # 构建 ORDER BY 子句
    return f"ORDER BY {sort_expression} {sort_order_upper} NULLS LAST"


FILTER_OPS = {"gt": ">", "lt": "<"}


def parse_metric_filters(raw: Optional[str]) -> List[dict]:
    """解析数值筛选参数: '字段:gt:100;字段:lt:5' -> [{field, op, value}]"""
    if not raw:
        return []
    filters = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        pieces = part.split(":", 2)
        if len(pieces) != 3:
            raise ValueError(f"无效的筛选条件: {part}，格式应为 字段:gt|lt:值")
        filters.append({"field": pieces[0], "op": pieces[1], "value": pieces[2]})
    return filters


def build_filter_conditions(filters: List[dict], is_hourly: bool = False) -> List[str]:
    """数值筛选条件，字段复用排序白名单; 值经 float 校验后内联，无注入风险"""
    whitelist = (
        SORTABLE_FIELDS["hourly"] if is_hourly else SORTABLE_FIELDS["aggregated"]
    )
    conditions = []
    for f in filters:
        field, op = f["field"], f["op"]
        if field not in whitelist:
            raise ValueError(f"无效的筛选字段: {field}")
        if op not in FILTER_OPS:
            raise ValueError(f"无效的筛选操作: {op}，必须是 gt 或 lt")
        try:
            value = float(f["value"])
        except (TypeError, ValueError):
            raise ValueError(f"无效的筛选值: {f['value']}")
        expr = whitelist[field]
        if field.endswith("成本"):
            # 成本类指标都是 花费/转化数, 转化为 0 时除法结果为 NULL 导致比较永假。
            # 改写为乘法: 花费 op 值*转化数, 与除法等价且无 NULL——
            # 有花费无转化命中"大于"(成本无穷大), 不命中"小于"; 0花费0转化两者都不命中
            numerator, denominator = expr.split("/", 1)
            conditions.append(
                f"({numerator}) {FILTER_OPS[op]} {value} * COALESCE({denominator}, 0)"
            )
        else:
            conditions.append(f"({expr}) {FILTER_OPS[op]} {value}")
    return conditions


def generate_dimension_subset(target_field, tabs: List = None):
    tmp = tabs if tabs else dimension_list
    target_index = tmp.index(target_field)
    return set(tmp[:target_index])


async def get_channel_account_mapping(erp_db: AsyncMySQL) -> Dict[str, List[str]]:
    """
    从 ERP 获取渠道与账户的映射关系

    Returns:
        Dict[channel_id, List[account_ids]] - 渠道ID到账户ID列表的映射（账户ID带act_前缀）
    """
    sql = """
    SELECT ca.channel_id, ca.fb_account_id
    FROM fbad_channel_account ca
    """
    results = await erp_db.fetchall(sql, as_dict=True)

    mapping = {}
    for row in results:
        channel_id = str(row["channel_id"])
        account_id = str(row["fb_account_id"])
        if channel_id not in mapping:
            mapping[channel_id] = []
        mapping[channel_id].append(account_id)

    return mapping


class DateSubmitData(BaseModel):
    date: str
    china_date: Optional[str] = None
    agent_line: str
    game_platform: str
    # timezone_name: Optional[str] = None
    registrations: Optional[int] = None
    first_recharge_amount: Optional[int] = None
    first_recharge_users: Optional[int] = None


async def send_tg(messages: List[dict]):
    data = [message for message in messages if message.get("is_send", False)]
    if not data:
        return
    data.sort(key=lambda x: (x.get("type", ""), x.get("level", "")))
    ext_infos = [
        message.get("ext_info", "") for message in data if message.get("ext_info")
    ]
    if ext_infos:
        combined_message = "\n".join(ext_infos)
        await send_tg_msg(combined_message, -4919777167)


async def start_task(data: DateSubmitData):
    date = format_date(data.date)
    payload = {
        "date": date.strftime(HourFormat),
        "game_platform": data.game_platform,
        "agent_line": data.agent_line,
        "registrations": data.registrations,
        "first_recharge_amount": data.first_recharge_amount,
        "first_recharge_users": data.first_recharge_users,
    }
    await redis_cli.publish(REDIS_KEY_HOURLY, str(payload))


def format_date(date):
    return datetime.strptime(date, HourFormat)


async def generate_grouped_sql(
    db,
    date,
    game_platform,
    agent_line,  # timezone_name=None
) -> dict:
    group_by_fields = [
        "date",
        "game_platform",
        "ad_platform",
        "agent_line",
        "china_date",
        # "timezone_name",
        "department",
    ]
    sum_fields = [
        "amount_spent",
        "impressions",
        "clicks_all",
        "clicks_unique",
        "reach",
        "app_installs",
        "purchases",
        "purchases_value",
        "complete_registration",
        "subscribe_website",
        "subscribe_website_values",
        "lead",
        "inline_link_clicks",
        "unique_inline_link_clicks",
    ]
    sum_expressions = ", ".join([f"SUM({field}) AS {field}" for field in sum_fields])

    sql_query = f"""
    SELECT {", ".join(group_by_fields)}, {sum_expressions}
    FROM ad_hourly_detail WHERE date=%s and game_platform=%s
    and agent_line=%s and level='campaign'
    GROUP BY {", ".join(group_by_fields)};
    """
    data = await db.fetchone(sql_query, (date, game_platform, agent_line), as_dict=True)
    return data if data else {}


@router.post("/report/hourly_submit")
@skip_ip_auth("172.*", "127.0.0.1")
async def hourly_submit(
    data: DateSubmitData,
    db: AsyncMySQL = Depends(get_db),
):
    if data.china_date:
        # date 到半点后一个整点有 :00/:30 两次 sub-run,按整点前缀范围取最新一次的状态
        hour_dt = datetime.strptime(data.china_date, HourFormat)
        history = await cols.ad_sync_history.find_one(
            {
                "date": {
                    "$gte": hour_dt.strftime(HourFormat),
                    "$lt": (hour_dt + timedelta(hours=1)).strftime(HourFormat),
                },
                "agent_lines": data.agent_line,
            },
            {"run_status": 1, "_id": 0},
            sort=[("create_time", -1)],
        )
        res = history["run_status"] if history else None
        if res != RunStatus.COMPLETED:
            if res is None:
                res = "没有"
            return ErrResponse(
                message=f"填写失败,当前中国日期{data.china_date}数据同步状态{res}"
            )
    if not (
        data.registrations is None
        and data.first_recharge_amount is None
        and data.first_recharge_users is None
    ):
        result = {
            "bi_registrations": data.registrations,
            "bi_first_recharge_amount": data.first_recharge_amount,
            "bi_first_recharge_users": data.first_recharge_users,
        }
        grouped_data = await generate_grouped_sql(
            db, data.date, data.game_platform, data.agent_line
        )
        result.update(grouped_data)
        if not grouped_data:
            return ErrResponse(message="该时间暂无数据同步")
        sql, params = db.generate_insert_sql("ad_hourly_summary", result)
        await db.execute(sql, params)
    await start_task(data)
    return ApiResponse()


class BiHistoryQueryParams(BaseModel):
    date: str = Field(..., description="日期，格式：YYYY-MM-DD")
    agent_line: Optional[str] = Field(None, description="代理线")
    game_platform: Optional[str] = Field(None, description="游戏平台")


@router.get("/bi_history")
async def get_bi_history(
    query: BiHistoryQueryParams = Depends(),
    db: AsyncMySQL = Depends(get_db),
) -> ApiResponse:
    start_datetime = (
        datetime.strptime(query.date, DayFormat) - timedelta(days=1)
    ).strftime(DayFormat)
    end_datetime = (
        datetime.strptime(query.date, DayFormat) + timedelta(days=1)
    ).strftime(DayFormat)
    sql = f"""
    SELECT 
        date,
        game_platform,
        ad_platform,
        agent_line,
        amount_spent,
        bi_registrations,
        bi_first_recharge_amount,
        bi_first_recharge_users,
        impressions,
        clicks_all,
        amount_spent/bi_first_recharge_users as bi_first_recharge_cost,
        bi_first_recharge_amount/16000/amount_spent as bi_first_roas,
        bi_first_recharge_amount/16000/bi_first_recharge_users as bi_first_arppu,
        amount_spent/bi_registrations as bi_registration_cost
    FROM ad_hourly_summary
    WHERE date BETWEEN '{start_datetime}' AND '{end_datetime}' AND agent_line = %s AND game_platform = %s
    ORDER BY date DESC
    """
    result = await db.fetchall(
        sql, [query.agent_line, query.game_platform], as_dict=True
    )
    for item in result:
        for key, value in item.items():
            if isinstance(value, float):
                item[key] = round(value, 2)
    return ApiResponse(data=result)


@router.get("/operation_history")
async def get_operation_history(
    date: str,
    agent_line: Optional[str] = None,
    game_platform: Optional[str] = None,
) -> ApiResponse:
    start_datetime = f"{(datetime.strptime(date, DayFormat) - timedelta(days=1)).strftime(DayFormat)} 00:00:00"
    end_datetime = f"{(datetime.strptime(date, DayFormat) + timedelta(days=1)).strftime(DayFormat)} 00:00:00"

    query = {"start_time": {"$gte": start_datetime, "$lte": end_datetime}}
    if agent_line:
        query["dev.agent_lines"] = {"$in": [agent_line]}
    if game_platform:
        query["dev.game_platform"] = game_platform
    cursor = cols.ad_operations.find(
        query,
        projection={
            "dev.access_token": 0,
            "dev.app_secret": 0,
            "dev.dev_id": 0,
            "dev.proxy": 0,
            "dev.db_id": 0,
            "_id": 0,
        },
    ).sort("start_time", -1)
    result = []
    async for doc in cursor:
        result.append(doc)
        if doc["data"]["time"]:
            doc["data"]["time"] = (
                datetime.fromtimestamp(doc["data"]["time"], ZoneInfo("Asia/Shanghai"))
                .strftime(SecondFormat)
            )
    return ApiResponse(data=result)


class ColumnSettingUpsert(BaseModel):
    tab: str
    visible_columns: Optional[List[str]] = None
    column_order: Optional[List[str]] = None


@router.get("/column-settings")
async def get_column_settings(
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse:
    """获取当前用户所有 tab 的自定义列配置"""
    doc = await cols.dashboard_column_settings.find_one(
        {"user_id": current_user.id}, {"_id": 0, "user_id": 0}
    )
    return ApiResponse(data=doc)


@router.put("/column-settings")
async def upsert_column_settings(
    body: ColumnSettingUpsert,
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse:
    """保存某个 tab 的自定义列"""
    update_fields = {}
    if body.visible_columns is not None:
        update_fields[f"{body.tab}.visible_columns"] = body.visible_columns
    if body.column_order is not None:
        update_fields[f"{body.tab}.column_order"] = body.column_order
    if update_fields:
        await cols.dashboard_column_settings.update_one(
            {"user_id": current_user.id},
            {"$set": update_fields},
            upsert=True,
        )
    return ApiResponse()
