import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Optional
from app.conf.api_conf import get_proxies
from bson import ObjectId
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.api import FacebookAdsApi, FacebookSession
from facebook_business.exceptions import FacebookRequestError
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from pymongo import UpdateOne

from app.core.security import auth_current_user
from app.db.clients import get_db, redis_cli_2 as redis_db
from app.db.mongo import cols, user_cols
from app.model_type_defs.common_models import ApiResponse, ErrResponse
from app.model_type_defs.user_models import Roles, UserModel, DEPT_ALL
from app.services import fb_asset_assignment as assignment_service
from app.services.fb_common import TokenType, push_personal_to_sync_queue
from app.services.fb_page_service import (
    assign_pages_for_keys,
    filter_pools_by_name,
    get_personal_pages_by_key,
)

TZ_CST = timezone(timedelta(hours=8))
APPLICATION_FIELDS = ["id", "name", "object_store_urls", "supported_platforms"]
APPLICATIONS_FETCH_TIMEOUT = 15
APPLICATIONS_FETCH_CONCURRENCY = 10
# FB 调用专用线程池：不与全局 asyncio.to_thread（上传/哈希/minio 等阻塞活儿）共享，
# 避免共享池被占满后 FB 请求排队、wait_for 计时空转导致误超时
_FB_EXECUTOR = ThreadPoolExecutor(
    max_workers=APPLICATIONS_FETCH_CONCURRENCY, thread_name_prefix="fb-apps"
)



router = APIRouter(prefix="/fb_resource", tags=["fb_resource"])

# MongoDB 集合
user_col = user_cols.user
personal_accounts_col = cols.personal_accounts
fb_ad_accounts_col = cols.fb_ad_accounts
fb_businesss_col = cols.fb_businesses
fb_pages_col = cols.fb_pages
fb_pixels_col = cols.fb_pixels
accounts_col = cols.accounts
materials_col = cols.materials


class PaginatedResponse(BaseModel):
    """分页响应数据结构"""

    total: int
    items: list
    page: int
    page_size: int


class BaseQuery(BaseModel):
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(10, description="每页数量")
    id: Optional[List[str]] = Field(None, description="多个ID 精确查询")
    name: Optional[str] = Field(None, description="名称模糊查询")
    sort_by: Optional[str] = Field(None, description="排序字段")
    sort_order: Optional[str] = Field(None, description="排序方向")
    status: Optional[bool] = Field(None, description="筛选个号状态")
    user_name: Optional[str] = Field(None, description="用户名称模糊查询")


class BusinessQuery(BaseModel):
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(10, description="每页数量")
    id: Optional[str] = Field(None, description="ID 精确查询")
    name: Optional[str] = Field(None, description="名称模糊查询")
    personal_id: Optional[str] = Field(None, description="个号 ID 精确查询")


class TargetAccount(BaseModel):
    account_id: str
    pixel_ids: List[str] = []  # 缺省只拉户本身;指定则合并进该户像素列表


class SyncTargets(BaseModel):
    accounts: List[TargetAccount] = []
    page_ids: List[str] = []


class PersonalQuery(BaseModel):
    personal_id: str
    personal_type: TokenType
    # 非空时定向同步指定资产,不做全量同步
    targets: Optional[SyncTargets] = None

    @field_validator("personal_type", mode="before")
    @classmethod
    def _normalize_personal_type(cls, v):
        if v == "system":
            return TokenType.SYSTEM_USER
        return v


class PersonalProgress(BaseModel):
    personal_ids: List[str]


def safe_int(value) -> int:
    """将 Redis 返回值安全转为 int，异常时返回 0。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def base_mongo_query(
    collection,
    page: int,
    page_size: int,
    query: dict,
    projection: Optional[dict] = None,
    sort_field: str = "updated_at",
    sort_order: str = "desc",
) -> dict:
    """
    通用 MongoDB 分页查询方法
    """
    sort_dir = 1 if sort_order == "asc" else -1
    skip = (page - 1) * page_size
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query, projection)
        .sort(sort_field, sort_dir)
        .skip(skip)
        .limit(page_size)
    )
    items = await cursor.to_list(length=page_size)

    for item in items:
        if "_id" in item and item["_id"] is not None:
            item["_id"] = str(item["_id"])

    return {
        "total": total,
        "items": items,
        "page": page,
        "page_size": page_size,
    }


async def _visible_personal_user_names(
    current_user: UserModel,
) -> Optional[list[str]]:
    """个号可见范围: admin 不限(None); operator_leader 为本部门用户; 其余仅本人"""
    if Roles.ADMIN in current_user.roles:
        return None
    if Roles.OPERATOR_LEADER in current_user.roles:
        users = await user_col.find(
            {"department": current_user.department}, {"real_name": 1}
        ).to_list(length=None)
        return [u["real_name"] for u in users if u.get("real_name")]
    return [current_user.real_name]


async def _visible_asset_ids(
    current_user: UserModel, field: str
) -> Optional[list[str]]:
    """可见个号名下 field(accounts/pages/pixels) 的资产 id 列表; None 表示不限制"""
    user_names = await _visible_personal_user_names(current_user)
    if user_names is None:
        return None
    docs = await personal_accounts_col.find(
        {"user_name": {"$in": user_names}}, {f"{field}.id": 1}
    ).to_list(length=None)
    return [item["id"] for d in docs for item in d.get(field, []) if item.get("id")]


@router.get("/personal_accounts", response_model=ApiResponse, summary="查询个人号列表")
async def get_personal_accounts(
    query: Annotated[BaseQuery, Query()],
    current_user: UserModel = Depends(auth_current_user),
):
    """
    - 无条件：返回全部，分页
    - _id：精确匹配
    - name：模糊匹配（正则，不区分大小写）
    - 隐藏敏感字段：access_token, app_secret
    """
    projection = {
        "_id": 1,
        "name": 1,
        "app_id": 1,
        "accounts": 1,
        "business": 1,
        "pages": 1,
        "updated_at": 1,
        "status": 1,
        "user_name": 1
    }
    mongo_query = {}
    if query.id:
        mongo_query["_id"] = {"$in": query.id}
    if query.name:
        mongo_query["name"] = {"$regex": re.escape(query.name), "$options": "i"}
    if isinstance(query.status, bool):
        mongo_query["status"] = query.status
    if query.user_name:
        mongo_query["user_name"] = {"$regex": re.escape(query.user_name), "$options": "i"}
    # 权限: 非 admin 只能看到可见范围内的个号
    visible_names = await _visible_personal_user_names(current_user)
    if visible_names is not None:
        if query.user_name:
            kw = query.user_name.lower()
            visible_names = [n for n in visible_names if kw in n.lower()]
        mongo_query["user_name"] = {"$in": visible_names}
    result = await base_mongo_query(
        personal_accounts_col, query.page, query.page_size, mongo_query, projection
    )
    return ApiResponse(data=result)


@router.get("/ad_accounts", response_model=ApiResponse, summary="查询广告账户列表")
async def get_ad_accounts(
    query: Annotated[BaseQuery, Query()],
    current_user: UserModel = Depends(auth_current_user),
):
    """
    - _id：精确匹配
    - name：模糊匹配（正则，不区分大小写）
    """
    projection = {
        "_id": 1,
        "account_status": 1,
        "age": 1,
        "amount_spent": 1,
        "currency": 1,
        "disable_reason": 1,
        "is_prepay_account": 1,
        "name": 1,
        "owner": 1,
        "pixels": 1,
        "spend_cap": 1,
        "tax_id_status": 1,
        "timezone_name": 1,
        "account_dsl": 1,
        "updated_at": 1,
    }
    mongo_query = {}
    if query.id:
        mongo_query["_id"] = {"$in": query.id}
    if query.name:
        mongo_query["name"] = {"$regex": re.escape(query.name), "$options": "i"}
    # 权限: 非 admin 只能看到可见个号名下的广告账户
    allowed_ids = await _visible_asset_ids(current_user, "accounts")
    if allowed_ids is not None:
        if query.id:
            allowed_ids = [i for i in allowed_ids if i in query.id]
        mongo_query["_id"] = {"$in": allowed_ids}
    raw_sort_by = query.sort_by
    raw_sort_order = query.sort_order
    sort_by = raw_sort_by if raw_sort_by == "updated_at" else "updated_at"
    sort_order = "asc" if raw_sort_order in ("asc", "ascend") else "desc"

    requested_ids = list(dict.fromkeys(query.id or []))
    matched_ids = []
    missing_ids = []
    if requested_ids:
        matched_id_set = {
            str(item_id)
            for item_id in await fb_ad_accounts_col.distinct("_id", mongo_query)
        }
        matched_ids = [item_id for item_id in requested_ids if item_id in matched_id_set]
        missing_ids = [item_id for item_id in requested_ids if item_id not in matched_id_set]

    result = await base_mongo_query(
        fb_ad_accounts_col,
        query.page,
        query.page_size,
        mongo_query,
        projection,
        sort_field=sort_by,
        sort_order=sort_order,
    )
    result["matched_ids"] = matched_ids
    result["missing_ids"] = missing_ids

    message = "部分 ID 未匹配" if missing_ids else "Success"
    return ApiResponse(data=result, message=message)


@router.get(
    "/ad_accounts/available",
    response_model=ApiResponse,
    summary="查询当前用户可见的可用广告账户",
)
async def get_available_ad_accounts(
    current_user: UserModel = Depends(auth_current_user),
):
    """按个号分组返回名下 account_status=1 的广告账户，不分页:
    items: [{personal_id, personal_name, ad_accounts: [{id, name}]}]
    个号可见范围: admin 全部 / leader 本部门用户 / 其余按本人 real_name 查个号"""
    mongo_query: dict = {"status": True}
    visible_names = await _visible_personal_user_names(current_user)
    if visible_names is not None:
        mongo_query["user_name"] = {"$in": visible_names}
    personals = await personal_accounts_col.find(
        mongo_query, {"name": 1, "accounts.id": 1}
    ).to_list(length=None)

    all_ids = [
        a["id"] for p in personals for a in p.get("accounts", []) if a.get("id")
    ]
    active = {
        doc["_id"]: doc.get("name")
        async for doc in fb_ad_accounts_col.find(
            {"_id": {"$in": all_ids}, "account_status": 1}, {"name": 1}
        )
    }
    items = [
        {
            "personal_id": p["_id"],
            "personal_name": p.get("name"),
            "ad_accounts": [
                {"id": a["id"], "name": active[a["id"]]}
                for a in p.get("accounts", [])
                if a.get("id") in active
            ],
        }
        for p in personals
    ]
    return ApiResponse(data={"total": len(items), "items": items})


@router.get("/businesss", response_model=ApiResponse, summary="查询 BM 列表")
async def get_businesss(
    query: BusinessQuery = Depends(),
    current_user: UserModel = Depends(auth_current_user),
):
    """
    查询 BM（Business Manager）列表

    - 无条件：返回全部，分页
    - facebook_id：按个号 ID 精确匹配
    - business_id：按 BM ID 精确匹配
    - facebook_id + business_id：拼接为 _id 精确查询
    - business_name：模糊匹配（正则，不区分大小写）
    """
    projection = {
        "_id": 1,
        "accounts": 1,
        "business_id": 1,
        "business_name": 1,
        "facebook_id": 1,
        "pages": 1,
        "pixels": 1,
        "updated_at": 1,
    }
    mongo_query = {}
    if query.personal_id and query.id:
        mongo_query["_id"] = f"{query.id}_{query.personal_id}"
    else:
        if query.personal_id:
            mongo_query["_id"] = {"$regex": f"_{re.escape(query.personal_id)}$"}
        if query.id:
            mongo_query["business_id"] = query.id
        if query.name:
            mongo_query["business_name"] = {
                "$regex": re.escape(query.name),
                "$options": "i",
            }
    # 权限: 非 admin 只能看到可见个号名下的 BM (doc_id = 个号 _id)
    user_names = await _visible_personal_user_names(current_user)
    if user_names is not None:
        personal_ids = await personal_accounts_col.distinct(
            "_id", {"user_name": {"$in": user_names}}
        )
        mongo_query["doc_id"] = {"$in": personal_ids}
    result = await base_mongo_query(
        fb_businesss_col, query.page, query.page_size, mongo_query, projection
    )
    for item in result["items"]:
        item["facebook_id"] = item["_id"].split("_", 1)[1]

    return ApiResponse(data=result)


@router.get("/pages", response_model=ApiResponse, summary="查询主页列表")
async def get_pages(
    query: Annotated[BaseQuery, Query()],
    current_user: UserModel = Depends(auth_current_user),
):
    """
    查询主页列表

    - 无条件：返回全部，分页
    - _id：精确匹配
    - name：模糊匹配（正则，不区分大小写）
    """
    projection = {
        "_id": 1,
        "can_post": 1,
        "category": 1,
        "fan_count": 1,
        "followers_count": 1,
        "is_published": 1,
        "is_unclaimed": 1,
        "link": 1,
        "name": 1,
        "new_like_count": 1,
        "talking_about_count": 1,
        "updated_at": 1,
        "username": 1,
        "verification_status": 1,
        "picture": 1,
    }
    mongo_query = {}
    if query.id:
        mongo_query["_id"] = {"$in": query.id}
    if query.name:
        mongo_query["name"] = {"$regex": re.escape(query.name), "$options": "i"}
    # 权限: 非 admin 只能看到可见个号名下的主页
    allowed_ids = await _visible_asset_ids(current_user, "pages")
    if allowed_ids is not None:
        if query.id:
            allowed_ids = [i for i in allowed_ids if i in query.id]
        mongo_query["_id"] = {"$in": allowed_ids}
    result = await base_mongo_query(
        fb_pages_col, query.page, query.page_size, mongo_query, projection
    )

    return ApiResponse(data=result)


@router.get(
    "/personal-pages", response_model=ApiResponse, summary="按个号批量分配/查询主页"
)
async def get_personal_pages(
    personal_ids: List[str] = Query(
        ..., description="个号 key 列表,允许重复;按行顺序传入,返回 items 与之 1:1"
    ),
    name: Optional[str] = None,
    current_user: UserModel = Depends(auth_current_user),
):
    """按行随机分配主页 + 返回每个个号的候选池。

    返回:
      items: 与 personal_ids 等长,每项 {personal_id, page} —— page 为 null 表示该个号无可用主页。
             分配策略:跨整批尽量不重复(use_count 最小者优先,同票随机)。
      pools: {personal_id: [page, ...]} —— 仅去重 key,供前端下拉框做候选;name 命中时已过滤。
    """
    keys = [pid for pid in personal_ids if pid]
    if not keys:
        return ApiResponse(data={"items": [], "pools": {}})

    scope_dept = current_user.department
    scope_user_id = None if Roles.ADMIN in current_user.roles else current_user.id
    pools = await get_personal_pages_by_key(keys, scope_dept, scope_user_id)
    pools = filter_pools_by_name(pools, name)
    chosen = assign_pages_for_keys(keys, pools)

    def _slim(p: dict | None) -> dict | None:
        if not p:
            return None
        return {
            "id": p.get("_id"),
            "name": p.get("name"),
            "picture": p.get("picture", ""),
        }

    items = [
        {"personal_id": k, "page": _slim(chosen[i])} for i, k in enumerate(keys)
    ]
    pools_out = {
        k: [_slim(p) for p in pages] for k, pages in pools.items()
    }
    return ApiResponse(data={"items": items, "pools": pools_out})


@router.get("/posts", response_model=ApiResponse, summary="查询原贴列表")
async def get_posts(
    query: Annotated[BaseQuery, Query()],
    current_user: UserModel = Depends(auth_current_user),
    db=Depends(get_db),
):
    """
    根据主页查询原贴,
    从ad_hourly_detail 中查询
    """
    page = query.page
    page_size = query.page_size
    offset = (page - 1) * page_size
    page_ids = query.id or []
    placeholders = ",".join(["%s"] * len(page_ids))

    total_sql = """
        SELECT COUNT(DISTINCT CONCAT(page_id, '_', post_id)) AS total
        FROM ad_hourly_detail
        WHERE page_id IN ({placeholders}) AND post_id IS NOT NULL AND post_id != ''
    """.format(placeholders=placeholders or "NULL")
    list_sql = """
        SELECT
            ANY_VALUE(ad_name) AS name,
            page_id,
            post_id,
            ANY_VALUE(unique_name) AS unique_name
        FROM ad_hourly_detail
        WHERE page_id IN ({placeholders}) AND post_id IS NOT NULL AND post_id != ''
        GROUP BY page_id, post_id
        ORDER BY post_id DESC
        LIMIT %s OFFSET %s
    """.format(placeholders=placeholders or "NULL")

    total_row = await db.fetchone(total_sql, tuple(page_ids), as_dict=True)
    items = await db.fetchall(
        list_sql, (*page_ids, page_size, offset), as_dict=True
    )
    total = total_row["total"]
    unique_names = {item["unique_name"] for item in items if item.get("unique_name")}
    thumb_map = {}
    if unique_names:
        async for doc in materials_col.find(
            {"basename": {"$in": list(unique_names)}},
            {"basename": 1, "img": 1, "_id": 0},
        ):
            thumb_map[doc["basename"]] = doc.get("img")
    for item in items:
        item["thumbnail"] = thumb_map.get(item.pop("unique_name"))

    result = {
        "total": total,
        "items": items,
        "page": page,
        "page_size": page_size,
    }

    return ApiResponse(data=result)


@router.get("/pixels", response_model=ApiResponse, summary="查询像素列表")
async def get_pixels(
    query: Annotated[BaseQuery, Query()],
    current_user: UserModel = Depends(auth_current_user),
):
    """
    查询像素列表

    - 无条件：返回全部，分页
    - _id：精确匹配
    - name：模糊匹配（正则，不区分大小写）
    """
    projection = {
        "_id": 1,
        "data_use_setting": 1,
        "is_unavailable": 1,
        "last_fired_time": 1,
        "name": 1,
        "owner_business": 1,
        "updated_at": 1,
    }
    mongo_query = {}
    if query.id:
        mongo_query["_id"] = {"$in": query.id}
    if query.name:
        mongo_query["name"] = {"$regex": re.escape(query.name), "$options": "i"}
    # 权限: 非 admin 只能看到可见个号名下广告账户下的像素 (像素归属于户)
    account_ids = await _visible_asset_ids(current_user, "accounts")
    if account_ids is not None:
        accounts = await fb_ad_accounts_col.find(
            {"_id": {"$in": account_ids}}, {"pixels.id": 1}
        ).to_list(length=None)
        allowed_ids = [
            px["id"] for a in accounts for px in a.get("pixels", []) if px.get("id")
        ]
        if query.id:
            allowed_ids = [i for i in allowed_ids if i in query.id]
        mongo_query["_id"] = {"$in": allowed_ids}
    result = await base_mongo_query(
        fb_pixels_col, query.page, query.page_size, mongo_query, projection
    )

    return ApiResponse(data=result)


def _is_today_cst(dt: Optional[datetime]) -> bool:
    if not dt:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ_CST)
    return dt.astimezone(TZ_CST).date() == datetime.now(TZ_CST).date()


class ApplicationsSyncItem(BaseModel):
    personal_id: str = Field(..., description="执行个号 ID(facebook_id 或系统开发者 _id)")
    ad_account_ids: List[str] = Field(
        ..., min_length=1, description="该号下要同步的广告账户 ID 列表"
    )


class ApplicationsSyncRequest(BaseModel):
    items: List[ApplicationsSyncItem] = Field(..., min_length=1, description="按个号分组的同步任务")
    personal_type: TokenType = Field(..., description="个号类型: personal / system_user")
    force_refresh: bool = Field(False, description="强制刷新,跳过缓存与当日防抖")


async def _resolve_token_proxy(
    personal_id: str, personal_type: TokenType
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """返回 (access_token, app_id, app_secret, proxy, error_msg)."""
    if personal_type == TokenType.PERSONAL:
        personal = await personal_accounts_col.find_one(
            {"_id": personal_id, "status": True},
            {"access_token": 1, "app_id": 1,},
        )
        if not personal:
            return None, None, None, None, "未找到对应启用状态的个人号"
        dev = await accounts_col.find_one(
            {"app_id": personal["app_id"], "status": 1},
            {"proxy": 1, "app_secret": 1},
        )
        proxy = dev.get("proxy") if dev else None
        # personal_accounts.app_secret 可能为空,从 accounts 兜底
        app_secret = dev.get("app_secret") if dev else None
        return personal["access_token"], personal["app_id"], app_secret, proxy, None

    dev = await accounts_col.find_one(
        {"_id": ObjectId(personal_id), "status": 1},
        {"access_token": 1, "app_id": 1, "app_secret": 1, "proxy": 1},
    )
    if not dev:
        return None, None, None, None, "未找到对应启用状态的系统开发者"
    return (
        dev.get("access_token"),
        dev.get("app_id"),
        dev.get("app_secret"),
        dev.get("proxy"),
        None,
    )


def _fetch_applications_sync(
    ad_account_id: str,
    app_id: str,
    app_secret: str,
    access_token: str,
    proxy: Optional[str],
) -> dict:
    session = FacebookSession(
        app_id,
        app_secret,
        access_token,
        proxies=get_proxies(proxy_host=proxy),
        timeout=APPLICATIONS_FETCH_TIMEOUT,
    )
    api = FacebookAdsApi(session)
    account = AdAccount(f"act_{ad_account_id}", api=api)
    try:
        cursor = account.get_applications(fields=APPLICATION_FIELDS)
        applications = [dict(app) for app in cursor]
        return {"ad_account_id": ad_account_id, "applications": applications}
    except FacebookRequestError as e:
        return {"ad_account_id": ad_account_id, "error": e.api_error_message() or str(e)}


async def _fetch_account_applications(
    ad_account_id: str,
    app_id: str,
    app_secret: str,
    access_token: str,
    proxy: Optional[str],
) -> dict:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                _FB_EXECUTOR,
                _fetch_applications_sync,
                ad_account_id, app_id, app_secret, access_token, proxy,
            ),
            timeout=APPLICATIONS_FETCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return {"ad_account_id": ad_account_id, "error": "FB API 请求超时"}


async def _process_group(
    item: ApplicationsSyncItem,
    force_refresh: bool,
    personal_type: TokenType,
    semaphore: asyncio.Semaphore,
) -> List[dict]:
    """单个开发者下的户串行处理,共用 token/proxy."""
    aids = list(dict.fromkeys(item.ad_account_ids))
    sub: List[dict] = []

    docs: dict = {}
    async for d in fb_ad_accounts_col.find(
        {"_id": {"$in": aids}},
        {"_id": 1, "applications": 1, "updated_at": 1},
    ):
        docs[d["_id"]] = d

    need_fetch: List[str] = []
    for aid in aids:
        ad = docs[aid]

        if not force_refresh and "applications" in ad:
            sub.append({
                "ad_account_id": aid,
                "applications": ad.get("applications", []),
                "from_cache": True,
            })
            continue
        if not force_refresh and _is_today_cst(ad.get("updated_at")):
            sub.append({
                "ad_account_id": aid,
                "error": "当日已请求过该账户,可使用强制刷新",
            })
            continue
        need_fetch.append(aid)

    if not need_fetch:
        return sub

    access_token, app_id, app_secret, proxy, err = await _resolve_token_proxy(
        item.personal_id, personal_type
    )
    if err or not access_token or not app_secret or not app_id:
        for aid in need_fetch:
            sub.append({
                "ad_account_id": aid,
                "error": err or "无可用 app_id / app_secret / access_token",
            })
        return sub

    async with semaphore:
        bulk_ops = []
        now = datetime.now(TZ_CST)
        for aid in need_fetch:
            r = await _fetch_account_applications(
                aid, app_id, app_secret, access_token, proxy
            )
            if "applications" in r:
                bulk_ops.append(
                    UpdateOne(
                        {"_id": aid},
                        {"$set": {
                            "applications": r["applications"],
                            "updated_at": now,
                        }},
                    )
                )
                sub.append({**r, "from_cache": False})
            else:
                bulk_ops.append(
                    UpdateOne(
                        {"_id": aid},
                        {"$set": {"updated_at": now}},
                    )
                )
                sub.append(r)
        if bulk_ops:
            await fb_ad_accounts_col.bulk_write(bulk_ops)

    return sub


@router.post(
    "/ad_accounts/applications/sync",
    response_model=ApiResponse,
    summary="批量同步广告账户绑定的应用列表",
)
async def sync_ad_account_applications(
    payload: ApplicationsSyncRequest,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    并发策略:
    - 按 items(开发者/个号) 维度并发,Semaphore 限制开发者并发上限
    - 同一开发者下的多个广告户串行 for 处理,复用同一份 token 与 proxy

    缓存与防抖(基于 mongo.fb_ad_accounts):
    - applications 字段存在(含空数组) 视为命中,直接返回
    - 否则若 updated_at 在中国时区当天,视为当日已请求,挡掉(提示可强制刷新)
    - 否则调 FB Graph API; 成功写 applications + updated_at, 失败仅写 updated_at(触发后续防抖)
    - 强制刷新: 跳过以上两项判断,直接调 FB 并刷新 updated_at
    """
    semaphore = asyncio.Semaphore(APPLICATIONS_FETCH_CONCURRENCY)
    groups = await asyncio.gather(
        *[
            _process_group(item, payload.force_refresh, payload.personal_type, semaphore)
            for item in payload.items
        ]
    )

    items: List[dict] = []
    for g in groups:
        items.extend(g)
    return ApiResponse(data={"items": items})


@router.post("/sync/push", response_model=ApiResponse, summary="手动同步个号资产")
async def push_queue(
    query: PersonalQuery,
    current_user: UserModel = Depends(auth_current_user),
):
    if query.personal_type == TokenType.PERSONAL:
        account = await personal_accounts_col.find_one({"_id": query.personal_id})
        if not account:
            return ErrResponse(code=404, message="个人号不存在")
        # 权限: 与个号列表同口径(admin 不限/leader 本部门/其余仅本人授权)
        visible_names = await _visible_personal_user_names(current_user)
        if visible_names is not None and account.get("user_name") not in visible_names:
            return ErrResponse(code=403, message="无权同步该个号")
        # 个号的 proxy 跟随系统开发者配置(accounts),不直接用 personal_accounts 上的字段
        dev_config = await accounts_col.find_one(
            {"app_id": account["app_id"], "status": 1}, {"proxy": 1}
        )
        proxy = dev_config.get("proxy") if dev_config else None
    elif query.personal_type == TokenType.SYSTEM_USER:
        account = await accounts_col.find_one({"_id": ObjectId(query.personal_id)})
        if not account:
            return ErrResponse(code=404, message="系统开发者不存在")
        # 权限: 与系统开发者列表同口径(admin 不限/其余仅本人部门)
        if Roles.ADMIN not in current_user.roles:
            dept = account.get("department")
            depts = dept if isinstance(dept, list) else [dept]
            if current_user.department not in depts:
                return ErrResponse(code=403, message="无权同步该系统开发者")
        proxy = account.get("proxy")

    targets = None
    if query.targets and (query.targets.accounts or query.targets.page_ids):
        targets = query.targets.model_dump()

    await push_personal_to_sync_queue(
        facebook_id=query.personal_id,
        personal_type=query.personal_type,
        app_id=account["app_id"],
        app_secret=account["app_secret"],
        access_token=account["access_token"],
        proxy=proxy,
        targets=targets,
    )

    return ApiResponse(data="同步个号任务提交成功")


@router.post(
    "/sync/progress", response_model=ApiResponse, summary="查询个号资产同步进度"
)
async def get_sync_progress(
    query: PersonalProgress,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    批量查询个号资产同步进度

    Redis key: fb:bm:sync:{personal_id}
    Redis type: string, 值格式: "{processed}/{total}"
    """
    unique_ids = list(dict.fromkeys(pid for pid in query.personal_ids if pid))
    if not unique_ids:
        return ErrResponse(code=400, message="personal_ids 不能为空")

    pipe = redis_db.pipeline()
    for pid in unique_ids:
        pipe.get(f"fb:bm:sync:{pid}")
    redis_results = await pipe.execute()

    result: dict[str, dict[str, int | None]] = {}
    for pid, value in zip(unique_ids, redis_results):
        if value is None:
            continue
        parts = value.split("/", 1)
        if len(parts) == 2:
            result[pid] = {
                "processed": safe_int(parts[0]),
                "total": safe_int(parts[1]),
            }
    if not result:
        return ApiResponse(data="暂无同步资产数据")

    return ApiResponse(data=result)


# ----------------------------- 系统开发者展示 -----------------------------


@router.get(
    "/system_accounts", response_model=ApiResponse, summary="查询系统开发者列表"
)
async def get_system_accounts(
    query: Annotated[BaseQuery, Query()],
    current_user: UserModel = Depends(auth_current_user),
):
    """
    查询系统开发者列表，关联 fb_system_users 返回名下的 accounts 与 pages
    - _id：精确匹配
    - status：状态筛选
    """
    mongo_query = {}
    if query.id:
        mongo_query["_id"] = {"$in": [ObjectId(item) for item in query.id]}
    if isinstance(query.status, bool):
        mongo_query["status"] = int(query.status)
    # 权限: 非 admin 只能看到本人部门的系统开发者
    if Roles.ADMIN not in current_user.roles:
        mongo_query["department"] = current_user.department

    skip = (query.page - 1) * query.page_size
    total = await accounts_col.count_documents(mongo_query)
    pipeline = [
        {"$match": mongo_query},
        {"$sort": {"_id": -1}},
        {"$skip": skip},
        {"$limit": query.page_size},
        {
            "$lookup": {
                "from": "fb_system_users",
                "localField": "app_id",
                "foreignField": "_id",
                "as": "system_user",
            }
        },
        {"$unwind": {"path": "$system_user", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id": 1,
                "app_id": 1,
                "status": 1,
                "accounts": "$system_user.accounts",
                "pages": "$system_user.pages",
                "update_time": 1,
            }
        },
    ]
    items = await accounts_col.aggregate(pipeline).to_list(length=query.page_size)
    for item in items:
        item["_id"] = str(item["_id"])

    return ApiResponse(
        data={
            "total": total,
            "items": items,
            "page": query.page,
            "page_size": query.page_size,
        }
    )


# ----------------------------- 资产分配（用户 ↔ 广告户/主页） -----------------------------


class AssetRef(BaseModel):
    id: str
    name: str


class AssetAssignCreate(BaseModel):
    user_ids: List[str] = Field(default_factory=list)
    remark: Optional[str] = None
    ad_accounts: List[AssetRef] = Field(default_factory=list)
    pages: List[AssetRef] = Field(default_factory=list)


class AssetAssignUpdate(BaseModel):
    user_id: Optional[str] = None
    remark: Optional[str] = None
    ad_accounts: Optional[List[AssetRef]] = None
    pages: Optional[List[AssetRef]] = None


class AssetAssignQuery(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(10, ge=1)
    user_id: Optional[str] = None
    department: Optional[str] = None
    ad_account_name: Optional[str] = None
    page_id: Optional[str] = None


class AssetPageValidationRequest(BaseModel):
    pages: List[AssetRef] = Field(default_factory=list)


@router.post(
    "/asset_assignments/validate-pages",
    response_model=ApiResponse,
    summary="校验主页是否关联到系统用户",
)
async def validate_asset_assignment_pages(
    payload: AssetPageValidationRequest,
    _current_user: UserModel = Depends(auth_current_user),
):
    pages = [item.model_dump() for item in payload.pages]
    linked_pages, warning, _ = await assignment_service.filter_assets_in_system_users(
        pages, "pages", "主页"
    )
    linked_ids = [item["id"] for item in linked_pages]
    page_docs = await fb_pages_col.find(
        {"_id": {"$in": linked_ids}}, {"_id": 1, "name": 1}
    ).to_list(length=None)
    page_map = {item["_id"]: item for item in page_docs}
    valid_pages = []
    for item in linked_pages:
        page = page_map.get(item["id"])
        if not page:
            continue
        page_name = page.get("name") or ""
        input_name = " ".join(item["name"].split()).casefold()
        if input_name != " ".join(page_name.split()).casefold():
            continue
        valid_pages.append({"id": item["id"], "name": page_name})
    valid_ids = {item["id"] for item in valid_pages}
    missing_pages = [item for item in pages if item["id"] not in valid_ids]
    return ApiResponse(
        data={"valid_pages": valid_pages, "missing_pages": missing_pages},
        message=warning or "校验通过",
    )


@router.post(
    "/asset_assignments",
    response_model=ApiResponse,
    summary="新增用户或公共池资产分配",
)
async def create_asset_assignments(
    payload: AssetAssignCreate,
    current_user: UserModel = Depends(auth_current_user),
):
    warning_messages = []
    ad_accounts = [item.model_dump() for item in payload.ad_accounts]
    pages = [item.model_dump() for item in payload.pages]
    if ad_accounts:
        ad_accounts, warning, _ = await assignment_service.filter_assets_in_system_users(
            ad_accounts, "accounts", "广告账户"
        )
        if warning:
            warning_messages.append(warning)
    if pages:
        pages, warning, _ = await assignment_service.filter_assets_in_system_users(
            pages, "pages", "主页"
        )
        if warning:
            warning_messages.append(warning)

    error_message = []
    result = await assignment_service.save_assignments(
        user_ids=payload.user_ids,
        department=current_user.department,
        remark=payload.remark,
        ad_accounts=ad_accounts,
        pages=pages,
        operator=current_user.username,
        error_message=error_message,
        bypass_department=Roles.ADMIN in current_user.roles,
    )
    if error_message:
        return ErrResponse(code=400, message=", ".join(error_message))
    return ApiResponse(data=result, message="；".join(warning_messages) or "分配完成")


@router.put(
    "/asset_assignments/{record_id}",
    response_model=ApiResponse,
    summary="修改单条资产分配",
)
async def update_asset_assignment(
    record_id: str,
    payload: AssetAssignUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    warning_messages = []
    is_admin = Roles.ADMIN in current_user.roles
    allowed = current_user.departments or []

    if not is_admin:
        record_department = await assignment_service.resolve_record_department(record_id)
        if DEPT_ALL not in allowed and record_department not in allowed:
            return ErrResponse(code=403, message="无权修改其他部门的资产分配")

    ad_accounts = (
        [item.model_dump() for item in payload.ad_accounts]
        if payload.ad_accounts is not None
        else None
    )
    pages = (
        [item.model_dump() for item in payload.pages]
        if payload.pages is not None
        else None
    )

    if ad_accounts:
        ad_accounts, warning, su_ids = await assignment_service.filter_assets_in_system_users(
            ad_accounts, "accounts", "广告账户"
        )
        if warning:
            warning_messages.append(warning)

        if not is_admin and DEPT_ALL not in allowed:
            depts = {
                d
                async for acc in accounts_col.find({"app_id": {"$in": su_ids}}, {"department": 1})
                for d in (acc.get("department") or [])
            }
            if not depts & set(allowed):
                names = "、".join(acc["name"] for acc in ad_accounts)
                return ErrResponse(code=403, message=f"广告账户 {names} 属于非本部门，无法分配")

    if pages:
        pages, warning, _ = await assignment_service.filter_assets_in_system_users(
            pages, "pages", "主页"
        )
        if warning:
            warning_messages.append(warning)

    record = await assignment_service.update_assignment(
        record_id=record_id,
        user_id=payload.user_id,
        remark=payload.remark,
        ad_accounts=ad_accounts,
        pages=pages,
        operator=current_user.username,
    )
    return ApiResponse(data=record, message="；".join(warning_messages) or "更新成功")


@router.delete(
    "/asset_assignments/{record_id}",
    response_model=ApiResponse,
    summary="删除单条资产分配",
)
async def delete_asset_assignment(
    record_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    if Roles.ADMIN not in current_user.roles:
        record_department = await assignment_service.resolve_record_department(record_id)
        allowed = current_user.departments or []
        if DEPT_ALL not in allowed and record_department not in allowed:
            return ErrResponse(code=403, message="无权删除其他部门的资产分配")

    deleted = await assignment_service.delete_assignment(record_id)
    return ApiResponse(data=None, message="删除成功")


@router.delete(
    "/asset_assignments",
    response_model=ApiResponse,
    summary="按条件批量解绑",
)
async def delete_asset_assignments(
    user_id: Optional[str] = None,
    department: Optional[str] = None,
    ad_account_id: Optional[str] = None,
    page_id: Optional[str] = None,
    current_user: UserModel = Depends(auth_current_user),
):
    if Roles.ADMIN not in current_user.roles:
        department = current_user.department

    deleted = await assignment_service.delete_by_filter(
        user_id=user_id,
        department=department,
        ad_account_id=ad_account_id,
        page_id=page_id,
    )
    return ApiResponse(data={"deleted": deleted}, message="解绑成功")


@router.get(
    "/asset_assignments", response_model=ApiResponse, summary="查询资产分配列表"
)
async def list_asset_assignments(
    query: AssetAssignQuery = Depends(),
    current_user: UserModel = Depends(auth_current_user),
):
    result = await assignment_service.list_assignments(
        page=query.page,
        page_size=query.page_size,
        user_id=query.user_id,
        department=query.department,
        ad_account_name=query.ad_account_name,
        page_id=query.page_id,
    )
    return ApiResponse(data=result)
