import asyncio
import base64
import io
import json
import re
from datetime import datetime
from io import BytesIO
from typing import Optional

import pandas as pd
from bson import ObjectId
from fastapi import APIRouter, Depends, Query, status, UploadFile, File
from openpyxl import Workbook
from openpyxl.styles import Font
from pymongo import UpdateOne

from app.api.routes.department import get_department_lineage
from app.core.security import auth_current_user
from app.db.async_mysql import AsyncMySQL
from app.db.clients import get_db
from app.db.mongo import cols, trash, user_cols
from app.model_type_defs.ad_operation import OperationFields, OpType
from app.model_type_defs.common_models import ApiResponse, ErrResponse, SecondFormat
from app.model_type_defs.platform_models import (
    PlatformConfigCreate,
    PlatformConfigUpdate,
    AgentLineConfigCreate,
    AgentLineConfigUpdate,
    AgentLineKpiConfig,
)
from app.model_type_defs.user_models import Roles, UserModel

router = APIRouter(
    prefix="/platform-config",
    tags=["平台代理线配置"],
)

collection = cols.platform_config
agent_collection = cols.agent_line_config
kpi_collection = cols.agent_line_kpi_config
fb_pixels_collection = cols.fb_pixels
material_category_collection = cols.material_category

collection_trash = trash.platform_config
material_category_trash = trash.material_category


async def get_pixel_id_by_name(pixel_name: str) -> Optional[str]:
    """根据像素名称查询像素ID"""
    if not pixel_name:
        return None
    doc = await fb_pixels_collection.find_one({"name": pixel_name})
    if doc:
        return str(doc["_id"])
    return None


async def get_pixel_ids_by_names(pixel_names: list[str]) -> dict[str, str]:
    """批量根据像素名称查询像素ID"""
    if not pixel_names:
        return {}
    pixel_name_to_id = {}
    cursor = fb_pixels_collection.find({"name": {"$in": pixel_names}})
    async for doc in cursor:
        pixel_name_to_id[doc["name"]] = str(doc["_id"])
    return pixel_name_to_id


agent_collection_trash = trash.agent_line_config
kpi_collection_trash = trash.agent_line_kpi_config


async def link_agent_lines_to_platform(game_platform: str, agent_lines: list[str]):
    """
    统一将代理线关联到平台配置
    """
    if not agent_lines:
        return
    await collection.update_one(
        {"_id": game_platform},
        {"$addToSet": {"agent_lines": {"$each": agent_lines}}},
    )


async def soft_delete_agent_line(agent_line_id: str, current_user_name: str):
    """
    软删除代理线:
    1. 移动到 trash 集合 (修改_id防止冲突)
    2. 从 agent_line_config 删除
    3. 从所有 platform_config.agent_lines 中移除引用
    """
    # 1 & 2: Move to Trash & Delete
    config = await agent_collection.find_one_and_delete({"_id": agent_line_id})
    if config:
        config["delete_time"] = datetime.now().strftime(SecondFormat)
        config["deleted_by"] = current_user_name
        # 修改 _id 防止冲突
        config["_id"] = f"{config['_id']}_del_{int(datetime.now().timestamp())}"
        await agent_collection_trash.insert_one(config)

    # 3: Unlink from platforms
    await collection.update_many(
        {"agent_lines": agent_line_id},
        {"$pull": {"agent_lines": agent_line_id}},
    )


async def soft_delete_platform(game_platform: str, current_user_name: str):
    """
    软删除平台:
    1. 级联软删除关联的 agent_lines (Move to Trash, 修改_id)
    2. 级联软删除关联的 KPIs (Move to Trash)
    3. 级联软删除关联的 material_categories (Move to Trash)
    4. 软删除平台自身 (Move to Trash, 修改_id)
    """
    config = await collection.find_one({"_id": game_platform})
    if not config:
        return False

    # 1. Cascade Delete Agent Lines
    agent_line_ids = config.get("agent_lines", [])
    if agent_line_ids:
        # 批量查询并移动到 Trash
        lines = await agent_collection.find({"_id": {"$in": agent_line_ids}}).to_list()
        if lines:
            for line in lines:
                line["delete_time"] = datetime.now().strftime(SecondFormat)
                line["deleted_by"] = current_user_name
                # 修改 _id 防止冲突
                line["_id"] = f"{line['_id']}_del_{int(datetime.now().timestamp())}"
            await agent_collection_trash.insert_many(lines)
            await agent_collection.delete_many({"_id": {"$in": agent_line_ids}})

    # 2. Cascade Delete KPIs
    kpis = await kpi_collection.find({"game_platform": game_platform}).to_list()
    if kpis:
        await kpi_collection_trash.insert_many(kpis)
        await kpi_collection.delete_many({"game_platform": game_platform})

    # 3. Cascade Delete Material Categories
    material_category_ids = config.get("material_category_ids", [])
    if material_category_ids:
        object_ids = [ObjectId(cid) for cid in material_category_ids]
        categories = await material_category_collection.find(
            {"_id": {"$in": object_ids}}
        ).to_list()
        if categories:
            for cat in categories:
                cat["delete_time"] = datetime.now().strftime(SecondFormat)
                cat["deleted_by"] = current_user_name
                cat["original_id"] = str(cat["_id"])
                cat["_id"] = ObjectId()
            await material_category_trash.insert_many(categories)
            await material_category_collection.delete_many({"_id": {"$in": object_ids}})

    # 4. Delete Platform
    config["delete_time"] = datetime.now().strftime(SecondFormat)
    config["deleted_by"] = current_user_name
    # 修改 _id 防止冲突
    config["_id"] = f"{config['_id']}_del_{int(datetime.now().timestamp())}"
    await collection_trash.insert_one(config)
    await collection.delete_one({"_id": game_platform})
    return True


@router.get("/")
async def get_platform_configs(
    page: Optional[int] = None,
    pageSize: Optional[int] = None,
    game_platform: Optional[str] = None,
    agent_line: Optional[str] = None,
    department: Optional[str] = None,
    current_user: UserModel = Depends(auth_current_user),
):
    query = {}
    if game_platform:
        query["_id"] = {"$regex": game_platform, "$options": "i"}
    if agent_line:
        query["agent_lines"] = agent_line
    if department:
        query["$or"] = [
            {"departments": department},
            {"internal_team": department},
            {"external_team": department},
        ]
    # 非 admin 只能看到本人部门(含祖先/后代部门)所属的平台
    if Roles.ADMIN not in current_user.roles:
        user_departments = await get_department_lineage(current_user.department)
        query["$and"] = [
            {
                "$or": [
                    {"internal_team": {"$in": user_departments}},
                    {"external_team": {"$in": user_departments}},
                ]
            }
        ]

    total = await collection.count_documents(query)
    cursor = collection.find(query, {"agent_lines": 0}).sort("_id", 1)

    # 有分页参数时进行分页
    if page and pageSize:
        skip = (page - 1) * pageSize
        cursor = cursor.skip(skip).limit(pageSize)
        configs = await cursor.to_list(length=pageSize)
    else:
        configs = await cursor.to_list(length=None)

    items = []
    for config in configs:
        items.append(config)

    return ApiResponse(
        data={
            "items": items,
            "total": total,
            "page": page,
            "pageSize": pageSize,
        }
    )


@router.get("/agent_options/")
async def get_agent_options(
    platform: Optional[str] = None, agent_name: Optional[str] = None
):
    query = {}
    if platform:
        query["_id"] = platform
    # 只有在没有指定 platform 且 show_all 为 False 时，才过滤隐藏的平台

    if agent_name:
        regex = re.escape(agent_name)
        query["agent_lines"] = {"$regex": regex, "$options": "i"}
        # $filter 只保留匹配的代理线，避免返回整条数组
        cursor = collection.aggregate(
            [
                {"$match": query},
                {
                    "$project": {
                        "agent_lines": {
                            "$filter": {
                                "input": "$agent_lines",
                                "as": "line",
                                "cond": {
                                    "$regexMatch": {
                                        "input": "$$line",
                                        "regex": regex,
                                        "options": "i",
                                    }
                                },
                            }
                        }
                    }
                },
            ]
        )
    else:
        cursor = collection.find(query, {"agent_lines": 1})

    result = []
    async for doc in cursor:
        result.append(doc)
    return ApiResponse(data=result)


@router.get("/plat_options/")
async def get_platform_options():
    res = await collection.distinct("_id")
    return ApiResponse(data=res)


@router.post("/")
async def create_platform_config(
    config_in: PlatformConfigCreate,
    current_user: UserModel = Depends(auth_current_user),
):
    game_platform = config_in.game_platform
    # _id 就是 game_platform
    existing = await collection.find_one({"_id": game_platform})
    if existing:
        return ErrResponse(code=400, message="平台名称已存在")
    config_data = config_in.model_dump(by_alias=True)

    # null 会让 erp_kpi_sync 的 $addToSet 报错, 数组字段一律落 []
    config_data["target_region"] = config_data["target_region"] or []
    config_data["agent_lines"] = []
    config_data["material_category_ids"] = []
    config_data["enabled"] = True
    config_data["visible"] = True
    config_data["create_time"] = datetime.now().strftime(SecondFormat)
    config_data["update_time"] = config_data["create_time"]
    config_data["created_by"] = current_user.username
    await collection.insert_one(config_data)
    created_config = await collection.find_one(
        {"_id": game_platform}, {"agent_lines": 0}
    )
    # 添加默认kpi
    kpi_config = AgentLineKpiConfig(game_platform=game_platform, agent_lines=[])
    await create_agent_line_kpi_logic(kpi_config.model_dump(), current_user)
    return ApiResponse(data=created_config)


@router.put("/{game_platform}")
async def update_platform_config(
    game_platform: str,
    config_update: PlatformConfigUpdate,
    current_user: UserModel = Depends(auth_current_user),
    db=Depends(get_db),
):
    # _id 就是 game_platform
    config = await collection.find_one({"_id": game_platform})
    if not config:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到平台配置")

    update_data = {k: v for k, v in config_update.model_dump().items() if v is not None}
    update_data["update_time"] = datetime.now().strftime(SecondFormat)
    update_data["updated_by"] = current_user.username
    await collection.update_one({"_id": game_platform}, {"$set": update_data})
    updated_config = await collection.find_one(
        {"_id": game_platform}, {"agent_lines": 0}
    )
    return ApiResponse(data=updated_config)


@router.delete("/{game_platform}")
async def delete_platform_config(
    game_platform: str,
    current_user: UserModel = Depends(auth_current_user),
):
    # _id 就是 game_platform
    deleted = await soft_delete_platform(game_platform, current_user.username)
    if not deleted:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到平台配置")

    return ApiResponse(data=None, message="平台配置已删除")


@router.get("/agent-line-kpi/")
async def get_agent_line_kpi_configs(
    game_platform: Optional[str] = None,
    agent_line: Optional[str] = None,
):
    """
    获取KPI配置列表

    Args:
        game_platform: 平台名称（可选，不传则返回所有平台）
        agent_line: 代理线名称（支持前缀匹配）
            示例：传入 "come-nyc-10" 会匹配 "come-nyc-10", "come-nyc-100", "come-nyc-101" 等
    """
    query = {"game_platform": game_platform} if game_platform else {}
    cursor = kpi_collection.find(query)
    configs = await cursor.to_list()

    items = []
    for config in configs:
        config["id"] = str(config.pop("_id"))
        if agent_line:
            agent_line_lower = agent_line.lower()
            if not any(
                l.lower().startswith(agent_line_lower)
                for l in config.get("agent_lines", [])
            ):
                continue
        items.append(config)
    return ApiResponse(data=items)


async def create_agent_line_kpi_logic(
    config_data: dict, current_user: UserModel
) -> dict:
    config_data["create_time"] = datetime.now().strftime(SecondFormat)
    config_data["update_time"] = config_data["create_time"]
    config_data["created_by"] = current_user.username
    result = await kpi_collection.insert_one(config_data)
    created_config = await kpi_collection.find_one({"_id": result.inserted_id})
    created_config["id"] = str(created_config.pop("_id"))
    return created_config


@router.post("/agent-line-kpi/")
async def create_agent_line_kpi_config(
    config_in: AgentLineKpiConfig,
    current_user: UserModel = Depends(auth_current_user),
):
    config_data = config_in.model_dump()
    created_config = await create_agent_line_kpi_logic(config_data, current_user)
    return ApiResponse(data=created_config)


@router.put("/agent-line-kpi/{config_id}")
async def update_agent_line_kpi_config(
    config_id: str,
    config_update: AgentLineKpiConfig,
    current_user: UserModel = Depends(auth_current_user),
):
    config = await kpi_collection.find_one({"_id": ObjectId(config_id)})
    if not config:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到KPI配置")
    update_data = {k: v for k, v in config_update.model_dump().items() if v is not None}
    update_data["update_time"] = datetime.now().strftime(SecondFormat)
    update_data["updated_by"] = current_user.username
    await kpi_collection.update_one({"_id": ObjectId(config_id)}, {"$set": update_data})
    updated_config = await kpi_collection.find_one({"_id": ObjectId(config_id)})
    updated_config["id"] = str(updated_config.pop("_id"))
    return ApiResponse(data=updated_config)


@router.delete("/agent-line-kpi/{config_id}")
async def delete_agent_line_kpi_config(
    config_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    config = await kpi_collection.find_one_and_delete({"_id": ObjectId(config_id)})
    if not config:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到KPI配置")
    update_data = {
        "delete_time": datetime.now().strftime(SecondFormat),
        "deleted_by": current_user.username,
    }
    config.update(update_data)
    await kpi_collection_trash.insert_one(config)
    return ApiResponse(data=None, message="KPI配置已删除")


@router.get("/agent-line/")
async def get_agent_line_configs(
    game_platform: Optional[str] = None,
    agent_line: Optional[str] = None,
    department: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1, description="页码,从1开始"),
    page_size: Optional[int] = Query(None, ge=1, le=200, description="每页数量"),
    current_user: UserModel = Depends(auth_current_user),
):
    """
    获取代理线配置列表。传分页参数时分页，否则返回全部记录。

    Args:
        game_platform: 平台名称（可选）
        agent_line: 代理线名称（支持前缀匹配）
            示例：传入 "come-nyc-10" 会匹配 "come-nyc-10", "come-nyc-100", "come-nyc-101" 等
        department: 部门名称（可选），按优化师所属部门筛选
        page: 页码,从1开始
        page_size: 每页数量,默认20,最大200

    返回:
        {"items": [...], "total": N, "page": N, "page_size": N}
    """
    # 部门过滤:先解析为该部门下所有用户的 real_name
    department_optimizers: Optional[list] = None
    if department:
        users = await user_cols.user.find(
            {"department": department},
            {"real_name": 1},
        ).to_list(length=None)
        department_optimizers = [u["real_name"] for u in users if u.get("real_name")]

    paginate = page is not None or page_size is not None
    current_page = page or 1
    current_page_size = page_size or 20
    empty_response = {
        "items": [],
        "total": 0,
        "page": current_page if paginate else None,
        "page_size": current_page_size if paginate else None,
    }

    # 权限: 非 admin 只能看到本人部门(含祖先/后代部门)所属平台下的代理线
    is_admin = Roles.ADMIN in current_user.roles
    allowed_line_ids: Optional[set] = None
    if not is_admin:
        user_departments = await get_department_lineage(current_user.department)
        dept_platforms = await collection.find(
            {
                "$or": [
                    {"internal_team": {"$in": user_departments}},
                    {"external_team": {"$in": user_departments}},
                ]
            },
            {"agent_lines": 1},
        ).to_list(length=None)
        allowed_line_ids = {
            line for p in dept_platforms for line in p.get("agent_lines", [])
        }
        if not allowed_line_ids:
            return ApiResponse(data=empty_response)

    # 构建 Mongo 查询条件
    if game_platform:
        platform = await collection.find_one(
            {"_id": game_platform}, {"agent_lines": 1}
        )
        if not platform or not platform.get("agent_lines"):
            return ApiResponse(data=empty_response)
        agent_line_ids = platform["agent_lines"]
        if agent_line:
            agent_line_lower = agent_line.lower()
            agent_line_ids = [
                id for id in agent_line_ids if id.lower().startswith(agent_line_lower)
            ]
        if allowed_line_ids is not None:
            agent_line_ids = [id for id in agent_line_ids if id in allowed_line_ids]
        if not agent_line_ids:
            return ApiResponse(data=empty_response)
        query = {"_id": {"$in": agent_line_ids}}
    else:
        query = {}
        if allowed_line_ids is not None:
            if agent_line:
                agent_line_lower = agent_line.lower()
                allowed_line_ids = {
                    id
                    for id in allowed_line_ids
                    if id.lower().startswith(agent_line_lower)
                }
                if not allowed_line_ids:
                    return ApiResponse(data=empty_response)
            query["_id"] = {"$in": list(allowed_line_ids)}
        elif agent_line:
            escaped_agent_line = re.escape(agent_line)
            query["_id"] = {"$regex": f"^{escaped_agent_line}", "$options": "i"}

    if department_optimizers is not None:
        query["optimizer"] = {"$in": department_optimizers}

    # 权限: 非 admin/operator_leader 只能看到优化师为自己的代理线
    if not is_admin and Roles.OPERATOR_LEADER not in current_user.roles:
        if (
            department_optimizers is not None
            and current_user.real_name not in department_optimizers
        ):
            return ApiResponse(data=empty_response)
        query["optimizer"] = current_user.real_name

    cursor = agent_collection.find(query).sort("_id", 1)
    if paginate:
        cursor = cursor.skip((current_page - 1) * current_page_size).limit(
            current_page_size
        )
    total, items = await asyncio.gather(
        agent_collection.count_documents(query),
        cursor.to_list(length=None),
    )

    return ApiResponse(
        data={
            "items": items,
            "total": total,
            "page": current_page if paginate else None,
            "page_size": current_page_size if paginate else None,
        }
    )


async def create_agent_lines_batch_logic(
    configs: list[AgentLineConfigCreate],
    current_user: UserModel,
    game_platform: str,
) -> tuple[list[dict], int, list[str]]:
    """
    批量新增代理线的核心逻辑
    返回: (成功创建的代理线ID列表, 更新数量, 被剔除的代理线名称列表)
    """
    # 提取 configs 中所有代理线名称
    input_agent_lines = [config.id for config in configs]

    # 查询这些代理线已经存在于哪些平台中
    cursor = collection.find(
        {"agent_lines": {"$in": input_agent_lines}}, {"_id": 1, "agent_lines": 1}
    )
    # 构建 agent_line -> platform 的映射
    agent_line_to_platform: dict[str, str] = {}
    async for doc in cursor:
        for agent_line in doc.get("agent_lines", []):
            if agent_line in input_agent_lines:
                agent_line_to_platform[agent_line] = doc["_id"]

    # 找出已存在于其他平台的代理线（剔除）
    in_other_platform = [
        agent_line
        for agent_line, platform in agent_line_to_platform.items()
        if platform != game_platform
    ]

    # 剔除已存在于其他平台的配置
    configs = [config for config in configs if config.id not in in_other_platform]

    if not configs:
        return [], 0, in_other_platform

    operations = []
    now = datetime.now()
    for config_in in configs:
        config_data = config_in.model_dump(by_alias=True)
        if config_data["package_url"] and not config_data["history_package_urls"]:
            config_data["history_package_urls"] = [config_data["package_url"]]

        config_data["update_time"] = now
        config_data["created_by"] = current_user.username

        operations.append(
            UpdateOne(
                {"_id": config_data["_id"]},
                {"$set": config_data, "$setOnInsert": {"create_time": now}},
                upsert=True,
            )
        )
    result = await agent_collection.bulk_write(operations)

    # 把所有未在其他平台的 line 都 link 一次:
    # - upserted 的(新建)需要 link;
    # - modified 的可能是孤儿(在 agent_line_config 但不在任何 platform.agent_lines)
    #   或已挂在本平台,$addToSet 幂等,本平台已挂的会自动跳过;
    # 不区分会让"重新导入"自动修复历史孤儿。
    ids_to_link = [config.id for config in configs]
    if ids_to_link:
        await link_agent_lines_to_platform(game_platform, ids_to_link)

    created_ids = list(result.upserted_ids.values())
    return created_ids, result.modified_count, in_other_platform


def build_agent_line_update_doc(
    config_data: dict,
    current_config: dict,
    update_time,
    username: str,
) -> dict:
    history_package_urls = config_data.pop("history_package_urls", None)
    config_data["update_time"] = update_time
    config_data["updated_by"] = username
    new_package_url = config_data.get("package_url")
    old_package_url = current_config.get("package_url")
    update_doc = {"$set": config_data}

    if history_package_urls is not None:
        if new_package_url is not None and new_package_url != old_package_url and old_package_url:
            history_package_urls = [*history_package_urls, new_package_url]
        update_doc["$set"]["history_package_urls"] = list(
            dict.fromkeys(history_package_urls)
        )
        return update_doc

    if new_package_url is not None and new_package_url != old_package_url and old_package_url:
        update_doc["$set"]["history_package_urls"] = list(
            dict.fromkeys(
                [*(current_config.get("history_package_urls") or []), old_package_url]
            )
        )

    return update_doc


async def update_agent_lines_batch_logic(
    configs: list[AgentLineConfigUpdate],
    current_user: UserModel,
) -> tuple[int, int, list[str]]:
    """
    批量更新代理线的核心逻辑（仅更新已存在的记录，不创建新记录）
    返回: (成功更新数量, 不存在的记录数量, 不存在的代理线名称列表)
    """
    # 提取 configs 中所有代理线名称
    input_agent_lines = [config.id for config in configs]

    existing_configs = await agent_collection.find(
        {"_id": {"$in": input_agent_lines}},
        {"_id": 1, "package_url": 1, "history_package_urls": 1},
    ).to_list(length=None)
    existing_config_map = {config["_id"]: config for config in existing_configs}
    existing_agent_lines = set(existing_config_map)

    # 找出不存在的代理线
    not_exist = [
        agent_line
        for agent_line in input_agent_lines
        if agent_line not in existing_agent_lines
    ]

    # 只保留已存在的代理线配置
    configs = [config for config in configs if config.id in existing_agent_lines]

    if not configs:
        return 0, len(not_exist), not_exist

    operations = []
    now = datetime.now()
    for config_in in configs:
        # 只导出非空字段
        config_data = {
            k: v
            for k, v in config_in.model_dump(by_alias=True, exclude_unset=True).items()
            if v is not None
        }

        # 移除 _id，因为它在过滤条件中
        agent_line_id = config_data.pop("_id")

        update_doc = build_agent_line_update_doc(
            config_data,
            existing_config_map[agent_line_id],
            now,
            current_user.username,
        )

        operations.append(
            UpdateOne(
                {"_id": agent_line_id},
                update_doc,
            )
        )

    result = await agent_collection.bulk_write(operations)

    return result.modified_count, len(not_exist), not_exist


# TODO 增加一个参数已存在覆盖
@router.post("/agent-line/parse-file")
async def parse_agent_line_file(
    file: UploadFile = File(...),
    current_user: UserModel = Depends(auth_current_user),
):
    filename = file.filename
    content = await file.read()

    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    elif filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content))
    else:
        return ErrResponse(code=400, message="不支持的文件格式，仅支持 xlsx, xls, csv")

    # 查询有效优化师（operator/operator_leader 角色用户的 real_name）
    valid_optimizers = set(
        await user_cols.user.distinct(
            "real_name",
            {"roles": {"$in": ["operator", "operator_leader"]}, "status": 1},
        )
    )

    # 批量处理列：转字符串、去空白、空值转None
    cols = ["项目", "渠道号", "投放链接", "像素名称", "优化师"]
    not_exist_cols = []
    for col in cols:
        if col in df.columns:
            is_na = df[col].isna()
            df[col] = df[col].astype(str).str.strip()
            df.loc[is_na | (df[col] == "") | (df[col] == "nan"), col] = None
        else:
            not_exist_cols.append(col)
    if cols[0] in not_exist_cols or cols[1] in not_exist_cols:
        return ErrResponse(message=f"未在表格中找到{not_exist_cols}")
    # 过滤必填字段为空的行
    df = df.dropna(subset=["项目", "渠道号"])

    # 查询已存在的项目，_id 就是 game_platform
    valid_platforms = set(await collection.distinct("_id"))
    df_platforms = set(df["项目"].unique())
    invalid_platforms = ", ".join(df_platforms - valid_platforms)

    # 过滤掉项目不存在的行
    df = df[df["项目"].isin(valid_platforms)]

    # 按项目分组处理
    platform_agent_map = {}
    df = df.replace({pd.NA: None, float("nan"): None})
    for row in df.to_dict("records"):
        platform = row["项目"]
        if platform not in platform_agent_map:
            platform_agent_map[platform] = []
        platform_agent_map[platform].append(
            AgentLineConfigCreate(
                _id=row["渠道号"],
                package_url=row.get("投放链接"),
                pixel_name=row.get("像素名称"),
                optimizer=(
                    row.get("优化师") if row.get("优化师") in valid_optimizers else None
                ),
                enabled=True,
            )
        )

    total_created = 0
    existing_count = 0
    all_skipped = []
    # 按平台批量创建并更新 platform_config.agent_lines
    for platform, configs_in in platform_agent_map.items():
        created_ids, modified_count, skipped = await create_agent_lines_batch_logic(
            configs_in, current_user, platform
        )
        total_created += len(created_ids)
        existing_count += modified_count
        all_skipped.extend(skipped)

    message = ""
    if total_created:
        message += f"创建 {total_created} 条. "
    if existing_count:
        message += f"更新 {existing_count} 条. "
    if all_skipped:
        message += f"跳过: [{']['.join(all_skipped)}]. "
    if invalid_platforms:
        message += f"找不到平台: [{invalid_platforms}]. "
    return ApiResponse(data=message)


@router.post("/agent-line/budgets")
async def get_agent_line_budgets(
    ids: list[str],
    current_user: UserModel = Depends(auth_current_user),
):
    """批量查询代理线的预算上下限,返回 [{_id, budget_cap, budget_floor}]"""
    if not ids:
        return ApiResponse(data=[])
    items = await agent_collection.find(
        {"_id": {"$in": ids}},
        {"budget_cap": 1, "budget_floor": 1},
    ).to_list(length=None)
    return ApiResponse(data=items)


@router.post("/agent-line/{game_platform}")
async def create_agent_line_config(
    game_platform: str,
    config_in: AgentLineConfigCreate,
    current_user: UserModel = Depends(auth_current_user),
):
    # 验证平台是否存在，_id 就是 game_platform
    platform = await collection.find_one({"_id": game_platform})
    if not platform:
        return ErrResponse(code=400, message="游戏平台不存在")
    agent_line = await agent_collection.find_one({"_id": config_in.id})
    if agent_line:
        exist = await collection.find_one(
            {"agent_lines": agent_line["_id"]}, {"_id": 1}
        )
        if exist:
            return ErrResponse(
                code=400,
                message=f"该代理线已存在平台[{exist['_id']}]中, 请添加投手后缀",
            )
        # exist is None 表示该 line 是孤儿(在 agent_line_config 但没挂在任何 platform),
        # 不返回错误,让 create_agent_lines_batch_logic 把它挂回当前平台来自愈。
    created_ids, modified_count, skipped = await create_agent_lines_batch_logic(
        [config_in], current_user, game_platform
    )
    if skipped:
        return ErrResponse(
            code=400, message=f"代理线 {skipped[0]} 不在平台的代理线列表中"
        )
    return ApiResponse(data=created_ids[0] if created_ids else None)


@router.put("/agent-line/batch")
async def update_agent_line_configs_batch(
    configs: list[AgentLineConfigUpdate],
    current_user: UserModel = Depends(auth_current_user),
):
    """
    批量更新代理线配置

    - 只更新已存在的代理线，不创建新记录
    - 自动处理投放链接首尾空格
    - Google Play 链接自动设置包类型为 Store

    返回：
    - updated_count: 成功更新的数量
    - not_exist_count: 不存在的记录数量
    - not_exist: 不存在的代理线名称列表
    """
    if not configs:
        return ErrResponse(code=400, message="配置列表不能为空")

    updated_count, not_exist_count, not_exist = await update_agent_lines_batch_logic(
        configs, current_user
    )

    message = ""
    if updated_count:
        message += f"更新 {updated_count} 条. "
    if not_exist_count:
        message += f"不存在: [{']['.join(not_exist)}]. "

    return ApiResponse(
        data={
            "updated_count": updated_count,
            "not_exist_count": not_exist_count,
            "not_exist": not_exist,
        },
        message=message or "批量更新完成",
    )


@router.put("/agent-line/")
async def update_agent_line_config(
    config_update: AgentLineConfigUpdate,
    current_user: UserModel = Depends(auth_current_user),
):
    current_config = await agent_collection.find_one(
        {"_id": config_update.id},
        {"package_url": 1, "history_package_urls": 1},
    )
    if not current_config:
        return ErrResponse(message="代理线只能通过删除新增,不能修改代理线名称")

    update_data = {
        k: v
        for k, v in config_update.model_dump(exclude_unset=True).items()
        if v is not None
    }
    update_data.pop("id")
    update_doc = build_agent_line_update_doc(
        update_data,
        current_config,
        datetime.now().strftime(SecondFormat),
        current_user.username,
    )
    await agent_collection.update_one({"_id": config_update.id}, update_doc)
    updated_config = await agent_collection.find_one({"_id": config_update.id})
    return ApiResponse(data=updated_config)


@router.delete("/agent-line/{config_id}")
async def delete_agent_line_config(
    config_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    # 检查是否存在
    exists = await agent_collection.find_one({"_id": config_id})
    if not exists:
        return ErrResponse(code=status.HTTP_404_NOT_FOUND, message="未找到代理线配置")

    await soft_delete_agent_line(config_id, current_user.username)
    return ApiResponse(data=None, message="代理线配置已删除")


@router.get("/template")
async def download_agent_line_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "模板"
    ws.append(["项目", "渠道号", "投放链接", "像素名称", "优化师"])
    header_font = Font(bold=True, size=14)
    for cell in ws[1]:
        cell.font = header_font
    ws.column_dimensions["A"].width = 15
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 40  # 链接一般拉宽
    ws.column_dimensions["D"].width = 20
    ws.column_dimensions["E"].width = 15
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    file_content = base64.b64encode(output.read()).decode("utf-8")
    return ApiResponse(
        data={
            "filename": "adp导入代理线模板",
            "content": file_content,
        }
    )
