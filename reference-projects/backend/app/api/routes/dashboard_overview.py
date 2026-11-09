"""数据看板概览类接口 (项目 / 投手 / 渠道商 / 分时趋势)。
维度数据从 Doris (ad_daily_detail / ad_hourly_detail, level='campaign') 聚合;
地区/投手/渠道等业务属性来自 Mongo platform_config / agent_line_config / user 与 Doris fb_ad_channel。
"""

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from pymongo import ReturnDocument

from app.core.security import auth_current_user
from app.db.async_mysql import AsyncMySQL
from app.db.clients import get_db
from app.db.mongo import cols, user_cols, tz_cst
from app.model_type_defs.common_models import (
    ApiResponse,
    ErrResponse,
    DayFormat,
    SecondFormat,
)
from app.model_type_defs.user_models import UserModel, DEPT_ALL

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ═══════════════════════════════════════════════════════════════════════════
# 公共辅助
# ═══════════════════════════════════════════════════════════════════════════


def _split(value: Optional[str]) -> Optional[list[str]]:
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()] or None


async def _dept_where(current_user: UserModel) -> tuple[str, list]:
    """部门可见性过滤, 与 dashboard 明细路由保持一致。"""
    depts = current_user.departments or []
    if DEPT_ALL in depts:
        return "", []
    if depts:
        placeholders = ", ".join(["%s"] * len(depts))
        return f"AND department IN ({placeholders})", list(depts)
    real_name = current_user.real_name
    docs = await cols.personal_accounts.find(
        {"user_name": real_name, "status": True}, {"accounts.id": 1}
    ).to_list(length=None)
    account_ids = [
        acc["id"] for d in docs for acc in d.get("accounts", []) if acc.get("id")
    ]
    if account_ids:
        placeholders = ", ".join(["%s"] * len(account_ids))
        return f"AND (placer_id = %s OR account_id IN ({placeholders}))", [
            real_name,
            *account_ids,
        ]
    return "AND (placer_id = %s)", [real_name]


def _vs7(cur: Optional[float], prev: Optional[float]) -> Optional[str]:
    """环比, 带 +/- 号; 无基准返回 None。"""
    if not prev:
        return None
    pct = (float(cur or 0) - float(prev)) / float(prev) * 100
    return f"{'+' if pct >= 0 else '-'}{abs(round(pct, 2))}%"


def _dept_filter_where(department: Optional[list[str]]) -> tuple[str, list]:
    """用户所选部门筛选 (Doris department 列), 叠加在 _dept_where 可见性之上。"""
    if not department:
        return "", []
    placeholders = ", ".join(["%s"] * len(department))
    return f"AND department IN ({placeholders})", list(department)


def _placer_where(placer: Optional[str]) -> tuple[str, list]:
    """选了投手时只统计该投手的消耗 (placer_id = 优化师 real_name); 同项目可能还有别的投手在投。"""
    placers = _split(placer)
    if not placers:
        return "", []
    placeholders = ", ".join(["%s"] * len(placers))
    return f"AND placer_id IN ({placeholders})", list(placers)


async def _channel_where(channel: Optional[str], db: AsyncMySQL) -> tuple[str, list]:
    """渠道 id → 渠道下账户 → AND account_id IN (...); 兼容账户号带/不带 act_ 前缀。
    选了渠道但渠道无账户时返回恒假条件 (结果为空)。"""
    ids = _split(channel)
    if not ids:
        return "", []
    placeholders = ", ".join(["%s"] * len(ids))
    rows = await db.fetchall(
        "SELECT json_extract(account_ids_json, '$[*].account_id') AS account_ids "
        f"FROM fb_ad_channel WHERE id IN ({placeholders})",
        ids,
        as_dict=True,
    )
    accounts = {a for r in rows for a in _coerce_ids(r.get("account_ids"))}
    if not accounts:
        return "AND 1 = 0", []
    variants = [v for a in accounts for v in (a, f"act_{a}")]
    ph = ", ".join(["%s"] * len(variants))
    return f"AND account_id IN ({ph})", variants


# ═══════════════════════════════════════════════════════════════════════════
# 筛选项 (项目 / 地区 / 渠道商 / 投手)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/filter_options")
async def filter_options(
    db: AsyncMySQL = Depends(get_db),
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse:
    projects = sorted(p for p in await cols.platform_config.distinct("_id") if p)
    regions = sorted(
        r for r in await cols.platform_config.distinct("target_region") if r
    )

    users = await user_cols.user.find(
        {"roles": {
            "$in": ["operator", "operator_leader"]
        }},
        {"real_name": 1, "full_name": 1},
    ).to_list(length=None)
    seen, placers = set(), []
    for u in users:
        rn = u.get("real_name")
        if rn and rn not in seen:
            seen.add(rn)
            placers.append({"value": rn, "label": u.get("full_name") or rn})

    departments = sorted(
        d
        for d in await user_cols.user.distinct(
            "department",
            {"roles": ["operator"]},
        )
        if d
    )

    ch_rows = await db.fetchall(
        "SELECT id, channel_name FROM fb_ad_channel", as_dict=True
    )
    channels = [
        {"value": str(r["id"]), "label": r["channel_name"]}
        for r in ch_rows
        if r.get("channel_name")
    ]

    return ApiResponse(
        data={
            "projects": projects,
            "regions": regions,
            "placers": placers,
            "channels": channels,
            "departments": departments,
        }
    )


@router.get("/filter_search")
async def filter_search(
    type: str,
    q: Optional[str] = None,
    limit: int = 50,
    db: AsyncMySQL = Depends(get_db),
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    """筛选项前缀搜索 (项目/地区/投手/渠道商), 给筛选下拉框按需加载用。
    项目/地区/投手走 Mongo 前缀匹配, 渠道商走 Doris fb_ad_channel。"""
    kw = (q or "").strip()
    rx = {"$regex": f"^{re.escape(kw)}", "$options": "i"} if kw else None

    if type == "project":
        docs = (
            await cols.platform_config.find({"_id": rx} if rx else {}, {"_id": 1})
            .sort("_id", 1)
            .limit(limit)
            .to_list(length=limit)
        )
        return ApiResponse(
            data=[{"label": d["_id"], "value": d["_id"]} for d in docs if d.get("_id")]
        )
    if type == "region":
        # target_region 是数组, 需 unwind 后对单个值前缀匹配再去重
        pipeline: list = [{"$unwind": "$target_region"}]
        if rx:
            pipeline.append({"$match": {"target_region": rx}})
        pipeline += [
            {"$group": {"_id": "$target_region"}},
            {"$sort": {"_id": 1}},
            {"$limit": limit},
        ]
        docs = await cols.platform_config.aggregate(pipeline).to_list(length=limit)
        return ApiResponse(
            data=[{"label": d["_id"], "value": d["_id"]} for d in docs if d.get("_id")]
        )
    if type == "placer":
        query: dict = {"roles": "operator"}
        if rx:
            query["$or"] = [{"full_name": rx}, {"real_name": rx}]
        users = (
            await user_cols.user.find(query, {"real_name": 1, "full_name": 1})
            .limit(limit)
            .to_list(length=limit)
        )
        seen, placers = set(), []
        for u in users:
            rn = u.get("real_name")
            if not rn or rn in seen:
                continue
            seen.add(rn)
            placers.append({"value": rn, "label": u.get("full_name") or rn})
        return ApiResponse(data=placers)
    if type == "channel":
        # 渠道商来自 Doris fb_ad_channel, 按 channel_name 前缀匹配, 返回 id/名称
        if kw:
            ch_rows = await db.fetchall(
                "SELECT id, channel_name FROM fb_ad_channel "
                "WHERE channel_name LIKE %s ORDER BY channel_name LIMIT %s",
                [f"{kw}%", limit],
                as_dict=True,
            )
        else:
            ch_rows = await db.fetchall(
                "SELECT id, channel_name FROM fb_ad_channel ORDER BY channel_name LIMIT %s",
                [limit],
                as_dict=True,
            )
        return ApiResponse(
            data=[
                {"label": r["channel_name"], "value": str(r["id"])}
                for r in ch_rows
                if r.get("channel_name")
            ]
        )
    return ErrResponse(message="type 应为 project/region/placer/channel")


# ═══════════════════════════════════════════════════════════════════════════
# 项目维度
# ═══════════════════════════════════════════════════════════════════════════

PROJECT_COLUMNS = [
    "项目",
    "地区",
    "投手数量",
    "消耗",
    "vs7日",
    "roas",
    "cpa",
    "注册",
    "付费成本",
    "订阅成本",
    "消耗趋势",
]
PROJECT_SORT_KEYS = {
    "投手数量",
    "消耗",
    "vs7日",
    "roas",
    "cpa",
    "注册",
    "付费成本",
    "订阅成本",
}


async def _platforms_by_region(regions: list[str]) -> set[str]:
    docs = await cols.platform_config.find(
        {"target_region": {"$in": regions}}, {"_id": 1}
    ).to_list(length=None)
    return {d["_id"] for d in docs}


async def _platforms_by_placer(placers: list[str]) -> set[str]:
    """投手(优化师 real_name) -> 其代理线 -> 关联的项目。"""
    line_docs = await cols.agent_line_config.find(
        {"optimizer": {"$in": placers}}, {"_id": 1}
    ).to_list(length=None)
    line_ids = [d["_id"] for d in line_docs]
    if not line_ids:
        return set()
    plat_docs = await cols.platform_config.find(
        {"agent_lines": {"$in": line_ids}}, {"_id": 1}
    ).to_list(length=None)
    return {d["_id"] for d in plat_docs}


async def _resolve_gp_set(
    game_platform: Optional[str], region: Optional[str], placer: Optional[str]
) -> Optional[set[str]]:
    """筛选项 项目/地区/投手 → 项目集合交集; None=未筛选, 空集=无匹配。"""
    filter_sets = []
    if gp_filter := _split(game_platform):
        filter_sets.append(set(gp_filter))
    if region_filter := _split(region):
        filter_sets.append(await _platforms_by_region(region_filter))
    if placer_filter := _split(placer):
        filter_sets.append(await _platforms_by_placer(placer_filter))
    if not filter_sets:
        return None
    return set.intersection(*filter_sets)


def _gp_where(gp_set: Optional[set[str]]) -> tuple[str, list]:
    if gp_set is None:
        return "", []
    placeholders = ", ".join(["%s"] * len(gp_set))
    return f"AND game_platform IN ({placeholders})", list(gp_set)


@router.get("/project_overview")
async def project_overview(
    date: Optional[str] = None,
    game_platform: Optional[str] = None,
    region: Optional[str] = None,
    placer: Optional[str] = None,
    department: Optional[list[str]] = Query(None),
    channel: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 100,
    db: AsyncMySQL = Depends(get_db),
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    day = (date or datetime.now().strftime(DayFormat)).strip()
    try:
        day_dt = datetime.strptime(day, DayFormat)
    except ValueError:
        return ErrResponse(message="date 格式应为单天 'YYYY-MM-DD'")
    prev_day = (day_dt - timedelta(days=7)).strftime(DayFormat)
    # 折线图: 含当天在内的最近 7 天 (升序)
    week_dates = [
        (day_dt - timedelta(days=i)).strftime(DayFormat) for i in range(6, -1, -1)
    ]

    def empty():
        return ApiResponse(
            data={
                "data": [],
                "columns": PROJECT_COLUMNS,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": 0,
                    "total_pages": 0,
                },
            }
        )

    # 项目筛选集合: 项目/地区/投手 取交集
    gp_set = await _resolve_gp_set(game_platform, region, placer)
    if gp_set is not None and not gp_set:
        return empty()

    dept_sql, dept_params = await _dept_where(current_user)
    deptf_sql, deptf_params = _dept_filter_where(department)
    gp_sql, gp_params = _gp_where(gp_set)
    ch_sql, ch_params = await _channel_where(channel, db)
    placer_sql, placer_params = _placer_where(placer)
    extra_sql = f"{dept_sql} {deptf_sql} {gp_sql} {ch_sql} {placer_sql}"
    extra_params = [*dept_params, *deptf_params, *gp_params, *ch_params, *placer_params]

    metrics_sql = f"""SELECT
    game_platform AS id,
    ROUND(SUM(amount_spent),2) AS 消耗,
    ROUND(SUM(purchases_value)/NULLIF(SUM(amount_spent),0),2) AS roas,
    ROUND(SUM(amount_spent)/NULLIF(SUM(complete_registration),0),2) AS cpa,
    SUM(complete_registration) AS 注册,
    ROUND(SUM(amount_spent)/NULLIF(SUM(purchases),0),2) AS 付费成本,
    ROUND(SUM(amount_spent)/NULLIF(SUM(subscribe_website),0),2) AS 订阅成本
FROM ad_daily_detail
WHERE level = 'campaign' AND department IS NOT NULL AND date = %s {extra_sql}
GROUP BY game_platform"""

    # 单次区间查询同时支撑: vs7日 基准(prev_day) 与 折线图(最近7天)
    window_sql = f"""SELECT game_platform AS id, DATE_FORMAT(date, '%%Y-%%m-%%d') AS d, ROUND(SUM(amount_spent),2) AS spend
FROM ad_daily_detail
WHERE level = 'campaign' AND department IS NOT NULL AND date BETWEEN %s AND %s {extra_sql}
GROUP BY game_platform, date"""

    cur_rows = await db.fetchall(metrics_sql, [day, *extra_params], as_dict=True)
    cur_rows = [r for r in cur_rows if (r["消耗"] or 0) > 0]
    if not cur_rows:
        return empty()
    window_rows = await db.fetchall(
        window_sql, [prev_day, day, *extra_params], as_dict=True
    )
    spend_by_gp_date: dict = {}
    for wr in window_rows:
        spend_by_gp_date.setdefault(wr["id"], {})[wr["d"]] = wr["spend"]

    # 地区 + 投手数量
    result_gps = [r["id"] for r in cur_rows]
    plat_docs = await cols.platform_config.find(
        {"_id": {"$in": result_gps}}, {"target_region": 1, "agent_lines": 1}
    ).to_list(length=None)
    plat_map = {d["_id"]: d for d in plat_docs}
    all_line_ids = list({lid for d in plat_docs for lid in d.get("agent_lines", [])})
    line_opt: dict = {}
    if all_line_ids:
        line_docs = await cols.agent_line_config.find(
            {"_id": {"$in": all_line_ids}}, {"optimizer": 1}
        ).to_list(length=None)
        line_opt = {d["_id"]: d.get("optimizer") for d in line_docs}

    rows = []
    for r in cur_rows:
        gp = r["id"]
        doc = plat_map.get(gp, {})
        regions = doc.get("target_region") or []
        optimizers = {line_opt.get(lid) for lid in doc.get("agent_lines", [])}
        optimizers.discard(None)
        gp_spend = spend_by_gp_date.get(gp, {})
        rows.append(
            {
                "项目": gp,
                "地区": ", ".join(regions) if regions else None,
                "投手数量": len(optimizers),
                "消耗": r["消耗"],
                "vs7日": _vs7(r["消耗"], gp_spend.get(prev_day)),
                "roas": r["roas"],
                "cpa": r["cpa"],
                "注册": r["注册"],
                "付费成本": r["付费成本"],
                "订阅成本": r["订阅成本"],
                "消耗趋势": [
                    {"date": d, "消耗": gp_spend.get(d, 0)} for d in week_dates
                ],
            }
        )

    sort_key = sort_by if sort_by in PROJECT_SORT_KEYS else "消耗"

    def _sval(row):
        v = row.get(sort_key)
        if sort_key == "vs7日":
            return float(v.rstrip("%")) if v else 0.0
        return v if isinstance(v, (int, float)) else 0.0

    rows.sort(key=_sval, reverse=(sort_order != "asc"))

    rows = [r for r in rows if r["项目"]]

    total = len(rows)
    start_idx = (page - 1) * page_size
    page_rows = rows[start_idx : start_idx + page_size]

    return ApiResponse(
        data={
            "data": page_rows,
            "columns": PROJECT_COLUMNS,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
            },
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
# 投手维度 (placer_id = 优化师 real_name)
# ═══════════════════════════════════════════════════════════════════════════

PLACER_COLUMNS = [
    "投手",
    "组",
    "在投代理线",
    "消耗",
    "ROAS",
    "CPI",
    "付费成本",
    "订阅成本",
]
PLACER_SORT_KEYS = {"在投代理线", "消耗", "ROAS", "CPI", "付费成本", "订阅成本"}
LEADERBOARD_COLUMNS = ["排名", "投手", "组", "消耗", "同比上月"]
TEAM_LEADERBOARD_COLUMNS = ["排名", "组", "消耗", "同比上月"]


async def _placers_in_departments(departments: list[str]) -> set[str]:
    users = await user_cols.user.find(
        {"department": {"$in": departments}}, {"real_name": 1}
    ).to_list(length=None)
    return {u["real_name"] for u in users if u.get("real_name")}


async def _user_map(real_names: list[str]) -> dict:
    """real_name -> {full_name, department, roles}"""
    if not real_names:
        return {}
    users = await user_cols.user.find(
        {"real_name": {"$in": real_names}},
        {"real_name": 1, "full_name": 1, "department": 1, "roles": 1},
    ).to_list(length=None)
    return {u["real_name"]: u for u in users}


async def _resolve_placer_set(
    placer: Optional[str], department: Optional[list[str]]
) -> Optional[set]:
    """按投手/组筛选取交集; 无筛选返回 None(不限制)。"""
    filter_sets = []
    if placer_filter := _split(placer):
        filter_sets.append(set(placer_filter))
    if department:
        filter_sets.append(await _placers_in_departments(department))
    if not filter_sets:
        return None
    return set.intersection(*filter_sets)


@router.get("/placer_overview")
async def placer_overview(
    date: Optional[str] = None,
    game_platform: Optional[str] = None,
    region: Optional[str] = None,
    department: Optional[list[str]] = Query(None),
    placer: Optional[str] = None,
    channel: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 100,
    db: AsyncMySQL = Depends(get_db),
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    day = (date or datetime.now().strftime(DayFormat)).strip()
    try:
        datetime.strptime(day, DayFormat)
    except ValueError:
        return ErrResponse(message="date 格式应为单天 'YYYY-MM-DD'")

    def empty():
        return ApiResponse(
            data={
                "data": [],
                "columns": PLACER_COLUMNS,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": 0,
                    "total_pages": 0,
                },
            }
        )

    gp_set = await _resolve_gp_set(game_platform, region, None)
    if gp_set is not None and not gp_set:
        return empty()
    placer_set = await _resolve_placer_set(placer, department)
    if placer_set is not None and not placer_set:
        return empty()

    dept_sql, dept_params = await _dept_where(current_user)
    gp_sql, gp_params = _gp_where(gp_set)
    ch_sql, ch_params = await _channel_where(channel, db)
    placer_sql, placer_params = "", []
    if placer_set is not None:
        placeholders = ", ".join(["%s"] * len(placer_set))
        placer_sql = f"AND placer_id IN ({placeholders})"
        placer_params = list(placer_set)

    metrics_sql = f"""SELECT
    placer_id AS id,
    ROUND(SUM(amount_spent),2) AS 消耗,
    ROUND(SUM(purchases_value)/NULLIF(SUM(amount_spent),0),2) AS ROAS,
    ROUND(SUM(amount_spent)/NULLIF(SUM(app_installs),0),2) AS CPI,
    ROUND(SUM(amount_spent)/NULLIF(SUM(purchases),0),2) AS 付费成本,
    ROUND(SUM(amount_spent)/NULLIF(SUM(subscribe_website),0),2) AS 订阅成本
FROM ad_daily_detail
WHERE level = 'campaign' AND department IS NOT NULL AND date = %s AND placer_id IS NOT NULL {dept_sql} {gp_sql} {ch_sql} {placer_sql}
GROUP BY placer_id"""

    cur_rows = await db.fetchall(
        metrics_sql,
        [day, *dept_params, *gp_params, *ch_params, *placer_params],
        as_dict=True,
    )
    cur_rows = [r for r in cur_rows if (r["消耗"] or 0) > 0]
    if not cur_rows:
        return empty()

    real_names = [r["id"] for r in cur_rows]
    umap = await _user_map(real_names)
    # 在投代理线数: 每个 optimizer 名下 enabled 的代理线条数
    line_docs = await cols.agent_line_config.find(
        {"optimizer": {"$in": real_names}, "enabled": True}, {"optimizer": 1}
    ).to_list(length=None)
    line_count = Counter(d["optimizer"] for d in line_docs)

    rows = []
    for r in cur_rows:
        rn = r["id"]
        u = umap.get(rn, {})
        if u.get("roles") != ["operator"]:  # 仅保留角色只有 operator 的投手
            continue
        rows.append(
            {
                "real_name": rn,
                "投手": u.get("full_name") or rn,
                "组": u.get("department"),
                "在投代理线": line_count.get(rn, 0),
                "消耗": r["消耗"],
                "ROAS": r["ROAS"],
                "CPI": r["CPI"],
                "付费成本": r["付费成本"],
                "订阅成本": r["订阅成本"],
            }
        )

    sort_key = sort_by if sort_by in PLACER_SORT_KEYS else "消耗"
    rows.sort(
        key=lambda x: (
            x.get(sort_key) if isinstance(x.get(sort_key), (int, float)) else 0.0
        ),
        reverse=(sort_order != "asc"),
    )

    total = len(rows)
    start_idx = (page - 1) * page_size
    page_rows = rows[start_idx : start_idx + page_size]

    return ApiResponse(
        data={
            "data": page_rows,
            "columns": PLACER_COLUMNS,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
            },
        }
    )


@router.get("/placer_leaderboard")
async def placer_leaderboard(
    month: Optional[str] = None,
    game_platform: Optional[str] = None,
    region: Optional[str] = None,
    department: Optional[list[str]] = Query(None),
    placer: Optional[str] = None,
    channel: Optional[str] = None,
    group_by: str = "placer",
    page: int = 1,
    page_size: int = 100,
    db: AsyncMySQL = Depends(get_db),
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    if group_by not in ("placer", "department"):
        return ErrResponse(message="group_by 应为 'placer' 或 'department'")
    columns = (
        TEAM_LEADERBOARD_COLUMNS if group_by == "department" else LEADERBOARD_COLUMNS
    )
    month = (month or datetime.now().strftime("%Y-%m")).strip()
    try:
        ym = datetime.strptime(f"{month}-01", DayFormat)
    except ValueError:
        return ErrResponse(message="month 格式应为 'YYYY-MM'")

    start = ym.strftime(DayFormat)
    end = (ym + timedelta(days=32)).replace(day=1).strftime(DayFormat)  # 本月末+1
    prev_start = (ym - timedelta(days=1)).replace(day=1).strftime(DayFormat)  # 上月初

    def empty():
        return ApiResponse(
            data={
                "data": [],
                "columns": columns,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": 0,
                    "total_pages": 0,
                },
            }
        )

    gp_set = await _resolve_gp_set(game_platform, region, None)
    if gp_set is not None and not gp_set:
        return empty()
    placer_set = await _resolve_placer_set(placer, department)
    if placer_set is not None and not placer_set:
        return empty()

    dept_sql, dept_params = await _dept_where(current_user)
    gp_sql, gp_params = _gp_where(gp_set)
    ch_sql, ch_params = await _channel_where(channel, db)
    placer_sql, placer_params = "", []
    if placer_set is not None:
        placeholders = ", ".join(["%s"] * len(placer_set))
        placer_sql = f"AND placer_id IN ({placeholders})"
        placer_params = list(placer_set)

    # 一次区间(上月初~本月末)拿本月与上月消耗
    sql = f"""SELECT placer_id AS id,
    ROUND(SUM(CASE WHEN date >= %s THEN amount_spent ELSE 0 END),2) AS cur_spend,
    ROUND(SUM(CASE WHEN date < %s THEN amount_spent ELSE 0 END),2) AS prev_spend
FROM ad_daily_detail
WHERE level = 'campaign' AND department IS NOT NULL AND date >= %s AND date < %s AND placer_id IS NOT NULL {dept_sql} {gp_sql} {ch_sql} {placer_sql}
GROUP BY placer_id"""

    db_rows = await db.fetchall(
        sql,
        [
            start,
            start,
            prev_start,
            end,
            *dept_params,
            *gp_params,
            *ch_params,
            *placer_params,
        ],
        as_dict=True,
    )
    rows_raw = [r for r in db_rows if (r["cur_spend"] or 0) > 0]
    if not rows_raw:
        return empty()

    umap = await _user_map([r["id"] for r in rows_raw])

    if group_by == "department":
        # 投手消耗按所属部门汇总; 无所属部门的投手不计入
        dept_agg: dict[str, dict] = {}
        for r in rows_raw:
            dept = umap.get(r["id"], {}).get("department")
            if not dept or dept == "运营部":
                continue
            agg = dept_agg.setdefault(
                dept, {"id": dept, "cur_spend": 0.0, "prev_spend": 0.0}
            )
            agg["cur_spend"] += float(r["cur_spend"] or 0)
            agg["prev_spend"] += float(r["prev_spend"] or 0)
        rows_raw = list(dept_agg.values())

    rows_raw.sort(key=lambda x: x["cur_spend"] or 0, reverse=True)

    total = len(rows_raw)
    start_idx = (page - 1) * page_size
    page_slice = rows_raw[start_idx : start_idx + page_size]

    data = []
    for i, r in enumerate(page_slice):
        row = {
            "排名": start_idx + i + 1,
            "消耗": round(r["cur_spend"], 2),
            "同比上月": _vs7(r["cur_spend"], r["prev_spend"]),
        }
        if group_by == "department":
            row["组"] = r["id"]
        else:
            u = umap.get(r["id"], {})
            row.update(
                {
                    "real_name": r["id"],
                    "投手": u.get("full_name") or r["id"],
                    "组": u.get("department"),
                }
            )
        data.append(row)

    return ApiResponse(
        data={
            "data": data,
            "columns": columns,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
            },
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
# 渠道商维度 (Doris fb_ad_channel)
# ═══════════════════════════════════════════════════════════════════════════

CHANNEL_COLUMNS = ["渠道商", "总消耗", "账户数", "封户数", "封户率", "VS7日"]
_GOOD_STATUS = {1, 8, 9}


def _norm_acc(a) -> str:
    return str(a).removeprefix("act_")


def _coerce_ids(v) -> list[str]:
    """Doris ARRAY 经 MySQL 协议可能返回 list 或 '["a","b"]' 字符串。"""
    if not v:
        return []
    if isinstance(v, list):
        return [_norm_acc(x) for x in v]
    s = str(v).strip()
    if not s or s in ("[]", "null"):
        return []
    try:
        return [_norm_acc(x) for x in json.loads(s)]
    except Exception:
        return [
            _norm_acc(x.strip().strip('"').strip("'"))
            for x in s.strip("[]").split(",")
            if x.strip()
        ]


def _is_banned(status) -> bool:
    if status is None:
        return False
    try:
        return int(status) not in _GOOD_STATUS
    except (TypeError, ValueError):
        return False


@router.get("/channel_overview")
async def channel_overview(
    game_platform: Optional[str] = None,
    region: Optional[str] = None,
    placer: Optional[str] = None,
    department: Optional[list[str]] = Query(None),
    channel: Optional[str] = None,
    date: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
    db: AsyncMySQL = Depends(get_db),
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    day = (date or datetime.now().strftime(DayFormat)).strip()
    try:
        prev_day = (datetime.strptime(day, DayFormat) - timedelta(days=7)).strftime(
            DayFormat
        )
    except ValueError:
        return ErrResponse(message="date 格式应为单天 'YYYY-MM-DD'")

    def empty():
        return ApiResponse(
            data={
                "data": [],
                "columns": CHANNEL_COLUMNS,
                "total_row": {"总消耗": 0, "账户数": 0, "封户数": 0, "封户率": "0.0%"},
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": 0,
                    "total_pages": 0,
                },
            }
        )

    gp_set = await _resolve_gp_set(game_platform, region, placer)
    if gp_set is not None and not gp_set:
        return empty()
    dept_sql, dept_params = await _dept_where(current_user)
    deptf_sql, deptf_params = _dept_filter_where(department)
    gp_sql, gp_params = _gp_where(gp_set)
    ch_sql, ch_params = await _channel_where(channel, db)
    placer_sql, placer_params = _placer_where(placer)

    # 按账户的当天/7天前消耗 + 当天最新状态 (不传项目则统计全部项目)
    acc_sql = f"""SELECT account_id AS id,
    ROUND(SUM(CASE WHEN date = %s THEN amount_spent ELSE 0 END),2) AS cur_spend,
    ROUND(SUM(CASE WHEN date = %s THEN amount_spent ELSE 0 END),2) AS prev_spend,
    MAX(CASE WHEN date = %s THEN account_status END) AS account_status
FROM ad_daily_detail
WHERE level = 'campaign' AND department IS NOT NULL AND date IN (%s, %s) {gp_sql} {dept_sql} {deptf_sql} {ch_sql} {placer_sql}
GROUP BY account_id"""
    acc_rows = await db.fetchall(
        acc_sql,
        [
            day,
            prev_day,
            day,
            day,
            prev_day,
            *gp_params,
            *dept_params,
            *deptf_params,
            *ch_params,
            *placer_params,
        ],
        as_dict=True,
    )
    spend_map = {
        _norm_acc(r["id"]): r
        for r in acc_rows
        if r.get("id") and (r["cur_spend"] or 0) > 0
    }
    if not spend_map:
        return empty()

    ch_rows = await db.fetchall(
        "SELECT id, channel_name, channel_short_name, channel_code, "
        "json_extract(account_ids_json, '$[*].account_id') AS account_ids FROM fb_ad_channel",
        as_dict=True,
    )

    rows = []
    for ch in ch_rows:
        members = [a for a in _coerce_ids(ch.get("account_ids")) if a in spend_map]
        if not members:
            continue
        total = round(sum(spend_map[a]["cur_spend"] or 0 for a in members), 2)
        prev = round(sum(spend_map[a]["prev_spend"] or 0 for a in members), 2)
        banned = sum(1 for a in members if _is_banned(spend_map[a]["account_status"]))
        acc_n = len(members)
        rows.append(
            {
                "channel_id": ch["id"],
                "渠道商": ch.get("channel_name"),
                "渠道简称": ch.get("channel_short_name"),
                "渠道编码": ch.get("channel_code"),
                "总消耗": total,
                "账户数": acc_n,
                "封户数": banned,
                "封户率": f"{round(banned / acc_n * 100, 1)}%" if acc_n else "0.0%",
                "VS7日": _vs7(total, prev),
            }
        )

    if not rows:
        return empty()
    rows.sort(key=lambda x: x["总消耗"], reverse=True)

    # 总计 (全量, 不受分页影响)
    sum_spend = round(sum(r["总消耗"] for r in rows), 2)
    sum_acc = sum(r["账户数"] for r in rows)
    sum_banned = sum(r["封户数"] for r in rows)
    total_row = {
        "总消耗": sum_spend,
        "账户数": sum_acc,
        "封户数": sum_banned,
        "封户率": f"{round(sum_banned / sum_acc * 100, 1)}%" if sum_acc else "0.0%",
    }

    total = len(rows)
    start_idx = (page - 1) * page_size
    page_rows = rows[start_idx : start_idx + page_size]

    return ApiResponse(
        data={
            "data": page_rows,
            "columns": CHANNEL_COLUMNS,
            "total_row": total_row,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
            },
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
# 今日总消耗概览 (全局: 今日/昨日/近7日平均/本月 + 7日折线)
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/spend_summary")
async def spend_summary(
    date: Optional[str] = None,
    trend_days: int = 14,
    game_platform: Optional[str] = None,
    region: Optional[str] = None,
    placer: Optional[str] = None,
    department: Optional[list[str]] = Query(None),
    channel: Optional[str] = None,
    db: AsyncMySQL = Depends(get_db),
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    day = (date or datetime.now().strftime(DayFormat)).strip()
    try:
        day_dt = datetime.strptime(day, DayFormat)
    except ValueError:
        return ErrResponse(message="date 格式应为单天 'YYYY-MM-DD'")

    yesterday = (day_dt - timedelta(days=1)).strftime(DayFormat)
    # 折线含所选天; 所选天是今天时数据进行中, 点上带「进行中」标记, 前端定标时排除它
    trend_dates = [
        (day_dt - timedelta(days=i)).strftime(DayFormat)
        for i in range(trend_days - 1, -1, -1)
    ]
    month_first = day_dt.replace(day=1).strftime(DayFormat)
    last7_start = (day_dt - timedelta(days=7)).strftime(DayFormat)
    window_start = min(
        trend_dates[0], month_first, last7_start
    )  # 覆盖 折线 / 本月 / 近7日平均 的较早端
    next_day = (day_dt + timedelta(days=1)).strftime(DayFormat)

    gp_set = await _resolve_gp_set(game_platform, region, placer)
    dept_sql, dept_params = await _dept_where(current_user)
    deptf_sql, deptf_params = _dept_filter_where(department)
    gp_sql, gp_params = _gp_where(gp_set)
    ch_sql, ch_params = await _channel_where(channel, db)
    placer_sql, placer_params = _placer_where(placer)

    if gp_set is not None and not gp_set:
        daily = {}  # 筛选交集无匹配项目
    else:
        sql = f"""SELECT DATE_FORMAT(date, '%%Y-%%m-%%d') AS d, ROUND(SUM(amount_spent),2) AS spend
FROM ad_daily_detail
WHERE level = 'campaign' AND department IS NOT NULL AND date >= %s AND date < %s {dept_sql} {deptf_sql} {gp_sql} {ch_sql} {placer_sql}
GROUP BY date"""
        rows = await db.fetchall(
            sql,
            [
                window_start,
                next_day,
                *dept_params,
                *deptf_params,
                *gp_params,
                *ch_params,
                *placer_params,
            ],
            as_dict=True,
        )
        daily = {r["d"]: (r["spend"] or 0) for r in rows}

    today_total = daily.get(day, 0)
    yesterday_total = daily.get(yesterday, 0)
    # 近7日平均: 所选天之前的 7 个完整天 (所选天可能进行中, 不参与)
    last7_avg = round(
        sum(
            daily.get((day_dt - timedelta(days=i)).strftime(DayFormat), 0)
            for i in range(1, 8)
        )
        / 7,
        2,
    )
    month_total = round(sum(s for d, s in daily.items() if d >= month_first), 2)
    in_progress_day = day if day == datetime.now().strftime(DayFormat) else None

    return ApiResponse(
        data={
            "今日总消耗": today_total,
            "昨日": yesterday_total,
            "环比昨日": _vs7(today_total, yesterday_total),
            "近7日平均": last7_avg,
            "本月": month_total,
            "消耗趋势": [
                {"date": d, "消耗": daily.get(d, 0), "进行中": d == in_progress_day}
                for d in trend_dates
            ],
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
# 全局当天分时趋势
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/intraday_trend")
async def intraday_trend(
    date: Optional[str] = None,
    period: str = "24h",
    kpi_target: Optional[float] = None,
    game_platform: Optional[str] = None,
    region: Optional[str] = None,
    placer: Optional[str] = None,
    department: Optional[list[str]] = Query(None),
    channel: Optional[str] = None,
    db: AsyncMySQL = Depends(get_db),
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    day = (date or datetime.now().strftime(DayFormat)).strip()
    try:
        day_dt = datetime.strptime(day, DayFormat)
    except ValueError:
        return ErrResponse(message="date 格式应为单天 'YYYY-MM-DD'")
    next_day = (day_dt + timedelta(days=1)).strftime(DayFormat)

    # 24h=当天每小时(ad_hourly_detail); 7d/30d=按天(ad_daily_detail), 截止所选天
    if period == "24h":
        table, time_fmt, start = "ad_hourly_detail", "%%H:%%i", day
    elif period in ("7d", "30d"):
        days = 7 if period == "7d" else 30
        table, time_fmt = "ad_daily_detail", "%%m-%%d"
        start = (day_dt - timedelta(days=days - 1)).strftime(DayFormat)
    else:
        return ErrResponse(message="period 应为 24h/7d/30d")

    gp_set = await _resolve_gp_set(game_platform, region, placer)
    if gp_set is not None and not gp_set:
        return ApiResponse(data={"data": [], "kpi_target": kpi_target})
    dept_sql, dept_params = await _dept_where(current_user)
    deptf_sql, deptf_params = _dept_filter_where(department)
    gp_sql, gp_params = _gp_where(gp_set)
    ch_sql, ch_params = await _channel_where(channel, db)
    placer_sql, placer_params = _placer_where(placer)

    where = f"level = 'campaign' AND department IS NOT NULL AND date >= %s AND date < %s {dept_sql} {deptf_sql} {gp_sql} {ch_sql} {placer_sql}"
    params = [
        start,
        next_day,
        *dept_params,
        *deptf_params,
        *gp_params,
        *ch_params,
        *placer_params,
    ]

    sql = f"""SELECT DATE_FORMAT(date, '{time_fmt}') AS 时间,
    ROUND(SUM(amount_spent),2) AS 消耗,
    ROUND(SUM(amount_spent)/NULLIF(SUM(purchases),0),2) AS 付费成本,
    ROUND(SUM(amount_spent)/NULLIF(SUM(subscribe_website),0),2) AS 订阅成本
FROM {table}
WHERE {where}
GROUP BY date
ORDER BY date"""
    rows = await db.fetchall(sql, params, as_dict=True)

    proj_sql = f"""SELECT DATE_FORMAT(date, '{time_fmt}') AS t, game_platform AS gp,
    ROUND(SUM(amount_spent),2) AS spend,
    ROUND(SUM(amount_spent)/NULLIF(SUM(purchases),0),2) AS 付费成本,
    ROUND(SUM(amount_spent)/NULLIF(SUM(subscribe_website),0),2) AS 订阅成本
FROM {table}
WHERE {where}
GROUP BY date, game_platform"""
    proj_rows = await db.fetchall(proj_sql, params, as_dict=True)

    # 0 点桶存的是前一天的数据, 保留时间点但数值归零 (仅小时粒度有 0 点桶)
    zero_t = "00:00" if period == "24h" else None
    for r in rows:
        if r.get("时间") == zero_t:
            r["消耗"] = 0
            r["付费成本"] = 0
            r["订阅成本"] = 0

    # 每个时间点挂分项目消耗 (按消耗降序), 折线仍画总消耗, 明细给 tooltip 用
    by_time: dict = {}
    for pr in proj_rows:
        if pr["t"] == zero_t or not (pr["spend"] or 0) > 0:
            continue
        gp = pr["gp"] or "未知"
        by_time.setdefault(pr["t"], {})[gp] = {
            "消耗": pr["spend"],
            "付费成本": pr["付费成本"],
            "订阅成本": pr["订阅成本"],
        }
    for r in rows:
        detail = by_time.get(r.get("时间"), {})
        r["项目明细"] = [
            {"项目": gp, **vals}
            for gp, vals in sorted(detail.items(), key=lambda kv: -(kv[1]["消耗"] or 0))
        ]

    return ApiResponse(
        data={
            "data": rows,
            "kpi_target": kpi_target,
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
# 筛选模板 (个人私有: 项目/地区/投手, 不含日期)
# ═══════════════════════════════════════════════════════════════════════════


class FilterTemplateFilters(BaseModel):
    game_platform: list[str] = []
    region: list[str] = []
    placer: list[str] = []


class FilterTemplateCreate(BaseModel):
    name: str
    filters: FilterTemplateFilters


def _fmt_use_time(dt) -> Optional[str]:
    return dt.strftime(SecondFormat) if dt else None


@router.get("/filter_templates")
async def list_filter_templates(
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse:
    # 列表只给名称 + 上次使用时间; 按使用时间倒序, 未用过的(无 use_time)排末尾, 再按创建时间
    docs = (
        await cols.dashboard_filter_templates.find(
            {"real_name": current_user.real_name}
        )
        .sort([("use_time", -1), ("created_at", -1)])
        .to_list(length=None)
    )
    return ApiResponse(
        data=[
            {
                "id": str(d["_id"]),
                "name": d["name"],
                "use_time": _fmt_use_time(d.get("use_time")),
            }
            for d in docs
        ]
    )


@router.get("/filter_templates/{template_id}")
async def apply_filter_template(
    template_id: str,
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    """应用模板: 返回实际筛选参数, 同时把使用时间刷新为当前。"""
    try:
        oid = ObjectId(template_id)
    except Exception:
        return ErrResponse(message="template_id 非法")
    doc = await cols.dashboard_filter_templates.find_one_and_update(
        {"_id": oid, "real_name": current_user.real_name},
        {"$set": {"use_time": datetime.now(tz_cst)}},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        return ErrResponse(message="模板不存在或无权访问")
    return ApiResponse(
        data={
            "id": str(doc["_id"]),
            "name": doc["name"],
            "filters": doc.get("filters", {}),
            "use_time": _fmt_use_time(doc.get("use_time")),
        }
    )


@router.post("/filter_templates")
async def create_filter_template(
    body: FilterTemplateCreate,
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    name = body.name.strip()
    if not name:
        return ErrResponse(message="模板名不能为空")
    # 新建不写 use_time: 没被应用过就是"未使用"
    doc = {
        "real_name": current_user.real_name,
        "name": name,
        "filters": body.filters.model_dump(),
        "created_at": datetime.now(tz_cst),
    }
    res = await cols.dashboard_filter_templates.insert_one(doc)
    return ApiResponse(
        data={"id": str(res.inserted_id), "name": name, "use_time": None}
    )


@router.delete("/filter_templates/{template_id}")
async def delete_filter_template(
    template_id: str,
    current_user: UserModel = Depends(auth_current_user),
) -> ApiResponse | ErrResponse:
    try:
        oid = ObjectId(template_id)
    except Exception:
        return ErrResponse(message="template_id 非法")
    res = await cols.dashboard_filter_templates.delete_one(
        {"_id": oid, "real_name": current_user.real_name}
    )
    if res.deleted_count == 0:
        return ErrResponse(message="模板不存在或无权删除")
    return ApiResponse(data={"id": template_id})
