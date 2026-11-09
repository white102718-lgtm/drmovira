"""
广告配置模板 API
集合名称: ad_create_templates
路径前缀: /operations/templates

数据结构：
    - name: 模板名称
    - real_name: 创建者名称
    - description: 描述
    - settings: 完整设置
        - series: 广告系列设置
        - adGroup: 广告组设置
        - regionGroup: 地区组定向设置
        - derived: 派生设置

索引设计（通过 init_db.py 创建）:
    # 用户级别模板名唯一索引
    db.ad_create_templates.createIndex({ "real_name": 1, "name": 1 }, { unique: true })

    # 用户查询索引
    db.ad_create_templates.createIndex({ "real_name": 1 })

    # 时间排序索引
    db.ad_create_templates.createIndex({ "create_time": -1 })

数据迁移（已有数据设置默认 real_name）:
    db.ad_create_templates.updateMany(
        { "real_name": { "$exists": false } },
        { "$set": { "real_name": "system" } }
    )
"""

from datetime import datetime

from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, status, Query, Depends

from app.core.security import auth_current_user
from app.db.mongo import cols, trash
from app.model_type_defs.user_models import UserModel
from app.model_type_defs.common_models import ApiResponse, ErrResponse, SecondFormat
from app.model_type_defs.ad_create_templates_models import (
    AdCreateTemplateCreate,
    AdCreateTemplateUpdate,
    MaterialTemplateCreate,
    MaterialTemplateUpdate,
)

router = APIRouter(prefix="/operations/templates", tags=["广告配置模板"])

# MongoDB 集合 - 广告配置模板
collection = cols.ad_create_templates
collection_trash = trash.ad_create_templates

# MongoDB 集合 - 素材模板
material_collection = cols.material_templates
material_collection_trash = trash.material_templates


def build_simple_response(template: dict) -> dict:
    """构建简洁的响应数据结构（用于列表查询）"""
    return {
        "id": str(template.get("_id", "")),
        "name": template.get("name", ""),
        "real_name": template.get("real_name", ""),
        "description": template.get("description"),
    }


def build_full_response(template: dict, template_id: str = None) -> dict:
    """构建完整的响应数据结构（用于创建和更新）"""
    tid = template_id or str(template.get("_id", ""))

    return {
        "id": tid,
        "name": template.get("name", ""),
        "real_name": template.get("real_name", ""),
        "description": template.get("description"),
        "settings": template.get("settings", {})
    }


@router.get("/")
async def get_templates(
    real_name: Optional[str] = Query(None, description="按创建者筛选"),
    name: Optional[str] = Query(None, description="按模板名查询（模糊匹配）"),
):
    """
    获取模板列表（用于下拉选择）
    - 支持按创建者筛选
    - 支持按模板名模糊查询
    - 按创建时间降序排列
    - 返回全部模板（简洁结构）
    """
    query = {}
    if real_name:
        query["real_name"] = real_name
    if name:
        query["name"] = {"$regex": name, "$options": "i"}
    cursor = collection.find(query).sort("create_time", -1)
    templates = await cursor.to_list(length=None)

    items = []
    for template in templates:
        items.append(build_simple_response(template))

    return ApiResponse(data=items)


# ==================== 树形结构接口（用于创建广告页面展示模板） ====================


@router.get("/tree")
async def get_templates_tree(
    real_name: Optional[str] = Query(None, description="按创建者筛选"),
):
    """
    获取模板树形结构
    - 支持按创建者筛选
    - 返回精简的层级结构数据，用于创建广告页面展示
    """
    query = {}
    if real_name:
        query["real_name"] = real_name
    cursor = collection.find(query).sort("create_time", -1)
    templates = await cursor.to_list(length=None)

    tree_data = []
    for template in templates:
        tree_data.append(build_simple_response(template))

    return ApiResponse(data=tree_data)


# ==================== 素材模板接口 ====================
# 路径前缀: /operations/templates/materials
# 注意：静态路由必须放在动态路由 /{template_id} 之前，避免路由匹配冲突


@router.get("/materials")
async def get_material_templates(
    real_name: Optional[str] = Query(None, description="按创建者筛选"),
    name: Optional[str] = Query(None, description="按模板名查询（模糊匹配）"),
):
    """
    获取素材模板列表（用于下拉选择）
    - 支持按创建者筛选
    - 支持按模板名模糊查询
    - 按创建时间降序排列
    - 返回全部模板
    """
    query = {}
    if real_name:
        query["real_name"] = real_name
    if name:
        query["name"] = {"$regex": name, "$options": "i"}
    cursor = material_collection.find(query).sort("create_time", -1)
    templates = await cursor.to_list(length=None)

    items = []
    for template in templates:
        items.append({
            "id": str(template.pop("_id")),
            "name": template.get("name"),
            "real_name": template.get("real_name"),
            "description": template.get("description"),
            "batchTitle": template.get("batchTitle"),
            "batchDescription": template.get("batchDescription"),
        })

    return ApiResponse(data=items)


@router.get("/materials/{template_id}")
async def get_material_template_detail(template_id: str):
    """
    获取单个素材模板详情
    """
    try:
        template = await material_collection.find_one({"_id": ObjectId(template_id)})
    except Exception:
        return ErrResponse(code=400, message="无效的模板ID")

    if not template:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="模板不存在")

    response_data = {
        "id": str(template.pop("_id")),
        "name": template.get("name"),
        "real_name": template.get("real_name"),
        "description": template.get("description"),
        "batchTitle": template.get("batchTitle"),
        "batchDescription": template.get("batchDescription"),
    }
    return ApiResponse(data=response_data)


@router.post("/materials")
async def create_material_template(template_in: MaterialTemplateCreate):
    """
    创建新素材模板
    - 模板名称在同一用户下必须唯一
    - 返回 MaterialTemplateCreate 定义的字段 + id
    """
    # 检查同一用户下模板名称是否已存在
    existing = await material_collection.find_one({
        "name": template_in.name,
        "real_name": template_in.real_name,
    })
    if existing:
        return ErrResponse(code=400, message="模板名称已存在")

    # 构建模板数据
    now = datetime.now().strftime(SecondFormat)
    template_data = template_in.model_dump()
    template_data["create_time"] = now
    template_data["update_time"] = now

    # 插入数据库
    result = await material_collection.insert_one(template_data)

    # 返回 MaterialTemplateCreate 定义的字段 + id
    response_data = template_in.model_dump()
    response_data["id"] = str(result.inserted_id)

    return ApiResponse(data=response_data, message="创建模板成功")


@router.put("/materials/{template_id}")
async def update_material_template(
    template_id: str,
    template_update: MaterialTemplateUpdate,
):
    """
    更新素材模板
    - 如果修改名称，需要检查新名称是否已存在
    - 返回 MaterialTemplateUpdate 定义的所有字段 + id
    """
    try:
        template = await material_collection.find_one({"_id": ObjectId(template_id)})
    except Exception:
        return ErrResponse(code=400, message="无效的模板ID")

    if not template:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="模板不存在")

    # 如果修改模板名称，检查同一用户下新名称是否已存在
    if template_update.name and template_update.name != template.get("name"):
        existing = await material_collection.find_one({
            "name": template_update.name,
            "real_name": template.get("real_name"),
            "_id": {"$ne": ObjectId(template_id)},
        })
        if existing:
            return ErrResponse(code=400, message="模板名称已存在")

    # 构建更新数据
    update_data = {}
    if template_update.name is not None:
        update_data["name"] = template_update.name
    if template_update.real_name is not None:
        update_data["real_name"] = template_update.real_name
    if template_update.description is not None:
        update_data["description"] = template_update.description
    if template_update.batchTitle is not None:
        update_data["batchTitle"] = template_update.batchTitle
    if template_update.batchDescription is not None:
        update_data["batchDescription"] = template_update.batchDescription

    update_data["update_time"] = datetime.now().strftime(SecondFormat)

    # 更新数据库
    await material_collection.update_one(
        {"_id": ObjectId(template_id)},
        {"$set": update_data}
    )

    # 获取更新后的完整数据，返回所有字段 + id
    updated_template = await material_collection.find_one({"_id": ObjectId(template_id)})
    response_data = {
        "id": template_id,
        "name": updated_template.get("name"),
        "real_name": updated_template.get("real_name"),
        "description": updated_template.get("description"),
        "batchTitle": updated_template.get("batchTitle"),
        "batchDescription": updated_template.get("batchDescription"),
    }

    return ApiResponse(data=response_data, message="更新模板成功")


@router.delete("/materials/{template_id}")
async def delete_material_template(
    template_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    删除素材模板
    - 删除的模板会移动到回收站
    - 记录删除操作者
    """
    try:
        template = await material_collection.find_one_and_delete({"_id": ObjectId(template_id)})
    except Exception:
        return ErrResponse(code=400, message="无效的模板ID")

    if not template:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="模板不存在")

    # 添加删除信息并移动到回收站
    template["delete_time"] = datetime.now().strftime(SecondFormat)
    template["deleted_by"] = current_user.username
    await material_collection_trash.insert_one(template)

    return ApiResponse(data=None, message="模板已删除")


# ==================== 广告配置模板详情接口 ====================
# 注意：动态路由 /{template_id} 必须放在所有静态路由之后


@router.get("/{template_id}")
async def get_template_detail(template_id: str):
    """
    获取单个模板详情（完整结构，包含 settings）
    """
    try:
        template = await collection.find_one({"_id": ObjectId(template_id)})
    except Exception:
        return ErrResponse(code=400, message="无效的模板ID")

    if not template:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="模板不存在")

    return ApiResponse(data=build_full_response(template, template_id))


@router.post("/")
async def create_template(template_in: AdCreateTemplateCreate):
    """
    创建新模板
    - 模板名称在同一用户下必须唯一
    - 返回完整的模板数据结构
    """
    # 检查同一用户下模板名称是否已存在
    existing = await collection.find_one({
        "name": template_in.name,
        "real_name": template_in.real_name,
    })
    if existing:
        return ErrResponse(code=400, message="模板名称已存在")

    # 构建模板数据
    now = datetime.now().strftime(SecondFormat)
    template_data = template_in.model_dump()
    template_data["create_time"] = now
    template_data["update_time"] = now

    # 插入数据库
    result = await collection.insert_one(template_data)

    # 返回完整的模板数据结构
    response_data = {
        "id": str(result.inserted_id),
        "name": template_in.name,
        "real_name": template_in.real_name,
        "description": template_in.description,
        "settings": template_in.settings
    }

    return ApiResponse(data=response_data, message="创建模板成功")


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    template_update: AdCreateTemplateUpdate,
):
    """
    更新模板
    - 如果修改名称，需要检查新名称是否已存在
    - 返回完整的模板数据结构
    """
    try:
        template = await collection.find_one({"_id": ObjectId(template_id)})
    except Exception:
        return ErrResponse(code=400, message="无效的模板ID")

    if not template:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="模板不存在")

    # 如果修改模板名称，检查同一用户下新名称是否已存在
    if template_update.name and template_update.name != template.get("name"):
        existing = await collection.find_one({
            "name": template_update.name,
            "real_name": template.get("real_name"),
            "_id": {"$ne": ObjectId(template_id)},
        })
        if existing:
            return ErrResponse(code=400, message="模板名称已存在")

    # 构建更新数据
    update_data = {}
    if template_update.name is not None:
        update_data["name"] = template_update.name
    if template_update.real_name is not None:
        update_data["real_name"] = template_update.real_name
    if template_update.description is not None:
        update_data["description"] = template_update.description

    # settings 直接替换，不做合并处理
    if template_update.settings is not None:
        update_data["settings"] = template_update.settings

    update_data["update_time"] = datetime.now().strftime(SecondFormat)

    # 更新数据库
    await collection.update_one(
        {"_id": ObjectId(template_id)},
        {"$set": update_data}
    )

    # 获取更新后的完整数据
    updated_template = await collection.find_one({"_id": ObjectId(template_id)})

    return ApiResponse(data=build_full_response(updated_template, template_id), message="更新模板成功")


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    删除模板
    - 删除的模板会移动到回收站
    - 记录删除操作者
    """
    try:
        template = await collection.find_one_and_delete({"_id": ObjectId(template_id)})
    except Exception:
        return ErrResponse(code=400, message="无效的模板ID")

    if not template:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="模板不存在")

    # 添加删除信息并移动到回收站
    template["delete_time"] = datetime.now().strftime(SecondFormat)
    template["deleted_by"] = current_user.username
    await collection_trash.insert_one(template)

    return ApiResponse(data=None, message="模板已删除")