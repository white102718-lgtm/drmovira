import json
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, List, Type

from bson import ObjectId
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import require_roles, auth_current_user
from app.db.clients import redis_cli
from app.db.mongo import cols, trash
from app.model_type_defs.common_models import (
    ApiResponse,
    ErrResponse,
    DayFormat,
    HourFormat,
    SecondFormat,
)
from app.model_type_defs.user_models import Roles, UserModel

router = APIRouter(prefix="/developers", tags=["developers"])


def mask_secret(value: str) -> str:
    """只显示前后四位，中间替换为****"""
    if not value or len(value) < 8:
        return "****"
    return value[:4] + "****" + value[-4:]


class AdPlatform(str, Enum):
    facebook = "facebook"
    google = "google"


class DeveloperBase(BaseModel):
    ad_platform: AdPlatform
    status: int = 0
    description: Optional[str] = None
    proxy: Optional[str] = None
    department: Optional[List] = None


class AccountUsage(BaseModel):
    insights_pull: bool = False
    facebook_login: bool = False
    sync_personal: bool = False
    sync_bm: bool = False
    sync_pixels: bool = False


# Facebook 特定字段模型
class FacebookFields(BaseModel):
    dev_id: str
    app_id: str
    app_secret: str
    access_token: str
    account_usage: AccountUsage
    config_id: Optional[str] = None


# Google 特定字段模型
class GoogleFields(BaseModel):
    customer_id: str
    login_customer_id: str
    developer_token: str
    service_account_json: str


# Facebook 创建模型
class FacebookDeveloperCreate(DeveloperBase, FacebookFields):
    pass


# Google 创建模型
class GoogleDeveloperCreate(DeveloperBase, GoogleFields):
    pass


# 通用创建模型 - 包含所有平台字段（用于 API 接收）
class DeveloperCreate(DeveloperBase):
    # Facebook 字段
    dev_id: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    access_token: Optional[str] = None
    account_usage: AccountUsage
    config_id: Optional[str] = None

    # Google 字段
    customer_id: Optional[str] = None
    login_customer_id: Optional[str] = None
    developer_token: Optional[str] = None
    service_account_json: Optional[str] = None


# 更新模型基类 - 公共字段
class DeveloperUpdateBase(BaseModel):
    status: Optional[int] = None
    description: Optional[str] = None
    proxy: Optional[str] = None
    ad_platform: Optional[str] = None
    department: Optional[List] = None


# Facebook 更新字段模型
class FacebookUpdateFields(BaseModel):
    dev_id: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    access_token: Optional[str] = None
    account_usage: AccountUsage
    config_id: Optional[str] = None


# Google 更新字段模型
class GoogleUpdateFields(BaseModel):
    customer_id: Optional[str] = None
    login_customer_id: Optional[str] = None
    developer_token: Optional[str] = None
    service_account_json: Optional[str] = None


# 通用更新模型 - 包含所有平台字段
class DeveloperUpdate(DeveloperUpdateBase, FacebookUpdateFields, GoogleUpdateFields):
    pass


@router.get("/ad_sync_history")
async def get_report_param(
    day: str,
    hour: int = None,
    agent_lines: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
):
    date = datetime.strptime(day, DayFormat)
    if hour is not None:
        # date 到半点后,一个整点有 :00/:30 两条;按整点前缀范围匹配本小时全部 sub-run
        date = date.replace(hour=hour)
        query = {
            "date": {
                "$gte": date.strftime(HourFormat),
                "$lt": (date + timedelta(hours=1)).strftime(HourFormat),
            }
        }
    else:
        query = {
            "date": {
                "$gte": date.strftime(DayFormat),
                "$lte": (date + timedelta(days=1)).strftime(DayFormat),
            }
        }
    if agent_lines:
        query["agent_lines"] = {"$in": agent_lines.split(",")}
    projection = {
        "dev_id": 1,
        "ad_platform": 1,
        "agent_lines": 1,
        "placer_id": 1,
        "description": 1,
        "proxy": 1,
        "date": 1,
        "run_status": 1,
        "create_time": 1,
        "_id": 0,
        "update_time": 1,
        "errors": 1,
    }
    total = await cols.ad_sync_history.count_documents(query)
    skip = (page - 1) * page_size
    cursor = (
        cols.ad_sync_history.find(query, projection=projection)
        .sort([("date", -1), ("run_status", -1), ("_id", 1)])
        .skip(skip)
        .limit(page_size)
    )
    results = []
    async for doc in cursor:
        if "update_time" not in doc:
            doc["update_time"] = None
        results.append(doc)
    return ApiResponse(
        data={
            "items": results,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }
    )


@router.get("/")
async def get_developers(
    dev_id: Optional[str] = None,
    ad_platform: Optional[str] = None,
    status: Optional[int] = None,
    description: Optional[str] = None,
    proxy: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: UserModel = Depends(auth_current_user),
):
    query = {}
    if Roles.ADMIN not in current_user.roles:
        query["department"] = {
            "$in": [current_user.department] if current_user.department else []
        }
    if dev_id:
        query["dev_id"] = dev_id
    if ad_platform:
        query["ad_platform"] = ad_platform
    if status is not None:
        query["status"] = status
    if description:
        query["description"] = {"$regex": description, "$options": "i"}
    if proxy:
        query["proxy"] = {"$regex": proxy, "$options": "i"}

    collection = cols.accounts
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort([("update_time", -1), ("_id", -1)])
        .skip(skip)
        .limit(limit)
    )
    items = await cursor.to_list(length=limit)

    sensitive_fields = ("access_token", "app_secret", "developer_token", "service_account_json")
    for item in items:
        item["_id"] = str(item["_id"])
        for field in sensitive_fields:
            if item.get(field):
                item[field] = mask_secret(item[field])

    return ApiResponse(
        data={
            "items": items,
            "total": total,
            "page": skip // limit + 1,
            "pageSize": limit,
        }
    )


PLATFORM_MODEL_MAP: dict[AdPlatform, Type[BaseModel]] = {
    AdPlatform.google: GoogleDeveloperCreate,
    AdPlatform.facebook: FacebookDeveloperCreate,
}


@router.post("/", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))])
async def create_developer(
    developer: DeveloperCreate,
    current_user: UserModel = Depends(auth_current_user),
):
    if not developer.department:
        return ErrResponse(message="部门必填")
    if Roles.ADMIN not in current_user.roles and current_user.department not in developer.department:
        return ErrResponse(message="部门必须包含自己的部门")
    model_cls = PLATFORM_MODEL_MAP.get(developer.ad_platform)
    developer = model_cls(**developer.model_dump(exclude_none=True))
    collection = cols.accounts

    # 转换为字典并过滤 None 值
    developer_data = {k: v for k, v in developer.model_dump().items() if v is not None}

    # 去除字符串字段的前后空格
    for key, value in developer_data.items():
        if isinstance(value, str):
            developer_data[key] = value.strip()

    developer_data["update_time"] = datetime.now().strftime(SecondFormat)

    # 检查是否已存在相同的dev_id
    if "dev_id" in developer_data:
        existing = await collection.find_one({"dev_id": developer_data["dev_id"]})
        if existing:
            return ErrResponse(message=f"开发者ID {developer_data['dev_id']} 已存在")
    elif "customer_id" in developer_data:
        existing = await collection.find_one(
            {"customer_id": developer_data["customer_id"]}
        )
        if existing:
            return ErrResponse(
                message=f"开发者ID {developer_data['customer_id']} 已存在"
            )

    result = await collection.insert_one(developer_data)

    return ApiResponse(data={"_id": str(result.inserted_id), "message": "创建成功"})


@router.put(
    "/{developer_id}", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))]
)
async def update_developer(
    developer_id: str,
    developer: DeveloperUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    try:
        collection = cols.accounts

        existing = await collection.find_one({"_id": ObjectId(developer_id)})
        if not existing:
            return ErrResponse(message="开发者不存在")

        if Roles.ADMIN not in current_user.roles and current_user.department not in (
            existing.get("department") or []
        ):
            return ErrResponse(message="无权修改其他部门的开发者")

        if "department" in developer.model_fields_set:
            if not developer.department:
                return ErrResponse(message="部门必填")
            if (
                Roles.ADMIN not in current_user.roles
                and current_user.department not in developer.department
            ):
                return ErrResponse(message="部门必须包含自己的部门")

        # 只取前端实际传入的字段，过滤脱敏占位值（含 **** 说明用户未修改该字段）
        update_data = {
            k: v
            for k, v in developer.model_dump().items()
            if k in developer.model_fields_set
            and not (isinstance(v, str) and "****" in v)
        }

        if not update_data:
            return ApiResponse(data={"message": "没有提供要更新的字段"})

        # 如果更新dev_id，检查是否与其他记录冲突
        if "dev_id" in update_data and update_data["dev_id"] != existing.get("dev_id"):
            duplicate = await collection.find_one(
                {
                    "dev_id": update_data["dev_id"],
                    "_id": {"$ne": ObjectId(developer_id)},
                }
            )
            if duplicate:
                return ErrResponse(
                    message=f"开发者ID {update_data['dev_id']} 已被其他记录使用"
                )
        update_data["update_time"] = datetime.now().strftime(SecondFormat)
        result = await collection.update_one(
            {"_id": ObjectId(developer_id)}, {"$set": update_data}
        )

        if result.modified_count:
            return ApiResponse(data={"message": "更新成功"})
        else:
            return ApiResponse(data={"message": "无需更新"})
    except Exception as e:
        logging.error(f"更新开发者失败: {str(e)}")
        return ErrResponse(message="更新开发者失败")


@router.delete(
    "/{developer_id}", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))]
)
async def delete_developer(
    developer_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    collection = cols.accounts
    collection_trash = trash.accounts

    # 检查开发者是否存在
    existing = await collection.find_one(
        {"_id": ObjectId(developer_id)}, {"status": 1, "department": 1}
    )
    if not existing:
        return ErrResponse(message="开发者不存在")
    if Roles.ADMIN not in current_user.roles and current_user.department not in (
        existing.get("department") or []
    ):
        return ErrResponse(message="无权删除其他部门的开发者")
    if existing.get("status") == 1:
        return ErrResponse(message="开发者正在使用中，无法删除")

    result = await collection.find_one_and_delete({"_id": ObjectId(developer_id)})
    result.update(
        {
            "delete_time": datetime.now().strftime(SecondFormat),
            "deleted_by": current_user.username,
        }
    )
    r = await collection_trash.insert_one(result)
    if result:
        return ApiResponse(data={"message": "删除成功"})
    else:
        return ErrResponse(message="删除失败")


KEY = "ad:sync:hourly"


class RestartConsumerParams(BaseModel):
    id: str = Field(alias="_id")
    date: str


async def get_agent_plat_map(agent_lines):
    # _id 就是 game_platform
    cursor = cols.platform_config.find(
        {"agent_lines": {"$in": list(agent_lines)}},
        {"agent_lines": 1},
    )
    plat_agents = await cursor.to_list(length=None)
    agent_line_to_platform = {
        agent_line: item["_id"]
        for item in plat_agents
        for agent_line in item["agent_lines"]
    }
    return agent_line_to_platform


KEY_PRODUCER = "ad:sync:hourly"


class ProducerMethod(Enum):
    PRODUCER = "producer"
    PERSONAL_PRODUCER = "personal_producer"


@router.post(
    "/restart_consumer", dependencies=[Depends(require_roles(Roles.OPERATOR_ALL))]
)
async def restart_consumer(
    data: RestartConsumerParams,
    current_user: UserModel = Depends(auth_current_user),
):
    collection = cols.accounts
    dev = await collection.find_one({"_id": ObjectId(data.id)})
    if not dev:
        return ErrResponse(message="开发者不存在")
    if Roles.ADMIN not in current_user.roles and current_user.department not in (
        dev.get("department") or []
    ):
        return ErrResponse(message="无权操作其他部门的开发者")
    now = datetime.now(timezone(timedelta(hours=8)))
    if data.date == now.strftime(DayFormat):
        china_time = now.strftime(HourFormat)
        review = False
    else:
        date_obj = datetime.strptime(data.date, DayFormat)
        china_time = (date_obj + timedelta(days=1)).strftime(HourFormat)
        review = True
    message = {
        "date": china_time,
        "review": review,
        "_id": str(dev["_id"]),
        "type": ProducerMethod.PRODUCER.value,
    }
    await redis_cli.rpush(KEY_PRODUCER, json.dumps(message))
    logging.info(f"已发送消息: {message}")
    return ApiResponse(data={"message": "同步中, 请查看历史记录"})
