import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import require_roles
from app.db.async_mysql import AsyncMySQL
from app.db.clients import get_db, redis_cli_2
from app.db.mongo import cols
from app.model_type_defs.common_models import ApiResponse, ErrResponse
from app.model_type_defs.user_models import Roles, UserModel

from .dashboard_detail import _hourly_columns

router = APIRouter(prefix="/ad-config", tags=["拉取广告配置/操作记录"])

# 与 schedulers 的 ad_config_worker 对齐(redis db2 + 同一 key)
AD_CONFIG_QUEUE_KEY = "ad:config:queue"

Level = Literal["ad", "adset", "campaign"]

# config 实体表按层级分三张:一对象一条最新态,_id=FB 对象 id
LEVEL_COLLECTIONS = {
    "campaign": cols.ad_config_campaigns,
    "adset": cols.ad_config_adsets,
    "ad": cols.ad_config_ads,
}

_SHANGHAI = ZoneInfo("Asia/Shanghai")

# 未封存(账户当天)的记录多久才允许后台再拉一次,防同账户翻多个对象时频繁打 FB
ACTIVITY_DAY_REFRESH_TTL_SECONDS = 60

# find_latest 逐天回溯的上限,防止从未被操作过的对象无限拉历史
WALK_BACK_MAX_DAYS = 30

LEVEL_ID_COLUMN = {"campaign": "campaign_id", "adset": "ad_set_id", "ad": "ad_id"}

# 操作时点快照:状态/投放/预算 + 面板同款指标列(_hourly_columns 是单行不聚合,含购物成本等派生列)
SNAPSHOT_COLUMNS = {
    "状态": "status",
    "投放状态": "delivery_str",
    "预算": "ROUND(budget/100,2)",
    **_hourly_columns(),
}
_SNAPSHOT_SELECT = ", ".join(f"{expr} AS `{name}`" for name, expr in SNAPSHOT_COLUMNS.items())


class ConfigPullRequest(BaseModel):
    level: Level = Field(..., description="对象层级: ad / adset / campaign")
    ids: list[str] = Field(..., description="该层级对象 ID 列表")
    include_related: bool = Field(True, description="拉取该对象所属系列的整棵树配置")


class ActivitiesPullRequest(BaseModel):
    level: Level = Field(..., description="对象层级: ad / adset / campaign")
    ids: list[str] = Field(..., description="该层级对象 ID 列表")
    date: str = Field(..., description="日期 YYYY-MM-DD(东八区)")
    include_related: bool = Field(True, description="拉取该对象所属系列整棵树的操作记录")


async def _enqueue_pull(
    pull_type: str,
    level: str,
    ids: list[str],
    include_related: bool,
    date: str | None,
    real_name: str,
) -> list[str]:
    """config:在层级实体表按 _id=object_id upsert 出 pending 文档(保留已有 config),
    worker 拉完把整棵树对象各自 upsert 回实体表;
    activities:插 ObjectId 种子文档,worker 回写种子 + 插兄弟文档(共享 request_id)。"""
    now = datetime.now(timezone.utc)
    request_ids: list[str] = []
    for object_id in ids:
        rid = ObjectId()
        if pull_type == "config":
            await LEVEL_COLLECTIONS[level].update_one(
                {"_id": str(object_id)},
                {
                    "$set": {
                        "request_id": str(rid),
                        "level": level,
                        "object_id": str(object_id),
                        "include_related": include_related,
                        "real_name": real_name,
                        "status": "pending",
                        "error": None,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"config": None, "created_at": now},
                },
                upsert=True,
            )
        else:
            seed = {
                "_id": rid,
                "request_id": str(rid),
                "level": level,
                "object_id": object_id,
                "include_related": include_related,
                "real_name": real_name,
                "status": "pending",
                "error": None,
                "created_at": now,
                "updated_at": now,
            }
            if date:
                seed["date"] = date
            await cols.ad_config_activities.insert_one(seed)
        await redis_cli_2.rpush(
            AD_CONFIG_QUEUE_KEY,
            json.dumps(
                {
                    "request_id": str(rid),
                    "pull_type": pull_type,
                    "level": level,
                    "object_id": object_id,
                    "include_related": include_related,
                    "real_name": real_name,
                    "date": date,
                },
                ensure_ascii=False,
            ),
        )
        request_ids.append(str(rid))
    return request_ids


@router.post("/config", response_model=ApiResponse, summary="提交拉取配置任务(广告/组/系列,可选整棵系列树)")
async def pull_ad_config(
    request: ConfigPullRequest,
    current_user: UserModel = Depends(require_roles([Roles.ADMIN])),
):
    if not request.ids:
        return ErrResponse(message="请至少传入一个 ID")
    request_ids = await _enqueue_pull(
        "config",
        request.level,
        request.ids,
        request.include_related,
        None,
        current_user.real_name,
    )
    return ApiResponse(data={"request_ids": request_ids})


@router.post("/operations", response_model=ApiResponse, summary="提交拉取某天 FB 操作记录任务(广告/组/系列,可选整棵系列树)")
async def pull_ad_operations(
    request: ActivitiesPullRequest,
    current_user: UserModel = Depends(require_roles([Roles.ADMIN])),
):
    if not request.ids:
        return ErrResponse(message="请至少传入一个 ID")
    try:
        datetime.strptime(request.date, "%Y-%m-%d")
    except ValueError:
        return ErrResponse(message="日期格式应为 YYYY-MM-DD")
    request_ids = await _enqueue_pull(
        "activities",
        request.level,
        request.ids,
        request.include_related,
        request.date,
        current_user.real_name,
    )
    return ApiResponse(data={"request_ids": request_ids})


class ConfigViewRequest(BaseModel):
    level: Level = Field("ad", description="对象层级: ad / adset / campaign")
    object_id: str = Field(..., description="对象 ID")
    include_related: bool = Field(True, description="拉取该对象所属系列的整棵树配置")
    include_children: bool = Field(False, description="附带返回该对象下已拉取的组/广告配置")


@router.post("/config-view", response_model=ApiResponse, summary="查看对象配置(含所属系列/组):已拉取过直接返回,否则提交拉取")
async def view_config(
    request: ConfigViewRequest,
    current_user: UserModel = Depends(require_roles([Roles.ADMIN])),
):
    """实体表按 _id 直查:有 config → 直接返回,parents 附所属系列/组的已拉取配置;
    正在拉取 → 返回 pending;无记录或上次失败 → 入队新拉取(默认整棵系列树)。"""
    doc = await LEVEL_COLLECTIONS[request.level].find_one({"_id": request.object_id})
    if doc and doc.get("config") is not None:
        parents = []
        # campaign 文档的 campaign_id 是它自己,跳过避免把自己当 parent
        for lvl, oid in (("campaign", doc.get("campaign_id")), ("adset", doc.get("ad_set_id"))):
            if not oid or oid == request.object_id:
                continue
            p = await LEVEL_COLLECTIONS[lvl].find_one(
                {"_id": oid, "config": {"$ne": None}}
            )
            if p:
                parents.append(p)
        children = []
        if request.include_children and request.level != "ad":
            child_specs = (
                [("adset", "campaign_id"), ("ad", "campaign_id")]
                if request.level == "campaign"
                else [("ad", "ad_set_id")]
            )
            for lvl, fk in child_specs:
                async for c in (
                    LEVEL_COLLECTIONS[lvl]
                    .find({fk: request.object_id, "config": {"$ne": None}})
                    .sort("_id", 1)
                ):
                    children.append(c)
        return ApiResponse(
            data={"status": "done", "object": doc, "parents": parents, "children": children}
        )
    if doc and doc.get("status") == "pending":
        return ApiResponse(
            data={"status": "pending", "request_id": doc.get("request_id")}
        )
    request_ids = await _enqueue_pull(
        "config",
        request.level,
        [request.object_id],
        request.include_related,
        None,
        current_user.real_name,
    )
    return ApiResponse(data={"status": "pending", "request_id": request_ids[0]})


@router.get("/records", response_model=ApiResponse, summary="已拉取对象列表(不含 config/activities 大字段)")
async def list_pull_records(
    pull_type: str = "config",
    object_id: str | None = None,
    level: str | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: UserModel = Depends(require_roles([Roles.ADMIN])),
):
    if pull_type == "activities":
        query: dict = {}
        if object_id:
            query["object_id"] = object_id
        if level:
            query["level"] = level
        total = await cols.ad_config_activities.count_documents(query)
        cursor = (
            cols.ad_config_activities.find(query, {"activities": 0})
            .sort("created_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        items = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc["pull_type"] = pull_type
            items.append(doc)
        return ApiResponse(
            data={"items": items, "total": total, "page": page, "page_size": page_size}
        )

    if pull_type != "config":
        return ErrResponse(message="pull_type 应为 config / activities")

    # config 分三张实体表:指定 level 查单表,否则三表合并按更新时间倒序
    query = {}
    if object_id:
        query["_id"] = object_id
    colls = (
        [LEVEL_COLLECTIONS[level]]
        if level in LEVEL_COLLECTIONS
        else list(LEVEL_COLLECTIONS.values())
    )
    total = 0
    merged: list[dict] = []
    for coll in colls:
        total += await coll.count_documents(query)
        async for doc in (
            coll.find(query, {"config": 0}).sort("updated_at", -1).limit(page * page_size)
        ):
            doc["pull_type"] = pull_type
            merged.append(doc)
    merged.sort(
        key=lambda d: d.get("updated_at") or d.get("created_at") or datetime.min,
        reverse=True,
    )
    items = merged[(page - 1) * page_size : page * page_size]
    return ApiResponse(
        data={"items": items, "total": total, "page": page, "page_size": page_size}
    )


@router.get("/result/{request_id}", response_model=ApiResponse, summary="按提交批次查完整结果(同一次拉取的所有对象)")
async def get_pull_result(
    request_id: str,
    pull_type: str = "config",
    current_user: UserModel = Depends(require_roles([Roles.ADMIN])),
):
    if pull_type == "activities":
        objects = []
        async for obj in cols.ad_config_activities.find({"request_id": request_id}).sort(
            [("level", 1), ("created_at", 1)]
        ):
            obj["_id"] = str(obj["_id"])
            objects.append(obj)
        return ApiResponse(data={"objects": objects})

    if pull_type != "config":
        return ErrResponse(message="pull_type 应为 config / activities")

    # 实体表 upsert 后 request_id 反映"最后一次触碰该对象的批次"
    objects = []
    for coll in LEVEL_COLLECTIONS.values():
        async for obj in coll.find({"request_id": request_id}):
            objects.append(obj)
    objects.sort(key=lambda o: (o.get("level") or "", str(o.get("object_id") or "")))
    return ApiResponse(data={"objects": objects})


class OperationsViewRequest(BaseModel):
    level: Level = Field("ad", description="对象层级: ad / adset / campaign")
    object_id: str = Field(..., description="对象 ID")
    date: str = Field(..., description="日期 YYYY-MM-DD(东八区),多天范围传最后一天")
    force: bool = Field(False, description="强制重拉:无视封存/刷新间隔直接入队")
    find_latest: bool = Field(
        False, description="从 date 逐天回溯到该对象最近一次有操作的天(上限 30 天)"
    )


def _china_str(dt) -> str | None:
    """mongo 存的 UTC 时间转中国时间字符串,用于展示上次拉取时间。"""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


def _event_time_to_china(v) -> datetime | None:
    """FB activity event_time(unix 或 ISO 带时区)转东八区 naive datetime,用于比 china_date。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        dt = datetime.fromtimestamp(v, tz=timezone.utc)
    else:
        s = str(v).strip()
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_SHANGHAI).replace(tzinfo=None)


async def _snapshot_at(db: AsyncMySQL, level: str, object_id: str, t_china: datetime) -> dict | None:
    """取该对象在操作时刻(东八区)之前、当天最新的一条 half_hour 行 = 当时的数据状态。
    必须带 level:同一 campaign_id 下系列/组/广告三层都各有一行,不加 level 会抓错行。"""
    id_col = LEVEL_ID_COLUMN[level]
    sql = (
        f"SELECT {_SNAPSHOT_SELECT} FROM ad_half_hour_detail "
        f"WHERE {id_col} = %s AND level = %s "
        f"AND china_date <= %s AND china_date >= %s "
        f"ORDER BY china_date DESC LIMIT 1"
    )
    return await db.fetchone(
        sql,
        [object_id, level, t_china.strftime("%Y-%m-%d %H:%M:%S"), t_china.strftime("%Y-%m-%d 00:00:00")],
        as_dict=True,
    )


async def _resolve_account_id(db: AsyncMySQL, level: str, object_id: str) -> str | None:
    """从 doris 反查该对象所属账户(activities 只能按账户拉)。"""
    id_col = LEVEL_ID_COLUMN[level]
    row = await db.fetchone(
        f"SELECT account_id FROM ad_daily_detail WHERE level = 'ad' AND {id_col} = %s "
        f"ORDER BY date DESC LIMIT 1",
        [object_id],
        as_dict=True,
    )
    return str(row["account_id"]) if row and row.get("account_id") else None


async def _enqueue_activity_day(account_id: str, date: str, real_name: str) -> None:
    await redis_cli_2.rpush(
        AD_CONFIG_QUEUE_KEY,
        json.dumps(
            {"pull_type": "activity_day", "account_id": account_id, "date": date, "real_name": real_name},
            ensure_ascii=False,
        ),
    )


def _parse_change(raw) -> tuple[str, str, str]:
    """解析 extra_data,返回 (变更展示, 变更前, 变更后)。
    - 预算(payment_amount):金额分转元、带币种,变更展示人类可读
    - 开启关闭(run_status)等顶层 old_value/new_value 是可读串:前后单独给,变更展示保持原样
    - 其他:原样返回,前后留空
    """
    if not raw:
        return "", "", ""
    try:
        d = json.loads(raw)
    except (ValueError, TypeError):
        return str(raw), "", ""
    ov, nv = d.get("old_value"), d.get("new_value")
    if isinstance(ov, dict) or isinstance(nv, dict):
        ovd, nvd = ov or {}, nv or {}
        if "payment_amount" in (ovd.get("type"), nvd.get("type")):
            cur = nvd.get("currency") or ovd.get("currency") or ""
            before = f"{(ovd.get('old_value') or 0) / 100:.2f} {cur}".strip()
            after = f"{(nvd.get('new_value') or 0) / 100:.2f} {cur}".strip()
            label = nvd.get("additional_value") or ovd.get("additional_value") or ""
            disp = f"{before} → {after}" + (f"({label})" if label else "")
            return disp, before, after
        return str(raw), "", ""
    # 顶层 old_value/new_value 为可读串(如开启关闭)
    before = "" if ov is None else str(ov)
    after = "" if nv is None else str(nv)
    return str(raw), before, after


async def _build_records(db: AsyncMySQL, level: str, object_id: str, activities: list) -> list:
    """从账户当天全部记录里筛出本对象的,按操作时点补 half_hour 快照,解析变更前后,倒序。"""
    records = [a for a in activities if str(a.get("object_id") or "") == str(object_id)]
    for act in records:
        t_china = _event_time_to_china(act.get("event_time"))
        act["event_time_china"] = t_china.strftime("%Y-%m-%d %H:%M:%S") if t_china else None
        act["snapshot"] = (
            await _snapshot_at(db, level, object_id, t_china) if t_china else None
        )
        disp, before, after = _parse_change(act.get("extra_data"))
        act["change"] = disp
        act["change_before"] = before
        act["change_after"] = after
    records.sort(key=lambda a: str(a.get("event_time") or ""), reverse=True)
    return records


async def _view_latest_operations(
    db: AsyncMySQL, request: OperationsViewRequest, account_id: str, real_name: str
) -> ApiResponse:
    """从 request.date 逐天回溯找该对象最近一次有操作的天。已缓存的天(含封存)只读
    Mongo 不打 FB;遇到未缓存的天入队账户级拉取并返回 pending,由前端轮询推进。"""
    now = datetime.now(timezone.utc)
    start = datetime.strptime(request.date, "%Y-%m-%d")
    for i in range(WALK_BACK_MAX_DAYS):
        day = (start - timedelta(days=i)).strftime("%Y-%m-%d")
        doc = await cols.ad_config_activity_days.find_one({"account_id": account_id, "date": day})
        if doc is None or (doc.get("activities") is None and doc.get("status") == "failed"):
            await _enqueue_activity_day(account_id, day, real_name)
            await cols.ad_config_activity_days.update_one(
                {"account_id": account_id, "date": day},
                {
                    "$set": {"status": "pending", "error": None, "refresh_enqueued_at": now},
                    "$setOnInsert": {"activities": None, "sealed": False, "created_at": now},
                },
                upsert=True,
            )
            return ApiResponse(data={"status": "pending", "probe_date": day})
        if doc.get("activities") is None:
            return ApiResponse(data={"status": "pending", "probe_date": day})
        if any(
            str(a.get("object_id") or "") == str(request.object_id)
            for a in doc["activities"]
        ):
            records = await _build_records(db, request.level, request.object_id, doc["activities"])
            return ApiResponse(
                data={
                    "status": "done",
                    "records": records,
                    "snapshot_columns": list(SNAPSHOT_COLUMNS),
                    "updated_at": _china_str(doc.get("updated_at")),
                    "found_date": day,
                }
            )
    return ApiResponse(
        data={
            "status": "done",
            "records": [],
            "snapshot_columns": list(SNAPSHOT_COLUMNS),
            "updated_at": None,
            "found_date": None,
            "searched_days": WALK_BACK_MAX_DAYS,
        }
    )


@router.post("/operations-view", response_model=ApiResponse, summary="查看对象某天操作记录(每条附操作时点的成效快照):按账户+天缓存,已封存的天直接读不重拉")
async def view_operations(
    request: OperationsViewRequest,
    current_user: UserModel = Depends(require_roles([Roles.ADMIN])),
    db: AsyncMySQL = Depends(get_db),
):
    """按(账户+天)缓存整天操作记录(worker 一次账户级拉取拆给当天所有对象共用):
    - 已缓存且 sealed(该天在账户时区已过,不会再有操作)→ 直接读,不调 FB
    - 已缓存但未封存(仍是账户当天)→ 直接返回旧数据,并在超过刷新间隔时后台再拉一次更新
    - 没缓存 / 上次失败 → 入队拉取,返回 pending
    """
    try:
        datetime.strptime(request.date, "%Y-%m-%d")
    except ValueError:
        return ErrResponse(message="日期格式应为 YYYY-MM-DD")

    account_id = await _resolve_account_id(db, request.level, request.object_id)
    if not account_id:
        return ErrResponse(message="未找到该对象所属账户(doris 无记录)")

    if request.find_latest and not request.force:
        return await _view_latest_operations(db, request, account_id, current_user.real_name)

    now = datetime.now(timezone.utc)
    doc = await cols.ad_config_activity_days.find_one({"account_id": account_id, "date": request.date})

    # 强制触发:无视封存/节流直接入队重拉;不覆盖 updated_at(上次真实拉取时间保留)
    if request.force:
        await _enqueue_activity_day(account_id, request.date, current_user.real_name)
        await cols.ad_config_activity_days.update_one(
            {"account_id": account_id, "date": request.date},
            {
                "$set": {"error": None, "refresh_enqueued_at": now}
                | ({} if doc and doc.get("activities") is not None else {"status": "pending"}),
                "$setOnInsert": {"activities": None, "sealed": False, "created_at": now},
            },
            upsert=True,
        )
        doc = await cols.ad_config_activity_days.find_one({"account_id": account_id, "date": request.date})

    updated_at = _china_str(doc.get("updated_at")) if doc else None

    if doc is None or (doc.get("activities") is None and doc.get("status") == "failed"):
        if not request.force:
            await _enqueue_activity_day(account_id, request.date, current_user.real_name)
            await cols.ad_config_activity_days.update_one(
                {"account_id": account_id, "date": request.date},
                {
                    "$set": {"status": "pending", "error": None, "refresh_enqueued_at": now},
                    "$setOnInsert": {"activities": None, "sealed": False, "created_at": now},
                },
                upsert=True,
            )
        return ApiResponse(data={"status": "pending", "updated_at": updated_at})

    if doc.get("activities") is None:
        return ApiResponse(data={"status": "pending", "updated_at": updated_at})

    # 有缓存数据:未封存且超过刷新间隔 → 后台再拉一次(不阻塞,旧数据先返回)
    if not request.force and not doc.get("sealed"):
        last = doc.get("refresh_enqueued_at") or doc.get("updated_at")
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last is None or (now - last).total_seconds() > ACTIVITY_DAY_REFRESH_TTL_SECONDS:
            await _enqueue_activity_day(account_id, request.date, current_user.real_name)
            await cols.ad_config_activity_days.update_one(
                {"_id": doc["_id"]}, {"$set": {"refresh_enqueued_at": now}}
            )

    records = await _build_records(db, request.level, request.object_id, doc["activities"])
    return ApiResponse(
        data={
            "status": "done",
            "records": records,
            "snapshot_columns": list(SNAPSHOT_COLUMNS),
            "updated_at": updated_at,
        }
    )
