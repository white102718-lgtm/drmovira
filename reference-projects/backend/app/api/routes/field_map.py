from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.core.security import auth_current_user, require_roles
from app.db.clients import get_db
from app.db.mongo import cols
from app.model_type_defs.common_models import ApiResponse, ErrResponse, SecondFormat
from app.model_type_defs.user_models import UserModel, Roles
from datetime import datetime, timezone, timedelta

router = APIRouter(
    prefix="/field-map",
    tags=["平台字段映射"],
)

collection = cols.platform_field_map
platform_collection = cols.platform_config


class SpecialAgentMapping(BaseModel):
    """特殊代理线映射"""

    agent_line: str
    field_mappings: dict[str, str]
    description: Optional[str] = None
    is_active: bool = True


class FieldMapCreate(BaseModel):
    """创建字段映射"""

    default_field_mappings: dict[str, str] = Field(default_factory=dict)
    description: Optional[str] = None
    is_active: bool = True
    special_agent_mappings: list[SpecialAgentMapping] = Field(default_factory=list)


class FieldMapUpdate(BaseModel):
    """更新字段映射"""

    default_field_mappings: Optional[dict[str, str]] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    special_agent_mappings: Optional[list[SpecialAgentMapping]] = None


class SpecialAgentMappingUpdate(BaseModel):
    """更新特殊代理线映射"""

    field_mappings: Optional[dict[str, str]] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


# ==================== 平台字段映射 CRUD ====================


@router.get("/")
async def get_all_field_maps(
    platform_id: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """获取所有平台的字段映射"""
    query = {}
    if platform_id:
        query["_id"] = {"$regex": platform_id, "$options": "i"}
    if is_active is not None:
        query["is_active"] = is_active

    cursor = collection.find(query).sort("_id", 1)
    items = await cursor.to_list(length=None)

    return ApiResponse(data={"items": items, "total": len(items)})


@router.get("/{platform_id}")
async def get_field_map(platform_id: str):
    """获取某个平台的字段映射"""
    doc = await collection.find_one({"_id": platform_id})
    if not doc:
        return ErrResponse(
            code=status.HTTP_404_NOT_FOUND, message="未找到该平台的字段映射配置"
        )

    return ApiResponse(data=doc)


@router.post("/{platform_id}")
async def create_field_map(
    platform_id: str,
    field_map_in: FieldMapCreate,
    current_user: UserModel = Depends(auth_current_user),
):
    """为某个平台创建字段映射"""
    # 检查平台是否存在
    platform = await platform_collection.find_one({"_id": platform_id})
    if not platform:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到平台配置")

    # 检查是否已存在
    existing = await collection.find_one({"_id": platform_id})
    if existing:
        return ErrResponse(code=400, message="该平台已存在字段映射配置，请使用更新接口")

    china_tz = timezone(timedelta(hours=8))
    now = datetime.now(timezone.utc).astimezone(china_tz).strftime(SecondFormat)
    doc = field_map_in.model_dump()
    doc["_id"] = platform_id
    doc["created_at"] = now
    doc["updated_at"] = now
    doc["created_by"] = current_user.username

    await collection.insert_one(doc)
    created = await collection.find_one({"_id": platform_id})
    return ApiResponse(data=created)


@router.put("/{platform_id}")
async def update_field_map(
    platform_id: str,
    field_map_update: FieldMapUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    """更新某个平台的字段映射"""
    existing = await collection.find_one({"_id": platform_id})
    if not existing:
        return ErrResponse(
            code=status.HTTP_404_NOT_FOUND, message="未找到该平台的字段映射配置"
        )

    update_data = {
        k: v for k, v in field_map_update.model_dump().items() if v is not None
    }
    if not update_data:
        return ErrResponse(code=400, message="没有需要更新的字段")

    update_data["updated_at"] = datetime.now().strftime(SecondFormat)
    update_data["updated_by"] = current_user.username

    await collection.update_one({"_id": platform_id}, {"$set": update_data})
    updated = await collection.find_one({"_id": platform_id})
    return ApiResponse(data=updated)


@router.delete("/{platform_id}")
async def delete_field_map(
    platform_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """删除某个平台的字段映射"""
    existing = await collection.find_one({"_id": platform_id})
    if not existing:
        return ErrResponse(
            code=status.HTTP_404_NOT_FOUND, message="未找到该平台的字段映射配置"
        )

    await collection.delete_one({"_id": platform_id})
    return ApiResponse(data=None, message="字段映射已删除")


# ==================== 特殊代理线映射 CRUD ====================


@router.get("/{platform_id}/agent/{agent_line}")
async def get_agent_mapping(platform_id: str, agent_line: str):
    """获取某个平台某个代理线的特殊映射"""
    doc = await collection.find_one({"_id": platform_id})
    if not doc:
        return ErrResponse(
            code=status.HTTP_404_NOT_FOUND, message="未找到该平台的字段映射配置"
        )

    for mapping in doc.get("special_agent_mappings", []):
        if mapping["agent_line"] == agent_line:
            return ApiResponse(data=mapping)

    return ErrResponse(
        code=status.HTTP_404_NOT_FOUND, message="未找到该代理线的特殊映射"
    )


@router.post("/{platform_id}/agent")
async def add_agent_mapping(
    platform_id: str,
    agent_mapping: SpecialAgentMapping,
    current_user: UserModel = Depends(auth_current_user),
):
    """为某个平台添加特殊代理线映射"""
    doc = await collection.find_one({"_id": platform_id})
    if not doc:
        return ErrResponse(
            code=status.HTTP_404_NOT_FOUND, message="未找到该平台的字段映射配置"
        )

    # 检查代理线是否已存在
    for mapping in doc.get("special_agent_mappings", []):
        if mapping["agent_line"] == agent_mapping.agent_line:
            return ErrResponse(
                code=400, message="该代理线已存在特殊映射，请使用更新接口"
            )

    await collection.update_one(
        {"_id": platform_id},
        {
            "$push": {"special_agent_mappings": agent_mapping.model_dump()},
            "$set": {
                "updated_at": datetime.now().strftime(SecondFormat),
                "updated_by": current_user.username,
            },
        },
    )

    updated = await collection.find_one({"_id": platform_id})
    return ApiResponse(data=updated)


@router.put("/{platform_id}/agent/{agent_line}")
async def update_agent_mapping(
    platform_id: str,
    agent_line: str,
    agent_update: SpecialAgentMappingUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    """更新某个平台某个代理线的特殊映射"""
    doc = await collection.find_one({"_id": platform_id})
    if not doc:
        return ErrResponse(
            code=status.HTTP_404_NOT_FOUND, message="未找到该平台的字段映射配置"
        )

    # 查找并更新特定代理线
    found = False
    mappings = doc.get("special_agent_mappings", [])
    for i, mapping in enumerate(mappings):
        if mapping["agent_line"] == agent_line:
            found = True
            update_data = {
                k: v for k, v in agent_update.model_dump().items() if v is not None
            }
            mappings[i].update(update_data)
            break

    if not found:
        return ErrResponse(
            code=status.HTTP_404_NOT_FOUND, message="未找到该代理线的特殊映射"
        )

    await collection.update_one(
        {"_id": platform_id},
        {
            "$set": {
                "special_agent_mappings": mappings,
                "updated_at": datetime.now().strftime(SecondFormat),
                "updated_by": current_user.username,
            },
        },
    )

    updated = await collection.find_one({"_id": platform_id})
    return ApiResponse(data=updated)


@router.delete("/{platform_id}/agent/{agent_line}")
async def delete_agent_mapping(
    platform_id: str,
    agent_line: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """删除某个平台某个代理线的特殊映射"""
    doc = await collection.find_one({"_id": platform_id})
    if not doc:
        return ErrResponse(
            code=status.HTTP_404_NOT_FOUND, message="未找到该平台的字段映射配置"
        )

    # 检查代理线是否存在
    found = any(
        m["agent_line"] == agent_line for m in doc.get("special_agent_mappings", [])
    )
    if not found:
        return ErrResponse(
            code=status.HTTP_404_NOT_FOUND, message="未找到该代理线的特殊映射"
        )

    await collection.update_one(
        {"_id": platform_id},
        {
            "$pull": {"special_agent_mappings": {"agent_line": agent_line}},
            "$set": {
                "updated_at": datetime.now().strftime(SecondFormat),
                "updated_by": current_user.username,
            },
        },
    )

    return ApiResponse(data=None, message="代理线特殊映射已删除")


# ==================== Doris 表结构查询 ====================

# 表结构缓存
_schema_cache: dict = {}
_schema_cache_time: Optional[datetime] = None
SCHEMA_CACHE_TTL = 3 * 60 * 60  # 3小时（秒）


async def _fetch_table_schemas(db) -> dict:
    """从数据库获取表结构"""
    tables = ["ad_hourly_detail", "ad_hourly_cleaned"]
    result = {}

    for table in tables:
        sql = f"SHOW FULL COLUMNS FROM {table}"
        rows = await db.fetchall(sql, as_dict=True)
        result[table] = [
            {
                "field": row["Field"],
                "type": row["Type"],
                "comment": row["Comment"],
            }
            for row in rows
        ]

    return result


@router.get("/schema/tables")
async def get_table_schemas(db=Depends(get_db)):
    """获取 ad_hourly_detail 和 ad_hourly_cleaned 表结构（3小时缓存）"""
    global _schema_cache, _schema_cache_time

    now = datetime.now()

    # 检查缓存是否有效
    if _schema_cache and _schema_cache_time:
        elapsed = (now - _schema_cache_time).total_seconds()
        if elapsed < SCHEMA_CACHE_TTL:
            return ApiResponse(data=_schema_cache)

    # 缓存过期或不存在，重新查询
    _schema_cache = await _fetch_table_schemas(db)
    _schema_cache_time = now

    return ApiResponse(data=_schema_cache)
