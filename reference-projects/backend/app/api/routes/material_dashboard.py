"""素材数据看板：素材师维度的素材消耗统计。
消耗取 Doris ad_daily_detail (level='ad')，素材归属取 Mongo materials.creative_editor。
广告行一律经 unique_name 直连 basename——FB 原始素材名里嵌着的系统素材名由
schedulers/tasks/ad_materials/asset_name_sync.py 抽出来回写 unique_name，
这里不再单独查 ad_asset_names。"""

import asyncio
import base64
import io
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

import pandas as pd
from bson import ObjectId
from fastapi import APIRouter, Depends, Query

from app.db.clients import get_db
from app.db.mongo import cols, user_cols
from app.model_type_defs.common_models import ApiResponse
from app.services import task_service

router = APIRouter(prefix="/material-dashboard", tags=["素材数据看板"])

CST = timezone(timedelta(hours=8))


async def _order_match_cond(order_query: dict) -> tuple[list, dict]:
    """工单侧筛选 ->（命中的 order_id，素材侧匹配条件）。
    素材经 order_id 直连工单，或 basename 在其产出物中；产出物侧直接用 order_id。"""
    oids = [
        str(o["_id"])
        async for o in cols.material_orders.find(order_query, projection={"_id": 1})
    ]
    basenames = [
        o["basename"]
        async for o in cols.material_order_outputs.find(
            {"order_id": {"$in": oids}, "basename": {"$ne": None}},
            projection={"basename": 1},
        )
    ]
    return oids, {
        "$or": [{"order_id": {"$in": oids}}, {"basename": {"$in": basenames}}]
    }


async def _order_output_docs(basenames: List[str], with_img: bool = True) -> dict:
    """按 basename 取工单产出物最新一版 -> {basename: doc}，同名多版本只留一条。
    文档内嵌 base64 缩略图，先投影再分组；导出不展示缩略图，用 with_img=False 排掉。"""
    if not basenames:
        return {}
    projection = {
        "basename": 1,
        "object_key": 1,
        "filename": 1,
        "filetype": 1,
        "created_at": 1,
        "designer": 1,
        "order_id": 1,
    }
    if with_img:
        projection["img"] = 1
    return {
        d["_id"]: d["doc"]
        async for d in cols.material_order_outputs.aggregate(
            [
                {"$match": {"basename": {"$in": basenames}}},
                {"$project": projection},
                {"$sort": {"_id": -1}},
                {"$group": {"_id": "$basename", "doc": {"$first": "$$ROOT"}}},
            ]
        )
    }


def _as_material_doc(doc: dict) -> dict:
    """工单产出物转为素材库行组装使用的字段口径。"""
    return {
        "_id": doc["_id"],
        "basename": doc["basename"],
        "filename": doc.get("object_key"),
        "origin_filename": doc.get("filename"),
        "filetype": doc.get("filetype"),
        "created_at": doc.get("created_at"),
        "creative_editor": doc.get("designer"),
        "order_id": doc.get("order_id"),
        "img": doc.get("img"),
        "is_order_output": True,
    }


def _spend_window(
    spend_start: Optional[str], spend_end: Optional[str], game_platform: Optional[str] = None,
) -> tuple[str, list]:
    """投放时间(消耗发生日期 ad.date)及游戏平台 -> Doris 条件，end 含当日"""
    conds = ["ad.`level` = 'ad'"]
    params: list = []
    if spend_start:
        conds.append("ad.`date` >= %s")
        params.append(spend_start)
    if spend_end:
        conds.append("ad.`date` < %s")
        params.append(
            (datetime.strptime(spend_end, "%Y-%m-%d") + timedelta(days=1)).strftime(
                "%Y-%m-%d"
            )
        )
    if game_platform:
        conds.append("ad.game_platform = %s")
        params.append(game_platform)
    return " AND ".join(conds), params


def _stat_metrics(st: dict) -> dict:
    """成效聚合行 -> 行展示指标（排序 key 与行展示共用同一套公式）"""
    spend = float(st.get("spend") or 0)
    reach = int(st.get("reach") or 0)
    impressions = int(st.get("impressions") or 0)
    clicks = int(st.get("clicks") or 0)
    link_clicks = int(st.get("link_clicks") or 0)
    installs = int(st.get("installs") or 0)
    registrations = int(st.get("registrations") or 0)
    purchases = int(st.get("purchases") or 0)
    return {
        "spend": round(spend, 2),
        "reach": reach,
        "impressions": impressions,
        "frequency": round(float(st.get("frequency") or 0), 2),
        "clicks": clicks,
        "cpc": round(spend / clicks, 2) if clicks else 0,
        "link_clicks": link_clicks,
        "link_ctr": round(link_clicks / impressions * 100, 2) if impressions else 0,
        "link_cpc": round(spend / link_clicks, 2) if link_clicks else 0,
        "registrations": registrations,
        "purchases": purchases,
        "purchase_cost": round(spend / purchases, 2) if purchases else 0,
        "purchase_value": round(float(st.get("purchase_value") or 0), 2),
        "cpm": round(spend / impressions * 1000, 2) if impressions else 0,
        "ctr": round(clicks / impressions * 100, 2) if impressions else 0,
        "cvr": round(registrations / clicks * 100, 2) if clicks else 0,
        "ir": round(installs / clicks * 100, 2) if clicks else 0,
    }


SORT_FIELDS = frozenset(
    {
        "spend", "reach", "impressions", "frequency", "cpm", "clicks", "ctr", "cpc",
        "link_clicks", "link_ctr", "link_cpc", "registrations", "cvr", "ir", "purchases",
        "purchase_cost", "purchase_value",
    }
)


def _merge_stat_rows(row_lists, wanted: Optional[set] = None) -> dict:
    """多路统计行合并为 {basename: 聚合行}：同一 basename 多行命中时数值累加、
    日期取 max；聚合为 NULL 的字段不落 key。"""
    merged: dict[str, dict] = {}
    for rows in row_lists:
        for r in rows:
            b = r.pop("k")
            if wanted is not None and b not in wanted:
                # 单扫路径会带出集合外 unique_name(未入库/已删素材)的统计，丢弃
                continue
            dst = merged.setdefault(b, {})
            for f, v in r.items():
                if v is None:
                    continue
                prev = dst.get(f)
                if prev is None:
                    dst[f] = v
                elif isinstance(v, (int, float, Decimal)):
                    dst[f] = prev + v
                else:
                    dst[f] = max(prev, v)
    return merged


async def _fetch_candidates(mat_query: dict) -> tuple[list, dict]:
    """候选集 basename 列表 + {basename: created_at 时间戳}（排序并列时的次级 key，
    同名多文档取最新）。投影被 basename_1_created_at_1 / dashboard_covered_v3 覆盖，不回表"""
    all_basenames: list = []
    created_ts: dict[str, float] = {}
    async for m in cols.materials.find(
        mat_query, projection={"basename": 1, "created_at": 1, "_id": 0}
    ):
        all_basenames.append(m["basename"])
        ca = m.get("created_at")
        if ca:
            created_ts[m["basename"]] = max(
                created_ts.get(m["basename"], 0), ca.timestamp()
            )
    return all_basenames, created_ts


async def _fetch_output_candidates(out_query: dict) -> tuple[list, dict]:
    """工单产出物候选 basename 列表 + {basename: created_at 时间戳}，同名多版本取最新。
    谓词与投影都在 dashboard_outputs_by_basename / _by_created 内，不读内嵌大缩略图的文档。
    designer 为空的不出（与素材库侧 creative_editor 非空同一口径）。"""
    seen: set = set()
    basenames: list = []
    created_ts: dict[str, float] = {}
    async for d in cols.material_order_outputs.find(
        out_query,
        projection={"basename": 1, "created_at": 1, "designer": 1, "_id": 0},
    ):
        b = d.get("basename")
        if not b or not d.get("designer"):
            continue
        if b not in seen:
            seen.add(b)
            basenames.append(b)
        if ca := d.get("created_at"):
            created_ts[b] = max(created_ts.get(b, 0), ca.timestamp())
    return basenames, created_ts


async def _basenames_with_editor(basenames: List[str]) -> set:
    """creative_editor 非空的 basename 子集（无素材师的素材不展示不统计）。
    谓词与投影都在 basename_1_creative_editor_1 内，覆盖查询不读大文档"""
    async def _one(chunk):
        return [
            m["basename"]
            async for m in cols.materials.find(
                {"basename": {"$in": chunk}, "creative_editor": {"$gt": ""}},
                projection={"basename": 1, "_id": 0},
            )
        ]

    allowed: set = set()
    for rows in await asyncio.gather(
        *[_one(basenames[i : i + 5000]) for i in range(0, len(basenames), 5000)]
    ):
        allowed.update(rows)
    return allowed


async def _spend_stats_by_basename(
    db, basenames: List[str], stat_cols: str,
    conds: str = "ad.`level` = 'ad'", params: list = (),
) -> dict:
    """消耗统计按 unique_name 直连聚合为 {basename: 聚合行}。"""
    tasks = []
    if len(basenames) > 5000:
        # 大集合分片 IN 会变成 N 次全表扫描：unique_name 非空即系统素材名，
        # 直接单次扫描全量分组，合并时按 basename 集合过滤
        tasks.append(
            db.fetchall(
                f"""
                SELECT ad.unique_name AS k, {stat_cols}
                FROM ad_daily_detail ad
                WHERE {conds} AND ad.unique_name IS NOT NULL
                GROUP BY ad.unique_name
                """,
                list(params),
                as_dict=True,
            )
        )
    else:
        for i in range(0, len(basenames), 5000):
            chunk = basenames[i : i + 5000]
            placeholders = ", ".join(["%s"] * len(chunk))
            tasks.append(
                db.fetchall(
                    f"""
                    SELECT ad.unique_name AS k, {stat_cols}
                    FROM ad_daily_detail ad
                    WHERE {conds} AND ad.unique_name IN ({placeholders})
                    GROUP BY ad.unique_name
                    """,
                    list(params) + chunk,
                    as_dict=True,
                )
            )
    return _merge_stat_rows(await asyncio.gather(*tasks), set(basenames))


@router.get("/designer-spend")
async def designer_spend(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    keyword: Optional[str] = Query(None, description="素材师名搜索"),
    department: Optional[str] = Query(None, description="部门名，传了只展示该部门下的素材师"),
    order: str = Query("desc", description="消耗排序: asc / desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=500),
    db=Depends(get_db),
) -> ApiResponse:
    """看板表格：日期范围筛投放日期(ad_daily_detail.date)——先统计窗口内的成效，
    消耗行经 unique_name 直连归属素材，再按 materials.creative_editor 聚到素材师，
    按消耗排序分页。"""
    stat = "SUM(ad.amount_spent) AS spend, MAX(ad.`date`) AS last_date"
    cond = "ad.`level` = 'ad' AND ad.`date` >= %s AND ad.`date` < %s"
    params = [
        start_date,
        (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"),
    ]
    rows_by_basename = {
        r["k"]: r
        for r in await db.fetchall(
            f"""
            SELECT ad.unique_name AS k, {stat}
            FROM ad_daily_detail ad
            WHERE {cond} AND ad.unique_name IS NOT NULL
            GROUP BY ad.unique_name
            """,
            params,
            as_dict=True,
        )
    }

    # 有成效的 basename 反查素材师：creative_editor 为空回退工单产出物 designer
    # （与 /materials 行展示、designers 筛选同一归属规则），两者皆无则丢弃
    editor_by_basename = {
        m["basename"]: m.get("creative_editor")
        async for m in cols.materials.find(
            {"basename": {"$in": list(rows_by_basename)}},
            projection={"basename": 1, "creative_editor": 1, "_id": 0},
        )
    }
    missing = [b for b, e in editor_by_basename.items() if not e]
    if missing:
        async for o in cols.material_order_outputs.find(
            {"basename": {"$in": missing}, "designer": {"$ne": None}},
            projection={"basename": 1, "designer": 1},
        ):
            if not editor_by_basename.get(o["basename"]):
                editor_by_basename[o["basename"]] = o["designer"]

    agg: dict[str, dict] = {}
    for basename, editor in editor_by_basename.items():
        if not editor:
            continue
        item = agg.setdefault(editor, {"name": editor, "spend": 0.0, "last_date": None})
        r = rows_by_basename[basename]
        item["spend"] += float(r.get("spend") or 0)
        ld = r.get("last_date")
        if ld:
            item["last_date"] = max(item["last_date"], ld) if item["last_date"] else ld

    editor_names = list(agg)
    member_dept: dict = {}
    async for u in user_cols.user.find(
        {
            "$or": [
                {"real_name": {"$in": editor_names}},
                {"full_name": {"$in": editor_names}},
            ]
        },
        projection={"real_name": 1, "full_name": 1, "department": 1},
    ):
        for name in (u.get("real_name"), u.get("full_name")):
            if name:
                member_dept[name] = u.get("department")

    items = list(agg.values())
    for i in items:
        i["department"] = member_dept.get(i["name"])
    if department == "-":
        # "-" 表示筛选无所属部门的素材师
        items = [i for i in items if not i["department"]]
    elif department:
        items = [i for i in items if i["department"] == department]
    if keyword:
        items = [i for i in items if keyword in i["name"]]
    items.sort(key=lambda i: i["spend"], reverse=order != "asc")

    total = len(items)
    spend_total = round(sum(i["spend"] for i in items), 2)
    items = items[(page - 1) * page_size : page * page_size]
    for i in items:
        i["spend"] = round(i["spend"], 2)
        i["last_date"] = str(i["last_date"]) if i["last_date"] else None
    return ApiResponse(data={"list": items, "total": total, "spend_total": spend_total})


async def _query_materials(
    submit_start, submit_end, project, game_platform, department, creators, designers,
    demand_type, country, spend_start, spend_end, order, db,
    page=None, page_size=None, with_total=False, basenames=None, sort_by="spend",
):
    """素材查询主体，/materials 与导出共用；page=None 时不分页返回全量。
    行来源 = 素材库(materials) ∪ 工单产出物(material_order_outputs) 里素材库还没有的
    那部分，两边同一套筛选、并入同一次排序分页与合计；工单字段经 order_id 或 basename
    反查带出。需求方/素材师/国家取 materials，缺失时回退工单；提交日期在素材库上是
    入库时间、在产出物上是交付时间；部门口径=需求方部门：素材库行 operator(full_name)
    优先、空则回退上传人 user(real_name)，产出物行取工单需求方；筛选与行展示同口径
    （先经覆盖索引解析成 basename 集合）。消耗按 basename(=Doris unique_name)在投放
    时间(ad_daily_detail.date，消耗发生日期)范围内汇总。
    基础表分流：只筛了提交日期时以素材库/产出物为基础表，created_at 收窄候选集后查
    消耗；其余情况以成效表 ad_daily_detail 为基础表——投放窗口的选择性远高于提交日期
    窗口，且窗口内无消耗的素材不出现。
    素材师为空的行不展示不统计（素材库看 creative_editor，产出物看 designer）。
    点名查(basenames)没出现在结果里的，第四个返回值给出逐个原因。"""
    if sort_by not in SORT_FIELDS:
        sort_by = "spend"
    # $gt "" 等价于"非空字符串"，且可被覆盖索引用上（$exists 会破坏覆盖查询）
    mat_query: dict = {"basename": {"$gt": ""}}
    out_query: dict = {"basename": {"$gt": ""}}
    submit_range: dict = {}
    if submit_start:
        submit_range["$gte"] = datetime.strptime(submit_start, "%Y-%m-%d").replace(
            tzinfo=CST
        )
    if submit_end:
        submit_range["$lt"] = datetime.strptime(submit_end, "%Y-%m-%d").replace(
            tzinfo=CST
        ) + timedelta(days=1)
    if submit_range:
        mat_query["created_at"] = submit_range
        out_query["created_at"] = submit_range

    if demand_type:
        # 素材自身文件类型(image/video)，直接筛 filetype，不走工单 demand_type
        mat_query["filetype"] = demand_type
        out_query["filetype"] = demand_type

    # 工单字段筛选（需求方/项目只存在于工单上）：先解析成匹配工单集合
    order_side: dict = {}
    if project:
        order_side["project"] = {"$regex": re.escape(project), "$options": "i"}
    if creators:
        order_side["creator"] = {"$in": creators}
    and_conds: list = []
    out_conds: list = []
    if basenames:
        and_conds.append({"basename": {"$in": basenames}})
        out_conds.append({"basename": {"$in": basenames}})
    if department:
        # 部门=需求方部门：素材库行 operator 优先、为空回退上传人 user(real_name)，与行展示同口径。
        # operator 存量混 full_name/real_name（工单入库为 real_name），按两者并集匹配。
        # operator 为空的谓词(null)会破坏覆盖查询，先经覆盖索引把两路解析成 basename 集合再 $in
        dept_names, reals = set(), set()
        async for u in user_cols.user.find(
            {"department": department}, projection={"real_name": 1, "full_name": 1}
        ):
            if u.get("full_name"):
                dept_names.add(u["full_name"])
            if u.get("real_name"):
                dept_names.add(u["real_name"])
                reals.add(u["real_name"])
        op_map = {
            m["basename"]: m["operator"]
            async for m in cols.materials.find(
                {"operator": {"$gt": ""}},
                projection={"basename": 1, "operator": 1, "_id": 0},
            )
        }
        user_set = {
            m["basename"]
            async for m in cols.materials.find(
                {"user": {"$in": list(reals)}}, projection={"basename": 1, "_id": 0}
            )
        }
        dept_basenames = {b for b, o in op_map.items() if o in dept_names} | (
            user_set - set(op_map)
        )
        and_conds.append({"basename": {"$in": list(dept_basenames)}})
        # 产出物行的部门取工单需求方（与行展示一致），按 creator 反查工单
        dept_oids, _ = await _order_match_cond({"creator": {"$in": list(dept_names)}})
        out_conds.append({"order_id": {"$in": dept_oids}})
    if order_side:
        oids, cond = await _order_match_cond(order_side)
        and_conds.append(cond)
        out_conds.append({"order_id": {"$in": oids}})
    if country:
        # 素材自带 country（直传）或所属工单国家含该国（工单入库素材无 country 字段）
        country_oids, cond = await _order_match_cond({"tags.country": country})
        and_conds.append({"$or": [{"country": country}] + cond["$or"]})
        out_conds.append({"order_id": {"$in": country_oids}})
    if designers:
        # 有效素材师口径 = creative_editor，为空时才回退产出物 designer
        # （与行展示、designer-spend 归属一致，避免消耗归属和筛选对不上）
        d_basenames = [
            o["basename"]
            async for o in cols.material_order_outputs.find(
                {"designer": {"$in": designers}, "basename": {"$ne": None}},
                projection={"basename": 1},
            )
        ]
        and_conds.append(
            {
                "$or": [
                    {"creative_editor": {"$in": designers}},
                    {
                        "creative_editor": {"$in": [None, ""]},
                        "basename": {"$in": d_basenames},
                    },
                ]
            }
        )
        out_conds.append({"designer": {"$in": designers}})

    # 投放时间=消耗发生日期(ad.date)，与 designer-spend 同口径
    doris_conds, params = _spend_window(spend_start, spend_end, game_platform)
    stat_cols = (
        "SUM(ad.amount_spent) AS spend, SUM(ad.reach) AS reach, "
        "SUM(ad.impressions) AS impressions, AVG(ad.frequency) AS frequency, "
        "SUM(ad.clicks_all) AS clicks, SUM(ad.inline_link_clicks) AS link_clicks, "
        "SUM(ad.app_installs) AS installs, SUM(ad.complete_registration) AS registrations, "
        "SUM(ad.purchases) AS purchases, SUM(ad.purchases_value) AS purchase_value"
    )
    projection = {
        "basename": 1,
        "filename": 1,
        "origin_filename": 1,
        "filetype": 1,
        "created_at": 1,
        "creative_editor": 1,
        "country": 1,
        "order_id": 1,
        "user": 1,
        "operator": 1,
    }
    if submit_range and not (spend_start or spend_end):
        # 素材库/产出物为基础表：created_at 已收窄候选集。产出物文档内嵌大缩略图，
        # 整文档拉取在生产库要 80s+：两边都先走覆盖索引只取名字，消耗分批并行查
        if and_conds:
            mat_query["$and"] = and_conds
        if out_conds:
            out_query["$and"] = out_conds
        lib_basenames, created_ts = await _fetch_candidates(mat_query)
        out_basenames, out_ts = await _fetch_output_candidates(out_query)
        stats_map = await _spend_stats_by_basename(
            db,
            list(set(lib_basenames) | set(out_basenames) | set(basenames or [])),
            stat_cols, doris_conds, params,
        )
    else:
        # 成效表为基础表：投放窗口内按 unique_name 全量聚合（与 designer-spend 同路），
        # 两边都匹配不到的行丢弃，窗口内无消耗的素材不出现
        direct_rows = await db.fetchall(
            f"""
            SELECT ad.unique_name AS k, {stat_cols}
            FROM ad_daily_detail ad
            WHERE {doris_conds} AND ad.unique_name IS NOT NULL
            GROUP BY ad.unique_name
            """,
            params,
            as_dict=True,
        )
        stats_map = _merge_stat_rows([direct_rows])
        pool = list(stats_map)
        and_conds.append({"basename": {"$in": pool}})
        out_conds.append({"basename": {"$in": pool}})
        mat_query["$and"] = and_conds
        out_query["$and"] = out_conds
        lib_basenames, created_ts = await _fetch_candidates(mat_query)
        out_basenames, out_ts = await _fetch_output_candidates(out_query)

    # 无素材师(creative_editor 空)的素材不展示不统计：排序分页前过滤，
    # total/合计/切片在下游自然同口径（产出物侧的 designer 已在候选查询里过滤掉）
    uniq = list(dict.fromkeys(lib_basenames))
    allowed = await _basenames_with_editor(uniq)
    uniq = [b for b in uniq if b in allowed]

    # 素材库已有的不从产出物再出一行（同 basename 即同内容，素材库那条信息更全）；
    # 按过滤前的库内集合去重，库内没填素材师的素材不会绕道产出物冒出来
    in_lib = set(lib_basenames)
    out_uniq = [b for b in out_basenames if b not in in_lib]
    out_set = set(out_uniq)
    created_ts.update({b: t for b, t in out_ts.items() if b in out_set})

    # 点名查但没出现在结果里的，逐个标原因，前端据此提示
    missing = []
    if pending := [
        b for b in basenames or [] if b not in set(uniq) and b not in out_set
    ]:
        lib_hit = set(
            await cols.materials.distinct("basename", {"basename": {"$in": pending}})
        )
        out_hit = set(
            await cols.material_order_outputs.distinct(
                "basename", {"basename": {"$in": pending}}
            )
        )
        no_stats = [b for b in pending if b not in stats_map]
        # 成效表里压根没有这个 unique_name(素材没投过) 与"选的窗口内没消耗"是两回事，
        # 提示要分开；没传投放窗口时 stats_map 本就是全量，不用多查一次
        if no_stats and (spend_start or spend_end):
            placeholders = ", ".join(["%s"] * len(no_stats))
            ever = {
                r[0]
                for r in await db.fetchall(
                    f"""
                    SELECT DISTINCT ad.unique_name FROM ad_daily_detail ad
                    WHERE ad.`level` = 'ad' AND ad.unique_name IN ({placeholders})
                    """,
                    no_stats,
                )
            }
            never = set(no_stats) - ever
        else:
            never = set(no_stats)
        # 库内但没填素材师的被 allowed 过滤掉了，单独提示：一个筛选条件都没传时
        # 也会命中，报"不符合其他筛选条件"会误导
        no_editor: set = set()
        if lib_pending := [b for b in pending if b in lib_hit]:
            no_editor = set(lib_pending) - await _basenames_with_editor(lib_pending)
        for b in pending:
            if b not in lib_hit and b not in out_hit:
                reason = "素材不存在"
            elif b in never:
                reason = "素材无投放记录"
            elif b not in stats_map:
                reason = "所选投放时间内无消耗"
            elif b in no_editor:
                reason = "素材未填素材师"
            else:
                reason = "不符合其他筛选条件"
            missing.append({"basename": b, "reason": reason})

    ranked = uniq + out_uniq
    total = len(ranked)
    if with_total:
        # 排序本来就需要全量消耗，合计只是求和，不多发查询
        spend_total = round(
            sum(float((stats_map.get(b) or {}).get("spend") or 0) for b in ranked), 2
        )
    # 两遍稳定排序：主指标并列的素材按上传时间降序（与页内 items 排序同规则）
    ranked = sorted(ranked, key=lambda b: created_ts.get(b, 0), reverse=True)
    ranked.sort(
        key=lambda b: _stat_metrics(stats_map.get(b) or {})[sort_by],
        reverse=order != "asc",
    )
    if page is None:
        # 导出全量：覆盖投影直接出行数据（dashboard_covered_v3 索引），不回表读大文档；
        # 导出表里没有缩略图列，产出物那批排掉 img 再取，免得拉一堆 base64
        mats = [
            m
            async for m in cols.materials.find(
                mat_query, projection={**projection, "_id": 0}
            )
            if m["basename"] in allowed
        ]
        out_docs = await _order_output_docs(out_uniq, with_img=False)
    else:
        page_basenames = ranked[(page - 1) * page_size : page * page_size]
        mats = [
            m
            async for m in cols.materials.find(
                {"$and": [mat_query, {"basename": {"$in": page_basenames}}]},
                projection=projection,
            )
        ]
        out_docs = await _order_output_docs([b for b in page_basenames if b in out_set])
    mats.extend(_as_material_doc(d) for d in out_docs.values())

    # 无 order_id 的素材（直接上传/存量数据）用 basename 反查工单产出物，补工单关联和素材师
    no_order_basenames = [m["basename"] for m in mats if not m.get("order_id")]
    output_by_basename: dict = {}
    if no_order_basenames:
        async for out in cols.material_order_outputs.find(
            {"basename": {"$in": no_order_basenames}},
            projection={"basename": 1, "order_id": 1, "designer": 1},
        ):
            output_by_basename.setdefault(out["basename"], out)

    order_ids = {m["order_id"] for m in mats if m.get("order_id")}
    order_ids.update(o["order_id"] for o in output_by_basename.values())
    orders_map = {
        str(o["_id"]): o
        async for o in cols.material_orders.find(
            {"_id": {"$in": [ObjectId(i) for i in order_ids]}},
            projection={
                "project": 1,
                "product_info": 1,
                "demand_type": 1,
                "tags.country": 1,
                "creator": 1,
            },
        )
    }

    # 产出物没有 operator/user，部门按需求方口径取工单创建人
    for m in mats:
        if m.get("is_order_output"):
            m["operator"] = (orders_map.get(m.get("order_id")) or {}).get("creator")

    # 行部门 = 需求方部门：operator 优先，为空回退上传人 user(real_name)。
    # operator 存量混 full_name/real_name，与 user 一起按 full_name/real_name 双路解析部门
    operators = {m["operator"] for m in mats if m.get("operator")}
    users = {m["user"] for m in mats if not m.get("operator") and m.get("user")}
    dept_by_name: dict = {}
    names = list(operators | users)
    if names:
        async for u in user_cols.user.find(
            {"$or": [{"full_name": {"$in": names}}, {"real_name": {"$in": names}}]},
            projection={"full_name": 1, "real_name": 1, "department": 1},
        ):
            if u.get("full_name"):
                dept_by_name[u["full_name"]] = u.get("department")
            if u.get("real_name"):
                dept_by_name[u["real_name"]] = u.get("department")

    items = []
    for m in mats:
        out = output_by_basename.get(m["basename"], {}) if not m.get("order_id") else {}
        o = orders_map.get(m.get("order_id") or out.get("order_id"), {})
        designer = m.get("creative_editor") or out.get("designer")
        row_country = (
            [m["country"]] if m.get("country") else (o.get("tags") or {}).get("country") or []
        )
        ca = m.get("created_at")
        items.append(
            {
                "id": str(m["_id"]) if m.get("_id") else None,
                "filename": m.get("origin_filename") or m["filename"],
                "filetype": m.get("filetype"),
                # 桶内对象名，前端拿它去 /materials/url/{object_key} 现签预览/下载链接
                "object_key": m["filename"],
                "basename": m["basename"],
                "create_time": ca.astimezone(CST).strftime("%Y-%m-%d") if ca else None,
                "project": o.get("project"),
                "product_info": o.get("product_info"),
                "creator": o.get("creator"),
                "demand_type": o.get("demand_type"),
                "country": row_country,
                "designer": designer,
                "department": dept_by_name.get(m["operator"])
                if m.get("operator")
                else dept_by_name.get(m.get("user")),
                # 未入库的工单素材：按 id 写素材库的操作对它无效，前端据此禁用
                "is_order_output": bool(m.get("is_order_output")),
                "img": m.get("img"),
                **_stat_metrics(stats_map.get(m["basename"]) or {}),
            }
        )

    items.sort(key=lambda i: created_ts.get(i["basename"], 0), reverse=True)
    items.sort(key=lambda i: i[sort_by], reverse=order != "asc")
    return items, total, spend_total if with_total else None, missing


async def _apply_ad_lifetime(
    items: list, db, spend_start: Optional[str] = None, spend_end: Optional[str] = None,
    game_platform: Optional[str] = None,
) -> None:
    """delivery_start / delivery_cutoff：传了投放时间范围时直接回显该范围；
    未传时为素材固有属性——首次投放取全部广告最早 create_time，消耗截止取
    最后一条广告日行（仍在投(delivery=1)则为"长期投放"，否则取其 china_date）"""
    if spend_start and spend_end:
        for i in items:
            i["delivery_start"] = spend_start
            i["delivery_cutoff"] = spend_end
        return
    basenames = list({i["basename"] for i in items})
    game_platform_sql = " AND ad.game_platform = %s" if game_platform else ""
    tasks = []
    for i in range(0, len(basenames), 5000):
        chunk = basenames[i : i + 5000]
        placeholders = ", ".join(["%s"] * len(chunk))
        tasks.append(
            db.fetchall(
                f"""
                SELECT k, china_date, delivery, first_create_time FROM (
                    SELECT ad.unique_name AS k, ad.china_date, ad.delivery,
                           ROW_NUMBER() OVER (PARTITION BY ad.unique_name ORDER BY ad.`date` DESC) AS rn,
                           MIN(ad.create_time) OVER (PARTITION BY ad.unique_name) AS first_create_time
                    FROM ad_daily_detail ad
                    WHERE ad.`level` = 'ad' AND ad.unique_name IN ({placeholders}){game_platform_sql}
                ) t WHERE rn = 1
                """,
                chunk + ([game_platform] if game_platform else []),
                as_dict=True,
            )
        )
    cand: dict[str, dict] = {}
    for rows in await asyncio.gather(*tasks):
        for r in rows:
            cand[r["k"]] = r

    for i in items:
        r = cand.get(i["basename"])
        if not r:
            i["delivery_start"] = None
            i["delivery_cutoff"] = None
            continue
        first = r.get("first_create_time")
        i["delivery_start"] = str(first) if first else None
        i["delivery_cutoff"] = (
            "长期投放" if r.get("delivery") else str(r.get("china_date"))
        )


async def _apply_ad_counts(
    items: list, db, spend_start: Optional[str] = None, spend_end: Optional[str] = None,
    game_platform: Optional[str] = None,
) -> None:
    """每行补 ads_count：投放窗口内关联广告数(去重 ad_id)，
    与 /materials/ads 的 total 同口径。只补当前页，一次查询够用"""
    basenames = list({i["basename"] for i in items})
    if not basenames:
        return
    conds, params = _spend_window(spend_start, spend_end, game_platform)
    placeholders = ", ".join(["%s"] * len(basenames))
    rows = await db.fetchall(
        f"""
        SELECT ad.unique_name AS k, COUNT(DISTINCT ad.ad_id) AS n
        FROM ad_daily_detail ad
        WHERE {conds} AND ad.unique_name IN ({placeholders})
        GROUP BY ad.unique_name
        """,
        list(params) + basenames,
        as_dict=True,
    )
    counts = {r["k"]: int(r["n"] or 0) for r in rows}
    for i in items:
        i["ads_count"] = counts.get(i["basename"], 0)


AD_STAT_FIELDS = (
    "spend", "impressions", "clicks", "registrations",
    "subscriptions", "subscribe_value", "purchases", "purchase_value",
)


def _ad_metrics(st: dict) -> dict:
    """订阅率/购物率分母为注册数，与 dashboard 明细页同口径"""
    spend = float(st.get("spend") or 0)
    impressions = int(st.get("impressions") or 0)
    clicks = int(st.get("clicks") or 0)
    registrations = int(st.get("registrations") or 0)
    subscriptions = int(st.get("subscriptions") or 0)
    purchases = int(st.get("purchases") or 0)
    return {
        "spend": round(spend, 2),
        "impressions": impressions,
        "clicks": clicks,
        "cpm": round(spend / impressions * 1000, 2) if impressions else 0,
        "ctr": round(clicks / impressions * 100, 2) if impressions else 0,
        "cpa": round(spend / registrations, 2) if registrations else 0,
        "subscriptions": subscriptions,
        "subscribe_rate": round(subscriptions / registrations * 100, 2) if registrations else 0,
        "subscribe_cost": round(spend / subscriptions, 2) if subscriptions else 0,
        "subscribe_value": round(float(st.get("subscribe_value") or 0), 2),
        "purchases": purchases,
        "purchase_rate": round(purchases / registrations * 100, 2) if registrations else 0,
        "purchase_cost": round(spend / purchases, 2) if purchases else 0,
        "purchase_value": round(float(st.get("purchase_value") or 0), 2),
    }


async def _material_ad_details(
    basename: str, db, spend_start: Optional[str], spend_end: Optional[str],
    game_platform: Optional[str],
    page: int, page_size: int,
) -> tuple[list, int]:
    """单素材投放窗口内关联广告分页明细：分页下沉 Doris——先取消耗降序页内 ad_id
    （ad_id 次级排序保证翻页稳定）与 total(窗口内去重广告数)，再只查页内广告的逐日行；
    父级指标由逐日行汇总，属性(名称等)可能随时间变、取最新一天的值，daily 为有成效
    日期的逐日子行（日期升序，无数的天不出现）；单天窗口(spend_start==spend_end)不带 daily。"""
    conds, params = _spend_window(spend_start, spend_end, game_platform)
    where = f"{conds} AND ad.unique_name = %s"
    params = params + [basename]

    page_rows, total_row = await asyncio.gather(
        db.fetchall(
            f"""
            SELECT ad.ad_id, SUM(ad.amount_spent) AS spend
            FROM ad_daily_detail ad
            WHERE {where}
            GROUP BY ad.ad_id
            ORDER BY spend DESC, ad.ad_id
            LIMIT %s OFFSET %s
            """,
            params + [page_size, (page - 1) * page_size],
            as_dict=True,
        ),
        db.fetchone(
            f"SELECT COUNT(DISTINCT ad.ad_id) AS total FROM ad_daily_detail ad WHERE {where}",
            params,
            as_dict=True,
        ),
    )
    total = int(total_row["total"] or 0)
    if not page_rows:
        return [], total

    stat = (
        "MAX(ad.ad_name) AS ad_name, MAX(ad.campaign_id) AS campaign_id, "
        "MAX(ad.ad_set_id) AS ad_set_id, "
        "SUM(ad.amount_spent) AS spend, SUM(ad.impressions) AS impressions, "
        "SUM(ad.clicks_all) AS clicks, SUM(ad.complete_registration) AS registrations, "
        "SUM(ad.subscribe_website) AS subscriptions, "
        "SUM(ad.subscribe_website_values) AS subscribe_value, "
        "SUM(ad.purchases) AS purchases, SUM(ad.purchases_value) AS purchase_value"
    )
    ad_ids = [r["ad_id"] for r in page_rows]
    placeholders = ", ".join(["%s"] * len(ad_ids))
    daily_rows = await db.fetchall(
        f"""
        SELECT ad.`date`, ad.ad_id, {stat}
        FROM ad_daily_detail ad
        WHERE {where} AND ad.ad_id IN ({placeholders})
        GROUP BY ad.`date`, ad.ad_id
        """,
        params + ad_ids,
        as_dict=True,
    )
    rows_by_ad: dict[str, list] = {}
    for r in daily_rows:
        rows_by_ad.setdefault(r["ad_id"], []).append(r)
    single_day = bool(spend_start) and spend_start == spend_end
    ads = []
    for ad_id in ad_ids:
        rows = rows_by_ad[ad_id]
        rows.sort(key=lambda r: r["date"])
        latest = rows[-1]
        item = {
            "ad_id": ad_id,
            "ad_name": latest["ad_name"],
            "campaign_id": latest["campaign_id"],
            "ad_set_id": latest["ad_set_id"],
            "spend_start": spend_start,
            "spend_end": spend_end,
            **_ad_metrics({f: sum(r[f] or 0 for r in rows) for f in AD_STAT_FIELDS}),
        }
        if not single_day and item["spend"] > 0:
            # 只出实际有数的日期，窗口内无成效的天不补 0 行
            item["daily"] = [
                {"date": str(r["date"]), **_ad_metrics(r)} for r in rows
            ]
        ads.append(item)
    return ads, total


async def _basename_matches_project(basename: str, project: str) -> bool:
    """确认素材（或尚未入素材库的工单产出物）归属指定项目。"""
    order_ids, material_cond = await _order_match_cond(
        {"project": {"$regex": re.escape(project), "$options": "i"}}
    )
    if not order_ids:
        return False
    if await cols.materials.find_one(
        {"basename": basename, **material_cond}, projection={"_id": 1}
    ):
        return True
    return bool(await cols.material_order_outputs.find_one(
        {"basename": basename, "order_id": {"$in": order_ids}}, projection={"_id": 1}
    ))


@router.get("/materials/ads")
async def material_ads(
    basename: str = Query(..., description="素材basename"),
    project: Optional[str] = Query(None, description="项目，限制素材归属"),
    game_platform: Optional[str] = Query(None, description="游戏平台，仅作用于广告成效"),
    spend_start: Optional[str] = Query(..., description="投放时间起 YYYY-MM-DD"),
    spend_end: Optional[str] = Query(..., description="投放时间止 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=500),
    db=Depends(get_db),
) -> ApiResponse:
    """素材关联广告明细（点开素材行时请求）：父级为广告（窗口内聚合，按消耗降序，
    分页下沉 Doris，total=广告数=列表行 ads_count），子级 daily 为逐日数据
    （日期升序，仅含有成效的天）；单天窗口(spend_start==spend_end)不带 daily。"""
    if project and not await _basename_matches_project(basename, project):
        return ApiResponse(data={"list": [], "total": 0})
    ads, total = await _material_ad_details(
        basename, db, spend_start, spend_end, game_platform, page, page_size
    )
    return ApiResponse(data={"list": ads, "total": total})


@router.get("/materials")
async def material_list(
    submit_start: Optional[str] = Query(None, description="提交日期起 YYYY-MM-DD"),
    submit_end: Optional[str] = Query(None, description="提交日期止 YYYY-MM-DD"),
    project: Optional[str] = Query(None, description="项目ID，模糊匹配"),
    game_platform: Optional[str] = Query(None, description="游戏平台，仅作用于消耗统计"),
    department: Optional[str] = Query(None, description="部门(需求方口径)：operator 优先，空则回退上传人 user"),
    creators: Optional[List[str]] = Query(None, description="需求方(投手)，多选"),
    designers: Optional[List[str]] = Query(None, description="素材师，多选"),
    demand_type: Optional[str] = Query(None, description="素材类型: image / video，筛 materials.filetype"),
    country: Optional[str] = Query(None, description="国家"),
    basenames: Optional[List[str]] = Query(None, description="素材basename，多选"),
    spend_start: Optional[str] = Query(None, description="投放时间起 YYYY-MM-DD，仅作用于消耗统计"),
    spend_end: Optional[str] = Query(None, description="投放时间止 YYYY-MM-DD"),
    sort_by: str = Query("spend", description="排序字段见接口返回指标，白名单外回退 spend"),
    order: str = Query("desc", description="排序方向: asc / desc"),
    with_total: bool = Query(False, description="是否返回筛选结果总消耗，筛选变化时传，翻页不传"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=500),
    db=Depends(get_db),
) -> ApiResponse:
    """素材管理列表：查询逻辑见 _query_materials；投放时间/广告明细数(ads_count)/缩略图
    只补当前页，广告明细本身走 GET /materials/ads 按素材单独拉取，
    预览/下载链接由前端拿行里的 object_key 走 GET /materials/url/{object_key} 现签。
    传了 basenames 时，未出现在列表里的名字经 missing_basenames 返回原因供前端提示。"""
    items, total, spend_total, missing = await _query_materials(
        submit_start, submit_end, project, game_platform, department, creators, designers,
        demand_type, country, spend_start, spend_end, order, db,
        page=page, page_size=page_size, with_total=with_total, basenames=basenames,
        sort_by=sort_by,
    )
    await asyncio.gather(
        _apply_ad_lifetime(items, db, spend_start, spend_end, game_platform),
        _apply_ad_counts(items, db, spend_start, spend_end, game_platform),
    )

    # 缩略图 img 每行都带（视频存的是首帧），原文件预签名不在这里发，
    # 列表里签好的链接等用户点开预览时多半已过期，改由前端经 /materials/url/{object_key} 现签
    imgs = {
        str(d["_id"]): d.get("img")
        async for d in cols.materials.find(
            {"_id": {"$in": [ObjectId(i["id"]) for i in items]}},
            projection={"img": 1},
        )
    }
    for i in items:
        # 产出物行的 img 随产出物文档带出，素材库里查不到
        i["img"] = i.get("img") or imgs.get(i["id"])

    data = {"list": items, "total": total, "missing_basenames": missing}
    if with_total:
        data["spend_total"] = spend_total
    return ApiResponse(data=data)


EXPORT_COLS = {
    "basename": "名称",
    "create_time": "上传时间",
    "delivery_start": "开始日期",
    "delivery_cutoff": "结束日期",
    "designer": "素材师",
    "filetype": "类型",
    "spend": "消耗",
    "cpm": "CPM",
    "cvr": "CVR(%)",
    "ctr": "CTR(%)",
    "ir": "IR(%)",
    "impressions": "展示数",
    "clicks": "点击数",
    "registrations": "注册数",
    "country": "投放地区",
    "department": "部门",
    "creator": "需求方",
    "project": "项目",
    "product_info": "官方台子名",
}


def _build_export_excel(items: list) -> dict:
    for i in items:
        i["country"] = ",".join(i["country"])
    df = pd.DataFrame(items, columns=list(EXPORT_COLS)).rename(columns=EXPORT_COLS)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="素材数据")
    output.seek(0)
    filename = f"素材数据_{datetime.now(CST).strftime('%Y%m%d_%H%M%S')}.xlsx"
    return {
        "filename": filename,
        "content": base64.b64encode(output.read()).decode("utf-8"),
    }


async def _run_export_job(
    task_id, submit_start, submit_end, project, game_platform, department, creators, designers,
    demand_type, country, spend_start, spend_end, order, db, basenames=None,
    sort_by="spend",
):
    try:
        await task_service.set_processing(task_id)
        items, _, _, _ = await _query_materials(
            submit_start, submit_end, project, game_platform, department, creators, designers,
            demand_type, country, spend_start, spend_end, order, db,
            basenames=basenames, sort_by=sort_by,
        )
        await _apply_ad_lifetime(items, db, spend_start, spend_end, game_platform)
        # Excel 生成是 CPU 密集，放线程池避免卡事件循环
        result = await asyncio.to_thread(_build_export_excel, items)
        await task_service.done(task_id, result)
    except Exception as e:
        await task_service.fail(task_id, str(e))


@router.get("/materials/export")
async def material_export(
    submit_start: Optional[str] = Query(None, description="提交日期起 YYYY-MM-DD"),
    submit_end: Optional[str] = Query(None, description="提交日期止 YYYY-MM-DD"),
    project: Optional[str] = Query(None, description="项目ID，模糊匹配"),
    game_platform: Optional[str] = Query(None, description="游戏平台，仅作用于消耗统计"),
    department: Optional[str] = Query(None, description="部门(需求方口径)：operator 优先，空则回退上传人 user"),
    creators: Optional[List[str]] = Query(None, description="需求方(投手)，多选"),
    designers: Optional[List[str]] = Query(None, description="素材师，多选"),
    demand_type: Optional[str] = Query(None, description="素材类型: image / video，筛 materials.filetype"),
    country: Optional[str] = Query(None, description="国家"),
    basenames: Optional[List[str]] = Query(None, description="素材basename，多选，与其它条件叠加"),
    spend_start: Optional[str] = Query(None, description="投放时间起 YYYY-MM-DD，仅作用于消耗统计"),
    spend_end: Optional[str] = Query(None, description="投放时间止 YYYY-MM-DD"),
    sort_by: str = Query("spend", description="排序字段见接口返回指标，白名单外回退 spend"),
    order: str = Query("desc", description="排序方向: asc / desc"),
    db=Depends(get_db),
) -> ApiResponse:
    """素材管理列表导出 Excel：与 /materials 同口径同筛选，不分页。
    立即返回 {task_id}，前端轮询 GET /upload-tasks/{task_id}，
    done 时 result 为 {filename, content(base64)}。"""
    task_id = await task_service.create()
    task_service.spawn(
        _run_export_job(
            task_id, submit_start, submit_end, project, game_platform, department, creators,
            designers, demand_type, country, spend_start, spend_end, order, db,
            basenames=basenames, sort_by=sort_by,
        )
    )
    return ApiResponse(data={"task_id": task_id})
