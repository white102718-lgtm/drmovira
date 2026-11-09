import asyncio
import copy
import json
import logging
import random
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import APIRouter, Depends, Query

from app.core.security import auth_current_user
from app.db.async_mysql import AsyncMySQL
from app.db.clients import get_db, redis_cli_3
from app.db.op_queue import push_op_message
from app.db.mongo import cols, user_cols
from app.model_type_defs.ad_operation import OperationFields, OpType

logger = logging.getLogger(__name__)

OP_TYPE_VALUES = tuple(e.value for e in OpType)

# level -> 对应 ad_hourly_detail 表中的 ID 列名
LEVEL_ID_COLUMN = {
    "campaign": "campaign_id",
    "adset": "ad_set_id",
    "ad": "ad_id",
}

LEVEL_NAME_COLUMN = {
    "campaign": "campaign_name",
    "adset": "ad_set_name",
    "ad": "ad_name",
}

# 系列可删除门槛: 该系列下至少有一个广告处于被拒或暂停(广告/组/系列任一层暂停)状态
DELETABLE_DELIVERY_STATUSES = (
    "DISAPPROVED",
    "PAUSED",
    "ADSET_PAUSED",
    "CAMPAIGN_PAUSED",
)

from app.model_type_defs.common_models import (
    ApiResponse,
    ErrResponse,
    HourFormat,
)
from app.model_type_defs.operation_models import (
    AdCreateConfig,
    ChooseDevRequest,
    CreateAdsRequest,
    DeleteAdsRequest,
    DeletePreviewRequest,
    QueryAdStructureRequest,
    SubtaskAccountQueryRequest,
    OperateRequest,
    SubtaskQuery,
)
from app.model_type_defs.user_models import Roles, UserModel
from app.utils.message_signing import OP_API_KEY, sign_payload
from app.services.ad_creation_service import (
    attach_material_tags,
    create_adset_ads,
    delete_adset_ads,
    distribute_ads,
    distribute_ads_for_app_promotion,
    save_creative_history,
    _resolve_dev_app,
)
from app.services.fb_asset_assignment import assigned_asset_ids
from app.services.operation_history_service import (
    build_create_rows,
    detect_create_stage,
    trim_operation_history_data,
)

router = APIRouter(prefix="/operations", tags=["广告操作"])


# MongoDB 集合
creative_histories_collection = cols.creative_histories
materials_collection = cols.materials


def _shallow_summary(data: OperationFields) -> dict:
    """过滤掉嵌套的 dict/list 字段，只保留标量值，用于日志摘要"""

    def _filter_dict(d: dict) -> dict:
        return {k: v for k, v in d.items() if not isinstance(v, (dict, list))}

    result = {}
    for k, v in data.items():
        if isinstance(v, dict):
            result[k] = _filter_dict(v)
        elif isinstance(v, list):
            result[k] = [
                _filter_dict(item) if isinstance(item, dict) else item for item in v
            ]
        else:
            result[k] = v
    return result


def _localize_schedule(value: str | None, tz_name: str | None) -> str | None:
    """把规整出的墙上时间按账户时区附上 UTC 偏移交给 FB；否则 FB 按平台默认时区(太平洋)解释。"""
    if not value:
        return value
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    if tz_name:
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


async def _insert_and_send(operation_message: OperationFields, now: datetime) -> None:
    """入库占位拿 _id（状态 PENDING），签名后推送到 Redis 操作队列。"""
    insert_result = await cols.ad_operations.insert_one(
        {"status": "PENDING", "start_time": now, "data": operation_message}
    )
    operation_message["_id"] = str(insert_result.inserted_id)

    signed_message = sign_payload(operation_message, OP_API_KEY)
    message_data = json.dumps(signed_message, ensure_ascii=False).encode("utf-8")
    logging.info(f"提交任务: {_shallow_summary(operation_message)}")
    await push_op_message(operation_message, message_data)
    logging.info(f"提交任务完成,{message_data}")


async def enrich_creatives_with_material_info(creatives: list[dict]) -> list[dict]:
    """
    关联素材信息（缩略图、文件类型等）
    根据 path 字段中的文件名查询 materials 集合
    """
    if not creatives:
        return []

    # 提取所有文件名
    filenames = []
    for creative in creatives:
        path = creative.get("path")
        if path:
            # path 可能是完整路径或文件名，提取文件名部分
            filename = path.split("/")[-1] if "/" in path else path
            filenames.append(filename)

    # 批量查询素材信息
    material_map = {}
    if filenames:
        cursor = materials_collection.find(
            {"filename": {"$in": filenames}},
            {"filename": 1, "img": 1, "filetype": 1},
        )
        async for doc in cursor:
            material_map[doc["filename"]] = {
                "img": doc.get("img", ""),
                "filetype": doc.get("filetype", ""),
            }

    # 关联素材信息到每个 creative
    enriched_creatives = []
    for creative in creatives:
        enriched = dict(creative)
        path = creative.get("path")
        if path:
            filename = path.split("/")[-1] if "/" in path else path
            material_info = material_map.get(filename, {})
            enriched["img"] = material_info.get("img", "")
            enriched["filetype"] = material_info.get("filetype", "")
        else:
            if "img" not in enriched:
                enriched["img"] = ""
            if "filetype" not in enriched:
                enriched["filetype"] = ""
        enriched_creatives.append(enriched)

    return enriched_creatives


@router.post("/create-ad", response_model=ApiResponse)
async def create_ad(
    request: AdCreateConfig,
    current_user: UserModel = Depends(auth_current_user),
):
    config_data = request.model_dump()
    # 一个提交请求对应一个批次；后续系列/广告组/广告消息都透传此 ID，供进度查询精确合并。
    batch_id = uuid.uuid4().hex

    # 保存素材创意历史（不影响主流程）
    await save_creative_history(config_data["ads"], current_user)

    # 只给 by_tag 的广告挂标签,分配时的标签约束只在它们之间生效
    tag_ads = [ad for ad in config_data["ads"] if ad.get("by_tag")]
    if tag_ads:
        await attach_material_tags(tag_ads)

    # 按系列广告目标选分配策略:OUTCOME_APP_PROMOTION 走 object_store_url↔link_url
    # 匹配分配,其它走默认的笛卡尔 + 全局均分。
    if config_data["campaigns"][0]["objective"] == "OUTCOME_APP_PROMOTION":
        config_data = distribute_ads_for_app_promotion(config_data)
    else:
        config_data = distribute_ads(config_data)

    # 获取所有账户
    all_accounts = config_data.get("accounts", [])
    personal_accounts, developer_accounts = await asyncio.gather(
        cols.personal_accounts.find(
            {"status": True},
            {"_id": 1, "app_id": 1, "access_token": 1},
        ).to_list(length=None),
        cols.accounts.find(
            {"status": 1},
            {"_id": 1, "app_id": 1, "access_token": 1, "app_secret": 1, "proxy": 1},
        ).to_list(length=None),
    )
    personal_map = {
        str(personal_account["_id"]): {
            "app_id": personal_account["app_id"],
            "access_token": personal_account["access_token"],
        }
        for personal_account in personal_accounts
    }
    dev_by_id = {
        str(developer_account["_id"]): {
            "app_id": developer_account["app_id"],
            "access_token": developer_account.get("access_token"),
            "app_secret": developer_account["app_secret"],
            "proxy": developer_account.get("proxy"),
        }
        for developer_account in developer_accounts
    }
    dev_by_app_id = {
        developer_account["app_id"]: {
            "app_id": developer_account["app_id"],
            "access_token": developer_account.get("access_token"),
            "app_secret": developer_account["app_secret"],
            "proxy": developer_account.get("proxy"),
        }
        for developer_account in developer_accounts
    }
    devs = {}
    groups = defaultdict(list)
    no_dev_config_accounts = []
    for account in all_accounts:
        person_id = account["person_id"]
        personal_info = personal_map.get(person_id)
        if personal_info:
            developer_info = dev_by_app_id.get(personal_info["app_id"])
            matched_dev_info = (
                {
                    "app_id": developer_info["app_id"],
                    "access_token": personal_info["access_token"],
                    "app_secret": developer_info["app_secret"],
                    "proxy": developer_info.get("proxy"),
                }
                if developer_info
                else None
            )
        else:
            matched_dev_info = dev_by_id.get(person_id)
        if not matched_dev_info:
            logging.info(f"{account['account_id']} 没找到对应开发者配置")
            no_dev_config_accounts.append(
                f"{account['account_id']}（主页{account['page_id']}，{account['person_name']}）"
            )
            continue
        account["dev_app"] = matched_dev_info
        group_key = (matched_dev_info["app_id"], matched_dev_info["access_token"])
        groups[group_key].append(account)
        devs[group_key] = matched_dev_info
    missing_info = ""
    if no_dev_config_accounts:
        missing_info += f"未找到有效开发者配置：{', '.join(no_dev_config_accounts)}；"
    if not groups:
        return ErrResponse(message=missing_info or "请确认个号或授权系统开发者权限")
    # 排期时间按账户时区落地：批量取 timezone_name（fb_ad_accounts._id 不带 act_ 前缀）
    tz_by_account = {
        doc["_id"]: doc.get("timezone_name")
        for doc in await cols.fb_ad_accounts.find(
            {"_id": {"$in": [a["account_id"].removeprefix("act_") for a in all_accounts]}},
            {"timezone_name": 1},
        ).to_list(length=None)
    }

    china_tz = timezone(timedelta(hours=8))  # UTC+8 中国时区
    now = datetime.now(timezone.utc).astimezone(china_tz)
    date_str = now.strftime("%m%d/%H%M")  # 中国时区，精确到分钟，如 0114_1530

    idx = 0
    adset_idx = 0
    for group_key, grouped_accounts in groups.items():
        # 收集同一个开发者下的所有账户
        accounts_list = []
        for account in grouped_accounts:
            # 使用账户自己的 campaigns（已在 distribute_ads 中分配好素材）
            campaigns_copy = copy.deepcopy(account["campaigns"])
            account_tz = tz_by_account.get(account["account_id"].removeprefix("act_"))

            for campaign in campaigns_copy:
                idx += 1
                # 重命名系列：代理线_账户名称(后8位)_日期时间_序号_投手
                account_name_short = account["account_name"][-8:]
                campaign["name"] = (
                    f"{account['agent_line']}_{account_name_short}_{date_str}_{idx}_{current_user.real_name}"
                )

                for adset in campaign["adsets"]:
                    adset_idx += 1
                    # 重命名广告组：代理线_日期时间_序号_投手
                    adset["name"] = (
                        f"{account['agent_line']}_{date_str}_{adset_idx}_{current_user.real_name}"
                    )
                    if adset.get("start_time"):
                        adset["start_time"] = _localize_schedule(
                            adset["start_time"], account_tz
                        )
                    if adset.get("end_time"):
                        adset["end_time"] = _localize_schedule(
                            adset["end_time"], account_tz
                        )

                    promoted_object = adset.get("promoted_object") or {}
                    engagement_config = adset.get("engagement_config") or {}
                    if engagement_config:
                        page_id = engagement_config.get("page_id") or account["page_id"]
                        engagement_config["page_id"] = page_id
                        adset["engagement_config"] = engagement_config
                        promoted_object["page_id"] = page_id
                        adset["destination_type"] = (
                            adset.get("destination_type") or "MESSENGER"
                        )
                        adset["optimization_goal"] = (
                            adset.get("optimization_goal") or "CONVERSATIONS"
                        )
                        adset["billing_event"] = (
                            adset.get("billing_event") or "IMPRESSIONS"
                        )
                    elif account.get("pixel_id"):
                        promoted_object["pixel_id"] = account["pixel_id"]
                    if promoted_object:
                        adset["promoted_object"] = promoted_object
                    # 设置 page_id 到 ads
                    for ad in adset["ads"]:
                        ad["page_id"] = account["page_id"]

            # 将账户信息添加到列表，每个账户包含自己的 game_platform 等字段
            accounts_list.append(
                {
                    "account_id": account["account_id"],
                    "account_name": account["account_name"],
                    "page_id": account["page_id"],
                    "page_name": account["page_name"],
                    "pixel_id": account["pixel_id"],
                    "pixel_name": account["pixel_name"],
                    "game_platform": account["game_platform"],
                    "country": account["country"],
                    "agent_line": account["agent_line"], 
                    "link_url": account["link_url"],
                    "instagram_user_id": account["instagram_user_id"],
                    "campaigns": campaigns_copy,
                }
            )

        # 同一个开发者的账户一起发送
        operation_message: OperationFields = {
            "type": OpType.CREATE,
            "dev_app": devs[group_key],
            "auto_run": True,
            "is_send": False,
            "create_config": accounts_list,
            "batch_id": batch_id,
            "real_name": current_user.real_name,
            "user_id": current_user.id,
        }

        # 进度以 户×系列 为最小可独立失败单元。无论消息大小都拆到单系列，
        # 后续广告组阶段再由 consumer 拆到单广告组；所有子消息共享 batch_id。
        for account in accounts_list:
            for campaign in account.get("campaigns") or []:
                account_copy = {**account, "campaigns": [campaign]}
                await _insert_and_send(
                    {**operation_message, "create_config": [account_copy]}, now
                )

    msg = "广告创建任务已提交"
    if missing_info:
        msg += f"\n（注意：{missing_info.rstrip('；')}）"
    return ApiResponse(data=msg)


@router.post("/create-ads", summary="用来同系列/组补广告的")
async def create_ads(
    request: CreateAdsRequest,
    current_user: UserModel = Depends(auth_current_user),
):
    total = sum(len(op.ads) for op in request.operations)
    if not total:
        return ErrResponse(message="至少需要创建一个广告")
    try:
        await create_adset_ads(request.model_dump(exclude_none=True), current_user)
    except Exception as e:
        return ErrResponse(message=str(e))
    return ApiResponse(data=f"任务已提交: 创建 {total} 个广告")


@router.post("/delete-ads")
async def delete_ads(
    request: DeleteAdsRequest,
    current_user: UserModel = Depends(auth_current_user),
):
    if not request.ads:
        return ErrResponse(message="至少需要删除一个广告")
    await delete_adset_ads(request.model_dump(), current_user)
    return ApiResponse(data=f"任务已提交: 删除 {len(request.ads)} 个广告")


@router.post("/choose-dev", description="操作广告、补广告查询开发者配置")
async def choose_dev(
    request: ChooseDevRequest,
    current_user: UserModel = Depends(auth_current_user),
    db: AsyncMySQL = Depends(get_db),
):
    """
    根据系列/组/广告 ID 反查 daily 成效里的 account_id，再返回该账户在
    部门下可用的系统开发者及当前用户名下的个号开发者。返回 {id: [option, ...]}。
    """
    campaign_ids = request.campaign_ids or []
    adset_ids = request.adset_ids or []
    ad_ids = request.ad_ids or []
    if not (campaign_ids or adset_ids or ad_ids):
        return ErrResponse(message="至少传入一个 ID")

    id_to_account: dict[str, str] = {}

    async def _collect(field: str, ids: list[str]) -> None:
        if not ids:
            return
        placeholders = ",".join(["%s"] * len(ids))
        rows = await db.fetchall(
            f"SELECT DISTINCT {field} AS xid, account_id FROM ad_daily_detail "
            f"WHERE level = 'ad' AND {field} IN ({placeholders})",
            ids,
            as_dict=True,
        )
        for row in rows:
            xid = row.get("xid")
            account_id = row.get("account_id")
            if xid and account_id and xid not in id_to_account:
                id_to_account[xid] = account_id

    await _collect("campaign_id", campaign_ids)
    await _collect("ad_set_id", adset_ids)
    await _collect("ad_id", ad_ids)

    account_ids = list(set(id_to_account.values()))
    options_by_account: dict[str, list[dict]] = {acc: [] for acc in account_ids}

    if account_ids:
        system_docs = await cols.accounts.aggregate(
            [
                {"$match": {"status": 1}},
                {
                    "$lookup": {
                        "from": "fb_system_users",
                        "localField": "app_id",
                        "foreignField": "_id",
                        "as": "users",
                    }
                },
                {"$match": {"users.accounts.id": {"$in": account_ids}}},
                {
                    "$project": {
                        "app_id": 1,
                        "dev_id": 1,
                        "users.accounts.id": 1,
                    }
                },
            ]
        ).to_list(length=None)

        for doc in system_docs:
            opt = {
                "id": str(doc["_id"]),
                "name": f'系_{doc.get("dev_id")}_{doc["app_id"]}',
                "type": "system",
                "dev_id": doc.get("dev_id"),
            }
            related: set[str] = set()
            for user in doc.get("users") or []:
                for acc in user.get("accounts") or []:
                    aid = acc.get("id")
                    if aid in options_by_account:
                        related.add(aid)
            for aid in related:
                options_by_account[aid].append(opt)

        dept_real_names = (
            [
                u["real_name"]
                async for u in user_cols.user.find(
                    {"department": current_user.department},
                    {"real_name": 1},
                )
                if u.get("real_name")
            ]
            if current_user.department
            else []
        )

        personal_docs = (
            await cols.personal_accounts.find(
                {
                    "user_name": {"$in": dept_real_names},
                    "status": True,
                    "accounts.id": {"$in": account_ids},
                },
                {"_id": 1, "name": 1, "accounts.id": 1},
            ).to_list(length=None)
            if dept_real_names
            else []
        )

        for doc in personal_docs:
            opt = {
                "id": str(doc["_id"]),
                "name": doc.get("name", ""),
                "type": "personal",
                "dev_id": None,
            }
            for acc in doc.get("accounts") or []:
                aid = acc.get("id")
                if aid in options_by_account:
                    options_by_account[aid].append(opt)

    for opts in options_by_account.values():
        _sort_dev_options(opts)  # 注释此行可关闭排序

    result: dict[str, list[dict]] = {
        xid: [
            {k: v for k, v in opt.items() if k != "dev_id"}
            for opt in options_by_account.get(account_id, [])
        ]
        for xid, account_id in id_to_account.items()
    }
    return ApiResponse(data=result)


def _sort_dev_options(opts: list[dict]) -> None:
    """开发者选项排序：dev_id == 'niunai' 的系统开发者优先，其次其他系统，最后个号。原地排序。"""

    def _key(opt: dict) -> tuple:
        if opt["type"] == "system":
            return (0 if opt.get("dev_id") == "niunai" else 1, opt["name"])
        return (2, opt["name"])

    opts.sort(key=_key)


@router.post("/query-ad-structure", summary="查询指定广告上级系列数据")
async def query_ad_structure(
    request: QueryAdStructureRequest,
    current_user: UserModel = Depends(auth_current_user),
    db: AsyncMySQL = Depends(get_db),
):
    if not request.campaign_ids and not request.adset_ids and not request.ad_ids:
        return ErrResponse(message="至少需要传入一个ID列表")
    if not current_user.department:
        return ErrResponse(message="无权查询：未分配部门")

    or_parts = []
    params = []

    if request.ad_ids:
        placeholders = ",".join(["%s"] * len(request.ad_ids))
        or_parts.append(f"ad_id IN ({placeholders})")
        params.extend(request.ad_ids)
    if request.adset_ids:
        placeholders = ",".join(["%s"] * len(request.adset_ids))
        or_parts.append(f"ad_set_id IN ({placeholders})")
        params.extend(request.adset_ids)
    if request.campaign_ids:
        placeholders = ",".join(["%s"] * len(request.campaign_ids))
        or_parts.append(f"campaign_id IN ({placeholders})")
        params.extend(request.campaign_ids)

    id_filter = f"({' OR '.join(or_parts)})"
    dept_filter = "department = %s"
    rows = await db.fetchall(
        f"SELECT DISTINCT t.account_id, t.account_name, t.campaign_id, t.campaign_name, "
        f"t.ad_set_id, t.ad_set_name, t.ad_id, t.ad_name, t.agent_line, t.unique_name, t.page_id "
        f"FROM ad_daily_detail t "
        f"INNER JOIN ("
        f"  SELECT account_id, MAX(date) AS max_date FROM ad_daily_detail "
        f"  WHERE level = 'ad' AND {id_filter} AND {dept_filter} GROUP BY account_id"
        f") m ON t.account_id = m.account_id AND t.date = m.max_date "
        f"WHERE t.level = 'ad' AND {id_filter} AND t.{dept_filter}",
        params + [current_user.department] + params + [current_user.department],
        as_dict=True,
    )
    if not rows:
        return ErrResponse(message="未找到该广告数据或你没有该广告部门权限")
    agent_lines = {row["agent_line"] for row in rows if row.get("agent_line")}
    account_ids = {row["account_id"] for row in rows if row.get("account_id")}

    # 从 agent_line_config 查 link_url (package_url)
    link_map = {}  # agent_line -> link_url
    if agent_lines:
        async for cfg in cols.agent_line_config.find(
            {"_id": {"$in": list(agent_lines)}},
            {"package_url": 1},
        ):
            link_map[cfg["_id"]] = cfg.get("package_url", "")

    # 从 materials 集合批量获取缩略图
    unique_names = {row["unique_name"] for row in rows if row.get("unique_name")}
    thumb_map = {}  # unique_name -> base64 img
    if unique_names:
        async for doc in cols.materials.find(
            {"basename": {"$in": list(unique_names)}},
            {"basename": 1, "img": 1, "_id": 0},
        ):
            thumb_map[doc["basename"]] = doc.get("img")

    # 每个账户用过的主页集合(用来过滤掉"完全没主页可投"的开发者)
    account_page_ids: dict[str, set[str]] = {}
    for row in rows:
        pid = row.get("page_id")
        acc_id = row.get("account_id")
        if pid and acc_id:
            account_page_ids.setdefault(acc_id, set()).add(pid)

    # 账户 → 开发者列表;开发者 → 名下主页 ID 集合
    account_devs, dev_page_ids = await _collect_account_developers(
        list(account_ids), current_user.department, account_page_ids
    )

    # 主页元信息(name/picture):覆盖广告里出现的 page_id + 开发者池里的 page_id
    page_meta: dict[str, dict] = {}
    all_page_ids: set[str] = {row["page_id"] for row in rows if row.get("page_id")}
    for pids in dev_page_ids.values():
        all_page_ids.update(pids)
    if all_page_ids:
        async for p in cols.fb_pages.find(
            {"_id": {"$in": list(all_page_ids)}},
            {"_id": 1, "name": 1, "picture": 1},
        ):
            pic = p.get("picture")
            if isinstance(pic, dict):
                pic = pic.get("url", "")
            page_meta[p["_id"]] = {
                "id": p["_id"],
                "name": p.get("name", ""),
                "picture": pic or "",
            }

    return ApiResponse(
        data=_build_ad_tree(
            rows,
            link_map,
            thumb_map,
            account_devs,
            dev_page_ids,
            page_meta,
        )
    )


async def _redis_paused_ad_ids(ad_ids: list[str]) -> set[str]:
    """这批广告里刚被手动暂停成功的 ad_id 集合(worker 在 redis 留痕, TTL 1h, status=COMPLETED)。
    ad_daily_detail 每小时才刷新, 用它兜住"先暂停、紧接着删系列"时数据表尚未刷新的窗口。"""
    if not ad_ids:
        return set()
    keys = [f"ad_op:ad:{aid}:{OpType.PAUSE.value}" for aid in ad_ids]
    values = await redis_cli_3.mget(keys)
    return {
        aid
        for aid, raw in zip(ad_ids, values)
        if raw and json.loads(raw).get("status") == "COMPLETED"
    }


def _build_delete_tree(rows: list[dict]) -> list[dict]:
    """把 ad 级最新快照行聚合成 账户>系列>组>广告 嵌套树。
    每个系列节点带 can_delete(至少一个广告被拒或暂停, 见 DELETABLE_DELIVERY_STATUSES)。"""
    accounts: dict[str, dict] = {}
    for r in rows:
        acc_id = str(r.get("account_id") or "")
        acc = accounts.setdefault(acc_id, {
            "account_id": acc_id,
            "account_name": r.get("account_name") or "",
            "_camps": {},
        })
        camp_id = str(r.get("campaign_id") or "")
        camp = acc["_camps"].setdefault(camp_id, {
            "campaign_id": camp_id,
            "campaign_name": r.get("campaign_name") or "",
            "_adsets": {},
            "_deletable": False,
        })
        if r.get("delivery_str") in DELETABLE_DELIVERY_STATUSES:
            camp["_deletable"] = True
        as_id = str(r.get("ad_set_id") or "")
        adset = camp["_adsets"].setdefault(as_id, {
            "adset_id": as_id,
            "adset_name": r.get("ad_set_name") or "",
            "ads": [],
        })
        adset["ads"].append({
            "ad_id": str(r.get("ad_id") or ""),
            "ad_name": r.get("ad_name") or "",
            "effective_status": r.get("delivery_str"),
        })

    result = []
    for acc in accounts.values():
        campaigns = []
        for camp in acc["_camps"].values():
            campaigns.append({
                "campaign_id": camp["campaign_id"],
                "campaign_name": camp["campaign_name"],
                "can_delete": camp["_deletable"],
                "reason": None if camp["_deletable"]
                else "该系列下没有被拒或暂停广告，不允许删除",
                "adsets": list(camp["_adsets"].values()),
            })
        result.append({
            "account_id": acc["account_id"],
            "account_name": acc["account_name"],
            "campaigns": campaigns,
        })
    return result


@router.post("/delete-preview", summary="删除前预览: 账户>系列>组>广告 结构树")
async def delete_preview(
    request: DeletePreviewRequest,
    current_user: UserModel = Depends(auth_current_user),
    db: AsyncMySQL = Depends(get_db),
):
    if request.level not in LEVEL_ID_COLUMN:
        return ErrResponse(message="不支持的层级")
    if not request.ids:
        return ErrResponse(message="未选择对象")
    if not current_user.department:
        return ErrResponse(message="无权查询：未分配部门")

    src_col = LEVEL_ID_COLUMN[request.level]
    dept = current_user.department

    # 选中行解析到所属系列, 再展开各系列完整子树
    src_ph = ",".join(["%s"] * len(request.ids))
    camp_rows = await db.fetchall(
        f"SELECT DISTINCT campaign_id FROM ad_daily_detail "
        f"WHERE level = 'ad' AND {src_col} IN ({src_ph}) AND department = %s",
        list(request.ids) + [dept],
        as_dict=True,
    )
    campaign_ids = [str(r["campaign_id"]) for r in camp_rows if r.get("campaign_id")]
    if not campaign_ids:
        return ErrResponse(message="未找到对应数据或你没有该数据的部门权限")

    ph = ",".join(["%s"] * len(campaign_ids))
    rows = await db.fetchall(
        f"SELECT t.account_id, t.account_name, t.campaign_id, t.campaign_name, "
        f"t.ad_set_id, t.ad_set_name, t.ad_id, t.ad_name, t.delivery_str "
        f"FROM ad_daily_detail t INNER JOIN ("
        f"  SELECT ad_id, MAX(date) AS md FROM ad_daily_detail "
        f"  WHERE level = 'ad' AND campaign_id IN ({ph}) AND department = %s GROUP BY ad_id"
        f") m ON t.ad_id = m.ad_id AND t.date = m.md "
        f"WHERE t.level = 'ad' AND t.campaign_id IN ({ph}) AND t.department = %s",
        campaign_ids + [dept] + campaign_ids + [dept],
        as_dict=True,
    )
    if not rows:
        return ErrResponse(message="未找到对应数据")

    return ApiResponse(data={"accounts": _build_delete_tree(rows)})


async def _collect_account_developers(
    account_ids: list[str],
    department: str | None,
    account_page_ids: dict[str, set[str]] | None = None,
) -> tuple[dict[str, list[dict]], dict[str, set[str]]]:
    """按 account_id 收集关联开发者(系统 + 个号),并返回每个开发者名下的主页 ID 集合。

    返回:
      account_devs: account_id → [{id, name, type}]
      dev_page_ids: developer.id → set[page_id]

    个号开发者限制在 current_user.department 内的真实姓名;系统开发者只看 status=1 的 accounts。
    传入 account_page_ids 时,过滤掉"在该账户广告涉及的主页里一张都不持有"的开发者 ——
    这样前端默认选中的开发者一定能命中至少一张候选主页。
    """
    account_devs: dict[str, list[dict]] = {acc: [] for acc in account_ids}
    dev_page_ids: dict[str, set[str]] = {}
    if not account_ids:
        return account_devs, dev_page_ids

    system_docs = await cols.accounts.aggregate(
        [
            {"$match": {"status": 1}},
            {
                "$lookup": {
                    "from": "fb_system_users",
                    "localField": "app_id",
                    "foreignField": "_id",
                    "as": "users",
                }
            },
            {"$match": {"users.accounts.id": {"$in": account_ids}}},
            {
                "$project": {
                    "app_id": 1,
                    "dev_id": 1,
                    "users.accounts.id": 1,
                    "users.pages.id": 1,
                }
            },
        ]
    ).to_list(length=None)
    for doc in system_docs:
        dev_id = str(doc["_id"])
        dev_entry = {
            "id": dev_id,
            "name": f'系_{doc.get("dev_id")}_{doc["app_id"]}',
            "type": "system",
        }
        related: set[str] = set()
        pages: set[str] = set()
        for user in doc.get("users") or []:
            for acc in user.get("accounts") or []:
                aid = acc.get("id")
                if aid in account_devs:
                    related.add(aid)
            for p in user.get("pages") or []:
                pid = p.get("id")
                if pid:
                    pages.add(pid)
        if not related:
            continue
        dev_page_ids[dev_id] = pages
        for aid in related:
            account_devs[aid].append(dev_entry)

    dept_real_names: list[str] = []
    if department:
        dept_real_names = [
            u["real_name"]
            async for u in user_cols.user.find(
                {"department": department},
                {"real_name": 1},
            )
            if u.get("real_name")
        ]
    if dept_real_names:
        personal_docs = await cols.personal_accounts.find(
            {
                "user_name": {"$in": dept_real_names},
                "status": True,
                "accounts.id": {"$in": account_ids},
            },
            {"_id": 1, "name": 1, "accounts.id": 1, "pages.id": 1},
        ).to_list(length=None)
        for doc in personal_docs:
            dev_id = str(doc["_id"])
            dev_entry = {
                "id": dev_id,
                "name": doc.get("name", ""),
                "type": "personal",
            }
            dev_page_ids[dev_id] = {
                p.get("id") for p in doc.get("pages") or [] if p.get("id")
            }
            for acc in doc.get("accounts") or []:
                aid = acc.get("id")
                if aid in account_devs:
                    account_devs[aid].append(dev_entry)

    # 过滤:开发者必须持有该账户广告涉及的至少一张主页,否则前端选中也没候选可投
    if account_page_ids is not None:
        for aid, devs in account_devs.items():
            used = account_page_ids.get(aid) or set()
            if not used:
                account_devs[aid] = []
                continue
            account_devs[aid] = [
                d for d in devs if dev_page_ids.get(d["id"], set()) & used
            ]

    for opts in account_devs.values():
        opts.sort(key=lambda o: (0 if o["type"] == "system" else 1, o["name"]))
    return account_devs, dev_page_ids


def _build_person_page(
    personal_accounts: list[dict], page_id: str | None = None
) -> dict:
    person_page = {}
    for personal_account in personal_accounts:
        pages = personal_account.get("pages") or []
        if page_id is not None:
            pages = [page for page in pages if page.get("id") == page_id]
        person_page.setdefault(personal_account["name"], []).extend(
            [{"person_id": personal_account["_id"], **page} for page in pages]
        )
    return person_page


def _build_account_payload(account: dict, person_page: dict) -> dict:
    spend_cap = int(account.get("spend_cap", 0))
    return {
        "ad_account_id": account.get("_id"),
        "ad_account_name": account.get("name"),
        "status": "活跃",
        "person_and_page": person_page,
        "pixels": account.get("pixels", []),
        "applications": account.get("applications", []),
        "spend_cap": spend_cap / 100,
        "balance": (spend_cap - int(account.get("amount_spent", 0))) / 100,
    }


def _build_person_page_by_account(
    personal_accounts: list[dict], page_id: str | None = None
) -> dict:
    person_page_by_account = {}
    for personal_account in personal_accounts:
        matched_pages = _build_person_page([personal_account], page_id)
        for account in personal_account.get("accounts", []):
            account_id = account.get("id")
            if account_id:
                person_page_by_account.setdefault(account_id, {}).update(matched_pages)
    return person_page_by_account


async def _get_personal_accounts(
    data_name: str,
    field_name: str,
    ad_account_ids: set[str] | None = None,
) -> list[dict]:
    match_stage = {field_name: data_name, "status": True}
    if ad_account_ids is not None:
        match_stage["accounts.id"] = {"$in": list(ad_account_ids)}
    personal_accounts = await cols.personal_accounts.find(
        match_stage, {"_id": 1, "name": 1, "pages": 1, "accounts": 1}
    ).to_list(length=None)
    if ad_account_ids is None:
        return personal_accounts
    result = []
    for pa in personal_accounts:
        matched = [a for a in pa.get("accounts", []) if a.get("id") in ad_account_ids]
        if matched:
            pa["accounts"] = matched
            result.append(pa)
    return result


async def _fill_page_pictures(*groups: list[dict]) -> None:
    """从 fb_pages 集合查询头像，回填到多组 personal-account-like 结构的 pages 列表。

    多组传入时合并 page_ids 去重，只发一次 mongo 请求；之前每组单独调一次会重复
    查询大量同样的主页。"""
    page_ids: set[str] = set()
    for group in groups:
        for pa in group:
            for page in pa.get("pages", []):
                pid = page.get("id")
                if pid:
                    page_ids.add(pid)
    if not page_ids:
        return
    picture_map: dict[str, str] = {}
    cursor = cols.fb_pages.find(
        {"_id": {"$in": list(page_ids)}},
        {"_id": 1, "picture": 1},
    ).batch_size(1000)
    async for doc in cursor:
        picture_map[doc["_id"]] = doc.get("picture", {}).get("url", "")
    for group in groups:
        for pa in group:
            for page in pa.get("pages", []):
                pid = page.get("id")
                if pid in picture_map:
                    page["picture"] = picture_map[pid]


def _filter_accounts(
    all_accounts: list[dict],
    account_name: list[str] | None,
    account_id: list[str] | None,
    pixel_name_filter: str | None,
    status: str | None,
    person_name: str | None = None,
) -> list[dict]:
    """在分页切片之前，对 all_accounts 做内存级筛选。account_name/account_id 任一关键词命中即匹配。"""
    result = all_accounts
    if person_name:
        result = [a for a in result if person_name in (a.get("person_and_page") or {})]
    if account_name:
        kws = [kw.lower() for kw in account_name]
        result = [
            a
            for a in result
            if any(kw in (a.get("ad_account_name") or "").lower() for kw in kws)
        ]
    if account_id:
        kws = [kw.lower() for kw in account_id]
        result = [
            a
            for a in result
            if any(kw in (a.get("ad_account_id") or "").lower() for kw in kws)
        ]
    if pixel_name_filter:
        kw = pixel_name_filter.lower()
        result = [
            a
            for a in result
            if any(kw in (px.get("name") or "").lower() for px in a.get("pixels", []))
        ]
    if status:
        result = [a for a in result if a.get("status") == status]
    return result


async def _collect_accounts_for_source(
    personal_accounts: list[dict],
    page_id: str | None = None,
) -> list[dict]:
    """将一份 personal-account-like 列表转换为广告账户 payload 列表；未关联个号的账户静默跳过。"""
    if not personal_accounts:
        return []

    account_ids = {
        account.get("id")
        for personal_account in personal_accounts
        for account in personal_account.get("accounts", [])
        if account.get("id")
    }
    if not account_ids:
        return []

    person_page_by_account = _build_person_page_by_account(personal_accounts, page_id)
    accounts_cursor = cols.fb_ad_accounts.find(
        {"_id": {"$in": list(account_ids)}},
        {
            "_id": 1,
            "name": 1,
            "account_status": 1,
            "pixels": 1,
            "applications": 1,
            "amount_spent": 1,
            "spend_cap": 1,
        },
    )

    payloads = []
    skipped = []
    async for account in accounts_cursor:
        acc_id = account.get("_id")
        if account.get("account_status", 1) != 1:
            skipped.append(f"{acc_id}(status={account.get('account_status')})")
            continue
        person_page = person_page_by_account.get(acc_id) or {}
        payloads.append(_build_account_payload(account, person_page))
    if skipped:
        logger.warning(
            "skip %s inactive ad_accounts: %s", len(skipped), ", ".join(skipped)
        )
    return payloads


def _filter_person_and_page_by_allowed(
    items: list[dict], allowed_page_ids: set[str] | None
) -> None:
    """按部门可用主页 ID 集合就地裁剪 item.person_and_page,池外的页直接拿掉。"""
    if not items or allowed_page_ids is None:
        return
    for item in items:
        pap = item.get("person_and_page") or {}
        for k, pages in list(pap.items()):
            pap[k] = [p for p in pages if p.get("id") in allowed_page_ids]


def assign_pages_to_items(items: list[dict]) -> None:
    """批量为账户原地写入 assigned_page_id/name/picture。

    主页授权跟着个号走：每个 item 的候选池来自自身 person_and_page。
    分配策略：处理顺序随机；每个 item 在自己候选里选全局使用计数最小的(同票随机),
    使整切片里 page 重复"尽量"少。
    - 单个号场景：先用没用过的，用完才回头(等价"单轮全排列前缀")。
    - 多个号场景：不同个号通常 page 不重叠，自然不重；重叠也优先未用。
    """
    if not items:
        return
    use_count: dict[str, int] = {}
    order = list(range(len(items)))
    random.shuffle(order)
    for i in order:
        item = items[i]
        candidates: list[dict] = []
        for pages in (item.get("person_and_page") or {}).values():
            candidates.extend(pages)
        if not candidates:
            continue
        random.shuffle(candidates)
        chosen = min(candidates, key=lambda p: use_count.get(p.get("id"), 0))
        page_id = chosen.get("id")
        if not page_id:
            continue
        item["assigned_page_id"] = page_id
        item["assigned_page_name"] = chosen.get("name")
        item["assigned_page_picture"] = chosen.get("picture", "")
        use_count[page_id] = use_count.get(page_id, 0) + 1


def _sort_accounts_by_pixel(accounts: list[dict], pixel_name: str | None) -> list[dict]:
    """组内按像素匹配排序：含 pixel_name 的排前，不改变组间顺序。大小写不敏感，与 pixel_name_filter 一致。"""
    if not pixel_name:
        return accounts
    target = pixel_name.lower()
    return sorted(
        accounts,
        key=lambda a: (
            0
            if any(
                (px.get("name") or "").lower() == target for px in a.get("pixels", [])
            )
            else 1
        ),
    )


def _front_load_pixel(accounts: list[dict], pixel_name: str | None) -> None:
    """每个账户的 pixels 内把任务线像素挪到最前，供前端默认选中；其余保持原序。大小写不敏感。"""
    if not pixel_name:
        return
    target = pixel_name.lower()
    for account in accounts:
        pixels = account.get("pixels")
        if not pixels:
            continue
        account["pixels"] = sorted(
            pixels,
            key=lambda px: 0 if (px.get("name") or "").lower() == target else 1,
        )


def _make_dev_entry(dev_info: dict, pages: list[dict], accounts: list[dict]) -> dict:
    return {
        "_id": dev_info["_id"],
        "name": f'系_{dev_info["dev_id"]}_{dev_info["app_id"]}',
        "pages": pages,
        "accounts": accounts,
    }


async def _fetch_dept_dev_entries(
    department: str, ad_account_ids: set[str]
) -> list[dict]:
    dev_configs = await cols.accounts.find(
        {"status": 1, "department": department},
        {"_id": 1, "app_id": 1, "dev_id": 1},
    ).to_list(length=None)
    valid_app_ids = [d["app_id"] for d in dev_configs if d.get("app_id")]
    dev_info_map = {
        d["app_id"]: {
            "_id": str(d["_id"]),
            "app_id": d["app_id"],
            "dev_id": d["dev_id"],
        }
        for d in dev_configs
        if d.get("app_id")
    }
    ids = list(ad_account_ids)
    sys_users = await cols.fb_system_users.aggregate(
        [
            {"$match": {"_id": {"$in": valid_app_ids}, "accounts.id": {"$in": ids}}},
            {
                "$project": {
                    "_id": 1,
                    "pages": 1,
                    "accounts": {
                        "$filter": {
                            "input": "$accounts",
                            "as": "a",
                            "cond": {"$in": ["$$a.id", ids]},
                        }
                    },
                }
            },
        ]
    ).to_list(length=None)
    return [
        _make_dev_entry(dev_info_map[su["_id"]], su.get("pages") or [], su["accounts"])
        for su in sys_users
        if su.get("_id") in dev_info_map and su.get("accounts")
    ]


def _subtask_item_base(query: SubtaskQuery, config: dict) -> dict:
    item = {
        "task_name": query.task_name,
        "target_region": config.get("target_region") or [],
        "subtask_name": query.subtask_name,
        "url": config.get("package_url", ""),
    }
    if config.get("pixel_name"):
        item["pixel_name"] = config["pixel_name"]
    if config.get("page_id"):
        item["page_id"] = config["page_id"]
    return item


async def _build_unified_subtask_item(
    query: SubtaskQuery,
    config: dict,
    ordered_groups: list[tuple[str, list[dict]]],
    page: int,
    page_size: int,
    account_name: list[str] | None,
    account_id: list[str] | None,
    pixel_name_filter: str | None,
    status: str | None,
    allowed_page_ids: set[str] | None = None,
    person_name: str | None = None,
) -> dict:
    """合并 ordered_groups：过滤 → 组内像素排序 → 统一分页 → 按各账户关联个号分配 assigned_page_id。"""
    config_pixel_name = config.get("pixel_name")
    # 用户按像素搜索时，默认选中跟着搜索走；否则用任务线配置的像素
    default_pixel_name = pixel_name_filter or config_pixel_name
    merged: list[dict] = []
    for _, group_accounts in ordered_groups:
        filtered = _filter_accounts(
            group_accounts, account_name, account_id, pixel_name_filter, status,
            person_name=person_name,
        )
        filtered = _sort_accounts_by_pixel(filtered, default_pixel_name)
        merged.extend(filtered)

    accounts_total = len(merged)
    offset = (page - 1) * page_size
    accounts_list = merged[offset : offset + page_size]
    _front_load_pixel(accounts_list, default_pixel_name)

    # 主页权限跟着个号走;默认主页只来自代理线配置,未配置则不预选
    _filter_person_and_page_by_allowed(accounts_list, allowed_page_ids)
    if config.get("page_id"):
        assign_pages_to_items(accounts_list)

    item = _subtask_item_base(query, config)
    item.update({
        "accounts": accounts_list,
        "accounts_total": accounts_total,
        "accounts_page": page,
        "accounts_page_size": page_size,
    })
    return item


def _collect_ad_account_ids(groups: list[dict]) -> set[str]:
    return {
        account.get("id")
        for group in groups
        for account in group.get("accounts", [])
        if account.get("id")
    }


def _collect_page_ids(groups: list[dict]) -> set[str]:
    return {
        page.get("id")
        for group in groups
        for page in group.get("pages", [])
        if page.get("id")
    }


async def _fetch_dept_sources(
    dept: str | None, real_name: str | None, scope_user_id: str | None = None
) -> tuple[list[dict], set[str] | None]:
    """部门系统开发者条目（accounts 已按户池过滤）+ 用户被分配的主页 ID。

    户池规则：assigned_account_ids ∩ real_name 个号下的户;
    real_name 为空时仅取 assigned_account_ids。
    scope_user_id 传入(非 admin)时,资产关联限定为该用户本人 + 部门共享记录,
    并返回其被分配的主页 ID 集合;admin 为部门口径,主页不额外限制(返回 None)。
    """
    assigned_account_ids, assigned_page_ids = await assigned_asset_ids(
        dept, scope_user_id
    )
    page_scope = assigned_page_ids if scope_user_id else None
    if not assigned_account_ids:
        return [], page_scope

    if real_name:
        personal_accounts = await _get_personal_accounts(real_name, "user_name")
        personal_account_ids = {
            a.get("id")
            for pa in personal_accounts
            for a in pa.get("accounts", [])
            if a.get("id")
        }
        account_pool = assigned_account_ids & personal_account_ids
    else:
        account_pool = assigned_account_ids

    if not account_pool:
        return [], page_scope

    return await _fetch_dept_dev_entries(dept, account_pool), page_scope


async def _get_subtask_account_info_item_unified(
    query: SubtaskQuery,
    config: dict,
    dept_devs: list[dict],
    user_personals: list[dict],
    page: int = 1,
    page_size: int = 50,
    account_name: list[str] | None = None,
    account_id: list[str] | None = None,
    pixel_name_filter: str | None = None,
    status: str | None = None,
    allowed_page_ids: set[str] | None = None,
    person_name: str | None = None,
) -> dict | None:
    seen_payload: dict[str, dict] = {}
    ordered_groups: list[tuple[str, list[dict]]] = []
    for source_key, group in (
        ("department_system", dept_devs),
        ("personal", user_personals),
    ):
        raw = await _collect_accounts_for_source(
            group, page_id=config.get("page_id")
        )
        fresh = []
        for payload in raw:
            aid = payload["ad_account_id"]
            prior = seen_payload.get(aid)
            if prior is not None:
                prior["person_and_page"].update(payload["person_and_page"])
                continue
            seen_payload[aid] = payload
            fresh.append(payload)
        ordered_groups.append((source_key, fresh))

    if not any(group for _, group in ordered_groups):
        return None

    return await _build_unified_subtask_item(
        query,
        config,
        ordered_groups,
        page=page,
        page_size=page_size,
        account_name=account_name,
        account_id=account_id,
        pixel_name_filter=pixel_name_filter,
        status=status,
        allowed_page_ids=allowed_page_ids,
        person_name=person_name,
    )


def _build_subtask_account_error_message(errors: dict) -> str:
    parts = []
    if errors["missing_configs"]:
        parts.append(f"代理线不存在: {', '.join(errors['missing_configs'])}")
    if errors["missing_model"]:
        parts.append(errors["missing_model"])
    if errors["missing_pixels"]:
        parts.append(
            f"平台代理线中未配置[像素名称]: {', '.join(errors['missing_pixels'])}"
        )
    return "；".join(parts)


async def _build_subtask_account_info_response(
    request: SubtaskAccountQueryRequest,
    dept_devs: list[dict],
    user_personals: list[dict],
    missing_model_message: str,
    assigned_page_ids: set[str] | None = None,
):
    if not request.queries:
        return ApiResponse(data=[])

    result = []
    errors = {"missing_configs": [], "missing_pixels": [], "missing_model": ""}

    subtask_names = [q.subtask_name for q in request.queries]
    configs = {}
    async for doc in cols.agent_line_config.aggregate([
        {"$match": {"_id": {"$in": subtask_names}}},
        {"$lookup": {
            "from": "platform_config",
            "localField": "_id",
            "foreignField": "agent_lines",
            "as": "_plat",
            "pipeline": [{"$project": {"target_region": 1}}],
        }},
        {"$addFields": {"target_region": {"$first": "$_plat.target_region"}}},
    ]):
        configs[doc["_id"]] = doc
    errors["missing_configs"].extend(n for n in subtask_names if n not in configs)

    allowed_page_ids = _collect_page_ids(dept_devs) or None
    # 非 admin:主页还须在资产关联中分配给本人,空集就是没有可用主页,不能折叠成 None
    if assigned_page_ids is not None:
        allowed_page_ids = (allowed_page_ids or set()) & assigned_page_ids

    if request.meta_only:
        for query in request.queries:
            config = configs.get(query.subtask_name)
            if not config:
                continue
            item = _subtask_item_base(query, config)
            item["accounts"] = []
            result.append(item)
            if not config.get("pixel_name"):
                errors["missing_pixels"].append(query.subtask_name)
    elif not dept_devs and not user_personals:
        errors["missing_model"] = missing_model_message
    else:
        await _fill_page_pictures(dept_devs, user_personals)

        for query in request.queries:
            config = configs.get(query.subtask_name)
            if not config:
                continue
            item = await _get_subtask_account_info_item_unified(
                query,
                config,
                dept_devs,
                user_personals,
                page=request.page,
                page_size=request.page_size,
                account_name=request.account_name,
                account_id=request.account_id,
                pixel_name_filter=request.pixel_name_filter,
                status=request.status,
                allowed_page_ids=allowed_page_ids,
                person_name=request.person_name,
            )
            if item:
                result.append(item)
                if not config.get("pixel_name"):
                    errors["missing_pixels"].append(query.subtask_name)

    message = _build_subtask_account_error_message(errors)
    if not result:
        return ErrResponse(message=message or "未找到代理线配置信息")
    return ApiResponse(data=result, message=message)


@router.post("/subtask-account-info", response_model=ApiResponse)
async def get_subtask_account_info(
    request: SubtaskAccountQueryRequest,
    current_user: UserModel = Depends(auth_current_user),
):
    dept = current_user.department
    scope_user_id = None if Roles.ADMIN in current_user.roles else current_user.id
    dept_devs, assigned_page_ids = (
        ([], None)
        if request.meta_only
        else await _fetch_dept_sources(dept, request.real_name, scope_user_id)
    )
    return await _build_subtask_account_info_response(
        request,
        dept_devs,
        [],
        f"部门「{dept or '未分配'}」下未查询到可用的系统开发者资产",
        assigned_page_ids=assigned_page_ids,
    )


@router.post("/subtask-personal-account-info", response_model=ApiResponse)
async def get_subtask_personal_account_info(
    request: SubtaskAccountQueryRequest,
    current_user: UserModel = Depends(auth_current_user),
):
    user_name = current_user.real_name
    user_personals = (
        []
        if request.meta_only
        else await _get_personal_accounts(user_name, "user_name")
    )
    return await _build_subtask_account_info_response(
        request,
        [],
        user_personals,
        f"个号「{user_name}」下未查询到可用资产",
    )


def _build_ad_tree(
    rows: list[dict],
    link_map: dict[str, str] = None,
    thumb_map: dict[str, str | None] = None,
    account_devs: dict[str, list[dict]] = None,
    dev_page_ids: dict[str, set[str]] = None,
    page_meta: dict[str, dict] = None,
) -> list[dict]:
    """将扁平结果构建为 账户→系列→组→广告 嵌套树。

    账户层挂 developers;广告组层挂 page_options —— 仅本组下广告里实际出现过的 page_id,
    每个 page 标注 developer_ids(本户开发者中"持有该页"者),前端按选中开发者过滤。
    """
    link_map = link_map or {}
    thumb_map = thumb_map or {}
    account_devs = account_devs or {}
    dev_page_ids = dev_page_ids or {}
    page_meta = page_meta or {}
    accounts: dict[str, dict] = {}
    adset_page_ids: dict[tuple[str, str, str], set[str]] = {}

    for row in rows:
        acc_id = row["account_id"]
        camp_id = row["campaign_id"]
        adset_id = row["ad_set_id"]

        if acc_id not in accounts:
            accounts[acc_id] = {
                "account_id": acc_id,
                "account_name": row.get("account_name"),
                "link_url": link_map.get(row.get("agent_line"), ""),
                "developers": account_devs.get(acc_id, []),
                "_campaigns": {},
            }

        campaigns = accounts[acc_id]["_campaigns"]
        if camp_id not in campaigns:
            campaigns[camp_id] = {
                "campaign_id": camp_id,
                "campaign_name": row.get("campaign_name"),
                "_adsets": {},
            }

        adsets = campaigns[camp_id]["_adsets"]
        if adset_id not in adsets:
            adsets[adset_id] = {
                "adset_id": adset_id,
                "adset_name": row.get("ad_set_name"),
                "ads": [],
            }

        ad_item = {
            "ad_id": row["ad_id"],
            "ad_name": row.get("ad_name"),
        }
        unique_name = row.get("unique_name")
        if unique_name:
            ad_item["thumbnail"] = thumb_map.get(unique_name)
        adsets[adset_id]["ads"].append(ad_item)

        pid = row.get("page_id")
        if pid:
            adset_page_ids.setdefault((acc_id, camp_id, adset_id), set()).add(pid)

    result = []
    for acc_id, acc in accounts.items():
        dev_pages_for_acc = {
            d["id"]: dev_page_ids.get(d["id"], set()) for d in acc["developers"]
        }
        campaigns_list = []
        for camp_id, camp in acc.pop("_campaigns").items():
            adsets_list = []
            for adset_id, adset in camp.pop("_adsets").items():
                pids = adset_page_ids.get((acc_id, camp_id, adset_id), set())
                page_options = []
                for pid in pids:
                    meta = page_meta.get(pid) or {"id": pid, "name": "", "picture": ""}
                    developer_ids = [
                        dev_id
                        for dev_id, owned in dev_pages_for_acc.items()
                        if pid in owned
                    ]
                    page_options.append({**meta, "developer_ids": developer_ids})
                adset["page_options"] = page_options
                adsets_list.append(adset)
            camp["adsets"] = adsets_list
            campaigns_list.append(camp)
        acc["campaigns"] = campaigns_list
        result.append(acc)

    return result


def _normalize_fb_error_text(error_str: str) -> str:
    if not error_str:
        return error_str

    # 先把 \uXXXX 转成中文
    try:
        decoded = error_str.encode().decode("unicode_escape")
    except Exception:
        decoded = error_str

    # 提取字段
    message = re.search(r'"message"\s*:\s*"([^"]+)"', decoded)
    # title = re.search(r'"error_user_title"\s*:\s*"([^"]+)"', decoded)
    user_msg = re.search(r'"error_user_msg"\s*:\s*"([^"]+)"', decoded)

    message_val = message.group(1) if message else ""
    # title_val = title.group(1) if title else ""
    user_msg_val = user_msg.group(1) if user_msg else ""

    return (
        user_msg_val if user_msg_val else message_val
    )


async def _mark_retried_success(items: list[dict]) -> None:
    """FAILED 记录若之后有同 (level,id,type) 的 COMPLETED 记录,标 retried_success=True。"""
    failed_by_key: dict[tuple, list[dict]] = {}
    for doc in items:
        data = doc.get("data") or {}
        if doc.get("status") == "FAILED" and data.get("id"):
            key = (data.get("level"), data.get("id"), data.get("type"))
            failed_by_key.setdefault(key, []).append(doc)
    if not failed_by_key:
        return
    or_conds = [
        {
            "data.level": level,
            "data.id": obj_id,
            "data.type": op_type,
            "status": "COMPLETED",
            "start_time": {"$gt": min(d["start_time"] for d in docs)},
        }
        for (level, obj_id, op_type), docs in failed_by_key.items()
    ]
    cursor = cols.ad_operations.find(
        {"$or": or_conds},
        projection={"data.level": 1, "data.id": 1, "data.type": 1, "start_time": 1},
    )
    async for ok_doc in cursor:
        ok_data = ok_doc.get("data") or {}
        key = (ok_data.get("level"), ok_data.get("id"), ok_data.get("type"))
        for failed_doc in failed_by_key.get(key, []):
            if ok_doc["start_time"] > failed_doc["start_time"]:
                failed_doc["retried_success"] = True


@router.get("/operation_history")
async def get_operation_history(
    start: str,
    end: str,
    operate_type: list[str] = Query(...),
    current_user: Optional[str] = None,
    operte_level: Optional[str] = None,
    game_platform: Optional[str] = None,
    agent_line: Optional[str] = None,
    ad_status: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> ApiResponse:
    # 入参是东八区时间,而 BSON 存的是 UTC;pymongo 会把 naive datetime 当作 UTC 编码,
    # 故显式标 +08:00 让查询按东八区→UTC 换算(等价于减 8 小时),否则会差 8 小时。
    china_tz = timezone(timedelta(hours=8))
    start_datetime = datetime.strptime(start, HourFormat).replace(tzinfo=china_tz)
    end_datetime = datetime.strptime(end, HourFormat).replace(tzinfo=china_tz)

    if start_datetime.date() == end_datetime.date() and end_datetime.hour == 0:
        end_datetime = end_datetime.replace(hour=23)
    # end 精确到小时,+1h 半开区间覆盖该小时全部记录,否则会漏掉如 23:00 之后的记录
    end_datetime += timedelta(hours=1)
    query = {
        "start_time": {"$gte": start_datetime, "$lt": end_datetime},
        "data.type": {"$in": operate_type},
    }
    if operte_level:
        query.update({"data.level": operte_level})
    if current_user:
        query.update({"data.real_name": current_user})

    if game_platform:
        query["data.ext_info.game_platform"] = game_platform
    if agent_line:
        query["data.ext_info.agent_line"] = agent_line
    cursor = cols.ad_operations.find(
        query,
        projection={
            "_id": 1,
            "status": 1,
            "start_time": 1,
            "error": 1,
            "data.type": 1,
            "data.batch_id": 1,
            "data.real_name": 1,
            "data.value": 1,
            "data.level": 1,
            "data.id": 1,
            "data.ext_info": 1,
            "data.create_config.account_id": 1,
            "data.create_config.account_name": 1,
            "data.create_config.game_platform": 1,
            "data.create_config.campaign_id": 1,
            "data.create_config.campaign_name": 1,
            "data.create_config.adset_id": 1,
            "data.create_config.adset_name": 1,
            "data.create_config.name": 1,
            "data.create_config.ads.name": 1,
            "data.create_config.campaigns.name": 1,
            "data.create_config.campaigns.adsets.name": 1,
            "data.create_config.campaigns.adsets.promoted_object.custom_event_type": 1,
            "data.create_config.campaigns.adsets.ads.name": 1,
        },
    ).sort("start_time", -1)
    campaign_docs: list[dict] = []
    adset_docs: list[dict] = []
    ad_docs: list[dict] = []
    non_create_items: list[dict] = []

    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        data = doc.get("data") or {}

        # 处理error信息
        error_str = doc.get("error")
        if error_str:
            # 规整会丢掉 Path 里的 act_ 账户,先从原始文本提取出错账户(纯数字)
            acc_match = re.search(r"act_(\d+)", error_str)
            doc["error_account_id"] = acc_match.group(1) if acc_match else None
            # access_token 失效(code 190)是开发者级错误:同 doc 内户共用该 token,未建成的
            # 户都因同一原因失败。标记后由合并逻辑把该错误一并挂到这些户(已建成的户不受影响)。
            doc["error_is_dev_level"] = bool(re.search(r'"code"\s*:\s*190\b', error_str))
            match = re.search(r"Response:\s*(\{[\s\S]*\})\s*$", error_str)
            doc["error"] = (
                _normalize_fb_error_text(match[0])
                if match
                else error_str.strip().split("\n")[-1].strip()
            )

        stage = detect_create_stage(data)
        if stage == "campaign":
            campaign_docs.append(doc)
        elif stage == "adset":
            adset_docs.append(doc)
        elif stage == "ad":
            ad_docs.append(doc)
        else:
            non_create_items.append(doc)

    # create 三阶段 doc 合并后摊平为 户×系列 汇总行
    create_rows = await build_create_rows(campaign_docs, adset_docs, ad_docs)
    if ad_status:
        create_rows = [r for r in create_rows if r.get("status") == ad_status]

    # 非 create: 走原裁剪逻辑
    for doc in non_create_items:
        trim_operation_history_data(doc)

    await _mark_retried_success(non_create_items)

    result = create_rows + non_create_items
    result.sort(key=lambda x: x.get("start_time") or datetime.min, reverse=True)

    total = len(result)
    # 失败但之后重试已成功的按成功算
    success_count = sum(
        1 for item in result
        if item.get("status") in ("success", "COMPLETED") or item.get("retried_success")
    )
    failure_count = sum(
        1 for item in result
        if item.get("status") in ("failed", "partial", "FAILED")
        and not item.get("retried_success")
    )
    finished_total = success_count + failure_count
    if finished_total:
        success_rate = round(success_count / finished_total * 100, 2)
        failure_rate = round(failure_count / finished_total * 100, 2)
    else:
        success_rate = 0
        failure_rate = 0

    # page 不传保持原全量返回（QueryProgressModal 依赖）
    if page:
        result = result[(page - 1) * page_size : page * page_size]

    return ApiResponse(
        data={
            "items": result,
            "total": total,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
        }
    )


@router.get("/creative-histories")
async def get_creative_histories(
    current_user: UserModel = Depends(auth_current_user),
):
    """
    获取素材创意历史记录列表
    - 仅返回当前用户的历史记录
    - 按创建时间倒序排列
    - 包含素材缩略图信息
    """
    query = {"username": current_user.username}

    # 查询所有历史记录
    cursor = creative_histories_collection.find(query).sort("created_at", -1)

    items = []
    async for doc in cursor:
        # 关联素材信息（获取缩略图）
        creatives_with_material = await enrich_creatives_with_material_info(
            doc.get("creatives", [])
        )
        items.append(
            {
                "id": str(doc["_id"]),
                "creatives": creatives_with_material,
                "creatives_count": doc.get("creatives_count", 0),
                "created_at": doc.get("created_at", ""),
                "real_name": doc.get("real_name", ""),
            }
        )

    return ApiResponse(data=items)


@router.get("/creative-histories/{history_id}")
async def get_creative_history_detail(
    history_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    获取素材创意历史记录详情
    - 返回完整的素材创意配置
    - 仅能查看自己的历史记录
    """
    try:
        history = await creative_histories_collection.find_one(
            {
                "_id": ObjectId(history_id),
                "username": current_user.username,
            }
        )
    except Exception:
        return ErrResponse(code=400, message="无效的历史记录ID")

    if not history:
        return ErrResponse(code=404, message="历史记录不存在或无权访问")

    # 关联素材信息
    creatives_with_material = await enrich_creatives_with_material_info(
        history.get("creatives", [])
    )

    return ApiResponse(
        data={
            "id": str(history["_id"]),
            "creatives": creatives_with_material,
            "creatives_count": history.get("creatives_count", 0),
            "created_at": history.get("created_at", ""),
            "real_name": history.get("real_name", ""),
        }
    )


@router.post("/creative-histories/{history_id}/reuse")
async def reuse_creative_history(
    history_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    复用素材创意历史
    - 返回历史记录中的素材创意配置
    - 前端可直接使用返回数据填充广告创建表单
    """
    try:
        history = await creative_histories_collection.find_one(
            {
                "_id": ObjectId(history_id),
                "username": current_user.username,
            }
        )
    except Exception:
        return ErrResponse(code=400, message="无效的历史记录ID")

    if not history:
        return ErrResponse(code=404, message="历史记录不存在或无权访问")

    # 关联素材信息
    creatives_with_material = await enrich_creatives_with_material_info(
        history.get("creatives", [])
    )

    return ApiResponse(
        data={"creatives": creatives_with_material},
        message="获取成功，可用于创建新广告",
    )


@router.delete("/creative-histories/{history_id}")
async def delete_creative_history(
    history_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    删除素材创意历史记录
    - 仅能删除自己的历史记录
    """
    try:
        result = await creative_histories_collection.delete_one(
            {
                "_id": ObjectId(history_id),
                "username": current_user.username,
            }
        )
    except Exception:
        return ErrResponse(code=400, message="无效的历史记录ID")

    if result.deleted_count == 0:
        return ErrResponse(code=404, message="历史记录不存在或无权访问")

    return ApiResponse(data=None, message="历史记录已删除")


async def _resolve_system_dev_app_by_account(
    account_id: str, department: str
) -> dict | None:
    system_users = await cols.fb_system_users.find(
        {"accounts.id": account_id.removeprefix("act_")},
        {"_id": 1},
    ).to_list(length=None)
    return await cols.accounts.find_one(
        {
            "app_id": {"$in": [user["_id"] for user in system_users]},
            "department": department,
            "status": 1,
        },
        {"_id": 0, "app_id": 1, "access_token": 1, "app_secret": 1, "proxy": 1},
    )


@router.post("/operate", response_model=ApiResponse)
async def operate(
    request: OperateRequest,
    current_user: UserModel = Depends(auth_current_user),
    db: AsyncMySQL = Depends(get_db),
):
    # 部门权限校验
    id_col = LEVEL_ID_COLUMN.get(request.level)
    if not id_col:
        return ErrResponse(message=f"不支持的层级: {request.level}")

    if not current_user.department:
        return ErrResponse(message="无权操作：未分配部门")

    # 查询去重部门，任一属于用户部门即可
    dept_rows = await db.fetchall(
        f"SELECT DISTINCT department FROM ad_daily_detail "
        f"WHERE level = 'ad' AND {id_col} = %s",
        [request.id],
        as_dict=True,
    )
    if not dept_rows:
        return ErrResponse(message="未找到该广告的数据")
    departments = {r["department"] for r in dept_rows}
    # 技术部可操作无限部的广告
    tech_cross = current_user.department == "技术部" and "无限部" in departments
    if current_user.department not in departments and not tech_cross:
        return ErrResponse(message="无权操作：该广告不属于你的部门")
    # 跨部门操作时按广告实际所属部门取数据与开发者配置
    op_department = "无限部" if tech_cross else current_user.department

    # 删除系列: 要求该系列下至少有一个广告被拒或暂停
    if request.op_type == OpType.DELETE and request.level == "campaign":
        ph = ",".join(["%s"] * len(DELETABLE_DELIVERY_STATUSES))
        rej = await db.fetchone(
            "SELECT 1 FROM ad_daily_detail t INNER JOIN ("
            "  SELECT ad_id, MAX(date) AS md FROM ad_daily_detail "
            "  WHERE level = 'ad' AND campaign_id = %s GROUP BY ad_id"
            ") m ON t.ad_id = m.ad_id AND t.date = m.md "
            f"WHERE t.level = 'ad' AND t.campaign_id = %s AND t.delivery_str IN ({ph}) LIMIT 1",
            [request.id, request.id, *DELETABLE_DELIVERY_STATUSES],
            as_dict=True,
        )
        # 数据表未命中时, 再查该系列下广告是否有刚手动暂停成功的 redis 留痕
        if not rej:
            ad_rows = await db.fetchall(
                "SELECT DISTINCT ad_id FROM ad_daily_detail WHERE level = 'ad' AND campaign_id = %s",
                [request.id],
                as_dict=True,
            )
            ad_ids = [str(r["ad_id"]) for r in ad_rows if r.get("ad_id")]
            if not await _redis_paused_ad_ids(ad_ids):
                return ErrResponse(message="该系列下没有被拒或暂停广告，不允许删除")

    row = await db.fetchone(
        f"SELECT department, game_platform, agent_line, "
        f"account_id, account_name, campaign_id, campaign_name, "
        f"ad_set_id, ad_set_name, ad_id, ad_name, placer_id, page_id "
        f"FROM ad_daily_detail "
        f"WHERE {id_col} = %s AND department = %s "
        f"ORDER BY date DESC LIMIT 1",
        [request.id, op_department],
        as_dict=True,
    )

    if request.object_type and request.personal_id:
        dev_app = await _resolve_dev_app(request.object_type, request.personal_id)
    else:
        dev_app = await _resolve_system_dev_app_by_account(
            row["account_id"], op_department
        )
        if not dev_app:
            return ErrResponse(message="未找到当前部门可用的系统开发者配置")

    operation_message: OperationFields = {
        "type": request.op_type,
        "dev_app": dev_app,
        "auto_run": True,
        "is_send": True,
        "level": request.level,
        "id": request.id,
        "real_name": current_user.real_name,
        "user_id": current_user.id,
    }
    ext_info = {}
    if request.name:
        ext_info["name"] = request.name
    for field in (
        "game_platform",
        "agent_line",
        "account_id",
        "account_name",
        "campaign_id",
        "campaign_name",
        "ad_set_id",
        "ad_set_name",
        "ad_id",
        "ad_name",
        "placer_id",
    ):
        if row.get(field):
            ext_info[field] = row[field]
    if ext_info:
        operation_message["ext_info"] = ext_info
    if request.value is not None:
        operation_message["value"] = request.value

    # 先入库占位拿 _id，状态 PENDING；worker 收到消息后按此 _id 回写进度
    china_tz = timezone(timedelta(hours=8))
    now = datetime.now(timezone.utc).astimezone(china_tz)
    insert_result = await cols.ad_operations.insert_one(
        {"status": "PENDING", "start_time": now, "data": operation_message}
    )
    operation_message["_id"] = str(insert_result.inserted_id)

    # 提交即写一条 PENDING 进度到 redis，让面板提交后立刻可见；worker 执行到再翻 STARTED→COMPLETED。
    # key/payload 与 worker OpTracker 对齐；PENDING 不触发其 STARTED 重复执行守卫。
    await redis_cli_3.set(
        f"ad_op:{request.level}:{request.id}:{request.op_type.value}",
        json.dumps(
            {
                "op_type": request.op_type.value,
                "status": "PENDING",
                "value": request.value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            },
            ensure_ascii=False,
        ),
        ex=3600,
    )

    signed_message = sign_payload(operation_message, OP_API_KEY)
    message_data = json.dumps(signed_message, ensure_ascii=False).encode("utf-8")
    logging.info(f"提交操作: {operation_message}")
    await push_op_message(operation_message, message_data)
    return ApiResponse(data="操作指令已提交")


@router.get("/operate-status", response_model=ApiResponse)
async def operate_status(
    ids: str = Query(..., description="逗号分隔的 FB 对象 ID 列表"),
    level: str = Query(..., description="层级: campaign / adset / ad"),
):
    id_list = [s for i in ids.split(",") if (s := i.strip())]
    if not id_list:
        return ApiResponse(data={})

    keys = [
        f"ad_op:{level}:{obj_id}:{op_type}"
        for obj_id in id_list
        for op_type in OP_TYPE_VALUES
    ]
    values = await redis_cli_3.mget(keys)

    # 按 id 分组解析结果
    result = {}
    idx = 0
    for obj_id in id_list:
        obj_status = {}
        for op_type in OP_TYPE_VALUES:
            raw = values[idx]
            idx += 1
            if not raw:
                continue
            try:
                obj_status[op_type] = json.loads(raw)
            except Exception as e:
                logging.warning(
                    f"operate-status JSON解析失败 key=ad_op:{level}:{obj_id}:{op_type}, raw={raw!r}, error={e}"
                )
                continue
        if obj_status:
            result[obj_id] = obj_status
    return ApiResponse(data=result)
