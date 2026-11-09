"""
素材组管理 API
集合名称: material_groups, material_group_histories
路径前缀: /operations/material-groups

功能说明:
    - 素材组：保存素材ID及其配置（标题、正文、CTA），支持打标签和搜索
    - 应用历史：记录素材组的应用操作，支持一键重新应用
    - 权限控制：仅个人可见（按 user_id 过滤）
    - 历史限制：每个用户保留最近100条应用历史

数据结构:
    material_groups:
        - name: 素材组名称
        - description: 描述
        - tags: 标签列表
        - materials: 素材配置列表
            - material_id: 素材ID
            - title: 广告标题
            - body: 广告正文
            - call_to_action: CTA按钮类型
        - materials_count: 素材数量
        - username: 创建者用户名
        - real_name: 创建者姓名
        - created_at: 创建时间
        - updated_at: 更新时间

    material_group_histories:
        - group_id: 素材组ID
        - group_name: 素材组名称（快照）
        - materials: 素材配置快照
        - materials_count: 素材数量
        - applied_at: 应用时间
        - username: 应用用户名
        - real_name: 用户姓名
        - apply_mode: 应用方式（replace/append）

索引设计（需通过 init_db.py 创建）:
    # material_groups
    db.material_groups.createIndex({ "username": 1, "name": 1 }, { unique: true })
    db.material_groups.createIndex({ "username": 1, "created_at": -1 })
    db.material_groups.createIndex({ "tags": 1 })

    # material_group_histories
    db.material_group_histories.createIndex({ "username": 1, "applied_at": -1 })
    db.material_group_histories.createIndex({ "group_id": 1 })
"""

from datetime import datetime
from typing import Optional, Literal

from bson import ObjectId
from fastapi import APIRouter, status, Query, Depends, Body

from app.core.security import auth_current_user
from app.db.mongo import cols
from app.model_type_defs.user_models import UserModel
from app.model_type_defs.common_models import ApiResponse, ErrResponse
from app.model_type_defs.ad_create_templates_models import (
    MaterialGroupCreate,
    MaterialGroupUpdate,
    MaterialItem,
)

router = APIRouter(prefix="/operations/material-groups", tags=["素材组管理"])

# MongoDB 集合
material_groups_collection = cols.material_groups
material_group_histories_collection = cols.material_group_histories
materials_collection = cols.materials

# 历史记录保留数量限制
HISTORY_LIMIT = 100


def build_group_list_response(group: dict) -> dict:
    """构建素材组列表响应数据"""
    return {
        "id": str(group.get("_id", "")),
        "name": group.get("name", ""),
        "description": group.get("description", ""),
        "tags": group.get("tags", []),
        "materials_count": group.get("materials_count", 0),
        "created_at": group.get("created_at", ""),
        "updated_at": group.get("updated_at", ""),
        "real_name": group.get("real_name", ""),
    }


def build_group_detail_response(group: dict) -> dict:
    """构建素材组详情响应数据"""
    return {
        "id": str(group.get("_id", "")),
        "name": group.get("name", ""),
        "description": group.get("description", ""),
        "tags": group.get("tags", []),
        "materials": group.get("materials", []),
        "materials_count": group.get("materials_count", 0),
        "created_at": group.get("created_at", ""),
        "updated_at": group.get("updated_at", ""),
        "username": group.get("username", ""),
        "real_name": group.get("real_name", ""),
    }


def build_history_response(history: dict) -> dict:
    """构建历史记录响应数据"""
    return {
        "id": str(history.get("_id", "")),
        "group_id": history.get("group_id", ""),
        "group_name": history.get("group_name", ""),
        "materials_count": history.get("materials_count", 0),
        "applied_at": history.get("applied_at", ""),
        "real_name": history.get("real_name", ""),
        "apply_mode": history.get("apply_mode", ""),
    }


async def filter_valid_materials(material_items: list[MaterialItem]) -> tuple[list[dict], list[str]]:
    """
    过滤有效的素材（检查素材是否存在）
    返回: (有效的素材列表, 无效的素材ID列表)
    """
    if not material_items:
        return [], []

    material_ids = [item.material_id for item in material_items]

    # 批量查询素材是否存在
    valid_material_ids = set()
    cursor = materials_collection.find(
        {"_id": {"$in": [ObjectId(mid) for mid in material_ids if ObjectId.is_valid(mid)]}},
        {"_id": 1}
    )
    async for doc in cursor:
        valid_material_ids.add(str(doc["_id"]))

    # 分离有效和无效的素材
    valid_materials = []
    invalid_material_ids = []

    for item in material_items:
        if item.material_id in valid_material_ids:
            valid_materials.append(item.model_dump())
        else:
            invalid_material_ids.append(item.material_id)

    return valid_materials, invalid_material_ids


async def cleanup_old_histories(username: str):
    """清理超过限制的历史记录（保留最近100条）"""
    # 统计当前用户的历史记录数量
    count = await material_group_histories_collection.count_documents({"username": username})

    if count > HISTORY_LIMIT:
        # 找出需要删除的记录（按时间倒序，跳过最新的100条）
        cursor = material_group_histories_collection.find(
            {"username": username}
        ).sort("applied_at", -1).skip(HISTORY_LIMIT)

        ids_to_delete = []
        async for doc in cursor:
            ids_to_delete.append(doc["_id"])

        if ids_to_delete:
            await material_group_histories_collection.delete_many(
                {"_id": {"$in": ids_to_delete}}
            )


# ==================== 素材组 CRUD 接口 ====================


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_material_group(
    group_in: MaterialGroupCreate,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    创建素材组
    - 素材组名称在同一用户下必须唯一
    - 自动过滤已删除的素材
    - 返回创建的素材组完整信息
    """
    # 检查同一用户下素材组名称是否已存在
    existing = await material_groups_collection.find_one({
        "username": current_user.username,
        "name": group_in.name,
    })
    if existing:
        return ErrResponse(code=400, message=f"素材组名称 '{group_in.name}' 已存在")

    # 过滤有效的素材
    valid_materials, invalid_ids = await filter_valid_materials(group_in.materials)

    if not valid_materials:
        return ErrResponse(code=400, message="所有素材均不存在或已被删除，无法创建素材组")

    # 构建素材组数据
    now = datetime.utcnow().isoformat()
    group_data = {
        "name": group_in.name,
        "description": group_in.description,
        "tags": group_in.tags,
        "materials": valid_materials,
        "materials_count": len(valid_materials),
        "username": current_user.username,
        "real_name": current_user.real_name,
        "created_at": now,
        "updated_at": now,
    }

    # 插入数据库
    result = await material_groups_collection.insert_one(group_data)
    group_data["_id"] = result.inserted_id

    response_data = build_group_detail_response(group_data)

    # 如果有无效素材，添加提示信息
    message = "素材组创建成功"
    if invalid_ids:
        message += f"（已过滤 {len(invalid_ids)} 个无效素材）"

    return ApiResponse(data=response_data, message=message)


@router.get("/")
async def get_material_groups(
    name: Optional[str] = Query(None, description="按名称模糊搜索"),
    tags: Optional[str] = Query(None, description="按标签筛选（逗号分隔多个标签）"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: UserModel = Depends(auth_current_user),
):
    """
    获取素材组列表
    - 仅返回当前用户创建的素材组
    - 支持按名称模糊搜索
    - 支持按标签筛选（多个标签取交集）
    - 支持分页
    - 按创建时间倒序排列
    """
    query = {"username": current_user.username}

    if name:
        query["name"] = {"$regex": name, "$options": "i"}

    if tags:
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        if tag_list:
            query["tags"] = {"$all": tag_list}

    # 统计总数
    total = await material_groups_collection.count_documents(query)

    # 分页查询
    skip = (page - 1) * size
    cursor = material_groups_collection.find(query).sort("created_at", -1).skip(skip).limit(size)

    items = []
    async for group in cursor:
        items.append(build_group_list_response(group))

    return ApiResponse(data={
        "items": items,
        "total": total,
        "page": page,
        "size": size,
    })


# ==================== 应用历史记录接口（静态路由必须在动态路由之前） ====================


@router.get("/histories")
async def get_material_group_histories(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(10, ge=1, le=100, description="每页数量"),
    current_user: UserModel = Depends(auth_current_user),
):
    """
    获取应用历史记录列表
    - 仅返回当前用户的历史记录
    - 按应用时间倒序排列
    - 支持分页
    """
    query = {"username": current_user.username}

    # 统计总数
    total = await material_group_histories_collection.count_documents(query)

    # 分页查询
    skip = (page - 1) * size
    cursor = material_group_histories_collection.find(query).sort("applied_at", -1).skip(skip).limit(size)

    items = []
    async for history in cursor:
        items.append(build_history_response(history))

    return ApiResponse(data={
        "items": items,
        "total": total,
        "page": page,
        "size": size,
    })


@router.get("/histories/{history_id}")
async def get_material_group_history_detail(
    history_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    获取历史记录详情
    - 返回完整的素材配置快照
    - 仅能查看自己的历史记录
    """
    try:
        history = await material_group_histories_collection.find_one({
            "_id": ObjectId(history_id),
            "username": current_user.username,
        })
    except Exception:
        return ErrResponse(code=400, message="无效的历史记录ID")

    if not history:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="历史记录不存在或无权访问")

    response_data = {
        "id": str(history["_id"]),
        "group_id": history.get("group_id", ""),
        "group_name": history.get("group_name", ""),
        "materials": history.get("materials", []),
        "materials_count": history.get("materials_count", 0),
        "applied_at": history.get("applied_at", ""),
        "real_name": history.get("real_name", ""),
        "apply_mode": history.get("apply_mode", ""),
    }

    return ApiResponse(data=response_data)


@router.post("/histories/{history_id}/reapply")
async def reapply_material_group_history(
    history_id: str,
    mode: Literal["replace", "append"] = Body(..., embed=True, description="应用方式: replace=替换, append=追加"),
    current_user: UserModel = Depends(auth_current_user),
):
    """
    重新应用历史快照
    - 使用历史记录中保存的素材配置
    - 自动过滤已删除的素材
    - 创建新的历史记录
    """
    try:
        history = await material_group_histories_collection.find_one({
            "_id": ObjectId(history_id),
            "username": current_user.username,
        })
    except Exception:
        return ErrResponse(code=400, message="无效的历史记录ID")

    if not history:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="历史记录不存在或无权访问")

    # 过滤有效的素材
    materials = history.get("materials", [])
    material_items = [MaterialItem(**m) for m in materials]
    valid_materials, invalid_ids = await filter_valid_materials(material_items)

    if not valid_materials:
        return ErrResponse(code=400, message="该历史记录中的所有素材均已被删除，无法应用")

    # 创建新的历史记录
    new_history_data = {
        "group_id": history.get("group_id", ""),
        "group_name": history.get("group_name", ""),
        "materials": valid_materials,
        "materials_count": len(valid_materials),
        "applied_at": datetime.utcnow().isoformat(),
        "username": current_user.username,
        "real_name": current_user.real_name,
        "apply_mode": mode,
    }

    result = await material_group_histories_collection.insert_one(new_history_data)
    new_history_id = str(result.inserted_id)

    # 清理超过限制的历史记录
    await cleanup_old_histories(current_user.username)

    # 返回数据供前端使用
    response_data = {
        "history_id": new_history_id,
        "materials": valid_materials,
        "mode": mode,
    }

    message = "历史记录应用成功"
    if invalid_ids:
        message += f"（已自动过滤 {len(invalid_ids)} 个已删除的素材）"

    return ApiResponse(data=response_data, message=message)


# ==================== 素材组详情/更新/删除/应用接口（动态路由放在后面） ====================


@router.get("/{group_id}")
async def get_material_group_detail(
    group_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    获取素材组详情
    - 返回完整的素材配置信息
    - 仅能查看自己创建的素材组
    """
    try:
        group = await material_groups_collection.find_one({
            "_id": ObjectId(group_id),
            "username": current_user.username,
        })
    except Exception:
        return ErrResponse(code=400, message="无效的素材组ID")

    if not group:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="素材组不存在或无权访问")

    return ApiResponse(data=build_group_detail_response(group))


@router.put("/{group_id}")
async def update_material_group(
    group_id: str,
    group_update: MaterialGroupUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    更新素材组
    - 如果修改名称，需要检查新名称是否已存在
    - 如果更新素材列表，会自动过滤已删除的素材
    - 仅能更新自己创建的素材组
    """
    try:
        group = await material_groups_collection.find_one({
            "_id": ObjectId(group_id),
            "username": current_user.username,
        })
    except Exception:
        return ErrResponse(code=400, message="无效的素材组ID")

    if not group:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="素材组不存在或无权访问")

    # 如果修改名称，检查新名称是否已存在
    if group_update.name and group_update.name != group.get("name"):
        existing = await material_groups_collection.find_one({
            "username": current_user.username,
            "name": group_update.name,
            "_id": {"$ne": ObjectId(group_id)},
        })
        if existing:
            return ErrResponse(code=400, message=f"素材组名称 '{group_update.name}' 已存在")

    # 构建更新数据
    update_data = {}
    warning_message = None

    if group_update.name is not None:
        update_data["name"] = group_update.name
    if group_update.description is not None:
        update_data["description"] = group_update.description
    if group_update.tags is not None:
        update_data["tags"] = group_update.tags

    # 如果更新素材列表，过滤无效素材
    if group_update.materials is not None:
        valid_materials, invalid_ids = await filter_valid_materials(group_update.materials)
        if not valid_materials:
            return ErrResponse(code=400, message="所有素材均不存在或已被删除，无法更新素材组")

        update_data["materials"] = valid_materials
        update_data["materials_count"] = len(valid_materials)

        if invalid_ids:
            warning_message = f"已过滤 {len(invalid_ids)} 个无效素材"

    update_data["updated_at"] = datetime.utcnow().isoformat()

    # 更新数据库
    await material_groups_collection.update_one(
        {"_id": ObjectId(group_id)},
        {"$set": update_data}
    )

    # 获取更新后的数据
    updated_group = await material_groups_collection.find_one({"_id": ObjectId(group_id)})

    message = "素材组更新成功"
    if warning_message:
        message += f"（{warning_message}）"

    return ApiResponse(data=build_group_detail_response(updated_group), message=message)


@router.delete("/{group_id}")
async def delete_material_group(
    group_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    删除素材组
    - 仅能删除自己创建的素材组
    - 删除后不可恢复（直接删除，不移入回收站）
    """
    try:
        result = await material_groups_collection.delete_one({
            "_id": ObjectId(group_id),
            "username": current_user.username,
        })
    except Exception:
        return ErrResponse(code=400, message="无效的素材组ID")

    if result.deleted_count == 0:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="素材组不存在或无权访问")

    return ApiResponse(data=None, message="素材组已删除")


# ==================== 素材组应用接口 ====================


@router.post("/{group_id}/apply")
async def apply_material_group(
    group_id: str,
    mode: Literal["replace", "append"] = Body(..., embed=True, description="应用方式: replace=替换, append=追加"),
    current_user: UserModel = Depends(auth_current_user),
):
    """
    应用素材组
    - 自动过滤已删除的素材
    - 支持替换或追加模式
    - 创建应用历史记录
    - 自动清理超过100条的历史记录
    """
    try:
        group = await material_groups_collection.find_one({
            "_id": ObjectId(group_id),
            "username": current_user.username,
        })
    except Exception:
        return ErrResponse(code=400, message="无效的素材组ID")

    if not group:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="素材组不存在或无权访问")

    # 过滤有效的素材
    materials = group.get("materials", [])
    material_items = [MaterialItem(**m) for m in materials]
    valid_materials, invalid_ids = await filter_valid_materials(material_items)

    if not valid_materials:
        return ErrResponse(code=400, message="该素材组中的所有素材均已被删除，无法应用")

    # 创建应用历史记录
    history_data = {
        "group_id": str(group["_id"]),
        "group_name": group.get("name", ""),
        "materials": valid_materials,
        "materials_count": len(valid_materials),
        "applied_at": datetime.utcnow().isoformat(),
        "username": current_user.username,
        "real_name": current_user.real_name,
        "apply_mode": mode,
    }

    result = await material_group_histories_collection.insert_one(history_data)
    history_id = str(result.inserted_id)

    # 清理超过限制的历史记录
    await cleanup_old_histories(current_user.username)

    # 返回数据供前端使用
    response_data = {
        "history_id": history_id,
        "materials": valid_materials,
        "mode": mode,
    }

    message = "素材组应用成功"
    if invalid_ids:
        message += f"（已自动过滤 {len(invalid_ids)} 个已删除的素材）"

    return ApiResponse(data=response_data, message=message)
